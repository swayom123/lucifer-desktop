"""Small provider-neutral JSON client for action plans, answers and source generation.

The providers receive user requests and relevant search/source/diagnostic context. API keys
are read from the environment and are never included in exceptions, logs or Result messages.
"""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_PROMPT_CHARS = 250_000
MAX_PROVIDER_RESPONSE_BYTES = 2_000_000


class LLMError(RuntimeError):
    """A provider failed without exposing its response body or credentials."""


class LLMClient:
    def __init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "groq").casefold()
        self.groq_key = os.getenv("GROQ_API_KEY", "")
        self.gemini_key = os.getenv("GEMINI_API_KEY", "")
        self.groq_model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    def generate_program(self, request: str, language: str, repair_context: str = "") -> dict:
        prompt = _program_prompt(request, language, repair_context)
        return self.complete_json(prompt)

    @property
    def available(self) -> bool:
        return bool(self.groq_key or self.gemini_key)

    def complete_json(self, prompt: str) -> dict:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
            raise LLMError("AI request exceeded the local size limit.")
        providers = (self.provider, "gemini" if self.provider == "groq" else "groq")
        errors = []
        for provider in providers:
            try:
                if provider == "groq" and self.groq_key:
                    return _parse_json(self._groq(prompt))
                if provider == "gemini" and self.gemini_key:
                    return _parse_json(self._gemini(prompt))
            except LLMError as error:
                errors.append(str(error))
        if not self.groq_key and not self.gemini_key:
            raise LLMError("No AI API key is configured in .env.")
        raise LLMError(
            "AI request failed. Check the provider key, free-tier quota and network connection."
        )

    def _groq(self, prompt: str) -> str:
        body = {
            "model": self.groq_model,
            "messages": [
                {"role": "system", "content": "Return only the requested JSON object."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.15,
            "max_completion_tokens": 5000,
            "response_format": {"type": "json_object"},
        }
        response = _post_json(
            "https://api.groq.com/openai/v1/chat/completions",
            body,
            {"Authorization": f"Bearer {self.groq_key}"},
        )
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMError("Groq returned an invalid coding response.") from error

    def _gemini(self, prompt: str) -> str:
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.15, "responseMimeType": "application/json"},
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_key}"
        response = _post_json(url, body, {})
        try:
            return response["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMError("Gemini returned an invalid coding response.") from error


def _post_json(url: str, body: dict, extra_headers: dict[str, str]) -> dict:
    payload = json.dumps(body).encode("utf-8")
    # Groq's edge rejects Python's default urllib user agent with a 403; identify the
    # client explicitly without ever putting credentials in the user-agent.
    headers = {"Content-Type": "application/json", "User-Agent": "curl/8.0", **extra_headers}
    request = Request(url, data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=60) as response:
            content = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
        if len(content) > MAX_PROVIDER_RESPONSE_BYTES:
            raise LLMError("Provider response exceeded the local size limit.")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise LLMError("Provider returned an invalid response.")
        return parsed
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        raise LLMError("Provider request failed.") from error


def _parse_json(content: str) -> dict:
    if not isinstance(content, str):
        raise LLMError("Provider returned invalid JSON text.")
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise LLMError("Provider returned invalid JSON.") from error
    if not isinstance(result, dict):
        raise LLMError("Provider returned an invalid coding object.")
    return result


def _program_prompt(request: str, language: str, repair_context: str) -> str:
    repair = (
        f"\nRepair this compiler output from the previous attempt:\n{repair_context}"
        if repair_context
        else ""
    )
    return f"""Create a small educational program for this request: {request}
Language: {language}
Return exactly one JSON object with these keys:
{{"project_name":"Title Case words", "file_name":"Relevant_Name.{_extension(language)}", "code":"complete source", "summary":"one sentence"}}
Rules: code must be a single self-contained source file; use standard-library features only;
include a main entry point; write clear comments; don't read files, write files, access the
network, spawn processes, invoke shells, use eval/exec, or include destructive operations.
The filename must contain only letters, digits, underscores and the correct extension.
Do not include Markdown fences or any key besides the four requested keys.{repair}"""


def _extension(language: str) -> str:
    return {"c": "c", "c++": "cpp", "cpp": "cpp", "python": "py", "javascript": "js"}.get(
        language.casefold(), "txt"
    )
