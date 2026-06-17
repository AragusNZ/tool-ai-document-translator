from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from document_translator import __version__
from document_translator.config.defaults import DEFAULT_TARGET_LANG
from document_translator.config.formats import ExportFormat
from document_translator.config.languages import normalize_lang_code
from document_translator.config.llms import supported_llms, validate_llm_selector
from document_translator.config.settings import PipelineConfig
from document_translator.errors import ConfigurationError
from document_translator.lib.preflight import run_preflight_checks
from document_translator.lib.validation import (
    resolve_job_root,
    validate_input_file,
    validate_job_id,
)
from document_translator.models import BatchJobResult, JobResult, TranslationOptions
from document_translator.observability import configure_observability
from document_translator.pipeline import DocumentTranslationService
from document_translator.types import JobStatus, TranslationMode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI document translation pipeline")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    translate = sub.add_parser("translate", help="Translate one or more documents")
    translate.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="One or more input document paths",
    )
    translate.add_argument("--job-id", type=str, default=None, help="Job UUID for a single input (generated if omitted)")
    translate.add_argument(
        "--job-ids",
        nargs="+",
        default=None,
        help="Job UUIDs for each input (count must match inputs; generated if omitted)",
    )
    translate.add_argument("--output-dir", type=Path, default=None, help="Runs directory (default: ./runs)")
    translate.add_argument("--format", choices=["text", "json"], default="text", help="Stdout output format")
    translate.add_argument(
        "--export-format",
        choices=[f.value for f in ExportFormat],
        default=None,
        help="Final document export format (default: match input extension, else pdf)",
    )
    translate.add_argument("--force-overwrite", action="store_true", help="Overwrite existing job artifacts")
    translate.add_argument(
        "--target-lang",
        default=None,
        help="Target output language as ISO 639-1 code (default: en)",
    )
    translate.add_argument(
        "--source-lang",
        default=None,
        help="Source document language as ISO 639-1 code (skips detection; warns if detection disagrees)",
    )
    translate.add_argument(
        "--translation-context",
        default=None,
        help="Per-job context for translation (e.g. contract parties); improves chunk coherence",
    )
    translate.add_argument(
        "--llm",
        default=None,
        help="LLM selector as provider:model (e.g. cursor:composer-2.5, openai:gpt-4o)",
    )
    translate.add_argument(
        "--mode",
        choices=[m.value for m in TranslationMode],
        default=None,
        help="Translation mode: quick (single-pass, default) or thorough (dual-pass verification)",
    )
    translate.add_argument(
        "--no-pdf-ocr",
        action="store_true",
        help="Disable OCR fallback for scanned/image-only PDFs (PyMuPDF text extraction only)",
    )
    translate.add_argument(
        "--no-translate",
        action="store_true",
        help="Skip translation; export extracted text without translating",
    )
    translate.add_argument(
        "--save-resolved",
        action="store_true",
        help="Keep resolved markdown artifact (04-resolved.md) after job completes",
    )
    translate.add_argument(
        "--no-cover-page",
        action="store_true",
        help="Export final document without the cover page",
    )
    translate.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Maximum job duration in seconds (also DOCUMENT_TRANSLATOR_JOB_TIMEOUT)",
    )
    translate.add_argument(
        "--webhook-url",
        default=None,
        help="HTTPS URL to POST terminal job payload (also DOCUMENT_TRANSLATOR_WEBHOOK_URL)",
    )
    translate.add_argument(
        "--webhook-secret",
        default=None,
        help="Optional HMAC secret for X-Document-Translator-Signature (DOCUMENT_TRANSLATOR_WEBHOOK_SECRET)",
    )
    translate.add_argument("--config", type=Path, default=None, help="Optional JSON config (PipelineConfig + export_format + target_lang + source_lang + translation_context + translation_mode + no_translate + save_resolved + no_cover_page + pdf_ocr + job_timeout_seconds + webhook_url + webhook_secret)")

    check = sub.add_parser("check", help="Verify system dependencies and configuration")
    check.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    check.add_argument(
        "--llm",
        default=None,
        help="LLM selector as provider:model (default: from config / cursor:composer-2.5)",
    )
    check.add_argument(
        "--export-format",
        choices=[f.value for f in ExportFormat],
        default=None,
        help="Validate dependencies for a specific export format (default: pdf-level checks)",
    )
    check.add_argument("--output-dir", type=Path, default=None, help="Runs directory to verify is writable")
    check.add_argument(
        "--require-ocr",
        action="store_true",
        help="Treat missing Tesseract as a failure instead of a warning",
    )
    check.add_argument(
        "--no-pdf-ocr",
        action="store_true",
        help="Skip Tesseract check (matches translate --no-pdf-ocr)",
    )

    list_llms = sub.add_parser("list-llms", help="List supported LLM selectors")
    list_llms.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    return parser


def _exit_code_for_status(status: JobStatus) -> int:
    if status == JobStatus.COMPLETED:
        return 0
    if status == JobStatus.COMPLETED_WITH_WARNINGS:
        return 3
    if status == JobStatus.FAILED:
        return 2
    return 1


def _aggregate_exit_code(results: list[JobResult]) -> int:
    worst = 0
    for result in results:
        code = _exit_code_for_status(result.status)
        if code == 2:
            return 2
        if code == 3:
            worst = 3
    return worst


def _resolve_job_ids(
    input_count: int,
    job_id: str | None,
    job_ids: list[str] | None,
) -> list[str] | None:
    if job_ids is not None:
        if job_id is not None:
            print("Cannot use --job-id with --job-ids.", file=sys.stderr)
            return None
        if len(job_ids) != input_count:
            print(
                f"--job-ids count ({len(job_ids)}) must match input count ({input_count}).",
                file=sys.stderr,
            )
            return None
        if len(job_ids) != len(set(job_ids)):
            print("Job IDs must be unique.", file=sys.stderr)
            return None
        return _validate_job_id_list(job_ids)

    if input_count == 1:
        return _validate_job_id_list([job_id or str(uuid4())])

    if job_id is not None:
        print("Cannot use --job-id with multiple inputs; use --job-ids.", file=sys.stderr)
        return None

    return _validate_job_id_list([str(uuid4()) for _ in range(input_count)])


def _validate_job_id_list(job_ids: list[str]) -> list[str] | None:
    validated: list[str] = []
    for job_id in job_ids:
        try:
            validated.append(validate_job_id(job_id))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return None
    return validated


def _preflight_translate_inputs(
    inputs: list[Path],
    job_ids: list[str],
    runs_dir: Path,
    force_overwrite: bool,
    *,
    max_input_bytes: int | None,
) -> int | None:
    for input_path in inputs:
        try:
            validate_input_file(input_path, max_bytes=max_input_bytes)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if not force_overwrite:
        for job_id in job_ids:
            try:
                job_root = resolve_job_root(runs_dir, job_id)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            if job_root.exists():
                print(f"Job directory already exists: {job_root}. Use --force-overwrite.", file=sys.stderr)
                return 1
    return None


def _load_translate_config(
    args: argparse.Namespace,
) -> tuple[PipelineConfig, dict[str, object]] | None:
    config = PipelineConfig()
    if args.output_dir:
        config.runs_dir = Path(args.output_dir)

    config_overrides: dict[str, object] = {}
    if args.config:
        if not args.config.exists():
            print(f"Config file not found: {args.config}", file=sys.stderr)
            return None
        try:
            config_overrides = json.loads(args.config.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"Invalid config JSON: {exc}", file=sys.stderr)
            return None
        if "runs_dir" in config_overrides:
            config_overrides["runs_dir"] = Path(config_overrides["runs_dir"])
        if "root" in config_overrides:
            config_overrides["root"] = Path(config_overrides["root"])
        if "job_timeout_seconds" in config_overrides:
            timeout = config_overrides["job_timeout_seconds"]
            if timeout is not None and float(timeout) <= 0:
                print("job_timeout_seconds must be positive", file=sys.stderr)
                return None
        config_fields = set(PipelineConfig.model_fields.keys())
        config_values = {
            key: value for key, value in config_overrides.items() if key in config_fields
        }
        try:
            config = PipelineConfig.model_validate({**config.model_dump(), **config_values})
        except ValidationError as exc:
            print(str(exc), file=sys.stderr)
            return None

    if args.llm is not None:
        try:
            config.llm = validate_llm_selector(args.llm)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return None

    if args.no_pdf_ocr:
        config.pdf_ocr = False

    if args.timeout is not None:
        if args.timeout <= 0:
            print("--timeout must be a positive number of seconds", file=sys.stderr)
            return None
        config.job_timeout_seconds = args.timeout

    if args.webhook_url is not None:
        try:
            config = PipelineConfig.model_validate(
                {**config.model_dump(), "webhook_url": args.webhook_url}
            )
        except ValidationError as exc:
            print(str(exc), file=sys.stderr)
            return None

    if args.webhook_secret is not None:
        config = PipelineConfig.model_validate(
            {**config.model_dump(), "webhook_secret": args.webhook_secret}
        )

    return config, config_overrides


def _build_translation_options(
    job_id: str,
    args: argparse.Namespace,
    config_overrides: dict[str, object],
) -> TranslationOptions | None:
    export_format: ExportFormat | None = None
    if args.export_format is not None:
        export_format = ExportFormat(args.export_format)
    elif "export_format" in config_overrides:
        export_format = ExportFormat(str(config_overrides["export_format"]))

    target_lang = args.target_lang
    if target_lang is None and "target_lang" in config_overrides:
        target_lang = str(config_overrides["target_lang"])
    if target_lang is None:
        target_lang = DEFAULT_TARGET_LANG
    try:
        target_lang = normalize_lang_code(target_lang)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return None

    source_lang = args.source_lang
    if source_lang is None and "source_lang" in config_overrides:
        source_lang = str(config_overrides["source_lang"])
    if source_lang is not None:
        try:
            source_lang = normalize_lang_code(source_lang)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return None

    translation_mode: TranslationMode = TranslationMode.QUICK
    if args.mode is not None:
        translation_mode = TranslationMode(args.mode)
    elif "translation_mode" in config_overrides:
        try:
            translation_mode = TranslationOptions(
                translation_mode=config_overrides["translation_mode"]
            ).translation_mode
        except ValidationError as exc:
            print(str(exc), file=sys.stderr)
            return None

    translation_context = args.translation_context
    if translation_context is None and "translation_context" in config_overrides:
        translation_context = str(config_overrides["translation_context"])
    if translation_context is not None:
        try:
            translation_context = TranslationOptions(
                translation_context=translation_context
            ).translation_context
        except ValidationError as exc:
            print(str(exc), file=sys.stderr)
            return None

    no_translate = args.no_translate
    if "no_translate" in config_overrides:
        no_translate = bool(config_overrides["no_translate"])

    save_resolved = args.save_resolved
    if "save_resolved" in config_overrides:
        save_resolved = bool(config_overrides["save_resolved"])

    no_cover_page = args.no_cover_page
    if "no_cover_page" in config_overrides:
        no_cover_page = bool(config_overrides["no_cover_page"])

    return TranslationOptions(
        job_id=job_id,
        force_overwrite=args.force_overwrite,
        export_format=export_format,
        source_lang=source_lang,
        target_lang=target_lang,
        translation_mode=translation_mode,
        translation_context=translation_context,
        no_translate=no_translate,
        save_resolved=save_resolved,
        no_cover_page=no_cover_page,
    )


def _print_job_result(result: JobResult, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result.model_dump_json_api(), indent=2))
    elif result.status == JobStatus.FAILED:
        print(f"Pipeline failed: {result.error_message}", file=sys.stderr)
    else:
        print(f"Translation completed: job_id={result.job_id} (status={result.status.value})")
        availability = result.metadata.artifact_availability
        if availability.get("final_output"):
            print(f"Final document: {result.artifacts.final_output}")
        elif result.status == JobStatus.COMPLETED_WITH_WARNINGS:
            print("Final document: not available (see metadata.json for warnings)", file=sys.stderr)
        if availability.get("resolved_md"):
            print(f"Resolved markdown: {result.artifacts.resolved_md}")


def _print_batch_result(batch: BatchJobResult, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(batch.model_dump_json_api(), indent=2))
        return

    print(
        f"Batch translation completed: status={batch.status.value} "
        f"({len(batch.jobs)} job(s))"
    )
    for result in batch.jobs:
        if result.status == JobStatus.FAILED:
            print(
                f"  {result.job_id}: failed — {result.error_message}",
                file=sys.stderr,
            )
            continue
        print(f"  {result.job_id}: {result.status.value}")
        availability = result.metadata.artifact_availability
        if availability.get("final_output"):
            print(f"    Final document: {result.artifacts.final_output}")
        elif result.status == JobStatus.COMPLETED_WITH_WARNINGS:
            print(
                "    Final document: not available (see metadata.json for warnings)",
                file=sys.stderr,
            )
        if availability.get("resolved_md"):
            print(f"    Resolved markdown: {result.artifacts.resolved_md}")


def _print_supported_llms(output_format: str) -> int:
    entries = supported_llms()
    if output_format == "json":
        print(json.dumps(entries, indent=2))
        return 0
    for entry in entries:
        print(f"{entry['id']}\t{entry['label']}\t({entry['env_key']})")
    return 0


def _run_check(args: argparse.Namespace) -> int:
    config = PipelineConfig()
    if args.output_dir:
        config.runs_dir = Path(args.output_dir)
    if args.llm is not None:
        try:
            config.llm = validate_llm_selector(args.llm)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.no_pdf_ocr:
        config.pdf_ocr = False

    export_format: ExportFormat | None = None
    if args.export_format is not None:
        export_format = ExportFormat(args.export_format)

    result = run_preflight_checks(
        config,
        export_format=export_format,
        require_ocr=args.require_ocr,
    )
    if args.format == "json":
        payload = {
            "ready": result.ready,
            "checks": [check.model_dump(mode="json") for check in result.checks],
        }
        print(json.dumps(payload, indent=2))
    else:
        for check in result.checks:
            label = check.status.value.upper()
            required = "" if check.required else " (optional)"
            print(f"[{label}]{required} {check.name}: {check.message}")
        print("ready" if result.ready else "not ready")
    return 0 if result.ready else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list-llms":
        return _print_supported_llms(args.format)

    if args.command == "check":
        return _run_check(args)

    if args.command != "translate":
        parser.print_help()
        return 1

    inputs: list[Path] = list(args.inputs)

    loaded = _load_translate_config(args)
    if loaded is None:
        return 1
    config, config_overrides = loaded

    job_ids = _resolve_job_ids(len(inputs), args.job_id, args.job_ids)
    if job_ids is None:
        return 1

    runs_dir = config.resolve_runs_dir()
    preflight_code = _preflight_translate_inputs(
        inputs,
        job_ids,
        runs_dir,
        args.force_overwrite,
        max_input_bytes=config.max_input_bytes,
    )
    if preflight_code is not None:
        return preflight_code

    configure_observability(config)

    items: list[tuple[Path, TranslationOptions]] = []
    for input_path, job_id in zip(inputs, job_ids, strict=True):
        options = _build_translation_options(job_id, args, config_overrides)
        if options is None:
            return 1
        items.append((input_path, options))

    service = DocumentTranslationService(config=config)

    try:
        if len(items) == 1:
            result = service.translate(items[0][0], items[0][1])
            _print_job_result(result, args.format)
            return _exit_code_for_status(result.status)

        batch = service.translate_batch(items)
        _print_batch_result(batch, args.format)
        return _aggregate_exit_code(batch.jobs)
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
