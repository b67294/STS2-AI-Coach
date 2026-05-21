# STS2 AI Coach

一个给《Slay the Spire 2》做 AI 陪练的本地项目。

核心思路是：游戏 Mod 读取当前局面，转换成结构化状态；本地 Coach 服务把状态和私域知识拼成上下文，调用 LLM 给出路线、抓牌、商店、Boss 前体检和复盘建议。

## 项目结构

```text
STS2 AI Coach
├─ sts2-coach/          本项目主要开发目录：本地网页陪练 + LLM 调用
├─ STS2-Agent/          外部依赖：游戏 Mod + MCP Server，使用 Git submodule 管理
├─ README.md            当前说明文档
├─ .gitignore           主仓库忽略规则
└─ .gitmodules          submodule 来源记录
```

## 技术链路

```text
Slay the Spire 2
    ↓
C# Mod 读取游戏对象和运行状态
    ↓
本地 HTTP JSON 状态桥接
    ↓
Python Coach 服务压缩当前局面
    ↓
Markdown / JSON 私域知识增强
    ↓
OpenAI-compatible LLM
    ↓
HTML / CSS / JS 本地网页展示建议
```

## 模块说明

| 模块 | 技术 | 作用 |
| --- | --- | --- |
| 游戏状态采集 | C# Mod / .NET / GodotSharp / Harmony | 注入游戏环境，读取游戏内存和对象中的状态 |
| 状态桥接 | Local HTTP Server / JSON | 把游戏内部对象序列化成外部程序可读的结构化数据 |
| MCP 外接 | Python / FastMCP | 将 STS2-Agent 的能力封装为 MCP tools，供支持 MCP 的 AI 客户端调用 |
| Coach 陪练 | Python 标准库 HTTP Server | 读取当前状态，压缩局面，拼接知识库并调用 LLM |
| 知识增强 | Markdown / JSON / Prompt Stuffing | 不使用向量数据库，直接把轻量私域资料放入模型上下文 |
| 前端交互 | HTML / CSS / JavaScript | 展示当前局面，并触发路线、商店、Boss 前体检、复盘等分析 |

## 为什么用 submodule

`STS2-Agent` 是外部项目，后续可能继续更新。这里不把它复制成普通目录，而是作为 Git submodule 引入。

这样主仓库只记录：

```text
STS2-Agent 来自哪个 GitHub 仓库
当前锁定到哪个 commit
```

如果上游更新，可以单独更新 submodule，而不会把外部项目的历史和代码揉进本仓库。

## Clone

Clone with submodules:

```powershell
git clone --recurse-submodules <repository-url>
```

If the repository was cloned without submodules:

```powershell
git submodule update --init --recursive
```

## 更新 STS2-Agent

当外部 `STS2-Agent` 有新版本时，在主项目根目录执行：

```powershell
cd STS2-Agent
git pull origin main
cd ..
git add STS2-Agent
git commit -m "Update STS2-Agent submodule"
git push
```

After pulling updates from this repository:

```powershell
git pull
git submodule update --init --recursive
```

## 运行 Coach

先确保游戏已经安装并启用 `STS2-Agent` Mod，然后确认本地能访问：

```text
http://127.0.0.1:8080/health
```

配置环境变量：

```powershell
cd sts2-coach
copy .env.example .env
```

在 `.env` 中填写模型 API Key，然后启动：

```powershell
.\start-coach.ps1
```

打开：

```text
http://127.0.0.1:8766
```

## Development Notes

- Application code lives in `sts2-coach/`.
- `STS2-Agent/` is tracked as an external submodule dependency.
- Local secrets, logs, caches, downloaded release bundles, and runtime artifacts are excluded from version control.
- Changes to `STS2-Agent` should be made in a fork or upstream contribution flow, then referenced by updating the submodule target.

## 当前实现特点

- 只读陪练，不自动代打
- 不使用向量数据库，降低部署复杂度
- 每次分析都会发送当前局面摘要和轻量知识文本
- 模型无状态，每次请求都基于本次上下文生成结果
