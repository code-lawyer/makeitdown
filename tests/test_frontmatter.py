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


def test_prepend_frontmatter():
    out = prepend_frontmatter("# Body", "---\nx: 1\n---\n")
    assert out == "---\nx: 1\n---\n\n# Body"
