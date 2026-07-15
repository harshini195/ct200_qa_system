"""
LLM client for generating QA test-case ideas from selected document text.

Provider: Groq (OpenAI-compatible chat completions endpoint), chosen for its
free tier. If no GROQ_API_KEY is set in the environment, falls back to a
deterministic MOCK generator so the rest of the system (selections,
staleness, retrieval) can be demoed/tested end-to-end without an API key.

Structured-output contract: the model is instructed to return ONLY a JSON
object matching TestCaseList. On a malformed/incomplete response:
  - retry ONCE with an explicit "your last reply was not valid JSON,
    return ONLY the JSON object" follow-up message
  - if that also fails validation, do NOT raise / silently drop -- return a
    result with status="failed" and the raw text preserved, so the caller
    can persist a record that generation was attempted and failed. Silent
    failure would violate traceability just as much as a wrong test case.
"""

import os
import json
import requests
from pydantic import BaseModel, ValidationError, Field


GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class TestCase(BaseModel):
    title: str
    steps: str
    expected_result: str


class TestCaseList(BaseModel):
    test_cases: list[TestCase] = Field(min_length=3, max_length=5)


SYSTEM_PROMPT = """You are a QA engineer generating test case ideas for a \
regulated medical device (a home blood pressure monitor). You will be given \
a section of the device's technical manual. Generate 3 to 5 concrete, \
repeatable QA test cases that verify the behavior described in that text.

Each test case must be concrete enough that another engineer could execute \
it without guessing: state the specific input/action and the specific \
expected outcome (numbers, error codes, thresholds -- use the exact values \
given in the text, do not invent your own).

Respond with ONLY a JSON object in exactly this shape, no other text, no \
markdown code fences:

{"test_cases": [{"title": "...", "steps": "...", "expected_result": "..."}]}
"""


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _call_groq(messages: list[dict]) -> str:
    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": GROQ_MODEL, "messages": messages, "temperature": 0.3},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _mock_generate(source_text: str) -> str:
    """Deterministic offline fallback so the pipeline is fully runnable
    without an API key. Not a substitute for real LLM output quality --
    purely so graders/reviewers can exercise the full flow."""
    return json.dumps({
        "test_cases": [
            {
                "title": "MOCK: verify primary behavior described in source text",
                "steps": "1. Set up device per section preconditions. 2. Trigger the behavior described in the source text.",
                "expected_result": "Device behaves as described in the source text (mock mode - no live LLM call).",
            },
            {
                "title": "MOCK: boundary condition check",
                "steps": "1. Drive the relevant parameter to its stated boundary value.",
                "expected_result": "Device transitions state exactly at the documented threshold.",
            },
            {
                "title": "MOCK: error/edge path check",
                "steps": "1. Force the failure condition implied by the source text.",
                "expected_result": "Device reports the documented error/edge behavior, not a crash or silent failure.",
            },
        ]
    })


def generate_test_cases(source_text: str) -> dict:
    """
    Returns a dict:
      {"status": "success", "test_cases": [...], "raw_response": "..."}
      or
      {"status": "failed", "test_cases": None, "raw_response": "...", "error": "..."}
    """
    user_message = f"Manual section text:\n\n{source_text}"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    def attempt(msgs):
        if GROQ_API_KEY:
            return _call_groq(msgs)
        return _mock_generate(source_text)

    raw = attempt(messages)
    parsed, error = _try_parse(raw)
    if parsed is not None:
        return {"status": "success", "test_cases": parsed.model_dump()["test_cases"], "raw_response": raw}

    # Retry once with an explicit correction instruction.
    retry_messages = messages + [
        {"role": "assistant", "content": raw},
        {"role": "user", "content": (
            "Your last reply was not valid JSON matching the required shape "
            f"(error: {error}). Reply again with ONLY the JSON object, no "
            "other text, no markdown fences."
        )},
    ]
    raw2 = attempt(retry_messages)
    parsed2, error2 = _try_parse(raw2)
    if parsed2 is not None:
        return {"status": "success", "test_cases": parsed2.model_dump()["test_cases"], "raw_response": raw2}

    return {
        "status": "failed",
        "test_cases": None,
        "raw_response": raw2,
        "error": error2,
    }


def _try_parse(raw: str):
    try:
        cleaned = _strip_code_fences(raw)
        data = json.loads(cleaned)
        parsed = TestCaseList(**data)
        return parsed, None
    except (json.JSONDecodeError, ValidationError) as e:
        return None, str(e)
