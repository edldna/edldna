"""
SuperGuard - API FastAPI Principal
Inclui: painel web, gerenciamento de alertas/câmeras/usuários, bot Telegram integrado
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from sqlalchemy import text

from app.core.config import settings
from app.models.database import engine, Base
from app.api.routes.alerts import router as alerts_router
from app.api.routes.cameras import router as cameras_router
from app.api.routes.users import router as users_router
from app.api.routes.auth import router as auth_router
from app.api.routes.web import router as web_router


# ── Lifecycle (startup/shutdown) ──────────────────────────────────────────────

_bot_app = None  # Instância global do bot Telegram


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Inicializa banco e bot Telegram no startup; encerra no shutdown."""
    global _bot_app

    logger.info("SuperGuard API iniciando...")

    # Cria pasta de alertas
    Path(settings.alerts_dir).mkdir(parents=True, exist_ok=True)

    # Cria tabelas (Alembic fará migrações; isso garante criação inicial)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Inicia bot Telegram em background (se token configurado)
    if settings.telegram_bot_token:
        try:
            from app.bot.telegram_bot import criar_aplicacao
            _bot_app = criar_aplicacao()
            await _bot_app.initialize()
            await _bot_app.start()
            await _bot_app.updater.start_polling(drop_pending_updates=True)
            app.state.telegram_bot = _bot_app.bot
            logger.info("Bot Telegram iniciado com sucesso.")
        except Exception as e:
            logger.error(f"Falha ao iniciar bot Telegram: {e}")
            app.state.telegram_bot = None
    else:
        logger.warning(
            "TELEGRAM_BOT_TOKEN não configurado. "
            "Alertas Telegram desativados."
        )
        app.state.telegram_bot = None

    yield  # API operacional

    # Shutdown
    logger.info("SuperGuard API encerrando...")
    if _bot_app is not None:
        await _bot_app.updater.stop()
        await _bot_app.stop()
        await _bot_app.shutdown()


# ── Criação da aplicação ──────────────────────────────────────────────────────

app = FastAPI(
    title="SuperGuard API",
    description="Sistema de Segurança Inteligente para Supermercados",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Arquivos estáticos e templates
static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"
static_dir.mkdir(parents=True, exist_ok=True)
templates_dir.mkdir(parents=True, exist_ok=True)

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Diretório de alertas (fotos)
alerts_dir = Path(settings.alerts_dir)
if alerts_dir.exists():
    app.mount("/alerts", StaticFiles(directory=str(alerts_dir)), name="alerts")

# ── Inclui rotas ──────────────────────────────────────────────────────────────

app.include_router(auth_router, prefix="/auth", tags=["Autenticação"])
app.include_router(web_router, tags=["Painel Web"])
app.include_router(alerts_router, prefix="/api/alertas", tags=["Alertas"])
app.include_router(cameras_router, prefix="/api/cameras", tags=["Câmeras"])
app.include_router(users_router, prefix="/api/usuarios", tags=["Usuários"])


# ── Endpoints básicos ─────────────────────────────────────────────────────────

@app.get("/health", tags=["Sistema"])
async def health_check():
    """Verifica saúde da API e conexão com o banco."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "store": settings.store_name,
        "telegram_ativo": app.state.telegram_bot is not None,
    }


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(status_code=404, content={"detalhe": "Recurso não encontrado."})


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    logger.error(f"Erro interno: {exc}")
    return JSONResponse(status_code=500, content={"detalhe": "Erro interno do servidor."})
