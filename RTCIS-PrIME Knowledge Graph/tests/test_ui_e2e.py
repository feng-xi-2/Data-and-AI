"""Browser end-to-end tests of the WHS GenAI UI with the real API (Edge via Playwright):
- knowledge-graph.html, tab "Semantic Layer . RTCIS <-> PrIME 2014 <-> 2022": graph templates read live from Cosmos;
- assistant.html?id=sql-query-convertor: the one-box SQL Remediation dialog (question / SQL / convert / batch) on the
  replicas through the cloud model.
    KG_UIUX_DIR=<UIUX> [KG_E2E_API=http://127.0.0.1:8738] python -m pytest tests/test_ui_e2e.py -m cloud"""
import asyncio
import os
import pathlib
import sys

import pytest

pytestmark = pytest.mark.cloud
UI = os.environ.get("KG_UIUX_DIR", "")
API = os.environ.get("KG_E2E_API", "http://127.0.0.1:8738")


@pytest.fixture(scope="module")
def browser():
    if not UI:
        pytest.skip("set KG_UIUX_DIR")
    from playwright.sync_api import sync_playwright
    prev = asyncio.get_event_loop_policy()
    if sys.platform == "win32":     # the Gremlin client switches to the selector loop, which cannot start the browser process
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        yield b
        b.close()
    asyncio.set_event_loop_policy(prev)


def open_page(browser, path):
    pg = browser.new_page(viewport={"width": 1400, "height": 1800})
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.add_init_script(f"localStorage.setItem('rp_api', '{API}')")
    pg.goto(pathlib.Path(UI, path.split("?")[0].split("#")[0]).as_uri() + path[len(path.split("?")[0].split("#")[0]):])
    return pg


@pytest.fixture(scope="module")
def graph_page(browser):
    pg = open_page(browser, "knowledge-graph.html#rp")
    pg.wait_for_selector("#rp-meta:has-text('Live from Cosmos DB')", timeout=90000)
    yield pg
    pg.close()


@pytest.fixture(scope="module")
def sr_page(browser):
    pg = open_page(browser, "assistant.html?id=sql-query-convertor")
    pg.wait_for_selector("#sr-cfg:has-text('model')", timeout=60000)
    yield pg
    pg.close()


# ---- Knowledge Graph page ------------------------------------------------------------------------------------
def test_graph_tab_loads_live_from_cosmos_and_has_no_dialog(graph_page):
    assert graph_page.locator("#rp-svg .kgf-node").count() > 10
    assert graph_page.locator("#rp-text").count() == 0 and graph_page.locator("#kgtab-rp a[href*='sql-query-convertor']").count() == 1
    assert graph_page.errors == []


def test_semantic_layer_template_draws_concepts_and_tables(graph_page):
    graph_page.select_option("#rp-tmpl", "semantic")
    graph_page.select_option("#rp-key", "location")
    graph_page.click("#rp-load")
    graph_page.wait_for_function("(t => t.includes('table') && t.includes('SemanticConcept'))(document.querySelector('#rp-legend').innerText)",
                                 timeout=90000)
    assert "MAPPED_FROM" in graph_page.text_content("#rp-svg")


def test_sidebar_has_one_knowledge_graph_entry(graph_page):
    side = graph_page.inner_text("#app-sidebar")
    assert "Semantic Layer & Knowledge Graph" in side and "RTCIS \u2194 PrIME Graph" not in side


# ---- SQL Remediation assistant: one box ----------------------------------------------------------------------
def _send(page, text, site, dst=""):
    page.select_option("#sr-site", site)
    page.select_option("#sr-dst", dst)
    page.fill("#sr-text", text)
    n = page.locator("#sr-thread .sr-turn").count()
    page.click("#sr-go")
    page.wait_for_function(f"document.querySelectorAll('#sr-thread .sr-turn').length > {n}")
    turn = page.locator("#sr-thread .sr-turn").first
    turn.locator(".sr-out .chip").first.wait_for(timeout=400000)
    return turn


def test_one_box_validates_sql_on_the_run_site(sr_page):
    t = _send(sr_page, "SELECT TOP 5 LODNUM, STOLOC FROM dbo.invlod WHERE WH_ID = @wh_id", "PRIME22_DE08")
    assert "validate" in t.inner_text() and "rows on" in t.inner_text()


def test_one_box_asks_a_question_with_evidence_links(sr_page):
    t = _send(sr_page, "How many pallets (loads) are stored per location area?", "PRIME22_DE08")
    assert "validated" in t.inner_text()
    assert t.locator("a[href*='knowledge-graph.html#rp:versions:']").count() >= 1


def test_one_box_converts_rtcis_sql_to_prime(sr_page):
    t = _send(sr_page, "SELECT equip, equip_desc FROM [EUSKIRCHEN_simp].live3.equip", "RTCIS_EUS", "PRIME22_DE08")
    assert "convert" in t.inner_text() and "Column contract" in t.inner_text()


def test_one_box_runs_several_questions_as_a_batch_and_offers_download(sr_page):
    t = _send(sr_page, "How many locations per area?\nHow many loads per area?", "PRIME22_DE08")
    assert "batch ask" in t.inner_text() and t.locator(".sr-item").count() == 2
    assert sr_page.is_enabled("#sr-csv") and sr_page.errors == []
