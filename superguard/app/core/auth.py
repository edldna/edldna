"""
SuperGuard - Utilitários de autenticação JWT
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Contexto de hashing de senhas com bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verificar_senha(senha_plana: str, senha_hash: str) -> bool:
    """Verifica se a senha em texto plano corresponde ao hash armazenado."""
    return pwd_context.verify(senha_plana, senha_hash)


def criar_hash_senha(senha: str) -> str:
    """Gera hash bcrypt da senha fornecida."""
    return pwd_context.hash(senha)


def criar_token_acesso(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Gera token JWT para autenticação no painel web."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decodificar_token(token: str) -> Optional[dict]:
    """Decodifica e valida um token JWT. Retorna None se inválido."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
