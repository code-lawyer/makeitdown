from pathlib import Path
import makeitdown.cli as cli


def test_cli_wires_args_to_convert_tree(tmp_path, monkeypatch):
    captured = {}

    def fake_convert_tree(input_dir, output_dir, **kw):
        captured["input_dir"] = Path(input_dir)
        captured["output_dir"] = Path(output_dir)
        captured.update(kw)
        return {"succeeded": 0, "warned": 0, "failed": 0, "skipped_existing": 0,
                "skipped_unsupported": 0, "failures": [], "warnings": []}

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
                         "skipped_unsupported": 0, "failures": [], "warnings": []})
    monkeypatch.setenv("PADDLEOCR_AISTUDIO_TOKEN", "ENVTKN")

    rc = cli.main(["docs"])
    assert rc == 0
    assert captured["output_dir"] == Path("docs_md")
    assert captured["cloud_token"] == "ENVTKN"
    assert captured["ocr_engine"] == "auto"


def _report(**over):
    base = {"succeeded": 0, "warned": 0, "failed": 0, "skipped_existing": 0,
            "skipped_unsupported": 0, "failures": [], "warnings": []}
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

    # overrides
    cli.main(["in", "--no-quality-check", "--warn-min-chars", "5",
              "--warn-min-chars-per-page", "80", "--warn-garbled-ratio", "0.1",
              "--warn-repeat-count", "100"])
    assert captured["quality_check"] is False
    t = captured["quality_thresholds"]
    assert (t.min_chars, t.min_chars_per_page, t.garbled_ratio, t.repeat_count) == (5, 80, 0.1, 100)


def test_cli_summary_includes_warned(monkeypatch, capsys):
    monkeypatch.setattr(cli, "convert_tree",
                        lambda input_dir, output_dir, **kw: _report(succeeded=3, warned=2))
    monkeypatch.delenv("PADDLEOCR_AISTUDIO_TOKEN", raising=False)
    cli.main(["in"])
    out = capsys.readouterr().out
    assert "warned=2" in out
