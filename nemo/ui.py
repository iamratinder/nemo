"""Everything that writes to the terminal: colors, markdown, streaming display."""

import os
import sys

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

console = Console()
CODE_THEME = os.getenv("NEMO_CODE_THEME", "monokai")


def _color_enabled():
    return sys.stdout.isatty() and not os.getenv("NO_COLOR")


class Palette:
    """ANSI codes, blanked out when the output is not a terminal."""

    def __init__(self, on):
        self.dim = "\033[2m" if on else ""
        self.bold = "\033[1m" if on else ""
        self.cyan = "\033[36m" if on else ""
        self.green = "\033[32m" if on else ""
        self.red = "\033[31m" if on else ""
        self.reset = "\033[0m" if on else ""


c = Palette(_color_enabled())


def info(msg):
    """A note for the user, on stderr so it stays out of piped output."""
    print(f"{c.dim}{msg}{c.reset}", file=sys.stderr)


def die(msg, code=1):
    print(f"{c.red}error:{c.reset} {msg}", file=sys.stderr)
    sys.exit(code)


def render(text, markdown):
    """Print an assistant reply, as rendered markdown or as-is."""
    if not text:
        return
    if markdown:
        console.print(Markdown(text, code_theme=CODE_THEME))
    else:
        print(text)


def reasoning_block(text):
    """Print reasoning the model returned all at once."""
    if text:
        print(f"{c.dim}thinking: {text}{c.reset}\n")


def speaker(model):
    """The label printed above a non-streamed reply."""
    print(f"{c.green}{c.bold}{model.split('/')[-1]}>{c.reset}")


class StreamPrinter:
    """Displays streaming events; markdown re-renders in place as it grows."""

    def __init__(self, markdown, show_reasoning):
        self.markdown = markdown
        self.show_reasoning = show_reasoning
        self._content = []
        self._live = None
        self._in_reasoning = False

    def handle(self, event):
        if event.kind == "reasoning":
            self._reasoning(event.text)
        elif event.kind == "content":
            self._piece(event.text)

    def _reasoning(self, text):
        if not self.show_reasoning:
            return
        if not self._in_reasoning:
            print(f"{c.dim}thinking: ", end="", flush=True)
            self._in_reasoning = True
        print(f"{c.dim}{text}{c.reset}", end="", flush=True)

    def _piece(self, text):
        if self._in_reasoning:
            print(f"{c.reset}\n")
            self._in_reasoning = False
        self._content.append(text)
        if not self.markdown:
            print(text, end="", flush=True)
            return
        if self._live is None:
            # vertical_overflow="visible" so replies taller than the window
            # scroll normally instead of being cropped to the viewport.
            self._live = Live(console=console, refresh_per_second=12,
                              vertical_overflow="visible")
            self._live.start()
        self._live.update(Markdown("".join(self._content), code_theme=CODE_THEME))

    def close(self):
        """Tear down the live region. Safe to call more than once."""
        if self._live is not None:
            self._live.stop()
            self._live = None
        elif self._in_reasoning:
            print(c.reset)
            self._in_reasoning = False
        print()
