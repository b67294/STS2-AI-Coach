# STS2 AI Coach

🔗 Repository: https://github.com/b67294/sts2-ai-coach

一个面向《Slay the Spire 2》的本地 AI 陪练项目。它通过游戏 Mod 读取当前局面，把游戏状态转换成结构化上下文，再结合本地策略知识库调用 LLM，为玩家提供路线、抓牌、商店、事件、Boss 前体检和复盘建议。

> 当前定位是 **只读陪练 / 决策辅助**，不是自动代打工具。

## ✨ Highlights

- 🎮 **游戏内状态采集**：通过 `STS2-Agent` Mod 读取当前 run 状态。
- 🔌 **本地状态桥接**：将游戏对象序列化为外部程序可消费的 JSON。
- 🧠 **轻量知识增强**：使用 Markdown / JSON 私域资料增强模型上下文，不依赖向量数据库。
- 🤖 **LLM 分析**：支持 OpenAI Responses API，也兼容 OpenAI-style Chat Completions 服务。
- 🖥️ **本地网页陪练**：用原生 HTML / CSS / JavaScript 提供简洁交互界面。
- 🧩 **Submodule 管理**：`STS2-Agent` 作为外部依赖引入，便于跟随上游更新。

## 🧱 Architecture

```text
Slay the Spire 2
    ↓
C# Mod reads game objects and runtime state
    ↓
Local HTTP JSON state bridge
    ↓
Python Coach service summarizes the current run
    ↓
Markdown / JSON private knowledge context
    ↓
OpenAI-compatible LLM
    ↓
Local Web UI shows decision advice
```

## 📦 Project Structure

```text
sts2-ai-coach/
├─ sts2-coach/       Local coach web app and LLM integration
├─ STS2-Agent/       External game Mod + MCP Server, tracked as a Git submodule
├─ README.md         Project documentation
├─ .gitignore        Ignore rules for secrets and runtime artifacts
└─ .gitmodules       Submodule source configuration
```

## 🧠 How It Works

### 1. Game State Collection

`STS2-Agent` is a C# Mod built for Slay the Spire 2. It runs inside the game environment and reads runtime objects such as:

- player state
- deck
- relics
- potions
- rewards
- map
- shop
- events
- combat state

The raw game state is exposed as structured data for external tools.

### 2. Local State Bridge

The Mod exposes a local HTTP JSON bridge. External programs do not need to understand the internal game object model or hook the game process directly. They only consume structured local state.

`STS2-Agent` also provides an MCP wrapper so MCP-compatible AI clients can access game state and actions as tools.

### 3. Coach Layer

`sts2-coach` is the local companion app. It reads the current state, compresses it into a model-friendly summary, then combines it with local knowledge files before calling an LLM.

This project does **not** use a vector database or embedding retrieval yet. The current design is a lightweight prompt-stuffing approach:

```text
current game state summary
+ local Markdown / JSON knowledge
+ user note
+ system prompt
=> LLM advice
```

This keeps the system simple and easy to run. The tradeoff is higher token usage per request.

### 4. Web Interaction

The frontend is a small local control panel built with HTML, CSS, and JavaScript. It shows current run state and provides scenario buttons such as:

- reward analysis
- route advice
- shop advice
- boss checkup
- run review

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
| --- | --- | --- |
| Game Mod | C# / .NET / GodotSharp / Harmony | Read game runtime state from inside STS2 |
| State Bridge | Local HTTP / JSON | Convert game objects into structured external data |
| MCP Wrapper | Python / FastMCP | Expose Mod capabilities as MCP tools |
| Coach Backend | Python standard library HTTP server | Summarize state, assemble context, call LLM |
| Knowledge Layer | Markdown / JSON / Prompt Stuffing | Lightweight private knowledge augmentation |
| Model API | OpenAI Responses API / Chat Completions-compatible API | Generate advice |
| Frontend | HTML / CSS / JavaScript | Local UI for player interaction |

## 🚀 Quick Start

### 1. Clone

Clone with submodules:

```powershell
git clone --recurse-submodules https://github.com/b67294/sts2-ai-coach.git
```

If the repository was cloned without submodules:

```powershell
git submodule update --init --recursive
```

### 2. Install and Start STS2-Agent

Install the `STS2-Agent` Mod into the Slay the Spire 2 `mods/` directory, then start the game.

Verify the Mod bridge:

```text
http://127.0.0.1:8080/health
```

### 3. Configure Coach

```powershell
cd sts2-coach
copy .env.example .env
```

Fill in `.env`:

```text
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-5.4
```

### 4. Run

```powershell
.\start-coach.ps1
```

Open:

```text
http://127.0.0.1:8766
```

## 🔄 Updating STS2-Agent

`STS2-Agent` is tracked as a Git submodule. To update it:

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

## 🔐 Version Control Notes

The repository excludes local-only artifacts such as:

- `.env`
- logs
- Python caches
- downloaded release bundles
- local vendor archives

`STS2-Agent/` should usually be treated as an external dependency. If changes to `STS2-Agent` are required, use a fork or upstream contribution flow, then update the submodule reference.

## 📌 Current Scope

- Read-only AI coaching
- Local single-user workflow
- Lightweight knowledge augmentation
- No vector database
- No automatic gameplay execution from `sts2-coach`

## 📄 License

This repository depends on `STS2-Agent`, which is licensed separately. Check the submodule repository for its license and usage terms.
