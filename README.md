# rtk-rewrite

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
