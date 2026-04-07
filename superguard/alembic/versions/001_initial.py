"""Criação inicial das tabelas: usuarios, cameras, alertas

Revision ID: 001
Revises: 
Create Date: 2026-03-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum types ────────────────────────────────────────────────────────────
    op.execute("CREATE TYPE IF NOT EXISTS user_role AS ENUM ('admin', 'seguranca')")
    op.execute("CREATE TYPE IF NOT EXISTS camera_status AS ENUM ('ativa', 'inativa', 'erro')")
    op.execute("CREATE TYPE IF NOT EXISTS alert_type AS ENUM ('furto', 'comportamento_suspeito', 'objeto_abandonado')")

    # ── Tabela: usuarios ──────────────────────────────────────────────────────
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("chat_id", sa.String(64), nullable=False),
        sa.Column("username", sa.String(128), nullable=True),
        sa.Column("nome", sa.String(256), nullable=False),
        sa.Column("role", sa.Enum("admin", "seguranca", name="user_role"), nullable=False, server_default="seguranca"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("hashed_password", sa.String(512), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id"),
    )
    op.create_index("ix_usuarios_chat_id", "usuarios", ["chat_id"])

    # ── Tabela: cameras ───────────────────────────────────────────────────────
    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("nome", sa.String(128), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("localizacao", sa.String(256), nullable=True),
        sa.Column("status", sa.Enum("ativa", "inativa", "erro", name="camera_status"), nullable=False, server_default="ativa"),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Tabela: alertas ───────────────────────────────────────────────────────
    op.create_table(
        "alertas",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("camera_nome", sa.String(128), nullable=False),
        sa.Column("tipo", sa.Enum("furto", "comportamento_suspeito", "objeto_abandonado", name="alert_type"), nullable=False, server_default="furto"),
        sa.Column("confianca", sa.Float(), nullable=False),
        sa.Column("foto_path", sa.Text(), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("telegram_enviado", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("detectado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alertas_camera_id", "alertas", ["camera_id"])
    op.create_index("ix_alertas_detectado_em", "alertas", ["detectado_em"])


def downgrade() -> None:
    op.drop_table("alertas")
    op.drop_table("cameras")
    op.drop_table("usuarios")
    op.execute("DROP TYPE IF EXISTS alert_type")
    op.execute("DROP TYPE IF EXISTS camera_status")
    op.execute("DROP TYPE IF EXISTS user_role")
