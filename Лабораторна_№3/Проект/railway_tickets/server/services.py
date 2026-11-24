"""Бізнес-логіка сервера: користувачі, рейси, квитки, оцінки."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta

from protocol import AppError, fmt, now, parse_dt, req_int, req_str

STATUS_BOOKED = "Заброньовано"
STATUS_PAID = "Оплачено"
STATUS_CANCELLED = "Скасовано"

LOGIN_RE = re.compile(r"^[A-Za-z0-9_.]{5,20}$")


# ---------------------------------------------------------------- паролі
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000)
    return digest.hex(), salt


def verify_password(password, pw_hash, salt):
    return secrets.compare_digest(hash_password(password, salt)[0], pw_hash)


def validate_login(login):
    if not LOGIN_RE.match(login):
        raise AppError("VALIDATION", "Логін має містити 5–20 символів: латинські літери, цифри, '_' або '.'.")


def validate_password(password):
    if len(password) < 8:
        raise AppError("VALIDATION", "Пароль має містити щонайменше 8 символів.")
    if not re.search(r"\d", password) or not re.search(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]", password):
        raise AppError("VALIDATION", "Пароль має містити хоча б одну літеру та одну цифру.")


# ---------------------------------------------------------------- сесії
class AuthService:
    def __init__(self, config):
        self.session_hours = config.get("session_hours", 12)

    def register(self, conn, req):
        login = req_str(req, "login", max_len=50)
        password = req_str(req, "password", max_len=100)
        full_name = req.get("fullName") or ""
        validate_login(login)
        validate_password(password)
        if conn.execute("SELECT 1 FROM Users WHERE Login = ?", (login,)).fetchone():
            raise AppError("CONFLICT", "Користувач з таким логіном уже існує.")
        pw_hash, salt = hash_password(password)
        cur = conn.execute(
            "INSERT INTO Users (Login, FullName, PasswordHash, Salt, CreatedAt) VALUES (?,?,?,?,?)",
            (login, str(full_name)[:100], pw_hash, salt, fmt(now())))
        return "Реєстрація успішна. Тепер увійдіть у систему.", {"userId": cur.lastrowid, "login": login}

    def login(self, conn, req):
        login = req_str(req, "login", max_len=50)
        password = req_str(req, "password", max_len=100)
        user = conn.execute("SELECT * FROM Users WHERE Login = ?", (login,)).fetchone()
        if not user:
            raise AppError("USER_NOT_FOUND", "Користувача '%s' не знайдено." % login)
        if not verify_password(password, user["PasswordHash"], user["Salt"]):
            raise AppError("WRONG_PASSWORD", "Невірний пароль.")
        token = secrets.token_hex(24)
        expires = now() + timedelta(hours=self.session_hours)
        conn.execute("INSERT INTO Sessions (UserId, Token, CreatedAt, ExpiresAt) VALUES (?,?,?,?)",
                     (user["Id"], token, fmt(now()), fmt(expires)))
        return "Вхід виконано.", {"userId": user["Id"], "login": user["Login"],
                                  "fullName": user["FullName"], "token": token, "expiresAt": fmt(expires)}

    def require_user(self, conn, req):
        token = req_str(req, "token", max_len=100)
        row = conn.execute(
            "SELECT s.*, u.Login FROM Sessions s JOIN Users u ON u.Id = s.UserId WHERE s.Token = ?",
            (token,)).fetchone()
        if not row or row["ClosedAt"] is not None or parse_dt(row["ExpiresAt"]) <= now():
            raise AppError("UNAUTHORIZED", "Сесія не активна. Увійдіть у систему знову.")
        return row["UserId"]

    def logout(self, conn, req):
        token = req_str(req, "token", max_len=100)
        self.require_user(conn, req)
        conn.execute("UPDATE Sessions SET ClosedAt = ? WHERE Token = ?", (fmt(now()), token))
        return "Ви вийшли з системи.", {}


# ---------------------------------------------------------------- рейси
def occupied_seats(conn, trip_id):
    rows = conn.execute(
        "SELECT SeatNumber FROM Tickets WHERE TripId = ? AND (Status = ? OR (Status = ? AND ReservedUntil > ?))",
        (trip_id, STATUS_PAID, STATUS_BOOKED, fmt(now()))).fetchall()
    return {r[0] for r in rows}


def trip_to_dict(conn, row):
    taken = occupied_seats(conn, row["Id"])
    rating = conn.execute("SELECT AVG(Stars), COUNT(*) FROM Ratings WHERE TripId = ?", (row["Id"],)).fetchone()
    return {
        "id": row["Id"], "name": row["Name"], "fromCity": row["FromCity"], "toCity": row["ToCity"],
        "departureAt": row["DepartureAt"], "arrivalAt": row["ArrivalAt"], "price": row["Price"],
        "trainId": row["TrainId"], "trainName": row["TrainName"], "trainNumber": row["TrainNumber"],
        "seatsTotal": row["SeatsTotal"], "freeSeatsCount": row["SeatsTotal"] - len(taken),
        "takenSeats": sorted(taken),
        "averageRating": round(rating[0], 2) if rating[0] else 0, "ratingsCount": rating[1],
        "isDeparted": parse_dt(row["DepartureAt"]) <= now(),
    }


TRIP_SELECT = ("SELECT t.*, tr.Name AS TrainName, tr.Number AS TrainNumber, tr.SeatsTotal "
               "FROM Trips t JOIN Trains tr ON tr.Id = t.TrainId ")


class TripService:
    def __init__(self, auth):
        self.auth = auth

    def search_by_name(self, conn, req):
        self.auth.require_user(conn, req)
        name = req_str(req, "name", allow_empty=True, max_len=100).lower()
        rows = conn.execute(TRIP_SELECT + "ORDER BY t.DepartureAt").fetchall()
        # lower() у Python коректно працює з кирилицею (на відміну від LOWER у SQLite)
        trips = [trip_to_dict(conn, r) for r in rows
                 if not name or name in r["Name"].lower() or name in r["FromCity"].lower()
                 or name in r["ToCity"].lower()]
        trips.sort(key=lambda t: (t["isDeparted"], t["departureAt"] if not t["isDeparted"] else ""))
        return self._result(trips)

    def search_by_date(self, conn, req):
        self.auth.require_user(conn, req)
        raw = req_str(req, "date", max_len=20)
        day = None
        for f in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                day = datetime.strptime(raw, f).date()
                break
            except ValueError:
                pass
        if day is None:
            raise AppError("INVALID_FIELD", "Дата має бути у форматі РРРР-ММ-ДД або ДД.ММ.РРРР.")
        if day < now().date():
            raise AppError("VALIDATION", "Неможливо шукати рейси на дату, що вже минула.")
        rows = conn.execute(TRIP_SELECT + "WHERE substr(t.DepartureAt,1,10) = ? ORDER BY t.DepartureAt",
                            (day.isoformat(),)).fetchall()
        return self._result([trip_to_dict(conn, r) for r in rows])

    def trip_details(self, conn, req):
        self.auth.require_user(conn, req)
        trip_id = req_int(req, "tripId")
        row = conn.execute(TRIP_SELECT + "WHERE t.Id = ?", (trip_id,)).fetchone()
        if not row:
            raise AppError("NOT_FOUND", "Рейс з таким номером не знайдено.")
        return "Інформація про рейс.", {"trip": trip_to_dict(conn, row)}

    @staticmethod
    def _result(trips):
        msg = "Знайдено рейсів: %d." % len(trips) if trips else "Рейсів за вашим запитом не знайдено."
        return msg, {"trips": trips}


# ---------------------------------------------------------------- квитки
class TicketService:
    def __init__(self, auth, config):
        self.auth = auth
        self.booking_hours = config.get("booking_hours", 24)

    def _check_trip_and_seat(self, conn, req):
        trip_id = req_int(req, "tripId")
        seat = req_int(req, "seatNumber")
        trip = conn.execute(TRIP_SELECT + "WHERE t.Id = ?", (trip_id,)).fetchone()
        if not trip:
            raise AppError("NOT_FOUND", "Рейс з таким номером не знайдено.")
        if parse_dt(trip["DepartureAt"]) <= now():
            raise AppError("VALIDATION", "Рейс уже відправився — квиток придбати не можна.")
        if seat < 1 or seat > trip["SeatsTotal"]:
            raise AppError("VALIDATION", "Місце має бути від 1 до %d." % trip["SeatsTotal"])
        if seat in occupied_seats(conn, trip_id):
            raise AppError("CONFLICT", "Місце %d уже зайняте. Оберіть інше." % seat)
        return trip, seat

    def _create(self, conn, req, status):
        user_id = self.auth.require_user(conn, req)
        trip, seat = self._check_trip_and_seat(conn, req)
        t_now = now()
        reserved_until = None
        paid_at = None
        if status == STATUS_BOOKED:
            limit = min(t_now + timedelta(hours=self.booking_hours),
                        parse_dt(trip["DepartureAt"]) - timedelta(minutes=30))
            reserved_until = fmt(max(limit, t_now + timedelta(minutes=5)))
        else:
            paid_at = fmt(t_now)
        cur = conn.execute(
            "INSERT INTO Tickets (UserId, TripId, SeatNumber, Price, Status, BookedAt, ReservedUntil, PaidAt) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (user_id, trip["Id"], seat, trip["Price"], status, fmt(t_now), reserved_until, paid_at))
        return self._ticket(conn, cur.lastrowid)

    def book(self, conn, req):
        t = self._create(conn, req, STATUS_BOOKED)
        return "Місце %d заброньовано до %s. Оплатіть квиток у розділі «Мої квитки»." % (
            t["seatNumber"], t["reservedUntil"]), {"ticket": t}

    def buy(self, conn, req):
        t = self._create(conn, req, STATUS_PAID)
        return "Квиток куплено: місце %d, %.2f грн." % (t["seatNumber"], t["price"]), {"ticket": t}

    def pay(self, conn, req):
        user_id = self.auth.require_user(conn, req)
        ticket = self._own_ticket(conn, req, user_id)
        if ticket["Status"] == STATUS_PAID:
            raise AppError("CONFLICT", "Цей квиток уже оплачено.")
        if ticket["Status"] == STATUS_CANCELLED:
            raise AppError("CONFLICT", "Квиток скасовано — оплатити його не можна.")
        if parse_dt(ticket["ReservedUntil"]) <= now():
            raise AppError("VALIDATION", "Час бронювання минув. Забронюйте місце знову.")
        conn.execute("UPDATE Tickets SET Status = ?, PaidAt = ? WHERE Id = ?",
                     (STATUS_PAID, fmt(now()), ticket["Id"]))
        return "Квиток оплачено.", {"ticket": self._ticket(conn, ticket["Id"])}

    def cancel(self, conn, req):
        user_id = self.auth.require_user(conn, req)
        ticket = self._own_ticket(conn, req, user_id)
        if ticket["Status"] == STATUS_CANCELLED:
            raise AppError("CONFLICT", "Цей квиток уже скасовано.")
        trip = conn.execute("SELECT DepartureAt FROM Trips WHERE Id = ?", (ticket["TripId"],)).fetchone()
        if parse_dt(trip["DepartureAt"]) <= now():
            raise AppError("VALIDATION", "Рейс уже відправився — скасувати квиток не можна.")
        conn.execute("UPDATE Tickets SET Status = ?, CancelledAt = ? WHERE Id = ?",
                     (STATUS_CANCELLED, fmt(now()), ticket["Id"]))
        return "Квиток скасовано, місце знову вільне.", {"ticket": self._ticket(conn, ticket["Id"])}

    def my_tickets(self, conn, req):
        user_id = self.auth.require_user(conn, req)
        ids = [r[0] for r in conn.execute(
            "SELECT k.Id FROM Tickets k JOIN Trips t ON t.Id = k.TripId WHERE k.UserId = ? "
            "ORDER BY t.DepartureAt DESC", (user_id,))]
        tickets = [self._ticket(conn, i) for i in ids]
        msg = "Квитків: %d." % len(tickets) if tickets else "У вас ще немає квитків."
        return msg, {"tickets": tickets}

    @staticmethod
    def _own_ticket(conn, req, user_id):
        ticket_id = req_int(req, "ticketId")
        row = conn.execute("SELECT * FROM Tickets WHERE Id = ? AND UserId = ?", (ticket_id, user_id)).fetchone()
        if not row:
            raise AppError("NOT_FOUND", "Квиток не знайдено.")
        return row

    @staticmethod
    def _ticket(conn, ticket_id):
        r = conn.execute(
            "SELECT k.*, t.Name AS TripName, t.FromCity, t.ToCity, t.DepartureAt, t.ArrivalAt, "
            "tr.Name AS TrainName, tr.Number AS TrainNumber FROM Tickets k "
            "JOIN Trips t ON t.Id = k.TripId JOIN Trains tr ON tr.Id = t.TrainId WHERE k.Id = ?",
            (ticket_id,)).fetchone()
        status = r["Status"]
        if status == STATUS_BOOKED and parse_dt(r["ReservedUntil"]) <= now():
            status = "Бронь минула"
        departed = parse_dt(r["DepartureAt"]) <= now()
        my = conn.execute("SELECT Stars FROM Ratings WHERE UserId = ? AND TripId = ?",
                          (r["UserId"], r["TripId"])).fetchone()
        return {
            "id": r["Id"], "tripId": r["TripId"], "tripName": r["TripName"], "fromCity": r["FromCity"],
            "toCity": r["ToCity"], "departureAt": r["DepartureAt"], "arrivalAt": r["ArrivalAt"],
            "trainName": r["TrainName"], "trainNumber": r["TrainNumber"], "seatNumber": r["SeatNumber"],
            "price": r["Price"], "status": status, "bookedAt": r["BookedAt"],
            "reservedUntil": r["ReservedUntil"], "paidAt": r["PaidAt"],
            "canPay": status == STATUS_BOOKED and not departed,
            "canCancel": status in (STATUS_BOOKED, STATUS_PAID) and not departed,
            "canRate": status == STATUS_PAID and departed and not my,
            "myRating": my[0] if my else 0,
        }


# ---------------------------------------------------------------- оцінки
class RatingService:
    def __init__(self, auth):
        self.auth = auth

    def rate(self, conn, req):
        user_id = self.auth.require_user(conn, req)
        trip_id = req_int(req, "tripId")
        stars = req_int(req, "stars")
        comment = str(req.get("comment") or "")[:300]
        if not conn.execute("SELECT 1 FROM Trips WHERE Id = ?", (trip_id,)).fetchone():
            raise AppError("NOT_FOUND", "Рейс з таким номером не знайдено.")
        if stars < 1 or stars > 5:
            raise AppError("VALIDATION", "Оцінка має бути від 1 до 5.")
        dep = conn.execute("SELECT DepartureAt FROM Trips WHERE Id = ?", (trip_id,)).fetchone()[0]
        if parse_dt(dep) > now():
            raise AppError("VALIDATION", "Оцінити рейс можна лише після поїздки (рейс ще не відправився).")
        if not conn.execute("SELECT 1 FROM Tickets WHERE UserId = ? AND TripId = ? AND Status = ?",
                            (user_id, trip_id, STATUS_PAID)).fetchone():
            raise AppError("VALIDATION", "Оцінити рейс можна лише маючи на нього оплачений квиток.")
        if conn.execute("SELECT 1 FROM Ratings WHERE UserId = ? AND TripId = ?", (user_id, trip_id)).fetchone():
            raise AppError("CONFLICT", "Ви вже оцінили цей рейс.")
        conn.execute("INSERT INTO Ratings (UserId, TripId, Stars, Comment, CreatedAt) VALUES (?,?,?,?,?)",
                     (user_id, trip_id, stars, comment, fmt(now())))
        avg, cnt = conn.execute("SELECT AVG(Stars), COUNT(*) FROM Ratings WHERE TripId = ?", (trip_id,)).fetchone()
        return "Дякуємо за оцінку!", {"tripId": trip_id, "stars": stars,
                                      "averageRating": round(avg, 2), "ratingsCount": cnt}

    def train_rating(self, conn, req):
        self.auth.require_user(conn, req)
        rows = conn.execute(
            "SELECT tr.Id, tr.Name, tr.Number, AVG(r.Stars) AS Avg, COUNT(r.Id) AS Cnt "
            "FROM Trains tr LEFT JOIN Trips t ON t.TrainId = tr.Id LEFT JOIN Ratings r ON r.TripId = t.Id "
            "GROUP BY tr.Id ORDER BY (Avg IS NULL), Avg DESC, Cnt DESC, tr.Name").fetchall()
        trains = [{"place": i + 1, "trainId": r["Id"], "name": r["Name"], "number": r["Number"],
                   "averageRating": round(r["Avg"], 2) if r["Avg"] else 0, "ratingsCount": r["Cnt"]}
                  for i, r in enumerate(rows)]
        return "Рейтинг поїздів сформовано.", {"trains": trains}
