from pathlib import Path
import makeitdown.cli as cli


def test_cli_wires_args_to_convert_tree(tmp_path, monkeypatch):
    captured = {}

    def fake_convert_tree(input_dir, output_dir, **kw):
        captured["input_dir"] = Path(input_dir)
        captured["output_dir"] = Path(output_dir)
        captured.update(kw)
        return {"succeeded": 0, "failed": 0, "skipped_existing": 0,
                "skipped_unsupported": 0, "failures": []}

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
                        {"succeeded": 0, "failed": 0, "skipped_existing": 0,
                         "skipped_unsupported": 0, "failures": []})
    monkeypatch.setenv("PADDLEOCR_AISTUDIO_TOKEN", "ENVTKN")

    rc = cli.main(["docs"])
    assert rc == 0
    assert captured["output_dir"] == Path("docs_md")
    assert captured["cloud_token"] == "ENVTKN"
    assert captured["ocr_engine"] == "auto"
