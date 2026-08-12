#!/usr/bin/env python3
"""nemo - a small CLI for chatting with OpenRouter models, reasoning included.

One-shot:     ./nemo.py "How many r's are in 'strawberry'?"
Interactive:  ./nemo.py
Piped:        echo "explain quicksort" | ./nemo.py
"""

import argparse
import json
import os
import sys

import requests
from dotenv import load_dotenv

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3.5-lightning:free"
TIMEOUT = 120


# --- pretty printing ---------------------------------------------------------

def _color_enabled():
    return sys.stdout.isatty() and not os.getenv("NO_COLOR")


class C:
    """ANSI codes, blanked out when the output is not a terminal."""

    def __init__(self, on):
        self.dim = "\033[2m" if on else ""
        self.bold = "\033[1m" if on else ""
        self.cyan = "\033[36m" if on else ""
        self.green = "\033[32m" if on else ""
        self.red = "\033[31m" if on else ""
        self.reset = "\033[0m" if on else ""


c = C(_color_enabled())


def info(msg):
    print(f"{c.dim}{msg}{c.reset}", file=sys.stderr)


def die(msg, code=1):
    print(f"{c.red}error:{c.reset} {msg}", file=sys.stderr)
    sys.exit(code)


# --- API ---------------------------------------------------------------------

def merge_reasoning_details(acc, deltas):
    """Fold streamed reasoning_details fragments into `acc`, keyed by index."""
    for position, delta in enumerate(deltas or []):
        if not isinstance(delta, dict):
            continue
        index = delta.get("index", position)
        current = acc.get(index)
        if current is None:
            acc[index] = dict(delta)
            continue
        for key, value in delta.items():
            # Text-ish fields arrive in pieces; everything else is a whole value.
            if key in ("text", "summary", "data") and isinstance(value, str) \
                    and isinstance(current.get(key), str):
                current[key] += value
            elif value is not None:
                current[key] = value


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


def _headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _api_error(payload):
    """Pull a human-readable message out of an OpenRouter error body."""
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):
        return err.get("message") or json.dumps(err)
    if isinstance(err, str):
        return err
    return None


def complete(messages, cfg, api_key):
    """Non-streaming request. Returns (assistant_message, usage)."""
    try:
        response = requests.post(
            url=API_URL,
            headers=_headers(api_key),
            data=json.dumps(_payload(messages, cfg, stream=False)),
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"request failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError(
            f"HTTP {response.status_code}: {response.text[:400] or 'empty response'}"
        ) from None

    message = _api_error(payload)
    if message:
        raise RuntimeError(f"HTTP {response.status_code}: {message}")
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {json.dumps(payload)[:400]}")

    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"no choices in response: {json.dumps(payload)[:400]}")

    return choices[0].get("message") or {}, payload.get("usage")


def stream_complete(messages, cfg, api_key, show_reasoning):
    """Streaming request. Prints as it goes; returns (assistant_message, usage)."""
    try:
        response = requests.post(
            url=API_URL,
            headers=_headers(api_key),
            data=json.dumps(_payload(messages, cfg, stream=True)),
            stream=True,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"request failed: {exc}") from exc

    if response.status_code >= 400:
        body = response.text[:400]
        try:
            message = _api_error(json.loads(body)) or body
        except ValueError:
            message = body or "empty response"
        raise RuntimeError(f"HTTP {response.status_code}: {message}")

    content_parts = []
    reasoning_parts = []
    details = {}
    usage = None
    in_reasoning = False

    for line in response.iter_lines(decode_unicode=True):
        if not line or line.startswith(":"):
            continue  # keep-alive comment
        if not line.startswith("data: "):
            continue
        data = line[len("data: "):]
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except ValueError:
            continue

        message = _api_error(chunk)
        if message:
            raise RuntimeError(message)

        usage = chunk.get("usage") or usage
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}

        reasoning = delta.get("reasoning")
        if reasoning:
            reasoning_parts.append(reasoning)
            if show_reasoning:
                if not in_reasoning:
                    print(f"{c.dim}thinking: ", end="", flush=True)
                    in_reasoning = True
                print(f"{c.dim}{reasoning}{c.reset}", end="", flush=True)

        merge_reasoning_details(details, delta.get("reasoning_details"))

        piece = delta.get("content")
        if piece:
            if in_reasoning:
                print(f"{c.reset}\n")
                in_reasoning = False
            content_parts.append(piece)
            print(piece, end="", flush=True)

    if in_reasoning:
        print(c.reset)
    print()

    message = {"role": "assistant", "content": "".join(content_parts)}
    if reasoning_parts:
        message["reasoning"] = "".join(reasoning_parts)
    if details:
        message["reasoning_details"] = [details[k] for k in sorted(details)]
    return message, usage


def ask(messages, cfg, api_key, stream, show_reasoning, printed):
    """Send `messages`, echo the reply, and return the assistant message.

    `printed` says whether the caller wants the answer on stdout; streaming
    prints as it arrives, so this only covers the non-streaming path.
    """
    if stream:
        return stream_complete(messages, cfg, api_key, show_reasoning)

    message, usage = complete(messages, cfg, api_key)

    if show_reasoning:
        reasoning = message.get("reasoning") or _reasoning_text(message)
        if reasoning:
            print(f"{c.dim}thinking: {reasoning}{c.reset}\n")
    if printed:
        print(message.get("content") or "")
    return message, usage


def _reasoning_text(message):
    """Best-effort reasoning text when the model only fills reasoning_details."""
    parts = []
    for detail in message.get("reasoning_details") or []:
        if isinstance(detail, dict):
            text = detail.get("text") or detail.get("summary")
            if text:
                parts.append(text)
    return "\n".join(parts)


def to_history(message):
    """Trim an API message down to what we send back on the next turn."""
    entry = {"role": "assistant", "content": message.get("content")}
    details = message.get("reasoning_details")
    if details:
        entry["reasoning_details"] = details
    return entry


def format_usage(usage):
    if not usage:
        return None
    prompt = usage.get("prompt_tokens", "?")
    completion = usage.get("completion_tokens", "?")
    total = usage.get("total_tokens", "?")
    return f"tokens: {prompt} in / {completion} out / {total} total"


# --- interactive session -----------------------------------------------------

HELP = """commands:
  /help              show this help
  /reset             clear the conversation (keeps the system prompt)
  /model [name]      show or switch the model
  /system [text]     show, set, or clear (/system with no text) the system prompt
  /reasoning [on|off]toggle reasoning
  /think [on|off]    toggle showing the model's reasoning
  /stream [on|off]   toggle streaming
  /history           dump the raw message list as JSON
  /save <file>       write the conversation to a JSON file
  /exit              quit (Ctrl-D works too)"""


def _toggle(arg, current, label):
    if arg in ("on", "true", "1", "yes"):
        value = True
    elif arg in ("off", "false", "0", "no"):
        value = False
    elif not arg:
        value = not current
    else:
        info(f"usage: /{label} [on|off]")
        return current
    info(f"{label}: {'on' if value else 'off'}")
    return value


def repl(cfg, api_key):
    messages = []
    if cfg.system:
        messages.append({"role": "system", "content": cfg.system})

    info(f"{cfg.model} - /help for commands, Ctrl-D to quit")

    while True:
        try:
            line = input(f"{c.cyan}{c.bold}you>{c.reset} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not line:
            continue

        if line.startswith("/"):
            command, _, arg = line.partition(" ")
            arg = arg.strip()

            if command in ("/exit", "/quit", "/q"):
                return 0
            if command == "/help":
                info(HELP)
            elif command == "/reset":
                messages = [m for m in messages if m.get("role") == "system"]
                info("conversation cleared")
            elif command == "/model":
                if arg:
                    cfg.model = arg
                info(f"model: {cfg.model}")
            elif command == "/system":
                messages = [m for m in messages if m.get("role") != "system"]
                if arg:
                    cfg.system = arg
                    messages.insert(0, {"role": "system", "content": arg})
                    info(f"system: {arg}")
                else:
                    cfg.system = None
                    info("system prompt cleared")
            elif command == "/reasoning":
                cfg.reasoning = _toggle(arg, cfg.reasoning, "reasoning")
            elif command == "/think":
                cfg.show_reasoning = _toggle(arg, cfg.show_reasoning, "think")
            elif command == "/stream":
                cfg.stream = _toggle(arg, cfg.stream, "stream")
            elif command == "/history":
                print(json.dumps(messages, indent=2))
            elif command == "/save":
                if not arg:
                    info("usage: /save <file>")
                    continue
                try:
                    with open(os.path.expanduser(arg), "w") as handle:
                        json.dump(messages, handle, indent=2)
                    info(f"saved {len(messages)} messages to {arg}")
                except OSError as exc:
                    info(f"could not save: {exc}")
            else:
                info(f"unknown command: {command} (try /help)")
            continue

        messages.append({"role": "user", "content": line})

        if not cfg.stream:
            print(f"{c.green}{c.bold}{cfg.model.split('/')[-1]}>{c.reset}")
        try:
            message, usage = ask(
                messages, cfg, api_key,
                stream=cfg.stream,
                show_reasoning=cfg.show_reasoning,
                printed=True,
            )
        except RuntimeError as exc:
            messages.pop()  # drop the turn that failed
            info(str(exc))
            continue
        except KeyboardInterrupt:
            messages.pop()
            print()
            info("interrupted")
            continue

        messages.append(to_history(message))
        if cfg.usage:
            usage_line = format_usage(usage)
            if usage_line:
                info(usage_line)
        print()


# --- entry point -------------------------------------------------------------

class Config:
    def __init__(self, args):
        self.model = args.model
        self.system = args.system
        self.reasoning = not args.no_reasoning
        self.show_reasoning = args.think
        self.stream = args.stream
        self.temperature = args.temperature
        self.max_tokens = args.max_tokens
        self.usage = args.usage


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="nemo",
        description="Chat with an OpenRouter model from the terminal.",
        epilog="With no PROMPT (and a terminal on stdin) it starts an interactive chat.",
    )
    parser.add_argument("prompt", nargs="*", help="one-shot prompt; omit for interactive chat")
    parser.add_argument("-m", "--model", default=os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL),
                        help=f"model slug (default: {DEFAULT_MODEL})")
    parser.add_argument("-s", "--system", help="system prompt")
    parser.add_argument("-t", "--think", action="store_true",
                        help="print the model's reasoning as well as the answer")
    parser.add_argument("--no-reasoning", action="store_true",
                        help="ask the model not to produce reasoning")
    parser.add_argument("--stream", action="store_true", help="stream the reply token by token")
    parser.add_argument("--temperature", type=float, help="sampling temperature")
    parser.add_argument("--max-tokens", type=int, help="cap the reply length")
    parser.add_argument("--usage", action="store_true", help="print token usage after each reply")
    parser.add_argument("--json", action="store_true",
                        help="print the raw assistant message as JSON (one-shot only)")
    return parser.parse_args(argv)


def main(argv=None):
    load_dotenv()
    args = parse_args(argv)

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        die("OPENROUTER_API_KEY is not set (put it in .env or export it)")

    cfg = Config(args)

    prompt = " ".join(args.prompt).strip()
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()

    if not prompt:
        if args.json:
            die("--json needs a prompt; it does not apply to interactive chat")
        return repl(cfg, api_key)

    messages = []
    if cfg.system:
        messages.append({"role": "system", "content": cfg.system})
    messages.append({"role": "user", "content": prompt})

    try:
        message, usage = ask(
            messages, cfg, api_key,
            stream=cfg.stream and not args.json,
            show_reasoning=cfg.show_reasoning and not args.json,
            printed=not args.json,
        )
    except RuntimeError as exc:
        die(str(exc))
    except KeyboardInterrupt:
        print()
        return 130

    if args.json:
        print(json.dumps(message, indent=2))
    if cfg.usage:
        usage_line = format_usage(usage)
        if usage_line:
            info(usage_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
