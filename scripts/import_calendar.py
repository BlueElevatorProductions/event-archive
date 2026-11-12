#!/usr/bin/env python3
"""Add events picked from the Calendar scan.

Reads data/calendar_picks.json: a list of
  {"id": <calendar item id from data/calendar_items.jsonl>, "title": "...",
   "kind": "concert|festival|comedy|theatre|sports|kids|other", "venue": "", "city": ""}
written by whoever reviewed the scan (you, or your AI assistant). A calendar
entry is a plan, not proof, so everything lands as status 'review' with source
'calendar'. Same-day events that already exist (including ones archived in the
app) are left alone. Idempotent via source_ref."""
import json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from schema import connect  # noqa: E402
from settings import load  # noqa: E402

STOP = {"the", "a", "and", "of", "at", "vs", "new", "york", "show", "s", "game", "live", "tour", "concert", "performance"}
tok = lambda s: {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if t not in STOP}


def main():
    picks_path = ROOT / "data/calendar_picks.json"
    if not picks_path.exists():
        sys.exit("no data/calendar_picks.json yet. Run scan_calendar.py, review data/calendar_items.jsonl, then write the picks.")
    shared = load()["calendars"]["shared_with"]
    items = {}
    for l in open(ROOT / "data/calendar_items.jsonl"):
        o = json.loads(l)
        items[o["id"]] = o
    db = connect()
    stats = dict(added=0, existing=0, missing=0, renamed=0)
    for p in json.loads(picks_path.read_text()):
        cid, title, kind, venue, city = p["id"], p["title"], p.get("kind", "other"), p.get("venue", ""), p.get("city", "")
        o = items.get(cid)
        if not o:
            stats["missing"] += 1
            continue
        ref = f"calendar:{cid}"
        if db.execute("select 1 from concerts where source_ref=?", (ref,)).fetchone():
            continue
        same = db.execute("select * from concerts where date between date(?,'-1 day') and date(?,'+1 day')",
                          (o["date"], o["date"])).fetchall()
        hit = next((e for e in same if tok(e["artist"] + " " + e["supporting"]) & tok(title)
                    or (venue and tok(e["venue"]) & tok(venue))), None)
        if hit is None and kind != "kids":   # a non-kid event already on that exact day is almost always the same night out
            hit = next((e for e in same if e["date"] == o["date"] and e["kind"] not in ("kids", "archived")), None)
        if hit is None and kind == "kids":   # same for a kids' show already found by email or Photos that day
            hit = next((e for e in same if e["date"] == o["date"] and (e["kind"] == "kids" or e["source"] == "photos")), None)
        if hit:
            if hit["artist"].startswith("Unidentified performance") and hit["kind"] != "archived":
                db.execute("update concerts set artist=?, kind=?, venue=case when venue='' then ? else venue end where id=?",
                           (title, kind, venue, hit["id"]))
                stats["renamed"] += 1
            stats["existing"] += 1
            continue
        note = f"From your calendar ({o['cal']}): “{o['summary']}”" + (f" at {o['location']}" if o["location"] else "") + "."
        new = db.execute(
            "insert into concerts(date,artist,supporting,venue,city,kind,notes,source,source_ref,status,created)"
            " values(?,?,'',?,?,?,?,'calendar',?,'review',?)",
            (o["date"], title, venue, city, kind, note, ref, time.time())).lastrowid
        who = shared.get(o["cal"])           # a calendar shared with someone: tag them
        if who:
            db.execute("insert or ignore into people(name) values(?)", (who,))
            pid = db.execute("select id from people where name=?", (who,)).fetchone()[0]
            db.execute("insert or ignore into concert_people values(?,?,'manual')", (new, pid))
        stats["added"] += 1
    db.commit()
    print(stats)


if __name__ == "__main__":
    main()
