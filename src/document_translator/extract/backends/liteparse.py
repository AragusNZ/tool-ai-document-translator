from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from document_translator.config.settings import PipelineConfig

LITEPARSE_INSTALL_HINT = (
    "LiteParse is not installed. Install the optional extra: "
    "pip install 'document-translator[extract-liteparse]'"
)


def _page_text_items(page: object) -> list[object]:
    items = getattr(page, "text_items", None)
    if items is None:
        items = getattr(page, "textItems", None)
    return list(items or [])


def _page_number(page: object) -> int | None:
    value = getattr(page, "page_num", None)
    if value is None:
        value = getattr(page, "page_number", None)
    return int(value) if value is not None else None


def _count_ocr_pages(pages: list[object]) -> int:
    """Count pages with OCR-derived text items (confidence metadata present)."""
    ocr_pages = 0
    for page in pages:
        if any(getattr(item, "confidence", None) is not None for item in _page_text_items(page)):
            ocr_pages += 1
    return ocr_pages


def _serialize_text_item(item: object) -> dict[str, Any]:
    return {
        "text": getattr(item, "text", ""),
        "x": getattr(item, "x", None),
        "y": getattr(item, "y", None),
        "width": getattr(item, "width", None),
        "height": getattr(item, "height", None),
        "font_name": getattr(item, "font_name", None),
        "font_size": getattr(item, "font_size", None),
        "confidence": getattr(item, "confidence", None),
    }


def _serialize_layout_json(pages: list[object]) -> dict[str, Any]:
    return {
        "pages": [
            {
                "page_num": _page_number(page),
                "width": getattr(page, "width", getattr(page, "page_width", None)),
                "height": getattr(page, "height", getattr(page, "page_height", None)),
                "text": getattr(page, "text", ""),
                "text_items": [_serialize_text_item(item) for item in _page_text_items(page)],
            }
            for page in pages
        ]
    }


def _build_page_stats(pages: list[object]) -> tuple[dict[str, Any], ...]:
    stats: list[dict[str, Any]] = []
    for page in pages:
        items = _page_text_items(page)
        page_text = getattr(page, "text", "")
        stats.append(
            {
                "page_num": _page_number(page),
                "char_count": len(page_text),
                "ocr": any(getattr(item, "confidence", None) is not None for item in items),
                "text_item_count": len(items),
                "method": "liteparse",
            }
        )
    return tuple(stats)


def _build_layout_text(pages: list[object]) -> str | None:
    page_texts = [str(getattr(page, "text", "") or "").strip() for page in pages]
    if not any(page_texts):
        return None
    return "\n\n".join(text for text in page_texts if text)


def _liteparse_kwargs(config: PipelineConfig) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "ocr_enabled": config.pdf_ocr,
        "ocr_language": config.pdf_ocr_languages,
    }
    if config.target_pages:
        kwargs["target_pages"] = config.target_pages
    if config.pdf_password:
        kwargs["password"] = config.pdf_password
    if config.extract_dpi is not None:
        kwargs["dpi"] = config.extract_dpi
    return kwargs


def _capture_screenshots(parser: object, path: Path) -> tuple[tuple[Path, ...], Path | None]:
    screenshot = getattr(parser, "screenshot", None)
    if screenshot is None:
        return (), None

    temp_dir = Path(tempfile.mkdtemp(prefix="dt-screenshots-"))
    shots = screenshot(str(path))
    paths: list[Path] = []
    for shot in shots:
        page_num = getattr(shot, "page_num", len(paths) + 1)
        dest = temp_dir / f"page-{int(page_num):04d}.png"
        dest.write_bytes(getattr(shot, "image_bytes", b""))
        paths.append(dest)
    return tuple(paths), temp_dir


class LiteParseBackend:
    name = "liteparse"

    def extract(self, path: Path, *, config: PipelineConfig):
        from document_translator.extract.common import ExtractionResult, normalize_text

        try:
            from liteparse import LiteParse
        except ImportError as exc:
            raise RuntimeError(LITEPARSE_INSTALL_HINT) from exc

        parser = LiteParse(**_liteparse_kwargs(config))
        result = parser.parse(str(path))
        file_bytes = path.stat().st_size
        pages = list(result.pages)
        ocr_pages = _count_ocr_pages(pages) if config.pdf_ocr else 0
        screenshot_paths: tuple[Path, ...] = ()
        screenshot_temp_dir: Path | None = None
        if config.extract_screenshots:
            screenshot_paths, screenshot_temp_dir = _capture_screenshots(parser, path)

        return ExtractionResult(
            text=normalize_text(result.text),
            pages=len(pages),
            bytes=file_bytes,
            conversion_method="liteparse",
            extract_backend=self.name,
            ocr_pages=ocr_pages,
            layout_text=normalize_text(_build_layout_text(pages) or result.text),
            layout_json=_serialize_layout_json(pages),
            screenshot_paths=screenshot_paths,
            screenshot_temp_dir=screenshot_temp_dir,
            extract_page_stats=_build_page_stats(pages),
        )
