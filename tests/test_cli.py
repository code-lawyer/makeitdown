from pathlib import Path
import makeitdown.cli as cli


def test_cli_wires_args_to_convert_tree(tmp_path, monkeypatch):
    captured = {}

    def fake_convert_tree(input_dir, output_dir, **kw):
        captured["input_dir"] = Path(input_dir)
        captured["output_dir"] = Path(output_dir)
        captured.update(kw)
        return {"succeeded": 0, "warned": 0, "failed": 0, "skipped_existing": 0,
                "skipped_unsupported": 0, "failures": [], "warnings": [], "skipped": []}

    monkeypatch.setattr(cli, "convert_tree", fake_convert_tree)
    monkeypatch.delenv("PADDLEOCR_AISTUDIO_TOKEN", raising=False)

    rc = cli.main(["./in", "-o", "./out", "--ocr-engine", "cloud",
                   "--cloud-token", "TKN", "--workers", "3", "--skip-existing"])
    assert rc == 0
    assert captured["output_dir"] == Path("./out")
    assert captured["ocr_engine"] == "cloud"
    assert captured["cloud_token"] == "TKN"
    assert captured["workers"] == 3
    assert captured["skip_existing"] is True


def test_cli_defaults_output_and_reads_token_from_env(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "convert_tree",
                        lambda input_dir, output_dir, **kw: captured.update(
                            {"output_dir": Path(output_dir), **kw}) or
                        {"succeeded": 0, "warned": 0, "failed": 0, "skipped_existing": 0,
                         "skipped_unsupported": 0, "failures": [], "warnings": [], "skipped": []})
    monkeypatch.setenv("PADDLEOCR_AISTUDIO_TOKEN", "ENVTKN")

    rc = cli.main(["docs"])
    assert rc == 0
    assert captured["output_dir"] == Path("docs_md")
    assert captured["cloud_token"] == "ENVTKN"
    assert captured["ocr_engine"] == "auto"


def _report(**over):
    base = {"succeeded": 0, "warned": 0, "failed": 0, "skipped_existing": 0,
            "skipped_unsupported": 0, "failures": [], "warnings": [], "skipped": []}
    base.update(over)
    return base


def test_cli_quality_defaults_and_flags_wired(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "convert_tree",
                        lambda input_dir, output_dir, **kw: captured.update(kw) or _report())
    monkeypatch.delenv("PADDLEOCR_AISTUDIO_TOKEN", raising=False)

    # defaults
    cli.main(["in"])
    assert captured["quality_check"] is True
    assert captured["quality_thresholds"].min_chars == 20
    assert captured["quality_thresholds"].garbled_ratio == 0.02

    assert captured["quality_thresholds"].min_confidence == 0.6

    # overrides
    cli.main(["in", "--no-quality-check", "--warn-min-chars", "5",
              "--warn-min-chars-per-page", "80", "--warn-garbled-ratio", "0.1",
              "--warn-repeat-count", "100", "--warn-min-confidence", "0.7"])
    assert captured["quality_check"] is False
    t = captured["quality_thresholds"]
    assert (t.min_chars, t.min_chars_per_page, t.garbled_ratio, t.repeat_count) == (5, 80, 0.1, 100)
    assert t.min_confidence == 0.7


def test_cli_summary_includes_warned(monkeypatch, capsys):
    monkeypatch.setattr(cli, "convert_tree",
                        lambda input_dir, output_dir, **kw: _report(succeeded=3, warned=2))
    monkeypatch.delenv("PADDLEOCR_AISTUDIO_TOKEN", raising=False)
    cli.main(["in"])
    out = capsys.readouterr().out
    assert "warned=2" in out


def test_cli_structure_headings_builds_structurer(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "convert_tree",
                        lambda input_dir, output_dir, **kw: captured.update(kw) or _report())
    monkeypatch.delenv("PADDLEOCR_AISTUDIO_TOKEN", raising=False)

    rc = cli.main(["in", "--structure-headings", "--llm-base-url", "http://x/v1",
                   "--llm-model", "deepseek-chat", "--llm-api-key", "K"])
    assert rc == 0
    s = captured["structurer"]
    assert s is not None
    assert s.model == "deepseek-chat"
    assert s.base_url == "http://x/v1"


def test_cli_structure_headings_reads_llm_config_from_env(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "convert_tree",
                        lambda input_dir, output_dir, **kw: captured.update(kw) or _report())
    monkeypatch.delenv("PADDLEOCR_AISTUDIO_TOKEN", raising=False)
    monkeypatch.setenv("MAKEITDOWN_LLM_BASE_URL", "http://env/v1")
    monkeypatch.setenv("MAKEITDOWN_LLM_MODEL", "qwen")
    monkeypatch.setenv("MAKEITDOWN_LLM_API_KEY", "ENVK")

    cli.main(["in", "--structure-headings"])
    assert captured["structurer"].model == "qwen"


def test_cli_structure_headings_fail_fast_without_config(monkeypatch, capsys):
    called = {"n": 0}

    def spy(input_dir, output_dir, **kw):
        called["n"] += 1
        return _report()

    monkeypatch.setattr(cli, "convert_tree", spy)
    monkeypatch.delenv("PADDLEOCR_AISTUDIO_TOKEN", raising=False)
    for var in ("MAKEITDOWN_LLM_BASE_URL", "MAKEITDOWN_LLM_MODEL", "MAKEITDOWN_LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    rc = cli.main(["in", "--structure-headings"])
    assert rc != 0
    assert called["n"] == 0
    assert "structure-headings" in capsys.readouterr().err


def test_cli_default_passes_no_structurer(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "convert_tree",
                        lambda input_dir, output_dir, **kw: captured.update(kw) or _report())
    monkeypatch.delenv("PADDLEOCR_AISTUDIO_TOKEN", raising=False)
    cli.main(["in"])
    assert captured["structurer"] is None


def test_cli_summary_includes_structured_when_enabled(monkeypatch, capsys):
    monkeypatch.setattr(cli, "convert_tree",
                        lambda input_dir, output_dir, **kw: _report(succeeded=4, structured=4))
    monkeypatch.delenv("PADDLEOCR_AISTUDIO_TOKEN", raising=False)
    monkeypatch.setenv("MAKEITDOWN_LLM_BASE_URL", "http://env/v1")
    monkeypatch.setenv("MAKEITDOWN_LLM_MODEL", "qwen")
    monkeypatch.setenv("MAKEITDOWN_LLM_API_KEY", "ENVK")
    cli.main(["in", "--structure-headings"])
    assert "structured=4" in capsys.readouterr().out


def test_cli_notes_actionable_skips(monkeypatch, capsys):
    skipped = [{"file": "a.doc", "reason": "needs WPS/Office or LibreOffice"}]
    monkeypatch.setattr(cli, "convert_tree",
                        lambda input_dir, output_dir, **kw: _report(skipped_unsupported=1,
                                                                    skipped=skipped))
    monkeypatch.delenv("PADDLEOCR_AISTUDIO_TOKEN", raising=False)
    cli.main(["in"])
    err = capsys.readouterr().err
    assert "1 file(s)" in err and "report" in err.lower()
