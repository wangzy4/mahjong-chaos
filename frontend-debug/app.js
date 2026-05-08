let socket = null;
let selectedTile = null;
let latestState = null;
let chiMode = false;
let chiSelectedTiles = [];

const $ = (id) => document.getElementById(id);

const RULES = [
  {
    title: "基本规则",
    items: [
      "使用万、条、筒三种花色，每种 1-9 点，每张 4 张，共 108 张。",
      "支持 2-4 人局；少于 4 人开局或重新开始时需要房主确认。",
      "轮到玩家时由服务端自动摸牌，玩家摸牌后必须出一张牌，不能由客户端决定摸到什么牌。",
      "可以吃、碰、暗杠、明杠、补杠；吃牌需要点击“吃牌”后再点两张自己的手牌，不合法会要求重选。",
      "响应别人打出的牌时，按胡、杠、碰、吃的顺序处理；同一优先级仍按第一个有效请求处理。",
      "胡牌支持标准 4 面子 + 1 雀头，也支持七小对。",
      "本局结束后，非房主准备，房主在所有非房主准备后重新开始。",
    ],
  },
  {
    title: "分数计算",
    items: [
      "所有计分都保持零和：有人加多少，其他玩家合计就扣多少。",
      "点炮胡基础支付为 3 分；自摸时每个其他玩家基础支付 2 分。",
      "番型乘法叠加且默认不封顶：门前清 x2，清一色 x2，碰碰胡 x2，七小对 x4。",
      "七小对已经包含门前清收益，因此命中七小对时不再额外叠加门前清。",
      "七小对可以和清一色叠加，不能和碰碰胡叠加。",
      "庄家赢或庄家输时，相关那一笔付款 x2；庄家倍率独立于番型倍率。",
      "胡牌支付公式：基础分 * 番型倍率 * 庄家倍率 * 豪赌倍率。",
      "暗杠每家基础支付 2 分，明杠点杠者基础支付 3 分，补杠每家基础支付 1 分。",
      "杠分立即结算，只受庄家倍率影响，不受胡牌番型和豪赌影响。",
    ],
  },
  {
    title: "技能",
    items: [
      "开局每名玩家随机获得 1 个技能。",
      "窥视牌墙：查看牌墙顶 3 张牌，只对自己可见。",
      "封印碰牌：封印一名玩家的下一次碰牌机会，只限制碰，不限制吃和杠。",
      "豪赌 DoubleScore：胡牌结算时作为额外 x2 倍率；点炮胡时胡牌者或点炮者任意一方有豪赌都会生效，但不叠乘。",
      "豪赌不影响杠分，也不影响番型识别。",
    ],
  },
];

function apiBase() {
  return $("apiBase").value.replace(/\/$/, "");
}

function wsBase() {
  return apiBase().replace(/^http/, "ws");
}

function playerId() {
  return $("playerId").value.trim();
}

function roomId() {
  return $("roomId").value.trim();
}

function showMessage(text) {
  $("message").textContent = text;
}

function showRules() {
  renderRules();
  $("rulesModal").classList.add("open");
}

function closeRules() {
  $("rulesModal").classList.remove("open");
}

function renderRules() {
  $("rulesContent").innerHTML = "";
  RULES.forEach((section) => {
    const sectionNode = document.createElement("section");
    sectionNode.className = "rule-section";

    const title = document.createElement("h3");
    title.textContent = section.title;
    sectionNode.appendChild(title);

    const list = document.createElement("ul");
    section.items.forEach((item) => {
      const listItem = document.createElement("li");
      listItem.textContent = item;
      list.appendChild(listItem);
    });
    sectionNode.appendChild(list);
    $("rulesContent").appendChild(sectionNode);
  });
}

async function request(path, options = {}) {
  const response = await fetch(`${apiBase()}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `请求失败，状态码：${response.status}`);
  }
  return body;
}

async function createRoom() {
  const body = await request("/rooms", {
    method: "POST",
    body: JSON.stringify({ player_id: playerId(), name: $("playerName").value.trim() }),
  });
  $("roomId").value = body.room_id;
  showMessage(`已创建房间：${body.room_id}`);
  await refreshState();
}

async function joinRoom() {
  await request(`/rooms/${roomId()}/join`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId(), name: $("playerName").value.trim() }),
  });
  showMessage("已加入房间");
  await refreshState();
}

async function startGame() {
  let confirmUnderfilled = false;
  if (roomId() && playerId()) {
    await refreshState();
    const playerCount = latestState?.players?.length || 0;
    const hostPlayerId = latestState?.host_player_id;
    if (playerCount > 1 && playerCount < 4) {
      if (playerId() !== hostPlayerId) {
        throw new Error("人数不足 4 人时，只能由房主确认后开始。");
      }
      confirmUnderfilled = window.confirm(`当前只有 ${playerCount} 人，确认直接开始吗？`);
      if (!confirmUnderfilled) {
        showMessage("已取消开始游戏");
        return;
      }
    }
  }
  await request(`/rooms/${roomId()}/start`, {
    method: "POST",
    body: JSON.stringify({
      player_id: playerId(),
      confirm_underfilled: confirmUnderfilled,
    }),
  });
  showMessage("游戏已开始");
  await refreshState();
}

async function readyNextGame() {
  const body = await request(`/rooms/${roomId()}/ready`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId() }),
  });
  showMessage("已准备下一局");
  renderState(body);
}

async function restartGame() {
  await refreshState();
  const playerCount = latestState?.players?.length || 0;
  let confirmUnderfilled = false;
  if (playerCount > 1 && playerCount < 4) {
    confirmUnderfilled = window.confirm(`当前只有 ${playerCount} 人，确认重新开始下一局吗？`);
    if (!confirmUnderfilled) {
      showMessage("已取消重新开始");
      return;
    }
  }
  const body = await request(`/rooms/${roomId()}/restart`, {
    method: "POST",
    body: JSON.stringify({
      player_id: playerId(),
      confirm_underfilled: confirmUnderfilled,
    }),
  });
  showMessage("已重新开始");
  renderState(body);
}

async function sendAction(action) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    const { type, ...payload } = action;
    socket.send(JSON.stringify({ type, payload }));
    showMessage(`已发送操作：${type}`);
    return;
  }
  const body = await request(`/rooms/${roomId()}/actions`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId(), ...action }),
  });
  renderState(body);
}

async function setAutoSortHand(enabled) {
  const body = await request(`/rooms/${roomId()}/settings/auto-sort-hand`, {
    method: "POST",
    body: JSON.stringify({ player_id: playerId(), enabled }),
  });
  renderState(body);
}

async function refreshState() {
  if (!roomId() || !playerId()) {
    return;
  }
  const body = await request(`/rooms/${roomId()}/state?viewer_id=${encodeURIComponent(playerId())}`);
  renderState(body);
}

function connectWebSocket() {
  if (socket) {
    socket.close();
  }
  socket = new WebSocket(`${wsBase()}/ws/${roomId()}/${encodeURIComponent(playerId())}`);
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
    } else {
      renderState(message);
    }
  };
  socket.onclose = () => {
    $("wsStatus").textContent = "已断开";
  };
  socket.onerror = () => {
    $("wsStatus").textContent = "连接错误";
  };
}

function renderState(state) {
  latestState = state;
  selectedTile = null;
  if (!chiMode) {
    chiSelectedTiles = [];
  }
  $("currentPlayer").textContent = state.current_player_id || "-";
  $("roomStatus").textContent = state.status || "-";
  $("hostPlayer").textContent = state.host_player_id || "-";
  $("readyPlayers").textContent = state.ready_player_ids?.join("、") || "-";
  $("pengHint").textContent = renderClaimHint(state);
  $("wallCount").textContent = state.wall_count ?? "-";
  $("huHint").textContent = state.can_hu ? "你可以胡了" : "-";
  $("huHint").className = state.can_hu ? "hint" : "";
  $("huNotice").textContent = state.hu_notice?.message || "-";
  $("huNotice").className = state.hu_notice?.message ? "winner" : "";
  $("scores").textContent = formatScoreMap(state.scores);
  $("roundScoreDelta").textContent = formatScoreMap(state.round_score_delta);
  $("settlementSummary").textContent = formatSettlementSummary(state.settlement_summary);
  $("winnerBanner").textContent = state.hu_notice?.self_message || "";
  $("winnerBanner").className = state.hu_notice?.self_message ? "winner" : "";
  $("peekWall").textContent = state.private_data?.peek_wall?.join("、") || "-";
  renderHand(state);
  renderPlayers(state);
  renderSkills(state);
  $("actionLog").textContent = JSON.stringify(state.action_log || [], null, 2);
  renderNextGameButtons(state);
}

function formatScoreMap(scores) {
  if (!scores || Object.keys(scores).length === 0) {
    return "-";
  }
  return Object.entries(scores)
    .map(([id, score]) => `${id}:${score}`)
    .join("，");
}

function formatSettlementSummary(summary) {
  if (!summary) {
    return "-";
  }
  if (summary.message) {
    return summary.message;
  }
  const labelMap = {
    self_draw: "自摸胡",
    discard: "点炮胡",
    draw_game: "流局",
  };
  const label = summary.label || labelMap[summary.type] || summary.type || "结算";
  const parts = [`${label}：赢家 ${summary.winner_id || "-"}`];
  if (summary.loser_id) {
    parts.push(`点炮玩家 ${summary.loser_id}`);
  }
  if (summary.winning_tile) {
    parts.push(`胡牌牌 ${summary.winning_tile}`);
  }
  parts.push(`分数 ${formatScoreMap(summary.delta)}`);
  return parts.join("，");
}

function renderHand(state) {
  const viewer = (state.players || []).find((player) => player.player_id === playerId());
  const hand = viewer?.hand || [];
  if (viewer && $("autoSortHand").checked !== viewer.auto_sort_hand) {
    $("autoSortHand").checked = viewer.auto_sort_hand;
  }
  $("hand").innerHTML = "";
  hand.forEach((tile, index) => {
    const button = document.createElement("button");
    button.className = "tile";
    button.textContent = tile;
    if (chiSelectedTiles.some((selected) => selected.index === index)) {
      button.classList.add("chi-selected");
    } else if (selectedTile === tile) {
      button.classList.add("selected");
    }
    button.onclick = () => handleHandTileClick(tile, index);
    $("hand").appendChild(button);
  });
}

function handleHandTileClick(tile, index) {
  if (chiMode) {
    toggleChiTile(tile, index);
    return;
  }
  selectedTile = tile;
  document.querySelectorAll(".tile").forEach((node) => node.classList.remove("selected"));
  renderHand(latestState);
}

async function toggleChiTile(tile, index) {
  const existingIndex = chiSelectedTiles.findIndex((selected) => selected.index === index);
  if (existingIndex >= 0) {
    chiSelectedTiles.splice(existingIndex, 1);
    showMessage(`吃牌选择中：${chiSelectedTiles.map((selected) => selected.tile).join("、") || "未选择"}`);
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
    showMessage(`已选择 ${tile}，请再点击一张用于吃牌的手牌。`);
    return;
  }

  const claimedTile = latestState?.last_discard?.tile || latestState?.pending_peng?.tile;
  if (!claimedTile) {
    resetChiMode();
    throw new Error("当前没有可吃的弃牌。");
  }

  const tiles = [claimedTile, ...chiSelectedTiles.map((selected) => selected.tile)];
  if (!isValidChiSelection(tiles)) {
    chiSelectedTiles = [];
    renderHand(latestState);
    showMessage("这两张牌不能吃，请重新选择两张同花色连续的手牌。");
    return;
  }

  resetChiMode();
  await sendAction({ type: "chi", tiles });
}

function isValidChiSelection(tiles) {
  if (tiles.length !== 3) {
    return false;
  }
  const parsedTiles = tiles.map(parseTileText);
  if (parsedTiles.some((tile) => !tile)) {
    return false;
  }
  const suit = parsedTiles[0].suit;
  if (!parsedTiles.every((tile) => tile.suit === suit)) {
    return false;
  }
  const ranks = parsedTiles.map((tile) => tile.rank).sort((a, b) => a - b);
  return ranks[1] === ranks[0] + 1 && ranks[2] === ranks[1] + 1;
}

function parseTileText(tileText) {
  const match = /^([1-9])([万筒条])$/.exec(tileText);
  if (!match) {
    return null;
  }
  return { rank: Number(match[1]), suit: match[2] };
}

function resetChiMode() {
  chiMode = false;
  chiSelectedTiles = [];
  renderHand(latestState);
}

function renderPlayers(state) {
  $("players").innerHTML = "";
  (state.players || []).forEach((player) => {
    const div = document.createElement("div");
    const melds = (player.melds || [])
      .map((meld) => `${meld.type}[${(meld.tiles || []).join("、")}]`)
      .join(" ");
    const tags = [];
    if (player.is_host) {
      tags.push("房主");
    }
    if (player.ready) {
      tags.push("已准备");
    }
    div.textContent = `${player.player_id} ${player.name} ${tags.join(" ")} 手牌:${player.hand_count} 弃牌:${(player.discard_pile || []).join("、") || "-"} 副露:${melds || "-"}`;
    $("players").appendChild(div);
  });
}

function renderNextGameButtons(state) {
  const isFinished = state.status === "finished";
  const isWaiting = state.status === "waiting";
  const isHost = state.host_player_id === playerId();
  $("readyNextGame").disabled = !(isWaiting || isFinished) || (isFinished && isHost);
  $("restartGame").disabled = !isFinished || !isHost;
}

function renderClaimHint(state) {
  const pending = state.pending_peng;
  if (!pending) {
    return "-";
  }
  if (pending.sealed) {
    return `有人打出 ${pending.tile}，但你被封印，不能碰`;
  }
  if (pending.can_peng) {
    return `有人打出 ${pending.tile}，你可以碰；如果是下家且有顺子，也可以点吃牌后选两张手牌`;
  }
  return `有人打出 ${pending.tile}，等待吃碰杠响应`;
}

function renderSkills(state) {
  const viewer = (state.players || []).find((player) => player.player_id === playerId());
  $("skills").textContent = viewer?.skills?.join("、") || "-";
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
bind("startGame", startGame);
bind("readyNextGame", readyNextGame);
bind("restartGame", restartGame);
bind("connectWs", connectWebSocket);
bind("refreshState", refreshState);
bind("showRules", showRules);
bind("drawTile", () => showMessage("摸牌已由服务端在轮到你时自动完成。"));
bind("discardTile", () => {
  if (!selectedTile) {
    throw new Error("请先点击选择一张手牌");
  }
  return sendAction({ type: "discard", tile: selectedTile });
});
bind("pengTile", () => sendAction({ type: "peng" }));
bind("chiTile", () => {
  if (!latestState?.last_discard && !latestState?.pending_peng) {
    throw new Error("当前没有可吃的弃牌。");
  }
  chiMode = true;
  chiSelectedTiles = [];
  renderHand(latestState);
  showMessage("吃牌模式：请点击两张自己的手牌。");
});
bind("gangTile", () => {
  const tile = $("gangTileValue").value.trim();
  if (!tile) {
    throw new Error("请填写要杠的牌，例如：1万");
  }
  return sendAction({ type: "gang", gang_type: $("gangType").value, tile });
});
bind("passPeng", () => sendAction({ type: "pass_peng" }));
bind("declareHu", () => sendAction({ type: "hu" }));
bind("usePeekWall", () => sendAction({ type: "use_skill", skill_id: "peek_wall", params: {} }));
bind("useSealPeng", () => {
  const target = $("sealPengTarget").value.trim();
  if (!target) {
    throw new Error("请先填写要封印的玩家 ID");
  }
  return sendAction({
    type: "use_skill",
    skill_id: "seal_peng",
    params: { target_player_id: target },
  });
});
$("autoSortHand").onchange = async () => {
  try {
    await setAutoSortHand($("autoSortHand").checked);
  } catch (error) {
    showMessage(error.message);
  }
};

window.addEventListener("beforeunload", () => {
  if (socket) {
    socket.close();
  }
});

$("closeRules").onclick = closeRules;
$("rulesModal").onclick = (event) => {
  if (event.target === $("rulesModal")) {
    closeRules();
  }
};
