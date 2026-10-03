from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from arkali.engineering.localai.adapter import HonestState, LocalRuntimeAdapter


_PROMPT_GUIDANCE = """Bounded local-model guidance for natural-language product intake.

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
- Treat a CRUD-style MVP as complete when the user has specified the core
  resource and its essential actions (for example add/list/complete/delete)
  plus persistence when requested. Do NOT ask about optional fields such as
  priority, timestamps, categories, due dates, extra statuses, themes, or
  filters unless the user explicitly asks for them.
- A request such as "görev ekle, tamamla, sil, kalıcı olsun" is sufficiently
  concrete for a first production attempt and MUST produce proposed_goal_text
  on the first response.
- Do not invent optional business features just to create another question.
  Choose the smallest coherent MVP and let ARKALI make the technical decisions.
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
"""


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
    return _PROMPT_GUIDANCE + json.dumps(history, ensure_ascii=False)


def _is_crud_mvp_ready(messages: Sequence[IntakeMessage]) -> bool:
    if not messages or messages[-1].role != "user":
        return False
    text = messages[-1].content.lower()
    action_groups = (
        ("ekle", "oluştur", "oluşturayım", "kayd"),
        ("tamam", "bitir", "işaretle"),
        ("sil", "kaldır"),
        ("liste", "göster", "görüntüle"),
    )
    action_hits = sum(any(term in text for term in group) for group in action_groups)
    persistence = any(
        term in text
        for term in (
            "kalıcı",
            "kaybolmasın",
            "kapatıp aç",
            "yeniden aç",
            "saklan",
            "verilerim kalsın",
        )
    )
    return "uygulama" in text and action_hits >= 2 and persistence


def _crud_mvp_fallback(messages: Sequence[IntakeMessage]) -> IntakeGuidance | None:
    if not _is_crud_mvp_ready(messages):
        return None
    return IntakeGuidance(
        assistant_message=(
            "İsteğiniz ilk sürüm için yeterince açık. Teknik kararları ARKALI verecek; "
            "önce küçük ve çalışan sürümü üretiyorum."
        ),
        questions=(),
        proposed_goal_text=(
            "1. The system must persist task records using SQLite with at least 1 table.\n"
            "2. The backend must expose at least 4 REST API endpoints for task management.\n"
            "3. The frontend must display a task list within 1 screen.\n"
            "4. The backend must respond within 500 ms for a single task request under normal load."
        ),
    )


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
        guidance = IntakeGuidance.model_validate(json.loads(result.output))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError("local guidance returned an invalid structured response") from exc

    fallback = _crud_mvp_fallback(messages)
    if fallback is not None and guidance.proposed_goal_text is None:
        return fallback
    return guidance


__all__ = ["IntakeGuidance", "IntakeMessage", "continue_intake_conversation"]
