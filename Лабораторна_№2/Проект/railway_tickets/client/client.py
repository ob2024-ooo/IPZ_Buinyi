"""Клієнтська частина (GUI) системи бронювання та купівлі залізничних квитків.

Інтерфейс відкривається у вікні браузера, а вся логіка клієнта (сутності, перевірка
даних, сесія, обмін з сервером по TCP) виконується в цьому Python-процесі.
Нічого встановлювати не потрібно - лише стандартна бібліотека Python 3.8+.

Запуск:  python client.py                 (сервер 127.0.0.1:5055, GUI на http://127.0.0.1:8080)
         python client.py --server-port 5055 --gui-port 8080 --no-browser
"""
import argparse
import json
import mimetypes
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from entities import (AppSession, LoginEntity, RatingEntity, RegisterEntity,  # noqa: E402
                      SearchEntity, TicketOrderEntity, ValidationError)
from network_client import ApiError, NetworkClient  # noqa: E402

WEB_DIR = os.path.join(HERE, "web")


class ClientController:
    """Обробники дій користувача. Кожна дія: сутність -> перевірка -> запит на сервер."""

    def __init__(self, network):
        self.net = network
        self.session = AppSession()

    def _token(self):
        if not self.session.is_logged_in:
            raise ApiError("UNAUTHORIZED", "Спочатку увійдіть у систему.")
        return self.session.token

    def _call(self, command, **fields):
        try:
            return self.net.send(command, **fields)
        except ApiError as e:
            if e.code == "UNAUTHORIZED":
                self.session.clear()
            raise

    # ---------- дії ----------
    def session_info(self, body):
        return "", {"loggedIn": self.session.is_logged_in, "login": self.session.login,
                    "fullName": self.session.full_name,
                    "server": "%s:%s" % (self.net.host, self.net.port)}

    def login(self, body):
        entity = LoginEntity(body.get("login"), body.get("password"))
        entity.validate()
        message, data = self._call("login", login=entity.login, password=entity.password)
        self.session.token = data["token"]
        self.session.login = data["login"]
        self.session.full_name = data.get("fullName")
        return message, {"login": data["login"], "fullName": data.get("fullName", "")}

    def register(self, body):
        entity = RegisterEntity(body.get("login"), body.get("password"),
                                body.get("confirmPassword"), body.get("fullName"))
        entity.validate()
        return self._call("register", login=entity.login, password=entity.password,
                          fullName=entity.full_name)

    def logout(self, body):
        try:
            message, _ = self._call("logout", token=self._token())
        finally:
            self.session.clear()
        return message, {}

    def search(self, body):
        entity = SearchEntity(body.get("mode", "name"), body.get("query"))
        entity.validate()
        if entity.mode == "name":
            return self._call("searchtripsbyname", token=self._token(), name=entity.query)
        return self._call("searchtripsbydate", token=self._token(), date=entity.parsed_date().isoformat())

    def trip(self, body):
        return self._call("tripdetails", token=self._token(), tripId=body.get("tripId"))

    def order(self, body):
        entity = TicketOrderEntity(body.get("tripId"), body.get("seatNumber"), body.get("action", "buy"))
        entity.validate()
        command = "buyticket" if entity.action == "buy" else "bookticket"
        return self._call(command, token=self._token(), tripId=entity.trip_id, seatNumber=entity.seat_number)

    def my_tickets(self, body):
        return self._call("mytickets", token=self._token())

    def pay(self, body):
        return self._call("payticket", token=self._token(), ticketId=body.get("ticketId"))

    def cancel(self, body):
        return self._call("cancelticket", token=self._token(), ticketId=body.get("ticketId"))

    def rate(self, body):
        entity = RatingEntity(body.get("tripId"), body.get("stars"), body.get("comment"))
        entity.validate()
        return self._call("ratetrip", token=self._token(), tripId=entity.trip_id,
                          stars=entity.stars, comment=entity.comment)

    def train_rating(self, body):
        return self._call("trainrating", token=self._token())

    ACTIONS = {
        "session": session_info, "login": login, "register": register, "logout": logout,
        "search": search, "trip": trip, "order": order, "mytickets": my_tickets,
        "pay": pay, "cancel": cancel, "rate": rate, "trainrating": train_rating,
    }

    def handle(self, action, body):
        handler = self.ACTIONS.get(action)
        if handler is None:
            return {"ok": False, "code": "UNKNOWN_ACTION", "message": "Невідома дія."}
        try:
            message, data = handler(self, body)
            return {"ok": True, "message": message, "data": data}
        except ValidationError as e:
            return {"ok": False, "code": "CLIENT_VALIDATION", "message": str(e)}
        except ApiError as e:
            return {"ok": False, "code": e.code, "message": e.message}
        except Exception as e:  # непередбачена помилка - показуємо, а не падаємо
            return {"ok": False, "code": "CLIENT_ERROR", "message": "Помилка клієнта: %s" % e}


class GuiRequestHandler(BaseHTTPRequestHandler):
    controller = None  # встановлюється в main()

    def log_message(self, fmt, *args):
        pass  # не засмічуємо консоль

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            path = "/index.html"
        file_path = os.path.normpath(os.path.join(WEB_DIR, path.lstrip("/")))
        if not file_path.startswith(WEB_DIR) or not os.path.isfile(file_path):
            self.send_error(404)
            return
        with open(file_path, "rb") as f:
            content = f.read()
        ctype = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._reply(200, content, ctype)

    def do_POST(self):
        if not self.path.startswith("/api/"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            body = {}
        result = self.controller.handle(self.path[5:], body)
        self._reply(200, json.dumps(result, ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8")

    def _reply(self, status, content, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)


def create_gui_server(server_host="127.0.0.1", server_port=5055, gui_port=8080):
    GuiRequestHandler.controller = ClientController(NetworkClient(server_host, server_port))
    return ThreadingHTTPServer(("127.0.0.1", gui_port), GuiRequestHandler)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Клієнт системи продажу залізничних квитків")
    p.add_argument("--server-host", default="127.0.0.1")
    p.add_argument("--server-port", type=int, default=5055)
    p.add_argument("--gui-port", type=int, default=8080)
    p.add_argument("--no-browser", action="store_true")
    a = p.parse_args()
    try:
        httpd = create_gui_server(a.server_host, a.server_port, a.gui_port)
    except OSError as e:
        print("Порт %s зайнятий (%s). Запустіть з --gui-port 8081" % (a.gui_port, e))
        sys.exit(1)
    url = "http://127.0.0.1:%d/" % a.gui_port
    print("Клієнт запущено. Відкрийте у браузері:", url)
    print("Сервер квитків:", "%s:%s" % (a.server_host, a.server_port), "| Ctrl+C - вихід", flush=True)
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nКлієнт зупинено.")


if __name__ == "__main__":
    main()
