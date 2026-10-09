import asyncio
import hashlib
import hmac
import html
import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import aiosqlite
from dotenv import load_dotenv
from quart import Quart, abort, request, Response, jsonify, redirect, render_template, session, websocket
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

from werkzeug.utils import secure_filename

from claim_info import claim_info
from models import Message
from report import render_reports, EDITABLE_COLUMNS, DB_PATH, parse_due_date

load_dotenv()

def _format_lab_type(val):
    """Render Lab.type (0 = lab, 1 = imaging) as "lab" or "im"; empty for None,
    other values pass through unchanged."""
    if val is None:
        return ""
    return {"0": "lab", "1": "im"}.get(str(val), str(val))


def _format_encounter_type(val):
    """Render Lab.encounterType (1 = current, 5 = virtual) as ("C", "Current")
    or ("V", "Virtual"), the second element being the tooltip text; ("", None)
    for None, other values pass through unchanged."""
    if val is None:
        return "", None
    return {"1": ("C", "Current"), "5": ("V", "Virtual")}.get(str(val), (str(val), None))


def _format_from_lab(val):
    """Render Lab.fromLabId as the lab source name; empty for None, other
    values pass through unchanged."""
    if val is None:
        return ""
    return {"1": "Quest", "2": "SimonMed", "3": "LabCorp"}.get(str(val), str(val))


def _format_priority(val):
    """Render Lab.priority as "!" for 1, blank for 0/None, other values pass
    through unchanged."""
    if val is None or val == "0":
        return ""
    return "!" if val == "1" else str(val)


# All columns of the Lab table, in display order. "collected" is the
# combined collDate + collTime. "Patient" shows patientname, "O" is the
# encounter type (encounterType), "!" is the priority flag, "lab" is the
# lab source (fromLabId) and "status" is the InterfaceStatus.
LAB_COLUMNS = [
    "id", "itemid", "encounterId", "Patient", "name", "O", "!", "date", "collected",
    "ResultDate", "lab", "status", "result", "type",
]

app = Quart(__name__)
app.secret_key = os.environ["SECRET_KEY"]

db_path = f"sqlite+aiosqlite:///{DB_PATH}"
engine = create_async_engine(db_path, echo=True, future=True)
async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

PBKDF2_ITERATIONS = 100_000
UPLOAD_DIR = Path("/srv/allen/uploads")

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
validator = RequestValidator(TWILIO_AUTH_TOKEN) if TWILIO_AUTH_TOKEN else None

# --- Live "who's online" tracker for the /report page -----------------
# One entry per open tab, so a user with the page open in several tabs
# appears that many times ("Online: alice, alice, bob").
# State is in memory only, so the app must run with a single worker.
# Cell edit updates are broadcast on this same websocket as JSON.
REPORT_VIEWERS: list[str] = []  # username per open tab
REPORT_WEBSOCKETS: set = set()  # live websockets viewing /report


async def _broadcast_report(message: str):
    """Send a message to every connected /report viewer."""
    for ws in list(REPORT_WEBSOCKETS):
        try:
            await ws.send(message)
        except Exception:
            pass  # connection may have just dropped


async def _broadcast_report_online():
    """Send the current online list to every connected /report viewer."""
    await _broadcast_report(
        json.dumps({"type": "online", "viewers": list(REPORT_VIEWERS)})
    )


@app.websocket("/ws/report")
async def ws_report():
    """Track who has the /report page open; the client opens one connection per tab."""
    if not session.get("logged_in"):
        await websocket.close(code=1008, reason="unauthorized")
        return

    username = session.get("user", "unknown")
    current_ws = websocket._get_current_object()
    REPORT_WEBSOCKETS.add(current_ws)
    REPORT_VIEWERS.append(username)
    await _broadcast_report_online()

    try:
        # No data is expected from the client for now; later this loop
        # will also carry cell presence and edit update messages.
        while True:
            await websocket.receive()
    finally:
        # Client disconnected (tab closed, page left, or server shutting down)
        REPORT_WEBSOCKETS.discard(current_ws)
        if username in REPORT_VIEWERS:
            REPORT_VIEWERS.remove(username)
        await _broadcast_report_online()


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS).hex()


@app.route("/")
async def index():
    if not session.get("logged_in"):
        return redirect("/login")
    return ('<div style="padding-top: 20px; padding-left: 20px"><ul>'
            '<li><a href="/report">Report</a></li>'
            '<li><a href="/lab">Lab</a></li>'
            '<li><a href="/upload">Upload</a></li>'
            '<li><a href="/messages">Messages</a></li>'
            '</ul></div>')


@app.route("/report")
async def report():
    if not session.get("logged_in"):
        return redirect("/login")

    cutoff = None
    try:
        months = int(request.args.get("months"))
    except (TypeError, ValueError):
        months = 3
    if months:
        cutoff = (date.today() - timedelta(days=months * 30)).isoformat()
    header, body = await render_reports(months, cutoff)
    return await render_template("report.html", header=header, body=body)


@app.route("/lab")
async def lab():
    if not session.get("logged_in"):
        return redirect("/login")

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM Lab ORDER BY ResultDate DESC")
        rows = await cur.fetchall()

    header = "".join(f"<th>{html.escape(c)}</th>" for c in LAB_COLUMNS)
    body_rows = []
    for row in rows:
        # Unreviewed labs (status 0) render bold. NULL status is legacy
        # (pre-status rows, all scraped from the Reviewed tab) and not bolded.
        tr_cls = ' class="unreviewed"' if row["status"] == 0 and row["fromLabId"] != 0 else ""
        tds = []
        for col in LAB_COLUMNS:
            if col == "collected":
                # Raw parts only (ISO collDate + collTime); lab.html formats
                # them as "m/d/yy h:MM am" for display.
                parts = [str(v) for v in (row["collDate"], row["collTime"]) if v not in (None, "")]
                tds.append(f"<td>{html.escape(' '.join(parts))}</td>")
                continue
            if col == "type":
                tds.append(f"<td>{html.escape(_format_lab_type(row[col]))}</td>")
                continue
            if col == "O":
                text, tip = _format_encounter_type(row["encounterType"])
                title = f' title="{html.escape(tip)}"' if tip else ""
                tds.append(f"<td{title}>{html.escape(text)}</td>")
                continue
            if col == "!":
                tds.append(f"<td>{html.escape(_format_priority(row['priority']))}</td>")
                continue
            if col == "Patient":
                tds.append(f"<td>{html.escape(row['patientname'] or '')}</td>")
                continue
            if col == "lab":
                tds.append(f"<td>{html.escape(_format_from_lab(row['fromLabId']))}</td>")
                continue
            if col == "status":
                text = "" if row["InterfaceStatus"] is None else str(row["InterfaceStatus"])
                tds.append(f"<td>{html.escape(text)}</td>")
                continue
            val = row[col]
            if col == "result" and val:
                # Non-empty result: link that pops up the result details
                lab_id = html.escape(str(row["id"]), quote=True)
                lab_name = html.escape(str(row["name"] or ""), quote=True)
                tds.append(f'<td><a class="result-link" data-lab="{lab_id}" data-name="{lab_name}">view</a></td>')
                continue
            # date / ResultDate travel as the raw stored ISO (yyyy-mm-dd);
            # lab.html formats them as m/d/yy for display.
            text = "" if val is None else str(val)
            tds.append(f"<td>{html.escape(text)}</td>")
        body_rows.append(f"      <tr{tr_cls}>" + "".join(tds) + "</tr>")
    return await render_template("lab.html", header=header, body="\n".join(body_rows))


# Columns of the Message table shown on /messages, in display order.
MESSAGE_COLUMNS = [
    "created_at", "from_number", "body",
]

# UI labels for the columns (defaults to the column name).
MESSAGE_COLUMN_LABELS = {"body": "message"}

PACIFIC = ZoneInfo("America/Los_Angeles")


def to_pacific(val):
    """Convert a UTC datetime (stored value) to Pacific Time; naive values are
    assumed to be UTC."""
    if val is None:
        return None
    if val.tzinfo is None:
        val = val.replace(tzinfo=timezone.utc)
    return val.astimezone(PACIFIC)


def format_phone(num):
    """Format a phone number for display: strip "+1" and dash the digits
    (e.g. "+16106182100" -> "610-618-2100")."""
    if not num:
        return ""
    digits = re.sub(r"\D", "", num)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return num


@app.route("/messages")
async def messages_page():
    """All Twilio webhook messages, newest first."""
    if not session.get("logged_in"):
        return redirect("/login")

    async with async_session() as db:
        rows = (await db.exec(select(Message).order_by(Message.created_at.desc()))).all()

    body_rows = []
    for m in rows:
        tds = []
        for col in MESSAGE_COLUMNS:
            if col == "created_at":
                val = to_pacific(getattr(m, col))
                if val is None:
                    text = ""
                else:
                    hour = val.hour % 12 or 12
                    text = f"{val.month}/{val.day} {hour}:{val.minute:02d} {'am' if val.hour < 12 else 'pm'}"
            else:
                val = getattr(m, col)
                if val is None:
                    text = ""
                elif col.endswith("_number"):
                    text = format_phone(val)
                else:
                    text = str(val)
            tds.append(f"<td>{html.escape(text)}</td>")
        body_rows.append("      <tr>" + "".join(tds) + "</tr>")

    header = "".join(f"<th>{html.escape(MESSAGE_COLUMN_LABELS.get(c, c))}</th>" for c in MESSAGE_COLUMNS)
    return await render_template("messages.html", header=header, body="\n".join(body_rows))


@app.route("/upload")
async def upload_page():
    if not session.get("logged_in"):
        return redirect("/login")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return await render_template("upload.html")


@app.route("/upload", methods=["POST"])
async def upload_files():
    """Save the files from a multipart upload (form field "files") to UPLOAD_DIR."""
    if not session.get("logged_in"):
        return "unauthorized", 401
    files = (await request.files).getlist("files")
    if not files:
        return "no files", 400
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        name = secure_filename(f.filename)
        if not name:
            return "bad filename", 400
        # Never clobber an existing file: insert a counter before the suffix.
        if (UPLOAD_DIR / name).exists():
            stem, dot, suffix = name.rpartition(".")
            if not dot:
                stem, suffix = name, ""
            i = 1
            while (UPLOAD_DIR / f"{stem}-{i}.{suffix}" if suffix else UPLOAD_DIR / f"{stem}-{i}").exists():
                i += 1
            name = f"{stem}-{i}.{suffix}" if suffix else f"{stem}-{i}"
        await f.save(str(UPLOAD_DIR / name))
        saved.append(name)
    return jsonify({"ok": True, "files": saved})


@app.route("/api/uploads")
async def api_uploads():
    """List the files stored in UPLOAD_DIR, newest first."""
    if not session.get("logged_in"):
        return "unauthorized", 401
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for p in UPLOAD_DIR.iterdir():
        if not p.is_file():
            continue
        st = p.stat()
        files.append({
            "name": p.name,
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        })
    files.sort(key=lambda f: f["mtime"], reverse=True)
    return jsonify(files)


@app.route("/login", methods=["GET", "POST"])
async def login():
    if request.method == "POST":
        form = await request.form
        name = form.get("name", "")
        password = form.get("pass", "")
        async with aiosqlite.connect(DB_PATH) as conn:
            row = await conn.execute_fetchall(
                "SELECT hash, salt FROM user WHERE name = ?", (name,)
            )
        if row:
            stored_hash, salt = row[0]
            if hmac.compare_digest(_hash_password(password, salt), stored_hash):
                session["logged_in"] = True
                session["user"] = name
                return redirect("/report")
        return await render_template("login.html", error="invalid username or password"), 401
    return await render_template("login.html")


@app.route("/logout")
async def logout():
    session.pop("logged_in", None)
    return "logged out"


@app.route("/api/update", methods=["POST"])
async def api_update():
    """Autosave one editable field back to the Report and Encounter tables."""
    if not session.get("logged_in"):
        return "unauthorized", 401
    data = await request.get_json(silent=True) or {}
    field = data.get("field")
    value = data.get("value")
    enc = data.get("encounter")
    if field not in EDITABLE_COLUMNS or not isinstance(value, str):
        return "bad request", 400
    try:
        enc = int(enc)
    except (TypeError, ValueError):
        return "bad request", 400

    save_value = value
    if field == "due_date" and value.strip():
        # Stored as yyyy-mm-dd; the client sends that raw ISO as the value.
        # Invalid dates are rejected and never saved.
        try:
            save_value = parse_due_date(value)
        except ValueError:
            return "invalid due_date", 400

    async with aiosqlite.connect(DB_PATH) as conn:
        # field comes from the EDITABLE_COLUMNS whitelist, safe to interpolate
        await conn.execute(f"UPDATE Report SET {field} = ? WHERE encounter = ?", (save_value, enc))
        await conn.execute(f"UPDATE Encounter SET {field} = ? WHERE encounter = ?", (save_value, enc))
        await conn.commit()

    # Push the new cell value to every connected /report tab so their
    # tables stay in sync without a page refresh. due_date values travel
    # as the raw ISO; clients convert to their mm/dd display themselves.
    payload = {"type": "cell_update", "encounter": enc, "field": field, "value": value}
    await _broadcast_report(json.dumps(payload))
    return {"ok": True}


@app.route("/api/claim_info")
async def api_claim_info():
    """Phone details for one claim number (claim_info.py), for the report page's bottom pane."""
    if not session.get("logged_in"):
        return "unauthorized", 401
    try:
        claim = int(request.args.get("claim", ""))
    except (TypeError, ValueError):
        return "bad request", 400

    def _fetch():
        con = sqlite3.connect(DB_PATH)
        try:
            return claim_info(con, str(claim))
        finally:
            con.close()

    info = await asyncio.to_thread(_fetch)
    if not info:
        return "no such claim", 404
    return jsonify(info)


@app.route("/api/lab_result")
async def api_lab_result():
    """Result details (Lab.result JSON) for one lab report id, for the /lab table."""
    if not session.get("logged_in"):
        return "unauthorized", 401
    lab_id = request.args.get("id", "")
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT result FROM Lab WHERE id = ?", (lab_id,))
        row = await cur.fetchone()
    if row is None or row[0] is None:
        return "no such lab", 404
    try:
        return jsonify(json.loads(row[0]))
    except (TypeError, json.JSONDecodeError):
        return "bad result data", 400


@app.route("/webhook", methods=["POST"])
async def twilio_webhook():
    if validator:
        twilio_signature = request.headers.get("X-Twilio-Signature", "")
        form_data = await request.form
        is_valid = validator.validate(
            request.url, 
            dict(form_data), 
            twilio_signature
        )
        if not is_valid:
            abort(403, description="Invalid Twilio signature.")

    form_data = await request.form
    data = dict(form_data)

    # Note: Inbound webhooks from Twilio sometimes omit DateCreated/DateUpdated 
    # depending on the webhook type. We can fallback to current UTC time if missing.
    now_str = datetime.now(timezone.utc).isoformat()
    if "DateCreated" not in data:
        data["DateCreated"] = now_str
    if "DateUpdated" not in data:
        data["DateUpdated"] = now_str

    try:
        message = Message.from_webhook(data)
    except Exception as e:
        print(e)
        abort(400, description=f"Invalid payload format: {e}")

    async with async_session() as session:
        session.add(message)
        await session.commit()

    response = MessagingResponse()
    # response.message("Thanks for your message! We'll be in touch.")
    return Response(str(response), mimetype="application/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
