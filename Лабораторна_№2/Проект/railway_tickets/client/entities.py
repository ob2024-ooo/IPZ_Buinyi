"""Класи-сутності клієнта. Усі поля закриті та доступні через властивості (get/set).
Сеттери перевіряють значення, тож некоректні дані не доходять до сервера."""
import re
from datetime import date, datetime


class ValidationError(Exception):
    pass


class AppSession:
    """Поточна сесія користувача (токен зберігається лише на боці Python-клієнта)."""

    def __init__(self):
        self._token = None
        self._login = None
        self._full_name = ""

    @property
    def token(self):
        return self._token

    @token.setter
    def token(self, value):
        self._token = value

    @property
    def login(self):
        return self._login

    @login.setter
    def login(self, value):
        self._login = value

    @property
    def full_name(self):
        return self._full_name

    @full_name.setter
    def full_name(self, value):
        self._full_name = value or ""

    @property
    def is_logged_in(self):
        return self._token is not None

    def clear(self):
        self._token = None
        self._login = None
        self._full_name = ""


class LoginEntity:
    def __init__(self, login="", password=""):
        self._login = ""
        self._password = ""
        self.login = login
        self.password = password

    @property
    def login(self):
        return self._login

    @login.setter
    def login(self, value):
        self._login = (value or "").strip()

    @property
    def password(self):
        return self._password

    @password.setter
    def password(self, value):
        self._password = value or ""

    def validate(self):
        if not self._login:
            raise ValidationError("Введіть логін.")
        if not self._password:
            raise ValidationError("Введіть пароль.")


class RegisterEntity(LoginEntity):
    LOGIN_RE = re.compile(r"^[A-Za-z0-9_.]{5,20}$")

    def __init__(self, login="", password="", confirm_password="", full_name=""):
        super().__init__(login, password)
        self._confirm_password = confirm_password or ""
        self._full_name = (full_name or "").strip()

    @property
    def confirm_password(self):
        return self._confirm_password

    @confirm_password.setter
    def confirm_password(self, value):
        self._confirm_password = value or ""

    @property
    def full_name(self):
        return self._full_name

    @full_name.setter
    def full_name(self, value):
        self._full_name = (value or "").strip()

    def validate(self):
        if not self.login and not self.password:
            raise ValidationError("Заповніть усі поля форми реєстрації.")
        if not self.LOGIN_RE.match(self.login):
            raise ValidationError("Логін має містити 5–20 символів: латинські літери, цифри, '_' або '.'.")
        if len(self.password) < 8:
            raise ValidationError("Пароль має містити щонайменше 8 символів.")
        if not re.search(r"\d", self.password) or not re.search(r"[^\d\W]", self.password):
            raise ValidationError("Пароль має містити хоча б одну літеру та одну цифру.")
        if self.password != self._confirm_password:
            raise ValidationError("Паролі не співпадають.")


class SearchEntity:
    def __init__(self, mode="name", query=""):
        self._mode = "name"
        self._query = ""
        self.mode = mode
        self.query = query

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value):
        if value not in ("name", "date"):
            raise ValidationError("Невідомий режим пошуку.")
        self._mode = value

    @property
    def query(self):
        return self._query

    @query.setter
    def query(self, value):
        self._query = (value or "").strip()

    def parsed_date(self):
        for f in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(self._query, f).date()
            except ValueError:
                pass
        raise ValidationError("Введіть дату у форматі РРРР-ММ-ДД або ДД.ММ.РРРР.")

    def validate(self):
        if self._mode == "date":
            if self.parsed_date() < date.today():
                raise ValidationError("Обрана дата вже минула. Оберіть сьогоднішню або майбутню дату.")


class TicketOrderEntity:
    """Замовлення квитка: рейс + місце + дія (бронювання чи купівля)."""

    def __init__(self, trip_id=None, seat_number=None, action="buy"):
        self._trip_id = None
        self._seat_number = None
        self._action = "buy"
        if trip_id is not None:
            self.trip_id = trip_id
        if seat_number not in (None, ""):
            self.seat_number = seat_number
        self.action = action

    @property
    def trip_id(self):
        return self._trip_id

    @trip_id.setter
    def trip_id(self, value):
        try:
            self._trip_id = int(value)
        except (TypeError, ValueError):
            raise ValidationError("Некоректний номер рейсу.")

    @property
    def seat_number(self):
        return self._seat_number

    @seat_number.setter
    def seat_number(self, value):
        try:
            self._seat_number = int(value)
        except (TypeError, ValueError):
            raise ValidationError("Оберіть місце у вагоні.")

    @property
    def action(self):
        return self._action

    @action.setter
    def action(self, value):
        if value not in ("buy", "book"):
            raise ValidationError("Невідома дія з квитком.")
        self._action = value

    def validate(self):
        if self._trip_id is None:
            raise ValidationError("Оберіть рейс.")
        if self._seat_number is None:
            raise ValidationError("Оберіть місце у вагоні.")


class RatingEntity:
    def __init__(self, trip_id=None, stars=0, comment=""):
        self._trip_id = trip_id
        self._stars = 0
        self._comment = ""
        self.stars = stars
        self.comment = comment

    @property
    def trip_id(self):
        return self._trip_id

    @trip_id.setter
    def trip_id(self, value):
        self._trip_id = int(value)

    @property
    def stars(self):
        return self._stars

    @stars.setter
    def stars(self, value):
        try:
            self._stars = int(value or 0)
        except (TypeError, ValueError):
            raise ValidationError("Оцінка має бути числом від 1 до 5.")

    @property
    def comment(self):
        return self._comment

    @comment.setter
    def comment(self, value):
        self._comment = (value or "").strip()[:300]

    def validate(self):
        if self._stars == 0:
            raise ValidationError("Оберіть оцінку (кількість зірок).")
        if not 1 <= self._stars <= 5:
            raise ValidationError("Оцінка має бути від 1 до 5.")
