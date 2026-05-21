from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app import (
    KNOWLEDGE_DIR,
    ROOT,
    call_openai,
    detect_recommended_mode,
    get_raw_state,
    json_char_count,
    load_knowledge,
    load_memory,
    read_text,
    summarize_state,
)
from tracing import TraceContext


MODELS = ("qwen3.5-flash", "qwen3.6-plus")
CONTEXT_PROFILES = ("full_context", "slim_context")


@dataclass
class BenchResult:
    model: str
    context_profile: str
    ok: bool
    total_ms: int | None
    llm_http_wait_ms: int | None
    input_chars: int | None
    knowledge_chars: int
    output_chars: int | None
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
        parts.append("当前不是事件页；此 slim_context 仍按 EVENT 裁剪策略执行。")

    return "\n\n".join(parts)


def span_ms(trace_payload: dict[str, Any], name: str) -> int | None:
    for span in trace_payload.get("spans", []):
        if isinstance(span, dict) and span.get("name") == name:
            value = span.get("ms")
            return value if isinstance(value, int) else None
    return None


def run_case(
    *,
    model: str,
    context_profile: str,
    summary: dict[str, Any],
    memory: str,
    full_knowledge: str,
    slim_knowledge: str,
    previous_model: str | None,
) -> BenchResult:
    knowledge = full_knowledge if context_profile == "full_context" else slim_knowledge
    os.environ["OPENAI_MODEL"] = model
    trace = TraceContext()
    trace.set_meta(
        model=model,
        context_profile=context_profile,
        state_chars=json_char_count(summary),
        memory_chars=len(memory),
        knowledge_chars=len(knowledge),
    )

    try:
        with trace.span("llm_request"):
            advice = call_openai("event", summary, "", memory, knowledge, trace)
        trace.set_meta(output_chars=len(advice))
        payload = trace.to_payload()
        meta = payload.get("meta", {})
        return BenchResult(
            model=model,
            context_profile=context_profile,
            ok=True,
            total_ms=payload.get("total_ms"),
            llm_http_wait_ms=span_ms(payload, "llm_http_wait"),
            input_chars=meta.get("input_chars") if isinstance(meta, dict) else None,
            knowledge_chars=len(knowledge),
            output_chars=meta.get("output_chars") if isinstance(meta, dict) else None,
            error="",
        )
    except Exception as exc:
        payload = trace.to_payload()
        meta = payload.get("meta", {})
        return BenchResult(
            model=model,
            context_profile=context_profile,
            ok=False,
            total_ms=payload.get("total_ms"),
            llm_http_wait_ms=span_ms(payload, "llm_http_wait"),
            input_chars=meta.get("input_chars") if isinstance(meta, dict) else None,
            knowledge_chars=len(knowledge),
            output_chars=meta.get("output_chars") if isinstance(meta, dict) else None,
            error=str(exc).replace("\n", " ")[:180],
        )
    finally:
        if previous_model is None:
            os.environ.pop("OPENAI_MODEL", None)
        else:
            os.environ["OPENAI_MODEL"] = previous_model


def markdown_row(result: BenchResult) -> str:
    def cell(value: Any) -> str:
        if value is None:
            return ""
        text = str(value).replace("|", "\\|")
        return text

    return (
        f"| {cell(result.model)} "
        f"| {cell(result.context_profile)} "
        f"| {cell(result.total_ms)} "
        f"| {cell(result.llm_http_wait_ms)} "
        f"| {cell(result.input_chars)} "
        f"| {cell(result.knowledge_chars)} "
        f"| {cell(result.output_chars)} "
        f"| {'yes' if result.ok else 'no'} "
        f"| {cell(result.error)} |"
    )


def main() -> None:
    raw_state = get_raw_state()
    summary = summarize_state(raw_state)
    memory = load_memory()
    full_knowledge = load_knowledge()
    slim_knowledge = slim_knowledge_for(summary)
    previous_model = os.environ.get("OPENAI_MODEL")

    print(f"mode: event")
    print(f"screen: {summary.get('screen')}")
    print(f"full_knowledge_chars: {len(full_knowledge)}")
    print(f"slim_knowledge_chars: {len(slim_knowledge)}")
    print()
    print("| model | context | total_ms | llm_http_wait_ms | input_chars | knowledge_chars | output_chars | ok | error |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |")

    for model in MODELS:
        for context_profile in CONTEXT_PROFILES:
            result = run_case(
                model=model,
                context_profile=context_profile,
                summary=summary,
                memory=memory,
                full_knowledge=full_knowledge,
                slim_knowledge=slim_knowledge,
                previous_model=previous_model,
            )
            print(markdown_row(result), flush=True)


if __name__ == "__main__":
    main()
