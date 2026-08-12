"""Runtime settings, assembled from CLI flags and the environment."""

import os
import sys
from dataclasses import dataclass
from typing import Optional

DEFAULT_MODEL = "nvidia/nemotron-3.5-lightning:free"


def default_model():
    """The model to use when --model is not given."""
    return os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)


@dataclass
class Config:
    """Everything the REPL can change mid-session, plus the sampling knobs."""

    model: str = DEFAULT_MODEL
    system: Optional[str] = None
    reasoning: bool = True
    show_reasoning: bool = False
    stream: bool = False
    markdown: bool = True
    usage: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

    @classmethod
    def from_args(cls, args):
        return cls(
            model=args.model,
            system=args.system,
            reasoning=not args.no_reasoning,
            show_reasoning=args.think,
            stream=args.stream,
            # Rendering markdown into a pipe would mangle it, so only do it for
            # a real terminal unless the user forces the issue.
            markdown=not args.plain and sys.stdout.isatty(),
            usage=args.usage,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
