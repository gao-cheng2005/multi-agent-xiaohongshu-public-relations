# 基于多 Agent 协作的小红书舆情公关系统

面向品牌方（如小米米家台灯及其子产品）的小红书舆情监测与公关应对平台。系统自动采集小红书笔记与评论，由多 Agent 工作流完成**情感判断 → 风险分级 → 问题维度抽取 → 负面预警 → 应对方案生成 → 文案话术库沉淀 → 产品优化报告**，形成"监测 → 分析 → 预警 → 应对 → 复盘"的业务闭环。

## 功能特性

| 模块 | 说明 |
|------|------|
| 舆情采集 | 关键词搜索 / 单篇链接两种模式采集小红书笔记与评论；URL 去参哈希去重、增量跳过、放大窗口补采 |
| 智能分析 | 大模型（Qwen 等）+ 规则引擎双通道，完成情感判断、风险分级、主题提取 |
| 负面预警 | 按风险等级与敏感词规则自动生成预警，支持单条 / 按笔记批量处理 |
| 应对方案 | 多 Agent 自动决策渠道（私信/公开评论）、撰写公关文案并打分质检，支持按人工反馈重写（≤2 轮） |
| 文案话术库（RAG） | "完成处理时采用的优秀文案"自动向量化入 ChromaDB；生成新文案时按情感/风险/渠道/维度语义检索参考 |
| 问题标签 | Agent⑥ 自动抽取用户问题维度（如"安全隐患"），支持人工确认与归并 |
| 数据看板 | 情感趋势、热词、产品维度分析、应对效果、产品优化建议报告 |
| 报表导出 | Markdown / Excel 全量数据导出 |

## 多 Agent 流水线

```
采集(OpenCLI + Chrome 登录态)
   │
   ▼
┌─ 采集后处理图（LangGraph）──────────────────────────────┐
│  ① 情感判断 → ② 风险分级 → 落库分析 + 预警（同步）      │
│  ⑥ 问题标签抽取 → 落库标签（异步）                      │
└────────────────────────────────────────────────────────┘
   │
   ▼
┌─ 方案生成图（LangGraph，异步）───────────────────────────┐
│  ③ 渠道决策 → ④ 文案撰写（带 RAG 参考）→ ⑤ 打分质检      │
│  不达标 ≤2 轮重写 → 落库方案                             │
└────────────────────────────────────────────────────────┘
   │
   ▼
完成处理 → 文案入库(ChromaDB) → ⑦ 产品优化报告(缓存)
```

## 技术栈

- 后端：Python 3.11 · FastAPI · SQLAlchemy(async) · MySQL 8.0 · Alembic
- 多 Agent 编排：LangGraph（7 个 Agent 节点化编排）
- 采集：OpenCLI 驱动本机 Chrome 登录态抓取小红书，统一采集适配层
- 大模型：硅基流动（OpenAI 兼容接口）Qwen 系列
- 向量检索：ChromaDB + jieba/BM25 字面检索兜底
- 前端：Vue3 + Vite + Pinia + Vue Router

## 目录结构

```text
├── app_v2/                 后端应用
│   ├── main.py             FastAPI 应用与生命周期
│   ├── controllers/        接口层（路由）
│   ├── services/           业务服务 + workflows（LangGraph 图）+ agents（①~⑦）
│   ├── repositories/       数据访问层
│   ├── models/             SQLAlchemy Model 与 Pydantic Schema
│   ├── db/                 会话、初始化与迁移
│   ├── collectors/         OpenCLI 采集适配
│   └── core/               配置、日志、清洗、时间工具
├── frontend/               Vue3 前端工程（Vite + Pinia + Vue Router）
├── tests/                  后端单元测试（pytest）
├── scripts/                运维脚本（查看/清空/重建向量库等）
├── run.py                  后端启动入口
├── requirements.txt        后端依赖
├── alembic.ini             数据库迁移配置
├── .env.example            配置模板（复制为 .env 使用）
└── README.md               本文档
```

> `data/`（ChromaDB）、`logs/`（运行日志）为运行时自动生成，未纳入版本控制。

## 快速开始

### 环境要求

- Python 3.11+，Node.js 18+（前端）
- MySQL 8.0（本机已启动）
- 采集需要：Chrome/Edge + OpenCLI CLI 与浏览器扩展（见下文"采集配置"）

### 1. 后端

```bash
pip install -r requirements.txt
copy .env.example .env        # 然后按需修改 .env（见配置表）
python run.py                 # 启动后：http://127.0.0.1:8000/docs
```

> 注意：请**在 `code/` 目录内启动**（alembic 迁移脚本路径基于启动目录解析），或直接使用 `启动后端.bat`。

### 2. 前端

```bash
cd frontend
npm install
npm run dev                   # 浏览器打开 http://127.0.0.1:5173（/api 自动代理到 8000）
```

### 3. 采集配置（OpenCLI）

1. `npm install -g @jackwener/opencli`（若新版搜索适配器报 `ambiguous_option`，可临时 `npm install -g @jackwener/opencli@1.8.7`）
2. Chrome 登录小红书，安装 OpenCLI 浏览器扩展（`opencli doctor` 应显示扩展已连接）
3. 重启后端后即可在平台触发采集

## 配置（`.env`）

| 变量 | 说明 |
|------|------|
| `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` | MySQL 业务库（默认 `yuqing_pr`） |
| `CHECKPOINT_DATABASE` | LangGraph 长流程状态库（`yuqing_pr_langgraph`） |
| `SILICONFLOW_API_KEY` | 硅基流动 API Key（前端不展示，仅后端读取） |
| `SILICONFLOW_BASE_URL` | 硅基流动接口地址 |
| `SILICONFLOW_DEFAULT_MODEL` | 默认模型，运行中可在设置页切换 |
| `SILICONFLOW_EMBEDDING_MODEL` | RAG 向量化模型（默认 `BAAI/bge-large-zh-v1.5`） |
| `EMBEDDING_TIMEOUT` | 向量化请求超时（秒） |
| `RAG_ENABLED` | 文案话术库检索开关（`true`/`false`） |
| `RAG_TOP_K` | 每次生成文案最多注入的参考条数 |
| `SENTIMENT_MODE` | `auto`（有 Key 用 LLM 否则规则）/ `llm` / `rule` |
| `OPENCLI_BIN` | OpenCLI 命令名 |

## 测试

```bash
pytest
```

## 接口摘要

主要接口（统一前缀 `/api/v1`）：

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/health`、`/info`、`/stats` | 健康检查 / 运行状态 / 总览 |
| GET/POST/DELETE | `/keywords` | 监控关键词管理 |
| POST | `/collect` | 触发采集（关键词或笔记链接） |
| GET/DELETE | `/contents...` | 内容列表、评论、批量删除 |
| GET/POST | `/alerts...` | 预警列表与处理 |
| GET/POST | `/plans...` | 方案列表、生成、决策、完成处理 |
| GET/POST | `/analytics...` | 趋势/热词/效果/产品分析/报告 |
| GET/POST | `/llm/...` | 模型清单与切换 |

## License

内部项目，保留所有权利。
