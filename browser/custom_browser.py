from pathlib import Path
from playwright_stealth import Stealth

def get_endpoint() -> str:
    with (Path.home() / "Downloads/endpoint.txt").open() as f:
        return f.read()

get_wrapper = Stealth
