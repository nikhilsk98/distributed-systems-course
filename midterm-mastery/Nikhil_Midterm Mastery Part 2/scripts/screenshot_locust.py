"""Screenshot Locust HTML reports headlessly with Playwright (full page: charts + stats tables).
usage: python screenshot_locust.py results/E3/configA/report.html screenshots/E3_configA_locust_report.png [...pairs]
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

pairs = list(zip(sys.argv[1::2], sys.argv[2::2]))
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=1.5)
    for src, dst in pairs:
        page.goto(Path(src).resolve().as_uri())
        page.wait_for_timeout(2500)  # let the echarts animations finish
        page.screenshot(path=dst, full_page=True)
        print("screenshot", dst)
    b.close()
