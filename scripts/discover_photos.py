#!/usr/bin/env python3
"""Find events with no email trail from the Photos library's own search index.

Photos tags pictures with public event names ("U2 Concert", "Bills at Jets"),
event categories, venue names and scene labels. This groups those by day:
  - a day that already has a matching event gets photos/people attached;
  - otherwise a new event is added with status 'review', source 'photos'.
READ-ONLY against the Photos library. Pass --dry to only print.
"""
import collections, re, shutil, sqlite3, struct, sys, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from schema import connect, MEDIA  # noqa: E402

LIB = Path.home() / "Pictures/Photos Library.photoslibrary"
DRY = "--dry" in sys.argv
MAXP = 12
from settings import load, canonical  # noqa: E402
CFG = load()
EVENT, EVCAT, POI, CITY, STATE, MEANING = 1800, 1802, 1700, 5, 11, 1600
SCENES = {"Concert", "Performance", "Theater"}
STOP = {"the", "a", "and", "of", "at", "vs", "new", "york", "concert", "live"}
tok = lambda s: {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if t not in STOP}


def kind_of(cats, names):
    c = " ".join(cats).lower()
    if any(k in c for k in ("sport", "football", "baseball", "basketball", "hockey")):
        return "sports"
    if "comedy" in c:
        return "comedy"
    if "theater" in c or "cabaret" in c:
        return "theatre"
    if "festival" in c:
        return "festival"
    if any(k in c for k in ("music", "rock", "pop", "folk", "concert", "alternative")) or any("Concert" in n for n in names):
        return "concert"
    if "theater" in c or "cabaret" in c:
        return "theatre"
    return "other"


def main():
    ph = sqlite3.connect(f"file:{LIB}/database/Photos.sqlite?mode=ro", uri=True)
    psi = sqlite3.connect(f"file:{LIB}/database/search/psi.sqlite?mode=ro", uri=True)
    # asset table: ZUUID -> (pk, local day, kind)
    assets = {}
    for pk, u, day, kind in ph.execute("""
        select a.Z_PK, a.ZUUID, date(a.ZDATECREATED+978307200+coalesce(x.ZTIMEZONEOFFSET,-18000)-10800,'unixepoch'), a.ZKIND
        from ZASSET a left join ZADDITIONALASSETATTRIBUTES x on x.ZASSET=a.Z_PK where a.ZTRASHEDSTATE=0"""):
        assets[u] = (pk, day, kind)
    tags = collections.defaultdict(lambda: collections.defaultdict(set))  # uuid -> category -> strings
    for u0, u1, cat, s in psi.execute(f"""
        select a.uuid_0, a.uuid_1, g.category, g.content_string from ga join groups g on g.rowid=ga.groupid
        join assets a on a.rowid=ga.assetid where g.category in ({EVENT},{EVCAT},{POI},{CITY},{STATE},{MEANING})"""):
        u = str(uuid.UUID(bytes=struct.pack("<qq", u0, u1))).upper()
        if u not in assets:
            u = str(uuid.UUID(bytes=struct.pack(">qq", u0, u1))).upper()
        if u in assets:
            tags[u][cat].add(s.rstrip('\x00').strip())
    days = collections.defaultdict(list)
    for u, t in tags.items():
        if t.get(EVENT) or (t.get(MEANING, set()) & SCENES):
            days[assets[u][1]].append(u)

    db = connect()
    existing = collections.defaultdict(list)
    for r in db.execute("select * from concerts where kind!='archived'"):
        existing[r["date"]].append(r)
    stats = collections.Counter()
    for day in sorted(days):
        us = days[day]
        names, cats, pois, city, state = (collections.Counter() for _ in range(5))
        for u in us:
            t = tags[u]
            names.update(t.get(EVENT, ())); cats.update(t.get(EVCAT, ())); pois.update(t.get(POI, ()))
            city.update(t.get(CITY, ())); state.update(t.get(STATE, ()))
        named = bool(names)
        if not named and len(us) < 6:      # unnamed scene-only clusters need some weight
            continue
        ordered = [n for n, _ in names.most_common()]
        clean = [re.sub(r"\s+Concert$", "", n) for n in ordered]
        kind = kind_of(cats, ordered) if named else "other"
        venue = next((p for p, _ in pois.most_common() if re.search(
            r"Stadium|Theat|Hall|Center|Field|Park|Garden|Arena|Ballroom|Paramount|Casino|EXIT|Music|Coliseum|Amphithea", p)), "")
        where = ", ".join(x.most_common(1)[0][0].strip() for x in (city, state) if x)
        if named and kind == "other" and re.search(r"science|museum", " ".join(cats).lower()):
            continue                       # museum exhibits, not events
        title = clean[0] if named else f"Unidentified performance{' at ' + venue if venue else ''}"
        hit = None
        for e in existing.get(day, []):
            if (tok(e["artist"]) | tok(e["supporting"])) & tok(" ".join(clean)) or (venue and tok(e["venue"]) & tok(venue)) \
                    or (not named) or e["kind"] == kind:
                hit = e
                break
        pks = [assets[u][0] for u in us]
        people = {canonical(n, CFG) for (n,) in ph.execute(
            f"select distinct p.ZFULLNAME from ZDETECTEDFACE f join ZPERSON p on p.Z_PK=f.ZPERSONFORFACE "
            f"where p.ZFULLNAME!='' and f.ZASSETFORFACE in ({','.join('?' * len(pks))})", pks)}
        people = {n for n in people if n}
        if DRY:
            print(f"{day} | {'=' if hit else '+'} | {kind:8} | {title[:40]:40} | {venue[:28]:28} | {where[:18]:18} | {len(us):3} | {','.join(sorted(people))[:40]}")
            stats["match" if hit else ("new_named" if named else "new_unnamed")] += 1
            continue
        if hit:
            cid = hit["id"]
            stats["matched_existing"] += 1
        else:
            others = ", ".join(dict.fromkeys(c for c in clean[1:4] if tok(c) - tok(title)))
            ref = f"photos:{day}:{'-'.join(sorted(tok(title)))[:60]}"
            if db.execute("select 1 from concerts where source_ref=?", (ref,)).fetchone():
                continue
            note = (f"Found in Photos: {len(us)} pictures that day tagged with this event." if named else
                    f"Found in Photos: {len(us)} pictures that day that look like a stage/performance. Name it or dismiss it.")
            cid = db.execute(
                "insert into concerts(date,artist,supporting,venue,city,kind,notes,source,source_ref,status,created)"
                " values(?,?,?,?,?,?,?,'photos',?,'review',?)",
                (day, title, others, venue, where, kind, note, ref, time.time())).lastrowid
            stats["new_named" if named else "new_unnamed"] += 1
        for n in people:
            db.execute("insert or ignore into people(name) values(?)", (n,))
            pid = db.execute("select id from people where name=?", (n,)).fetchone()[0]
            db.execute("insert or ignore into concert_people values(?,?,'photos')", (cid, pid))
        have = {r[0] for r in db.execute("select path from media where concert_id=? and kind='photo'", (cid,))}
        stills = [u for u in us if assets[u][2] == 0]
        n = len(have)
        for u in stills[::max(1, len(stills) // MAXP)]:
            src = LIB / "resources/derivatives" / u[0] / f"{u}_1_105_c.jpeg"
            if not src.exists():   # fall back to the small thumbnail
                src = LIB / "resources/derivatives/masters" / u[0] / f"{u}_4_5005_c.jpeg"
            name = f"photo-{u}.jpeg"
            if n >= MAXP or name in have or not src.exists():
                continue
            shutil.copyfile(src, MEDIA / name)
            db.execute("insert into media(concert_id,kind,path,caption,created) values(?,?,?,?,?)",
                       (cid, "photo", name, "Photos library", time.time()))
            n += 1
            stats["photos_added"] += 1
    db.commit()
    print(dict(stats))


if __name__ == "__main__":
    main()
