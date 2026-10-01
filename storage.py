"""
storage.py — общие функции для работы с JSON-хранилищем пользователей и
сессий. Используется и в app.py (GUI), и в bot.py (Telegram-бот).

Модель безопасности 2FA:
- Telegram-аккаунт привязывается к логину РОВНО ОДИН РАЗ — во время
  регистрации, через отдельный код привязки (bind-код), который пользователь
  сам набирает в чате с ботом.
- При входе и при сбросе пароля бот НЕ ждёт код от пользователя — он сам
  находит telegram_id, привязанный к логину, и сам отправляет ИМЕННО ТУДА
  сообщение с inline-кнопкой подтверждения ("push-сессия"). Значит
  подтвердить действие может только владелец уже привязанного
  Telegram-аккаунта, даже если пароль узнает кто-то посторонний.
- Один Telegram-аккаунт нельзя привязать более чем к одному логину.

Роли:
- "admin"    — полный доступ (управление складом, пользователями, журналом).
- "employee" — минимальные права (просмотр склада, продажа). Это роль по
  умолчанию для всех, кто регистрируется самостоятельно через GUI.
Ровно один администратор создаётся автоматически при первом запуске
(см. ensure_default_admin()).

ВАЖНО: это учебная/демонстрационная реализация. Для продакшена вместо
JSON-файлов стоит использовать настоящую базу данных с транзакциями.
"""

import json
import os
import sys
import hashlib
import secrets
import time

if getattr(sys, "frozen", False):
    # PyInstaller --onefile распаковывается во временную папку, которая
    # удаляется при выходе — поэтому храним данные рядом с самим exe.
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

USERS_FILE = os.path.join(BASE_DIR, "users.json")
BIND_SESSIONS_FILE = os.path.join(BASE_DIR, "bind_sessions.json")
PUSH_SESSIONS_FILE = os.path.join(BASE_DIR, "push_sessions.json")

BIND_CODE_TTL_SECONDS = 300  # сколько живёт код привязки Telegram (при регистрации)

# TTL push-сессий по типу: "login" (вход) и "reset" (сброс пароля)
PUSH_SESSION_TTL_SECONDS = {
    "login": 120,
    "reset": 300,
}

ROLE_ADMIN = "admin"
ROLE_EMPLOYEE = "employee"
DEFAULT_ADMIN_LOGIN = "admin"


# ---------- Низкоуровневые JSON-хелперы ----------

def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return json.loads(content) if content else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_json(path: str, data: dict) -> None:
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


# ---------- Пользователи и пароли ----------

def load_users() -> dict:
    return _load_json(USERS_FILE)


def save_users(users: dict) -> None:
    _save_json(USERS_FILE, users)


def hash_password(password: str, salt: str = None):
    """PBKDF2-HMAC-SHA256 со случайной солью. Возвращает (hash_hex, salt_hex)."""
    if salt is None:
        salt = secrets.token_hex(16)
    salt_bytes = bytes.fromhex(salt)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 100_000)
    return pwd_hash.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    calc_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(calc_hash, stored_hash)


def user_exists(login: str) -> bool:
    return login in load_users()


def create_user(login: str, password: str, role: str = ROLE_EMPLOYEE) -> None:
    """Создаёт пользователя. Все, кто регистрируется сам через GUI, получают
    минимальную роль ROLE_EMPLOYEE — role=ROLE_ADMIN сюда вручную не передаётся
    нигде в коде приложения, кроме ensure_default_admin()."""
    users = load_users()
    pwd_hash, salt = hash_password(password)
    users[login] = {
        "password_hash": pwd_hash,
        "salt": salt,
        "telegram_id": None,  # привязывается через bind-код сразу после регистрации
        "role": role,
    }
    save_users(users)


def check_credentials(login: str, password: str) -> bool:
    users = load_users()
    user = users.get(login)
    if not user:
        return False
    return verify_password(password, user["password_hash"], user["salt"])


def reset_password(login: str, new_password: str) -> bool:
    """Задаёт новый пароль (используется и самостоятельным восстановлением
    через Telegram, и сбросом администратором)."""
    users = load_users()
    if login not in users:
        return False
    pwd_hash, salt = hash_password(new_password)
    users[login]["password_hash"] = pwd_hash
    users[login]["salt"] = salt
    save_users(users)
    return True


def admin_generate_temp_password(login: str):
    """Генерирует и сразу устанавливает случайный временный пароль для
    пользователя (инструмент администратора). Возвращает пароль в открытом
    виде ОДИН РАЗ — его нужно передать пользователю отдельным безопасным
    способом (не хранится нигде, кроме как в виде хеша)."""
    users = load_users()
    if login not in users:
        return None
    new_password = secrets.token_urlsafe(9)  # ~12 читаемых символов
    reset_password(login, new_password)
    return new_password


# ---------- Роли ----------

def get_role(login: str) -> str:
    return load_users().get(login, {}).get("role", ROLE_EMPLOYEE)


def list_users() -> dict:
    """Для панели администратора: логин -> {role, telegram_linked}.
    Хеши и соль паролей сюда намеренно не включаются."""
    users = load_users()
    return {
        login: {
            "role": u.get("role", ROLE_EMPLOYEE),
            "telegram_linked": bool(u.get("telegram_id")),
        }
        for login, u in users.items()
    }


def set_role(login: str, new_role: str):
    """Меняет роль пользователя. Отказывает, если это последний администратор
    в системе — чтобы случайно не остаться без единого админ-аккаунта.
    Возвращает (успех: bool, причина_отказа: str)."""
    users = load_users()
    if login not in users:
        return False, "not_found"

    current_role = users[login].get("role", ROLE_EMPLOYEE)
    if current_role == ROLE_ADMIN and new_role != ROLE_ADMIN:
        admin_count = sum(1 for u in users.values() if u.get("role") == ROLE_ADMIN)
        if admin_count <= 1:
            return False, "last_admin"

    users[login]["role"] = new_role
    save_users(users)
    return True, ""


def ensure_default_admin():
    """Гарантирует существование ровно одного администратора. Вызывается при
    старте приложения. Если админа ещё нет — создаёт логин DEFAULT_ADMIN_LOGIN
    со случайным паролем и возвращает этот пароль (его нужно один раз
    показать пользователю — больше он нигде не сохраняется в открытом виде).
    Если администратор уже есть — возвращает None, ничего не создаёт."""
    users = load_users()
    if any(u.get("role") == ROLE_ADMIN for u in users.values()):
        return None

    login = DEFAULT_ADMIN_LOGIN
    if login in users:
        # Редкий случай: логин "admin" занят обычным пользователем —
        # просто повышаем его роль, не трогая существующий пароль.
        users[login]["role"] = ROLE_ADMIN
        save_users(users)
        return None

    password = secrets.token_urlsafe(9)
    pwd_hash, salt = hash_password(password)
    users[login] = {
        "password_hash": pwd_hash,
        "salt": salt,
        "telegram_id": None,
        "role": ROLE_ADMIN,
    }
    save_users(users)
    return password


# ---------- Telegram: привязка и восстановление ----------

def get_telegram_id(login: str):
    return load_users().get(login, {}).get("telegram_id")


def is_telegram_id_taken(telegram_id: int) -> bool:
    """Проверяет, не привязан ли этот Telegram-аккаунт уже к другому логину."""
    users = load_users()
    return any(u.get("telegram_id") == telegram_id for u in users.values())


def bind_telegram_id(login: str, telegram_id: int) -> bool:
    """Привязывает telegram_id к логину. Возвращает False, если логина нет,
    у логина уже есть привязанный Telegram, или этот telegram_id уже
    привязан к другому логину."""
    users = load_users()
    user = users.get(login)
    if not user:
        return False
    if user.get("telegram_id"):
        return False
    if is_telegram_id_taken(telegram_id):
        return False
    user["telegram_id"] = telegram_id
    save_users(users)
    return True


def unbind_telegram(login: str) -> bool:
    """Инструмент администратора: отвязывает Telegram от аккаунта.
    Нужен для восстановления доступа, если пользователь потерял доступ к
    своему Telegram-аккаунту — после этого он сможет привязать новый при
    следующей попытке входа (см. LoginFrame в app.py)."""
    users = load_users()
    if login not in users:
        return False
    users[login]["telegram_id"] = None
    save_users(users)
    return True


# ---------- Bind-сессии (привязка Telegram — только при регистрации) ----------

def _generate_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))


def create_bind_session(login: str) -> str:
    """Создаёт одноразовый код привязки Telegram-аккаунта к логину."""
    sessions = _load_json(BIND_SESSIONS_FILE)
    code = _generate_code()
    while code in sessions:
        code = _generate_code()

    now = time.time()
    sessions[code] = {
        "login": login,
        "created_at": now,
        "expires_at": now + BIND_CODE_TTL_SECONDS,
        "status": "pending",  # pending -> confirmed / expired / rejected
    }
    _save_json(BIND_SESSIONS_FILE, sessions)
    return code


def get_bind_session(code: str):
    return _load_json(BIND_SESSIONS_FILE).get(code)


def get_bind_session_status(code: str) -> str:
    sessions = _load_json(BIND_SESSIONS_FILE)
    session = sessions.get(code)
    if not session:
        return "not_found"
    if session["status"] == "pending" and time.time() > session["expires_at"]:
        session["status"] = "expired"
        sessions[code] = session
        _save_json(BIND_SESSIONS_FILE, sessions)
    return session["status"]


def confirm_bind_session(code: str, telegram_id: int):
    """Вызывается ботом, когда пользователь присылает код привязки.
    Возвращает (успех: bool, причина_отказа: str)."""
    sessions = _load_json(BIND_SESSIONS_FILE)
    session = sessions.get(code)
    if not session:
        return False, "not_found"
    if session["status"] != "pending":
        return False, session["status"]
    if time.time() > session["expires_at"]:
        session["status"] = "expired"
        sessions[code] = session
        _save_json(BIND_SESSIONS_FILE, sessions)
        return False, "expired"

    login = session["login"]
    if not bind_telegram_id(login, telegram_id):
        reason = "telegram_taken" if is_telegram_id_taken(telegram_id) else "already_bound"
        session["status"] = "rejected"
        sessions[code] = session
        _save_json(BIND_SESSIONS_FILE, sessions)
        return False, reason

    session["status"] = "confirmed"
    sessions[code] = session
    _save_json(BIND_SESSIONS_FILE, sessions)
    return True, ""


# ---------- Push-сессии: вход ("login") и сброс пароля ("reset") ----------
# Пользователь НИЧЕГО не вводит боту — бот сам находит привязанный telegram_id
# и сам шлёт туда кнопку подтверждения. Это единый механизм для обоих случаев,
# отличается только TTL и текстом сообщения (формируется в bot.py).

def create_push_session(login: str, kind: str):
    """Создаёт push-сессию. Требует, чтобы у логина уже был привязан
    telegram_id — иначе возвращает None (нужно сначала привязать Telegram)."""
    telegram_id = get_telegram_id(login)
    if not telegram_id:
        return None

    sessions = _load_json(PUSH_SESSIONS_FILE)
    session_id = secrets.token_hex(16)
    while session_id in sessions:
        session_id = secrets.token_hex(16)

    now = time.time()
    ttl = PUSH_SESSION_TTL_SECONDS.get(kind, 120)
    sessions[session_id] = {
        "login": login,
        "telegram_id": telegram_id,
        "kind": kind,  # "login" или "reset"
        "created_at": now,
        "expires_at": now + ttl,
        "status": "pending",  # pending -> confirmed / expired / failed
        "notified": False,    # бот ещё не отправил inline-кнопку
    }
    _save_json(PUSH_SESSIONS_FILE, sessions)
    return session_id


def get_push_session(session_id: str):
    return _load_json(PUSH_SESSIONS_FILE).get(session_id)


def get_push_session_status(session_id: str) -> str:
    sessions = _load_json(PUSH_SESSIONS_FILE)
    session = sessions.get(session_id)
    if not session:
        return "not_found"
    if session["status"] == "pending" and time.time() > session["expires_at"]:
        session["status"] = "expired"
        sessions[session_id] = session
        _save_json(PUSH_SESSIONS_FILE, sessions)
    return session["status"]


def get_unnotified_push_sessions():
    """Для фонового цикла бота: список (session_id, session) сессий, о
    которых ещё не отправлено сообщение с кнопкой подтверждения."""
    sessions = _load_json(PUSH_SESSIONS_FILE)
    result = []
    changed = False
    for session_id, session in sessions.items():
        if session["status"] != "pending":
            continue
        if time.time() > session["expires_at"]:
            session["status"] = "expired"
            changed = True
        elif not session.get("notified"):
            result.append((session_id, dict(session)))
    if changed:
        _save_json(PUSH_SESSIONS_FILE, sessions)
    return result


def mark_push_notified(session_id: str) -> None:
    sessions = _load_json(PUSH_SESSIONS_FILE)
    if session_id in sessions:
        sessions[session_id]["notified"] = True
        _save_json(PUSH_SESSIONS_FILE, sessions)


def mark_push_failed(session_id: str) -> None:
    """Если бот не смог отправить сообщение (например, пользователь
    заблокировал бота) — помечаем сессию неудачной, чтобы GUI не ждал вечно."""
    sessions = _load_json(PUSH_SESSIONS_FILE)
    if session_id in sessions:
        sessions[session_id]["status"] = "failed"
        _save_json(PUSH_SESSIONS_FILE, sessions)


def confirm_push_session(session_id: str, telegram_id: int) -> bool:
    """Вызывается ботом при нажатии inline-кнопки. Дополнительно сверяет
    telegram_id нажавшего с адресатом сессии — защита на случай подделки
    callback_data посторонним пользователем."""
    sessions = _load_json(PUSH_SESSIONS_FILE)
    session = sessions.get(session_id)
    if not session:
        return False
    if session["status"] != "pending":
        return False
    if time.time() > session["expires_at"]:
        session["status"] = "expired"
        sessions[session_id] = session
        _save_json(PUSH_SESSIONS_FILE, sessions)
        return False
    if session["telegram_id"] != telegram_id:
        return False  # чужой Telegram пытается подтвердить не свою сессию

    session["status"] = "confirmed"
    sessions[session_id] = session
    _save_json(PUSH_SESSIONS_FILE, sessions)
    return True
