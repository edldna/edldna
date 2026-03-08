"""
SuperGuard - Testes Unitários do Detector de Furtos
Testa a lógica de detecção sem necessitar de GPU ou câmera real.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.cv.detector import DetectorFurto, DeteccaoFurto


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def frame_dummy() -> np.ndarray:
    """Frame BGR sintético de 480x640."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def detector(monkeypatch):
    """
    Instância do DetectorFurto com YOLO mockado.
    O modelo real não é carregado; apenas a lógica de scoring é testada.
    """
    det = DetectorFurto(confianca_minima=0.5)

    class ModeloMock:
        def predict(self, frame, **kwargs):
            return []

    det._modelo = ModeloMock()
    return det


# ── Testes de scoring ─────────────────────────────────────────────────────────

class TestCalcularScoreSuspeita:

    def test_sem_pessoas_retorna_zero(self, detector):
        """Score deve ser 0 quando não há pessoas."""
        score = detector._calcular_score_suspeita(
            pessoas=[],
            objetos=[
                (np.array([100, 100, 200, 200]), 0.9),
            ],
            shape=(480, 640, 3),
        )
        assert score == 0.0

    def test_sem_objetos_retorna_zero(self, detector):
        """Score deve ser 0 quando não há objetos."""
        score = detector._calcular_score_suspeita(
            pessoas=[
                (np.array([100, 100, 300, 400]), 0.9),
            ],
            objetos=[],
            shape=(480, 640, 3),
        )
        assert score == 0.0

    def test_objeto_dentro_da_pessoa_gera_score_alto(self, detector):
        """Objeto completamente dentro do bbox da pessoa → score alto."""
        bbox_pessoa = np.array([50, 50, 400, 450])   # grande
        bbox_objeto = np.array([100, 100, 200, 200])  # pequeno, dentro da pessoa

        score = detector._calcular_score_suspeita(
            pessoas=[(bbox_pessoa, 0.95)],
            objetos=[(bbox_objeto, 0.90)],
            shape=(480, 640, 3),
        )
        # Objeto está 100% dentro da pessoa → score deve ser significativo
        assert score > 0.4, f"Score esperado > 0.4, obtido: {score:.4f}"

    def test_objeto_longe_gera_score_baixo(self, detector):
        """Objeto muito longe da pessoa → score baixo."""
        bbox_pessoa = np.array([0, 0, 100, 100])
        bbox_objeto = np.array([500, 400, 600, 480])  # canto oposto

        score = detector._calcular_score_suspeita(
            pessoas=[(bbox_pessoa, 0.8)],
            objetos=[(bbox_objeto, 0.8)],
            shape=(480, 640, 3),
        )
        # Sem sobreposição e muito longe → score baixo (< 0.5)
        assert score < 0.5, f"Score deveria ser < 0.5, obtido: {score:.4f}"

    def test_score_entre_zero_e_um(self, detector):
        """Score sempre deve estar em [0, 1]."""
        bbox_pessoa = np.array([0, 0, 640, 480])
        bbox_objeto = np.array([10, 10, 100, 100])

        score = detector._calcular_score_suspeita(
            pessoas=[(bbox_pessoa, 1.0)],
            objetos=[(bbox_objeto, 1.0)],
            shape=(480, 640, 3),
        )
        assert 0.0 <= score <= 1.0


# ── Testes de salvamento de foto ──────────────────────────────────────────────

class TestDeteccaoFurto:

    def test_salvar_foto_cria_arquivo(self, tmp_path, frame_dummy):
        """Salvar foto deve criar arquivo JPEG no diretório especificado."""
        deteccao = DeteccaoFurto(
            camera_id=1,
            camera_nome="Câmera 01",
            confianca=0.85,
            frame=frame_dummy,
        )
        caminho = deteccao.salvar_foto(str(tmp_path))

        assert caminho.endswith(".jpg")
        assert (tmp_path / caminho.split("/")[-1]).exists()
        assert deteccao.foto_path == caminho

    def test_salvar_foto_cria_diretorio_se_necessario(self, tmp_path, frame_dummy):
        """Deve criar o diretório automaticamente se não existir."""
        novo_dir = str(tmp_path / "alertas" / "novos")
        deteccao = DeteccaoFurto(
            camera_id=2,
            camera_nome="Câmera 02",
            confianca=0.75,
            frame=frame_dummy,
        )
        caminho = deteccao.salvar_foto(novo_dir)
        assert caminho.endswith(".jpg")

    def test_nome_arquivo_contem_camera_id(self, tmp_path, frame_dummy):
        """Nome do arquivo deve conter o ID da câmera."""
        deteccao = DeteccaoFurto(
            camera_id=3,
            camera_nome="Câmera 03",
            confianca=0.80,
            frame=frame_dummy,
        )
        caminho = deteccao.salvar_foto(str(tmp_path))
        nome = caminho.split("/")[-1]
        assert "cam03" in nome

    def test_nome_arquivo_contem_score(self, tmp_path, frame_dummy):
        """Nome do arquivo deve conter a pontuação de confiança."""
        deteccao = DeteccaoFurto(
            camera_id=1,
            camera_nome="Câmera 01",
            confianca=0.89,
            frame=frame_dummy,
        )
        caminho = deteccao.salvar_foto(str(tmp_path))
        nome = caminho.split("/")[-1]
        assert "089" in nome  # 89% → "089"
