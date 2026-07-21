"""One-click provider presets. All IMAP/SMTP under the hood except the OAuth entries."""

# key -> preset. Ports: IMAP 993 (SSL); SMTP 465 (SSL) or 587 (STARTTLS).
PRESETS = {
    "gmail_oauth": {
        "label": "Gmail (Google SSO — recommended)",
        "provider_type": "gmail_oauth",
        "auth": "oauth",
        "notes": "Sign in with Google. No password stored.",
    },
    "gmail_imap": {
        "label": "Gmail (IMAP + App Password)",
        "provider_type": "imap_smtp",
        "imap_host": "imap.gmail.com", "imap_port": 993,
        "smtp_host": "smtp.gmail.com", "smtp_port": 465,
        "use_ssl": True, "starttls": False,
        "auth": "app_password",
        "notes": "Requires 2-Step Verification + an App Password. Prefer the Google SSO option.",
    },
    "outlook_oauth": {
        "label": "Outlook / Microsoft 365 (Microsoft SSO)",
        "provider_type": "microsoft_oauth",
        "imap_host": "outlook.office365.com", "imap_port": 993,
        "smtp_host": "smtp.office365.com", "smtp_port": 587,
        "use_ssl": True, "starttls": True,
        "auth": "oauth",
        "notes": "Sign in with Microsoft. Basic password auth is deprecated by Microsoft.",
    },
    "yahoo": {
        "label": "Yahoo Mail",
        "provider_type": "imap_smtp",
        "imap_host": "imap.mail.yahoo.com", "imap_port": 993,
        "smtp_host": "smtp.mail.yahoo.com", "smtp_port": 465,
        "use_ssl": True, "starttls": False,
        "auth": "app_password",
        "notes": "Requires a Yahoo App Password.",
    },
    "icloud": {
        "label": "iCloud Mail",
        "provider_type": "imap_smtp",
        "imap_host": "imap.mail.me.com", "imap_port": 993,
        "smtp_host": "smtp.mail.me.com", "smtp_port": 587,
        "use_ssl": True, "starttls": True,
        "auth": "app_password",
        "notes": "Requires an app-specific password from appleid.apple.com.",
    },
    "proton": {
        "label": "Proton Mail (Bridge)",
        "provider_type": "imap_smtp",
        "imap_host": "127.0.0.1", "imap_port": 1143,
        "smtp_host": "127.0.0.1", "smtp_port": 1025,
        "use_ssl": False, "starttls": True,
        "auth": "password",
        "notes": "Requires Proton Mail Bridge running locally; use the Bridge-provided password.",
    },
    "zoho": {
        "label": "Zoho Mail",
        "provider_type": "imap_smtp",
        "imap_host": "imap.zoho.com", "imap_port": 993,
        "smtp_host": "smtp.zoho.com", "smtp_port": 465,
        "use_ssl": True, "starttls": False,
        "auth": "app_password",
        "notes": "Use an app password if 2FA is enabled.",
    },
    "fastmail": {
        "label": "Fastmail",
        "provider_type": "imap_smtp",
        "imap_host": "imap.fastmail.com", "imap_port": 993,
        "smtp_host": "smtp.fastmail.com", "smtp_port": 465,
        "use_ssl": True, "starttls": False,
        "auth": "app_password",
        "notes": "Requires an app password.",
    },
    "gmx": {
        "label": "GMX",
        "provider_type": "imap_smtp",
        "imap_host": "imap.gmx.com", "imap_port": 993,
        "smtp_host": "mail.gmx.com", "smtp_port": 587,
        "use_ssl": True, "starttls": True,
        "auth": "password",
        "notes": "Enable IMAP/POP access in GMX settings.",
    },
    "aol": {
        "label": "AOL Mail",
        "provider_type": "imap_smtp",
        "imap_host": "imap.aol.com", "imap_port": 993,
        "smtp_host": "smtp.aol.com", "smtp_port": 465,
        "use_ssl": True, "starttls": False,
        "auth": "app_password",
        "notes": "Requires an App Password.",
    },
    "yandex": {
        "label": "Yandex Mail",
        "provider_type": "imap_smtp",
        "imap_host": "imap.yandex.com", "imap_port": 993,
        "smtp_host": "smtp.yandex.com", "smtp_port": 465,
        "use_ssl": True, "starttls": False,
        "auth": "app_password",
        "notes": "Enable IMAP; use an app password.",
    },
    "custom": {
        "label": "Custom IMAP/SMTP",
        "provider_type": "imap_smtp",
        "imap_host": "", "imap_port": 993,
        "smtp_host": "", "smtp_port": 465,
        "use_ssl": True, "starttls": False,
        "auth": "password",
        "notes": "Enter your provider's IMAP/SMTP settings manually.",
    },
}


def list_presets() -> list[dict]:
    """Serialized presets for the UI dropdown (no secrets involved)."""
    out = []
    for key, p in PRESETS.items():
        entry = {"key": key}
        entry.update(p)
        out.append(entry)
    return out


def get_preset(key: str) -> dict | None:
    return PRESETS.get(key)
