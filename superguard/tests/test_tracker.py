"""
SuperGuard - Testes do Rastreador de Objetos
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from app.cv.tracker import RastreadorFurto, EstadoPessoa


class TestRastreadorFurto:

    @pytest.fixture
    def rastreador(self):
        return RastreadorFurto()

    def test_sem_deteccoes_retorna_vazio(self, rastreador):
        """Sem detecções, não deve retornar eventos."""
        eventos = rastreador.atualizar([], [], (480, 640, 3))
        assert eventos == []

    def test_pessoa_com_objeto_nao_gera_evento_imediato(self, rastreador):
        """Pessoa com objeto logo detectada não deve gerar evento ainda."""
        bbox_pessoa = np.array([100, 100, 300, 400])
        bbox_objeto = np.array([150, 150, 250, 300])

        eventos = rastreador.atualizar(
            deteccoes_pessoas=[(bbox_pessoa, 0.9)],
            deteccoes_objetos=[(bbox_objeto, 0.9)],
            shape=(480, 640, 3),
        )
        assert len(eventos) == 0

    def test_pessoa_tem_objeto_detecta_sobreposicao(self, rastreador):
        """Método _pessoa_tem_objeto deve detectar objeto dentro do bbox."""
        bbox_pessoa = np.array([50, 50, 400, 450])
        bbox_objeto = np.array([100, 100, 200, 200])

        tem = rastreador._pessoa_tem_objeto(bbox_pessoa, [(bbox_objeto, 0.9)])
        assert tem is True

    def test_pessoa_nao_tem_objeto_sem_sobreposicao(self, rastreador):
        """Sem sobreposição suficiente, objeto não é contado."""
        bbox_pessoa = np.array([0, 0, 100, 100])
        bbox_objeto = np.array([500, 400, 600, 480])

        tem = rastreador._pessoa_tem_objeto(bbox_pessoa, [(bbox_objeto, 0.9)])
        assert tem is False

    def test_evento_suspeito_quando_objeto_some(self, rastreador):
        """
        Simula pessoa que tinha objeto por muitos frames e depois o objeto desaparece.
        Deve gerar evento suspeito.
        """
        track_id = 99

        # Insere estado manualmente simulando histórico
        estado = EstadoPessoa(
            track_id=track_id,
            ultima_bbox=np.array([100, 100, 300, 400]),
            tinha_objeto=True,
            frames_com_objeto=RastreadorFurto.MIN_FRAMES_COM_OBJETO + 5,
            frames_sem_objeto=RastreadorFurto.FRAMES_SEM_OBJETO + 5,
            passou_pelo_caixa=False,
        )
        rastreador._pessoas[track_id] = estado

        eventos = rastreador._detectar_eventos()

        assert len(eventos) == 1
        assert eventos[0].track_id == track_id
        assert eventos[0].tipo == "objeto_desaparecido"
        assert 0.0 < eventos[0].score <= 1.0

    def test_nao_duplica_eventos_para_mesma_pessoa(self, rastreador):
        """Após gerar evento, não deve gerar novamente para a mesma pessoa."""
        track_id = 77

        estado = EstadoPessoa(
            track_id=track_id,
            ultima_bbox=np.array([100, 100, 300, 400]),
            tinha_objeto=True,
            frames_com_objeto=50,
            frames_sem_objeto=50,
            passou_pelo_caixa=False,
        )
        rastreador._pessoas[track_id] = estado

        eventos1 = rastreador._detectar_eventos()
        eventos2 = rastreador._detectar_eventos()

        assert len(eventos1) == 1
        assert len(eventos2) == 0  # Não duplica

    def test_pessoa_que_passou_pelo_caixa_nao_gera_evento(self, rastreador):
        """Pessoa que passou pelo caixa não deve ser marcada como suspeita."""
        track_id = 55

        estado = EstadoPessoa(
            track_id=track_id,
            ultima_bbox=np.array([580, 100, 640, 400]),
            tinha_objeto=True,
            frames_com_objeto=50,
            frames_sem_objeto=50,
            passou_pelo_caixa=True,  # ← passou pelo caixa
        )
        rastreador._pessoas[track_id] = estado

        eventos = rastreador._detectar_eventos()
        assert len(eventos) == 0
