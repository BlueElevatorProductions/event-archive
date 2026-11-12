# /// script
# requires-python = ">=3.11"
# dependencies = ["flask>=3"]
# ///
"""Event Archive — local web app.  Run:  uv run app/server.py"""
import sqlite3, time, uuid
from pathlib import Path
from flask import Flask, g, jsonify, request, send_from_directory, abort

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import connect, MEDIA, DB  # noqa: E402

FIELDS = ["date", "artist", "supporting", "venue", "city", "kind", "notes", "section", "price", "status"]

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("pragma foreign_keys=on")
    return g.db


@app.teardown_appcontext
def close(_):
    d = g.pop("db", None)
    if d:
        d.close()


def full(row):
    c = dict(row)
    c["people"] = [dict(r) for r in db().execute(
        "select p.id, p.name, cp.source from concert_people cp join people p on p.id=cp.person_id "
        "where cp.concert_id=? and cp.source!='removed' order by p.name", (c["id"],))]
    c["media"] = [dict(r) for r in db().execute(
        "select id, kind, path, caption from media where concert_id=? order by kind='stub' desc, id", (c["id"],))]
    return c


def set_people(cid, names):
    d = db()
    # The submitted list is the truth. Names taken off are kept as 'removed'
    # tombstones so the email/Photos importers don't add them back later.
    want = {n.strip() for n in names if n.strip()}
    have = {r["name"]: (r["id"], r["source"]) for r in d.execute(
        "select p.id, p.name, cp.source from concert_people cp join people p on p.id=cp.person_id "
        "where cp.concert_id=?", (cid,))}
    for n, (pid, src) in have.items():
        if n not in want and src != "removed":
            d.execute("update concert_people set source='removed' where concert_id=? and person_id=?", (cid, pid))
        elif n in want and src == "removed":
            d.execute("update concert_people set source='manual' where concert_id=? and person_id=?", (cid, pid))
    for n in want - set(have):
        d.execute("insert or ignore into people(name) values(?)", (n,))
        pid = d.execute("select id from people where name=?", (n,)).fetchone()[0]
        d.execute("insert or ignore into concert_people values(?,?, 'manual')", (cid, pid))


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/media/<path:p>")
def media(p):
    r = send_from_directory(MEDIA, p)
    if p.endswith(".html"):  # stored email receipts: never run their scripts
        r.headers["Content-Security-Policy"] = "sandbox; script-src 'none'; object-src 'none'"
    return r


@app.get("/api/concerts")
def list_concerts():
    rows = db().execute("select * from concerts order by date desc, id desc").fetchall()
    return jsonify([full(r) for r in rows])


@app.get("/api/people")
def list_people():
    return jsonify([r["name"] for r in db().execute("select name from people order by name")])


@app.post("/api/concerts")
def create():
    j = request.get_json()
    if not j.get("date") or not j.get("artist"):
        abort(400, "date and artist are required")
    cur = db().execute(
        f"insert into concerts({','.join(FIELDS)},source,created) values({','.join('?'*len(FIELDS))},'manual',?)",
        [j.get(f, "") or {"kind": "concert", "status": "confirmed"}.get(f, "") for f in FIELDS] + [time.time()])
    set_people(cur.lastrowid, j.get("people", []))
    db().commit()
    return jsonify(full(db().execute("select * from concerts where id=?", (cur.lastrowid,)).fetchone()))


@app.put("/api/concerts/<int:cid>")
def update(cid):
    j = request.get_json()
    sets = [f for f in FIELDS if f in j]
    if sets:
        db().execute(f"update concerts set {','.join(f+'=?' for f in sets)} where id=?", [j[f] for f in sets] + [cid])
    if "people" in j:
        set_people(cid, j["people"])
    db().commit()
    row = db().execute("select * from concerts where id=?", (cid,)).fetchone()
    return jsonify(full(row)) if row else abort(404)


@app.delete("/api/concerts/<int:cid>")
def delete(cid):
    # Soft rule of this workspace: never hard-delete. Hide instead.
    db().execute("update concerts set kind='archived' where id=?", (cid,))
    db().commit()
    return jsonify(ok=True)


@app.post("/api/concerts/<int:cid>/media")
def upload(cid):
    f = request.files.get("file")
    kind = request.form.get("kind", "stub")
    if not f or kind not in ("stub", "photo"):
        abort(400)
    ext = Path(f.filename or "").suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif", ".pdf"):
        abort(400, "unsupported file type")
    name = f"{cid}-{kind}-{uuid.uuid4().hex[:8]}{ext}"
    f.save(MEDIA / name)
    db().execute("insert into media(concert_id,kind,path,caption,created) values(?,?,?,?,?)",
                 (cid, kind, name, request.form.get("caption", ""), time.time()))
    db().commit()
    return jsonify(full(db().execute("select * from concerts where id=?", (cid,)).fetchone()))


@app.delete("/api/media/<int:mid>")
def unlink_media(mid):
    # Detaches from the concert; the file stays in data/media.
    db().execute("update media set concert_id=null where id=?", (mid,))
    db().commit()
    return jsonify(ok=True)


if __name__ == "__main__":
    connect().close()
    app.run(host="127.0.0.1", port=5177, debug=False)
