"""FR-OUT-02 for the Resolution Card: the printed card keeps its status, situation, context and
applicability under the uncontrolled-copy stamp (stage 2)."""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.stage2]


def test_tc_out_002_a_card_prints_with_its_status_and_applicability(workspace):
    body = workspace.card("The WMS shows error GR-204 after I scan the delivery.").json()
    page = workspace.visitor.client.get(f"/notebooks/{workspace.id}/outputs/{body['output_id']}/print").text
    assert "Printed copy: uncontrolled." in page
    assert body["output"]["card"]["status_label"] in page
    assert "The WMS shows error GR-204" in page and "as of 2026-10-07" in page
    assert "<h3>Applicability</h3>" in page
    assert "#viewer-slot" not in page, "no buttons that would open a passage on paper"
