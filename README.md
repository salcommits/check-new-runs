# Airtable Running Club — HyperAgent Skills

Skills powering the Airtable Running Club Slack bot.

## Skills

| File | Runs | What it does |
|---|---|---|
| `skills/check_new_runs.py` | Every hour | Polls Strava for all members, posts new activities to Slack |
| `skills/weekly_summary.py` | Monday 9am | Leaderboard + awards post |
| `skills/send_encouragement.py` | Wed 12pm + Fri 4pm | Mid-week hype messages |

## Airtable Schema

**Base:** `Running Team`

**Table: Members**
| Field | Type |
|---|---|
| Name | Single line text |
| Slack User ID | Single line text |
| Strava Athlete ID | Single line text |
| Access Token | Single line text |
| Refresh Token | Single line text |
| Token Expiry | Number (Unix timestamp) |
| Join Date | Date |

**Table: Activities**
| Field | Type |
|---|---|
| Strava Activity ID | Single line text |
| Member | Link to Members |
| Name | Single line text |
| Date | Date |
| Type | Single select |
| Distance (km) | Number |
| Duration (min) | Number |
| Pace | Single line text |
| Elevation (m) | Number |
| Strava URL | URL |

## Environment Variables

```
AIRTABLE_API_KEY
AIRTABLE_BASE_ID
SLACK_BOT_TOKEN
SLACK_CHANNEL_ID
STRAVA_CLIENT_ID
STRAVA_CLIENT_SECRET
```
