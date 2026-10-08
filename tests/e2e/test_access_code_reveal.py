"""FR-ACC-07: the access code can be shown while typing, and the form still works (stage 1)."""

import pytest

from tests.conftest import ACCESS_CODE

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]


def test_tc_acc_007_show_and_hide_the_access_code(page, server_url):
    page.goto(server_url + "/")
    page.fill("#access-code", ACCESS_CODE)
    toggle = page.get_by_role("button", name="Show")
    assert toggle.is_visible() and toggle.get_attribute("aria-pressed") == "false"
    toggle.click()
    assert page.get_attribute("#access-code", "type") == "text"
    assert page.get_attribute("[data-reveal]", "aria-pressed") == "true"
    assert page.locator("[data-reveal]").inner_text() == "Hide"
    page.click("[data-reveal]")
    assert page.get_attribute("#access-code", "type") == "password"
    page.click("button[type=submit]")
    page.wait_for_url("**/app")
    assert page.js_errors == []
