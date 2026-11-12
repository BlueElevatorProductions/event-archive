"""Personal settings for the scanners, read from data/settings.json.

Everything about *you* (your name, the people you go to shows with, which
calendars are yours) lives in that one private file, which is never shared.
Copy settings.example.json to data/settings.json and fill it in, or let your
AI assistant do it by following AGENTS.md. Missing keys fall back to blanks."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "settings.json"
DEFAULTS = {
    "owner": "",                # your full name, as it appears on tickets
    "about": "",                # one line of context for the classifier: where you live(d), kids' first names
    "self_names": [],           # names that mean you (never tagged as a companion)
    "aliases": {},              # other spellings -> the name to show, e.g. {"liz smith": "Elizabeth Smith"}
    "not_people": ["ticketmaster", "stubhub", "seatgeek", "seat geek"],
    "calendars": {
        "personal": [],         # calendar names scanned in full
        "work": [],             # calendar names scanned for evenings/weekends only
        "work_prefixes": [],    # same, matched by how the calendar name starts
        "shared_with": {},      # shared calendar name -> person to tag on its events
    },
    "skip_mailboxes": [],       # extra mailbox names the email scan should ignore
    "skip_email_ids": [],       # individual Mail message ids to ignore
    "openrouter_key_ref": "",   # optional 1Password reference; or set OPENROUTER_API_KEY instead
}


def load():
    s = json.loads(json.dumps(DEFAULTS))
    if PATH.exists():
        mine = json.loads(PATH.read_text())
        for k, v in mine.items():
            if isinstance(v, dict) and isinstance(s.get(k), dict):
                s[k].update(v)
            else:
                s[k] = v
    s["self_names"] = {n.lower() for n in s["self_names"]} | ({s["owner"].lower()} if s["owner"] else set())
    s["aliases"] = {k.lower(): v for k, v in s["aliases"].items()}
    s["not_people"] = {n.lower() for n in s["not_people"]} | s["self_names"]
    return s


def canonical(name, s):
    """Apply aliases; returns '' for names that are you or not a person."""
    n = " ".join(str(name).split())
    k = n.lower()
    if not n or "@" in n or k in s["not_people"] or len(n) > 40:
        return ""
    return s["aliases"].get(k, n)
