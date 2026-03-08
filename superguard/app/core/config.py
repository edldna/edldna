"""
SuperGuard - Configurações centrais via Pydantic Settings
Lê variáveis do arquivo .env automaticamente
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Todas as configurações do sistema carregadas do ambiente / .env"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Banco de dados ---
    database_url: str = (
        "postgresql+asyncpg://superguard:superguard123@localhost:5432/superguard"
    )

    # --- JWT ---
    secret_key: str = "TROQUE_ESTA_CHAVE_SECRETA"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""

    # --- Câmeras ---
    camera_urls: str = ""
    camera_names: str = ""

    # --- Supermercado ---
    store_name: str = "Supermercado Central"

    # --- Detecção ---
    detection_confidence: float = 0.75
    debounce_seconds: int = 30
    target_fps: int = 15

    # --- Armazenamento ---
    alerts_dir: str = "/app/alerts"

    # --- Ambiente ---
    environment: str = "development"

    # ── Propriedades derivadas ────────────────────────────────────────────────

    @property
    def camera_url_list(self) -> List[str]:
        """Retorna lista de URLs de câmeras."""
        if not self.camera_urls:
            return []
        return [u.strip() for u in self.camera_urls.split(",") if u.strip()]

    @property
    def camera_name_list(self) -> List[str]:
        """Retorna lista de nomes de câmeras."""
        if not self.camera_names:
            return [f"Câmera {i+1:02d}" for i in range(len(self.camera_url_list))]
        names = [n.strip() for n in self.camera_names.split(",") if n.strip()]
        # Preenche com nomes genéricos se houver mais URLs do que nomes
        while len(names) < len(self.camera_url_list):
            names.append(f"Câmera {len(names)+1:02d}")
        return names

    @property
    def debounce_segundos(self) -> int:
        """Alias para debounce_seconds em português (compatibilidade)."""
        return self.debounce_seconds

    @field_validator("detection_confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("detection_confidence deve ser entre 0.0 e 1.0")
        return v


@lru_cache
def get_settings() -> Settings:
    """Retorna instância cacheada das configurações."""
    return Settings()


# Instância global para uso direto
settings = get_settings()
