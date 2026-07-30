from __future__ import annotations

import json
import logging
from typing import Any

import litellm
from litellm import JSONSchemaValidationError, completion

from config import LLM_MODEL

logger = logging.getLogger(__name__)


def completion_json(
        *,
        messages: list[dict[str, str]],
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_retries: int = 2,
) -> dict[str, Any]:
    last_error: Exception | None = None
    working_messages = list(messages)

    for attempt in range(1, max_retries + 1):
        raw = ""

        try:
            kwargs = {
                "model": LLM_MODEL,
                "messages": working_messages,
                "temperature": temperature,
            }

            if json_schema:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_output",
                        "strict": True,
                        "schema": json_schema,
                    },
                }
            else:
                kwargs["response_format"] = {"type": "json_object"}

            response = completion(**kwargs)
            raw = (response.choices[0].message.content or "").strip()
            if not raw:
                raise ValueError("Model returned empty content")
            return json.loads(raw)

        except JSONSchemaValidationError as exc:
            last_error = exc
            logger.warning(
                "completion_json: schema validation failed for model=%s: %s",
                LLM_MODEL,
                exc,
            )

            raw = getattr(exc, "raw_response", "") or raw

            if raw:
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    pass

        except (litellm.UnsupportedParamsError, litellm.BadRequestError) as exc:
            last_error = exc
            logger.warning(
                "completion_json: structured response request failed for model=%s, falling back to prompt-only JSON: %s",
                LLM_MODEL,
                exc,
            )

            if json_schema is not None:
                try:
                    fallback_response = completion(
                        model=LLM_MODEL,
                        messages=working_messages + [{
                            "role": "user",
                            "content": (
                                "Return ONLY valid JSON matching the requested schema exactly. "
                                "Do not include markdown fences, comments, or explanation."
                            ),
                        }],
                        temperature=temperature,
                    )
                    raw = (fallback_response.choices[0].message.content or "").strip()
                    if not raw:
                        raise ValueError("Model returned empty content")
                    return json.loads(raw)
                except Exception as fallback_exc:
                    last_error = fallback_exc

        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning(
                "completion_json: invalid JSON from model=%s on attempt %d: %s",
                LLM_MODEL,
                attempt,
                exc,
            )

        except Exception as exc:
            last_error = exc
            logger.warning(
                "completion_json: unexpected error from model=%s on attempt %d: %s",
                LLM_MODEL,
                attempt,
                exc,
            )

        if attempt < max_retries:
            working_messages = working_messages + [
                {
                    "role": "assistant",
                    "content": raw or "Previous response could not be parsed.",
                },
                {
                    "role": "user",
                    "content": "Your previous response was invalid. Return valid JSON only.",
                },
            ]

    raise ValueError(
        f"LLM JSON completion failed after {max_retries} attempts: {last_error}"
    )