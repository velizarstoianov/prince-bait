"""Universal mail provider layer. Mirrors llm_provider.py: an ABC + concrete
implementations + a get_mail_provider() factory.

- ImapSmtpProvider: stdlib imaplib/smtplib. Plain password OR XOAUTH2 auth. Universal.
- GmailApiProvider: wraps the existing Gmail API code, creds from the DB account.
- MicrosoftProvider: ImapSmtpProvider subclass forcing XOAUTH2 (Outlook/M365).
"""
import ssl
import base64
import imaplib
import smtplib
from abc import ABC, abstractmethod
from email import message_from_bytes
from email.policy import default as email_default_policy
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid, getaddresses

from agent.classes import Mail

_TIMEOUT = 30  # socket timeout (seconds)


class MailProvider(ABC):
    @abstractmethod
    def fetch_unread(self) -> list[Mail]: ...

    @abstractmethod
    def send_reply(self, reply_text: str, mail: Mail) -> None: ...

    @abstractmethod
    def mark_read(self, mail: Mail) -> None: ...

    @abstractmethod
    def test_connection(self) -> dict: ...


# ── IMAP/SMTP (universal) ─────────────────────────────────────────────────────

def _extract_body(msg) -> str:
    """Best-effort plain-text body from a parsed email.message.EmailMessage."""
    try:
        body = msg.get_body(preferencelist=("plain", "html"))
        if body is not None:
            content = body.get_content()
            if body.get_content_type() == "text/html":
                import re
                content = re.sub(r"<[^>]+>", " ", content)
            return content.strip()
    except Exception:
        pass
    # Fallback: walk parts
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_content().strip()
                except Exception:
                    continue
    try:
        return msg.get_content().strip()
    except Exception:
        return ""


def _root_message_id(msg) -> str:
    """Stable thread key over IMAP: root of the References chain, else In-Reply-To,
    else this message's own Message-ID."""
    refs = msg.get("References", "")
    if refs:
        parts = refs.split()
        if parts:
            return parts[0].strip()
    in_reply = msg.get("In-Reply-To", "")
    if in_reply:
        return in_reply.strip()
    return (msg.get("Message-ID", "") or "").strip()


class ImapSmtpProvider(MailProvider):
    def __init__(self, account: dict):
        self.account = account
        self.email = account["email_address"]
        self.username = account.get("username") or self.email
        self.imap_host = account.get("imap_host")
        self.imap_port = account.get("imap_port") or 993
        self.smtp_host = account.get("smtp_host")
        self.smtp_port = account.get("smtp_port") or 465
        self.use_ssl = account.get("use_ssl", True)
        self.starttls = account.get("starttls", False)
        self.auth_kind = account.get("auth_kind", "password")
        self.password = account.get("secret")

    # Overridden by MicrosoftProvider / OAuth variants
    def _uses_xoauth2(self) -> bool:
        return self.auth_kind == "oauth"

    def _access_token(self) -> str:
        raise NotImplementedError("XOAUTH2 requested but no token source configured.")

    def _sasl_xoauth2(self) -> bytes:
        token = self._access_token()
        return f"user={self.email}\x01auth=Bearer {token}\x01\x01".encode("utf-8")

    # ── Connections ──
    def _imap_connect(self) -> imaplib.IMAP4:
        if self.use_ssl:
            imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port,
                                     ssl_context=ssl.create_default_context(), timeout=_TIMEOUT)
        else:
            imap = imaplib.IMAP4(self.imap_host, self.imap_port, timeout=_TIMEOUT)
            if self.starttls:
                imap.starttls(ssl.create_default_context())
        if self._uses_xoauth2():
            imap.authenticate("XOAUTH2", lambda _: self._sasl_xoauth2())
        else:
            imap.login(self.username, self.password or "")
        return imap

    def _smtp_connect(self) -> smtplib.SMTP:
        if self.use_ssl and not self.starttls:
            smtp = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port,
                                    context=ssl.create_default_context(), timeout=_TIMEOUT)
        else:
            smtp = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=_TIMEOUT)
            smtp.ehlo()
            if self.starttls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
        if self._uses_xoauth2():
            smtp.auth("XOAUTH2", lambda _=None: self._sasl_xoauth2().decode("utf-8"))
        else:
            smtp.login(self.username, self.password or "")
        return smtp

    # ── Operations ──
    def fetch_unread(self) -> list[Mail]:
        imap = self._imap_connect()
        mails: list[Mail] = []
        try:
            imap.select("INBOX")
            typ, data = imap.uid("SEARCH", None, "UNSEEN")
            if typ != "OK":
                return []
            uids = data[0].split()
            for uid in uids:
                typ, msg_data = imap.uid("FETCH", uid, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = message_from_bytes(raw, policy=email_default_policy)
                m = Mail()
                from_hdr = msg.get("From", "")
                addrs = getaddresses([from_hdr])
                m.from_address = addrs[0][1] if addrs else from_hdr
                to_addrs = getaddresses([msg.get("To", "")])
                m.to_address = to_addrs[0][1] if to_addrs else self.email
                m.subject = str(msg.get("Subject", ""))
                m.msg_id = (msg.get("Message-ID", "") or "").strip()
                m.thread_id = _root_message_id(msg) or m.msg_id
                m.mail_body = _extract_body(msg)
                m.uid = uid.decode() if isinstance(uid, bytes) else str(uid)
                m.folder = "INBOX"
                mails.append(m)
        finally:
            try:
                imap.logout()
            except Exception:
                pass
        return mails

    def send_reply(self, reply_text: str, mail: Mail) -> None:
        message = MIMEMultipart()
        message["To"] = mail.from_address
        message["From"] = self.email
        subject = mail.subject or ""
        message["Subject"] = subject if subject.lower().startswith("re:") else "Re: " + subject
        if mail.msg_id:
            message["In-Reply-To"] = mail.msg_id
            message["References"] = mail.msg_id
        message["Message-ID"] = make_msgid()
        message.attach(MIMEText(reply_text, "plain", "utf-8"))
        smtp = self._smtp_connect()
        try:
            smtp.send_message(message)
        finally:
            try:
                smtp.quit()
            except Exception:
                pass

    def mark_read(self, mail: Mail) -> None:
        if not mail.uid:
            return
        imap = self._imap_connect()
        try:
            imap.select(mail.folder or "INBOX")
            imap.uid("STORE", mail.uid, "+FLAGS", "(\\Seen)")
        finally:
            try:
                imap.logout()
            except Exception:
                pass

    def test_connection(self) -> dict:
        try:
            imap = self._imap_connect()
            try:
                imap.noop()
            finally:
                imap.logout()
        except Exception as exc:
            return {"ok": False, "detail": f"IMAP failed: {exc}"}
        try:
            smtp = self._smtp_connect()
            try:
                smtp.noop()
            finally:
                smtp.quit()
        except Exception as exc:
            return {"ok": False, "detail": f"SMTP failed: {exc}"}
        return {"ok": True, "detail": "IMAP and SMTP login succeeded."}


class MicrosoftProvider(ImapSmtpProvider):
    """Outlook.com / Microsoft 365 via IMAP/SMTP + XOAUTH2 (delegated)."""
    def __init__(self, account: dict):
        account = dict(account)
        account.setdefault("imap_host", "outlook.office365.com")
        account.setdefault("imap_port", 993)
        account.setdefault("smtp_host", "smtp.office365.com")
        account.setdefault("smtp_port", 587)
        account["use_ssl"] = True
        account["starttls"] = True  # SMTP uses STARTTLS on 587; IMAP uses SSL on 993
        account["auth_kind"] = "oauth"
        super().__init__(account)

    def _uses_xoauth2(self) -> bool:
        return True

    def _imap_connect(self) -> imaplib.IMAP4:
        # IMAP is always SSL:993 for Outlook regardless of the STARTTLS flag (which is for SMTP)
        imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port,
                                 ssl_context=ssl.create_default_context(), timeout=_TIMEOUT)
        imap.authenticate("XOAUTH2", lambda _: self._sasl_xoauth2())
        return imap

    def _access_token(self) -> str:
        from agent.mail_oauth import microsoft_access_token
        return microsoft_access_token(self.account)


# ── Gmail API (dedicated, backward-compatible) ────────────────────────────────

class GmailApiProvider(MailProvider):
    def __init__(self, account: dict):
        self.account = account

    def _service(self):
        from agent.mail_oauth import gmail_service_for_account
        return gmail_service_for_account(self.account)

    def fetch_unread(self) -> list[Mail]:
        from agent import gmail_interface
        return gmail_interface.get_last_mails_unread(service=self._service())

    def send_reply(self, reply_text: str, mail: Mail) -> None:
        from agent import gmail_interface
        gmail_interface.reply_to_mail(reply_text, mail, service=self._service())

    def mark_read(self, mail: Mail) -> None:
        from agent import gmail_interface
        gmail_interface.add_mail_label(mail.thread_id, "READ", user_id="me", service=self._service())

    def test_connection(self) -> dict:
        try:
            svc = self._service()
            svc.users().getProfile(userId="me").execute()
            return {"ok": True, "detail": "Gmail API reachable."}
        except Exception as exc:
            return {"ok": False, "detail": f"Gmail API failed: {exc}"}


# ── Factory ───────────────────────────────────────────────────────────────────

def get_mail_provider(account: dict) -> MailProvider:
    """account is an INTERNAL (decrypted) dict from db.get_*_mail_account(internal=True)."""
    providers = {
        "imap_smtp": ImapSmtpProvider,
        "gmail_oauth": GmailApiProvider,
        "microsoft_oauth": MicrosoftProvider,
    }
    ptype = account.get("provider_type")
    cls = providers.get(ptype)
    if cls is None:
        raise ValueError(f"Unknown mail provider_type: {ptype}")
    return cls(account)
