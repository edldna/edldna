"""
SuperGuard - Rotas de Usuários
GET    /api/usuarios              - Lista usuários (admin)
POST   /api/usuarios              - Cria usuário (admin)
PUT    /api/usuarios/{id}         - Atualiza usuário (admin)
PATCH  /api/usuarios/{id}/toggle  - Ativa/desativa usuário (admin)
DELETE /api/usuarios/{id}         - Remove usuário (admin)
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import get_current_user, requer_admin
from app.core.auth import criar_hash_senha
from app.models.database import User, UserRole, get_db

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class UsuarioCreate(BaseModel):
    chat_id: str
    nome: str
    username: Optional[str] = None
    role: str = "seguranca"
    senha: Optional[str] = None


class UsuarioUpdate(BaseModel):
    nome: Optional[str] = None
    role: Optional[str] = None
    ativo: Optional[bool] = None
    senha: Optional[str] = None


class UsuarioResponse(BaseModel):
    id: int
    chat_id: str
    nome: str
    username: Optional[str]
    role: str
    ativo: bool

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[UsuarioResponse])
async def listar_usuarios(
    admin: Annotated[User, Depends(requer_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os usuários (apenas admins)."""
    resultado = await db.execute(select(User).order_by(User.id))
    return resultado.scalars().all()


@router.post("", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
async def criar_usuario(
    dados: UsuarioCreate,
    admin: Annotated[User, Depends(requer_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Cria um novo usuário no sistema."""
    # Verifica se chat_id já existe
    resultado = await db.execute(
        select(User).where(User.chat_id == dados.chat_id)
    )
    if resultado.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Usuário com este chat_id já existe.",
        )

    role = UserRole.admin if dados.role == "admin" else UserRole.seguranca
    hashed = criar_hash_senha(dados.senha) if dados.senha else None

    novo = User(
        chat_id=dados.chat_id,
        nome=dados.nome,
        username=dados.username,
        role=role,
        ativo=True,
        hashed_password=hashed,
    )
    db.add(novo)
    await db.commit()
    await db.refresh(novo)
    return novo


@router.put("/{usuario_id}", response_model=UsuarioResponse)
async def atualizar_usuario(
    usuario_id: int,
    dados: UsuarioUpdate,
    admin: Annotated[User, Depends(requer_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Atualiza dados de um usuário."""
    resultado = await db.execute(select(User).where(User.id == usuario_id))
    usuario = resultado.scalar_one_or_none()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if dados.nome is not None:
        usuario.nome = dados.nome
    if dados.role is not None:
        usuario.role = UserRole.admin if dados.role == "admin" else UserRole.seguranca
    if dados.ativo is not None:
        usuario.ativo = dados.ativo
    if dados.senha is not None:
        usuario.hashed_password = criar_hash_senha(dados.senha)

    await db.commit()
    await db.refresh(usuario)
    return usuario


@router.patch("/{usuario_id}/toggle", response_model=UsuarioResponse)
async def toggle_usuario(
    usuario_id: int,
    admin: Annotated[User, Depends(requer_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Ativa ou desativa um usuário."""
    resultado = await db.execute(select(User).where(User.id == usuario_id))
    usuario = resultado.scalar_one_or_none()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    usuario.ativo = not usuario.ativo
    await db.commit()
    await db.refresh(usuario)
    return usuario


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_usuario(
    usuario_id: int,
    admin: Annotated[User, Depends(requer_admin)],
    db: AsyncSession = Depends(get_db),
):
    """Remove um usuário do sistema."""
    resultado = await db.execute(select(User).where(User.id == usuario_id))
    usuario = resultado.scalar_one_or_none()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    await db.delete(usuario)
    await db.commit()
