import asyncio
import hashlib
import logging
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
from report import render_reports, EDITABLE_COLUMNS, DB_PATH, parse_due_date, format_date

load_dotenv()

def _format_lab_type(val):
    """Render Lab.type (0 = lab, 1 = imaging) as "lab" or "im"; empty for None,
    other values pass through unchanged."""
    if val is None:
        return ""
    return {"0": "lab", "1": "im"}.get(str(val), str(val))


def _format_encounter_type(val):
    """Render Lab.encounter_type (1 = current, 5 = virtual) as ("C", "Current")
    or ("V", "Virtual"), the second element being the tooltip text; ("", None)
    for None, other values pass through unchanged."""
    if val is None:
        return "", None
    return {"1": ("C", "Current"), "5": ("V", "Virtual")}.get(str(val), (str(val), None))


def _format_from_lab(val):
    """Render Lab.from_lab_id as the lab source name; empty for None, other
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
# combined coll_date + coll_time. "Patient" shows patientname, "O" is the
# encounter type (encounter_type), "!" is the priority flag, "lab" is the
# lab source (from_lab_id) and "status" is the interface_status.
LAB_COLUMNS = [
    "id", "itemid", "encounter_id", "Patient", "name", "O", "!", "date", "collected",
    "result_date", "lab", "status", "result", "type",
]

app = Quart(__name__)
app.secret_key = os.environ["SECRET_KEY"]

# Uvicorn's access log always shows the proxy (127.0.0.1) because it logs the
# TCP peer. Log the real client instead: nginx must send X-Forwarded-For and
# uvicorn (proxy-headers on by default, trusting 127.0.0.1/::1) rewrites
# scope["client"] to the real client IP from that header.
_client_log = logging.getLogger("client.access")
if not _client_log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
    )
    _client_log.addHandler(_handler)
    _client_log.propagate = False


@app.after_request
async def log_client_ip(response):
    client = request.scope.get("client")
    ip = client[0] if client else "?"
    _client_log.info(
        '%s - "%s %s" %s', ip, request.method, request.path, response.status
    )
    return response


# Keep JSON object keys in insertion order (the /api/encounter rows list the
# table columns in display order).
app.json.sort_keys = False

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
            '<li><a href="/encounter">Encounter</a></li>'
            '<li><a href="/lab">Lab</a></li>'
            '<li><a href="/upload">Upload</a></li>'
            '<li><a href="/payclaim">PayClaim</a></li>'
            '<li><a href="/payment">Payment</a></li>'
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
        cur = await conn.execute("SELECT * FROM Lab ORDER BY result_date DESC")
        rows = await cur.fetchall()

    header = "".join(f"<th>{html.escape(c)}</th>" for c in LAB_COLUMNS)
    body_rows = []
    for row in rows:
        # Unreviewed labs (status 0) render bold. NULL status is legacy
        # (pre-status rows, all scraped from the Reviewed tab) and not bolded.
        tr_cls = ' class="unreviewed"' if row["status"] == 0 and row["from_lab_id"] != 0 else ""
        tds = []
        for col in LAB_COLUMNS:
            if col == "collected":
                # Raw parts only (ISO coll_date + coll_time); lab.html formats
                # them as "m/d/yy h:MM am" for display.
                parts = [str(v) for v in (row["coll_date"], row["coll_time"]) if v not in (None, "")]
                tds.append(f"<td>{html.escape(' '.join(parts))}</td>")
                continue
            if col == "type":
                tds.append(f"<td>{html.escape(_format_lab_type(row[col]))}</td>")
                continue
            if col == "O":
                text, tip = _format_encounter_type(row["encounter_type"])
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
                tds.append(f"<td>{html.escape(_format_from_lab(row['from_lab_id']))}</td>")
                continue
            if col == "status":
                text = "" if row["interface_status"] is None else str(row["interface_status"])
                tds.append(f"<td>{html.escape(text)}</td>")
                continue
            val = row[col]
            if col == "result" and val:
                # Non-empty result: link that pops up the result details
                lab_id = html.escape(str(row["id"]), quote=True)
                lab_name = html.escape(str(row["name"] or ""), quote=True)
                tds.append(f'<td><a class="result-link" data-lab="{lab_id}" data-name="{lab_name}">view</a></td>')
                continue
            # date / result_date travel as the raw stored ISO (yyyy-mm-dd);
            # lab.html formats them as m/d/yy for display.
            text = "" if val is None else str(val)
            tds.append(f"<td>{html.escape(text)}</td>")
        body_rows.append(f"      <tr{tr_cls}>" + "".join(tds) + "</tr>")
    return await render_template("lab.html", header=header, body="\n".join(body_rows))


# Columns of the PayClaim table shown on /payclaim, in display order.
PAYCLAIM_COLUMNS = [
    "payment", "postedDate", "date", "claim", "encounter", "mrn",
    "payorName", "payorType", "paid", "allowed", "adjustment", "deduct",
    "paymentType", "paymentDetail", "ERADetail", "MsgCode",
    "postedBy", "created", "name", "payorId",
]

# The most recent payment rows the /payclaim page shows (server-side limit).
PAYCLAIM_LIMIT = 500


@app.route("/payclaim")
async def payclaim_page():
    """The most recent PayClaim rows, newest first, capped at PAYCLAIM_LIMIT.
    The limit is enforced in the SQL query so the page can never serve more."""
    if not session.get("logged_in"):
        return redirect("/login")

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM PayClaim ORDER BY payment DESC LIMIT ?", (PAYCLAIM_LIMIT,)
        )
        rows = await cur.fetchall()

    body_rows = []
    for row in rows:
        tds = []
        for col in PAYCLAIM_COLUMNS:
            val = row[col]
            text = "" if val is None else str(val)
            tds.append(f"<td>{html.escape(text)}</td>")
        body_rows.append("      <tr>" + "".join(tds) + "</tr>")

    header = "".join(f"<th>{html.escape(c)}</th>" for c in PAYCLAIM_COLUMNS)
    return await render_template("payclaim.html", header=header, body="\n".join(body_rows))


# Columns of the Pay table shown on /payment, in display order.
PAY_COLUMNS = [
    "payment", "postedDate", "paid", "payorId", "payorName", "payorType",
    "postedBy", "ERADetail", "paymentType", "deleted", "created",
]

# Columns rendered right-aligned as numbers (also sent to the client so its
# table can right-align the same columns).
PAY_NUMERIC_COLUMNS = ("paid",)

# ORDER BY expressions for server-side sorting on /api/payment. paid is
# stored as NUMERIC with mixed integer/real values, so it must be cast to
# sort numerically; every other column sorts as-is (dates are ISO text,
# so text order == chronological order).
PAYMENT_ORDER_BY = {"paid": "CAST(paid AS REAL)"}

# Order used when the client sends no valid sort: newest first.
PAYMENT_DEFAULT_ORDER = "payment DESC"

# The /payment client requests this many rows per page...
PAYMENT_PAGE_LENGTH = 100
# ...and the API never serves more than this per request (DataTables treats
# a negative length as "all rows", which must not stream the whole table).
PAYMENT_MAX_PAGE_LENGTH = 1000

# The most common paid amounts offered in the /payment filter dropdown.
PAYMENT_PAID_VALUES_LIMIT = 50


@app.route("/payment")
async def payment_page():
    """The Pay table. Rows are fetched by DataTables from /api/payment,
    which does the sorting, paging and the paid-equals filter server-side."""
    if not session.get("logged_in"):
        return redirect("/login")

    # Most common paid amounts, for the filter's datalist.
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT paid FROM Pay WHERE paid IS NOT NULL GROUP BY paid "
            "ORDER BY COUNT(*) DESC LIMIT ?", (PAYMENT_PAID_VALUES_LIMIT,)
        )
        paid_values = [str(v) for (v,) in await cur.fetchall()]

    header = "".join(f"<th>{html.escape(c)}</th>" for c in PAY_COLUMNS)
    return await render_template(
        "payment.html", header=header,
        columns=PAY_COLUMNS, numeric=PAY_NUMERIC_COLUMNS,
        paid_values=paid_values,
    )


@app.route("/api/payment")
async def api_payment():
    """Server-side DataTables endpoint for /payment.

    Like /api/encounter, plus an optional paid= query param: when set, only
    rows whose paid amount numerically equals it are served and counted
    (the cast means stored integer 20 and real 20.0 both match). Unparseable
    values are ignored and the table is served unfiltered.
    """
    if not session.get("logged_in"):
        return "unauthorized", 401

    where, where_args = None, ()
    paid = (request.args.get("paid") or "").strip()
    if paid:
        try:
            where = "CAST(paid AS REAL) = ?"
            where_args = (float(paid),)
        except ValueError:
            # Unparseable: clear both, so a half-set where clause can never
            # reach the query with missing bindings.
            where, where_args = None, ()

    return jsonify(await _data_table_payload(
        "Pay", PAY_COLUMNS,
        page_length=PAYMENT_PAGE_LENGTH,
        max_page_length=PAYMENT_MAX_PAGE_LENGTH,
        order_by=PAYMENT_ORDER_BY,
        default_order=PAYMENT_DEFAULT_ORDER,
        where=where,
        where_args=where_args,
    ))


# Columns of the Encounter table shown on /encounter, in display order.
ENCOUNTER_COLUMNS = [
    "encounter", "claim", "date", "mrn", "type", "reason", "dr",
    "visittype", "billed", "paid", "balance", "due_date",
    "assignee", "task", "notes",
]

# UI labels for the columns (defaults to the column name).
ENCOUNTER_COLUMN_LABELS = {"due_date": "due"}

# Columns rendered right-aligned as numbers (also sent to the client so its
# table can right-align the same columns).
ENCOUNTER_NUMERIC_COLUMNS = ("billed", "paid", "balance")

# ORDER BY expressions for server-side sorting. The amount columns are stored
# as text, so they must be cast to sort numerically; every other column sorts
# as-is (dates are ISO text, so text order == chronological order).
ENCOUNTER_ORDER_BY = {
    "billed": "CAST(billed AS REAL)",
    "paid": "CAST(paid AS REAL)",
    "balance": "CAST(balance AS REAL)",
}

# Order used when the client sends no valid sort: newest first.
ENCOUNTER_DEFAULT_ORDER = "date DESC, encounter DESC"

# The /encounter client requests this many rows per page...
ENCOUNTER_PAGE_LENGTH = 100
# ...and the API never serves more than this per request (DataTables treats
# a negative length as "all rows", which must not stream the whole table).
ENCOUNTER_MAX_PAGE_LENGTH = 1000


# --- Shared server-side DataTables plumbing ------------------------------
# /api/encounter and /api/payment speak the same protocol: the client sends
# draw, start, length and order[i][column]/order[i][dir]; the response is
# {draw, recordsTotal, recordsFiltered, data}. Column indexes are resolved
# through a per-table column whitelist, so only whitelisted ORDER BY
# expressions ever reach the SQL.


def _data_table_order_sql(columns, order_by, default_order):
    """Resolve the client's order[i][column]/order[i][dir] params into a list
    of ORDER BY expressions; falls back to default_order when no valid sort
    is sent."""
    order_sql = []
    i = 0
    while True:
        col = request.args.get(f"order[{i}][column]")
        if col is None:
            break
        direction = (request.args.get(f"order[{i}][dir]") or "").lower()
        try:
            name = columns[int(col)]
        except (ValueError, IndexError):
            name = None
        if name is not None and direction in ("asc", "desc"):
            order_sql.append(f"{order_by.get(name, name)} {direction.upper()}")
        i += 1
    return order_sql or [default_order]


def _plain_cell(row, col):
    """Display text for a plain cell: None renders as the empty string."""
    val = row[col]
    return "" if val is None else str(val)


async def _data_table_payload(
    table, columns, *, page_length, max_page_length, order_by=None,
    default_order, cell=None, where=None, where_args=(),
):
    """Run the shared server-side DataTables query for one table and return
    the {draw, recordsTotal, recordsFiltered, data} response dict.

    table, the columns/order_by whitelists and where come from module-level
    constants built by the caller; client input only affects pagination,
    whitelisted sort order and the caller-validated where clause. With no
    where clause recordsFiltered equals recordsTotal.
    """
    cell = cell or _plain_cell
    try:
        draw = int(request.args.get("draw", 0))
    except ValueError:
        draw = 0
    try:
        start = max(int(request.args.get("start", 0)), 0)
    except ValueError:
        start = 0
    try:
        length = int(request.args.get("length", page_length))
    except ValueError:
        length = page_length
    # A negative length means "all rows" to DataTables; cap it so one
    # request can never stream the whole table.
    if length < 0:
        length = max_page_length
    length = min(length, max_page_length)

    order_sql = _data_table_order_sql(columns, order_by or {}, default_order)
    where_sql = f" WHERE {where}" if where else ""

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(f"SELECT COUNT(*) FROM {table}")
        total = (await cur.fetchone())[0]
        filtered = total
        if where:
            cur = await conn.execute(
                f"SELECT COUNT(*) FROM {table}{where_sql}", where_args
            )
            filtered = (await cur.fetchone())[0]
        cur = await conn.execute(
            f"SELECT * FROM {table}{where_sql} "
            f"ORDER BY {', '.join(order_sql)} LIMIT ? OFFSET ?",
            (*where_args, length, start),
        )
        rows = await cur.fetchall()

    # Cells travel as display text; the client shows them as-is (sorting is
    # done server-side, so no client-side render hooks are needed).
    return {
        "draw": draw,
        "recordsTotal": total,
        "recordsFiltered": filtered,
        "data": [{col: cell(row, col) for col in columns} for row in rows],
    }


def _encounter_cell(row, col):
    """Display text for one Encounter cell. date shows m/d; due_date shows
    mm/dd (matching /report); None renders as the empty string."""
    val = row[col]
    if col in ("billed", "paid", "balance") and isinstance(val, (int, float)):
        return f"{val:.2f}"
    if col in ("date", "due_date"):
        return format_date(val, padded=(col == "due_date"))
    return "" if val is None else str(val)


@app.route("/encounter")
async def encounter_page():
    """The Encounter table. Rows are fetched by DataTables from /api/encounter,
    which does the sorting and paging server-side."""
    if not session.get("logged_in"):
        return redirect("/login")

    header = "".join(
        f"<th>{html.escape(ENCOUNTER_COLUMN_LABELS.get(c, c))}</th>"
        for c in ENCOUNTER_COLUMNS
    )
    return await render_template(
        "encounter.html", header=header,
        columns=ENCOUNTER_COLUMNS, numeric=ENCOUNTER_NUMERIC_COLUMNS,
    )


@app.route("/api/encounter")
async def api_encounter():
    """Server-side DataTables endpoint for /encounter.

    The client sends draw, start, length and order[i][column]/order[i][dir];
    the response is {draw, recordsTotal, recordsFiltered, data}. There is no
    search, so recordsFiltered always equals recordsTotal.
    """
    if not session.get("logged_in"):
        return "unauthorized", 401

    return jsonify(await _data_table_payload(
        "Encounter", ENCOUNTER_COLUMNS,
        page_length=ENCOUNTER_PAGE_LENGTH,
        max_page_length=ENCOUNTER_MAX_PAGE_LENGTH,
        order_by=ENCOUNTER_ORDER_BY,
        default_order=ENCOUNTER_DEFAULT_ORDER,
        cell=_encounter_cell,
    ))


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
                "SELECT hash, salt FROM users WHERE name = ?", (name,)
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
