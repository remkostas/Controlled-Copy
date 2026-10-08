"""FR-STU-03: Studio templates are data."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from controlled_copy.studio import engine

pytestmark = [pytest.mark.unit, pytest.mark.stage1]


def test_tc_stu_003_template_files_validate_against_the_schema():
    files = sorted(engine.TEMPLATE_DIR.glob("*.json"))
    assert files, "at least one template file"
    for path in files:
        template = engine.load_template(path)
        schema = template.schema()
        assert schema["required"] == [s.key for s in template.sections]
        assert template.output_model().model_fields.keys() == {s.key for s in template.sections}


def test_tc_stu_003_invalid_template_is_rejected(tmp_path: Path):
    bad = json.loads((engine.TEMPLATE_DIR / "briefing.json").read_text())
    bad["sections"][0]["key"] = "Not A Key"
    bad["unexpected"] = True
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(ValidationError):
        engine.load_template(path)


def test_tc_stu_003_no_template_specific_code_path():
    source = Path(engine.__file__).read_text() + Path(engine.__file__).with_name("actions.py").read_text()
    for template_id in engine.core_templates():
        assert f'"{template_id}"' not in source and f"'{template_id}'" not in source


def test_tc_stu_003_descriptions_say_studio_reads_the_sources():
    # First-time users could not tell whether Studio uses the chat or the sources (issue #13).
    for path in sorted(engine.TEMPLATE_DIR.glob("*.json")):
        description = engine.load_template(path).description
        assert description.startswith("From the selected sources: "), path.name
