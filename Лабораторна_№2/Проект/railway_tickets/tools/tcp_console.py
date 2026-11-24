"""Консольний TCP-клієнт для перевірки API сервера (ЛР3).

    python tools/tcp_console.py '{"command":"ping"}'
    python tools/tcp_console.py            - інтерактивний режим: вводьте JSON-рядки

Токен з відповіді на login запам'ятовується і підставляється автоматично.
"""
import json
import socket
import sys

HOST, PORT = "127.0.0.1", 5055
token = None


def send(line):
    global token
    req = json.loads(line)
    if token and "token" not in req and req.get("command") not in ("login", "register", "ping"):
        req["token"] = token
    raw = json.dumps(req, ensure_ascii=False)
    print(">>> " + raw)
    with socket.create_connection((HOST, PORT), timeout=5) as s:
        s.sendall((raw + "\n").encode("utf-8"))
        resp = json.loads(s.makefile("rb").readline().decode("utf-8"))
    if resp.get("data", {}).get("token"):
        token = resp["data"]["token"]
    print("<<< " + json.dumps(resp, ensure_ascii=False, indent=2))
    return resp


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            send(arg)
        return
    print("Підключення до %s:%s. Введіть JSON-запит (порожній рядок - вихід)." % (HOST, PORT))
    while True:
        line = input("json> ").strip()
        if not line:
            break
        try:
            send(line)
        except (ValueError, OSError) as e:
            print("Помилка:", e)


if __name__ == "__main__":
    main()
