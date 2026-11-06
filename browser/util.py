import asyncio
from pathlib import Path
import json

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from start_browser import URL_LOGIN

PWD_STEP = "getPwdPage"
# logout.jsp is what the app's signOut() navigates to; use it to verify
# that clicking the dialog's Log Out button really logged the user out.
LOGOUT_URL_MARKER = "logout.jsp"


async def _ensure_menu_visible(page):
    """Make sure the left nav is open and showing the main menu.

    The main menu holding #Billing_menu lives in #jcarousel2, switched in
    via the arrow next to the star (#next-fav). With the nav collapsed,
    the Ctrl+Alt+VC keybind is a no-op and #Billing_menu is not visible,
    so both the keybind and the click fallback need the nav open on the
    main menu.
    """
    await _open_nav(page)

    main_carousel = page.locator("#jcarousel2")
    if "active" not in (await main_carousel.get_attribute("class") or ""):
        await page.locator("#next-fav").click()
        await page.wait_for_selector(
            "#jcarousel2.active", state="visible", timeout=10_000)


async def open_nav(page):
    """Open the collapsed left nav (#leftnavApp).

    The left nav is collapsed by default (slid off-screen at left:-61px);
    the star at top-left (#jellybean-panelLink5) toggles its "visible"
    class and slides it in. On some pages (e.g. office visits) the star
    is display:none and a hamburger icon
    (#jellybean-panelLink4, class "navgator mainMenu") takes its place in
    the same spot, so it is used as a fallback when the star is not
    visible. With the nav open, the Favorites carousel (#jcarousel3) is
    shown by default.
    """
    nav_cls = await page.locator("#leftnavApp").get_attribute("class")
    if "visible" not in (nav_cls or ""):
        star = page.locator("#jellybean-panelLink5")
        if await star.is_visible():
            await star.click()
        else:
            await page.locator("#jellybean-panelLink4").click()
        await page.wait_for_selector(
            "#leftnavApp.visible", state="visible", timeout=10_000)


async def _dismiss_session_expiry_modal(page):
    """Log out via the session-expiration dialog if it is open.

    When the server-side session times out, the app shows the
    "Session Expiration-Automatic Log Out" dialog (#sessionExpiredMessageModal;
    the "in" class marks it open, like the other app modals). While it is
    up, a plain page.goto(URL_LOGIN) does not reach the login page, so the
    dialog's "Log Out" button (#cancelBtnSession) is clicked instead. Its
    onclick doLogout() only acts when the app's session-expired localStorage
    flag is set; it is set explicitly first so the click always logs out.
    """
    modal = page.locator("#sessionExpiredMessageModal.in")
    if not await modal.count():
        return
    await page.evaluate("localStorage.setItem('sessionExpired', 'yes')")
    print("Session-expiration dialog is open; clicking Log Out.")
    await modal.locator("#cancelBtnSession").click()
    await modal.wait_for(state="hidden", timeout=30_000)
    # signOut() navigates to logout.jsp, which lands on the login page
    await page.wait_for_url(
        lambda url: LOGOUT_URL_MARKER in url
        or PWD_STEP in url or "newLogin" in url,
        timeout=30_000)


async def close_claim_modal(page):
    """Close a leftover claim detail panel if open.

    A single-result claim lookup opens it automatically (right-panel mode)
    and its backdrop blocks clicks on the page behind it, so commands that
    drive the page close it first to stay idempotent. The modal id varies
    between runs (#claimModal<timestamp>); the "in" class marks it as open.
    (If the user left unsaved claim edits, a Save/Don't Save prompt may
    appear instead of the panel closing.)

    A leftover "View Selected ERA" panel (#Claim-viewERAModal<timestamp>)
    and a leftover "Claim Log" panel (#claimlogId) stack on top of the
    claim panel, so they are closed first.
    """
    era_modal = page.locator('div.modal.in[id^="Claim-viewERAModal"]')
    if await era_modal.count():
        await era_modal.locator(".modal-header button.close").click()
        await era_modal.wait_for(state="hidden", timeout=10_000)

    # The modal nests other (hidden) log modals with their own .close
    # buttons, so scope the click to the top-level header only.
    log_modal = page.locator(
        "div.modal.in#claimlogId > .modal-dialog > .modal-content "
        "> .modal-header > button.close")
    if await log_modal.count():
        await log_modal.click()
        await page.locator("div.modal.in#claimlogId").wait_for(
            state="hidden", timeout=10_000)

    claim_modal = page.locator('div.modal.in[id^="claimModal"]')
    if await claim_modal.count():
        await claim_modal.locator(".modal-header button.close").click()
        await claim_modal.wait_for(state="hidden", timeout=10_000)


async def login(page):
    on_pwd_step = PWD_STEP in page.url
    if not on_pwd_step and not page.url.startswith(URL_LOGIN):
        # An open session-expiration dialog blocks the login navigation
        await _dismiss_session_expiry_modal(page)
        if not on_pwd_step and not page.url.startswith(URL_LOGIN):
            await page.goto(URL_LOGIN)
    print(f"Current page: {page.url}")

    with (Path.home() / 'Downloads/pass.json').open() as f:
        password = json.load(f)["ecw"]

    # Step 1: enter username and click Next
    if not on_pwd_step:
        username_box = page.get_by_role(
            "textbox", name="Enter username to continue")
        await username_box.wait_for(state="visible", timeout=30_000)
        await username_box.fill("lingj")
        await page.get_by_role("button", name="Next").click()

    # Step 2: enter password and log in (captcha is not enforced, skip it)
    password_box = page.get_by_role(
        "textbox", name="Enter Password to continue")
    await password_box.wait_for(state="visible", timeout=30_000)
    await password_box.fill(password)
    await page.get_by_role("button", name="Log In").click()

    # Wait until the login page is gone
    await page.wait_for_url(
        lambda url: PWD_STEP not in url and "newLogin" not in url,
        timeout=60_000)
    print(f"Logged in. Current page: {page.url}")


def _install_dialog_handler(page):
    """Auto-dismiss dialogs (beforeunload warnings, confirms) that the
    app raises during the script's own navigations, so they never
    block the automation. Installed once per page."""
    if getattr(page, "_ecw_dialog_handler", False):
        return

    async def on_dialog(dialog):
        try:
            await dialog.dismiss()
        except Exception:
            pass  # already handled by another client

    page.on("dialog", on_dialog)
    page._ecw_dialog_handler = True


async def _clear_pending_dialog(page) -> bool:
    """Dismiss a dialog that was left pending (e.g. a beforeunload
    warning the app raised on a session-expiry redirect while nothing
    was driving the page).

    Playwright only auto-dismisses dialogs that fire while it is the
    driving client; a dialog left over from an idle period stays open
    indefinitely. A pending JS dialog freezes the page's script
    thread, which leaves the login page's inputs stuck disabled (the
    init script that enables #passwordField never runs) and blocks
    every Playwright action until it is handled.

    Detection: a pending dialog makes the page unresponsive, so a
    quick evaluate times out. Returns True if a dialog was dismissed.
    """
    cdp = await page.context.new_cdp_session(page)
    try:
        try:
            await asyncio.wait_for(
                cdp.send("Runtime.evaluate", {"expression": "1"}),
                timeout=1_000)
            return False  # page script thread responsive -> no dialog
        except asyncio.TimeoutError:
            pass  # page blocked -> a dialog is probably holding it
        try:
            await cdp.send(
                "Page.handleJavaScriptDialog", {"action": "dismiss"})
        except Exception:
            return False  # no dialog after all (page was just busy)
        print("Dismissed a leftover dialog that was blocking the page.")
        return True
    finally:
        await cdp.detach()


async def prepare(page):
    """Make the page safe to drive: auto-dismiss dialogs that fire from
    now on, clear any dialog already pending, and let the navigation a
    dismissed beforeunload dialog releases finish so the page state
    (URL) read afterwards is current."""
    _install_dialog_handler(page)
    if await _clear_pending_dialog(page):
        try:
            await page.wait_for_load_state(
                "domcontentloaded", timeout=15_000)
        except PlaywrightTimeoutError:
            pass
