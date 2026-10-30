# Legado NG Fork · AI / MCP 增强

本仓库是 [joestar817/legado_NG](https://github.com/joestar817/legado_NG) 的个人 fork，目标是围绕 **AI 助手** 和 **MCP 工具层** 做功能增强。

- 上游项目：`joestar817/legado_NG`（源自阅读 Sigma，规则生态沿用 Legado）
- 许可证：**GNU GPL v3.0**，本 fork 同样遵循
- 上游 README 见 [README.md](README.md)

> 本文件只记录 fork 的定位、开发约定和当前改动，不替换上游 README。

---

## 当前目标

### 1. 新增 MCP 工具：`bookshelf_text_search`（正文搜索）

让 App 内置 AI 和外部 MCP 客户端能够在**已缓存 / 本地**的章节正文中检索关键词或正则，并返回章节位置与上下文片段。

**状态**：可行性已确认，设计已定稿，尚未实现。

#### 为什么可行

- 阅读页已有同构实现：`ui/book/searchContent/SearchContentViewModel.kt`（逐章读取 → 匹配 → 截取上下文）。
- MCP 侧已有书籍定位、目录读取、正文读取能力，可直接复用。
- 正文以文件形式保存在 `book_cache/`，本地书实时解析；无需改数据库即可实现。

#### 已知约束

| 约束 | 说明 |
| --- | --- |
| 无全文索引 | 正文不在 SQLite 中，只能逐章读文件扫描 |
| 仅限已缓存/本地 | 与现有 MCP 读接口一致，不主动联网抓取未缓存章节 |
| 同步协议 | MCP 当前是同步 JSON-RPC，无任务/SSE，必须限制单次扫描量并支持分页 |
| 成本可控 | 默认扫描 200 章、命中 50 条即停，返回 `has_more` 和下一页起点 |

#### 接口设计（草案）

工具名：`bookshelf_text_search`，只读（`McpToolSideEffect.READ`），归属书架模块。

参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `work_key` / `book_url` / `name`+`author` | string | — | 书籍定位，复用 `resolveBook` |
| `query` | string | 必填 | 关键词 |
| `regex` | boolean | false | 正则搜索 |
| `match_case` | boolean | false | 区分大小写 |
| `start_chapter_index` | int | 0 | 起始章节（含） |
| `max_chapters` | int | 200 | 单次扫描上限，最大 2000 |
| `max_results` | int | 50 | 命中上限，最大 200 |
| `context_chars` | int | 40 | 命中点左右各取字符数 |
| `apply_replace` | boolean | false | 是否套用本书净化规则 |

返回要点：

```json
{
  "book": { "work_key": "...", "name": "...", "author": "..." },
  "scanned_chapters": 200,
  "total_chapters": 3120,
  "cached_chapters_in_range": 180,
  "matched_chapters": 3,
  "total_matches": 7,
  "results": [
    {
      "chapter_index": 42,
      "chapter_title": "第四十二章 夜行",
      "match_count": 2,
      "matches": [
        { "position": 1830, "snippet": "……上下文片段……" }
      ]
    }
  ],
  "has_more": true,
  "next_start_chapter_index": 200
}
```

明确不做：

- 不返回整章正文（由 `bookshelf_chapter_content_get` 负责）
- 不联网补取未缓存章节
- 不做简繁转换（避免 offset 与原文不一致）
- 默认不套净化规则（显式开启 `apply_replace` 才生效）

#### 改动清单

| 文件 | 改动 |
| --- | --- |
| `app/src/main/java/io/legado/app/web/mcp/BookshelfMcpTools.kt` | 工具定义 + `call()` 分发 + 实现 |
| `app/src/main/java/io/legado/app/web/mcp/McpInternalToolCatalog.kt` | 新增能力 `bookshelf.search_content` |
| `docs/MCP_API.md` | 工具总览、能力分组、调用示例 |
| `scripts/test_mcp_api.py` | `EXPECTED_TOOLS` 与只读用例 |

### 2. 后续方向（待定）

- 全书架范围正文搜索（需异步任务 + 轮询）
- 持久化全文索引（Room FTS）
- MCP 外部通道鉴权（token / 只读模式）
- AI 聊天接入非 OpenAI 兼容协议（Claude / Gemini 原生格式）

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
