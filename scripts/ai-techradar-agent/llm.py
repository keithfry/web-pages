"""Thin Ollama wrapper for all LLM operations in the pipeline."""

import json
import re
import sys
import threading
import time

import ollama

from config import SUMMARIZE_MODEL

_llm_call_lock = threading.Lock()
_llm_call_count = 0
_llm_total_duration = 0.0


def llm_stats() -> tuple[int, float]:
    """Return (call_count, total_duration_seconds) accumulated so far."""
    with _llm_call_lock:
        return _llm_call_count, _llm_total_duration


def _extract_json(text: str) -> str:
    """Extract the first JSON object from text that may contain prose or markdown code blocks."""
    # Strip markdown code fences: ```json ... ``` or ``` ... ```
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)
    # Fall back to first {...} block in the text
    brace = re.search(r"\{.*?\}", text, re.DOTALL)
    if brace:
        return brace.group(0)
    return text


def _chat(prompt: str, model: str, json_mode: bool = False, think: bool = False) -> str:
    global _llm_call_count, _llm_total_duration

    kwargs: dict = {"think": think}
    if json_mode:
        kwargs["format"] = "json"

    t0 = time.perf_counter()
    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    elapsed = time.perf_counter() - t0

    with _llm_call_lock:
        _llm_call_count += 1
        _llm_total_duration += elapsed
        cnt = _llm_call_count

    print(f"  [llm:{cnt}] {model} {elapsed:.3f}s", flush=True)

    return response["message"]["content"].strip()


def summarize_title(text: str, model: str = SUMMARIZE_MODEL) -> str:
    """Derive a concise article title from body text."""
    prompt = (
        "Write a concise, specific headline (under 12 words) for the following article. "
        "Return only the headline, no punctuation at the end, no quotes.\n\n"
        f"Article:\n{text[:2000]}\n\n"
        "Headline:"
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
        data = json.loads(_extract_json(raw))
        tags = data.get("tags", [])
        valid = {"policy", "model", "agents", "safety", "robotics", "voice", "health", "research", "ethics"}
        return [t for t in tags if t in valid][:3]
    except (json.JSONDecodeError, AttributeError):
        print(f"[warn] tag() failed to parse JSON: {raw!r}", file=sys.stderr)
        return ["research"]


def classify_ai(title: str, summary: str, model: str = SUMMARIZE_MODEL) -> bool:
    """Return True if the content is AI/ML/robotics related."""
    prompt = (
        "Is the following content specifically about artificial intelligence, machine learning, "
        "robotics, or LLMs? Answer YES only if the primary topic is AI/ML/robotics technology.\n\n"
        "Answer NO for: travel, lifestyle, product sales, referral programs, real estate, "
        "finance, sports, gaming, cloud gaming, advertisements, promotional emails, merchandise "
        "listings, gift guides, product catalogs, sponsored content, or any tech topic not "
        "primarily about AI/ML/robotics.\n\n"
        'Answer with a JSON object: {"relevant": true} or {"relevant": false}.\n\n'
        f"Title: {title}\n"
        f"Content: {summary[:500]}"
    )
    raw = _chat(prompt, model, json_mode=True)
    try:
        return bool(json.loads(_extract_json(raw)).get("relevant", False))
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
        groups: list[list[int]] = json.loads(_extract_json(raw)).get("duplicates", [])
    except (json.JSONDecodeError, AttributeError):
        print(f"[warn] deduplicate() failed to parse JSON: {raw!r}", file=sys.stderr)
        return items

    # For each duplicate group, keep the item with the longest summary
    to_drop: set[int] = set()
    for group in groups:
        if not isinstance(group, list) or len(group) < 2:
            continue
        # Clamp indices to valid range
        group = [i for i in group if isinstance(i, int) and 0 <= i < len(items)]
        if len(group) < 2:
            continue
        best = max(group, key=lambda i: len(items[i].get("summary", "")))
        for i in group:
            if i != best:
                to_drop.add(i)

    return [item for i, item in enumerate(items) if i not in to_drop]
