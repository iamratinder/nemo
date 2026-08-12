"""Glue between the API client and the terminal: send a turn, show the reply."""

from . import ui
from .messages import reasoning_text


def ask(client, messages, cfg, stream, show_reasoning, printed, markdown=False):
    """Send `messages` and display the reply. Returns (message, usage).

    `printed` covers the non-streaming path only; a streamed reply is written
    as it arrives, which is the whole point of streaming it.
    """
    if stream:
        return _streamed(client, messages, cfg, show_reasoning, markdown)

    message, usage = client.complete(messages, cfg)

    if show_reasoning:
        ui.reasoning_block(message.get("reasoning") or reasoning_text(message))
    if printed:
        ui.render(message.get("content"), markdown)
    return message, usage


def _streamed(client, messages, cfg, show_reasoning, markdown):
    printer = ui.StreamPrinter(markdown, show_reasoning)
    message, usage = {}, None
    try:
        for event in client.stream(messages, cfg):
            if event.kind == "done":
                message, usage = event.message or {}, event.usage
            else:
                printer.handle(event)
    finally:
        printer.close()
    return message, usage
