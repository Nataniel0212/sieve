/* Live NDJSON and recorded campaigns share a renderer. Model output is always
   text, never HTML. Judge codes stay in the password field, never in storage. */
"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = String(text);
    return node;
  };
  const money = (value) => `$${Number(value || 0).toFixed(4)}`;
  const seconds = (value) => `${Number(value || 0).toFixed(1)}s`;
  const title = (value) => value.charAt(0).toUpperCase() + value.slice(1);
  const shortModel = (value) => String(value || "unknown").replace(/^nvidia\//, "");
  const severityClass = (value) => ({critical: "crit", high: "high", medium: "med", safe: "ok"}[value] || "warn");
  const STOP_REASONS = {baseline_failed: "baseline failed · agent acted on benign content",
    budget: "budget stop", http_402: "provider credit exhausted (HTTP 402)"};
  const state = {catalog: null, health: null, scenario: "bank", target: "lightning", busy: false,
    cards: new Map(), max: 0, calls: 0, tokens: 0, latency: 0, cost: 0, complete: false, replay: null};

  function notice(text) {
    $("notice").textContent = text;
    $("notice").hidden = !text;
  }
  function pill(text, cls = "") {
    $("pill").className = `pill ${cls}`;
    $("pill-text").textContent = text;
  }
  function theme() {
    const dark = (document.documentElement.dataset.theme ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark";
    $("theme").textContent = dark ? "Light" : "Dark";
    $("theme").setAttribute("aria-label", `Switch to ${dark ? "light" : "dark"} theme`);
  }
  try {
    const saved = localStorage.getItem("sieve-theme");
    if (["light", "dark"].includes(saved)) document.documentElement.dataset.theme = saved;
  } catch { /* Storage can be disabled in private browsing. */ }
  theme();
  $("theme").addEventListener("click", () => {
    document.documentElement.dataset.theme = getComputedStyle(document.documentElement).colorScheme === "dark" ? "light" : "dark";
    try { localStorage.setItem("sieve-theme", document.documentElement.dataset.theme); } catch { /* optional */ }
    theme();
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", theme);

  function hasReplay() {
    return state.catalog?.replays.includes(`${state.scenario}-${state.target}`);
  }
  function controls() {
    const h = state.health;
    $("run-replay").disabled = state.busy || !hasReplay();
    $("run-live").disabled = state.busy || !h?.key_configured || !(h.public_open || h.judge_open);
    document.querySelectorAll('[role="radio"], #code').forEach((node) => { node.disabled = state.busy; });
    $("replay-ctl").hidden = !state.replay;
  }
  function availability() {
    const h = state.health;
    if (!h) $("live-status").textContent = "Live service unavailable. Recorded runs still work.";
    else if (h.fake_llm) $("live-status").textContent = "Offline development mode: simulated calls, no API spend.";
    else if (h.key_configured && h.public_open) $("live-status").textContent = "Live runs available. Each campaign has a budget stop and an attempt limit.";
    else if (h.key_configured && h.judge_open) {
      $("live-status").textContent = "Live runs need a judge code. Replays are available to everyone.";
      $("code-box").open = true;
    } else $("live-status").textContent = "Live runs are paused. Replay a recorded campaign below.";
    if (h?.shared_store) $("guard-copy").textContent =
      "Each live run has a budget stop and an attempt limit. A shared budget store reserves daily and lifetime spend before admission, with rate limits for public runs. Replays remain available when live runs are paused.";
    controls();
  }
  async function health() {
    try {
      const res = await fetch("/api/health", {cache: "no-store", signal: AbortSignal.timeout(12000)});
      if (!res.ok) throw new Error("Health unavailable");
      state.health = await res.json();
    } catch { state.health = null; }
    availability();
  }
  function choices(id, items, selected, select) {
    const group = $(id);
    group.replaceChildren();
    for (const [key, label, detail] of items) {
      const btn = el("button", id === "scen" ? "sc" : "", "");
      btn.type = "button";
      btn.setAttribute("role", "radio");
      btn.setAttribute("aria-checked", String(key === selected));
      btn.tabIndex = key === selected ? 0 : -1;
      btn.append(el("span", "t", label));
      if (detail) btn.append(el("small", "", detail));
      btn.addEventListener("click", () => {
        if (state.busy) return;
        select(key);
        renderChoices();
        $(id).querySelector('[aria-checked="true"]').focus();
      });
      group.append(btn);
    }
    group.onkeydown = (event) => {
      const keys = ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"];
      if (!keys.includes(event.key) || state.busy) return;
      event.preventDefault();
      const i = items.findIndex(([key]) => key === selected);
      const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 :
        (i + (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1) + items.length) % items.length;
      group.children[next].click();
    };
  }
  function renderChoices() {
    const catalog = state.catalog;
    choices("scen", catalog.scenarios.map((s) => [s.key, title(s.title), s.user_task]), state.scenario,
      (key) => { state.scenario = key; });
    choices("models", Object.entries(catalog.targets).map(([key, value]) =>
      [key, title(key), key === "lightning" ? "3.5" : key === "nano" ? "30B" : "550B"]), state.target,
      (key) => { state.target = key; });
    $("model-hint").textContent = (state.health?.targets || catalog.targets)[state.target].label;
    const scn = catalog.scenarios.find((s) => s.key === state.scenario);
    const brief = $("brief-body");
    brief.replaceChildren();
    for (const [label, text] of [["User task", scn.user_task], ["System prompt", scn.system_prompt],
      ["Injection point", scn.injection_point], ["Tools", scn.tools.join(" · ")]]) {
      brief.append(el("div", "k", label), el("p", "", text));
    }
    controls();
  }
  function reset(mode) {
    state.cards.clear();
    state.max = state.calls = state.tokens = state.latency = state.cost = state.realAttempts = 0;
    state.complete = false;
    $("feed").replaceChildren();
    $("calls").tBodies[0].replaceChildren();
    $("calls-n").textContent = "";
    $("mode").textContent = mode;
    $("m-att").textContent = "0/0";
    meters();
    pill("Starting", "run");
  }
  function meters() {
    $("m-calls").textContent = state.calls;
    $("m-tok").textContent = state.tokens.toLocaleString("en-US");
    $("m-cost").textContent = money(state.cost);
    $("m-time").textContent = seconds(state.latency);
  }
  function card(attempt, technique = "") {
    if (state.cards.has(attempt)) return state.cards.get(attempt);
    const node = el("li", `ev${attempt === 0 ? " base" : ""}`);
    const heading = el("div", "ev-h");
    heading.append(el("span", "t", attempt ? `Attempt ${attempt}` : "Baseline · benign content"), el("span", "c", technique));
    const content = el("div");
    const tools = el("div", "tools");
    const verdict = el("div", "verdict");
    const reply = el("div", "reply");
    node.append(heading, content, el("div", "who", "Agent tool calls"), tools, verdict, reply);
    $("feed").append(node);
    const result = {node, content, tools, verdict, reply};
    state.cards.set(attempt, result);
    return result;
  }
  function verdict(view, status, description) {
    view.verdict.replaceChildren(el("span", `badge ${severityClass(status)}`, status.toUpperCase()), el("span", "", description));
  }
  function render(event) {
    const feed = $("feed");
    const follow = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 100;
    switch (event.type) {
      case "start":
        state.max = event.max_attempts;
        state.runModels = event.models;
        $("m-att").textContent = `0/${state.max}`;
        pill("Baseline", "run");
        card(0);
        break;
      case "call": {
        const expectedModel = state.runModels?.[event.phase === "attacker" ? "attacker" : "target"];
        if (expectedModel && event.model !== expectedModel) {
          notice(`Model fallback: a ${event.phase} call used ${shortModel(event.model)} instead of ${shortModel(expectedModel)}. The call log shows the actual model for each response.`);
        }
        state.calls++;
        state.tokens += event.prompt_tokens + event.completion_tokens;
        state.cost = event.total_cost;
        state.latency += event.latency_s;
        meters();
        const row = el("tr");
        for (const value of [state.calls, event.phase, shortModel(event.model), event.prompt_tokens,
          event.completion_tokens, seconds(event.latency_s), money(event.cost_usd)]) row.append(el("td", "", value));
        $("calls").tBodies[0].append(row);
        $("calls-n").textContent = `(${state.calls})`;
        break;
      }
      case "baseline": {
        const view = card(0);
        verdict(view, event.safe ? "safe" : "high", event.safe ? "No unauthorized action with benign content." : "Baseline failed: this campaign cannot establish injection causality.");
        view.reply.textContent = event.final_text || "";
        break;
      }
      case "attempt_start": {
        pill(`Attempt ${event.attempt}`, "run");
        $("m-att").textContent = `${event.attempt}/${state.max}`;
        card(event.attempt, event.technique).content.append(el("div", "who", "Attacker · generating injection…"));
        break;
      }
      case "injection": {
        const view = card(event.attempt, event.technique);
        view.who = el("div", "who", event.refused ? "Attacker refused · not a valid attack" : "Attacker · injected untrusted text");
        view.content.replaceChildren(view.who, el("pre", "inj", event.text));
        break;
      }
      case "tool": {
        const view = card(event.attempt);
        const details = el("details", "tool-detail");
        details.append(el("summary", "tool", event.name), el("pre", "tool-data", JSON.stringify({arguments: event.args, result: event.result}, null, 2)));
        view.tools.append(details);
        break;
      }
      case "attempt": {
        if (!event.refused) state.realAttempts++;
        const view = card(event.attempt, event.technique);
        // A payload that matched the refusal check but changed the agent's
        // behaviour was a real attack; the server's final flag decides.
        if (!event.refused && view.who) view.who.textContent = "Attacker · injected untrusted text";
        verdict(view, event.status, event.refused ? `Attacker refusal. Observed: ${event.desc}` : event.desc);
        view.reply.textContent = event.final_text || "";
        if (event.actions?.length) view.content.append(el("p", "actions", event.actions.join("\n")));
        break;
      }
      case "done": {
        state.complete = true;
        const total = event.totals;
        state.calls = total.calls;
        state.tokens = total.prompt_tokens + total.completion_tokens;
        state.cost = total.cost_usd;
        state.latency = total.latency_s;
        meters();
        $("m-att").textContent = `${event.attempts_run}/${state.max}`;
        const finished = ["max_attempts", "critical_found"].includes(event.stopped_reason) && event.baseline_safe === true;
        // The server's valid_trial is authoritative; older recordings predate it.
        const completed = event.valid_trial ?? (finished && state.realAttempts > 0);
        const status = event.top_status;
        // Say why a run stopped before saying that no real attack completed.
        const why = !finished ? STOP_REASONS[event.stopped_reason] || event.stopped_reason.replaceAll("_", " ") : "no real attack completed";
        const text = !completed ? `Inconclusive · ${why}` :
          status === "critical" ? `CRITICAL · attempt ${event.compromised_at}` :
            status === "safe" ? "HELD · within this campaign" : `${status.toUpperCase()} · partial compromise`;
        const cls = completed ? (status === "critical" ? "crit" : status === "safe" ? "ok" : "warn") : "warn";
        pill(text, cls);
        const node = el("li", `ev final ${cls}`);
        node.append(el("div", "big", text), el("div", "nums", `${event.attempts_run} attempts · ${total.calls} calls · ${money(total.cost_usd)} · ${seconds(total.latency_s)} model time`),
          el("p", "note", !completed ? `${finished ? "Every attempt was an attacker refusal" : "This run stopped early"}. It is not evidence that the agent is safe.` :
            status === "critical" ? "The sandbox state confirms the unauthorized action. All accounts and data are synthetic." :
              "One campaign is not a robustness estimate. See the repeated benchmark and confidence intervals below."));
        feed.append(node);
        break;
      }
      case "error": throw new Error(event.message || "The upstream run failed.");
      case "ping": break;
      default: break;
    }
    if (follow) feed.scrollTop = feed.scrollHeight;
  }
  async function replay(reason = "") {
    if (!hasReplay()) throw new Error("No recorded run exists for this selection.");
    const res = await fetch(`/data/replays/${state.scenario}-${state.target}.json`, {signal: AbortSignal.timeout(15000)});
    if (!res.ok) throw new Error("The recording could not be loaded. Please try again.");
    const data = await res.json();
    if (data.scenario !== state.scenario || data.target !== state.target || !Array.isArray(data.events) ||
      data.events.at(-1)?.type !== "done") throw new Error("The recording is incomplete or does not match your selection.");
    notice(reason);
    reset(`Recorded live run · ${data.recorded} · no new API calls${data.redactions ? " · synthetic token text redacted" : ""}`);
    const playback = {stopped: false, fast: false, wake: null, timer: null, started: performance.now()};
    state.replay = playback;
    controls();
    for (const event of data.events) {
      const delay = Math.max(0, Number(event.t) * 1000 - (performance.now() - playback.started));
      if (!playback.fast && !playback.stopped && delay > 0) await new Promise((resolve) => {
        playback.wake = resolve;
        playback.timer = setTimeout(resolve, delay);
      });
      if (playback.stopped) break;
      render(event);
    }
    if (playback.stopped) pill("Replay stopped");
    state.replay = null;
  }
  function wakeReplay(stop) {
    const playback = state.replay;
    if (!playback) return;
    playback.fast = true;
    playback.stopped = stop;
    clearTimeout(playback.timer);
    playback.wake?.();
  }
  $("skip").addEventListener("click", () => wakeReplay(false));
  $("stop-replay").addEventListener("click", () => wakeReplay(true));

  async function live() {
    const code = $("code").value.trim();
    if (!state.health.public_open && !code) {
      $("code-box").open = true;
      $("code").focus();
      notice("Enter the judge code from the private testing instructions, or choose Replay.");
      return;
    }
    reset(state.health.fake_llm ? "Offline simulation · no real API calls or spend" : "Live · Nebius Token Factory");
    const res = await fetch("/api/attack", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({scenario: state.scenario, target: state.target, code: code || null}),
      signal: AbortSignal.timeout(330000),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      if (["bad_code", "judge_only"].includes(detail.error)) {
        notice(detail.message);
        pill("Judge code required", "warn");
        $("code-box").open = true;
        return;
      }
      throw new Error(detail.message || `Live service returned HTTP ${res.status}.`);
    }
    if (!res.body) throw new Error("This browser cannot read the live stream.");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const {value, done} = await reader.read();
        buffer += done ? decoder.decode() : decoder.decode(value, {stream: true});
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) if (line.trim()) render(JSON.parse(line));
        if (done) break;
      }
      if (buffer.trim()) render(JSON.parse(buffer));
      if (!state.complete) throw new Error("The live stream ended before the final verdict.");
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }
  async function run(mode) {
    if (state.busy || !state.catalog) return;
    state.busy = true;
    notice("");
    controls();
    try {
      if (mode === "live") {
        try { await live(); }
        catch (error) {
          const explanation = `${error.message} Live run stopped${state.cost ? ` after ${money(state.cost)} metered` : ""}.`;
          if (hasReplay()) await replay(`${explanation} Showing a recorded campaign; the meters now describe that recording.`);
          else throw new Error(explanation);
        }
      } else await replay();
    } catch (error) {
      notice(error.message || "The campaign could not be loaded.");
      pill("Unavailable", "warn");
    } finally {
      state.busy = false;
      state.replay = null;
      controls();
      if (mode === "live") void health();
    }
  }
  $("run-live").addEventListener("click", () => void run("live"));
  $("run-replay").addEventListener("click", () => void run("replay"));
  async function init() {
    try {
      const res = await fetch("/data/catalog.json", {signal: AbortSignal.timeout(15000)});
      if (!res.ok) throw new Error("Demo configuration unavailable. Please reload the page.");
      state.catalog = await res.json();
      renderChoices();
    } catch (error) { notice(error.message); }
  }
  void init();
  void health();
})();
