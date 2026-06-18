from makeitdown.structure import (
    HeadingStructurer,
    apply_heading_levels,
    extract_heading_candidates,
)


def _structurer(fake, **kw):
    return HeadingStructurer("http://x", "k", "deepseek-chat", completion_fn=fake, **kw)


def test_extract_skips_blank_long_and_table_lines():
    text = "\n".join([
        "Short title",          # 0 -> candidate
        "",                     # 1 blank -> skip
        "   ",                  # 2 whitespace -> skip
        "| a | b |",            # 3 table row -> skip
        "x" * 200,              # 4 too long -> skip
        "## Existing heading",  # 5 existing # -> candidate
        "A normal short line",  # 6 short -> candidate (LLM decides if body)
    ])
    cands = extract_heading_candidates(text, max_len=80)
    assert [c.line_no for c in cands] == [0, 5, 6]
    assert cands[0].text == "Short title"


def test_apply_sets_and_relevels_without_stacking():
    text = "\n".join(["Title A", "body text", "## Sub"])
    out = apply_heading_levels(text, {0: 1, 2: 2})
    assert out.split("\n") == ["# Title A", "body text", "## Sub"]


def test_apply_preserves_body_bytes_and_heading_content():
    # Legal-critical: body lines (amounts/dates) must be byte-identical.
    text = "\n".join(["第一条 总则", "  缩进正文 5000元", "###  已有标题  ", "| t | b |", ""])
    levels = {0: 1, 2: 3}
    out = apply_heading_levels(text, levels).split("\n")
    src = text.split("\n")
    for i in (1, 3, 4):  # not in levels -> byte-identical
        assert out[i] == src[i]

    def core(s):
        return s.lstrip().lstrip("#").strip()

    for i in (0, 2):  # headings: content sans #/space preserved
        assert core(out[i]) == core(src[i])
        assert out[i].startswith("#")
    assert out[0] == "# 第一条 总则"
    assert out[2] == "### 已有标题"


def test_apply_is_lossless_round_trip():
    text = "line one\n## two\nthree 12345\n\nfour"
    levels = {0: 2, 1: 1, 2: 3}
    out = apply_heading_levels(text, levels)

    def core(s):
        return s.lstrip().lstrip("#").strip()

    assert [core(x) for x in out.split("\n")] == [core(x) for x in text.split("\n")]


def test_restructure_applies_levels_and_labels_engine():
    hs = _structurer(lambda m: '{"levels": {"0": 1, "2": 2}}', max_heading_ratio=1.0)
    new, suffix, warn = hs.restructure("Title\nbody\nSub")
    assert new.split("\n") == ["# Title", "body", "## Sub"]
    assert suffix == "llm-heads:deepseek-chat"
    assert warn is None


def test_restructure_falls_back_to_original_on_llm_error():
    def boom(messages):
        raise RuntimeError("network down")

    new, suffix, warn = _structurer(boom).restructure("Title\nbody")
    assert new == "Title\nbody"
    assert suffix is None
    assert "skipped" in warn


def test_restructure_ignores_out_of_range_levels_and_unknown_lines():
    # level 99 invalid; line 5 not a candidate -> both dropped, only {0:1} kept.
    hs = _structurer(lambda m: '{"levels": {"0": 1, "2": 99, "5": 3}}')
    new, suffix, warn = hs.restructure("Title\nbody\nSub")
    assert new.split("\n") == ["# Title", "body", "Sub"]
    assert suffix == "llm-heads:deepseek-chat"


def test_restructure_density_guard_keeps_flat():
    new, suffix, warn = _structurer(
        lambda m: '{"levels": {"0": 1, "1": 1, "2": 1}}'
    ).restructure("one\ntwo\nthree")
    assert new == "one\ntwo\nthree"
    assert suffix is None
    assert "too many headings" in warn


def test_restructure_all_body_returns_flat_without_warning():
    # Chat-log case: model judges everything body -> keep flat, no warning.
    new, suffix, warn = _structurer(lambda m: '{"levels": {}}').restructure(
        "张三：你好\n李四：收到\n张三：明天见"
    )
    assert new == "张三：你好\n李四：收到\n张三：明天见"
    assert suffix is None
    assert warn is None


def test_restructure_skips_oversized_without_calling_llm():
    called = []

    def spy(messages):
        called.append(1)
        return '{"levels": {}}'

    hs = _structurer(spy, max_input_lines=2)
    new, suffix, warn = hs.restructure("a\nb\nc")
    assert new == "a\nb\nc"
    assert "too many candidate lines" in warn
    assert called == []


def test_restructure_handles_fenced_json():
    # Real models often wrap JSON in ```json fences or add prose; parse anyway.
    fenced = '```json\n{"levels": {"0": 1}}\n```'
    new, suffix, warn = _structurer(lambda m: fenced, max_heading_ratio=1.0).restructure(
        "Title\nbody"
    )
    assert new.split("\n")[0] == "# Title"
    assert suffix == "llm-heads:deepseek-chat"


def test_restructure_handles_json_with_surrounding_prose():
    raw = 'Here are the levels:\n{"levels": {"0": 2}}\nHope this helps!'
    new, suffix, _ = _structurer(lambda m: raw, max_heading_ratio=1.0).restructure(
        "Title\nbody"
    )
    assert new.split("\n")[0] == "## Title"
    assert suffix == "llm-heads:deepseek-chat"


def test_restructure_never_takes_body_text_from_llm():
    # Safety: even if the LLM smuggles tampered body into its response, we only
    # read integer levels -> the amount in the body is untouched.
    def tamper(messages):
        return '{"levels": {"0": 1}, "text": "金额 99999 元 已被篡改"}'

    new, suffix, warn = _structurer(tamper).restructure("Title\n金额 5000 元\nSub")
    assert "99999" not in new
    assert new.split("\n")[1] == "金额 5000 元"
