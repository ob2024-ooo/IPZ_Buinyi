"""Серверна частина системи бронювання та купівлі залізничних квитків (варіант 6).

Консольна програма: приймає TCP-з'єднання, розбирає JSON-команди,
виконує їх над базою SQLite і повертає JSON-відповідь.

Запуск:  python server.py            (порт і файл БД - у config.json)
         python server.py --reset    (перестворити БД з демо-даними)
"""
import argparse
import json
import os
import socket
import socketserver
import sqlite3
import sys
import threading
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from db import Database  # noqa: E402
from protocol import AppError, encode, fail, fmt, now, ok  # noqa: E402
from services import AuthService, RatingService, TicketService, TripService  # noqa: E402
import seed  # noqa: E402


def load_config(path=None):
    path = path or os.path.join(HERE, "config.json")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if not os.path.isabs(cfg["database"]):
        cfg["database"] = os.path.join(HERE, cfg["database"])
    return cfg


class CommandDispatcher:
    """Зіставляє назву команди з методом сервісу та виконує його в транзакції."""

    def __init__(self, database, config):
        self.db = database
        self.quiet = config.get("quiet", False)
        auth = AuthService(config)
        trips = TripService(auth)
        tickets = TicketService(auth, config)
        ratings = RatingService(auth)
        self.handlers = {
            "ping": lambda conn, req: ("Сервер працює.", {"time": fmt(now())}),
            "register": auth.register,
            "login": auth.login,
            "logout": auth.logout,
            "searchtripsbyname": trips.search_by_name,
            "searchtripsbydate": trips.search_by_date,
            "tripdetails": trips.trip_details,
            "bookticket": tickets.book,
            "buyticket": tickets.buy,
            "payticket": tickets.pay,
            "cancelticket": tickets.cancel,
            "mytickets": tickets.my_tickets,
            "ratetrip": ratings.rate,
            "trainrating": ratings.train_rating,
        }

    def dispatch(self, raw_line, client_addr="local"):
        command = "?"
        try:
            try:
                req = json.loads(raw_line)
            except (ValueError, UnicodeDecodeError):
                raise AppError("BAD_JSON", "Запит не є коректним JSON.")
            if not isinstance(req, dict):
                raise AppError("BAD_JSON", "Запит має бути JSON-об'єктом.")
            command = str(req.get("command", "")).strip().lower()
            if not command:
                raise AppError("MISSING_FIELD", "Не вказано команду (поле 'command').")
            handler = self.handlers.get(command)
            if handler is None:
                raise AppError("UNKNOWN_COMMAND", "Невідома команда '%s'." % command)
            with self.db.write_lock:
                conn = self.db.connect()
                try:
                    message, data = handler(conn, req)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()
            response = ok(message, data)
        except AppError as e:
            response = fail(e.code, e.message)
        except sqlite3.Error as e:
            response = fail("DB_ERROR", "Помилка бази даних: %s" % e)
        except Exception as e:  # будь-яка інша помилка не повинна "покласти" сервер
            response = fail("INTERNAL", "Внутрішня помилка сервера: %s" % e)
        self._log(client_addr, command, response)
        return response

    def _log(self, client_addr, command, response):
        try:
            with self.db.write_lock:
                conn = self.db.connect()
                conn.execute("INSERT INTO RequestLog (ReceivedAt, ClientAddr, Command, Success, Code) "
                             "VALUES (?,?,?,?,?)",
                             (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), client_addr, command[:40],
                              1 if response["success"] else 0, response["code"]))
                conn.commit()
                conn.close()
        except sqlite3.Error:
            pass
        if self.quiet:
            return
        print("[%s] %-15s %-18s -> %s %s" % (
            datetime.now().strftime("%H:%M:%S"), client_addr, command, response["code"],
            response["message"]), flush=True)


class RequestHandler(socketserver.StreamRequestHandler):
    """Обробка одного TCP-з'єднання: можна надіслати кілька запитів, кожен - окремим рядком."""

    def handle(self):
        cfg = self.server.config
        self.connection.settimeout(cfg.get("socket_timeout_sec", 10))
        addr = "%s:%s" % self.client_address[:2]
        limit = cfg.get("max_request_bytes", 65536)
        while True:
            try:
                line = self.rfile.readline(limit + 1)
            except (socket.timeout, ConnectionError, OSError):
                return
            if not line:
                return
            if len(line) > limit and not line.endswith(b"\n"):
                self._send(fail("TOO_LARGE", "Запит перевищує %d байт." % limit))
                return
            if not line.strip():
                continue
            response = self.server.dispatcher.dispatch(line.decode("utf-8", errors="replace"), addr)
            if not self._send(response):
                return

    def _send(self, response):
        try:
            self.wfile.write(encode(response))
            self.wfile.flush()
            return True
        except (ConnectionError, OSError):
            return False


class TicketServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, config, database):
        self.config = config
        self.dispatcher = CommandDispatcher(database, config)
        super().__init__((config["host"], config["port"]), RequestHandler)


def prepare_database(config, reset=False):
    if reset and os.path.exists(config["database"]):
        os.remove(config["database"])
    database = Database(config["database"])
    database.create_schema()
    if database.is_empty():
        seed.fill(database)
        print("Базу даних заповнено демо-даними:", config["database"])
    return database


def start_in_thread(config=None, reset=False):
    """Запуск сервера у фоновому потоці (використовується run.py і тестами)."""
    config = config or load_config()
    database = prepare_database(config, reset)
    server = TicketServer(config, database)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="TCP-сервер продажу залізничних квитків")
    parser.add_argument("--reset", action="store_true", help="перестворити БД з демо-даними")
    parser.add_argument("--port", type=int, help="порт (за замовчуванням з config.json)")
    args = parser.parse_args()
    config = load_config()
    if args.port:
        config["port"] = args.port
    database = prepare_database(config, args.reset)
    try:
        server = TicketServer(config, database)
    except OSError as e:
        print("Не вдалося відкрити порт %s: %s" % (config["port"], e))
        sys.exit(1)
    print("=" * 70)
    print(" Сервер залізничних квитків запущено на %s:%s" % (config["host"], config["port"]))
    print(" База даних:", database.path)
    print(" Ctrl+C - зупинити сервер")
    print("=" * 70, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер зупинено.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
