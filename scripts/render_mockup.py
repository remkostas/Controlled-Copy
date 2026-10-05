"""Render the static UI mock-up from the real templates with fixture data.

Usage: python scripts/render_mockup.py  (writes docs/mockup/*.html)
The pages reference the real stylesheet, fonts and icons, so the mock-up shows
exactly what the app renders. Serve the repository root over HTTP to view it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

from markupsafe import Markup

from controlled_copy.web.render import make_environment
from controlled_copy.web.segments import build_segments

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "mockup"
CORPUS = ROOT / "demo-data" / "inbound-operations"


def body_of(name: str) -> str:
    text = (CORPUS / name).read_text(encoding="utf-8")
    return text.split("---\n", 2)[2].lstrip("\n")


def cite(n, sid, label, deleted=False):
    return NS(n=n, url=f"/sources/{sid}?start=0&end=10", label=label, deleted=deleted)


def main() -> None:
    env = make_environment(static_prefix="../../src/controlled_copy/web/static/")
    OUT.mkdir(parents=True, exist_ok=True)

    sop3 = NS(
        id="s1",
        title="Inbound Receiving Procedure",
        kind="md",
        kind_label="Markdown",
        size_label="14 sections",
        warnings=[],
        meta=NS(document_id="SOP-INB-001", revision="3", status="approved", effective_from="2026-01-01", site="HAM-01"),
        origin_label="Metadata asserted by uploader",
        origin_short="asserted by uploader",
        created_label="2026-10-06 07:12",
        superseded_by=None,
    )
    sources = [
        sop3,
        NS(
            id="s2",
            title="Inbound Receiving Procedure",
            kind="md",
            kind_label="Markdown",
            size_label="8 sections",
            warnings=[],
            meta=NS(document_id="SOP-INB-001", revision="2", status="obsolete", effective_from="2024-03-01", site="HAM-01"),
            origin_label="Metadata asserted by uploader",
            origin_short="asserted by uploader",
            created_label="2026-10-06 07:12",
            superseded_by="SOP-INB-001 rev 3",
        ),
        NS(
            id="s3",
            title="Forklift operating rules (scanned handbook)",
            kind="pdf",
            kind_label="PDF",
            size_label="12 pages",
            warnings=["2 pages without extractable text"],
            meta=None,
            origin_label="",
            origin_short="none",
            created_label="2026-10-06 07:14",
            superseded_by=None,
        ),
        NS(
            id="s4",
            title="Shift handover notes, week 41",
            kind="paste",
            kind_label="Pasted text",
            size_label="412 words",
            warnings=[],
            meta=None,
            origin_label="",
            origin_short="none",
            created_label="2026-10-06 07:15",
            superseded_by=None,
        ),
    ]
    sop_label = "SOP-INB-001 rev 3 · 4.2 Quantity check and tolerance"
    turns = [
        NS(
            id="t1",
            question="What is the quantity tolerance at goods receipt?",
            search_query=None,
            answer=NS(
                kind="answer",
                statements=[
                    NS(
                        text="Deviations of up to 2% of the ordered quantity or 2 units, whichever is smaller, are posted as counted with a note in the goods receipt.",
                        cites=[cite(1, "s1", sop_label)],
                    ),
                    NS(
                        text="Larger deviations are not posted until the shift lead has confirmed a recount; then the counted quantity is posted, never the ordered quantity.",
                        cites=[cite(1, "s1", sop_label), cite(2, "s1", "SOP-INB-001 rev 3 · 3 Responsibilities")],
                    ),
                ],
                gaps=[],
                cite_count=2,
                source_count=1,
                removed=0,
            ),
        ),
        NS(
            id="t2",
            question="And who tells purchasing about it?",
            search_query="Who informs purchasing about a confirmed quantity deviation at goods receipt?",
            answer=NS(
                kind="answer",
                statements=[
                    NS(
                        text="The shift lead informs purchasing about every confirmed short or over delivery.",
                        cites=[cite(1, "s1", sop_label)],
                    )
                ],
                gaps=["how quickly purchasing must react"],
                cite_count=1,
                source_count=1,
                removed=1,
            ),
        ),
        NS(
            id="t3",
            question="What is the forklift speed limit in the yard?",
            search_query=None,
            answer=NS(
                kind="refusal",
                searched_sources=4,
                search_query="What is the forklift speed limit in the yard?",
                reason="",
            ),
        ),
    ]
    outputs = [
        NS(
            id="o1",
            title="Briefing",
            meta_label="4 sources · 07:21",
            open=True,
            kind="ok",
            removed=0,
            sections=[
                NS(
                    title="Overview",
                    items=[
                        NS(
                            type_label=None,
                            text="The notebook describes how inbound deliveries are received at site HAM-01, from the truck to the goods receipt posting.",
                            cites=[cite(1, "s1", "SOP-INB-001 rev 3 · 1 Purpose")],
                        )
                    ],
                ),
                NS(
                    title="Key points",
                    items=[
                        NS(
                            type_label=None,
                            text="Quality-managed material always goes to quality inspection stock.",
                            cites=[cite(2, "s1", "SOP-INB-001 rev 3 · 4.3 Quality-managed material")],
                        ),
                        NS(
                            type_label=None,
                            text="WMS errors must never be bypassed by posting against a different order line.",
                            cites=[cite(3, "s1", "SOP-INB-001 rev 3 · 4.5 Goods receipt posting")],
                        ),
                    ],
                ),
                NS(
                    title="Important terms",
                    items=[
                        NS(
                            type_label=None,
                            text="Quality inspection stock: stock that only the QA inspector can release to unrestricted stock.",
                            cites=[cite(2, "s1", "SOP-INB-001 rev 3 · 4.3 Quality-managed material")],
                        )
                    ],
                ),
                NS(
                    title="Open questions",
                    items=[
                        NS(
                            type_label=None,
                            text="Revision 2 is still in the notebook although revision 3 supersedes it.",
                            cites=[cite(4, "s2", "SOP-INB-001 rev 2 · 6 Change history")],
                        )
                    ],
                ),
            ],
        )
    ]
    base = dict(
        product_name="Controlled Copy",
        tagline="A NotebookLM-style notebook for controlled documents",
        csrf_token="mockup",
        notebooks=[NS(id="nb1", title="Inbound receiving (my notes)"), NS(id="nb2", title="Supplier audit prep")],
        nb=NS(id="nb1", title="Inbound receiving (my notes)", kind="personal"),
        sources=sources,
        selected_ids={"s1", "s3", "s4"},
        turns=turns,
        outputs=outputs,
        notice=None,
        read_only=False,
        can_create_notebook=True,
        limits=NS(max_sources=20, max_file_mb=10, max_pdf_pages=150, question_chars=1500),
        ui=NS(
            topbar_partials=[],
            studio_actions=[
                NS(id="briefing", title="Briefing", description="Cited summary: overview, key points, terms, open questions", icon="list-checks", partial=None)
            ],
        ),
        pending=False,
        questions=[],
        initial_viewer=None,
    )
    workspace = env.get_template("workspace.html")
    (OUT / "workspace.html").write_text(workspace.render(**base), encoding="utf-8")

    text = body_of("SOP-INB-001_inbound-receiving_rev3.md")
    sentence = "Deviations of up to 2% of the ordered quantity or 2 units, whichever is smaller, are posted as counted with a note in the goods receipt."
    start = text.index(sentence)
    viewer = env.get_template("partials/viewer.html").render(
        s=sop3,
        segments=build_segments(text, (start, start + len(sentence)), markdown=True),
        focus_label=sop_label,
    )
    reading = dict(base, initial_viewer=Markup(viewer))  # noqa: S704 - rendered by our own autoescaping template
    (OUT / "workspace-viewer.html").write_text(workspace.render(**reading), encoding="utf-8")

    empty = dict(base, sources=[], selected_ids=set(), turns=[], outputs=[], nb=NS(id="nb3", title="Untitled notebook", kind="personal"))
    (OUT / "workspace-empty.html").write_text(workspace.render(**empty), encoding="utf-8")

    landing = env.get_template("landing.html")
    (OUT / "landing.html").write_text(
        landing.render(product_name=base["product_name"], tagline=base["tagline"], retention_days=7, error=None),
        encoding="utf-8",
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
