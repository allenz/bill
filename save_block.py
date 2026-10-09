from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlmodel import Session

from models import Block

# wall-clock times in the feed are facility local time
FACILITY_TZ = ZoneInfo('America/Los_Angeles')


BLOCK_CONSTANTS = {
    "facilityId": "0",
    "color": "16777215",
    "blockType": "0",
    "resources": "122",
    "blkcolor": "16777215",
    "AllDay": "0",
    "doctorId": "122",
    "POS": 0,
    "facilityName": "",
}


def save_blocks(rows: list[dict[str, str | int]], session: Session) -> list[Block]:
    blocks = []
    now = datetime.now(timezone.utc)

    for data in rows:
        # Validate fields that are not part of the database table schema
        for key, expected_value in BLOCK_CONSTANTS.items():
            if data.get(key) != expected_value:
                print(f"Got {data.get(key)} for {key}.")

        # --- ID Extraction ---
        # The incoming ID is formatted as "blk:6233:122" -> extract the integer part (6233)
        raw_id = data.get("id", "")
        try:
            if isinstance(raw_id, str) and raw_id.startswith("blk:"):
                block_id = int(raw_id.split(":")[1])
            else:
                block_id = int(raw_id)
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid ID format: '{raw_id}'") from e

        # Upsert by primary key: the 1-week feed re-serves the same block IDs
        # on every run, so a plain INSERT would violate block_pkey on re-runs
        # (same idiom as db.upsert, inlined to avoid a circular import).
        block = session.get(Block, block_id) or Block(id=block_id)
        block.start = datetime.strptime(data["start"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=FACILITY_TZ)
        block.end = datetime.strptime(data["end"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=FACILITY_TZ)
        block.title = data["title"]
        block.comments = data["Comments"]
        block.encounter_count = data["encounterCount"]
        block.updated = now
        blocks.append(block)

    session.add_all(blocks)
    session.commit()
    return blocks
