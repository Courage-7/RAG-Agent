"""Bounded LangGraph StateGraph implementation for Adaptive RAG."""

import re
from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import UUID

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from rag_core.models.contracts import ChatMessage, ChatModelPort, ModelRequest
from rag_core.models.profiles import ModelPurpose
from rag_core.retrieval.models import RetrievalQuery, RetrievedChunk
from rag_core.retrieval.ports import RerankerPort, RetrieverPort, WebSearchPort
from rag_core.retrieval.query_transform import condense_query
from rag_core.retrieval.service import SYSTEM_PROMPT

logger = structlog.get_logger(__name__)


class AgentState(BaseModel):
    query: str
    workspace_id: UUID
    user_id: UUID
    knowledge_base_ids: tuple[UUID, ...]
    chat_history: tuple[ChatMessage, ...] = ()
    effective_query: str = ""
    route: Literal["direct", "retrieve", "web_search"] = "retrieve"
    chunks: tuple[RetrievedChunk, ...] = ()
    web_content: str = ""
    answer: str = ""
    citations: tuple[dict[str, Any], ...] = ()
    status: str = "answered"


class AdaptiveRagGraph:
    """Bounded, stateful reasoning graph balancing local knowledge and web search."""

    def __init__(
        self,
        model: ChatModelPort,
        retriever: RetrieverPort,
        *,
        reranker: RerankerPort | None = None,
        web_search: WebSearchPort | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        self._model = model
        self._retriever = retriever
        self._reranker = reranker
        self._web_search = web_search
        self._checkpointer = checkpointer or MemorySaver()
        self._workflow = self._build_graph()

    def _build_graph(self) -> Any:
        workflow = StateGraph(AgentState)

        workflow.add_node("route_and_condense", self._route_and_condense)
        workflow.add_node("retrieve_documents", self._retrieve_documents)
        workflow.add_node("web_search_fallback", self._web_search_fallback)
        workflow.add_node("generate_answer", self._generate_answer)

        workflow.set_entry_point("route_and_condense")

        workflow.add_conditional_edges(
            "route_and_condense",
            lambda state: state.route,
            {
                "direct": "generate_answer",
                "retrieve": "retrieve_documents",
                "web_search": "web_search_fallback",
            },
        )

        workflow.add_conditional_edges(
            "retrieve_documents",
            self._decide_after_retrieval,
            {
                "web_search": "web_search_fallback",
                "synthesize": "generate_answer",
            },
        )

        workflow.add_edge("web_search_fallback", "generate_answer")
        workflow.add_edge("generate_answer", END)

        return workflow.compile(checkpointer=self._checkpointer)

    async def _route_and_condense(self, state: AgentState) -> dict[str, Any]:
        effective = state.query
        if state.chat_history:
            effective = await condense_query(
                self._model,
                state.chat_history,
                state.query,
                model_alias=ModelPurpose.FAST_STRUCTURED.value,
            )

        lower_q = effective.lower()
        if lower_q.startswith(("hi", "hello", "hey", "who are you")):
            route: Literal["direct", "retrieve", "web_search"] = "direct"
        elif any(w in lower_q for w in ("latest news", "current stock", "today's weather")):
            route = "web_search"
        else:
            route = "retrieve"

        return {"effective_query": effective, "route": route}

    async def _retrieve_documents(self, state: AgentState) -> dict[str, Any]:
        fetch_k = 16 if self._reranker is not None else 6
        query = RetrievalQuery(
            text=state.effective_query or state.query,
            workspace_id=state.workspace_id,
            user_id=state.user_id,
            knowledge_base_ids=state.knowledge_base_ids,
            top_k=fetch_k,
        )
        res = await self._retriever.retrieve(query)
        chunks = res.chunks

        if self._reranker is not None and chunks:
            reranked = await self._reranker.rerank(
                state.query,
                chunks,
                top_k=6,
            )
            chunks = tuple(reranked)

        return {"chunks": chunks}

    def _decide_after_retrieval(self, state: AgentState) -> Literal["web_search", "synthesize"]:
        if not state.chunks and self._web_search is not None:
            return "web_search"
        return "synthesize"

    async def _web_search_fallback(self, state: AgentState) -> dict[str, Any]:
        if self._web_search is None:
            return {"web_content": ""}

        results = await self._web_search.search(state.effective_query or state.query, max_results=3)
        formatted = "\n\n".join(
            f"[Web {i + 1}] {r.title} ({r.url}):\n{r.content}" for i, r in enumerate(results)
        )
        return {"web_content": formatted}

    async def _generate_answer(self, state: AgentState) -> dict[str, Any]:
        if state.route == "direct":
            resp = await self._model.complete(
                ModelRequest(
                    profile_alias=ModelPurpose.QUALITY.value,
                    messages=(
                        ChatMessage(role="system", content="You are a helpful assistant."),
                        ChatMessage(role="user", content=state.query),
                    ),
                )
            )
            return {"answer": resp.text, "status": "answered", "citations": ()}

        context_parts: list[str] = []
        chunk_map: dict[int, RetrievedChunk] = {}
        for i, chunk in enumerate(state.chunks, start=1):
            chunk_map[i] = chunk
            context_parts.append(f"[{i}] (Chunk ID: {chunk.chunk_id}):\n{chunk.content}")

        if state.web_content:
            context_parts.append(f"Web Search Results:\n{state.web_content}")

        evidence_text = "\n\n".join(context_parts)
        if not evidence_text:
            return {
                "answer": (
                    "I do not have sufficient evidence in the knowledge base or web to answer this."
                ),
                "status": "abstained",
                "citations": (),
            }

        user_content = f"Evidence Sources:\n{evidence_text}\n\nUser Question: {state.query}"
        resp = await self._model.complete(
            ModelRequest(
                profile_alias=ModelPurpose.QUALITY.value,
                messages=(
                    ChatMessage(role="system", content=SYSTEM_PROMPT),
                    ChatMessage(role="user", content=user_content),
                ),
            )
        )

        cited_ordinals = {
            int(m) for m in re.findall(r"\[(\d+)\]", resp.text) if int(m) in chunk_map
        }
        citations = [
            {
                "ordinal": ord_idx,
                "chunk_id": str(chunk_map[ord_idx].chunk_id),
                "document_id": str(chunk_map[ord_idx].document_id),
                "source_label": f"Source Chunk {ord_idx}",
            }
            for ord_idx in sorted(cited_ordinals)
        ]

        status = "answered" if (citations or state.web_content) else "abstained"
        return {"answer": resp.text, "status": status, "citations": tuple(citations)}

    async def ainvoke(
        self,
        query: str,
        *,
        workspace_id: UUID,
        user_id: UUID,
        knowledge_base_ids: tuple[UUID, ...],
        chat_history: tuple[ChatMessage, ...] = (),
        thread_id: str | None = None,
    ) -> AgentState:
        """Execute the adaptive agent graph with thread checkpointing."""
        initial_state = AgentState(
            query=query,
            workspace_id=workspace_id,
            user_id=user_id,
            knowledge_base_ids=knowledge_base_ids,
            chat_history=chat_history,
        )
        config = {"configurable": {"thread_id": thread_id or f"thread-{user_id}"}}
        final_dict = await self._workflow.ainvoke(initial_state, config=config)
        return AgentState.model_validate(final_dict)

    async def astream(
        self,
        query: str,
        *,
        workspace_id: UUID,
        user_id: UUID,
        knowledge_base_ids: tuple[UUID, ...],
        chat_history: tuple[ChatMessage, ...] = (),
        thread_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream step updates from the adaptive agent graph."""
        initial_state = AgentState(
            query=query,
            workspace_id=workspace_id,
            user_id=user_id,
            knowledge_base_ids=knowledge_base_ids,
            chat_history=chat_history,
        )
        tid = thread_id or f"thread-{user_id}"
        config = {"configurable": {"thread_id": tid}}

        async for chunk in self._workflow.astream(
            initial_state, config=config, stream_mode="updates"
        ):
            if "route_and_condense" in chunk:
                yield {"event": "routing", "data": chunk["route_and_condense"]}
            elif "retrieve_documents" in chunk:
                update = chunk["retrieve_documents"]
                raw_chunks: tuple[RetrievedChunk, ...] = update.get("chunks", ())
                chunks_list = [
                    {
                        "chunk_id": str(c.chunk_id),
                        "document_id": str(c.document_id),
                        "score": c.reranker_score or c.fused_score,
                    }
                    for c in raw_chunks
                ]
                yield {
                    "event": "retrieval",
                    "data": {"count": len(chunks_list), "chunks": chunks_list},
                }
            elif "web_search_fallback" in chunk:
                update = chunk["web_search_fallback"]
                yield {
                    "event": "web_search",
                    "data": {"content_preview": update.get("web_content", "")[:200]},
                }
            elif "generate_answer" in chunk:
                update = chunk["generate_answer"]
                yield {"event": "answer", "data": update}

        yield {"event": "done", "data": {"thread_id": tid}}
