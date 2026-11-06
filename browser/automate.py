import argparse
import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from custom_browser import get_wrapper, get_endpoint
from start_browser import URL_LOGIN

from util import login, close_claim_modal, prepare, PWD_STEP
from run_payment import payment

# The Patient Hub header contains emoji (e.g. \U0001f382); keep the cp1252
# Windows console from crashing on them.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LABS_PATH = "jellybean/labs"


async def run_login():
    async with get_wrapper().use_async(async_playwright()) as p:
        browser = await p.chromium.connect(get_endpoint())
        page = browser.contexts[0].pages[0]
        await prepare(page)
        await login(page)


async def lab():
    async with get_wrapper().use_async(async_playwright()) as p:
        browser = await p.chromium.connect(get_endpoint())
        page = browser.contexts[0].pages[0]
        await prepare(page)
        print(f"Current page: {page.url}")

        # Log in first if the session is not authenticated
        if "newLogin" in page.url or PWD_STEP in page.url:
            await login(page)

        # A leftover claim detail panel blocks the nav links
        await close_claim_modal(page)

        if LABS_PATH in page.url:
            print("Already on the lab page.")
            return

        # Preferred: the Ctrl+Shift+L keybind opens the Labs ("L") jellybean
        await page.keyboard.press("Control+Shift+L")
        try:
            await page.wait_for_url(
                lambda url: LABS_PATH in url, timeout=4_000)
        except PlaywrightTimeoutError:
            # Fallback: click the "L" button in the jellybean navigation
            await page.get_by_role(
                "link", name=re.compile(r"^L\b")).click()
            await page.wait_for_url(
                lambda url: LABS_PATH in url, timeout=4_000)

        print(f"On lab page. Current page: {page.url}")


async def patient(name: str):
    async with get_wrapper().use_async(async_playwright()) as p:
        browser = await p.chromium.connect(get_endpoint())
        page = browser.contexts[0].pages[0]
        await prepare(page)
        print(f"Current page: {page.url}")

        # Log in first if the session is not authenticated
        if "newLogin" in page.url or PWD_STEP in page.url:
            await login(page)

        # Close leftover modals if still open (they block the Action link
        # with a pointer-events overlay) so reruns are idempotent
        await close_claim_modal(page)
        modal = page.locator("#patient-lookup-screen")
        if await modal.count():
            await page.locator("#patientSearchBtn1").click()
            await modal.wait_for(state="hidden", timeout=4_000)

        # An already-open Patient Hub also blocks the Action link. Its id
        # varies between runs (#patient-hub / #patient_hub); the "in" class
        # marks it as open.
        hub_modal = page.locator("div#patient-hub.in, div#patient_hub.in")
        if await hub_modal.count():
            await page.locator("#patient-hubBtn1").click()
            await hub_modal.wait_for(state="hidden", timeout=4_000)

        # Click the "Action" jellybean panel link
        action_link = page.locator("#jellybean-panelLink65")
        await action_link.wait_for(state="visible", timeout=4_000)
        await action_link.click()

        # Search for the patient in the lookup modal. The search is
        # automatic (search by "Name"), so filling the primary search box
        # is enough; no Search button click needed.
        search_box = page.locator("#patient-lookup-screen #searchText")
        await search_box.wait_for(state="visible", timeout=4_000)
        await search_box.fill(name)

        # Wait for a result row to appear in the lookup results table
        result_row = page.locator("#patient-lookup-screen .tablebody tr")
        await result_row.first.wait_for(state="visible", timeout=4_000)
        print(f"Patient lookup complete: {name!r} "
              f"({await result_row.count()} result(s)). Current page: {page.url}")

        # Click the patient name in the top result row to launch the
        # Patient Hub. Both name cells carry a "Launch Patient Hub"
        # tooltip and ng-click="confirmLaunchPatientHub(patient)".
        name_link = result_row.first.locator(
            "span[title^='Launch Patient Hub']").first
        await name_link.click()

        # Wait for the Patient Hub modal header. The modal's own id varies
        # (#patient-hub / #patient_hub), but the header title is stable.
        hub_title = page.locator(
            ".modal-title:visible", has_text=re.compile(r"^Patient Hub\b"))
        await hub_title.wait_for(state="visible", timeout=60_000)
        print(f"Patient hub launched: "
              f"{(await hub_title.first.inner_text()).strip()!r}. "
              f"Current page: {page.url}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Drive the ECW browser session (requires the "
                    "persistent browser started by start_browser.py).")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("login", help="log in to the portal")
    sub.add_parser("lab", help="open the Labs page")
    sub.add_parser("payment", help="add payments")

    p_patient = sub.add_parser(
        "patient", help="launch the Patient Hub for a patient")
    p_patient.add_argument(
        "name", nargs="?", default="Zhu, Lingyu",
        help=f"patient name to search")
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    # Legacy behavior: no subcommand runs the default patient lookup
    if args.command is None:
        args.command = "payment"
    if args.command == "login":
        asyncio.run(run_login())
    elif args.command == "lab":
        asyncio.run(lab())
    elif args.command == "payment":
        asyncio.run(payment())
    else:
        asyncio.run(patient(args.name))


if __name__ == "__main__":
    main()
