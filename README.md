# AI Knowledge 知识库

自动化技术情报收集与分析系统，持续追踪 AI/LLM/Agent 领域的高质量技术资讯。

## 核心功能

- 多源数据采集：GitHub Trending、Hacker News、arXiv
- 三阶段 Agent 流水线：采集 → 分析 → 整理
- 结构化 JSON 输出，便于下游应用消费
- 每日自动运行，保持知识库更新

## 项目结构

```
.
├── AGENTS.md                 # 项目定义与工作流规范
├── .env                     # 环境变量配置
├── .opencode/
│   └── agents/              # Agent 角色定义
│       ├── collector.md     # 采集 Agent
│       ├── analyzer.md     # 分析 Agent
│       └── organizer.md    # 整理 Agent
└── knowledge/
    ├── raw/                # 原始采集数据
    └── articles/           # 整理后的知识条目
```

## 快速开始

1. 配置环境变量（参考 `.env.example`）

2. 调用 Agent 执行流水线

```bash
# 采集数据
@collector 采集今天的 GitHub Trending

# 分析数据
@analyzer 分析 knowledge/raw/github-trending-2026-04-17.json

# 整理知识条目
@organizer 整理今天所有已分析的原始数据
```

## 工作流

```
[Collector] ──采集──→ knowledge/raw/
                      │
[Analyzer]  ──分析──→ knowledge/raw/ (enriched)
                      │
[Organizer] ──整理──→ knowledge/articles/
```

## 技术栈

- OpenCode + LLM（DeepSeek / Qwen）
- GitHub API v3、Hacker News API
