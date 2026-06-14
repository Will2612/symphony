# Symphony Swift 实施计划

> 当前阶段：**M0 — Swift 运行时壳**。后续阶段先留位，细节随调研补充。

---

## 0. 背景与目标

`Symphony` 是 OpenAI 提出的"长跑守护进程"规范：监听 issue tracker、为每个 issue 创建隔离 workspace、调用 coding agent（codex app-server）完成实现、汇总结果并回写。

- 原规范：<https://github.com/openai/symphony/blob/main/SPEC.md>
- 现有实现：`atjsh/symphony-swift`（Swift/SwiftUI）、`jamesharperfd/symphony`（Swift）
- 现有实现硬编码 Linear 作为 issue tracker；本项目使用 GitHub Projects v2 替代

本仓库目标：用 Swift 重写一个 `symphony` daemon，最终以多架构 Docker 镜像发布，支持 amd64 + arm64。

---

## 1. 全局技术决策

| 维度 | 决定 |
|---|---|
| 语言/工具链 | Swift 6.0+（`swift-tools-version: 6.3`），纯 Swift Package Manager，无 Xcode 依赖 |
| Issue 源 | GitHub Projects v2（GraphQL） |
| Agent 协议层 | 抽象 `AgentClient` 协议；下接 `CodexAgentClient`（v2 JSON-RPC）与 `OpencodeACPClient`（ACP）；daemon 只看 `AgentClient` |
| Worker 暴露方式 | 抽象 `worker-bridge/`：在独立容器中把 stdio-only agent 装到 TCP socket；含 `codex-bridge.mjs`（端口 8765）与 `opencode-bridge.mjs` |
| Swift 端调用 | 自写 `NetworkWorkerClient`（TCP JSON-RPC），指向任意 worker image（`codex:8765` 等） |
| 模板引擎 | 待定 M1 启动时敲定（Liquid(strict) / Mustache / 自写 mini 渲染器） |
| Worker 协议版本锁定 | 待定 M2 启动时决定（锁定到具体 codex / opencode 版本，CI 内置 schema 校验） |
| 基镜像 | `swift:6.3.2-noble`（build） → `swift:6.3.2-noble-slim`（runtime） |
| 多架构 | amd64 + arm64，buildx manifest list |
| 镜像仓库 | `ghcr.io/will2612/symphony` |
| CI | GitHub Actions，单 job + QEMU 多架构；branch push + semver tag 触发；`:dev` 始终指向最新 |
| 配置传递 | env + bind mount（`workflow/`, `repos/`, `logs/`） |
| Token | `GITHUB_TOKEN`（fine-grained，需 `repo` + `project` + `read:org`），`OPENAI_API_KEY` |

### 关于 "codex 是 ACP 服务吗？"

**不是。** codex app-server 是 OpenAI 自有协议（JSON-RPC over stdio，方法集 `initialize` / `thread/start` / `turn/start` 等），与开放标准 Agent Client Protocol（ACP，Zed 推动）思路相似但不是同一份规范。后续实现"网络版 AgentRunner"时以 codex 容器内 `server.mjs` 的 TCP 接口为准。

---

## 2. 阶段路线图

| 阶段 | 范围 | 状态 |
|---|---|---|
| **M0** | Swift 运行时壳：CLI + Docker 多架构镜像 + CI 发布 | **当前** |
| M1 | `Configuration` + `Tracker`（GitHub Projects v2 客户端） | 待启动 |
| M2 | `Agent`（`NetworkCodexClient` + `server.mjs` 桥）+ Codex 容器 | 待启动 |
| M3 | `Orchestrator`（轮询、并发、retry、stall、reconciliation、`Workspace`、`Hook`） | 待启动 |
| M4 | 生产化（文档、`.env.example`、示例 `WORKFLOW.md`、dashboard 雏形） | 待启动 |

---

## 3. M0 详细计划

### 3.1 范围

**包含：**
- `Package.swift`（0 第三方依赖）
- `Sources/Symphony/main.swift`（CLI 入口：仅识别 `--version` / `--help`）
- `deploy/Dockerfile`（多阶段，缓存挂载，`--static-swift-stdlib`）
- `deploy/docker-compose.yml`（仅 `symphony` 服务，`command: ["--version"]`）
- `deploy/.env.example`（注释列出未来用到的变量）
- `.github/workflows/release.yml`（多架构 buildx → GHCR）
- `.gitignore`、根 `README.md`

**不包含：**
- codex 容器 / `server.mjs`
- `WORKFLOW.md` 加载
- 任何业务模块（`Configuration` / `Tracker` / `Agent` / `Orchestrator`）
- 任何第三方依赖（`swift-argument-parser`、`Yams`、`swift-log` 等）

### 3.2 仓库结构

```
.
├── Package.swift
├── Sources/
│   └── Symphony/
│       └── main.swift
├── deploy/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── .env.example
├── .github/
│   └── workflows/
│       └── release.yml
├── .gitignore
├── README.md
└── Plan.md
```

### 3.3 `Package.swift` 草案

```swift
// swift-tools-version: 6.3
import PackageDescription

let package = Package(
    name: "Symphony",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "symphony", targets: ["Symphony"]),
    ],
    targets: [
        .executableTarget(name: "Symphony"),
    ]
)
```

### 3.4 `main.swift` 职责

- 解析 argv，识别 `--version` / `-v` / `--help` / `-h`
- `--version` → 打印 `symphony 0.0.0-dev (swift 6.3.2)`，退出 0
- `--help` → 打印 6 行用法（Usage / 空 / 2 个 option / 空 / 一行描述），退出 0
- 无参数 / 未知参数 → 打印提示到 stderr，退出 64（`EX_USAGE`，magic number 保留不抽常量）
- 版本号硬编码在文件顶部常量（不接 `git describe`）

### 3.5 `deploy/Dockerfile` 草案

```dockerfile
# syntax=docker/dockerfile:1.7
ARG SWIFT_VERSION=6.3.2

FROM --platform=$TARGETPLATFORM swift:${SWIFT_VERSION}-noble AS builder
WORKDIR /build
COPY Package.swift ./
COPY Sources ./Sources
RUN --mount=type=cache,target=/root/.cache/swift \
    --mount=type=cache,target=/build/.build \
    swift build -c release --static-swift-stdlib && \
    cp /build/.build/release/symphony /symphony

FROM --platform=$TARGETPLATFORM swift:${SWIFT_VERSION}-noble-slim AS runtime
RUN useradd -m -u 10001 symphony
WORKDIR /app
COPY --from=builder /symphony /usr/local/bin/symphony
USER symphony
ENTRYPOINT ["symphony"]
```

### 3.6 `deploy/docker-compose.yml` 草案

```yaml
name: symphony

services:
  symphony:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    image: ghcr.io/will2612/symphony:dev
    command: ["--version"]
    volumes:
      - ./repos:/app/repos
      - ./logs:/app/logs
    restart: "no"
```

M0 让容器起来后直接打印版本号并退出，验证管线通畅。后续改成无 `command`，跑 daemon。

### 3.7 `deploy/.env.example` 草案

```bash
# M0 不消费；M2+ codex worker 专用（opencode worker 走自身 provider 配置）
# OPENAI_API_KEY=

# M1+ 接入 GitHub Projects 时使用
# GITHUB_TOKEN=
# GITHUB_PROJECT_OWNER=
# GITHUB_PROJECT_NUMBER=

# M2+ 默认 worker（opencode/ACP）连接信息
# OPENCODE_HOST=opencode
# OPENCODE_PORT=<port>

# M2+ 可选 worker（codex v2 JSON-RPC）连接信息
# CODEX_HOST=codex
# CODEX_PORT=8765
```

### 3.8 CI（`.github/workflows/release.yml`）

- 触发：`push branches: [swift-implementation]` + `push tags: ['v*']` + `workflow_dispatch`（手动 build 不推 GHCR）
- **单 job** 在 `ubuntu-latest` 上跑，buildx 用 `--platform linux/amd64,linux/arm64` 一次性构建。arm64 走 QEMU 模拟（`docker/setup-qemu-action@v3`）。原本设计的 per-arch matrix 在同一 tag 上后写覆盖前写，所以简化为单 job。
- 所有 6 个 `uses:` 都 SHA-pin（`actions/checkout@v4.3.1` 等），并在行尾注释标版本。Elixir 仓的 supply-chain 约定。
- 登录 GHCR 用 `secrets.GITHUB_TOKEN`（`permissions: packages: write`），push 事件触发；dispatch 不登录
- `docker/metadata-action@v5` 配 `flavor: latest=false`，输出 tag 模式：
  - `type=raw,value=dev`（branch + tag push 都出 `:dev` 始终指向最新）
  - `type=semver,pattern={{raw}}`（仅 tag push 触发，保留 `v` 前缀 → `:v0.0.0-dev`）
  - `type=sha,format=short`（所有 push 出 `:sha-abc1234`，方便回溯）
- `provenance: false` + `sbom: false`：禁掉 buildkit 默认的 SLSA attestation 副作用（避免 OCI index 多出 `unknown/unknown` 幽灵 manifest）

### 3.9 验证标准

- [x] 1. `swift build` 在 Ubuntu 上能编出 release 二进制（容器内 `swift:6.3.2-noble` 验证）
- [x] 2. 本机 `./.build/release/symphony --version` 打印版本字符串并退出 0
- [x] 3. 本机 `./.build/release/symphony` 不带参数以 64 退出并打提示
- [x] 4. `docker buildx build --platform linux/amd64,linux/arm64 -f deploy/Dockerfile .` 在两架构上能出镜像（本地 + CI）
- [x] 5. `docker compose -f deploy/docker-compose.yml up` 能跑出 `--version` 输出并退出码 0
- [x] 6. 推 commit 触发 release workflow，CI 在 GHCR 上出 `ghcr.io/will2612/symphony:dev` + `:sha-<short>`，manifest list 干净（仅 amd64 + arm64，无 attestation 幽灵）— **未走 semver tag 路径**（没推 `v*` tag），但 `{{raw}}` 模式与 `{{sha}}`/`{{dev}}` 模式走同一 metadata-action 配置，结构同源；M0 收尾时是否真推一个 `v0.0.0-dev` 由 M1 启动时决定

### 3.10 实施顺序

1. `Package.swift`
2. `Sources/Symphony/main.swift`
3. `deploy/Dockerfile`
4. `deploy/docker-compose.yml`
5. `deploy/.env.example`
6. `.github/workflows/release.yml`
7. `.gitignore`
8. `README.md`

每写一个文件停下 review，再写下一个。

---

## 4. 待定项（需在实施前敲定）

- [x] **GHCR owner**：`will2612`（个人用户名；仓库 `git@github.com:Will2612/symphony.git`）
- [x] **CI tag 策略**：单 job + QEMU 多架构；branch + semver tag 触发；`:dev` 始终指向最新；`flavor: latest=false`；不上 `:edge`（per user preference "git push 自动 build 推到 ghcr"）
- [x] **本地 dev 工作流**：不引入 `Makefile` / `justfile`；`docker build` / `docker compose` / `swift build`（容器内）即足够
- [ ] **SwiftLint / swift-format**：M0 不引入，后续阶段决定是否启用（倾向不引入，README 给推荐配置）
- [ ] **模板引擎**：Liquid(strict) / Mustache / 自写 mini 渲染器（M1 启动时定）
- [ ] **Worker 协议版本锁定策略**：codex / opencode 的协议版本与 CI 内置 schema 校验（M2 启动时定）
- [ ] **GitHub Projects v2 → state 名称归一化约定**：Tracker 在 query 时如何把 Project status 映射到 SPEC `active_states` / `terminal_states`（M1 启动时定）
- [ ] **WORKFLOW.md 监听方式**：`DispatchSource.makeFileSystemObjectSource` + FSEvents / `Task.sleep` + `mtime` check（M3 启动时定）

---

## 5. 后续阶段占位（细节待启动时再细化）

### M1 — Configuration + Tracker
对位 SPEC §5、§6、§11、§12、§13.1。
- `WorkflowLoader`（YAML front-matter，使用 Yams，SPEC §5.2 / §5.3）
- `ConfigLayer`（严格校验，env 解析，dynamic reload，SPEC §6.1 / §6.2 / §6.3）
- `Tracker` 协议 + `GitHubProjectsV2Tracker`（URLSession + GraphQL 字符串查询，SPEC §11.1–§11.3）
- `MemoryTracker`（测试用 fixture，SPEC §11.1 fallback）
- `StructuredLogger`（JSON 行 + 必要 context 字段，SPEC §13.1）
- `Issue` 领域模型（SPEC §4.1.1，归一化规则 §11.3）
- 模板渲染（strict variables + strict filters，SPEC §5.4 / §12.2）

### M2 — Workers（协议层 + 多 worker 实现）
对位 SPEC §10、§10.5、§10.6、§10.7。
- `AgentClient` 协议抽象（SPEC §10.7）
- `worker-bridge/` 目录：通用 stdio↔TCP JSON-RPC 桥
  - `codex-bridge.mjs`（端口 8765，codex 协议）
  - `opencode-bridge.mjs`（端口待定，ACP 协议）
- `NetworkWorkerClient`（Swift 端：JSON-RPC 客户端，TCP）
- `CodexAgentClient`（v2 方法模型：`initialize` / `thread/start` / `turn/start` / `thread/resume`）
- `OpencodeACPClient`（ACP 方法模型：`initialize` / `session/new` / `session/prompt` 等）
- Approval / tool call / input-required 策略（SPEC §10.5）
- Timeout / error mapping（SPEC §10.6）
- 联调：daemon → `codex:8765` 跑一个 turn，daemon → `opencode:<port>` 跑一个 turn

### M3 — Orchestrator
对位 SPEC §7、§8、§9、§9.5、§6.2、§14。
- 状态机（`Unclaimed` / `Claimed` / `Running` / `RetryQueued` / `Released`，SPEC §7.1）
- 轮询循环（`polling.interval_ms`，SPEC §8.1）
- 并发控制（`max_concurrent_agents` + per-state，SPEC §8.3）
- retry 队列（指数退避 + continuation 重试，SPEC §7.1 / §8.4）
- stall 检测（`codex.stall_timeout_ms`，SPEC §8.5 Part A）
- reconciliation（终止状态变化导致的孤儿 worker，SPEC §8.5 Part B / §8.6）
- `WorkspaceManager` + 钩子执行（`after_create` / `before_run` / `after_run` / `before_remove`，SPEC §9.4）
- 安全不变量：cwd 必须在 workspace 内；workspace 必须在 root 下；key 仅 `[A-Za-z0-9._-]`（SPEC §9.5 / §15.2）
- 动态重载：WORKFLOW.md 修改后未来 dispatch 自动应用新配置（SPEC §6.2）
- 失败分类与恢复（SPEC §14.1 / §14.2）
- 算术事件 / token accounting（SPEC §13.5）

### M4 — 生产化
对位 SPEC §13、§17、§18。
- 多架构镜像稳定 + GHCR 自动发布
- 文档（README、ARCHITECTURE、WORKFLOW 编写指南）
- `.env.example` 完善
- 示例 `WORKFLOW.md`（GitHub Projects 配置版，含 prompt body 模板）
- Runtime snapshot 接口（SPEC §13.3，OPTIONAL 但 RECOMMENDED）
- 可选：terminal status surface（`Status Surface`，SPEC §13.4）
- OPTIONAL HTTP server（SPEC §13.7）
- 5 篇博客发布（M0–M4 各一篇）

---

## 6. 决策日志

- **2026-06-14**：放弃 Linear，改用 GitHub Projects v2。
- **2026-06-14**：codex 容器化方案——Node.js stdio↔TCP 桥。
- **2026-06-14**：M0 范围收窄到仅 Swift 壳，不接 codex、不加载 workflow。
- **2026-06-14**：M0 阶段 0 第三方依赖。
- **2026-06-14**：M0 同步上多架构（amd64 + arm64）。
- **2026-06-14**：CLI 仅识别 `--version` / `--help`，不接受 workflow 参数。
- **2026-06-14**：worker 是可替换协议层（`AgentClient` 协议）；opencode（ACP）为默认 worker，codex（v2 JSON-RPC）为可选 worker；`worker-bridge/` 是协议无关的桥接模式。
- **2026-06-14**：教学仓 `symphony` / 实现仓 `symphony-swift` 双仓联动；lesson `Verify` 段指向实现仓具体文件 + 行号。
- **2026-06-14**：纯 Swift Package Manager，无 `.xcodeproj`、无 Xcode 依赖；`swift build` / `swift test` / `swift run` 即可。
- **2026-06-14**：教学按 SPEC 18 章节分块，共 42 课（HTML 交付，每节 5–10 分钟）；每篇博客在里程碑（M0–M4）收尾时发布。
- **2026-06-14（M0 review 决议）**：
  - `swift-tools-version` 升 6.0 → 6.3（与运行时基础镜像对齐）
  - Dockerfile builder 用 `$TARGETPLATFORM`（非 `$BUILDPLATFORM`；Swift 无 native cross-compile，必须 native build + QEMU 模拟）
  - Dockerfile build 末尾加 `cp /build/.build/release/symphony /symphony`（BuildKit cache mount 不可见，需把产物拷出 mount）
  - docker-compose `context: ..`（compose 文件在 `deploy/`，`.` 解析到 `deploy/`，必须回到仓根）
  - release workflow 改单 job + QEMU 多架构（原本 per-arch matrix 在同一 tag 上后写覆盖前写，CI 验证发现 manifest 缺 amd64）
  - 所有 GitHub Actions `uses:` SHA-pin（Elixir 仓 supply-chain 约定；`docker/build-push-action` 同时 v5→v6.19.2，因仓库未发布 v5）
  - 加 `flavor: latest=false` + `provenance: false` + `sbom: false`（避免 OCI image index 多出 `unknown/unknown` 幽灵 attestation manifest）
  - 加 `:dev` tag（用户偏好：`docker pull :dev` 要能拉）
  - `Package.resolved` 改为 commit（与 Elixir 仓 `mix.lock` 策略一致；M0 暂无 lockfile 文件，M1+ 引入第三方依赖后生效）
  - `--help` 输出 4 行 → 6 行（含 2 行空行分隔）
  - magic number `64` 保留不抽常量（用户偏好「M0 抽象越少越好」）

---

## 7. 教学 ↔ 实现时间线对齐表

教学仓 `symphony`（`/home/will/Projects/symphony`）按 SPEC 18 章节分 42 课推进；实现仓 `symphony-swift`（`/home/will/Projects/symphony-swift`，即本仓）按 M0–M4 推进。每一行说明"学到哪一课时可以动哪段代码"。

| 教学阶段 | 课 | SPEC | 对应实现里程碑 | 可以动 / 不动 |
|---|---|---|---|---|
| Phase 0 工具与基础 | 0001–0004 | — | **M0 验收** | ✅ 读 M0 产物（`Package.swift`、`deploy/Dockerfile`、CI、compose）；不动业务代码 |
| Phase 1 问题与架构 | 0005–0009 | §1–3 | — | ❌ 不写代码；画 6 层对位 Swift 模块的**手绘草图** |
| Phase 2 Domain Model | 0010–0012 | §4 | M1 预热 | ⚠️ 允许写 `Sources/Symphony/Model/Issue.swift` 占位 struct（无行为） |
| Phase 3 Workflow | 0013–0015 | §5 | **M1 第一段** | ✅ 写 `WorkflowLoader.swift` + front matter 解析 + prompt 模板 |
| Phase 4 Configuration | 0016–0017 | §6 | **M1 第二段** | ✅ 写 `Config.swift` + env 解析 + 校验 + dynamic reload 监听 |
| Phase 5 Orchestration State | 0018–0020 | §7 | M3 预热 | ⚠️ 写 `OrchestratorState.swift`（actor，只装状态） |
| Phase 6 Polling/Reconcile | 0021–0023 | §8 | **M3 主线** | ✅ 写 `PollLoop.swift` / `Reconciler.swift` / `RetryQueue.swift` |
| Phase 7 Workspace & Safety | 0024–0025 | §9 | **M3 配套** | ✅ 写 `WorkspaceManager.swift` + 3 个 safety invariants |
| Phase 8 Agent Protocol | 0026–0027 | §10 | **M2 协议层** | ✅ 写 `AgentClient` 协议 + `CodexAgentClient` + `OpencodeACPClient`（无 transport） |
| Phase 9 Tracker | 0028–0029 | §11 | **M1 第三段** | ✅ 写 `Tracker` 协议 + `GitHubProjectsV2Tracker` + `MemoryTracker`（测试用） |
| Phase 10 Prompt | 0030 | §12 | M1 收尾 | ✅ 把 §12 渲染规则接进 `WorkflowLoader` |
| Phase 11 Observability | 0031–0032 | §13 | M3 收尾 | ✅ 写 `StructuredLogger` + runtime snapshot（dashboard M4 再做） |
| Phase 12 Failure | 0033–0034 | §14 | M3 收尾 | ✅ 把 §14 错误分类接入 orchestrator |
| Phase 13 Security | 0035–0036 | §15 | M3 收尾 | ✅ 写 `SecretRedactor` + 钩子 timeout 强制 |
| Phase 14 Algorithms | 0037–0039 | §16 | M3 校验 | ⚠️ 用 §16 算法当 e2e test fixture（参考算法是伪代码，不直接照抄） |
| Phase 15 Test/Validation | 0040–0042 | §17–18 | **M4** | ✅ 补 §17 测试矩阵 + §18 conformance checklist；出 GHCR 镜像 |

**规则**：

1. 表里"可以动"标记 ✅，意味着该教学阶段结束前**可以**写对应的 Swift 代码；标记 ⚠️ 意味着**只允许写占位/接口**；标记 ❌ 意味着**完全不动代码**。
2. lesson `Verify` 段必须指向本表声明的"可以动"路径，**不得要求读本表未声明的代码**。
3. 每篇博客（5 篇）发布时机：M0 收尾 / M1 收尾 / M2 收尾 / M3 收尾 / M4 收尾。**Phase 0 课结束不写博客**——M0 本身没业务。
