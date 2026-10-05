"""NFR-SEC-04: deploy mode refuses an insecure configuration."""

import pytest

from controlled_copy.app import create_app
from controlled_copy.config import AppMode, ConfigError, Settings

pytestmark = [pytest.mark.unit, pytest.mark.security, pytest.mark.stage1]

GOOD = dict(
    _env_file=None,
    app_mode=AppMode.DEPLOY,
    app_access_code="long-enough-code",
    app_secret_key="k" * 40,
    model_provider="openrouter",
    openrouter_api_key="test-key-not-real",
)


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"app_access_code": None}, "APP_ACCESS_CODE"),
        ({"app_secret_key": None}, "APP_SECRET_KEY"),
        ({"app_secret_key": "short"}, "APP_SECRET_KEY"),
        ({"app_debug": True}, "APP_DEBUG"),
        ({"model_provider": "fake"}, "fake model provider"),
        ({"openrouter_api_key": None}, "OPENROUTER_API_KEY"),
        ({"model_calls_per_day": 0}, "MODEL_CALLS_PER_DAY"),
    ],
)
def test_tc_sec_004_deploy_mode_refuses_insecure_configuration(tmp_path, change, fragment):
    settings = Settings(**{**GOOD, "data_dir": tmp_path, **change})
    with pytest.raises(ConfigError, match=fragment):
        create_app(settings, run_purge=False)


def test_tc_sec_004_secure_deploy_configuration_starts(tmp_path):
    app = create_app(Settings(**{**GOOD, "data_dir": tmp_path}), run_purge=False)
    assert app.state.settings.secure_cookies is True


def test_tc_sec_004_local_mode_still_needs_an_access_code(tmp_path):
    with pytest.raises(ConfigError, match="APP_ACCESS_CODE"):
        Settings(_env_file=None, model_provider="fake", data_dir=tmp_path).check_startup()
