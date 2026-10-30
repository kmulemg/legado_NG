# Legado NG Fork · AI / MCP 增强

本仓库是 [joestar817/legado_NG](https://github.com/joestar817/legado_NG) 的个人 fork，目标是围绕 **AI 助手** 和 **MCP 工具层** 做功能增强。

- 上游项目：`joestar817/legado_NG`（源自阅读 Sigma，规则生态沿用 Legado）
- 许可证：**GNU GPL v3.0**，本 fork 同样遵循
- 上游 README 见 [README.md](README.md)

> 本文件只记录 fork 的定位、开发约定和当前改动，不替换上游 README。

---

## 当前目标

### 1. 新增 MCP 工具：`bookshelf_text_search`（单本正文搜索）

**用途**：让 AI 在做角色卡、扫书等任务时，先在**一本书**里定位"某角色出现在哪些章节"，然后只读取这些章节，避免通读全书浪费 token。

**状态**：已实现；Debug 编译、MCP 目录/路由单测、匹配器单测通过；待真机联调。

#### 为什么可行

- 阅读页已有同构实现：`ui/book/searchContent/SearchContentViewModel.kt`（逐章读取 → 匹配 → 截取上下文）。
- MCP 侧已有书籍定位、目录读取、正文读取能力，可直接复用。
- 正文以文件形式保存在 `book_cache/`，本地书实时解析；无需改数据库即可实现。

#### 已知约束

| 约束 | 说明 |
| --- | --- |
| 仅单本 | 不支持跨书架全局搜索；全局搜索需要异步任务，留到二期 |
| 无全文索引 | 正文不在 SQLite 中，只能逐章读文件扫描 |
| 仅限已缓存/本地 | 与现有 MCP 读接口一致，不主动联网抓取未缓存章节 |
| 同步协议 | 默认扫描整本缓存，但命中上限 500 章或 15 秒即停，返回 `has_more` 与续扫位置 |
| 默认不给正文 | `include_snippets=false`，只返回章节命中清单，token 成本最低 |

#### 接口设计

工具名：`bookshelf_text_search`，只读（`McpToolSideEffect.READ`），归属书架模块，能力项 `bookshelf.search_content`。

参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `work_key` / `book_url` / `name`+`author` | string | — | 书籍定位，复用 `resolveBook` |
| `query` | string | — | 单个关键词或正则 |
| `queries` | string[] | — | 最多 10 个关键词，用于一次传入角色名 + 全部别名 |
| `regex` | boolean | false | 正则搜索 |
| `ignore_case` | boolean | true | 忽略大小写 |
| `start_chapter_index` | int | 0 | 起始章节（含） |
| `end_chapter_index` | int | 全部 | 结束章节（含） |
| `max_matched_chapters` | int | 200 | 命中章节上限，最大 500 |
| `include_snippets` | boolean | false | 是否返回上下文片段 |
| `snippet_chars` | int | 30 | 片段左右各取字符数，最大 200 |
| `snippets_per_chapter` | int | 2 | 每章每个查询的片段数，最大 5 |
| `time_budget_ms` | int | 15000 | 扫描时间预算，最大 60000 |
| `apply_replace` | boolean | false | 是否套用本书净化规则 |

返回要点：

```json
{
  "book": { "work_key": "...", "name": "...", "author": "..." },
  "queries": [
    { "query": "林动", "matched_chapters": 87, "total_matches": 431, "chapter_indexes": [3, 5, 7] },
    { "query": "小炎", "matched_chapters": 12, "total_matches": 30, "chapter_indexes": [3, 9] }
  ],
  "scanned_chapters": 3120,
  "missing_chapters": 0,
  "matched_chapters": 90,
  "total_matches": 461,
  "chapters": [
    {
      "index": 3,
      "title": "第三章 青阳镇",
      "count": 2,
      "hits": { "林动": 2 }
    }
  ],
  "has_more": false,
  "next_start_chapter_index": null
}
```

明确不做：

- 不返回整章正文（由 `bookshelf_chapter_content_get` / `bookshelf_text_window_get` 负责）
- 不联网补取未缓存章节
- 不做简繁转换（避免 offset 与原文不一致）
- 默认不套净化规则（显式开启 `apply_replace` 才生效）
- 不跨书架搜索

#### 角色卡 Skill 接入

`assets/skills/character_card_generate.md` 已升级到版本 27：

- `mcp_capabilities` 增加 `bookshelf.search_content`
- preview 阶段允许工具增加 `bookshelf_text_search`
- 新增"用正文搜索定位角色章节"流程：拿到角色名/别名后一次性搜索，按命中章节选读
- 高频主角按确定性规则稀疏采样（fast 6 章 / balanced 12 章 / deep 20 章），避免把上百个命中章节读完
- 预览与应用硬门禁：扫描强度不等于写入授权，必须先展示待审核表格并等待明确应用确认
- 记忆关闭时自动降级为纯聊天流程，不再阻塞或产生待写入告警
- 探索预算与追读预算分离，避免窗口数与单轮上限互相矛盾
- 应用确认块提供固定 JSON 结构，部分写入失败标记为 `partial` 并支持只重试失败项
- 指定角色入口直接搜索缓存章节，不再强制询问范围；发现模式保留范围/强度选择
- 章节号统一按 1-based 换算，已有角色卡按 name/aliases 去重并复用 id 更新
- 单文件约 430 行；`references/` 拆分需要额外的 Agent Skill 包加载支持，暂未启用
- 去掉 `intro` 长度限制；缓存按 `next_start` 分页；MCP 结果新增 `chapter_number`
- 发现模式每个候选至少读 1 个命中窗口；窗口和片段不重复读，片段折算追读预算
- `AiChatClient` 改为累计一轮内所有模型调用的真实 token，不再只记录最后一次调用


#### 改动清单

| 文件 | 改动 |
| --- | --- |
| `app/src/main/java/io/legado/app/web/mcp/BookshelfMcpTools.kt` | 工具定义 + `call()` 分发 + 扫描实现 |
| `app/src/main/java/io/legado/app/web/mcp/McpTextQuery.kt` | 新增纯匹配器（关键词/正则、计数、片段） |
| `app/src/main/java/io/legado/app/web/mcp/McpInternalToolCatalog.kt` | 新增能力 `bookshelf.search_content` |
| `app/src/main/assets/skills/character_card_generate.md` | 版本 27：双模式、章节号换算、去重、分析/生成分离、缓存分页、候选补读、片段预算、真实 token 统计 |
| `app/src/test/java/io/legado/app/web/mcp/McpTextQueryTest.kt` | 匹配与片段单元测试 |
| `docs/MCP_API.md` | 工具总览、能力分组、调用示例 |
| `scripts/test_mcp_api.py` | `EXPECTED_TOOLS` 与只读用例 |

### 2. 后续方向（待定）

- 全书架范围正文搜索（需异步任务 + 轮询）
- 持久化全文索引（Room FTS）
- MCP 外部通道鉴权（token / 只读模式）
- AI 聊天接入非 OpenAI 兼容协议（Claude / Gemini 原生格式）

---

## 调试工具

### AI 聊天记录本地同步

```bash
python3 scripts/sync_chat_records.py \
  --endpoint http://10.101.2.224:1124/mcp \
  --out chat_records
```

- 只读调用 `ai_chat_conversation_list` / `ai_chat_conversation_get`
- 输出 Markdown 转写、原始 JSON、会话索引
- `chat_records/.gitignore` 默认忽略记录文件，避免把书名、正文片段和工具参数提交到 GitHub

---

## 开发环境

| 依赖 | 版本 |
| --- | --- |
| JDK | **17**（项目使用 jvmToolchain 17） |
| Android SDK | compileSdk / targetSdk **36** |
| Gradle | 8.14.4（wrapper 自带） |
| Node.js | ≥ 20（仅 `modules/web` 需要） |

首次准备：

```bash
# 1. 安装 JDK 17
brew install --cask temurin@17

# 2. 安装 Android SDK（cmdline-tools + platform 36 + build-tools）
#    然后写入 local.properties
echo "sdk.dir=$HOME/Library/Android/sdk" > local.properties

# 3. 编译 Debug 包
./gradlew assembleAppDebug

# 4. 单元测试（Robolectric / Roborazzi）
./gradlew testAppDebugUnitTest
```

产物：`app/build/outputs/apk/app/debug/legado_app_*.apk`（包名 `io.legado.app.ng.debug`）。

Release 需要在 `app/signing.properties` 或命令行提供 `RELEASE_STORE_FILE` 等参数；未配置时只产出未签名包。

---

## 与上游同步

```bash
git remote -v          # origin = 本 fork，upstream = joestar817/legado_NG
git fetch upstream
git merge upstream/main      # 或 git rebase upstream/main
```

如果本地是浅克隆，先补全历史：

```bash
git fetch --unshallow
```

---

## 开发约定

新增或修改 MCP 工具时，务必**同时**处理以下位置，避免权限或文档不一致：

1. 工具定义（`*McpTools.kt` 的 `tools()`）
2. 调用分发（同文件 `call()`）
3. 能力目录与副作用分级（`McpInternalToolCatalog.kt`）
4. 接口文档（`docs/MCP_API.md`）
5. 集成测试脚本（`scripts/test_mcp_api.py`）

UI 相关改动遵守仓库内规范：

- `docs/COMPOSE_MIGRATION_STANDARD.md`
- `docs/NG_DESIGN_SYSTEM_ARCHITECTURE.md`
- `docs/READING_NG_UI_STYLE.md`

---

## 致谢与许可

- 上游：[gedoor/legado](https://github.com/gedoor/legado) → [Luoyacheng/legado-E](https://github.com/Luoyacheng/legado-E) → [joestar817/legado_NG](https://github.com/joestar817/legado_NG)
- 本 fork 代码遵循 [GNU GPL v3.0](LICENSE)
- 第三方素材权利归各自作者所有
