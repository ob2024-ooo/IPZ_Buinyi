"""Запуск усієї системи однією командою: сервер (TCP 5055) + клієнт (GUI у браузері).

    python run.py            - запустити
    python run.py --reset    - перестворити базу даних з демо-даними і запустити

Можна запускати і окремо: python server/server.py  та  python client/client.py
"""
import argparse
import os
import sys
import threading
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(ROOT, "client"))

import server as srv  # noqa: E402
import client as cli  # noqa: E402


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--reset", action="store_true", help="перестворити БД з демо-даними")
    p.add_argument("--gui-port", type=int, default=8080)
    p.add_argument("--no-browser", action="store_true")
    a = p.parse_args()

    config = srv.load_config()
    try:
        tcp = srv.start_in_thread(config, reset=a.reset)
    except OSError as e:
        print("Не вдалося запустити сервер на порту %s: %s" % (config["port"], e))
        print("Можливо, сервер уже запущено окремо - тоді запустіть лише client/client.py")
        sys.exit(1)
    try:
        gui = cli.create_gui_server("127.0.0.1", config["port"], a.gui_port)
    except OSError as e:
        print("Порт %s зайнятий (%s). Спробуйте: python run.py --gui-port 8081" % (a.gui_port, e))
        tcp.shutdown()
        sys.exit(1)

    url = "http://127.0.0.1:%d/" % a.gui_port
    print("=" * 66)
    print(" Система бронювання та купівлі залізничних квитків (варіант 6)")
    print(" TCP-сервер:  %s:%s   БД: %s" % (config["host"], config["port"], os.path.basename(config["database"])))
    print(" Інтерфейс:   %s" % url)
    print(" Демо-вхід:   ivan_koval / Tickets2025")
    print(" Ctrl+C - зупинити")
    print("=" * 66, flush=True)
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        gui.serve_forever()
    except KeyboardInterrupt:
        print("\nЗупинено.")
    finally:
        tcp.shutdown()


if __name__ == "__main__":
    main()
