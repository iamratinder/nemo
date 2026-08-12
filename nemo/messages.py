"""Assembling the message list, including the reasoning carried between turns.

Pure data handling - nothing here talks to the network or the terminal.
"""

# Fields that stream in fragments and must be concatenated rather than replaced.
TEXT_FIELDS = ("text", "summary", "data")


def initial(system):
    """The starting message list for a conversation."""
    return [{"role": "system", "content": system}] if system else []


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
            if key in TEXT_FIELDS and isinstance(value, str) \
                    and isinstance(current.get(key), str):
                current[key] += value
            elif value is not None:
                current[key] = value


def ordered_details(acc):
    """The merged reasoning_details, back in the order the model sent them."""
    return [acc[key] for key in sorted(acc)]


def reasoning_text(message):
    """Best-effort reasoning text when the model only fills reasoning_details."""
    parts = []
    for detail in message.get("reasoning_details") or []:
        if isinstance(detail, dict):
            text = detail.get("text") or detail.get("summary")
            if text:
                parts.append(text)
    return "\n".join(parts)


def to_history(message):
    """Trim an API message down to what we send back on the next turn.

    Keeping reasoning_details is the point: it lets a follow-up build on the
    model's earlier chain of thought instead of starting cold.
    """
    entry = {"role": "assistant", "content": message.get("content")}
    details = message.get("reasoning_details")
    if details:
        entry["reasoning_details"] = details
    return entry


def format_usage(usage):
    """One line of token counts, or None if the API reported none."""
    if not usage:
        return None
    prompt = usage.get("prompt_tokens", "?")
    completion = usage.get("completion_tokens", "?")
    total = usage.get("total_tokens", "?")
    return f"tokens: {prompt} in / {completion} out / {total} total"
