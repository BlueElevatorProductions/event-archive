#!/usr/bin/env python3
"""Attach Photos-library pictures + recognized people to events.

A photo matches when it was taken on the event's date (until 3am next day) within
RADIUS_M of the venue. Venues are geocoded by name via OpenStreetMap Nominatim
(only the venue name + city is sent; cached in data/geocode.json).
READ-ONLY against the Photos library; preview-size copies go to data/media/.
"""
import json, math, shutil, sqlite3, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from schema import connect, DATA, MEDIA  # noqa: E402

LIB = Path.home() / "Pictures/Photos Library.photoslibrary"
RADIUS_M, MAX_PER_EVENT = 500, 12
from settings import load, canonical  # noqa: E402
CFG = load()
GEO = DATA / "geocode.json"


def geocode(q, cache):
    if q in cache:
        return cache[q]
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "event-archive-local/1.0"}), timeout=20) as r:
            j = json.loads(r.read())
        cache[q] = [float(j[0]["lat"]), float(j[0]["lon"])] if j else None
    except Exception:
        return None
    GEO.write_text(json.dumps(cache, indent=1))
    time.sleep(1.1)
    return cache[q]


def dist(a, b, c, d):
    p = math.radians
    h = math.sin(p(c - a) / 2) ** 2 + math.cos(p(a)) * math.cos(p(c)) * math.sin(p(d - b) / 2) ** 2
    return 12742000 * math.asin(math.sqrt(h))


def main():
    db = connect()
    ph = sqlite3.connect(f"file:{LIB}/database/Photos.sqlite?mode=ro", uri=True)
    cache = json.loads(GEO.read_text()) if GEO.exists() else {}
    stats = dict(events=0, geocoded=0, with_photos=0, photos=0, people=0)
    for c in db.execute("select * from concerts where kind!='archived' and venue!='' order by date").fetchall():
        stats["events"] += 1
        if db.execute("select 1 from media where concert_id=? and kind='photo' and caption like 'Photos%'", (c["id"],)).fetchone():
            continue
        loc = geocode(f"{c['venue']}, {c['city']}".strip(", "), cache) or (c["city"] and geocode(f"{c['venue']}", cache))
        if not loc:
            continue
        stats["geocoded"] += 1
        lat, lon = loc
        rows = ph.execute("""
            select a.Z_PK, a.ZUUID, a.ZLATITUDE, a.ZLONGITUDE, a.ZKIND
            from ZASSET a left join ZADDITIONALASSETATTRIBUTES x on x.ZASSET=a.Z_PK
            where a.ZTRASHEDSTATE=0 and a.ZLATITUDE between ? and ? and a.ZLONGITUDE between ? and ?
              and datetime(a.ZDATECREATED+978307200+coalesce(x.ZTIMEZONEOFFSET,-18000)-10800,'unixepoch') like ?
            order by a.ZDATECREATED""", (lat - .01, lat + .01, lon - .015, lon + .015, c["date"] + "%")).fetchall()
        rows = [r for r in rows if dist(lat, lon, r[2], r[3]) <= RADIUS_M]
        if not rows:
            continue
        stats["with_photos"] += 1
        pks = [r[0] for r in rows]
        names = {n for (n,) in ph.execute(
            f"select distinct p.ZFULLNAME from ZDETECTEDFACE f join ZPERSON p on p.Z_PK=f.ZPERSONFORFACE "
            f"where p.ZFULLNAME!='' and f.ZASSETFORFACE in ({','.join('?' * len(pks))})", pks)}
        for n in names:
            n = canonical(n, CFG)
            if not n:
                continue
            db.execute("insert or ignore into people(name) values(?)", (n,))
            pid = db.execute("select id from people where name=?", (n,)).fetchone()[0]
            db.execute("insert or ignore into concert_people values(?,?,'photos')", (c["id"], pid))
            stats["people"] += 1
        stills = [r for r in rows if r[4] == 0]
        step = max(1, len(stills) // MAX_PER_EVENT)
        n = 0
        for r in stills[::step]:
            src = LIB / "resources/derivatives" / r[1][0] / f"{r[1]}_1_105_c.jpeg"
            if not src.exists():
                src = LIB / "resources/derivatives/masters" / r[1][0] / f"{r[1]}_4_5005_c.jpeg"
            if not src.exists() or n >= MAX_PER_EVENT:
                continue
            name = f"photo-{r[1]}.jpeg"
            shutil.copyfile(src, MEDIA / name)
            db.execute("insert into media(concert_id,kind,path,caption,created) values(?,?,?,?,?)",
                       (c["id"], "photo", name, "Photos library", time.time()))
            n += 1
        stats["photos"] += n
        db.commit()
    print(stats)


if __name__ == "__main__":
    main()
