# Stickercast Google Ads Mutation Server

The execution layer of an AI managed Google Ads optimization system. This is a FastAPI service that exposes Google Ads write operations as a clean set of HTTP endpoints, usable both as MCP compatible tools for an interactive agent and as callable endpoints for an automated workflow.

An LLM analyzes campaign performance and decides what to change. This server is what actually applies those changes to the Google Ads account, behind an API key, with a human in the loop approval model for anything that involves money or compliance.

Built on the Google Ads API v24 (Python client).

## What it does

The server wraps Google Ads mutate operations as 28 endpoints across the areas an agent needs to manage a search campaign:

- **Campaigns:** create, update status, update budget, update CPC ceiling, geo target type, ad schedule, mobile bid modifier
- **Ad groups:** create, update status, demographic criterion and bid modifier
- **Keywords:** create (with a two pass policy exemption pattern), pause, update bid, add and remove negatives
- **Ads:** create RSA, update status, update final URL, remove
- **Assets:** call, sitelink, callout, structured snippet, schedules, removal
- **Conversions:** phone call and form submission actions
- **Locations:** location criteria and proximity radius
- **Reporting:** a single stats endpoint that runs nine dimensional queries (daily, device, network, hour, day of week, keywords, search terms, gender, age range)

Every write endpoint is protected by an API key header. Each wraps a Google Ads mutate call and returns a structured result or a surfaced Google Ads error.

## Architecture

The full system design, including the n8n orchestration, the two model LLM pipeline, the two brain memory, and the layered governance model, is documented in [ARCHITECTURE.md](ARCHITECTURE.md).

In short, there are two ways this server is driven:

1. **Interactive (supervised):** an agent in Claude Desktop reads campaign data, proposes changes, and calls these endpoints only after a human approves in the session.
2. **Automated (scheduled):** an n8n workflow runs on a schedule, analyzes each client, and calls these endpoints for the safe action set, routing anything involving money or compliance to a human approval email first.

## Validation

The server was built and refined against a live Google Ads campaign for a real client, which surfaced the Google Ads API v24 field and enum fixes documented inline in the code.

## Setup

See [SETUP.md](SETUP.md) for the full walkthrough: obtaining a developer token, creating an OAuth client, generating a refresh token, building your `google-ads.yaml`, setting the environment variables, and running the server.

Quick version:

```bash
pip install -r requirements.txt
cp google-ads.yaml.example google-ads.yaml   # then fill in your own credentials
cp .env.example .env                          # then set your own API key and yaml path
python -m uvicorn mutation_server:app --port 8001
```

Confirm it is up:

```bash
curl http://localhost:8001/health
curl http://localhost:8001/tools
```

## Security

- All credentials are supplied at runtime through environment variables or a local `google-ads.yaml` that is never committed. Both are listed in `.gitignore`.
- No developer token, OAuth client secret, refresh token, or API key appears anywhere in this repository.
- The API key is read from the `MUTATION_API_KEY` environment variable. Set a strong value before exposing the server beyond localhost.
- Supply your own Google Ads account IDs at request time. None are hardcoded.

## Status

Operational. The interactive mode runs through Claude Desktop, and the automated workflow runs on an hourly schedule. Roadmap items, including a database backed memory store and automated rollback, are listed in ARCHITECTURE.md.


