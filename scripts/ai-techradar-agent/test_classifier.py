#!/usr/bin/env python3
"""Test cases for the AI/robotics content classifier.

Usage:
    uv run test_classifier.py

Tests both the keyword pre-filter and the LLM classifier.
"""

import sys
from main import _AI_KEYWORDS
from llm import classify_ai
from config import SUMMARIZE_MODEL

# ---------------------------------------------------------------------------
# Test cases: (title, summary, expected_relevant)
# ---------------------------------------------------------------------------

CASES = [
    # --- Should be REJECTED ---
    (
        False,
        "United Introduces Adjustable Armrests on Long-Haul Flights",
        "United Airlines is introducing adjustable armrests on long-haul flights in 2027 across "
        "over 200 aircraft. The 'Relax Row' seat offering will feature three economy seats that "
        "can be converted into a couch with additional amenities. These seats are intended to "
        "provide more comfort and space for passengers during long flights.",
    ),
    (
        False,
        "Refer Friends to The Hustle and Earn Exclusive Perks",
        "To refer friends to The Hustle and earn exclusive perks, share a unique link with them. "
        "They must subscribe through the personalized referral link, then confirm their "
        "subscription via email. Prizes are available for purchase in the shop.",
    ),
    (
        False,
        "Candles Mugs Hats Tees and Desk Organizers for Sale",
        "Candles, mugs, hats, and desk organizers are available for purchase from a list of 24 "
        "products, priced between $5.75 and $55.50. The selection includes items from brands "
        "such as Bella + Canvas and Brigham.",
    ),
    (
        False,
        "Exclusive Zip Code Leads Available",
        "Real Intent provides exclusive zip code leads to one agent per zip code, offering up to "
        "25 new leads weekly from households looking to buy or sell a home. The company uses "
        "intent data to track and target clients, ensuring no competitors in the area. Annual "
        "plans cost $2000/year.",
    ),
    (
        False,
        "Game On: Five New Titles Now Streaming on GeForce NOW",
        "GeForce NOW is adding five new titles to its streaming service, including a retro-racing "
        "game called 'Screamer' that offers pixel-perfect speed. The new games can be streamed "
        "instantly across various devices, helping players clear their gaming backlog. GeForce "
        "NOW's cloud gaming platform provides access to a library of games, allowing users to "
        "play without the need for dedicated hardware.",
    ),
    # --- Should be ACCEPTED ---
    (
        True,
        "GPT-4o Gets New Voice Mode Capabilities",
        "OpenAI has released an update to GPT-4o adding real-time voice conversation support "
        "with improved latency and emotional tone recognition. The model can now handle "
        "interruptions naturally.",
    ),
    (
        True,
        "Boston Dynamics Spot Gets New Manipulation Arm",
        "Boston Dynamics announced an upgraded manipulation arm for its Spot robot, improving "
        "payload capacity and dexterity for industrial inspection tasks. The new hardware "
        "supports autonomous object retrieval.",
    ),
    (
        True,
        "Mistral Releases New 7B Instruct Model",
        "Mistral AI has released a new 7B parameter instruct model with improved reasoning "
        "benchmarks. The model is available under an Apache 2.0 license and can run locally "
        "on consumer hardware via Ollama.",
    ),
]


def keyword_matches(title: str, summary: str) -> bool:
    lowered = (title + " " + summary).lower()
    return any(kw in lowered for kw in _AI_KEYWORDS)


def run_tests() -> None:
    passed = 0
    failed = 0

    print(f"Model: {SUMMARIZE_MODEL}\n")
    print(f"{'#':<3} {'Expected':<10} {'KW':<6} {'LLM':<6} {'Result':<8}  Title")
    print("-" * 90)

    for i, (expected, title, summary) in enumerate(CASES, 1):
        kw_match = keyword_matches(title, summary)

        if kw_match:
            # Keyword matched → would be auto-accepted without LLM call
            llm_result = None
            final = True
        else:
            llm_result = classify_ai(title, summary, SUMMARIZE_MODEL)
            final = llm_result

        ok = final == expected
        status = "PASS" if ok else "FAIL"
        kw_str = "yes" if kw_match else "no"
        llm_str = ("yes" if llm_result else "no") if llm_result is not None else "skip"

        print(f"{i:<3} {'yes' if expected else 'no':<10} {kw_str:<6} {llm_str:<6} {status:<8}  {title[:60]}")

        if ok:
            passed += 1
        else:
            failed += 1

    print("-" * 90)
    print(f"\n{passed}/{passed+failed} passed", end="")
    if failed:
        print(f", {failed} FAILED", end="")
        sys.exit(1)
    else:
        print(" ✓")


if __name__ == "__main__":
    run_tests()
