"""
database.py — SQLite layer for ZeusX Auto Re-Lister
=====================================================
Single source of truth untuk semua data:
  - config   : konfigurasi bot
  - products : daftar produk
  - auth     : session cookies Playwright

auth.json tetap di-sync ke disk karena Playwright butuh file path.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE  = os.path.join(BASE_DIR, "zeusx.db")
AUTH_FILE = os.path.join(BASE_DIR, "auth.json")

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT UNIQUE NOT NULL,
    title           TEXT DEFAULT '',
    price           TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    images          TEXT DEFAULT '[]',
    local_images    TEXT DEFAULT '[]',
    game_name       TEXT DEFAULT '',
    sub_game        TEXT DEFAULT '',
    delivery_time   TEXT DEFAULT '',
    delivery_hours  INTEGER DEFAULT 0,
    delivery_days   INTEGER DEFAULT 0,
    delivery_method TEXT DEFAULT '',
    quantity        INTEGER DEFAULT 20,
    enabled         INTEGER DEFAULT 1,
    last_relisted   TEXT,
    scraped_at      TEXT
);

CREATE TABLE IF NOT EXISTS auth (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    storage_state TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
"""


# ─── Connection ──────────────────────────────────────────────────────────────

@contextmanager
def _conn():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    with _conn() as con:
        con.executescript(SCHEMA)


# ─── Config ──────────────────────────────────────────────────────────────────

def load_config() -> dict:
    init_db()
    with _conn() as con:
        rows = con.execute("SELECT key, value FROM config").fetchall()

    if not rows:
        # Auto-fallback: SQLite kosong → baca JSON, lalu langsung simpan ke DB
        json_path = os.path.join(BASE_DIR, "config.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            save_config(cfg)
            return cfg
        return {"interval_minutes": 10, "headless": False}

    cfg = {}
    for row in rows:
        try:
            cfg[row["key"]] = json.loads(row["value"])
        except Exception:
            cfg[row["key"]] = row["value"]
    cfg.setdefault("interval_minutes", 10)
    cfg.setdefault("headless", False)
    return cfg


def save_config(cfg: dict):
    init_db()
    with _conn() as con:
        for key, val in cfg.items():
            con.execute(
                "INSERT INTO config(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(val)),
            )


# ─── Products ─────────────────────────────────────────────────────────────────

def _row_to_product(row) -> dict:
    p = dict(row)
    for field in ("images", "local_images"):
        try:
            p[field] = json.loads(p[field] or "[]")
        except Exception:
            p[field] = []
    p["enabled"] = bool(p.get("enabled", 1))
    return p


def _product_params(p: dict) -> dict:
    return {
        "url":             p.get("url", ""),
        "title":           p.get("title", ""),
        "price":           str(p.get("price", "")),
        "description":     p.get("description", ""),
        "images":          json.dumps(p.get("images", [])),
        "local_images":    json.dumps(p.get("local_images", [])),
        "game_name":       p.get("game_name", ""),
        "sub_game":        p.get("sub_game", ""),
        "delivery_time":   p.get("delivery_time", ""),
        "delivery_hours":  int(p.get("delivery_hours", 0)),
        "delivery_days":   int(p.get("delivery_days", 0)),
        "delivery_method": p.get("delivery_method", ""),
        "quantity":        int(p.get("quantity", 20)),
        "enabled":         1 if p.get("enabled", True) else 0,
        "last_relisted":   p.get("last_relisted"),
        "scraped_at":      p.get("scraped_at"),
    }


_UPSERT_SQL = """
INSERT INTO products (
    url, title, price, description,
    images, local_images,
    game_name, sub_game,
    delivery_time, delivery_hours, delivery_days, delivery_method,
    quantity, enabled, last_relisted, scraped_at
) VALUES (
    :url, :title, :price, :description,
    :images, :local_images,
    :game_name, :sub_game,
    :delivery_time, :delivery_hours, :delivery_days, :delivery_method,
    :quantity, :enabled, :last_relisted, :scraped_at
)
ON CONFLICT(url) DO UPDATE SET
    title           = excluded.title,
    price           = excluded.price,
    description     = excluded.description,
    images          = excluded.images,
    local_images    = excluded.local_images,
    game_name       = excluded.game_name,
    sub_game        = excluded.sub_game,
    delivery_time   = excluded.delivery_time,
    delivery_hours  = excluded.delivery_hours,
    delivery_days   = excluded.delivery_days,
    delivery_method = excluded.delivery_method,
    quantity        = excluded.quantity,
    enabled         = excluded.enabled,
    last_relisted   = excluded.last_relisted,
    scraped_at      = excluded.scraped_at
"""


def load_products() -> list:
    init_db()
    with _conn() as con:
        rows = con.execute("SELECT * FROM products ORDER BY id").fetchall()

    if not rows:
        # Auto-fallback: SQLite kosong → baca JSON, lalu langsung simpan ke DB
        json_path = os.path.join(BASE_DIR, "products.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                products = json.load(f)
            if products:
                save_products(products)
                return products
        return []

    return [_row_to_product(r) for r in rows]


def save_products(products: list):
    """Ganti seluruh isi tabel products."""
    init_db()
    with _conn() as con:
        con.execute("DELETE FROM products")
        for p in products:
            con.execute(_UPSERT_SQL, _product_params(p))


def upsert_product(product: dict):
    """Insert atau update satu produk berdasarkan URL."""
    init_db()
    with _conn() as con:
        con.execute(_UPSERT_SQL, _product_params(product))


def update_product_relisted(url: str, timestamp: str):
    """Update hanya kolom last_relisted untuk satu produk."""
    init_db()
    with _conn() as con:
        con.execute(
            "UPDATE products SET last_relisted=? WHERE url=?",
            (timestamp, url),
        )


# ─── Auth / Session ───────────────────────────────────────────────────────────

def has_session() -> bool:
    init_db()
    with _conn() as con:
        row = con.execute(
            "SELECT storage_state FROM auth WHERE id=1"
        ).fetchone()

    if row and row["storage_state"]:
        try:
            data = json.loads(row["storage_state"])
            if data.get("cookies"):
                return True
        except Exception:
            pass

    # Auto-fallback: cek auth.json langsung, lalu simpan ke DB
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("cookies"):
                save_session_from_file(AUTH_FILE)
                return True
        except Exception:
            pass

    return False


def save_session_dict(state: dict):
    """
    Simpan Playwright storage-state (dict) ke SQLite dan sync ke auth.json.
    Dipanggil setelah context.storage_state() mengembalikan dict.
    """
    content = json.dumps(state, ensure_ascii=False, indent=2)
    _write_auth_to_db(content)
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        f.write(content)


def save_session_from_file(path: str = AUTH_FILE):
    """Baca file Playwright storage-state dan simpan ke SQLite."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    _write_auth_to_db(content)


def _write_auth_to_db(json_content: str):
    init_db()
    with _conn() as con:
        con.execute(
            "INSERT INTO auth(id, storage_state, updated_at) VALUES(1,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "storage_state=excluded.storage_state, updated_at=excluded.updated_at",
            (json_content, datetime.now().isoformat()),
        )


def get_session_path() -> str | None:
    """
    Tulis session dari SQLite ke auth.json, kembalikan path-nya.
    Return None kalau tidak ada session.
    Dipakai oleh Playwright yang butuh file path.
    """
    init_db()
    with _conn() as con:
        row = con.execute(
            "SELECT storage_state FROM auth WHERE id=1"
        ).fetchone()
    if not row or not row["storage_state"]:
        return None
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        f.write(row["storage_state"])
    return AUTH_FILE


def clear_session():
    """Hapus session dari SQLite dan auth.json."""
    init_db()
    with _conn() as con:
        con.execute("DELETE FROM auth WHERE id=1")
    if os.path.exists(AUTH_FILE):
        os.remove(AUTH_FILE)


# ─── Migration dari JSON ──────────────────────────────────────────────────────

def migrate_from_json(
    config_path: str = None,
    products_path: str = None,
    auth_path: str = None,
) -> dict:
    """
    Pindahkan data dari file JSON lama ke SQLite.
    Return: {"migrated": [...], "errors": [...], "counts": {...}}
    """
    config_path   = config_path   or os.path.join(BASE_DIR, "config.json")
    products_path = products_path or os.path.join(BASE_DIR, "products.json")
    auth_path     = auth_path     or os.path.join(BASE_DIR, "auth.json")

    init_db()
    migrated = []
    errors   = []
    counts   = {}

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            save_config(cfg)
            counts["config"] = len(cfg)
            migrated.append(f"config ({len(cfg)} key)")
        except Exception as e:
            errors.append(f"config.json: {e}")

    if os.path.exists(products_path):
        try:
            with open(products_path, "r", encoding="utf-8") as f:
                products = json.load(f)
            save_products(products)
            counts["products"] = len(products)
            migrated.append(f"products ({len(products)} item)")
        except Exception as e:
            errors.append(f"products.json: {e}")

    if os.path.exists(auth_path):
        try:
            save_session_from_file(auth_path)
            counts["auth"] = 1
            migrated.append("auth/session")
        except Exception as e:
            errors.append(f"auth.json: {e}")

    return {"migrated": migrated, "errors": errors, "counts": counts}


def json_files_exist() -> dict:
    """Cek file JSON lama mana yang masih ada."""
    base = BASE_DIR
    return {
        "config":   os.path.exists(os.path.join(base, "config.json")),
        "products": os.path.exists(os.path.join(base, "products.json")),
        "auth":     os.path.exists(os.path.join(base, "auth.json")),
    }


def db_stats() -> dict:
    """Statistik isi database saat ini."""
    init_db()
    with _conn() as con:
        n_products = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        n_config   = con.execute("SELECT COUNT(*) FROM config").fetchone()[0]
        has_auth   = con.execute("SELECT COUNT(*) FROM auth").fetchone()[0]
    return {
        "products": n_products,
        "config_keys": n_config,
        "has_auth": bool(has_auth),
        "db_size_kb": round(os.path.getsize(DB_FILE) / 1024, 1) if os.path.exists(DB_FILE) else 0,
    }
