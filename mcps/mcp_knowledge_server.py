#!/usr/bin/env python3
"""
MCP Knowledge Server — 本地知识库搜索工具

通过 JSON-RPC 2.0 over stdio 提供 MCP 接口。
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any


# ── 常量 ──────────────────────────────────────────────────────────────────

ARTICLES_DIR = Path(
    os.environ.get(
        "KNOWLEDGE_ARTICLES_DIR",
        Path(__file__).resolve().parent.parent / "knowledge" / "articles",
    )
)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

TOOL_SEARCH = "search_articles"
TOOL_GET = "get_article"
TOOL_STATS = "knowledge_stats"


# ── 数据加载 ──────────────────────────────────────────────────────────────


def _read_articles() -> list[dict[str, Any]]:
    if not ARTICLES_DIR.is_dir():
        return []
    articles: list[dict[str, Any]] = []
    for path in sorted(ARTICLES_DIR.glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, list):
            articles.extend(data)
        elif isinstance(data, dict):
            articles.append(data)
    return articles


_cache: list[dict[str, Any]] | None = None


def _get_articles() -> list[dict[str, Any]]:
    global _cache
    if _cache is None:
        _cache = _read_articles()
    return _cache


# ── 工具实现 ──────────────────────────────────────────────────────────────


def search_articles(keyword: str, limit: int = 5) -> dict[str, Any]:
    articles = _get_articles()
    keyword_lower = keyword.lower()
    results: list[dict[str, Any]] = []
    for art in articles:
        title = str(art.get("title", "")).lower()
        summary = str(art.get("summary", "")).lower()
        if keyword_lower in title or keyword_lower in summary:
            results.append(
                {
                    "id": art.get("id"),
                    "title": art.get("title"),
                    "source": art.get("source", ""),
                    "summary": art.get("summary"),
                    "score": art.get("score"),
                    "tags": art.get("tags", []),
                }
            )
            if len(results) >= limit:
                break
    return {
        "content": [
            {"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}
        ]
    }


def get_article(article_id: str) -> dict[str, Any]:
    articles = _get_articles()
    for art in articles:
        if art.get("id") == article_id:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(art, ensure_ascii=False, indent=2),
                    }
                ]
            }
    return {
        "isError": True,
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {"error": f"article not found: {article_id}"},
                    ensure_ascii=False,
                ),
            }
        ],
    }


def _get_source(art: dict[str, Any]) -> str:
    source = art.get("source", "")
    if source:
        return source
    source_url = art.get("source_url", "")
    if not source_url:
        return "unknown"
    for domain, label in [
        ("arxiv", "arxiv"),
        ("github", "github"),
        ("huggingface", "huggingface"),
        ("twitter", "twitter"),
        ("x.com", "twitter"),
    ]:
        if domain in source_url.lower():
            return label
    return "other"


def knowledge_stats() -> dict[str, Any]:
    articles = _get_articles()
    total = len(articles)
    source_counter: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()

    for art in articles:
        source_counter[_get_source(art)] += 1
        for tag in art.get("tags", []):
            if isinstance(tag, str) and tag.strip():
                tag_counter[tag.strip().lower()] += 1

    hot_tags = [
        {"tag": tag, "count": count}
        for tag, count in tag_counter.most_common(10)
    ]

    stats = {
        "total_articles": total,
        "source_distribution": dict(source_counter.most_common()),
        "hot_tags": hot_tags,
    }
    return {
        "content": [
            {"type": "text", "text": json.dumps(stats, ensure_ascii=False, indent=2)}
        ]
    }


# ── MCP 协议 ──────────────────────────────────────────────────────────────

_TOOLS = [
    {
        "name": TOOL_SEARCH,
        "description": "按关键词搜索文章标题和摘要",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "limit": {
                    "type": "number",
                    "default": 5,
                    "description": "返回结果数量上限",
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": TOOL_GET,
        "description": "按 ID 获取文章完整内容",
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "文章 ID",
                },
            },
            "required": ["article_id"],
        },
    },
    {
        "name": TOOL_STATS,
        "description": "返回知识库统计信息（文章总数、来源分布、热门标签）",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

_TOOL_DISPATCH: dict[str, Any] = {
    TOOL_SEARCH: search_articles,
    TOOL_GET: get_article,
    TOOL_STATS: knowledge_stats,
}


def _rpc_result(
    result: Any, req_id: int | str | None = None
) -> dict[str, Any]:
    resp: dict[str, Any] = {"jsonrpc": "2.0", "result": result}
    if req_id is not None:
        resp["id"] = req_id
    return resp


def _rpc_error(
    code: int, message: str, req_id: int | str | None = None
) -> dict[str, Any]:
    resp: dict[str, Any] = {
        "jsonrpc": "2.0",
        "error": {"code": code, "message": message},
    }
    if req_id is not None:
        resp["id"] = req_id
    return resp


def _handle_request(msg: dict[str, Any]) -> dict[str, Any] | None:
    method: str = msg.get("method", "")
    req_id = msg.get("id")

    if method.startswith("notifications/"):
        return None

    if method == "initialize":
        params = msg.get("params") or {}
        return _rpc_result(
            {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "mcp-knowledge-server",
                    "version": "1.0.0",
                },
            },
            req_id,
        )

    if method == "tools/list":
        return _rpc_result({"tools": _TOOLS}, req_id)

    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        handler = _TOOL_DISPATCH.get(name)
        if handler is None:
            return _rpc_result(
                {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {"error": f"unknown tool: {name}"}
                            ),
                        }
                    ],
                },
                req_id,
            )
        try:
            result = handler(**arguments)
        except TypeError as e:
            return _rpc_result(
                {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {"error": f"invalid arguments: {e}"},
                                ensure_ascii=False,
                            ),
                        }
                    ],
                },
                req_id,
            )
        except Exception as e:
            return _rpc_result(
                {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {"error": f"execution error: {e}"},
                                ensure_ascii=False,
                            ),
                        }
                    ],
                },
                req_id,
            )
        return _rpc_result(result, req_id)

    return _rpc_error(METHOD_NOT_FOUND, f"method not found: {method}", req_id)


def main() -> None:
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as e:
            resp = _rpc_error(PARSE_ERROR, f"parse error: {e}")
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue

        if not isinstance(msg, dict) or "method" not in msg:
            resp = _rpc_error(
                INVALID_REQUEST,
                "invalid request: missing 'method'",
                msg.get("id") if isinstance(msg, dict) else None,
            )
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue

        try:
            resp = _handle_request(msg)
        except Exception as e:
            resp = _rpc_error(INTERNAL_ERROR, f"internal error: {e}", msg.get("id"))

        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
