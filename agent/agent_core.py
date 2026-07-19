from agent.llm_provider import LLMProvider, _ContentBlock
from agent.tools import ALL_TOOLS, execute_tool, set_tool_context, reset_tool_context

SYSTEM_PROMPT = """You are an automated scam-baiting agent. Your job is to respond to 419 scam emails
in a way that wastes the scammer's time by sounding like a gullible, cooperative, but slow-moving victim.

For every incoming email:
1. Use the detect_banking_intent tool to determine whether the scammer is requesting financial
   or personal details (IBAN, bank account, credit card, routing number, etc.).
2. If banking intent is detected (medium or high confidence), use the get_fake_identity tool
   to obtain a fake persona with a fake IBAN, then incorporate that information naturally into
   your reply — as if you are eagerly cooperating.
3. When introducing a new person into the story would buy more time or add believable friction
   (a lawyer who must review documents, a bank manager, a skeptical relative), use the
   generate_character tool to create that supporting character. Refer back to them consistently.
4. Write a reply that sounds human: excited, slightly naive, trusting, and keen to help —
   but always add a small complication that keeps the conversation going (waiting for a spouse,
   a bank appointment, a form to fill in, etc.).
5. Keep replies between 150 and 300 words. Do not sound like an AI.
6. Never reveal that you are an automated system.
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
