let selectedClientId = null;
let displayedSessionId = null;
let refreshMs = 1000;
let lastClients = [];
let lastRenderableSessions = [];
let openDropdownKey = null;
let inactiveHistoryVisible = false;
let lastHadActiveClients = false;
let activeDisplaySuppressed = false;

const DEFAULT_TITLE = "Gonzales Lab Behavior Training";
const DEFAULT_SUBTITLE = "--";
const MAX_RECENT_TRIALS = 10;
const VIEW_RECENT = "recent";
const VIEW_ALL = "all";
const SVG_NS = "http://www.w3.org/2000/svg";
const DROPDOWN_KEYS = ["animal", "phase", "date"];

const plotViewModes = new Map();

const DROPDOWN_CONFIG = {
  animal: { buttonId: "session-animal-arrow", menuId: "session-animal-menu", ariaLabel: "Select animal" },
  phase: { buttonId: "session-phase-arrow", menuId: "session-phase-menu", ariaLabel: "Select phase" },
  date: { buttonId: "session-date-arrow", menuId: "session-date-menu", ariaLabel: "Select date" },
};

const PLOT_DEFS = [
  {
    svgId: "plot-outcome",
    modeId: "plot-mode-outcome",
    yLabel: "Outcome",
    color: "#31ff7a",
    showYTicks: false,
    includeZero: true,
    useZeroBaseline: true,
    drawBars: true,
    getValue: (trial) => trial.outcomeValue,
  },
  {
    svgId: "plot-duration",
    modeId: "plot-mode-duration",
    yLabel: "Duration (s)",
    color: "#28d7ff",
    showYTicks: true,
    includeZero: false,
    useZeroBaseline: false,
    drawBars: false,
    getValue: (trial) => trial.durationSeconds,
  },
  {
    svgId: "plot-rate",
    modeId: "plot-mode-rate",
    yLabel: "Success Rate",
    color: "#ff9f1a",
    showYTicks: true,
    includeZero: false,
    useZeroBaseline: false,
    drawBars: false,
    getValue: (trial) => trial.ratePercent,
  },
];

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = value;
  }
}

function getById(...ids) {
  for (const id of ids) {
    const el = document.getElementById(id);
    if (el) {
      return el;
    }
  }

  return null;
}

function parseTimestamp(value) {
  if (!value) {
    return null;
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) {
    return null;
  }

  return parsed;
}

function parseSessionDate(value) {
  const text = String(value ?? "").trim();
  if (!text) {
    return null;
  }

  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    const parsed = new Date(`${text}T00:00:00`);
    return Number.isNaN(parsed.valueOf()) ? null : parsed;
  }

  const slashMatch = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (slashMatch) {
    const month = Number.parseInt(slashMatch[1], 10) - 1;
    const day = Number.parseInt(slashMatch[2], 10);
    const year = Number.parseInt(slashMatch[3], 10);
    const parsed = new Date(year, month, day);
    return Number.isNaN(parsed.valueOf()) ? null : parsed;
  }

  return parseTimestamp(text);
}

function formatClockTime(value) {
  const parsed = parseTimestamp(value);
  if (!parsed) {
    return "--";
  }

  return parsed.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatCompactDate(value, fallbackTimestamp = null) {
  const parsed = parseSessionDate(value) ?? parseTimestamp(fallbackTimestamp);
  if (!parsed || Number.isNaN(parsed.valueOf())) {
    return "--";
  }

  return `${parsed.getMonth() + 1}-${parsed.getDate()}-${parsed.getFullYear()}`;
}

function formatDuration(totalSeconds) {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) {
    return "--";
  }

  const roundedSeconds = Math.floor(totalSeconds);
  const hours = Math.floor(roundedSeconds / 3600);
  const minutes = Math.floor((roundedSeconds % 3600) / 60);
  const seconds = roundedSeconds % 60;

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function shouldRenderClientTab(client) {
  return Boolean(client?.session_active || client?.published_at);
}

function compareSessions(a, b) {
  const activeDelta = Number(Boolean(b?.session_active)) - Number(Boolean(a?.session_active));
  if (activeDelta !== 0) {
    return activeDelta;
  }

  const publishedDelta = (parseTimestamp(b?.published_at)?.valueOf() || 0) - (parseTimestamp(a?.published_at)?.valueOf() || 0);
  if (publishedDelta !== 0) {
    return publishedDelta;
  }

  return String(b?.session_id || "").localeCompare(String(a?.session_id || ""));
}

function buildSessionRecordFromClient(client) {
  const session = { ...(client?.session ?? {}) };
  const sessionId = String(session.session_id || "").trim();
  if (!sessionId) {
    return null;
  }

  return {
    session_id: sessionId,
    client_id: String(client?.client_id || "").trim(),
    client_label: String(client?.label || client?.client_id || "").trim(),
    session_active: Boolean(client?.session_active),
    started: Boolean(client?.started),
    note: String(client?.note || ""),
    published_at: client?.published_at || null,
    session,
    trial_display: client?.trial_display ?? null,
  };
}

function mergeSessionRecords(existing, incoming) {
  if (!existing) {
    return { ...incoming };
  }

  return {
    ...existing,
    ...incoming,
    session_active: Boolean(incoming?.session_active || existing?.session_active),
    started: Boolean(incoming?.started || existing?.started),
    client_label: String(incoming?.client_label || existing?.client_label || incoming?.client_id || existing?.client_id || ""),
    note: String(incoming?.note || existing?.note || ""),
    published_at: incoming?.published_at || existing?.published_at || null,
    session: {
      ...(existing?.session ?? {}),
      ...(incoming?.session ?? {}),
    },
    trial_display: incoming?.trial_display ?? existing?.trial_display ?? null,
  };
}

function normalizeSessions(clients, sessions) {
  const byId = new Map();

  for (const item of sessions ?? []) {
    const sessionId = String(item?.session_id || item?.session?.session_id || "").trim();
    if (!sessionId) {
      continue;
    }

    const normalized = {
      session_id: sessionId,
      client_id: String(item?.client_id || "").trim(),
      client_label: String(item?.client_label || item?.client_id || "").trim(),
      session_active: Boolean(item?.session_active),
      started: Boolean(item?.started),
      note: String(item?.note || ""),
      published_at: item?.published_at || null,
      session: { ...(item?.session ?? {}), session_id: sessionId },
      trial_display: item?.trial_display ?? null,
    };
    byId.set(sessionId, mergeSessionRecords(byId.get(sessionId), normalized));
  }

  for (const client of clients ?? []) {
    const record = buildSessionRecordFromClient(client);
    if (!record) {
      continue;
    }
    byId.set(record.session_id, mergeSessionRecords(byId.get(record.session_id), record));
  }

  return Array.from(byId.values()).sort(compareSessions);
}

function syncSelectedClient(clients) {
  const activeClients = clients.filter((client) => client.session_active);
  const selectedClient = activeClients.find((client) => client.client_id === selectedClientId) ?? null;
  if (selectedClient) {
    return selectedClient;
  }

  if (!activeClients.length) {
    selectedClientId = null;
    return null;
  }

  selectedClientId = activeClients[0].client_id;
  return activeClients[0];
}

function getLastActiveSession(clients) {
  const disconnected = clients
    .filter((client) => !client.session_active && client.published_at)
    .map((client) => ({ client, publishedAt: parseTimestamp(client.published_at) }))
    .filter((item) => item.publishedAt);

  if (disconnected.length > 0) {
    disconnected.sort((a, b) => b.publishedAt - a.publishedAt);
    return disconnected[0].client;
  }

  const activeOrRecent = clients
    .filter((client) => client.published_at)
    .map((client) => ({ client, publishedAt: parseTimestamp(client.published_at) }))
    .filter((item) => item.publishedAt);

  if (activeOrRecent.length > 0) {
    activeOrRecent.sort((a, b) => b.publishedAt - a.publishedAt);
    return activeOrRecent[0].client;
  }

  return null;
}

function renderHeroStatus(clients) {
  const lastActiveClient = getLastActiveSession(clients);
  if (lastActiveClient?.published_at) {
    const dateText = formatCompactDate(lastActiveClient.session?.date, lastActiveClient.published_at);
    const timeText = formatClockTime(lastActiveClient.published_at);
    setText("site-subtitle", `${dateText}   ${timeText}`);
  } else {
    setText("site-subtitle", DEFAULT_SUBTITLE);
  }
}

function getCurrentSessionForClient(clients, sessions, clientId) {
  const client = (clients ?? []).find((item) => item.client_id === clientId && item.session_active);
  const sessionId = String(client?.session?.session_id || "").trim();
  if (!sessionId) {
    return null;
  }

  return sessions.find((item) => item.session_id === sessionId) ?? buildSessionRecordFromClient(client);
}

function getDisplayedSession(clients, sessions) {
  const existing = sessions.find((item) => item.session_id === displayedSessionId) ?? null;
  if (existing) {
    return existing;
  }

  const selectedClient = syncSelectedClient(clients);
  if (!selectedClient) {
    displayedSessionId = null;
    return null;
  }

  if (activeDisplaySuppressed) {
    displayedSessionId = null;
    return null;
  }

  const currentSession = getCurrentSessionForClient(clients, sessions, selectedClient.client_id);
  if (currentSession) {
    displayedSessionId = currentSession.session_id;
    return currentSession;
  }

  displayedSessionId = sessions[0]?.session_id ?? null;
  return sessions[0] ?? null;
}

function getSelectionSession(clients, sessions) {
  return getDisplayedSession(clients, sessions) ?? sessions[0] ?? null;
}

function getActiveSessionForClient(clients, sessions, clientId) {
  return getCurrentSessionForClient(clients, sessions, clientId);
}

function extractNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  const match = String(value ?? "").match(/-?\d+(?:\.\d+)?/);
  if (!match) {
    return null;
  }

  const parsed = Number.parseFloat(match[0]);
  return Number.isFinite(parsed) ? parsed : null;
}

function getTrialRows(trial) {
  if (Array.isArray(trial?.rows) && trial.rows.length > 0) {
    return trial.rows;
  }

  if (trial?.columns) {
    return [trial.columns];
  }

  return [];
}

function parseTrialMetrics(trial) {
  return getTrialRows(trial)
    .map((row, index) => {
      const successCell = String(row?.SUCCESS ?? "").trim();
      const failureCell = String(row?.FAILURE ?? "").trim();
      const trialNumber = extractNumber(row?.TRIAL) ?? (index + 1);
      const durationSeconds = extractNumber(row?.ELAPSED);
      const ratePercent = extractNumber(row?.RATE);

      let outcomeValue = null;
      if (successCell) {
        outcomeValue = 1;
      } else if (failureCell) {
        outcomeValue = -1;
      }

      if (
        !Number.isFinite(trialNumber)
        || !Number.isFinite(durationSeconds)
        || !Number.isFinite(ratePercent)
        || !Number.isFinite(outcomeValue)
      ) {
        return null;
      }

      return {
        trialNumber,
        durationSeconds,
        ratePercent,
        outcomeValue,
      };
    })
    .filter(Boolean);
}

function getPlotViewMode(sessionId) {
  if (!sessionId) {
    return VIEW_RECENT;
  }

  const current = plotViewModes.get(sessionId);
  if (current === VIEW_ALL || current === VIEW_RECENT) {
    return current;
  }

  plotViewModes.set(sessionId, VIEW_RECENT);
  return VIEW_RECENT;
}

function formatPlotMode(sessionId, totalTrials) {
  const mode = getPlotViewMode(sessionId);
  if (mode === VIEW_ALL) {
    return totalTrials > 0 ? `All ${totalTrials} Trials` : "All Trials";
  }

  const recentCount = Math.min(MAX_RECENT_TRIALS, totalTrials || MAX_RECENT_TRIALS);
  return `Last ${recentCount} Trials`;
}

function getVisibleTrials(sessionRecord) {
  const allTrials = parseTrialMetrics(sessionRecord?.trial_display);
  const mode = getPlotViewMode(sessionRecord?.session_id);

  return {
    allTrials,
    visibleTrials: mode === VIEW_ALL ? allTrials : allTrials.slice(-MAX_RECENT_TRIALS),
  };
}

function togglePlotView(sessionId) {
  if (!sessionId) {
    return;
  }

  const current = getPlotViewMode(sessionId);
  plotViewModes.set(sessionId, current === VIEW_ALL ? VIEW_RECENT : VIEW_ALL);
  renderPanel(lastClients, lastRenderableSessions);
}

function createSvgElement(tagName, attrs = {}) {
  const element = document.createElementNS(SVG_NS, tagName);
  Object.entries(attrs).forEach(([key, value]) => {
    element.setAttribute(key, String(value));
  });
  return element;
}

function clearPlot(svg) {
  svg.replaceChildren();
  svg.removeAttribute("viewBox");
}

function getPlotDimensions(svg) {
  const bounds = svg.getBoundingClientRect();
  return {
    width: Math.max(260, Math.round(bounds.width) || 360),
    height: Math.max(220, Math.round(bounds.height) || 320),
  };
}

function getNiceStep(range, targetTickCount = 5) {
  const safeRange = Math.max(range, 1e-6);
  const roughStep = safeRange / Math.max(1, targetTickCount - 1);
  const exponent = Math.floor(Math.log10(roughStep));
  const base = 10 ** exponent;
  const fraction = roughStep / base;

  let niceFraction = 10;
  if (fraction <= 1) {
    niceFraction = 1;
  } else if (fraction <= 2) {
    niceFraction = 2;
  } else if (fraction <= 5) {
    niceFraction = 5;
  }

  return niceFraction * base;
}

function buildYAxis(values, { includeZero = false } = {}) {
  let minValue = Math.min(...values);
  let maxValue = Math.max(...values);

  if (includeZero) {
    minValue = Math.min(minValue, 0);
    maxValue = Math.max(maxValue, 0);
  }

  if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) {
    minValue = 0;
    maxValue = 1;
  }

  if (minValue === maxValue) {
    const spread = Math.max(Math.abs(minValue) * 0.25, 0.5);
    minValue -= spread;
    maxValue += spread;
  } else {
    const padding = (maxValue - minValue) * 0.12;
    minValue -= padding;
    maxValue += padding;
  }

  if (includeZero) {
    minValue = Math.min(minValue, 0);
    maxValue = Math.max(maxValue, 0);
  }

  const step = getNiceStep(maxValue - minValue);
  let niceMin = Math.floor(minValue / step) * step;
  let niceMax = Math.ceil(maxValue / step) * step;

  if (includeZero) {
    niceMin = Math.min(niceMin, 0);
    niceMax = Math.max(niceMax, 0);
  }

  const ticks = [];
  for (let tick = niceMin; tick <= (niceMax + (step * 0.5)); tick += step) {
    ticks.push(Number(tick.toFixed(6)));
  }

  return {
    min: niceMin,
    max: niceMax,
    step,
    ticks,
  };
}

function formatAxisTick(value, step) {
  const absStep = Math.abs(step);
  const decimals = absStep >= 10 ? 0 : absStep >= 1 ? 1 : Math.min(3, Math.max(1, Math.ceil(-Math.log10(absStep)) + 1));

  return Number(value.toFixed(decimals)).toString();
}

function buildXTicks(points, maxTicks = 5) {
  if (points.length <= maxTicks) {
    return points.map((point, index) => ({ index, label: point.trialNumber }));
  }

  const ticks = [];
  const seen = new Set();

  for (let slot = 0; slot < maxTicks; slot += 1) {
    const index = Math.round((slot * (points.length - 1)) / (maxTicks - 1));
    if (seen.has(index)) {
      continue;
    }

    seen.add(index);
    ticks.push({ index, label: points[index].trialNumber });
  }

  return ticks;
}

function renderPlot(svg, plotDef, trials) {
  if (!svg) {
    return;
  }

  if (!trials.length) {
    clearPlot(svg);
    return;
  }

  const { width, height } = getPlotDimensions(svg);
  const marginLeft = plotDef.showYTicks ? 70 : 50;
  const marginRight = 16;
  const marginTop = 18;
  const marginBottom = 38;
  const plotLeft = marginLeft;
  const plotRight = width - marginRight;
  const plotTop = marginTop;
  const plotBottom = height - marginBottom;
  const plotWidth = Math.max(16, plotRight - plotLeft);
  const plotHeight = Math.max(16, plotBottom - plotTop);

  const points = trials.map((trial, index) => ({
    index,
    trialNumber: trial.trialNumber,
    value: plotDef.getValue(trial),
  }));

  const yAxis = buildYAxis(points.map((point) => point.value), { includeZero: plotDef.includeZero });
  const yToPx = (value) => plotBottom - (((value - yAxis.min) / (yAxis.max - yAxis.min)) * plotHeight);
  const xToPx = (index) => {
    if (points.length === 1) {
      return plotLeft + (plotWidth / 2);
    }
    return plotLeft + (((index + 0.5) / points.length) * plotWidth);
  };

  svg.replaceChildren();
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "none");

  const rootBackground = createSvgElement("rect", {
    x: 0,
    y: 0,
    width,
    height,
    fill: "transparent",
  });
  const plotBackground = createSvgElement("rect", {
    x: plotLeft,
    y: plotTop,
    width: plotWidth,
    height: plotHeight,
    rx: 8,
    fill: "#000000",
  });

  svg.append(rootBackground, plotBackground);

  yAxis.ticks.forEach((tick) => {
    const y = yToPx(tick);
    const gridLine = createSvgElement("line", {
      x1: plotLeft,
      y1: y,
      x2: plotRight,
      y2: y,
      stroke: "rgba(255,255,255,0.14)",
      "stroke-width": 1,
    });
    svg.appendChild(gridLine);

    if (plotDef.showYTicks) {
      const tickLabel = createSvgElement("text", {
        x: plotLeft - 8,
        y: y + 4,
        fill: "#ffffff",
        "font-size": 11,
        "text-anchor": "end",
      });
      tickLabel.textContent = formatAxisTick(tick, yAxis.step);
      svg.appendChild(tickLabel);
    }
  });

  const xTicks = buildXTicks(points);
  xTicks.forEach((tick) => {
    const x = xToPx(tick.index);
    const tickMark = createSvgElement("line", {
      x1: x,
      y1: plotBottom,
      x2: x,
      y2: plotBottom + 5,
      stroke: "#ffffff",
      "stroke-width": 1,
    });
    const tickLabel = createSvgElement("text", {
      x,
      y: plotBottom + 18,
      fill: "#ffffff",
      "font-size": 11,
      "text-anchor": "middle",
    });
    tickLabel.textContent = String(tick.label);
    svg.append(tickMark, tickLabel);
  });

  const zeroY = yToPx(0);
  const xAxisY = plotDef.useZeroBaseline ? zeroY : plotBottom;
  const xAxis = createSvgElement("line", {
    x1: plotLeft,
    y1: xAxisY,
    x2: plotRight,
    y2: xAxisY,
    stroke: "#ffffff",
    "stroke-width": 1.25,
  });
  const yAxisLine = createSvgElement("line", {
    x1: plotLeft,
    y1: plotTop,
    x2: plotLeft,
    y2: plotBottom,
    stroke: "#ffffff",
    "stroke-width": 1.25,
  });

  svg.append(xAxis, yAxisLine);

  if (plotDef.drawBars) {
    const barWidth = Math.min(26, plotWidth / Math.max(points.length, 1) * 0.66);
    points.forEach((point) => {
      const x = xToPx(point.index);
      const y = yToPx(point.value);
      const rect = createSvgElement("rect", {
        x: x - (barWidth / 2),
        y: Math.min(y, zeroY),
        width: Math.max(2, barWidth),
        height: Math.max(1, Math.abs(zeroY - y)),
        rx: 2,
        fill: point.value >= 0 ? "#31ff7a" : "#ff4343",
      });
      svg.appendChild(rect);
    });
  } else {
    const polyline = createSvgElement("polyline", {
      fill: "none",
      stroke: plotDef.color,
      "stroke-width": 2.5,
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
      points: points.map((point) => `${xToPx(point.index)},${yToPx(point.value)}`).join(" "),
    });
    svg.appendChild(polyline);

    points.forEach((point) => {
      const circle = createSvgElement("circle", {
        cx: xToPx(point.index),
        cy: yToPx(point.value),
        r: 4.4,
        fill: plotDef.color,
      });
      svg.appendChild(circle);
    });
  }

  const yLabel = createSvgElement("text", {
    x: 18,
    y: plotTop + (plotHeight / 2),
    fill: "#ffffff",
    "font-size": 12,
    "font-weight": 600,
    "text-anchor": "middle",
    transform: `rotate(-90 18 ${plotTop + (plotHeight / 2)})`,
  });
  yLabel.textContent = plotDef.yLabel;
  svg.appendChild(yLabel);
}

function renderTrialPlots(sessionRecord) {
  const placeholder = getById("table-placeholder", "empty-state");
  const { allTrials, visibleTrials } = getVisibleTrials(sessionRecord);
  const modeText = formatPlotMode(sessionRecord?.session_id, allTrials.length);
  const interactive = Boolean(sessionRecord?.session_id && allTrials.length > 0);

  if (placeholder) {
    placeholder.hidden = visibleTrials.length > 0 || !sessionRecord;
  }

  PLOT_DEFS.forEach((plotDef) => {
    const svg = document.getElementById(plotDef.svgId);
    const modeEl = document.getElementById(plotDef.modeId);
    const panel = svg?.closest(".plot-panel");

    if (modeEl) {
      modeEl.textContent = modeText;
    }

    if (panel) {
      panel.style.cursor = interactive ? "pointer" : "default";
    }

    if (svg) {
      svg.style.cursor = interactive ? "pointer" : "default";
      svg.onclick = interactive ? () => togglePlotView(sessionRecord.session_id) : null;
      renderPlot(svg, plotDef, visibleTrials);
    }
  });
}

function closeAllDropdowns() {
  openDropdownKey = null;
  renderDropdowns(lastRenderableSessions, getSelectionSession(lastClients, lastRenderableSessions));
}

function getSessionsByAnimal(sessions, animalId) {
  return sessions.filter((sessionRecord) => String(sessionRecord?.session?.animal_id || "") === String(animalId || ""));
}

function getSessionsByAnimalPhase(sessions, animalId, phaseId) {
  return sessions.filter(
    (sessionRecord) => (
      String(sessionRecord?.session?.animal_id || "") === String(animalId || "")
      && String(sessionRecord?.session?.phase_id || "") === String(phaseId || "")
    ),
  );
}

function buildAnimalOptions(sessions, displayedSession) {
  const seen = new Set();
  const selectedAnimal = String(displayedSession?.session?.animal_id || "");

  return sessions
    .filter((sessionRecord) => String(sessionRecord?.session?.animal_id || "").trim())
    .filter((sessionRecord) => {
      const animalId = String(sessionRecord.session.animal_id);
      if (seen.has(animalId)) {
        return false;
      }
      seen.add(animalId);
      return true;
    })
    .map((sessionRecord) => ({
      id: sessionRecord.session.animal_id,
      label: sessionRecord.session.animal_id,
      selected: sessionRecord.session.animal_id === selectedAnimal,
      sessionId: sessionRecord.session_id,
    }));
}

function buildPhaseOptions(sessions, displayedSession) {
  const animalId = String(displayedSession?.session?.animal_id || "");
  const seen = new Set();
  const selectedPhase = String(displayedSession?.session?.phase_id || "");

  return getSessionsByAnimal(sessions, animalId)
    .filter((sessionRecord) => String(sessionRecord?.session?.phase_id || "").trim())
    .filter((sessionRecord) => {
      const phaseId = String(sessionRecord.session.phase_id);
      if (seen.has(phaseId)) {
        return false;
      }
      seen.add(phaseId);
      return true;
    })
    .map((sessionRecord) => ({
      id: sessionRecord.session.phase_id,
      label: sessionRecord.session.phase_id,
      selected: sessionRecord.session.phase_id === selectedPhase,
      sessionId: sessionRecord.session_id,
    }));
}

function buildDateOptions(sessions, displayedSession) {
  const animalId = String(displayedSession?.session?.animal_id || "");
  const phaseId = String(displayedSession?.session?.phase_id || "");
  const filtered = getSessionsByAnimalPhase(sessions, animalId, phaseId);
  const selectedSessionId = String(displayedSession?.session_id || "");
  const counts = new Map();

  filtered.forEach((sessionRecord) => {
    const baseLabel = formatCompactDate(sessionRecord?.session?.date, sessionRecord?.published_at);
    counts.set(baseLabel, (counts.get(baseLabel) || 0) + 1);
  });

  return filtered.map((sessionRecord) => {
    const baseLabel = formatCompactDate(sessionRecord?.session?.date, sessionRecord?.published_at);
    const duplicateCount = counts.get(baseLabel) || 0;
    const timeText = formatClockTime(sessionRecord?.published_at);
    const clientText = String(sessionRecord?.client_label || sessionRecord?.client_id || "").trim();
    let label = baseLabel;

    if (duplicateCount > 1) {
      label = `${baseLabel} | ${timeText} | ${clientText}`.trim();
    }

    return {
      id: sessionRecord.session_id,
      label,
      selected: sessionRecord.session_id === selectedSessionId,
      sessionId: sessionRecord.session_id,
    };
  });
}

function getDropdownOptions(key, sessions, displayedSession) {
  switch (key) {
    case "animal":
      return buildAnimalOptions(sessions, displayedSession);
    case "phase":
      return buildPhaseOptions(sessions, displayedSession);
    case "date":
      return buildDateOptions(sessions, displayedSession);
    default:
      return [];
  }
}

function selectDropdownOption(option) {
  if (!option?.sessionId) {
    return;
  }

  displayedSessionId = option.sessionId;
  activeDisplaySuppressed = false;
  if (!lastClients.some((client) => client.session_active)) {
    inactiveHistoryVisible = true;
  }
  closeAllDropdowns();
  renderTabs(lastClients, lastRenderableSessions);
  renderPanel(lastClients, lastRenderableSessions);
}

function renderDropdownMenu(key, options) {
  const config = DROPDOWN_CONFIG[key];
  const button = document.getElementById(config.buttonId);
  const menu = document.getElementById(config.menuId);

  if (!button || !menu) {
    return;
  }

  const disabled = options.length <= 1;
  button.disabled = disabled;
  button.setAttribute("aria-label", config.ariaLabel);
  button.setAttribute("aria-expanded", openDropdownKey === key && !disabled ? "true" : "false");

  if (openDropdownKey !== key || disabled) {
    menu.hidden = true;
    menu.replaceChildren();
    return;
  }

  menu.hidden = false;
  menu.replaceChildren();

  options.forEach((option) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "session-dropdown-option";
    if (option.selected) {
      item.classList.add("selected");
    }
    item.setAttribute("role", "option");
    item.setAttribute("aria-selected", option.selected ? "true" : "false");
    item.textContent = option.label;
    item.addEventListener("click", (event) => {
      event.stopPropagation();
      selectDropdownOption(option);
    });
    menu.appendChild(item);
  });
}

function renderDropdowns(sessions, displayedSession) {
  DROPDOWN_KEYS.forEach((key) => {
    renderDropdownMenu(key, getDropdownOptions(key, sessions, displayedSession));
  });
}

function toggleDropdown(key) {
  const options = getDropdownOptions(key, lastRenderableSessions, getSelectionSession(lastClients, lastRenderableSessions));
  if (options.length <= 1) {
    openDropdownKey = null;
  } else {
    openDropdownKey = openDropdownKey === key ? null : key;
  }
  renderDropdowns(lastRenderableSessions, getSelectionSession(lastClients, lastRenderableSessions));
}

function attachDropdownHandlers() {
  DROPDOWN_KEYS.forEach((key) => {
    const config = DROPDOWN_CONFIG[key];
    const button = document.getElementById(config.buttonId);
    if (!button) {
      return;
    }

    button.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleDropdown(key);
    });
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".session-feature")) {
      closeAllDropdowns();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && openDropdownKey !== null) {
      closeAllDropdowns();
    }
  });
}

function renderTabs(clients, sessions) {
  const list = document.getElementById("tab-list");
  if (!list) {
    return;
  }

  list.innerHTML = "";
  const visibleClients = clients.filter((client) => shouldRenderClientTab(client));
  syncSelectedClient(clients);
  const displayedSession = getDisplayedSession(clients, sessions);

  visibleClients.forEach((client) => {
    const button = document.createElement("button");
    button.className = "tab";
    button.type = "button";
    button.role = "tab";
    button.textContent = client.label;
    const activeSession = getActiveSessionForClient(clients, sessions, client.client_id);
    const isDisplayedActiveSession = Boolean(
      client.session_active
      && activeSession
      && displayedSession
      && activeSession.session_id === displayedSession.session_id,
    );

    button.setAttribute("aria-selected", isDisplayedActiveSession ? "true" : "false");
    button.setAttribute("aria-disabled", client.session_active ? "false" : "true");
    button.classList.add(client.session_active ? "connected" : "disconnected");

    if (isDisplayedActiveSession) {
      button.classList.add("selected");
    }

    button.addEventListener("click", () => {
      if (!client.session_active) {
        return;
      }

      if (isDisplayedActiveSession) {
        displayedSessionId = null;
        activeDisplaySuppressed = true;
        inactiveHistoryVisible = false;
        openDropdownKey = null;
        renderTabs(clients, sessions);
        renderPanel(clients, sessions);
        return;
      }

      selectedClientId = client.client_id;
      displayedSessionId = activeSession?.session_id ?? null;
      activeDisplaySuppressed = false;
      inactiveHistoryVisible = false;
      openDropdownKey = null;
      renderTabs(clients, sessions);
      renderPanel(clients, sessions);
    });

    list.appendChild(button);
  });
}

function renderSessionMeta(sessionRecord, sessions) {
  const session = sessionRecord?.session ?? {};
  const clientFeature = document.getElementById("session-client-feature");
  const showClient = Boolean(sessionRecord && !sessionRecord.session_active);

  setText("session-animal", session.animal_id || "-");
  setText("session-phase", session.phase_id || "-");
  setText("session-date", formatCompactDate(session.date, sessionRecord?.published_at));
  setText("session-time-elapsed", formatDuration(Number(session.duration_sec)));
  setText("session-client", showClient ? (sessionRecord?.client_label || sessionRecord?.client_id || "-") : "-");

  if (clientFeature) {
    clientFeature.hidden = !showClient;
  }

  renderDropdowns(sessions, sessionRecord);
}

function resetSessionMeta() {
  setText("session-animal", "--");
  setText("session-phase", "--");
  setText("session-date", "--");
  setText("session-time-elapsed", "--");
  setText("session-client", "-");

  const clientFeature = document.getElementById("session-client-feature");
  if (clientFeature) {
    clientFeature.hidden = true;
  }

  DROPDOWN_KEYS.forEach((key) => {
    const config = DROPDOWN_CONFIG[key];
    const button = document.getElementById(config.buttonId);
    const menu = document.getElementById(config.menuId);
    if (button) {
      button.disabled = true;
      button.setAttribute("aria-expanded", "false");
    }
    if (menu) {
      menu.hidden = true;
      menu.replaceChildren();
    }
  });
}

function showPanelMessage(message) {
  const panelEmptyState = getById("panel-empty-state", "empty-state");
  const sessionView = document.getElementById("session-view");

  if (panelEmptyState) {
    panelEmptyState.textContent = message;
    panelEmptyState.hidden = false;
  }

  if (sessionView) {
    sessionView.hidden = true;
  }
}

function renderPanel(clients, sessions) {
  const activeClients = clients.filter((client) => client.session_active);
  const displayedSession = getDisplayedSession(clients, sessions);
  const selectionSession = getSelectionSession(clients, sessions);

  renderHeroStatus(clients);

  if (activeClients.length === 0) {
    activeDisplaySuppressed = false;
    if (!selectionSession) {
      openDropdownKey = null;
      renderTrialPlots(null);
      resetSessionMeta();
      showPanelMessage("No active sessions");
      return;
    }

    renderSessionMeta(selectionSession, sessions);

    if (!inactiveHistoryVisible || !displayedSession) {
      renderTrialPlots(null);
      showPanelMessage("No active sessions");
      return;
    }

    const panelEmptyState = getById("panel-empty-state", "empty-state");
    const sessionView = document.getElementById("session-view");

    if (panelEmptyState) {
      panelEmptyState.hidden = true;
    }
    if (sessionView) {
      sessionView.hidden = false;
    }

    renderTrialPlots(displayedSession);
    return;
  }

  inactiveHistoryVisible = false;

  if (!displayedSession) {
    renderTrialPlots(null);
    if (selectionSession) {
      renderSessionMeta(selectionSession, sessions);
    } else {
      resetSessionMeta();
    }
    showPanelMessage("Select an active client");
    return;
  }

  const panelEmptyState = getById("panel-empty-state", "empty-state");
  const sessionView = document.getElementById("session-view");

  if (panelEmptyState) {
    panelEmptyState.hidden = true;
  }
  if (sessionView) {
    sessionView.hidden = false;
  }

  renderSessionMeta(displayedSession, sessions);
  renderTrialPlots(displayedSession);
}

async function refreshStatus() {
  try {
    const payload = await fetchJson("/api/status");
    const clients = payload.clients ?? [];
    const sessions = normalizeSessions(clients, payload.sessions ?? []);
    const hasActiveClients = clients.some((client) => client.session_active);

    if (hasActiveClients && !lastHadActiveClients) {
      displayedSessionId = null;
      inactiveHistoryVisible = false;
      activeDisplaySuppressed = false;
    } else if (!hasActiveClients && lastHadActiveClients) {
      inactiveHistoryVisible = false;
      activeDisplaySuppressed = false;
    }

    lastHadActiveClients = hasActiveClients;

    lastClients = clients;
    lastRenderableSessions = sessions;

    renderTabs(clients, sessions);
    renderPanel(clients, sessions);
  } catch (error) {
    openDropdownKey = null;
    showPanelMessage("Unable to load session status");
  }
}

async function bootstrap() {
  try {
    const payload = await fetchJson("/api/bootstrap");
    const ui = payload.ui ?? {};

    setText("site-title", ui.site_title || DEFAULT_TITLE);
    setText("site-subtitle", DEFAULT_SUBTITLE);
    document.title = ui.site_title || DEFAULT_TITLE;
    refreshMs = Math.max(250, Number(ui.refresh_ms || 1000));
  } catch (error) {
    showPanelMessage("Unable to load session settings");
    setText("site-title", DEFAULT_TITLE);
    setText("site-subtitle", DEFAULT_SUBTITLE);
    document.title = DEFAULT_TITLE;
  }

  attachDropdownHandlers();

  window.addEventListener("resize", () => {
    renderPanel(lastClients, lastRenderableSessions);
  });

  await refreshStatus();
  window.setInterval(refreshStatus, refreshMs);
}

bootstrap();
