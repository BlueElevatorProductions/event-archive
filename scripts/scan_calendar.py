#!/usr/bin/env python3
"""Pull past one-off calendar entries that could be live events -> data/calendar_items.jsonl.

READ-ONLY against the local Calendar store (all accounts synced to this Mac).
Private/admin entries (medical, legal, pickups, calls...) are dropped here and
never leave the machine. Guests are kept locally for tagging only.
"""
import json, re, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = Path.home() / "Library/Group Containers/group.com.apple.calendar/Calendar.sqlitedb"
sys.path.insert(0, str(ROOT / "app"))
from settings import load  # noqa: E402
CAL = load()["calendars"]
PERSONAL, WORK = set(CAL["personal"]), set(CAL["work"])      # work calendars: evenings/weekends only
WORK_PREFIX = tuple(CAL["work_prefixes"])
SKIP = re.compile(
    r"\b(dr\.?|doctor|dentist|ortho|pediatric|therap|lawyer|attorney|divorce|court|custody|mediat|meds?|pharmacy|"
    r"vet|appointment|appt|pick ?up|drop ?off|call|zoom|meeting|mtg|1:1|sync|standup|stand-up meeting|interview|"
    r"session|edit|mix|deadline|invoice|pay |rent|bill|flight|fly |hotel|check[- ]?in|airbnb|vacation|camp|"
    r"conference[s]? ?$|parent teacher|school closed|no school|half day|first day|haircut|oil change|repair|"
    r"delivery|genius bar|birthday|bday|wedding|shower|funeral|lunch|breakfast|coffee|dinner|brunch|drinks|"
    r"work|home early|practice|rehearsal|lesson|class|gymnastics|swim|soccer practice|tutor|homework|"
    r"eval|visit|wellness|psych|iep|sick|covid|vaccine|shot|test|regents|dismissal|permission slip|due|rec|"
    r"recording|chat|in town|contact|trial|take|watch|quotes?|booking|vocals|drums|write|"
    r"reminder|renew|tax|irs|bank|dmv|jury|move|movers|inspection|closing|tickets on sale|on sale|presale)\b", re.I)


def main():
    if not PERSONAL and not WORK:
        names = [r[0] for r in sqlite3.connect(f"file:{DB}?mode=ro", uri=True).execute("select distinct title from Calendar where title!=''")]
        sys.exit("List your calendars in data/settings.json first. Calendars on this Mac: " + ", ".join(names))
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    idcols = [r[1] for r in db.execute("pragma table_info(Identity)")]
    name_col = "display_name" if "display_name" in idcols else None
    rows = db.execute("""
        select ci.ROWID id, ci.summary, ci.all_day, ci.has_attendees, c.title cal, l.title loc, l.address addr,
          case when ci.all_day=1 then date(ci.start_date+978307200,'unixepoch')
               else date(ci.start_date+978307200,'unixepoch','localtime') end day,
          case when ci.all_day=1 then '' else strftime('%H:%M',ci.start_date+978307200,'unixepoch','localtime') end tm,
          cast(strftime('%w', ci.start_date+978307200,'unixepoch','localtime') as int) dow
        from CalendarItem ci join Calendar c on c.ROWID=ci.calendar_id left join Location l on l.ROWID=ci.location_id
        where ci.has_recurrences=0 and ci.orig_item_id=0 and coalesce(ci.summary,'')!=''
          and ci.start_date+978307200 < strftime('%s','now') and ci.start_date > 0 and coalesce(ci.status,0)!=3
        order by ci.start_date""").fetchall()
    out, seen = [], set()
    for r in rows:
        cal, s = r["cal"], r["summary"].strip()
        if re.search(r"zoom\.us|riverside|meet\.google|teams\.microsoft", (r["loc"] or "") + (r["addr"] or "")):
            continue
        if cal in WORK or (WORK_PREFIX and cal.startswith(WORK_PREFIX)):
            if r["all_day"] or not (r["tm"] >= "17:30" or r["dow"] in (0, 6)):
                continue
        elif cal not in PERSONAL:
            continue
        if SKIP.search(s) or len(s) < 3:
            continue
        loc = " ".join(x for x in ((r["loc"] or ""), (r["addr"] or "")) if x).replace("\n", ", ")
        key = (r["day"], s.lower())
        if key in seen:
            continue
        seen.add(key)
        guests = []
        if r["has_attendees"] and name_col:
            guests = [g[0] for g in db.execute(
                f"select distinct i.{name_col} from Participant p join Identity i on i.ROWID=p.identity_id "
                f"where p.owner_id=? and p.is_self=0 and coalesce(i.{name_col},'')!=''", (r["id"],))]
        out.append(dict(id=r["id"], date=r["day"], time=r["tm"], cal=cal, summary=s, location=loc[:120], guests=guests[:12]))
    p = ROOT / "data/calendar_items.jsonl"
    p.write_text("".join(json.dumps(o) + "\n" for o in out))
    by = {}
    for o in out:
        by[o["cal"]] = by.get(o["cal"], 0) + 1
    print(len(rows), "one-off past items ->", len(out), "kept", by)


if __name__ == "__main__":
    main()
