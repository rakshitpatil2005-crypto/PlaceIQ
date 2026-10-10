from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import random
import re
import threading
import time
from typing import Any
from groq import Groq
from app.config import settings

logger = logging.getLogger(__name__)

client = Groq(api_key=settings.GROQ_API_KEY, max_retries=0, timeout=40.0)

# ── Model selection (cached after first call) ─────────────────────────────────
_cached_model: str | None = None
_MAX_AUTOMATIC_RETRY_WAIT_SECONDS = 10
_MAX_WRAPPER_ATTEMPTS = 2
_MAX_CONCURRENT_PROVIDER_REQUESTS = 2
_MAX_PROVIDER_QUEUE_WAIT_SECONDS = 5
_RATE_LIMIT_FALLBACK_COOLDOWN_SECONDS = 0.75
_provider_slots = threading.BoundedSemaphore(_MAX_CONCURRENT_PROVIDER_REQUESTS)
_rate_limit_lock = threading.Lock()
_rate_limited_until = 0.0


def _register_rate_limit(
    retry_after: float | None,
    fallback_wait_seconds: float,
) -> float:
    global _rate_limited_until
    cooldown = (
        retry_after
        if retry_after is not None
        else fallback_wait_seconds
    )
    with _rate_limit_lock:
        _rate_limited_until = max(
            _rate_limited_until,
            time.monotonic() + max(0.0, cooldown),
        )
        return max(0.0, _rate_limited_until - time.monotonic())


def _acquire_provider_slot(
    ignore_rate_limit: bool = False,
) -> tuple[bool, float | None, str | None]:
    deadline: float | None = None
    while True:
        if ignore_rate_limit:
            cooldown = 0.0
        else:
            with _rate_limit_lock:
                cooldown = max(0.0, _rate_limited_until - time.monotonic())
        if cooldown > _MAX_AUTOMATIC_RETRY_WAIT_SECONDS:
            return False, cooldown, "rate_limit_exceeded"
        if cooldown:
            time.sleep(cooldown)

        if deadline is None:
            deadline = time.monotonic() + _MAX_PROVIDER_QUEUE_WAIT_SECONDS
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not _provider_slots.acquire(timeout=remaining):
            return False, 1.0, "provider_busy"

        if ignore_rate_limit:
            cooldown = 0.0
        else:
            with _rate_limit_lock:
                cooldown = max(0.0, _rate_limited_until - time.monotonic())
        if not cooldown:
            return True, None, None

        _provider_slots.release()
        deadline = None
        if cooldown > _MAX_AUTOMATIC_RETRY_WAIT_SECONDS:
            return False, cooldown, "rate_limit_exceeded"
        time.sleep(cooldown)


class LLMJSONResponse(dict[str, Any]):
    def __init__(
        self,
        payload: dict[str, Any],
        model: str,
        attempts: int,
        duration_ms: int = 0,
    ) -> None:
        super().__init__(payload)
        self.provider_model = model
        self.attempts = attempts
        self.duration_ms = duration_ms
        self.response_format = "json_object"


def _safe_error_category(error: Exception) -> str:
    status_code = getattr(error, "status_code", None)
    error_name = type(error).__name__.lower()
    body = getattr(error, "body", None)
    provider_code = (
        body.get("error", {}).get("code")
        if isinstance(body, dict) and isinstance(body.get("error"), dict)
        else body.get("code")
        if isinstance(body, dict)
        else None
    )

    if status_code in (401, 403):
        return "authentication"
    if status_code == 429:
        if provider_code in {"insufficient_quota", "quota_exceeded"}:
            return "quota_exceeded"
        return "rate_limit_exceeded"
    if status_code == 408 or "timeout" in error_name:
        return "timeout"
    if "connection" in error_name or "connect" in error_name:
        return "network"
    if isinstance(status_code, int) and status_code >= 500:
        return "provider_server_error"
    if status_code == 404:
        return "model_unavailable"
    if status_code == 400:
        return "provider_bad_request"
    return "provider_error"


def _retry_after_seconds(error: Exception) -> float | None:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {})
    for header_name, multiplier in (
        ("retry-after", 1.0),
        ("retry-after-ms", 0.001),
        ("x-ratelimit-reset-requests", 1.0),
        ("x-ratelimit-reset-tokens", 1.0),
    ):
        raw_value = headers.get(header_name) if headers else None
        if not raw_value:
            continue
        try:
            normalized = str(raw_value).strip().lower()
            if normalized.endswith("ms"):
                seconds = float(normalized[:-2]) / 1000
            elif normalized.endswith("s"):
                seconds = float(normalized[:-1])
            else:
                seconds = float(normalized) * multiplier
            return max(0.0, seconds)
        except (TypeError, ValueError):
            if header_name != "retry-after":
                continue
            try:
                retry_at = parsedate_to_datetime(str(raw_value))
            except (TypeError, ValueError, OverflowError):
                continue
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
    return None


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
    last_category = "provider_error"
    last_status_code: int | None = None
    last_retry_after: float | None = None
    last_model: str | None = None
    attempts_made = 0
    started_at = time.monotonic()
    max_attempts = min(max(1, retries), _MAX_WRAPPER_ATTEMPTS)
    for attempt in range(max_attempts):
        slot_acquired, wait_seconds, gate_category = _acquire_provider_slot(
            ignore_rate_limit=attempt > 0 and last_category == "rate_limit_exceeded",
        )
        if not slot_acquired:
            last_category = gate_category or "provider_busy"
            last_retry_after = wait_seconds
            last_status_code = 429 if last_category == "rate_limit_exceeded" else None
            logger.warning(
                "Groq request deferred: stage=shared_request_gate category=%s status=%s",
                last_category,
                last_status_code if last_status_code is not None else "none",
                extra={
                    "groq_stage": "shared_request_gate",
                    "groq_category": last_category,
                    "groq_status_code": last_status_code,
                    "groq_retry_after_seconds": last_retry_after,
                },
            )
            break

        stage = "model_discovery"
        model: str | None = None
        attempts_made = attempt + 1
        try:
            model = _get_model()
            last_model = model
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
                if not isinstance(raw, str):
                    raise TypeError("Provider response content was not text")
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise TypeError("Provider response JSON was not an object")
                duration_ms = int((time.monotonic() - started_at) * 1000)
                logger.info(
                    "Groq request completed: provider=%s stage=response_parse category=success "
                    "status=200 response_format=json_object attempt=%d duration_ms=%d",
                    model,
                    attempt + 1,
                    duration_ms,
                    extra={
                        "groq_stage": "response_parse",
                        "groq_category": "success",
                        "groq_attempt": attempt + 1,
                        "groq_model": model,
                        "groq_status_code": 200,
                        "groq_response_format": "json_object",
                        "groq_duration_ms": duration_ms,
                    },
                )
                return LLMJSONResponse(parsed, model, attempt + 1, duration_ms)
            except (json.JSONDecodeError, TypeError):
                # Secondary: attempt JSON repair
                repaired = _try_repair_json(raw if isinstance(raw, str) else "")
                if isinstance(repaired, dict):
                    duration_ms = int((time.monotonic() - started_at) * 1000)
                    logger.info(
                        "Groq request completed: provider=%s stage=response_parse category=json_repaired "
                        "status=200 response_format=json_object attempt=%d duration_ms=%d",
                        model,
                        attempt + 1,
                        duration_ms,
                        extra={
                            "groq_stage": "response_parse",
                            "groq_category": "json_repaired",
                            "groq_attempt": attempt + 1,
                            "groq_model": model,
                            "groq_status_code": 200,
                            "groq_response_format": "json_object",
                            "groq_duration_ms": duration_ms,
                        },
                    )
                    return LLMJSONResponse(repaired, model, attempt + 1, duration_ms)
                last_error = f"JSON decode failed on attempt {attempt + 1}"
                last_category = "malformed_json"
                last_status_code = None
                last_retry_after = None
                logger.warning(
                    "Groq response could not be parsed as JSON: provider=%s stage=response_parse category=%s status=none response_format=json_object attempt=%d",
                    model,
                    last_category,
                    attempt + 1,
                    extra={
                        "groq_stage": "response_parse",
                        "groq_category": last_category,
                        "groq_attempt": attempt + 1,
                        "groq_model": model,
                        "groq_status_code": None,
                        "groq_response_format": "json_object",
                    },
                )

        except Exception as e:
            last_error = str(e)
            last_category = _safe_error_category(e)
            status_code = getattr(e, "status_code", None)
            last_status_code = status_code if isinstance(status_code, int) else None
            last_retry_after = _retry_after_seconds(e)
            if last_category == "rate_limit_exceeded":
                fallback_wait = min(
                    0.5 * (2**attempt) + random.uniform(0, 0.25),
                    2.0,
                )
                last_retry_after = _register_rate_limit(
                    last_retry_after,
                    fallback_wait,
                )
            logger.warning(
                "Groq request failed: provider=%s stage=%s category=%s status=%s response_format=json_object attempt=%d",
                model or "unavailable",
                stage,
                last_category,
                last_status_code if last_status_code is not None else "none",
                attempt + 1,
                extra={
                    "groq_stage": stage,
                    "groq_category": last_category,
                    "groq_attempt": attempt + 1,
                    "groq_model": model,
                    "groq_status_code": last_status_code,
                    "groq_response_format": "json_object",
                },
            )
        finally:
            _provider_slots.release()
            if last_category in {"authentication", "model_unavailable"}:
                global _cached_model
                _cached_model = None

        retryable_categories = {
            "rate_limit_exceeded",
            "timeout",
            "network",
            "provider_server_error",
            "malformed_json",
        }
        if last_category not in retryable_categories or attempt + 1 >= max_attempts:
            break
        if last_category == "rate_limit_exceeded" and last_retry_after is not None:
            wait_seconds = last_retry_after
        elif last_category == "rate_limit_exceeded":
            wait_seconds = _RATE_LIMIT_FALLBACK_COOLDOWN_SECONDS
        else:
            wait_seconds = min(0.5 * (2**attempt) + random.uniform(0, 0.25), 2.0)
        if wait_seconds > _MAX_AUTOMATIC_RETRY_WAIT_SECONDS:
            break
        time.sleep(wait_seconds)

    return {
        "error": last_error,
        "error_category": last_category,
        "status_code": last_status_code,
        "retry_after_seconds": last_retry_after,
        "attempts": attempts_made,
        "model": last_model,
        "response_format": "json_object",
        "duration_ms": int((time.monotonic() - started_at) * 1000),
    }