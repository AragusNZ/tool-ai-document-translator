"""HTTP OCR client for the LiteParse OCR API (POST /ocr)."""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# 1x1 white PNG for health probes.
_PROBE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

_TESSERACT_TO_HTTP_LANG: dict[str, str] = {
    "eng": "en",
    "spa": "es",
    "fra": "fr",
    "deu": "de",
    "ita": "it",
    "por": "pt",
    "rus": "ru",
    "chi_sim": "zh",
    "jpn": "ja",
    "kor": "ko",
    "ara": "ar",
}


class OcrHttpError(RuntimeError):
    """OCR HTTP request failed."""


def tesseract_lang_to_http(language: str) -> str:
    primary = language.split("+", maxsplit=1)[0].strip().lower()
    if not primary:
        return "en"
    return _TESSERACT_TO_HTTP_LANG.get(primary, primary[:2] if len(primary) >= 2 else "en")


def merge_ocr_results(results: list[dict[str, Any]]) -> str:
    lines = [str(item.get("text", "")).strip() for item in results]
    return "\n".join(line for line in lines if line)


def _encode_multipart(
    *,
    file_field: str,
    filename: str,
    file_bytes: bytes,
    content_type: str,
    fields: dict[str, str],
) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode()
    )
    chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode())
    chunks.append(file_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)
    return body, f"multipart/form-data; boundary={boundary}"


def recognize_image(
    server_url: str,
    image_bytes: bytes,
    *,
    language: str = "en",
    timeout_seconds: float = 30.0,
) -> str:
    body, content_type = _encode_multipart(
        file_field="file",
        filename="page.png",
        file_bytes=image_bytes,
        content_type="image/png",
        fields={"language": language},
    )
    request = Request(
        server_url,
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise OcrHttpError(f"OCR server returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise OcrHttpError(f"OCR server request failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise OcrHttpError("OCR server returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise OcrHttpError("OCR server response must be a JSON object")
    if "error" in payload:
        raise OcrHttpError(str(payload["error"]))
    results = payload.get("results")
    if not isinstance(results, list):
        raise OcrHttpError("OCR server response missing results array")
    return merge_ocr_results(results)


def probe_ocr_server(server_url: str, *, timeout_seconds: float = 5.0) -> tuple[bool, str]:
    try:
        recognize_image(
            server_url,
            _PROBE_PNG,
            language="en",
            timeout_seconds=timeout_seconds,
        )
    except OcrHttpError as exc:
        return False, str(exc)
    return True, f"OCR server reachable at {server_url}"
