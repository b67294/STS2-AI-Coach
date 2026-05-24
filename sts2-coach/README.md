# STS2 Coach

本地网页陪练 MVP：读取 `STS2-Agent` Mod 的只读状态接口，调用 OpenAI API，给《杀戮尖塔 2》当前 run 的中文宏观建议。

## 运行前准备

1. 安装并启动 `STS2-Agent` Mod。
2. 确认浏览器能打开：

```text
http://127.0.0.1:8080/health
```

3. 复制/改名 `.env.example` 为 `.env`，并在 `.env` 中填入自己的 `OPENAI_API_KEY`。
4. 如果要使用地图侦察的怪物图、遭遇池和随机事件池，首次运行前同步一次 Spire Codex 本地资料：

```powershell
python scripts\sync_spire_codex.py
```

同步结果会保存到 `data/spire-codex/`，该目录只作为本地缓存，不提交 GitHub。

## 启动

```powershell
cd "F:\slay the spire\sts2-coach"
.\start-coach.bat
```

或者显式使用 PowerShell 执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-coach.ps1
```

然后打开：

```text
http://127.0.0.1:8766
```

## 安全边界

这个项目只调用 `GET /health`、`GET /state` 和可选的 `GET /data/...`。它不会调用 STS2-Agent 的 `POST /action`，因此不会自动选牌、走图、买东西或打牌。

## 可用按钮

- 分析当前选择：适用于奖励、事件、火堆等当前屏幕。
- 路线建议：适用于地图。
- 地图分析：在地图页展示本张图可能出现的弱怪、普通怪、精英、Boss 和随机事件池；点击事件标签可查看事件介绍与选项。
- 商店建议：适用于商店。
- Boss 前体检：适用于进入 Boss 前或想检查牌组短板时。
- 复盘这把：用于死亡/胜利后总结经验。

## 配置

- `STS2_API_BASE_URL`：默认 `http://127.0.0.1:8080`
- `OPENAI_BASE_URL`：默认 `https://api.openai.com/v1`；DeepSeek 用 `https://api.deepseek.com`
- `OPENAI_API_KEY`：OpenAI API key
- `OPENAI_MODEL`：默认 `gpt-5.4`；DeepSeek 推荐 `deepseek-v4-flash` 或 `deepseek-v4-pro`
- `OPENAI_REASONING_EFFORT`：默认 `medium`
- `COACH_PORT`：默认 `8766`

## 使用 DeepSeek

DeepSeek 使用 OpenAI-compatible Chat Completions 接口。`.env` 示例：

```text
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=你的 DeepSeek key
OPENAI_MODEL=deepseek-v4-flash
```

## 下载 STS2-Agent Release

如果你还没有 Mod release 包，可以运行：

```powershell
cd "F:\slay the spire\sts2-coach"
.\download-sts2-agent-release.ps1
```

脚本会把最新 release asset 下载到 `vendor/`，然后你手动解压并复制 `STS2AIAgent.dll`、`STS2AIAgent.pck`、`mod_id.json` 到游戏的 `mods/` 目录。
