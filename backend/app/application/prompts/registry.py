"""Prompt registry — the single catalog of versioned prompts.

Every prompt used on the request path has a stable version id that the agent
writes into state and the trace (FR-19), so any run can be traced back to the
exact prompt text that produced it. Registering these with MLflow at startup is a
best-effort adapter step; the versions themselves are the source of truth here.
"""

from __future__ import annotations

from app.application.prompts.clarify import CLARIFY_VERSION
from app.application.prompts.explanation import EXPLANATION_VERSION
from app.application.prompts.sql_generation import SQL_GENERATION_VERSION
from app.application.services.eval_service import FAITHFULNESS_VERSION

# name -> version. The repair path reuses the sql-generation prompt (with the DB
# error appended), and verify is rule-based, so those don't add rows here.
PROMPT_VERSIONS: dict[str, str] = {
    "sql_generation": SQL_GENERATION_VERSION,
    "explanation": EXPLANATION_VERSION,
    "clarify": CLARIFY_VERSION,
    "faithfulness_judge": FAITHFULNESS_VERSION,
}
