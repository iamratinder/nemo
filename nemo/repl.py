"""The interactive chat session."""

import json
import os

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI

from . import commands, messages as msg, ui
from .chat import ask
from .errors import NemoError
from .ui import c, info


def make_reader():
    """A prompt that pops up the command menu on '/', with plain-input fallback."""
    prompt = f"{c.cyan}{c.bold}you>{c.reset} "
    try:
        session = PromptSession(
            completer=commands.SlashCompleter(),
            complete_while_typing=True,
            reserve_space_for_menu=len(commands.COMMANDS) + 1,
        )
    except Exception:
        return lambda: input(prompt)  # not a full terminal; degrade quietly
    return lambda: session.prompt(ANSI(prompt))


class Repl:
    """Holds the conversation and the settings the slash commands mutate."""

    def __init__(self, cfg, client, read=None):
        self.cfg = cfg
        self.client = client
        self.messages = msg.initial(cfg.system)
        self.read = read or make_reader()

    def run(self):
        info(f"{self.cfg.model} - type / for commands, Ctrl-D to quit")
        while True:
            try:
                line = self.read().strip()
            except EOFError:
                print()
                return 0
            except KeyboardInterrupt:
                continue  # Ctrl-C clears the line; Ctrl-D or /exit quits

            if not line:
                continue
            if line.startswith("/"):
                if not self.command(line):
                    return 0
                continue
            self.turn(line)

    # -- commands -----------------------------------------------------------

    def command(self, line):
        """Run a slash command. Returns False when the session should end."""
        if line == "/":
            info(commands.help_text())
            return True

        word, _, arg = line.partition(" ")
        arg = arg.strip()
        command = commands.resolve(word)
        if command is None:
            return True
        if command == "/exit":
            return False

        cfg = self.cfg
        if command == "/help":
            info(commands.help_text())
        elif command == "/config":
            info(commands.config_text(cfg, self.messages))
        elif command == "/reset":
            self.messages = [m for m in self.messages if m.get("role") == "system"]
            info("conversation cleared")
        elif command == "/model":
            if arg:
                cfg.model = arg
            info(f"model: {cfg.model}")
        elif command == "/system":
            self.set_system(arg)
        elif command == "/reasoning":
            cfg.reasoning = commands.toggle(arg, cfg.reasoning, "reasoning")
        elif command == "/think":
            cfg.show_reasoning = commands.toggle(arg, cfg.show_reasoning, "think")
        elif command == "/stream":
            cfg.stream = commands.toggle(arg, cfg.stream, "stream")
        elif command == "/markdown":
            cfg.markdown = commands.toggle(arg, cfg.markdown, "markdown")
        elif command == "/history":
            print(json.dumps(self.messages, indent=2))
        elif command == "/save":
            self.save(arg)
        else:
            info(f"unknown command: {command} (try /help)")
        return True

    def set_system(self, text):
        self.messages = [m for m in self.messages if m.get("role") != "system"]
        if text:
            self.cfg.system = text
            self.messages.insert(0, {"role": "system", "content": text})
            info(f"system: {text}")
        else:
            self.cfg.system = None
            info("system prompt cleared")

    def save(self, path):
        if not path:
            info("usage: /save <file>")
            return
        try:
            with open(os.path.expanduser(path), "w") as handle:
                json.dump(self.messages, handle, indent=2)
            info(f"saved {len(self.messages)} messages to {path}")
        except OSError as exc:
            info(f"could not save: {exc}")

    # -- a chat turn --------------------------------------------------------

    def turn(self, line):
        cfg = self.cfg
        self.messages.append({"role": "user", "content": line})

        if not cfg.stream:
            ui.speaker(cfg.model)
        try:
            message, usage = ask(
                self.client, self.messages, cfg,
                stream=cfg.stream,
                show_reasoning=cfg.show_reasoning,
                printed=True,
                markdown=cfg.markdown,
            )
        except NemoError as exc:
            self.messages.pop()  # drop the turn that failed
            info(str(exc))
            return
        except KeyboardInterrupt:
            self.messages.pop()
            print()
            info("interrupted")
            return

        self.messages.append(msg.to_history(message))
        if cfg.usage:
            line = msg.format_usage(usage)
            if line:
                info(line)
        print()
