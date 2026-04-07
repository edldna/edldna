"""
SuperGuard - Testes de Integração com Mock do Telegram
Testa os handlers do bot sem enviar mensagens reais.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ── Fixtures de mock ──────────────────────────────────────────────────────────

def _criar_update_mock(
    chat_id: str = "999999",
    texto: str = "/start",
    full_name: str = "Usuário Teste",
    username: str = "usuario_teste",
) -> MagicMock:
    """Cria um mock de Update do Telegram."""
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user.full_name = full_name
    update.effective_user.username = username
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.text = texto
    return update


def _criar_context_mock() -> MagicMock:
    """Cria um mock de ContextTypes.DEFAULT_TYPE."""
    context = MagicMock()
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_photo = AsyncMock()
    context.args = []
    return context


# ── Testes do comando /start ───────────────────────────────────────────────────

class TestCmdStart:

    @pytest.mark.asyncio
    async def test_start_usuario_nao_autorizado(self):
        """Usuário não cadastrado deve receber mensagem de boas-vindas sem acesso."""
        update = _criar_update_mock(chat_id="111")
        context = _criar_context_mock()

        # Mock da sessão de banco — usuário não existe
        with patch("app.bot.telegram_bot._SessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            # execute retorna scalar_one_or_none = None (usuário não encontrado)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session_cls.return_value = mock_session

            from app.bot.telegram_bot import cmd_start
            await cmd_start(update, context)

        update.message.reply_text.assert_called_once()
        chamada_args = update.message.reply_text.call_args[0][0]
        assert "não está cadastrado" in chamada_args or "registrar" in chamada_args.lower()

    @pytest.mark.asyncio
    async def test_start_usuario_autorizado(self):
        """Usuário cadastrado deve receber mensagem personalizada."""
        from app.models.database import User, UserRole

        update = _criar_update_mock(chat_id="222", full_name="João Admin")
        context = _criar_context_mock()

        usuario_mock = MagicMock(spec=User)
        usuario_mock.ativo = True
        usuario_mock.role = UserRole.seguranca

        with patch("app.bot.telegram_bot._SessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = usuario_mock
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session_cls.return_value = mock_session

            from app.bot.telegram_bot import cmd_start
            await cmd_start(update, context)

        update.message.reply_text.assert_called_once()
        chamada_args = update.message.reply_text.call_args[0][0]
        assert "João Admin" in chamada_args
        assert "cadastrado" in chamada_args.lower()


# ── Testes do comando /registrar ──────────────────────────────────────────────

class TestCmdRegistrar:

    @pytest.mark.asyncio
    async def test_registrar_usuario_ja_cadastrado(self):
        """Usuário já cadastrado deve receber aviso."""
        from app.models.database import User, UserRole

        update = _criar_update_mock(chat_id="333")
        context = _criar_context_mock()

        usuario_mock = MagicMock(spec=User)
        usuario_mock.ativo = True

        with patch("app.bot.telegram_bot._SessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = usuario_mock
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session_cls.return_value = mock_session

            from app.bot.telegram_bot import cmd_registrar
            await cmd_registrar(update, context)

        chamada_args = update.message.reply_text.call_args[0][0]
        assert "já está cadastrado" in chamada_args

    @pytest.mark.asyncio
    async def test_registrar_novo_usuario_notifica_admin(self):
        """Novo usuário deve notificar o admin."""
        update = _criar_update_mock(chat_id="444", full_name="Novo Usuário")
        context = _criar_context_mock()

        with patch("app.bot.telegram_bot._SessionLocal") as mock_session_cls, \
             patch("app.bot.telegram_bot.settings") as mock_settings:

            mock_settings.telegram_admin_chat_id = "admin_123"
            mock_settings.store_name = "Supermercado Teste"

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None  # não existe
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session_cls.return_value = mock_session

            from app.bot.telegram_bot import cmd_registrar
            await cmd_registrar(update, context)

        # Deve ter tentado notificar o admin
        context.bot.send_message.assert_called_once()
        args_admin = context.bot.send_message.call_args[1]
        assert args_admin["chat_id"] == "admin_123"

        # Deve confirmar para o usuário
        update.message.reply_text.assert_called_once()


# ── Testes do envio de alertas ─────────────────────────────────────────────────

class TestEnvioAlertaTelegram:

    @pytest.mark.asyncio
    async def test_alerta_enviado_para_todos_usuarios_ativos(self, tmp_path):
        """Alerta deve ser enviado para todos os usuários ativos."""
        from datetime import datetime
        from app.models.database import User, UserRole

        # Cria uma foto fake
        foto = tmp_path / "alerta_test.jpg"
        foto.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # Header JPEG mínimo

        usuario1 = MagicMock(spec=User)
        usuario1.chat_id = "111"
        usuario1.nome = "Segurança 1"
        usuario1.ativo = True

        usuario2 = MagicMock(spec=User)
        usuario2.chat_id = "222"
        usuario2.nome = "Admin"
        usuario2.ativo = True

        bot_mock = AsyncMock()
        bot_mock.send_photo = AsyncMock()
        bot_mock.send_message = AsyncMock()

        with patch("app.bot.telegram_bot._SessionLocal") as mock_session_cls, \
             patch("app.bot.telegram_bot.settings") as mock_settings:

            mock_settings.store_name = "Supermercado Teste"

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [usuario1, usuario2]
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session_cls.return_value = mock_session

            from app.bot.telegram_bot import enviar_alerta_telegram
            await enviar_alerta_telegram(
                bot=bot_mock,
                camera_nome="Câmera 01",
                confianca=0.89,
                foto_path=str(foto),
                detectado_em=datetime.now(),
            )

        # Deve ter chamado send_photo para ambos os usuários
        assert bot_mock.send_photo.call_count == 2
