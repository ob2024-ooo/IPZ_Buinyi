"""Робота з базою даних SQLite: створення схеми та підключення."""
import os
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS Users (
    Id           INTEGER PRIMARY KEY AUTOINCREMENT,
    Login        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    FullName     TEXT NOT NULL DEFAULT '',
    PasswordHash TEXT NOT NULL,
    Salt         TEXT NOT NULL,
    CreatedAt    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS Sessions (
    Id        INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId    INTEGER NOT NULL REFERENCES Users(Id),
    Token     TEXT NOT NULL UNIQUE,
    CreatedAt TEXT NOT NULL,
    ExpiresAt TEXT NOT NULL,
    ClosedAt  TEXT
);
CREATE TABLE IF NOT EXISTS Trains (
    Id         INTEGER PRIMARY KEY AUTOINCREMENT,
    Name       TEXT NOT NULL,
    Number     TEXT NOT NULL UNIQUE,
    SeatsTotal INTEGER NOT NULL CHECK (SeatsTotal > 0)
);
CREATE TABLE IF NOT EXISTS Trips (
    Id          INTEGER PRIMARY KEY AUTOINCREMENT,
    Name        TEXT NOT NULL,
    FromCity    TEXT NOT NULL,
    ToCity      TEXT NOT NULL,
    DepartureAt TEXT NOT NULL,
    ArrivalAt   TEXT NOT NULL,
    Price       REAL NOT NULL CHECK (Price > 0),
    TrainId     INTEGER NOT NULL REFERENCES Trains(Id)
);
CREATE TABLE IF NOT EXISTS Tickets (
    Id            INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId        INTEGER NOT NULL REFERENCES Users(Id),
    TripId        INTEGER NOT NULL REFERENCES Trips(Id),
    SeatNumber    INTEGER NOT NULL,
    Price         REAL NOT NULL,
    Status        TEXT NOT NULL,
    BookedAt      TEXT NOT NULL,
    ReservedUntil TEXT,
    PaidAt        TEXT,
    CancelledAt   TEXT
);
CREATE TABLE IF NOT EXISTS Ratings (
    Id        INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId    INTEGER NOT NULL REFERENCES Users(Id),
    TripId    INTEGER NOT NULL REFERENCES Trips(Id),
    Stars     INTEGER NOT NULL CHECK (Stars BETWEEN 1 AND 5),
    Comment   TEXT NOT NULL DEFAULT '',
    CreatedAt TEXT NOT NULL,
    UNIQUE (UserId, TripId)
);
CREATE TABLE IF NOT EXISTS RequestLog (
    Id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ReceivedAt TEXT NOT NULL,
    ClientAddr TEXT NOT NULL,
    Command    TEXT NOT NULL,
    Success    INTEGER NOT NULL,
    Code       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS IX_Tickets_Trip ON Tickets(TripId, SeatNumber);
CREATE INDEX IF NOT EXISTS IX_Tickets_User ON Tickets(UserId);
"""


class Database:
    """Обгортка над SQLite. Одне підключення на кожен запит + блокування для записів."""

    def __init__(self, path):
        self._path = path
        self.write_lock = threading.Lock()

    @property
    def path(self):
        return self._path

    def connect(self):
        conn = sqlite3.connect(self._path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create_schema(self):
        conn = self.connect()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def is_empty(self):
        conn = self.connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM Trains").fetchone()[0] == 0
        finally:
            conn.close()

    def exists(self):
        return os.path.exists(self._path)
