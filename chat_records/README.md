# AI 聊天记录本地备份

这个目录存放从 Legado NG 的 MCP 接口同步下来的 AI 对话记录。

## 目录结构

```
chat_records/
├── README.md          # 本说明
├── index.json         # 会话索引（id、标题、时间、消息数、工具调用数）
├── raw/
│   └── <会话ID>.json  # MCP 原始返回，包含完整消息、工具轨迹和 upload_messages
└── YYYY-MM-DD_<标题>_<短ID>.md   # 可直接阅读的 Markdown 版本
```

## 同步方式

```bash
# 默认读取 LEGADO_MCP_ENDPOINT 或 http://127.0.0.1:1124/mcp
python3 scripts/sync_chat_records.py --endpoint http://10.101.2.224:1124/mcp

# 指定输出目录和数量
python3 scripts/sync_chat_records.py \
  --endpoint http://10.101.2.224:1124/mcp \
  --out chat_records \
  --limit 100
```

脚本是只读的，只调用：

- `ai_chat_conversation_list`
- `ai_chat_conversation_get`

不会修改手机上的任何数据。

## 隐私说明

聊天记录可能包含书名、正文片段、角色名、模型调用信息和工具参数。为了不误提交到 GitHub：

- `chat_records/.gitignore` 默认忽略除 `README.md` 和 `.gitignore` 之外的所有文件。
- 如果你确实想把记录提交到仓库，删除 `chat_records/.gitignore` 后再 `git add`。
- 分享仓库或截图前，请先检查 `raw/` 和 Markdown 文件里是否有敏感内容。

## 常见问题

- **连接失败**：确认手机和电脑在同一网络，App 的 `我的 → 服务管理 → MCP 服务` 已开启，端口一致（默认 1124）。
- **USB 调试**：也可以 `adb forward tcp:1124 tcp:1124`，然后使用 `http://127.0.0.1:1124/mcp`。
- **记录不是最新**：重新执行同步脚本即可，同名文件会被覆盖为最新版本。
