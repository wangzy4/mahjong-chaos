let socket = null;
let latestState = null;
let selectedTile = null;
let chiMode = false;
let chiSelectedTiles = [];
let selectedSkillIds = [];
let activeManualTab = "operate";
let manualOpen = false;
let reconnectTimer = null;
let currentParamTemplateSkillId = null;
let lastPrivateResultCount = 0;

const $ = (id) => document.getElementById(id);

const STORAGE_KEYS = {
  playerId: "mahjong_chaos_player_id",
  playerName: "mahjong_chaos_player_name",
  roomId: "mahjong_chaos_room_id",
};

const SKILL_INFO = {
  mirror_reflection: {
    name: "镜像反射",
    type: "被动",
    limit: "每局 1 次，自动触发",
    effect: "别人对你使用目标型主动技能时，取消该技能，并把效果反射给对方。",
    usage: "不用手动使用。可反射偷窥、偷天换日、偷暗杠。",
    params: "",
  },
  desperate_gamble: {
    name: "破釜沉舟",
    type: "主动",
    limit: "每局 1 次",
    effect: "发动后，本局你胡牌时胡牌分数 x4；如果本局没胡，结束时额外 -24，其他玩家平分。",
    usage: "自己回合使用，不需要参数。",
    params: "{}",
  },
  close_enough: {
    name: "差不多就行",
    type: "被动",
    limit: "每局最多触发 1 次",
    effect: "胡牌时如果没有命中高价值番型，但差一点清一色、碰碰胡或门前清，胡牌分数 x2。",
    usage: "不用手动使用，胡牌结算时自动判断。",
    params: "",
  },
  astrology: {
    name: "观星",
    type: "主动信息",
    limit: "四巡一次",
    effect: "查看牌墙顶 4 张牌，不改变牌墙顺序。",
    usage: "自己回合使用，不需要参数。结果只显示给自己。",
    params: "{}",
  },
  peek_neighbor: {
    name: "偷窥",
    type: "主动目标",
    limit: "四巡一次",
    effect: "查看上家或下家的随机两张手牌。",
    usage: "自己回合使用。文本框已填好模板，只需要把 target_direction 改成 prev 或 next。",
    params: '{"target_direction":"prev"}',
  },
  swap_with_neighbor: {
    name: "偷天换日",
    type: "主动目标",
    limit: "每局 2 次",
    effect: "你指定给出一张牌，随机获得上家或下家的一张牌。",
    usage: "自己回合使用。文本框已填好模板，只需要改方向和你要交出去的牌名。",
    params: '{"target_direction":"next","give_tile":"3万"}',
  },
  killing_intent_sense: {
    name: "杀意感知",
    type: "被动防御",
    limit: "每局 1 次，自动触发",
    effect: "第一次即将点炮时提醒你，可确认打出或撤回重选。",
    usage: "不用手动使用。触发后按页面提示确认或取消。",
    params: "",
  },
  change_suit: {
    name: "换色",
    type: "主动改牌",
    limit: "四巡一次",
    effect: "把一张牌换成数字相同的另一花色牌，目标牌必须还在牌墙里。",
    usage: "自己回合使用。只需要改 from_tile 的牌名和 to_suit 的花色。wan=万，tong=筒，tiao=条。",
    params: '{"from_tile":"5万","to_suit":"tong"}',
  },
  stealth_gang: {
    name: "偷摸开杠",
    type: "主动杠",
    limit: "每局 1 次",
    effect: "手里有三张相同牌时，从牌墙拿第 4 张，直接形成暗杠并按暗杠结算。",
    usage: "自己回合使用。只需要把 tile 改成你手里有三张的牌名。",
    params: '{"tile":"5万"}',
  },
  steal_concealed_gang: {
    name: "偷暗杠",
    type: "主动目标",
    limit: "每局 1 次",
    effect: "用自己一张牌替换别人暗杠中的一张真实牌，一个暗杠只能被偷一次。",
    usage: "填写目标玩家 ID，并把 your_tile 改成你要交出去的牌名。target_meld_id 目前不用填。",
    params: '{"target_player_id":"p2","your_tile":"3万"}',
  },
  recycle_river: {
    name: "回收牌河",
    type: "主动摸牌替代",
    limit: "自己牌河 1 次，别人牌河 1 次",
    effect: "摸牌前改为从牌河拿回一张指定牌。",
    usage: "只需要改来源、目标玩家 ID 和要回收的牌名。source=own 表示自己的牌河，others 表示别人的牌河。",
    params: '{"source":"others","target_player_id":"p2","tile":"3万"}',
  },
  wish_tile: {
    name: "自行印牌",
    type: "主动摸牌替代",
    limit: "每局 1 次",
    effect: "摸牌前许愿一张牌。牌墙里有就直接拿，没有则消耗技能并正常摸一张。",
    usage: "自己摸牌前使用。只需要把 tile 改成想要的牌名。",
    params: '{"tile":"5筒"}',
  },
};

function getOrCreatePlayerId() {
  let id = sessionStorage.getItem(STORAGE_KEYS.playerId);
  if (!id) {
    id = makePlayerId();
    sessionStorage.setItem(STORAGE_KEYS.playerId, id);
  }
  return id;
}

function makePlayerId() {
  return `p_${crypto.randomUUID().slice(0, 8)}`;
}

function setPlayerId(value) {
  const normalized = value.trim() || makePlayerId();
  sessionStorage.setItem(STORAGE_KEYS.playerId, normalized);
  $("playerIdInput").value = normalized;
  return normalized;
}

function playerId() {
  return $("playerIdInput").value.trim();
}

function roomId() {
  return $("roomId").value.trim();
}

function playerName() {
  return $("playerName").value.trim() || playerId();
}

function apiPath(path) {
  return `/api${path}`;
}

function wsUrl() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws/${roomId()}/${encodeURIComponent(playerId())}`;
}

function showMessage(text) {
  $("message").textContent = text;
}

async function request(path, options = {}) {
  const response = await fetch(apiPath(path), {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `请求失败，状态码：${response.status}`);
  }
  return body;
}

function persistLocalRoomInputs() {
  sessionStorage.setItem(STORAGE_KEYS.playerId, playerId());
  sessionStorage.setItem(STORAGE_KEYS.playerName, $("playerName").value.trim());
  sessionStorage.setItem(STORAGE_KEYS.roomId, roomId());
}

function updateShareLink(roomIdValue) {
  $("roomIdText").textContent = roomIdValue || "-";
  if (!roomIdValue) {
    $("shareLink").value = "";
    return;
  }
  const url = new URL(window.location.href);
  url.searchParams.set("room_id", roomIdValue);
  $("shareLink").value = url.toString();
}

async function createRoom() {
  persistLocalRoomInputs();
  const body = await request("/rooms", {
    method: "POST",
    body: JSON.stringify({ player_id: playerId(), name: playerName() }),
  });
  $("roomId").value = body.room_id;
  persistLocalRoomInputs();
  updateShareLink(body.room_id);
  showMessage(`已创建房间：${body.room_id}。请点击“准备”和“连接/重连”。`);
  renderState(body);
  connectWebSocket();
}

async function joinRoom() {
  persistLocalRoomInputs();
  const body = await request(`/rooms/${roomId()}/join`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId(), name: playerName() }),
  });
  persistLocalRoomInputs();
  updateShareLink(roomId());
  showMessage("已加入房间。请点击“准备”，并确认已经连接。");
  renderState(body);
  connectWebSocket();
}

async function readyRoom() {
  const body = await request(`/rooms/${roomId()}/ready`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId(), ready: true }),
  });
  showMessage("已准备。请确认连接状态为“已连接”。");
  renderState(body);
}

async function startGame() {
  await refreshState();
  const playerCount = latestState?.players?.length || 0;
  const isHost = latestState?.host_player_id === playerId();
  let confirmUnderfilled = false;

  if (playerCount > 1 && playerCount < 4) {
    if (!isHost) {
      throw new Error("人数不足 4 人时，只有房主确认后才能开始。");
    }
    confirmUnderfilled = window.confirm(`当前只有 ${playerCount} 人，确定要少人开局吗？`);
    if (!confirmUnderfilled) {
      showMessage("已取消少人开局。");
      return;
    }
  }

  const body = await request(`/rooms/${roomId()}/start`, {
    method: "POST",
    body: JSON.stringify({
      player_id: playerId(),
      confirm_underfilled: confirmUnderfilled,
    }),
  });
  showMessage("游戏已开始，请同步选择本局技能。所有人选完后才会正式对局。");
  renderState(body);
}

async function refreshState() {
  if (!roomId()) {
    return;
  }
  const body = await request(`/rooms/${roomId()}/state?viewer_id=${encodeURIComponent(playerId())}`);
  renderState(body);
}

function connectWebSocket({ silent = false } = {}) {
  if (!roomId()) {
    if (!silent) {
      showMessage("请先创建或加入房间。");
    }
    return;
  }
  if (socket) {
    socket.onclose = null;
    socket.close();
  }
  clearTimeout(reconnectTimer);
  socket = new WebSocket(wsUrl());
  socket.onopen = () => {
    $("wsStatus").textContent = "已连接";
    if (!silent) {
      showMessage("已连接到房间，状态会实时同步。");
    }
  };
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "state") {
      renderState(message.data);
    } else if (message.type === "error") {
      showMessage(message.message);
    } else if (message.type === "system") {
      showMessage(message.message);
    }
  };
  socket.onclose = (event) => {
    if (event.code === 1008) {
      $("wsStatus").textContent = "连接被拒绝";
      showMessage("连接被拒绝：当前玩家 ID 不在这个房间里，请先加入房间，或改回刷新前使用的玩家 ID。");
      return;
    }
    $("wsStatus").textContent = "已断开，正在尝试重连";
    reconnectTimer = window.setTimeout(() => {
      if (roomId() && playerId()) {
        connectWebSocket({ silent: true });
      }
    }, 1200);
  };
  socket.onerror = () => {
    $("wsStatus").textContent = "连接错误";
  };
}

async function sendAction(action) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    const { type, ...payload } = action;
    socket.send(JSON.stringify({ type, payload }));
    return;
  }
  const body = await request(`/rooms/${roomId()}/actions`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId(), ...action }),
  });
  renderState(body);
}

function renderState(state) {
  latestState = state;
  if (state.room_id) {
    $("roomId").value = state.room_id;
    persistLocalRoomInputs();
  }
  updateShareLink(state.room_id || roomId());
  $("roomStatus").textContent = `${statusLabel(state.status)} / ${phaseLabel(state.phase)}`;
  $("hostPlayer").textContent = state.host_player_id || "-";
  $("currentPlayer").textContent = state.current_player_id || "-";
  $("wallCount").textContent = state.wall_count ?? "-";
  $("huHint").textContent = state.can_hu ? "你可以胡了" : "-";
  $("winnerBanner").textContent = state.hu_notice?.self_message || state.hu_notice?.message || "";
  $("winnerBanner").className = state.hu_notice?.message ? "winner" : "";
  $("skills").textContent = formatSkillNames(currentViewer(state)?.skills || []);
  $("scores").textContent = formatMap(state.scores);
  $("roundScoreDelta").textContent = formatMap(state.round_score_delta);
  $("settlementSummary").textContent = state.settlement_summary?.message || "-";
  const privateResults =
    currentViewer(state)?.private_skill_results || state.private_data?.private_skill_results || [];
  $("privateSkillResults").textContent = formatPrivateSkillResults(privateResults);
  notifyNewPrivateSkillResult(privateResults);
  renderSkillSelection(state);
  renderSkillUsePanel(state);
  $("actionLog").textContent = formatActionLog(state.action_log || []);
  renderHand(state);
  renderPlayers(state);
}

function renderSkillSelection(state) {
  const viewer = currentViewer(state);
  const candidates = viewer?.skill_candidates || [];
  const alreadySelected = viewer?.skills || [];
  $("skillCandidates").innerHTML = "";

  if (state.phase !== "skill_selection") {
    $("skillSelectionHint").textContent =
      state.phase === "playing" ? "技能选择已完成，已进入正式对局。" : "当前不在技能选择阶段。";
    $("selectSkills").disabled = true;
    return;
  }

  if (alreadySelected.length === 2) {
    $("skillSelectionHint").textContent = "你已经选完技能，等待其他玩家选择。";
    $("selectSkills").disabled = true;
  } else {
    $("skillSelectionHint").textContent = "请从下面 3 个候选技能中选择 2 个。其他玩家会同步看到你是否已选完，但看不到你的候选。";
    $("selectSkills").disabled = false;
  }

  selectedSkillIds = selectedSkillIds.filter((id) => candidates.includes(id));
  candidates.forEach((skillId) => {
    const info = skillInfo(skillId);
    const label = document.createElement("label");
    label.className = "skill-card";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.disabled = alreadySelected.length === 2;
    checkbox.checked = selectedSkillIds.includes(skillId) || alreadySelected.includes(skillId);
    checkbox.onchange = () => toggleSkillCandidate(checkbox, skillId);
    label.appendChild(checkbox);
    label.appendChild(skillDescriptionNode(skillId, info));
    $("skillCandidates").appendChild(label);
  });
}

function toggleSkillCandidate(checkbox, skillId) {
  if (checkbox.checked) {
    if (selectedSkillIds.length >= 2) {
      checkbox.checked = false;
      showMessage("只能选择 2 个技能。");
      return;
    }
    selectedSkillIds.push(skillId);
  } else {
    selectedSkillIds = selectedSkillIds.filter((id) => id !== skillId);
  }
}

function renderSkillUsePanel(state) {
  const viewer = currentViewer(state);
  const skills = viewer?.skills || [];
  const select = $("skillSelect");
  const previousValue = select.value;
  select.innerHTML = "";

  if (skills.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "暂无可用技能";
    select.appendChild(option);
    $("skillUseHelp").textContent = "技能选择完成后，这里会显示你的技能。";
    return;
  }

  skills.forEach((skillId) => {
    const option = document.createElement("option");
    option.value = skillId;
    option.textContent = skillLabel(skillId);
    select.appendChild(option);
  });
  if (skills.includes(previousValue)) {
    select.value = previousValue;
  }
  updateSkillUseHelp();
}

function updateSkillUseHelp() {
  const skillId = $("skillSelect").value;
  const info = skillInfo(skillId);
  $("skillUseHelp").innerHTML = `<strong>${info.name}</strong>（${info.type}，${info.limit}）：${info.effect}<br />使用方式：${info.usage}`;
  if (info.params) {
    const template = formatSkillParamsTemplate(info.params);
    $("skillParamsInput").placeholder = template;
    if (currentParamTemplateSkillId !== skillId || !$("skillParamsInput").value.trim()) {
      $("skillParamsInput").value = template;
      currentParamTemplateSkillId = skillId;
    }
  } else {
    $("skillParamsInput").placeholder = "该技能不用手动填写参数";
    $("skillParamsInput").value = "";
    currentParamTemplateSkillId = skillId;
  }
}

function currentViewer(state) {
  return (state.players || []).find((player) => player.player_id === playerId());
}

function renderHand(state) {
  const viewer = currentViewer(state);
  const hand = viewer?.hand || [];
  $("hand").innerHTML = "";
  hand.forEach((tile, index) => {
    const button = document.createElement("button");
    button.className = "tile";
    button.textContent = tile;
    if (selectedTile === tile) {
      button.classList.add("selected");
    }
    if (chiSelectedTiles.some((selected) => selected.index === index)) {
      button.classList.add("chi-selected");
    }
    button.onclick = () => handleHandClick(tile, index);
    $("hand").appendChild(button);
  });
}

function handleHandClick(tile, index) {
  if (chiMode) {
    toggleChiTile(tile, index);
    return;
  }
  selectedTile = tile;
  renderHand(latestState);
}

async function toggleChiTile(tile, index) {
  const existingIndex = chiSelectedTiles.findIndex((selected) => selected.index === index);
  if (existingIndex >= 0) {
    chiSelectedTiles.splice(existingIndex, 1);
    renderHand(latestState);
    return;
  }
  if (chiSelectedTiles.length >= 2) {
    showMessage("吃牌只需要选择两张手牌。");
    return;
  }
  chiSelectedTiles.push({ tile, index });
  renderHand(latestState);
  if (chiSelectedTiles.length < 2) {
    showMessage("请再选择一张用于吃牌的手牌。");
    return;
  }
  const claimedTile = latestState?.last_discard?.tile;
  const tiles = [claimedTile, ...chiSelectedTiles.map((selected) => selected.tile)];
  if (!claimedTile || !isValidChiSelection(tiles)) {
    chiSelectedTiles = [];
    renderHand(latestState);
    showMessage("这两张牌不能吃，请重新选择。");
    return;
  }
  chiMode = false;
  chiSelectedTiles = [];
  await sendAction({ type: "chi", tiles });
}

function isValidChiSelection(tiles) {
  const parsed = tiles.map(parseTileText);
  if (parsed.some((tile) => !tile)) {
    return false;
  }
  const suit = parsed[0].suit;
  if (!parsed.every((tile) => tile.suit === suit)) {
    return false;
  }
  const ranks = parsed.map((tile) => tile.rank).sort((a, b) => a - b);
  return ranks[0] + 1 === ranks[1] && ranks[1] + 1 === ranks[2];
}

function parseTileText(text) {
  const match = /^([1-9])(万|筒|条)$/.exec(text || "");
  return match ? { rank: Number(match[1]), suit: match[2] } : null;
}

function renderPlayers(state) {
  $("players").innerHTML = "";
  (state.players || []).forEach((player) => {
    const div = document.createElement("div");
    div.className = "player-row";
    const melds = (player.melds || [])
      .map((meld) => `${meldTypeLabel(meld.type)}[${(meld.tiles || []).join("、")}]`)
      .join(" ");
    const skillStatus =
      state.phase === "skill_selection"
        ? player.skill_selected
          ? "已选技能"
          : "未选技能"
        : formatSkillNames(player.skills || []);
    div.textContent = `${player.player_id} ${player.name} ${player.connected ? "在线" : "离线"} ${
      player.ready ? "已准备" : "未准备"
    } ${skillStatus} 手牌:${player.hand_count ?? "-"} 弃牌:${
      (player.discard_pile || []).join("、") || "-"
    } 副露:${melds || "-"}`;
    $("players").appendChild(div);
  });
}

function formatMap(value) {
  if (!value || Object.keys(value).length === 0) {
    return "-";
  }
  return Object.entries(value)
    .map(([key, score]) => `${key}:${score}`)
    .join("；");
}

function formatPrivateSkillResults(results) {
  if (!results || results.length === 0) {
    return "-";
  }
  return results.map(formatPrivateSkillResult).join("\n");
}

function formatPrivateSkillResult(result) {
  const skillName = skillInfo(result.type).name || result.type;
  if (result.type === "astrology") {
    return `观星：牌墙顶 ${result.tiles?.length || 0} 张是 ${formatTiles(result.tiles)}。`;
  }
  if (result.type === "peek_neighbor") {
    return `偷窥：看到玩家 ${result.target_player_id} 的 ${formatTiles(result.tiles)}。`;
  }
  if (result.type === "swap_with_neighbor") {
    return `偷天换日：你获得了 ${result.gained_tile || "-"}。`;
  }
  if (result.type === "change_suit") {
    return `换色：${result.from_tile || "-"} 换成了 ${result.to_tile || "-"}。`;
  }
  if (result.type === "steal_concealed_gang") {
    return `偷暗杠：你从玩家 ${result.target_player_id} 的暗杠里偷到了 ${result.stolen_tile || "-"}。`;
  }
  if (result.type === "wish_tile") {
    return `自行印牌：许愿 ${result.wished_tile || "-"}，${
      result.success ? "成功" : "失败后改为正常摸牌"
    }，摸到 ${result.drawn_tile || "-"}。`;
  }
  if (result.type === "killing_intent_sense") {
    return `杀意感知：${result.message || ""} ${result.tile || ""}`;
  }
  if (result.message) {
    return `${skillName}：${result.message}`;
  }
  return `${skillName}：${JSON.stringify(result)}`;
}

function notifyNewPrivateSkillResult(results) {
  if (!results || results.length <= lastPrivateResultCount) {
    lastPrivateResultCount = results?.length || 0;
    return;
  }
  const latest = results[results.length - 1];
  lastPrivateResultCount = results.length;
  if (latest?.type === "astrology") {
    showMessage(`观星成功：牌墙顶 ${latest.tiles?.length || 0} 张是 ${formatTiles(latest.tiles)}。`);
  }
}

function formatTiles(tiles) {
  return tiles && tiles.length ? tiles.join("、") : "-";
}

function formatActionLog(actionLog) {
  if (!actionLog.length) {
    return "-";
  }
  return JSON.stringify(
    actionLog.map((action) => ({
      ...action,
      skill_name: action.skill_id ? skillInfo(action.skill_id).name : undefined,
      type_label: actionTypeLabel(action.type),
    })),
    null,
    2,
  );
}

function parseSkillParams() {
  const text = $("skillParamsInput").value.trim();
  if (!text) {
    return {};
  }
  return JSON.parse(text);
}

function formatSkillParamsTemplate(paramsText) {
  try {
    return JSON.stringify(JSON.parse(paramsText), null, 2);
  } catch {
    return paramsText;
  }
}

function skillInfo(skillId) {
  return (
    SKILL_INFO[skillId] || {
      name: skillId || "未知技能",
      type: "未知",
      limit: "-",
      effect: "-",
      usage: "-",
      params: "",
    }
  );
}

function skillLabel(skillId) {
  const info = skillInfo(skillId);
  return `${info.name}（${skillId}）`;
}

function formatSkillNames(skillIds) {
  if (!skillIds || skillIds.length === 0) {
    return "-";
  }
  return skillIds.map(skillLabel).join("、");
}

function skillDescriptionNode(skillId, info) {
  const wrapper = document.createElement("span");
  wrapper.className = "skill-card-body";
  const title = document.createElement("strong");
  title.textContent = skillLabel(skillId);
  const meta = document.createElement("span");
  meta.className = "skill-meta";
  meta.textContent = `${info.type}，${info.limit}`;
  const effect = document.createElement("span");
  effect.textContent = `效果：${info.effect}`;
  const usage = document.createElement("span");
  usage.textContent = `用法：${info.usage}`;
  wrapper.append(title, meta, effect, usage);
  return wrapper;
}

function renderSkillManual() {
  $("skillManualList").innerHTML = "";
  Object.entries(SKILL_INFO).forEach(([skillId, info]) => {
    const card = document.createElement("div");
    card.className = "skill-card manual-skill";
    card.appendChild(skillDescriptionNode(skillId, info));
    if (info.params) {
      const params = document.createElement("code");
      params.textContent = `参数模板：${formatSkillParamsTemplate(info.params)}`;
      card.appendChild(params);
    }
    $("skillManualList").appendChild(card);
  });
}

function renderManual() {
  $("manualPanel").classList.toggle("hidden", !manualOpen);
  $("toggleManual").textContent = manualOpen ? "隐藏说明书" : "查看说明书";
  ["operate", "rules", "skills"].forEach((tab) => {
    const page = $(`manual${capitalize(tab)}`);
    if (page) {
      page.classList.toggle("hidden", activeManualTab !== tab);
    }
  });
}

function capitalize(text) {
  return text.slice(0, 1).toUpperCase() + text.slice(1);
}

function meldTypeLabel(type) {
  return (
    {
      chi: "吃",
      peng: "碰",
      concealed_gang: "暗杠",
      exposed_gang: "明杠",
      added_gang: "补杠",
      hidden_gang: "暗杠",
    }[type] || type
  );
}

function statusLabel(status) {
  return (
    {
      waiting: "等待中",
      playing: "游戏中",
      finished: "已结束",
    }[status] || status || "-"
  );
}

function phaseLabel(phase) {
  return (
    {
      waiting: "等待中",
      skill_selection: "技能选择",
      playing: "正式对局",
      waiting_for_reaction: "等待响应",
      finished: "已结束",
      draw_game: "流局",
    }[phase] || phase || "-"
  );
}

function actionTypeLabel(type) {
  return (
    {
      start_game: "开始游戏",
      deal: "发牌",
      draw: "摸牌",
      discard: "出牌",
      chi: "吃",
      peng: "碰",
      gang: "杠",
      hu: "胡牌",
      select_skills: "选择技能",
      skill_effect: "技能生效",
      use_skill: "使用技能",
      score: "计分",
      restart_game: "重新开始",
      set_auto_sort_hand: "设置自动理牌",
    }[type] || type
  );
}

function bind(id, handler) {
  $(id).onclick = async () => {
    try {
      await handler();
    } catch (error) {
      showMessage(error.message);
    }
  };
}

bind("createRoom", createRoom);
bind("joinRoom", joinRoom);
bind("readyRoom", readyRoom);
bind("startGame", startGame);
bind("connectWs", () => connectWebSocket());
bind("newPlayerId", () => {
  setPlayerId(makePlayerId());
  showMessage("已生成新的玩家 ID。多窗口测试时，每个窗口都应不同。");
});
bind("selectSkills", () => {
  if (selectedSkillIds.length !== 2) {
    throw new Error("请选择 2 个技能。");
  }
  return sendAction({ type: "select_skills", skill_ids: selectedSkillIds });
});
bind("copyShareLink", async () => {
  await navigator.clipboard.writeText($("shareLink").value);
  showMessage("已复制房间链接。");
});
bind("discardTile", () => {
  if (!selectedTile) {
    throw new Error("请先点击一张手牌。");
  }
  return sendAction({ type: "discard", tile: selectedTile });
});
bind("declareHu", () => sendAction({ type: "hu" }));
bind("huOnDiscard", () => sendAction({ type: "hu_on_discard" }));
bind("chiTile", () => {
  chiMode = true;
  chiSelectedTiles = [];
  renderHand(latestState);
  showMessage("吃牌模式：请点击两张手牌。");
});
bind("pengTile", () => sendAction({ type: "peng" }));
bind("passAction", () => sendAction({ type: "pass" }));
bind("gangTile", () =>
  sendAction({
    type: "gang",
    gang_type: $("gangType").value,
    tile: $("gangTileValue").value.trim(),
  }),
);
bind("useSkill", () => {
  const skillId = $("skillSelect").value;
  if (!skillId) {
    throw new Error("请选择技能。");
  }
  return sendAction({ type: "use_skill", skill_id: skillId, params: parseSkillParams() });
});
bind("toggleManual", () => {
  manualOpen = !manualOpen;
  renderManual();
});

function init() {
  $("playerIdInput").value = getOrCreatePlayerId();
  const params = new URLSearchParams(window.location.search);
  const urlRoomId = params.get("room_id");
  $("playerName").value = sessionStorage.getItem(STORAGE_KEYS.playerName) || "";
  if (urlRoomId) {
    $("roomId").value = urlRoomId;
    updateShareLink(urlRoomId);
  } else {
    const savedRoomId = sessionStorage.getItem(STORAGE_KEYS.roomId);
    if (savedRoomId) {
      $("roomId").value = savedRoomId;
      updateShareLink(savedRoomId);
    }
  }

  $("playerIdInput").addEventListener("change", () => {
    setPlayerId($("playerIdInput").value);
    persistLocalRoomInputs();
  });
  $("playerName").addEventListener("change", persistLocalRoomInputs);
  $("roomId").addEventListener("change", persistLocalRoomInputs);
  $("skillSelect").addEventListener("change", updateSkillUseHelp);
  document.querySelectorAll("[data-manual-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      activeManualTab = button.dataset.manualTab;
      renderManual();
    });
  });

  renderSkillManual();
  renderManual();
  showMessage("加入房间后，请点击“准备”和“连接/重连”。刷新页面后会保留本窗口身份，并自动尝试恢复牌局。");

  if (roomId()) {
    refreshState()
      .then(() => connectWebSocket({ silent: true }))
      .catch((error) => {
        showMessage(`已带入房间号。请输入昵称后加入房间，或检查原玩家 ID 是否属于该房间。${error.message}`);
      });
  }
}

init();
