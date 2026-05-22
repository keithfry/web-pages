"""Thin Ollama wrapper for all LLM operations in the pipeline."""

import json
import re
import sys
import threading
import time

import ollama

from config import SUMMARIZE_MODEL, RANK_MODEL

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
        f"Article:\n{text[:8000]}\n\n"
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
        f"Content:\n{text[:8000]}"
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
        valid = {
            "policy",
            "model",
            "agents",
            "safety",
            "robotics",
            "voice",
            "health",
            "research",
            "ethics",
        }
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
        f"Content: {summary[:3000]}"
    )
    raw = _chat(prompt, model, json_mode=True)
    try:
        return bool(json.loads(_extract_json(raw)).get("relevant", False))
    except (json.JSONDecodeError, AttributeError):
        # Default to keeping the item if classification fails
        return True


def classify_ad(title: str, summary: str, model: str = SUMMARIZE_MODEL) -> tuple[bool, str]:
    """Return (is_ad, reason). Fails open — returns (False, 'parse error') on JSON failure."""
    prompt = (
        "You are a content classifier. Identify promotional, advertising, or non-editorial "
        "content that should be excluded from a curated AI/tech news feed.\n\n"
        "Mark is_ad: true if the item primarily does ONE of these:\n\n"
        "1. REFERRAL PROGRAM — asks reader to share a link for rewards/prizes.\n"
        "   Signals: \"share your link\", \"refer a friend\", \"earn rewards\", \"prizes available\"\n\n"
        "2. LEAD-GEN OFFER — free guide/ebook/template/checklist as lead capture.\n"
        "   Signals: \"free guide\", \"download now\", \"150+ prompts\", \"get access\", \"free stack\"\n\n"
        "3. NEWSLETTER CTA — asks reader to confirm subscription or re-engage to avoid removal.\n"
        "   Signals: \"still interested?\", \"click to confirm\", \"monitoring subscriber activity\", "
        "\"high email costs\", \"vote to stay\"\n\n"
        "4. ADVERTISING PITCH — promotes buying ad slots in a newsletter or marketing platform.\n"
        "   Signals: \"advertise in\", \"reach X million\", \"ROI\", \"pipeline value\", \"ad slot\"\n\n"
        "5. SUBSCRIPTION PRODUCT — paid membership, exclusive access, or recurring service pitch.\n"
        "   Signals: \"exclusive zip code\", \"one agent per city\", \"$X/year\", \"weekly leads\", "
        "\"apply now\", \"acceptance rate\"\n\n"
        "6. PRODUCT FEATURE DISGUISED AS NEWS — product email written to drive feature adoption.\n"
        "   Signals: imperative language (\"start shopping\", \"try it\"), reader is the target "
        "user, written from product POV\n\n"
        "Do NOT mark as ad: news about product launches (neutrally reported by third parties), "
        "research papers, analysis/opinion, technical tutorials, press releases from official "
        "company blogs with no purchase CTA.\n\n"
        "Examples:\n"
        "Title: \"Refer Friends and Get Rewards with The Hustle Program\"\n"
        "Summary: \"Share a unique link. Prizes are available for purchase.\"\n"
        '→ {"is_ad": true, "reason": "referral program with prize incentive"}\n\n'
        "Title: \"Free Guide to 150+ AI Prompts for Solopreneurs\"\n"
        "Summary: \"A free guide provides 150+ plug-and-play AI prompts. Download your free stack.\"\n"
        '→ {"is_ad": true, "reason": "lead-gen gated content offer"}\n\n'
        "Title: \"Top-Tier Tech Marketers Advertise in TLDR Newsletter\"\n"
        "Summary: \"Reach over 7 million tech professionals. Results: $382k in pipeline, 20.1x ROI.\"\n"
        '→ {"is_ad": true, "reason": "newsletter advertising network pitch"}\n\n'
        "Title: \"A faster way to shop\"\n"
        "Summary: \"ChatGPT helps you browse and compare products side-by-side. Start shopping.\"\n"
        '→ {"is_ad": true, "reason": "product feature pitch disguised as editorial"}\n\n'
        "Title: \"Still interested in Tech news?\"\n"
        "Summary: \"Due to high email costs, we monitor subscriber activity. Click to confirm.\"\n"
        '→ {"is_ad": true, "reason": "newsletter re-engagement CTA"}\n\n'
        "Title: \"Exclusive Real Estate Agent Program for Proven Performers Only\"\n"
        "Summary: \"One agent per city. Apply now. 15+ closings required. $2000/year.\"\n"
        '→ {"is_ad": true, "reason": "subscription product pitch with exclusivity framing"}\n\n'
        "Title: \"Gemini 3.5 Flash, Karpathy joins Anthropic, OpenAI Guaranteed Capacity\"\n"
        "Summary: \"Google introduced Gemini 3.5 Flash. Karpathy joins Anthropic.\"\n"
        '→ {"is_ad": false, "reason": "neutral news digest about AI developments"}\n\n'
        "Title: \"GPT-4o Gets New Voice Mode Capabilities\"\n"
        "Summary: \"OpenAI released an update adding real-time voice conversation.\"\n"
        '→ {"is_ad": false, "reason": "factual product capability news"}\n\n'
        "Title: \"Andrej Karpathy Joins Anthropic: What Happens Next\"\n"
        "Summary: \"Karpathy joins Anthropic as a researcher focused on AI capabilities.\"\n"
        '→ {"is_ad": false, "reason": "industry hiring news, third-party analysis"}\n\n'
        f"Now classify:\n"
        f"Title: {title}\n"
        f"Summary: {summary}\n\n"
        'Respond ONLY with JSON: {"is_ad": true/false, "reason": "brief explanation"}'
    )
    raw = _chat(prompt, model, json_mode=True)
    try:
        data = json.loads(_extract_json(raw))
        return bool(data.get("is_ad", False)), str(data.get("reason", ""))
    except (json.JSONDecodeError, AttributeError):
        print(f"[warn] classify_ad() failed to parse JSON: {raw!r}", file=sys.stderr)
        return False, "parse error"


def deduplicate(items: list[dict], model: str = SUMMARIZE_MODEL) -> list[dict]:
    """Remove near-duplicate items, keeping the one with the longer summary."""
    if len(items) <= 1:
        return items

    # Build a compact index for the LLM
    index_lines = "\n".join(f"{i}: {item['title']}" for i, item in enumerate(items))
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


def rank_items(items: list[dict], model: str = RANK_MODEL) -> list[dict]:
    """Rank items by AI/robotics relevance and newsworthiness, 1 = most important.

    Returns a new list sorted by rank with a 'rank' field added to each item.
    Falls back to original order if LLM response cannot be parsed.
    """
    if not items:
        return []

    index_lines = "\n".join(
        f"{i}: {item['title']}" for i, item in enumerate(items)
    )
    prompt = (
        "You are an editor ranking AI and robotics news items by importance and interest "
        "for a daily listener. Rank the following items from most to least important. "
        "Consider: breadth of impact, novelty, practical significance for AI practitioners.\n\n"
        "Return a JSON object with key 'ranked' — a list of original indices in order "
        "from most to least important. Include every index exactly once.\n\n"
        f"Items:\n{index_lines}\n\n"
        'Example response: {"ranked": [3, 0, 2, 1]}'
    )
    raw = _chat(prompt, model, json_mode=True)
    try:
        order: list[int] = json.loads(_extract_json(raw)).get("ranked", [])
        order = [int(x) for x in order]
        if sorted(order) != list(range(len(items))):
            raise ValueError(f"Bad ranking: {order}")
        ranked = []
        for rank, orig_idx in enumerate(order, 1):
            item = dict(items[orig_idx])
            item["rank"] = rank
            ranked.append(item)
        return ranked
    except (json.JSONDecodeError, AttributeError, ValueError) as e:
        print(f"[warn] rank_items() failed ({e}), using original order", file=sys.stderr)
        return [dict(item, rank=i + 1) for i, item in enumerate(items)]


def generate_audio_script(item: dict, model: str = SUMMARIZE_MODEL) -> str:
    """Generate a ~140-word news-report style spoken script for a single podcast segment.

    Structure: source/title attribution → overview (5-10s) → body (45s) → conclusion (10-15s).
    """
    source = item.get("source", "")
    title = item.get("title", "")
    summary = item.get("summary", "")

    prompt = (
        "Write a spoken podcast news segment in three parts. "
        "Use a factual, third-person news-report tone — no personal opinions, no 'you', no 'we'. "
        "No bullet points. No markdown. No URLs. No 'click here' or 'read more'. "
        "Write as one continuous spoken passage.\n\n"
        f"Source: {source}\n"
        f"Title: {title}\n"
        f"Summary: {summary}\n\n"
        "Structure — write all three parts as a single flowing paragraph:\n"
        f"1. ATTRIBUTION (1 sentence): Begin with 'From {source}, \"{title}\".' "
        "then immediately state in one sentence what this story is about and its key result or finding.\n"
        "2. BODY (about 100 words): Report the details — what was done, how it was accomplished, "
        "the process, the methodology, the specific findings or announcements. Be precise and factual.\n"
        "3. CONCLUSION (about 30 words): State what this means for the AI/tech industry "
        "or what to watch for next. No rhetorical questions.\n\n"
        "Target total: approximately 140 words.\n\n"
        "Spoken segment:"
    )
    return _chat(prompt, model).strip()


def generate_intro_script(items: list[dict], date: "datetime", model: str = SUMMARIZE_MODEL) -> str:
    """Generate a podcast intro mentioning date, item count, and top-3 topics."""
    date_str = f"{date.strftime('%B')} {date.day}, {date.year}"
    top3 = [item["title"] for item in items[:3]]
    top3_str = "\n".join(f"- {t}" for t in top3)
    prompt = (
        f"Write a short podcast intro (under 45 words). "
        f"Date: {date_str}. Total items: {len(items)}. "
        f"Mention up to 3 top stories by topic (not exact title). "
        f"Sound natural and welcoming. No markdown. End naturally, don't say 'let's get started'.\n\n"
        f"Top stories:\n{top3_str}\n\n"
        "Intro:"
    )
    return _chat(prompt, model).strip()
