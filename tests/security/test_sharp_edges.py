"""Misuse resistance (sharp-edges review): the easy path must be the safe path."""

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError

from controlled_copy.config import ConfigError, Settings
from controlled_copy.providers.base import call_with_deadline
from controlled_copy.storage.db import transaction

pytestmark = [pytest.mark.security, pytest.mark.stage1]


def test_tc_acc_005_notebook_methods_refuse_a_raw_id(visitor, services):
    with pytest.raises(TypeError, match="OwnedNotebook"):
        services.repo.list_sources(visitor.notebook_id)
    with pytest.raises(TypeError):
        services.repo.list_turns(visitor.notebook_id)
    other_session = "not-the-owner"
    assert services.repo.get_notebook(other_session, visitor.notebook_id) is None


@pytest.mark.parametrize(
    "change",
    [
        {"evidence_floor": 0},
        {"evidence_floor": 1},
        {"retention_hours": -1},
        {"retention_hours": 0},
        {"max_file_bytes": 0},
        {"provider_timeout_seconds": 0},
        {"max_sources_per_notebook": -5},
    ],
)
def test_tc_sec_004_configuration_cliffs_are_rejected_at_load(tmp_path, change):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_access_code="x", model_provider="fake", data_dir=tmp_path, **change)


def test_tc_sec_004_api_key_never_goes_over_plain_http(tmp_path):
    settings = Settings(
        _env_file=None,
        app_access_code="x",
        openrouter_api_key="k",
        openrouter_base_url="http://openrouter.example/api/v1",
        data_dir=tmp_path,
    )
    with pytest.raises(ConfigError, match="https"):
        settings.check_startup()
    local = settings.model_copy(update={"openrouter_base_url": "http://127.0.0.1:8080/v1"})
    local.check_startup()


def test_tc_sec_004_deadline_requires_a_positive_timeout():
    with pytest.raises(ValueError, match="positive"):
        call_with_deadline(lambda: 1, 0)
    assert call_with_deadline(lambda: 1, 1) == 1


def test_tc_sec_004_nested_transactions_become_savepoints(db):
    db.execute("CREATE TABLE t (x INTEGER)")
    with transaction(db):
        db.execute("INSERT INTO t VALUES (1)")
        with pytest.raises(RuntimeError), transaction(db):
            db.execute("INSERT INTO t VALUES (2)")
            raise RuntimeError("inner fails")
        with transaction(db):
            db.execute("INSERT INTO t VALUES (3)")
    assert [r[0] for r in db.execute("SELECT x FROM t ORDER BY x")] == [1, 3]


def test_tc_sec_002_every_write_route_requires_the_csrf_token(app, visitor):
    from controlled_copy.web.routes import router

    routes = list(router.routes) + [r for layer in app.state.registry.routers for r in layer.routes]
    checked = 0
    for route in routes:
        if not isinstance(route, APIRoute) or route.path == "/access":
            continue
        for method in route.methods & {"POST", "PUT", "PATCH", "DELETE"}:
            path = (
                route.path.replace("{notebook_id}", visitor.notebook_id)
                .replace("{source_id}", "x")
                .replace("{template_id}", "briefing")
            )
            response = visitor.client.request(method, path)
            assert response.status_code == 403, f"{method} {route.path} -> {response.status_code}"
            checked += 1
    assert checked >= 6
