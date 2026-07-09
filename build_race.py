#!/usr/bin/env python3
"""Team Tier Goal ladder + Individual Race computations, from the already-built
pipeline.partial.json and stripe.partial.json.
Usage: python3 build_race.py
Writes race.partial.json (merged into data.json by build_dashboard.py).

Metric mapping assumptions (the source dashboard's exact server logic isn't visible from
outside; these are documented, tunable best-guesses, not invented numbers pulled from
nowhere - every one is a real aggregate of already-reconciled pipeline/stripe data):
  - "Open Deals" is a LIVE snapshot (opportunities currently sitting in an open stage for
    that closer right now), not window-scoped - a pipeline doesn't empty out at midnight.
  - "Meetings" (per-rep stat) and "Meetings Booked" (team strip) = calls booked in the
    window (GHL's BOOKED_STAGES bucket), window-scoped.
  - "Close Rate" = dealsWon(window) / openDeals(live). This is the one mapping verified
    against real observed numbers on the source site (Caleb: 1 deal won, 92 open deals ->
    1.1% at one decimal place, exactly 1/92*100).
  - Badges: Top Closer = #1 all-time cash among active roster. Pipeline King = most open
    deals live among active roster. First Deal = >=1 deal won all-time. Fast Starter =
    >=1 deal won within the first 3 days of the current window (week/month only, not
    day - a 1-day window trivially satisfies "first 3 days"). Leading = rank 1, always
    (even at $0, ranking falls back to pipeline).
"""
import json
import sys
from datetime import datetime, timedelta, timezone

from lib import (ACTIVE_CLOSERS, WINDOW_KEYS, NOMINAL_WINDOW_DAYS, TEAM_LEVEL_TARGETS_MONTHLY, RACE_TARGET_MONTHLY,
                  money_round, pct, in_window, to_la_date)


def load(name):
    with open(name, encoding="utf-8") as f:
        return json.load(f)


def scale_to_window(monthly_dollars, win_key):
    """Monthly target scaled by the window's NOMINAL length (1/7/30 days), never by the
    actual (possibly launch-clamped) span of the window's date range - confirmed against
    the source dashboard: daily L1 = 200000/30 = 6667, weekly L1 = 200000/30*7 = 46667,
    and Monthly kept a flat, unscaled $200,000 target even while its date range was
    launch-clamped to fewer than 30 real days."""
    return round(monthly_dollars * 100 * NOMINAL_WINDOW_DAYS[win_key] / 30.0)  # cents


def build_team_ladder(collected_cents, win_key):
    targets_cents = [scale_to_window(t, win_key) for t in TEAM_LEVEL_TARGETS_MONTHLY]
    level = sum(1 for t in targets_cents if collected_cents >= t)
    states = []
    for i, t in enumerate(targets_cents):
        if i < level:
            states.append("reached")
        elif i == level:
            states.append("in_reach")
        else:
            states.append("locked")
    if level < len(targets_cents):
        next_target = targets_cents[level]
        to_reach = next_target - collected_cents
        pct_to_next = 100.0 * collected_cents / next_target if next_target else 0.0
    else:
        next_target = None
        to_reach = 0
        pct_to_next = 100.0
    return {
        "levelTargetsCents": targets_cents,
        "collectedCents": collected_cents,
        "level": level,
        "nextLevel": level + 1 if level < len(targets_cents) else None,
        "nextTargetCents": next_target,
        "toReachNextCents": to_reach,
        "pctToNextNum": round(pct_to_next, 0),
        "levelStates": states,
        "complete": level == len(targets_cents),
    }


def build_race_rows(pipeline, stripe, win_key, career_top_cash_key, career_first_deal_keys):
    team_cash = 0
    rows = []
    for c in ACTIVE_CLOSERS:
        key = c["key"]
        pipe_row = pipeline["byCloser"][key][win_key]
        cash_cents = stripe["byCloser"][key][win_key]["cash_cents"]
        open_deals = pipeline["byCloser"][key]["openDeals"]
        deals_won = pipe_row["won"]
        meetings = pipe_row["booked"]
        team_cash += cash_cents
        rows.append({
            "key": key,
            "name": c["name"],
            "cashCents": cash_cents,
            "dealsWon": deals_won,
            "openDeals": open_deals,
            "meetings": meetings,
            "closeRate": rate1(deals_won, open_deals),
        })

    ranked_by_cash = team_cash > 0
    if ranked_by_cash:
        rows.sort(key=lambda r: (-r["cashCents"], -r["dealsWon"], -r["openDeals"], r["name"]))
        ranked_by_label = "Ranked by cash, then deals won, then pipeline owned"
    else:
        rows.sort(key=lambda r: (-r["openDeals"], r["name"]))
        ranked_by_label = "Ranked by open pipeline"

    for i, r in enumerate(rows):
        r["rank"] = i + 1

    target_cents = scale_to_window(RACE_TARGET_MONTHLY, win_key)
    leader = rows[0] if rows else None
    fast_starter_keys = fast_starters(pipeline, win_key, pipeline["windows"][win_key]) if win_key in ("week", "month") else set()

    for r in rows:
        r["pctToGoalNum"] = round(100.0 * r["cashCents"] / target_cents, 0) if target_cents else 0
        r["toGoCents"] = max(0, target_cents - r["cashCents"])
        r["leading"] = r["rank"] == 1
        badges = []
        if r["leading"]:
            badges.append("Leading")
        if career_top_cash_key and r["key"] == career_top_cash_key:
            badges.append("Top Closer")
        if r["key"] in career_first_deal_keys:
            badges.append("First Deal")
        if r["key"] in fast_starter_keys:
            badges.append("Fast Starter")
        r["badges"] = badges
        if not ranked_by_cash:
            r["lineA"] = None  # the shared zero-cash banner already covers this
        else:
            r["lineA"] = "Every deal counts" if r["cashCents"] > 0 else "First on the board wins"
        if r["rank"] == 1:
            r["lineB"] = "Setting the pace"
        else:
            gap = leader["cashCents"] - r["cashCents"]
            r["lineB"] = (money_round(gap) + " to pass " + leader["name"]) if gap > 0 else ("Tied with " + leader["name"])

    pipeline_king_key = max(rows, key=lambda r: r["openDeals"])["key"] if rows and max(r["openDeals"] for r in rows) > 0 else None
    for r in rows:
        if pipeline_king_key and r["key"] == pipeline_king_key:
            r["badges"].insert(1 if r["leading"] else 0, "Pipeline King")

    banner = None
    if not ranked_by_cash:
        period_word = {"day": "today", "week": "this week", "month": "this month"}[win_key]
        banner = "No cash collected " + period_word + ". First on the board wins. Ranked by open pipeline until then."

    return {
        "targetCents": target_cents,
        "rankedByCash": ranked_by_cash,
        "rankedByLabel": ranked_by_label,
        "bannerNote": banner,
        "teamCashCents": team_cash,
        "rows": rows,
    }


def rate1(numer, denom):
    """One-decimal percentage, matching the source dashboard's Close Rate display (e.g. 1.1%)."""
    if not denom:
        return "0%" if not numer else "awaiting"
    return "{:.1f}%".format(100.0 * numer / denom)


def fast_starters(pipeline, win_key, window):
    """Closers who won >=1 deal within the first 3 days of the current window.
    Requires per-opportunity won dates, which build_pipeline.py doesn't currently retain
    per-day - approximated here as: the closer won at least one deal in this window AND
    the window itself is <=3 days old so far (i.e. we're still within the first 3 days),
    OR the window is longer and the closer's win count in the window is already >0 by the
    window's 3rd day. Since build_pipeline only gives a window total (not day-by-day),
    this reduces to: window has run <=3 days so far and the closer already has a win.
    Documented approximation - see module docstring."""
    days_elapsed = (datetime.strptime(window["end"], "%Y-%m-%d") - datetime.strptime(window["start"], "%Y-%m-%d")).days + 1
    today = datetime.now(timezone.utc).date().isoformat()
    days_so_far = (datetime.strptime(min(today, window["end"]), "%Y-%m-%d") - datetime.strptime(window["start"], "%Y-%m-%d")).days + 1
    if days_so_far > 3:
        return set()
    return {c["key"] for c in ACTIVE_CLOSERS if pipeline["byCloser"][c["key"]][win_key]["won"] > 0}


def main():
    pipeline = load("pipeline.partial.json")
    stripe = load("stripe.partial.json")

    if pipeline["windows"] != stripe["windows"]:
        print("RECONCILE FAIL (race): pipeline/stripe partials disagree on window boundaries")
        sys.exit(1)
    windows = pipeline["windows"]

    career_top_cash_key = None
    best = -1
    for c in ACTIVE_CLOSERS:
        cash = stripe["byCloser"][c["key"]]["allTime"]["cash_cents"]
        if cash > best and cash > 0:
            best = cash
            career_top_cash_key = c["key"]
    career_first_deal_keys = {c["key"] for c in ACTIVE_CLOSERS if pipeline["byCloser"][c["key"]]["allTime"]["won"] > 0}

    team = {}
    race = {}
    team_totals = {}
    for win_key in WINDOW_KEYS:
        active_cash = sum(stripe["byCloser"][c["key"]][win_key]["cash_cents"] for c in ACTIVE_CLOSERS)
        team[win_key] = build_team_ladder(active_cash, win_key)
        race[win_key] = build_race_rows(pipeline, stripe, win_key, career_top_cash_key, career_first_deal_keys)

        active_deals = sum(pipeline["byCloser"][c["key"]][win_key]["won"] for c in ACTIVE_CLOSERS)
        active_open = sum(pipeline["byCloser"][c["key"]]["openDeals"] for c in ACTIVE_CLOSERS)
        active_meetings = sum(pipeline["byCloser"][c["key"]][win_key]["booked"] for c in ACTIVE_CLOSERS)
        team_totals[win_key] = {
            "cashCents": active_cash,
            "dealsWon": active_deals,
            "openDeals": active_open,
            "meetingsBooked": active_meetings,
        }
        # Reconcile gate: team ladder's collected figure must equal the race section's own
        # team cash tally and the team totals strip, to the cent - one number, shown three ways.
        if team[win_key]["collectedCents"] != race[win_key]["teamCashCents"]:
            print("RECONCILE FAIL (race): %s team ladder cash != race section team cash" % win_key)
            sys.exit(1)
        if team[win_key]["collectedCents"] != team_totals[win_key]["cashCents"]:
            print("RECONCILE FAIL (race): %s team ladder cash != team totals cash" % win_key)
            sys.exit(1)
        if sum(r["cashCents"] for r in race[win_key]["rows"]) != active_cash:
            print("RECONCILE FAIL (race): %s race rows cash sum != active cash" % win_key)
            sys.exit(1)

    out = {
        "windows": windows,
        "team": team,
        "race": race,
        "teamTotals": team_totals,
    }
    with open("race.partial.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("OK race.partial.json written. month team level=%d collected=%s" % (
        team["month"]["level"], money_round(team["month"]["collectedCents"])))


if __name__ == "__main__":
    main()
