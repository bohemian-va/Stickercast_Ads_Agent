# Stickercast Architecture: n8n + Google Sheets + Railway

## Production System Overview

Stickercast is an AI managed Google Ads service for local businesses. This document describes the production architecture: an event driven orchestration that runs on a schedule, analyzes campaign performance with a two model LLM pipeline, applies a layered governance model, and executes safe optimizations autonomously while routing anything involving money or compliance to a human for approval.

**Status:** operational. The n8n workflow runs on an hourly schedule, the FastAPI mutation service runs on Railway, the two brain memory reads and writes on every cycle, and the governance router enforces the human approval boundary.

Identifiers in this document (account IDs, service account, hosted URL, email addresses) are shown as placeholders. Supply your own in a local configuration that is never committed.

---

## 1. High Level Component Map

```
┌──────────────────────────────────────────────────────────────────────────┐
│              STICKERCAST PRODUCTION SYSTEM (hourly schedule)             │
│        Orchestrated · Autonomous · Multi Client · Cloud Hosted           │
└──────────────────────────────────────────────────────────────────────────┘

ORCHESTRATION TIER (n8n)
┌───────────────────────────────────────────────────────────────┐
│  Workflow: StickerCast Hourly Agent                           │
│                                                               │
│  [1] Schedule Trigger (hourly)                               │
│       ↓                                                       │
│  [2] Google Sheets READ: client roster                       │
│       Columns: client_name, customer_id, campaign_id,        │
│       business_category, city, monitoring_tier, active       │
│       ↓ (one row per active client)                          │
│  [3] Google Sheets READ: Client Memory (per customer_id)     │
│       Past decisions, baselines, budget history, notes       │
│       ↓                                                       │
│  [4] Google Sheets READ: Market Memory (category + city)     │
│       Keyword patterns, seasonal trends, CPC benchmarks      │
│       ↓                                                       │
│  [5] HTTP Request: GET FastAPI /campaigns/stats              │
│       Params: customer_id, campaign_id, period               │
│       Returns: 9 dimensions of performance data              │
│       ↓                                                       │
│  [6] AI Agent / Haiku: Data formatter                        │
│       Converts raw JSON to readable text (no analysis)       │
│       ↓                                                       │
│  [7] AI Agent / Opus: Analyst + decision maker               │
│       Full analysis + structured JSON decision               │
│       Context: campaign data + client memory + market memory │
│       ↓                                                       │
│  [8] IF node: 4 conditions                                   │
│       action_needed = true                                   │
│       AND involves_money = false                             │
│       AND compliance_flagged = false                         │
│       AND has_pending_approvals = false                      │
│       ↓                                                       │
│    ┌──── TRUE branch (autonomous) ────────┐                  │
│    │ [9a] Code node (JS):                   │                │
│    │  Parse Opus JSON, split actions        │                │
│    │       ↓                                 │                │
│    │ [10a] HTTP Request: POST FastAPI        │                │
│    │  + action_type path                     │                │
│    │  Executes the safe action set           │                │
│    │  (preflight passed negatives + pauses)  │                │
│    └─────────────────────────────────────────┘               │
│    ┌──── FALSE branch (human review) ──────┐                 │
│    │ [9b] Send message + wait:              │                 │
│    │  SMTP approval email                   │                 │
│    │  <notifications@domain> →              │                 │
│    │  <approvals@domain>                    │                 │
│    │       ↓                                 │                │
│    │  Human replies approve/reject           │                │
│    └─────────────────────────────────────────┘               │
│       ↓                                                       │
│  [11] Google Sheets WRITE: Client Memory                     │
│       Append outcome, decision, date                         │
│       ↓                                                       │
│  [12] Google Sheets WRITE: Market Memory                     │
│       Update market signals (what worked this cycle)         │
└───────────────────────────────────────────────────────────────┘
         ↓ (HTTPS over the internet, API key auth)

EXECUTION TIER (Railway, always on)
┌───────────────────────────────────────────────────────────────┐
│  FastAPI Mutation Server                                      │
│  Hosted on Railway, exposed over HTTPS                        │
│  Credentials from environment variables                      │
│                                                               │
│  Read endpoint:  GET /campaigns/stats                        │
│  Write endpoints: 28 mutation endpoints                      │
│    /keywords/add-negative, /keywords/update-status,          │
│    /campaigns/update-budget, /ads/update-status, etc.        │
└───────────────────────────────────────────────────────────────┘
         ↓ (HTTPS + OAuth2)

GOOGLE CLOUD TIER
┌───────────────────────────────────────────────────────────────┐
│  Google Ads API v24                                           │
│  MCC: <MCC_ID> → Client: <CLIENT_ACCOUNT_ID> → + more clients │
│                                                               │
│  Service account for Sheets: <service-account>@<project>...   │
│  OAuth2 for Ads API: developer token + client secret         │
└───────────────────────────────────────────────────────────────┘

SUPERVISORY TIER (Claude Desktop, on demand)
┌───────────────────────────────────────────────────────────────┐
│  Claude Desktop agent                                        │
│  Role: supervisor, not operator                              │
│  - Investigates anomalies the workflow flags                 │
│  - Builds new campaigns for new clients                      │
│  - Handles complex changes outside the hourly loop           │
│  - Reviews and tunes the Opus prompt                         │
└───────────────────────────────────────────────────────────────┘
```

---

## 2. Architectural Design Patterns

### 2.1 Pipeline / Pipes and Filters (the n8n node chain)

Data flows through a linear chain of nodes. Each node transforms the data and passes it forward: read clients, read memory, fetch stats, format, analyze, route, execute, write back. The chain runs end to end on every trigger.

Rationale:
- Each node has a single responsibility
- Output is inspectable at any stage, so debugging is visual
- Nodes can be reordered or swapped without rewriting the system
- Failures isolate to one node rather than the whole pipeline

### 2.2 Two Stage LLM (Haiku formatter, then Opus analyst)

Raw Google Ads JSON is nested and verbose. Haiku formats it into clean readable text first. Opus then reasons on the clean input. Both calls run inside every cycle.

Rationale:
- Cost efficiency: the cheap model handles mechanical formatting so the expensive model spends its tokens on reasoning rather than parsing
- Quality: reasoning is more reliable on clean, labeled input than on raw nested JSON
- Separation of concerns: formatting logic is isolated from analysis logic

### 2.3 Two Brain Memory (Google Sheets)

Two memory stores give the agent context beyond the current snapshot. Both are read at the start of every cycle and written at the end.

- **Client Memory** (keyed by customer_id): past decisions, performance baselines, budget history, client specific rules
- **Market Memory** (keyed by business_category + city): keyword patterns, seasonal trends, competitor intelligence, cross client learnings for the segment

Rationale:
- Without memory the agent re-decides from scratch every cycle
- Client memory prevents repeating rejected decisions
- Market memory lets a learning from one client in a market benefit the next client in the same market
- Sheets is a zero cost, human readable store that can be inspected directly

Trade off: Google Sheets is not a transactional database. Concurrent writes can conflict, there is no transaction safety, and performance degrades past a few thousand rows. The planned migration is PostgreSQL once client count grows.

### 2.4 Router (the IF node with 4 conditions)

After Opus decides, the IF node routes to one of two branches on four boolean conditions. All four must be true for autonomous execution; any false sends the batch to human approval.

```
action_needed = true
AND involves_money = false
AND compliance_flagged = false
AND has_pending_approvals = false
   ↓
TRUE  → autonomous execution branch
FALSE → human approval email branch
```

Rationale:
- Governance is enforced in the orchestration layer, not only in the prompt
- Even if the model proposes something risky, the router physically stops it from auto executing
- Defense in depth: prompt rules and router rules both have to pass

### 2.5 Approval Queue (SMTP send and wait)

When the router sends to the human branch, n8n emails a plain English summary and pauses that execution until the reply arrives. Approval is asynchronous: the human does not have to be present at the moment of decision.

Rationale:
- Decouples decision time from approval time
- Scales beyond one person (approvals can go to a shared inbox)
- Produces an email record of every approval

### 2.6 Staged Autonomy with a Kill Switch

The autonomous execution node went through a deliberate rollout. It first ran in supervised shadow mode: the full workflow executed (reads, analysis, decision, memory writes, approval emails) while the final mutation node stayed disconnected, so the agent's decisions could be observed without being applied. Once the decisions proved sound, the node was connected and now executes the safe action set. The connection remains a single point kill switch: disconnecting it reverts the system to observe and advise while everything else keeps running.

Rationale:
- Autonomy is earned by observation rather than assumed
- The safe action set is deliberately narrow (negatives and pauses that pass four preflight checks); anything with financial or compliance weight routes to a human
- The kill switch pauses autonomy instantly without taking the system down

### 2.7 Service Layer (FastAPI as a shared backend)

The same FastAPI codebase runs on Railway, reading credentials from environment variables. Both the n8n workflow and the Claude Desktop supervisor call the same endpoints.

Rationale:
- One mutation layer serves both the autonomous workflow and the human supervisor
- No duplicated Google Ads logic
- Credential handling is centralized

---

## 3. System State and Governance (Human in the Loop)

### 3.1 Where State Lives

| Store | Role | Persistence |
|---|---|---|
| Google Sheets (client roster) | Which clients are active, their tier | Durable |
| Google Sheets (Client Memory) | Per account decision history | Durable, written each cycle |
| Google Sheets (Market Memory) | Per segment intelligence | Durable, written each cycle |
| n8n execution log | Every workflow run, every node output | Durable |
| Email inbox | Approval requests and responses | Durable |
| Google Ads account | Source of truth for live state | Durable |
| Railway logs | FastAPI request and response records | Rolling |

State is durable and queryable. A question like "what did the agent do to a given client last week" is answered by reading the memory sheet and the n8n execution log.

### 3.2 Governance Flow

```
Opus produces decision JSON:
{
  "action_needed": true,
  "involves_money": false,
  "compliance_flagged": false,
  "has_pending_approvals": false,
  "actions": [{negative keyword that passed all 4 preflight checks}],
  "flagged_for_approval": [],
  "rationale": "...",
  "human_message": "..."
}
        ↓
IF node evaluates the 4 booleans
        ↓
All true → autonomous branch → execution node → mutation runs
Any false → email branch → human approves → then execute
        ↓
Outcome written to Client Memory + Market Memory
```

### 3.3 Four Layer Safety Model

A mutation that touches money or compliance has to survive four independent layers before it can execute:

1. **Prompt guardrails (Opus):** a four check preflight system for negative keywords, a medical term blocklist, and a conversion data reliability gate. The model flags anything uncertain.
2. **Self flagging rule (Opus):** if anything is flagged for approval, the model sets involves_money to true, which forces the whole batch to the human branch. No partial autonomy when money is in play.
3. **Router enforcement (n8n IF node):** even if the prompt failed, the four condition router blocks money and compliance mutations from the autonomous branch.
4. **Kill switch (execution node):** the autonomous branch can be disconnected, reverting the system to observe and advise while everything else keeps running.

### 3.4 Compliance as Code

For health sector clients, the Opus prompt checks ad copy against provincial regulatory advertising standards (for example CPSA in Alberta): it flags unsubstantiated outcome claims, unverifiable superlatives, testimonials, and misleading availability claims. For non health clients, compliance_flagged is set to false automatically. The check runs every cycle, on every client, and is documented in the rationale field of each decision.

---

## 4. Security and Authentication Model

### 4.1 FastAPI Endpoint Protection

Every request includes an API key header; the key is held in an environment variable, not in code.

```
POST https://<your-app>.railway.app/keywords/add-negative
Header: X-API-Key: <from environment variable>
Body: {mutation JSON}
```

Transport is HTTPS, so traffic between n8n and FastAPI is encrypted in transit.

### 4.2 Credential Handling

Credentials are injected as environment variables and read through os.environ. No secrets touch disk, and no secrets live in the repository.

```
GOOGLE_ADS_DEVELOPER_TOKEN
GOOGLE_ADS_LOGIN_CUSTOMER_ID
GOOGLE_ADS_CLIENT_ID
GOOGLE_ADS_CLIENT_SECRET
STICKERCAST_API_KEY
GOOGLE_ADS_SERVICE_ACCOUNT_JSON
```

For local development the same values live in a google-ads.yaml file kept outside the repository and never committed.

### 4.3 Three Identity Boundaries

1. **n8n to FastAPI:** API key (shared secret). Authorizes the workflow to request mutations.
2. **FastAPI to Google Ads:** OAuth2 (client ID, client secret, refresh token) plus a developer token. Authorizes mutations against the ad accounts.
3. **n8n to Google Sheets:** a service account scoped to the memory and roster sheets only.

Each boundary has its own credential. A compromise of one does not grant the others.

### 4.4 SMTP Identity

Approval emails are sent from a dedicated sending address and received at a separate approvals address, so approval traffic is separable and auditable.

### 4.5 Remaining Hardening

- The API key is a static shared secret; request signing (HMAC) would be stronger.
- Google Sheets as a store has no row level access control.
- There is no rate limiting at the FastAPI layer yet; it relies on Google's limits.
- Environment variable secrets are good; a dedicated secrets manager with rotation is the enterprise grade target.

---

## 5. Key Bottlenecks and Failure Modes

### 5.1 Google Sheets as a Database
Both memory brains and the roster live in Sheets. Concurrent writes from overlapping runs can overwrite each other (no locking), there are no transactions, performance degrades past a few thousand rows, and the Sheets API has its own quota. The binding constraint arrives around 20 to 30 active clients on an hourly cadence. Fix: migrate the brains and roster to PostgreSQL and keep a read only Sheets mirror for visibility.

### 5.2 Single Linear Workflow (no per client isolation)
One workflow processes all clients in sequence, so a malformed row or a slow API response for one client can delay or halt the rest of that cycle. Fix: per client sub workflows triggered in parallel, or error branches that catch and continue.

### 5.3 LLM Output Reliability (JSON parsing)
The autonomous branch depends on the model returning valid JSON in the exact schema, which the Code node parses. Risks are stray text around the JSON, a malformed field, or a hallucinated action_type. The prompt is strict about format, which mitigates this. Fix: add a JSON schema validation node between the model and the parser, and on a parse failure route to the human branch rather than silently dropping the cycle.

### 5.4 Context Window and Memory Growth
As client and market memory accumulate, the context injected into the model grows, which crowds out current campaign data and raises token cost per cycle. Fix: a periodic job that condenses raw history into a compact state, storing full history in the database and injecting only a summarized view.

### 5.5 Google Ads API Rate Limits at Scale
Limits are 60,000 queries and 6,000 mutations per day per MCC. Hourly cycles multiply fast as clients are added, and the stats endpoint pulls nine dimensions per client per cycle. Fix: batch mutations where the API allows, move lower tier clients to a weekly workflow, and cache the stats pull so one read serves both the formatter and the analyst.

### 5.6 The SMTP Approval Dependency
Human approvals depend on email delivery and the send and wait node holding state. An approval email in spam leaves the run waiting, a slow reply can time the execution out, and free text replies can be misparsed. Fix: a timeout with a safe default (no action, escalate), a structured approval link or button instead of free text parsing, and a log of every pending approval.

### 5.7 Railway as a Single Point of Execution
All mutations route through one service, so downtime stops mutations, a bad deploy breaks every client at once, and cold starts add latency. Fix: health check monitoring with alerting, a staging environment to test deploys, and keeping the instance warm given the hourly cadence.

### 5.8 No Rollback Mechanism Yet
Mutations are forward only. A wrongly paused keyword stays paused until a human notices, and a negative keyword that slipped through blocks traffic silently (the failure the preflight system is built to prevent, though no system is perfect). Fix: log the inverse of every mutation (pause has an unpause, add negative has a remove negative) and build a one click rollback that replays inverses. The remove endpoints already exist; the missing piece is automated inverse logging.

---

## 6. Design Rationale (Mechanism to Value)

| Technical Mechanism | Purpose |
|---|---|
| Scheduled trigger (hourly) | Continuous optimization without human presence |
| Two stage LLM (Haiku then Opus) | Cost control at scale; premium reasoning only where it matters |
| Two brain memory | Intelligence that compounds per market over time |
| Four condition router | Structural guarantee that money and compliance need a human |
| Approval queue (SMTP) | Asynchronous human control that scales past one operator |
| Staged autonomy + kill switch | Autonomy that is earned, narrow, and reversible |
| Compliance as code | Every client checked every cycle; documented in each decision |
| Environment variable credentials | No secrets on disk or in the repository |
| Memory write back | Auditable decision history |

---

## 7. Current Status and Roadmap

**Operational today:**
- The hourly workflow runs on schedule
- Reads, two stage analysis, decision, routing, and memory write back run each cycle
- The autonomous branch executes the safe action set
- The four layer governance model is active, so money and compliance route to a human
- Credentials run from environment variables
- The two brain memory accumulates per client and per market

**Roadmap:**
- Migrate memory from Google Sheets to PostgreSQL (the first scaling constraint)
- Add automated rollback with inverse logging
- Add per client error isolation in the workflow
- Build the weekly workflow for lower tier clients
- Add a JSON schema validation gate before the parser

---

## 8. Related Components

- **FastAPI mutation server:** the execution backend described above. Read endpoint plus 28 mutation endpoints wrapping Google Ads API v24 mutate calls.
- **Read path (Google Ads MCP):** a read only Model Context Protocol server for GAQL queries, used by the Claude Desktop supervisor.
- **Local supervised mode:** the same mutation backend can be driven interactively from Claude Desktop, with every mutation approved in a live session. This is the lower autonomy counterpart to the scheduled production system described here.
