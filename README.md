# Event Archive

A private, searchable scrapbook of every concert, game, play and show you've been to. It runs entirely on your own Mac.

Each event gets a ticket stub (a photo of the real one, or the email receipt), the photos you took that night, and the people you went with. You can add events by hand, and an AI assistant can dig the rest out of your email, calendar and photo library.

## What you need

- A Mac.
- [uv](https://docs.astral.sh/uv/) to run it (`brew install uv`).
- Optional, for the automatic scan: an AI coding assistant such as Claude Code, and your mail, calendar and photos synced to this Mac (Apple Mail, Calendar and Photos).

## Start it

```bash
uv run app/server.py
```

Then open <http://localhost:5177>. It starts empty; use **+ Add event** to add your first one.

To get an icon you can click instead:

```bash
bash launcher/make_app.sh
```

That puts **Event Archive** in `~/Applications`. Clicking it starts the server if needed and opens the page. Run it again if you move this folder.

## Fill it automatically

Open this folder in your AI assistant and say:

> Build my event archive. Follow AGENTS.md.

It will ask you a few questions (your name, who you usually go with, which calendars are yours), then scan your Mac and load what it finds. Expect a few rounds of "that's not right, fix it"; the app has buttons for confirming or dismissing each find.

## Privacy

- Everything lives in the `data/` folder inside this project and is never uploaded or shared. Back that folder up if you care about it.
- The scanners only read your Mail, Calendar and Photos. They never change, send or delete anything.
- Two things can leave your Mac, both optional: venue names (not yours) are looked up on OpenStreetMap to match photos by location, and if you set an OpenRouter key, email text is sent to a cheap AI model for sorting. Without a key your own assistant does the sorting.
- Nothing is ever deleted. Dismissing an event hides it.

## What's in here

| Folder | What it is |
|---|---|
| `app/` | The web app (a small local server and one page) |
| `scripts/` | Scanners for Mail, Calendar and Photos, and importers |
| `launcher/` | Builds the clickable app and its icon |
| `data/` | Your archive: database, photos, receipts, settings. Private; created on first run |
| `AGENTS.md` | Instructions for your AI assistant |
