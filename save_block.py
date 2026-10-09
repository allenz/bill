from datetime import datetime
from sqlmodel import Session

from models import Block


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

        # --- Create the Model Instance ---
        block = Block(
            id=block_id,
            start=datetime.strptime(data["start"], "%Y-%m-%d %H:%M:%S"),
            end=datetime.strptime(data["end"], "%Y-%m-%d %H:%M:%S"),
            title=data["title"],
            comments=data["Comments"],
            encounter_count=data["encounterCount"],
        )
        blocks.append(block)

    session.add_all(blocks)
    session.commit()
    session.refresh(block)
    return blocks
