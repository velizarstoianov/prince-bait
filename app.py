import os
import re
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from agent.llm_provider import get_provider, PROVIDER_MODELS, MODEL_LABELS
from agent.agent_core import run_agent
from agent.classes import Identity
from agent.fake_personality import generate_identity
from agent import database as db

app = FastAPI(title="419 Scam Baiter Agent")
templates = Jinja2Templates(directory="templates")

_DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "claude")
_DEFAULT_MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5")
_DEFAULT_IDENTITY_MODE = os.getenv("IDENTITY_MODE", "fake")
_DEFAULT_LOCALE = os.getenv("IDENTITY_LOCALE", "en_US")
_LOCALES = ["en_US", "fr_FR", "es_ES", "it_IT", "de_DE", "pt_PT", "nl_NL", "pl_PL"]


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
        from agent.gmail_interface import get_last_mails_unread, reply_to_mail, add_mail_label

        provider = _provider_from(_DEFAULT_PROVIDER, _DEFAULT_MODEL)
        emails = get_last_mails_unread()
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

            reply_to_mail(result["reply"], email)
            add_mail_label(email.thread_id, "READ", user_id="me")

            processed.append({
                "thread_id": email.thread_id,
                "from": email.from_address,
                "banking_intent": result["banking_intent"],
                "tools_called": [t["name"] for t in result["tools_called"]],
                "characters_created": [c["role"] for c in result["characters_created"]],
            })

        return JSONResponse({"processed": processed})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
