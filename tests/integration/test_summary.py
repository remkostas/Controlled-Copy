"""FR-STU-07: a short, cited Summary, first in Studio and one click from the chat (stage 1)."""

import pytest

from controlled_copy.studio.engine import core_templates

pytestmark = [pytest.mark.stage1]


@pytest.mark.unit
def test_tc_stu_007_summary_is_the_first_studio_action():
    templates = list(core_templates())
    assert templates[0] == "summary"
    assert templates[1:] == sorted(templates[1:]), "the others keep their file-name order"


@pytest.mark.integration
def test_tc_stu_007_the_chat_offers_a_summary_once_there_are_sources(visitor):
    assert "data-chat-summary" not in visitor.refresh().page, "nothing to summarise yet"
    visitor.paste(
        "Dock rules", "Inbound trucks are unloaded at dock two. The shift lead confirms every recount."
    )
    page = visitor.refresh().page
    button = page.split("data-chat-summary", 1)[1].split("</button>", 1)[0]
    assert f'hx-post="/notebooks/{visitor.notebook_id}/studio/summary"' in button
    assert 'hx-include="#source-list-wrap"' in button and "Summarise the selected sources" in button
