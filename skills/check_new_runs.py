#!/usr/bin/env python3
"""
check_new_runs.py
-----------------
Airtable Running Club — HyperAgent Skill

Polls Strava for new activities from every registered member.
Returns formatted Slack messages as output — HyperAgent posts
them to #airtable-running-club via its native Slack integration.
Stores posted activities in Airtable to prevent duplicate posts.

Schedule: run every hour via HyperAgent scheduled invocation.

Environment variables required:
  AIRTABLE_API_KEY       - Airtable personal access token
  AIRTABLE_BASE_ID       - ID of the "Running Team" base
  STRAVA_CLIENT_ID       - Strava app client ID
  STRAVA_CLIENT_SECRET   - Strava app client secret
"""

import os
import time
import json
import requests
from datetime import datetime

from pyairtable import Api

# ── Config ─────────────────────────────────────────────────────────────────────

AIRTABLE_API_KEY     = os.environ["AIRTABLE_API_KEY"]
AIRTABLE_BASE_ID     = os.environ["AIRTABLE_BASE_ID"]
STRAVA_CLIENT_ID     = os.environ["STRAVA_CLIENT_ID"]
STRAVA_CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]

STRAVA_TOKEN_URL     = "https://www.strava.com/oauth/token"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"

# How far back to look for activities (90 min to handle any Strava upload lag)
LOOKBACK_SECONDS = 90 * 60

ACTIVITY_EMOJIS = {
    "Run":           "🏃",
    "Walk":          "🚶",
    "Ride":          "🚴",
    "Swim":          "🏊",
    "Hike":          "🥾",
    "WeightTraining":"🏋️",
    "Workout":       "💪",
    "VirtualRun":    "🏃",
    "VirtualRide":   "🚴",
}


# ── Strava helpers ─────────────────────────────────────────────────────────────

def refresh_token_if_needed(member: dict) -> dict:
    """
    Check whether the member's Strava access token has expired.
    If so, refresh it and return the new token fields to write back to Airtable.
    Returns an empty dict if the existing token is still valid.
    """
    expiry = int(member["fields"].get("Token Expiry", 0))
    # Refresh if within 5 minutes of expiry
    if time.time() < expiry - 300:
        return {}

    print(f"  🔄 Refreshing token for {member['fields'].get('Name', 'unknown')}")
    resp = requests.post(STRAVA_TOKEN_URL, data={
        "client_id":     STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "grant_type":    "refresh_token",
        "refresh_token": member["fields"]["Refresh Token"],
    })
    resp.raise_for_status()
    data = resp.json()
    return {
        "Access Token":  data["access_token"],
        "Refresh Token": data["refresh_token"],
        "Token Expiry":  data["expires_at"],
    }


def get_recent_activities(access_token: str, after_ts: int) -> list:
    """Fetch up to 10 activities from Strava after the given Unix timestamp."""
    resp = requests.get(
        STRAVA_ACTIVITIES_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"after": after_ts, "per_page": 10},
    )
    resp.raise_for_status()
    return resp.json()


# ── Formatting ─────────────────────────────────────────────────────────────────

def format_pace(meters: float, seconds: float) -> str:
    """Convert distance (m) and time (s) to a min/km pace string."""
    if meters < 1:
        return "?"
    pace_sec = (seconds / meters) * 1000
    mins, secs = divmod(int(pace_sec), 60)
    return f"{mins}:{secs:02d} /km"


def format_distance(meters: float) -> str:
    if meters >= 1000:
        return f"{meters / 1000:.2f} km"
    return f"{int(meters)} m"


def format_duration(seconds: float) -> str:
    mins = int(seconds // 60)
    if mins >= 60:
        h, m = divmod(mins, 60)
        return f"{h}h {m}m"
    return f"{mins}m"


def generate_quip(activity: dict) -> str:
    """
    Build a short witty comment based on time of day, distance, and elevation.
    Keeps it celebratory — never negative.
    """
    dist_km = activity["distance"] / 1000
    raw_date = activity.get("start_date_local", "")
    hour = 12  # default
    if raw_date:
        try:
            hour = datetime.fromisoformat(raw_date.replace("Z", "")).hour
        except ValueError:
            pass

    elevation = activity.get("total_elevation_gain", 0)
    parts = []

    # Time of day
    if hour < 6:
        parts.append("Running before the sun comes up — absolute unit. 🌑")
    elif hour < 9:
        parts.append("Early bird gets the miles. 🌅")
    elif hour >= 21:
        parts.append("Night run. Either very dedicated or very behind on steps. 🌙")

    # Distance
    if dist_km >= 42:
        parts.append(f"Marathon distance! {dist_km:.1f} km — someone's a machine. 🏅")
    elif dist_km >= 21:
        parts.append(f"Half marathon! {dist_km:.1f} km — this is not a drill. 🔥")
    elif dist_km >= 10:
        parts.append(f"Double digits — {dist_km:.1f} km on the board. 💪")
    elif dist_km >= 5:
        parts.append(f"Solid {dist_km:.1f} km. The legs are doing their job. ✅")
    else:
        parts.append(f"Every km counts. {dist_km:.1f} km logged. 👟")

    # Elevation bonus
    if elevation >= 300:
        parts.append(f"Plus {elevation:.0f} m of climbing. Showing off. ⛰️")
    elif elevation >= 100:
        parts.append(f"With {elevation:.0f} m of elevation too. Hilly work! ⛰️")

    return "  ".join(parts[:2])


def build_slack_message(name: str, activity: dict) -> str:
    """Assemble the full Slack message block for a new activity."""
    a_type   = activity.get("sport_type") or activity.get("type", "Workout")
    emoji    = ACTIVITY_EMOJIS.get(a_type, "🏃")
    dist     = format_distance(activity["distance"])
    duration = format_duration(activity["moving_time"])
    url      = f"https://www.strava.com/activities/{activity['id']}"
    quip     = generate_quip(activity)

    stats = f"📏 {dist}   ⏱️ {duration}"
    if a_type in ("Run", "Walk", "Hike", "VirtualRun"):
        stats += f"   ⚡ {format_pace(activity['distance'], activity['moving_time'])}"
    elev = activity.get("total_elevation_gain", 0)
    if elev > 10:
        stats += f"   ⛰️ {elev:.0f} m"

    return "\n".join([
        f"{emoji}  *{name}* just logged a {a_type.lower()}!",
        stats,
        f"_{quip}_",
        f"<{url}|View on Strava>",
    ])


# ── Airtable ───────────────────────────────────────────────────────────────────

def get_posted_ids(activities_table) -> set:
    """Return the set of Strava activity IDs already stored in Airtable."""
    records = activities_table.all(fields=["Strava Activity ID"])
    return {
        r["fields"]["Strava Activity ID"]
        for r in records
        if "Strava Activity ID" in r["fields"]
    }


def record_activity(activities_table, member_record_id: str, activity: dict) -> None:
    """Persist a newly-posted activity to Airtable."""
    a_type = activity.get("sport_type") or activity.get("type", "Workout")
    is_run = a_type in ("Run", "Walk", "Hike", "VirtualRun")
    activities_table.create({
        "Strava Activity ID": str(activity["id"]),
        "Member":             [member_record_id],
        "Name":               activity.get("name", ""),
        "Date":               activity["start_date_local"][:10],
        "Type":               a_type,
        "Distance (km)":      round(activity["distance"] / 1000, 3),
        "Duration (min)":     round(activity["moving_time"] / 60, 1),
        "Pace":               format_pace(activity["distance"], activity["moving_time"]) if is_run else "",
        "Elevation (m)":      round(activity.get("total_elevation_gain", 0), 1),
        "Strava URL":         f"https://www.strava.com/activities/{activity['id']}",
    })


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    airtable         = Api(AIRTABLE_API_KEY)
    members_table    = airtable.table(AIRTABLE_BASE_ID, "Members")
    activities_table = airtable.table(AIRTABLE_BASE_ID, "Activities")

    members = members_table.all()
    if not members:
        print("No registered members — nothing to do.")
        return

    print(f"Checking {len(members)} member(s) for new Strava activity...")
    posted_ids = get_posted_ids(activities_table)
    after_ts   = int(time.time()) - LOOKBACK_SECONDS
    new_posts  = 0
    messages   = []

    for member in members:
        fields = member["fields"]
        name   = fields.get("Name", "A teammate")

        # Refresh expired token
        updated = refresh_token_if_needed(member)
        if updated:
            members_table.update(member["id"], updated)
            fields.update(updated)

        if not fields.get("Access Token"):
            print(f"  ⚠️  No access token for {name}, skipping.")
            continue

        try:
            activities = get_recent_activities(fields["Access Token"], after_ts)
        except requests.HTTPError as e:
            print(f"  ⚠️  Strava error for {name}: {e}")
            continue

        for activity in activities:
            strava_id = str(activity["id"])
            if strava_id in posted_ids:
                continue  # already announced

            try:
                message = build_slack_message(name, activity)
                record_activity(activities_table, member["id"], activity)
                posted_ids.add(strava_id)
                messages.append(message)
                new_posts += 1
            except Exception as e:
                print(f"  ❌ Failed to process activity {strava_id} for {name}: {e}")

    if messages:
        # Output for HyperAgent to post via its native Slack integration
        print(f"POST_TO_SLACK_CHANNEL: #airtable-running-club")
        print(f"MESSAGE_COUNT: {len(messages)}")
        print("---")
        for msg in messages:
            print(msg)
            print("---")
    else:
        print("NO_NEW_ACTIVITIES")


if __name__ == "__main__":
    main()
