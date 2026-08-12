"""The slash commands: the table, its help, and the type-ahead menu."""

from prompt_toolkit.completion import Completer, Completion

from .ui import info

# (command, argument spec, description) - drives both /help and the type-ahead
# menu, so the two can't drift apart.
COMMANDS = [
    ("/help", "", "show this help"),
    ("/config", "", "show the current settings"),
    ("/reset", "", "clear the conversation (keeps the system prompt)"),
    ("/model", "[name]", "show or switch the model"),
    ("/system", "[text]", "show, set, or clear (no text) the system prompt"),
    ("/reasoning", "[on|off]", "toggle reasoning"),
    ("/think", "[on|off]", "toggle showing the model's reasoning"),
    ("/stream", "[on|off]", "toggle streaming"),
    ("/markdown", "[on|off]", "toggle markdown rendering"),
    ("/history", "", "dump the raw message list as JSON"),
    ("/save", "<file>", "write the conversation to a JSON file"),
    ("/exit", "", "quit (Ctrl-D works too)"),
]

ALIASES = {"/quit": "/exit", "/q": "/exit"}

NAMES = [name for name, _, _ in COMMANDS]

TRUTHY = ("on", "true", "1", "yes")
FALSY = ("off", "false", "0", "no")

SYSTEM_PREVIEW = 60


def help_text():
    width = max(len(name) + len(spec) + 1 for name, spec, _ in COMMANDS)
    lines = ["commands:"]
    for name, spec, description in COMMANDS:
        usage = f"{name} {spec}".strip()
        lines.append(f"  {usage.ljust(width)}  {description}")
    return "\n".join(lines)


def _onoff(value):
    return "on" if value else "off"


def config_text(cfg, messages=None):
    """Everything the flags and toggles are currently set to."""
    system = cfg.system or "(none)"
    if len(system) > SYSTEM_PREVIEW:
        system = system[:SYSTEM_PREVIEW - 3] + "..."
    rows = [
        ("model", cfg.model),
        ("system", system),
        ("reasoning", _onoff(cfg.reasoning)),
        ("think", _onoff(cfg.show_reasoning)),
        ("stream", _onoff(cfg.stream)),
        ("markdown", _onoff(cfg.markdown)),
        ("usage", _onoff(cfg.usage)),
        ("temperature",
         "model default" if cfg.temperature is None else str(cfg.temperature)),
        ("max-tokens",
         "unlimited" if cfg.max_tokens is None else str(cfg.max_tokens)),
    ]
    if messages is not None:
        turns = sum(1 for m in messages if m.get("role") == "user")
        rows.append(("conversation", f"{len(messages)} messages, {turns} turns"))
    width = max(len(label) for label, _ in rows)
    return "\n".join(["config:"] + [f"  {l.ljust(width)}  {v}" for l, v in rows])


def resolve(word):
    """Map a typed command to a real one, accepting unambiguous prefixes.

    Returns None when the prefix is ambiguous (already reported to the user).
    """
    if word in ALIASES:
        return ALIASES[word]
    if word in NAMES:
        return word
    matches = [name for name in NAMES if name.startswith(word)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        info(f"ambiguous: {word} matches {', '.join(matches)}")
        return None
    return word  # unknown; the dispatcher reports it


def toggle(arg, current, label):
    """Read an on/off argument, defaulting to flipping the current value."""
    if arg in TRUTHY:
        value = True
    elif arg in FALSY:
        value = False
    elif not arg:
        value = not current
    else:
        info(f"usage: /{label} [on|off]")
        return current
    info(f"{label}: {_onoff(value)}")
    return value


class SlashCompleter(Completer):
    """Offer the command list as soon as the line starts with a slash."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return  # not a command, or already past the command word
        for name, spec, description in COMMANDS:
            if name.startswith(text):
                yield Completion(
                    name,
                    start_position=-len(text),
                    display=f"{name} {spec}".strip(),
                    display_meta=description,
                )
