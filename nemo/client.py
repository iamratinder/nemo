"""HTTP access to the OpenRouter chat-completions endpoint.

This layer never prints. Streaming yields events and the caller decides how to
display them, which is what keeps the renderer swappable and this file testable.
"""

import json
from typing import NamedTuple, Optional

import requests

from .errors import NemoError
from .messages import merge_reasoning_details, ordered_details

API_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT = 120
DATA_PREFIX = "data: "
DONE = "[DONE]"


class StreamEvent(NamedTuple):
    """One thing that happened while a reply was streaming.

    kind is "reasoning" or "content" (with `text`), or "done" (with the
    assembled `message` and `usage`).
    """

    kind: str
    text: str = ""
    message: Optional[dict] = None
    usage: Optional[dict] = None


def error_message(payload):
    """Pull a human-readable message out of an OpenRouter error body."""
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):
        return err.get("message") or json.dumps(err)
    if isinstance(err, str):
        return err
    return None


class OpenRouterClient:
    """A thin client over one endpoint, reusing a connection across turns."""

    def __init__(self, api_key, url=API_URL, timeout=TIMEOUT, session=None):
        self.api_key = api_key
        self.url = url
        self.timeout = timeout
        self.session = session or requests.Session()

    # -- request building ---------------------------------------------------

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _payload(messages, cfg, stream):
        body = {
            "model": cfg.model,
            "messages": messages,
            "reasoning": {"enabled": cfg.reasoning},
            "stream": stream,
        }
        if cfg.temperature is not None:
            body["temperature"] = cfg.temperature
        if cfg.max_tokens is not None:
            body["max_tokens"] = cfg.max_tokens
        return body

    def _post(self, messages, cfg, stream):
        try:
            return self.session.post(
                url=self.url,
                headers=self._headers(),
                data=json.dumps(self._payload(messages, cfg, stream)),
                stream=stream,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise NemoError(f"request failed: {exc}") from exc

    # -- requests -----------------------------------------------------------

    def complete(self, messages, cfg):
        """Ask for a whole reply at once. Returns (message, usage)."""
        response = self._post(messages, cfg, stream=False)

        try:
            payload = response.json()
        except ValueError:
            raise NemoError(
                f"HTTP {response.status_code}: "
                f"{response.text[:400] or 'empty response'}"
            ) from None

        message = error_message(payload)
        if message:
            raise NemoError(f"HTTP {response.status_code}: {message}")
        if response.status_code >= 400:
            raise NemoError(
                f"HTTP {response.status_code}: {json.dumps(payload)[:400]}")

        choices = payload.get("choices") or []
        if not choices:
            raise NemoError(f"no choices in response: {json.dumps(payload)[:400]}")

        return choices[0].get("message") or {}, payload.get("usage")

    def stream(self, messages, cfg):
        """Yield StreamEvents as the reply arrives, ending with a "done" event."""
        response = self._post(messages, cfg, stream=True)

        if response.status_code >= 400:
            raise NemoError(f"HTTP {response.status_code}: {self._body_error(response)}")

        # The server sends text/event-stream with no charset, and requests falls
        # back to ISO-8859-1 for text/*. SSE is always UTF-8; without this, every
        # em dash and smart quote arrives as mojibake.
        response.encoding = "utf-8"

        content_parts = []
        reasoning_parts = []
        details = {}
        usage = None

        try:
            for line in response.iter_lines(decode_unicode=True):
                if not line or line.startswith(":"):
                    continue  # blank line or keep-alive comment
                if not line.startswith(DATA_PREFIX):
                    continue
                data = line[len(DATA_PREFIX):]
                if data == DONE:
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue  # a fragment we can't use; the stream goes on

                message = error_message(chunk)
                if message:
                    raise NemoError(message)

                usage = chunk.get("usage") or usage
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}

                reasoning = delta.get("reasoning")
                if reasoning:
                    reasoning_parts.append(reasoning)
                    yield StreamEvent("reasoning", reasoning)

                merge_reasoning_details(details, delta.get("reasoning_details"))

                piece = delta.get("content")
                if piece:
                    content_parts.append(piece)
                    yield StreamEvent("content", piece)
        finally:
            response.close()

        message = {"role": "assistant", "content": "".join(content_parts)}
        if reasoning_parts:
            message["reasoning"] = "".join(reasoning_parts)
        if details:
            message["reasoning_details"] = ordered_details(details)
        yield StreamEvent("done", message=message, usage=usage)

    @staticmethod
    def _body_error(response):
        body = response.text[:400]
        try:
            return error_message(json.loads(body)) or body
        except ValueError:
            return body or "empty response"

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
