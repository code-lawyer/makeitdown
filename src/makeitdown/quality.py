"""Heuristic quality checks for converted Markdown.

Pure, dependency-free, and non-destructive: ``assess`` only *reports* suspect
output, it never modifies content. Every reason string carries the measured
value so a human can judge the flag. Defaults are deliberately conservative
(prefer missing a problem over crying wolf).
"""

from dataclasses import dataclass


@dataclass
class QualityThresholds:
    min_chars: int = 20
    min_chars_per_page: int = 50
    garbled_ratio: float = 0.02
    repeat_count: int = 30


# Punctuation treated as legitimate content, so it never counts as "garbled".
_ALLOWED_PUNCT = set(
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"               # ASCII punctuation
    "，。、；：？！“”‘’（）《》【】〈〉「」『』…—–·～％"   # common CJK punctuation
)


def _non_ws_count(text: str) -> int:
    return sum(1 for c in text if not c.isspace())


def _is_garbled_char(c: str) -> bool:
    # Letters, digits and CJK ideographs are all alphanumeric; whitespace and
    # known punctuation are legitimate. Anything else (replacement chars,
    # control bytes, stray symbols) is treated as garble.
    return not (c.isspace() or c.isalnum() or c in _ALLOWED_PUNCT)


def assess(
    text: str,
    *,
    source_type: str,
    pages: int | None = None,
    thresholds: QualityThresholds | None = None,
) -> list[str]:
    """Return human-readable warning reasons for suspect output; [] if clean.

    Each reason string is a stable user-facing format consumed verbatim by
    report.json, the .md frontmatter, and the console. If these ever need to be
    machine-filtered or localized, switch to structured reasons + an edge
    formatter rather than parsing these strings.
    """
    thresholds = thresholds or QualityThresholds()
    reasons: list[str] = []

    non_ws = _non_ws_count(text)

    # near-empty
    if non_ws < thresholds.min_chars:
        reasons.append(f"near-empty output ({non_ws} chars)")

    # low chars per page — only meaningful for genuinely multi-page documents;
    # a short single page is plausibly legitimate.
    if pages and pages >= 2:
        avg = non_ws // pages
        if avg < thresholds.min_chars_per_page:
            reasons.append(f"avg {avg} chars/page over {pages} pages")

    # garbled ratio
    if non_ws > 0:
        bad = sum(1 for c in text if _is_garbled_char(c))
        ratio = bad / non_ws
        if ratio > thresholds.garbled_ratio:
            reasons.append(f"garbled-char ratio {ratio * 100:.1f}%")

    # runaway repetition (ignore short lines like table separators)
    counts: dict[str, int] = {}
    for line in text.split("\n"):
        s = line.strip()
        if len(s) > 10:
            counts[s] = counts.get(s, 0) + 1
    if counts:
        _, n = max(counts.items(), key=lambda kv: kv[1])
        if n > thresholds.repeat_count:
            reasons.append(f"line repeated {n}x (possible OCR loop)")

    return reasons
