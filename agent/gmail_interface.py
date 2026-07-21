import os
import pickle
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from agent.classes import Mail, Conversation_Thread

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

GMAIL_USER_ID = os.getenv("GMAIL_USER_ID", "me")


def authorize():
    creds = None
    token_path = os.getenv("TOKEN_PICKLE_PATH", "token.pickle")
    creds_path = os.getenv("CREDENTIALS_JSON_PATH", "credentials.json")

    if os.path.exists(token_path):
        with open(token_path, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "wb") as f:
            pickle.dump(creds, f)

    return creds


def _decode_body(message_parts) -> str:
    if not message_parts:
        return ""
    for part in message_parts:
        data = part.get("body", {}).get("data")
        if data:
            try:
                return base64.urlsafe_b64decode(bytes(data, "utf-8")).decode("utf-8", errors="replace")
            except Exception:
                continue
    return ""


def _parse_headers(headers: list) -> dict:
    result = {"from": "", "to": "", "subject": "", "message-id": ""}
    for header in headers:
        name = str(header.get("name", "")).lower()
        if name in result:
            result[name] = header.get("value", "")
    return result


def _build_mail(message_in_thread: dict) -> Mail:
    payload = message_in_thread.get("payload", {})
    headers = _parse_headers(payload.get("headers", []))
    mail_body = _decode_body(payload.get("parts"))
    obj = Mail()
    obj.from_address = headers["from"]
    obj.to_address = headers["to"]
    obj.subject = headers["subject"]
    obj.msg_id = headers["message-id"]
    obj.thread_id = str(message_in_thread.get("threadId", ""))
    obj.mail_body = mail_body
    return obj


def _svc(service=None):
    """Return an injected Gmail service, or build one from the legacy env/token.pickle flow."""
    if service is not None:
        return service
    creds = authorize()
    return build("gmail", "v1", credentials=creds)


def get_last_mails_unread(service=None) -> list[Mail]:
    service = _svc(service)
    threads = service.users().threads().list(userId=GMAIL_USER_ID).execute().get("threads", [])
    last_mails = []
    for thread in threads:
        thread_data = service.users().threads().get(userId=GMAIL_USER_ID, id=thread["id"]).execute()
        messages = thread_data["messages"]
        last_msg = messages[-1]
        labels = last_msg.get("labelIds", [])
        if "UNREAD" not in labels or "INBOX" not in labels:
            continue
        last_mails.append(_build_mail(last_msg))
    return last_mails


def get_last_mails() -> list[Mail]:
    creds = authorize()
    service = build("gmail", "v1", credentials=creds)
    threads = service.users().threads().list(userId=GMAIL_USER_ID).execute().get("threads", [])
    last_mails = []
    for thread in threads:
        thread_data = service.users().threads().get(userId=GMAIL_USER_ID, id=thread["id"]).execute()
        messages = thread_data["messages"]
        last_msg = messages[-1]
        if "INBOX" not in last_msg.get("labelIds", []):
            continue
        last_mails.append(_build_mail(last_msg))
    return last_mails


def get_mailbox_unread() -> list[Conversation_Thread]:
    creds = authorize()
    service = build("gmail", "v1", credentials=creds)
    threads = service.users().threads().list(userId=GMAIL_USER_ID).execute().get("threads", [])
    mailbox = []
    for thread in threads:
        thread_data = service.users().threads().get(userId=GMAIL_USER_ID, id=thread["id"]).execute()
        temp_thread = Conversation_Thread()
        temp_thread.thread_id = thread_data["id"]
        for msg in thread_data["messages"]:
            labels = msg.get("labelIds", [])
            if "UNREAD" not in labels or "INBOX" not in labels:
                continue
            mail_obj = _build_mail(msg)
            if mail_obj.from_address not in temp_thread.scammer_acc:
                temp_thread.scammer_acc.append(mail_obj.from_address)
            temp_thread.conversation.append(mail_obj)
            temp_thread.sender_acc = mail_obj.to_address
        mailbox.append(temp_thread)
    return mailbox


def reply_to_mail(reply_text: str, mail_to_reply: Mail, service=None):
    service = _svc(service)
    message = MIMEMultipart()
    message["to"] = mail_to_reply.from_address
    message["from"] = mail_to_reply.to_address
    message["In-Reply-To"] = mail_to_reply.msg_id
    message["References"] = mail_to_reply.msg_id
    message["Subject"] = "Re: " + mail_to_reply.subject
    message.attach(MIMEText(reply_text, "plain"))
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(
        userId="me",
        body={"raw": raw, "threadId": mail_to_reply.thread_id},
    ).execute()


def remove_mail_label(thread_id: str, remove: str = "UNREAD", user_id: str = GMAIL_USER_ID):
    if remove not in ("UNREAD", "READ"):
        return
    creds = authorize()
    service = build("gmail", "v1", credentials=creds)
    service.users().messages().modify(
        userId=user_id, id=thread_id, body={"removeLabelIds": [remove]}
    ).execute()


def add_mail_label(thread_id: str, add: str = "READ", user_id: str = GMAIL_USER_ID, service=None):
    # BUG FIX: original used undefined 'remove', called wrong authorize(), used removeLabelIds
    if add not in ("UNREAD", "READ"):
        return
    service = _svc(service)
    service.users().messages().modify(
        userId=user_id, id=thread_id, body={"addLabelIds": [add]}
    ).execute()
