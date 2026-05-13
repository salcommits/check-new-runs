// api/strava_callback.js
// ----------------------
// Airtable Running Club — Strava OAuth Callback
//
// Vercel serverless function. Strava redirects here after a user authorises
// the app. This function:
//   1. Exchanges the auth code for Strava access + refresh tokens
//   2. Fetches the athlete's profile from Strava
//   3. Writes the new member record to Airtable
//   4. POSTs to the HyperAgent webhook to trigger the Slack welcome message
//   5. Returns a friendly HTML confirmation page to the user
//
// Environment variables (set in Vercel project settings):
//   STRAVA_CLIENT_ID       - Strava app client ID
//   STRAVA_CLIENT_SECRET   - Strava app client secret
//   AIRTABLE_API_KEY       - Airtable PAT with data.records:write
//   AIRTABLE_BASE_ID       - Running Club base ID (appkyz7mLDeMl0OK0)
//   HYPERAGENT_WEBHOOK_URL     - HyperAgent webhook URL for the welcome trigger
//   HYPERAGENT_WEBHOOK_SECRET  - Must match webhook receiver; sent as X-Hyperagent-Webhook-Secret

const STRAVA_TOKEN_URL   = "https://www.strava.com/oauth/token";
const STRAVA_ATHLETE_URL = "https://www.strava.com/api/v3/athlete";
const AIRTABLE_URL       = `https://api.airtable.com/v0/${process.env.AIRTABLE_BASE_ID}/Members`;

// ── Helpers ───────────────────────────────────────────────────────────────────

async function exchangeCode(code) {
  const res = await fetch(STRAVA_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id:     process.env.STRAVA_CLIENT_ID,
      client_secret: process.env.STRAVA_CLIENT_SECRET,
      code,
      grant_type: "authorization_code",
    }),
  });
  if (!res.ok) throw new Error(`Strava token exchange failed: ${res.status}`);
  return res.json();
}

async function writeToAirtable(member) {
  const res = await fetch(AIRTABLE_URL, {
    method: "POST",
    headers: {
      Authorization:  `Bearer ${process.env.AIRTABLE_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ fields: member }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Airtable write failed: ${err}`);
  }
  return res.json();
}

async function triggerWelcome(name, slackUserId) {
  const webhookUrl = process.env.HYPERAGENT_WEBHOOK_URL;
  if (!webhookUrl) return; // skip if not configured yet
  await fetch(webhookUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Hyperagent-Webhook-Secret": process.env.HYPERAGENT_WEBHOOK_SECRET,
    },
    body: JSON.stringify({
      message: `New runner registered. Post this welcome message to #airtable-running-club in Slack: "🎉 ${name} just joined the Airtable Running Club! Welcome to the team! 🏃"`,
      slackUserId,
    }),
  });
}

// ── Success page ──────────────────────────────────────────────────────────────

function successPage(name) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>You're in! — Airtable Running Club</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f97316;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
    }
    .card {
      background: rgba(0,0,0,0.15);
      border-radius: 24px;
      padding: 48px 40px;
      text-align: center;
      max-width: 420px;
      width: 90%;
    }
    .emoji { font-size: 64px; margin-bottom: 24px; }
    h1 { font-size: 28px; font-weight: 700; margin-bottom: 12px; }
    p  { font-size: 17px; opacity: 0.9; line-height: 1.5; }
    .sub { margin-top: 24px; font-size: 14px; opacity: 0.7; }
  </style>
</head>
<body>
  <div class="card">
    <div class="emoji">🏃</div>
    <h1>You're in, ${name}!</h1>
    <p>Welcome to the Airtable Running Club.<br/>Your Strava is connected and your runs will start appearing in Slack.</p>
    <p class="sub">You can close this tab now.</p>
  </div>
</body>
</html>`;
}

function errorPage(message) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Something went wrong</title>
  <style>
    body { font-family: sans-serif; display:flex; align-items:center; justify-content:center; min-height:100vh; background:#1a1a1a; color:white; }
    .card { text-align:center; padding:40px; }
    h1 { font-size:24px; margin-bottom:12px; }
    p { opacity:0.7; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Something went wrong 😬</h1>
    <p>${message}</p>
    <p style="margin-top:16px">Head back to Slack and try <strong>@Hyperagent register</strong> again.</p>
  </div>
</body>
</html>`;
}

// ── Handler ───────────────────────────────────────────────────────────────────

export default async function handler(req, res) {
  const { code, state: slackUserId, error } = req.query;

  // User denied access on Strava
  if (error) {
    return res
      .status(400)
      .setHeader("Content-Type", "text/html")
      .send(errorPage("You denied access to Strava."));
  }

  if (!code) {
    return res
      .status(400)
      .setHeader("Content-Type", "text/html")
      .send(errorPage("No authorisation code received from Strava."));
  }

  try {
    // 1. Exchange code for tokens
    const tokenData = await exchangeCode(code);
    const athlete   = tokenData.athlete;
    const name      = `${athlete.firstname} ${athlete.lastname}`.trim();

    // 2. Write member to Airtable
    await writeToAirtable({
      "Name":              name,
      "Slack User ID":     slackUserId || "",
      "Strava Athlete ID": String(athlete.id),
      "Access Token":      tokenData.access_token,
      "Refresh Token":     tokenData.refresh_token,
      "Token Expiry":      tokenData.expires_at,
      "Join Date":         new Date().toISOString().split("T")[0],
    });

    // 3. Trigger HyperAgent welcome message in Slack
    await triggerWelcome(name, slackUserId);

    // 4. Show success page
    return res
      .status(200)
      .setHeader("Content-Type", "text/html")
      .send(successPage(name));

  } catch (err) {
    console.error("OAuth callback error:", err);
    return res
      .status(500)
      .setHeader("Content-Type", "text/html")
      .send(errorPage("Registration failed. Please try again."));
  }
}
