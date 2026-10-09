import asyncio
import hashlib
import logging
import hmac
import html
import json
import os
import re
import psycopg2
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from pathlib import Path

from dotenv import load_dotenv
from quart import Quart, abort, request, Response, jsonify, redirect, render_template, session, websocket
from sqlmodel import select, Session, create_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

from werkzeug.utils import secure_filename

from claim_info import claim_info
from config import DATABASE_URL, DATABASE_URL_ASYNC, PG_DSN
from db import upsert, update_lab_result, update_patient_note
from ecw_session import ESession
from lab_summary import build_lab_summary
from models import Message, Patient
from report import render_reports, EDITABLE_COLUMNS, parse_due_date, format_date
from ecw_client import Client

load_dotenv()

def _format_lab_type(val):
    """Render Lab.type (0 = lab, 1 = imaging) as "lab" or "im"; empty for None,
    other values pass through unchanged."""
    if val is None:
        return ""
    return {"0": "lab", "1": "im"}.get(str(val), str(val))


def _format_encounter_type(val) -> tuple[str, str | None]:
    """Render Lab.encounter_type (1 = current, 5 = virtual), and tooltip text.
    Other values pass through unchanged.
    The second element being the tooltip text."""
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
    if val is None or str(val) == "0":
        return ""
    return "!" if str(val) == "1" else str(val)


def _fmt_float(v: float) -> str:
    """Display a stored float the way the old SQLite db did: values that are
    integral render without a trailing .0 (SQLite stored those as INTEGER)."""
    s = f"{v:.10f}".rstrip("0").rstrip(".")
    return s if s else "0"


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

engine = create_async_engine(DATABASE_URL_ASYNC, echo=True)
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
            '<li><a href="/encounters">Encounter</a></li>'
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
        cutoff = date.today() - timedelta(days=months * 30)
    header, body = await render_reports(months, cutoff)
    return await render_template("report.html", header=header, body=body)


@app.route("/lab")
async def lab():
    """The lab table. Rows are fetched by DataTables from /api/lab, which
    does the filtering, sorting and paging server-side."""
    if not session.get("logged_in"):
        return redirect("/login")

    header = "".join(f"<th>{html.escape(c)}</th>" for c in LAB_COLUMNS)
    return await render_template("lab.html", header=header, columns=LAB_COLUMNS)


# Columns of the encounter table shown on /patient, in display order.
PATIENT_ENCOUNTER_COLUMNS = ["date", "type", "reason", "message", "refills"]


def _age_sex_suffix(dob, sex):
    """"43F"-style age/sex suffix for the patient heading: the current age
    from dob (birthday not yet reached this year doesn't count) followed by
    the sex initial (only f/m; other values are omitted). None when neither
    is known."""
    age = None
    if dob is not None:
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    sex_char = ""
    if sex and sex[0].lower() in ("f", "m"):
        sex_char = sex[0].upper()
    if age is None and not sex_char:
        return None
    return ("" if age is None else str(age)) + sex_char


def _fmt_dob(val):
    """date -> '12/26/82' (the /patient DOB line); None renders as None."""
    if val is None:
        return None
    return f"{val.month}/{val.day}/{val.year % 100:02d}"


def _patient_phones(pt):
    """The patient's phones for the contact line, home first, then the cell
    when it differs: up_phone is the stored home number; the cell comes from
    cell_phone, falling back to the (C) entry of gr_phone's combined string
    ('415-802-8663(C), 415-699-2623(H)'). [] when nothing is stored."""
    home = format_phone(pt.get("up_phone") or "")
    cell = format_phone(pt.get("cell_phone") or "")
    if not cell:
        for part in (pt.get("gr_phone") or "").split(","):
            part = part.strip()
            if part.upper().endswith("(C)"):
                cell = format_phone(part[:-3].strip())
                break
    phones = []
    for p in (home, cell):
        if p and p not in phones:  # dedupe: cell often equals home
            phones.append(p)
    return phones


def _patient_address(pt):
    """'969 Governors Bay Dr, Redwood City, CA 94065-2206': address and
    address2, then city, state, zipcode, joined with ', ' (empty parts are
    skipped). None when nothing is stored."""
    city_parts = [v for v in (pt.get("city"), pt.get("state"), pt.get("zipcode")) if v]
    parts = [pt.get("address"), pt.get("address2")]
    if city_parts:
        parts.append(", ".join(city_parts))
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None


def _sticky_age(val):
    """Relative age for the yellow sticky's yellow_updated (timestamptz):
    (text, pt_tooltip). text is a readable 'how long ago' ('7 hours ago',
    '1 day ago'; under a minute or a future value reads 'just now');
    pt_tooltip is the full PT timestamp for the hover tooltip. Both are None
    when yellow_updated is NULL (the note predates the stamp)."""
    if val is None:
        return None, None
    pt = to_pacific(val)
    now_pt = to_pacific(datetime.now(timezone.utc))
    secs = (now_pt - pt).total_seconds()
    if secs < 60:
        text = "just now"
    else:
        minutes = int(secs // 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        for n, unit in ((days, "day"), (hours, "hour"), (minutes, "minute")):
            if n >= 1:
                text = f"{n} {unit}{'s' if n != 1 else ''} ago"
                break
    hour = pt.hour % 12 or 12
    pt_tooltip = (f"{pt.year:04d}-{pt.month:02d}-{pt.day:02d} "
                  f"{hour}:{pt.minute:02d} {'am' if pt.hour < 12 else 'pm'} PT")
    return text, pt_tooltip


@app.route("/patient")
async def patient_page():
    """One patient (by MRN): name, the yellow sticky note, that patient's
    labs in the past 3 months, and their encounters (newest first)."""
    if not session.get("logged_in"):
        return redirect("/login")

    mrn = request.args.get("mrn", "").strip()
    if not mrn.isdigit():
        return "bad mrn", 400
    mrn = int(mrn)

    async with engine.connect() as conn:
        pt = (await conn.execute(
            sa_text("SELECT name, dob, sex, email, insurance, up_phone, "
                    "gr_phone, cell_phone, "
                    "address, address2, city, state, zipcode, "
                    "yellow_note, yellow_updated FROM patient "
                    "WHERE mrn = :mrn"),
            {"mrn": mrn},
        )).fetchone()
        pt = pt._mapping if pt else {}
        name = pt["name"]
        rows = (await conn.execute(
            sa_text("SELECT date, type, reason, message, refills FROM encounter "
                    "WHERE mrn = :mrn "
                    "ORDER BY date DESC NULLS LAST, id DESC"),
            {"mrn": mrn},
        )).fetchall()
        # The patient's labs in the past 3 months (order date; 30 days per
        # month, matching /report's months convention), newest result first
        # (matching /lab's default order).
        cutoff = date.today() - timedelta(days=3 * 30)
        lab_rows = (await conn.execute(
            sa_text("SELECT id, name, priority, date, coll_date, coll_time, result_date, "
                    "from_lab_id, status, result, type FROM lab "
                    "WHERE mrn = :mrn AND result_date >= :cutoff "
                    "ORDER BY result_date DESC NULLS LAST, id DESC"),
            {"mrn": mrn, "cutoff": cutoff},
        )).fetchall()

    body_rows = []
    for row in rows:
        row = row._mapping
        text, tip = _format_encounter_type(row["type"])
        title = f' title="{html.escape(tip)}"' if tip else ""
        tds = [
            f"<td>{html.escape(format_date(row['date']))}</td>",
            f"<td{title}>{html.escape(text)}</td>",
            f"<td>{html.escape(row['reason'] or '')}</td>",
            f"<td>{html.escape(row['message'] or '')}</td>",
            f"<td>{html.escape(row['refills'] or '')}</td>",
        ]
        body_rows.append("      <tr>" + "".join(tds) + "</tr>")

    lab_body_rows = []
    for row in lab_rows:
        row = row._mapping
        # collected = coll_date + coll_time, like /lab's "collected" column.
        collected = " ".join(
            fmt(v)
            for v, fmt in ((row["coll_date"], _fmt_lab_date),
                           (row["coll_time"], _fmt_lab_time))
            if v not in (None, "")
        )
        if row["result"] or row["result_date"]:
            result_cell = (
                f'<a class="result-link" data-lab="{row["id"]}" '
                f'data-name="{html.escape(row["name"] or str(row["id"]), quote=True)}">'
                f"view</a>"
            )
        else:
            result_cell = ""
        # Unreviewed labs render bold (keep in sync with
        # LAB_FILTERS["unreviewed"] in app.py): still outstanding
        # (status = 0) and from a lab source; a NULL from_lab_id counts as
        # unreviewed (COALESCE), matching the JS rule in lab.html.
        unreviewed = row["status"] == 0 and (
            row["from_lab_id"] is None or row["from_lab_id"] != 0)
        tr_tag = '<tr class="unreviewed">' if unreviewed else "<tr>"
        # Checkbox for the page's reviewed/unreviewed button (client-side
        # selection; data-unreviewed mirrors the bold-row rule above).
        check_cell = (
            f'<td class="check"><input type="checkbox" class="lab-check" '
            f'data-lab="{row["id"]}" data-unreviewed="{1 if unreviewed else 0}">'
            f"</td>"
        )
        tds = [
            check_cell,
            f"<td>{html.escape(row['name'] or '')}</td>",
            f"<td>{html.escape(_format_priority(row['priority']))}</td>",
            f"<td>{html.escape(_fmt_lab_date(row['date']) if row['date'] else '')}</td>",
            f"<td>{html.escape(collected)}</td>",
            f"<td>{html.escape(_fmt_lab_date(row['result_date']) if row['result_date'] else '')}</td>",
            f"<td>{html.escape(_format_from_lab(row['from_lab_id']))}</td>",
            f"<td>{result_cell}</td>",
            f"<td>{html.escape(_format_lab_type(row['type']))}</td>",
        ]
        lab_body_rows.append(f"      {tr_tag}" + "".join(tds) + "</tr>")

    # One-line summary of the recent labs, shown under the Labs heading
    # above the table. lab_rows are already in the newest-first order the
    # summary needs.
    lab_summary = build_lab_summary([
        {"name": row._mapping["name"], "result": row._mapping["result"],
         "result_date": row._mapping["result_date"],
         "date": row._mapping["date"]}
        for row in lab_rows
    ])

    # When the yellow sticky was last updated: readable age above the sticky,
    # full PT timestamp in the hover tooltip.
    sticky_updated, sticky_updated_tip = _sticky_age(pt.get("yellow_updated"))

    # Info block under the heading: DOB, phones (home, then cell when it
    # differs), email, insurance, address, and the MRN at the bottom.
    # Stored '' (not NULL) counts as missing, same as None.
    phones = _patient_phones(pt)
    info = []
    if pt.get("dob") is not None:
        info.append(f"DOB: {_fmt_dob(pt['dob'])}")
    info += [p for p in (
        phones + [pt.get("email") or None,
                  pt.get("insurance") or None,
                  _patient_address(pt)]
    ) if p]
    info.append(f"MRN: {mrn}")

    return await render_template(
        "patient.html", mrn=mrn, name=name,
        name_suffix=_age_sex_suffix(pt.get("dob"), pt.get("sex")),
        info=info,
        sticky=pt.get("yellow_note"),
        sticky_updated=sticky_updated, sticky_updated_tip=sticky_updated_tip,
        body="\n".join(body_rows),
        labs_body="\n".join(lab_body_rows), lab_summary=lab_summary,
    )


# Columns of the pay_claim table shown on /payclaim, in display order.
PAYCLAIM_COLUMNS = [
    "payment", "posted_date", "date", "claim", "encounter", "mrn",
    "payor_name", "payor_type", "paid", "allowed", "adjustment", "deduct",
    "payment_type", "payment_detail", "era_detail", "msg_code",
    "posted_by", "created", "name", "payor_id",
]

# The most recent payment rows the /payclaim page shows (server-side limit).
PAYCLAIM_LIMIT = 500


@app.route("/payclaim")
async def payclaim_page():
    """The most recent pay_claim rows, newest first, capped at PAYCLAIM_LIMIT.
    The limit is enforced in the SQL query so the page can never serve more."""
    if not session.get("logged_in"):
        return redirect("/login")

    async with engine.connect() as conn:
        rows = (await conn.execute(
            sa_text("SELECT * FROM pay_claim ORDER BY payment DESC NULLS LAST LIMIT :limit"),
            {"limit": PAYCLAIM_LIMIT},
        )).fetchall()

    body_rows = []
    for row in rows:
        row = row._mapping
        tds = []
        for col in PAYCLAIM_COLUMNS:
            val = row[col]
            # money columns are numeric: asyncpg returns Decimal
            if isinstance(val, Decimal):
                val = float(val)
            if col in ("paid", "allowed", "adjustment", "deduct") and isinstance(val, float):
                text_ = _fmt_float(val)
            elif col == "created":
                text_ = _fmt_datetime(val)
            else:
                text_ = "" if val is None else str(val)
            tds.append(f"<td>{html.escape(text_)}</td>")
        body_rows.append("      <tr>" + "".join(tds) + "</tr>")

    header = "".join(f"<th>{html.escape(c)}</th>" for c in PAYCLAIM_COLUMNS)
    return await render_template("payclaim.html", header=header, body="\n".join(body_rows))


# Columns of the pay table shown on /payment, in display order.
PAY_COLUMNS = [
    "payment", "posted_date", "paid", "payor_id", "payor_name", "payor_type",
    "posted_by", "era_detail", "payment_type", "deleted", "created",
]

# Columns rendered right-aligned as numbers (also sent to the client so its
# table can right-align the same columns).
PAY_NUMERIC_COLUMNS = ("paid",)

# ORDER BY expressions for server-side sorting on /api/payment. paid is
# stored as a float; every other column sorts as-is (date columns are native
# DATE, so they sort chronologically).
PAYMENT_ORDER_BY = {"paid": "paid"}

# Order used when the client sends no valid sort: newest first.
# NULLS LAST matches the old SQLite ordering (NULLs sort as smallest).
PAYMENT_DEFAULT_ORDER = "payment DESC NULLS LAST"

# The /payment client requests this many rows per page...
PAYMENT_PAGE_LENGTH = 100
# ...and the API never serves more than this per request (DataTables treats
# a negative length as "all rows", which must not stream the whole table).
PAYMENT_MAX_PAGE_LENGTH = 1000

# The most common paid amounts offered in the /payment filter dropdown.
PAYMENT_PAID_VALUES_LIMIT = 50


@app.route("/payment")
async def payment_page():
    """The pay table. Rows are fetched by DataTables from /api/payment,
    which does the sorting, paging and the paid-equals filter server-side."""
    if not session.get("logged_in"):
        return redirect("/login")

    # Most common paid amounts, for the filter's datalist.
    async with engine.connect() as conn:
        rows = (await conn.execute(
            sa_text("SELECT paid FROM pay WHERE paid IS NOT NULL GROUP BY paid "
                 "ORDER BY COUNT(*) DESC LIMIT :limit"),
            {"limit": PAYMENT_PAID_VALUES_LIMIT},
        )).fetchall()
        paid_values = [_fmt_float(v) for (v,) in rows]

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
    (paid is stored as a float, so 20 and 20.0 both match). Unparseable
    values are ignored and the table is served unfiltered.
    """
    if not session.get("logged_in"):
        return "unauthorized", 401

    where, where_args = None, {}
    paid = (request.args.get("paid") or "").strip()
    if paid:
        try:
            where = "paid = :paid"
            where_args = {"paid": float(paid)}
        except ValueError:
            # Unparseable: clear both, so a half-set where clause can never
            # reach the query with missing bindings.
            where, where_args = None, {}

    return jsonify(await _data_table_payload(
        "pay", PAY_COLUMNS,
        page_length=PAYMENT_PAGE_LENGTH,
        max_page_length=PAYMENT_MAX_PAGE_LENGTH,
        order_by=PAYMENT_ORDER_BY,
        default_order=PAYMENT_DEFAULT_ORDER,
        cell=_pay_cell,
        where=where,
        where_args=where_args,
    ))


# Columns of the encounter table shown on /encounters, in display order.
ENCOUNTER_COLUMNS = [
    "id", "claim", "date", "mrn", "type", "reason", "dr",
    "visittype", "billed", "paid", "balance", "due_date",
    "assignee", "task", "notes",
]

# UI labels for the columns (defaults to the column name).
ENCOUNTER_COLUMN_LABELS = {"id": "encounter", "due_date": "due"}

# Columns rendered right-aligned as numbers (also sent to the client so its
# table can right-align the same columns).
ENCOUNTER_NUMERIC_COLUMNS = ("billed", "paid", "balance")

# ORDER BY expressions for server-side sorting. The money columns are numeric
# and sort natively; every other column sorts as-is (date columns are native
# DATE, so they sort chronologically). No special mappings are needed.
ENCOUNTER_ORDER_BY = {}

# Order used when the client sends no valid sort: newest first.
ENCOUNTER_DEFAULT_ORDER = "date DESC, id DESC"

# The /encounters client requests this many rows per page...
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
            # SQLite sorts NULLs first in ASC and last in DESC; PostgreSQL
            # defaults to the opposite, so make it explicit.
            nulls = "NULLS FIRST" if direction == "asc" else "NULLS LAST"
            order_sql.append(f"{order_by.get(name, name)} {direction.upper()} {nulls}")
        i += 1
    return order_sql or [default_order]


def _plain_cell(row, col):
    """Display text for a plain cell: None renders as the empty string."""
    val = row[col]
    return "" if val is None else str(val)


def _fmt_datetime(val):
    """Display text for a created/updated timestamp column (timestamptz),
    matching the old stored text format. None renders as the empty string."""
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime('%Y-%m-%d %H:%M:%S')
    return str(val)


def _pay_cell(row, col):
    """Display text for one pay cell: paid floats render without a trailing
    .0 (matching the old SQLite integer storage), deleted bools render as
    1/0 (matching the old SQLite integer booleans). Money columns are
    numeric, so asyncpg hands back Decimals; normalize to float first."""
    val = row[col]
    if isinstance(val, Decimal):
        val = float(val)
    if col == "paid" and isinstance(val, float):
        return _fmt_float(val)
    if col == "deleted":
        return "" if val is None else ("1" if val else "0")
    if col == "created":
        return _fmt_datetime(val)
    return _plain_cell(row, col)


async def _data_table_payload(
    table, columns, *, page_length, max_page_length, order_by=None,
    default_order, cell=None, where=None, where_args=None, row_extra=None,
):
    # where_args maps named placeholder (:name) keys to values.
    where_args = where_args or {}
    """Run the shared server-side DataTables query for one table and return
    the {draw, recordsTotal, recordsFiltered, data} response dict.

    table, the columns/order_by whitelists and where come from module-level
    constants built by the caller; client input only affects pagination,
    whitelisted sort order and the caller-validated where clause. With no
    where clause recordsFiltered equals recordsTotal.

    row_extra, when given, is called per row with the row mapping and its
    dict is merged into that row's data: caller-declared fields that are
    not display columns (e.g. raw values the client needs for links or
    styling). DataTables ignores keys without a column but exposes them to
    createdRow/render.
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

    async with engine.connect() as conn:
        total = (await conn.execute(sa_text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()
        filtered = total
        if where:
            filtered = (await conn.execute(
                sa_text(f"SELECT COUNT(*) FROM {table}{where_sql}"), where_args
            )).scalar_one()
        rows = (await conn.execute(
            sa_text(f"SELECT * FROM {table}{where_sql} "
                f"ORDER BY {', '.join(order_sql)} LIMIT :limit OFFSET :offset"),
            {**where_args, "limit": length, "offset": start},
        )).fetchall()

    # Cells travel as display text; the client shows them as-is (sorting is
    # done server-side, so no client-side render hooks are needed). Rows
    # also carry any caller-declared extra fields from row_extra.
    data = []
    for row in rows:
        item = row_extra(row._mapping) if row_extra else {}
        item.update({col: cell(row._mapping, col) for col in columns})
        data.append(item)
    return {
        "draw": draw,
        "recordsTotal": total,
        "recordsFiltered": filtered,
        "data": data,
    }


def _encounter_cell(row, col):
    """Display text for one encounter cell. date shows m/d; due_date shows
    mm/dd (matching /report); None renders as the empty string."""
    val = row[col]
    # money columns are numeric: val is a Decimal (or None), never text
    if col in ("billed", "paid", "balance") and val is not None:
        return f"{val:.2f}"
    if col in ("date", "due_date"):
        return format_date(val, padded=(col == "due_date"))
    return "" if val is None else str(val)


@app.route("/encounters")
async def encounter_page():
    """The encounter table. Rows are fetched by DataTables from /api/encounter,
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
    """Server-side DataTables endpoint for /encounters.

    The client sends draw, start, length and order[i][column]/order[i][dir];
    the response is {draw, recordsTotal, recordsFiltered, data}. There is no
    search, so recordsFiltered always equals recordsTotal.
    """
    if not session.get("logged_in"):
        return "unauthorized", 401

    return jsonify(await _data_table_payload(
        "encounter", ENCOUNTER_COLUMNS,
        page_length=ENCOUNTER_PAGE_LENGTH,
        max_page_length=ENCOUNTER_MAX_PAGE_LENGTH,
        order_by=ENCOUNTER_ORDER_BY,
        default_order=ENCOUNTER_DEFAULT_ORDER,
        cell=_encounter_cell,
    ))


# ORDER BY expressions for server-side sorting of /lab's display-alias
# columns: the client's column names are LAB_COLUMNS display names, some of
# which are not real columns, so map them to the column that sorts them.
# (Every other column sorts as-is; the date columns are native DATE, so they
# sort chronologically.)
LAB_ORDER_BY = {
    "Patient": "patientname",
    "O": "encounter_type",
    "!": "priority",
    "collected": "coll_date",
}

# Order used when the client sends no valid sort: newest result first.
LAB_DEFAULT_ORDER = "result_date DESC NULLS LAST"

# The /lab client requests this many rows per page...
LAB_PAGE_LENGTH = 100
# ...and the API never serves more than this per request (DataTables treats
# a negative length as "all rows", which must not stream the whole table).
LAB_MAX_PAGE_LENGTH = 1000

# Named row filters for /api/lab, keyed by the query param the client sends.
# The client may only select a filter by name; the SQL (and its bindings)
# lives here. "unreviewed" is the bold-row rule: still outstanding
# (status = 0) and from a lab source. A NULL from_lab_id counts as
# unreviewed (COALESCE), matching the JS rule in lab.html; a NULL status is
# legacy and never matches status = 0.
LAB_FILTERS = {
    "unreviewed": ("status = 0 AND COALESCE(from_lab_id, 0) <> 0", {}),
}


def _fmt_lab_date(val):
    """ISO yyyy-mm-dd -> m/d/yy (the old client-side display); other values
    pass through unchanged."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(val))
    if not m:
        return str(val)
    return f"{int(m[2])}/{int(m[3])}/{m[1][2:]}"


def _fmt_lab_time(val):
    """'3:05 PM' -> '3:05 pm' (the old client-side display); other values
    pass through unchanged."""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})\s+([AP])\s?M", str(val).strip(),
                     re.IGNORECASE)
    if not m:
        return str(val)
    return f"{int(m[1])}:{m[2]} {m[3].lower()}m"


def _lab_cell(row, col):
    """Display text for one lab cell, mirroring the old server-rendered /lab
    body: dates are formatted here (the client shows them as-is), while the
    Patient/result links and the unreviewed bold rule are built client-side
    in lab.html from the row's extra fields (see _lab_row_extra). None
    renders as the empty string."""
    if col == "collected":
        parts = [
            fmt(v)
            for v, fmt in ((row["coll_date"], _fmt_lab_date),
                           (row["coll_time"], _fmt_lab_time))
            if v not in (None, "")
        ]
        return " ".join(parts)
    if col in ("date", "result_date"):
        val = row[col]
        return "" if val in (None, "") else _fmt_lab_date(val)
    if col == "type":
        return _format_lab_type(row[col])
    if col == "O":
        return _format_encounter_type(row["encounter_type"])[0]
    if col == "!":
        return _format_priority(row["priority"])
    if col == "Patient":
        return row["patientname"] or ""
    if col == "lab":
        return _format_from_lab(row["from_lab_id"])
    if col == "status":
        return "" if row["interface_status"] is None else str(row["interface_status"])
    if col == "result":
        # "view" when the result is stored, or when it has been received at
        # the interface (result_date) and just needs pulling from the lab
        # interface; lab.html builds the link (with the data-fetched flag
        # from _lab_row_extra) from the non-empty text.
        if row[col] or row["result_date"]:
            return "view"
        return ""
    val = row[col]
    return "" if val is None else str(val)


def _lab_row_extra(row):
    """Per-row fields that are not display columns, for lab.html's
    render/createdRow hooks: the patient MRN (patient link), the raw
    unreviewed-rule inputs (the display "status" column is
    interface_status, not this int status), and whether the result is
    stored (result_fetched = 1) or only received at the interface (0,
    needs a fetch from the lab interface)."""
    return {
        "mrn": row["mrn"],
        "status_int": row["status"],
        "from_lab": row["from_lab_id"],
        "result_fetched": 1 if row["result"] else 0,
    }


@app.route("/api/lab")
async def api_lab():
    """Server-side DataTables endpoint for /lab.

    Like /api/encounter, plus an optional unreviewed= query param: any
    nonempty value serves and counts only the LAB_FILTERS["unreviewed"]
    rows. An empty or absent value serves the table unfiltered.
    """
    if not session.get("logged_in"):
        return "unauthorized", 401

    where, where_args = None, {}
    if (request.args.get("unreviewed") or "").strip():
        where, where_args = LAB_FILTERS["unreviewed"]

    return jsonify(await _data_table_payload(
        "lab", LAB_COLUMNS,
        page_length=LAB_PAGE_LENGTH,
        max_page_length=LAB_MAX_PAGE_LENGTH,
        order_by=LAB_ORDER_BY,
        default_order=LAB_DEFAULT_ORDER,
        cell=_lab_cell,
        row_extra=_lab_row_extra,
        where=where,
        where_args=where_args,
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
        async with engine.connect() as conn:
            rows = (await conn.execute(
                sa_text("SELECT hash, salt FROM users WHERE name = :name"), {"name": name}
            )).fetchall()
        if rows:
            stored_hash, salt = rows[0]._mapping["hash"], rows[0]._mapping["salt"]
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
    """Autosave one editable field back to the report and encounter tables."""
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
    if field == "due_date":
        if value.strip():
            # Stored as yyyy-mm-dd; the client sends that raw ISO as the
            # value. Invalid dates are rejected and never saved.
            try:
                save_value = parse_due_date(value)
            except ValueError:
                return "invalid due_date", 400
        else:
            # Clearing the due date stores NULL (due_date is a DATE column).
            save_value = None

    async with engine.connect() as conn:
        # field comes from the EDITABLE_COLUMNS whitelist, safe to interpolate
        await conn.execute(sa_text(f"UPDATE report SET {field} = :value WHERE encounter = :encounter"), {"value": save_value, "encounter": enc})
        await conn.execute(sa_text(f"UPDATE encounter SET {field} = :value WHERE id = :encounter"), {"value": save_value, "encounter": enc})
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
        con = psycopg2.connect(PG_DSN)
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
    """Result details (lab.result JSON) for one lab report id, for the /lab table.

    If the result has not been stored yet (NULL) it is pulled lazily from
    the ECW lab interface via db.update_lab_result() (the row's type,
    0 = lab, 1 = imaging; 0 when NULL). The thread opens its own sync
    connection, exactly like db.py's __main__; update_lab_result commits
    itself. The first call of a process may re-login to ECW (JSCrypto
    handshake), which takes a few seconds."""
    if not session.get("logged_in"):
        return "unauthorized", 401
    lab_id = request.args.get("id", "")
    try:
        lab_id = int(lab_id)
    except (TypeError, ValueError):
        return "no such lab", 404
    async with engine.connect() as conn:
        row = (await conn.execute(
            sa_text("SELECT result, type FROM lab WHERE id = :lab_id"),
            {"lab_id": lab_id},
        )).fetchone()
    if row is None:
        return "no such lab", 404
    result, report_type = row[0], row[1]
    if result is None:
        # Result received at the interface but not stored yet: pull it from
        # the ECW lab interface.
        def _fetch():
            with ESession() as esession:
                client = Client(esession)
                with Session(create_engine(DATABASE_URL)) as s:
                    # fresh=True: bypass the cache read so a result that was
                    # unavailable at an earlier fetch is not pinned to "no
                    # result" by a stale cache entry (see update_lab_result).
                    update_lab_result(s, client, lab_id, int(report_type or 0), fresh=True)
        try:
            await asyncio.to_thread(_fetch)
        except Exception:
            # requests failure, imaging-branch asserts, login failure...
            logging.exception(
                "lab %d: failed to fetch result from lab interface", lab_id)
            return "failed to fetch from lab interface", 502
        # Re-read: the fetch stored the result (or the interface had none).
        async with engine.connect() as conn:
            row = (await conn.execute(
                sa_text("SELECT result FROM lab WHERE id = :lab_id"),
                {"lab_id": lab_id},
            )).fetchone()
        result = row[0] if row else None
    if result is None:
        # The interface returned no reports: an empty
        # LabDataDetailJSONArray is a no-op in update_lab_result.
        return "no result available yet", 409
    try:
        return jsonify(json.loads(result))
    except (TypeError, json.JSONDecodeError):
        return "bad result data", 400


@app.route("/api/patient_note", methods=["POST"])
async def api_patient_note():
    """Refresh one patient's yellow sticky note (POST, mrn in the JSON body)
    for the /patient page's refresh button: re-fetches it from the ECW
    interface via db.update_patient_note(), which stores Patient.yellow_note
    and stamps yellow_updated.

    The thread opens its own sync connection, exactly like /api/lab_result;
    update_patient_note commits itself. The first call of a process may
    re-login to ECW (JSCrypto handshake), which takes a few seconds.
    The response carries the new note (always a string; an empty sticky is
    '') plus the same "Sticky updated ..." age/tooltip the page renders on
    load, so the client can update in place."""
    if not session.get("logged_in"):
        return "unauthorized", 401
    data = await request.get_json(silent=True) or {}
    try:
        # Same validation as /patient (mrn.isdigit()): update_patient_note
        # would otherwise upsert a patient row for an arbitrary value.
        mrn = int(data.get("mrn"))
        if not str(mrn).isdigit():
            raise ValueError
    except (TypeError, ValueError):
        return "bad request", 400

    def _fetch():
        with ESession() as esession:
            client = Client(esession)
            with Session(create_engine(DATABASE_URL)) as s:
                return update_patient_note(s, client, mrn)

    try:
        note = await asyncio.to_thread(_fetch)
    except Exception:
        # requests failure, expired-session re-login...
        logging.exception("mrn %d: failed to refresh the sticky note from ECW", mrn)
        return "failed to fetch from ECW", 502
    # Re-read the fresh yellow_updated so the page's "Sticky updated ..."
    # line can be rebuilt exactly like on load.
    async with engine.connect() as conn:
        row = (await conn.execute(
            sa_text("SELECT yellow_updated FROM patient WHERE mrn = :mrn"),
            {"mrn": mrn},
        )).fetchone()
    sticky_updated, sticky_updated_tip = _sticky_age(row[0] if row else None)
    return jsonify({
        "note": note,
        "sticky_updated": sticky_updated,
        "sticky_updated_tip": sticky_updated_tip,
    })


def _note_eq(a, b):
    """True when two sticky notes are the same (both always strings)."""
    return a == b


@app.route("/api/patient_note_edit", methods=["POST"])
async def api_patient_note_edit():
    """Save the /patient page's in-place sticky edit (POST, JSON body: mrn,
    original, new). Check the sticky against eCW before writing."""
    if not session.get("logged_in"):
        return "unauthorized", 401
    data = await request.get_json(silent=True) or {}
    try:
        # Same validation as /patient (mrn.isdigit()).
        mrn = int(data.get("mrn"))
        if not str(mrn).isdigit():
            raise ValueError
    except (TypeError, ValueError):
        return "bad request", 400
    original = data.get("original")
    new = data.get("new")
    if not isinstance(original, str):
        return "bad request", 400
    if not isinstance(new, str):
        return "bad request", 400
    if original == new:
        return "no change", 400

    def _save():
        with ESession() as esession:
            client = Client(esession)
            # Check the sticky against ECW before updating it: re-fetch the
            # source of truth and confirm it is still what the page loaded,
            # so the edit can't clobber a note that changed in ECW since the
            # page loaded. An empty sticky fetches ''.
            try:
                current = client.fetch_patient_note(mrn)
            except Exception:
                # A transient fetch failure. Treat the sticky as empty, so a
                # non-empty original conflicts and the save is refused.
                current = ''
            if not _note_eq(current, original):
                return "conflict", current
            client.save_patient_note(mrn, new)
            # Persist the note ECW now holds (a cleared note fetches as
            # '') and stamp it.
            try:
                note = client.fetch_patient_note(mrn)
            except IndexError:
                note = ''
            with Session(create_engine(DATABASE_URL)) as s:
                upsert(s, Patient, {
                    'mrn': mrn,
                    'yellow_note': note,
                    'yellow_updated': datetime.now(timezone.utc),
                }, key='mrn')
                s.commit()
        return "saved", note

    try:
        status, note = await asyncio.to_thread(_save)
    except Exception:
        # requests failure, expired-session re-login, ECW save failure...
        logging.exception("mrn %d: failed to save the sticky note to ECW", mrn)
        return "failed to save to ECW", 502
    if status == "conflict":
        # The sticky changed in ECW since this page loaded it.
        return ("sticky changed in ECW since this page loaded; reload and retry",
                409)
    # Re-read the fresh yellow_updated so the page's "Sticky updated ..."
    # line can be rebuilt exactly like on load.
    async with engine.connect() as conn:
        row = (await conn.execute(
            sa_text("SELECT yellow_updated FROM patient WHERE mrn = :mrn"),
            {"mrn": mrn},
        )).fetchone()
    sticky_updated, sticky_updated_tip = _sticky_age(row[0] if row else None)
    return jsonify({
        "note": note,
        "sticky_updated": sticky_updated,
        "sticky_updated_tip": sticky_updated_tip,
    })


@app.route("/api/lab_status", methods=["POST"])
async def api_lab_status():
    """Mark the /patient page's selected labs reviewed (status 1) or
    unreviewed (status 0) in ECW, then mirror the result in our lab table
    -- the same Lab.status db.py's unreviewed_labs() maintains (0 =
    outstanding, 1 = reviewed).

    reviewed: one client.review_labs() call for the whole selection
    (idempotent for already-reviewed labs). unreviewed: one
    client.unreview_lab() call per lab, which also needs the lab's
    encounter_id (400 when a selected lab has none).

    The labs must belong to the patient (mrn) in the body, so a stale page
    can't flip another patient's labs. The thread opens its own sync
    connection, exactly like /api/patient_note. The response carries each
    lab's fresh status and whether it is unreviewed under the page's
    bold-row rule (status = 0 and from a lab source), so the client
    re-styles the rows in place."""
    if not session.get("logged_in"):
        return "unauthorized", 401
    data = await request.get_json(silent=True) or {}
    try:
        # Same validation as /patient (mrn.isdigit()).
        mrn = int(data.get("mrn"))
        if not str(mrn).isdigit():
            raise ValueError
        lab_ids = [int(i) for i in data.get("lab_ids", [])]
        status = int(data.get("status"))
    except (TypeError, ValueError):
        return "bad request", 400
    if status not in (0, 1):
        return "bad request", 400
    if not lab_ids:
        return "no labs selected", 400

    unique_ids = list(dict.fromkeys(lab_ids))
    params = {"mrn": mrn, "status": status}
    for i, lab_id in enumerate(unique_ids):
        params[f"id{i}"] = lab_id
    placeholders = ", ".join(f":id{i}" for i in range(len(unique_ids)))

    def _set_status():
        with ESession() as esession:
            client = Client(esession)
            # Only this patient's labs: a stale page can't flip another
            # patient's labs.
            with Session(create_engine(DATABASE_URL)) as s:
                rows = s.execute(
                    sa_text("SELECT id, encounter_id FROM lab "
                            "WHERE mrn = :mrn AND id IN (" + placeholders + ")"),
                    params,
                ).fetchall()
            if not rows:
                return "ok", []
            if status == 1:
                client.review_labs([row.id for row in rows])
            else:
                # unreview_lab also unlocks the lab for editing and needs
                # its encounter_id; we can't unlock a lab we have no
                # encounter for.
                missing = [row.id for row in rows if row.encounter_id is None]
                if missing:
                    return "no encounter", missing
                for row in rows:
                    client.unreview_lab(row.id, row.encounter_id)
            # Mirror the ECW state locally so the page (and /lab) agree
            # without waiting for the next ECW sync.
            with Session(create_engine(DATABASE_URL)) as s:
                s.execute(
                    sa_text("UPDATE lab SET status = :status "
                            "WHERE mrn = :mrn AND id IN (" + placeholders + ")"),
                    params,
                )
                s.commit()
        return "ok", [row.id for row in rows]

    try:
        ecw_status, ids = await asyncio.to_thread(_set_status)
    except Exception:
        # requests failure, expired-session re-login, ECW status assert...
        logging.exception(
            "mrn %d: failed to %s lab(s) %s in ECW",
            mrn, "review" if status == 1 else "unreview",
            ",".join(map(str, unique_ids)),
        )
        return "failed to update labs in ECW", 502
    if ecw_status != "ok":
        return (f"lab(s) {','.join(map(str, ids))} have no encounter_id; "
                "can't unreview in ECW"), 400

    # Re-read the fresh status so the page's rows can be re-styled in place.
    async with engine.connect() as conn:
        rows = (await conn.execute(
            sa_text("SELECT id, status, from_lab_id FROM lab "
                    "WHERE mrn = :mrn AND id IN (" + placeholders + ")"),
            params,
        )).fetchall()

    labs = []
    for row in rows:
        row = row._mapping
        # Same rule as the page's bold rows (and /lab's): still outstanding
        # (status = 0) and from a lab source; a NULL from_lab_id counts as
        # unreviewed.
        labs.append({
            "id": row["id"],
            "status": row["status"],
            "unreviewed": row["status"] == 0 and (
                row["from_lab_id"] is None or row["from_lab_id"] != 0),
        })
    return jsonify({"labs": labs})


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
