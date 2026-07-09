#!/usr/bin/env python3
# slack_daily.py -- DM the current sales standings to Brodie. Optional. Skips if no token.
# Reads leaderboard.json (already rebuilt by build_leaderboard.py this run).
import os, json, urllib.request

TOKEN = os.environ.get("SLACK_BOT_TOKEN")
RECIPS = [x.strip() for x in os.environ.get("SLACK_RECIPIENTS", "").split(",") if x.strip()]
if not TOKEN or not RECIPS:
    print("slack: no token or recipients, skipping")
    raise SystemExit(0)

d = json.load(open(os.path.dirname(os.path.abspath(__file__)) + "/leaderboard.json"))


def appt(v):
    return "-" if v is None else str(v)


def block(key, title):
    p = d["periods"][key]
    out = [f"*{title}* ({p['window']})"]
    for r in p["reps"]:
        out.append(f"  {r['rank']}. {r['name']}  ${r['cash']:,}  "
                   f"({r['dealsWon']} won, {r['pipelineOwned']} pipeline, {appt(r['apptsBooked'])} booked)")
    return out


m = d["periods"]["monthly"]["team"]
tgt = m.get("target") or d.get("monthlyCashTarget", 150000)
pct = round(m["cash"] / tgt * 100) if tgt else 0
goal = [f"*Monthly goal* ${m['cash']:,} of ${tgt:,} collected  |  {pct}% to goal  |  ${max(0, tgt - m['cash']):,} to go", ""]

lines = ["*AIFS Sales Leaderboard*", ""] + goal
lines += block("monthly", "This Month") + [""]
lines += block("weekly", "This Week") + [""]
lines += block("daily", "Today") + [""]
lines += ["https://jayvee-eaze.github.io/aifs-race-leaderboard/"]
text = "\n".join(lines)


def api(method, payload):
    req = urllib.request.Request("https://slack.com/api/" + method,
                                 data=json.dumps(payload).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN,
                                          "Content-Type": "application/json; charset=utf-8"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())


for uid in RECIPS:
    ch = api("conversations.open", {"users": uid})
    if ch.get("ok"):
        api("chat.postMessage", {"channel": ch["channel"]["id"], "text": text, "unfurl_links": False})
        print("slack: sent to", uid)
    else:
        print("slack: could not open DM with", uid, ch.get("error"))
