import json
import time
from pathlib import Path

import requests

from .models import ConversionResult

JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
DEFAULT_MODEL = "PaddleOCR-VL-1.6"


class CloudOCR:
    """Client for the PaddleOCR AI Studio job-based HTTP API."""

    def __init__(self, token: str, model: str | None = None, poll_interval: float = 5.0):
        self.token = token
        self.model = model or DEFAULT_MODEL
        self.poll_interval = poll_interval

    @property
    def engine_label(self) -> str:
        return f"cloud:{self.model.lower()}"

    def _headers(self) -> dict:
        return {"Authorization": f"bearer {self.token}"}

    def _submit(self, path: Path) -> str:
        optional = {
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
        }
        data = {"model": self.model, "optionalPayload": json.dumps(optional)}
        with open(path, "rb") as fh:
            resp = requests.post(JOB_URL, headers=self._headers(),
                                 data=data, files={"file": fh})
        if resp.status_code != 200:
            raise RuntimeError(f"job submit failed ({resp.status_code}): {resp.text}")
        return resp.json()["data"]["jobId"]

    def _poll(self, job_id: str) -> str:
        while True:
            resp = requests.get(f"{JOB_URL}/{job_id}", headers=self._headers())
            if resp.status_code != 200:
                raise RuntimeError(f"job poll failed ({resp.status_code}): {resp.text}")
            data = resp.json()["data"]
            state = data["state"]
            if state == "done":
                return data["resultUrl"]["jsonUrl"]
            if state == "failed":
                raise RuntimeError(f"cloud OCR job failed: {data.get('errorMsg')}")
            time.sleep(self.poll_interval)

    def _fetch_markdown(self, jsonl_url: str) -> tuple[str, dict[str, bytes], int]:
        resp = requests.get(jsonl_url)
        resp.raise_for_status()
        parts: list[str] = []
        assets: dict[str, bytes] = {}
        pages = 0
        for line in resp.text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            result = json.loads(line)["result"]
            for res in result["layoutParsingResults"]:
                pages += 1
                parts.append(res["markdown"]["text"])
                for img_rel, img_url in res["markdown"].get("images", {}).items():
                    img = requests.get(img_url)
                    if img.status_code == 200:
                        assets[img_rel] = img.content
        return "\n\n".join(parts), assets, pages

    def convert(self, path: Path) -> ConversionResult:
        job_id = self._submit(path)
        jsonl_url = self._poll(job_id)
        text, assets, pages = self._fetch_markdown(jsonl_url)
        return ConversionResult(text=text, engine=self.engine_label, assets=assets, pages=pages)
