from __future__ import annotations

from pathlib import Path

from dcc_mcp_core import validate_skill

ROOT = Path(__file__).resolve().parents[1]


def test_skill_contract_has_no_validation_errors() -> None:
    report = validate_skill(str(ROOT / "skill" / "modeling-spec"))

    assert not report.has_errors, report
