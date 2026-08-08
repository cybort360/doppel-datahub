"""Capture DataHub lineage screenshot for the synthetic twin."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:9002"
OUTPUT = Path(__file__).parent.parent / "examples" / "ui-datahub-lineage.png"

SYNTHETIC_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:postgres,"
    "doppel.healthcare.patients_synthetic,NON_PROD)"
)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.goto(BASE, timeout=120_000)
        # Login form appears when not authenticated.
        try:
            page.wait_for_selector("#username", timeout=30_000)
            page.fill("#username", "datahub")
            page.fill("#password", "datahub")
            page.click('button:has-text("Login")')
            page.wait_for_url(lambda url: "/login" not in url, timeout=120_000)
        except Exception:
            pass  # Already authenticated or no login form.

        lineage_url = f"{BASE}/dataset/{SYNTHETIC_URN}/Lineage"
        page.goto(lineage_url, timeout=120_000)
        page.wait_for_timeout(10_000)
        # Dismiss the onboarding tour modal if it appears.
        try:
            page.click('button[aria-label="Close"]', timeout=5_000)
            page.wait_for_timeout(1_000)
        except Exception:
            pass
        page.screenshot(path=OUTPUT, full_page=True)
        print(f"Screenshot: {OUTPUT}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
