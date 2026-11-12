#!/usr/bin/env python3
"""Merge classified emails (+ concertarchives.org notification emails) into events
and load them into data/concerts.db. Idempotent: an event already present
(same source_ref) is left untouched, so manual edits survive re-runs."""
import collections, datetime, json, re, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from schema import connect, DATA, MEDIA  # noqa: E402

ROLE_RANK = ["purchase", "delivery", "transfer_in", "reminder", "post_event", "personal",
             "other", "refund", "cancelled", "sold", "transfer_out"]
GONE = {"sold", "transfer_out", "cancelled", "refund"}
STOP = set("the a an and of at vs v in for with to new york ny nyc tour live show presents students class".split())
from settings import load, canonical  # noqa: E402
CFG = load()
SKIP_IDS = set(CFG.get("skip_email_ids", []))   # emails to ignore, by Mail message id
MON = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}


def toks(s):
    s = re.sub(r"p\.?\s?s\.?\s?(\d+)", r"ps\1", (s or "").lower())
    return {t for t in re.findall(r"[a-z0-9]+", s) if t not in STOP and len(t) > 1}


def people_of(r):
    out = []
    if r.get("kind") == "kids":
        return out
    for n in r.get("people") or []:
        n = canonical(n, CFG)
        if n:
            out.append(n)
    return out


def concertarchives(cands):
    """Events the owner logged on concertarchives.org, parsed from its notification emails."""
    ev = {}
    for c in cands:
        if "concertarchives.org" not in c["sender"]:
            continue
        p = DATA / "emails" / f"{c['id']}.txt"
        text = p.read_text() if p.exists() else c["text"]
        hits = [(m[1], m[2], m[3]) for m in re.finditer(
            r"\n\s*([^\n]+?)\s*\n\s*([A-Z][a-z]{2} \d{2}, \d{4})\s*\n\s*([^\n]+?)\s*\n", text)]
        hits += [(m[1], m[2], "") for m in re.finditer(r"\n\s*([^\n]+?) – ([A-Z][a-z]{2} \d{2}, \d{4}):", text)]
        for acts, d, place in hits:
            mon, day, yr = re.match(r"(\w{3}) (\d{2}), (\d{4})", d).groups()
            date = f"{yr}-{MON[mon]:02d}-{day}"
            acts = [a.strip() for a in acts.split(" / ") if a.strip()]
            if not acts or "you saw" in acts[0].lower():
                continue
            bits = [b.strip() for b in place.split(",")]
            venue = bits[0] if place else ""
            city = ", ".join(bits[1:3]) if len(bits) > 2 else ""
            key = (date, acts[0].lower())
            if key not in ev or (venue and not ev[key]["venue"]):
                ev[key] = dict(date=date, artist=acts[0], supporting=", ".join(acts[1:]), venue=venue,
                               city=city, kind="concert", status="confirmed", source="concertarchives",
                               people=set(), roles=set(), emails=[], section="", price="", notes="")
    return list(ev.values())


def main():
    cands = [json.loads(l) for l in open(DATA / "candidates.jsonl")]
    rows = [json.loads(l) for l in open(DATA / "classified.jsonl")]
    events = concertarchives(cands)
    ca_ids = {c["id"] for c in cands if "concertarchives.org" in c["sender"]}
    rel = [r for r in rows if r.get("relevant") and r.get("date") and r["id"] not in SKIP_IDS
           and r["id"] not in ca_ids and re.match(r"\d{4}-\d\d-\d\d$", r["date"])]
    rel.sort(key=lambda r: ROLE_RANK.index(r.get("role")) if r.get("role") in ROLE_RANK else 9)
    for r in rel:
        name = r.get("headliner") or r.get("event") or ""
        if r.get("kind") in ("kids", "other", "theatre") and r.get("event"):
            name = r["event"]
        if not name:
            continue
        t = toks(name) | toks(r.get("headliner"))
        hit = None
        for e in events:
            if e["date"] == r["date"] and (t & (toks(e["artist"]) | e.get("t", set()))
                                           or (toks(r.get("venue")) & toks(e["venue"]))):
                hit = e
                break
        if not hit:
            hit = dict(date=r["date"], artist=name.strip(), supporting=r.get("supporting") or "",
                       venue="", city="", kind=r.get("kind") or "other", status="review", source="email",
                       people=set(), roles=set(), emails=[], section="", price="", notes="", t=set())
            events.append(hit)
        hit.setdefault("t", set()).update(t)
        for f in ("venue", "city", "section", "price", "supporting"):
            v = r.get(f)
            if v and not hit[f] and str(v).lower() not in ("unknown", "null", "none"):
                hit[f] = str(v).strip()
        hit["people"].update(people_of(r))
        hit["roles"].add(r.get("role"))
        hit["emails"].append(r["id"])

    db = connect()
    added = 0
    for e in sorted(events, key=lambda e: e["date"]):
        ref = f"{e['source']}:{e['date']}:{'-'.join(sorted(toks(e['artist'])))[:60]}"
        if db.execute("select 1 from concerts where source_ref=?", (ref,)).fetchone():
            continue
        if e["roles"] and e["roles"] <= GONE:
            e["notes"] = "Email trail only shows these tickets being sold, transferred away, or cancelled — you may not have gone."
        cur = db.execute(
            "insert into concerts(date,artist,supporting,venue,city,kind,notes,section,price,source,source_ref,status,created)"
            " values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (e["date"], e["artist"], e["supporting"], e["venue"], e["city"], e["kind"], e["notes"],
             e["section"], e["price"], e["source"], ref, e["status"], time.time()))
        cid = cur.lastrowid
        for n in e["people"]:
            db.execute("insert or ignore into people(name) values(?)", (n,))
            pid = db.execute("select id from people where name=?", (n,)).fetchone()[0]
            db.execute("insert or ignore into concert_people values(?,?,'email')", (cid, pid))
        for mid in e["emails"][:1]:  # best-ranked email becomes the receipt
            src = DATA / "emails" / f"{mid}.html"
            if src.exists():
                shutil.copyfile(src, MEDIA / f"email-{mid}.html")
                db.execute("insert into media(concert_id,kind,path,caption,created) values(?,?,?,?,?)",
                           (cid, "email", f"email-{mid}.html", "Email receipt", time.time()))
        added += 1
    db.commit()
    print("events:", len(events), "added:", added)
    print(collections.Counter(e["kind"] for e in events))
    print(collections.Counter(e["source"] for e in events))


if __name__ == "__main__":
    main()
