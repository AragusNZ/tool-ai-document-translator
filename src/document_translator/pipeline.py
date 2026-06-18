from __future__ import annotations

import shutil
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from document_translator.config.formats import resolve_export_format
from document_translator.config.settings import PipelineConfig
from document_translator.detect.language import detect_language
from document_translator.detect.legal import classify_legal_document
from document_translator.errors import (
    ChunkCountMismatchError,
    IssueCode,
    IssueSeverity,
    PipelineError,
    UnsupportedFormatError,
)
from document_translator.export.combine import build_export_markdown
from document_translator.export.converter import export_markdown
from document_translator.extract.common import (
    ExtractionResult,
    build_extracted_markdown,
    compute_extraction_alerts,
    extract_single_file,
    liteparse_only_options_active,
    persist_extraction_sidecars,
    strip_front_matter,
    supported_extension,
    translation_body_text,
)
from document_translator.lib.job_control import (
    JobDeadline,
    install_job_signal_handlers,
    reset_job_control,
)
from document_translator.lib.llm import LLMCallTracker, LLMClient, build_llm_client
from document_translator.lib.llm.usage import sync_tracker_to_metadata
from document_translator.lib.text.chunker import chunk_document, reassemble_chunks
from document_translator.lib.validation import validate_input_file
from document_translator.lib.webhook import deliver_terminal_webhook
from document_translator.models import (
    BatchJobResult,
    Discrepancy,
    DiscrepancySeverity,
    JobMetadata,
    JobResult,
    TranslationOptions,
    aggregate_job_status,
)
from document_translator.observability import (
    add_extract_breadcrumb,
    build_issue_listeners,
    finish_sentry_transaction,
    get_logger,
    sentry_translate_transaction,
)
from document_translator.observability.context import IssueListener
from document_translator.reconcile.resolve import reconcile_translations
from document_translator.report.collector import IssueCollector
from document_translator.report.cover import (
    build_job_summary,
    generate_cover_markdown,
    translate_cover_markdown,
)
from document_translator.storage.checkpoint import (
    CheckpointStage,
    CheckpointState,
    load_checkpoint,
    load_completed_chunks,
    read_layout_body_checkpoint,
    source_text_hash,
    write_checkpoint,
    write_chunk_checkpoint,
    write_extract_chunk_checkpoints,
    write_layout_body_checkpoint,
)
from document_translator.storage.paths import JobPaths
from document_translator.translate.glossary import Glossary, resolve_glossary
from document_translator.translate.service import (
    build_document_summary,
    translate_source_chunks,
)
from document_translator.types import JobStatus, PipelineStage, TranslationMode

logger = get_logger()


def _resolve_terminal_status(collector: IssueCollector) -> JobStatus:
    if collector.has_warnings():
        return JobStatus.COMPLETED_WITH_WARNINGS
    return JobStatus.COMPLETED


class DocumentTranslationService:
    def __init__(
        self,
        config: PipelineConfig | None = None,
        llm: LLMClient | None = None,
        issue_listeners: Sequence[IssueListener] | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self._issue_listeners = (
            list(issue_listeners)
            if issue_listeners is not None
            else build_issue_listeners(self.config)
        )
        self._tracker = LLMCallTracker()
        if llm is None:
            self.llm = build_llm_client(
                self.config,
                tracker=self._tracker,
                cwd=self.config.root,
            )
        else:
            injected_tracker = getattr(llm, "tracker", None)
            if isinstance(injected_tracker, LLMCallTracker):
                self._tracker = injected_tracker
            self.llm = llm

    def _finalize_job(
        self,
        *,
        job_paths: JobPaths,
        metadata: JobMetadata,
        collector: IssueCollector,
        discrepancies: list[Discrepancy],
        status: JobStatus,
        current_stage: PipelineStage,
        current_progress: float,
        error_message: str | None = None,
        error_code: IssueCode | None = None,
        keep_checkpoints: bool = False,
    ) -> JobResult:
        metadata.issues = collector.to_list()
        metadata.job_status = status
        metadata.discrepancies = discrepancies
        metadata.summary = build_job_summary(
            metadata,
            discrepancies,
            has_warnings=collector.has_warnings(),
        )
        metadata.error_message = error_message
        metadata.error_code = error_code
        if status == JobStatus.FAILED:
            metadata.failed_stage = current_stage

        job_paths.metadata_json.write_text(
            metadata.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

        job_paths.write_status(
            current_stage if status == JobStatus.FAILED else PipelineStage.COMPLETED,
            message=error_message or ("Completed with warnings" if status == JobStatus.COMPLETED_WITH_WARNINGS else "Completed"),
            progress=current_progress if status == JobStatus.FAILED else 1.0,
            issue_count=len(collector.to_list()),
            terminal_status=status,
            error_code=error_code,
            job_timeout_seconds=metadata.job_timeout_seconds,
            elapsed_seconds=metadata.duration_seconds,
        )

        job_paths.cleanup_working_files(
            keep_work_files=self.config.keep_work_files,
            keep_resolved=metadata.save_resolved,
            keep_checkpoints=keep_checkpoints,
        )
        metadata.artifact_availability = job_paths.artifact_availability()

        issue_count = len(collector.to_list())
        if status == JobStatus.FAILED:
            logger.error(
                "Job failed",
                extra={
                    "job_id": metadata.job_id,
                    "source_file": metadata.source_file,
                    "status": status.value,
                    "issue_count": issue_count,
                    "stage": current_stage.value,
                },
            )
        elif status == JobStatus.COMPLETED_WITH_WARNINGS:
            logger.warning(
                "Job completed with warnings",
                extra={
                    "job_id": metadata.job_id,
                    "source_file": metadata.source_file,
                    "status": status.value,
                    "issue_count": issue_count,
                },
            )
        else:
            logger.info(
                "Job completed",
                extra={
                    "job_id": metadata.job_id,
                    "source_file": metadata.source_file,
                    "status": status.value,
                    "issue_count": issue_count,
                },
            )

        return self._deliver_webhook_if_configured(
            result=JobResult(
                job_id=metadata.job_id,
                status=status,
                artifacts=job_paths.to_artifact_paths(),
                metadata=metadata,
                discrepancies=discrepancies,
                error_message=error_message,
                error_code=error_code,
                failed_stage=current_stage if status == JobStatus.FAILED else None,
            ),
            job_paths=job_paths,
            metadata=metadata,
            collector=collector,
        )

    def _deliver_webhook_if_configured(
        self,
        *,
        result: JobResult,
        job_paths: JobPaths,
        metadata: JobMetadata,
        collector: IssueCollector,
    ) -> JobResult:
        webhook_url = self.config.webhook_url
        if not webhook_url:
            return result

        try:
            deliver_terminal_webhook(
                webhook_url,
                result,
                secret=self.config.webhook_secret,
                timeout_seconds=self.config.webhook_timeout_seconds,
                max_retries=self.config.webhook_max_retries,
                retry_base_delay=self.config.webhook_retry_base_delay,
            )
        except Exception as exc:
            logger.warning(
                "Webhook delivery failed",
                extra={"job_id": metadata.job_id, "webhook_url": webhook_url},
                exc_info=exc,
            )
            collector.add(
                IssueCode.WEBHOOK_FAILED,
                IssueSeverity.WARN,
                f"Webhook delivery failed: {exc}",
                stage=PipelineStage.COMPLETED,
            )
            metadata.issues = collector.to_list()
            status = _resolve_terminal_status(collector) if result.status != JobStatus.FAILED else result.status
            metadata.job_status = status
            job_paths.metadata_json.write_text(
                metadata.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            job_paths.write_status(
                PipelineStage.COMPLETED,
                message=(
                    "Completed with warnings"
                    if status == JobStatus.COMPLETED_WITH_WARNINGS
                    else ("Completed" if status == JobStatus.COMPLETED else result.error_message or "Failed")
                ),
                progress=1.0,
                issue_count=len(collector.to_list()),
                terminal_status=status,
                error_code=result.error_code,
                job_timeout_seconds=metadata.job_timeout_seconds,
                elapsed_seconds=metadata.duration_seconds,
            )
            result = JobResult(
                job_id=result.job_id,
                status=status,
                artifacts=result.artifacts,
                metadata=metadata,
                discrepancies=result.discrepancies,
                error_message=result.error_message,
                error_code=result.error_code,
                failed_stage=result.failed_stage,
            )
        return result

    def translate(self, input_path: Path, options: TranslationOptions | None = None) -> JobResult:
        opts = options or TranslationOptions()
        reset_job_control()
        install_job_signal_handlers()
        started = time.monotonic()
        deadline = JobDeadline(self.config.job_timeout_seconds, started=started)
        collector = IssueCollector(self._issue_listeners)
        collector.set_context(job_id=opts.job_id, source_file=input_path.name)
        current_stage = PipelineStage.EXTRACTING
        current_progress = 0.0
        discrepancies: list[Discrepancy] = []
        pipeline_state = {
            "current_stage": current_stage,
            "current_progress": current_progress,
        }

        resolved_format = resolve_export_format(input_path=input_path, requested=opts.export_format)

        job_paths = JobPaths(
            self.config.resolve_runs_dir(),
            opts.job_id,
            export_format=resolved_format,
        )
        job_paths.ensure_dirs()
        job_paths.write_queued(job_timeout_seconds=self.config.job_timeout_seconds)

        metadata = JobMetadata(
            job_id=opts.job_id,
            source_file=input_path.name,
            model=self.config.llm,
            export_format=resolved_format.value,
            target_lang=opts.target_lang,
            translation_mode=opts.translation_mode.value,
            translation_context=opts.translation_context,
            job_timeout_seconds=self.config.job_timeout_seconds,
            save_resolved=opts.save_resolved,
            no_cover_page=opts.no_cover_page,
        )
        glossary = resolve_glossary(
            glossary_path=self.config.glossary_path,
            inline_glossary=self.config.glossary,
        )
        if glossary is not None:
            metadata.glossary_term_count = len(glossary)
        if self.config.glossary_path is not None:
            metadata.glossary_path = str(self.config.glossary_path)

        with sentry_translate_transaction(opts.job_id) as sentry_transaction:
            try:
                result = self._run_translation(
                    input_path=input_path,
                    opts=opts,
                    started=started,
                    deadline=deadline,
                    collector=collector,
                    job_paths=job_paths,
                    metadata=metadata,
                    discrepancies=discrepancies,
                    pipeline_state=pipeline_state,
                    glossary=glossary,
                )
            except Exception as exc:
                metadata.completed_at = datetime.now(UTC)
                metadata.duration_seconds = time.monotonic() - started
                sync_tracker_to_metadata(metadata, self._tracker, llm_selector=self.config.llm)
                current_stage = pipeline_state["current_stage"]
                current_progress = pipeline_state["current_progress"]

                if isinstance(exc, PipelineError):
                    error_code = exc.code
                    error_message = str(exc)
                    current_stage = exc.stage
                    logger.error(
                        error_message,
                        extra={
                            "job_id": opts.job_id,
                            "source_file": input_path.name,
                            "issue_code": error_code.value,
                            "stage": current_stage.value,
                        },
                    )
                    collector.add(
                        error_code,
                        IssueSeverity.ERROR,
                        error_message,
                        stage=current_stage,
                        scope=exc.scope,
                        cause=exc.cause,
                    )
                else:
                    error_code = IssueCode.PIPELINE_FAILED
                    error_message = str(exc)
                    logger.exception(
                        "Unexpected pipeline failure",
                        extra={
                            "job_id": opts.job_id,
                            "source_file": input_path.name,
                            "stage": current_stage.value,
                        },
                    )
                    collector.add(
                        IssueCode.PIPELINE_FAILED,
                        IssueSeverity.ERROR,
                        error_message,
                        stage=current_stage,
                        cause=exc,
                    )

                result = self._finalize_job(
                    job_paths=job_paths,
                    metadata=metadata,
                    collector=collector,
                    discrepancies=discrepancies,
                    status=JobStatus.FAILED,
                    current_stage=current_stage,
                    current_progress=current_progress,
                    error_message=error_message,
                    error_code=error_code,
                    keep_checkpoints=True,
                )

            finish_sentry_transaction(sentry_transaction, status=result.status)
            return result

    def translate_batch(
        self,
        items: list[tuple[Path, TranslationOptions]],
    ) -> BatchJobResult:
        if not items:
            raise ValueError("translate_batch requires at least one input")
        results = [self.translate(path, opts) for path, opts in items]
        return BatchJobResult(jobs=results, status=aggregate_job_status(results))

    def _run_translation(
        self,
        *,
        input_path: Path,
        opts: TranslationOptions,
        started: float,
        deadline: JobDeadline,
        collector: IssueCollector,
        job_paths: JobPaths,
        metadata: JobMetadata,
        discrepancies: list[Discrepancy],
        pipeline_state: dict[str, object],
        glossary: Glossary | None = None,
    ) -> JobResult:
        current_stage = PipelineStage.EXTRACTING
        current_progress = 0.0
        resume_state = load_checkpoint(job_paths.checkpoint_json) if opts.resume else None
        if opts.resume:
            metadata.resumed_from_checkpoint = True

        def status_kwargs() -> dict[str, float | None]:
            return self._status_timing(self.config, deadline)

        def persist_checkpoint(
            *,
            stage: CheckpointStage,
            chunk_index: int = -1,
            pass_num: int = 1,
            source_hash: str,
            chunk_count: int = 0,
        ) -> None:
            state = CheckpointState(
                stage=stage,
                chunk_index=chunk_index,
                pass_num=pass_num,
                source_hash=source_hash,
                llm=self.config.llm,
                translation_mode=opts.translation_mode.value,
                chunk_count=chunk_count,
                target_lang=opts.target_lang,
            )
            write_checkpoint(job_paths.checkpoint_json, state)
            metadata.checkpoint_stage = stage.value

        def validate_resume_state(source_hash: str) -> None:
            if resume_state is None:
                raise PipelineError(
                    "No checkpoint found for resume",
                    code=IssueCode.CHECKPOINT_MISMATCH,
                    stage=PipelineStage.EXTRACTING,
                )
            if (
                resume_state.llm != self.config.llm
                or resume_state.translation_mode != opts.translation_mode.value
                or resume_state.target_lang != opts.target_lang
            ):
                raise PipelineError(
                    "Checkpoint does not match current LLM, translation mode, or target language",
                    code=IssueCode.CHECKPOINT_MISMATCH,
                    stage=PipelineStage.TRANSLATING,
                )
            if resume_state.source_hash != source_hash:
                raise PipelineError(
                    "Source content changed since checkpoint; cannot resume",
                    code=IssueCode.CHECKPOINT_MISMATCH,
                    stage=PipelineStage.EXTRACTING,
                )

        skip_extract = bool(
            opts.resume and resume_state is not None and job_paths.extracted_md.is_file()
        )
        extraction_result: ExtractionResult | None = None

        deadline.check(current_stage)
        if not supported_extension(input_path):
            raise UnsupportedFormatError(input_path.suffix)

        if skip_extract:
            metadata.resumed_from_checkpoint = True
            extracted_md = job_paths.extracted_md.read_text(encoding="utf-8")
            layout_body = read_layout_body_checkpoint(job_paths.checkpoints_extract_dir)
            if layout_body is not None:
                body_text = layout_body
                metadata.used_layout_text = True
            else:
                body_text = strip_front_matter(extracted_md)
            current_progress = 0.15
            pipeline_state["current_stage"] = PipelineStage.DETECTING_LANGUAGE
            pipeline_state["current_progress"] = current_progress
        else:
            current_progress = 0.05
            pipeline_state["current_stage"] = PipelineStage.EXTRACTING
            pipeline_state["current_progress"] = current_progress
            self._log_stage(opts.job_id, PipelineStage.EXTRACTING, current_progress, "Extracting document")
            job_paths.write_status(
                PipelineStage.EXTRACTING,
                message="Extracting document",
                progress=current_progress,
                issue_count=0,
                **status_kwargs(),
            )

            try:
                validate_input_file(input_path, max_bytes=self.config.max_input_bytes)
            except ValueError as exc:
                raise PipelineError(
                    str(exc),
                    code=IssueCode.CONFIGURATION_ERROR,
                    stage=PipelineStage.EXTRACTING,
                ) from exc

            dest_input = job_paths.input_dir / input_path.name
            if input_path.resolve() != dest_input.resolve():
                shutil.copy2(input_path, dest_input, follow_symlinks=False)

            deadline.check(current_stage)
            extraction = extract_single_file(dest_input, config=self.config)
            deadline.check(current_stage)
            alerts = compute_extraction_alerts(extraction, input_path.name)
            metadata.extraction_alerts = alerts
            metadata.page_count = extraction.pages
            metadata.conversion_method = extraction.conversion_method
            metadata.extract_backend = extraction.extract_backend
            metadata.extract_page_stats = list(extraction.extract_page_stats)
            add_extract_breadcrumb(
                backend=extraction.extract_backend,
                pages=extraction.pages,
                ocr_pages=extraction.ocr_pages,
                source_file=input_path.name,
            )

            for alert in alerts:
                collector.add_from_alert(alert, stage=PipelineStage.EXTRACTING)
            if extraction.extract_backend == "pymupdf":
                for option in liteparse_only_options_active(self.config):
                    collector.add(
                        IssueCode.EXTRACT_OPTION_IGNORED,
                        IssueSeverity.WARN,
                        f"Extract option {option!r} is only supported by the liteparse backend",
                        stage=PipelineStage.EXTRACTING,
                        scope={"option": option},
                    )
            if extraction.ocr_pages > 0:
                collector.add(
                    IssueCode.OCR_APPLIED,
                    IssueSeverity.INFO,
                    f"OCR applied to {extraction.ocr_pages} page(s)",
                    stage=PipelineStage.EXTRACTING,
                    scope={"file": input_path.name, "ocr_pages": str(extraction.ocr_pages)},
                )
            if extraction.ocr_unavailable:
                if self.config.pdf_ocr_server_url:
                    ocr_message = (
                        "Sparse PDF pages detected but neither HTTP OCR server nor Tesseract is available"
                    )
                else:
                    ocr_message = "Sparse PDF pages detected but Tesseract is not installed"
                collector.add(
                    IssueCode.OCR_UNAVAILABLE,
                    IssueSeverity.WARN,
                    ocr_message,
                    stage=PipelineStage.EXTRACTING,
                    scope={"file": input_path.name},
                )
            for warning in extraction.conversion_warnings:
                collector.add(
                    IssueCode.CONVERSION_DEGRADED,
                    IssueSeverity.WARN,
                    warning,
                    stage=PipelineStage.EXTRACTING,
                    scope={"file": input_path.name},
                )

            extracted_md = build_extracted_markdown(
                extraction,
                source_file=input_path.name,
                alerts=alerts,
            )
            job_paths.extracted_md.write_text(extracted_md, encoding="utf-8")
            persist_extraction_sidecars(job_paths, extraction)
            extraction_result = extraction
            body_text = strip_front_matter(extracted_md)

            if self.config.fail_on_empty_extraction and not body_text.strip():
                raise PipelineError(
                    f"{input_path.name}: extraction produced no text",
                    code=IssueCode.EMPTY_EXTRACTION,
                    stage=PipelineStage.EXTRACTING,
                    scope={"file": input_path.name},
                )

        if self.config.preserve_layout:
            metadata.preserve_layout = True
        if self.config.preserve_layout and skip_extract and not metadata.used_layout_text:
            collector.add(
                IssueCode.PRESERVE_LAYOUT_UNAVAILABLE,
                IssueSeverity.WARN,
                "preserve_layout requested but layout text is unavailable when resuming from checkpoint",
                stage=PipelineStage.EXTRACTING,
            )
        elif self.config.preserve_layout and extraction_result is not None:
            layout_body = translation_body_text(extraction_result, preserve_layout=True)
            if extraction_result.layout_text:
                body_text = layout_body
                metadata.used_layout_text = True
            else:
                collector.add(
                    IssueCode.PRESERVE_LAYOUT_UNAVAILABLE,
                    IssueSeverity.WARN,
                    "preserve_layout requested but extractor did not provide layout_text",
                    stage=PipelineStage.EXTRACTING,
                )

        if metadata.used_layout_text:
            write_layout_body_checkpoint(job_paths.checkpoints_extract_dir, body_text)

        body_hash = source_text_hash(body_text)
        if opts.resume:
            validate_resume_state(body_hash)
        elif not skip_extract:
            persist_checkpoint(stage=CheckpointStage.EXTRACTED, source_hash=body_hash)

        current_stage = PipelineStage.DETECTING_LANGUAGE
        current_progress = 0.15
        pipeline_state["current_stage"] = current_stage
        pipeline_state["current_progress"] = current_progress
        deadline.check(current_stage)
        self._log_stage(opts.job_id, current_stage, current_progress, "Detecting language")
        job_paths.write_status(
            current_stage,
            message="Detecting language",
            progress=current_progress,
            issue_count=len(collector.to_list()),
            **status_kwargs(),
        )
        detected_lang, lang_conf, lang_used_ai = detect_language(
            body_text,
            llm=self.llm,
            confidence_threshold=self.config.lang_confidence_threshold,
        )
        deadline.check(current_stage)
        if opts.source_lang is not None:
            metadata.source_lang_override = True
            metadata.source_lang = opts.source_lang
            metadata.source_lang_confidence = 1.0
            metadata.lang_used_ai = False
            if detected_lang != "unknown" and detected_lang != opts.source_lang:
                collector.add(
                    IssueCode.SOURCE_LANG_MISMATCH,
                    IssueSeverity.WARN,
                    (
                        f"Source language override {opts.source_lang!r} differs from "
                        f"detected {detected_lang!r}"
                    ),
                    stage=PipelineStage.DETECTING_LANGUAGE,
                    scope={
                        "override": opts.source_lang,
                        "detected": detected_lang,
                        "detected_confidence": str(lang_conf),
                    },
                )
            source_lang = opts.source_lang
        else:
            source_lang = detected_lang
            metadata.source_lang = source_lang
            metadata.source_lang_confidence = lang_conf
            metadata.lang_used_ai = lang_used_ai
            if lang_used_ai:
                collector.add(
                    IssueCode.LANGUAGE_LOW_CONFIDENCE,
                    IssueSeverity.WARN,
                    "Language detection used AI fallback due to low confidence",
                    stage=PipelineStage.DETECTING_LANGUAGE,
                )

        is_legal, legal_used_ai, legal_parse_failed = classify_legal_document(body_text, self.llm)
        deadline.check(current_stage)
        metadata.is_legal_document = is_legal
        metadata.legal_used_ai = legal_used_ai
        if legal_used_ai:
            collector.add(
                IssueCode.LEGAL_CLASSIFICATION_AI,
                IssueSeverity.INFO,
                "Legal document classification confirmed via AI (ambiguous heuristic)",
                stage=PipelineStage.DETECTING_LANGUAGE,
            )
        if legal_parse_failed:
            collector.add(
                IssueCode.LLM_RESPONSE_PARSE_FAILED,
                IssueSeverity.WARN,
                "Legal classification AI response could not be parsed; used keyword heuristic",
                stage=PipelineStage.DETECTING_LANGUAGE,
            )

        skip_translation = opts.no_translate or source_lang == opts.target_lang
        thorough = opts.translation_mode == TranslationMode.THOROUGH

        if skip_translation:
            metadata.skipped_translation = True
            metadata.no_translate = opts.no_translate
            job_paths.translation_1_md.write_text(body_text, encoding="utf-8")
            if thorough:
                job_paths.translation_2_md.write_text(body_text, encoding="utf-8")
            job_paths.resolved_md.write_text(body_text, encoding="utf-8")
            discrepancies.clear()
        elif (
            opts.resume
            and resume_state is not None
            and resume_state.stage == CheckpointStage.COMPLETED
            and job_paths.resolved_md.is_file()
        ):
            metadata.resumed_from_checkpoint = True
            discrepancies.clear()
        else:
            source_chunks = chunk_document(
                body_text,
                max_chars=self.config.chunk_size,
                overlap_sentences=self.config.chunk_overlap_sentences,
            )
            metadata.chunk_count = len(source_chunks)
            write_extract_chunk_checkpoints(
                job_paths.checkpoints_extract_dir,
                chunks=[chunk.text for chunk in source_chunks],
            )
            document_summary = build_document_summary(body_text)
            translation_context = opts.translation_context or ""

            def make_chunk_callback(pass_num: int):
                def _on_chunk_complete(chunk_index: int, text: str) -> None:
                    write_chunk_checkpoint(
                        job_paths.checkpoints_dir,
                        pass_num=pass_num,
                        chunk_index=chunk_index,
                        text=text,
                        source_hash=body_hash,
                        llm=self.config.llm,
                    )
                    persist_checkpoint(
                        stage=CheckpointStage.TRANSLATING_PASS1
                        if pass_num == 1
                        else CheckpointStage.TRANSLATING_PASS2,
                        chunk_index=chunk_index,
                        pass_num=pass_num,
                        source_hash=body_hash,
                        chunk_count=len(source_chunks),
                    )

                return _on_chunk_complete

            completed_pass1: dict[int, str] = {}
            if opts.resume:
                completed_pass1 = load_completed_chunks(
                    job_paths.checkpoints_dir,
                    pass_num=1,
                    chunk_count=len(source_chunks),
                    source_hash=body_hash,
                    llm=self.config.llm,
                )

            current_stage = PipelineStage.TRANSLATING
            current_progress = 0.3
            pipeline_state["current_stage"] = current_stage
            pipeline_state["current_progress"] = current_progress
            deadline.check(current_stage)
            translate_message = "Translating (pass 1)" if thorough else "Translating"
            self._log_stage(opts.job_id, current_stage, current_progress, translate_message)
            job_paths.write_status(
                current_stage,
                message=translate_message,
                progress=current_progress,
                issue_count=len(collector.to_list()),
                **status_kwargs(),
            )
            trans1_chunks = translate_source_chunks(
                self.llm,
                source_chunks,
                source_lang=source_lang,
                target_lang=opts.target_lang,
                is_legal=is_legal,
                document_summary=document_summary,
                translation_context=translation_context,
                glossary=glossary,
                max_workers=self.config.max_concurrent_chunks,
                deadline=deadline,
                completed_chunks=completed_pass1,
                on_chunk_complete=make_chunk_callback(1),
            )
            trans1 = reassemble_chunks(trans1_chunks)
            job_paths.translation_1_md.write_text(trans1, encoding="utf-8")
            persist_checkpoint(
                stage=CheckpointStage.TRANSLATING_PASS2 if thorough else CheckpointStage.RECONCILING,
                chunk_index=len(source_chunks) - 1,
                pass_num=1,
                source_hash=body_hash,
                chunk_count=len(source_chunks),
            )

            if thorough:
                completed_pass2: dict[int, str] = {}
                if opts.resume:
                    completed_pass2 = load_completed_chunks(
                        job_paths.checkpoints_dir,
                        pass_num=2,
                        chunk_count=len(source_chunks),
                        source_hash=body_hash,
                        llm=self.config.llm,
                    )

                current_progress = 0.5
                pipeline_state["current_progress"] = current_progress
                deadline.check(current_stage)
                self._log_stage(opts.job_id, current_stage, current_progress, "Translating (pass 2)")
                job_paths.write_status(
                    current_stage,
                    message="Translating (pass 2)",
                    progress=current_progress,
                    issue_count=len(collector.to_list()),
                    **status_kwargs(),
                )
                trans2_chunks = translate_source_chunks(
                    self.llm,
                    source_chunks,
                    source_lang=source_lang,
                    target_lang=opts.target_lang,
                    is_legal=is_legal,
                    document_summary=document_summary,
                    translation_context=translation_context,
                    glossary=glossary,
                    max_workers=self.config.max_concurrent_chunks,
                    deadline=deadline,
                    completed_chunks=completed_pass2,
                    on_chunk_complete=make_chunk_callback(2),
                )
                if len(trans1_chunks) != len(trans2_chunks):
                    raise ChunkCountMismatchError(len(trans1_chunks), len(trans2_chunks))
                trans2 = reassemble_chunks(trans2_chunks)
                job_paths.translation_2_md.write_text(trans2, encoding="utf-8")
                persist_checkpoint(
                    stage=CheckpointStage.RECONCILING,
                    chunk_index=len(source_chunks) - 1,
                    pass_num=2,
                    source_hash=body_hash,
                    chunk_count=len(source_chunks),
                )

                current_stage = PipelineStage.RECONCILING
                current_progress = 0.7
                pipeline_state["current_stage"] = current_stage
                pipeline_state["current_progress"] = current_progress
                deadline.check(current_stage)
                self._log_stage(opts.job_id, current_stage, current_progress, "Comparing and resolving discrepancies")
                job_paths.write_status(
                    current_stage,
                    message="Comparing and resolving discrepancies",
                    progress=current_progress,
                    issue_count=len(collector.to_list()),
                    **status_kwargs(),
                )
                resolved, new_discrepancies = reconcile_translations(
                    self.llm,
                    source_chunks=source_chunks,
                    translation_1_chunks=trans1_chunks,
                    translation_2_chunks=trans2_chunks,
                    source_lang=source_lang,
                    target_lang=opts.target_lang,
                    is_legal=is_legal,
                    document_summary=document_summary,
                    translation_context=translation_context,
                    glossary=glossary,
                    similarity_threshold=self.config.similarity_threshold,
                    collector=collector,
                    deadline=deadline,
                )
                discrepancies.clear()
                discrepancies.extend(new_discrepancies)
                job_paths.resolved_md.write_text(resolved, encoding="utf-8")
                persist_checkpoint(
                    stage=CheckpointStage.COMPLETED,
                    chunk_index=len(source_chunks) - 1,
                    pass_num=2,
                    source_hash=body_hash,
                    chunk_count=len(source_chunks),
                )
            else:
                current_progress = 0.65
                pipeline_state["current_progress"] = current_progress
                job_paths.write_status(
                    current_stage,
                    message="Translating",
                    progress=current_progress,
                    issue_count=len(collector.to_list()),
                    **status_kwargs(),
                )
                discrepancies.clear()
                job_paths.resolved_md.write_text(trans1, encoding="utf-8")
                persist_checkpoint(
                    stage=CheckpointStage.COMPLETED,
                    chunk_index=len(source_chunks) - 1,
                    pass_num=1,
                    source_hash=body_hash,
                    chunk_count=len(source_chunks),
                )

        metadata.discrepancy_count = len(discrepancies)
        metadata.unresolved_breaking_count = sum(
            1
            for d in discrepancies
            if d.severity == DiscrepancySeverity.BREAKING and not d.resolved
        )

        current_stage = PipelineStage.EXPORTING
        current_progress = 0.9
        pipeline_state["current_stage"] = current_stage
        pipeline_state["current_progress"] = current_progress
        deadline.check(current_stage)
        export_label = job_paths.export_format.value
        self._log_stage(opts.job_id, current_stage, current_progress, f"Exporting {export_label}")
        job_paths.write_status(
            current_stage,
            message=f"Exporting {export_label}",
            progress=current_progress,
            issue_count=len(collector.to_list()),
            **status_kwargs(),
        )
        try:
            metadata.issues = collector.to_list()
            if opts.no_cover_page:
                combined_md = build_export_markdown(
                    "",
                    job_paths.resolved_md,
                    job_paths.export_format,
                    include_cover=False,
                )
            else:
                cover_md = generate_cover_markdown(
                    metadata,
                    discrepancies,
                    has_warnings=collector.has_warnings(),
                )
                if opts.target_lang != "en" and not opts.no_translate:
                    try:
                        deadline.check(current_stage)
                        cover_md = translate_cover_markdown(
                            self.llm,
                            cover_md,
                            target_lang=opts.target_lang,
                        )
                    except Exception as exc:
                        collector.add(
                            IssueCode.COVER_TRANSLATION_FAILED,
                            IssueSeverity.WARN,
                            f"Cover page translation failed; using English cover: {exc}",
                            stage=PipelineStage.EXPORTING,
                            cause=exc,
                        )
                combined_md = build_export_markdown(
                    cover_md,
                    job_paths.resolved_md,
                    job_paths.export_format,
                )
            job_paths.combined_export_md.write_text(combined_md, encoding="utf-8")
            export_markdown(
                job_paths.combined_export_md,
                job_paths.final_output,
                job_paths.export_format,
                subprocess_timeout_seconds=self.config.subprocess_timeout_seconds,
                target_lang=opts.target_lang,
            )
            metadata.final_exported = True
        except RuntimeError as exc:
            metadata.final_exported = False
            collector.add(
                IssueCode.EXPORT_FAILED,
                IssueSeverity.WARN,
                str(exc),
                stage=PipelineStage.EXPORTING,
                scope={"format": job_paths.export_format.value},
            )

        sync_tracker_to_metadata(metadata, self._tracker, llm_selector=self.config.llm)
        metadata.completed_at = datetime.now(UTC)
        metadata.duration_seconds = time.monotonic() - started

        terminal_status = _resolve_terminal_status(collector)
        pipeline_state["current_stage"] = current_stage
        pipeline_state["current_progress"] = current_progress
        return self._finalize_job(
            job_paths=job_paths,
            metadata=metadata,
            collector=collector,
            discrepancies=discrepancies,
            status=terminal_status,
            current_stage=current_stage,
            current_progress=current_progress,
            keep_checkpoints=self.config.keep_work_files,
        )

    @staticmethod
    def _status_timing(
        config: PipelineConfig,
        deadline: JobDeadline,
    ) -> dict[str, float | None]:
        timeout = config.job_timeout_seconds
        return {
            "job_timeout_seconds": timeout,
            "elapsed_seconds": round(deadline.elapsed(), 3) if timeout is not None else None,
        }

    @staticmethod
    def _log_stage(job_id: str, stage: PipelineStage, progress: float, message: str) -> None:
        logger.info(
            message,
            extra={
                "job_id": job_id,
                "stage": stage.value,
                "progress": progress,
            },
        )
