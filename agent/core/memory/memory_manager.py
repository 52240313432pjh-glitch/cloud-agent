"""协调短期和长期存储的统一内存管理器。

MemoryManager 是代理框架中所有内存操作的单一入口点。它委托给：

- :class:`ShortTermMemory`     – Redis，基于 TTL 的近期对话历史
- :class:`LongTermMemory`      – Milvus，基于向量的用户偏好/事实
- :class:`PreferenceExtractor` – 基于 LLM 的提取（在会话结束时注入）

当它们的服务不可用时，这两种存储后端都会优雅地降级。

会话生命周期
-----------------
1. **新会话，首次查询** – 调用 ``load_preferences(user_id)`` 从 Milvus 获取
   所有存储的偏好（缓存在调用者中）。
2. **每个查询轮次** – 调用 ``save_conversation(user_id, session_id, msgs)``
   将最近的消息持久化到 Redis。
3. **会话结束** – 调用 ``finalize_session(user_id, session_id, llm)``
   通过 LLM 提取偏好，保存到 Milvus，并清除 Redis。
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

from .short_term import ShortTermMemory
from .long_term import LongTermMemory
from .conversation_history import ConversationHistoryMemory
from .preference_extractor import PreferenceExtractor

logger = logging.getLogger(__name__)

_TOP_K_PREFERENCES = 20   # max preferences to retrieve per user
_MAX_HISTORY_TURNS = 20   # max conversation turns used for extraction
_RECENT_CONTEXT_MESSAGES = 6
_SUMMARY_TRIGGER_MESSAGES = 8
_SUMMARY_MAX_CHARS = 800
_TOP_K_RELATED_HISTORY = 3
_HISTORY_SUMMARY_MAX_CHARS = 700
_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v2")

@dataclass
class LayeredMemoryContext:
    context: str
    summary: str
    preferences: list[str]
    related_history: list[str]
    recent_messages: list[dict[str, Any]]


class MemoryManager:
    """协调短期 Redis 内存和长期 Milvus 内存。

    参数：
        redis_url: Redis 连接 URL。
        redis_ttl: 短期内存 TTL 秒数（默认 30 分钟）。
        milvus_host: Milvus 服务器主机名。
        milvus_port: Milvus 服务器端口。
        milvus_api_key: 可选的 Milvus 身份验证令牌。
        embedding_api_key: 用于 Milvus 嵌入的 DashScope API 密钥。

    示例::

        memory = MemoryManager(embedding_api_key="sk-...")
        await memory.initialize()

        # 每个查询轮次:
        await memory.save_conversation(user_id, session_id, messages)

        # 新会话 – 加载一次并缓存:
        prefs = await memory.load_preferences(user_id)

        # 会话结束:
        await memory.finalize_session(user_id, session_id, llm=chat_model)

        await memory.close()
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        redis_ttl: int = 1800,
        milvus_host: str = "localhost",
        milvus_port: int = 19530,
        milvus_api_key: str | None = None,
        embedding_api_key: str | None = None,
        embedding_model: str = _EMBEDDING_MODEL,
        embedding_dim: int = 1536,
    ) -> None:
        self.short_term = ShortTermMemory(redis_url=redis_url, ttl=redis_ttl)
        self.long_term = LongTermMemory(
            host=milvus_host,
            port=milvus_port,
            api_key=milvus_api_key,
            embedding_api_key=embedding_api_key,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
        )
        self.conversation_history = ConversationHistoryMemory(
            host=milvus_host,
            port=milvus_port,
            api_key=milvus_api_key,
            embedding_api_key=embedding_api_key,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Initialize both storage backends concurrently."""
        import asyncio

        await asyncio.gather(
            self.short_term.initialize(),
            self.long_term.initialize(),
            self.conversation_history.initialize(),
            return_exceptions=True,
        )
        logger.info(
            "MemoryManager ready – short_term=%s, long_term=%s",
            "✓" if self.short_term.available else "✗ (disabled)",
            "✓" if self.long_term.available else "✗ (disabled)",
        )

    async def close(self) -> None:
        """Close both storage backends."""
        import asyncio

        await asyncio.gather(
            self.short_term.close(),
            self.long_term.close(),
            self.conversation_history.close(),
            return_exceptions=True,
        )
        logger.info("MemoryManager closed")

    # ------------------------------------------------------------------
    # Per-turn operations
    # ------------------------------------------------------------------

    async def save_conversation(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        llm: Any | None = None,
    ) -> None:
        """Persist conversation messages to short-term (Redis) memory.

        Messages are appended to existing history. Only non-system messages
        are stored. Redis applies TTL automatically. When the message count
        exceeds the threshold, older messages are trimmed.

        Args:
            user_id: User identifier.
            session_id: Session identifier.
            messages: List of dicts with ``role`` and ``content`` keys.
        """
        non_system = [m for m in messages if m.get("role") != "system"]
        # Append to existing history instead of overwriting
        existing = await self.short_term.get_messages(user_id, session_id)
        combined = existing + non_system
        await self._save_conversation_history(
            user_id=user_id,
            session_id=session_id,
            messages=non_system,
            llm=llm,
        )

        if llm is not None and len([m for m in combined if m.get("role") != "system"]) > _SUMMARY_TRIGGER_MESSAGES:
            summary_saved = await self._update_session_summary(
                user_id=user_id,
                session_id=session_id,
                messages=combined,
                llm=llm,
            )
            if summary_saved:
                logger.debug(
                    "[MEMORY] Summarized session and kept recent messages for %s:%s",
                    user_id,
                    session_id,
                )
                return

        await self.short_term.save_messages(user_id, session_id, combined)
        logger.debug(
            "[MEMORY] Appended %d messages (total %d) for %s:%s",
            len(non_system), len(combined), user_id, session_id,
        )

    async def get_recent_messages(
        self, user_id: str, session_id: str
    ) -> list[dict[str, Any]]:
        """Return recent conversation messages from Redis.

        Args:
            user_id: User identifier.
            session_id: Session identifier.

        Returns:
            List of message dicts (may be empty if Redis is unavailable).
        """
        return await self.short_term.get_messages(user_id, session_id)

    async def get_layered_context(
        self,
        user_id: str,
        session_id: str,
        query: str,
        top_k_preferences: int = 3,
        top_k_history: int = _TOP_K_RELATED_HISTORY,
    ) -> LayeredMemoryContext:
        """Build L1/L2/L3 memory context for the current turn.

        L1: recent raw messages from Redis.
        L2: session summary from Redis.
        L3: relevant long-term preferences from Milvus.
        """
        summary = ""
        recent_messages: list[dict[str, Any]] = []
        preferences: list[str] = []
        related_history: list[str] = []

        if self.short_term.available:
            summary = await self.short_term.get_summary(user_id, session_id)
            history = await self.short_term.get_messages(user_id, session_id)
            non_system = [m for m in history if m.get("role") != "system"]
            recent_messages = non_system[-_RECENT_CONTEXT_MESSAGES:]

        if self.long_term.available:
            preferences = await self.load_preferences(
                user_id=user_id,
                query=query,
                top_k=top_k_preferences,
            )

        if self.conversation_history.available:
            related_history = await self.conversation_history.retrieve_relevant(
                user_id=user_id,
                query=query,
                current_session_id=session_id,
                top_k=top_k_history,
            )

        parts: list[str] = []
        if summary:
            parts.append("【会话摘要】")
            parts.append(summary)

        if preferences:
            parts.append("\n【长期用户偏好】")
            parts.extend(f"- {item}" for item in preferences)

        if related_history:
            parts.append("\n【跨会话相关历史】")
            parts.extend(f"- {item}" for item in related_history)

        if recent_messages:
            parts.append("\n【最近对话】")
            for msg in recent_messages:
                role = "User" if msg.get("role") == "user" else "Assistant"
                parts.append(f"{role}: {msg.get('content', '')}")

        return LayeredMemoryContext(
            context="\n".join(parts),
            summary=summary,
            preferences=preferences,
            related_history=related_history,
            recent_messages=recent_messages,
        )

    async def _save_conversation_history(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        llm: Any | None,
    ) -> None:
        if not self.conversation_history.available or len(messages) < 2:
            return

        question = ""
        answer = ""
        for msg in messages:
            if msg.get("role") == "user" and not question:
                question = str(msg.get("content", "")).strip()
            elif msg.get("role") == "assistant":
                answer = str(msg.get("content", "")).strip()

        if not question or not answer:
            return

        answer_summary = await self._summarize_history_answer(
            question=question,
            answer=answer,
            llm=llm,
        )
        if not answer_summary:
            return

        await self.conversation_history.save_history(
            user_id=user_id,
            session_id=session_id,
            question=question,
            answer_summary=answer_summary,
        )

    async def _summarize_history_answer(
        self,
        question: str,
        answer: str,
        llm: Any | None,
    ) -> str:
        if not llm:
            return answer[:_HISTORY_SUMMARY_MAX_CHARS]

        prompt = f"""请把下面这一轮客服对话压缩成可用于跨会话召回的历史片段。
要求：
- 只保留用户问题、业务事实、关键结论和必要条件。
- 不要加入原文没有的信息。
- 不要保留客套话、表情和无关解释。
- 控制在 {_HISTORY_SUMMARY_MAX_CHARS} 个中文字符以内。

用户问题：
{question}

客服回答：
{answer}
"""
        try:
            from langchain_core.messages import HumanMessage

            response = await llm.ainvoke([HumanMessage(content=prompt)])
            summary = str(getattr(response, "content", response)).strip()
            return summary[:_HISTORY_SUMMARY_MAX_CHARS]
        except Exception as exc:
            logger.warning("[MEMORY] History summary failed, using fallback: %s", exc)
            return answer[:_HISTORY_SUMMARY_MAX_CHARS]

    async def _update_session_summary(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        llm: Any,
    ) -> bool:
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) <= _SUMMARY_TRIGGER_MESSAGES:
            return False

        older_messages = non_system[:-_RECENT_CONTEXT_MESSAGES]
        recent_messages = non_system[-_RECENT_CONTEXT_MESSAGES:]
        if not older_messages:
            return False

        previous_summary = await self.short_term.get_summary(user_id, session_id)
        new_summary = await self._summarize_session(
            user_id=user_id,
            session_id=session_id,
            previous_summary=previous_summary,
            messages=older_messages,
            llm=llm,
        )
        if not new_summary:
            return False

        await self.short_term.save_summary(user_id, session_id, new_summary)
        await self.short_term.save_messages(user_id, session_id, recent_messages)
        return True

    async def _summarize_session(
        self,
        user_id: str,
        session_id: str,
        previous_summary: str,
        messages: list[dict[str, Any]],
        llm: Any,
    ) -> str:
        conversation_text = "\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')}" for m in messages
        )
        prompt = f"""请把以下会话信息压缩成一段面向客服 Agent 的会话摘要。

要求：
- 保留用户当前目标、已确认事实、偏好、约束、尚未解决的问题。
- 删除寒暄、重复表达和无关细节。
- 不要编造原文没有的信息。
- 控制在 {_SUMMARY_MAX_CHARS} 个中文字符以内。

已有摘要：
{previous_summary or "暂无"}

需要合并进摘要的较早对话：
{conversation_text}
"""
        try:
            from langchain_core.messages import HumanMessage

            response = await llm.ainvoke([HumanMessage(content=prompt)])
            summary = str(getattr(response, "content", response)).strip()
            if len(summary) > _SUMMARY_MAX_CHARS:
                summary = summary[:_SUMMARY_MAX_CHARS]
            return summary
        except Exception as exc:
            logger.warning("[MEMORY] Session summary update failed for %s:%s: %s", user_id, session_id, exc)
            return ""

    # ------------------------------------------------------------------
    # Long-term preference operations
    # ------------------------------------------------------------------

    async def load_preferences(
        self,
        user_id: str,
        query: str = "用户偏好习惯个性特点",
        top_k: int = 3,
    ) -> list[str]:
        """Retrieve relevant preferences for a user from Milvus.

        Uses the caller-supplied query for semantic search so that the
        most contextually relevant preferences are returned first.
        Intended to be called once per new session (on the user's first
        query) and then cached by the caller.

        Args:
            user_id: User identifier.
            query: Semantic search query (use the user's first question
                   for best relevance).  Defaults to a broad Chinese phrase
                   that covers all preference types.
            top_k: Maximum number of preferences to return (default 3).

        Returns:
            List of preference strings (may be empty if Milvus unavailable).
        """
        if not self.long_term.available:
            logger.debug("[MEMORY] load_preferences skipped: Milvus unavailable")
            return []
        try:
            result = await self.long_term.retrieve_relevant(
                user_id=user_id,
                query=query,
                top_k=top_k,
            )
            logger.debug(
                "[MEMORY] load_preferences user='%s' query='%s' top_k=%d → %d results: %s",
                user_id, query[:40], top_k, len(result), result,
            )
            return result
        except Exception as exc:
            logger.warning("load_preferences failed for %s: %s", user_id, exc)
            return []

    async def save_preference(self, user_id: str, preference_type: str, value: str) -> None:
        """Manually store a single user preference.
    
        Args:
            user_id: User identifier.
            preference_type: Category label (e.g. ``"language"``)
            value: Preference value (e.g. ``"Chinese"``)
        """
        await self.long_term.save_preference(user_id, preference_type, value)
    
    async def background_extract(
        self, user_id: str, session_id: str, llm: Any
    ) -> list[str]:
        """Silently extract and save preferences without clearing Redis.
    
        Unlike ``finalize_session``, this method is designed to be called
        periodically during an active session (e.g., every N turns). It
        extracts new preferences from current Redis history and persists
        them to Milvus but leaves Redis intact so the session continues.
    
        Args:
            user_id: User identifier.
            session_id: Session identifier.
            llm: LangChain-compatible chat model for preference extraction.
        """
        if not self.long_term.available:
            return
        if not user_id or not session_id:
            return
    
        messages = await self.short_term.get_messages(user_id, session_id)
        if len(messages) < 4:  # need at least 2 full turns
            return
    
        recent = messages[-_MAX_HISTORY_TURNS:]
        conversation_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in recent
        )
    
        try:
            extractor = PreferenceExtractor(llm=llm)
            existing = await self.load_preferences(user_id)
            new_items = await extractor.extract(
                conversation_text=conversation_text,
                existing=existing,
            )
            for item in new_items:
                await self.long_term.save_memory(
                    user_id=user_id,
                    content=item,
                    memory_type="preference",
                )
            if new_items:
                logger.info(
                    "[MEMORY] Background extract: saved %d new prefs for user '%s': %s",
                    len(new_items), user_id, new_items,
                )
                # Invalidate preference cache so next turn reloads fresh data
                return new_items
            else:
                logger.debug(
                    "[MEMORY] Background extract: no new prefs for user '%s'", user_id
                )
        except Exception as exc:
            logger.warning("[MEMORY] Background extract failed for %s: %s", user_id, exc)
    
        return []

    # ------------------------------------------------------------------
    # Session finalization
    # ------------------------------------------------------------------

    async def finalize_session(
        self, user_id: str, session_id: str, llm: Any
    ) -> None:
        """Finalize a session: extract preferences then clean up.

        Workflow:
        1. Read recent messages from Redis.
        2. Build conversation text from the last ``_MAX_HISTORY_TURNS`` turns.
        3. Use LLM (via :class:`PreferenceExtractor`) to extract new preferences.
        4. Load existing preferences from Milvus for deduplication.
        5. Save only genuinely new items to Milvus.
        6. Clear Redis short-term memory for this session.

        Args:
            user_id: User identifier.
            session_id: Session identifier.
            llm: LangChain-compatible chat model used for preference extraction.
        """
        if not user_id or not session_id:
            return

        # 1. Load recent conversation from Redis
        messages = await self.short_term.get_messages(user_id, session_id)
        if len(messages) < 2:
            logger.debug("Session too short, skipping extraction: %s:%s", user_id, session_id)
            await self.short_term.clear(user_id, session_id)
            return

        logger.info(
            "[MEMORY] Finalizing session %s:%s – %d messages in Redis history",
            user_id, session_id, len(messages),
        )

        # 2. Build conversation text (bounded to last N turns)
        recent = messages[-_MAX_HISTORY_TURNS:]
        conversation_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in recent
        )
        logger.debug(
            "[MEMORY] Conversation text sent to extractor (%d chars):\n%s",
            len(conversation_text), conversation_text[:600],
        )

        # 3. Extract preferences (LLM call)
        if self.long_term.available:
            extractor = PreferenceExtractor(llm=llm)
            existing = await self.load_preferences(user_id)
            logger.debug(
                "[MEMORY] Existing preferences (%d) for dedup: %s",
                len(existing), existing,
            )
            new_items = await extractor.extract(
                conversation_text=conversation_text,
                existing=existing,
            )

            # 4. Persist new items to Milvus
            for item in new_items:
                await self.long_term.save_memory(
                    user_id=user_id,
                    content=item,
                    memory_type="preference",
                )

            if new_items:
                logger.info(
                    "[MEMORY] Saved %d new preferences for user '%s': %s",
                    len(new_items), user_id, new_items,
                )
            else:
                logger.info("[MEMORY] No new preferences found for user '%s'", user_id)
        else:
            logger.info("[MEMORY] Milvus unavailable, skipping preference extraction")

        # 5. Clear Redis
        await self.short_term.clear(user_id, session_id)
        logger.info("[MEMORY] Short-term memory cleared for %s:%s", user_id, session_id)
