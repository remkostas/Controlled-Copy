"""FR-OUT-01 for the Resolution Card; layer-off behaviour (stage 3 on the governed layer)."""

import pytest
from fastapi.testclient import TestClient

from controlled_copy.app import create_app
from controlled_copy.governance.markdown import card_markdown
from controlled_copy.providers.fake import FakeProvider
from tests.helpers.cards import card_responder, empty_card, passage_with

pytestmark = [pytest.mark.integration, pytest.mark.stage3]


def supported_card(workspace, fake):
    def build(request):
        pid, quote = passage_with(
            request, "post only the open quantity after the shift lead has confirmed the count"
        )
        return empty_card(
            required_actions=[
                {
                    "type": "requirement",
                    "text": "Post only the | open quantity.",
                    "citations": [{"passage_id": pid, "quote": quote}],
                }
            ]
        )

    fake.responder = card_responder(build)
    return workspace.card("The WMS shows error GR-204 after I scan the delivery.").json()


def test_tc_out_001_the_card_exports_status_items_applicability_and_quotes(workspace, fake):
    body = supported_card(workspace, fake)
    url = f"/notebooks/{workspace.id}/outputs/{body['output_id']}.md"
    text = workspace.visitor.client.get(url).text
    assert text.startswith("# Resolution Card\n")
    assert "**Status: Supported by an approved instruction**" in text
    assert "**Context:** site HAM-01 · warehouse operator · as of 2026-10-07" in text
    assert "- **Requirement:** Post only the | open quantity. [1]" in text
    assert "> **Not applied: SOP-INB-001 rev 2** (obsolete)" in text
    assert "| Not applied | Reason |" in text and "| SOP-INB-001 rev 2 | obsolete |" in text
    assert "[1] GUIDE-WMS-003 rev 1" in text or "[1] SOP-INB-001 rev 3" in text
    quote = body["output"]["citations"][0]["quote"]
    assert " ".join(quote.split()) in text


def test_table_cells_escape_pipes():
    output = {
        "card": {
            "status_label": "Supported",
            "context": {},
            "excluded": [{"label": "A|B", "reason": "x | y", "origin": "asserted"}],
        }
    }
    text = card_markdown(output, "2026-10-06T10:00:00+00:00")
    assert "| A\\|B (asserted by uploader) | x \\| y |" in text


def test_tc_out_002_a_card_is_not_exported_with_the_layer_off(workspace, fake, settings):
    body = supported_card(workspace, fake)
    url = f"/notebooks/{workspace.id}/outputs/{body['output_id']}.md"
    cookies = dict(workspace.visitor.client.cookies)
    off = create_app(
        settings.model_copy(update={"feature_governance": False}), FakeProvider(), run_purge=False
    )
    with TestClient(off, cookies=cookies) as client:
        assert client.get(url).status_code == 404
