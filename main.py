"""
main.py — единая точка входа для сборки в ОДИН .exe файл (PyInstaller).

Запускает Telegram-бота (обработку сообщений + фоновый цикл уведомлений
о входе) в отдельном потоке и Tkinter GUI в главном потоке — всё внутри
одного процесса. Именно main.py нужно указывать PyInstaller'у.

Для обычной разработки/отладки по-прежнему можно запускать app.py и bot.py
по отдельности (см. README) — так удобнее видеть логи бота в своём терминале.
"""

import asyncio
import logging
import threading

from config import BOT_TOKEN
import bot as bot_module   # переиспользуем run_bot() из bot.py — одна точка правды
from app import AuthApp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_bot_in_thread() -> None:
    """Запускает бота (polling + фоновый нотификатор входов) в отдельном
    потоке со своим event loop."""
    try:
        asyncio.run(bot_module.run_bot(BOT_TOKEN))
    except Exception:
        logger.exception("Бот аварийно завершился")


def main() -> None:
    bot_thread = threading.Thread(target=run_bot_in_thread, daemon=True)
    bot_thread.start()

    # GUI — в главном потоке (обязательно для Tkinter).
    app = AuthApp()
    app.mainloop()


if __name__ == "__main__":
    main()
