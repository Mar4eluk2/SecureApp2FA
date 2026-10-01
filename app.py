"""
app.py — GUI-приложение: регистрация с обязательной привязкой Telegram,
вход по логину/паролю и подтверждение входа через Telegram (бот сам
отправляет кнопку привязанному аккаунту — код при входе не нужен).

Запуск: python app.py
(bot.py должен быть запущен отдельно, чтобы можно было привязать Telegram
и подтверждать входы.)
"""

import tkinter as tk
from tkinter import ttk, messagebox

import storage
from config import BOT_USERNAME

POLL_INTERVAL_MS = 1500  # как часто опрашивать статус привязки/входа


class AuthApp(tk.Tk):
    """Главное окно приложения. Переключает между экранами (frames)."""

    def __init__(self):
        super().__init__()
        self.title("Secure App — Вход")
        self.geometry("440x460")
        self.resizable(False, False)

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)

        self.frames = {}
        for F in (LoginFrame, RegisterFrame, BindFrame, LoginConfirmFrame, MainFrame):
            frame = F(container, self)
            self.frames[F.__name__] = frame
            frame.place(relwidth=1, relheight=1)

        self.show_frame("LoginFrame")

    def show_frame(self, name: str, **kwargs):
        frame = self.frames[name]
        if hasattr(frame, "on_show"):
            frame.on_show(**kwargs)
        frame.tkraise()


class LoginFrame(ttk.Frame):
    """Экран входа: логин + пароль (шаг 1). Код при входе не запрашивается —
    после проверки пароля бот сам пришлёт кнопку в привязанный Telegram."""

    def __init__(self, parent, controller: AuthApp):
        super().__init__(parent)
        self.controller = controller

        ttk.Label(self, text="Вход в аккаунт", font=("Segoe UI", 16, "bold")).pack(pady=(40, 20))

        form = ttk.Frame(self)
        form.pack(pady=10)

        ttk.Label(form, text="Логин:").grid(row=0, column=0, sticky="e", padx=5, pady=8)
        self.login_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.login_var, width=28).grid(row=0, column=1, pady=8)

        ttk.Label(form, text="Пароль:").grid(row=1, column=0, sticky="e", padx=5, pady=8)
        self.password_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.password_var, show="•", width=28).grid(row=1, column=1, pady=8)

        self.error_label = ttk.Label(self, text="", foreground="red", wraplength=360, justify="center")
        self.error_label.pack(pady=(0, 10))

        ttk.Button(self, text="Войти", command=self.try_login).pack(pady=5)
        ttk.Button(
            self, text="Нет аккаунта? Зарегистрироваться",
            command=lambda: controller.show_frame("RegisterFrame")
        ).pack(pady=5)

    def on_show(self):
        self.error_label.config(text="")
        self.password_var.set("")

    def try_login(self):
        login = self.login_var.get().strip()
        password = self.password_var.get()

        if not login or not password:
            self.error_label.config(text="Заполните оба поля.")
            return

        if not storage.user_exists(login):
            self.error_label.config(text="Пользователь не найден.")
            return

        if not storage.check_credentials(login, password):
            self.error_label.config(text="Неверный пароль.")
            return

        telegram_id = storage.get_telegram_id(login)

        if not telegram_id:
            # Аккаунт зарегистрирован, но привязку Telegram не завершили —
            # нужно завершить её перед первым входом.
            code = storage.create_bind_session(login)
            self.controller.show_frame("BindFrame", login=login, code=code, purpose="login")
            return

        # Пароль верный и Telegram уже привязан — создаём запрос на вход.
        # Никакого кода пользователю показывать не нужно: бот сам напишет
        # владельцу привязанного Telegram-аккаунта.
        session_id = storage.create_login_session(login)
        if not session_id:
            self.error_label.config(text="Не удалось создать запрос на вход. Попробуйте снова.")
            return

        self.controller.show_frame("LoginConfirmFrame", login=login, session_id=session_id)


class RegisterFrame(ttk.Frame):
    """Экран регистрации нового пользователя. После создания аккаунта сразу
    переходит к обязательной привязке Telegram (BindFrame)."""

    def __init__(self, parent, controller: AuthApp):
        super().__init__(parent)
        self.controller = controller

        ttk.Label(self, text="Регистрация", font=("Segoe UI", 16, "bold")).pack(pady=(40, 20))

        form = ttk.Frame(self)
        form.pack(pady=10)

        ttk.Label(form, text="Логин:").grid(row=0, column=0, sticky="e", padx=5, pady=8)
        self.login_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.login_var, width=28).grid(row=0, column=1, pady=8)

        ttk.Label(form, text="Пароль:").grid(row=1, column=0, sticky="e", padx=5, pady=8)
        self.password_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.password_var, show="•", width=28).grid(row=1, column=1, pady=8)

        ttk.Label(form, text="Повтор пароля:").grid(row=2, column=0, sticky="e", padx=5, pady=8)
        self.password2_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.password2_var, show="•", width=28).grid(row=2, column=1, pady=8)

        self.error_label = ttk.Label(self, text="", foreground="red", wraplength=360, justify="center")
        self.error_label.pack(pady=(0, 10))

        ttk.Button(self, text="Зарегистрироваться", command=self.try_register).pack(pady=5)
        ttk.Button(
            self, text="Назад ко входу",
            command=lambda: controller.show_frame("LoginFrame")
        ).pack(pady=5)

    def on_show(self):
        self.error_label.config(text="")
        self.login_var.set("")
        self.password_var.set("")
        self.password2_var.set("")

    def try_register(self):
        login = self.login_var.get().strip()
        password = self.password_var.get()
        password2 = self.password2_var.get()

        if not login or not password:
            self.error_label.config(text="Заполните все поля.")
            return

        if len(password) < 6:
            self.error_label.config(text="Пароль должен быть не короче 6 символов.")
            return

        if password != password2:
            self.error_label.config(text="Пароли не совпадают.")
            return

        if storage.user_exists(login):
            self.error_label.config(text="Такой логин уже занят.")
            return

        storage.create_user(login, password)

        # Сразу переходим к обязательной привязке Telegram — без этого
        # войти в аккаунт будет нельзя (2FA обязателен).
        code = storage.create_bind_session(login)
        self.controller.show_frame("BindFrame", login=login, code=code, purpose="register")


class BindFrame(ttk.Frame):
    """Экран привязки Telegram-аккаунта. Код здесь вводится ПОЛЬЗОВАТЕЛЕМ
    в чате с ботом только один раз — это единственное место во всей системе,
    где применяется код, который можно ввести вручную."""

    def __init__(self, parent, controller: AuthApp):
        super().__init__(parent)
        self.controller = controller
        self.login = None
        self.code = None
        self.purpose = None  # "register" или "login"
        self._poll_job = None

        ttk.Label(self, text="Привязка Telegram", font=("Segoe UI", 16, "bold")).pack(pady=(30, 10))

        self.instructions_label = ttk.Label(self, text="", justify="center", wraplength=380)
        self.instructions_label.pack(pady=10)

        self.code_label = ttk.Label(self, text="", font=("Consolas", 22, "bold"))
        self.code_label.pack(pady=15)

        self.status_label = ttk.Label(self, text="", foreground="gray", wraplength=380, justify="center")
        self.status_label.pack(pady=10)

        btns = ttk.Frame(self)
        btns.pack(pady=10)
        ttk.Button(btns, text="Новый код", command=self.regenerate).grid(row=0, column=0, padx=5)
        ttk.Button(btns, text="Отмена", command=self.cancel).grid(row=0, column=1, padx=5)

    def on_show(self, login: str, code: str, purpose: str):
        self.login = login
        self.code = code
        self.purpose = purpose
        self.instructions_label.config(
            text=f"Откройте Telegram, найдите бота @{BOT_USERNAME}, отправьте ему /start "
                 f"(если ещё не делали этого), а затем пришлите код ниже — это привяжет "
                 f"ваш Telegram к аккаунту «{login}». Это нужно сделать только один раз."
        )
        self.code_label.config(text=code)
        self.status_label.config(text="Ожидание кода в Telegram...", foreground="gray")
        self._start_polling()

    def regenerate(self):
        self.code = storage.create_bind_session(self.login)
        self.code_label.config(text=self.code)
        self.status_label.config(text="Ожидание кода в Telegram...", foreground="gray")
        self._start_polling()

    def _start_polling(self):
        self._stop_polling()
        self._poll_status()

    def _stop_polling(self):
        if self._poll_job is not None:
            self.after_cancel(self._poll_job)
            self._poll_job = None

    def _poll_status(self):
        status = storage.get_bind_session_status(self.code)

        if status == "confirmed":
            self._stop_polling()
            self._on_confirmed()
            return

        if status in ("expired", "not_found", "rejected"):
            self._stop_polling()
            messages = {
                "expired": "⌛ Код истёк. Нажмите «Новый код».",
                "not_found": "Ошибка сессии. Нажмите «Новый код».",
                "rejected": "❌ Не удалось привязать: аккаунт уже привязан к другому "
                            "Telegram, либо этот Telegram уже занят другим логином.",
            }
            self.status_label.config(text=messages[status], foreground="red")
            return

        self._poll_job = self.after(POLL_INTERVAL_MS, self._poll_status)

    def _on_confirmed(self):
        if self.purpose == "register":
            messagebox.showinfo("Готово", "Telegram успешно привязан! Теперь вы можете войти.")
            self.controller.show_frame("LoginFrame")
        else:
            # purpose == "login" — привязка была нужна прямо перед входом,
            # поэтому сразу продолжаем и создаём запрос на подтверждение.
            session_id = storage.create_login_session(self.login)
            if session_id:
                self.controller.show_frame(
                    "LoginConfirmFrame", login=self.login, session_id=session_id
                )
            else:
                messagebox.showinfo("Готово", "Telegram привязан. Войдите ещё раз.")
                self.controller.show_frame("LoginFrame")

    def cancel(self):
        self._stop_polling()
        self.controller.show_frame("LoginFrame")


class LoginConfirmFrame(ttk.Frame):
    """Экран ожидания подтверждения входа. Код здесь НЕ показывается —
    бот сам отправил кнопку подтверждения в привязанный Telegram-аккаунт,
    приложение лишь опрашивает статус этого запроса."""

    def __init__(self, parent, controller: AuthApp):
        super().__init__(parent)
        self.controller = controller
        self.login = None
        self.session_id = None
        self._poll_job = None

        ttk.Label(self, text="Подтверждение входа", font=("Segoe UI", 16, "bold")).pack(pady=(50, 15))

        self.instructions_label = ttk.Label(self, text="", justify="center", wraplength=380)
        self.instructions_label.pack(pady=15)

        self.status_label = ttk.Label(self, text="", foreground="gray")
        self.status_label.pack(pady=15)

        ttk.Button(self, text="Отмена", command=self.cancel).pack(pady=10)

    def on_show(self, login: str, session_id: str):
        self.login = login
        self.session_id = session_id
        self.instructions_label.config(
            text=f"Мы отправили запрос на подтверждение в Telegram, привязанный к "
                 f"аккаунту «{login}».\nОткройте чат с ботом @{BOT_USERNAME} и нажмите "
                 f"«✅ Подтвердить вход»."
        )
        self.status_label.config(text="Ожидание подтверждения...", foreground="gray")
        self._start_polling()

    def _start_polling(self):
        self._stop_polling()
        self._poll_status()

    def _stop_polling(self):
        if self._poll_job is not None:
            self.after_cancel(self._poll_job)
            self._poll_job = None

    def _poll_status(self):
        status = storage.get_login_session_status(self.session_id)

        if status == "confirmed":
            self._stop_polling()
            self.controller.show_frame("MainFrame", login=self.login)
            return

        if status == "expired":
            self._stop_polling()
            self.status_label.config(text="⌛ Запрос истёк. Попробуйте войти заново.", foreground="red")
            self.after(2000, lambda: self.controller.show_frame("LoginFrame"))
            return

        if status == "failed":
            self._stop_polling()
            self.status_label.config(
                text="❌ Не удалось отправить сообщение в Telegram (возможно, бот заблокирован).",
                foreground="red",
            )
            self.after(3000, lambda: self.controller.show_frame("LoginFrame"))
            return

        if status == "not_found":
            self._stop_polling()
            self.status_label.config(text="Ошибка сессии. Попробуйте снова.", foreground="red")
            self.after(2000, lambda: self.controller.show_frame("LoginFrame"))
            return

        # ещё pending (в т.ч. бот мог ещё не успеть отправить сообщение) — продолжаем опрос
        self._poll_job = self.after(POLL_INTERVAL_MS, self._poll_status)

    def cancel(self):
        self._stop_polling()
        self.controller.show_frame("LoginFrame")


class MainFrame(ttk.Frame):
    """Защищённая рабочая зона — доступна только после подтверждения в Telegram."""

    def __init__(self, parent, controller: AuthApp):
        super().__init__(parent)
        self.controller = controller

        self.welcome_label = ttk.Label(self, text="", font=("Segoe UI", 16, "bold"))
        self.welcome_label.pack(pady=(70, 10))

        ttk.Label(self, text="✅ Успешный вход! Это защищённая рабочая зона.").pack(pady=10)

        ttk.Button(self, text="Выйти из аккаунта", command=self.logout).pack(pady=30)

    def on_show(self, login: str):
        self.welcome_label.config(text=f"Добро пожаловать, {login}!")

    def logout(self):
        self.controller.show_frame("LoginFrame")


if __name__ == "__main__":
    app = AuthApp()
    app.mainloop()
