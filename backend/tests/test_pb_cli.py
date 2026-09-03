"""Pure parts of the pb client: env parsing and the human-readable diff."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import pb  # noqa: E402


def test_load_env_parses_and_ignores_comments(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# comment\nRESEARCH_API_TOKEN=abc123\n\nexport VPS_HOST=example.com\n")
    env = pb.load_env(f)
    assert env["RESEARCH_API_TOKEN"] == "abc123"
    assert env["VPS_HOST"] == "example.com"


def test_load_env_strips_quotes(tmp_path):
    f = tmp_path / ".env"
    f.write_text('RESEARCH_API_TOKEN="quoted"\n')
    assert pb.load_env(f)["RESEARCH_API_TOKEN"] == "quoted"


def test_format_report_marks_a_dry_run_and_lists_changes():
    out = pb.format_report({
        "dry_run": True, "request_id": 7, "status": "new",
        "tables": {"entity": {"created": 2, "updated": 1, "unchanged": 0, "skipped": 0}},
        "changes": [{"table": "entity", "key": "175376051", "field": "founded_year",
                     "from": None, "to": 2008}],
        "warnings": ["heads up"],
    })
    assert "DRY RUN" in out and "nothing was written" in out
    assert "entity" in out and "created 2" in out
    assert "founded_year" in out and "2008" in out
    assert "heads up" in out


def test_format_report_marks_an_applied_push():
    out = pb.format_report({"dry_run": False, "request_id": 7, "status": "delivered",
                            "tables": {}, "changes": [], "warnings": []})
    assert "APPLIED" in out and "delivered" in out


def test_format_report_never_prints_the_token():
    out = pb.format_report({"dry_run": True, "request_id": None, "status": None,
                            "tables": {}, "changes": [], "warnings": []})
    assert "TOKEN" not in out.upper()
