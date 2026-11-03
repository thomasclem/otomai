"""Durable listing records. One process may own a state file at a time."""

import hashlib
import json
import sqlite3
import typing as T
from pathlib import Path

import pydantic as pdt

Status = T.Literal[
    # signal
    "observing",
    "qualified",
    "no_signal",
    "expired",
    "excluded",
    "skipped",
    # position
    "submitting",
    "entry_pending",
    "open",
    "closing",
    "uncertain",
    "closed",
    "rejected",
]
Phase = T.Literal["entry", "protection", "open", "close"]

OWNED: set[str] = {"submitting", "entry_pending", "open", "closing", "uncertain"}
ENTRY: set[str] = {"submitting", "entry_pending"}

_COLUMNS = {"key", "symbol", "listing_ms", "volume", "status"}


class Listing(pdt.BaseModel):
    """One contract listing, from discovery to the end of its trade."""

    model_config = pdt.ConfigDict(extra="ignore", validate_assignment=True)

    key: str
    symbol: str
    listing_ms: int
    volume: float | None = None
    status: Status = "observing"
    reason: str | None = None
    # signal
    reference: float | None = None
    volume_ratio: float | None = None
    entry_due_ms: int | None = None
    entry_expiry_ms: int | None = None
    excluded_reason: str | None = None
    volume_error: str | None = None
    volume_retry_after_ms: int = 0
    # entry
    phase: Phase | None = None
    error: str | None = None
    client_id: str | None = None
    order_id: str | None = None
    quote: float | None = None
    submitted_ms: int | None = None
    amount: float | None = None
    notional: float | None = None
    # open position
    entry: float | None = None
    entry_ms: int | None = None
    deadline_ms: int | None = None
    stop_client_id: str | None = None
    target_client_id: str | None = None
    close_client_id: str | None = None
    adopted_ms: int | None = None
    closed_ms: int | None = None

    @property
    def excluded(self) -> bool:
        return self.excluded_reason is not None

    @property
    def blocks_admission(self) -> bool:
        """Only an unresolved entry can hold unknown exposure; the rest is on the venue."""
        return self.status in ENTRY or (
            self.status == "uncertain" and (self.phase or "entry") == "entry"
        )

    def order_id_for(self, suffix: str) -> str:
        """Deterministic client order ID of this listing (lowercase, at most 40 chars)."""
        return "olv" + hashlib.sha256(self.key.encode()).hexdigest()[:24] + suffix


class ListingState:
    def __init__(self, path: str, identity: dict):
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        # A separate SQLite exclusive transaction is a cross-platform process lock.
        # State writes use their own connection, so the lock never blocks our commits.
        self.lock = sqlite3.connect(str(target) + ".lock", timeout=0, check_same_thread=False)
        try:
            self.lock.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as exc:
            self.lock.close()
            raise RuntimeError(f"Another runner owns {target}") from exc
        self.db = sqlite3.connect(target, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        try:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError(f"Unsupported listing state version: {version}")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS listings (
                    key TEXT PRIMARY KEY, symbol TEXT NOT NULL, listing_ms INTEGER NOT NULL,
                    volume REAL, status TEXT NOT NULL DEFAULT 'observing',
                    data TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, time_ms INTEGER NOT NULL,
                    listing_key TEXT, kind TEXT NOT NULL, data TEXT NOT NULL
                );
                PRAGMA user_version=1;
            """)
            frozen = json.dumps(identity, sort_keys=True)
            row = self.db.execute("SELECT value FROM metadata WHERE key='identity'").fetchone()
            if row and row[0] != frozen:
                raise RuntimeError(
                    "State belongs to a different mode/account/rule; use a new state_path"
                )
            with self.db:
                self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('identity', ?)", (frozen,))
        except Exception:
            self.close()
            raise

    def close(self):
        if getattr(self, "db", None):
            self.db.close()
            self.db = None
        if self.lock:
            self.lock.rollback()
            self.lock.close()
            self.lock = None

    def rows(self) -> list[Listing]:
        """All listings, oldest first (ties by symbol)."""
        cursor = self.db.execute("SELECT * FROM listings ORDER BY listing_ms, symbol")
        return [Listing(**{c: r[c] for c in _COLUMNS}, **json.loads(r["data"])) for r in cursor]

    def discover(self, symbol: str, listing_ms: int) -> str:
        key = f"{symbol}@{listing_ms}"
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO listings(key,symbol,listing_ms) VALUES (?,?,?)",
                (key, symbol, listing_ms),
            )
        return key

    def save(self, listing: Listing, now_ms: int, *, record_event: bool = True, **changes):
        """Apply validated `changes` to `listing`, persist it and log them as an event."""
        for name, value in changes.items():
            setattr(listing, name, value)
        data = listing.model_dump(exclude=_COLUMNS, exclude_defaults=True)
        with self.db:
            self.db.execute(
                "UPDATE listings SET status=?,volume=?,data=? WHERE key=?",
                (listing.status, listing.volume, json.dumps(data, allow_nan=False), listing.key),
            )
            if record_event:
                self.db.execute(
                    "INSERT INTO events(time_ms,listing_key,kind,data) VALUES (?,?,?,?)",
                    (now_ms, listing.key, listing.status, json.dumps(changes, allow_nan=False)),
                )
