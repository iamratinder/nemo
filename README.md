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
| `--json` | print the raw assistant message (one-shot only) |

`--max-tokens` counts reasoning tokens too: set it too low and the reply comes
back as truncated thinking with no answer. Budget a few hundred tokens, or pass
`--no-reasoning`.

### Interactive commands

`/help` `/reset` `/model [name]` `/system [text]` `/reasoning [on|off]`
`/think [on|off]` `/stream [on|off]` `/history` `/save <file>` `/exit`
