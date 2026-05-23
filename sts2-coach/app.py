from __future__ import annotations

import json
import os
import socket
import sys
import time
from contextlib import nullcontext
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from map_scout import DATA_DIR as SPIRE_CODEX_DATA_DIR
from map_scout import scout_map, scout_prompt_summary
from tracing import TraceContext


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
MEMORY_DIR = ROOT / "memory"
KNOWLEDGE_DIR = ROOT / "knowledge"
PROMPTS_DIR = ROOT / "prompts"

ALLOWED_MODES = {"reward", "map", "event", "shop", "rest", "boss", "general", "review"}


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def sts2_base_url() -> str:
    return env("STS2_API_BASE_URL", "http://127.0.0.1:8080").rstrip("/")


def read_text(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return fallback


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def sse_start(handler: BaseHTTPRequestHandler) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "close")
    handler.end_headers()


def sse_write(handler: BaseHTTPRequestHandler, event: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False)
    body = f"event: {event}\ndata: {data}\n\n".encode("utf-8")
    handler.wfile.write(body)
    handler.wfile.flush()


def text_response(handler: BaseHTTPRequestHandler, status: int, body: bytes, content_type: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def content_type_for(path: Path) -> str:
    content_types = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
    }
    return content_types.get(path.suffix.lower(), "application/octet-stream")


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    data = handler.rfile.read(length)
    try:
        parsed = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON body must be an object.")
    return parsed


def http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 12.0,
    use_proxy: bool = True,
) -> Any:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, method=method, headers=headers, data=body)
    try:
        opener = request.build_opener(request.ProxyHandler({})) if not use_proxy else request
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read()
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {details}") from exc
    except (error.URLError, TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc}") from exc
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def unwrap_mod_response(payload: Any) -> Any:
    if isinstance(payload, dict) and payload.get("ok") is True and "data" in payload:
        return payload["data"]
    return payload


def get_mod_health() -> dict[str, Any]:
    return unwrap_mod_response(http_json("GET", f"{sts2_base_url()}/health", timeout=4.0, use_proxy=False))


def get_raw_state() -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            data = unwrap_mod_response(http_json("GET", f"{sts2_base_url()}/state", timeout=12.0, use_proxy=False))
            break
        except Exception as exc:
            last_error = exc
            if attempt < 2 and ("HTTP 502" in str(exc) or "Cannot reach" in str(exc)):
                time.sleep(0.5 + attempt * 0.75)
                continue
            raise
    else:
        raise RuntimeError(str(last_error) if last_error else "Failed to read state.")
    if isinstance(data, dict):
        return data
    return {"raw": data}


def short_value(value: Any, *, max_items: int = 30) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"sprite", "texture", "image", "art", "icon", "debug"}:
                continue
            out[str(key)] = short_value(item, max_items=max_items)
            if len(out) >= max_items:
                out["_truncated"] = True
                break
        return out
    if isinstance(value, list):
        return [short_value(item, max_items=max_items) for item in value[:max_items]]
    if isinstance(value, str) and len(value) > 900:
        return value[:900] + "...[truncated]"
    return value


def pick(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: data.get(key) for key in keys if key in data and data.get(key) is not None}


def summarize_cards(cards: Any) -> list[dict[str, Any]]:
    if not isinstance(cards, list):
        return []
    summarized = []
    for card in cards[:80]:
        if not isinstance(card, dict):
            summarized.append({"value": card})
            continue
        summarized.append(
            pick(
                card,
                "name",
                "id",
                "card_id",
                "cost",
                "type",
                "rarity",
                "upgraded",
                "description",
                "description_raw",
            )
        )
    return summarized


def summarize_relics(relics: Any) -> list[dict[str, Any]]:
    if not isinstance(relics, list):
        return []
    return [pick(item, "name", "id", "relic_id", "description", "counter") if isinstance(item, dict) else {"value": item} for item in relics[:80]]


def summarize_state(state: dict[str, Any]) -> dict[str, Any]:
    run = state.get("run") if isinstance(state.get("run"), dict) else {}
    player = state.get("player") if isinstance(state.get("player"), dict) else {}
    if not player and isinstance(run, dict):
        player = run.get("player") if isinstance(run.get("player"), dict) else {}

    deck = state.get("deck") or run.get("deck") if isinstance(run, dict) else None
    if isinstance(deck, dict):
        deck_cards = deck.get("cards") or deck.get("draw_pile") or deck.get("master_deck")
    else:
        deck_cards = deck

    summary: dict[str, Any] = {
        "screen": state.get("screen"),
        "session": short_value(state.get("session")),
        "run_id": state.get("run_id"),
        "available_actions": state.get("available_actions") or state.get("actions") or [],
        "run": short_value(
            {
                **pick(run, "floor", "act", "act_id", "boss", "boss_id", "ascension", "seed"),
                "character": run.get("character") or run.get("character_id") if isinstance(run, dict) else None,
            }
        ),
        "player": short_value(pick(player, "name", "character", "hp", "max_hp", "gold", "block", "energy")),
        "deck": summarize_cards(deck_cards),
        "relics": summarize_relics(state.get("relics") or run.get("relics") if isinstance(run, dict) else None),
        "potions": short_value(state.get("potions") or run.get("potions") if isinstance(run, dict) else None),
        "reward": short_value(state.get("reward")),
        "map": short_value(state.get("map")),
        "event": short_value(state.get("event")),
        "shop": short_value(state.get("shop")),
        "rest": short_value(state.get("rest")),
        "combat": short_value(pick(state.get("combat"), "encounter_id", "monsters", "turn") if isinstance(state.get("combat"), dict) else state.get("combat")),
    }

    return {key: value for key, value in summary.items() if value not in (None, {}, [])}


def detect_recommended_mode(summary: dict[str, Any]) -> str:
    screen = str(summary.get("screen") or "").lower()
    if "reward" in screen or summary.get("reward"):
        return "reward"
    if "map" in screen or summary.get("map"):
        return "map"
    if "shop" in screen or summary.get("shop"):
        return "shop"
    if "event" in screen or summary.get("event"):
        return "event"
    if "rest" in screen or summary.get("rest"):
        return "rest"
    return "general"


def load_knowledge() -> str:
    parts = []
    for filename in ("silent-a10.md", "bosses.md", "events.md"):
        text = read_text(KNOWLEDGE_DIR / filename)
        if text:
            parts.append(text)
    vendor_knowledge = ROOT / "vendor" / "sts2-ai-agent-v0.7.2-windows-2" / "docs" / "game-knowledge"
    for filename in ("agent-reference.md", "playbook.md", "events.md"):
        text = read_text(vendor_knowledge / filename)
        if text:
            parts.append("# STS2-Agent Extracted Reference\n\n" + text)
    return "\n\n".join(parts)


def load_memory() -> str:
    return "\n\n".join(
        [
            read_text(MEMORY_DIR / "current-run.md"),
            read_text(MEMORY_DIR / "lesson-ledger.md"),
        ]
    )


def mode_instruction(mode: str) -> str:
    instructions = {
        "reward": "重点分析当前奖励/抓牌/跳牌。必须评价当前牌组的攻击、防御、运转、成长平衡。",
        "map": "重点分析路线。结合血量、药水、牌组强度、商店/火堆/精英密度给路线建议。",
        "event": "重点分析事件选项。说明收益、代价、血量/金币阈值和当前牌组适配度。",
        "shop": "重点分析商店。给购买、删牌、药水、跳过的优先级。",
        "rest": "重点分析火堆。判断升级、休息或其他选项的收益和风险。",
        "boss": "重点做 Boss 前体检。指出当前对 Boss/精英的主要缺口，以及下一步补强目标。",
        "review": "重点复盘这把。总结关键失误、有效选择和下一把最该调整的 1-3 条原则。",
        "general": "按当前屏幕给宏观建议。如果不是决策点，说明现在最值得关注的牌组短板。",
    }
    return instructions.get(mode, instructions["general"])


def json_char_count(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False))


def build_user_payload(
    mode: str,
    state_summary: dict[str, Any],
    user_note: str,
    memory: str,
    knowledge: str,
) -> dict[str, Any]:
    return {
        "analysis_mode": mode,
        "mode_instruction": mode_instruction(mode),
        "user_note": user_note,
        "game_state_summary": state_summary,
        "memory": memory,
        "knowledge": knowledge,
    }


def build_openai_payload(
    mode: str,
    state_summary: dict[str, Any],
    user_note: str,
    memory: str,
    knowledge: str,
) -> dict[str, Any]:
    system_prompt = read_text(PROMPTS_DIR / "system.md")
    user_payload = build_user_payload(mode, state_summary, user_note, memory, knowledge)
    return {
        "model": env("OPENAI_MODEL", "gpt-5.4"),
        "reasoning": {"effort": env("OPENAI_REASONING_EFFORT", "medium")},
        "max_output_tokens": 1800,
        "input": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "请根据以下 JSON 为当前 STS2 猎人 A10 run 给宏观建议：\n"
                + json.dumps(user_payload, ensure_ascii=False, indent=2),
            },
        ],
    }


def extract_openai_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    chunks: list[str] = []
    for item in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks).strip() or json.dumps(payload, ensure_ascii=False, indent=2)


def call_openai(
    mode: str,
    state_summary: dict[str, Any],
    user_note: str,
    memory: str,
    knowledge: str,
    trace: TraceContext | None = None,
) -> str:
    api_key = env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured. Copy .env.example to .env and fill it in.")

    base_url = env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = env("OPENAI_MODEL", "gpt-5.4")
    if trace:
        trace.set_meta(model=model, base_url_host=urlparse(base_url).hostname)
    if "api.openai.com" not in base_url or model.startswith("deepseek"):
        return call_chat_completions(mode, state_summary, user_note, memory, knowledge, api_key, base_url, model, trace)

    with trace.span("llm_payload_build") if trace else nullcontext():
        payload = build_openai_payload(mode, state_summary, user_note, memory, knowledge)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if trace:
            trace.set_meta(input_chars=len(body.decode("utf-8")))
        req = request.Request(
            f"{base_url}/responses",
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            data=body,
        )
    try:
        with trace.span("llm_http_wait") if trace else nullcontext():
            with request.urlopen(req, timeout=90) as resp:
                response_payload = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error HTTP {exc.code}: {details}") from exc
    except (error.URLError, TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"Cannot reach OpenAI API: {exc}") from exc
    with trace.span("llm_response_parse") if trace else nullcontext():
        text = extract_openai_text(response_payload)
        if trace:
            trace.set_meta(output_chars=len(text))
        return text


def call_chat_completions(
    mode: str,
    state_summary: dict[str, Any],
    user_note: str,
    memory: str,
    knowledge: str,
    api_key: str,
    base_url: str,
    model: str,
    trace: TraceContext | None = None,
) -> str:
    with trace.span("llm_payload_build") if trace else nullcontext():
        system_prompt = read_text(PROMPTS_DIR / "system.md")
        user_payload = build_user_payload(mode, state_summary, user_note, memory, knowledge)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "请根据以下 JSON 为当前 STS2 猎人 A10 run 给宏观建议：\n"
                    + json.dumps(user_payload, ensure_ascii=False, indent=2),
                },
            ],
            "max_tokens": 1800,
            "temperature": 0.3,
            "enable_thinking": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if trace:
            trace.set_meta(input_chars=len(body.decode("utf-8")))
        req = request.Request(
            f"{base_url}/chat/completions",
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            data=body,
        )
    try:
        with trace.span("llm_http_wait") if trace else nullcontext():
            with request.urlopen(req, timeout=90) as resp:
                response_payload = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Chat Completions API error HTTP {exc.code}: {details}") from exc
    except (error.URLError, TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"Cannot reach Chat Completions API: {exc}") from exc

    with trace.span("llm_response_parse") if trace else nullcontext():
        choices = response_payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str) and content.strip():
                text = content.strip()
                if trace:
                    trace.set_meta(output_chars=len(text))
                return text
        text = json.dumps(response_payload, ensure_ascii=False, indent=2)
        if trace:
            trace.set_meta(output_chars=len(text))
        return text


def chat_stream_delta(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    choice = choices[0]
    if not isinstance(choice, dict):
        return ""
    delta = choice.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content
    message = choice.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""


def call_chat_completions_stream(
    mode: str,
    state_summary: dict[str, Any],
    user_note: str,
    memory: str,
    knowledge: str,
    api_key: str,
    base_url: str,
    model: str,
    on_delta: Any,
    trace: TraceContext | None = None,
) -> str:
    with trace.span("llm_payload_build") if trace else nullcontext():
        system_prompt = read_text(PROMPTS_DIR / "system.md")
        user_payload = build_user_payload(mode, state_summary, user_note, memory, knowledge)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "请根据以下 JSON 为当前 STS2 猎人 A10 run 给宏观建议：\n"
                    + json.dumps(user_payload, ensure_ascii=False, indent=2),
                },
            ],
            "max_tokens": 1800,
            "temperature": 0.3,
            "stream": True,
            "enable_thinking": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if trace:
            trace.set_meta(input_chars=len(body.decode("utf-8")))
        req = request.Request(
            f"{base_url}/chat/completions",
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            data=body,
        )

    output_parts: list[str] = []
    chunk_count = 0
    content_chunk_count = 0
    started = time.perf_counter()
    first_event_ms: int | None = None
    first_delta_ms: int | None = None
    try:
        with trace.span("llm_http_stream") if trace else nullcontext():
            with request.urlopen(req, timeout=120) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    if first_event_ms is None:
                        first_event_ms = round((time.perf_counter() - started) * 1000)
                        if trace:
                            trace.set_meta(first_stream_event_ms=first_event_ms)
                    chunk_count += 1
                    try:
                        event_payload = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = chat_stream_delta(event_payload)
                    if delta:
                        if first_delta_ms is None:
                            first_delta_ms = round((time.perf_counter() - started) * 1000)
                            if trace:
                                trace.set_meta(ttfb_ms=first_delta_ms, first_visible_delta_ms=first_delta_ms)
                        content_chunk_count += 1
                        output_parts.append(delta)
                        on_delta(delta)
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Chat Completions stream error HTTP {exc.code}: {details}") from exc
    except (error.URLError, TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"Cannot reach Chat Completions stream API: {exc}") from exc

    text = "".join(output_parts).strip()
    if trace:
        trace.set_meta(
            output_chars=len(text),
            stream_chunks=chunk_count,
            content_chunks=content_chunk_count,
            first_stream_event_ms=first_event_ms,
            first_visible_delta_ms=first_delta_ms,
            ttfb_ms=first_delta_ms,
        )
    return text


def call_openai_stream(
    mode: str,
    state_summary: dict[str, Any],
    user_note: str,
    memory: str,
    knowledge: str,
    on_delta: Any,
    trace: TraceContext | None = None,
) -> str:
    api_key = env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured. Copy .env.example to .env and fill it in.")

    base_url = env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = env("OPENAI_MODEL", "gpt-5.4")
    if trace:
        trace.set_meta(model=model, base_url_host=urlparse(base_url).hostname)
    return call_chat_completions_stream(
        mode,
        state_summary,
        user_note,
        memory,
        knowledge,
        api_key,
        base_url,
        model,
        on_delta,
        trace,
    )


def append_memory(note: str, *, source: str = "manual") -> str:
    cleaned = note.strip()
    if not cleaned:
        raise ValueError("note is required.")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"\n- {timestamp} [{source}] {cleaned}\n"
    path = MEMORY_DIR / "current-run.md"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return line.strip()


class CoachHandler(BaseHTTPRequestHandler):
    server_version = "STS2Coach/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/health":
                self.handle_health()
            elif parsed.path == "/api/state":
                self.handle_state()
            elif parsed.path == "/api/map/scout":
                self.handle_map_scout()
            elif parsed.path.startswith("/assets/spire-codex/"):
                self.handle_spire_codex_asset(parsed.path)
            else:
                self.handle_static(parsed.path)
        except Exception as exc:
            json_response(self, 500, {"ok": False, "error": str(exc)})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/analyze/stream":
                self.handle_analyze_stream()
            elif parsed.path == "/api/analyze":
                self.handle_analyze()
            elif parsed.path == "/api/memory/append":
                self.handle_memory_append()
            else:
                json_response(self, 404, {"ok": False, "error": "Route not found."})
        except ValueError as exc:
            json_response(self, 400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            json_response(self, 500, {"ok": False, "error": str(exc)})

    def handle_health(self) -> None:
        game_ok = False
        game_error = None
        health: Any = None
        summary: dict[str, Any] | None = None
        state_ok = False
        state_error = None
        try:
            health = get_mod_health()
            game_ok = True
        except Exception as exc:
            game_error = str(exc)
        if game_ok:
            try:
                summary = summarize_state(get_raw_state())
                state_ok = True
            except Exception as exc:
                state_error = str(exc)

        json_response(
            self,
            200,
            {
                "ok": True,
                "coach": {"status": "ready", "port": env("COACH_PORT", "8766")},
                "sts2": {
                    "ok": game_ok,
                    "base_url": sts2_base_url(),
                    "health": health,
                    "error": game_error,
                    "state_ok": state_ok,
                    "state_error": state_error,
                },
                "openai": {
                    "configured": bool(env("OPENAI_API_KEY")),
                    "base_url": env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                    "model": env("OPENAI_MODEL", "gpt-5.4"),
                    "reasoning_effort": env("OPENAI_REASONING_EFFORT", "medium"),
                },
                "current": {
                    "screen": summary.get("screen") if summary else None,
                    "recommended_mode": detect_recommended_mode(summary or {}),
                    "run": summary.get("run") if summary else None,
                    "player": summary.get("player") if summary else None,
                },
            },
        )

    def handle_state(self) -> None:
        raw_state = get_raw_state()
        summary = summarize_state(raw_state)
        json_response(
            self,
            200,
            {
                "ok": True,
                "recommended_mode": detect_recommended_mode(summary),
                "state": summary,
            },
        )

    def handle_map_scout(self) -> None:
        raw_state = get_raw_state()
        json_response(self, 200, scout_map(raw_state))

    def handle_analyze(self) -> None:
        trace = TraceContext()
        try:
            with trace.span("read_body"):
                body = read_json_body(self)
                mode = str(body.get("mode") or "general")
                user_note = str(body.get("note") or "")
                trace.set_meta(mode=mode)
                if mode not in ALLOWED_MODES:
                    raise ValueError(f"mode must be one of: {', '.join(sorted(ALLOWED_MODES))}")

            with trace.span("read_state"):
                raw_state = get_raw_state()
                trace.set_meta(state_chars=json_char_count(raw_state))

            with trace.span("summarize_state"):
                summary = summarize_state(raw_state)
                if mode == "map":
                    scout = scout_map(raw_state)
                    summary["map_scout"] = scout_prompt_summary(scout)
                    trace.set_meta(map_scout_ready=bool(scout.get("ok")))

            with trace.span("load_context"):
                memory = load_memory()
                knowledge = load_knowledge()
                trace.set_meta(memory_chars=len(memory), knowledge_chars=len(knowledge))

            with trace.span("llm_request"):
                advice = call_openai(mode, summary, user_note, memory, knowledge, trace)

            with trace.span("response_build"):
                payload = {
                    "ok": True,
                    "mode": mode,
                    "recommended_mode": detect_recommended_mode(summary),
                    "advice": advice,
                    "state": summary,
                    "created_at": int(time.time()),
                }
            payload["trace"] = trace.to_payload()

            json_response(self, 200, payload)
        except ValueError as exc:
            json_response(self, 400, {"ok": False, "error": str(exc), "trace": trace.to_payload()})
        except Exception as exc:
            json_response(self, 500, {"ok": False, "error": str(exc), "trace": trace.to_payload()})

    def handle_analyze_stream(self) -> None:
        trace = TraceContext()
        with trace.span("read_body"):
            body = read_json_body(self)
            mode = str(body.get("mode") or "general")
            user_note = str(body.get("note") or "")
            trace.set_meta(mode=mode, streaming=True)
            if mode not in ALLOWED_MODES:
                raise ValueError(f"mode must be one of: {', '.join(sorted(ALLOWED_MODES))}")

        sse_start(self)
        advice_parts: list[str] = []
        try:
            sse_write(self, "status", {"message": "reading_state"})
            with trace.span("read_state"):
                raw_state = get_raw_state()
                trace.set_meta(state_chars=json_char_count(raw_state))

            with trace.span("summarize_state"):
                summary = summarize_state(raw_state)
                if mode == "map":
                    scout = scout_map(raw_state)
                    summary["map_scout"] = scout_prompt_summary(scout)
                    trace.set_meta(map_scout_ready=bool(scout.get("ok")))

            recommended_mode = detect_recommended_mode(summary)
            sse_write(self, "state", {"state": summary, "recommended_mode": recommended_mode})

            sse_write(self, "status", {"message": "loading_context"})
            with trace.span("load_context"):
                memory = load_memory()
                knowledge = load_knowledge()
                trace.set_meta(memory_chars=len(memory), knowledge_chars=len(knowledge))

            def on_delta(delta: str) -> None:
                advice_parts.append(delta)
                sse_write(self, "delta", {"text": delta})

            sse_write(self, "status", {"message": "streaming_model"})
            with trace.span("llm_request"):
                advice = call_openai_stream(mode, summary, user_note, memory, knowledge, on_delta, trace)

            if not advice:
                advice = "".join(advice_parts).strip()

            with trace.span("response_build"):
                payload = {
                    "ok": True,
                    "mode": mode,
                    "recommended_mode": recommended_mode,
                    "advice": advice,
                    "state": summary,
                    "created_at": int(time.time()),
                    "trace": trace.to_payload(),
                }
            sse_write(self, "done", payload)
            self.close_connection = True
        except Exception as exc:
            sse_write(self, "error", {"ok": False, "error": str(exc), "trace": trace.to_payload()})
            self.close_connection = True

    def handle_memory_append(self) -> None:
        body = read_json_body(self)
        note = str(body.get("note") or "")
        source = str(body.get("source") or "web")
        entry = append_memory(note, source=source)
        json_response(self, 200, {"ok": True, "entry": entry})

    def handle_static(self, path: str) -> None:
        if path in {"", "/"}:
            path = "/index.html"
        safe = path.lstrip("/").replace("\\", "/")
        if ".." in safe.split("/"):
            json_response(self, 400, {"ok": False, "error": "Invalid path."})
            return
        file_path = STATIC_DIR / safe
        if not file_path.exists() or not file_path.is_file():
            json_response(self, 404, {"ok": False, "error": "Not found."})
            return
        text_response(self, 200, file_path.read_bytes(), content_type_for(file_path))

    def handle_spire_codex_asset(self, path: str) -> None:
        safe = path.removeprefix("/assets/spire-codex/").replace("\\", "/")
        if not safe or ".." in safe.split("/"):
            json_response(self, 400, {"ok": False, "error": "Invalid asset path."})
            return
        file_path = SPIRE_CODEX_DATA_DIR / safe
        if not file_path.exists() or not file_path.is_file():
            json_response(self, 404, {"ok": False, "error": "Asset not found."})
            return
        text_response(self, 200, file_path.read_bytes(), content_type_for(file_path))


def main() -> None:
    try:
        host = env("COACH_HOST", "127.0.0.1")
        port = int(env("COACH_PORT", "8766"))
        httpd = ThreadingHTTPServer((host, port), CoachHandler)
        try:
            print(f"STS2 Coach running at http://{host}:{port}", flush=True)
            print("Press Ctrl+C to stop.", flush=True)
        except OSError:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()
    except Exception as exc:
        log_path = ROOT / "server-error.log"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().isoformat()} {type(exc).__name__}: {exc}\n")
        raise


if __name__ == "__main__":
    main()
