"""OAuth helpers for Gmail (Google API) and Microsoft (IMAP/SMTP XOAUTH2).

Token bundles are stored encrypted (as JSON) in MailAccount.oauth_token_enc via the repo.
Access tokens are refreshed on use, then re-encrypted and persisted.
"""
import os
import json
import time

from agent import database as db

# ── Google (Gmail API) ────────────────────────────────────────────────────────

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


def _google_client_config() -> dict | None:
    """Build an InstalledAppFlow client config from env, or None to fall back to credentials.json."""
    cid = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if cid and secret:
        return {
            "installed": {
                "client_id": cid,
                "client_secret": secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
    return None


def _build_google_flow(redirect_uri: str | None = None):
    from google_auth_oauthlib.flow import InstalledAppFlow, Flow
    cfg = _google_client_config()
    if redirect_uri:
        if cfg:
            flow = Flow.from_client_config(cfg, scopes=GMAIL_SCOPES)
        else:
            flow = Flow.from_client_secrets_file(
                os.getenv("CREDENTIALS_JSON_PATH", "credentials.json"), scopes=GMAIL_SCOPES)
        flow.redirect_uri = redirect_uri
        return flow
    # loopback
    if cfg:
        return InstalledAppFlow.from_client_config(cfg, GMAIL_SCOPES)
    return InstalledAppFlow.from_client_secrets_file(
        os.getenv("CREDENTIALS_JSON_PATH", "credentials.json"), GMAIL_SCOPES)


def _google_creds_to_bundle(creds) -> str:
    return json.dumps({
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or GMAIL_SCOPES),
    })


def run_google_loopback() -> dict:
    """Blocking local-server consent flow. Returns a token bundle dict + email."""
    from googleapiclient.discovery import build
    flow = _build_google_flow()
    creds = flow.run_local_server(port=0)
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    return {"bundle": _google_creds_to_bundle(creds), "email": profile.get("emailAddress", "")}


def gmail_service_for_account(account: dict):
    """Build a Gmail API service from a stored (decrypted) account, refreshing if needed.
    Legacy accounts (no bundle) fall back to the env/token.pickle authorize() path."""
    from googleapiclient.discovery import build
    if account.get("_legacy") or not account.get("oauth_token"):
        from agent import gmail_interface
        return build("gmail", "v1", credentials=gmail_interface.authorize())

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    data = json.loads(account["oauth_token"])
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes", GMAIL_SCOPES),
    )
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        if account.get("id"):
            db.update_mail_account(account["id"], oauth_token=_google_creds_to_bundle(creds))
    return build("gmail", "v1", credentials=creds)


# ── Microsoft (IMAP/SMTP XOAUTH2 via MSAL) ─────────────────────────────────────

MS_SCOPES = [
    "https://outlook.office.com/IMAP.AccessAsUser.All",
    "https://outlook.office.com/SMTP.Send",
]


def _msal_app():
    import msal
    client_id = os.getenv("MICROSOFT_OAUTH_CLIENT_ID", "").strip()
    secret = os.getenv("MICROSOFT_OAUTH_CLIENT_SECRET", "").strip()
    tenant = os.getenv("MICROSOFT_OAUTH_TENANT", "common").strip() or "common"
    authority = f"https://login.microsoftonline.com/{tenant}"
    if not client_id:
        raise ValueError("MICROSOFT_OAUTH_CLIENT_ID is not set.")
    if secret:
        return msal.ConfidentialClientApplication(client_id, authority=authority, client_credential=secret)
    return msal.PublicClientApplication(client_id, authority=authority)


def _ms_result_to_bundle(result: dict) -> str:
    return json.dumps({
        "access_token": result.get("access_token"),
        "refresh_token": result.get("refresh_token"),
        "expires_at": int(time.time()) + int(result.get("expires_in", 0)),
        "scopes": MS_SCOPES,
    })


def run_microsoft_device_code(status_cb=None) -> dict:
    """Device-code flow for loopback/local use. Blocking. Returns bundle + email."""
    app = _msal_app()
    flow = app.initiate_device_flow(scopes=MS_SCOPES + ["offline_access"])
    if "user_code" not in flow:
        raise ValueError(f"Device flow failed to start: {flow.get('error_description', flow)}")
    if status_cb:
        status_cb(flow)  # surface verification_uri + user_code to the UI
    result = app.acquire_token_by_device_flow(flow)  # blocks until the user completes
    if "access_token" not in result:
        raise ValueError(f"Microsoft auth failed: {result.get('error_description', result)}")
    email = (result.get("id_token_claims") or {}).get("preferred_username", "")
    return {"bundle": _ms_result_to_bundle(result), "email": email}


def microsoft_access_token(account: dict) -> str:
    """Return a valid MS access token, refreshing via the cached refresh token if needed."""
    data = json.loads(account["oauth_token"]) if account.get("oauth_token") else {}
    if data.get("access_token") and data.get("expires_at", 0) - 60 > time.time():
        return data["access_token"]
    # refresh
    app = _msal_app()
    result = None
    if data.get("refresh_token"):
        result = app.acquire_token_by_refresh_token(data["refresh_token"], scopes=MS_SCOPES)
    if not result or "access_token" not in result:
        raise ValueError("Microsoft token expired and could not be refreshed — reconnect the account.")
    if account.get("id"):
        db.update_mail_account(account["id"], oauth_token=_ms_result_to_bundle(result))
    return result["access_token"]
