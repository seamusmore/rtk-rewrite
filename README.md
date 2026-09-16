# rtk-rewrite

### Windows Codex diagnostics (1.3.4)

The Windows adapter also handles explicit simple `rtk` commands, including
`rtk gain --history`. RTK diagnostics, stdout bytes and exit codes are preserved.
`rtk init -g` configures Claude Code by default; its hook-installation messages
are passed through unchanged. Python
handles streams so the launcher works in PowerShell ConstrainedLanguage mode.

RTK statistics require read/write access to the RTK data directory. A Codex
permission profile extending `:read-only` can grant only that directory write
access. Keep network access disabled and select the profile for new tasks.
The adapter never grants permissions itself. Under a strictly read-only
profile, statistics access may still fail and the original error is retained.

Without database access, compression can still succeed while statistics are
not persisted. `rtk gain` retains its failure exit code and prints a permission
hint. Grant access only to the RTK data directory if persistent statistics are
desired; installation never changes the user's sandbox policy.

支持 Hermes 和 Codex，两个平台共用 `shared/rewrite.py` 调用 RTK。
Hermes 使用现有 `plugin.yaml` / `__init__.py` 入口；Codex 使用原生 `PreToolUse` hook。

## Codex

需要 Python 3.10+、RTK，以及支持插件 hooks 和 `updatedInput` 的 Codex 版本。
Windows 需能执行 `python`，使用 PowerShell 和 RTK 0.49.0+；Linux/macOS 需能执行 `python3`。两端均直接使用 PATH 中已安装的 `rtk`。

通过 [Seamus 插件市场](https://github.com/seamusmore/agent-plugins) 安装：

```powershell
codex plugin marketplace add seamusmore/agent-plugins --ref main
codex plugin add rtk-rewrite@seamusmore
```

按 Codex 提示审核并信任插件 hook，然后开启新任务。安装完成和 hook 信任是两个步骤。

Codex 将终端调用以 `Bash` / `tool_input.command` 传给 hook，执行 shell 保持原设置。
例如 `git status` 会交给 `rtk git status`。Windows 通过随插件安装的 `hooks/rtk_windows.ps1` 启动，其他平台直接运行改写后的命令。
Windows 的 hook 由 Python 直接读取 `PLUGIN_ROOT` 环境变量，兼容 PowerShell 和 cmd 启动；最终工具命令仍由所选 shell 执行。

首版对单条简单命令自动改写。包含换行、管道、重定向、变量、命令替换、分号或控制运算符的命令保留原样，避免 POSIX/PowerShell 语法混用。
Codex 入口不添加 Hermes 的 `: RTK &&` 预览标记。

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `RTK_CODEX_MODE` | `rewrite` | `rewrite` 或 `off` |
| `RTK_CODEX_TIMEOUT_MS` | `2000` | 改写超时毫秒数，上限 8000；外层 hook 超时 10 秒 |

RTK 缺失、超时、没有对应改写或输出异常时保留原命令。返回码 `2` 阻止调用；`0` 和 `3` 使用有效改写结果。
Codex 的 `PreToolUse` 中 `allow` 配合 `updatedInput` 只替换工具参数，后续仍走终端工具自身的沙箱及审批流程。
插件不注册 `PermissionRequest` 审批处理器。RTK 读取的 Claude 权限配置与 Codex 自身权限配置分别由各自系统管理。

节省统计直接使用 `rtk gain`。Hermes 的 `/rtk` 命令和原有进程内计数继续保留。

### 开发验证

```powershell
python -m unittest discover -s tests -v
```

测试需要完整 Git 历史，以读取抽取前的 Hermes 基线 `07be79f`，对照配置、命令返回、计数、异常和注册行为。
安装 RTK 时额外运行真实 hook 启动测试，包括含空格的安装路径和不同工作目录。
已使用 Codex 0.154.0-alpha.6.2 原生 app-server 和本地固定 Responses 协议测试完成安装、信任、hook 自动触发及 PowerShell 执行验收；测试期间未调用外部模型服务。

Windows 沙箱兼容：本机沙箱中的 `SHGetKnownFolderPath(FOLDERID_Profile)` 返回 `0x80070002`，而 `USERPROFILE` 仍指向真实用户目录。RTK 0.49.0 在执行命令前查询该目录，因此插件的 PowerShell 启动脚本会在缺少显式覆盖时，为本次 RTK 子进程提供 `CLAUDE_CONFIG_DIR=USERPROFILE/.claude`，结束后恢复原值。这个变量用于保留 RTK 自身的 hook 完整性检查；插件不会写入 Claude 文件、全局环境变量或 Codex 环境配置。已有显式目录覆盖保持原样，命令仍在 Codex 原有沙箱内执行。显式选择其他 Windows shell 时保留原命令。
`rtk gain` 使用 RTK 自己的数据库；只读沙箱无法写入该数据库时，压缩命令仍可成功，统计无法持久化。插件保持宿主权限，数据库写权限需单独授权。

协议参考：[Codex Hooks](https://learn.chatgpt.com/docs/hooks)。

## Hermes

Hermes Agent 插件：将终端命令自动通过 [RTK](https://github.com/rtk-ai/rtk) 代理执行，节省 **60-90%** LLM token 消耗。

基于 [ogallotti/rtk-hermes](https://github.com/ogallotti/rtk-hermes)，改造为 Hermes 纯目录插件（无需 pip/venv）。

## 特性

- ✅ **命令自动改写** — `git status` → `rtk git status`，输出大幅精简
- ✅ **预览标记** — 改写后可看到 `: RTK &&` 前缀（默认开启）
- ✅ **模式切换** — `rewrite`（自动改写）/ `suggest`（仅建议）/ `off`（关闭）
- ✅ **后端控制** — 默认仅本地终端，SSH/Docker 需显式开启
- ✅ **斜杠命令** — `/rtk status` `/rtk stats` `/rtk config`
- ✅ **零依赖** — 纯 Python 标准库，无需 pip install
- ✅ **Fail-open** — RTK 不可用时命令照常执行，不阻塞

## 安装

### 第一步：安装 RTK 二进制

```bash
# macOS
brew install rtk

# Linux/macOS 快速安装
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh

# 或从源码编译
cargo install --git https://github.com/rtk-ai/rtk
```

验证安装：

```bash
rtk --version    # 应显示 rtk 0.x.x
rtk rewrite "git status"   # 应输出 rtk git status
```

### 第二步：安装本插件

```bash
hermes plugins install seamusmore/rtk-rewrite
```

此命令会自动将插件安装到 `~/.hermes/plugins/rtk-rewrite/` 并启用。如需手动安装或离线环境：

```bash
mkdir -p ~/.hermes/plugins
git clone https://github.com/seamusmore/rtk-rewrite.git ~/.hermes/plugins/rtk-rewrite
```

### 第三步：启用插件

在 `~/.hermes/config.yaml` 中确保 `rtk-rewrite` 在启用列表中：

```yaml
plugins:
  enabled:
    - rtk-rewrite
```

重启 Hermes 或开始新会话即可生效。

## 配置（环境变量）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `RTK_HERMES_MODE` | `rewrite` | `rewrite` / `suggest` / `off` |
| `RTK_HERMES_TIMEOUT_MS` | `2000` | `rtk rewrite` 超时（毫秒） |
| `RTK_HERMES_PREVIEW_MARKER` | `true` | 是否在命令前显示 `: RTK &&` |
| `RTK_HERMES_BACKENDS` | `local` | 允许改写的终端后端，逗号分隔；`all` 表示全部 |

示例：

```bash
export RTK_HERMES_MODE=rewrite
export RTK_HERMES_PREVIEW_MARKER=true
```

## 斜杠命令

在 Hermes 对话中使用：

- `/rtk status` — 插件状态、RTK 可用性、当前配置和统计
- `/rtk stats` — 仅统计信息
- `/rtk config` — 环境变量参考和当前配置
- `/rtk reset-stats` — 重置计数器

## 许可

MIT License. Copyright (c) 2026 ogallotti/rtk-hermes contributors, Copyright (c) 2026 Seamus.

本项目 fork 自 [ogallotti/rtk-hermes](https://github.com/ogallotti/rtk-hermes) （MIT），移除了 pip/setuptools 打包，改为 Hermes 纯目录插件。核心改写逻辑未变。

RTK 二进制项目：[rtk-ai/rtk](https://github.com/rtk-ai/rtk)
