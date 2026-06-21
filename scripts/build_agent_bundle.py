#!/usr/bin/env python3
"""Build the downloadable agent bundle: dist/makeitdown-agent.zip.

The bundle is a clean, self-contained, installable copy that a non-technical
user can download and hand to their AI agent. It contains the installable
package (src + pyproject), the agent skill (SKILL.md at the bundle root), a
human one-pager, and the README. Because the source is included, the agent can
install directly from the unzipped folder — no dependency on the Gitee/GitHub
code mirror (third-party PyPI deps still download as usual).

Run from anywhere: ``python scripts/build_agent_bundle.py``.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUNDLE = "makeitdown-agent"

# Single files: (path relative to repo root) -> (path inside the bundle).
FILES = {
    "pyproject.toml": "pyproject.toml",
    "README.md": "README.md",
    "skill/makeitdown/SKILL.md": "SKILL.md",
    "给你的AI助手.md": "给你的AI助手.md",
}
# Whole directories copied verbatim (minus caches).
DIRS = {"src": "src"}


def _members():
    for src_rel, arc_rel in FILES.items():
        yield ROOT / src_rel, f"{BUNDLE}/{arc_rel}"
    for src_rel, arc_rel in DIRS.items():
        base = ROOT / src_rel
        for p in sorted(base.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                yield p, f"{BUNDLE}/{arc_rel}/{p.relative_to(base).as_posix()}"


def main() -> None:
    missing = [s for s in FILES if not (ROOT / s).exists()]
    if missing:
        raise SystemExit(f"missing bundle inputs: {missing}")
    DIST.mkdir(exist_ok=True)
    out = DIST / f"{BUNDLE}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path, arc in _members():
            z.write(path, arc)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    with zipfile.ZipFile(out) as z:
        for name in z.namelist():
            print("  ", name)


if __name__ == "__main__":
    main()
