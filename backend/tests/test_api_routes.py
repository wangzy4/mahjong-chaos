import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes import room_manager
from backend.app.main import create_app
from core.mahjong.player import Meld
from core.mahjong.tile import Tile


def test_create_room_api() -> None:
    client = TestClient(create_app())

    response = client.post("/rooms", json={"player_id": "p1", "name": "Alice"})

    assert response.status_code == 201
    body = response.json()
    assert body["room_id"]
    assert body["status"] == "waiting"


def test_create_room_api_with_api_prefix() -> None:
    client = TestClient(create_app())

    response = client.post("/api/rooms", json={"player_id": "p1", "name": "Alice"})

    assert response.status_code == 201
    body = response.json()
    assert body["room_id"]
    assert body["players"][0]["player_id"] == "p1"


def test_join_room_api() -> None:
    client = TestClient(create_app())
    room_id = client.post("/rooms", json={"player_id": "p1", "name": "Alice"}).json()["room_id"]

    response = client.post(
        f"/rooms/{room_id}/join",
        json={"player_id": "p2", "name": "Bob"},
    )

    assert response.status_code == 200
    assert response.json()["players"][-1] == {
        "player_id": "p2",
        "name": "Bob",
        "ready": False,
        "is_host": False,
        "connected": False,
    }


def test_ready_api_marks_waiting_player_ready() -> None:
    client = TestClient(create_app())
    room_id = client.post("/rooms", json={"player_id": "p1", "name": "Alice"}).json()["room_id"]

    response = client.post(f"/rooms/{room_id}/ready", json={"player_id": "p1", "ready": True})

    assert response.status_code == 200
    body = response.json()
    assert body["ready_player_ids"] == ["p1"]
    assert body["players"][0]["ready"] is True


def test_start_room_api_requires_all_ready_once_ready_flow_started() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/ready", json={"player_id": "p1", "ready": True})

    response = client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})

    assert response.status_code == 400
    assert "还有玩家未准备" in response.json()["detail"]


def test_start_room_api_succeeds_when_all_players_ready() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    for player_id in ("p1", "p2", "p3", "p4"):
        client.post(f"/rooms/{room_id}/ready", json={"player_id": player_id, "ready": True})

    response = client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})

    assert response.status_code == 200
    assert response.json()["status"] == "playing"


def test_start_room_api_requires_at_least_two_players() -> None:
    client = TestClient(create_app())
    room_id = client.post("/rooms", json={"player_id": "p1", "name": "Alice"}).json()["room_id"]

    response = client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})

    assert response.status_code == 400
    assert "至少需要 2 名玩家" in response.json()["detail"]


def test_start_room_api_under_four_players_requires_confirmation() -> None:
    client = TestClient(create_app())
    room_id = client.post("/rooms", json={"player_id": "p1", "name": "Alice"}).json()["room_id"]
    client.post(f"/rooms/{room_id}/join", json={"player_id": "p2", "name": "Bob"})

    response = client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})

    assert response.status_code == 400
    assert "需要房主确认" in response.json()["detail"]


def test_start_room_api_under_four_players_success_after_confirmation() -> None:
    client = TestClient(create_app())
    room_id = client.post("/rooms", json={"player_id": "p1", "name": "Alice"}).json()["room_id"]
    client.post(f"/rooms/{room_id}/join", json={"player_id": "p2", "name": "Bob"})

    response = client.post(
        f"/rooms/{room_id}/start",
        json={"player_id": "p1", "confirm_underfilled": True},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "playing"


def test_start_room_api_when_room_is_full() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)

    response = client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})

    assert response.status_code == 200
    assert response.json()["status"] == "playing"


def test_ready_next_game_api_for_non_host_after_finished() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    room.status = "finished"
    assert room.game_state is not None
    room.game_state.phase = "finished"

    response = client.post(f"/rooms/{room_id}/ready", json={"player_id": "p2"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "finished"
    assert body["ready_player_ids"] == ["p2"]
    p2_view = next(player for player in body["players"] if player["player_id"] == "p2")
    assert p2_view["ready"] is True


def test_restart_game_api_requires_all_non_hosts_ready() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    room.status = "finished"
    assert room.game_state is not None
    room.game_state.phase = "finished"
    client.post(f"/rooms/{room_id}/ready", json={"player_id": "p2"})
    client.post(f"/rooms/{room_id}/ready", json={"player_id": "p3"})

    response = client.post(f"/rooms/{room_id}/restart", json={"player_id": "p1"})

    assert response.status_code == 400
    assert "还有玩家未准备：p4" in response.json()["detail"]


def test_restart_game_api_starts_new_round_when_all_non_hosts_ready() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    room.status = "finished"
    assert room.game_state is not None
    room.game_state.phase = "finished"
    client.post(f"/rooms/{room_id}/ready", json={"player_id": "p2"})
    client.post(f"/rooms/{room_id}/ready", json={"player_id": "p3"})
    client.post(f"/rooms/{room_id}/ready", json={"player_id": "p4"})

    response = client.post(f"/rooms/{room_id}/restart", json={"player_id": "p1"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "playing"
    assert body["ready_player_ids"] == []
    assert body["action_log"][-1]["type"] == "restart_game"


def test_restart_game_api_under_four_players_requires_confirmation() -> None:
    client = TestClient(create_app())
    room_id = client.post("/rooms", json={"player_id": "p1", "name": "Alice"}).json()["room_id"]
    client.post(f"/rooms/{room_id}/join", json={"player_id": "p2", "name": "Bob"})
    client.post(
        f"/rooms/{room_id}/start",
        json={"player_id": "p1", "confirm_underfilled": True},
    )
    room = room_manager.get_room(room_id)
    room.status = "finished"
    assert room.game_state is not None
    room.game_state.phase = "finished"
    client.post(f"/rooms/{room_id}/ready", json={"player_id": "p2"})

    response = client.post(f"/rooms/{room_id}/restart", json={"player_id": "p1"})

    assert response.status_code == 400
    assert "需要房主确认" in response.json()["detail"]


def test_restart_game_api_under_four_players_success_after_confirmation() -> None:
    client = TestClient(create_app())
    room_id = client.post("/rooms", json={"player_id": "p1", "name": "Alice"}).json()["room_id"]
    client.post(f"/rooms/{room_id}/join", json={"player_id": "p2", "name": "Bob"})
    client.post(
        f"/rooms/{room_id}/start",
        json={"player_id": "p1", "confirm_underfilled": True},
    )
    room = room_manager.get_room(room_id)
    room.status = "finished"
    assert room.game_state is not None
    room.game_state.phase = "finished"
    client.post(f"/rooms/{room_id}/ready", json={"player_id": "p2"})

    response = client.post(
        f"/rooms/{room_id}/restart",
        json={"player_id": "p1", "confirm_underfilled": True},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "playing"


def test_get_room_state_api_returns_public_view() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})

    response = client.get(f"/rooms/{room_id}/state", params={"viewer_id": "p1"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "playing"
    assert body["players"][0]["hand"]
    assert "hand" not in body["players"][1]
    assert body["phase"] == "skill_selection"
    assert len(body["players"][0]["skill_candidates"]) == 3
    assert body["players"][0]["skills"] == []
    assert body["players"][1]["skills"] == []
    assert "wall" not in body
    assert body["can_hu"] is False
    assert body["current_turn_has_drawn"] is True


def test_get_missing_room_returns_404() -> None:
    client = TestClient(create_app())

    response = client.get("/rooms/missing/state", params={"viewer_id": "p1"})

    assert response.status_code == 404


def test_frontend_index_is_served_for_share_link() -> None:
    client = TestClient(create_app())

    response = client.get("/?room_id=TEST01")

    assert response.status_code == 200
    assert "老千麻将" in response.text


def test_frontend_app_uses_relative_api_and_dynamic_websocket_url() -> None:
    client = TestClient(create_app())

    response = client.get("/app.js")

    assert response.status_code == 200
    assert "/api" in response.text
    assert 'window.location.protocol === "https:" ? "wss" : "ws"' in response.text
    assert "localhost" not in response.text
    assert "127.0.0.1" not in response.text


def test_action_api_can_use_peek_wall() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    assert room.game_state is not None
    room.game_state.phase = "playing"
    room.game_state.players["p1"].skills = ["astrology", "wish_tile"]

    response = client.post(
        f"/rooms/{room_id}/actions",
        json={"player_id": "p1", "type": "use_skill", "skill_id": "astrology"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["private_data"]["private_skill_results"][-1]["tiles"]) == 4
    assert body["action_log"][-1]["type"] == "use_skill"


def test_other_players_cannot_see_private_peek_wall_result() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    assert room.game_state is not None
    room.game_state.players["p1"].skills = ["peek_wall"]
    client.post(
        f"/rooms/{room_id}/actions",
        json={"player_id": "p1", "type": "use_skill", "skill_id": "peek_wall"},
    )

    response = client.get(f"/rooms/{room_id}/state", params={"viewer_id": "p2"})

    assert response.status_code == 200
    body = response.json()
    assert body["private_data"] == {}
    assert "hand" not in body["players"][0]
    assert body["players"][0]["skills"] == []


def test_public_action_log_filters_sensitive_keys() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    assert room.game_state is not None
    room.game_state.action_log.append(
        {
            "type": "debug",
            "player_id": "p1",
            "hand": ["1万"],
            "wall": ["2万"],
            "private_note": "secret",
        }
    )

    response = client.get(f"/rooms/{room_id}/state", params={"viewer_id": "p2"})

    assert response.status_code == 200
    leaked_log = response.json()["action_log"][-1]
    assert leaked_log == {"type": "debug", "player_id": "p1"}


def test_draw_action_is_rejected_because_draw_is_automatic() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})

    response = client.post(
        f"/rooms/{room_id}/actions",
        json={"player_id": "p1", "type": "draw", "tile": "1万"},
    )

    assert response.status_code == 400
    assert "摸牌已改为自动进行" in response.json()["detail"]


def test_discard_action_enters_pending_peng_phase() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    assert room.game_state is not None
    room.game_state.phase = "playing"
    before = client.get(f"/rooms/{room_id}/state", params={"viewer_id": "p1"}).json()
    tile = before["players"][0]["hand"][0]

    response = client.post(
        f"/rooms/{room_id}/actions",
        json={"player_id": "p1", "type": "discard", "tile": tile},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_player_id"] == "p2"
    assert body["current_turn_has_drawn"] is False
    assert body["pending_peng"]["tile"] == tile
    assert body["pending_peng"]["next_player_id"] == "p2"
    assert body["last_discard"]["available_for_claim"] is True
    assert body["action_log"][-1]["type"] == "discard"


def test_peng_action_records_melds_in_public_view() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    assert room.game_state is not None
    room.game_state.phase = "playing"
    discard = Tile("wan", 1)
    room.game_state.players["p1"].hand = [discard, *room.game_state.players["p1"].hand[:13]]
    room.game_state.players["p2"].hand = [
        discard,
        discard,
        *without_tile(room.game_state.players["p2"].hand, discard)[:11],
    ]
    room.game_state.players["p3"].hand = without_tile(room.game_state.players["p3"].hand, discard)
    room.game_state.players["p4"].hand = without_tile(room.game_state.players["p4"].hand, discard)

    client.post(
        f"/rooms/{room_id}/actions",
        json={"player_id": "p1", "type": "discard", "tile": "1万"},
    )
    response = client.post(f"/rooms/{room_id}/actions", json={"player_id": "p2", "type": "peng"})

    assert response.status_code == 200
    body = response.json()
    assert body["current_player_id"] == "p2"
    assert body["pending_peng"] is None
    assert body["last_discard"] is None
    p2_view = next(player for player in body["players"] if player["player_id"] == "p2")
    assert p2_view["melds"] == [
        {
            "type": "peng",
            "tiles": ["1万", "1万", "1万"],
            "from_player_id": "p1",
            "claimed_tile": "1万",
            "concealed": False,
        }
    ]


@pytest.mark.skip(reason="旧 seal_peng 技能已从新 12 技能池停用")
def test_seal_peng_skill_blocks_next_peng_chance() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    assert room.game_state is not None
    room.game_state.players["p1"].skills = ["seal_peng"]
    discard = Tile("wan", 1)
    room.game_state.players["p1"].hand = [discard, *room.game_state.players["p1"].hand[:13]]
    room.game_state.players["p2"].hand = [
        discard,
        discard,
        Tile("wan", 2),
        Tile("wan", 2),
        Tile("wan", 2),
        Tile("wan", 3),
        Tile("wan", 3),
        Tile("wan", 3),
        Tile("wan", 4),
        Tile("wan", 4),
        Tile("tong", 5),
    ]

    seal_response = client.post(
        f"/rooms/{room_id}/actions",
        json={
            "player_id": "p1",
            "type": "use_skill",
            "skill_id": "seal_peng",
            "params": {"target_player_id": "p2"},
        },
    )
    client.post(
        f"/rooms/{room_id}/actions",
        json={"player_id": "p1", "type": "discard", "tile": "1万"},
    )
    peng_response = client.post(
        f"/rooms/{room_id}/actions",
        json={"player_id": "p2", "type": "peng"},
    )

    assert seal_response.status_code == 200
    assert peng_response.status_code == 200
    body = peng_response.json()
    p2_view = next(player for player in body["players"] if player["player_id"] == "p2")
    assert p2_view["melds"] == []
    assert not body["sealed_peng"]
    assert body["pending_peng"]["tile"] == "1万"
    assert body["action_log"][-1] == {
        "type": "pass_peng",
        "player_id": "p2",
        "reason": "sealed_peng",
    }


def test_concealed_gang_is_hidden_from_other_players_public_view() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    assert room.game_state is not None
    room.game_state.phase = "playing"
    tile = Tile("wan", 1)
    room.game_state.players["p1"].hand = [
        tile,
        tile,
        tile,
        tile,
        *room.game_state.players["p1"].hand[:10],
    ]

    owner_response = client.post(
        f"/rooms/{room_id}/actions",
        json={"player_id": "p1", "type": "gang", "gang_type": "concealed_gang", "tile": "1万"},
    )
    other_response = client.get(f"/rooms/{room_id}/state", params={"viewer_id": "p2"})

    assert owner_response.status_code == 200
    owner_meld = owner_response.json()["players"][0]["melds"][0]
    assert owner_meld["type"] == "concealed_gang"
    assert owner_meld["tiles"] == ["1万", "1万", "1万", "1万"]
    assert other_response.status_code == 200
    other_meld = other_response.json()["players"][0]["melds"][0]
    assert other_meld["type"] == "hidden_gang"
    assert other_meld["tiles"] == ["?", "?", "?", "?"]
    assert "tile" not in other_response.json()["action_log"][-2]


def test_auto_sort_hand_setting_api() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})

    response = client.post(
        f"/rooms/{room_id}/settings/auto-sort-hand",
        json={"player_id": "p1", "enabled": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["players"][0]["auto_sort_hand"] is False
    assert body["action_log"][-1] == {
        "type": "set_auto_sort_hand",
        "player_id": "p1",
        "enabled": False,
    }


def test_hu_notice_is_visible_to_winner_and_table_players() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    assert room.game_state is not None
    room.game_state.players["p1"].hand = [
        Tile("wan", 1),
        Tile("wan", 2),
        Tile("wan", 3),
        Tile("wan", 4),
        Tile("wan", 5),
        Tile("wan", 6),
        Tile("tong", 2),
        Tile("tong", 3),
        Tile("tong", 4),
        Tile("tiao", 7),
        Tile("tiao", 8),
        Tile("tiao", 9),
        Tile("wan", 9),
        Tile("wan", 9),
    ]

    winner_response = client.post(
        f"/rooms/{room_id}/actions",
        json={"player_id": "p1", "type": "hu"},
    )
    table_response = client.get(f"/rooms/{room_id}/state", params={"viewer_id": "p2"})

    assert winner_response.status_code == 200
    winner_notice = winner_response.json()["hu_notice"]
    assert winner_notice == {
        "winner_id": "p1",
        "message": "玩家 p1 胡了",
        "self_message": "恭喜你，胡了！",
    }
    assert table_response.status_code == 200
    table_notice = table_response.json()["hu_notice"]
    assert table_notice == {
        "winner_id": "p1",
        "message": "玩家 p1 胡了",
        "self_message": None,
    }


def test_ron_hu_uses_last_discard_and_existing_melds() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    assert room.game_state is not None
    room.game_state.phase = "playing"
    for player in room.game_state.players.values():
        player.skills = []
    win_tile = Tile("wan", 9)
    room.game_state.players["p1"].hand = [win_tile, *room.game_state.players["p1"].hand[:13]]
    room.game_state.players["p2"].melds = [
        Meld(
            type="chi",
            tiles=[Tile("wan", 1), Tile("wan", 2), Tile("wan", 3)],
            from_player_id="p1",
            claimed_tile=Tile("wan", 3),
        )
    ]
    room.game_state.players["p2"].hand = [
        Tile("wan", 4),
        Tile("wan", 5),
        Tile("wan", 6),
        Tile("tong", 2),
        Tile("tong", 3),
        Tile("tong", 4),
        Tile("tiao", 7),
        Tile("tiao", 8),
        Tile("tiao", 9),
        Tile("wan", 9),
    ]
    client.post(
        f"/rooms/{room_id}/actions",
        json={"player_id": "p1", "type": "discard", "tile": "9万"},
    )

    pending_view = client.get(f"/rooms/{room_id}/state", params={"viewer_id": "p2"}).json()
    response = client.post(f"/rooms/{room_id}/actions", json={"player_id": "p2", "type": "hu"})

    assert pending_view["can_hu"] is True
    assert response.status_code == 200
    body = response.json()
    assert body["winner_id"] == "p2"
    assert body["last_discard"] is None
    assert body["action_log"][-2] == {
        "type": "hu",
        "player_id": "p2",
        "win_type": "discard",
        "from_player_id": "p1",
        "claimed_tile": "9万",
    }
    assert body["action_log"][-1]["type"] == "score"
    assert body["settlement_summary"]["type"] == "discard"
    assert body["settlement_summary"]["label"] == "点炮胡"
    assert body["settlement_summary"]["winner_id"] == "p2"
    assert body["settlement_summary"]["loser_id"] == "p1"
    assert body["settlement_summary"]["winning_tile"] == "9万"
    assert body["settlement_summary"]["delta"] == {"p1": -6, "p2": 6, "p3": 0, "p4": 0}
    assert "玩家 p2 点炮胡" in body["settlement_summary"]["message"]


def test_websocket_sends_initial_room_state() -> None:
    client = TestClient(create_app())
    room_id = client.post("/rooms", json={"player_id": "p1", "name": "Alice"}).json()["room_id"]

    with client.websocket_connect(f"/ws/rooms/{room_id}?viewer_id=p1") as websocket:
        body = websocket.receive_json()

    assert body["room_id"] == room_id
    assert body["status"] == "waiting"


def test_websocket_reconnect_gets_latest_private_state() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    assert room.game_state is not None
    room.game_state.phase = "playing"
    room.game_state.players["p1"].skills = ["astrology", "wish_tile"]
    client.post(
        f"/rooms/{room_id}/actions",
        json={"player_id": "p1", "type": "use_skill", "skill_id": "astrology"},
    )

    with client.websocket_connect(f"/ws/rooms/{room_id}?viewer_id=p1") as websocket:
        body = websocket.receive_json()

    assert body["status"] == "playing"
    assert len(body["private_data"]["private_skill_results"][-1]["tiles"]) == 4


def test_new_websocket_sends_wrapped_initial_state() -> None:
    client = TestClient(create_app())
    room_id = client.post("/rooms", json={"player_id": "p1", "name": "Alice"}).json()["room_id"]

    with client.websocket_connect(f"/ws/{room_id}/p1") as websocket:
        body = websocket.receive_json()

    assert body["type"] == "state"
    assert body["data"]["room_id"] == room_id
    assert body["data"]["players"][0]["connected"] is True


def test_new_websocket_illegal_discard_returns_error() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})

    with client.websocket_connect(f"/ws/{room_id}/p2") as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "discard", "payload": {"tile": "1万"}})
        body = websocket.receive_json()

    assert body["type"] == "error"
    assert body["message"]


def test_new_websocket_discard_broadcasts_state() -> None:
    client = TestClient(create_app())
    room_id = create_full_room(client)
    client.post(f"/rooms/{room_id}/start", json={"player_id": "p1"})
    room = room_manager.get_room(room_id)
    assert room.game_state is not None
    room.game_state.phase = "playing"
    before = client.get(f"/rooms/{room_id}/state", params={"viewer_id": "p1"}).json()
    tile = before["players"][0]["hand"][0]

    with client.websocket_connect(f"/ws/{room_id}/p1") as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "discard", "payload": {"tile": tile}})
        body = websocket.receive_json()

    assert body["type"] == "state"
    assert body["data"]["action_log"][-1]["type"] == "discard"
    assert "hand" in body["data"]["players"][0]


def create_full_room(client: TestClient) -> str:
    room_id = client.post("/rooms", json={"player_id": "p1", "name": "Alice"}).json()["room_id"]
    client.post(f"/rooms/{room_id}/join", json={"player_id": "p2", "name": "Bob"})
    client.post(f"/rooms/{room_id}/join", json={"player_id": "p3", "name": "Carol"})
    client.post(f"/rooms/{room_id}/join", json={"player_id": "p4", "name": "Dave"})
    return room_id


def without_tile(tiles: list[Tile], tile: Tile) -> list[Tile]:
    return [hand_tile for hand_tile in tiles if hand_tile != tile]
