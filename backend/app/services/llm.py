import json
import logging
import re
from groq import Groq
from app.config import settings

logger = logging.getLogger(__name__)

client = Groq(api_key=settings.GROQ_API_KEY)

# ── Model selection (cached after first call) ─────────────────────────────────
_cached_model: str | None = None


def _safe_error_category(error: Exception) -> str:
    status_code = getattr(error, "status_code", None)
    error_name = type(error).__name__.lower()

    if status_code in (401, 403):
        return "authentication"
    if status_code == 429:
        return "rate_limit_or_quota"
    if status_code == 408 or "timeout" in error_name:
        return "timeout"
    if "connection" in error_name or "connect" in error_name:
        return "network"
    if isinstance(status_code, int) and status_code >= 500:
        return "provider_server_error"
    if status_code == 400:
        return "provider_bad_request"
    return "provider_error"


def _get_model() -> str:
    """Fetch and cache the best available text model on this API key."""
    global _cached_model
    if _cached_model:
        return _cached_model

    available_models = client.models.list().data
    text_models = [m.id for m in available_models if "whisper" not in m.id.lower()]

    if not text_models:
        raise RuntimeError("No text models available on this Groq API key.")

    # Prefer known fast developer-tier models
    target = text_models[0]
    for model_id in text_models:
        if "gpt-oss-20b" in model_id.lower() or "qwen" in model_id.lower():
            target = model_id
            break

    _cached_model = target
    return _cached_model


def _try_repair_json(raw: str) -> dict | None:
    """
    Attempt to extract a JSON object from a string that has extra decoration
    (e.g. markdown fences, leading prose).  Returns None if not recoverable.
    """
    # Strip markdown fences
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    # Find first '{' and last '}'
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None


def ask_llm_json(
    prompt: str,
    retries: int = 2,
    max_tokens: int | None = None,
) -> dict:
    """
    Call the LLM and return parsed JSON. Optionally cap generated tokens for interactive calls.

    Retries up to `retries` times on failure.  On repeated failure returns
    {"error": "<reason>"}.
    """
    full_prompt = (
        prompt
        + "\n\nIMPORTANT: You must respond ONLY with valid JSON. "
        "Do not include markdown formatting like ```json or any conversational text."
    )

    last_error = "Unknown error"
    for attempt in range(max(1, retries)):
        stage = "model_discovery"
        try:
            model = _get_model()
            stage = "completion"
            completion_options: dict[str, object] = {
                "messages": [{"role": "user", "content": full_prompt}],
                "model": model,
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            }
            if max_tokens is not None:
                completion_options["max_tokens"] = max_tokens
            chat_completion = client.chat.completions.create(
                **completion_options,
            )
            raw = chat_completion.choices[0].message.content

            # Primary parse
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                # Secondary: attempt JSON repair
                repaired = _try_repair_json(raw)
                if repaired is not None:
                    return repaired
                last_error = f"JSON decode failed on attempt {attempt + 1}"
                category = "malformed_json"
                logger.warning(
                    "Groq response could not be parsed as JSON: stage=response_parse category=%s attempt=%d",
                    category,
                    attempt + 1,
                    extra={
                        "groq_stage": "response_parse",
                        "groq_category": category,
                        "groq_attempt": attempt + 1,
                    },
                )

        except Exception as e:
            last_error = str(e)
            category = _safe_error_category(e)
            logger.warning(
                "Groq request failed: stage=%s category=%s attempt=%d",
                stage,
                category,
                attempt + 1,
                extra={
                    "groq_stage": stage,
                    "groq_category": category,
                    "groq_attempt": attempt + 1,
                },
            )
            # Reset model cache if we hit an auth/quota error so it re-fetches
            if "model" in str(e).lower() or "auth" in str(e).lower():
                global _cached_model
                _cached_model = None

    return {"error": last_error}