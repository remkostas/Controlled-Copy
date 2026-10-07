"""FR-RET-01: rank fusion."""

import pytest

from controlled_copy.retrieval.search import RRF_K, extract_identifiers, fts_query, rrf

pytestmark = [pytest.mark.unit, pytest.mark.stage1]


def test_tc_ret_001_fused_order_matches_reciprocal_rank_formula():
    fts = [10, 20, 30]
    vec = [30, 40, 10]
    fused = dict(rrf([fts, vec]))
    assert fused[10] == pytest.approx(1 / (RRF_K + 1) + 1 / (RRF_K + 3))
    assert fused[30] == pytest.approx(1 / (RRF_K + 3) + 1 / (RRF_K + 1))
    assert fused[20] == pytest.approx(1 / (RRF_K + 2))
    assert fused[40] == pytest.approx(1 / (RRF_K + 2))
    order = [item for item, _ in rrf([fts, vec])]
    assert order[:2] == [10, 30]  # tie broken by ID, deterministic
    assert set(order) == {10, 20, 30, 40}


def test_tc_ret_001_fts_query_is_quoted_and_safe():
    import sqlite3

    query = fts_query('What does GR-204 mean? "DROP" AND NEAR(x) * col:value')
    assert '"gr 204"' in query
    assert '"drop"' in query
    assert all(t.startswith('"') and t.endswith('"') and t.count('"') == 2 for t in query.split(" OR "))
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(body, tokenize = 'porter unicode61')")
    conn.execute("INSERT INTO t VALUES ('error GR-204 means the quantity is too high')")
    assert conn.execute("SELECT count(*) FROM t WHERE t MATCH ?", (query,)).fetchone()[0] == 1


def test_tc_ret_001_identifiers_are_extracted():
    assert extract_identifiers("Error GR-204 and SOP-INB-001, not 2026") == ["GR-204", "SOP-INB-001"]
