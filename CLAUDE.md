# Prince Bait — Project Guide

An automated **419 scam-baiting agent** (originally a diploma thesis). It engages advance-fee
email scammers with a believable but perpetually-stalling victim persona to waste their time.
Modernized from GPT-2/TensorFlow to a multi-provider LLM agent with a web console.

> **Anti-fraud tool.** Every identity/financial detail the agent produces is fabricated. It never
> uses real data, never sends money, never meets anyone. Behavior is founded on the 419eater
> baiting methodology (see `agent/agent_core.py` SYSTEM_PROMPT).

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in ANTHROPIC_API_KEY (and others as needed)
ANTHROPIC_API_KEY=... python -m uvicorn app:app --port 8000 --reload
```
Open http://127.0.0.1:8000. DB (`princebait.db`) auto-creates on startup.
`?thread=N` deep-links a thread.

## Architecture

FastAPI backend + single-file plain-HTML/JS frontend. No build step.

```
app.py                    FastAPI: routes + thread orchestration + mail endpoints
agent/
  __init__.py
  agent_core.py           run_agent() agentic loop; SYSTEM_PROMPT (419eater methodology)
  llm_provider.py         LLMProvider ABC + Claude/OpenAI/Ollama; PROVIDER_MODELS, MODEL_LABELS, get_provider()
  tools.py                3 tools + contextvar for thread_id; ALL_TOOLS, TOOL_EXECUTORS, execute_tool()
  fake_personality.py     generate_identity() → generate-random.org; get_details() alias
  classes.py              Identity dataclass (extended), Mail (+uid/folder), Conversation_Thread
  models.py               SQLAlchemy 2.0 ORM: Thread, Persona, Participant, Message, MailAccount
  database.py             SQLAlchemy repo layer (dicts in/out, session_scope) incl. mail-account CRUD
  crypto.py               Fernet encryption for mail secrets at rest (MAIL_ENCRYPTION_KEY)
  mail_provider.py        MailProvider ABC + ImapSmtpProvider / GmailApiProvider / MicrosoftProvider + get_mail_provider()
  mail_presets.py         PRESETS registry (gmail/outlook/yahoo/icloud/proton/zoho/… + custom); list_presets()
  mail_oauth.py           Google + Microsoft OAuth helpers (token bundles, refresh, loopback/web)
  gmail_interface.py      Gmail API wrapper (authorize, get_last_mails_unread, reply_to_mail, add_mail_label); accepts injected service=
  custom_exceptions.py    DuplicateRows (legacy, unused by new code)
templates/index.html      Chat console UI (dark, sidebar + chat + Settings modal + Mail modal)
.env.example              Config template
requirements.txt
```

### Universal mail (multi-provider + SSO)
One `MailProvider` ABC (`fetch_unread`/`send_reply`/`mark_read`/`test_connection`), factory
`get_mail_provider(internal_account)`:
- **`ImapSmtpProvider`** (stdlib imaplib/smtplib) — universal path; plain password/app-password OR
  **XOAUTH2**. IMAP threading uses root Message-ID (References/In-Reply-To) as `Mail.thread_id`; `mark_read` = `\Seen`.
- **`GmailApiProvider`** — Gmail API, creds from the DB account's encrypted token (or legacy token.pickle fallback).
- **`MicrosoftProvider(ImapSmtpProvider)`** — Outlook/M365 via IMAP/SMTP + XOAUTH2 (delegated MSAL, no Graph/admin consent).
Accounts stored in `MailAccount` (DB), secrets **Fernet-encrypted at rest** (`agent/crypto.py`,
key = `MAIL_ENCRYPTION_KEY`). Repo returns **redacted** public dicts (no secrets) to routes;
decrypted internal dicts only for the provider factory. One account is `is_active`; `/process-emails`
uses it. Presets in `mail_presets.py`. OAuth is adaptive: `OAUTH_REDIRECT_MODE=loopback` (local
consent/device-code) or `web` (`OAUTH_BASE_URL` + `/oauth/callback`).

### LLM providers
`get_provider(name, model, **kwargs)` returns Claude / OpenAI / Ollama. All normalize responses to
`{content: [_ContentBlock], stop_reason}` so `agent_core` is provider-agnostic. Claude uses a real
`system` param; others get the prompt prepended. Models + labels in `PROVIDER_MODELS` / `MODEL_LABELS`.
Default: `claude-haiku-4-5` (cheap/fast).

### Tools (extensible — add a schema to `ALL_TOOLS` + an executor to `TOOL_EXECUTORS`)
- `detect_banking_intent` — LLM self-classifies whether the email requests financial details.
- `get_fake_identity` — fabricated persona + fake IBAN via generate-random.org.
- `generate_character` — spawns an ADDITIONAL side-character (lawyer, bank manager…) mid-convo;
  persisted + linked to the thread. Reaches the current `thread_id` via a `contextvars.ContextVar`
  (`set_tool_context`/`reset_tool_context`), so executor signatures stay `(input_data) -> dict`.

### Database (SQLAlchemy — light local, scales to prod)
`DATABASE_URL` env: `sqlite:///princebait.db` (default) or `postgresql+psycopg://…` (prod) — same code.
- **Thread**: external_thread_id (Gmail, nullable), identity_mode (real|fake), subject, timestamps
- **Persona**: full Identity fields + role + source (generated|real), FK thread
- **Participant**: roles/connections — persona_id OR scammer_email + role + connection_type (primary|side_character|contact)
- **Message**: direction (incoming|outgoing), body, seq (per-thread order), sender_persona_id
- Repo functions return plain dicts (sessions close → no DetachedInstanceError).

### Identity modes (real/fake/ask)
Set via `IDENTITY_MODE` env or the UI toggle.
- **fake** — full generated persona.
- **real** — only user_name/user_email; never fabricates financials.
- **ask** — UI prompts real-vs-fake per new thread; resolved to real|fake before thread creation
  (never stored as "ask").

## Key endpoints (`app.py`)
- `POST /chat` — `{message, provider, model, api_key?, ollama_url?, thread_id?, identity_mode?, user_name?, user_email?, locale?}`. Creates/loads thread, persists in+out messages, runs agent with history + context. Returns reply, tools_called, banking_intent, characters_created, thread_id, primary_persona.
- `GET /config` — providers, model_labels, identity_modes, locales, defaults, `oauth_redirect_mode`, `encryption_configured`, `has_active_mail_account`.
- `GET /threads` / `GET /threads/{id}` / `POST /threads` — thread list / full detail / pre-create.
- `POST /process-emails` — uses the **active mail account** (any provider); bait each unread, reply, mark read. 400 if no active account (legacy token.pickle fallback if present).
- **Mail**: `GET /mail/presets`, `GET /mail/accounts` (redacted), `POST /mail/accounts` (create IMAP/SMTP or preset; encrypts secret), `POST /mail/accounts/{id}/test`, `POST /mail/accounts/{id}/activate`, `DELETE /mail/accounts/{id}`.
- **OAuth (SSO)**: `GET /mail/oauth/start?provider=gmail|microsoft` (loopback: completes inline; web: returns `auth_url`), `GET /oauth/callback`.

## UI (`templates/index.html`)
Single file, no framework. Dark design system (Inter + JetBrains Mono), layered surfaces,
indigo/violet brand, red=scammer / blue=agent bubbles with avatars, typing indicator, thread
sidebar, personas panel, **Settings modal** (provider tabs + API key fields + identity toggle +
locale) and **Mail modal** (accounts list with Activate/Test/Delete; add via Preset / Custom
IMAP/SMTP / SSO buttons). LLM settings persist in `localStorage` (`princebait_settings`), sent
per-request with `.env` fallback. **Mail accounts are server-backed (encrypted DB), never
localStorage**; password inputs are write-only.

## Conventions & guardrails
- **Secrets**: `.gitignore` covers `.env`, `credentials.json`, `token.pickle`, `*.db`, model weights.
  Never commit secrets. LLM keys come from env or UI; mail secrets are Fernet-encrypted in the DB
  (`MAIL_ENCRYPTION_KEY`) and never returned to the client.
- **Git**: do NOT commit or push unless the user explicitly asks (standing instruction).
- Old top-level files (`main.py`, `database_interface.py`, `gpt-2/`, etc.) were deleted in the
  modernization; the live code is the `agent/` package.
- ⚠️ Historical exposure: `credentials.json`/`token.pickle` remain in old git history on the public
  repo — those Google OAuth credentials should be rotated.

## Status / roadmap
- ✅ Multi-provider LLM + tool calling; FastAPI + chat UI
- ✅ SQLAlchemy threads / personas / participants / history
- ✅ Identity generation (generate-random.org) + real/fake/ask
- ✅ generate_character side-characters
- ✅ 419eater-based behavior prompt
- ✅ UI visual redesign
- ✅ Universal mail connections: IMAP/SMTP + Gmail/Microsoft SSO + presets, encrypted DB storage, Mail menu
- ✅ Inbox panel: unread mail list, click-to-preview, Bait in Chat, Send by Mail; badge count
- 🔜 Expanding on the baiting methodology (planned)

---
_Keep this file current: update the Architecture, endpoints, or Status sections whenever the
corresponding code changes._
