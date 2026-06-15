def _yaml_value(value: str) -> str:
    """Quote a scalar string if it contains YAML-significant characters."""
    # Colon is only significant in YAML values when followed by a space or end-of-string
    # (which would indicate a mapping key). Bare colons in timestamps are fine.
    has_significant_colon = ": " in value or value.endswith(":")
    if has_significant_colon or any(c in value for c in '#"\n') or value.strip() != value:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def build_frontmatter(
    source: str,
    source_type: str,
    engine: str,
    pages: int | None,
    converted_at: str,
) -> str:
    """Return a YAML frontmatter block ending in a newline."""
    lines = ["---"]
    lines.append(f"source: {_yaml_value(source)}")
    lines.append(f"source_type: {_yaml_value(source_type)}")
    lines.append(f"engine: {_yaml_value(engine)}")
    if pages is not None:
        lines.append(f"pages: {pages}")
    lines.append(f"converted_at: {_yaml_value(converted_at)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def prepend_frontmatter(md_body: str, frontmatter: str) -> str:
    """Join frontmatter and body with one blank line between."""
    return f"{frontmatter}\n{md_body}"
