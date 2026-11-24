"""Наповнення БД демо-даними. Дати рейсів рахуються від сьогоднішнього дня,
тож у базі завжди є і минулі (для оцінок), і майбутні рейси (для купівлі)."""
import random
from datetime import datetime, timedelta

from protocol import fmt
from services import STATUS_BOOKED, STATUS_CANCELLED, STATUS_PAID, hash_password

DEMO_PASSWORD = "Tickets2025"

USERS = [
    ("ivan_koval", "Іван Коваль"), ("olena_bond", "Олена Бондар"), ("taras_melnyk", "Тарас Мельник"),
    ("sofia_tkachuk", "Софія Ткачук"), ("andrii_kravchuk", "Андрій Кравчук"),
    ("maria_savchuk", "Марія Савчук"), ("dmytro_hnatiuk", "Дмитро Гнатюк"),
    ("iryna_romaniuk", "Ірина Романюк"), ("bohdan_lysenko", "Богдан Лисенко"),
    ("kateryna_mazur", "Катерина Мазур"), ("oleh_kushnir", "Олег Кушнір"),
    ("yulia_hryniuk", "Юлія Гринюк"), ("roman_sobko", "Роман Собко"),
    ("daryna_stelmakh", "Дарина Стельмах"), ("maksym_vovk", "Максим Вовк"),
    ("solomiia_petrenko", "Соломія Петренко"), ("vasyl_shevchuk", "Василь Шевчук"),
    ("nazar_kovalchuk", "Назар Ковальчук"),
]

TRAINS = [
    ("Інтерсіті+ Hyundai", "743К", 40), ("Інтерсіті+ Škoda", "715К", 36), ("Інтерсіті Hyundai", "791Л", 40),
    ("Інтерсіті Škoda", "732Л", 32), ("Нічний швидкий", "091К", 36), ("Нічний пасажирський", "143Л", 32),
    ("Регіональний експрес", "805Л", 28), ("Регіональний Škoda", "816Л", 28), ("Електропоїзд ЕПЛ-2", "825Л", 24),
    ("Електропоїзд ЕПЛ-9", "844Л", 24), ("Швидкісний експрес", "701К", 40), ("Приміський експрес", "010Л", 20),
    ("Дизель-поїзд ДПКр-3", "154Л", 20), ("Дизель-поїзд Р1", "984Л", 20), ("Пасажирський Чернівці", "823Л", 32),
    ("Швидкий Карпати", "950Л", 36),
]

# (з, до, тривалість год, ціна)
ROUTES = [
    ("Львів", "Київ", 7, 480), ("Київ", "Одеса", 7, 550), ("Львів", "Ужгород", 5, 320),
    ("Харків", "Київ", 6, 460), ("Дніпро", "Запоріжжя", 2, 180), ("Івано-Франківськ", "Львів", 3, 190),
    ("Тернопіль", "Київ", 6, 370), ("Чернівці", "Львів", 5, 360), ("Одеса", "Миколаїв", 3, 210),
    ("Вінниця", "Київ", 3, 260), ("Луцьк", "Рівне", 2, 130), ("Полтава", "Харків", 2, 170),
    ("Київ", "Житомир", 2, 160), ("Ужгород", "Мукачево", 1, 90), ("Черкаси", "Київ", 3, 200),
    ("Київ", "Львів", 7, 480), ("Одеса", "Київ", 7, 550), ("Ужгород", "Львів", 5, 320),
    ("Київ", "Харків", 6, 460), ("Запоріжжя", "Дніпро", 2, 180), ("Львів", "Івано-Франківськ", 3, 190),
    ("Київ", "Тернопіль", 6, 390), ("Львів", "Чернівці", 5, 390), ("Миколаїв", "Одеса", 3, 230),
    ("Київ", "Вінниця", 3, 290), ("Рівне", "Луцьк", 2, 130), ("Харків", "Полтава", 2, 200),
    ("Житомир", "Київ", 2, 140), ("Мукачево", "Ужгород", 1, 120), ("Київ", "Черкаси", 3, 210),
]

COMMENTS = ["Чисто й вчасно", "Комфортний вагон", "Запізнення 20 хв", "Привітна провідниця",
            "Було прохолодно", "Чудова поїздка", "Зручні місця", "Нормально", "Все сподобалось", ""]


def fill(database):
    rnd = random.Random(6)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    conn = database.connect()
    try:
        for login, name in USERS:
            h, s = hash_password(DEMO_PASSWORD)
            conn.execute("INSERT INTO Users (Login, FullName, PasswordHash, Salt, CreatedAt) VALUES (?,?,?,?,?)",
                         (login, name, h, s, fmt(today - timedelta(days=rnd.randint(30, 200)))))
        for name, number, seats in TRAINS:
            conn.execute("INSERT INTO Trains (Name, Number, SeatsTotal) VALUES (?,?,?)", (name, number, seats))

        trips = []
        for i, (a, b, hours, price) in enumerate(ROUTES):
            # перші 10 рейсів - у минулому, решта - у майбутньому
            offset = -20 + i * 2 if i < 10 else (i - 9) + (i % 3)
            dep = today + timedelta(days=offset, hours=rnd.choice([6, 8, 10, 13, 16, 19, 22]),
                                    minutes=rnd.choice([0, 15, 30, 45]))
            arr = dep + timedelta(hours=hours)
            train_id = i % len(TRAINS) + 1
            cur = conn.execute(
                "INSERT INTO Trips (Name, FromCity, ToCity, DepartureAt, ArrivalAt, Price, TrainId) "
                "VALUES (?,?,?,?,?,?,?)", ("%s — %s" % (a, b), a, b, fmt(dep), fmt(arr), price, train_id))
            seats = TRAINS[train_id - 1][2]
            trips.append((cur.lastrowid, dep, price, seats))

        user_count = len(USERS)
        for trip_id, dep, price, seats in trips:
            taken = set()
            for _ in range(rnd.randint(1, 4)):
                seat = rnd.randint(1, seats)
                if seat in taken:
                    continue
                taken.add(seat)
                user_id = rnd.randint(1, user_count)
                booked = min(dep - timedelta(days=rnd.randint(1, 10)), datetime.now() - timedelta(hours=2))
                roll = rnd.random()
                if dep > datetime.now() and roll < 0.2:
                    status, until, paid, cancelled = STATUS_BOOKED, fmt(datetime.now() + timedelta(hours=20)), None, None
                elif roll < 0.3:
                    status, until, paid, cancelled = STATUS_CANCELLED, None, fmt(booked), fmt(booked + timedelta(hours=3))
                else:
                    status, until, paid, cancelled = STATUS_PAID, None, fmt(booked), None
                conn.execute(
                    "INSERT INTO Tickets (UserId, TripId, SeatNumber, Price, Status, BookedAt, ReservedUntil, "
                    "PaidAt, CancelledAt) VALUES (?,?,?,?,?,?,?,?,?)",
                    (user_id, trip_id, seat, price, status, fmt(booked), until, paid, cancelled))
                if status == STATUS_PAID and dep < datetime.now() and rnd.random() < 0.85:
                    conn.execute(
                        "INSERT OR IGNORE INTO Ratings (UserId, TripId, Stars, Comment, CreatedAt) VALUES (?,?,?,?,?)",
                        (user_id, trip_id, rnd.choice([3, 4, 4, 5, 5, 5, 2]), rnd.choice(COMMENTS),
                         fmt(dep + timedelta(hours=rnd.randint(8, 30)))))
        # гарантовано: у ivan_koval є оплачений квиток на минулий рейс без оцінки (для демонстрації)
        trip_id, dep, price, seats = trips[9]
        conn.execute("DELETE FROM Ratings WHERE UserId = 1 AND TripId = ?", (trip_id,))
        conn.execute("INSERT INTO Tickets (UserId, TripId, SeatNumber, Price, Status, BookedAt, PaidAt) "
                     "VALUES (1, ?, ?, ?, ?, ?, ?)",
                     (trip_id, seats, price, STATUS_PAID, fmt(dep - timedelta(days=3)), fmt(dep - timedelta(days=3))))
        conn.commit()
    finally:
        conn.close()
