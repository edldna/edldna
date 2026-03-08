"""
SuperGuard - Worker Principal de Visão Computacional
Gerencia múltiplas câmeras em paralelo com threading,
processa frames com YOLO e envia alertas via API interna.
"""

from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import cv2
import httpx
import numpy as np
from loguru import logger

from app.core.config import settings
from app.cv.detector import DetectorFurto, DeteccaoFurto
from app.cv.tracker import RastreadorFurto


# ── Configuração de logging ───────────────────────────────────────────────────

logger.add(
    "logs/cv_worker.log",
    rotation="100 MB",
    retention="30 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
)


# ── Worker por câmera ─────────────────────────────────────────────────────────

class CameraWorker(threading.Thread):
    """
    Thread dedicada a uma única câmera.
    Captura frames, detecta furtos e coloca alertas na fila.
    """

    def __init__(
        self,
        camera_id: int,
        camera_nome: str,
        camera_url: str,
        alerta_queue: queue.Queue,
        detector: DetectorFurto,
        fps_alvo: int = 15,
        debounce_segundos: int = 30,
    ):
        super().__init__(daemon=True, name=f"CamWorker-{camera_id:02d}")
        self.camera_id = camera_id
        self.camera_nome = camera_nome
        self.camera_url = camera_url
        self.alerta_queue = alerta_queue
        self.detector = detector
        self.fps_alvo = fps_alvo
        self.debounce_segundos = debounce_segundos

        self._parar = threading.Event()
        self._ultimo_alerta_ts: float = 0.0
        self._rastreador = RastreadorFurto()
        self._reconexoes = 0

    def run(self) -> None:
        """Loop principal de captura e processamento."""
        intervalo_frame = 1.0 / self.fps_alvo
        logger.info(f"[Câmera {self.camera_id:02d}] Iniciando worker: {self.camera_url}")

        while not self._parar.is_set():
            cap = self._conectar()
            if cap is None:
                logger.warning(f"[Câmera {self.camera_id:02d}] Aguardando reconexão...")
                time.sleep(5)
                continue

            logger.info(f"[Câmera {self.camera_id:02d}] Conectado com sucesso.")
            self._reconexoes = 0

            try:
                self._processar_stream(cap, intervalo_frame)
            except Exception as e:
                logger.error(f"[Câmera {self.camera_id:02d}] Erro no stream: {e}")
            finally:
                cap.release()

    def _conectar(self) -> Optional[cv2.VideoCapture]:
        """Tenta conectar à câmera. Retorna VideoCapture ou None."""
        self._reconexoes += 1
        if self._reconexoes > 10:
            logger.error(
                f"[Câmera {self.camera_id:02d}] Muitas tentativas de reconexão. "
                "Verifique a URL da câmera."
            )
            self._parar.set()
            return None

        cap = cv2.VideoCapture(self.camera_url)
        if not cap.isOpened():
            return None

        # Configura buffer mínimo para reduzir latência
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _processar_stream(
        self, cap: cv2.VideoCapture, intervalo_frame: float
    ) -> None:
        """Processa frames do stream continuamente."""
        while not self._parar.is_set():
            inicio = time.monotonic()
            ret, frame = cap.read()

            if not ret or frame is None:
                logger.warning(f"[Câmera {self.camera_id:02d}] Frame inválido. Reconectando...")
                break

            # Detecta furto no frame atual
            self._analisar_frame(frame)

            # Controle de FPS
            elapsed = time.monotonic() - inicio
            sleep_time = intervalo_frame - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _analisar_frame(self, frame: np.ndarray) -> None:
        """Analisa um frame e gera alerta se furto for detectado."""
        deteccao = self.detector.detectar(
            frame,
            camera_id=self.camera_id,
            camera_nome=self.camera_nome,
        )

        if deteccao is None:
            return

        # Debounce: ignora se já enviou alerta recentemente para esta câmera
        agora = time.time()
        if agora - self._ultimo_alerta_ts < self.debounce_segundos:
            logger.debug(
                f"[Câmera {self.camera_id:02d}] Alerta suprimido pelo debounce "
                f"({self.debounce_segundos}s)."
            )
            return

        self._ultimo_alerta_ts = agora

        # Salva foto do alerta
        deteccao.salvar_foto(settings.alerts_dir)
        logger.info(
            f"[Câmera {self.camera_id:02d}] ALERTA! Confiança: {deteccao.confianca:.0%} "
            f"| Foto: {deteccao.foto_path}"
        )

        # Coloca na fila para envio
        self.alerta_queue.put(deteccao)

    def parar(self) -> None:
        """Sinaliza o worker para encerrar."""
        self._parar.set()


# ── Gerenciador de alertas (envia para API) ───────────────────────────────────

class GerenciadorAlertas(threading.Thread):
    """
    Thread que consome alertas da fila e os registra via API interna.
    A API cuida de notificar o bot Telegram e salvar no banco.
    """

    API_BASE = "http://api:8000"

    def __init__(self, alerta_queue: queue.Queue):
        super().__init__(daemon=True, name="AlertaManager")
        self.alerta_queue = alerta_queue
        self._parar = threading.Event()

    def run(self) -> None:
        logger.info("Gerenciador de alertas iniciado.")
        while not self._parar.is_set():
            try:
                deteccao: DeteccaoFurto = self.alerta_queue.get(timeout=1)
                self._enviar_alerta(deteccao)
                self.alerta_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Erro ao processar alerta: {e}")

    def _enviar_alerta(self, deteccao: DeteccaoFurto) -> None:
        """Envia alerta para a API interna via HTTP."""
        payload = {
            "camera_id": deteccao.camera_id,
            "camera_nome": deteccao.camera_nome,
            "confianca": deteccao.confianca,
            "foto_path": deteccao.foto_path,
            "descricao": deteccao.descricao,
            "detectado_em": deteccao.timestamp.isoformat(),
        }

        tentativas = 3
        for tentativa in range(tentativas):
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(
                        f"{self.API_BASE}/api/alertas/interno",
                        json=payload,
                        headers={"X-Worker-Key": os.environ.get("WORKER_SECRET", "superguard")},
                    )
                    resp.raise_for_status()
                    logger.info(
                        f"Alerta câmera {deteccao.camera_id:02d} registrado. "
                        f"ID: {resp.json().get('id')}"
                    )
                    return
            except Exception as e:
                logger.warning(
                    f"Falha ao enviar alerta (tentativa {tentativa+1}/{tentativas}): {e}"
                )
                time.sleep(2 * (tentativa + 1))

        logger.error(
            f"Não foi possível registrar alerta da câmera {deteccao.camera_id:02d} "
            "após todas as tentativas."
        )

    def parar(self) -> None:
        self._parar.set()


# ── Ponto de entrada principal ────────────────────────────────────────────────

def main() -> None:
    """
    Inicializa todos os workers de câmera e o gerenciador de alertas.
    Lê configurações do ambiente.
    """
    logger.info("=" * 60)
    logger.info("SuperGuard CV Worker iniciando...")
    logger.info(f"Loja: {settings.store_name}")
    logger.info(f"FPS alvo: {settings.target_fps} | Debounce: {settings.debounce_segundos}s")
    logger.info(f"Confiança mínima: {settings.detection_confidence:.0%}")
    logger.info("=" * 60)

    camera_urls = settings.camera_url_list
    camera_nomes = settings.camera_name_list

    if not camera_urls:
        logger.error(
            "Nenhuma câmera configurada! "
            "Defina CAMERA_URLS no arquivo .env e reinicie o serviço."
        )
        return

    # Fila compartilhada de alertas
    alerta_queue: queue.Queue[DeteccaoFurto] = queue.Queue(maxsize=100)

    # Detector YOLO compartilhado entre cameras (modelo carregado uma vez)
    detector = DetectorFurto(
        modelo_path="yolo11n.pt",
        confianca_minima=settings.detection_confidence,
    )

    # Inicia workers de câmera
    workers: List[CameraWorker] = []
    for idx, (url, nome) in enumerate(zip(camera_urls, camera_nomes)):
        worker = CameraWorker(
            camera_id=idx + 1,
            camera_nome=nome,
            camera_url=url,
            alerta_queue=alerta_queue,
            detector=detector,
            fps_alvo=settings.target_fps,
            debounce_segundos=settings.debounce_segundos,
        )
        worker.start()
        workers.append(worker)
        logger.info(f"Worker iniciado: [{nome}] {url}")

    # Inicia gerenciador de alertas
    gerenciador = GerenciadorAlertas(alerta_queue)
    gerenciador.start()

    logger.info(
        f"{len(workers)} câmera(s) em monitoramento. "
        "Sistema operacional. Pressione Ctrl+C para encerrar."
    )

    try:
        while True:
            # Verifica saúde dos workers a cada 30s
            time.sleep(30)
            workers_ativos = sum(1 for w in workers if w.is_alive())
            logger.info(
                f"Status: {workers_ativos}/{len(workers)} câmeras ativas | "
                f"Alertas na fila: {alerta_queue.qsize()}"
            )
    except KeyboardInterrupt:
        logger.info("Encerrando SuperGuard CV Worker...")
    finally:
        for w in workers:
            w.parar()
        gerenciador.parar()
        logger.info("Sistema encerrado.")


if __name__ == "__main__":
    main()
