"""FR-ANS-09 in the governed layer: the Resolution Card follows the language of the situation."""

import pytest

from controlled_copy.governance import card as card_module

pytestmark = [pytest.mark.unit, pytest.mark.stage2]


def test_tc_ans_009_the_card_follows_the_language_of_the_situation():
    """The card's labels stay English (interface); its statements follow the situation."""
    system = card_module.card_template().system
    assert "in English" not in system
    assert "language of the situation" in system
