import os
import json
import requests
from abc import ABC, abstractmethod

PROVIDER_MODELS = {
    "claude": [
        "claude-haiku-4-5",   # cheap & fast
        "claude-sonnet-5",
        "claude-opus-4-8",
    ],
    "openai": ["gpt-4o-mini", "gpt-4o"],
    "ollama": ["llama3", "mistral", "gemma2"],
}

# Human-readable labels shown in the UI model picker
MODEL_LABELS = {
    "claude-haiku-4-5": "Haiku 4.5 — cheap & fast",
    "claude-sonnet-5":  "Sonnet 5",
    "claude-opus-4-8":  "Opus 4.8 — most capable",
    "gpt-4o-mini":      "GPT-4o mini — cheap & fast",
    "gpt-4o":           "GPT-4o",
}


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """
        Returns:
            {
                "content": list of content blocks,
                "stop_reason": str,
            }
        """
        ...


class _ContentBlock:
    """Normalized content block so agent_core works identically across providers."""
    def __init__(self, type: str, text: str = "", name: str = "",
                 input: dict = None, id: str = ""):
        self.type = type
        self.text = text
        self.name = name
        self.input = input or {}
        self.id = id


class ClaudeProvider(LLMProvider):
    def __init__(self, model: str = "claude-haiku-4-5", api_key: str | None = None):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        self.model = model

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        kwargs = dict(model=self.model, max_tokens=4096, messages=messages)
        if tools:
            kwargs["tools"] = tools
        response = self.client.messages.create(**kwargs)

        content = []
        for block in response.content:
            if block.type == "text":
                content.append(_ContentBlock(type="text", text=block.text))
            elif block.type == "tool_use":
                content.append(_ContentBlock(
                    type="tool_use",
                    name=block.name,
                    input=block.input,
                    id=block.id,
                ))
        return {"content": content, "stop_reason": response.stop_reason}


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4o-mini", api_key: str | None = None):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model

    def _to_openai_tools(self, tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        kwargs = dict(model=self.model, messages=messages)
        if tools:
            kwargs["tools"] = self._to_openai_tools(tools)
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        stop_reason = "end_turn"
        content = []

        if msg.tool_calls:
            stop_reason = "tool_use"
            for tc in msg.tool_calls:
                content.append(_ContentBlock(
                    type="tool_use",
                    name=tc.function.name,
                    input=json.loads(tc.function.arguments),
                    id=tc.id,
                ))
        elif msg.content:
            content.append(_ContentBlock(type="text", text=msg.content))

        return {"content": content, "stop_reason": stop_reason}


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "llama3",
                 base_url: str | None = None):
        self.model = model
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                    },
                }
                for t in tools
            ]

        resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        msg = data.get("message", {})
        stop_reason = "end_turn"
        content = []

        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            stop_reason = "tool_use"
            for tc in tool_calls:
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                content.append(_ContentBlock(
                    type="tool_use",
                    name=fn.get("name", ""),
                    input=args,
                    id=tc.get("id", f"ollama-{fn.get('name','')}"),
                ))
        else:
            text = msg.get("content", "")
            if text:
                content.append(_ContentBlock(type="text", text=text))

        return {"content": content, "stop_reason": stop_reason}


def get_provider(provider_name: str, model: str, **kwargs) -> LLMProvider:
    providers = {
        "claude": ClaudeProvider,
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
    }
    cls = providers.get(provider_name)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider_name}. Choose from: {list(providers)}")
    return cls(model=model, **kwargs)
