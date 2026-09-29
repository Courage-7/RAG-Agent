"""Conversational query transformation and contextual condensation."""

from collections.abc import Sequence

import structlog

from rag_core.models.contracts import ChatMessage, ChatModelPort, ModelRequest
from rag_core.models.profiles import ModelPurpose

logger = structlog.get_logger(__name__)

CONDENSE_PROMPT = """Given the chat history and latest user question,
rephrase the question into a standalone search query.
Rules:
1. The standalone query must be completely self-contained without needing the chat history.
2. Preserve all specific entities, technical terms, and intent from the history and question.
3. Do NOT answer the question. Only output the standalone search query.
4. If the latest question is already standalone, return it as is.
"""


async def condense_query(
    model: ChatModelPort,
    history: Sequence[ChatMessage],
    latest_query: str,
    *,
    model_alias: str = ModelPurpose.FAST_STRUCTURED.value,
) -> str:
    """Condense chat history and follow-up question into an independent retrieval query."""
    if not history:
        return latest_query

    formatted_history = "\n".join(f"{msg.role}: {msg.content}" for msg in history)
    user_prompt = (
        f"Chat History:\n{formatted_history}\n\n"
        f"Latest Question: {latest_query}\n\n"
        f"Standalone Query:"
    )

    try:
        response = await model.complete(
            ModelRequest(
                profile_alias=model_alias,
                messages=(
                    ChatMessage(role="system", content=CONDENSE_PROMPT),
                    ChatMessage(role="user", content=user_prompt),
                ),
            )
        )
        condensed = response.text.strip().strip('"').strip("'")
        if condensed:
            logger.info("query_condensed", original=latest_query, condensed=condensed)
            return condensed
    except Exception as exc:
        logger.warning("query_condense_failed", error=str(exc))

    return latest_query
