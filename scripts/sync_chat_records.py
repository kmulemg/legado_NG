#!/usr/bin/env python3
"""Sync Legado NG AI chat conversations from the native MCP endpoint to local files.

The script is read-only: it calls `ai_chat_conversation_list` and
`ai_chat_conversation_get`, then writes Markdown transcripts plus raw JSON.

Usage:
    python3 scripts/sync_chat_records.py --endpoint http://10.101.2.224:1124/mcp
    LEGADO_MCP_ENDPOINT=http://127.0.0.1:1124/mcp python3 scripts/sync_chat_records.py

Output (default `chat_records/`):
    README.md
    index.json
    raw/<conversation-id>.json
    YYYY-MM-DD_<title>_<short-id>.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_ENDPOINT = os.environ.get(
    "LEGADO_MCP_ENDPOINT", "http://127.0.0.1:1124/mcp"
)
LIST_PAGE_SIZE = 50
MAX_MESSAGE_LIMIT = 300
MAX_TEXT_CHARS = 64_000
MAX_UPLOAD_CHARS = 128_000


class McpError(RuntimeError):
    pass


def rpc(endpoint: str, method: str, params: dict[str, Any] | None = None) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000) % 2_000_000_000,
        "method": method,
        "params": params or {},
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as error:
        raise McpError(f"无法连接 {endpoint}: {error}") from error
    except json.JSONDecodeError as error:
        raise McpError(f"MCP 返回了非 JSON 响应: {error}") from error
    if "error" in body:
        error = body["error"]
        raise McpError(f"{method} 失败: {error.get('message', error)}")
    return body.get("result")


def call_tool(endpoint: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = rpc(
        endpoint,
        "tools/call",
        {
            "name": name,
            "arguments": arguments,
        },
    )
    if not isinstance(result, dict):
        raise McpError(f"{name} 返回格式异常")
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        if structured.get("ok") is False:
            warnings = structured.get("warnings") or []
            raise McpError(f"{name} 失败: {'; '.join(map(str, warnings))}")
        return structured
    # Some tools only return content[].text.
    content = result.get("content") or []
    if content and isinstance(content[0], dict) and "text" in content[0]:
        return json.loads(content[0]["text"])
    raise McpError(f"{name} 返回缺少 structuredContent")


def list_conversations(endpoint: str, limit: int) -> list[dict[str, Any]]:
    conversations: list[dict[str, Any]] = []
    offset = 0
    while len(conversations) < limit:
        page_limit = min(LIST_PAGE_SIZE, limit - len(conversations))
        data = call_tool(
            endpoint,
            "ai_chat_conversation_list",
            {"offset": offset, "limit": page_limit},
        )
        normalized = data.get("normalized_data") or {}
        page = normalized.get("conversations") or []
        conversations.extend(page)
        total = int(normalized.get("total") or 0)
        offset += len(page)
        if not page or offset >= total:
            break
    return conversations[:limit]


def fetch_detail(endpoint: str, conversation_id: str, include_upload: bool) -> dict[str, Any]:
    data = call_tool(
        endpoint,
        "ai_chat_conversation_get",
        {
            "id": conversation_id,
            "message_offset": 0,
            "message_limit": MAX_MESSAGE_LIMIT,
            "text_char_limit": MAX_TEXT_CHARS,
            "include_reasoning": True,
            "include_upload_messages": include_upload,
            "upload_char_limit": MAX_UPLOAD_CHARS,
        },
    )
    return data.get("normalized_data") or {}


def safe_title(value: str, fallback: str) -> str:
    text = (value or "").strip() or fallback
    text = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "-", text)
    text = re.sub(r"\s+", " ", text).strip(" .-")
    return (text[:60] or fallback).strip(" .-")


def conversation_date(conversation: dict[str, Any]) -> str:
    text = str(conversation.get("create_time_text") or "")
    if len(text) >= 10:
        return text[:10]
    timestamp = conversation.get("create_at")
    if isinstance(timestamp, (int, float)) and timestamp > 0:
        return dt.datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")
    return dt.date.today().isoformat()


def markdown_file_name(conversation: dict[str, Any]) -> str:
    conversation_id = str(conversation.get("id") or "unknown")
    title = safe_title(str(conversation.get("title") or ""), conversation_id[:8])
    return f"{conversation_date(conversation)}_{title}_{conversation_id[:8]}.md"


def render_markdown(
    endpoint: str,
    detail: dict[str, Any],
    synced_at: str,
    raw_name: str,
) -> str:
    conversation = detail.get("conversation") or {}
    messages = detail.get("messages") or []
    lines: list[str] = []
    title = conversation.get("title") or "未命名会话"
    lines.append(f"# {title}")
    lines.append("")
    lines.append("| 字段 | 值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 会话 ID | `{conversation.get('id', '')}` |")
    lines.append(f"| 创建时间 | {conversation.get('create_time_text', '')} |")
    lines.append(f"| 更新时间 | {conversation.get('update_time_text', '')} |")
    lines.append(f"| 消息数 | {detail.get('message_total', len(messages))} |")
    lines.append(f"| 工具调用数 | {conversation.get('tool_trace_count', 0)} |")
    skills = conversation.get("loaded_skill_ids") or []
    lines.append(f"| 已加载 Skill | {', '.join(map(str, skills)) if skills else '无'} |")
    lines.append(f"| 同步时间 | {synced_at} |")
    lines.append(f"| 来源 | `{endpoint}` |")
    lines.append(f"| 原始 JSON | `raw/{raw_name}` |")
    lines.append("")

    for index, message in enumerate(messages):
        role = message.get("role") or "unknown"
        lines.append(f"## {index + 1}. {role}")
        lines.append("")
        content = str(message.get("content") or "")
        lines.append(content if content.strip() else "_（空）_")
        lines.append("")

        reasoning = str(message.get("reasoning") or "")
        if reasoning.strip():
            lines.append("<details><summary>推理过程</summary>")
            lines.append("")
            lines.append(reasoning)
            lines.append("")
            lines.append("</details>")
            lines.append("")

        tool_trace = message.get("tool_trace") or []
        if tool_trace:
            lines.append(f"<details><summary>工具调用（{len(tool_trace)}）</summary>")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(tool_trace, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def sync(endpoint: str, out_dir: Path, limit: int, include_upload: bool) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    synced_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conversations = list_conversations(endpoint, limit)
    index_items: list[dict[str, Any]] = []

    for conversation in conversations:
        conversation_id = str(conversation.get("id") or "")
        if not conversation_id:
            continue
        try:
            detail = fetch_detail(endpoint, conversation_id, include_upload)
        except McpError as error:
            print(f"[skip] {conversation_id}: {error}", file=sys.stderr)
            continue

        raw_name = f"{conversation_id}.json"
        raw_payload = {
            "synced_at": synced_at,
            "endpoint": endpoint,
            **detail,
        }
        (raw_dir / raw_name).write_text(
            json.dumps(raw_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        markdown_name = markdown_file_name(conversation)
        (out_dir / markdown_name).write_text(
            render_markdown(endpoint, detail, synced_at, raw_name),
            encoding="utf-8",
        )
        index_items.append(
            {
                "id": conversation_id,
                "title": conversation.get("title") or "",
                "create_time_text": conversation.get("create_time_text") or "",
                "update_time_text": conversation.get("update_time_text") or "",
                "message_count": conversation.get("message_count") or 0,
                "tool_trace_count": conversation.get("tool_trace_count") or 0,
                "loaded_skill_ids": conversation.get("loaded_skill_ids") or [],
                "markdown": markdown_name,
                "raw": f"raw/{raw_name}",
            }
        )
        print(f"[ok] {conversation.get('title') or conversation_id} -> {markdown_name}")

    (out_dir / "index.json").write_text(
        json.dumps(
            {
                "synced_at": synced_at,
                "endpoint": endpoint,
                "count": len(index_items),
                "conversations": index_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n同步完成：{len(index_items)} 个会话 -> {out_dir}")
    return len(index_items)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把 Legado NG 的 AI 聊天记录同步到本地 Markdown/JSON"
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"MCP endpoint，默认 {DEFAULT_ENDPOINT}",
    )
    parser.add_argument(
        "--out",
        default="chat_records",
        help="输出目录，默认 chat_records",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="最多同步多少个会话，默认 100",
    )
    parser.add_argument(
        "--no-upload-messages",
        action="store_true",
        help="不保存会话的完整上下文 upload_messages_json（默认保存）",
    )
    args = parser.parse_args()
    try:
        sync(
            endpoint=args.endpoint,
            out_dir=Path(args.out),
            limit=max(1, args.limit),
            include_upload=not args.no_upload_messages,
        )
    except McpError as error:
        print(f"同步失败: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
