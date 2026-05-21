# STS2-AI-Coach

🔗 仓库地址：https://github.com/b67294/STS2-AI-Coach

一个面向《Slay the Spire 2》的本地 AI 陪练项目。它通过游戏 Mod 读取当前局面，把游戏状态转换成结构化上下文，再结合本地策略知识库调用大语言模型，为玩家提供路线、抓牌、商店、事件、Boss 前体检和复盘建议。

> 当前定位是 **只读陪练 / 决策辅助**，不是自动代打工具。

## ✨ 项目亮点

- 🎮 **游戏内状态采集**：通过 `STS2-Agent` Mod 读取当前 run 状态。
- 🔌 **本地状态桥接**：将游戏对象序列化为外部程序可消费的 JSON。
- 🧠 **轻量知识增强**：使用 Markdown / JSON 私域资料增强模型上下文，不依赖向量数据库。
- 🤖 **LLM 分析**：支持 OpenAI Responses API，也兼容 OpenAI-style Chat Completions 服务。
- 🖥️ **本地网页陪练**：用原生 HTML / CSS / JavaScript 提供简洁交互界面。
- 🧩 **Submodule 管理**：`STS2-Agent` 作为外部依赖引入，方便跟随上游更新。

## 🧱 技术架构

```text
Slay the Spire 2
    ↓
C# Mod 读取游戏对象和运行状态
    ↓
本地 HTTP JSON 状态桥接
    ↓
Python Coach 服务压缩当前局面
    ↓
Markdown / JSON 私域知识上下文
    ↓
OpenAI-compatible LLM
    ↓
本地 Web UI 展示决策建议
```

## 📦 项目结构

```text
STS2-AI-Coach/
├─ sts2-coach/       本地 Coach 网页应用和 LLM 调用逻辑
├─ STS2-Agent/       外部游戏 Mod + MCP Server，使用 Git submodule 管理
├─ README.md         项目说明文档
├─ .gitignore        密钥和运行产物忽略规则
└─ .gitmodules       submodule 来源配置
```

## 🧠 实现逻辑

### 1. 游戏状态采集

`STS2-Agent` 是一个面向 Slay the Spire 2 的 C# Mod。它运行在游戏环境内，读取当前局面的运行时对象，例如：

- 玩家状态
- 牌组
- 遗物
- 药水
- 奖励
- 地图
- 商店
- 事件
- 战斗状态

这一层的作用是把原本只存在于游戏进程里的信息转换成外部工具可以理解的结构化数据。

### 2. 本地状态桥接

Mod 会暴露一个本地 HTTP JSON 状态桥接。外部程序不需要理解游戏内部对象模型，也不需要自己 Hook 游戏进程，只需要读取本地结构化状态。

`STS2-Agent` 还提供了一层 MCP 封装，让支持 MCP 的 AI 客户端可以把游戏状态和动作能力作为工具调用。

### 3. Coach 陪练层

`sts2-coach` 是本项目的本地陪练应用。它读取当前游戏状态，将局面压缩成适合模型理解的摘要，然后结合本地知识文件调用 LLM。

当前没有使用向量数据库或 embedding 检索，而是采用轻量的 prompt stuffing：

```text
当前游戏状态摘要
+ 本地 Markdown / JSON 知识
+ 用户补充说明
+ 系统提示词
=> LLM 建议
```

这种方案部署简单、可解释性强，代价是每次请求会消耗更多 token。

### 4. 前端交互

前端是一个本地控制台，使用 HTML、CSS 和 JavaScript 实现。它展示当前 run 的摘要，并提供常用分析入口：

- 奖励 / 抓牌分析
- 路线建议
- 商店建议
- Boss 前体检
- 当前 run 复盘

## 🛠️ 技术栈

| 层级 | 技术 | 作用 |
| --- | --- | --- |
| 游戏 Mod | C# / .NET / GodotSharp / Harmony | 在 STS2 游戏环境内读取运行时状态 |
| 状态桥接 | Local HTTP / JSON | 将游戏对象转换成结构化外部数据 |
| MCP 封装 | Python / FastMCP | 将 Mod 能力封装成 MCP tools |
| Coach 后端 | Python 标准库 HTTP Server | 摘要状态、组装上下文、调用 LLM |
| 知识增强 | Markdown / JSON / Prompt Stuffing | 轻量私域知识增强 |
| 模型接口 | OpenAI Responses API / Chat Completions-compatible API | 生成陪练建议 |
| 前端 | HTML / CSS / JavaScript | 本地交互界面 |

## 🚀 快速开始

### 1. 克隆项目

包含 submodule 一起克隆：

```powershell
git clone --recurse-submodules https://github.com/b67294/STS2-AI-Coach.git
```

如果已经克隆过，但 `STS2-Agent/` 目录没有完整内容：

```powershell
git submodule update --init --recursive
```

### 2. 安装并启动 STS2-Agent

将 `STS2-Agent` Mod 安装到 Slay the Spire 2 的 `mods/` 目录，然后启动游戏。

确认 Mod 状态桥接可访问：

```text
http://127.0.0.1:8080/health
```

### 3. 配置 Coach

```powershell
cd sts2-coach
copy .env.example .env
```

在 `.env` 中填写模型配置：

```text
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-5.4
```

### 4. 启动

```powershell
.\start-coach.ps1
```

打开：

```text
http://127.0.0.1:8766
```

## 🔄 更新 STS2-Agent

`STS2-Agent` 使用 Git submodule 管理。更新方式：

```powershell
cd STS2-Agent
git pull origin main
cd ..
git add STS2-Agent
git commit -m "Update STS2-Agent submodule"
git push
```

从本仓库拉取更新后，同步 submodule：

```powershell
git pull
git submodule update --init --recursive
```

## 🔐 版本控制说明

仓库会忽略以下本地文件：

- `.env`
- 日志文件
- Python 缓存
- 下载的 release 包
- 本地 vendor 压缩包

`STS2-Agent/` 默认应视为外部依赖。如果需要修改 `STS2-Agent`，建议通过 fork 或上游贡献流程维护，再更新 submodule 指向。

## 📌 当前范围

- 只读 AI 陪练
- 本地单用户工作流
- 轻量知识增强
- 不使用向量数据库
- `sts2-coach` 不自动执行游戏操作

## 📄 License

本仓库依赖 `STS2-Agent`，其许可证和使用条款请参考 submodule 对应仓库。
