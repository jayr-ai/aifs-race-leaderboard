"""Shared constants and helpers for the Race Leaderboard build scripts.
Single place for facts that must stay identical across build_pipeline.py, build_stripe.py,
build_race.py and build_dashboard.py, so they can never drift apart.
"""
import json
import os
from datetime import datetime, timedelta, timezone

LOCATION_ID = "61bBcrk5Fi4BuTWwvW0P"
PIPELINE_ID = "PJbkfqE3g4KRP8i9ZeLb"
TZ_NAME = "America/Los_Angeles"
LA_OFFSET_HOURS = -7  # PDT (America/Los_Angeles daylight time; this account's operating window is northern-hemisphere summer)
LA = timezone(timedelta(hours=LA_OFFSET_HOURS))

# The full closer roster, active and offboarded, lives in roster.json (not here), so
# onboarding or offboarding a closer is a one-line data edit, never a code change.
# CLOSERS = everyone who ever held the role, active or not: attribution (matching a
#   pipeline opp's assignedTo or a Stripe charge's contact email) always checks the full
#   roster, so a departed closer's historical numbers are never silently reclassified.
# ACTIVE_CLOSERS = only status:"active": this is who appears as a ranked row in the
#   Individual Races. Team Tier Goal totals fold in any offboarded closer's real
#   historical contribution too (disclosed, never silently dropped).
_ROSTER_PATH = os.path.join(os.path.dirname(__file__), "roster.json")
with open(_ROSTER_PATH, encoding="utf-8") as _f:
    CLOSERS = json.load(_f)["closers"]
ACTIVE_CLOSERS = [c for c in CLOSERS if c.get("status") == "active"]
CLOSER_BY_ID = {c["id"]: c for c in CLOSERS}
ACTIVE_KEYS = {c["key"] for c in ACTIVE_CLOSERS}

# The business's marketing launch date, same account and same date as the AIFS CRO
# dashboard and the sales-leaderboard-dashboard project. "All time" means since this
# date, not since the pipeline's oldest record.
LAUNCH_DATE = "2026-06-15"

# The 3 user-facing toggle windows. "allTime" is computed too (career stats for badges:
# Top Closer, First Deal) but is never a visible tab on this dashboard.
WINDOW_KEYS = ("day", "week", "month")
ALL_WINDOW_KEYS = WINDOW_KEYS + ("allTime",)

# Nominal window length in days, used ONLY for scaling the tier-ladder/race targets.
# Confirmed against the source dashboard: Monthly kept a flat $200,000 Level-1 target
# even while the account was only 25 real days past launch (a trailing, launch-clamped
# date range) - so target scaling always uses the *nominal* period length, never the
# actual (possibly clamped) number of days a window's date range spans.
NOMINAL_WINDOW_DAYS = {"day": 1, "week": 7, "month": 30}

STAGE_MAP = {
    "b9bfc681-76ef-4402-a7b8-428e39788582": "newUnworked",
    "910d1097-8955-4f62-9c79-eaafc3963a22": "contacted",
    "a774b303-1cba-4279-b5d5-d06ae8eca597": "callBooked",
    "58b9e8fb-3e0f-4273-84d7-2a11c7bc0b59": "rescheduling",
    "8dec9a2c-863a-45d4-8495-f7dc8c17704b": "noShow",
    "fe83e23b-7a54-4906-95fd-3415a8824a32": "apptCancelled",
    "55f294c8-14a8-4734-83e3-9cb8d537c419": "callHeld",
    "a402364a-ad70-40af-b310-bfbce676ef45": "highPriority",
    "043f4a69-e187-481c-b43b-a7dd9ac34775": "closedWon",
    "a3bd42d8-305d-4307-aba7-b1da1658acbc": "longTermNurture",
    "368b91ca-95f0-48f8-89e2-6074426b983b": "lost",
}

# Stages that mean "a call was booked and its outcome, whatever it was, is now known
# or still pending" - the full universe booked-call denominator.
BOOKED_STAGES = {"callBooked", "rescheduling", "noShow", "apptCancelled", "callHeld", "highPriority", "closedWon"}
# Stages that mean the prospect actually showed up to the call (used as "meetings").
SHOWED_STAGES = {"callHeld", "highPriority", "closedWon"}
# Stages that mean the opportunity is still open (not won, not lost).
OPEN_STAGES = {"newUnworked", "contacted", "callBooked", "rescheduling", "noShow", "apptCancelled",
               "callHeld", "highPriority", "longTermNurture"}

TEST_DOMAINS = {"tothemoondigital.com.au", "amala.agency", "eazeconsulting.com", "eazepay.com"}

# Team Tier Goal ladder and the Individual Race target, both monthly bases scaled by
# window_days/30 for Daily/Weekly (confirmed against the source dashboard: daily L1 =
# $6,667 = 200000/30, weekly L1 = $46,667 = 200000/30*7, daily race = $5,000 = 150000/30).
TEAM_LEVEL_TARGETS_MONTHLY = (200000, 400000, 600000)  # dollars, Level 1/2/3
RACE_TARGET_MONTHLY = 150000  # dollars


def is_test_contact(email, opp_name=""):
    email = (email or "").lower()
    name = (opp_name or "").lower()
    if "+test" in email or "+medtest" in email:
        return True
    if "test" in name:
        return True
    domain = email.split("@")[-1] if "@" in email else ""
    return domain in TEST_DOMAINS


def parse_iso(ts):
    """Parse a GHL/Stripe ISO8601 UTC timestamp into an aware UTC datetime."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def to_la_date(ts):
    """Convert an ISO8601 UTC timestamp (or epoch seconds) to a YYYY-MM-DD date string in LA time."""
    dt = parse_iso(ts)
    if dt is None:
        return None
    return dt.astimezone(LA).date().isoformat()


def load_opportunities(paths):
    """Read one or more raw search-opportunity page dumps, return the flat opportunities list."""
    out = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
        d = raw.get("data", raw)
        opps = d.get("opportunities") or d.get("data", {}).get("opportunities") or []
        out.extend(opps)
    return out


def compute_windows(now_utc):
    """Given the current aware UTC datetime, return LA-local trailing window boundaries.
    Day = today only. Week = trailing 7 days ending today. Month = trailing 30 days
    ending today. Every window is clamped so it never starts before the business launch
    date (confirmed against the source dashboard: on day 25 since launch, its "Monthly"
    view still showed a date range starting at the launch date, not 30 days back).
    AllTime = since the business launch date. All bounds are inclusive date strings
    (YYYY-MM-DD) in America/Los_Angeles. "days" is the actual (possibly clamped) span of
    the window - use NOMINAL_WINDOW_DAYS, not this, for target scaling.
    """
    today = now_utc.astimezone(LA).date()
    launch = datetime.strptime(LAUNCH_DATE, "%Y-%m-%d").date()

    def fmt(d):
        return "{} {}".format(d.strftime("%b"), d.day)

    def trailing(nominal_days):
        start = max(launch, today - timedelta(days=nominal_days - 1))
        return start

    week_start = trailing(7)
    month_start = trailing(30)

    return {
        "day": {"start": today.isoformat(), "end": today.isoformat(),
                "days": 1, "label": "{}, {}".format(today.strftime("%a"), fmt(today))},
        "week": {"start": week_start.isoformat(), "end": today.isoformat(),
                 "days": (today - week_start).days + 1,
                 "label": "{} to {} {}".format(fmt(week_start), fmt(today), today.year)},
        "month": {"start": month_start.isoformat(), "end": today.isoformat(),
                  "days": (today - month_start).days + 1,
                  "label": "{} to {} {}".format(fmt(month_start), fmt(today), today.year)},
        "allTime": {"start": launch.isoformat(), "end": today.isoformat(),
                    "days": (today - launch).days + 1, "label": "Since launch, {}".format(fmt(launch))},
    }


def in_window(date_str, window):
    if date_str is None:
        return False
    return window["start"] <= date_str <= window["end"]


def money(cents):
    return "${:,.2f}".format(cents / 100.0)


def money_round(cents):
    """Whole-dollar money string, matching the source dashboard's rounded display (e.g. '$4,997')."""
    return "${:,.0f}".format(round(cents / 100.0))


def pct(numer, denom):
    if not denom:
        return "awaiting"
    return "{:.0f}%".format(100.0 * numer / denom)


def pct_num(numer, denom):
    """Same as pct() but returns a float (0-100) or None, for sorting/leader picks."""
    if not denom:
        return None
    return 100.0 * numer / denom
