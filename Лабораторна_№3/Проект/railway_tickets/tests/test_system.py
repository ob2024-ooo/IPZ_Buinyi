"""Автоматичні тести всієї системи (ЛР4).

Запуск:  python -m unittest tests/test_system.py -v      (з кореневої папки проєкту)
         python tests/test_system.py

Тести піднімають справжній TCP-сервер на окремому порту з тимчасовою копією БД
і перевіряють його через той самий NetworkClient, що використовує GUI-клієнт.
"""
import os
import socket
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(ROOT, "client"))

import server as srv  # noqa: E402
from client import ClientController  # noqa: E402
from entities import RegisterEntity, ValidationError  # noqa: E402
from network_client import ApiError, NetworkClient  # noqa: E402
from seed import DEMO_PASSWORD  # noqa: E402

TEST_PORT = 5066


class SystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cfg = srv.load_config()
        cfg.update(port=TEST_PORT, database=os.path.join(cls.tmp, "test.db"), quiet=True)
        cls.server = srv.start_in_thread(cfg, reset=True)
        cls.net = NetworkClient("127.0.0.1", TEST_PORT)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    # ---------- допоміжні ----------
    def call(self, command, **fields):
        return self.net.send(command, **fields)

    def token(self, login="ivan_koval"):
        return self.call("login", login=login, password=DEMO_PASSWORD)[1]["token"]

    def future_trip(self, token, skip=0):
        trips = self.call("searchtripsbyname", token=token, name="")[1]["trips"]
        return [t for t in trips if not t["isDeparted"]][skip]

    def free_seat(self, trip):
        return next(n for n in range(1, trip["seatsTotal"] + 1) if n not in trip["takenSeats"])

    def assertApiError(self, code, command, **fields):
        with self.assertRaises(ApiError) as ctx:
            self.call(command, **fields)
        self.assertEqual(ctx.exception.code, code, ctx.exception.message)
        return ctx.exception.message

    # ---------- 1. реєстрація ----------
    def test01_register_success(self):
        msg, data = self.call("register", login="new_passenger", password="Secret123", fullName="Новий Пасажир")
        self.assertIn("Реєстрація успішна", msg)
        self.assertGreater(data["userId"], 0)

    def test02_register_duplicate_login(self):
        self.assertApiError("CONFLICT", "register", login="IVAN_KOVAL", password="Secret123")

    def test03_register_short_login(self):
        self.assertApiError("VALIDATION", "register", login="abc", password="Secret123")

    def test04_register_weak_password(self):
        self.assertApiError("VALIDATION", "register", login="weak_user", password="password")

    def test05_client_checks_password_confirmation(self):
        with self.assertRaises(ValidationError):
            RegisterEntity("good_user", "Secret123", "Secret124").validate()

    # ---------- 2. вхід ----------
    def test06_login_unknown_user(self):
        self.assertApiError("USER_NOT_FOUND", "login", login="nobody_here", password="Secret123")

    def test07_login_wrong_password(self):
        self.assertApiError("WRONG_PASSWORD", "login", login="ivan_koval", password="Wrong1234")

    def test08_login_success_creates_session(self):
        msg, data = self.call("login", login="ivan_koval", password=DEMO_PASSWORD)
        self.assertEqual(data["login"], "ivan_koval")
        self.assertEqual(len(data["token"]), 48)

    def test09_request_without_session(self):
        self.assertApiError("UNAUTHORIZED", "mytickets", token="bad-token")

    # ---------- 3. пошук ----------
    def test10_search_by_name_case_insensitive(self):
        trips = self.call("searchtripsbyname", token=self.token(), name="КИЇВ")[1]["trips"]
        self.assertTrue(trips)
        self.assertTrue(all("Київ" in t["name"] for t in trips))

    def test11_search_not_found(self):
        msg, data = self.call("searchtripsbyname", token=self.token(), name="Токіо")
        self.assertEqual(data["trips"], [])
        self.assertIn("не знайдено", msg)

    def test12_search_by_date(self):
        tok = self.token()
        trip = self.future_trip(tok)
        day = trip["departureAt"][:10]
        trips = self.call("searchtripsbydate", token=tok, date=day)[1]["trips"]
        self.assertIn(trip["id"], [t["id"] for t in trips])
        d = day.split("-")
        trips2 = self.call("searchtripsbydate", token=tok, date="%s.%s.%s" % (d[2], d[1], d[0]))[1]["trips"]
        self.assertEqual(len(trips), len(trips2))

    def test13_search_past_date_rejected(self):
        self.assertApiError("VALIDATION", "searchtripsbydate", token=self.token(), date="2020-01-01")

    # ---------- 4. купівля та бронювання ----------
    def test14_buy_ticket_and_seat_becomes_taken(self):
        tok = self.token()
        trip = self.future_trip(tok, 1)
        seat = self.free_seat(trip)
        msg, data = self.call("buyticket", token=tok, tripId=trip["id"], seatNumber=seat)
        self.assertEqual(data["ticket"]["status"], "Оплачено")
        after = self.call("tripdetails", token=tok, tripId=trip["id"])[1]["trip"]
        self.assertIn(seat, after["takenSeats"])
        self.assertEqual(after["freeSeatsCount"], trip["freeSeatsCount"] - 1)

    def test15_seat_already_taken(self):
        tok = self.token()
        trip = self.future_trip(tok, 2)
        seat = self.free_seat(trip)
        self.call("buyticket", token=tok, tripId=trip["id"], seatNumber=seat)
        msg = self.assertApiError("CONFLICT", "buyticket", token=self.token("olena_bond"),
                                  tripId=trip["id"], seatNumber=seat)
        self.assertIn("уже зайняте", msg)

    def test16_seat_out_of_range_and_unknown_trip(self):
        tok = self.token()
        trip = self.future_trip(tok)
        self.assertApiError("VALIDATION", "buyticket", token=tok, tripId=trip["id"], seatNumber=0)
        self.assertApiError("VALIDATION", "buyticket", token=tok, tripId=trip["id"],
                            seatNumber=trip["seatsTotal"] + 1)
        self.assertApiError("NOT_FOUND", "buyticket", token=tok, tripId=99999, seatNumber=1)

    def test17_departed_trip_cannot_be_bought(self):
        tok = self.token()
        trips = self.call("searchtripsbyname", token=tok, name="")[1]["trips"]
        old = next(t for t in trips if t["isDeparted"])
        self.assertApiError("VALIDATION", "buyticket", token=tok, tripId=old["id"], seatNumber=1)

    def test18_book_then_pay(self):
        tok = self.token("taras_melnyk")
        trip = self.future_trip(tok, 3)
        seat = self.free_seat(trip)
        ticket = self.call("bookticket", token=tok, tripId=trip["id"], seatNumber=seat)[1]["ticket"]
        self.assertEqual(ticket["status"], "Заброньовано")
        self.assertTrue(ticket["canPay"])
        paid = self.call("payticket", token=tok, ticketId=ticket["id"])[1]["ticket"]
        self.assertEqual(paid["status"], "Оплачено")
        self.assertApiError("CONFLICT", "payticket", token=tok, ticketId=ticket["id"])

    # ---------- 5. скасування ----------
    def test19_cancel_ticket_frees_seat(self):
        tok = self.token("sofia_tkachuk")
        trip = self.future_trip(tok, 4)
        seat = self.free_seat(trip)
        ticket = self.call("buyticket", token=tok, tripId=trip["id"], seatNumber=seat)[1]["ticket"]
        cancelled = self.call("cancelticket", token=tok, ticketId=ticket["id"])[1]["ticket"]
        self.assertEqual(cancelled["status"], "Скасовано")
        after = self.call("tripdetails", token=tok, tripId=trip["id"])[1]["trip"]
        self.assertNotIn(seat, after["takenSeats"])
        self.assertApiError("CONFLICT", "cancelticket", token=tok, ticketId=ticket["id"])

    def test20_cannot_cancel_foreign_ticket(self):
        tok = self.token("maria_savchuk")
        trip = self.future_trip(tok, 5)
        ticket = self.call("buyticket", token=tok, tripId=trip["id"], seatNumber=self.free_seat(trip))[1]["ticket"]
        self.assertApiError("NOT_FOUND", "cancelticket", token=self.token("oleh_kushnir"), ticketId=ticket["id"])

    # ---------- 6. оцінки та рейтинг ----------
    def test21_rate_trip_rules(self):
        tok = self.token()
        tickets = self.call("mytickets", token=tok)[1]["tickets"]
        rateable = next(k for k in tickets if k["canRate"])
        self.assertApiError("VALIDATION", "ratetrip", token=tok, tripId=rateable["tripId"], stars=6)
        msg, data = self.call("ratetrip", token=tok, tripId=rateable["tripId"], stars=5, comment="Тест")
        self.assertEqual(data["stars"], 5)
        self.assertApiError("CONFLICT", "ratetrip", token=tok, tripId=rateable["tripId"], stars=4)

    def test22_cannot_rate_without_ticket(self):
        tok = self.token("nazar_kovalchuk")
        trips = self.call("searchtripsbyname", token=tok, name="")[1]["trips"]
        mine = {k["tripId"] for k in self.call("mytickets", token=tok)[1]["tickets"]}
        old = next(t for t in trips if t["isDeparted"] and t["id"] not in mine)
        self.assertApiError("VALIDATION", "ratetrip", token=tok, tripId=old["id"], stars=5)

    def test23_train_rating_sorted(self):
        trains = self.call("trainrating", token=self.token())[1]["trains"]
        rated = [t["averageRating"] for t in trains if t["ratingsCount"]]
        self.assertEqual(rated, sorted(rated, reverse=True))
        self.assertEqual([t["place"] for t in trains], list(range(1, len(trains) + 1)))

    # ---------- 7. вихід і стійкість ----------
    def test24_logout_closes_session(self):
        tok = self.token()
        self.call("logout", token=tok)
        self.assertApiError("UNAUTHORIZED", "mytickets", token=tok)

    def test25_bad_json_and_unknown_command(self):
        with socket.create_connection(("127.0.0.1", TEST_PORT), timeout=5) as s:
            s.sendall(b"this is not json\n")
            line = s.makefile("rb").readline().decode("utf-8")
        self.assertIn("BAD_JSON", line)
        self.assertApiError("UNKNOWN_COMMAND", "fly_to_moon")

    def test26_client_reports_server_offline(self):
        offline = ClientController(NetworkClient("127.0.0.1", 5999, timeout=2))
        result = offline.handle("login", {"login": "ivan_koval", "password": DEMO_PASSWORD})
        self.assertFalse(result["ok"])
        self.assertIn("Не вдалося підключитися", result["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
