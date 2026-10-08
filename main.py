import asyncio, logging, threading
import storage
from config import BOT_TOKEN
import bot as bot_module
from app import AuthApp

logging.basicConfig(level=logging.INFO)

def run_bot():
    try:
        asyncio.run(bot_module.run_bot(BOT_TOKEN))
    except Exception:
        logging.exception("Telegram bot stopped")

def main():
    storage.ensure_data()
    admin_password=storage.ensure_default_admin()
    app=AuthApp()
    if admin_password:
        app.after(300,lambda: app.show_admin_password(admin_password))
    threading.Thread(target=run_bot,daemon=True).start()
    app.mainloop()

if __name__=="__main__":
    main()
