"""FR-OUT-02: a Studio output prints as a page stamped as an uncontrolled copy, with its
quotes listed; only the owner can open it (stage 1)."""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.stage1]

SOURCE = "Inbound trucks are unloaded at dock two. Damaged pallets are photographed. The shift lead confirms every recount."


def briefing(visitor):
    visitor.paste("Dock rules", SOURCE)
    body = visitor.briefing().json()
    return body["output_id"], body["output"]


def test_tc_out_002_a_briefing_prints_with_the_stamp_and_its_quotes(visitor):
    output_id, output = briefing(visitor)
    url = f"/notebooks/{visitor.notebook_id}/outputs/{output_id}/print"
    assert f'href="{url}"' in visitor.refresh().page, "every output offers Print"
    response = visitor.client.get(url)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    page = response.text
    assert "Printed copy: uncontrolled." in page and "check the current revision" in page
    assert "data-autoprint" in page
    for section in output["sections"]:
        assert section["title"] in page
    for citation in output["citations"]:
        assert f'<li value="{citation["n"]}">' in page
        assert citation["quote"].split()[0] in page
    # Paper has no viewer: citations are plain numbers, not buttons that open a passage.
    assert 'class="cite cite--plain"' in page and "#viewer-slot" not in page
    # The workspace prints this page in a hidden frame, so this site, and only it, may frame it.
    assert "frame-ancestors 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    workspace = visitor.client.get("/app")
    assert "frame-ancestors 'none'" in workspace.headers["content-security-policy"]
    assert workspace.headers["x-frame-options"] == "DENY"


def test_tc_out_002_another_visitor_cannot_print_it(make_visitor):
    alice, bob = make_visitor(), make_visitor()
    output_id, _ = briefing(alice)
    assert bob.client.get(f"/notebooks/{alice.notebook_id}/outputs/{output_id}/print").status_code == 404
    assert alice.client.get(f"/notebooks/{alice.notebook_id}/outputs/nope/print").status_code == 404
