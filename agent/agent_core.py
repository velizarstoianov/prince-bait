from agent.llm_provider import LLMProvider, _ContentBlock
from agent.tools import ALL_TOOLS, execute_tool, set_tool_context, reset_tool_context

SYSTEM_PROMPT = """You are an automated scam-baiting agent. Your behavior is founded on the
established scam-baiting methodology (as documented by the 419eater community). Your purpose is
legitimate anti-fraud work: engage 419 / advance-fee scammers to waste their time so they have
less time to target real victims.

## GOALS (in priority order)
1. Consume the scammer's time and attention for as long as possible.
2. Keep the scammer believing you are a real, willing, but slow and complication-prone victim.
3. Never advance the scam toward any real-world harm.

## HARD SAFETY RULES — never violate these
- NEVER use real personal information. Every name, address, phone, email, and document you
  provide must be entirely fictional (use the get_fake_identity / generate_character tools).
- NEVER provide genuine financial account access. Any bank/IBAN/card details you give must be
  fabricated — real details would let the scammer launder money or steal.
- NEVER send real money, real valuables, or authentic identification documents.
- NEVER agree to meet a scammer in person or share a real location.
- NEVER reveal that you are an automated system or a baiter. Stay in character at all times.

## PERSONA
- Maintain a believable, consistent fictional persona with a coherent backstory (job, family,
  finances). Keep details consistent across the whole conversation thread.
- Present as eager, trusting, a little naive, and keen to cooperate — but perpetually slowed
  down by real-sounding obstacles.

## TIME-WASTING TACTICS — use these to stall without ever refusing outright
- Bureaucratic and legal friction: forms to fill in, notarization, a lawyer who must review
  everything first, compliance checks.
- Bank processing obstacles: transfer delays, holds, a manager who must approve, wrong branch.
- Life obstacles: travel, illness, a family emergency, a spouse who must be consulted.
- Verification demands: ask the scammer to prove things, resend details, confirm via extra steps.
- Small confusions and misunderstandings that require the scammer to re-explain.

## PER-MESSAGE WORKFLOW
1. Use detect_banking_intent to determine whether the scammer is requesting financial or personal
   details (IBAN, bank account, credit card, routing number, SSN, etc.).
2. If banking intent is detected (medium or high confidence), use get_fake_identity to obtain a
   fabricated persona + fake IBAN, then hand it over eagerly — but always wrapped in a delay
   ("here are my details, though my bank says the transfer may take a few days...").
3. When a new character would add believable friction or buy time (a lawyer who must review
   documents, a bank manager, a skeptical relative), use generate_character and then refer back
   to that character consistently.
4. Write a human-sounding reply: excited, cooperative, slightly naive — but always introduce at
   least one new complication or delay that keeps the thread alive.
5. Keep replies roughly 150–300 words. Do not sound like an AI. Never break character.
"""


def run_agent(
    email_text: str,
    provider: LLMProvider,
    tools: list[dict] | None = None,
    max_iterations: int = 10,
    context: dict | None = None,
    history: list[dict] | None = None,
) -> dict:
    """
    Run the agentic loop for one incoming email.

    Args:
        email_text: the latest scammer message.
        provider: an LLMProvider.
        context: optional {"thread_id": int} made available to tool executors.
        history: optional prior turns as [{"role": "user"|"assistant", "content": str}, ...].

    Returns:
        {
            "reply": str,
            "tools_called": list[dict],
            "banking_intent": bool,
            "fake_identity": dict | None,
            "characters_created": list[dict],
        }
    """
    if tools is None:
        tools = ALL_TOOLS

    tools_called: list[dict] = []
    banking_intent = False
    fake_identity: dict | None = None
    characters_created: list[dict] = []

    # Claude gets a proper system param; others get the system prompt prepended.
    use_system = hasattr(provider, "client") and hasattr(provider.client, "messages")

    base_history = list(history) if history else []
    if use_system:
        loop_messages = base_history + [{"role": "user", "content": email_text}]
    else:
        primed = f"[System]\n{SYSTEM_PROMPT}\n[End System]\n\nMessage to process:\n{email_text}"
        loop_messages = base_history + [{"role": "user", "content": primed}]

    token = set_tool_context(context)
    try:
        for _ in range(max_iterations):
            if use_system:
                response = provider.client.messages.create(
                    model=provider.model,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    tools=tools,
                    messages=loop_messages,
                )
                content = []
                for block in response.content:
                    if block.type == "text":
                        content.append(_ContentBlock(type="text", text=block.text))
                    elif block.type == "tool_use":
                        content.append(_ContentBlock(
                            type="tool_use", name=block.name, input=block.input, id=block.id,
                        ))
                stop_reason = response.stop_reason
            else:
                resp = provider.chat(messages=loop_messages, tools=tools)
                content = resp["content"]
                stop_reason = resp["stop_reason"]

            if stop_reason == "end_turn":
                return _result(_extract_text(content), tools_called, banking_intent,
                               fake_identity, characters_created)

            if stop_reason == "tool_use":
                if use_system:
                    loop_messages.append({"role": "assistant", "content": response.content})
                else:
                    assistant_content = []
                    for block in content:
                        if block.type == "tool_use":
                            assistant_content.append({
                                "type": "tool_use", "id": block.id,
                                "name": block.name, "input": block.input,
                            })
                        elif block.type == "text":
                            assistant_content.append({"type": "text", "text": block.text})
                    loop_messages.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in content:
                    if block.type != "tool_use":
                        continue
                    result = execute_tool(block.name, block.input)
                    tools_called.append({
                        "name": block.name,
                        "input": block.input,
                        "result": result,
                    })
                    if block.name == "detect_banking_intent":
                        banking_intent = result.get("has_banking_intent", False)
                    if block.name == "get_fake_identity":
                        fake_identity = result
                    if block.name == "generate_character" and "error" not in result:
                        characters_created.append(result)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })

                loop_messages.append({"role": "user", "content": tool_results})
                continue

            return _result(_extract_text(content), tools_called, banking_intent,
                           fake_identity, characters_created)

        return _result("I apologize, I was unable to generate a response at this time.",
                       tools_called, banking_intent, fake_identity, characters_created)
    finally:
        reset_tool_context(token)


def _result(reply, tools_called, banking_intent, fake_identity, characters_created) -> dict:
    return {
        "reply": reply,
        "tools_called": tools_called,
        "banking_intent": banking_intent,
        "fake_identity": fake_identity,
        "characters_created": characters_created,
    }


def _extract_text(content) -> str:
    parts = []
    for block in content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts).strip()
