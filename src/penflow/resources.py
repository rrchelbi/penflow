"""The guide and the Claude Code skill, from the installed package or from a source checkout."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

SKILL_NAME = "penflow-diagrams"
_CHECKOUT = Path(__file__).resolve().parents[2]


def _read(*parts: str) -> str:
    # A wheel ships docs/ and skills/ under penflow/_data (see pyproject.toml); a checkout has them at the root.
    packaged = resources.files("penflow").joinpath("_data", *parts)
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    return _CHECKOUT.joinpath(*parts).read_text(encoding="utf-8")


def guide() -> str:
    """The guide for drawing diagrams with Penflow (docs/guide.md)."""
    return _read("docs", "guide.md")


def skill() -> str:
    """The Claude Code skill for drawing diagrams (skills/penflow-diagrams/SKILL.md)."""
    return _read("skills", SKILL_NAME, "SKILL.md")


def install_skill(skills_dir: Path, force: bool = False) -> Path:
    """Write the skill to `skills_dir/penflow-diagrams/SKILL.md`. An edited copy is only replaced with `force`."""
    target = skills_dir / SKILL_NAME / "SKILL.md"
    text = skill()
    if target.exists() and target.read_text(encoding="utf-8") != text and not force:
        raise FileExistsError(f"{target} exists and differs from this version; pass --force to replace it")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    return target
