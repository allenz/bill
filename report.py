import html
import re
from datetime import date

import aiosqlite

DB_PATH = "/srv/allen/ecw/billing.sqlite3"

REPORT_COLUMNS = [
    "due_date", "assignee", "task", "notes", "claim", "date", "name", "reason", "mrn", "insurance",
    "ppo", "P", "coinsurance", "visittype", "cpt", "cpt_name",
    "billed", "paid", "deduct", "claim_balance", "pt_paid",
]

def format_date(val, padded=False):
    """Render an ISO date (YYYY-MM-DD) as M/D (or zero-padded mm/dd)."""
    if val is None or val == "":
        return ""
    try:
        d = date.fromisoformat(str(val))
        return d.strftime("%m/%d") if padded else d.strftime("%-m/%-d")
    except ValueError:
        return str(val)


# due_date is edited as mm/dd but stored as yyyy-mm-dd. The /api/update
# request sends the raw stored ISO directly as the value.
def parse_due_date(iso):
    """Validate a due_date value (yyyy-mm-dd) and return it.
    Raises ValueError if invalid."""
    if not isinstance(iso, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso):
        raise ValueError("expected yyyy-mm-dd")
    date.fromisoformat(iso)  # raises ValueError for impossible calendar dates
    return iso


NUMERIC_COLUMNS = {"ppo", "billed", "paid", "deduct", "claim_balance", "pt_paid"}

# Display labels for headers; any column not listed shows its raw name.
COLUMN_LABELS = {"claim_balance": "balance", "visittype": "type", "due_date": "due"}

# Columns the user can edit in the table. Edits are saved back to both the
# Report row(s) and the matching Encounter row (a single encounter may span
# multiple report rows, one per cpt).
EDITABLE_COLUMNS = {"due_date", "assignee", "task", "notes"}


async def render_reports(months, cutoff):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if months is None:
            cur = await conn.execute("SELECT * FROM Report ORDER BY date ASC")
            rows = await cur.fetchall()
            since = "(all time)"
        else:
            cur = await conn.execute(
                "SELECT * FROM Report WHERE date >= ? ORDER BY date ASC", (cutoff,)
            )
            rows = await cur.fetchall()
            since = cutoff

    header = "".join(
        f"<th>{html.escape(COLUMN_LABELS.get(c, c))}</th>" for c in REPORT_COLUMNS
    )
    body_rows = []
    for row in rows:
        tds = []
        for col in REPORT_COLUMNS:
            if col in EDITABLE_COLUMNS and row["encounter"] is not None:
                tds.append(f"<td>{editable_input(row, col)}</td>")
            else:
                val = row[col]
                if col in ("paid", "deduct", "claim_balance") and isinstance(val, (int, float)):
                    text = f"{val:.2f}"
                elif col == "billed" and isinstance(val, (int, float)):
                    text = str(round(val))
                elif col == "due_date":
                    text = format_date(val, padded=True)
                elif col == "date":
                    text = format_date(val)
                else:
                    text = "" if val is None else str(val)
                cls = ' class="num"' if col in NUMERIC_COLUMNS else ""
                if col == "claim" and val is not None:
                    # Clickable: opens the bottom claim-info pane (see /api/claim_info)
                    tds.append(f'<td><a class="claim-link" data-claim="{val}">{html.escape(text)}</a></td>')
                else:
                    tds.append(f"<td{cls}>{html.escape(text)}</td>")
        body_rows.append("      <tr>" + "".join(tds) + "</tr>")
    # Rendered into templates/report.html by app.py (header/body are
    # pre-escaped HTML, so the template passes them through with |safe).
    return header, "\n".join(body_rows)


def editable_input(row, col):
    """Render one editable cell with data-* attrs for the autosave handler."""
    raw = row[col]
    if col == "due_date" and raw:
        # Stored as yyyy-mm-dd, shown/edited as mm/dd. data-iso keeps the
        # original value so the client can reuse its year when editing.
        try:
            text = date.fromisoformat(str(raw)).strftime("%m/%d")
        except ValueError:
            text = str(raw)
        iso_attr = f' data-iso="{html.escape(str(raw), quote=True)}"'
    else:
        text = str(raw or "")
        iso_attr = ""
    enc = html.escape(str(row["encounter"]), quote=True)
    return (
        f'<input type="text" class="editable-input" '
        f'data-encounter="{enc}" data-field="{col}"{iso_attr} '
        f'value="{html.escape(text, quote=True)}">'
    )

