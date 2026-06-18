# Cloud Agent

一个面向云服务场景的多 Agent 智能客服系统，集成 FastAPI、Vue、LangGraph、FastMCP、Milvus、Neo4j、Redis、MySQL，并支持通过 vLLM 接入本地 Qwen 模型。

## 项目亮点

- 多 Agent 编排：通过 LangGraph 将产品问答、账单查询、推广营销、智能推荐、FinOps 分析等能力拆分为不同 Agent。
- MCP 工具调用：通过 FastMCP 暴露云资源、订单、商品、推广素材等工具，并在工具调用前注入当前用户身份，降低越权风险。
- 混合检索：结合 Milvus 向量检索与 Neo4j 知识图谱查询，提高云产品知识问答的覆盖率。
- 语义缓存：高频相似问题优先走缓存，减少模型调用和响应延迟。
- 记忆系统：Redis 保存短期对话上下文，Milvus 保存长期用户偏好。
- 本地模型支持：可通过 vLLM 部署本地 Qwen2.5 作为 LLM，同时继续使用 DashScope Embedding 作为向量模型。
- 前后端分离：FastAPI 提供接口，Vue + Element Plus 提供聊天界面。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 后端 API | FastAPI, Uvicorn |
| 前端 | Vue 3, Vite, Element Plus |
| Agent 编排 | LangGraph, LangChain |
| 工具协议 | FastMCP, langchain-mcp-adapters |
| LLM | DashScope / 本地 vLLM Qwen |
| Embedding | DashScope Embedding |
| 向量库 | Milvus |
| 知识图谱 | Neo4j |
| 短期记忆 | Redis |
| 业务数据 | MySQL |

## 目录结构

```text
cloud_agent/
├── agent/                 # Agent、MCP Server、记忆、检索、知识图谱相关代码
│   ├── agents/            # 不同业务 Agent
│   ├── core/              # MCP、Memory、Workflow、Graph 等核心模块
│   ├── mcp_servers/       # FastMCP 工具服务
│   ├── tools/             # 向量检索、图谱检索工具
│   ├── database/          # MySQL 初始化数据
│   └── test/              # Milvus/Neo4j 构建与测试脚本
├── app/                   # FastAPI 应用
│   ├── router/            # API 路由
│   ├── service/           # 聊天服务与 Agent 调用入口
│   └── infra/             # 语义缓存等基础设施
├── front/cloud_agent/     # Vue 前端
├── mock_data/             # 云产品知识文档与示例数据
├── studymatiral/          # 本地模型部署学习材料
└── README.md
```

## 环境准备

建议在 WSL/Linux 环境中运行后端和基础服务。

基础服务需要：

- Redis
- MySQL 8
- Milvus
- Neo4j
- Node.js 20+
- Python 3.10+ 或 3.12

## 环境变量

复制示例配置：

```bash
cp agent/.env.example agent/.env
```

按需修改 `agent/.env`。

如果使用 DashScope 作为 LLM 和 Embedding：

```env
DASHSCOPE_API_KEY=your_dashscope_api_key
BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL=qwen-plus
EMBEDDING_MODEL=text-embedding-v2
```

如果使用本地 vLLM Qwen 作为 LLM，但 Embedding 仍使用 DashScope：

```env
DASHSCOPE_API_KEY=your_dashscope_api_key
BASE_URL=http://localhost:8001/v1
MODEL=Qwen/Qwen2.5-7B-Instruct
EMBEDDING_MODEL=text-embedding-v2
```

注意：`agent/.env` 包含密钥和数据库密码，已被 `.gitignore` 忽略，不要提交到仓库。

## 启动基础服务

示例：

```bash
docker start redis
docker start mysql8
docker start neo4j
```

Milvus 如果使用 docker compose：

```bash
docker compose up -d
```

检查服务：

```bash
docker ps
```

## 初始化数据

初始化 MySQL 示例数据：

```bash
cd /mnt/d/项目实战/deep_research/cloud_agent
docker exec -i mysql8 mysql -ucloud_user -pYOUR_MYSQL_PASSWORD mydb < agent/database/init_mock_data.sql
```

构建 Milvus 向量库：

```bash
cd /mnt/d/项目实战/deep_research/cloud_agent/agent/test
source ../../.venv/bin/activate
python milvus_rag.py
```

构建 Neo4j 知识图谱：

```bash
cd /mnt/d/项目实战/deep_research/cloud_agent/agent/test
source ../../.venv/bin/activate
python build_kg.py
```

## 启动本地 Qwen/vLLM

如果使用本地 Qwen2.5：

```bash
source .venv_vllm/bin/activate

vllm serve Qwen/Qwen2.5-7B-Instruct \
  --host 0.0.0.0 \
  --port 8001 \
  --dtype auto \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.9 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
```

测试：

```bash
curl http://localhost:8001/v1/models
```

## 启动后端

```bash
cd /mnt/d/项目实战/deep_research/cloud_agent/app
source ../.venv/bin/activate
uvicorn app_main:app --host 0.0.0.0 --port 5000 --reload
```

接口文档：

```text
http://localhost:5000/docs
```

## 启动前端

```bash
cd /mnt/d/项目实战/deep_research/cloud_agent/front/cloud_agent
npm install
npm run dev
```

前端地址：

```text
http://localhost:5173/
```

## 常用排查命令

查看端口占用：

```bash
lsof -i :5000
lsof -i :5173
lsof -i :8001
```

检查 Redis：

```bash
docker exec -it redis redis-cli -a root ping
```

检查 MySQL：

```bash
docker exec -it mysql8 mysql -ucloud_user -pYOUR_MYSQL_PASSWORD mydb -e "SHOW TABLES;"
```

检查本地 GPU：

```bash
nvidia-smi
```

## 安全说明

- 不要提交 `agent/.env`、模型权重、虚拟环境、数据库 volume。
- MCP 工具调用通过 `UserIdInjector` 强制注入当前用户身份，避免模型按用户提示词越权查询其他用户数据。
- Neo4j 和数据库工具应尽量保持只读，写操作需要显式白名单和审计。

## 后续优化方向

- Agent Trace 可观测性：记录路由、工具调用、检索来源、耗时、token 消耗。
- 记忆分层：会话摘要 + 最近原文 + 长期偏好 + 相关历史检索。
- RAG 评测集：建立固定问题集，评估召回率、准确率、幻觉率和工具调用正确率。
- 语义缓存增强：问题归一化、缓存命中解释、缓存污染检测。
- 数据飞轮：记录用户反馈、失败案例和人工修正，形成后训练和知识库更新数据。
