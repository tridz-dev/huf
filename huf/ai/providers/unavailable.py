"""``ProviderUnavailableError`` and the curated, user-safe messages raised with it.

``huf.ai.providers.litellm`` re-exports these names.
"""


class ProviderUnavailableError(Exception):
    """Raised when the LLM provider cannot serve this request (conn refused, model missing,
    bad model prefix, auth). Distinct from content-level errors.

    ``public_message`` is sent to clients: it must be curated text written in huf code, NEVER raw
    exception or provider text (put that in ``log_message``). It is capped at 300 characters.
    """

    def __init__(self, public_message: str, *, log_message: str | None = None,
                 kind: str | None = None, status_code=None):
        public_message = public_message if isinstance(public_message, str) else str(public_message or "")
        self.public_message = (
            public_message if len(public_message) <= 300 else public_message[:299].rstrip() + "\u2026"
        )
        # str(e)/args carry only the capped, curated text; full detail lives in log_message.
        super().__init__(self.public_message)
        self.log_message = log_message or public_message
        self.status_code = status_code
        if kind is None:
            from huf.ai.providers.errors import classify_text
            kind = classify_text(f"{self.log_message} {public_message}")
        self.kind = kind


def _sanitize_provider_error_message(raw_message: str, normalized_model: str | None = None,
                                     provider: str | None = None, status_code=None) -> str:
    """Return a user-safe provider error message with no LiteLLM/provider internals."""
    text = (raw_message or "").lower()

    from huf.ai.providers.errors import classify_status, specific_message
    specific = specific_message(classify_status(status_code, raw_message or ""), provider, normalized_model)
    if specific:
        return specific

    if "api key not configured" in text or "password not found" in text or "invalid api key" in text:
        return "This provider is not configured correctly yet. Add or update its API key and try again."

    if any(marker in text for marker in (
        "no longer available",
        "model not found",
        "notfounderror",
        "unsupported model",
    )):
        return "The selected model is no longer available from this provider. Choose a different model and try again."

    if "ratelimit" in text or "rate limit" in text or "too many requests" in text:
        return "This provider is rate-limiting requests right now. Please wait a moment and try again."

    if "contextwindowexceedederror" in text or "context window" in text or "maximum context length" in text:
        return "This conversation is too large for the selected model. Start a new conversation or reduce the context and try again."

    if any(marker in text for marker in (
        "internalservererror",
        "server error",
        "service unavailable",
        "temporarily unavailable",
        "connection refused",
        "failed to connect",
        "connection error",
        "connection reset",
        "broken pipe",
        "unexpected eof",
    )):
        return "The AI provider is temporarily unavailable. Please try again in a moment."

    model_hint = f" for {normalized_model}" if normalized_model else ""
    return f"The AI provider could not complete this request{model_hint}. Please try again or choose a different model."


def _raise_provider_unavailable(raw_message: str, normalized_model: str | None = None,
                                provider: str | None = None, status_code=None):
    raise ProviderUnavailableError(
        _sanitize_provider_error_message(raw_message, normalized_model, provider, status_code),
        log_message=raw_message,
        status_code=status_code,
    )
