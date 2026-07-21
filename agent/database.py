import os
from contextlib import contextmanager

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from agent.models import Base, Thread, Persona, Participant, Message, MailAccount
from agent.classes import Identity
from agent import crypto

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///scambaiter.db")

_engine = None
_SessionFactory = None

# Persona columns that mirror Identity attributes (name-matched).
_IDENTITY_FIELDS = [
    "name", "first_name", "last_name", "email", "phone_number", "age", "birth",
    "gender", "country", "city", "state", "post_code", "address", "company",
    "job_title", "ssn", "username", "password", "iban", "bank_account",
    "swift_bic", "card_num", "card_date", "card_cvv",
]


def get_engine():
    global _engine
    if _engine is None:
        connect_args = {}
        if DATABASE_URL.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        _engine = create_engine(DATABASE_URL, future=True, connect_args=connect_args)
    return _engine


def get_session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, future=True
        )
    return _SessionFactory


def init_db():
    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope():
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── Serializers (return plain dicts to avoid DetachedInstanceError) ─────────────

def _thread_dict(t: Thread, message_count: int | None = None) -> dict:
    d = {
        "id": t.id,
        "external_thread_id": t.external_thread_id,
        "identity_mode": t.identity_mode,
        "subject": t.subject,
        "scam_level": t.scam_level,
        "notes": t.notes,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
    if message_count is not None:
        d["message_count"] = message_count
    return d


def _persona_dict(p: Persona) -> dict:
    d = {"id": p.id, "thread_id": p.thread_id, "role": p.role, "source": p.source}
    for f in _IDENTITY_FIELDS:
        d[f] = getattr(p, f)
    d["created_at"] = p.created_at.isoformat() if p.created_at else None
    return d


def _participant_dict(p: Participant) -> dict:
    return {
        "id": p.id,
        "thread_id": p.thread_id,
        "persona_id": p.persona_id,
        "scammer_email": p.scammer_email,
        "role": p.role,
        "connection_type": p.connection_type,
    }


def _message_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "thread_id": m.thread_id,
        "direction": m.direction,
        "sender_persona_id": m.sender_persona_id,
        "body": m.body,
        "seq": m.seq,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


# ── Threads ─────────────────────────────────────────────────────────────────

def create_thread(identity_mode: str, external_thread_id: str | None = None,
                   subject: str | None = None) -> dict:
    with session_scope() as s:
        t = Thread(
            identity_mode=identity_mode,
            external_thread_id=external_thread_id,
            subject=subject,
        )
        s.add(t)
        s.flush()
        return _thread_dict(t)


def get_thread(thread_id: int) -> dict | None:
    with session_scope() as s:
        t = s.get(Thread, thread_id)
        return _thread_dict(t) if t else None


def get_thread_by_external(external_thread_id: str) -> dict | None:
    with session_scope() as s:
        t = s.scalar(
            select(Thread).where(Thread.external_thread_id == external_thread_id)
        )
        return _thread_dict(t) if t else None


def list_threads(limit: int = 50) -> list[dict]:
    with session_scope() as s:
        threads = s.scalars(
            select(Thread).order_by(Thread.id.desc()).limit(limit)
        ).all()
        result = []
        for t in threads:
            count = s.scalar(
                select(func.count(Message.id)).where(Message.thread_id == t.id)
            )
            result.append(_thread_dict(t, message_count=count or 0))
        return result


# ── Messages ────────────────────────────────────────────────────────────────

def add_message(thread_id: int, direction: str, body: str,
                sender_persona_id: int | None = None) -> dict:
    with session_scope() as s:
        max_seq = s.scalar(
            select(func.max(Message.seq)).where(Message.thread_id == thread_id)
        )
        next_seq = 0 if max_seq is None else max_seq + 1
        m = Message(
            thread_id=thread_id,
            direction=direction,
            body=body,
            sender_persona_id=sender_persona_id,
            seq=next_seq,
        )
        s.add(m)
        s.flush()
        return _message_dict(m)


def get_messages(thread_id: int) -> list[dict]:
    with session_scope() as s:
        msgs = s.scalars(
            select(Message).where(Message.thread_id == thread_id).order_by(Message.seq)
        ).all()
        return [_message_dict(m) for m in msgs]


# ── Personas ──────────────────────────────────────────────────────────────

def create_persona(thread_id: int, identity: Identity, role: str = "",
                   source: str = "generated") -> dict:
    with session_scope() as s:
        kwargs = {f: (getattr(identity, f, "") or "") for f in _IDENTITY_FIELDS}
        kwargs["locale"] = getattr(identity, "locale", "") or ""
        p = Persona(thread_id=thread_id, role=role, source=source, **kwargs)
        s.add(p)
        s.flush()
        return _persona_dict(p)


def get_personas(thread_id: int) -> list[dict]:
    with session_scope() as s:
        personas = s.scalars(
            select(Persona).where(Persona.thread_id == thread_id).order_by(Persona.id)
        ).all()
        return [_persona_dict(p) for p in personas]


def get_primary_persona(thread_id: int) -> dict | None:
    with session_scope() as s:
        p = s.scalar(
            select(Persona)
            .where(Persona.thread_id == thread_id, Persona.role == "victim")
            .order_by(Persona.id)
        )
        if p is None:
            p = s.scalar(
                select(Persona).where(Persona.thread_id == thread_id).order_by(Persona.id)
            )
        return _persona_dict(p) if p else None


# ── Participants ──────────────────────────────────────────────────────────

def add_participant(thread_id: int, persona_id: int | None = None,
                    scammer_email: str | None = None, role: str = "",
                    connection_type: str = "primary") -> dict:
    with session_scope() as s:
        p = Participant(
            thread_id=thread_id,
            persona_id=persona_id,
            scammer_email=scammer_email,
            role=role,
            connection_type=connection_type,
        )
        s.add(p)
        s.flush()
        return _participant_dict(p)


def get_participants(thread_id: int) -> list[dict]:
    with session_scope() as s:
        parts = s.scalars(
            select(Participant).where(Participant.thread_id == thread_id).order_by(Participant.id)
        ).all()
        return [_participant_dict(p) for p in parts]


# ── Mail accounts ────────────────────────────────────────────────────────────

_MAIL_PUBLIC_FIELDS = [
    "id", "label", "provider_type", "email_address", "auth_kind",
    "imap_host", "imap_port", "smtp_host", "smtp_port", "use_ssl", "starttls",
    "username", "is_active",
]


def _mail_public_dict(a: MailAccount) -> dict:
    """Redacted view — safe to return to the client. No secrets, ever."""
    d = {f: getattr(a, f) for f in _MAIL_PUBLIC_FIELDS}
    d["has_secret"] = bool(a.secret_enc)
    d["has_oauth"] = bool(a.oauth_token_enc)
    d["created_at"] = a.created_at.isoformat() if a.created_at else None
    return d


def _mail_internal_dict(a: MailAccount) -> dict:
    """Full view with DECRYPTED secrets — for the provider factory only. Never returned by a route."""
    d = _mail_public_dict(a)
    d["secret"] = crypto.decrypt(a.secret_enc)
    d["oauth_token"] = crypto.decrypt(a.oauth_token_enc)  # JSON string or None
    return d


def create_mail_account(*, label="", provider_type, email_address, auth_kind="password",
                        imap_host=None, imap_port=None, smtp_host=None, smtp_port=None,
                        use_ssl=True, starttls=False, username=None,
                        secret=None, oauth_token=None, is_active=False) -> dict:
    with session_scope() as s:
        a = MailAccount(
            label=label or email_address,
            provider_type=provider_type,
            email_address=email_address,
            auth_kind=auth_kind,
            imap_host=imap_host, imap_port=imap_port,
            smtp_host=smtp_host, smtp_port=smtp_port,
            use_ssl=use_ssl, starttls=starttls,
            username=username or email_address,
            secret_enc=crypto.encrypt(secret),
            oauth_token_enc=crypto.encrypt(oauth_token),
            is_active=is_active,
        )
        if is_active:
            for other in s.scalars(select(MailAccount).where(MailAccount.is_active == True)).all():  # noqa: E712
                other.is_active = False
        s.add(a)
        s.flush()
        return _mail_public_dict(a)


def list_mail_accounts() -> list[dict]:
    with session_scope() as s:
        rows = s.scalars(select(MailAccount).order_by(MailAccount.id.desc())).all()
        return [_mail_public_dict(a) for a in rows]


def get_mail_account(account_id: int, *, internal: bool = False) -> dict | None:
    with session_scope() as s:
        a = s.get(MailAccount, account_id)
        if a is None:
            return None
        return _mail_internal_dict(a) if internal else _mail_public_dict(a)


def update_mail_account(account_id: int, *, secret=None, oauth_token=None, **fields) -> dict | None:
    with session_scope() as s:
        a = s.get(MailAccount, account_id)
        if a is None:
            return None
        for k, v in fields.items():
            if hasattr(a, k):
                setattr(a, k, v)
        if secret is not None:
            a.secret_enc = crypto.encrypt(secret)
        if oauth_token is not None:
            a.oauth_token_enc = crypto.encrypt(oauth_token)
        s.flush()
        return _mail_public_dict(a)


def delete_mail_account(account_id: int) -> bool:
    with session_scope() as s:
        a = s.get(MailAccount, account_id)
        if a is None:
            return False
        s.delete(a)
        return True


def set_active_mail_account(account_id: int) -> dict | None:
    with session_scope() as s:
        target = s.get(MailAccount, account_id)
        if target is None:
            return None
        for a in s.scalars(select(MailAccount).where(MailAccount.is_active == True)).all():  # noqa: E712
            a.is_active = False
        target.is_active = True
        s.flush()
        return _mail_public_dict(target)


def get_active_mail_account(*, internal: bool = False) -> dict | None:
    with session_scope() as s:
        a = s.scalar(select(MailAccount).where(MailAccount.is_active == True))  # noqa: E712
        if a is None:
            return None
        return _mail_internal_dict(a) if internal else _mail_public_dict(a)
