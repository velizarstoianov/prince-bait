import contextvars

from agent.fake_personality import generate_identity
from agent.database import create_persona, add_participant

# ── Request-scoped tool context (thread_id, etc.) ──────────────────────────────
# Lets stateless execute_tool() reach the current thread without changing the
# executor signatures. Set at run_agent entry, reset in its finally block.
_current_context: contextvars.ContextVar = contextvars.ContextVar("tool_context", default=None)


def set_tool_context(ctx: dict | None):
    return _current_context.set(ctx)


def reset_tool_context(token):
    _current_context.reset(token)


def _get_context() -> dict | None:
    return _current_context.get()


# ── Tool schemas (what the LLM sees) ──────────────────────────────────────────

DETECT_BANKING_INTENT_SCHEMA = {
    "name": "detect_banking_intent",
    "description": (
        "Analyze the incoming email text and determine whether the scammer is "
        "requesting banking or financial information — such as an IBAN, bank "
        "account number, routing number, credit card number, or any financial "
        "credentials. Return your assessment."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "has_banking_intent": {
                "type": "boolean",
                "description": "True if the email is requesting financial or banking information.",
            },
            "confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Confidence level of the detection.",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of the assessment.",
            },
        },
        "required": ["has_banking_intent", "confidence", "reasoning"],
    },
}

GET_FAKE_IDENTITY_SCHEMA = {
    "name": "get_fake_identity",
    "description": (
        "Fetch a completely fake persona — name, address, phone, fake "
        "credit card number, and a fake IBAN — to give to the scammer so they "
        "cannot obtain any real victim details. Call this only when banking "
        "intent has been detected."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

GENERATE_CHARACTER_SCHEMA = {
    "name": "generate_character",
    "description": (
        "Create an ADDITIONAL supporting character to further confuse and delay "
        "the scammer — for example a lawyer, bank manager, accountant, or a "
        "skeptical relative. The character has a complete fake identity and is "
        "recorded against the current conversation thread so you can refer back "
        "to them consistently. Use this when introducing a new person into the "
        "story would buy more time or add believable friction."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "description": "The character's role, e.g. 'lawyer', 'bank_manager', 'brother'.",
            },
            "gender": {
                "type": "string",
                "enum": ["male", "female"],
                "description": "Optional gender for the generated persona.",
            },
            "locale": {
                "type": "string",
                "description": "Optional locale, e.g. 'en_US', 'de_DE'.",
            },
        },
        "required": [],
    },
}

# Add new tool schemas here; pair each with an executor below.
ALL_TOOLS = [
    DETECT_BANKING_INTENT_SCHEMA,
    GET_FAKE_IDENTITY_SCHEMA,
    GENERATE_CHARACTER_SCHEMA,
]


def execute_detect_banking_intent(input_data: dict) -> dict:
    # The LLM fills in the fields itself; we pass them straight back as the result.
    return input_data


def execute_get_fake_identity(input_data: dict) -> dict:
    identity = generate_identity()
    if identity.verification_num == 0:
        return {"error": "Could not retrieve fake identity — generate-random.org may be unavailable."}
    return {
        "name": identity.name,
        "address": identity.address,
        "phone": identity.phone_number,
        "card_number": identity.card_num,
        "iban": identity.iban,
        "birth": identity.birth,
        "company": identity.company,
    }


def execute_generate_character(input_data: dict) -> dict:
    role = (input_data.get("role") or "side_character").strip()
    gender = input_data.get("gender")
    locale = input_data.get("locale") or "en_US"

    identity = generate_identity(locale=locale, gender=gender)
    if identity.verification_num == 0:
        return {"error": "Could not generate character — generate-random.org may be unavailable."}

    persona_id = None
    ctx = _get_context()
    if ctx and ctx.get("thread_id"):
        thread_id = ctx["thread_id"]
        persona = create_persona(thread_id, identity, role=role, source="generated")
        persona_id = persona["id"]
        add_participant(
            thread_id,
            persona_id=persona_id,
            role=role,
            connection_type="side_character",
        )

    return {
        "persona_id": persona_id,
        "role": role,
        "name": identity.name,
        "email": identity.email,
        "phone": identity.phone_number,
        "company": identity.company,
        "job_title": identity.job_title,
        "iban": identity.iban,
    }


# Register new executors here by tool name.
TOOL_EXECUTORS = {
    "detect_banking_intent": execute_detect_banking_intent,
    "get_fake_identity": execute_get_fake_identity,
    "generate_character": execute_generate_character,
}


def execute_tool(name: str, input_data: dict) -> dict:
    executor = TOOL_EXECUTORS.get(name)
    if executor is None:
        return {"error": f"Unknown tool: {name}"}
    return executor(input_data)
