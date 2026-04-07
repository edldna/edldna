"""
SuperGuard - Bot Telegram
Gerencia alertas em tempo real, registro de usuários e comandos administrativos.

Comandos disponíveis:
  /start       - Boas-vindas e instruções
  /registrar   - Solicita cadastro no sistema
  /status      - Status atual do sistema
  /cameras     - Lista câmeras ativas
  /usuarios    - (admin) Lista usuários cadastrados
  /adduser     - (admin) Adiciona usuário por chat_id
  /removeuser  - (admin) Remove usuário por chat_id
  /ajuda       - Mostra todos os comandos
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from telegram import Update, Bot
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.core.config import settings
from app.models.database import Alert, Camera, CameraStatus, User, UserRole


# ── Criação do motor de banco para o bot ──────────────────────────────────────

_engine = create_async_engine(settings.database_url, pool_pre_ping=True)
_SessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    return _SessionLocal()


# ── Helpers de permissão ──────────────────────────────────────────────────────

async def _obter_usuario(chat_id: str, session: AsyncSession) -> Optional[User]:
    resultado = await session.execute(
        select(User).where(User.chat_id == str(chat_id), User.ativo == True)
    )
    return resultado.scalar_one_or_none()


async def _usuario_autorizado(chat_id: str, session: AsyncSession) -> bool:
    usuario = await _obter_usuario(str(chat_id), session)
    return usuario is not None


async def _usuario_admin(chat_id: str, session: AsyncSession) -> bool:
    usuario = await _obter_usuario(str(chat_id), session)
    return usuario is not None and usuario.role == UserRole.admin


# ── Handlers dos comandos ─────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mensagem de boas-vindas."""
    chat_id = str(update.effective_chat.id)
    nome = update.effective_user.full_name or "Usuário"

    async with _SessionLocal() as session:
        autorizado = await _usuario_autorizado(chat_id, session)

    if autorizado:
        texto = (
            f"👋 Olá, *{nome}*!\n\n"
            f"✅ Você já está cadastrado no *SuperGuard*.\n"
            f"Você receberá alertas automáticos de segurança.\n\n"
            f"Use /ajuda para ver os comandos disponíveis."
        )
    else:
        texto = (
            f"👋 Olá, *{nome}*!\n\n"
            f"🛡️ Bem-vindo ao *SuperGuard* — Sistema de Segurança Inteligente.\n\n"
            f"⚠️ Você ainda *não está cadastrado* para receber alertas.\n"
            f"Use /registrar para solicitar acesso."
        )

    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)


async def cmd_registrar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Solicita cadastro do usuário."""
    chat_id = str(update.effective_chat.id)
    nome = update.effective_user.full_name or "Usuário"
    username = update.effective_user.username

    async with _SessionLocal() as session:
        ja_cadastrado = await _usuario_autorizado(chat_id, session)
        if ja_cadastrado:
            await update.message.reply_text(
                "✅ Você já está cadastrado no sistema!",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    # Notifica o admin
    admin_chat_id = settings.telegram_admin_chat_id
    if admin_chat_id:
        mensagem_admin = (
            f"🔔 *Nova solicitação de cadastro*\n\n"
            f"👤 Nome: {nome}\n"
            f"🆔 Chat ID: `{chat_id}`\n"
            f"📛 Username: @{username or 'desconhecido'}\n\n"
            f"Para aprovar, use:\n"
            f"`/adduser {chat_id} {nome} seguranca`"
        )
        try:
            await context.bot.send_message(
                chat_id=admin_chat_id,
                text=mensagem_admin,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error(f"Erro ao notificar admin: {e}")

    await update.message.reply_text(
        f"📋 Sua solicitação de cadastro foi enviada ao administrador.\n"
        f"Seu Chat ID: `{chat_id}`\n\n"
        f"Você receberá uma confirmação em breve.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exibe status do sistema."""
    chat_id = str(update.effective_chat.id)

    async with _SessionLocal() as session:
        if not await _usuario_autorizado(chat_id, session):
            await update.message.reply_text("❌ Acesso negado. Use /registrar para solicitar acesso.")
            return

        # Conta câmeras ativas
        resultado = await session.execute(
            select(Camera).where(Camera.ativa == True)
        )
        cameras_ativas = resultado.scalars().all()

        # Conta alertas nas últimas 24h
        from sqlalchemy import func
        agora = datetime.now(timezone.utc)
        resultado_alertas = await session.execute(
            select(func.count(Alert.id)).where(
                Alert.detectado_em >= agora.replace(hour=0, minute=0, second=0)
            )
        )
        total_alertas_hoje = resultado_alertas.scalar() or 0

    texto = (
        f"📊 *Status do SuperGuard*\n\n"
        f"🏪 Loja: *{settings.store_name}*\n"
        f"📹 Câmeras ativas: *{len(cameras_ativas)}*\n"
        f"🚨 Alertas hoje: *{total_alertas_hoje}*\n"
        f"⏱️ Horário: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        f"✅ Sistema operacional"
    )
    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)


async def cmd_cameras(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista câmeras cadastradas."""
    chat_id = str(update.effective_chat.id)

    async with _SessionLocal() as session:
        if not await _usuario_autorizado(chat_id, session):
            await update.message.reply_text("❌ Acesso negado.")
            return

        resultado = await session.execute(select(Camera))
        cameras = resultado.scalars().all()

    if not cameras:
        await update.message.reply_text("📹 Nenhuma câmera cadastrada.")
        return

    linhas = ["📹 *Câmeras cadastradas:*\n"]
    for cam in cameras:
        icone = "🟢" if cam.ativa else "🔴"
        linhas.append(f"{icone} *{cam.nome}*")
        if cam.localizacao:
            linhas.append(f"   📍 {cam.localizacao}")
        linhas.append(f"   Status: `{cam.status.value}`")

    await update.message.reply_text("\n".join(linhas), parse_mode=ParseMode.MARKDOWN)


async def cmd_usuarios(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Admin) Lista usuários cadastrados."""
    chat_id = str(update.effective_chat.id)

    async with _SessionLocal() as session:
        if not await _usuario_admin(chat_id, session):
            await update.message.reply_text("❌ Apenas administradores podem usar este comando.")
            return

        resultado = await session.execute(select(User))
        usuarios = resultado.scalars().all()

    if not usuarios:
        await update.message.reply_text("👥 Nenhum usuário cadastrado.")
        return

    linhas = ["👥 *Usuários cadastrados:*\n"]
    for u in usuarios:
        icone = "✅" if u.ativo else "❌"
        role_icon = "👑" if u.role == UserRole.admin else "🔒"
        linhas.append(
            f"{icone} {role_icon} *{u.nome}*\n"
            f"   Chat ID: `{u.chat_id}`\n"
            f"   Função: `{u.role.value}`"
        )

    await update.message.reply_text("\n".join(linhas), parse_mode=ParseMode.MARKDOWN)


async def cmd_adduser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    (Admin) Adiciona ou atualiza um usuário.
    Uso: /adduser <chat_id> <nome> [admin|seguranca]
    """
    chat_id = str(update.effective_chat.id)

    async with _SessionLocal() as session:
        if not await _usuario_admin(chat_id, session):
            await update.message.reply_text("❌ Apenas administradores podem usar este comando.")
            return

        args = context.args
        if not args or len(args) < 2:
            await update.message.reply_text(
                "⚠️ Uso correto:\n`/adduser <chat_id> <nome> [admin|seguranca]`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        novo_chat_id = args[0]
        novo_nome = " ".join(args[1:-1]) if len(args) > 2 else args[1]
        role_str = args[-1].lower() if len(args) > 2 else "seguranca"

        if role_str not in ("admin", "seguranca"):
            role_str = "seguranca"
        role = UserRole.admin if role_str == "admin" else UserRole.seguranca

        # Verifica se já existe
        resultado = await session.execute(
            select(User).where(User.chat_id == novo_chat_id)
        )
        usuario_existente = resultado.scalar_one_or_none()

        if usuario_existente:
            usuario_existente.nome = novo_nome
            usuario_existente.role = role
            usuario_existente.ativo = True
            await session.commit()
            msg = f"✅ Usuário *{novo_nome}* atualizado com sucesso!"
        else:
            novo_usuario = User(
                chat_id=novo_chat_id,
                nome=novo_nome,
                role=role,
                ativo=True,
            )
            session.add(novo_usuario)
            await session.commit()
            msg = f"✅ Usuário *{novo_nome}* adicionado com sucesso!"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    # Notifica o usuário adicionado
    try:
        await context.bot.send_message(
            chat_id=novo_chat_id,
            text=(
                f"🎉 Seu acesso ao *SuperGuard* foi aprovado!\n\n"
                f"✅ Você agora receberá alertas de segurança.\n"
                f"Use /ajuda para ver os comandos disponíveis."
            ),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.warning(f"Não foi possível notificar novo usuário {novo_chat_id}: {e}")


async def cmd_removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    (Admin) Remove/desativa um usuário.
    Uso: /removeuser <chat_id>
    """
    chat_id = str(update.effective_chat.id)

    async with _SessionLocal() as session:
        if not await _usuario_admin(chat_id, session):
            await update.message.reply_text("❌ Apenas administradores podem usar este comando.")
            return

        args = context.args
        if not args:
            await update.message.reply_text(
                "⚠️ Uso correto:\n`/removeuser <chat_id>`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        target_id = args[0]
        resultado = await session.execute(
            select(User).where(User.chat_id == target_id)
        )
        usuario = resultado.scalar_one_or_none()

        if not usuario:
            await update.message.reply_text(f"❌ Usuário com Chat ID `{target_id}` não encontrado.")
            return

        usuario.ativo = False
        await session.commit()

    await update.message.reply_text(
        f"✅ Usuário `{target_id}` desativado com sucesso.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exibe lista de comandos disponíveis."""
    chat_id = str(update.effective_chat.id)

    async with _SessionLocal() as session:
        eh_admin = await _usuario_admin(chat_id, session)

    linhas = [
        "🤖 *Comandos do SuperGuard:*\n",
        "👤 *Usuário:*",
        "/start — Boas-vindas",
        "/registrar — Solicitar acesso",
        "/status — Status do sistema",
        "/cameras — Ver câmeras ativas",
        "/ajuda — Esta mensagem",
    ]

    if eh_admin:
        linhas += [
            "",
            "👑 *Administrador:*",
            "/usuarios — Listar todos os usuários",
            "/adduser `<id> <nome> [role]` — Adicionar usuário",
            "/removeuser `<id>` — Remover usuário",
        ]

    await update.message.reply_text("\n".join(linhas), parse_mode=ParseMode.MARKDOWN)


async def handle_mensagem_desconhecida(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Responde mensagens não reconhecidas."""
    await update.message.reply_text(
        "❓ Comando não reconhecido. Use /ajuda para ver os comandos disponíveis."
    )


# ── Função pública para envio de alertas ─────────────────────────────────────

async def enviar_alerta_telegram(
    bot: Bot,
    camera_nome: str,
    confianca: float,
    foto_path: str,
    detectado_em: datetime,
) -> None:
    """
    Envia alerta de furto para todos os usuários autorizados.
    Chamada pela API quando um novo alerta é registrado.
    """
    legenda = (
        f"🚨 *ALERTA DE FURTO*\n\n"
        f"📹 Câmera: *{camera_nome}*\n"
        f"🏪 Loja: *{settings.store_name}*\n"
        f"🕐 Data/Hora: *{detectado_em.strftime('%d/%m/%Y %H:%M:%S')}*\n"
        f"🎯 Confiança: *{confianca:.0%}*"
    )

    async with _SessionLocal() as session:
        resultado = await session.execute(
            select(User).where(User.ativo == True)
        )
        usuarios = resultado.scalars().all()

    enviados = 0
    for usuario in usuarios:
        try:
            if foto_path and os.path.isfile(foto_path):
                with open(foto_path, "rb") as foto:
                    await bot.send_photo(
                        chat_id=usuario.chat_id,
                        photo=foto,
                        caption=legenda,
                        parse_mode=ParseMode.MARKDOWN,
                    )
            else:
                await bot.send_message(
                    chat_id=usuario.chat_id,
                    text=legenda,
                    parse_mode=ParseMode.MARKDOWN,
                )
            enviados += 1
        except Exception as e:
            logger.error(
                f"Erro ao enviar alerta para usuário {usuario.chat_id} ({usuario.nome}): {e}"
            )

    logger.info(f"Alerta enviado para {enviados}/{len(usuarios)} usuário(s).")


# ── Função de inicialização do bot ────────────────────────────────────────────

def criar_aplicacao() -> Application:
    """Cria e configura a aplicação do bot Telegram."""
    if not settings.telegram_bot_token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN não configurado. "
            "Adicione o token no arquivo .env."
        )

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )

    # Registra handlers de comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("registrar", cmd_registrar))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cameras", cmd_cameras))
    app.add_handler(CommandHandler("usuarios", cmd_usuarios))
    app.add_handler(CommandHandler("adduser", cmd_adduser))
    app.add_handler(CommandHandler("removeuser", cmd_removeuser))
    app.add_handler(CommandHandler("ajuda", cmd_ajuda))

    # Handler para mensagens não reconhecidas
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mensagem_desconhecida)
    )

    return app


async def iniciar_bot() -> None:
    """Inicia o bot em modo polling (para desenvolvimento/VPS simples)."""
    logger.info("Iniciando bot Telegram em modo polling...")
    app = criar_aplicacao()
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Bot Telegram ativo e aguardando mensagens.")
    return app


if __name__ == "__main__":
    asyncio.run(iniciar_bot())
