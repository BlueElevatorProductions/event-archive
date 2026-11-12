"""Shared SQLite schema + migrations for the Event Archive."""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MEDIA = DATA / "media"
DB = DATA / "concerts.db"

SCHEMA = """
create table if not exists concerts(
  id integer primary key, date text not null, artist text not null,
  supporting text default '', venue text default '', city text default '',
  kind text default 'concert', notes text default '',
  section text default '', price text default '',
  source text default 'manual', source_ref text default '', created real);
create table if not exists people(id integer primary key, name text unique not null);
create table if not exists concert_people(
  concert_id integer references concerts(id) on delete cascade,
  person_id integer references people(id) on delete cascade,
  source text default 'manual', primary key(concert_id, person_id));
create table if not exists media(
  id integer primary key, concert_id integer references concerts(id) on delete cascade,
  kind text not null,            -- stub | photo | email
  path text not null, caption text default '', created real);
"""


def connect():
    MEDIA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    cols = {r[1] for r in c.execute("pragma table_info(concerts)")}
    if "status" not in cols:  # confirmed | review
        c.execute("alter table concerts add column status text default 'confirmed'")
    c.execute("pragma foreign_keys=on")
    c.commit()
    return c
