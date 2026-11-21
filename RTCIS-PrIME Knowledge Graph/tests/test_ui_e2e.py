"""Browser end-to-end test of the RTCIS <-> PrIME tab of knowledge-graph.html with the real API (Edge via Playwright).
    KG_UIUX_DIR=<config-drift-governance\\UIUX> python -m pytest tests/test_ui_e2e.py -m cloud
Clicks the real buttons; the API calls Cosmos, the GenAI model and the replica databases."""
import os
import pathlib

import pytest

pytestmark = pytest.mark.cloud
UI = os.environ.get("KG_UIUX_DIR", "")


@pytest.fixture(scope="module")
def page():
    if not UI:
        pytest.skip("set KG_UIUX_DIR")
    import asyncio
    import sys
    from playwright.sync_api import sync_playwright
    prev = asyncio.get_event_loop_policy()
    if sys.platform == "win32":     # the Gremlin client switches to the selector loop, which cannot start the browser process
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        pg = b.new_page(viewport={"width": 1400, "height": 1800})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(pathlib.Path(UI, "knowledge-graph.html").as_uri() + "#rp")
        pg.wait_for_selector("#rp-meta:has-text('Live from Cosmos DB')", timeout=90000)
        pg.errors = errors
        yield pg
        b.close()
    asyncio.set_event_loop_policy(prev)


def test_tab_loads_live_graph_without_script_errors(page):
    assert page.locator("#rp-svg .kgf-node").count() > 10
    assert page.errors == []


def test_sdc_template_draws_module_and_pmc_nodes(page):
    page.select_option("#rp-tmpl", "sdc")
    page.wait_for_selector("#rp-meta:has-text('Live from Cosmos DB')", timeout=90000)
    page.wait_for_function("document.querySelector('#rp-legend').innerText.includes('PMCProcess')", timeout=90000)
    assert "SDCModule" in page.inner_text("#rp-legend")


def test_validate_button_shows_rows_from_the_database(page):
    page.click("#rp-v-go")
    page.wait_for_selector("#rp-v-out table", timeout=120000)
    assert "rows on" in page.inner_text("#rp-v-out")


def test_ask_button_returns_validated_sql_and_evidence_graph(page):
    page.click("#rp-ask-go")
    page.wait_for_selector("#rp-ask-out .chip", timeout=240000)
    assert "validated" in page.inner_text("#rp-ask-out .chip")
    page.click("#rp-ask-out [data-ev]")
    page.wait_for_selector("#rp-meta:has-text('Evidence used')", timeout=30000)
    assert page.errors == []
