from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "spire-codex"
IMAGE_ROUTE_PREFIX = "/assets/spire-codex/"


ROOM_TYPE_BY_NODE = {
    "Monster": {"Monster", "Normal", "WeakMonster"},
    "Elite": {"Elite"},
    "Boss": {"Boss"},
}

RESOURCE_NODE_LABELS = {
    "Rest": "火堆",
    "Shop": "商店",
    "Treasure": "宝箱",
    "Event": "事件",
    "Monster": "普通战斗",
    "Elite": "精英",
    "Boss": "Boss",
}


@dataclass
class SpireCodexKnowledge:
    ready: bool
    meta: dict[str, Any]
    monsters: list[dict[str, Any]]
    encounters: list[dict[str, Any]]
    events: list[dict[str, Any]]
    acts: list[dict[str, Any]]
    error: str | None = None


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback
    except json.JSONDecodeError:
        return fallback


def load_spire_codex(data_dir: Path = DATA_DIR) -> SpireCodexKnowledge:
    meta_path = data_dir / "meta.json"
    required = ("monsters.json", "encounters.json", "events.json", "acts.json")
    missing = [name for name in required if not (data_dir / name).exists()]
    if missing:
        return SpireCodexKnowledge(
            ready=False,
            meta={},
            monsters=[],
            encounters=[],
            events=[],
            acts=[],
            error="知识库未同步：请运行 python scripts/sync_spire_codex.py",
        )

    return SpireCodexKnowledge(
        ready=True,
        meta=read_json(meta_path, {}),
        monsters=as_list(read_json(data_dir / "monsters.json", [])),
        encounters=as_list(read_json(data_dir / "encounters.json", [])),
        events=as_list(read_json(data_dir / "events.json", [])),
        acts=as_list(read_json(data_dir / "acts.json", [])),
    )


def as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("data", "items", "results"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def coords_key(node: dict[str, Any]) -> tuple[int, int] | None:
    row = node.get("row")
    col = node.get("col")
    if isinstance(row, int) and isinstance(col, int):
        return row, col
    return None


def node_label(node_type: str) -> str:
    return RESOURCE_NODE_LABELS.get(node_type, node_type or "未知")


def act_token(state: dict[str, Any]) -> str | None:
    run = state.get("run") if isinstance(state.get("run"), dict) else {}
    raw = run.get("act") or run.get("act_id")
    if raw is None:
        return None
    text = str(raw)
    if text.isdigit():
        return f"Act {int(text) + 1}"
    return text


def belongs_to_act(item: dict[str, Any], token: str | None) -> bool:
    if not token:
        return True
    act = str(item.get("act") or item.get("act_id") or item.get("area") or "")
    return not act or token.lower() in act.lower()


def room_type_matches(encounter: dict[str, Any], node_type: str) -> bool:
    wanted = ROOM_TYPE_BY_NODE.get(node_type)
    if not wanted:
        return False
    raw = str(encounter.get("room_type") or encounter.get("type") or encounter.get("pool") or "")
    return raw in wanted or any(value.lower() in raw.lower() for value in wanted)


def first_value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def image_asset_url(raw_url: Any) -> str | None:
    if not isinstance(raw_url, str) or not raw_url:
        return None
    if raw_url.startswith("/assets/spire-codex/"):
        return raw_url
    filename = raw_url.rsplit("/", 1)[-1]
    if not filename:
        return None
    if not (DATA_DIR / "images" / filename).exists():
        return None
    return f"{IMAGE_ROUTE_PREFIX}images/{filename}"


def monster_index(monsters: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for monster in monsters:
        for key in ("id", "name", "internal_id"):
            value = monster.get(key)
            if isinstance(value, str) and value:
                index[value.lower()] = monster
    return index


def encounter_monster_refs(encounter: dict[str, Any]) -> list[str]:
    raw = first_value(encounter, "monsters", "monster_ids", "foes", "lineup", "enemies")
    refs: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                refs.append(item)
            elif isinstance(item, dict):
                value = first_value(item, "id", "monster_id", "name")
                if isinstance(value, str):
                    refs.append(value)
    return refs


def summarize_monster(monster: dict[str, Any]) -> dict[str, Any]:
    hp = first_value(monster, "hp", "hp_range", "max_hp", "health")
    moves = first_value(monster, "moves", "move_set", "attacks")
    if isinstance(moves, list):
        move_names = []
        for move in moves[:4]:
            if isinstance(move, dict):
                name = first_value(move, "name", "id", "intent")
                if isinstance(name, str):
                    move_names.append(name)
            elif isinstance(move, str):
                move_names.append(move)
        moves = move_names
    return {
        "id": monster.get("id"),
        "name": monster.get("name") or monster.get("id"),
        "type": first_value(monster, "type", "monster_type"),
        "hp": hp,
        "moves": moves if isinstance(moves, list) else [],
        "image_url": image_asset_url(first_value(monster, "image_url", "image", "sprite_url")),
    }


def summarize_encounter(encounter: dict[str, Any], monsters_by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    refs = encounter_monster_refs(encounter)
    monsters = []
    for ref in refs[:4]:
        monster = monsters_by_key.get(ref.lower())
        monsters.append(summarize_monster(monster) if monster else {"id": ref, "name": ref, "image_url": None})
    return {
        "id": encounter.get("id"),
        "name": encounter.get("name") or encounter.get("id"),
        "room_type": first_value(encounter, "room_type", "type", "pool"),
        "act": encounter.get("act"),
        "tags": encounter.get("tags") if isinstance(encounter.get("tags"), list) else [],
        "monsters": monsters,
    }


def possible_encounters(
    knowledge: SpireCodexKnowledge,
    node_type: str,
    token: str | None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    if node_type not in ROOM_TYPE_BY_NODE:
        return []
    monsters_by_key = monster_index(knowledge.monsters)
    matches = [
        encounter
        for encounter in knowledge.encounters
        if room_type_matches(encounter, node_type) and belongs_to_act(encounter, token)
    ]
    if not matches and token:
        matches = [encounter for encounter in knowledge.encounters if room_type_matches(encounter, node_type)]
    return [summarize_encounter(encounter, monsters_by_key) for encounter in matches[:limit]]


def possible_events(knowledge: SpireCodexKnowledge, token: str | None, limit: int = 8) -> list[dict[str, Any]]:
    matches = [event for event in knowledge.events if belongs_to_act(event, token)]
    if not matches and token:
        matches = knowledge.events
    output = []
    for event in matches[:limit]:
        output.append(
            {
                "id": event.get("id"),
                "name": event.get("name") or event.get("id"),
                "type": event.get("type"),
                "act": event.get("act"),
                "description": event.get("description"),
                "options": event.get("options") if isinstance(event.get("options"), list) else [],
                "preconditions": event.get("preconditions") if isinstance(event.get("preconditions"), list) else [],
                "image_url": image_asset_url(first_value(event, "image_url", "image")),
            }
        )
    return output


def encounters_by_group(knowledge: SpireCodexKnowledge, token: str | None, limit_per_group: int = 12) -> dict[str, list[dict[str, Any]]]:
    monsters_by_key = monster_index(knowledge.monsters)
    groups = {"weak": [], "normal": [], "elite": [], "boss": []}
    for encounter in knowledge.encounters:
        if not belongs_to_act(encounter, token):
            continue
        room_type = str(encounter.get("room_type") or "")
        if room_type == "Boss":
            group = "boss"
        elif room_type == "Elite":
            group = "elite"
        elif room_type == "Monster" and encounter.get("is_weak") is True:
            group = "weak"
        elif room_type == "Monster":
            group = "normal"
        else:
            continue
        if len(groups[group]) < limit_per_group:
            groups[group].append(summarize_encounter(encounter, monsters_by_key))
    return groups


def expand_path(start: dict[str, Any], nodes_by_coord: dict[tuple[int, int], dict[str, Any]], depth: int) -> list[dict[str, Any]]:
    path = [start]
    current = start
    seen = {coords_key(start)}
    while len(path) < depth:
        children = current.get("children") if isinstance(current.get("children"), list) else []
        candidates = []
        for child in children:
            if not isinstance(child, dict):
                continue
            key = coords_key(child)
            if key and key in nodes_by_coord and key not in seen:
                candidates.append(nodes_by_coord[key])
        if not candidates:
            break
        candidates.sort(key=lambda node: (node.get("row", 999), node.get("col", 999)))
        current = candidates[0]
        path.append(current)
        seen.add(coords_key(current))
        if str(current.get("node_type")) == "Boss":
            break
    return path


def route_risk_level(path: list[dict[str, Any]]) -> str:
    score = 0
    for node in path:
        node_type = str(node.get("node_type") or "")
        if node_type == "Elite":
            score += 3
        elif node_type == "Boss":
            score += 4
        elif node_type == "Monster":
            score += 1
        elif node_type in {"Rest", "Shop", "Treasure"}:
            score -= 1
    if score >= 5:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def warnings_for_path(path: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for node in path:
        node_type = str(node.get("node_type") or "Unknown")
        counts[node_type] = counts.get(node_type, 0) + 1
    warnings = []
    if counts.get("Elite", 0) >= 2:
        warnings.append("未来路线包含多个精英，低血量或牌组未成型时风险高。")
    if counts.get("Monster", 0) >= 3:
        warnings.append("连续普通战斗较多，需要稳定防御和前期输出。")
    if counts.get("Rest", 0) == 0 and (counts.get("Elite", 0) or counts.get("Boss", 0)):
        warnings.append("精英/Boss 前缺少火堆，注意血量和关键牌升级窗口。")
    if counts.get("Shop", 0):
        warnings.append("路线含商店，金币、删牌和药水价值上升。")
    if counts.get("Event", 0) >= 2:
        warnings.append("事件密度高，收益波动大，适合需要变牌/删牌/资源补强的局面。")
    return warnings


def image_urls_for_route(route: dict[str, Any], limit: int = 8) -> list[str]:
    urls = []
    for encounter in route.get("possible_encounters", []):
        for monster in encounter.get("monsters", []):
            url = monster.get("image_url")
            if isinstance(url, str) and url not in urls:
                urls.append(url)
            if len(urls) >= limit:
                return urls
    for event in route.get("possible_events", []):
        url = event.get("image_url")
        if isinstance(url, str) and url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            return urls
    return urls


def scout_map(state: dict[str, Any], knowledge: SpireCodexKnowledge | None = None, depth: int = 5) -> dict[str, Any]:
    knowledge = knowledge or load_spire_codex()
    if not knowledge.ready:
        return {
            "ok": False,
            "knowledge": {"ready": False, "error": knowledge.error},
            "routes": [],
        }

    map_state = state.get("map") if isinstance(state.get("map"), dict) else None
    if not map_state:
        return {
            "ok": False,
            "knowledge": knowledge_payload(knowledge),
            "error": "当前不在地图界面，无法生成地图侦察。",
            "routes": [],
        }

    nodes = [node for node in map_state.get("nodes", []) if isinstance(node, dict)]
    nodes_by_coord = {key: node for node in nodes if (key := coords_key(node))}
    token = act_token(state)
    routes = []
    for available in map_state.get("available_nodes", []):
        if not isinstance(available, dict):
            continue
        key = coords_key(available)
        start = nodes_by_coord.get(key, available)
        path = expand_path(start, nodes_by_coord, depth)
        node_types = [str(node.get("node_type") or "Unknown") for node in path]
        route = {
            "option_index": available.get("index"),
            "start": {"row": available.get("row"), "col": available.get("col"), "node_type": available.get("node_type")},
            "path": [
                {"row": node.get("row"), "col": node.get("col"), "node_type": node.get("node_type"), "label": node_label(str(node.get("node_type") or ""))}
                for node in path
            ],
            "node_sequence": " -> ".join(node_label(node_type) for node_type in node_types),
            "risk_level": route_risk_level(path),
            "possible_encounters": [],
            "possible_events": [],
            "warnings": warnings_for_path(path),
        }
        seen_node_types = set(node_types)
        for node_type in ("Monster", "Elite", "Boss"):
            if node_type in seen_node_types:
                route["possible_encounters"].extend(possible_encounters(knowledge, node_type, token))
        if "Event" in seen_node_types:
            route["possible_events"] = possible_events(knowledge, token)
        route["image_urls"] = image_urls_for_route(route)
        routes.append(route)

    return {
        "ok": True,
        "knowledge": knowledge_payload(knowledge),
        "act": token,
        "boss": (state.get("run") or {}).get("boss_id") if isinstance(state.get("run"), dict) else None,
        "current_node": map_state.get("current_node"),
        "overview": {
            "encounters": encounters_by_group(knowledge, token),
            "events": possible_events(knowledge, token, limit=24),
        },
        "routes": routes,
    }


def knowledge_payload(knowledge: SpireCodexKnowledge) -> dict[str, Any]:
    return {
        "ready": knowledge.ready,
        "source": "Spire Codex",
        "synced_at": knowledge.meta.get("synced_at"),
        "language": knowledge.meta.get("language"),
        "revision": knowledge.meta.get("revision"),
    }


def scout_prompt_summary(scout: dict[str, Any]) -> str:
    if not scout.get("ok"):
        return str(scout.get("error") or scout.get("knowledge", {}).get("error") or "地图侦察不可用。")
    lines = [
        f"地图侦察：当前 Act={scout.get('act') or '未知'}，Boss={scout.get('boss') or '未知'}。",
        "以下是当前可选路线的遭遇池/事件池风险摘要，不代表精确预测。",
    ]
    for route in scout.get("routes", [])[:4]:
        lines.append(f"- 路线 option_index={route.get('option_index')}：{route.get('node_sequence')}；风险={route.get('risk_level')}")
        for warning in route.get("warnings", [])[:3]:
            lines.append(f"  - 注意：{warning}")
        encounters = route.get("possible_encounters", [])[:3]
        if encounters:
            names = []
            for encounter in encounters:
                monster_names = [monster.get("name") for monster in encounter.get("monsters", []) if monster.get("name")]
                names.append(f"{encounter.get('name')}: {'/'.join(monster_names)}")
            lines.append(f"  - 可能遭遇：{'; '.join(names)}")
        events = route.get("possible_events", [])[:5]
        if events:
            lines.append("  - 可能事件：" + "、".join(str(event.get("name")) for event in events if event.get("name")))
    return "\n".join(lines)
