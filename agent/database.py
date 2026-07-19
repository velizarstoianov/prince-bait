import os
from contextlib import contextmanager

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from agent.models import Base, Thread, Persona, Participant, Message
from agent.classes import Identity

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
