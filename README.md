# 远见工作台

使用 Python 3.10+ 标准库和原生 HTML、CSS、JavaScript 的本地调研工作台，支持关键词洞察、电商竞品比较和报告导出，无需安装 pip 或 npm 依赖。

## GitHub 公开源码仓库

本仓库仅包含源码、文档和测试，不包含团队连接、API 密钥、个人登录、本机配置、项目业务数据、已有报告或运行时。团队资料清单 `package-manifest.json` 也不提交。

从 GitHub 克隆后，在项目根目录初始化并启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
.\.venv\Scripts\python.exe -X utf8 -u .\team_start.py --open
```

macOS 或 Linux 使用 `python3 team_start.py --open`。服务仅监听 `127.0.0.1`，默认地址为 `http://127.0.0.1:8765`；以启动日志中的实际地址为准。首次使用可在界面新建项目、导入通过授权获得的项目包，或体验带有虚构标记的演示。

新增第三方采集需要自行配置相应数据源；AI 分析需要本机可用且已登录的 Codex。团队连接和业务数据不会随 Git 同步。

源码回归验证：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

下文保留的是已有团队资料包的使用说明。文中的“本包”“随包提供”、默认项目、已有报告和团队连接仅适用于另行交付的私有资料包，不表示这些内容已公开或包含在 GitHub 仓库内。`scripts/check_project.py` 用于具有 `data/projects/` 和 `package-manifest.json` 的本机资料包验收，不能直接用于仅克隆源码的目录。现有双击启动脚本保留团队资料包的默认项目；首次克隆请使用上方不带 `--project` 的启动命令。

## 当前项目的 Windows 启动方式

源码已直接放在项目根目录。首次使用时运行以下命令创建本地 `.venv`；脚本支持本机 Python 或 Codex 自带的 Python 3.10+，无需安装第三方依赖：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

随后双击 `打开工作台.cmd`，会启动服务并打开「宠物饮水机」项目。保留启动窗口，按 `Ctrl+C` 停止服务。也可以在 PowerShell 中运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

默认访问地址为 `http://127.0.0.1:8765/#guide?project=caaaa93ac46840cb`。端口被占用时，以启动窗口显示的实际地址为准。可通过 `-Port 8775` 指定起始端口，通过 `-NoBrowser` 仅启动服务。

初始化及服务验收：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\scripts\check_project.py
.\.venv\Scripts\python.exe -X utf8 .\scripts\check_project.py --url http://127.0.0.1:8765
```

Git 仅用于管理源码；`.team/`、`data/`、`exports/`、独立业务报告、`.venv/` 和 `.runtime/` 已排除。复制到其他电脑后需重新建立虚拟环境，业务资料请通过应用导出交接。

### 指定工作台使用的 Codex 程序

当前电脑通过根目录的 `codex.local.json` 指定 Codex 桌面版程序，避免调用 PATH 中另一套 CLI。由于 Windows 拒绝直接执行 WindowsApps 安装目录中的文件，实际运行 `.runtime/codex-desktop/codex.exe`：它是从用户指定的桌面版 `app/resources/codex.exe` 复制的同版本文件，已验证 SHA-256 一致，没有修改系统目录权限。配置中记录了源路径和校验和。

本地配置及运行副本均已加入 Git 忽略规则；没有复制登录凭据。切换可执行文件不会自动切换账号，认证方式以该程序的实际状态为准。

程序选择顺序为：环境变量 `FIELDWORK_CODEX_PATH`、`codex.local.json` 的 `executable` 绝对路径、默认 CLI 查找。只要显式指定了路径，路径失效或配置格式错误时就报错，不会悄悄改用其他 CLI。桌面应用升级后，安装目录中的版本号可能变化；需要更新运行副本、核对校验和及本地配置，再重启工作台。

`GET /api/ai` 返回实际选中的 `executable`，用于确认调用位置。认证仍由选中的 Codex 程序处理，检测到可执行文件不代表已登录或模型调用成功。

分析任务保留 Codex 用户配置中的模型服务地址、服务提供方和凭据存储设置，由 Codex 自行读取凭据。工作台不另外复制或保存模型密钥。任务在临时目录内运行，忽略规则文件和项目说明；先用相同功能配置列出 MCP 服务，再逐项禁用，同时保留命令、浏览器、插件等工具限制。无法确认工具隔离配置时不启动分析。

为兼容未严格执行结构化输出参数的模型服务，完整 JSON Schema 同时通过 CLI 参数和任务指令提供。报告返回后仍校验全部字段及证据引用，缺失字段不能自动补成事实。

开发验证可运行 `python -m unittest discover -s tests -v`。认证状态检查仅说明程序识别到凭据；实际模型请求返回有效结果，才能确认当前服务与凭据匹配。

## 交给 Codex 启动

1. 将压缩包完整解压到一个可写文件夹，例如「文稿」。
2. 在 Codex 中打开解压后的文件夹，发送下面这句话。
3. Codex 启动后，浏览器会打开「宠物饮水机」项目的使用指南。使用期间保留服务进程。

> 请按 README.md 和 AGENTS.md 启动这个工作台，使用 team_start.py，打开宠物饮水机项目。卖家精灵连接已经随包提供，不要把连接内容打印出来，也不要替我配置 TikHub。

本包仅包含源码与资料，不包含 Python、Codex 或个人登录。工作台使用 Python 3.10+ 标准库，没有 pip、Node.js 或 npm 运行依赖。Codex 先查找本机可用 Python；有 `python3` 时运行：

```sh
python3 "team_start.py" --open --project caaaa93ac46840cb
```

也可双击「打开工作台.command」。重复打开会复用已有服务；端口被占用时自动换到空闲端口。不需要结束其他程序或修改系统配置。

只想看结果，可直接双击「先看完整报告.html」，无需启动服务、登录或联网。

## 三个入口

| 入口 | 做什么 |
| --- | --- |
| 关键词洞察 | 采集关键词、内容和评论，查看关键词报告，再分析需求与营销方向。 |
| 电商盯盘 | 查询 Amazon 竞品、加入候选、比较商品、手动读取历史。 |
| 报告与选品 | 查看结论、原文依据、选品资料缺口，导出报告和项目包。 |

采集后按页面的「下一步」继续。已有报告和原始资料随包提供，可先查看再决定是否追加付费采集；虚构演示项目始终带有演示标记。

## 数据源与 AI

- **卖家精灵已随团队包提供连接。**成员共用同一份查询额度，打开页面不会自动扣除业务查询次数，点击查询才会调用。密钥文件仅用于本地后端，不进入页面或报告；请勿将压缩包或解压目录公开发布。
- **本包不包含 TikHub API 凭据。**已有小红书、TikTok、Reddit 数据和报告仍可阅读；新增三平台采集需要在「数据源与能力」填入成员自己的 TikHub Key。未配置 TikHub 时，Amazon 新查询请使用英文产品词，例如 `pet water dispenser`；当前中文搜索词转英文也依赖 TikHub。
- **新增 AI 分析和中文翻译使用成员本机已安装并登录的 Codex。**本包不包含发送方的登录，成员使用自己的登录与额度。未登录时，已有报告和 Amazon 查询仍可使用。分析样本会发送至 Codex 模型服务，并非离线模型。
- 竞品历史需手动点「读取历史」或「更新趋势」，每次最多 2 次 MCP 查询；没有开启定时监控。第三方估算销量不等于真实订单，缺失指标不会补零。

## 项目与交接

包内保留 9 个项目的当前版本、原文、译文与报告。数据保存于 `data/projects/`，不依赖发送方电脑或原工作台。关闭后重新启动即可继续使用。

**发给不同成员后，每个人得到的是独立副本，不会自动实时合并。**需要交接时，在「报告与选品」导出项目包，由下一位成员导入恢复；不要覆盖他人正在编辑的数据目录。

## 目录

- `打开工作台.command`：双击启动。
- `先看完整报告.html`：直接阅读完整报告。
- `team_start.py`：载入团队连接后启动服务，Codex 应使用此入口。
- `web/`、`prompts/`：界面与分析提示词。
- `data/projects/`、`exports/`：项目资料、已有报告与导出文件。
- `AGENTS.md`：供成员的 Codex 阅读的启动和维护说明。

本包为团队内部协作使用，不包含发送方的 TikHub 凭据、Codex 登录、浏览器资料、双设备私网配置或开发验收日志。
