"""Протокол обміну: один рядок JSON (закінчується '\\n') -> один рядок JSON у відповідь.

Запит:     {"command": "login", "login": "...", "password": "..."}
Відповідь: {"success": true/false, "code": "OK"/"...", "message": "...", "data": {...}}
"""
import json
from datetime import datetime

DT_FORMAT = "%Y-%m-%d %H:%M"


class AppError(Exception):
    """Бізнес-помилка, яка повертається клієнту як success=false."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def ok(message="Успішно.", data=None):
    return {"success": True, "code": "OK", "message": message, "data": data or {}}


def fail(code, message):
    return {"success": False, "code": code, "message": message, "data": {}}


def encode(response):
    return (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")


def now():
    return datetime.now().replace(second=0, microsecond=0)


def fmt(dt):
    return dt.strftime(DT_FORMAT) if dt else None


def parse_dt(value):
    return datetime.strptime(value, DT_FORMAT)


# ---- читання полів запиту з перевіркою ----

def req_str(req, name, allow_empty=False, max_len=200):
    if name not in req or req[name] is None:
        raise AppError("MISSING_FIELD", "Не передано поле '%s'." % name)
    value = req[name]
    if not isinstance(value, str):
        raise AppError("INVALID_FIELD", "Поле '%s' має бути рядком." % name)
    value = value.strip()
    if not allow_empty and not value:
        raise AppError("MISSING_FIELD", "Поле '%s' не може бути порожнім." % name)
    if len(value) > max_len:
        raise AppError("INVALID_FIELD", "Поле '%s' задовге." % name)
    return value


def req_int(req, name):
    if name not in req or req[name] is None or req[name] == "":
        raise AppError("MISSING_FIELD", "Не передано поле '%s'." % name)
    value = req[name]
    if isinstance(value, bool):
        raise AppError("INVALID_FIELD", "Поле '%s' має бути цілим числом." % name)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise AppError("INVALID_FIELD", "Поле '%s' має бути цілим числом." % name)
