"""The Resolution Card as Markdown: status and reasons first, then the situation, the
typed statements with citation numbers, the applicability tables and the verified quotes."""

from __future__ import annotations

from typing import Any

from controlled_copy.web.markdown import citations_md, clean, footer_md, sections_md, table


def _labelled(document: dict[str, Any]) -> str:
    asserted = " (asserted by uploader)" if document.get("origin") == "asserted" else ""
    return str(document.get("label", "")) + asserted


def card_markdown(output: dict[str, Any], created_at: str) -> str:
    card = output.get("card", {})
    ctx = card.get("context", {})
    lines = [
        "# Resolution Card",
        "",
        f"**Status: {clean(card.get('status_label'))}**",
        "",
        *[f"- {clean(reason)}" for reason in card.get("reasons", [])],
        "",
        f"**Situation:** {clean(card.get('situation'))}",
        "",
        "**Context:** site {} · {} · as of {}".format(
            clean(ctx.get("site")), clean(ctx.get("role", "")).replace("_", " "), clean(ctx.get("as_of"))
        ),
    ]
    if card.get("identifiers"):
        line = "**Identifiers:** " + ", ".join(clean(i) for i in card["identifiers"])
        if card.get("undocumented"):
            line += " (not covered by an applicable approved document: "
            line += ", ".join(clean(i) for i in card["undocumented"]) + ")"
        lines += ["", line]
    for warning in card.get("warnings", []):
        lines += [
            "",
            f"> **Not applied: {clean(warning.get('label'))}** ({clean(warning.get('reason'))}):"
            f' "{clean(warning.get("excerpt"))}"',
        ]
    lines += sections_md(output)
    used = card.get("used", [])
    excluded = card.get("excluded", [])
    if used or excluded or card.get("consulted"):
        lines += ["", "## Applicability"]
    if used:
        rows = [
            [_labelled(d), d.get("status"), d.get("effective") or "-", d.get("site") or "-"] for d in used
        ]
        lines += ["", *table(["Used", "Status", "Effective", "Site"], rows)]
    if card.get("consulted"):
        names = ", ".join(clean(d.get("label")) for d in card["consulted"])
        lines += ["", f"Also given to the model, not cited: {names}"]
    if excluded:
        rows = [[_labelled(d), d.get("reason")] for d in excluded]
        lines += ["", *table(["Not applied", "Reason"], rows)]
    lines += citations_md(output)
    lines += footer_md(output, created_at)
    return "\n".join(lines).strip() + "\n"
