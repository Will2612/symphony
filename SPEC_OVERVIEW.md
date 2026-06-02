# SPEC Overview Table

| 章节 | 标题 | 主要内容概括 |
|------|------|--------------|
| 1 | Problem Statement | 说明 Symphony 需要解决的四大运营问题：调度、隔离、配置即代码、可观测。阐明服务的边界（仅调度/运行，不直接写票）。 |
| 2 | Goals & Non‑Goals | 列出实现目标（轮询、并发、工作空间、恢复、日志等）以及明确不在范围内的特性（完整 UI、通用工作流引擎、强制沙箱等）。 |
| 3 | System Overview | 描述系统的 8 大核心组件（Workflow Loader、Config Layer、Issue Tracker Client、Orchestrator、Workspace Manager、Agent Runner、Status Surface、Logging）以及它们的抽象层次（Policy → Config → Coordination → Execution → Integration → Observability）。 |
| 4 | Core Domain Model | 定义 Issue、WorkflowDefinition、Service Config 三大实体及其字段，说明数据在系统内部如何流动和规范化。 |
| 5 | Workflow Specification | 规定 WORKFLOW.md 文件的发现顺序、YAML 前置内容、模板体、可扩展的顶层键、以及 tracker / polling / workspace / hooks / agent / codex 各子块的字段、默认值、校验规则。 |
| 6 | Config Resolution | 说明配置层如何读取 WorkflowDefinition.config、处理 $VAR 环境变量、应用默认、执行类型检查，并在运行时动态刷新（仅对可热更的键）。 |
| 7 | Orchestration State Machine | 给出 orchestrator 状态机（idle / new / claimed / running / retry / stop / stopped / terminal / terminal_batch / end）以及运行周期（调度 → 过滤 → 选择 → 派发 → 运行 → 结束）。 |
| 8 | Polling, Scheduling & Reconciliation | 描述轮询循环（间隔、指数退避、最大回退），以及 reconciliation（在每轮 tick 前刷新 tracker、清理终态 issue、重新调度）。 |
| 9 | Workspace Management | 解释工作空间根目录的解析、创建/重用规则、hooks（after_create / before_run / after_run / before_remove）的执行与超时，以及安全的路径/变量展开。 |
| 10 | Agent Runner Protocol | 定义 Codex app‑server 子协议（启动、标准输入/输出、事件流），列出 12 类事件、5 种完成条件、错误分类，以及审批/沙箱的可配置策略。 |
| 11 | Tracker Integration | 给出 Linear 适配器的必备字段（api_key / endpoint / project_slug / active_states / terminal_states）、GraphQL 查询结构、分页/重试、以及认证/网络超时的默认值。 |
| 12 | Prompt Construction | 说明 Liquid‑compatible 模板引擎的使用方式、必需的模板变量（issue、attempt），以及未知变量/过滤器报错策略。 |
| 13 | Logging & Observability | 规定结构化日志（键值对、时间戳、会话/issue 标识），以及可选的状态仪表盘／JSON API（端口、路径、返回结构、错误包装、token 统计）。 |
| 14 | Failure Model & Recovery | 列出 5 类错误（missing_workflow_file / workflow_parse_error / template_parse_error / template_render_error / other_error），以及容错策略（停止新派发、保持服务运行、日志记录）。 |
| 15 | Security & Safety | 提供安全最佳实践：trust / high‑trust 模式、环境变量/密钥不泄漏、hooks 的信任范围、工作空间权限限制，以及硬化建议（专用 OS 用户、只读挂载、最小化凭证）。 |
| 16 | Reference Algorithms | 给出 7 条参考算法（整数指数退避、时间戳比较、集合差分、服务端事件结构、外部工具调用方式、日志键值规范、JWT‑HS256 生成）。 |
| 17 | Test Matrix | 为实现提供完整的合规性测试清单（启动、配置、调度、工作空间、Agent Runner、Tracker、Prompt、日志、错误、恢复、扩展、可观察性、性能、平台）。 |
| 18 | Implementation Checklist | 细化交付物检查表（代码布局、Makefile、formatter、CI、CLI 标记、文档、示例、覆盖率、观察仪表盘、无数据库、二进制构建、e2e 测试）。 |
| Appendix A | SSH Worker Extension | 描述 SSH‑based worker 的工作流（远程 host、SSH keys、隧道、错误转发），以及需要考虑的安全/可靠性要点。 |
