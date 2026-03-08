"""
SuperGuard - Detector de Furtos com YOLO
Usa Ultralytics YOLO para detectar pessoas e objetos suspeitos
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

from app.core.config import settings

# Importação condicional do YOLO para permitir testes sem GPU
try:
    from ultralytics import YOLO
    YOLO_DISPONIVEL = True
except ImportError:
    YOLO_DISPONIVEL = False


# ── Estruturas de dados ───────────────────────────────────────────────────────

@dataclass
class DeteccaoFurto:
    """Resultado de uma detecção de furto em um frame."""
    camera_id: int
    camera_nome: str
    confianca: float
    frame: np.ndarray
    timestamp: datetime = field(default_factory=datetime.now)
    descricao: str = ""
    foto_path: str = ""

    def salvar_foto(self, diretorio: str) -> str:
        """Salva o frame como imagem JPEG e retorna o caminho."""
        Path(diretorio).mkdir(parents=True, exist_ok=True)
        ts = self.timestamp.strftime("%Y%m%d_%H%M%S")
        nome_arquivo = f"alerta_cam{self.camera_id:02d}_{ts}_{int(self.confianca*100):03d}.jpg"
        caminho = os.path.join(diretorio, nome_arquivo)
        cv2.imwrite(caminho, self.frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        self.foto_path = caminho
        return caminho


# ── Classes de detecção ───────────────────────────────────────────────────────

class DetectorFurto:
    """
    Detecta comportamentos suspeitos de furto usando YOLO.

    Lógica de detecção:
    1. Detecta todas as pessoas e objetos no frame
    2. Verifica se alguma pessoa está segurando/escondendo objetos
    3. Aplica scoring baseado em: proximidade pessoa-objeto, bbox overlap, área relativa
    4. Retorna detecção se score superar o limiar configurado
    """

    # Classes COCO relevantes para detecção de furto
    CLASSES_PESSOAS = {0}  # person
    CLASSES_OBJETOS = {
        24,  # backpack (mochila)
        25,  # umbrella
        26,  # handbag (bolsa)
        28,  # suitcase (mala)
        39,  # bottle (garrafa)
        40,  # wine glass
        41,  # cup (copo)
        46,  # banana
        47,  # apple
        48,  # sandwich
        49,  # orange
        56,  # chair
        63,  # laptop
        64,  # mouse
        65,  # remote
        66,  # keyboard
        67,  # cell phone
        73,  # book
        74,  # clock
        75,  # vase
        76,  # scissors
        77,  # teddy bear
        79,  # toothbrush
    }

    def __init__(
        self,
        modelo_path: str = "yolo11n.pt",
        confianca_minima: float = None,
    ):
        self.confianca_minima = confianca_minima or settings.detection_confidence
        self.modelo_path = modelo_path
        self._modelo = None

    def _carregar_modelo(self) -> None:
        """Carrega o modelo YOLO (lazy loading)."""
        if self._modelo is None:
            if not YOLO_DISPONIVEL:
                raise RuntimeError("Ultralytics YOLO não está instalado.")
            # YOLOv11 nano por padrão; substituir por modelo treinado se disponível
            self._modelo = YOLO(self.modelo_path)

    def detectar(
        self,
        frame: np.ndarray,
        camera_id: int = 0,
        camera_nome: str = "Câmera 01",
    ) -> DeteccaoFurto | None:
        """
        Processa um frame e retorna DeteccaoFurto se atividade suspeita for detectada.

        Args:
            frame: Frame BGR do OpenCV
            camera_id: ID da câmera
            camera_nome: Nome legível da câmera

        Returns:
            DeteccaoFurto ou None
        """
        self._carregar_modelo()

        # Inferência YOLO
        resultados = self._modelo.predict(
            frame,
            conf=0.3,  # Limiar baixo aqui; scoring próprio será mais rigoroso
            verbose=False,
            device="cpu",  # Fallback para CPU; YOLO detecta GPU automaticamente
        )

        if not resultados:
            return None

        resultado = resultados[0]
        boxes = resultado.boxes

        if boxes is None or len(boxes) == 0:
            return None

        # Separa pessoas e objetos detectados
        pessoas: List[Tuple[np.ndarray, float]] = []
        objetos: List[Tuple[np.ndarray, float]] = []

        for box in boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            bbox = box.xyxy[0].cpu().numpy()  # [x1, y1, x2, y2]

            if cls_id in self.CLASSES_PESSOAS:
                pessoas.append((bbox, conf))
            elif cls_id in self.CLASSES_OBJETOS:
                objetos.append((bbox, conf))

        if not pessoas or not objetos:
            return None

        # Calcula score de suspeita
        score = self._calcular_score_suspeita(pessoas, objetos, frame.shape)

        if score < self.confianca_minima:
            return None

        # Anota o frame com as detecções
        frame_anotado = self._anotar_frame(frame.copy(), resultado, score, camera_nome)

        descricao = (
            f"Objeto suspeito detectado próximo a pessoa. "
            f"Score: {score:.0%} | Pessoas: {len(pessoas)} | Objetos: {len(objetos)}"
        )

        return DeteccaoFurto(
            camera_id=camera_id,
            camera_nome=camera_nome,
            confianca=score,
            frame=frame_anotado,
            descricao=descricao,
        )

    def _calcular_score_suspeita(
        self,
        pessoas: List[Tuple[np.ndarray, float]],
        objetos: List[Tuple[np.ndarray, float]],
        shape: Tuple[int, ...],
    ) -> float:
        """
        Calcula pontuação de suspeita baseada em:
        - Sobreposição (IoU) entre pessoa e objeto
        - Proximidade relativa
        - Confiança das detecções individuais
        """
        altura, largura = shape[:2]
        area_frame = altura * largura

        score_maximo = 0.0

        for bbox_pessoa, conf_pessoa in pessoas:
            px1, py1, px2, py2 = bbox_pessoa
            area_pessoa = (px2 - px1) * (py2 - py1)

            for bbox_objeto, conf_objeto in objetos:
                ox1, oy1, ox2, oy2 = bbox_objeto

                # Calcula sobreposição (interseção)
                ix1 = max(px1, ox1)
                iy1 = max(py1, oy1)
                ix2 = min(px2, ox2)
                iy2 = min(py2, oy2)

                if ix2 > ix1 and iy2 > iy1:
                    area_intersecao = (ix2 - ix1) * (iy2 - iy1)
                    area_objeto = (ox2 - ox1) * (oy2 - oy1)

                    # Razão: objeto contido na área da pessoa
                    razao_sobreposicao = area_intersecao / max(area_objeto, 1)

                    # Objeto pequeno relativo à pessoa (pode estar sendo escondido)
                    razao_tamanho = area_objeto / max(area_pessoa, 1)
                    # Penaliza objetos muito grandes (menos suspeito) ou muito pequenos (ruído).
                    # O valor ideal é ~15% do tamanho da pessoa (produto de bolso/mão típico)
                    fator_tamanho = 1.0 - abs(razao_tamanho - 0.15) * 2

                    # Score combinado
                    score = (
                        razao_sobreposicao * 0.5
                        + conf_pessoa * 0.25
                        + conf_objeto * 0.25
                        + max(fator_tamanho, 0) * 0.1
                    )
                    score_maximo = max(score_maximo, min(score, 1.0))

                else:
                    # Não há sobreposição direta; verifica proximidade
                    centro_pessoa = np.array([(px1 + px2) / 2, (py1 + py2) / 2])
                    centro_objeto = np.array([(ox1 + ox2) / 2, (oy1 + oy2) / 2])
                    distancia = np.linalg.norm(centro_pessoa - centro_objeto)
                    distancia_normalizada = distancia / (max(largura, altura))

                    # Objetos muito próximos mas sem sobreposição também são suspeitos
                    if distancia_normalizada < 0.1:
                        score = conf_pessoa * 0.4 + conf_objeto * 0.4 - distancia_normalizada
                        score_maximo = max(score_maximo, max(score, 0.0))

        return score_maximo

    def _anotar_frame(
        self,
        frame: np.ndarray,
        resultado,
        score: float,
        camera_nome: str,
    ) -> np.ndarray:
        """
        Anota o frame com bounding boxes, labels e pontuação de suspeita.
        Retorna frame anotado em BGR.
        """
        # Usa o plot nativo do YOLO para anotar detecções
        frame_anotado = resultado.plot(img=frame)

        # Adiciona overlay de alerta no topo
        overlay = frame_anotado.copy()
        h, w = frame_anotado.shape[:2]
        cv2.rectangle(overlay, (0, 0), (w, 60), (0, 0, 180), -1)
        cv2.addWeighted(overlay, 0.6, frame_anotado, 0.4, 0, frame_anotado)

        timestamp_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        texto = f"ALERTA - {camera_nome} - {timestamp_str} - Confianca: {score:.0%}"
        cv2.putText(
            frame_anotado,
            texto,
            (10, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        return frame_anotado
