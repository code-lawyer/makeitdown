import json
from dataclasses import dataclass


@dataclass
class Candidate:
    """A line that might be a heading, with its index into text.split('\\n')."""

    line_no: int
    text: str


def _is_table_row(stripped: str) -> bool:
    return stripped.startswith("|") or stripped.count("|") >= 2


def extract_heading_candidates(text: str, *, max_len: int = 80) -> list[Candidate]:
    """Cheap heuristic to pick lines that could be headings.

    Keeps non-blank lines whose stripped length is <= max_len and that are not
    table rows. Existing ``#`` heading lines are included too (so the LLM may
    re-level them). Body-looking short lines are kept as candidates on purpose;
    the LLM marks them level 0. Line numbers index ``text.split("\\n")``.
    """
    candidates: list[Candidate] = []
    for i, line in enumerate(text.split("\n")):
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) > max_len:
            continue
        if _is_table_row(stripped):
            continue
        candidates.append(Candidate(line_no=i, text=stripped))
    return candidates


def _heading_text(line: str) -> str:
    """The visible heading text, stripped of leading whitespace and # markers."""
    return line.lstrip().lstrip("#").strip()


def apply_heading_levels(text: str, levels: dict[int, int]) -> str:
    """Rebuild ``text`` applying ``{line_no: level}`` as ``#`` prefixes.

    Lines absent from ``levels`` are copied byte-for-byte. For lines present,
    any existing leading ``#`` markers are replaced (not stacked) by exactly
    ``level`` hashes plus a space. Only the heading marker is ever touched, so
    body content can never be altered.
    """
    lines = text.split("\n")
    for line_no, level in levels.items():
        if 0 <= line_no < len(lines):
            lines[line_no] = "#" * level + " " + _heading_text(lines[line_no])
    return "\n".join(lines)


_SYSTEM_PROMPT = (
    "You are a document structure analyzer. For each numbered line you are given, "
    "decide its Markdown heading level (1-6); use 0 for body text. "
    "Return ONLY JSON of the form {\"levels\": {\"<line_no>\": <level>}}. "
    "Never rewrite, translate, or output any of the text itself. "
    "If the document has no clear heading structure (e.g. chat logs, flat lists, "
    "forms, a single short notice), return all 0 (an empty levels object) and do "
    "not invent structure."
)


def _extract_json_object(raw: str) -> str:
    """Pull the JSON object out of an LLM reply.

    Models often wrap the JSON in ``` fences or surround it with prose, which
    breaks a strict ``json.loads``. Slicing from the first ``{`` to the last
    ``}`` recovers the object in those common cases.
    """
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        return raw[start:end + 1]
    return raw


class HeadingStructurer:
    """Re-levels Markdown headings via an LLM that returns only integer levels.

    The LLM never produces body text: ``restructure`` reads only a
    ``{line_no: level}`` map and applies it locally, so document content cannot
    be altered. Any failure, malformed response, oversized input, or excessive
    heading density falls back to the original text (optionally with a warning).
    Returns ``(text, engine_suffix | None, warning | None)``.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        max_heading_len: int = 80,
        max_input_lines: int = 1500,
        max_heading_ratio: float = 0.35,
        request_timeout: float = 60.0,
        completion_fn=None,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.max_heading_len = max_heading_len
        self.max_input_lines = max_input_lines
        self.max_heading_ratio = max_heading_ratio
        self.request_timeout = request_timeout
        self._completion_fn = completion_fn

    def restructure(self, text: str) -> tuple[str, str | None, str | None]:
        candidates = extract_heading_candidates(text, max_len=self.max_heading_len)
        if not candidates:
            return text, None, None
        if len(candidates) > self.max_input_lines:
            return text, None, (
                f"heading structuring skipped: too many candidate lines "
                f"({len(candidates)})"
            )
        try:
            raw = self._complete(self._build_messages(candidates))
            levels = self._parse_levels(raw, candidates)
        except Exception as exc:
            return text, None, f"heading structuring skipped: {type(exc).__name__}"

        if not levels:
            # Model judged everything body (e.g. a chat log): keep it flat.
            return text, None, None

        ratio = len(levels) / len(candidates)
        if ratio > self.max_heading_ratio:
            return text, None, (
                f"heading structuring skipped: too many headings "
                f"({round(ratio * 100)}%)"
            )

        return apply_heading_levels(text, levels), f"llm-heads:{self.model}", None

    def _build_messages(self, candidates: list[Candidate]) -> list[dict]:
        listing = "\n".join(f"{c.line_no}: {c.text}" for c in candidates)
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": listing},
        ]

    def _parse_levels(
        self, raw: str, candidates: list[Candidate]
    ) -> dict[int, int]:
        data = json.loads(_extract_json_object(raw))
        levels_raw = data.get("levels", data) if isinstance(data, dict) else {}
        valid_line_nos = {c.line_no for c in candidates}
        levels: dict[int, int] = {}
        for key, value in dict(levels_raw).items():
            try:
                line_no = int(key)
                level = int(value)
            except (TypeError, ValueError):
                continue
            if line_no in valid_line_nos and 1 <= level <= 6:
                levels[line_no] = level
        return levels

    def _complete(self, messages: list[dict]) -> str:
        if self._completion_fn is not None:
            return self._completion_fn(messages)
        return self._default_completion(messages)

    def _default_completion(self, messages: list[dict]) -> str:
        import requests

        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=self.request_timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
