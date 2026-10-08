"""FR-GOV-09: the card's date defaults to today in Germany, like the chat (stage 2)."""

from datetime import UTC, date, datetime

import pytest

from controlled_copy import clock
from controlled_copy.governance.routes import default_context

pytestmark = [pytest.mark.integration, pytest.mark.stage2]

# 00:30 on 9 October in Germany, still 8 October in UTC.
AFTER_MIDNIGHT_IN_GERMANY = datetime(2026, 10, 8, 22, 30, tzinfo=UTC)


@pytest.fixture
def after_midnight(monkeypatch):
    monkeypatch.setattr(clock, "utc_now", lambda: AFTER_MIDNIGHT_IN_GERMANY)


def test_tc_gov_010_a_card_without_a_date_uses_today_in_germany(after_midnight):
    context = default_context([], site="HAM-01", role="warehouse_operator", as_of="")
    assert context.as_of == date(2026, 10, 9)


def test_tc_gov_010_the_card_form_starts_at_today_in_germany(after_midnight, workspace):
    workspace.refresh()
    assert 'id="card-date" name="as_of" type="date" value="2026-10-09"' in workspace.page
