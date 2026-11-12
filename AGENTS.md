# AGENTS.md — building someone's Event Archive

You are helping the person at this Mac build a private archive of every live event they've attended (concerts, sports, theatre, comedy, festivals, their kids' performances), using what is already on this machine. This file is the playbook. The owner is "they" below.

## Rules

1. **Read-only on their data.** Mail, Calendar and Photos stores are opened read-only (`mode=ro`). Never write to, send from, or delete in those apps. The scripts already do this; keep it that way if you write new ones.
2. **Everything stays local.** All output goes in `data/` (gitignored). Never commit, upload or paste its contents anywhere. Two disclosed exceptions: venue name + city go to OpenStreetMap Nominatim for geocoding, and `classify*.py` send text to OpenRouter only if the owner supplies a key. Tell them before either happens.
3. **Never delete.** Dismissed events are archived (`kind='archived'`), removed people are tombstoned (`source='removed'`), detached media files stay on disk. Before a bulk change, copy `data/concerts.db` into `data/_Archive/`.
4. **Don't overclaim.** A receipt, calendar entry or photo cluster is evidence, not proof. New finds get `status='review'` unless the owner has confirmed them or the source is their own log of shows attended. Never invent a date, venue or companion.
5. **Secrets.** Never print API keys or password-manager contents. Family details beyond first names don't belong in `settings.json`.
6. **The owner's edits win.** Importers are idempotent by `source_ref` and must not overwrite fields the owner changed in the app.

## Layout

- `app/server.py` — Flask app on `127.0.0.1:5177` (`uv run app/server.py`). `app/static/index.html` is the whole UI. `app/schema.py` creates the SQLite DB at `data/concerts.db`. `app/settings.py` loads `data/settings.json`.
- Tables: `concerts(date, artist, supporting, venue, city, kind, notes, section, price, source, source_ref, status)`, `people`, `concert_people(source: manual|email|photos|removed)`, `media(kind: stub|photo|email)`.
- `kind`: concert, festival, comedy, theatre, sports, kids, other, archived. `status`: confirmed, review.
- `scripts/` — one script per step below. `launcher/make_app.sh` builds the clickable app.

## Steps

### 0. Set up

- Check `uv` exists; start the app and confirm the page loads empty.
- The scanners need to read `~/Library/Mail`, the Calendar store and the Photos library. If a read fails with a permission error, ask the owner to grant **Full Disk Access** to the app you are running in (System Settings → Privacy & Security), then retry. Don't work around it.
- Interview the owner briefly and write `data/settings.json` from `settings.example.json`: full name; a line about where they've lived and their kids' first names (it helps date and place events); the people they usually go with and any alternate spellings (aliases); which email accounts and calendars are theirs.
- Ask which kinds of events they want. Default: everything.

### 1. Email (`scan_mail.py` → classify → `build_events.py`)

- `python3 scripts/scan_mail.py` writes `data/candidates.jsonl` plus each body under `data/emails/`. It looks in `~/Library/Mail/V10`; on other macOS versions the folder may be `V9` or `V11`, so check and adjust `MAIL`.
- Classify the candidates. Either run `scripts/classify.py` (needs `OPENROUTER_API_KEY`; costs well under a dollar for ~700 emails) or read `candidates.jsonl` yourself and write `data/classified.jsonl` in the format described in that script's prompt.
- `python3 scripts/build_events.py` merges emails about the same event, attaches the best receipt, and tags people named in transfers and forwards.
- Check afterwards: is all their mail actually downloaded? Compare local message counts per mailbox with the server counts in the Envelope Index. Tell them how far back the mail really goes.

### 2. A list they already keep (optional)

If they track shows on concertarchives.org, setlist.fm or a spreadsheet, turn it into `data/concertarchives.json` (format in `scripts/import_concertarchives.py`) and run that script. These are their own record, so they import as confirmed.

### 3. Photos (`match_photos.py`, `discover_photos.py`)

- `match_photos.py` geocodes each event's venue and attaches photos taken that night within 500 m, plus the people Photos recognizes in them.
- `discover_photos.py --dry` lists days whose photos Apple tagged as a named public event or a stage/performance scene. Review the list with the owner in mind, then run it without `--dry`.
- With "Optimize Mac Storage" on, originals aren't local; the scripts fall back to preview and thumbnail copies.

### 4. Calendar (`scan_calendar.py` → picks → `import_calendar.py`)

- Run `scan_calendar.py` once with no calendars set; it prints the calendar names on this Mac. Put the owner's in `settings.json` (`personal` are scanned fully, `work` only for evenings and weekends, `shared_with` maps a shared calendar to the person to tag).
- Run it again to get `data/calendar_items.jsonl`. Private entries (medical, legal, school admin) are filtered out before anything else sees them.
- Pick the real events. Read the items yourself, or run `classify_calendar.py` with an OpenRouter key. Write `data/calendar_picks.json`, then `python3 scripts/import_calendar.py`. Run `match_photos.py` again afterwards.

### 5. Hand over

- Tell the owner the counts by source and kind, how far back each source went, and what is guesswork.
- Show them the review filter and the "✓ I was there" / "Not an event / didn't go" buttons.
- Offer `bash launcher/make_app.sh` for the clickable icon.

## When the owner remembers a show you didn't find

Search in this order and stop when you have a date: email subjects, then decoded email bodies, then the Photos search index, then the calendar. If none names it, look up the performer's tour dates in the owner's city and check which of those dates has photos taken at that venue. Confirm with the photo itself (a marquee, the stage) before adding.

## Things that went wrong the first time

- People named in ticket emails are sometimes organizers or colleagues, not companions. When unsure, leave them off.
- Photos' event names are guesses and its strings carry a trailing NUL (`\x00`); strip it.
- A person's own gigs, movies, parties and TV sports nights all look like events in a calendar. Leave them out unless the owner says otherwise.
- Kids' performances show up three times (school email, calendar, photos). Merge by day.
- In the UI, the attendee field uses a custom autocomplete (a native `datalist` only matches the first name in a comma list) and receipts load into a sandboxed iframe via `srcdoc` (plain frame navigation was blocked). Don't "simplify" either back.
