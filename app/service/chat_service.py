import asyncio
import json
import sys
import os
import time

# 初始化 Agent 和 Graph
AGENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent")
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from core.workflow.graph_manager import AgentGraphManager
from core.memory.memory_manager import MemoryManager
from core.observability import new_trace_id, trace_log, trace_ms
from infra.cache import semantic_cache

# Global variables for graph and memory
graph = None
memory = None
memory_llm = None
mcp_manager = None
background_tasks = set()

async def init_agent_system():
    global graph, memory, memory_llm, mcp_manager
    if graph is None:
        from config import get_settings
        from core.mcp import MCPManager
        from agents.billing_agent import UserIdInjector
        settings = get_settings()

        print("初始化 MCP 工具管理器...")
        mcp_manager = MCPManager(
            settings.mcp_servers_config,
            tool_interceptors=[UserIdInjector()],
        )
        await mcp_manager.connect()

        print("🚀 初始化 Multi-Agent 图编排...")
        graph_manager = AgentGraphManager(mcp_manager=mcp_manager)
        graph = graph_manager.build_graph()
        
        print("🧠 初始化 Memory 系统...")
        memory = MemoryManager(
            redis_url=settings.redis_url,
            redis_ttl=settings.redis_ttl,
            milvus_host=settings.milvus_host,
            milvus_port=settings.milvus_port,
            milvus_api_key=settings.milvus_api_key,
            embedding_api_key=settings.dashscope_api_key,
            embedding_model=settings.embedding_model,
        )
        await memory.initialize()
        await semantic_cache.initialize()
        
        from langchain_openai import ChatOpenAI
        memory_llm = ChatOpenAI(
            api_key=settings.dashscope_api_key,
            model=settings.model,
            base_url=settings.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=0.0,
        )
        print("✅ Agent 系统初始化完成！")

async def shutdown_agent_system():
    global mcp_manager
    if mcp_manager is not None:
        await mcp_manager.close()
        mcp_manager = None

async def _extract_memory_context(user_id: str, session_id: str, query: str) -> str:
    context_parts = []
    if memory and memory.short_term.available:
        history = await memory.short_term.get_messages(user_id, session_id)
        if history:
            recent_history = history[-10:] if len(history) > 10 else history
            context_parts.append("【近期对话历史】:")
            for msg in recent_history:
                role = "User" if msg["role"] == "user" else "Assistant"
                context_parts.append(f"{role}: {msg['content']}")
    
    if memory and memory.long_term.available:
        prefs = await memory.long_term.retrieve_relevant(user_id, query)
        if prefs:
            context_parts.append("\n【用户长期偏好/背景】:")
            for p in prefs:
                context_parts.append(f"- {p}")
                
    return "\n".join(context_parts)

async def _background_extract_preferences(user_id: str, session_id: str) -> None:
    if not memory or not memory_llm or not memory.long_term.available:
        return
    try:
        new_items = await memory.background_extract(user_id, session_id, memory_llm)
        if new_items:
            print(f"🧠 [LongTermMemory] 已沉淀 {len(new_items)} 条用户偏好: {new_items}")
    except Exception as exc:
        print(f"⚠️ [LongTermMemory] 后台偏好抽取失败: {exc}")

def _schedule_preference_extraction(user_id: str, session_id: str) -> None:
    task = asyncio.create_task(_background_extract_preferences(user_id, session_id))
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

async def stream_chat(query: str, user_id: str, session_id: str):
    trace_id = new_trace_id()
    chat_start = time.perf_counter()
    trace_log(trace_id, "chat_start", user_id=user_id, session_id=session_id, query=query)

    cache_start = time.perf_counter()
    cache_hit = await semantic_cache.get_cache(query, user_id)
    if cache_hit:
        response_text = cache_hit["answer"]
        trace_log(
            trace_id,
            "cache_hit",
            user_id=user_id,
            session_id=session_id,
            latency_ms=trace_ms(cache_start),
            level=cache_hit.get("level"),
            distance=cache_hit.get("distance"),
            matched_question=cache_hit.get("matched_question"),
        )
        print(
            f"⚡ 语义缓存命中: {cache_hit['level']} distance={cache_hit['distance']:.4f} matched='{cache_hit['matched_question']}'"
        )
    else:
        print("🏃 进入 Agent 工作流推理...")
        trace_log(
            trace_id,
            "cache_miss",
            user_id=user_id,
            session_id=session_id,
            latency_ms=trace_ms(cache_start),
        )
        memory_start = time.perf_counter()
        mem_context = await _extract_memory_context(user_id, session_id, query)
        trace_log(
            trace_id,
            "memory_loaded",
            user_id=user_id,
            session_id=session_id,
            latency_ms=trace_ms(memory_start),
            context_chars=len(mem_context),
        )
        state = {
            "messages": [("user", query)],
            "user_id": user_id,
            "session_id": session_id,
            "trace_id": trace_id,
            "memory_context": mem_context,
            "next_agent": "",
            "metadata": {}
        }
        config = {"configurable": {"user_id": user_id, "trace_id": trace_id}}
        workflow_start = time.perf_counter()
        trace_log(trace_id, "workflow_start", user_id=user_id, session_id=session_id)
        result = await asyncio.to_thread(asyncio.run, graph.ainvoke(state, config=config)) if not asyncio.iscoroutinefunction(graph.ainvoke) else await graph.ainvoke(state, config=config)
        response_text = result["messages"][-1].content
        trace_log(
            trace_id,
            "workflow_end",
            user_id=user_id,
            session_id=session_id,
            latency_ms=trace_ms(workflow_start),
            response_chars=len(response_text),
        )
    
    # 保存短时记忆
    if memory and memory.short_term.available:
        save_start = time.perf_counter()
        turn = [
            {"role": "user", "content": query},
            {"role": "assistant", "content": response_text},
        ]
        await memory.save_conversation(user_id, session_id, turn)
        trace_log(
            trace_id,
            "memory_saved",
            user_id=user_id,
            session_id=session_id,
            latency_ms=trace_ms(save_start),
            messages_saved=len(turn),
        )
        _schedule_preference_extraction(user_id, session_id)
        
    # 流式返回大模型结果
    chunk_size = 5
    for i in range(0, len(response_text), chunk_size):
        chunk = response_text[i:i+chunk_size]
        yield f"data: {json.dumps({'content': chunk})}\n\n"
        await asyncio.sleep(0.02)
        
    trace_log(
        trace_id,
        "chat_end",
        user_id=user_id,
        session_id=session_id,
        latency_ms=trace_ms(chat_start),
        response_chars=len(response_text),
    )
    yield f"data: {json.dumps({'done': True})}\n\n"
