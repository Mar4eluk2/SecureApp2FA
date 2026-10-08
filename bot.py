import asyncio, logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError
import storage
from config import BOT_TOKEN

logging.basicConfig(level=logging.INFO)
logger=logging.getLogger(__name__)
router=Router()
POLL=1.0

@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "👋 Бот двухфакторной аутентификации.\n\n"
        "При регистрации приложение покажет 6-значный код привязки.\n"
        "При входе или восстановлении пароля я сам пришлю кнопку подтверждения."
    )

@router.message(F.text.regexp(r"^\d{6}$"))
async def bind(message: Message):
    ok,reason=storage.confirm_bind_session(message.text.strip(),message.from_user.id)
    if ok:
        s=storage.get_bind_session(message.text.strip())
        await message.answer(f"✅ Telegram привязан к аккаунту «{s['login']}».")
    else:
        texts={"not_found":"Код не найден.","expired":"Код истёк.","telegram_taken":"Этот Telegram уже используется.",
               "already_bound":"К аккаунту уже привязан Telegram."}
        await message.answer("❌ "+texts.get(reason,"Не удалось выполнить привязку."))

@router.callback_query(F.data.startswith("push_ok:"))
async def push_ok(callback: CallbackQuery):
    sid=callback.data.split(":",1)[1]
    ok=storage.confirm_push_session(sid,callback.from_user.id)
    await callback.answer("Подтверждено" if ok else "Сессия недействительна.")
    if ok: await callback.message.edit_text("✅ Запрос подтверждён. Вернитесь в приложение.")

@router.callback_query(F.data.startswith("push_no:"))
async def push_no(callback: CallbackQuery):
    sid=callback.data.split(":",1)[1]
    ok=storage.reject_push_session(sid,callback.from_user.id)
    await callback.answer("Запрос отклонён" if ok else "Сессия недействительна.")
    if ok: await callback.message.edit_text("❌ Запрос отклонён.")

@router.message()
async def other(message: Message):
    await message.answer("Используйте код привязки из приложения при регистрации. Для входа и восстановления пароля код не нужен.")

async def notifier(bot):
    while True:
        try:
            for sid,s in storage.get_unnotified_push_sessions():
                kind=s["kind"]
                title="вход в систему" if kind=="login" else "восстановление пароля"
                kb=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Подтвердить",callback_data=f"push_ok:{sid}"),
                    InlineKeyboardButton(text="❌ Отклонить",callback_data=f"push_no:{sid}")
                ]])
                try:
                    await bot.send_message(s["telegram_id"],f"🔐 Запрос: {title} для «{s['login']}».\nЕсли это были вы, подтвердите запрос.",reply_markup=kb)
                    storage.mark_push_notified(sid)
                except TelegramAPIError:
                    logger.exception("Telegram send failed")
                    storage.mark_push_failed(sid)
        except Exception:
            logger.exception("Notifier error")
        await asyncio.sleep(POLL)

async def run_bot(token):
    if token.startswith("ВСТАВЬТЕ_"): raise RuntimeError("Не задан BOT_TOKEN в config.py")
    bot=Bot(token=token); dp=Dispatcher(); dp.include_router(router)
    await asyncio.gather(dp.start_polling(bot),notifier(bot))

if __name__=="__main__":
    asyncio.run(run_bot(BOT_TOKEN))
