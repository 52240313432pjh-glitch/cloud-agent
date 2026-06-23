"""Milvus-backed cross-session conversation history memory."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

COLLECTION_NAME = "conversation_history_memory"
MAX_CONTENT_LENGTH = 2048
MAX_QUESTION_LENGTH = 512
MAX_ANSWER_SUMMARY_LENGTH = 1536
MIN_QUESTION_LENGTH = 4
MIN_ANSWER_LENGTH = 20


class ConversationHistoryMemory:
    """Stores searchable conversation snippets for cross-session recall."""

    def __init__(
        self,
        embedding_model: str,
        embedding_dim: int,
        host: str = "localhost",
        port: int = 19530,
        api_key: str | None = None,
        embedding_api_key: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._api_key = api_key
        self._embedding_api_key = embedding_api_key
        self._embedding_model = embedding_model
        self._embedding_dim = embedding_dim
        self._client: Any = None
        self._embeddings: Any = None
        self._available = False

    async def initialize(self) -> None:
        try:
            from langchain_community.embeddings import DashScopeEmbeddings
            from pymilvus import MilvusClient

            connect_kwargs: dict[str, Any] = {
                "uri": f"http://{self._host}:{self._port}"
            }
            if self._api_key:
                connect_kwargs["token"] = self._api_key

            self._client = MilvusClient(**connect_kwargs)
            self._embeddings = DashScopeEmbeddings(
                model=self._embedding_model,
                dashscope_api_key=self._embedding_api_key,
            )
            self._ensure_collection()
            self._available = True
            logger.info(
                "ConversationHistoryMemory: Milvus connected at %s:%s",
                self._host,
                self._port,
            )
        except Exception as exc:
            logger.warning(
                "ConversationHistoryMemory: unavailable (%s), history memory disabled.",
                exc,
            )
            self._available = False

    async def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass

    async def save_history(
        self,
        user_id: str,
        session_id: str,
        question: str,
        answer_summary: str,
    ) -> bool:
        if not self._available or not self._is_valid_history(question, answer_summary):
            return False

        question = question.strip()[:MAX_QUESTION_LENGTH]
        answer_summary = answer_summary.strip()[:MAX_ANSWER_SUMMARY_LENGTH]
        content = f"用户曾询问：{question}\n系统回答要点：{answer_summary}"
        content = content[:MAX_CONTENT_LENGTH]

        try:
            embedding = await self._embeddings.aembed_query(content)
            self._client.insert(
                collection_name=COLLECTION_NAME,
                data=[
                    {
                        "user_id": user_id,
                        "session_id": session_id,
                        "content": content,
                        "question": question,
                        "answer_summary": answer_summary,
                        "created_at": int(time.time()),
                        "embedding": embedding,
                    }
                ],
            )
            self._client.flush(collection_name=COLLECTION_NAME)
            print(
                f"[ConversationHistoryMemory] saved history for {user_id} {session_id}"
            )
            return True
        except Exception as exc:
            logger.error("ConversationHistoryMemory.save_history failed: %s", exc)
            return False

    async def retrieve_relevant(
        self,
        user_id: str,
        query: str,
        current_session_id: str | None = None,
        top_k: int = 3,
    ) -> list[str]:
        if not self._available or not query.strip():
            return []

        safe_user = self._escape_filter_value(user_id)
        filter_expr = f'user_id == "{safe_user}"'
        if current_session_id:
            safe_session = self._escape_filter_value(current_session_id)
            filter_expr += f' and session_id != "{safe_session}"'

        try:
            query_embedding = await self._embeddings.aembed_query(query.strip())
            results = self._client.search(
                collection_name=COLLECTION_NAME,
                data=[query_embedding],
                filter=filter_expr,
                limit=top_k,
                output_fields=["content", "question", "answer_summary", "session_id"],
            )
            history: list[str] = []
            for hits in results:
                for hit in hits:
                    content = hit.get("entity", {}).get("content", "")
                    if content:
                        history.append(content)
            return history
        except Exception as exc:
            logger.error("ConversationHistoryMemory.retrieve_relevant failed: %s", exc)
            return []

    @property
    def available(self) -> bool:
        return self._available

    def _ensure_collection(self) -> None:
        from pymilvus import DataType

        if self._client.has_collection(COLLECTION_NAME):
            return

        schema = self._client.create_schema()
        schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field("user_id", DataType.VARCHAR, max_length=128)
        schema.add_field("session_id", DataType.VARCHAR, max_length=128)
        schema.add_field("content", DataType.VARCHAR, max_length=MAX_CONTENT_LENGTH)
        schema.add_field("question", DataType.VARCHAR, max_length=MAX_QUESTION_LENGTH)
        schema.add_field(
            "answer_summary",
            DataType.VARCHAR,
            max_length=MAX_ANSWER_SUMMARY_LENGTH,
        )
        schema.add_field("created_at", DataType.INT64)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=self._embedding_dim)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            "embedding",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            params={"nlist": 128},
        )

        self._client.create_collection(
            collection_name=COLLECTION_NAME,
            schema=schema,
            index_params=index_params,
        )
        logger.info(
            "ConversationHistoryMemory: created Milvus collection '%s'",
            COLLECTION_NAME,
        )

    @staticmethod
    def _is_valid_history(question: str, answer_summary: str) -> bool:
        question = question.strip()
        answer_summary = answer_summary.strip()
        if len(question) < MIN_QUESTION_LENGTH or len(answer_summary) < MIN_ANSWER_LENGTH:
            return False
        invalid_markers = (
            "请求失败",
            "请检查后端服务",
            "Traceback",
            "Error",
            "Exception",
        )
        return not any(marker in answer_summary for marker in invalid_markers)

    @staticmethod
    def _escape_filter_value(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')
