"""Argument parsing and the two entry paths: one-shot and interactive."""

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from . import __version__
from .chat import ask
from .client import OpenRouterClient
from .config import DEFAULT_MODEL, Config, default_model
from .errors import NemoError
from .messages import format_usage, initial
from .repl import Repl
from .ui import die, info


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="nemo",
        description="Chat with an OpenRouter model from the terminal.",
        epilog="With no PROMPT (and a terminal on stdin) it starts an interactive chat.",
    )
    parser.add_argument("prompt", nargs="*",
                        help="one-shot prompt; omit for interactive chat")
    parser.add_argument("-m", "--model", default=default_model(),
                        help=f"model slug (default: {DEFAULT_MODEL})")
    parser.add_argument("-s", "--system", help="system prompt")
    parser.add_argument("-t", "--think", action="store_true",
                        help="print the model's reasoning as well as the answer")
    parser.add_argument("--no-reasoning", action="store_true",
                        help="ask the model not to produce reasoning")
    parser.add_argument("--stream", action="store_true",
                        help="stream the reply token by token")
    parser.add_argument("--temperature", type=float, help="sampling temperature")
    parser.add_argument("--max-tokens", type=int, help="cap the reply length")
    parser.add_argument("--usage", action="store_true",
                        help="print token usage after each reply")
    parser.add_argument("--plain", action="store_true",
                        help="print raw markdown instead of rendering it")
    parser.add_argument("--json", action="store_true",
                        help="print the raw assistant message as JSON (one-shot only)")
    parser.add_argument("--version", action="version", version=f"nemo {__version__}")
    return parser.parse_args(argv)


def read_prompt(args):
    """The one-shot prompt, from the command line or from a pipe."""
    prompt = " ".join(args.prompt).strip()
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    return prompt


def one_shot(client, cfg, args, prompt):
    messages = initial(cfg.system) + [{"role": "user", "content": prompt}]
    try:
        message, usage = ask(
            client, messages, cfg,
            stream=cfg.stream and not args.json,
            show_reasoning=cfg.show_reasoning and not args.json,
            printed=not args.json,
            markdown=cfg.markdown and not args.json,
        )
    except NemoError as exc:
        die(str(exc))
    except KeyboardInterrupt:
        print()
        return 130

    if args.json:
        print(json.dumps(message, indent=2))
    if cfg.usage:
        line = format_usage(usage)
        if line:
            info(line)
    return 0


def main(argv=None):
    load_dotenv()
    args = parse_args(argv)

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        die("OPENROUTER_API_KEY is not set (put it in .env or export it)")

    cfg = Config.from_args(args)
    prompt = read_prompt(args)

    if not prompt and args.json:
        die("--json needs a prompt; it does not apply to interactive chat")

    with OpenRouterClient(api_key) as client:
        if prompt:
            return one_shot(client, cfg, args, prompt)
        return Repl(cfg, client).run()


if __name__ == "__main__":
    sys.exit(main())
