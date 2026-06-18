import json
import os
from typing import Any, Dict

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agents.billing_agent import UserIdInjector
from core.workflow.state import AgentState
from tools.vector_tool import query_vector_db


class RecommendationAgent:
    """Recommend cloud products based on user requirements."""

    def __init__(self, mcp_manager=None):
        self.mcp_manager = mcp_manager

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        dotenv_path = os.path.join(project_root, ".env")
        load_dotenv(dotenv_path)

        self.llm = ChatOpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            model=os.getenv("MODEL", "qwen-plus"),
            base_url=os.getenv("BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            temperature=0.3,
        )

        agent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(agent_dir, "config", "mcp_servers.json")
        with open(config_path, "r", encoding="utf-8") as f:
            self.servers_config = json.load(f)

    async def _get_mcp_tools(self):
        target_tools = {
            "get_promotable_products",
            "search_product_catalog",
            "get_promotion_materials",
        }

        if self.mcp_manager is not None:
            return await self.mcp_manager.get_tools_by_names(target_tools)

        client = MultiServerMCPClient(
            connections=self.servers_config.get("mcpServers", {}),
            tool_interceptors=[UserIdInjector()],
        )
        all_tools = await client.get_tools()
        return [tool for tool in all_tools if tool.name in target_tools]

    async def __call__(self, state: AgentState) -> Dict[str, Any]:
        memory_context = state.get("memory_context", "")
        config = {"configurable": {"user_id": state.get("user_id", "unknown"), "trace_id": state.get("trace_id")}}

        mcp_tools = await self._get_mcp_tools()
        tools = [query_vector_db] + mcp_tools

        system_prompt = f"""You are a senior cloud architect and a recommendation agent.

Your job is to recommend suitable cloud products or instance specifications based on
the user's business scenario, budget, concurrency, region preference, and constraints.

Workflow:
1. Understand the user's requirement first. If the user only asks what products are
   available, call get_promotable_products to fetch real recommendable products.
2. If the user mentions a concrete product, specification, or scenario, call
   search_product_catalog to query the real product catalog.
3. If product features, usage scenarios, or technical specifications are needed,
   call query_vector_db to search the product knowledge base.
4. Recommendations must be based on tool results. Do not invent products, specs,
   prices, discounts, or links.
5. For final recommended products, call get_promotion_materials to obtain purchase
   or promotion links and include them in the final response.

Response rules:
- Reply in the same language as the user. If the user asks in Chinese, reply in Chinese.
- Be professional, clear, and practical.
- Explain why each recommendation fits the user's requirement.
- If tools return no matching product, say so honestly.
- At the end, list only data sources actually used, for example:
  Answer sources:
  - Vector search: xxx.md
  - Product catalog: search_product_catalog

User memory/background context:
{memory_context if memory_context else "No background context."}
"""

        inner_agent = create_react_agent(
            model=self.llm,
            tools=tools,
            prompt=system_prompt,
        )

        print("[RecommendationAgent] Running product recommendation...")

        result = await inner_agent.ainvoke(
            {"messages": state["messages"]},
            config=config,
        )
        final_message = result["messages"][-1]
        return {"messages": [final_message]}
