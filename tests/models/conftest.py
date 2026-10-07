"""Stage 3 fixtures: the app with the model picker layer switched on."""

from __future__ import annotations

import pytest

from controlled_copy.config import Settings


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"feature_model_picker": True})
