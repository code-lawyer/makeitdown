from makeitdown.quality import assess, QualityThresholds


# --- OCR confidence (Phase 2): low recognition scores flag suspect output ---

_GOOD = "正常的中文合同内容" * 5  # passes the other rules so we isolate confidence


def test_low_confidence_region_flagged():
    reasons = assess(_GOOD, source_type="png", pages=1,
                     confidences=[0.99, 0.42, 0.95])
    assert any("low-confidence" in r and "0.42" in r for r in reasons)


def test_all_high_confidence_not_flagged():
    reasons = assess(_GOOD, source_type="png", pages=1,
                     confidences=[0.99, 0.97, 0.93])
    assert not any("confidence" in r for r in reasons)


def test_confidence_none_skips_rule():
    assert assess(_GOOD, source_type="png", pages=1, confidences=None) == []


def test_confidence_empty_skips_rule():
    assert assess(_GOOD, source_type="png", pages=1, confidences=[]) == []


def test_confidence_threshold_is_configurable():
    # 0.55 is below the default 0.6 (flagged) but above a custom 0.5 (not).
    assert any("confidence" in r
               for r in assess(_GOOD, source_type="png", pages=1, confidences=[0.55]))
    t = QualityThresholds(min_confidence=0.5)
    assert not any("confidence" in r
                   for r in assess(_GOOD, source_type="png", pages=1,
                                   confidences=[0.55], thresholds=t))


# --- clean inputs should never warn (guard against false positives) ---

def test_clean_chinese_paragraph_no_warnings():
    text = "本协议由甲乙双方于二〇二四年三月十五日在北京签订，双方就采购框架达成如下一致条款。"
    assert assess(text, source_type="pdf", pages=1) == []


def test_english_contract_no_warnings():
    text = ("This Agreement is entered into by and between the parties as of "
            "March 15, 2024, and sets forth the terms of the purchase framework.")
    # No language detection: pure English must not be flagged.
    assert assess(text, source_type="docx", pages=1) == []


def test_numeric_table_no_warnings():
    text = "| 项目 | 金额 |\n|---|---|\n| 货款 | 100000 |\n| 税额 | 13000 |\n| 合计 | 113000 |"
    assert assess(text, source_type="xlsx", pages=1) == []


# --- near-empty ---

def test_near_empty_flagged():
    assert assess("abc", source_type="png", pages=1) == ["near-empty output (3 chars)"]


def test_near_empty_counts_non_whitespace_only():
    # 5 visible chars padded with whitespace stays under the default floor of 20.
    assert assess("a b\n c   d e", source_type="png", pages=1) == [
        "near-empty output (5 chars)"
    ]


# --- low chars per page ---

def test_low_chars_per_page_flagged():
    text = "字" * 360
    assert assess(text, source_type="pdf", pages=30) == [
        "avg 12 chars/page over 30 pages"
    ]


def test_low_chars_per_page_skipped_when_pages_unknown():
    text = "字" * 30  # above near-empty floor, but only 30 chars
    assert assess(text, source_type="docx", pages=None) == []


# --- garbled ratio ---

def test_garbled_ratio_flagged():
    text = "正常的中文内容占多数" * 4 + "�" * 5  # 40 good + 5 replacement chars
    reasons = assess(text, source_type="png", pages=None)
    assert reasons == ["garbled-char ratio 11.1%"]


def test_control_chars_count_as_garbled():
    text = "正常的中文内容占多数" * 4 + "\x00" * 5
    reasons = assess(text, source_type="png", pages=None)
    assert reasons == ["garbled-char ratio 11.1%"]


# --- runaway repetition ---

def test_repetition_flagged():
    line = "这是一条会被重复很多次的行内容"
    text = "\n".join([line] * 40)
    assert assess(text, source_type="pdf", pages=None) == [
        "line repeated 40x (possible OCR loop)"
    ]


def test_repeated_header_below_threshold_no_warning():
    line = "中华人民共和国某某人民法院民事判决书页眉"
    text = "\n".join([line] * 5)
    assert assess(text, source_type="pdf", pages=None) == []


def test_short_repeated_lines_ignored():
    # Lines of length <= 10 (e.g. table separators) are not repetition signals.
    text = "\n".join(["| --- |"] * 50)
    assert "possible OCR loop" not in " ".join(
        assess(text, source_type="xlsx", pages=None)
    )


# --- configurability & combinations ---

def test_thresholds_configurable():
    text = "a" * 50
    reasons = assess(text, source_type="txt", pages=None,
                     thresholds=QualityThresholds(min_chars=100))
    assert reasons == ["near-empty output (50 chars)"]


def test_multiple_reasons_accumulate():
    text = "字" * 300 + "�" * 100  # low per-page AND garbled
    reasons = assess(text, source_type="pdf", pages=30)
    assert any("chars/page" in r for r in reasons)
    assert any("garbled" in r for r in reasons)
