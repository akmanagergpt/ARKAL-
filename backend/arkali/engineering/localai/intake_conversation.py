from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from arkali.engineering.localai.adapter import HonestState, LocalRuntimeAdapter


class IntakeMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class IntakeGuidance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    assistant_message: str = Field(min_length=1, max_length=4000)
    questions: tuple[str, ...] = Field(default=(), max_length=3)
    proposed_goal_text: str | None = Field(default=None, max_length=12000)


def _prompt(messages: Sequence[IntakeMessage]) -> str:
    history = [{"role": item.role, "content": item.content} for item in messages]
    return """Bounded local-model guidance for natural-language product intake.

The model is ARKALI's conversational discovery layer. It may ask a small number
of BUSINESS questions and propose a production goal, but it never enqueues work,
derives the authoritative blueprint, or approves its own product.

USER EXPERIENCE RULES:
- Speak clear, natural Turkish.
- Ask only about business/domain behavior that is genuinely missing.
- NEVER ask the user to choose a programming language, framework, database,
  API style, hosting, port, architecture, or other technical implementation
  detail unless the user explicitly brought it up.
- ARKALI owns technical decisions. Default to a local web application,
  SQLite persistence, a conventional REST backend, and a simple usable
  responsive frontend unless the user explicitly requests another platform or
  technology.
- Do not ask a question merely because a technical choice is possible.
- If the user's request already specifies enough business behavior, stop asking
  questions and propose the goal immediately.
- A request such as "görev ekle, tamamla, sil, kalıcı olsun" is sufficiently
  concrete for a first production attempt.
- At most two short questions in one turn.
- If the user says "tamam", "üret", "başla", "yap", or otherwise approves the
  proposed scope, keep proposed_goal_text populated and do not ask another
  question.

GOAL RULES:
- proposed_goal_text is the exact text that will be passed unchanged to the
  deterministic Factory blueprint engine.
- Make it implementation-ready but concise.
- Include the domain resources and the requested user actions.
- Include persistence requirements when the user asks for data to survive
  refresh/restart.
- Include explicit, mechanically testable acceptance statements using numeric
  constraints so the current deterministic blueprint engine can resolve them.
- Prefer a single compact numbered list in proposed_goal_text, with each item
  containing a concrete measurable criterion such as "within 2000ms" or
  "HTTP 2xx". Do not invent business rules that the user did not ask for.
- Do not expose internal ARKALI identifiers, architecture vocabulary, or
  acceptance-engine jargon in assistant_message.

Return JSON only with keys assistant_message, questions, proposed_goal_text.
Use null for proposed_goal_text only while genuinely missing business
information. When enough is known, proposed_goal_text MUST be non-null.

Conversation:
""" + json.dumps(history, ensure_ascii=False)


def continue_intake_conversation(
    adapter: LocalRuntimeAdapter,
    model_id: str,
    messages: Sequence[IntakeMessage],
    *,
    timeout_seconds: float = 180.0,
) -> IntakeGuidance:
    if not messages or messages[-1].role != "user":
        raise ValueError("conversation must end with a user message")
    result = adapter.infer(model_id, _prompt(messages), timeout_seconds=timeout_seconds)
    if result.state is not HonestState.PASS or not result.output.strip():
        raise RuntimeError(result.detail or "local guidance did not return output")
    try:
        return IntakeGuidance.model_validate(json.loads(result.output))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError("local guidance returned an invalid structured response") from exc


__all__ = ["IntakeGuidance", "IntakeMessage", "continue_intake_conversation"]
