"""
SuperGuard - Rastreador de Objetos/Pessoas
Usa supervision (ByteTrack) para rastrear entidades entre frames
e detectar comportamentos suspeitos como:
- Pessoa com objeto que sai da área sem passar pelo caixa
- Objeto que some do campo de visão junto com a pessoa
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

# Importação condicional do supervision
try:
    import supervision as sv
    SUPERVISION_DISPONIVEL = True
except ImportError:
    SUPERVISION_DISPONIVEL = False


# ── Estruturas de dados ───────────────────────────────────────────────────────

@dataclass
class EstadoPessoa:
    """Estado rastreado de uma pessoa no vídeo."""
    track_id: int
    ultima_bbox: np.ndarray
    ultimo_frame_ts: float = field(default_factory=time.time)
    tinha_objeto: bool = False
    frames_com_objeto: int = 0
    frames_sem_objeto: int = 0
    passou_pelo_caixa: bool = False
    suspeito: bool = False


@dataclass
class EventoSuspeito:
    """Evento de comportamento suspeito detectado pelo tracker."""
    track_id: int
    tipo: str
    score: float
    descricao: str
    timestamp: float = field(default_factory=time.time)


# ── Rastreador principal ──────────────────────────────────────────────────────

class RastreadorFurto:
    """
    Rastreia pessoas e objetos ao longo do tempo para identificar
    comportamentos suspeitos de furto.

    Regra principal: Pessoa que tinha um objeto (por >= MIN_FRAMES_COM_OBJETO frames)
    e de repente o objeto desaparece por >= FRAMES_SEM_OBJETO frames é marcada como
    suspeita — o objeto pode ter sido escondido na roupa ou mochila.
    """

    MIN_FRAMES_COM_OBJETO = 10   # frames mínimos segurando objeto para contar
    FRAMES_SEM_OBJETO = 15       # frames sem objeto para considerar "escondeu"
    TTL_PESSOA = 10.0            # segundos sem aparecer para remover da memória

    def __init__(self, largura_roi_caixa: float = 0.2):
        """
        Args:
            largura_roi_caixa: Fração da largura direita do frame considerada "área do caixa".
                               Pessoas que passam por ali não são marcadas como suspeitas.
        """
        self.largura_roi_caixa = largura_roi_caixa
        self._pessoas: Dict[int, EstadoPessoa] = {}
        self._tracker: Optional[object] = None
        self._inicializar_tracker()

    def _inicializar_tracker(self) -> None:
        """Inicializa o ByteTracker do supervision."""
        if SUPERVISION_DISPONIVEL:
            self._tracker = sv.ByteTracker(
                track_activation_threshold=0.25,
                lost_track_buffer=30,
                minimum_matching_threshold=0.8,
                frame_rate=15,
            )

    def atualizar(
        self,
        deteccoes_pessoas: List[Tuple[np.ndarray, float]],
        deteccoes_objetos: List[Tuple[np.ndarray, float]],
        shape: Tuple[int, ...],
    ) -> List[EventoSuspeito]:
        """
        Atualiza o estado do rastreador com novas detecções e retorna
        lista de eventos suspeitos identificados.

        Args:
            deteccoes_pessoas: Lista de (bbox [x1,y1,x2,y2], confiança)
            deteccoes_objetos: Lista de (bbox [x1,y1,x2,y2], confiança)
            shape: (altura, largura, canais) do frame

        Returns:
            Lista de EventoSuspeito
        """
        altura, largura = shape[:2]
        agora = time.time()

        # Atualiza rastreamento com supervision se disponível
        ids_rastreados = self._atualizar_tracks(deteccoes_pessoas, shape)

        # Atualiza estado de cada pessoa rastreada
        for track_id, bbox in ids_rastreados.items():
            estado = self._pessoas.get(track_id)
            if estado is None:
                estado = EstadoPessoa(track_id=track_id, ultima_bbox=bbox)
                self._pessoas[track_id] = estado

            estado.ultima_bbox = bbox
            estado.ultimo_frame_ts = agora

            # Verifica se está na área do caixa
            centro_x = (bbox[0] + bbox[2]) / 2 / largura
            if centro_x > (1.0 - self.largura_roi_caixa):
                estado.passou_pelo_caixa = True

            # Verifica se tem objeto próximo
            tem_objeto_agora = self._pessoa_tem_objeto(bbox, deteccoes_objetos)

            if tem_objeto_agora:
                estado.tinha_objeto = True
                estado.frames_com_objeto += 1
                estado.frames_sem_objeto = 0
            elif estado.tinha_objeto:
                estado.frames_sem_objeto += 1

        # Remove pessoas expiradas
        ids_expirados = [
            tid for tid, e in self._pessoas.items()
            if agora - e.ultimo_frame_ts > self.TTL_PESSOA
        ]
        for tid in ids_expirados:
            del self._pessoas[tid]

        # Detecta eventos suspeitos
        return self._detectar_eventos()

    def _atualizar_tracks(
        self,
        deteccoes_pessoas: List[Tuple[np.ndarray, float]],
        shape: Tuple[int, ...],
    ) -> Dict[int, np.ndarray]:
        """Retorna mapeamento track_id -> bbox das pessoas rastreadas."""
        if not deteccoes_pessoas:
            return {}

        if not SUPERVISION_DISPONIVEL or self._tracker is None:
            # Fallback simples sem rastreamento real (usa índice como ID)
            return {i: bbox for i, (bbox, _) in enumerate(deteccoes_pessoas)}

        # Converte para formato supervision
        bboxes = np.array([bbox for bbox, _ in deteccoes_pessoas])
        confs = np.array([conf for _, conf in deteccoes_pessoas])
        class_ids = np.zeros(len(deteccoes_pessoas), dtype=int)

        detections = sv.Detections(
            xyxy=bboxes,
            confidence=confs,
            class_id=class_ids,
        )

        tracks = self._tracker.update_with_detections(detections)

        if tracks.tracker_id is None:
            return {}

        return {
            int(tid): bbox
            for tid, bbox in zip(tracks.tracker_id, tracks.xyxy)
        }

    def _pessoa_tem_objeto(
        self,
        bbox_pessoa: np.ndarray,
        objetos: List[Tuple[np.ndarray, float]],
        limiar_iou: float = 0.1,
    ) -> bool:
        """Verifica se algum objeto está dentro/sobreposto ao bounding box da pessoa."""
        px1, py1, px2, py2 = bbox_pessoa
        for bbox_obj, _ in objetos:
            ox1, oy1, ox2, oy2 = bbox_obj
            ix1, iy1 = max(px1, ox1), max(py1, oy1)
            ix2, iy2 = min(px2, ox2), min(py2, oy2)
            if ix2 > ix1 and iy2 > iy1:
                area_intersecao = (ix2 - ix1) * (iy2 - iy1)
                area_obj = max((ox2 - ox1) * (oy2 - oy1), 1)
                if area_intersecao / area_obj >= limiar_iou:
                    return True
        return False

    def _detectar_eventos(self) -> List[EventoSuspeito]:
        """Varre estados das pessoas e gera eventos suspeitos."""
        eventos: List[EventoSuspeito] = []

        for estado in self._pessoas.values():
            if estado.passou_pelo_caixa or estado.suspeito:
                continue

            # Pessoa tinha objeto por tempo suficiente e agora ele sumiu
            if (
                estado.tinha_objeto
                and estado.frames_com_objeto >= self.MIN_FRAMES_COM_OBJETO
                and estado.frames_sem_objeto >= self.FRAMES_SEM_OBJETO
            ):
                # Score baseado em quanto tempo ficou com o objeto vs sem
                score = min(
                    0.6
                    + (estado.frames_com_objeto / 30) * 0.2
                    + (estado.frames_sem_objeto / 30) * 0.2,
                    0.95,
                )
                evento = EventoSuspeito(
                    track_id=estado.track_id,
                    tipo="objeto_desaparecido",
                    score=score,
                    descricao=(
                        f"Pessoa ID {estado.track_id} tinha objeto por "
                        f"{estado.frames_com_objeto} frames e sumiu por "
                        f"{estado.frames_sem_objeto} frames sem passar pelo caixa."
                    ),
                )
                eventos.append(evento)
                estado.suspeito = True  # Evita duplicar alertas

        return eventos
