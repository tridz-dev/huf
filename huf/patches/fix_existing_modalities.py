import frappe
import json


VALID_MODALITIES = {"Text", "Image", "Text-to-Speech", "Transcription", "Embeddings"}

MODEL_NAME_MODALITY_MAP = {
    "elevenlabs": "Text-to-Speech",
    "whisper": "Transcription",
    "transcrib": "Transcription",
    "dall-e": "Image",
    "dall_e": "Image",
    "gpt-image": "Image",
    "qwen3-vl": "Image",
    "vision": "Image",
    "vl": "Image",
    "image": "Image",
    "embedding": "Embeddings",
    "embed": "Embeddings",
    "text-embedding": "Embeddings",
}


def normalize_value(value):
    value = (value or "").strip()
    if not value:
        return None

    normalized = value.lower()
    if normalized == "text":
        return "Text"
    if normalized == "image":
        return "Image"
    if normalized in {"audio", "transcription"}:
        return "Transcription"
    if normalized == "text-to-speech":
        return "Text-to-Speech"
    if normalized == "embeddings":
        return "Embeddings"

    return None


def resolve_explicit_modalities(model_name):
    model_name = (model_name or "").lower()
    for pattern, mod in MODEL_NAME_MODALITY_MAP.items():
        if pattern in model_name:
            return mod
    return None


def execute():
    """Fix old AI Model modalities values for the current site."""
    records = frappe.db.sql(
        "SELECT name, model_name, modalities FROM `tabAI Model` WHERE IFNULL(modalities, '') != ''",
        as_dict=True,
    )

    updated_count = 0
    for record in records:
        try:
            raw = record.modalities
            values = []
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        values = parsed
                    else:
                        values = [parsed]
                except Exception:
                    values = [v.strip() for v in str(raw).split(",") if v.strip()]

            normalized = [normalize_value(v) for v in values if normalize_value(v)]
            explicit = resolve_explicit_modalities(record.model_name or record.name)

            if normalized:
                new_modalities = normalized[0]
            elif explicit:
                new_modalities = explicit
            else:
                new_modalities = None

            if new_modalities is None:
                frappe.db.set_value("AI Model", record.name, "modalities", None, update_modified=False)
                updated_count += 1
            else:
                if str(new_modalities) != str(raw):
                    frappe.db.set_value("AI Model", record.name, "modalities", new_modalities, update_modified=False)
                    updated_count += 1
        except Exception as exc:
            frappe.log_error(
                f"Error fixing modalities for {record.name}: {str(exc)}",
                "Fix Existing Modalities",
            )

    if updated_count > 0:
        frappe.db.commit()
        print(f"✅ Fixed modalities for {updated_count} AI Model records")
