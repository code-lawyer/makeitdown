import json
from pathlib import Path
import makeitdown.ocr_cloud as oc
from makeitdown.models import ConversionResult


class _Resp:
    def __init__(self, status=200, payload=None, text="", content=b""):
        self.status_code = status
        self._payload = payload or {}
        self.text = text
        self.content = content

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"status {self.status_code}")


def test_cloud_convert_happy_path(tmp_path, monkeypatch):
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4")

    # Sequence: POST job -> GET job (running) -> GET job (done) -> GET jsonl
    states = iter([
        _Resp(payload={"data": {"state": "running",
                                "extractProgress": {"totalPages": 1, "extractedPages": 0}}}),
        _Resp(payload={"data": {"state": "done",
                                "extractProgress": {"extractedPages": 1,
                                                    "startTime": "t0", "endTime": "t1"},
                                "resultUrl": {"jsonUrl": "https://x/result.jsonl"}}}),
    ])
    jsonl_line = json.dumps({"result": {"layoutParsingResults": [
        {"markdown": {"text": "# Page 1\n\n| a | b |\n|---|---|", "images": {}}}
    ]}})

    def fake_post(url, **kw):
        return _Resp(payload={"data": {"jobId": "job-123"}})

    def fake_get(url, **kw):
        if url.endswith("result.jsonl"):
            return _Resp(text=jsonl_line)
        return next(states)

    monkeypatch.setattr(oc.requests, "post", fake_post)
    monkeypatch.setattr(oc.requests, "get", fake_get)

    client = oc.CloudOCR(token="TKN", poll_interval=0)
    result = client.convert(f)
    assert isinstance(result, ConversionResult)
    assert "# Page 1" in result.text
    assert result.engine == "cloud:paddleocr-vl-1.6"
    assert result.pages == 1


def test_cloud_convert_raises_on_poll_http_error(tmp_path, monkeypatch):
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(oc.requests, "post",
                        lambda url, **kw: _Resp(payload={"data": {"jobId": "j"}}))
    monkeypatch.setattr(oc.requests, "get",
                        lambda url, **kw: _Resp(status=500, text="server error"))
    client = oc.CloudOCR(token="TKN", poll_interval=0)
    try:
        client.convert(f)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "job poll failed" in str(e)


def test_cloud_convert_raises_on_failed_job(tmp_path, monkeypatch):
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(oc.requests, "post",
                        lambda url, **kw: _Resp(payload={"data": {"jobId": "j"}}))
    monkeypatch.setattr(oc.requests, "get",
                        lambda url, **kw: _Resp(payload={"data": {"state": "failed",
                                                                  "errorMsg": "boom"}}))
    client = oc.CloudOCR(token="TKN", poll_interval=0)
    try:
        client.convert(f)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "boom" in str(e)
