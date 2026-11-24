# Система бронювання та купівлі залізничних квитків (варіант 6)

Клієнт-серверна система для лабораторних робіт з «Інженерії програмного забезпечення».
Написана на **Python 3.8+ лише зі стандартною бібліотекою** – нічого встановлювати не потрібно.

## Як запустити (VS Code)

1. Відкрийте папку `railway_tickets` у VS Code.
2. У терміналі (Terminal → New Terminal) виконайте:

```
python run.py
```

Запуститься TCP-сервер (порт 5055) і клієнт; інтерфейс відкриється у браузері
за адресою http://127.0.0.1:8080/. Зупинити – `Ctrl+C` у терміналі.

Також можна натиснути **F5** (Run and Debug → «Запуск системи»).

**Демо-вхід:** логін `ivan_koval`, пароль `Tickets2025` (такий самий пароль у всіх 18 демо-користувачів).

| Команда | Що робить |
|---|---|
| `python run.py` | сервер + клієнт однією командою |
| `python run.py --reset` | перестворити БД з демо-даними і запустити |
| `python server/server.py` | лише сервер (консоль із журналом запитів) – для ЛР3 |
| `python client/client.py` | лише клієнт (якщо сервер запущено окремо) |
| `python tools/tcp_console.py` | консольний TCP-клієнт: вводьте JSON-запити вручну (ЛР3) |
| `python tools/show_db.py Tickets 10` | показати останні рядки таблиці БД |
| `python -m unittest tests/test_system.py -v` | 26 автоматичних тестів (ЛР4) |

Якщо порт 8080 зайнятий: `python run.py --gui-port 8081`.
На Windows, якщо команда `python` не знаходиться, використовуйте `py run.py`.

## Структура

```
run.py                  запуск усієї системи
server/                 ЛР3 – TCP-сервер
  server.py             TicketServer, RequestHandler, CommandDispatcher
  services.py           бізнес-логіка (користувачі, рейси, квитки, оцінки)
  protocol.py           формат запитів/відповідей, AppError
  db.py, seed.py        схема SQLite і демо-дані
  config.json           порт, файл БД, тривалість сесії/броні
client/                 ЛР2 – клієнт з GUI
  client.py             ClientController (try/except на кожну дію), локальний веб-сервер GUI
  entities.py           класи з get/set (property) і перевіркою даних
  network_client.py     TCP-клієнт
  web/index.html        розмітка всіх вікон і діалогів
  web/styles.css        окремий файл стилів (кольори, кнопки)
  web/app.js            data binding (BindableBase, bind), view-моделі, вікна
tests/test_system.py    ЛР4 – автоматичні тести
tools/                  консольний TCP-клієнт і перегляд БД
docs/uml/               ЛР1 – джерела діаграм PlantUML (.puml) і готові PNG
```

## Протокол

Один рядок JSON на запит → один рядок JSON у відповідь:

```
{"command":"login","login":"ivan_koval","password":"Tickets2025"}
{"success":true,"code":"OK","message":"Вхід виконано.","data":{"token":"…", …}}
```

Команди: `register, login, logout, searchtripsbyname, searchtripsbydate, tripdetails,
buyticket, bookticket, payticket, cancelticket, mytickets, ratetrip, trainrating, ping`.
