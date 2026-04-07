"""
SuperGuard - Rotas de Alertas
GET  /api/alertas              - Lista alertas com paginação
GET  /api/alertas/{id}         - Detalhes de um alerta
POST /api/alertas/interno      - Recebe alerta do worker CV (uso interno)
DELETE /api/alertas/{id}       - Remove alerta (admin)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import get_current_user, requer_admin
from app.models.database import Alert, AlertType, User, get_db
from app.core.config import settings

router = APIRouter()

# Chave secreta para comunicação interna entre worker e API
WORKER_SECRET = os.environ.get("WORKER_SECRET", "superguard")


# ── Schemas ───────────────────────────────────────────────────────────────────

class AlertaResponse(BaseModel):
    id: int
    camera_id: int
    camera_nome: str
    tipo: str
    confianca: float
    foto_path: Optional[str]
    descricao: Optional[str]
    telegram_enviado: bool
    detectado_em: datetime

    model_config = {"from_attributes": True}


class AlertaInternoRequest(BaseModel):
    camera_id: int
    camera_nome: str
    confianca: float
    foto_path: Optional[str] = None
    descricao: Optional[str] = None
    detectado_em: Optional[datetime] = None


class PaginacaoAlertas(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    alertas: List[AlertaResponse]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=PaginacaoAlertas)
async def listar_alertas(
    usuario: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    pagina: int = 1,
    por_pagina: int = 20,
    camera_id: Optional[int] = None,
):
    """Lista alertas com paginação. Usuários autenticados podem ver todos."""
    por_pagina = min(por_pagina, 100)
    offset = (pagina - 1) * por_pagina

    query = select(Alert).order_by(Alert.detectado_em.desc())
    count_query = select(func.count(Alert.id))

    if camera_id:
        query = query.where(Alert.camera_id == camera_id)
        count_query = count_query.where(Alert.camera_id == camera_id)

    total = (await db.execute(count_query)).scalar() or 0
    alertas = (await db.execute(query.offset(offset).limit(por_pagina))).scalars().all()

    return PaginacaoAlertas(
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        alertas=[AlertaResponse.model_validate(a) for a in alertas],
    )


@router.get("/{alerta_id}", response_model=AlertaResponse)
async def obter_alerta(
    alerta_id: int,
    usuario: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Obtém detalhes de um alerta específico."""
    resultado = await db.execute(select(Alert).where(Alert.id == alerta_id))
    alerta = resultado.scalar_one_or_none()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta não encontrado.")
    return alerta


@router.post("/interno", status_code=status.HTTP_201_CREATED)
async def receber_alerta_interno(
    payload: AlertaInternoRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_worker_key: Optional[str] = Header(default=None),
):
    """
    Endpoint interno: recebe alertas do worker de CV.
    Autenticado por chave secreta (X-Worker-Key header).
    """
    if x_worker_key != WORKER_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chave de worker inválida.",
        )

    novo_alerta = Alert(
        camera_id=payload.camera_id,
        camera_nome=payload.camera_nome,
        tipo=AlertType.furto,
        confianca=payload.confianca,
        foto_path=payload.foto_path,
        descricao=payload.descricao,
        telegram_enviado=False,
        detectado_em=payload.detectado_em or datetime.now(timezone.utc),
    )
    db.add(novo_alerta)
    await db.flush()
    await db.refresh(novo_alerta)

    # Envia alerta Telegram
    bot = getattr(request.app.state, "telegram_bot", None)
    if bot:
        try:
            from app.bot.telegram_bot import enviar_alerta_telegram
            await enviar_alerta_telegram(
                bot=bot,
                camera_nome=payload.camera_nome,
                confianca=payload.confianca,
                foto_path=payload.foto_path or "",
                detectado_em=novo_alerta.detectado_em,
            )
            novo_alerta.telegram_enviado = True
        except Exception as e:
            from loguru import logger
            logger.error(f"Falha ao enviar alerta Telegram: {e}")

    await db.commit()
    return {"id": novo_alerta.id, "status": "criado"}


@router.delete("/{alerta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_alerta(
    alerta_id: int,
    admin: Annotated[User, Depends(requer_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Remove um alerta (apenas admins)."""
    resultado = await db.execute(select(Alert).where(Alert.id == alerta_id))
    alerta = resultado.scalar_one_or_none()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta não encontrado.")
    await db.delete(alerta)
    await db.commit()
