from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch

import pytest

from document_translator.extract.ocr_http import (
    merge_ocr_results,
    probe_ocr_server,
    recognize_image,
    tesseract_lang_to_http,
)
from document_translator.extract.ocr_http import OcrHttpError


def test_tesseract_lang_to_http_maps_common_codes() -> None:
    assert tesseract_lang_to_http("eng") == "en"
    assert tesseract_lang_to_http("eng+spa") == "en"
    assert tesseract_lang_to_http("fra") == "fr"


def test_merge_ocr_results_joins_text() -> None:
    merged = merge_ocr_results(
        [
            {"text": "Hello", "bbox": [0, 0, 1, 1], "confidence": 0.9},
            {"text": "World", "bbox": [1, 1, 2, 2], "confidence": 0.8},
        ]
    )
    assert merged == "Hello\nWorld"


def test_recognize_image_posts_multipart_and_parses_response() -> None:
    payload = {"results": [{"text": "Line one", "bbox": [0, 0, 1, 1], "confidence": 1.0}]}
    response = BytesIO(json.dumps(payload).encode("utf-8"))

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return response.getvalue()

    with patch("document_translator.extract.ocr_http.urlopen", return_value=FakeResponse()):
        text = recognize_image("http://localhost:8828/ocr", b"png", language="en")

    assert text == "Line one"


def test_recognize_image_raises_on_error_payload() -> None:
    response = BytesIO(json.dumps({"error": "bad image"}).encode("utf-8"))

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return response.getvalue()

    with patch("document_translator.extract.ocr_http.urlopen", return_value=FakeResponse()):
        with pytest.raises(OcrHttpError, match="bad image"):
            recognize_image("http://localhost:8828/ocr", b"png")


def test_probe_ocr_server_success() -> None:
    with patch(
        "document_translator.extract.ocr_http.recognize_image",
        return_value="",
    ):
        ok, message = probe_ocr_server("http://localhost:8828/ocr")
    assert ok is True
    assert "reachable" in message


def test_probe_ocr_server_failure() -> None:
    with patch(
        "document_translator.extract.ocr_http.recognize_image",
        side_effect=OcrHttpError("connection refused"),
    ):
        ok, message = probe_ocr_server("http://localhost:8828/ocr")
    assert ok is False
    assert "connection refused" in message
