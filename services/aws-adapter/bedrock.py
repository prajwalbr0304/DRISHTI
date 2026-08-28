"""Narrow Chinese-model-only Amazon Bedrock operation for the AWS adapter.

The caller is authenticated by handler.py before this module runs. This module
then enforces exact model identity, text-only Converse input, bounded prompt
size, and deterministic inference. It never logs prompt or response content.
"""
from __future__ import annotations

import os
from typing import Any

APPROVED_BEDROCK_MODELS = frozenset({"zai.glm-4.7-flash"})
DEFAULT_BEDROCK_MODEL_ID = "zai.glm-4.7-flash"
_MAX_MESSAGES = 15
_MAX_TOTAL_TEXT_CHARS = 160_000


class BedrockRequestError(ValueError):
    """The signed request violates the narrow Bedrock contract."""


class BedrockUnavailable(RuntimeError):
    """Bedrock failed with a safe, non-secret operational code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _configured_model_id() -> str:
    model_id = os.getenv("DRISHTI_BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID).strip().lower()
    if model_id not in APPROVED_BEDROCK_MODELS:
        raise BedrockUnavailable("model_not_approved")
    return model_id


def _text_blocks(value: Any, *, field: str) -> tuple[list[dict], int]:
    if not isinstance(value, list) or not value:
        raise BedrockRequestError(f"{field} must contain text blocks")
    normalized: list[dict] = []
    chars = 0
    for block in value:
        if not isinstance(block, dict) or set(block) != {"text"}:
            raise BedrockRequestError(f"{field} supports text blocks only")
        text = block.get("text")
        if not isinstance(text, str) or not text.strip():
            raise BedrockRequestError(f"{field} contains empty text")
        chars += len(text)
        normalized.append({"text": text})
    return normalized, chars


def _validated_request(body: dict) -> tuple[str, str, list[dict], list[dict]]:
    if not isinstance(body, dict):
        raise BedrockRequestError("request must be a JSON object")
    request_id = str(body.get("request_id") or "").strip().lower()
    if len(request_id) != 32 or any(c not in "0123456789abcdef" for c in request_id):
        raise BedrockRequestError("request_id must be 32 lowercase hex characters")
    model_id = str(body.get("model_id") or "").strip().lower()
    configured = _configured_model_id()
    if model_id != configured or model_id not in APPROVED_BEDROCK_MODELS:
        raise BedrockRequestError("model is not approved")

    system, total_chars = _text_blocks(body.get("system"), field="system")
    raw_messages = body.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise BedrockRequestError("messages are required")
    if len(raw_messages) > _MAX_MESSAGES:
        raise BedrockRequestError("too many messages")

    messages: list[dict] = []
    for message in raw_messages:
        if not isinstance(message, dict):
            raise BedrockRequestError("message must be an object")
        role = message.get("role")
        if role not in ("user", "assistant"):
            raise BedrockRequestError("unsupported message role")
        content, chars = _text_blocks(message.get("content"), field="message content")
        total_chars += chars
        messages.append({"role": role, "content": content})
    if total_chars > _MAX_TOTAL_TEXT_CHARS:
        raise BedrockRequestError("prompt exceeds the character cap")
    return request_id, model_id, system, messages


def converse(body: dict) -> dict:
    """Call Bedrock Converse using only the Lambda execution role.

    The inference configuration from the caller is intentionally not forwarded:
    the adapter pins temperature=0 and does not impose an incompatible app-level
    max-token cap on GLM 4.7 Flash.
    """
    request_id, model_id, system, messages = _validated_request(body)
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import (BotoCoreError, ClientError,
                                         EndpointConnectionError, NoCredentialsError)

        client = boto3.client(
            "bedrock-runtime",
            region_name=os.getenv("AWS_REGION", "ap-south-1"),
            config=Config(read_timeout=45, connect_timeout=10, retries={"max_attempts": 2}),
        )
        response = client.converse(
            modelId=model_id,
            system=system,
            messages=messages,
            inferenceConfig={"temperature": 0},
        )
    except ClientError as exc:
        aws_code = str(exc.response.get("Error", {}).get("Code") or "")
        safe_codes = {
            "AccessDeniedException": "access_denied",
            "ResourceNotFoundException": "model_not_found",
            "ValidationException": "validation_error",
            "ThrottlingException": "throttled",
            "ServiceUnavailableException": "service_unavailable",
            "ModelTimeoutException": "model_timeout",
            "ModelErrorException": "model_error",
        }
        raise BedrockUnavailable(safe_codes.get(aws_code, "aws_client_error")) from None
    except NoCredentialsError:
        raise BedrockUnavailable("credentials_unavailable") from None
    except EndpointConnectionError:
        raise BedrockUnavailable("endpoint_unavailable") from None
    except BotoCoreError:
        raise BedrockUnavailable("aws_sdk_error") from None

    content = "".join(
        block.get("text", "")
        for block in response.get("output", {}).get("message", {}).get("content", [])
        if isinstance(block, dict)
    ).strip()
    if not content:
        raise BedrockUnavailable("empty_model_response")
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    return {
        "request_id": request_id,
        "model_id": model_id,
        "content": content,
        "stop_reason": response.get("stopReason"),
        "usage": {
            "input_tokens": int(usage.get("inputTokens") or 0),
            "output_tokens": int(usage.get("outputTokens") or 0),
        },
    }
