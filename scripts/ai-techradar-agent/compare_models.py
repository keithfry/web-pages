#!/usr/bin/env python3
"""Compare summarization quality of two Ollama models across 20 RSS articles.

Memory-efficient approach: all articles are processed by one model at a time,
then all judging is done by qwen at the end — so only one large model is loaded
into VRAM at any point.

Usage:
    uv run compare_models.py
    uv run compare_models.py --hours 48   # wider lookback if fewer articles
    uv run compare_models.py --out results.txt
"""

import argparse
import json
import math
import time
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import ollama

from config import LOOKBACK_HOURS
from feed_fetcher import fetch_all_feeds

MODELS = ["gemma4:e4b", "llama3.1:8b"]
JUDGE_MODEL = "llama3.1:8b"
ARTICLE_COUNT = 50


def _get_model_size(model: str) -> str:
    """Return human-readable model size from ollama."""
    try:
        models = ollama.list()["models"]
        for m in models:
            if m["name"] == model or m["model"] == model:
                size_bytes = m.get("size", 0)
                size_gb = size_bytes / 1e9
                return f"{size_gb:.1f} GB"
    except Exception:
        pass
    return "?"


def _summarize(article_num: int, title: str, text: str, model: str) -> tuple[str, float]:
    prompt = (
        "Summarize the following article in 3-4 sentences. "
        "Be specific and factual. Return only the summary, no preamble.\n\n"
        f"Title: {title}\n\nContent:\n{text[:2000]}"
    )
    t0 = time.perf_counter()
    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.perf_counter() - t0
    print(f"  [#{article_num}] {model} {elapsed:.2f}s", flush=True)
    return response["message"]["content"].strip(), elapsed


def _judge(article_num: int, title: str, summaries: dict[str, str]) -> dict:
    sections = "\n\n".join(
        f"=== Model: {m} ===\n{s}" for m, s in summaries.items()
    )
    prompt = (
        "You are evaluating AI-generated article summaries. "
        "Score each summary from 0.0 to 10.0 based on accuracy, clarity, "
        "completeness, and conciseness. Then give a composite ranking.\n\n"
        f"Article #{article_num}: {title}\n\n"
        f"{sections}\n\n"
        "Return a JSON object with this exact shape:\n"
        '{"scores": {"<model_name>": <score>, ...}, "winner": "<model_name>", '
        '"reasoning": "<one sentence>"}'
    )
    t0 = time.perf_counter()
    response = ollama.chat(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        format="json",
    )
    elapsed = time.perf_counter() - t0
    print(f"  [#{article_num}] {JUDGE_MODEL} (judge) {elapsed:.2f}s", flush=True)
    try:
        return json.loads(response["message"]["content"])
    except json.JSONDecodeError:
        return {"scores": {m: 0.0 for m in summaries}, "winner": "unknown", "reasoning": "parse error"}


def _generate_image(
    models: list[str],
    sizes: dict[str, str],
    avg_latency: dict[str, float],
    avg_scores: dict[str, float],
    final_scores: dict[str, float],
) -> None:
    col_labels = ["Model", "Size", "Avg Latency", "Avg Quality\nScore (0–10)", "Final Score\n(0–10)"]
    rows = []
    for m in models:
        rows.append([
            m,
            sizes.get(m, "?"),
            f"{avg_latency[m]:.2f}s",
            f"{avg_scores[m]:.2f}",
            f"{final_scores[m]:.2f}",
        ])

    # Sort by final score descending
    rows.sort(key=lambda r: float(r[4]), reverse=True)

    fig, ax = plt.subplots(figsize=(10, 2.8 + len(rows) * 0.7))
    ax.axis("off")

    table = ax.table(
        cellText=rows,
        colLabels=col_labels,
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1, 2.2)

    # Style header
    for col in range(len(col_labels)):
        cell = table[0, col]
        cell.set_facecolor("#1a1a2e")
        cell.set_text_props(color="white", fontweight="bold")

    # Style rows — highlight winner (row 1 = top score)
    row_colors = ["#e8f4fd", "#ffffff"]
    for row_idx, _ in enumerate(rows, start=1):
        bg = row_colors[0] if row_idx == 1 else row_colors[1]
        for col in range(len(col_labels)):
            cell = table[row_idx, col]
            cell.set_facecolor(bg)
            if col == 4 and row_idx == 1:
                cell.set_text_props(fontweight="bold", color="#0066cc")

    # Formula note — anchored just below the table
    ax.text(
        0.5, 0.02,
        "Final Score = 0.7 × Avg Quality Score  +  0.3 × Avg Latency",
        transform=ax.transAxes,
        fontsize=10,
        ha="center", va="bottom",
        color="#444444",
        fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f5f5f5", edgecolor="#cccccc"),
    )

    fig.suptitle(
        f"Model Comparison — {datetime.now().strftime('%Y-%m-%d')}",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )
    plt.tight_layout()
    plt.savefig("compare_models.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=LOOKBACK_HOURS)
    parser.add_argument("--out", default="compare_models_output.txt")
    args = parser.parse_args()

    # --- Fetch articles ---
    print(f"Fetching RSS feeds (last {args.hours}h)...", flush=True)
    articles, _ = fetch_all_feeds(args.hours)
    articles = [a for a in articles if a.get("title") and (a.get("summary") or "").strip()]
    articles = articles[:ARTICLE_COUNT]
    print(f"Using {len(articles)} articles\n", flush=True)

    # summaries[i] = {model: summary_text}
    summaries: dict[int, dict[str, str]] = {i: {} for i in range(len(articles))}
    # latencies[model] = [elapsed, ...]
    latencies: dict[str, list[float]] = {m: [] for m in MODELS}

    # --- Phase 1: summarize all articles with each model, one model at a time ---
    for model in MODELS:
        print(f"── {model}: summarizing {len(articles)} articles ──", flush=True)
        for i, article in enumerate(articles):
            title = article["title"]
            text = article.get("summary", "") or article.get("body", "")
            summary, elapsed = _summarize(i + 1, title, text, model)
            summaries[i][model] = summary
            latencies[model].append(elapsed)
        print(flush=True)

    # --- Phase 2: judge all articles sequentially with qwen ---
    print(f"── {JUDGE_MODEL}: judging {len(articles)} articles ──", flush=True)
    judgments: list[dict] = []
    for i, article in enumerate(articles):
        judgment = _judge(i + 1, article["title"], summaries[i])
        judgments.append(judgment)
        print(f"  [#{i+1}] winner={judgment.get('winner')}  scores={judgment.get('scores')}", flush=True)
    print(flush=True)

    # --- Write output file ---
    lines = [
        f"Model Comparison — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Models:   {', '.join(MODELS)}",
        f"Judge:    {JUDGE_MODEL}",
        f"Articles: {len(articles)}",
        "=" * 80,
        "",
    ]

    for i, article in enumerate(articles):
        j = judgments[i]
        lines += [
            f"Article #{i+1}: {article['title']}",
            f"Source: {article.get('source', '')}",
            "",
        ]
        for model in MODELS:
            score = j.get("scores", {}).get(model, "?")
            lines += [
                f"  [{model}]  score={score}",
                f"  {summaries[i][model]}",
                "",
            ]
        lines += [
            f"  Winner:    {j.get('winner')}",
            f"  Reasoning: {j.get('reasoning')}",
            "-" * 80,
            "",
        ]

    # Aggregate win counts and average scores
    win_counts: dict[str, int] = {m: 0 for m in MODELS}
    score_totals: dict[str, float] = {m: 0.0 for m in MODELS}
    score_counts: dict[str, int] = {m: 0 for m in MODELS}
    for j in judgments:
        winner = j.get("winner")
        if winner in win_counts:
            win_counts[winner] += 1
        for m, s in j.get("scores", {}).items():
            if m in score_totals:
                try:
                    score_totals[m] += float(s)
                    score_counts[m] += 1
                except (TypeError, ValueError):
                    pass

    avg_scores = {m: score_totals[m] / score_counts[m] if score_counts[m] else 0.0 for m in MODELS}
    avg_latency = {m: sum(latencies[m]) / len(latencies[m]) if latencies[m] else 0.0 for m in MODELS}

    # Final score: 70% quality + 30% speed, both normalized 0–10
    # quality component: avg_score is already 0–10
    # speed component: best (lowest) latency = 10, others scaled proportionally
    min_latency = min(avg_latency.values()) or 1.0
    speed_scores = {m: (min_latency / avg_latency[m]) * 10 if avg_latency[m] else 0.0 for m in MODELS}
    final_scores = {m: 0.7 * avg_scores[m] + 0.3 * speed_scores[m] for m in MODELS}

    lines += ["SUMMARY", "=" * 80]
    for m in MODELS:
        lines.append(
            f"  {m:30s}  wins={win_counts[m]:3d}  avg_score={avg_scores[m]:.2f}"
            f"  avg_latency={avg_latency[m]:.2f}s  final_score={final_scores[m]:.2f}"
        )
    lines.append("")

    with open(args.out, "w") as f:
        f.write("\n".join(lines))

    print(f"Results written to {args.out}\n")
    print("SUMMARY")
    print("=" * 40)
    for m in MODELS:
        print(
            f"  {m:30s}  wins={win_counts[m]}  avg={avg_scores[m]:.2f}"
            f"  latency={avg_latency[m]:.2f}s  final={final_scores[m]:.2f}"
        )

    # --- Generate comparison image ---
    model_sizes = {m: _get_model_size(m) for m in MODELS}
    _generate_image(MODELS, model_sizes, avg_latency, avg_scores, final_scores)
    print("Image written to compare_models.png")


if __name__ == "__main__":
    main()
