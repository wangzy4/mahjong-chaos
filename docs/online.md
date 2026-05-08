# 联网对战说明

## 架构

当前版本使用 FastAPI 提供 HTTP 接口和 WebSocket 接口，房间与牌局状态暂时保存在服务端内存中。客户端只发送“我要做什么”的动作意图，真正的摸牌、出牌、吃碰杠胡、技能和计分都由服务端校验并执行。

## HTTP API

- `GET /health`：健康检查。
- `POST /rooms`：创建房间，创建者自动成为房主。
- `POST /rooms/{room_id}/join`：加入房间。同一个 `player_id` 重复加入视为重连/刷新昵称。
- `POST /rooms/{room_id}/ready`：准备或取消准备，请求体为 `{"player_id": "p1", "ready": true}`。兼容旧用法，缺省 `ready=true`。
- `POST /rooms/{room_id}/start`：房主开始游戏。当前兼容旧调试流程；如果房间已经有人点过准备，则会要求所有玩家都准备。
- `POST /rooms/{room_id}/restart`：本局结束后房主重新开始。
- `GET /rooms/{room_id}/state?viewer_id=p1`：获取针对某个玩家脱敏后的 public view。
- `POST /rooms/{room_id}/actions`：HTTP 调试动作入口。

## WebSocket 协议

新协议路径：

```text
/ws/{room_id}/{player_id}
```

连接成功后，服务端立即发送：

```json
{
  "type": "state",
  "data": {}
}
```

客户端发送动作：

```json
{
  "type": "discard",
  "payload": {
    "tile": "3万"
  }
}
```

支持动作：

- `discard`
- `chi`
- `peng`
- `gang`
- `hu`
- `hu_on_discard`
- `use_skill`
- `pass`

服务端消息：

- `{"type": "state", "data": {...}}`：状态更新。
- `{"type": "error", "message": "..."}`：只发给非法操作的玩家。
- `{"type": "system", "message": "..."}`：玩家连接/断开等系统提示。

旧调试路径 `/ws/rooms/{room_id}?viewer_id=p1` 暂时保留，用于兼容已有测试和旧页面。

## Public View 脱敏规则

- 玩家只能看到自己的手牌。
- 其他玩家只显示手牌数量。
- 牌墙只显示剩余数量，不公开具体牌。
- 暗杠对其他玩家显示为 `?`。
- 私有技能结果只出现在对应玩家自己的 `private_data` 中。
- 计分、公开副露、弃牌堆和公开 action log 可以被同桌玩家看到。

## 服务端权威原则

客户端不能提交完整 `GameState`，也不能提交手牌、牌墙、分数等隐藏状态。服务端只接受动作意图，并在服务端完成规则校验、状态变更、计分和广播。

## 断线重连

玩家断线后不会被移出房间，房间和牌局仍保存在内存中。同一个 `player_id` 再次连接 `/ws/{room_id}/{player_id}` 后，会立即收到当前自己的 public view。

## 当前限制

- 使用内存存储，服务重启后房间消失。
- 没有账号系统，仅用 `player_id + name` 简化身份。
- 没有房间密码。
- 没有观战模式。
- 暂不支持跨服务器多实例。
- 暂不支持持久化战绩。
- 同优先级抢牌仍按第一个有效请求处理。
