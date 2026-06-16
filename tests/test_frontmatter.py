from makeitdown.frontmatter import build_frontmatter, prepend_frontmatter


def test_build_frontmatter_basic():
    fm = build_frontmatter(
        source="sub/report.pdf",
        source_type="pdf",
        engine="markitdown",
        pages=12,
        converted_at="2026-06-15T10:30:00",
    )
    assert fm.startswith("---\n")
    assert fm.rstrip().endswith("---")
    assert "source: sub/report.pdf" in fm
    assert "source_type: pdf" in fm
    assert "engine: markitdown" in fm
    assert "pages: 12" in fm
    assert "converted_at: 2026-06-15T10:30:00" in fm


def test_build_frontmatter_omits_pages_when_none():
    fm = build_frontmatter(
        source="a.png", source_type="png", engine="local:pp-structurev3",
        pages=None, converted_at="2026-06-15T10:30:00",
    )
    assert "pages:" not in fm


def test_build_frontmatter_quotes_paths_with_special_chars():
    fm = build_frontmatter(
        source="dir: weird/名字.pdf", source_type="pdf", engine="markitdown",
        pages=None, converted_at="2026-06-15T10:30:00",
    )
    assert 'source: "dir: weird/名字.pdf"' in fm


def test_build_frontmatter_omits_quality_when_no_warnings():
    fm = build_frontmatter(
        source="a.pdf", source_type="pdf", engine="markitdown",
        pages=3, converted_at="2026-06-15T10:30:00",
    )
    assert "quality:" not in fm
    assert "warnings:" not in fm


def test_build_frontmatter_includes_warnings_as_yaml_list():
    fm = build_frontmatter(
        source="a.pdf", source_type="pdf", engine="cloud:paddleocr-vl-1.6",
        pages=30, converted_at="2026-06-15T10:30:00",
        warnings=["avg 12 chars/page over 30 pages", "garbled-char ratio 7.3%"],
    )
    assert "quality: suspect" in fm
    assert "warnings:" in fm
    # Rendered via the shared _yaml_value helper: plain scalars stay unquoted.
    assert "  - avg 12 chars/page over 30 pages" in fm
    assert "  - garbled-char ratio 7.3%" in fm


def test_build_frontmatter_empty_warnings_treated_as_clean():
    fm = build_frontmatter(
        source="a.pdf", source_type="pdf", engine="markitdown",
        pages=3, converted_at="2026-06-15T10:30:00", warnings=[],
    )
    assert "quality:" not in fm


def test_prepend_frontmatter():
    out = prepend_frontmatter("# Body", "---\nx: 1\n---\n")
    assert out == "---\nx: 1\n---\n\n# Body"
