"""FR-ANS-05: malformed model output is retried once, then a clear error."""

import json

import pytest

from controlled_copy.answering.answer import AnswerOut
from controlled_copy.answering.generate import GenerationError, generate, parse_payload
from controlled_copy.answering.prompts import ANSWER_SCHEMA
from controlled_copy.providers.base import ProviderBadOutput

pytestmark = [pytest.mark.unit, pytest.mark.stage1]

GOOD = {"statements": [], "unanswerable": ["nothing"]}


@pytest.mark.parametrize(
    "content", ["not json at all", '{"statements": "wrong type", "unanswerable": []}', "[]"]
)
def test_tc_ans_005_parse_rejects_non_json_and_schema_violations(content):
    with pytest.raises(ProviderBadOutput):
        parse_payload(content, AnswerOut)


def test_tc_ans_005_parse_accepts_fenced_json():
    payload = parse_payload("```json\n" + json.dumps(GOOD) + "\n```", AnswerOut)
    assert payload.unanswerable == ["nothing"]


def test_tc_ans_005_one_retry_then_success(services, fake):
    replies = iter(["garbage", json.dumps(GOOD)])
    fake.responder = lambda request: next(replies)
    payload, result = generate(
        services,
        [{"role": "user", "content": "q"}],
        schema=ANSWER_SCHEMA,
        schema_name="answer",
        model_cls=AnswerOut,
    )
    assert payload.unanswerable == ["nothing"]
    assert [c.model for c in fake.chat_calls] == [
        services.settings.model_generation,
        services.settings.model_generation_fallback,
    ]
    assert result.model == services.settings.model_generation_fallback


def test_tc_ans_005_two_malformed_outputs_give_a_clear_error_without_content(services, fake):
    fake.responder = lambda request: "SECRET-CANARY not json"
    with pytest.raises(GenerationError) as error:
        generate(
            services,
            [{"role": "user", "content": "q"}],
            schema=ANSWER_SCHEMA,
            schema_name="answer",
            model_cls=AnswerOut,
        )
    assert error.value.status == 502
    assert "unexpected format" in error.value.message
    assert "SECRET-CANARY" not in error.value.message
    assert len(fake.chat_calls) == 2
