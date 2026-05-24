const gameStatus = document.getElementById("gameStatus");
const apiStatus = document.getElementById("apiStatus");
const screenStatus = document.getElementById("screenStatus");
const modeStatus = document.getElementById("modeStatus");
const stateSummary = document.getElementById("stateSummary");
const adviceText = document.getElementById("adviceText");
const loading = document.getElementById("loading");
const noteInput = document.getElementById("noteInput");
const saveAdviceBtn = document.getElementById("saveAdviceBtn");
const refreshBtn = document.getElementById("refreshBtn");
const toggleScoutBtn = document.getElementById("toggleScoutBtn");
const refreshScoutBtn = document.getElementById("refreshScoutBtn");
const mapScoutBody = document.getElementById("mapScoutBody");
const mapScoutText = document.getElementById("mapScoutText");
const mapScoutOverview = document.getElementById("mapScoutOverview");
const monsterDetail = document.getElementById("monsterDetail");
const eventDetail = document.getElementById("eventDetail");
const mapScoutRoutes = document.getElementById("mapScoutRoutes");

let lastAdvice = "";
let lastState = null;
let scoutCollapsed = false;

function setStatus(el, text, ok) {
  el.textContent = text;
  el.classList.toggle("ok", ok === true);
  el.classList.toggle("fail", ok === false);
}

function compactState(state) {
  if (!state) return "无状态";
  const run = state.run || {};
  const player = state.player || {};
  const deck = Array.isArray(state.deck) ? state.deck : [];
  const relics = Array.isArray(state.relics) ? state.relics : [];
  const hp = player.hp ?? run.hp ?? run.current_hp ?? state.current_hp;
  const maxHp = player.max_hp ?? run.max_hp ?? state.max_hp;
  const gold = player.gold ?? run.gold ?? state.gold;
  const lines = [
    `角色/进阶：${run.character || player.character || "未知"} / A${run.ascension ?? "?"}`,
    `楼层/Boss：${run.floor ?? "?"} / ${run.boss || run.boss_id || "未知"}`,
    `血量/金币：${hp ?? "?"}/${maxHp ?? "?"} / ${gold ?? "?"}`,
    `牌组：${deck.length} 张`,
    `遗物：${relics.length} 个`,
    `可用动作：${Array.isArray(state.available_actions) ? state.available_actions.join(", ") : "未知"}`,
  ];
  if (state.reward) lines.push("奖励：已检测到");
  if (state.map) lines.push("地图：已检测到");
  if (state.event) lines.push("事件：已检测到");
  if (state.shop) lines.push("商店：已检测到");
  if (state.rest) lines.push("火堆：已检测到");
  return lines.join("\n");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    const error = new Error(payload.error || `HTTP ${response.status}`);
    error.payload = payload;
    throw error;
  }
  return payload;
}

function formatTrace(trace) {
  if (!trace || !Array.isArray(trace.spans)) return "";
  const spans = trace.spans.map((span) => `- ${span.name}: ${span.ms}ms`).join("\n");
  const slowest = trace.spans.reduce((best, span) => (!best || span.ms > best.ms ? span : best), null);
  const slowestLine = slowest ? `\n最慢阶段：${slowest.name} (${slowest.ms}ms)` : "";
  const firstEventLine =
    trace.meta && trace.meta.first_stream_event_ms ? `\n首个流事件：${trace.meta.first_stream_event_ms}ms` : "";
  const visibleLine =
    trace.meta && trace.meta.first_visible_delta_ms ? `\n首个可见文本：${trace.meta.first_visible_delta_ms}ms` : "";
  const failedLine = trace.failed_span ? `\n失败阶段：${trace.failed_span}` : "";
  return `\n\n本次耗时：${trace.total_ms}ms${firstEventLine}${visibleLine}${slowestLine}${failedLine}\n${spans}`;
}

function withTrace(text, trace) {
  return `${text || ""}${formatTrace(trace)}`;
}

function markdownToHtml(markdown) {
  const source = markdown || "";
  if (!window.marked || !window.DOMPurify) {
    return source.replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[char]);
  }
  marked.setOptions({ breaks: true, gfm: true });
  return DOMPurify.sanitize(marked.parse(source));
}

function setAdviceMarkdown(markdown) {
  adviceText.innerHTML = markdownToHtml(markdown);
}

function setAdvicePlain(text) {
  adviceText.textContent = text || "";
}

function clearMapScout(text = "地图页会显示未来路线的怪物、事件和风险预警。") {
  mapScoutText.textContent = text;
  mapScoutOverview.innerHTML = "";
  monsterDetail.hidden = true;
  monsterDetail.innerHTML = "";
  eventDetail.hidden = true;
  eventDetail.innerHTML = "";
  mapScoutRoutes.innerHTML = "";
}

function setScoutCollapsed(collapsed) {
  scoutCollapsed = collapsed;
  mapScoutBody.hidden = collapsed;
  toggleScoutBtn.textContent = collapsed ? "展开" : "收起";
}

function riskLabel(risk) {
  if (risk === "high") return "高风险";
  if (risk === "medium") return "中风险";
  return "低风险";
}

function encounterImages(encounter) {
  const monsters = Array.isArray(encounter.monsters) ? encounter.monsters : [];
  return monsters.map((monster) => monster.image_url).filter(Boolean);
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "object") {
    if ("normal" in value || "ascension" in value) {
      const normal = value.normal ?? "?";
      const asc = value.ascension ?? normal;
      return `${normal} / 进阶 ${asc}`;
    }
    return JSON.stringify(value);
  }
  return String(value);
}

function hpLine(monster) {
  const normal =
    monster.min_hp !== null && monster.min_hp !== undefined && monster.max_hp !== null && monster.max_hp !== undefined
      ? `${monster.min_hp}-${monster.max_hp}`
      : "";
  const asc =
    monster.min_hp_ascension !== null &&
    monster.min_hp_ascension !== undefined &&
    monster.max_hp_ascension !== null &&
    monster.max_hp_ascension !== undefined
      ? `${monster.min_hp_ascension}-${monster.max_hp_ascension}`
      : "";
  if (normal && asc) return `生命：${normal} / 进阶 ${asc}`;
  if (normal) return `生命：${normal}`;
  return "";
}

function renderMonsterDetail(monster) {
  monsterDetail.hidden = false;
  monsterDetail.innerHTML = "";
  eventDetail.hidden = true;

  const header = document.createElement("div");
  header.className = "monster-detail-header";
  if (monster.image_url) {
    const img = document.createElement("img");
    img.src = monster.image_url;
    img.alt = monster.name || "怪物";
    header.appendChild(img);
  }
  const titleBox = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = monster.name || monster.id || "未知怪物";
  titleBox.appendChild(title);
  const meta = document.createElement("div");
  meta.className = "monster-detail-meta";
  meta.textContent = [monster.type, hpLine(monster)].filter(Boolean).join(" / ");
  titleBox.appendChild(meta);
  header.appendChild(titleBox);
  monsterDetail.appendChild(header);

  if (monster.attack_pattern && monster.attack_pattern.description) {
    const pattern = document.createElement("p");
    pattern.textContent = `行动模式：${monster.attack_pattern.description}`;
    monsterDetail.appendChild(pattern);
  }

  const moves = Array.isArray(monster.moves) ? monster.moves : [];
  if (moves.length) {
    const moveTitle = document.createElement("h4");
    moveTitle.textContent = "可能意图 / 行动";
    monsterDetail.appendChild(moveTitle);
    const list = document.createElement("div");
    list.className = "monster-moves";
    for (const move of moves) {
      const item = document.createElement("div");
      item.className = "monster-move";
      const name = document.createElement("strong");
      name.textContent = `${move.name || move.id || "行动"}${move.intent ? ` · ${move.intent}` : ""}`;
      item.appendChild(name);
      const parts = [];
      const damage = formatValue(move.damage);
      const block = formatValue(move.block);
      if (damage) parts.push(`伤害：${damage}`);
      if (block) parts.push(`格挡：${block}`);
      if (Array.isArray(move.powers) && move.powers.length) {
        parts.push(
          `效果：${move.powers
            .map((power) => `${power.power_id || "Power"}${power.amount !== undefined ? ` ${power.amount}` : ""}`)
            .join(" / ")}`
        );
      }
      if (parts.length) {
        const desc = document.createElement("span");
        desc.textContent = parts.join("；");
        item.appendChild(desc);
      }
      list.appendChild(item);
    }
    monsterDetail.appendChild(list);
  }
}

function renderEncounterGroup(title, encounters) {
  if (!Array.isArray(encounters) || !encounters.length) return null;
  const section = document.createElement("section");
  section.className = "scout-group";

  const heading = document.createElement("h3");
  heading.textContent = `${title}（${encounters.length}）`;
  section.appendChild(heading);

  const grid = document.createElement("div");
  grid.className = "encounter-grid";
  for (const encounter of encounters) {
    const item = document.createElement("article");
    item.className = "encounter-card";

    const encounterMonsters = Array.isArray(encounter.monsters) ? encounter.monsters : [];
    if (encounterMonsters.some((monster) => monster.image_url)) {
      const imgBox = document.createElement("div");
      imgBox.className = "encounter-images";
      for (const monster of encounterMonsters.slice(0, 4)) {
        if (!monster.image_url) continue;
        const button = document.createElement("button");
        button.type = "button";
        button.title = monster.name || monster.id || "怪物";
        button.addEventListener("click", () => renderMonsterDetail(monster));
        const img = document.createElement("img");
        img.src = monster.image_url;
        img.alt = monster.name || "怪物";
        img.loading = "lazy";
        button.appendChild(img);
        imgBox.appendChild(button);
      }
      item.appendChild(imgBox);
    }

    const name = document.createElement("strong");
    name.textContent = encounter.name || encounter.id || "未知遭遇";
    item.appendChild(name);

    const monsters = encounterMonsters.map((monster) => monster.name || monster.id).filter(Boolean);
    if (monsters.length) {
      const meta = document.createElement("span");
      meta.textContent = monsters.join(" / ");
      item.appendChild(meta);
    }

    grid.appendChild(item);
  }
  section.appendChild(grid);
  return section;
}

function renderEventPool(events) {
  if (!Array.isArray(events) || !events.length) return null;
  const section = document.createElement("section");
  section.className = "scout-group";
  const heading = document.createElement("h3");
  heading.textContent = `随机事件池（${events.length}）`;
  section.appendChild(heading);

  const list = document.createElement("div");
  list.className = "event-pool";
  for (const event of events) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.textContent = event.name || event.id || "未知事件";
    chip.addEventListener("click", () => renderEventDetail(event));
    list.appendChild(chip);
  }
  section.appendChild(list);
  return section;
}

function cleanMarkup(text) {
  return String(text || "")
    .replace(/\[[^\]]+\]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function renderEventDetail(event) {
  eventDetail.hidden = false;
  eventDetail.innerHTML = "";
  monsterDetail.hidden = true;

  const title = document.createElement("h3");
  title.textContent = event.name || event.id || "未知事件";
  eventDetail.appendChild(title);

  const meta = document.createElement("div");
  meta.className = "event-detail-meta";
  meta.textContent = `${event.act || "未知区域"} / ${event.type || "Event"}`;
  eventDetail.appendChild(meta);

  const description = cleanMarkup(event.description);
  if (description) {
    const body = document.createElement("p");
    body.textContent = description;
    eventDetail.appendChild(body);
  }

  const preconditions = Array.isArray(event.preconditions) ? event.preconditions.filter(Boolean) : [];
  if (preconditions.length) {
    const box = document.createElement("div");
    box.className = "event-detail-block";
    box.textContent = `出现条件：${preconditions.map(cleanMarkup).join(" / ")}`;
    eventDetail.appendChild(box);
  }

  const options = Array.isArray(event.options) ? event.options.slice(0, 6) : [];
  if (options.length) {
    const list = document.createElement("div");
    list.className = "event-options";
    for (const option of options) {
      const item = document.createElement("div");
      item.className = "event-option";
      const name = document.createElement("strong");
      name.textContent = option.title || option.id || "选项";
      item.appendChild(name);
      const optionText = cleanMarkup(option.description);
      if (optionText) {
        const desc = document.createElement("span");
        desc.textContent = optionText;
        item.appendChild(desc);
      }
      list.appendChild(item);
    }
    eventDetail.appendChild(list);
  }
}

function renderMapOverview(overview) {
  mapScoutOverview.innerHTML = "";
  monsterDetail.hidden = true;
  monsterDetail.innerHTML = "";
  eventDetail.hidden = true;
  eventDetail.innerHTML = "";
  if (!overview || !overview.encounters) return;
  const groups = [
    ["弱怪", overview.encounters.weak],
    ["普通怪", overview.encounters.normal],
    ["精英", overview.encounters.elite],
    ["Boss", overview.encounters.boss],
  ];
  for (const [title, encounters] of groups) {
    const section = renderEncounterGroup(title, encounters);
    if (section) mapScoutOverview.appendChild(section);
  }
  const events = renderEventPool(overview.events);
  if (events) mapScoutOverview.appendChild(events);
}

function renderMapScout(payload) {
  mapScoutOverview.innerHTML = "";
  mapScoutRoutes.innerHTML = "";
  if (!payload || payload.ok === false) {
    const message = payload && payload.knowledge && payload.knowledge.error ? payload.knowledge.error : payload.error;
    clearMapScout(message || "当前没有可用地图侦察。");
    return;
  }

  const routes = Array.isArray(payload.routes) ? payload.routes : [];
  mapScoutText.textContent = `Act：${payload.act || "未知"} / Boss：${payload.boss || "未知"} / 当前可选路线：${routes.length}`;
  renderMapOverview(payload.overview);
}

async function refreshMapScout() {
  try {
    mapScoutText.textContent = "正在读取地图侦察...";
    const response = await fetch("/api/map/scout");
    const payload = await response.json();
    renderMapScout(payload);
  } catch (error) {
    clearMapScout(`地图侦察失败：${error.message}`);
  }
}

async function refreshHealth() {
  try {
    const payload = await fetchJson("/api/health");
    const stateOk = payload.sts2.state_ok;
    const gameText = payload.sts2.ok ? (stateOk ? "已连接" : "状态异常") : "未连接";
    setStatus(gameStatus, gameText, payload.sts2.ok && stateOk);
    setStatus(apiStatus, payload.openai.configured ? payload.openai.model : "未配置", payload.openai.configured);
    screenStatus.textContent = payload.current.screen || "未知";
    modeStatus.textContent = payload.current.recommended_mode || "general";
    if (payload.sts2.ok && !stateOk) {
      stateSummary.textContent = `Mod 已连接，但 /state 状态接口异常：\n${payload.sts2.state_error || "未知错误"}`;
    } else {
      await refreshState();
    }
  } catch (error) {
    setStatus(gameStatus, "错误", false);
    setStatus(apiStatus, "未知", false);
    stateSummary.textContent = error.message;
  }
}

async function refreshState() {
  try {
    const payload = await fetchJson("/api/state");
    lastState = payload.state;
    stateSummary.textContent = compactState(payload.state);
    screenStatus.textContent = payload.state.screen || "未知";
    modeStatus.textContent = payload.recommended_mode || "general";
    if (payload.state.map) {
      await refreshMapScout();
    } else {
      clearMapScout();
    }
  } catch (error) {
    stateSummary.textContent = `读取状态失败：${error.message}`;
  }
}

function parseSseEvents(buffer) {
  const events = [];
  let rest = buffer;
  let boundary = rest.indexOf("\n\n");
  while (boundary !== -1) {
    const rawEvent = rest.slice(0, boundary);
    rest = rest.slice(boundary + 2);
    const parsed = { event: "message", data: "" };
    for (const line of rawEvent.split("\n")) {
      if (line.startsWith("event:")) {
        parsed.event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        parsed.data += line.slice(5).trim();
      }
    }
    if (parsed.data) events.push(parsed);
    boundary = rest.indexOf("\n\n");
  }
  return { events, rest };
}

async function analyzeStream(mode) {
  const response = await fetch("/api/analyze/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, note: noteInput.value }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let advice = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseEvents(buffer);
    buffer = parsed.rest;

    for (const item of parsed.events) {
      const payload = JSON.parse(item.data);
      if (item.event === "state") {
        lastState = payload.state;
        stateSummary.textContent = compactState(payload.state);
        modeStatus.textContent = payload.recommended_mode || mode;
      } else if (item.event === "status" && !advice) {
        setAdvicePlain("分析中，正在等待模型输出...");
      } else if (item.event === "delta") {
        advice += payload.text || "";
        setAdviceMarkdown(advice);
      } else if (item.event === "done") {
        lastAdvice = payload.advice || advice;
        lastState = payload.state || lastState;
        setAdviceMarkdown(withTrace(lastAdvice, payload.trace));
        modeStatus.textContent = payload.recommended_mode || mode;
        saveAdviceBtn.disabled = !lastAdvice;
        return;
      } else if (item.event === "error") {
        const error = new Error(payload.error || "stream error");
        error.payload = payload;
        throw error;
      }
    }
  }

  lastAdvice = advice;
  saveAdviceBtn.disabled = !lastAdvice;
}

async function analyze(mode) {
  loading.hidden = false;
  setAdvicePlain("分析中，正在建立流式连接...");
  saveAdviceBtn.disabled = true;
  lastAdvice = "";
  try {
    if (mode === "map") {
      await refreshMapScout();
    }
    await analyzeStream(mode);
  } catch (error) {
    setAdviceMarkdown(withTrace(`分析失败：${error.message}`, error.payload && error.payload.trace));
  } finally {
    loading.hidden = true;
  }
}

async function saveAdvice() {
  if (!lastAdvice) return;
  const note = `AI 建议：${lastAdvice}`;
  try {
    const payload = await fetchJson("/api/memory/append", {
      method: "POST",
      body: JSON.stringify({ source: "advice", note }),
    });
    setAdviceMarkdown(`${lastAdvice}\n\n已记录：${payload.entry}`);
  } catch (error) {
    setAdviceMarkdown(`${lastAdvice}\n\n记录失败：${error.message}`);
  }
}

document.querySelectorAll("[data-mode]").forEach((button) => {
  button.addEventListener("click", () => analyze(button.dataset.mode));
});

refreshBtn.addEventListener("click", refreshHealth);
toggleScoutBtn.addEventListener("click", () => setScoutCollapsed(!scoutCollapsed));
refreshScoutBtn.addEventListener("click", refreshMapScout);
saveAdviceBtn.addEventListener("click", saveAdvice);

refreshHealth();
