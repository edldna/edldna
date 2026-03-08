"""
SuperGuard - Rotas de Autenticação (JWT)
POST /auth/login    - Realiza login e retorna token JWT
GET  /auth/me       - Retorna dados do usuário logado
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import criar_token_acesso, decodificar_token, verificar_senha
from app.core.config import settings
from app.models.database import User, UserRole, get_db

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Schemas ───────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    nome: str
    role: str


class UsuarioAtual(BaseModel):
    id: int
    chat_id: str
    nome: str
    role: str

    model_config = {"from_attributes": True}


# ── Dependência: obtém usuário atual a partir do token JWT ────────────────────

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    credenciais_excecao = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decodificar_token(token)
    if payload is None:
        raise credenciais_excecao

    chat_id: str = payload.get("sub")
    if not chat_id:
        raise credenciais_excecao

    resultado = await db.execute(
        select(User).where(User.chat_id == chat_id, User.ativo == True)
    )
    usuario = resultado.scalar_one_or_none()
    if usuario is None:
        raise credenciais_excecao

    return usuario


async def requer_admin(
    usuario: Annotated[User, Depends(get_current_user)],
) -> User:
    if usuario.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissão de administrador necessária.",
        )
    return usuario


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
):
    """
    Realiza login no painel web.
    Username = chat_id do Telegram
    Password = senha definida pelo admin
    """
    resultado = await db.execute(
        select(User).where(User.chat_id == form_data.username, User.ativo == True)
    )
    usuario = resultado.scalar_one_or_none()

    if usuario is None or usuario.hashed_password is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chat ID ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verificar_senha(form_data.password, usuario.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chat ID ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = criar_token_acesso(
        {"sub": usuario.chat_id, "role": usuario.role.value},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )

    return TokenResponse(
        access_token=token,
        nome=usuario.nome,
        role=usuario.role.value,
    )


@router.get("/me", response_model=UsuarioAtual)
async def me(usuario: Annotated[User, Depends(get_current_user)]):
    """Retorna dados do usuário autenticado."""
    return usuario
