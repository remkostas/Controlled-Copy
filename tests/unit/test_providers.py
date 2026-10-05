"""FR-IDX-03: requests to OpenRouter carry the privacy flags."""

import pytest

from controlled_copy.providers.openrouter import build_chat_request, build_embedding_request

pytestmark = [pytest.mark.unit, pytest.mark.stage1]


def test_tc_idx_003_embedding_request_uses_bge_m3_with_privacy_flags_and_batches():
    body = build_embedding_request(["one", "two", "three"], "baai/bge-m3")
    assert body["model"] == "baai/bge-m3"
    assert body["input"] == ["one", "two", "three"]
    assert body["provider"]["zdr"] is True
    assert body["provider"]["data_collection"] == "deny"


def test_tc_idx_003_embeddings_are_sent_in_batches(services, fake):
    from controlled_copy.ingestion.pipeline import embed_texts

    services.settings.embedding_batch_size = 2
    vectors = embed_texts(services, ["a b", "c d", "e f", "g h", "i j"])
    assert len(vectors) == 5
    assert fake.embed_calls == 3


def test_tc_idx_003_chat_request_requires_schema_support_and_privacy():
    body = build_chat_request([{"role": "user", "content": "q"}], {"type": "object"}, "answer", "m")
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["provider"] == {"zdr": True, "data_collection": "deny", "require_parameters": True}
