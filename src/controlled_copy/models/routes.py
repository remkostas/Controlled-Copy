"""HTTP route of the model picker layer."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, Response

from controlled_copy.logs import log_event
from controlled_copy.models import label
from controlled_copy.storage.db import transaction
from controlled_copy.web.deps import WriteDep, wants_json
from controlled_copy.web.routes import notice, render

router = APIRouter()


@router.post("/settings/model")
def choose_model(
    request: Request, services: WriteDep, model: Annotated[str, Form(max_length=120)] = ""
) -> Response:
    settings = services.settings
    if model not in settings.model_choice_list:
        return notice(request, "That model is not available here.", 422, "#toast")
    conn = services.repo.conn
    with transaction(conn):
        conn.execute(
            "INSERT INTO model_choice (session_id, model) VALUES (?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET model = excluded.model",
            (services.sid, model),
        )
    log_event("model_chosen", session=services.sid, model=model)
    if wants_json(request):
        return JSONResponse({"model": model})
    return render(request, "models/model_saved.html", {"label": label(model)})
