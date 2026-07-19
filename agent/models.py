from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_thread_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    identity_mode: Mapped[str] = mapped_column(String(16), default="fake")  # resolved: real|fake
    subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    scam_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    personas: Mapped[list["Persona"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )
    participants: Mapped[list["Participant"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id"), index=True)
    role: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(16), default="generated")  # generated|real

    # Identity fields
    name: Mapped[str] = mapped_column(String(255), default="")
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[str] = mapped_column(String(128), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    phone_number: Mapped[str] = mapped_column(String(64), default="")
    age: Mapped[str] = mapped_column(String(16), default="")
    birth: Mapped[str] = mapped_column(String(32), default="")
    gender: Mapped[str] = mapped_column(String(16), default="")
    locale: Mapped[str] = mapped_column(String(16), default="")
    country: Mapped[str] = mapped_column(String(128), default="")
    city: Mapped[str] = mapped_column(String(128), default="")
    state: Mapped[str] = mapped_column(String(128), default="")
    post_code: Mapped[str] = mapped_column(String(32), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    company: Mapped[str] = mapped_column(String(255), default="")
    job_title: Mapped[str] = mapped_column(String(255), default="")
    ssn: Mapped[str] = mapped_column(String(64), default="")
    username: Mapped[str] = mapped_column(String(128), default="")
    password: Mapped[str] = mapped_column(String(128), default="")
    # Financial
    iban: Mapped[str] = mapped_column(String(64), default="")
    bank_account: Mapped[str] = mapped_column(String(64), default="")
    swift_bic: Mapped[str] = mapped_column(String(32), default="")
    card_num: Mapped[str] = mapped_column(String(32), default="")
    card_date: Mapped[str] = mapped_column(String(16), default="")
    card_cvv: Mapped[str] = mapped_column(String(8), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    thread: Mapped["Thread"] = relationship(back_populates="personas")


class Participant(Base):
    """Roles and connections attached to a thread (req #4).

    A participant is either one of our generated/real personas (persona_id set)
    or a raw scammer email address (scammer_email set).
    """
    __tablename__ = "thread_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id"), index=True)
    persona_id: Mapped[int | None] = mapped_column(ForeignKey("personas.id"), nullable=True)
    scammer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(64), default="")  # victim|scammer|lawyer|...
    connection_type: Mapped[str] = mapped_column(String(32), default="primary")  # primary|side_character|contact
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    thread: Mapped["Thread"] = relationship(back_populates="participants")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id"), index=True)
    direction: Mapped[str] = mapped_column(String(16))  # incoming (scammer) | outgoing (agent)
    sender_persona_id: Mapped[int | None] = mapped_column(ForeignKey("personas.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    seq: Mapped[int] = mapped_column(Integer, default=0)  # per-thread ordering
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    thread: Mapped["Thread"] = relationship(back_populates="messages")
