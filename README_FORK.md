# Legado NG Fork · AI / MCP 增强

本仓库是 [joestar817/legado_NG](https://github.com/joestar817/legado_NG) 的个人 fork，目标是围绕 **AI 助手** 和 **MCP 工具层** 做功能增强。

- 上游项目：`joestar817/legado_NG`（源自阅读 Sigma，规则生态沿用 Legado）
- 许可证：**GNU GPL v3.0**，本 fork 同样遵循
- 上游 README 见 [README.md](README.md)

> 本文件只记录 fork 的定位、开发约定和当前改动，不替换上游 README。

---

## 改动与 PR 状态

| 功能 | PR | 状态 |
| --- | --- | --- |
| MCP 单本正文搜索 `bookshelf_text_search` | [#96](https://github.com/joestar817/legado_NG/pull/96) | 已合并进 `upstream/main` |
| 角色卡指定角色模式与正文选中入口 | [#97](https://github.com/joestar817/legado_NG/pull/97) | 待评审（head `7078310cd`，已处理同名语义与记忆开关单测） |
| 角色卡编辑页显示并复制生图提示词 | [#98](https://github.com/joestar817/legado_NG/pull/98) | 已合并进 `upstream/main` |
| AI 聊天 token 用量累计 | [#99](https://github.com/joestar817/legado_NG/pull/99) | 已合并进 `upstream/main`（2026-11-03） |

`#97` 原先基于 `#96` 堆叠；`#96` 合并后，`#97` 的 diff 已收敛到 12 个文件。分支上的提交都保留，Review 修改使用新增提交，不 force-push。

---

## 功能详情

### 1. 新增 MCP 工具：`bookshelf_text_search`（单本正文搜索）

**用途**：让 AI 在做角色卡、扫书等任务时，先在**一本书**里定位"某角色出现在哪些章节"，然后只读取这些章节，避免通读全书浪费 token。

**状态**：已实现并合并（PR #96，`19d7b3058`）。Debug 编译、MCP 目录/路由单测、匹配器单测通过；MCP 集成脚本与真机联调仍需按设备环境单独执行。

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

`assets/skills/character_card_generate.md` 已升级到版本 28：

- `mcp_capabilities` 增加 `bookshelf.search_content`
- preview 阶段允许工具增加 `bookshelf_text_search`
- 新增"用正文搜索定位角色章节"流程：拿到角色名/别名后一次性搜索，按命中章节选读
- 高频主角按确定性规则稀疏采样（fast 6 章 / balanced 12 章 / deep 20 章），避免把上百个命中章节读完
- 预览与应用硬门禁：扫描强度不等于写入授权，必须先展示待审核表格并等待明确应用确认
- 记忆关闭时自动降级为纯聊天流程，不再阻塞或产生待写入告警
- 探索预算与追读预算分离，避免窗口数与单轮上限互相矛盾
- 应用确认块提供固定 JSON 结构，部分写入失败标记为 `partial` 并支持只重试失败项
- 指定角色入口直接搜索缓存章节，不再强制询问范围；发现模式保留范围/强度选择
- 同名角色统一收敛为「更新已有 / 跳过」，不提供“新建为不同角色”；同一作品同名不同人物暂不支持分别建卡
- 章节号统一按 1-based 换算，已有角色卡按 name/aliases 去重并复用 id 更新
- 单文件约 430 行；`references/` 拆分需要额外的 Agent Skill 包加载支持，暂未启用
- 去掉 `intro` 长度限制；缓存按 `next_start` 分页；MCP 结果新增 `chapter_number`
- 发现模式每个候选至少读 1 个命中窗口；窗口和片段不重复读，片段折算追读预算
- `AiChatClient` 改为累计一轮内所有模型调用的真实 token，不再只记录最后一次调用

#### 正文选中入口（PR #97）

阅读页长按选中文本后，操作菜单新增「创建角色卡」：

- 只接受单个角色名：自动去掉引号、书名号和括号，长度超过 24、含换行或标点时会提示「请只选择一个角色名字」
- 入口把 `work_key`、书名/作者、`book_url`、当前章节号（1-based）、章节标题和总章节数写入 `AgentModeEntryContext`
- 自动加载 `character_card_generate`，并以“指定角色模式”预填输入：直接使用当前书已缓存章节，不再询问扫描范围或强度
- 正文选中菜单的顺序不做历史迁移，新动作追加在已保存顺序之后，用户仍可在设置里调整
- 当前入口不新增 MCP 工具，复用 `bookshelf.search_content` / `bookshelf.read_content`

真机验证（vivo PD2256，Android 16，`3.26.110315debug`）：

- 已验证：菜单入口、会话标题、Skill 芯片、选中角色附件、预填提示词、设备内 Skill 从 v20 自动升级到 v27
- 未验证：真实模型调用、预览表格、应用/取消、已有角色更新

#### 改动清单

| 文件 | 改动 |
| --- | --- |
| `app/src/main/java/io/legado/app/web/mcp/BookshelfMcpTools.kt` | 工具定义 + `call()` 分发 + 扫描实现 |
| `app/src/main/java/io/legado/app/web/mcp/McpTextQuery.kt` | 新增纯匹配器（关键词/正则、计数、片段） |
| `app/src/main/java/io/legado/app/web/mcp/McpInternalToolCatalog.kt` | 新增能力 `bookshelf.search_content` |
| `app/src/main/assets/skills/character_card_generate.md` | 版本 28：双模式、章节号换算、去重、分析/生成分离、缓存分页、候选补读、片段预算、真实 token 统计、同名角色收敛为更新或跳过 |
| `app/src/test/java/io/legado/app/web/mcp/McpTextQueryTest.kt` | 匹配与片段单元测试 |
| `docs/MCP_API.md` | 工具总览、能力分组、调用示例 |
| `scripts/test_mcp_api.py` | `EXPECTED_TOOLS` 与只读用例 |
| `app/src/main/java/io/legado/app/ui/book/read/ReadBookActivity.kt` | 文本选择菜单「创建角色卡」入口与角色名校验 |
| `app/src/main/java/io/legado/app/ui/book/info/BookAiAssistantLauncher.kt` | 构造 `text_selection_character_card` 入口上下文与预填提示词 |
| `app/src/main/java/io/legado/app/help/config/TextSelectionActionOrder.kt` | 注册新动作；不再迁移旧顺序 |
| `app/src/main/res/menu/content_select_action.xml` | 新增 `menu_character_card` |
| `scripts/test_character_card_skill.py` | 指定角色模式与 v27 策略测试（21 个用例） |

### 2. 后续方向（待定）

- 全书架范围正文搜索（需异步任务 + 轮询）
- 持久化全文索引（Room FTS）
- MCP 外部通道鉴权（token / 只读模式）
- AI 聊天接入非 OpenAI 兼容协议（Claude / Gemini 原生格式）

---

## AI 提供商配置

AI 设置 → 提供商页面在 2026-11 合并了以下改进（上游 PR #93、#95）。

### 列表卡片

- 副标题显示 Base URL host；名称与 host 相同时省略，避免重复
- 状态行显示「已启用/已禁用」、Key 状态和模型数量
- 未配置 API Key 显示「未配置 Key」，不再显示「0 个模型」
- 已配置 Key 但未拉取到模型显示「未获取模型」
- 移除「当前使用」标签

「当前使用」来自 `aiActiveProviderId`，但该偏好没有 UI 可以设置，实际 AI 功能都显式传入自己的 `providerId`。保留标签会展示陈旧偏好，反而误导用户。

### 自定义提供商命名

- 新建自定义 provider 时，默认名称取 Base URL host，例如 `api.openai.com`
- 修改 Base URL 时，自动名称跟随 host 变化
- 手动修改名称后，后续 Base URL 修改不再覆盖名称
- 自动状态由表单字段 `nameAutoGenerated` 显式记录，不再用当前 host 反推
- 修复了 Base URL 经过 `https://` 这类空 host 中间态后名称不再跟随的问题

### 重置设置

提供商详情 → 配置页底部新增「重置设置」，点击后弹出确认框。

恢复默认：

- 名称（内置 provider 恢复内置名称；自定义 provider 的手动名称保留）
- Base URL
- API 路径
- 超时
- 流式响应、自定义余额 API、自定义模型列表 API 等开关和地址

保留：

- API Key
- 启用/禁用状态
- 已获取的模型列表
- 已选模型

这样误改 Base URL 后可以直接恢复，不需要重新填写 Key 或重新拉取模型。

### 内置提供商启用状态

- 移除读取配置时强制启用全部内置 provider 的逻辑
- 只在首次初始化（本地没有提供商配置）时启用内置 provider
- 之后尊重用户手动禁用状态，不再在每次读取时改回来

### 模型能力恢复

模型编辑抽屉在「模型类型」下方新增「按模型名重新识别」：

- 按 `AiModelRegistry` 恢复模型类型、输入/输出模态、Tool/Reasoning 能力
- 仅对注册表能识别的模型显示按钮
- 未知模型不显示，避免把私有模型静默重置成聊天模型
- 不修改显示名称

### 遗留代码

`activeProviderId()` / `activeProvider()` / `setActiveProvider()`、`PreferKey.aiActiveProviderId`、`AiConfig.currentSetting()` / `savedModels()` / `saveModels()` / `clearModels()` 目前仍保留，但已没有 UI 或实际功能依赖，建议后续单独清理。

---

## 角色卡生图提示词

角色卡编辑弹窗新增「生图提示词」字段（PR #98，已合并：`79196b6ac`）：

- 显示并编辑 `BookCharacter.imagePrompt`
- 非空时提供「复制」按钮，复制到系统剪贴板
- 该字段仅保存提示词，当前不会自动调用生图模型

---

## AI 聊天 token 用量

`AiChatClient` 累计一轮内所有模型调用的 usage，而不是只保留最后一次调用（PR #99）。

累计规则（`AiChatUsageAccumulator`）：

- `prompt_tokens` / `completion_tokens` / `total_tokens` 分别记录“是否上报”，缺失字段保持 `null`，不会补 0
- `total_tokens` 优先累计服务端每次调用上报的值
- 服务端未返回 `total` 时，只有单次调用的 prompt 和 completion 都已知，才用二者补算总量
- 多次调用中存在缺失 usage 时，`warnings` 会追加“本轮有 N 次模型调用未返回用量，token 统计仅包含已返回的部分”
- 全部调用都没有 usage 时结果为 `null`，避免 UI 显示 `↑0 / ↓0`

回归测试 `AiChatUsageAccumulatorTest` 覆盖完整/部分/全缺失 usage、多次调用、流式最终 chunk 和上报 0，共 9 个用例。

状态：P2 修正已提交到 `feature/ai-token-usage`（`d62a2eff8`），等待评审；仅有单测与编译验证，未做真机真实提供商回归。

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

产物：`app/build/outputs/apk/app/debug/legado_app_*.apk`（包名 `io.legado.app.ngs.debug`）。

Release 需要在 `app/signing.properties` 或命令行提供 `RELEASE_STORE_FILE` 等参数；未配置时只产出未签名包。

---

## 构建与发布（custom 分支）

`custom` 是自用的全功能集成分支，包名和发布链路与上游完全隔离：

| 项 | 值 |
| --- | --- |
| `applicationId` | `io.legado.app.ngs` |
| Release 包名 | `io.legado.app.ngs.release` |
| Debug 包名 | `io.legado.app.ngs.debug` |
| 桌面显示名 | 阅读NGS |
| 与官方包 | 包名不同，可与 `io.legado.app.ng.release` 共存安装 |

包名不能随意再改：Android 用「包名 + 签名证书」判定升级，换包名相当于换了一个 App，旧数据不会迁移，需要先在旧版做 `设置 → 备份与恢复` 再导入。

### 自动构建

push `custom` 触发 `.github/workflows/custom-apk.yml`：

1. JDK 17 + `assembleAppRelease`
2. 用仓库 Secrets 里的 keystore 签名（`RELEASE_KEY_STORE` / `RELEASE_KEY_ALIAS` / `RELEASE_KEY_PASSWORD` / `RELEASE_STORE_PASSWORD`）
3. 上传 Actions Artifact
4. 删除并重建滚动 Release `custom-latest`

滚动 Release 固定地址：`https://github.com/kmulemg/legado_NGS/releases/tag/custom-latest`

手动触发：`gh workflow run custom-apk.yml --ref custom -R kmulemg/legado_NGS`（本目录下 `gh` 会默认解析到上游 `joestar817/legado_NG`，必须带 `-R`）。连续 push 时并发组只保留最后一次构建。

两条硬约束：

- Release 资产名必须是 `legado_NG_<版本>00_release.apk`（匹配 `AppVersion.assetNameRegex`）
- Release 不能勾 `prerelease`，因为应用内更新走 `releases/latest`，该接口不返回 prerelease

### 应用内更新

`AppUpdateRelay.RELEASE_OWNER` 与 `AppUpdateGitHub` 的接口地址都指向本 fork，所以「检查更新」只看 `kmulemg/legado_NGS` 的 Release，不再提示上游版本（包名不同，装了也覆盖不了）。

改动更新相关代码后运行：

```bash
./gradlew :app:testAppDebugUnitTest --tests "io.legado.app.help.update.*"
```

---

## 与上游同步

仓库默认分支是 `custom`：GitHub 的 `schedule` 只执行默认分支上的 workflow，而同步脚本属于 fork 专属文件。`main` 是上游的纯镜像，不含 fork 提交，可以随时快进。

自动同步由 `.github/workflows/sync-upstream.yml` 完成，每天 04:00（北京时间）：

1. 调 `POST /repos/kmulemg/legado_NGS/merge-upstream` 把 `main` 快进到 `upstream/main`
2. 把 `main` 合入 `custom`，成功则 push 并派发 `custom-apk`
3. 冲突则不推送，开/追加标题含 `upstream-sync` 的 issue 列出冲突文件

手动同步：

```bash
git fetch upstream
git branch -f main upstream/main     # main 未被 checkout 时
git switch custom
git merge main
```

高频冲突点：`app/src/main/res/values/strings.xml` 与 `values-zh/strings.xml`（AI 字符串重复定义），以及 custom 专属的 `applicationId`、`AppUpdateRelay.RELEASE_OWNER`。本机已启用 `git rerere`，相同冲突会自动复用上次解法；CI 上没有 rerere，遇到冲突会停下来开 issue 等人工处理。

浅克隆需先 `git fetch --unshallow`。

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
