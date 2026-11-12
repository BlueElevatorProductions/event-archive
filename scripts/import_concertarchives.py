#!/usr/bin/env python3
"""Import a list of concerts you already keep somewhere else (a concertarchives.org
profile, setlist.fm, a spreadsheet).

Reads data/concertarchives.json: a list of
  {"date": "YYYY-MM-DD", "acts": "Headliner / Opener / Opener", "venue": "", "city": "City, ST", "notes": ""}
Existing events on the same date are confirmed and enriched rather than duplicated."""
import json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from schema import connect  # noqa: E402

tok = lambda s: set(re.findall(r"[a-z0-9]+", (s or "").lower())) - {"the", "a", "and", "of", "new", "york"}


def main():
    src = ROOT / "data/concertarchives.json"
    if not src.exists():
        sys.exit("no data/concertarchives.json to import")
    db = connect()
    new = merged = 0
    for r in json.loads(src.read_text()):
        date, venue, city, tour = r["date"], r.get("venue", ""), r.get("city", ""), r.get("notes", "")
        acts = [a.strip() for a in r["acts"].split(" / ")]
        head, support = acts[0], ", ".join(acts[1:])
        ref = f"concertarchives:{date}:{head.lower()}"
        if db.execute("select 1 from concerts where source_ref=?", (ref,)).fetchone():
            continue
        hit = next((e for e in db.execute("select * from concerts where date=? and kind!='archived'", (date,))
                    if tok(e["artist"]) & tok(" ".join(acts)) or tok(e["venue"]) & tok(venue)), None)
        if hit and hit["status"] == "confirmed" and hit["venue"] and hit["supporting"]:
            continue                          # already confirmed and filled in; nothing to add
        if hit:
            db.execute("update concerts set status='confirmed', kind='concert', supporting=?, venue=?, city=?, notes=? where id=?",
                       (hit["supporting"] or support, hit["venue"] or venue, hit["city"] or city,
                        hit["notes"] or tour, hit["id"]))
            merged += 1
        else:
            db.execute("insert into concerts(date,artist,supporting,venue,city,kind,notes,source,source_ref,status,created)"
                       " values(?,?,?,?,?,'concert',?,'concertarchives',?,'confirmed',?)",
                       (date, head, support, venue, city, tour, ref, time.time()))
            new += 1
    db.commit()
    print("new:", new, "merged into existing:", merged)


if __name__ == "__main__":
    main()
