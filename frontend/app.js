let socket = null;
let latestState = null;
let selectedTile = null;
let chiMode = false;
let chiSelectedTiles = [];

const $ = (id) => document.getElementById(id);

function getOrCreatePlayerId() {
  const key = "mahjong_chaos_player_id";
  let playerId = localStorage.getItem(key);
  if (!playerId) {
    playerId = `p_${crypto.randomUUID().slice(0, 8)}`;
    localStorage.setItem(key, playerId);
  }
  return playerId;
}

const playerId = getOrCreatePlayerId();

function roomId() {
  return $("roomId").value.trim();
}

function playerName() {
  return $("playerName").value.trim() || playerId;
}

function apiPath(path) {
  return `/api${path}`;
}

function wsUrl() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws/${roomId()}/${encodeURIComponent(playerId)}`;
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
  const body = await request("/rooms", {
    method: "POST",
    body: JSON.stringify({ player_id: playerId, name: playerName() }),
  });
  $("roomId").value = body.room_id;
  updateShareLink(body.room_id);
  showMessage(`已创建房间：${body.room_id}`);
  renderState(body);
}

async function joinRoom() {
  const body = await request(`/rooms/${roomId()}/join`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId, name: playerName() }),
  });
  updateShareLink(roomId());
  showMessage("已加入房间");
  renderState(body);
}

async function readyRoom() {
  const body = await request(`/rooms/${roomId()}/ready`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId, ready: true }),
  });
  showMessage("已准备");
  renderState(body);
}

async function startGame() {
  const body = await request(`/rooms/${roomId()}/start`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId }),
  });
  showMessage("游戏已开始");
  renderState(body);
}

async function refreshState() {
  if (!roomId()) {
    return;
  }
  const body = await request(`/rooms/${roomId()}/state?viewer_id=${encodeURIComponent(playerId)}`);
  renderState(body);
}

function connectWebSocket() {
  if (!roomId()) {
    showMessage("请先创建或加入房间");
    return;
  }
  if (socket) {
    socket.close();
  }
  socket = new WebSocket(wsUrl());
  socket.onopen = () => {
    $("wsStatus").textContent = "已连接";
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
  socket.onclose = () => {
    $("wsStatus").textContent = "已断开";
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
    body: JSON.stringify({ player_id: playerId, ...action }),
  });
  renderState(body);
}

function renderState(state) {
  latestState = state;
  updateShareLink(state.room_id || roomId());
  $("roomStatus").textContent = state.status || "-";
  $("hostPlayer").textContent = state.host_player_id || "-";
  $("currentPlayer").textContent = state.current_player_id || "-";
  $("wallCount").textContent = state.wall_count ?? "-";
  $("huHint").textContent = state.can_hu ? "你可以胡了" : "-";
  $("winnerBanner").textContent = state.hu_notice?.self_message || state.hu_notice?.message || "";
  $("winnerBanner").className = state.hu_notice?.message ? "winner" : "";
  $("skills").textContent = currentViewer(state)?.skills?.join("、") || "-";
  $("scores").textContent = formatMap(state.scores);
  $("roundScoreDelta").textContent = formatMap(state.round_score_delta);
  $("settlementSummary").textContent = state.settlement_summary?.message || "-";
  $("peekWall").textContent = state.private_data?.peek_wall?.join("、") || "-";
  $("actionLog").textContent = JSON.stringify(state.action_log || [], null, 2);
  renderHand(state);
  renderPlayers(state);
}

function currentViewer(state) {
  return (state.players || []).find((player) => player.player_id === playerId);
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
    showMessage("吃牌只需要选择两张手牌");
    return;
  }
  chiSelectedTiles.push({ tile, index });
  renderHand(latestState);
  if (chiSelectedTiles.length < 2) {
    showMessage("请再选择一张用于吃牌的手牌");
    return;
  }
  const claimedTile = latestState?.last_discard?.tile;
  const tiles = [claimedTile, ...chiSelectedTiles.map((selected) => selected.tile)];
  if (!claimedTile || !isValidChiSelection(tiles)) {
    chiSelectedTiles = [];
    renderHand(latestState);
    showMessage("这两张牌不能吃，请重新选择");
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
  const match = /^([1-9])([万筒条])$/.exec(text || "");
  return match ? { rank: Number(match[1]), suit: match[2] } : null;
}

function renderPlayers(state) {
  $("players").innerHTML = "";
  (state.players || []).forEach((player) => {
    const div = document.createElement("div");
    const melds = (player.melds || [])
      .map((meld) => `${meld.type}[${(meld.tiles || []).join("、")}]`)
      .join(" ");
    div.textContent = `${player.player_id} ${player.name} ${player.connected ? "在线" : "离线"} ${
      player.ready ? "已准备" : ""
    } 手牌:${player.hand_count} 弃牌:${(player.discard_pile || []).join("、") || "-"} 副露:${
      melds || "-"
    }`;
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
bind("connectWs", connectWebSocket);
bind("copyShareLink", async () => {
  await navigator.clipboard.writeText($("shareLink").value);
  showMessage("已复制房间链接");
});
bind("discardTile", () => {
  if (!selectedTile) {
    throw new Error("请先点击一张手牌");
  }
  return sendAction({ type: "discard", tile: selectedTile });
});
bind("declareHu", () => sendAction({ type: "hu" }));
bind("huOnDiscard", () => sendAction({ type: "hu_on_discard" }));
bind("chiTile", () => {
  chiMode = true;
  chiSelectedTiles = [];
  renderHand(latestState);
  showMessage("吃牌模式：请选择两张手牌");
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
bind("usePeekWall", () => sendAction({ type: "use_skill", skill_id: "peek_wall", params: {} }));
bind("useSealPeng", () =>
  sendAction({
    type: "use_skill",
    skill_id: "seal_peng",
    params: { target_player_id: $("sealPengTarget").value.trim() },
  }),
);

function init() {
  $("playerIdText").textContent = playerId;
  const params = new URLSearchParams(window.location.search);
  const urlRoomId = params.get("room_id");
  if (urlRoomId) {
    $("roomId").value = urlRoomId;
    updateShareLink(urlRoomId);
  }
}

init();
