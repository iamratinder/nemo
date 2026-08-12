# nemo

A small terminal chat client for [OpenRouter](https://openrouter.ai), built around
`nvidia/nemotron-3.5-lightning:free`. Multi-turn conversations keep the model's
`reasoning_details` intact, so follow-ups like "are you sure?" reuse the earlier
chain of thought instead of starting cold.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
echo 'OPENROUTER_API_KEY=sk-or-...' > .env
```

## Use

```sh
# one-shot
.venv/bin/python nemo.py "How many r's are in 'strawberry'?"

# show the reasoning too, streamed
.venv/bin/python nemo.py --think --stream "How many r's are in 'strawberry'?"

# piped input
git diff | .venv/bin/python nemo.py "Write a commit message for this diff"

# raw message JSON, for scripting
.venv/bin/python nemo.py --json "hi" | jq -r .content

# interactive chat
.venv/bin/python nemo.py
```

### Flags

| flag | meaning |
| --- | --- |
| `-m, --model` | model slug (default `nvidia/nemotron-3.5-lightning:free`, or `$OPENROUTER_MODEL`) |
| `-s, --system` | system prompt |
| `-t, --think` | print the model's reasoning alongside the answer |
| `--no-reasoning` | ask the model not to reason |
| `--stream` | stream the reply as it is generated |
| `--temperature`, `--max-tokens` | sampling controls |
| `--usage` | print token counts after each reply |
| `--plain` | print raw markdown instead of rendering it |
| `--json` | print the raw assistant message (one-shot only) |

`--max-tokens` counts reasoning tokens too: set it too low and the reply comes
back as truncated thinking with no answer. Budget a few hundred tokens, or pass
`--no-reasoning`.

### Markdown

Replies are rendered with [rich](https://github.com/Textualize/rich) — bold and
headers styled, bullets as real bullets, fenced code blocks syntax-highlighted,
long lines wrapped to the terminal. Streaming re-renders in place as text
arrives.

Rendering only happens when stdout is a terminal, so pipes and redirects still
get the model's raw markdown and stay safe to parse. `--plain` forces raw output
in a terminal too, and `/markdown off` toggles it mid-chat. Set
`NEMO_CODE_THEME` to any Pygments theme (default `monokai`) if the code-block
colors clash with your terminal.

### Interactive commands

Type `/` and the full command list drops down with descriptions, filtering as
you keep typing. Tab or the arrow keys pick one; unambiguous prefixes work on
their own, so `/mar` runs `/markdown` and `/m` reports that it's ambiguous
between `/model` and `/markdown`.

| command | |
| --- | --- |
| `/help` | the command list (so does a bare `/`) |
| `/config` | show every current setting, plus the conversation size |
| `/reset` | clear the conversation, keep the system prompt |
| `/model [name]` | show or switch the model |
| `/system [text]` | show, set, or clear the system prompt |
| `/reasoning [on\|off]` | toggle reasoning |
| `/think [on\|off]` | toggle showing the model's reasoning |
| `/stream [on\|off]` | toggle streaming |
| `/markdown [on\|off]` | toggle markdown rendering |
| `/history` | dump the raw message list as JSON |
| `/save <file>` | write the conversation to a JSON file |
| `/exit` | quit (`/quit`, `/q` too) |

Ctrl-C clears the current line; Ctrl-D quits. Up and down arrows walk back
through what you've typed this session.
