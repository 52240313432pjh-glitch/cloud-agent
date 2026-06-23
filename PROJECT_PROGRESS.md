# Project Progress

本文档用于记录 Cloud Agent 项目的功能开发进度。以后每新增、修改或移除一个重要功能，都在这里追加记录，方便回顾项目演进、准备简历/答辩/复盘材料。

## 维护规则

- 每完成一个功能，新增一条记录，不覆盖旧记录。
- 记录内容包括：日期、功能名称、涉及模块、完成状态、核心说明。
- 只记录对项目能力有影响的改动；纯格式化、临时调试不需要记录。
- 如果功能仍在实验阶段，状态标记为 `进行中` 或 `实验中`。

## 当前项目快照

- 项目定位：面向云服务场景的多 Agent 智能客服系统。
- 前端：Vue 3 + Vite + Element Plus。
- 后端：FastAPI + Uvicorn。
- Agent 编排：LangGraph + LangChain。
- 工具协议：FastMCP + langchain-mcp-adapters。
- 记忆系统：Redis 短期记忆 + Milvus 长期记忆。
- 知识检索：Milvus 向量检索 + Neo4j 知识图谱检索。
- 业务数据：MySQL。
- 模型接入：DashScope / 本地 vLLM Qwen。
- 可观测性：后端 Agent Trace 日志。

## 已开发功能清单

### 1. FastAPI 后端服务

- 状态：已完成
- 涉及模块：`app/`
- 功能说明：
  - 使用 FastAPI 提供后端 API 服务。
  - 提供 Swagger 文档页面 `/docs`。
  - 通过生命周期函数初始化 Agent 系统和记忆系统。
  - 支持服务关闭时清理 MCP 连接等资源。

### 2. Vue 前端聊天界面

- 状态：已完成
- 涉及模块：`front/cloud_agent/`
- 功能说明：
  - 提供 Web 聊天入口。
  - 支持向后端 `/api/chat` 发送问题。
  - 支持流式展示 AI 回复。
  - 支持用户切换下拉菜单，用于模拟不同用户身份。

### 3. 用户列表接口

- 状态：已完成
- 涉及模块：`app/router/users.py`
- 功能说明：
  - 后端提供用户列表接口。
  - 前端可从后端加载用户，而不是写死固定用户。
  - 用于测试不同用户的记忆隔离和业务数据隔离。

### 4. LangGraph 多 Agent 编排

- 状态：已完成
- 涉及模块：`agent/core/workflow/`, `agent/agents/`
- 功能说明：
  - 使用 LangGraph 管理多 Agent 工作流。
  - Orchestrator 负责识别用户意图并路由到具体 Agent。
  - 已拆分产品咨询、账单查询、促销推广、智能推荐、FinOps 分析等 Agent。

### 5. Product Agent 产品咨询

- 状态：已完成
- 涉及模块：`agent/agents/product_agent.py`
- 功能说明：
  - 负责云产品知识问答。
  - 可结合向量数据库和知识图谱返回答案。
  - 适合回答 ECS、VPC、退款规则、产品属性等问题。

### 6. Billing Agent 账单查询

- 状态：已完成
- 涉及模块：`agent/agents/billing_agent.py`
- 功能说明：
  - 负责账单、订单、消费记录等查询场景。
  - 通过 MCP 工具访问 MySQL 中的模拟业务数据。
  - 工具调用前自动注入当前用户 ID，降低越权查询风险。

### 7. Promotion Agent 促销推广

- 状态：已完成
- 涉及模块：`agent/agents/promotion_agent.py`
- 功能说明：
  - 负责促销活动、优惠策略、营销素材等场景。
  - 通过 MCP 工具获取促销相关数据。

### 8. Recommendation Agent 智能推荐

- 状态：已完成
- 涉及模块：`agent/agents/recommendation_agent.py`
- 功能说明：
  - 负责根据用户上下文和业务数据给出推荐。
  - 支持本地工具和 MCP 工具组合使用。
  - 已修复历史乱码和语法异常问题。

### 9. FinOps Agent 成本优化

- 状态：已完成
- 涉及模块：`agent/agents/finops_agent.py`
- 功能说明：
  - 负责云资源成本分析、资源浪费判断和降本建议。
  - 可通过 MCP 工具查询云资源和监控类模拟数据。

### 10. FastMCP 工具服务

- 状态：已完成
- 涉及模块：`agent/mcp_servers/`
- 功能说明：
  - 使用 FastMCP 暴露云资源、订单、促销、推荐等工具。
  - Agent 可通过 MCP Client 调用工具。
  - 支持把业务能力封装成可被 LLM 调用的工具。

### 11. MCPManager 统一工具管理

- 状态：已完成
- 涉及模块：`agent/core/mcp/mcp_manager.py`
- 功能说明：
  - 统一管理 MCP 连接和工具加载。
  - 支持按工具名称筛选工具。
  - 支持工具拦截器，用于用户身份注入和调用追踪。
  - 避免每个 Agent 各自重复创建 MCP Client。

### 12. 用户身份注入拦截器

- 状态：已完成
- 涉及模块：`agent/agents/billing_agent.py`
- 功能说明：
  - MCP 工具调用前自动注入 `user_id`。
  - 避免模型根据用户提示词伪造或修改用户身份。
  - 是项目防越权访问的重要安全边界之一。

### 13. MySQL 模拟业务数据库

- 状态：已完成
- 涉及模块：`agent/database/init_mock_data.sql`
- 功能说明：
  - 提供云实例、订单、监控指标等模拟业务数据。
  - 支持账单查询、资源查询、FinOps 分析等场景。

### 14. Redis 短期记忆

- 状态：已完成
- 涉及模块：`agent/core/memory/short_term.py`
- 功能说明：
  - 使用 Redis 保存短期对话上下文。
  - 支持按 `user_id` 和 `session_id` 隔离会话记忆。
  - 后端请求时会加载最近对话片段作为上下文。

### 15. Milvus 长期记忆

- 状态：已完成
- 涉及模块：`agent/core/memory/long_term.py`
- 功能说明：
  - 使用 Milvus 保存长期用户偏好。
  - 后台从对话中提取用户偏好并沉淀。
  - 支持跨会话继承用户画像类信息。

### 16. 偏好提取后台任务

- 状态：已完成
- 涉及模块：`agent/core/memory/preference_extractor.py`, `app/service/chat_service.py`
- 功能说明：
  - 对话结束后异步提取用户偏好。
  - 避免偏好提取阻塞主聊天响应。
  - 可沉淀如机器偏好、使用习惯等长期信息。

### 17. Milvus 向量知识库

- 状态：已完成
- 涉及模块：`agent/tools/vector_tool.py`, `mock_data/`
- 功能说明：
  - 将云产品文档切分并向量化入库。
  - 支持基于语义相似度检索文档片段。
  - 用于 RAG 问答的数据召回。

### 18. Neo4j 知识图谱

- 状态：已完成
- 涉及模块：`agent/core/graph/`, `agent/tools/graph_tool.py`
- 功能说明：
  - 支持把云产品文档抽取为节点和关系。
  - 支持知识图谱查询。
  - 用于补充向量检索在结构化关系问题上的不足。

### 19. 混合检索

- 状态：已完成
- 涉及模块：`agent/tools/vector_tool.py`, `agent/tools/graph_tool.py`, `agent/agents/product_agent.py`
- 功能说明：
  - 结合 Milvus 向量检索和 Neo4j 知识图谱检索。
  - 向量检索负责语义召回。
  - 图谱检索负责实体关系和结构化知识查询。
  - 当图谱查询不足时，可通过关键词或普通检索策略兜底。

### 20. 语义缓存

- 状态：已完成
- 涉及模块：`app/infra/cache.py`, `app/preload_cache.py`
- 功能说明：
  - 对高频相似问题进行缓存命中。
  - 命中缓存时跳过 Agent 工作流，降低延迟和模型调用成本。
  - 支持缓存预热。
  - 支持输出缓存命中日志，便于判断是否走缓存。

### 21. 本地 vLLM Qwen 接入

- 状态：已完成
- 涉及模块：`agent/.env.example`, Agent LLM 初始化逻辑
- 功能说明：
  - 支持通过 OpenAI Compatible API 接入本地 vLLM。
  - 可使用本地 Qwen2.5 作为 LLM。
  - Embedding 可继续使用 DashScope，避免更换向量模型导致 Milvus 维度不一致。

### 22. DashScope Embedding 接入

- 状态：已完成
- 涉及模块：向量检索、语义缓存、长期记忆相关模块
- 功能说明：
  - 使用 DashScope Embedding 生成向量。
  - 支持 Milvus 文档检索、长期记忆和语义缓存。
  - 已明确更换向量模型时需要关注维度一致性和集合重建问题。

### 23. Agent Trace 后端日志版

- 状态：已完成
- 涉及模块：`agent/core/observability/`, `app/service/chat_service.py`, `agent/agents/`
- 功能说明：
  - 为每次聊天生成 `trace_id`。
  - 记录 `chat_start`、`cache_hit`、`cache_miss`、`memory_loaded`、`workflow_start`、`orchestrator_route`、`workflow_end`、`memory_saved`、`chat_end` 等事件。
  - MCP 工具调用支持记录开始、结束和异常。
  - 可用于分析慢请求、缓存命中、路由决策和 Agent 耗时。

### 24. ProductAgent 内部 Trace

- 状态：已完成
- 涉及模块：`agent/agents/product_agent.py`
- 功能说明：
  - 增加 `product_agent_start`、`product_agent_end`、`product_agent_error` 事件。
  - 为 ProductAgent 内部 LLM 调用增加 `product_llm_start`、`product_llm_end`、`product_llm_error` 事件。
  - 为 `query_vector_db` 和 `query_knowledge_graph` 增加工具包装 Trace。
  - 可分别观察向量检索、知识图谱检索和 ProductAgent 内部大模型推理耗时。

### 25. Trace JSONL 落文件与查询接口

- 状态：已完成
- 涉及模块：`agent/core/observability/trace.py`, `app/router/traces.py`, `app/service/chat_service.py`
- 功能说明：
  - `trace_log` 除了打印控制台，也会追加写入 `logs/agent_trace.jsonl`。
  - 新增 `GET /api/traces?limit=20` 查询最近 Trace 摘要。
  - 新增 `GET /api/traces/{trace_id}` 查询单次请求完整事件链。
  - 聊天 SSE 结束事件返回 `trace_id`，方便前端后续查看链路详情。

### 26. 前端 Trace 面板

- 状态：已完成
- 涉及模块：`front/cloud_agent/src/App.vue`
- 功能说明：
  - 前端接收聊天 SSE 结束事件中的 `trace_id`，并绑定到对应 AI 回复。
  - AI 回复旁提供“查看链路”按钮。
  - 点击后调用 `GET /api/traces/{trace_id}` 获取完整事件链。
  - 通过抽屉展示总耗时、缓存状态、路由结果、关键耗时拆解和事件时间线。

### 27. L1/L2/L3 记忆分层

- 状态：已完成
- 涉及模块：`agent/core/memory/short_term.py`, `agent/core/memory/memory_manager.py`, `app/service/chat_service.py`
- 功能说明：
  - L1 最近原文：保留最近 3 轮对话原文，保证当前会话连续性。
  - L2 会话摘要：当会话历史超过阈值时，用 LLM 压缩较早对话并写入 Redis。
  - L3 长期偏好：继续从 Milvus 检索当前 query 相关的用户长期偏好。
  - Agent 上下文统一按“会话摘要 + 长期用户偏好 + 最近对话”拼接。
  - Trace 的 `memory_loaded` 事件增加摘要长度、最近消息数和长期偏好数量。

### 28. 项目 GitHub 仓库重建

- 状态：已完成
- 涉及模块：Git 仓库
- 功能说明：
  - 重新初始化本地 Git 仓库。
  - 保留当前代码，丢弃旧提交历史。
  - 重新推送 `main` 和 `develop` 分支到 GitHub。
  - 旧 `.git` 已本地备份为 `.git_backup_before_reinit/` 并加入忽略规则。

### 29. 项目 README 和忽略规则

- 状态：已完成
- 涉及模块：`README.md`, `.gitignore`
- 功能说明：
  - 添加项目说明、启动步骤、环境变量示例和常用排查命令。
  - 忽略 `.env`、虚拟环境、`node_modules`、本地模型、数据库 volume、学习资料等不应入库内容。
  - 降低密钥泄露和仓库污染风险。

### 30. 语义缓存 COSINE 分数修正

- 状态：已完成
- 涉及模块：`app/infra/cache.py`, `app/service/chat_service.py`
- 功能说明：
  - 修正 Milvus COSINE 检索结果的判定逻辑：按 `similarity >= 0.86` 判断是否命中。
  - 增加 `cosine_distance = 1 - similarity`，避免把负数相似度误当作“小距离”。
  - Trace 中缓存命中事件改为记录 `similarity` 和 `cosine_distance`。
  - 保留旧 `distance` 字段作为兼容值，避免现有日志打印逻辑报错。

### 31. L4 跨会话相关历史记忆

- 状态：已完成
- 涉及模块：`agent/core/memory/conversation_history.py`, `agent/core/memory/memory_manager.py`, `app/service/chat_service.py`
- 功能说明：
  - 新增独立 Milvus Collection：`conversation_history_memory`。
  - 每轮有效问答结束后，将问答压缩为历史片段并写入 L4。
  - 新一轮提问时按当前 query 检索同一用户、不同 session 的相关历史。
  - Agent 上下文新增“跨会话相关历史”层，顺序为会话摘要、长期偏好、跨会话历史、最近对话。
  - Trace 的 `memory_loaded` 事件增加 `related_history_count` 和 `related_history_chars`。
  - Embedding 模型和维度遵从 `.env` 中的 `EMBEDDING_MODEL`、`EMBEDDING_DIM`。

## 开发记录

| 日期 | 功能 | 状态 | 说明 |
| --- | --- | --- | --- |
| 2026-06-23 | L4 跨会话相关历史记忆 | 已完成 | 新增独立 Milvus 历史记忆集合，支持跨 session 召回相关历史，并接入 Agent 上下文和 Trace。 |
| 2026-06-23 | 语义缓存 COSINE 分数修正 | 已完成 | 使用 similarity 阈值判定语义缓存命中，并计算 cosine_distance，修复负数误命中问题。 |
| 2026-06-23 | L1/L2/L3 记忆分层 | 已完成 | 增加 Redis 会话摘要，组合会话摘要、长期偏好和最近原文作为 Agent 上下文。 |
| 2026-06-23 | 前端 Trace 面板 | 已完成 | AI 回复绑定 trace_id，支持查看链路抽屉、耗时指标和事件时间线。 |
| 2026-06-23 | Trace JSONL 落文件与查询接口 | 已完成 | Trace 事件写入 `logs/agent_trace.jsonl`，并提供最近列表和详情查询接口。 |
| 2026-06-22 | ProductAgent 内部 Trace | 已完成 | 增加 ProductAgent、内部 LLM、向量检索和知识图谱检索的链路日志。 |
| 2026-06-22 | 项目进度文档 | 已完成 | 新增本文档，用于持续记录项目功能开发进度。 |
| 2026-06-18 | 后端 Agent Trace 日志 | 已完成 | 增加 trace_id 和关键链路事件日志，便于观察 Agent 调用过程。 |
| 2026-06-18 | Git 仓库重新初始化 | 已完成 | 重新初始化仓库并推送干净的 main/develop 分支。 |
| 2026-06-18 | 课程推广注释清理 | 已完成 | 删除 Agent 相关文件中的课程推广和联系方式注释。 |
| 2026-06-18 | README 文档 | 已完成 | 增加项目说明、启动方式、环境配置和排查命令。 |
| 2026-06-18 | test 与 introduce 目录不入库 | 已完成 | 更新忽略规则，避免测试材料和介绍材料进入 Git 仓库。 |
| 2026-06-18 | MCPManager 接入 | 已完成 | 统一管理 MCP 工具连接，减少重复初始化。 |
| 2026-06-18 | 长期记忆接入 | 已完成 | 对话后异步提取偏好并写入长期记忆。 |
| 2026-06-18 | 用户切换 | 已完成 | 前端支持选择不同用户，后端提供用户列表接口。 |

## 后续改进方向

- Agent Trace 前端可视化：展示路由、检索、工具调用、耗时和缓存命中。
- Product Agent 局部工具追踪：补充向量检索和知识图谱检索的详细 trace。
- RAG 评测集：固定问题集评估召回率、准确率和幻觉率。
- 语义缓存优化：增加问题归一化、命中解释和缓存污染检测。
- 记忆分层优化：会话摘要、最近原文、长期偏好、相关历史检索组合使用。
- 对话历史持久化：把完整历史对话落库，支持审计和数据飞轮。
- 安全加固：只读工具白名单、Cypher 查询限制、敏感操作审批。

## 新功能记录模板

```markdown
### 功能名称

- 日期：YYYY-MM-DD
- 状态：已完成 / 进行中 / 实验中 / 已移除
- 涉及模块：`path/to/module`
- 功能说明：
  - 说明 1
  - 说明 2
- 验证方式：
  - 命令、接口、页面或日志
```
