import random
import requests

from agent.classes import Identity

API_ENDPOINT = "https://generate-random.org/api/v1/generate/persons"


def generate_identity(locale: str = "en_US", gender: str | None = None,
                      include_financial: bool = True,
                      age_min: int = 18, age_max: int = 80) -> Identity:
    """Generate a fake persona via generate-random.org.

    Returns an Identity with verification_num=1 on success, 0 on any failure.
    """
    obj = Identity()
    params = {
        "count": 1,
        "locale": locale,
        "age_min": age_min,
        "age_max": age_max,
        "include_financial": str(include_financial).lower(),
        "include_professional": "true",
    }
    if gender in ("male", "female"):
        params["gender"] = gender

    try:
        resp = requests.get(API_ENDPOINT, params=params, timeout=10)
    except requests.RequestException:
        obj.verification_num = 0
        return obj

    if resp.status_code != 200:
        obj.verification_num = 0
        return obj

    try:
        payload = resp.json()
    except ValueError:
        obj.verification_num = 0
        return obj

    if not payload.get("success") or not payload.get("data"):
        obj.verification_num = 0
        return obj

    p = payload["data"][0]

    obj.first_name = p.get("first_name", "")
    obj.last_name = p.get("last_name", "")
    obj.name = f"{obj.first_name} {obj.last_name}".strip()
    obj.email = p.get("email", "")
    obj.phone_number = p.get("phone", "")
    obj.age = str(p.get("age", ""))
    obj.birth = p.get("birth_date", "")
    obj.gender = p.get("gender", "")
    obj.country = p.get("country", "")
    obj.city = p.get("city", "")
    obj.state = p.get("state") or ""
    obj.post_code = p.get("post_code", "")
    obj.ssn = p.get("ssn", "")
    obj.company = p.get("company", "")
    obj.job_title = p.get("job_title", "")

    # Compose a full address string
    parts = [p.get("street_address", ""), p.get("secondary_address") or ""]
    city_line = ", ".join(x for x in [p.get("city", ""), p.get("state") or "", p.get("post_code", "")] if x)
    parts.append(city_line)
    parts.append(p.get("country", ""))
    obj.address = "\n".join(x for x in parts if x)

    # Financial (present only when include_financial=true)
    obj.card_num = p.get("credit_card_number", "")
    obj.card_date = p.get("credit_card_expiration", "")
    obj.card_cvv = str(p.get("credit_card_cvv", "") or "")
    obj.iban = p.get("iban") or _generate_fake_iban()
    obj.bank_account = p.get("bank_account", "")
    obj.swift_bic = p.get("swift_bic", "")

    obj.verification_num = 1
    return obj


def get_details() -> Identity:
    """Backward-compatible alias used by tools.py."""
    return generate_identity()


def _generate_fake_iban() -> str:
    check = random.randint(10, 99)
    bank_code = random.randint(10000000, 99999999)
    account = random.randint(1000000000, 9999999999)
    return f"DE{check}{bank_code}{account}"
