"""Thin Ollama wrapper for all LLM operations in the pipeline."""

import json
import sys

import ollama

from config import SUMMARIZE_MODEL


def _chat(prompt: str, model: str, json_mode: bool = False) -> str:
    kwargs: dict = {}
    if json_mode:
        kwargs["format"] = "json"

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    return response["message"]["content"].strip()


def summarize_title(text: str, model: str = SUMMARIZE_MODEL) -> str:
    """Derive a concise article title from body text."""
    prompt = (
        "Write a concise, specific headline (under 12 words) for the following article. "
        "Return only the headline, no punctuation at the end, no quotes.\n\n"
        f"Article:\n{text[:2000]}"
    )
    return _chat(prompt, model).strip('"').strip()


def summarize(title: str, text: str, model: str = SUMMARIZE_MODEL) -> str:
    """Summarize an article in under 5 sentences."""
    prompt = (
        f"Summarize the following article in under 5 sentences. "
        f"Be specific and factual. Do not start with 'The article' or 'This article'. "
        f"Return only the summary text, no preamble.\n\n"
        f"Title: {title}\n\n"
        f"Content:\n{text[:3000]}"
    )
    return _chat(prompt, model)


def tag(title: str, summary: str, model: str = SUMMARIZE_MODEL) -> list[str]:
    """Assign 1-3 tags from the predefined set.

    Valid tag keys: policy, model, agents, safety, robotics, voice, health, research, ethics
    """
    prompt = (
        "Assign 1 to 3 tags to this AI/tech article from the following list ONLY. "
        "Return a JSON object with a single key 'tags' containing a list of tag strings.\n\n"
        "Tag definitions — only use a tag if the article is clearly about that topic:\n"
        "  policy   — government regulation, legislation, corporate AI policy, legal cases\n"
        "  model    — LLMs, model releases, benchmarks, training, quantization, inference, local models\n"
        "  agents   — AI agents, autonomous systems, multi-agent frameworks, agentic workflows\n"
        "  safety   — AI safety, alignment, security vulnerabilities, privacy, guardrails\n"
        "  robotics — physical robots, embodied AI, robotic hardware, autonomous vehicles\n"
        "  voice    — speech recognition, voice assistants, text-to-speech, audio AI\n"
        "  health   — healthcare, medical AI, biotech, drug discovery\n"
        "  research — academic papers, datasets, novel ML techniques, experiments\n"
        "  ethics   — bias, fairness, misinformation, AI misuse, societal impact\n\n"
        f"Title: {title}\n"
        f"Summary: {summary}\n\n"
        'Example response: {"tags": ["model", "research"]}'
    )
    raw = _chat(prompt, model, json_mode=True)
    try:
        data = json.loads(raw)
        tags = data.get("tags", [])
        valid = {"policy", "model", "agents", "safety", "robotics", "voice", "health", "research", "ethics"}
        return [t for t in tags if t in valid][:3]
    except (json.JSONDecodeError, AttributeError):
        print(f"[warn] tag() failed to parse JSON: {raw!r}", file=sys.stderr)
        return ["research"]


def classify_ai(title: str, summary: str, model: str = SUMMARIZE_MODEL) -> bool:
    """Return True if the content is AI/ML/robotics related."""
    prompt = (
        "Is the following content related to artificial intelligence, machine learning, "
        "robotics, LLMs, or adjacent technology topics? "
        'Answer with a JSON object: {"relevant": true} or {"relevant": false}.\n\n'
        f"Title: {title}\n"
        f"Content: {summary[:500]}"
    )
    raw = _chat(prompt, model, json_mode=True)
    try:
        return bool(json.loads(raw).get("relevant", False))
    except (json.JSONDecodeError, AttributeError):
        # Default to keeping the item if classification fails
        return True


def deduplicate(items: list[dict], model: str = SUMMARIZE_MODEL) -> list[dict]:
    """Remove near-duplicate items, keeping the one with the longer summary."""
    if len(items) <= 1:
        return items

    # Build a compact index for the LLM
    index_lines = "\n".join(
        f"{i}: {item['title']}" for i, item in enumerate(items)
    )
    prompt = (
        "The following is a numbered list of article titles. "
        "Identify groups of items that cover the same story or announcement. "
        "Return a JSON object with key 'duplicates' — a list of lists, where each inner list "
        "contains the indices of items that are duplicates of each other.\n\n"
        "Only include groups with 2 or more items. If there are no duplicates, return "
        '{"duplicates": []}.\n\n'
        f"Articles:\n{index_lines}"
    )
    raw = _chat(prompt, model, json_mode=True)

    try:
        groups: list[list[int]] = json.loads(raw).get("duplicates", [])
    except (json.JSONDecodeError, AttributeError):
        print(f"[warn] deduplicate() failed to parse JSON: {raw!r}", file=sys.stderr)
        return items

    # For each duplicate group, keep the item with the longest summary
    to_drop: set[int] = set()
    for group in groups:
        if not isinstance(group, list) or len(group) < 2:
            continue
        # Clamp indices to valid range
        group = [i for i in group if 0 <= i < len(items)]
        if len(group) < 2:
            continue
        best = max(group, key=lambda i: len(items[i].get("summary", "")))
        for i in group:
            if i != best:
                to_drop.add(i)

    return [item for i, item in enumerate(items) if i not in to_drop]
