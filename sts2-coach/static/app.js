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

let lastAdvice = "";
let lastState = null;

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
  const lines = [
    `角色/进阶：${run.character || player.character || "未知"} / A${run.ascension ?? "?"}`,
    `楼层/Boss：${run.floor ?? "?"} / ${run.boss || run.boss_id || "未知"}`,
    `血量/金币：${player.hp ?? "?"}/${player.max_hp ?? "?"} / ${player.gold ?? "?"}`,
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
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
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
      stateSummary.textContent = `Mod 已连接，但 /state 状态接口异常：\n${payload.sts2.state_error || "未知错误"}\n\n这通常是 STS2-Agent 与当前游戏版本不兼容。`;
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
  } catch (error) {
    stateSummary.textContent = `读取状态失败：${error.message}`;
  }
}

async function analyze(mode) {
  loading.hidden = false;
  adviceText.textContent = "分析中，请稍等...";
  saveAdviceBtn.disabled = true;
  try {
    const payload = await fetchJson("/api/analyze", {
      method: "POST",
      body: JSON.stringify({ mode, note: noteInput.value }),
    });
    lastAdvice = payload.advice;
    lastState = payload.state;
    adviceText.textContent = payload.advice;
    stateSummary.textContent = compactState(payload.state);
    modeStatus.textContent = payload.recommended_mode || mode;
    saveAdviceBtn.disabled = false;
  } catch (error) {
    adviceText.textContent = `分析失败：${error.message}`;
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
    adviceText.textContent = `${lastAdvice}\n\n已记录：${payload.entry}`;
  } catch (error) {
    adviceText.textContent = `${lastAdvice}\n\n记录失败：${error.message}`;
  }
}

document.querySelectorAll("[data-mode]").forEach((button) => {
  button.addEventListener("click", () => analyze(button.dataset.mode));
});

refreshBtn.addEventListener("click", refreshHealth);
saveAdviceBtn.addEventListener("click", saveAdvice);

refreshHealth();
