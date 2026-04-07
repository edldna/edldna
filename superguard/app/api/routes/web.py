"""
SuperGuard - Rotas do Painel Web (interface HTMX/HTML)
Serve as páginas HTML do painel de monitoramento
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import decodificar_token
from app.models.database import Alert, Camera, User, get_db

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _obter_usuario_do_cookie(request: Request) -> Optional[dict]:
    """Extrai e valida token JWT do cookie de sessão."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    return decodificar_token(token)


@router.get("/", response_class=HTMLResponse)
async def pagina_inicial(request: Request):
    """Redireciona para o dashboard ou login."""
    payload = _obter_usuario_do_cookie(request)
    if payload:
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")


@router.get("/login", response_class=HTMLResponse)
async def pagina_login(request: Request):
    """Página de login do painel."""
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login", response_class=HTMLResponse)
async def processar_login(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Processa formulário de login."""
    form = await request.form()
    chat_id = form.get("chat_id", "")
    senha = form.get("senha", "")

    from app.core.auth import verificar_senha, criar_token_acesso

    resultado = await db.execute(
        select(User).where(User.chat_id == chat_id, User.ativo == True)
    )
    usuario = resultado.scalar_one_or_none()

    if not usuario or not usuario.hashed_password or \
            not verificar_senha(senha, usuario.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "erro": "Chat ID ou senha incorretos."},
        )

    token = criar_token_acesso({"sub": usuario.chat_id, "role": usuario.role.value})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=3600,
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout():
    """Realiza logout limpando o cookie."""
    response = RedirectResponse(url="/login")
    response.delete_cookie("access_token")
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Dashboard principal do painel."""
    payload = _obter_usuario_do_cookie(request)
    if not payload:
        return RedirectResponse(url="/login")

    # Estatísticas
    total_cameras = (await db.execute(
        select(func.count(Camera.id)).where(Camera.ativa == True)
    )).scalar() or 0

    total_alertas = (await db.execute(select(func.count(Alert.id)))).scalar() or 0

    alertas_recentes = (await db.execute(
        select(Alert).order_by(Alert.detectado_em.desc()).limit(10)
    )).scalars().all()

    cameras = (await db.execute(
        select(Camera).order_by(Camera.id)
    )).scalars().all()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "usuario": payload,
            "total_cameras": total_cameras,
            "total_alertas": total_alertas,
            "alertas_recentes": alertas_recentes,
            "cameras": cameras,
        },
    )


@router.get("/alertas", response_class=HTMLResponse)
async def pagina_alertas(
    request: Request,
    db: AsyncSession = Depends(get_db),
    pagina: int = 1,
):
    """Histórico de alertas com fotos."""
    payload = _obter_usuario_do_cookie(request)
    if not payload:
        return RedirectResponse(url="/login")

    por_pagina = 20
    offset = (pagina - 1) * por_pagina

    total = (await db.execute(select(func.count(Alert.id)))).scalar() or 0
    alertas = (await db.execute(
        select(Alert).order_by(Alert.detectado_em.desc()).offset(offset).limit(por_pagina)
    )).scalars().all()

    return templates.TemplateResponse(
        "alertas.html",
        {
            "request": request,
            "usuario": payload,
            "alertas": alertas,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
        },
    )


@router.get("/usuarios", response_class=HTMLResponse)
async def pagina_usuarios(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Gerenciamento de usuários (apenas admins)."""
    payload = _obter_usuario_do_cookie(request)
    if not payload:
        return RedirectResponse(url="/login")
    if payload.get("role") != "admin":
        return RedirectResponse(url="/dashboard")

    usuarios = (await db.execute(
        select(User).order_by(User.id)
    )).scalars().all()

    cameras = (await db.execute(
        select(Camera).order_by(Camera.id)
    )).scalars().all()

    return templates.TemplateResponse(
        "usuarios.html",
        {
            "request": request,
            "usuario": payload,
            "usuarios": usuarios,
            "cameras": cameras,
        },
    )
