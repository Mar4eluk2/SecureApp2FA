"""
bot.py — Telegram-бот. Два независимых сценария:

1. ПРИВЯЗКА (только один раз, при регистрации в GUI):
   пользователь сам присылает боту 6-значный bind-код из приложения —
   бот привязывает его telegram_id к логину.

2. ВХОД (при каждой авторизации):
   бот НЕ ждёт код от пользователя. Он сам, в фоне, следит за новыми
   запросами на вход (login_sessions.json) и, найдя telegram_id, привязанный
   к логину, сам отправляет ИМЕННО ЕМУ сообщение с inline-кнопкой
   подтверждения. Подтвердить вход может только владелец уже привязанного
   Telegram-аккаунта — даже если пароль узнает кто-то посторонний, ему
   некому будет прислать код, потому что кода для входа больше нет.

Запуск: python bot.py
Перед первым использованием напишите боту /start — иначе Telegram не
позволит ему написать вам первым при последующих входах.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramAPIError

from config import BOT_TOKEN
import storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

NOTIFY_POLL_INTERVAL_SECONDS = 1.0  # как часто проверять новые запросы на вход


# ---------- Привязка Telegram-аккаунта (только при регистрации) ----------

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 Привет! Я бот двухфакторной аутентификации.\n\n"
        "Если вы только что зарегистрировались в приложении — пришлите мне "
        "6-значный код привязки, который показало приложение.\n\n"
        "При последующих входах ничего вводить не нужно: я сам пришлю сюда "
        "кнопку подтверждения, когда вы будете входить в аккаунт."
    )


@router.message(F.text.regexp(r"^\d{6}$"))
async def handle_bind_code(message: Message) -> None:
    """Обрабатывает 6-значный код — это ВСЕГДА код привязки аккаунта.
    Для входа коды больше не используются (см. login_notifier_loop)."""
    code = message.text.strip()
    telegram_id = message.from_user.id

    ok, reason = storage.confirm_bind_session(code, telegram_id)

    if ok:
        session = storage.get_bind_session(code)
        login = session["login"] if session else "?"
        await message.answer(
            f"✅ Telegram успешно привязан к аккаунту «{login}».\n"
            f"Теперь при входе в приложение я сам буду присылать сюда кнопку "
            f"подтверждения — вводить код повторно не нужно."
        )
        return

    texts = {
        "not_found": "❌ Такой код не найден. Проверьте код в приложении.",
        "expired": "⌛ Срок действия кода истёк. Запросите новый код в приложении.",
        "already_bound": "ℹ️ К этому аккаунту уже привязан другой Telegram.",
        "telegram_taken": "❌ Этот Telegram-аккаунт уже привязан к другому логину. "
                           "Один Telegram — один аккаунт.",
    }
    await message.answer(texts.get(reason, "❌ Не удалось привязать аккаунт. Попробуйте снова."))


@router.message()
async def handle_other(message: Message) -> None:
    """Любое другое сообщение — подсказываем, что делать."""
    await message.answer(
        "Если вы регистрируетесь — пришлите 6-значный код привязки из приложения.\n"
        "Для входа код не нужен: я сам пришлю кнопку подтверждения, когда вы "
        "будете входить в аккаунт."
    )


# ---------- Подтверждение входа (инициируется ботом, а не пользователем) ----------

@router.callback_query(F.data.startswith("login_confirm:"))
async def handle_login_confirm(callback: CallbackQuery) -> None:
    session_id = callback.data.split(":", 1)[1]
    telegram_id = callback.from_user.id

    ok = storage.confirm_login_session(session_id, telegram_id)

    if ok:
        await callback.message.edit_text("✅ Вход подтверждён! Можете вернуться в приложение.")
        await callback.answer("Готово!")
    else:
        status = storage.get_login_session_status(session_id)
        if status == "expired":
            text = "⌛ Запрос на вход истёк. Попробуйте войти заново в приложении."
        elif status == "confirmed":
            text = "✅ Этот вход уже был подтверждён."
        else:
            text = "❌ Не удалось подтвердить вход."
        await callback.message.edit_text(text)
        await callback.answer()


async def login_notifier_loop(bot: Bot) -> None:
    """Фоновая задача: следит за новыми запросами на вход и САМА отправляет
    привязанному Telegram-аккаунту сообщение с кнопкой подтверждения.

    Это и есть ключевая защита: получатель кнопки определяется сервером на
    основе уже сохранённой привязки телефон/логин, а не тем, кто первым
    отправил код боту."""
    while True:
        try:
            pending = storage.get_unnotified_login_sessions()
            for session_id, session in pending:
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(
                            text="✅ Подтвердить вход",
                            callback_data=f"login_confirm:{session_id}",
                        )]
                    ]
                )
                try:
                    await bot.send_message(
                        chat_id=session["telegram_id"],
                        text=(
                            f"🔐 Запрос на вход в аккаунт «{session['login']}».\n\n"
                            f"Если это были вы — нажмите кнопку ниже.\n"
                            f"Если нет — просто проигнорируйте сообщение."
                        ),
                        reply_markup=keyboard,
                    )
                    storage.mark_login_notified(session_id)
                except TelegramAPIError:
                    logger.exception(
                        "Не удалось отправить запрос на вход, session_id=%s", session_id
                    )
                    storage.mark_login_failed(session_id)
        except Exception:
            logger.exception("Ошибка в фоновом цикле уведомлений о входе")

        await asyncio.sleep(NOTIFY_POLL_INTERVAL_SECONDS)


# ---------- Точка запуска ----------

async def run_bot(token: str) -> None:
    """Запускает бота: одновременно слушает входящие сообщения/колбэки и
    следит за новыми запросами на вход. Вызывается и из __main__ этого
    файла, и из main.py (при сборке в один exe) — единая точка правды."""
    if token == "ВСТАВЬТЕ_СЮДА_ТОКЕН_ОТ_BOTFATHER":
        raise RuntimeError(
            "Не задан BOT_TOKEN! Откройте config.py и вставьте токен, "
            "полученный от @BotFather."
        )

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)

    logger.info("Бот запущен: слушаю сообщения и слежу за запросами на вход...")
    await asyncio.gather(
        dp.start_polling(bot),
        login_notifier_loop(bot),
    )


if __name__ == "__main__":
    asyncio.run(run_bot(BOT_TOKEN))
