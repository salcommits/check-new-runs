#!/usr/bin/env python3
"""
weekly_summary.py
-----------------
Airtable Running Club — HyperAgent Skill

Queries the Airtable Activities table for the past 7 days,
computes per-member stats and team totals, generates a celebration
summary with awards, and returns it for HyperAgent to post to Slack.

Schedule: every Monday at 9am via HyperAgent scheduled invocation.

Environment variables required:
  AIRTABLE_API_KEY  - Airtable personal access token
  AIRTABLE_BASE_ID  - ID of the "Running Team" base
"""

import os
from datetime import datetime, timedelta
from collections import defaultdict

from pyairtable import Api

# ── Config ─────────────────────────────────────────────────────────────────────

AIRTABLE_API_KEY = os.environ["AIRTABLE_API_KEY"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_pace(pace_str: str) -> float:
    """Convert 'M:SS /km' string to seconds-per-km float. Returns 0 if unparseable."""
    if not pace_str:
        return 0
    try:
        clean = pace_str.replace(" /km", "").strip()
        mins, secs = clean.split(":")
        return int(mins) * 60 + int(secs)
    except Exception:
        return 0


def format_pace(seconds_per_km: float) -> str:
    if seconds_per_km <= 0:
        return "?"
    mins, secs = divmod(int(seconds_per_km), 60)
    return f"{mins}:{secs:02d} /km"


def podium(position: int) -> str:
    return ["🥇", "🥈", "🥉"][position] if position < 3 else "  "


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    airtable         = Api(AIRTABLE_API_KEY)
    members_table    = airtable.table(AIRTABLE_BASE_ID, "Members")
    activities_table = airtable.table(AIRTABLE_BASE_ID, "Activities")

    # Date range
    today      = datetime.now().date()
    week_start = today - timedelta(days=7)
    week_label = f"{week_start.strftime('%b %d')} – {today.strftime('%b %d, %Y')}"

    # Member ID → name lookup
    members = {
        r["id"]: r["fields"].get("Name", "Unknown")
        for r in members_table.all()
    }

    # Pull and filter activities
    all_activities  = activities_table.all()
    week_activities = [
        a for a in all_activities
        if a["fields"].get("Date", "") >= str(week_start)
    ]

    if not week_activities:
        print(f"No activities logged this week ({week_label}). Time to lace up! 👟")
        return

    # ── Aggregate per member ──────────────────────────────────────────────────

    stats = defaultdict(lambda: {
        "name":           "",
        "runs":           0,
        "distance_km":    0.0,
        "elevation_m":    0.0,
        "best_pace_sec":  0,      # lowest value = fastest
        "longest_run_km": 0.0,
    })

    for activity in week_activities:
        f   = activity["fields"]
        ids = f.get("Member", [])
        if not ids:
            continue
        mid = ids[0]
        s   = stats[mid]

        s["name"]        = members.get(mid, "Unknown")
        s["runs"]        += 1
        s["distance_km"] += f.get("Distance (km)", 0)
        s["elevation_m"] += f.get("Elevation (m)", 0)

        dist = f.get("Distance (km)", 0)
        if dist > s["longest_run_km"]:
            s["longest_run_km"] = dist

        pace_sec = parse_pace(f.get("Pace", ""))
        if pace_sec > 0:
            if s["best_pace_sec"] == 0 or pace_sec < s["best_pace_sec"]:
                s["best_pace_sec"] = pace_sec

    if not stats:
        print("NO_ACTIVITIES_THIS_WEEK")
        return

    # ── Team totals ───────────────────────────────────────────────────────────

    total_km        = sum(s["distance_km"] for s in stats.values())
    total_runs      = sum(s["runs"]        for s in stats.values())
    total_elevation = sum(s["elevation_m"] for s in stats.values())
    total_members   = len(stats)

    # ── Awards ────────────────────────────────────────────────────────────────

    leaderboard      = sorted(stats.values(), key=lambda s: s["distance_km"], reverse=True)
    most_consistent  = max(stats.values(), key=lambda s: s["runs"])
    longest_runner   = max(stats.values(), key=lambda s: s["longest_run_km"])
    elevation_king   = max(stats.values(), key=lambda s: s["elevation_m"])
    pace_eligible    = [s for s in stats.values() if s["best_pace_sec"] > 0]
    fastest          = min(pace_eligible, key=lambda s: s["best_pace_sec"]) if pace_eligible else None

    # ── Build message ─────────────────────────────────────────────────────────

    run_word = "run" if total_runs == 1 else "runs"

    lines = [
        "🏃  *Airtable Running Club — Weekly Wrap*  🏃",
        f"_{week_label}_",
        "",
        (
            f"*{total_members} runners. {total_km:.1f} km. {total_runs} {run_word}.*"
            + (f" {total_elevation:.0f} m of elevation." if total_elevation > 0 else "")
            + " Absolute scenes this week. 🔥"
        ),
        "",
        "*📊 Distance Leaderboard*",
    ]

    for i, runner in enumerate(leaderboard):
        suffix = f"{runner['distance_km']:.1f} km  ·  {runner['runs']} {'run' if runner['runs'] == 1 else 'runs'}"
        lines.append(f"{podium(i)}  *{runner['name']}* — {suffix}")

    lines += [
        "",
        "*🏅 This Week's Awards*",
    ]

    if fastest:
        lines.append(f"⚡  *Fastest Pace* — {fastest['name']}  _{format_pace(fastest['best_pace_sec'])}_")

    lines += [
        f"📏  *Longest Run* — {longest_runner['name']}  _{longest_runner['longest_run_km']:.1f} km_",
        f"📅  *Most Consistent* — {most_consistent['name']}  _{most_consistent['runs']} activities_",
        f"⛰️  *Elevation King* — {elevation_king['name']}  _{elevation_king['elevation_m']:.0f} m climbed_",
        "",
        "_Keep moving Airtable — see you out there next week!_ 🧡",
    ]

    # ── Output for HyperAgent ─────────────────────────────────────────────────

    print("POST_TO_SLACK_CHANNEL: #airtable-running-club")
    print("---")
    print("\n".join(lines))
    print("---")


if __name__ == "__main__":
    main()
