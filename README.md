# 远见工作台

面向跨境电商团队的本地调研工作台：从多平台关键词和评论收集用户需求，分析具体人群，比较竞品，形成带原文依据的报告。

使用 Python 3.10+ 标准库和原生 HTML、CSS、JavaScript，无需安装 pip 或 npm 运行依赖。AI 使用成员本机 Codex 的登录与模型配置。

## 让 Codex 启动

在 Codex 中打开此仓库，发送：

> 请读取 AGENTS.md，检查项目并使用 team_start.py 启动远见工作台，打开浏览器。不要自动采集或调用模型。

macOS 或 Linux：

```sh
python3 "team_start.py" --open
```

macOS 也可双击「打开工作台.command」。Windows 首次运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

以后双击「打开工作台.cmd」。Windows 初始化会创建本机 `.venv`，不会安装全局依赖或修改系统配置。也可以由 Codex 查找本机可用的 Python 3.10+。

服务仅监听 `127.0.0.1`，默认地址为 `http://127.0.0.1:8765`；端口被占用时自动尝试后续端口，以启动日志为准。重复启动会识别同一工作目录的已有服务。保留服务进程，终端前台运行时按 `Ctrl+C` 停止。

公开仓库不包含业务数据、报告、API 密钥、团队连接或个人登录。首次打开可新建项目、导入获授权的项目包，或使用明确标为虚构的演示。已有本机数据保存在 `data/projects/`，代码更新不会替换这些文件。

## 从关键词到报告

1. **采集资料。**在「需求调研」输入产品词，可同时选小红书、TikTok、Reddit 等已支持平台；采集关键词后继续搜索内容、勾选内容采评论。中文输入可以直接使用。
2. **选择采词方式。**快速模式采一轮；A～Z 增加字母组合查询；意图深挖增加场景、问题和决策相关查询。高级模式可选 1～6 轮，后续轮次沿真实返回的新词继续查询。
3. **选择洞察内容。**点击采集后的「选择洞察内容」，勾选所需分析。每块独立生成、保存；失败可重跑该块，已成功的结果仍可查看。
4. **阅读完整报告。**按章节查看具体人群、需求、决策障碍与营销方向，点击依据回到实际样本。需要调整时重跑对应分析；综合判断会提示哪些结果需要更新。
5. **比较竞品并交付。**在「竞品研究」查询和比较 Amazon 竞品，手动读取历史；在「结论与行动」查看结论、选品资料缺口，导出 HTML、Markdown 报告或完整项目包。

采词前会显示请求预算。高级采词默认最多 200 次、硬上限 500 次；快速、内容和评论采集保持较小预算。多平台共享总上限，各平台和每轮的新增、重复、失败及停止原因分别保留。预算是请求上限，不保证返回固定数量的关键词；费用以供应商实际计费为准。

## 可以选择的洞察

| 分析 | 报告内容 |
| --- | --- |
| 关键词库 | 清洗、归类和主题整理，保留原始词与来源。 |
| 人群画像 | 具体处境、八层画像、一天中的场景、三层需求、购买触发、决策因素、障碍、替代方案和定位。 |
| 搜索意图 | 用户在找什么、处于哪个决策阶段、需要什么信息。 |
| 评论需求 | 评论原话、痛点、异议、期待和待验证需求。 |
| 内容规律 | 内容主题、表达方式及样本中可观察到的规律。 |
| 营销选题 | 面向具体人群的选题与内容建议，区分依据和推断。 |
| 综合判断 | 结合已完成分析，给出优先人群、机会、限制和下一步验证。 |

分析方法使用内置千机塔提示词快照，不依赖原工作台运行。每块保留实际样本范围、证据快照、提示词版本和任务状态；历史报告可以单独选择和导出。

人群分析不会从少量关键词编造年龄、收入或购买行为，依据不足会标为未知或提示补充材料。引用必须对应输入样本，模型推断单独标记；引用校验不等于所有推断都已被市场验证。小红书中文讨论与海外市场资料分别保留平台、市场范围。

## 数据源和 Codex

- 新增社交平台采集需要在「数据源与能力」配置自己的 TikHub Key；Amazon 查询使用卖家精灵 MCP 权益。未配置时仍可查看和导入已有资料。
- 独立私有资料包若附带 `.team/` 连接，会由 `team_start.py` 在内存中载入。共享连接会共用额度，不能公开提交或转发凭据。
- 打开页面不自动触发采集或分析。海外平台的中文查询翻译目前依赖 TikHub；报告和原文翻译使用 Codex，保留原文。
- Codex 使用当前成员的登录和模型服务配置，分析样本会发送至配置的模型服务；并非离线模型。检测到程序不等于已登录或有可用额度。
- 竞品历史由用户手动读取，没有默认开启定时监控。供应商估算销量不等于真实订单，缺失指标不会补零。

Codex 程序选择顺序：`FIELDWORK_CODEX_PATH`、忽略提交的 `codex.local.json` 中的 `executable` 绝对路径、默认程序查找。显式路径无效时会报错，不会自动换用另一套 CLI。`GET /api/ai` 可以查看选中的程序位置。

Windows 若无法执行 WindowsApps 中的程序，可在用户授权下使用经过 SHA-256 校验的本地同版本副本，记录在 `codex.local.json`；不改系统目录权限、不复制认证文件。应用升级后需重新核对路径和副本，再重启工作台。

分析保留 Codex 用户配置的 provider、服务地址和认证设置；先在相同临时目录、环境和功能配置下枚举 MCP，再逐项禁用，配合命令、浏览器和插件限制。无法确认工具隔离时不启动模型。完整 JSON Schema 同时传入 CLI 与任务指令，返回后仍校验结构、字段和证据。

## 团队 Git 协作

上游仓库：<https://github.com/imyexi/yuanjian-workbench>。

团队在本地 `main` 开发。每次开始先检查工作区、同步上游 `main`；存在未提交工作时先保留，不使用强制重置覆盖。

完成后运行验证、更新 `ROADMAP.md`、检查提交清单并 commit。通过独立的远端分支向上游 `main` 提 PR；无上游写权限的成员使用自己的 Fork。PR 合并后再同步上游。不要直接覆盖上游历史或使用 force push。

Git 只同步源码。`.team/`、本机配置、登录、`data/`、`exports/`、运行时和私有 ZIP 均被忽略。成员各自持有独立项目副本，需要交接时通过应用导出、导入项目包，不会自动实时合并业务数据。

## 验证与目录

```sh
python3 -m unittest discover -s tests -v
python3 "scripts/check_project.py"
python3 "scripts/check_project.py" --url http://127.0.0.1:8765
```

Windows 将 `python3` 替换为 `.\.venv\Scripts\python.exe`。初始化检查支持没有业务数据的公开源码目录；如果存在私有资料清单，会继续验证清单及项目版本校验和。`--url` 只允许本机回环地址，验证不调用采集或模型。

有 Node.js 时可运行前端回归测试，Node 仅用于开发验证：

```sh
node "tests/test_action_cards.js"
node "tests/test_flow_clarity.js"
node "tests/test_workflow.js"
node "tests/test_insight_modules.js"
node "tests/test_keyword_controls.js"
node "tests/test_keyword_module_link.js"
node "tests/test_ime.js"
node "tests/test_navigation.js"
node "tests/test_watch_ui.js"
```

- `team_start.py`、启动脚本：团队与公开源码的统一入口。
- `server.py`：本机接口、数据版本、导入恢复与静态文件。
- `collection_jobs.py`、`keyword_expansion.py`：有预算的多平台、多轮采集。
- `ai_jobs.py`、`ai_modules.py`、`codex_runner.py`：分析任务、分块报告和本机模型调用。
- `sources.py`、`sellersprite.py`、`credential_store.py`：数据源和凭据处理。
- `web/`、`prompts/`：页面、报告渲染与提示词快照。
- `tests/`、`scripts/check_project.py`：回归与初始化验收。
- `AGENTS.md`、`CLAUDE.md`：协作规则；`ROADMAP.md`：真实进度及验证边界。
