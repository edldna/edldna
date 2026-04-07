"""
SuperGuard - Modelos do banco de dados (SQLAlchemy 2.0)
Define as tabelas: usuarios, cameras, alertas
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings


# ── Motor assíncrono ──────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base declarativa ──────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Enums ─────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    """Nível de permissão do usuário no sistema."""
    admin = "admin"
    seguranca = "seguranca"


class AlertType(str, enum.Enum):
    """Tipo de evento detectado."""
    furto = "furto"
    comportamento_suspeito = "comportamento_suspeito"
    objeto_abandonado = "objeto_abandonado"


class CameraStatus(str, enum.Enum):
    """Estado operacional da câmera."""
    ativa = "ativa"
    inativa = "inativa"
    erro = "erro"


# ── Tabela: usuarios ──────────────────────────────────────────────────────────

class User(Base):
    """Usuários autorizados a receber alertas via Telegram e acessar o painel."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    nome: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.seguranca, nullable=False
    )
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Senha hasheada para acesso ao painel web (opcional para usuários só Telegram)
    hashed_password: Mapped[str | None] = mapped_column(String(512), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} nome={self.nome!r} role={self.role}>"


# ── Tabela: cameras ───────────────────────────────────────────────────────────

class Camera(Base):
    """Câmeras cadastradas no sistema."""

    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)  # URL RTSP ou HTTP
    localizacao: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[CameraStatus] = mapped_column(
        Enum(CameraStatus, name="camera_status"),
        default=CameraStatus.ativa,
        nullable=False,
    )
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Camera id={self.id} nome={self.nome!r} status={self.status}>"


# ── Tabela: alertas ───────────────────────────────────────────────────────────

class Alert(Base):
    """Registro de eventos de furto/roubo detectados."""

    __tablename__ = "alertas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    camera_nome: Mapped[str] = mapped_column(String(128), nullable=False)
    tipo: Mapped[AlertType] = mapped_column(
        Enum(AlertType, name="alert_type"), default=AlertType.furto, nullable=False
    )
    confianca: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0 a 1.0
    foto_path: Mapped[str | None] = mapped_column(Text, nullable=True)  # Caminho do frame salvo
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_enviado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    detectado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<Alert id={self.id} camera={self.camera_nome!r} confianca={self.confianca:.0%}>"


# ── Dependency injection para FastAPI ────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Fornece sessão do banco para injeção de dependência no FastAPI."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
