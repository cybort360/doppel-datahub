"""Capture DOPPEL demo screenshots and verify the browser flow end-to-end."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUTPUT = Path(__file__).parent.parent / "examples"


def wait_for_verification(page):
    page.wait_for_selector("#verdictStatus", state="visible", timeout=120_000)
    # Poll until the verdict is no longer the placeholder.
    page.wait_for_function(
        """
        () => {
            const el = document.querySelector('#verdictStatus');
            return el && el.textContent !== '—' && el.textContent.trim() !== '';
        }
        """,
        timeout=120_000,
    )


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Screen 1: Data asset
        page.goto(BASE)
        page.wait_for_selector("#patientsRowCount", state="visible")
        page.screenshot(path=OUTPUT / "ui-data-asset.png", full_page=True)
        print("Screenshot: ui-data-asset.png")

        # Screen 2: Generation plan
        page.click("#startDemoButton")
        page.wait_for_selector("#planPanels", state="visible")
        page.screenshot(path=OUTPUT / "ui-generation-plan.png", full_page=True)
        print("Screenshot: ui-generation-plan.png")

        # Screen 3: Live pipeline -> verification
        page.click("#runPipelineButton")
        wait_for_verification(page)
        page.screenshot(path=OUTPUT / "ui-verified-run.png", full_page=True)
        print("Screenshot: ui-verified-run.png")

        decision = page.inner_text("#verdictStatus")
        privacy = page.inner_text("#metricPrivacy")
        utility = page.inner_text("#metricUtility")
        integrity = page.inner_text("#metricIntegrity")
        overlap = page.inner_text("#metricOverlap")
        direct = page.inner_text("#metricDirect")

        print(f"Decision: {decision}")
        print(f"Privacy: {privacy}, Utility: {utility}, Integrity: {integrity}")
        print(f"Overlap: {overlap}, Direct matches: {direct}")

        if decision != "VERIFIED":
            print("ERROR: expected VERIFIED")
            return 1
        if overlap != "0" or direct != "0":
            print("ERROR: expected zero leakage")
            return 1

        # Screen 4: DataHub writeback
        page.click("#toWritebackButton")
        page.wait_for_selector("#writebackPatientsMeta", state="visible")
        page.screenshot(path=OUTPUT / "ui-writeback.png", full_page=True)
        print("Screenshot: ui-writeback.png")

        # Download bundle via the API so we know the download link works.
        download_href = page.get_attribute("#downloadTwinButton", "href")
        if download_href:
            response = page.request.get(f"{BASE}{download_href}")
            if response.status != 200:
                print(f"ERROR: download returned {response.status}")
                return 1
            print(f"Download OK: {len(response.body())} bytes")

        browser.close()
    print("Browser flow verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
