# 华米商城 AI 智能客服与销售助手

> 这是一个面向智能穿戴电商客服团队的 AI 售前转化与售后分流平台：消费者通过商品页咨询，AI 处理高频问题，复杂诉求转交人工，客服主管通过工单、质检和经营指标持续优化服务。

业务对象、服务角色和系统边界见 [docs/业务闭环与工程边界.md](docs/业务闭环与工程边界.md)。

基于 **LLM（DeepSeek）+ RAG（Elasticsearch 混合检索）** 的电商智能客服系统，解决传统客服回复机械、商品信息更新滞后、销售话术不统一三大痛点。

## 系统架构

```
商城页面 / H5          管理员
   │ 引入2行JS             │
   ▼                      ▼
┌─────────────┐   ┌──────────────┐
│ 聊天组件     │   │ 管理后台 Vue3 │
│ (widget)    │   │ ElementPlus  │
└──────┬──────┘   └──────┬───────┘
       │  SSE 流式        │ REST
       ▼                 ▼
┌─────────────────────────────────┐
│      FastAPI 后端 (Python)       │
│  ┌──────────┐  ┌─────────────┐  │
│  │ 意图识别  │→ │ RAG 混合检索 │  │
│  │ (LLM)    │  │ BM25+向量RRF │  │
│  └──────────┘  └──────┬──────┘  │
│  ┌──────────┐         │         │
│  │ 工具调用  │   ┌─────▼──────┐  │
│  │ 订单/物流 │   │ Agent 编排  │  │
│  └──────────┘   │ 话术/护栏/埋点│  │
│                 └────────────┘  │
└───────┬──────────────┬──────────┘
        ▼              ▼
   ┌─────────┐   ┌───────────────┐
   │  MySQL  │   │ Elasticsearch │
   │ 会话/订单│   │  知识库+商品   │
   └─────────┘   └───────────────┘
```

## 核心能力

| 能力     | 说明                                                                            |
| -------- | ------------------------------------------------------------------------------- |
| 智能问答 | 意图识别（售前/售后/投诉/闲聊/转人工）+ RAG 检索商品/FAQ/售后政策，答案有据可依 |
| 销售助力 | FABE 话术自动推荐、比价异议处理、下单引导，话术统一由后台配置                   |
| 混合检索 | ES BM25 关键词 + bge-m3 向量召回，RRF 融合排序，中文分词（IK）                  |
| 流式回复 | SSE 逐字输出，打字机体验                                                        |
| 人工兜底 | 用户要求/情绪负面/敏感词 → 自动转人工，后台实时接入接管                         |
| 知识管理 | 后台增删改 FAQ/政策/话术，一键同步 ES（自动分块+向量化），秒级生效              |
| 商品同步 | 后台维护商品库，价格库存变更即时同步检索与推荐                                  |
| 数据看板 | 会话量、AI 解决率、转人工率、意图分布、商品点击（转化信号）                     |
| 安全护栏 | 敏感词拦截、提示词注入防御、手机号脱敏、IP 限流                                 |

## 目录结构

```
agent-kefu/
├── backend/                # FastAPI 后端
│   ├── app/
│   │   ├── api/            # 路由：chat(SSE)/kb/products/sessions/dashboard/settings
│   │   ├── services/       # agent 编排/RAG/ES/LLM/意图/工具/护栏/埋点
│   │   ├── models/         # SQLAlchemy 模型
│   │   └── seeds/          # 种子数据（商品/FAQ/政策/话术/订单）
│   ├── scripts/init_data.py  # 初始化脚本
│   └── .env.example
├── frontend/
│   ├── widget/             # 可嵌入聊天组件（零构建）
│   └── admin/              # 管理后台（Vue3 + Element Plus + ECharts）
├── deploy/
│   ├── elasticsearch/      # ES + IK 分词镜像
│   └── nginx/              # nginx（托管后台+组件，反代后端）
└── docker-compose.yml      # 一键部署：mysql + es + backend + nginx
```

## 快速开始（云服务器 · Docker 部署，推荐）

> 服务器要求：2核4G 起步（ES 建议 1.5G 堆内存），已安装 Docker 与 Docker Compose，需放行 80 端口。

```bash
# 1. 上传代码到服务器后，配置环境变量
cp .env.example .env                       # compose 变量（端口/密码/ES内存）
cp backend/.env.example backend/.env       # 后端变量

# 2. 填写 backend/.env 中的三个密钥（必填）：
#    LLM_API_KEY        DeepSeek 平台申请 https://platform.deepseek.com
#    EMBEDDING_API_KEY  硅基流动/阿里百炼等（提供 bge-m3 或 text-embedding-v3）
#    SECRET_KEY         换成随机 64 位字符串
vi backend/.env

# 3. 构建并启动（首次会构建 ES+IK 与前端，约 5-10 分钟）
docker compose up -d --build

# 4. 查看初始化日志（自动建表/导入种子数据/同步ES/启动服务）
docker compose logs -f backend
```

启动完成后：

| 入口         | 地址                                                                   |
| ------------ | ---------------------------------------------------------------------- |
| 管理后台     | `http://服务器IP/admin`（默认账号 `admin` / `admin123`，**务必修改**） |
| 聊天组件演示 | `http://服务器IP/widget/demo.html`                                     |
| 健康检查     | `http://服务器IP/api/health`                                           |

> backend 容器启动时会自动执行 `init_data.py`：建表 → 管理员 → 种子商品/知识库/订单/话术 → 同步 ES。

---

## 多角色权限矩阵（后台 × 5 种内部角色 + 访客）

> 用于简历中呈现真实电商客服团队的协作分工。面试时可画出此表并结合每个角色说明你做的系统支持。

| 角色       | 账号                                     | 说明                                        | 可看板 | 可配置(商品/KB/话术) | 可接人工会话 | 可质检 | 可管理账号 |
| ---------- | ---------------------------------------- | ------------------------------------------- | ------ | -------------------- | ------------ | ------ | ---------- |
| 超级管理员 | `admin` / `admin123`                     | 全局权限、账号/角色/权限管理                | ✅     | ✅                   | ✅           | ✅     | ✅         |
| 运营管理员 | `ops_admin` / `Huami@2026`               | 商品/知识库/话术/敏感词/系统配置            | ✅     | ✅                   | ✅           | ✅     | ❌         |
| 客服主管   | `leader` / `Huami@2026`                  | 坐席会话池分配 + 质检打分 + 坐席绩效        | ✅     | ❌                   | ✅           | ✅     | ❌         |
| 在线客服   | `agent_li` / `agent_wang` → `Huami@2026` | 接单 / 回复 / 交还 AI / 转交同事 / 会话关闭 | ✅     | ❌                   | ✅           | ❌     | ❌         |
| 数据分析师 | `analyst` / `Huami@2026`                 | 只读看板，不能进入会话池与配置页            | 仅看板 | ❌                   | ❌           | ❌     | ❌         |
| 访客       | widget 匿名                              | 商城页匿名访问聊天组件，IP 限流 30/min      | —      | —                    | —            | —      | —          |

权限接口守卫使用 FastAPI 依赖工厂 `require_role(allowed)`（见 [backend/app/api/deps.py](backend/app/api/deps.py) + [backend/app/core/roles.py](backend/app/core/roles.py)），默认 super_admin 天然拥有全部权限，便于后续扩展新角色。

---

## 并发架构设计（支持真实业务多用户同时接入）

> 用于简历 / 面试：讲清每个机制的「问题 → 方案 → 实现」三点。

### 1. 人工会话抢单 CAS 原子更新（避免 TOCTOU 抢单冲突）

- **问题**：多个坐席（小李 / 小王）同时点「接这单」，如果先 SELECT `status=waiting_human` 再 UPDATE，会出现"接了同一单"。
- **方案**：Compare-And-Swap，使用原生 SQL 的 `UPDATE ... WHERE` 作为原子判断：
  ```sql
  UPDATE chat_sessions
     SET status='human_active', human_admin_id=:aid, assigned_at=NOW()
   WHERE id=:sid AND status='waiting_human' AND human_admin_id IS NULL;
  ```
- **实现**：sessions.py `claim_session` 使用 `db.execute(text(...))` + `rowcount==0` → 直接返回 **409 Conflict「会话已被其他客服接走」**，前端提示刷列表。
- **并发冒烟结果**：两个 httpx 客户端 `asyncio.gather` 并发 POST claim → **一个 200，一个 409**（见 scripts/roles_smoke.py）。
- **扩展点**：同样模式用于 `release`（仅当前接待人）、`transfer`（仅当前接待人转给在线坐席 + 目标容量检查）、`back-to-ai`。

### 2. SSE 实时推流（坐席端"新会话入池/新消息"即触即达，无需 WebSocket）

- **问题**：坐席工作台靠前端 3s 轮询 `/admin/sessions/waiting/count` 会错过即时通知，也加重 DB 压力。
- **方案**：Server-Sent Events 单向推流。每个坐席 `GET /api/admin/sessions/stream` 建立一条 25s 心跳长连接。
- **实现**：
  - `services/sse_bus.py` 基于 asyncio.Queue 做进程内发布订阅（全局广播频道 + 每个坐席 ID 的私人频道）。
  - 新会话入 waiting_human 池时 → `on_new_waiting()` 全局广播；领取 / 释放 / 转交时 → `on_pool_changed()` 全局广播；坐席接待会话收到访客新消息 → `on_session_message(admin_id)` 私人频道。
  - **扩展到多实例部署**：保留相同接口，把 sse_bus 内部的 Queue 替换成 Redis pub/sub（生产推荐）。
- **后端实现**：sessions.py `admin_sse_stream` 做 25s `wait_for` 超时时发送 keepalive，规避 nginx 60s 断长连接。
- **面试加分**：「为什么不用 WebSocket？」SSE 单向推送已覆盖坐席场景（坐席消息走 POST HTTP），实现/调试/鉴权更简单；且 nginx 原生反代 SSE 只需加 `X-Accel-Buffering: no` 头。

### 3. 分布式限流（Redis Lua 滑动窗口 vs 本地内存桶，自动切换）

- **问题**：单后端实例时可以用 deque 做时间窗口；docker-compose 开 2 个 backend 实例时，实例间无法共享计数。
- **方案**：
  - 抽象 `Limiter` 接口 + 两种实现：`MemoryLimiter`（本地 deque 滑动窗口 / 单进程开发用）和 `RedisLimiter`（Redis Lua + 有序集合 ZSET 滑动窗口 / 多实例生产用）。
  - 后端启动时读 `REDIS_URL`：为空 → MemoryLimiter；非空 → RedisLimiter。
- **Lua 脚本亮点**：整个限流判断在 Redis 内原子执行，避免"窗口过期与加计数"的竞态。滑动窗口精度 1ms（`ZADD` 精确到 ms），跨 60s 区间计数更准确（比固定窗口少 1 倍边界波动）。
- **代码位置**：[backend/app/services/rate_limiter.py](backend/app/services/rate_limiter.py)；docker-compose 已加 `redis:7-alpine` 服务并对 backend 注入 `REDIS_URL=redis://redis:6379/0`。

### 4. 运营配置乐观锁（Python 秒级快路径 + SQL BETWEEN 并发兜底，已实装 products/kb/settings 三接口）

- **问题**：运营两个运营人员同时改同一商品/FAQ 话术，如果不加锁会「后写入覆盖先写入」，也没任何冲突提示。
- **方案**：`updated_at` 乐观锁，双保险架构避免单一比较失败：
  - **① Python 层串行快路径**：请求入 DB ORM 取到行对象后，立刻把客户端传来的 `if_match_updated_at` 与 DB `product.updated_at` 做「秒级 ISO 字符串去微秒」比较；不匹配直接抛 409（不走 SQL）。
  - **② SQL BETWEEN 并发串行锁路径**：把客户端时间戳转成 1 秒区间（`req_start <= updated_at <= req_start + 0.999999s`），用原生 SQL：
    ```sql
    UPDATE products SET name=:name, price=:price, ..., updated_at = :ts
     WHERE id = :pid AND updated_at BETWEEN :req_start AND :req_end;
    ```
    数据库行锁串行化两个并发 UPDATE；败者 `rowcount==0` → 抛 409。`updated_at = NOW()` 强制写入新时间戳（不依赖 ORM `onupdate` 延迟刷新）。
- **为什么用 BETWEEN 秒级区间而非 `=`？**：不同 DB 驱动对 DATETIME 绑定参数的精度处理不同（SQLite aiosqlite 会把 datetime 转成带微妙字符串的 CAST），BETWEEN 是 100% 方言无关写法。
- **实装覆盖**：`PUT /admin/products/{id}`、`PUT /admin/kb/{id}`、`PUT /admin/settings/{key}` 三接口全部带 `if_match_updated_at` 参数（对应 [backend/app/api/products.py](backend/app/api/products.py) / [kb.py](backend/app/api/kb.py) / [settings.py](backend/app/api/settings.py)）。
- **前端配合**：管理后台 ProductManage/KbManage/PromptConfig 三个页打开编辑时先缓存 list 返回的 `updated_at` 到本地 `lockUpdatedAt`，save 时带上 `if_match_updated_at=lockUpdatedAt`；axios 拦截器统一处理 409 → ElNotification.warning「内容已被他人修改，请刷新后重试」。
- **olock_smoke.py 并发冒烟结果**：两个 httpx 用户 `asyncio.gather` 同时 PUT 同一商品 → **一个 200，一个 409**，sorted([200,409]) 通过；乐观锁单测 11/11 全 PASS（与 roles_smoke 27/27 合计 38/38）。

### 5. 质检流程（客服主管绩效）

- 任何已结束 / 人工结束的会话，**仅 `ROLE_CAN_QA`（超管/运营/主管）** 可写入 `quality_score (0-100) + quality_remark (≤500字) + quality_admin_id + quality_created_at`。
- 后台可按坐席 / 时间段统计：`AVG(quality_score) / COUNT(session_id)` 生成坐席月度绩效报表（配合 `dashboard` 已有接口）。

### 6. 前端 Vue3 坐席工作台（多角色菜单显隐 / SSE 带 Token / 409 冲突提示）

- **角色菜单显隐**：AdminLayout 取 `/me` 接口返回的 `can_agent/can_qa/can_configure/can_user_admin/can_analyze` 五个布尔值，在 `el-menu-item` 用 `v-if` 控制；同时 router `meta.requires` 路由守卫二次拦截，未命中自动重定向到 analyst→/dashboard，agent→/workbench。
- **坐席工作台 AgentWorkbench.vue（核心页）**：
  - 顶栏 4 Card 实时显示「待抢池 / 我接会话数 / 坐席容量 / SSE 连接状态」；
  - 双 Tab：待抢池（claim CAS 按钮）/ 我的会话（release / transfer / back-to-ai / close 四操作）；
  - 转交 Dialog：调 `/admin/auth/online-agents` 拉在线坐席并排除自己，选目标后 CAS transfer；
  - 右侧 Drawer 抽屉做会话详情：消息列表（显示 admin_name 人工发送人）、输入框 Enter 发送 / Shift+Enter 换行；
  - 工作台自身再建立一条 `createSSEStream` 订阅：`onNewWaiting` 刷待抢池、`onPoolRefresh` 刷列表、`onNewMessage` 命中当前打开抽屉时推到抽屉消息（无需整页轮询）。
- **质检中心 QualityScore.vue**：筛选（会话状态 / 访客关键字 / 分数区间 / 仅未打分）+ 每行质检分 Tag；点击行 Drawer 展示消息并提交 `quality_score` + `quality_remark`（质检权限 can_qa=true 才渲染打分 Form）。
- **用户管理 UserAdmin.vue**：关键字搜索 + 角色标签彩色 + presence 坐席状态 Tag + capacity 数显 + active switch 实时 PUT；新增 / 编辑 / 重置密码 三 Dialog 复用；角色下拉取 `/admin/auth/roles` 字典。
- **SSE 自定义带 Token（关键）**：浏览器原生 EventSource 不支持自定义 `Authorization: Bearer xxx`，因此 api/index.js 封装 `createSSEStream(url, handlers)` → `fetch + ReadableStream.getReader + TextDecoder + '\n\n' 分块解析`，完整支持 7 类回调：onConnected/onNewWaiting/onPoolRefresh/onNewMessage/onKeepalive/onAny/onError/onDisconnected。
- **HTTP 状态码全局处理**：axios 响应拦截器 401→清 token 跳登录，403→ElMessage.error「权限不足」，409→ElNotification.warning「并发冲突」+ detail 文案，429→ElMessage.warning「请求过于频繁，请稍后再试」。

---

## 简历 / 面试表达要点（面试防深挖）

> 这 7 个问答可直接背；每个回答前先点出 **业务问题 → 技术方案 → 实际效果** 三段式。

1. **问："你项目有几种角色？权限怎么划分？"**
   - 答：后台 5 种（超管/运营/主管/坐席/分析师）+ 匿名访客。角色职责和真实电商客服团队完全对齐（见上矩阵表）。
   - 技术：用 FastAPI 依赖工厂 `require_role(ROLE_*)` 注入式守卫；`has_any_role()` 让 super_admin 隐式获权，避免每个接口写 5 个角色。
   - 简历可写：**"基于 RBAC 权限模型实现 5 类后台角色 + 1 类前端访客角色，权限守卫以依赖工厂模式嵌入 12+ 个路由，支持零侵入扩展新角色"**。

2. **问："你们怎么避免两个客服同时接同一个会话？运营同时改商品不冲突吗？"**
   - 答（会话抢单）：典型 TOCTOU 问题，不用 SELECT FOR UPDATE（跨 SQLite/MySQL 兼容麻烦），而是**用 UPDATE + WHERE 做 CAS 原子操作**：
     - 仅当 `status='waiting_human' AND human_admin_id IS NULL` 时才写入新接待人；`rowcount==0` 返回 409。
     - 并发下由数据库行锁保证只有 1 条 SQL 成功。
   - 答（运营配置乐观锁）：商品/知识库/话术三套运营页面用 `updated_at` 乐观锁，**双保险架构**：
     1. Python 层先做「秒级 ISO 字符串去微秒」比较（串行快路径直接 409）；
     2. SQL 层写 `WHERE updated_at BETWEEN :req_start AND :req_end + SET updated_at = NOW()`（数据库行锁串行化并发，败者 rowcount=0 → 409），避免 DB 驱动 DATETIME 精度差异造成的误判。
   - 可扩展到 release/transfer/back-to-ai。
   - 实测：olock_smoke.py 两个运营账号同时 PUT 同一商品 → sorted([200,409])，38 条回归用例 100% 通过。
   - 简历可写：**"基于 CAS 原子更新 + rowcount 判断解决多人抢单竞态；运营三接口用 updated_at 乐观锁（Python 快路径 + SQL BETWEEN 并发兜底）双保险，极端并发下也能稳定返回 200/409 语义明确"**。

3. **问："坐席端怎么即时看到新入池的会话？你用了 WebSocket 吗？"**
   - 答：没用 WS，用 SSE（因为坐席端需要服务端单向推、坐席发送消息走普通 HTTP 请求更简单）。
   - 单实例内部用 asyncio.Queue 做 pub/sub；多实例部署时无缝替换 Redis pub/sub。
   - 关键细节：25s keepalive、反代 nginx 加 `X-Accel-Buffering: no` 避免缓冲卡死。
   - 简历可写：**"基于 SSE 设计坐席侧实时推送通道，事件分"全局/私人"两频道，支持新会话入池/新消息/状态变更/心跳 4 类事件；单进程 asyncio.Queue 与多进程 Redis pub/sub 接口一致"**。

4. **问："你们怎么做访客限流？单机和多机一样准吗？"**
   - 答：限流抽象成接口；无 `REDIS_URL` 时本地 deque 滑动窗口（30/min），有 Redis 时用 **Lua + ZSET 原子滑动窗口**（毫秒精度，跨实例完全一致）。
   - 关键细节：Lua 脚本保证"删除过期窗口 / 写入新命中 / 取总计数"三步原子；MySQL/SQLite 不需要单独限流存储。
   - 简历可写：**"实现限流抽象层，支持单进程内存滑动窗口与 Redis Lua ZSET 原子滑动窗口两种后端，后端 REDIS_URL 即开即用"**。

5. **问："质检怎么做的？谁能打分？谁不能？"**
   - 答：仅主管/运营/超管三个角色有质检权限；坐席和分析师不能打分。质检字段独立 4 列（分数/备注/人/时间）。
   - 可进一步按坐席 ID + 月份聚合平均得分做绩效排名看板。

6. **问："如果数据库 schema 升级（加列），线上老库怎么办？"**
   - 答：在 main.py lifespan 与 init_data.py 都加了幂等 `ALTER TABLE ADD COLUMN` 列表（try/except 捕获列已存在），兼容 SQLite 和 MySQL。
   - 同时新模型里保留历史字段（例如 user_ip / ua / intent_last / meta）保证老 dev.db 插入 NOT NULL 不报错。
   - 简历可写：**"设计运行时 DDL 幂等升级机制（10+ 条 ALTER 语句），对已有库零侵入，启动即补齐 4 admin_users 新列与 7+ chat_sessions 新列"**。

7. **问："用户说"转人工"，这个流程如何走通？"**
   - 答：两条路径——关键词短路（"转人工/人工客服/客服/人工/人工服务/找客服/我要人工" 7 个关键词）直接在 chat.py 切 status=waiting_human、写入「已为您接入人工客服，请稍候」系统消息、调 `sse_bus.on_new_waiting()` 广播给坐席 SSE 端；非关键词走 LLM 识别意图 escalated 事件，同样广播入池。
   - 坐席端 AgentWorkbench 收到 SSE `new_waiting` 事件后刷新待抢池 Tab → 客服点 `claim` CAS 原子领取 → Drawer 抽屉展开消息面板 → 输入框 Enter 发送 `POST /messages` 人工回复 → 或 `POST /release` 交还池、`POST /back-to-ai` 交还 AI、`POST /transfer {target_admin_id}` 转交在线坐席（校验目标在线+容量+自己是当前接待人）。
   - 转交后坐席间 SSE `on_pool_changed` 广播：旧接待人我的列表消失，新接待人我的列表新增，系统消息写「会话由 admin_name 转交给 target_name」。

8. **问（前端深挖）："前端怎么按角色隐藏/显示菜单 + 坐席没权限访问某路由时怎么办？"**
   - 答：双重保险：
     1. **渲染级**：AdminLayout `/me` 返回 `can_agent/can_qa/can_configure/can_user_admin/can_analyze` 五布尔，每个 `el-menu-item` 加 `v-if="u.can_agent"` 等条件，登录后立刻按角色渲染出「analyst 只看看板 / agent 能进工作台但不能看商品和用户管理 / 主管能看工作台和质检 / super 全量菜单」。
     2. **路由级**：router 每条路由 `meta.requires: 'can_agent'`，全局 `beforeEach` 调 `hasPermission(u, to.meta.requires)`，不满足 analyst 进工作台 → 403 自动跳 `/dashboard`，ops_admin 进用户管理 → 跳 `/settings`。
   - 为什么要双层？因为仅路由守卫会导致「菜单先出现又秒消失」，仅 v-if 会被用户直接 URL 手动输入绕过。两层组合 = 视觉干净 + 安全不漏。

9. **问（前端深挖）："SSE 长连接怎么带 JWT？原生 EventSource 不支持自定义 Header 吧？"**
   - 答：原生 EventSource 确实不能加 `Authorization` Header（只能靠 URL query 带 token，会暴露在 Nginx 日志，不推荐）。项目在 `api/index.js` 自己封装了 `createSSEStream(url, handlers)`：
     - 调 `fetch(url, { headers: { Authorization: 'Bearer ' + token } })` 拿 Response；
     - `response.body.getReader()` + `TextDecoder` 逐字拼 buffer，遇到 `\n\n` 当分块分隔符，按 `event:` / `data:` 行解析事件；
     - 事件类型映射：connected / new_waiting / pool_refresh / new_message / keepalive → 对应 handlers 回调，可多个订阅者并存（Layout 全局 + Workbench 页面内）。
     - 好处是保持 Bearer token 鉴权与普通 REST 完全一致（401 就关连接跳登录），后端无需额外 query 参数安全改造。

以上 9 个点可直接作为简历的"项目难点/亮点"展开（面试官问前端也有现成答案，不是只有后端接口）。

---

## 本地开发

```bash
# 后端（Python 3.11+）
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # 填好密钥；本地可先用 SQLite: DATABASE_URL=sqlite+aiosqlite:///./dev.db
python -m uvicorn app.main:app --reload --port 8000
# 另开终端初始化数据
python scripts/init_data.py

# 管理后台（Node 18+）
cd frontend/admin
npm install
npm run dev            # http://localhost:5173，已代理 /api 到 8000

# 聊天组件：直接用浏览器打开 frontend/widget/demo.html
```

> 本地没有 MySQL/ES 也能跑通流程：SQLite 存数据，检索退化为空（AI 会按兜底话术应答）。生产务必使用 MySQL + ES。

## 商城接入聊天组件

在商城任意页面（支持 H5）加入两行代码：

```html
<script>
  window.HUAMI_CHAT_CONFIG = {
    server: "https://你的客服域名",
    title: "华米智能客服",
  };
</script>
<script src="https://你的客服域名/widget/huami-chat.js" defer></script>
<link href="https://你的客服域名/widget/huami-chat.css" rel="stylesheet" />
```

配置项：`server`（后端地址，同域可省略）、`title`、`subtitle`、`theme`。

## 关键配置（backend/.env）

| 变量                         | 说明                                                                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `LLM_BASE_URL` / `LLM_MODEL` | 默认 DeepSeek；任何 OpenAI 兼容接口均可替换                                                                              |
| `EMBEDDING_*`                | 向量化服务。硅基流动 bge-m3（1024维）/ 百炼 text-embedding-v3 / 本地 sentence-transformers（`EMBEDDING_PROVIDER=local`） |
| `DATABASE_URL`               | MySQL 连接串（开发可用 sqlite+aiosqlite）                                                                                |
| `CORS_ORIGINS`               | 生产环境改为商城域名，如 `https://www.huami-mall.com`                                                                    |
| `RATE_LIMIT_PER_MIN`         | 单 IP 每分钟聊天请求上限                                                                                                 |
| `HUMAN_HANDOFF_KEYWORDS`     | 强制转人工关键词                                                                                                         |

## 对接真实商城系统

- **订单/物流**：替换 `app/services/tools.py` 中的 `query_orders`，改为调用商城内部 API（Agent 编排无需改动）。
- **商品库**：管理后台批量导入（JSON/CSV），或写定时任务调 `/api/admin/products/sync-all` 增量同步。
- **登录体系**：`app/api/auth.py` 可改为对接商城 SSO。

## 生产检查清单

- [ ] 修改默认管理员密码（当前 `admin/admin123`）
- [ ] `SECRET_KEY` 更换为随机值
- [ ] `CORS_ORIGINS` 收紧为商城域名
- [ ] MySQL/ES 不暴露公网（compose 已默认仅内网，nginx 80 端口对外）
- [ ] 建议为 nginx 配置 HTTPS（证书后增加 443 server 块）
- [ ] 定期备份 `mysql_data`、`es_data` 卷
- [ ] 日志：`docker compose logs -f backend`（可接入日志收集）

## 常见问题

**Q: ES 启动失败/报内存不足？** 调低 `.env` 中 `ES_JAVA_OPTS=-Xms512m -Xmx512m`（ES 仍需约 1G 总内存）。

**Q: IK 分词安装失败？** 代码已做兜底（自动退回 standard 分词），检索能力稍弱但功能不受影响；也可手动修改 `deploy/elasticsearch/Dockerfile` 换插件源。

**Q: 回复说“未能正常回复”？** 检查 `LLM_API_KEY` 是否配置、账户是否有余额：`docker compose exec backend python -c "from app.core.config import get_settings; print(bool(get_settings().LLM_API_KEY))"`。

**Q: 如何让话术立刻生效？** 话术配置保存后有 30 秒缓存；紧急情况重启 backend 容器即可。
