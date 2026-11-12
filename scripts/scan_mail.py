#!/usr/bin/env python3
"""Scan Apple Mail's local store for event-ticket candidate emails.

STRICTLY READ-ONLY against ~/Library/Mail (sqlite opened mode=ro, files only read).
Sends nothing. Writes data/candidates.jsonl and each candidate's body under
data/emails/<rowid>.{html,txt}.
"""
import email, email.policy, html, json, os, re, sqlite3
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
MAIL = Path.home() / "Library/Mail/V10"
OUT = ROOT / "data"
(OUT / "emails").mkdir(parents=True, exist_ok=True)

VENDORS = """ticketmaster livenation axs.com eventbrite ticketfly seetickets dice.fm stubhub
ticketweb etix seatgeek frontgatetickets brownpapertickets tixr venuepilot eventim
telecharge todaytix msg.com bowerypresents ticketnetwork vividseats showclix universe.com
wantickets ra.co tickets.com prekindle ovationtix tessitura lincolncenter carnegiehall bam.org
citywinery brooklynbowl ticketleap thundertix nightout.com holdmyticket festicket goldstar
partiful gametime tickpick mlb.com nba.com broadway roundabout publictheater playbill
telechargeoffers lovetheatre ticketspice onthestage showtix4u gofan hometown booktix
ludus cur8 zeffy humanitix luma tock""".split()
MARKETING = ("newsletter", "engage.", "eml.", "marketing", "campaign", "picks@", "weeklymix",
             "events@mail.stubhub", "email1.msg.com", "promo", "news@", "offers", "deals")
SUBJ = re.compile(r"ticket|e-?tix|\btix\b|will call|admit one|concert|recital|performance|"
                  r"talent show|showcase|musical|you'?re going|see you (at|tonight)|"
                  r"doors (at|open)|live at |opening night", re.I)
VSUBJ = re.compile(r"your|you'?re|you got|you just|confirm|order|see you|sent you|transfer|deliver|ready|reminder|receipt", re.I)
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "app"))
from settings import load  # noqa: E402
SKIP_BOX = re.compile(r"/(" + "|".join(["Newsletters", "Junk", "Google%20Junk", "Health", "Bills", "Security", "Deleted"]
                                       + [re.escape(b) for b in load().get("skip_mailboxes", [])]) + ")", re.I)
NOISE = re.compile(r"password|sign in activity|privacy policy|account information|get paid|"
                   r"support ticket|ticket #|\[ticket|zendesk|parking ticket|flight|airline|amtrak|"
                   r"jira|help ?desk|case #|lottery|powerball|raffle|boarding|itinerary|presale|"
                   r"on sale|just announced|coming soon|% off|picks for you|verify your|"
                   r"performance review|performance report|app performance", re.I)


def body_of(path):
    raw = path.read_bytes()
    nl = raw.index(b"\n")
    n = int(raw[:nl].strip())
    msg = email.message_from_bytes(raw[nl + 1: nl + 1 + n], policy=email.policy.default)
    h = t = None
    atts = []
    for part in msg.walk():
        fn = part.get_filename()
        if fn:
            atts.append(fn)
        if part.is_multipart() or fn:
            continue
        try:
            c = part.get_content()
        except Exception:
            continue
        ct = part.get_content_type()
        if ct == "text/html" and h is None:
            h = c
        elif ct == "text/plain" and t is None:
            t = c
    return msg, h, t, atts


def to_text(h):
    h = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|h\d|li|td)>", "\n", h)
    h = html.unescape(re.sub(r"<[^>]+>", " ", h))
    h = re.sub(r"[ \t ‌​͏­]+", " ", h)
    return re.sub(r"\n\s*\n+", "\n", h).strip()


def main():
    paths = {}
    for d, _, files in os.walk(MAIL):
        for f in files:
            if f.endswith(".emlx"):
                paths[f.split(".")[0]] = Path(d) / f
    db = sqlite3.connect(f"file:{MAIL}/MailData/Envelope Index?mode=ro", uri=True)
    rows = db.execute("""select m.rowid, m.date_received, a.address, a.comment, s.subject, mb.url
        from messages m join addresses a on a.rowid=m.sender join subjects s on s.rowid=m.subject
        join mailboxes mb on mb.rowid=m.mailbox where m.deleted=0 order by m.date_received""")
    seen, n = set(), 0
    with open(OUT / "candidates.jsonl", "w") as out:
        for rowid, ts, addr, name, subj, url in rows:
            addr = (addr or "").lower()
            subj = subj or ""
            vendor = any(v in addr for v in VENDORS)
            mk = any(m in addr for m in MARKETING)
            if NOISE.search(subj):
                continue
            if vendor:
                if not VSUBJ.search(subj) or (mk and not re.search(r"your (order|ticket)|you'?re going|confirm", subj, re.I)):
                    continue
            else:
                if SKIP_BOX.search(url) or mk or not SUBJ.search(subj):
                    continue
            key = (addr, subj, ts // 86400)
            if key in seen:
                continue
            seen.add(key)
            p = paths.get(str(rowid))
            text, atts, to = "", [], ""
            if p:
                try:
                    msg, h, t, atts = body_of(p)
                    to = str(msg.get("To", ""))[:200]
                    if h:
                        (OUT / "emails" / f"{rowid}.html").write_text(h)
                    text = to_text(h) if h else (t or "")
                    (OUT / "emails" / f"{rowid}.txt").write_text(text)
                except Exception as e:
                    text = f"[parse error {e}]"
            out.write(json.dumps(dict(
                id=rowid, ts=ts, sender=addr, sender_name=name or "", subject=subj,
                mailbox=unquote(url.split("/", 3)[-1]), account=url.split("/")[2], to=to,
                vendor=vendor, attachments=atts, has_body=bool(p), text=text[:3000])) + "\n")
            n += 1
    print(n, "candidates")


if __name__ == "__main__":
    main()
