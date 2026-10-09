import asyncio
import json

from quart.testing.connections import WebsocketDisconnectError

import app as app_module


def online(*viewers):
    return {"type": "online", "viewers": list(viewers)}


async def main():
    client = app_module.app.test_client()
    async with client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["user"] = "alice"

    # alice opens tab 1
    async with client.websocket("/ws/report") as ws1:
        assert json.loads(await ws1.receive()) == online("alice")

        # alice opens tab 2 -> both tabs see the duplicate
        async with client.websocket("/ws/report") as ws2:
            assert json.loads(await ws1.receive()) == online("alice", "alice")
            assert json.loads(await ws2.receive()) == online("alice", "alice")

            # bob joins
            bob = app_module.app.test_client()
            async with bob.session_transaction() as sess:
                sess["logged_in"] = True
                sess["user"] = "bob"
            async with bob.websocket("/ws/report") as ws3:
                assert json.loads(await ws1.receive()) == online("alice", "alice", "bob")
                assert json.loads(await ws2.receive()) == online("alice", "alice", "bob")
                assert json.loads(await ws3.receive()) == online("alice", "alice", "bob")
                # bob leaves
            assert json.loads(await ws1.receive()) == online("alice", "alice")
            assert json.loads(await ws2.receive()) == online("alice", "alice")

        # alice closes tab 2
        assert json.loads(await ws1.receive()) == online("alice")

    # alice closes tab 1 -> state fully cleaned up
    assert app_module.REPORT_VIEWERS == []
    assert app_module.REPORT_WEBSOCKETS == set()

    # /api/update is allowed even without a connected /report tab
    # (encounter 999999999 doesn't exist, so no rows are touched)
    resp = await client.post(
        "/api/update", json={"encounter": 999999999, "field": "notes", "value": "x"}
    )
    assert resp.status_code == 200

    # connected tabs get the cell_update broadcast
    async with client.websocket("/ws/report") as ws:
        assert json.loads(await ws.receive()) == online("alice")

        # a second tab joins, then alice's edit is broadcast to both
        async with client.websocket("/ws/report") as ws2:
            assert json.loads(await ws.receive()) == online("alice", "alice")
            assert json.loads(await ws2.receive()) == online("alice", "alice")
            resp = await client.post(
                "/api/update",
                json={"encounter": 999999999, "field": "notes", "value": "x"},
            )
            assert resp.status_code == 200
            expected = {
                "type": "cell_update", "encounter": 999999999,
                "field": "notes", "value": "x",
            }
            assert json.loads(await ws.receive()) == expected
            assert json.loads(await ws2.receive()) == expected

    # unauthenticated connection is rejected with 1008
    anon = app_module.app.test_client()
    async with anon.websocket("/ws/report") as ws:
        try:
            await ws.receive()
            raise AssertionError("expected disconnect for anonymous client")
        except WebsocketDisconnectError as e:
            assert str(e) == "1008", f"unexpected close code {e}"

    print("all websocket tracker checks passed")

asyncio.run(main())
