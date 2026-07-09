#!/usr/bin/env python3
"""Merge pipeline/stripe/race partials into data.json.
Usage: python3 build_dashboard.py
This is the hard reconcile gate: if the partials disagree with each other, or with an
independent recomputation of the tier-ladder/race-target scaling formula, this script
exits non-zero and data.json is NOT (re)written, so a bad pull can never reach render.js
or the deployed page.
"""
import json
import sys
from datetime import datetime, timezone

from lib import (CLOSERS, ACTIVE_CLOSERS, ACTIVE_KEYS, WINDOW_KEYS, NOMINAL_WINDOW_DAYS,
                  TEAM_LEVEL_TARGETS_MONTHLY, RACE_TARGET_MONTHLY, money, money_round)


def load(name):
    with open(name, encoding="utf-8") as f:
        return json.load(f)


def scale_to_window(monthly_dollars, win_key):
    return round(monthly_dollars * 100 * NOMINAL_WINDOW_DAYS[win_key] / 30.0)


def main():
    pipeline = load("pipeline.partial.json")
    stripe = load("stripe.partial.json")
    race = load("race.partial.json")

    if pipeline["windows"] != stripe["windows"] or pipeline["windows"] != race["windows"]:
        print("RECONCILE FAIL (dashboard): pipeline/stripe/race partials disagree on window boundaries")
        sys.exit(1)
    windows = pipeline["windows"]
    now_utc = datetime.now(timezone.utc)

    for win_key in WINDOW_KEYS:
        window = windows[win_key]
        team = race["team"][win_key]
        r = race["race"][win_key]
        tt = race["teamTotals"][win_key]

        # Independent recomputation of the scaling formula - catches drift/bugs in
        # build_race.py rather than trusting its own output.
        expect_team_targets = [scale_to_window(t, win_key) for t in TEAM_LEVEL_TARGETS_MONTHLY]
        if team["levelTargetsCents"] != expect_team_targets:
            print("RECONCILE FAIL (dashboard): %s team level targets != independent recompute" % win_key)
            sys.exit(1)
        expect_race_target = scale_to_window(RACE_TARGET_MONTHLY, win_key)
        if r["targetCents"] != expect_race_target:
            print("RECONCILE FAIL (dashboard): %s race target != independent recompute" % win_key)
            sys.exit(1)

        # Level math: level N reached iff collected >= target N, for every level.
        expect_level = sum(1 for t in expect_team_targets if team["collectedCents"] >= t)
        if team["level"] != expect_level:
            print("RECONCILE FAIL (dashboard): %s team level (%d) != recomputed (%d)" % (win_key, team["level"], expect_level))
            sys.exit(1)

        # Ranks must be a valid 1..N permutation with no gaps or repeats.
        ranks = sorted(row["rank"] for row in r["rows"])
        if ranks != list(range(1, len(r["rows"]) + 1)):
            print("RECONCILE FAIL (dashboard): %s race ranks not a clean 1..N permutation" % win_key)
            sys.exit(1)

        # Team cash === sum of active rep cash, to the cent, checked three ways at once.
        rows_cash = sum(row["cashCents"] for row in r["rows"])
        if not (team["collectedCents"] == rows_cash == tt["cashCents"] == r["teamCashCents"]):
            print("RECONCILE FAIL (dashboard): %s cash disagreement across team/race/teamTotals" % win_key)
            sys.exit(1)

        # Cross-check against the stripe partial directly (independent source, not race.py's own math).
        stripe_active_cash = sum(stripe["byCloser"][c["key"]][win_key]["cash_cents"] for c in ACTIVE_CLOSERS)
        if stripe_active_cash != team["collectedCents"]:
            print("RECONCILE FAIL (dashboard): %s team cash != stripe partial active-roster sum" % win_key)
            sys.exit(1)

        # Deals won across race rows must equal the pipeline partial's active-roster sum.
        pipeline_active_won = sum(pipeline["byCloser"][c["key"]][win_key]["won"] for c in ACTIVE_CLOSERS)
        if pipeline_active_won != sum(row["dealsWon"] for row in r["rows"]) or pipeline_active_won != tt["dealsWon"]:
            print("RECONCILE FAIL (dashboard): %s dealsWon disagreement" % win_key)
            sys.exit(1)

    data = {
        "asOf": windows["day"]["start"],
        "timezone": "America/Los_Angeles",
        "generatedAtUtc": now_utc.isoformat(timespec="seconds"),
        "windows": {k: windows[k] for k in WINDOW_KEYS},
        "roster": [{"key": c["key"], "name": c["name"]} for c in CLOSERS if c["key"] in ACTIVE_KEYS],
        "rosterNames": ", ".join(c["name"] for c in CLOSERS if c["key"] in ACTIVE_KEYS),
        "team": race["team"],
        "race": race["race"],
        "teamTotals": race["teamTotals"],
        "audit": {
            "excludedTestRecords": pipeline["excludedTestRecords"],
            "totalOpportunitiesPulled": pipeline["totalOpportunities"],
            "unattributedCashAllTime": money(stripe["unattributed"]["allTime"]["cash_cents"]),
            "offboardedClosers": [c["name"] for c in CLOSERS if c["key"] not in ACTIVE_KEYS],
        },
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("OK data.json written. asOf=%s month team collected=%s level=%d" % (
        data["asOf"], money_round(race["team"]["month"]["collectedCents"]), race["team"]["month"]["level"]))


if __name__ == "__main__":
    main()
