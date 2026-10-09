import asyncio
import sqlite3
import sys

import app as app_module
from claim_info import DB_PATH, claim_info


async def main():
    # claim_info.py must stay importable without the ECW cache machinery
    # (store.py opens cache.sqlite and reads the dict file on import),
    # since the web app imports it.
    assert "store" not in sys.modules, "claim_info imported the cache store"
    assert "scrape_ecw" not in sys.modules, "claim_info imported scrape_ecw"

    # encounter.claim is TEXT and can be '' for rows without a claim, so
    # pick one that holds a real (numeric) claim number.
    con = sqlite3.connect(DB_PATH)
    real_claim = con.execute(
        "SELECT claim FROM encounter WHERE claim GLOB '[0-9]*' ORDER BY claim DESC LIMIT 1"
    ).fetchone()[0]
    missing_claim = con.execute(
        "SELECT IFNULL(MAX(CAST(claim AS INTEGER)), 0) + 1 FROM encounter WHERE claim GLOB '[0-9]*'"
    ).fetchone()[0]
    con.close()

    # direct call: real claim -> detail dict, unknown claim -> {}
    info = claim_info(sqlite3.connect(DB_PATH), str(real_claim))
    assert "name" in info and "DOS" in info, info
    assert claim_info(sqlite3.connect(DB_PATH), str(missing_claim)) == {}

    client = app_module.app.test_client()

    # unauthenticated request is rejected
    resp = await client.get(f"/api/claim_info?claim={real_claim}")
    assert resp.status_code == 401

    # authenticated request returns the claim details
    async with client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["user"] = "alice"

    resp = await client.get(f"/api/claim_info?claim={real_claim}")
    assert resp.status_code == 200
    data = await resp.get_json()
    assert data == info, (data, info)

    # bad input and missing claims
    resp = await client.get("/api/claim_info?claim=not-a-number")
    assert resp.status_code == 400
    resp = await client.get(f"/api/claim_info?claim={missing_claim}")
    assert resp.status_code == 404

    # the report page carries the bottom-pane markup
    resp = await client.get("/report")
    html = (await resp.get_data()).decode()
    assert "claim-pane" in html

    print("all claim_info checks passed")


asyncio.run(main())
