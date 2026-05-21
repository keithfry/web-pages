#!/usr/bin/env python3
"""Ad detection test harness — measures precision/recall/F1 across multiple detectors.

Usage:
    uv run test_ad_detector.py                    # run all detectors
    uv run test_ad_detector.py --detector heuristic
    uv run test_ad_detector.py --detector llm
    uv run test_ad_detector.py --detector custom  # ad-detector Ollama model
    uv run test_ad_detector.py --verbose          # show per-example table
    uv run test_ad_detector.py --data path/to/labeled_examples.json
"""

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent
_DEFAULT_DATA = _SCRIPT_DIR / "test_data" / "labeled_examples.json"

# Detector configs: (name, model_or_None)
_DETECTORS = {
    "heuristic": None,
    "llm": "llama3.2:3b",
    "custom": "ad-detector",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_examples(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    examples = [e for e in data["examples"] if e.get("is_ad") is not None]
    return examples


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def run_heuristic(examples: list[dict]) -> list[bool]:
    sys.path.insert(0, str(_SCRIPT_DIR))
    from main import _is_advertisement
    return [_is_advertisement(e["title"], e["summary"]) for e in examples]


def run_llm_gate(examples: list[dict], model: str) -> list[bool]:
    sys.path.insert(0, str(_SCRIPT_DIR))
    from llm import classify_ad
    results = []
    for i, e in enumerate(examples):
        is_ad, reason = classify_ad(e["title"], e["summary"], model)
        print(f"  [{i+1}/{len(examples)}] {e['title'][:50]!r} → {is_ad} ({reason})", flush=True)
        results.append(is_ad)
    return results


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(y_true: list[bool], y_pred: list[bool]) -> dict:
    tp = sum(t and p for t, p in zip(y_true, y_pred))
    fp = sum(not t and p for t, p in zip(y_true, y_pred))
    tn = sum(not t and not p for t, p in zip(y_true, y_pred))
    fn = sum(t and not p for t, p in zip(y_true, y_pred))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(y_true) if y_true else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _bar(value: float, width: int = 20) -> str:
    filled = round(value * width)
    return "█" * filled + "░" * (width - filled)


def print_report(
    detector_name: str,
    examples: list[dict],
    y_pred: list[bool],
    metrics: dict,
    verbose: bool,
) -> None:
    y_true = [e["is_ad"] for e in examples]
    sep = "─" * 56
    print(f"\nDetector: {detector_name}")
    print(sep)
    print(f"  Precision : {metrics['precision']:.2f}  {_bar(metrics['precision'])}")
    print(f"  Recall    : {metrics['recall']:.2f}  {_bar(metrics['recall'])}")
    print(f"  F1        : {metrics['f1']:.2f}  {_bar(metrics['f1'])}")
    print(f"  Accuracy  : {metrics['accuracy']:.2f}  {_bar(metrics['accuracy'])}")
    print()
    print("  Confusion Matrix (predicted →, actual ↓):")
    print(f"              {'Pred AD':>10}  {'Pred OK':>10}")
    print(f"  True AD     {metrics['tp']:>10}  {metrics['fn']:>10}{'  ← FN' if metrics['fn'] else ''}")
    print(f"  True OK     {metrics['fp']:>10}  {metrics['tn']:>10}{'  ← FP' if metrics['fp'] else ''}")
    print()

    false_negatives = [e for e, t, p in zip(examples, y_true, y_pred) if t and not p]
    false_positives = [e for e, t, p in zip(examples, y_true, y_pred) if not t and p]

    if false_negatives:
        print(f"  False negatives ({len(false_negatives)} ads slipped through):")
        for e in false_negatives:
            print(f"    [FN] {e['title'][:60]!r}  ({e.get('ad_type', '')})")
    if false_positives:
        print(f"  False positives ({len(false_positives)} good items wrongly blocked):")
        for e in false_positives:
            print(f"    [FP] {e['title'][:60]!r}")

    if verbose:
        print()
        print("  Per-example results:")
        for e, t, p in zip(examples, y_true, y_pred):
            status = "OK  " if t == p else ("FN  " if t and not p else "FP  ")
            label = "AD " if t else "ok "
            pred = "AD " if p else "ok "
            print(f"    [{status}] truth={label} pred={pred}  {e['title'][:50]!r}")

    print(sep)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Test ad detectors against labeled examples")
    parser.add_argument("--detector", choices=list(_DETECTORS) + ["all"], default="all")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--data", type=Path, default=_DEFAULT_DATA)
    args = parser.parse_args()

    examples = load_examples(args.data)
    ad_count = sum(1 for e in examples if e["is_ad"])
    ok_count = len(examples) - ad_count
    print(f"Loaded {len(examples)} labeled examples: {ad_count} ads, {ok_count} not-ads")

    detectors = list(_DETECTORS.items()) if args.detector == "all" else [(args.detector, _DETECTORS[args.detector])]

    for name, model in detectors:
        print(f"\nRunning detector: {name}" + (f" (model={model})" if model else ""))
        try:
            if name == "heuristic":
                y_pred = run_heuristic(examples)
            else:
                y_pred = run_llm_gate(examples, model)
        except Exception as exc:
            print(f"  [error] {exc}")
            continue

        y_true = [e["is_ad"] for e in examples]
        metrics = compute_metrics(y_true, y_pred)
        print_report(name, examples, y_pred, metrics, args.verbose)


if __name__ == "__main__":
    main()
