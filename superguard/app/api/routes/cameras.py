"""
SuperGuard - Rotas de Câmeras
GET    /api/cameras              - Lista câmeras
POST   /api/cameras              - Adiciona câmera (admin)
PUT    /api/cameras/{id}         - Atualiza câmera (admin)
PATCH  /api/cameras/{id}/toggle  - Ativa/desativa câmera (admin)
DELETE /api/cameras/{id}         - Remove câmera (admin)
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import get_current_user, requer_admin
from app.models.database import Camera, CameraStatus, User, get_db

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class CameraCreate(BaseModel):
    nome: str
    url: str
    localizacao: Optional[str] = None


class CameraUpdate(BaseModel):
    nome: Optional[str] = None
    url: Optional[str] = None
    localizacao: Optional[str] = None
    ativa: Optional[bool] = None


class CameraResponse(BaseModel):
    id: int
    nome: str
    url: str
    localizacao: Optional[str]
    status: str
    ativa: bool

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[CameraResponse])
async def listar_cameras(
    usuario: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    apenas_ativas: bool = False,
):
    """Lista todas as câmeras cadastradas."""
    query = select(Camera)
    if apenas_ativas:
        query = query.where(Camera.ativa == True)
    resultado = await db.execute(query.order_by(Camera.id))
    return resultado.scalars().all()


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def criar_camera(
    dados: CameraCreate,
    admin: Annotated[User, Depends(requer_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Adiciona uma nova câmera ao sistema."""
    nova = Camera(
        nome=dados.nome,
        url=dados.url,
        localizacao=dados.localizacao,
        status=CameraStatus.ativa,
        ativa=True,
    )
    db.add(nova)
    await db.commit()
    await db.refresh(nova)
    return nova


@router.put("/{camera_id}", response_model=CameraResponse)
async def atualizar_camera(
    camera_id: int,
    dados: CameraUpdate,
    admin: Annotated[User, Depends(requer_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Atualiza dados de uma câmera."""
    resultado = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = resultado.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Câmera não encontrada.")

    if dados.nome is not None:
        camera.nome = dados.nome
    if dados.url is not None:
        camera.url = dados.url
    if dados.localizacao is not None:
        camera.localizacao = dados.localizacao
    if dados.ativa is not None:
        camera.ativa = dados.ativa

    await db.commit()
    await db.refresh(camera)
    return camera


@router.patch("/{camera_id}/toggle", response_model=CameraResponse)
async def toggle_camera(
    camera_id: int,
    admin: Annotated[User, Depends(requer_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Ativa ou desativa uma câmera."""
    resultado = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = resultado.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Câmera não encontrada.")

    camera.ativa = not camera.ativa
    camera.status = CameraStatus.ativa if camera.ativa else CameraStatus.inativa
    await db.commit()
    await db.refresh(camera)
    return camera


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_camera(
    camera_id: int,
    admin: Annotated[User, Depends(requer_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Remove uma câmera do sistema."""
    resultado = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = resultado.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Câmera não encontrada.")
    await db.delete(camera)
    await db.commit()
