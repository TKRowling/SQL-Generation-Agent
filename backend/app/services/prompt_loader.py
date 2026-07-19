from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class SkillPrompts:
    sql_rules: str
    summary_rules: str


SKILL_PATH = Path(__file__).resolve().parents[1] / "skills" / "askme-data-assistant" / "SKILL.md"


def _extract_section(text: str, name: str) -> str:
    pattern = re.compile(
        rf"<!--\s*{re.escape(name)}_START\s*-->(.*?)<!--\s*{re.escape(name)}_END\s*-->",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise RuntimeError(f"Missing {name} section in {SKILL_PATH}")
    return match.group(1).strip()


@lru_cache
def load_skill_prompts(max_rows: int) -> SkillPrompts:
    text = SKILL_PATH.read_text(encoding="utf-8")
    sql_rules = _extract_section(text, "SQL_RULES").replace("{{MAX_ROWS}}", str(max_rows))
    summary_rules = _extract_section(text, "SUMMARY_RULES").replace("{{MAX_ROWS}}", str(max_rows))
    return SkillPrompts(sql_rules=sql_rules, summary_rules=summary_rules)
