"""
OCR / document extraction engine for Huf.

Provides production-ready text extraction from any document type:
- Images: vision-capable LLMs
- PDFs: LiteLLM OCR endpoint (with retry), local PDF extraction fallback, vision fallback
- Office/text documents (DOCX, TXT, MD, HTML, ...): local extractors
- Other files: best-effort text extraction or vision for images

Design goals:
- Never process a stale file: resolve File docs by ID, verify paths, include content hashes.
- Universal format support via the existing knowledge extractor registry.
- Clear audit trail: returned metadata includes file name, hash, strategy and model used.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import mimetypes
import os
from dataclasses import dataclass
from typing import Any

import frappe

from huf.ai.knowledge.extractors import TextExtractor


# Maximum file size we are willing to read into memory for base64 encoding (bytes)
_MAX_BASE64_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

# Largest text result we will store verbatim in an Agent Message
_MAX_MESSAGE_TEXT_LENGTH = 15000


@dataclass
class ExtractionResult:
    success: bool
    text: str = ""
    pages: list[dict] | None = None
    strategy: str = ""
    model: str = ""
    file_id: str = ""
    file_name: str = ""
    file_hash: str = ""
    error: str = ""
    metadata: dict | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "text": self.text,
            "pages": self.pages or [],
            "strategy": self.strategy,
            "model": self.model,
            "file_id": self.file_id,
            "file_name": self.file_name,
            "file_hash": self.file_hash,
            "error": self.error,
            "metadata": self.metadata or {},
        }


def _log_error(message: str, title: str = "OCR Engine"):
    try:
        frappe.log_error(message, title)
    except Exception:
        pass


def _file_hash(file_path: str, algorithm: str = "sha256") -> str:
    """Return a hash of the file contents for cache-busting and verification."""
    h = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_file_doc(file_id: str | None = None, file_url: str | None = None):
    """
    Resolve a Frappe File document robustly.

    Rules:
    1. file_id is authoritative when provided.
    2. file_url is resolved directly first, then by file_name, handling both
       /files/ and /private/files/ paths.
    3. If a lookup by file_name would match multiple records, use the most recently
       created one (the newest upload) rather than an arbitrary old record.
    """
    file_doc = None

    if file_id:
        try:
            return frappe.get_doc("File", file_id)
        except frappe.DoesNotExistError:
            raise ValueError(f"File document '{file_id}' not found")
        except Exception as e:
            raise ValueError(f"Error loading File '{file_id}': {e}")

    if file_url:
        # Direct lookup by URL (handles both public and private paths)
        file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
        if file_name:
            return frappe.get_doc("File", file_name)

        # Derive a file_name from the URL and look up the newest matching record.
        # Using order_by creation desc avoids returning stale uploads that share a name.
        candidate_name = os.path.basename(file_url)
        if candidate_name:
            file_name = frappe.db.get_value(
                "File",
                {"file_name": candidate_name},
                "name",
                order_by="creation desc",
            )
            if file_name:
                return frappe.get_doc("File", file_name)

        raise ValueError(f"Could not resolve File for URL '{file_url}'")

    raise ValueError("Either file_id or file_url is required")


def _mime_type_and_extension(file_path: str, file_type: str | None = None) -> tuple[str, str]:
    """Return (mime_type, extension_lower) for a file path."""
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")

    if file_type:
        mime = file_type.strip()
    else:
        mime, _ = mimetypes.guess_type(file_path)
        mime = mime or "application/octet-stream"

    if not ext:
        # Try to recover extension from mime type
        ext = mimetypes.guess_extension(mime) or ""
        ext = ext.lower().lstrip(".")

    return mime, ext


def _is_image(mime_type: str, ext: str) -> bool:
    return mime_type.startswith("image/") or ext in {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tiff", "tif"}


def _is_pdf(mime_type: str, ext: str) -> bool:
    return mime_type == "application/pdf" or ext == "pdf"


def _is_pdf_by_content(file_path: str) -> bool:
    """Detect PDF files by magic bytes even when MIME type / extension is wrong."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(5)
            return header.startswith(b"%PDF-")
    except Exception:
        return False


def _has_local_extractor(mime_type: str, ext: str) -> bool:
    """Return True for document types we can extract locally without an LLM call."""
    known_local_types = {
        # PDF
        "application/pdf", "pdf", ".pdf",
        # Word
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx", ".docx",
        # Excel
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx", ".xlsx",
        # PowerPoint
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "pptx", ".pptx",
        # Text
        "text/plain", "txt", ".txt",
        # Markdown
        "text/markdown", "text/x-markdown", "md", ".md", "markdown",
        # HTML
        "text/html", "html", ".html", "htm", ".htm",
    }
    return mime_type.lower() in known_local_types or ext.lower() in known_local_types


def _determine_strategy(mime_type: str, ext: str, provider_name: str) -> str:
    """
    Choose the extraction strategy.

    - Images always go through vision models.
    - PDFs prefer vision for providers with strong multimodal PDF support;
      otherwise OCR endpoint. A local extraction fallback exists too.
    - Text/office documents use local extractors (fast, no API cost).
    - Unknown types attempt local extraction first, then vision if the file is small.
    """
    provider = provider_name.lower()

    if _is_image(mime_type, ext):
        return "vision"

    if _is_pdf(mime_type, ext):
        # Providers with a standard LiteLLM OCR endpoint
        if provider in {"mistral", "azure", "google", "gemini", "vertex_ai"}:
            return "ocr"
        # OpenAI, Anthropic and others do not have a LiteLLM OCR endpoint for PDFs.
        # Use standard local PDF extraction (pypdf/PyPDF2).
        return "local_pdf"

    if _has_local_extractor(mime_type, ext):
        return "local"

    # Unknown file type: if it looks text-ish, try local; otherwise vision for small files
    if mime_type.startswith("text/") or ext in {"csv", "json", "xml", "log"}:
        return "local"

    return "vision"


def _default_model(provider_name: str, strategy: str) -> str | None:
    """Return a sensible default model for the provider + strategy."""
    provider = provider_name.lower()

    if strategy == "ocr":
        return {
            "mistral": "mistral/mistral-ocr-latest",
            "azure": "azure_ai/ocr",
            "google": "vertex_ai/ocr",
            "gemini": "vertex_ai/ocr",
            "vertex_ai": "vertex_ai/ocr",
        }.get(provider)

    if strategy == "vision":
        return {
            "mistral": "mistral/mistral-small-latest",
            "openai": "gpt-4o",
            "google": "gemini/gemini-2.5-flash",
            "gemini": "gemini/gemini-2.5-flash",
            "vertex_ai": "vertex_ai/gemini-2.5-flash",
            "anthropic": "claude-3-5-sonnet-20241022",
        }.get(provider)

    return None


def _extract_local(file_path: str, mime_type: str) -> ExtractionResult:
    """Extract text using the knowledge extractor registry."""
    try:
        extractor = TextExtractor.get_extractor(mime_type)
        extracted = extractor.extract(file_path)
        return ExtractionResult(
            success=True,
            text=extracted.text or "",
            pages=[{"index": 0, "text": extracted.text or ""}],
            strategy="local",
            model="local_extractor",
            file_name=os.path.basename(file_path),
            metadata=extracted.metadata or {},
        )
    except Exception as e:
        return ExtractionResult(
            success=False,
            error=f"Local extraction failed: {e}",
            strategy="local",
            file_name=os.path.basename(file_path),
        )


async def _process_with_ocr_endpoint(
    file_path: str,
    model: str,
    api_key: str,
    pages: str | None = None,
    include_images: bool = False,
) -> ExtractionResult:
    """Process PDF/image using LiteLLM OCR endpoint with retry."""
    import litellm

    file_size = os.path.getsize(file_path)
    if file_size > _MAX_BASE64_FILE_SIZE:
        return ExtractionResult(
            success=False,
            error=(
                f"File too large for OCR endpoint ({file_size / (1024 * 1024):.1f} MB). "
                f"Maximum supported size is {_MAX_BASE64_FILE_SIZE / (1024 * 1024):.0f} MB."
            ),
            strategy="ocr",
            model=model,
            file_name=os.path.basename(file_path),
        )

    try:
        with open(file_path, "rb") as f:
            base64_content = base64.b64encode(f.read()).decode("utf-8")

        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        mime_type = "application/pdf" if ext == "pdf" else f"image/{ext}"

        ocr_params = {
            "model": model,
            "document": {
                "type": "document_url",
                "document_url": f"data:{mime_type};base64,{base64_content}",
            },
            "api_key": api_key,
        }

        if pages:
            try:
                page_list = [int(p.strip()) for p in str(pages).split(",") if p.strip()]
                if page_list:
                    ocr_params["pages"] = page_list
            except Exception:
                pass

        if include_images:
            ocr_params["include_image_base64"] = True

        # Retry loop for transient OCR endpoint failures
        last_error = None
        for attempt in range(3):
            try:
                response = await asyncio.to_thread(litellm.ocr, **ocr_params)
                break
            except Exception as e:
                last_error = e
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
                continue
        else:
            raise last_error or Exception("OCR endpoint failed after retries")

        all_text = []
        pages_data = []
        for page in getattr(response, "pages", []) or []:
            text = getattr(page, "markdown", "") or ""
            all_text.append(f"## Page {getattr(page, 'index', 0) + 1}\n\n{text}")
            pages_data.append({
                "index": getattr(page, "index", 0),
                "text": text,
                "dimensions": getattr(page, "dimensions", None),
            })

        return ExtractionResult(
            success=True,
            text="\n\n".join(all_text),
            pages=pages_data,
            strategy="ocr",
            model=model,
            file_name=os.path.basename(file_path),
        )

    except Exception as e:
        _log_error(f"OCR endpoint error for {os.path.basename(file_path)}: {e}", "OCR Endpoint")
        return ExtractionResult(
            success=False,
            error=f"OCR endpoint error: {e}",
            strategy="ocr",
            model=model,
            file_name=os.path.basename(file_path),
        )


async def _process_with_vision_model(
    file_path: str,
    model: str,
    api_key: str,
    file_name: str | None = None,
) -> ExtractionResult:
    """Process image/PDF using a vision-capable LLM via LiteLLM."""
    from huf.ai.providers.litellm import _litellm_completion_with_retry

    file_size = os.path.getsize(file_path)
    if file_size > _MAX_BASE64_FILE_SIZE:
        return ExtractionResult(
            success=False,
            error=(
                f"File too large for vision model ({file_size / (1024 * 1024):.1f} MB). "
                f"Maximum supported size is {_MAX_BASE64_FILE_SIZE / (1024 * 1024):.0f} MB."
            ),
            strategy="vision",
            model=model,
            file_name=file_name or os.path.basename(file_path),
        )

    try:
        with open(file_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")

        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        mime_type = "application/pdf" if ext == "pdf" else f"image/{ext}"

        prompt_text = (
            f"Extract all text from the attached file '{file_name or os.path.basename(file_path)}'. "
            "Preserve formatting, structure, and layout. Return the text in markdown format. "
            "If the file contains no text, state that explicitly."
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": f"data:{mime_type};base64,{base64_image}"},
                ],
            }
        ]

        response = await _litellm_completion_with_retry(
            model=model,
            messages=messages,
            api_key=api_key,
            timeout=180,
        )

        extracted_text = response.choices[0].message.content or ""

        return ExtractionResult(
            success=True,
            text=extracted_text,
            pages=[{"index": 0, "text": extracted_text}],
            strategy="vision",
            model=model,
            file_name=file_name or os.path.basename(file_path),
        )

    except Exception as e:
        _log_error(f"Vision model error for {file_name or os.path.basename(file_path)}: {e}", "OCR Vision")
        return ExtractionResult(
            success=False,
            error=f"Vision model error: {e}",
            strategy="vision",
            model=model,
            file_name=file_name or os.path.basename(file_path),
        )


def _build_agent_message_content(file_name: str, extracted_text: str, strategy: str, model: str) -> str:
    """Build a concise but unambiguous Agent Message content for the extraction result."""
    preview = extracted_text[:_MAX_MESSAGE_TEXT_LENGTH]
    if len(extracted_text) > _MAX_MESSAGE_TEXT_LENGTH:
        preview += (
            f"\n\n... [Extraction truncated from {len(extracted_text)} characters to "
            f"{_MAX_MESSAGE_TEXT_LENGTH} characters. The full text was returned to the tool caller.]"
        )

    return (
        f"**Extracted text from '{file_name}'** (method: {strategy}, model: {model})\n\n{preview}"
    )


async def extract_document(
    agent_doc,
    file_id: str | None = None,
    file_url: str | None = None,
    pages: str | None = None,
    include_images: bool = False,
    model: str | None = None,
    create_message: bool = True,
    conversation_id: str | None = None,
    agent_run_id: str | None = None,
) -> ExtractionResult:
    """
    Extract text from any document/image.

    This is the main entry point used by handle_ocr_document in sdk_tools.py.
    """
    provider_doc = frappe.get_doc("AI Provider", agent_doc.provider)
    api_key = provider_doc.get_password("api_key")
    if not api_key:
        return ExtractionResult(success=False, error="API key not configured for provider")

    # Resolve file
    try:
        file_doc = _resolve_file_doc(file_id=file_id, file_url=file_url)
    except Exception as e:
        return ExtractionResult(success=False, error=str(e))

    # Permission check: user must be able to read the File record
    if not file_doc.has_permission("read"):
        return ExtractionResult(
            success=False,
            error="You do not have permission to read this file",
            file_id=file_doc.name,
            file_name=file_doc.file_name,
        )

    file_path = file_doc.get_full_path()

    # Path traversal safety: ensure resolved path lives inside the site files area
    # Private files are stored under a separate path, so check against the correct root.
    try:
        from frappe.utils import get_files_path

        is_private = bool(getattr(file_doc, "is_private", 0))
        files_path = get_files_path(is_private=is_private)
        real_file_path = os.path.realpath(file_path)
        real_files_path = os.path.realpath(files_path)
        if not real_file_path.startswith(real_files_path + os.sep):
            return ExtractionResult(
                success=False,
                error="Resolved file path is outside the allowed files directory",
                file_id=file_doc.name,
                file_name=file_doc.file_name,
            )
    except Exception:
        pass

    if not os.path.exists(file_path):
        return ExtractionResult(
            success=False,
            error=f"File not found on disk at '{file_path}'",
            file_id=file_doc.name,
            file_name=file_doc.file_name,
        )

    try:
        file_size = os.path.getsize(file_path)
    except Exception:
        file_size = 0

    mime_type, ext = _mime_type_and_extension(file_path, file_doc.file_type)

    # Some uploads arrive with a generic or wrong MIME type (e.g. application/octet-stream
    # or a missing extension). If the file content is clearly a PDF, treat it as one so it
    # gets routed to PDF-capable extractors instead of a generic/local extractor.
    if _is_pdf_by_content(file_path):
        mime_type = "application/pdf"
        if ext != "pdf":
            ext = ext or "pdf"

    file_name = file_doc.file_name or os.path.basename(file_path)
    content_hash = _file_hash(file_path)

    provider_name = (provider_doc.provider_name or "").lower()
    strategy = _determine_strategy(mime_type, ext, provider_name)

    # Resolve model
    ocr_model = model
    if not ocr_model:
        ocr_model = _default_model(provider_name, strategy)
    if not ocr_model and strategy in {"ocr", "vision"}:
        return ExtractionResult(
            success=False,
            error=(
                f"No default model for provider '{provider_doc.provider_name}' "
                f"with strategy '{strategy}'. Provide a model parameter."
            ),
            file_id=file_doc.name,
            file_name=file_name,
            file_hash=content_hash,
            strategy=strategy,
        )

    from huf.ai.providers.litellm import _normalize_model_name

    result: ExtractionResult | None = None

    # Strategy: local extractors (DOCX, TXT, HTML, etc.)
    if strategy == "local":
        result = _extract_local(file_path, mime_type)

    # Strategy: local PDF extraction
    elif strategy == "local_pdf":
        result = _extract_local(file_path, "application/pdf")

    # Strategy: OCR endpoint
    elif strategy == "ocr":
        normalized_model = _normalize_model_name(ocr_model, agent_doc.provider)
        result = await _process_with_ocr_endpoint(
            file_path, normalized_model, api_key, pages, include_images
        )

    # Strategy: vision model
    elif strategy == "vision":
        normalized_model = _normalize_model_name(ocr_model, agent_doc.provider)
        result = await _process_with_vision_model(file_path, normalized_model, api_key, file_name)

    else:
        return ExtractionResult(
            success=False,
            error=f"Unknown extraction strategy '{strategy}'",
            file_id=file_doc.name,
            file_name=file_name,
            file_hash=content_hash,
        )

    # Fallback chain for PDFs: if the standard LiteLLM OCR endpoint failed,
    # fall back to local PDF extraction. We do not send PDFs to vision models
    # because provider support is inconsistent and non-standard.
    if not result.success and _is_pdf(mime_type, ext) and strategy != "local_pdf":
        _log_error(
            f"Primary extraction failed for PDF '{file_name}' ({strategy}); falling back to local PDF extraction.",
            "OCR Fallback",
        )
        result = _extract_local(file_path, "application/pdf")

    # Fallback chain for unknown / failed non-PDFs that are small enough to be images
    if not result.success and not _is_pdf(mime_type, ext) and file_size <= _MAX_BASE64_FILE_SIZE:
        if strategy != "vision" and _default_model(provider_name, "vision"):
            _log_error(
                f"Local extraction failed for '{file_name}'; falling back to vision model.",
                "OCR Fallback",
            )
            vision_model = _normalize_model_name(_default_model(provider_name, "vision"), agent_doc.provider)
            result = await _process_with_vision_model(file_path, vision_model, api_key, file_name)

    # Enrich result with file metadata
    if result:
        result.file_id = file_doc.name
        result.file_name = file_name
        result.file_hash = content_hash

    if not result or not result.success:
        return result or ExtractionResult(
            success=False,
            error="Extraction failed with no additional details",
            file_id=file_doc.name,
            file_name=file_name,
            file_hash=content_hash,
            strategy=strategy,
            model=ocr_model or "",
        )

    # Create Agent Message if requested
    if create_message and conversation_id:
        try:
            last_index = frappe.db.sql(
                """
                SELECT MAX(conversation_index) as last_index
                FROM `tabAgent Message`
                WHERE conversation = %s
                """,
                (conversation_id,),
                as_dict=1,
            )
            conversation_index = (
                last_index[0].last_index if last_index and last_index[0].last_index is not None else 0
            ) + 1

            message_doc = frappe.get_doc(
                {
                    "doctype": "Agent Message",
                    "conversation": conversation_id,
                    "role": "agent",
                    "content": _build_agent_message_content(
                        file_name, result.text, result.strategy, result.model
                    ),
                    "kind": "Message",
                    "agent": agent_doc.name,
                    "provider": agent_doc.provider,
                    "model": agent_doc.model,
                    "agent_run": agent_run_id,
                    "conversation_index": conversation_index,
                    "is_agent_message": 1,
                    "user": "Agent",
                }
            )
            message_doc.insert(ignore_permissions=True)

            frappe.db.sql(
                """
                UPDATE `tabAgent Conversation`
                SET total_messages = %s, last_activity = NOW()
                WHERE name = %s
                """,
                (conversation_index, conversation_id),
            )
            frappe.db.commit()

            try:
                frappe.publish_realtime(
                    event=f"conversation:{conversation_id}",
                    message={
                        "type": "new_agent_message",
                        "conversation_id": conversation_id,
                        "message_id": message_doc.name,
                        "kind": "Message",
                        "content": message_doc.content,
                        "conversation_index": conversation_index,
                    },
                    user=frappe.session.user,
                    after_commit=False,
                )
            except Exception as e:
                _log_error(f"Error emitting OCR socket event: {e}", "OCR Socket Event")

            result.metadata = (result.metadata or {}) | {"message_id": message_doc.name}

        except Exception as e:
            _log_error(f"Error creating Agent Message for OCR: {e}", "OCR Message Creation")

    return result
