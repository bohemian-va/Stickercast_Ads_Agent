# Setup Guide

This walks you through standing up the mutation server against your own Google Ads account. You supply your own credentials throughout. Nothing in this repository contains live secrets.

## Prerequisites

- Python 3.10 or newer
- A Google Ads account and a Google Ads Manager Account (MCC)
- A Google Ads API developer token (applied for in your MCC, under API Center)
- A Google Cloud project with the Google Ads API enabled

## Step 1: Install dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Create an OAuth client

In the Google Cloud console, under APIs and Services, then Credentials, create an OAuth client ID of type Desktop app. Note the client ID and client secret. These authorize your application to call the Google Ads API on your behalf.

## Step 3: Generate a refresh token

Run a one time OAuth flow to exchange your consent for a long lived refresh token. A minimal script:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": "YOUR_CLIENT_ID",
            "client_secret": "YOUR_CLIENT_SECRET",
            "redirect_uris": ["http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    },
    scopes=["https://www.googleapis.com/auth/adwords"],
)
creds = flow.run_local_server(port=0)
print("Refresh token:", creds.refresh_token)
```

Sign in with the Google account that owns the MCC, approve access, and copy the refresh token that prints.

## Step 4: Build your google-ads.yaml

Copy the template and fill in your own values:

```bash
cp google-ads.yaml.example google-ads.yaml
```

```yaml
developer_token: YOUR_DEVELOPER_TOKEN
client_id: YOUR_CLIENT_ID
client_secret: YOUR_CLIENT_SECRET
refresh_token: YOUR_REFRESH_TOKEN
login_customer_id: YOUR_MCC_ID_NO_DASHES
use_proto_plus: True
```

`login_customer_id` is your MCC (manager) account ID with no dashes, so the API acts as the agency managing the client accounts under it.

Keep this file out of version control. It is already in `.gitignore`.

## Step 5: Set environment variables

Copy the template and set your own values:

```bash
cp .env.example .env
```

```
MUTATION_API_KEY=choose-a-strong-secret
GOOGLE_ADS_YAML=/absolute/path/to/google-ads.yaml
```

The server reads `MUTATION_API_KEY` for endpoint protection and `GOOGLE_ADS_YAML` for the credentials file location. If you do not set `GOOGLE_ADS_YAML`, the server looks for `google-ads.yaml` in the working directory.

## Step 6: Run the server

```bash
python -m uvicorn mutation_server:app --port 8001
```

## Step 7: Confirm it works

```bash
curl http://localhost:8001/health
curl http://localhost:8001/tools
```

`/health` returns a status object. `/tools` lists every available endpoint.

Every write endpoint requires the API key header:

```bash
curl -X POST http://localhost:8001/campaigns/update-status \
  -H "X-API-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"YOUR_CLIENT_ID","campaign_id":"YOUR_CAMPAIGN_ID","status":"PAUSED"}'
```

Supply your own account and campaign IDs in the request body. Start against a paused test campaign before touching anything live.

## Notes

- For hosted deployment (for example on Railway), set the same values as environment variables in the host rather than using a yaml file on disk.
- Keep the developer token at the access level Google granted you. A test or basic level token limits which accounts you can operate on.
