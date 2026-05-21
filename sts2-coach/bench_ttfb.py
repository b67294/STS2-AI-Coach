from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from app import (
    KNOWLEDGE_DIR,
    PROMPTS_DIR,
    ROOT,
    build_user_payload,
    detect_recommended_mode,
    env,
    get_raw_state,
    json_char_count,
    load_knowledge,
    load_memory,
    read_text,
    summarize_state,
)


MODELS = ("qwen3.5-flash", "qwen3.6-plus")
CONTEXT_PROFILES = ("full_context", "slim_context")


@dataclass
class TtfbResult:
    model: str
    context_profile: str
    ok: bool
    ttfb_ms: int | None
    total_ms: int | None
    input_chars: int | None
    knowledge_chars: int
    output_chars: int | None
    chunks: int
    error: str


def slim_knowledge_for(summary: dict[str, Any]) -> str:
    parts = []
    for filename in ("silent-a10.md", "events.md"):
        text = read_text(KNOWLEDGE_DIR / filename)
        if text:
            parts.append(text)

    vendor_events = ROOT / "vendor" / "sts2-ai-agent-v0.7.2-windows-2" / "docs" / "game-knowledge" / "events.md"
    text = read_text(vendor_events)
    if text:
        parts.append("# STS2-Agent Event Reference\n\n" + text)

    if detect_recommended_mode(summary) != "event":
        parts.append("当前不是事件页；本次 slim_context 仍按 EVENT 裁剪策略执行。")

    return "\n\n".join(parts)


def build_chat_payload(
    *,
    model: str,
    mode: str,
    summary: dict[str, Any],
    user_note: str,
    memory: str,
    knowledge: str,
) -> bytes:
    system_prompt = read_text(PROMPTS_DIR / "system.md")
    user_payload = build_user_payload(mode, summary, user_note, memory, knowledge)
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
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def text_delta(payload: dict[str, Any]) -> str:
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


def run_stream_request(*, model: str, summary: dict[str, Any], memory: str, knowledge: str) -> TtfbResult:
    api_key = env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    base_url = env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    body = build_chat_payload(
        model=model,
        mode="event",
        summary=summary,
        user_note="",
        memory=memory,
        knowledge=knowledge,
    )
    started = time.perf_counter()
    first_chunk_at: float | None = None
    chunks = 0
    output_parts: list[str] = []
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

    try:
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
                if first_chunk_at is None:
                    first_chunk_at = time.perf_counter()
                chunks += 1
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                output_parts.append(text_delta(event))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Chat Completions stream error HTTP {exc.code}: {details}") from exc
    except (error.URLError, TimeoutError, socket.timeout) as exc:
        host = urlparse(base_url).hostname or base_url
        raise RuntimeError(f"Cannot reach Chat Completions stream API at {host}: {exc}") from exc

    total_ms = round((time.perf_counter() - started) * 1000)
    ttfb_ms = round((first_chunk_at - started) * 1000) if first_chunk_at is not None else None
    return TtfbResult(
        model=model,
        context_profile="",
        ok=True,
        ttfb_ms=ttfb_ms,
        total_ms=total_ms,
        input_chars=len(body.decode("utf-8")),
        knowledge_chars=len(knowledge),
        output_chars=len("".join(output_parts)),
        chunks=chunks,
        error="",
    )


def run_case(
    *,
    model: str,
    context_profile: str,
    summary: dict[str, Any],
    memory: str,
    full_knowledge: str,
    slim_knowledge: str,
) -> TtfbResult:
    knowledge = full_knowledge if context_profile == "full_context" else slim_knowledge
    try:
        result = run_stream_request(model=model, summary=summary, memory=memory, knowledge=knowledge)
        result.context_profile = context_profile
        return result
    except Exception as exc:
        return TtfbResult(
            model=model,
            context_profile=context_profile,
            ok=False,
            ttfb_ms=None,
            total_ms=None,
            input_chars=None,
            knowledge_chars=len(knowledge),
            output_chars=None,
            chunks=0,
            error=str(exc).replace("\n", " ")[:180],
        )


def markdown_row(result: TtfbResult) -> str:
    def cell(value: Any) -> str:
        if value is None:
            return ""
        return str(value).replace("|", "\\|")

    return (
        f"| {cell(result.model)} "
        f"| {cell(result.context_profile)} "
        f"| {cell(result.ttfb_ms)} "
        f"| {cell(result.total_ms)} "
        f"| {cell(result.input_chars)} "
        f"| {cell(result.knowledge_chars)} "
        f"| {cell(result.output_chars)} "
        f"| {cell(result.chunks)} "
        f"| {'yes' if result.ok else 'no'} "
        f"| {cell(result.error)} |"
    )


def main() -> None:
    raw_state = get_raw_state()
    summary = summarize_state(raw_state)
    memory = load_memory()
    full_knowledge = load_knowledge()
    slim_knowledge = slim_knowledge_for(summary)

    print("mode: event")
    print(f"screen: {summary.get('screen')}")
    print(f"state_chars: {json_char_count(summary)}")
    print(f"full_knowledge_chars: {len(full_knowledge)}")
    print(f"slim_knowledge_chars: {len(slim_knowledge)}")
    print()
    print("| model | context | ttfb_ms | total_ms | input_chars | knowledge_chars | output_chars | chunks | ok | error |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |")

    for model in MODELS:
        for context_profile in CONTEXT_PROFILES:
            result = run_case(
                model=model,
                context_profile=context_profile,
                summary=summary,
                memory=memory,
                full_knowledge=full_knowledge,
                slim_knowledge=slim_knowledge,
            )
            print(markdown_row(result), flush=True)


if __name__ == "__main__":
    main()
