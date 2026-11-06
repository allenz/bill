import asyncio
import subprocess
from pathlib import Path

from playwright.async_api import async_playwright
from custom_browser import get_wrapper

DATA_DIR = Path.home() / 'Downloads/e_data'
SESSION_NAME = 'e'

HOST = "https://cabahcapp.ecwcloud.com"
URL_INDEX = HOST + "/mobiledoc/jsp/webemr/index.jsp"
URL_LOGIN = HOST + "/mobiledoc/jsp/webemr/login/newLogin.jsp"


async def main():
    async with get_wrapper().use_async(async_playwright()) as p:
        context = await p.chromium.launch_persistent_context(DATA_DIR, headless=False)
        endpoint = await context.browser.bind(SESSION_NAME, workspace_dir=DATA_DIR)
        with open(Path.home() / "Downloads/endpoint.txt", "w") as f:
            f.write(endpoint["endpoint"])
        # context.on("response", handle_response)
        page = context.pages[0]
        await page.goto(URL_LOGIN)

        subprocess.Popen(f"playwright-cli attach {SESSION_NAME}", shell=True)

        await asyncio.get_event_loop().run_in_executor(
            None, input, "Press Enter to close the browser..."
        )

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
