import os
import re
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from agent.llm_provider import get_provider, PROVIDER_MODELS, MODEL_LABELS
from agent.agent_core import run_agent
from agent.classes import Identity
from agent.fake_personality import generate_identity
from agent import database as db
from agent import crypto, mail_presets
from agent.mail_provider import get_mail_provider

app = FastAPI(title="419 Scam Baiter Agent")
templates = Jinja2Templates(directory="templates")

_DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "claude")
_DEFAULT_MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5")
_DEFAULT_IDENTITY_MODE = os.getenv("IDENTITY_MODE", "fake")
_DEFAULT_LOCALE = os.getenv("IDENTITY_LOCALE", "en_US")
_LOCALES = ["en_US", "fr_FR", "es_ES", "it_IT", "de_DE", "pt_PT", "nl_NL", "pl_PL"]
_OAUTH_REDIRECT_MODE = os.getenv("OAUTH_REDIRECT_MODE", "loopback")


@app.on_event("startup")
def _startup():
    db.init_db()


# ── Helpers ───────────────────────────────────────────────────────────────

def _provider_from(provider_name, model, api_key=None, ollama_url=None):
    extra = {}
    if provider_name == "claude":
        extra["api_key"] = api_key or os.getenv("ANTHROPIC_API_KEY")
    elif provider_name == "openai":
        extra["api_key"] = api_key or os.getenv("OPENAI_API_KEY")
    elif provider_name == "ollama":
        extra["base_url"] = ollama_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    return get_provider(provider_name, model, **extra)


def _display_name_from_email(addr: str) -> str:
    """Extract a display name from a 'Name <email>' header, if present."""
    if not addr:
        return ""
    m = re.match(r'\s*"?([^"<]+?)"?\s*<', addr)
    if m:
        return m.group(1).strip()
    return ""


def _build_primary_persona(thread_id, mode, locale, user_name="", user_email="",
                           scammer_from=""):
    """Create the thread's primary (victim) persona according to identity mode."""
    if mode == "real":
        name = (user_name or _display_name_from_email(scammer_from) or "").strip()
        identity = Identity(name=name, email=(user_email or "").strip())
        source = "real"
    else:  # fake
        identity = generate_identity(locale=locale)
        # attach the locale so it gets persisted
        setattr(identity, "locale", locale)
        source = "generated"

    persona = db.create_persona(thread_id, identity, role="victim", source=source)
    db.add_participant(thread_id, persona_id=persona["id"], role="victim",
                       connection_type="primary")
    return persona


def _history_for_agent(thread_id) -> list[dict]:
    """Convert stored messages into agent conversation history."""
    history = []
    for m in db.get_messages(thread_id):
        role = "user" if m["direction"] == "incoming" else "assistant"
        history.append({"role": role, "content": m["body"]})
    return history


# ── Models ────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    provider: str = _DEFAULT_PROVIDER
    model: str = _DEFAULT_MODEL
    api_key: str | None = None
    ollama_url: str | None = None
    # Thread + identity
    thread_id: int | None = None
    identity_mode: str | None = None  # resolved real|fake (never "ask")
    user_name: str | None = None
    user_email: str | None = None
    locale: str | None = None


class ThreadCreateRequest(BaseModel):
    identity_mode: str | None = None
    user_name: str | None = None
    user_email: str | None = None
    locale: str | None = None
    subject: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        provider = _provider_from(req.provider, req.model, req.api_key, req.ollama_url)
        locale = req.locale or _DEFAULT_LOCALE

        # Resolve or create the thread
        if req.thread_id is None:
            mode = req.identity_mode or _DEFAULT_IDENTITY_MODE
            if mode == "ask":
                mode = "fake"  # safety fallback; UI should resolve before sending
            subject = req.message.strip().splitlines()[0][:60] if req.message.strip() else None
            thread = db.create_thread(mode, subject=subject)
            thread_id = thread["id"]
            _build_primary_persona(
                thread_id, mode, locale,
                user_name=req.user_name or "", user_email=req.user_email or "",
            )
        else:
            thread = db.get_thread(req.thread_id)
            if thread is None:
                raise HTTPException(status_code=404, detail="Thread not found")
            thread_id = thread["id"]
            mode = thread["identity_mode"]

        # History BEFORE we add the new incoming message
        history = _history_for_agent(thread_id)

        db.add_message(thread_id, "incoming", req.message)
        primary = db.get_primary_persona(thread_id)

        result = run_agent(
            req.message, provider,
            context={"thread_id": thread_id},
            history=history,
        )

        db.add_message(thread_id, "outgoing", result["reply"],
                       sender_persona_id=(primary["id"] if primary else None))

        return JSONResponse({
            "reply": result["reply"],
            "tools_called": result["tools_called"],
            "banking_intent": result["banking_intent"],
            "fake_identity": result["fake_identity"],
            "characters_created": result["characters_created"],
            "thread_id": thread_id,
            "identity_mode": mode,
            "primary_persona": primary,
            "provider": req.provider,
            "model": req.model,
        })
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/config")
async def config():
    return JSONResponse({
        "providers": PROVIDER_MODELS,
        "model_labels": MODEL_LABELS,
        "default_provider": _DEFAULT_PROVIDER,
        "default_model": _DEFAULT_MODEL,
        "identity_modes": ["real", "fake", "ask"],
        "identity_locales": _LOCALES,
        "default_identity_mode": _DEFAULT_IDENTITY_MODE,
        "default_locale": _DEFAULT_LOCALE,
        "oauth_redirect_mode": _OAUTH_REDIRECT_MODE,
        "encryption_configured": crypto.encryption_configured(),
        "has_active_mail_account": db.get_active_mail_account() is not None,
    })


@app.get("/threads")
async def list_threads():
    return JSONResponse(db.list_threads())


@app.get("/threads/{thread_id}")
async def get_thread(thread_id: int):
    thread = db.get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return JSONResponse({
        "thread": thread,
        "messages": db.get_messages(thread_id),
        "personas": db.get_personas(thread_id),
        "participants": db.get_participants(thread_id),
    })


@app.post("/threads")
async def create_thread(req: ThreadCreateRequest):
    mode = req.identity_mode or _DEFAULT_IDENTITY_MODE
    if mode == "ask":
        mode = "fake"
    locale = req.locale or _DEFAULT_LOCALE
    thread = db.create_thread(mode, subject=req.subject)
    persona = _build_primary_persona(
        thread["id"], mode, locale,
        user_name=req.user_name or "", user_email=req.user_email or "",
    )
    return JSONResponse({"thread": thread, "primary_persona": persona})


@app.post("/process-emails")
async def process_emails():
    try:
        # Resolve the active mail account → provider. Fall back to legacy Gmail
        # (env/token.pickle) if none is configured but the pickle exists.
        account = db.get_active_mail_account(internal=True)
        if account is not None:
            mail_provider = get_mail_provider(account)
        else:
            token_path = os.getenv("TOKEN_PICKLE_PATH", "token.pickle")
            if os.path.exists(token_path):
                from agent.mail_provider import GmailApiProvider
                mail_provider = GmailApiProvider({"provider_type": "gmail_oauth", "_legacy": True})
            else:
                raise HTTPException(
                    status_code=400,
                    detail="No active mail account configured. Add one in the Mail menu.",
                )

        provider = _provider_from(_DEFAULT_PROVIDER, _DEFAULT_MODEL)
        emails = await run_in_threadpool(mail_provider.fetch_unread)
        processed = []

        for email in emails:
            thread = db.get_thread_by_external(email.thread_id)
            if thread is None:
                thread = db.create_thread(
                    _DEFAULT_IDENTITY_MODE if _DEFAULT_IDENTITY_MODE != "ask" else "fake",
                    external_thread_id=email.thread_id,
                    subject=email.subject,
                )
                _build_primary_persona(
                    thread["id"],
                    thread["identity_mode"],
                    _DEFAULT_LOCALE,
                    scammer_from=email.from_address,
                )
                db.add_participant(
                    thread["id"], scammer_email=email.from_address,
                    role="scammer", connection_type="contact",
                )

            thread_id = thread["id"]
            history = _history_for_agent(thread_id)
            db.add_message(thread_id, "incoming", email.mail_body)
            primary = db.get_primary_persona(thread_id)

            result = run_agent(
                email.mail_body, provider,
                context={"thread_id": thread_id},
                history=history,
            )

            db.add_message(thread_id, "outgoing", result["reply"],
                           sender_persona_id=(primary["id"] if primary else None))

            await run_in_threadpool(mail_provider.send_reply, result["reply"], email)
            await run_in_threadpool(mail_provider.mark_read, email)

            processed.append({
                "thread_id": email.thread_id,
                "from": email.from_address,
                "banking_intent": result["banking_intent"],
                "tools_called": [t["name"] for t in result["tools_called"]],
                "characters_created": [c["role"] for c in result["characters_created"]],
            })

        return JSONResponse({"processed": processed})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Mail account management ────────────────────────────────────────────────

class MailAccountCreate(BaseModel):
    label: str = ""
    preset: str | None = None
    provider_type: str = "imap_smtp"
    email_address: str
    auth_kind: str = "password"
    imap_host: str | None = None
    imap_port: int | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    use_ssl: bool = True
    starttls: bool = False
    username: str | None = None
    secret: str | None = None   # write-only (password / app password)
    activate: bool = True


@app.get("/mail/presets")
async def mail_presets_route():
    return JSONResponse(mail_presets.list_presets())


@app.get("/mail/accounts")
async def mail_accounts_list():
    return JSONResponse(db.list_mail_accounts())


@app.post("/mail/accounts")
async def mail_accounts_create(req: MailAccountCreate):
    fields = req.model_dump()
    preset_key = fields.pop("preset", None)
    if preset_key:
        preset = mail_presets.get_preset(preset_key)
        if preset is None:
            raise HTTPException(status_code=400, detail=f"Unknown preset: {preset_key}")
        # Preset fills transport fields unless the request overrode them.
        for k in ("provider_type", "imap_host", "imap_port", "smtp_host",
                  "smtp_port", "use_ssl", "starttls"):
            if k in preset and preset.get(k) not in (None, ""):
                if fields.get(k) in (None, "", True, False) and k not in ("use_ssl", "starttls"):
                    fields[k] = preset[k]
        # ssl/starttls come from preset when the client didn't explicitly set them
        fields.setdefault("provider_type", preset.get("provider_type", "imap_smtp"))
        if fields.get("imap_host") in (None, ""):
            fields["imap_host"] = preset.get("imap_host")
        if not fields.get("imap_port"):
            fields["imap_port"] = preset.get("imap_port")
        if fields.get("smtp_host") in (None, ""):
            fields["smtp_host"] = preset.get("smtp_host")
        if not fields.get("smtp_port"):
            fields["smtp_port"] = preset.get("smtp_port")
        fields["use_ssl"] = preset.get("use_ssl", fields.get("use_ssl", True))
        fields["starttls"] = preset.get("starttls", fields.get("starttls", False))
        if preset.get("auth"):
            fields["auth_kind"] = "app_password" if preset["auth"] == "app_password" else \
                                  ("oauth" if preset["auth"] == "oauth" else "password")

    if fields.get("provider_type") in ("gmail_oauth", "microsoft_oauth"):
        raise HTTPException(
            status_code=400,
            detail="OAuth accounts are created via the Connect buttons (/mail/oauth/start), not here.",
        )

    activate = fields.pop("activate", True)
    account = db.create_mail_account(is_active=activate, **fields)
    return JSONResponse(account)


@app.post("/mail/accounts/{account_id}/test")
async def mail_accounts_test(account_id: int):
    account = db.get_mail_account(account_id, internal=True)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    provider = get_mail_provider(account)
    result = await run_in_threadpool(provider.test_connection)
    return JSONResponse(result)


@app.post("/mail/accounts/{account_id}/activate")
async def mail_accounts_activate(account_id: int):
    account = db.set_active_mail_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return JSONResponse(account)


@app.delete("/mail/accounts/{account_id}")
async def mail_accounts_delete(account_id: int):
    ok = db.delete_mail_account(account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return JSONResponse({"deleted": True})


# ── OAuth (SSO) ────────────────────────────────────────────────────────────

# Short-lived state store for the web-mode callback: state -> {provider, label, flow}
_oauth_state: dict = {}


@app.get("/mail/oauth/start")
async def mail_oauth_start(provider: str, label: str = ""):
    from agent import mail_oauth

    if provider not in ("gmail", "microsoft"):
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    try:
        if _OAUTH_REDIRECT_MODE == "loopback":
            # Blocking consent flows run in the threadpool so the event loop stays free.
            if provider == "gmail":
                res = await run_in_threadpool(mail_oauth.run_google_loopback)
            else:  # microsoft — device-code flow
                res = await run_in_threadpool(mail_oauth.run_microsoft_device_code)
            ptype = "gmail_oauth" if provider == "gmail" else "microsoft_oauth"
            account = db.create_mail_account(
                label=label or res["email"], provider_type=ptype,
                email_address=res["email"], auth_kind="oauth",
                oauth_token=res["bundle"], is_active=True,
            )
            return JSONResponse({"ok": True, "account": account})

        # web mode → return an auth URL the browser opens; callback finishes it
        base = os.getenv("OAUTH_BASE_URL", "").rstrip("/")
        if not base:
            raise HTTPException(status_code=400, detail="OAUTH_BASE_URL must be set in web mode.")
        redirect_uri = f"{base}/oauth/callback"
        import secrets as _secrets
        state = _secrets.token_urlsafe(24)
        if provider == "gmail":
            flow = mail_oauth._build_google_flow(redirect_uri=redirect_uri)
            auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
            _oauth_state[state] = {"provider": "gmail", "label": label, "flow": flow}
        else:
            app_msal = mail_oauth._msal_app()
            auth_url = app_msal.get_authorization_request_url(
                mail_oauth.MS_SCOPES + ["offline_access"], state=state, redirect_uri=redirect_uri)
            _oauth_state[state] = {"provider": "microsoft", "label": label, "redirect_uri": redirect_uri}
        return JSONResponse({"auth_url": auth_url})
    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail=(
            "Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID/SECRET in .env, "
            "or provide credentials.json."))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OAuth start failed: {exc}")


@app.get("/oauth/callback")
async def oauth_callback(request: Request):
    from agent import mail_oauth
    params = dict(request.query_params)
    state = params.get("state", "")
    code = params.get("code", "")
    entry = _oauth_state.pop(state, None)
    if entry is None or not code:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    if entry["provider"] == "gmail":
        flow = entry["flow"]
        await run_in_threadpool(flow.fetch_token, code=code)
        creds = flow.credentials
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        email = service.users().getProfile(userId="me").execute().get("emailAddress", "")
        db.create_mail_account(
            label=entry.get("label") or email, provider_type="gmail_oauth",
            email_address=email, auth_kind="oauth",
            oauth_token=mail_oauth._google_creds_to_bundle(creds), is_active=True,
        )
    elif entry["provider"] == "microsoft":
        app_msal = mail_oauth._msal_app()
        result = await run_in_threadpool(
            app_msal.acquire_token_by_authorization_code,
            code, mail_oauth.MS_SCOPES + ["offline_access"], entry["redirect_uri"],
        )
        if "access_token" not in result:
            raise HTTPException(status_code=400, detail=f"Microsoft auth failed: {result.get('error_description')}")
        email = (result.get("id_token_claims") or {}).get("preferred_username", "")
        db.create_mail_account(
            label=entry.get("label") or email, provider_type="microsoft_oauth",
            email_address=email, auth_kind="oauth",
            oauth_token=mail_oauth._ms_result_to_bundle(result), is_active=True,
        )

    return RedirectResponse(url="/")


# ── Inbox & send ─────────────────────────────────────────────────────────────

def _mail_to_dict(m) -> dict:
    """Serialize a Mail object to a JSON-safe dict."""
    return {
        "from_address": m.from_address,
        "to_address": m.to_address,
        "subject": m.subject,
        "mail_body": m.mail_body,
        "thread_id": m.thread_id,
        "msg_id": m.msg_id,
        "uid": getattr(m, "uid", ""),
        "folder": getattr(m, "folder", "INBOX"),
    }


@app.get("/mail/inbox")
async def mail_inbox():
    """Return all unread messages from the active mail account."""
    account = db.get_active_mail_account(internal=True)
    if account is None:
        raise HTTPException(status_code=400, detail="No active mail account. Configure one in the Mail menu.")
    try:
        provider = get_mail_provider(account)
        mails = await run_in_threadpool(provider.fetch_unread)
        return JSONResponse([_mail_to_dict(m) for m in mails])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inbox fetch failed: {exc}")


class SendMailRequest(BaseModel):
    reply_text: str
    # Mail context (from a /mail/inbox item or a DB message)
    from_address: str
    to_address: str
    subject: str
    thread_id: str = ""
    msg_id: str = ""
    uid: str = ""
    folder: str = "INBOX"
    mark_read: bool = True


@app.post("/mail/send")
async def mail_send(req: SendMailRequest):
    """Send a reply via the active mail account."""
    account = db.get_active_mail_account(internal=True)
    if account is None:
        raise HTTPException(status_code=400, detail="No active mail account. Configure one in the Mail menu.")
    try:
        from agent.classes import Mail
        mail = Mail(
            from_address=req.from_address,
            to_address=req.to_address,
            subject=req.subject,
            thread_id=req.thread_id,
            msg_id=req.msg_id,
            uid=req.uid,
            folder=req.folder,
        )
        provider = get_mail_provider(account)
        await run_in_threadpool(provider.send_reply, req.reply_text, mail)
        if req.mark_read and req.uid:
            await run_in_threadpool(provider.mark_read, mail)
        return JSONResponse({"ok": True, "to": req.from_address, "subject": req.subject})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Send failed: {exc}")
