# Mahjong Chaos

Mahjong Chaos 是一个朋友娱乐用的“技能麻将”原型项目：在普通 4 人麻将流程上，加入每个玩家可以主动释放的开挂技能。技能可以影响摸牌、手牌、弃牌和结算。

项目采用服务端权威状态：客户端不能决定摸到什么牌，也不能修改隐藏状态。所有玩家操作都会逐步接入 action log 记录。

第一阶段目标是先做一个小而清晰、可测试的 Python 规则核心、最小 FastAPI 后端，以及一个丑但能玩的 Web 调试页面。

## 技术栈

- Python 3.11+
- FastAPI
- WebSocket
- pytest
- ruff
- 前端调试页使用简单 HTML + JavaScript

## 安装依赖

```powershell
cd mahjong-chaos
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## 运行测试

```powershell
python -m pytest
```

## 启动后端

```powershell
uvicorn backend.app.main:app --reload
```

健康检查：

```text
http://127.0.0.1:8000/health
```

## 启动前端调试页

另开一个终端：

```powershell
cd mahjong-chaos/frontend-debug
python -m http.server 5173
```

然后打开：

```text
http://127.0.0.1:5173
```

调试方式：

- 4 个玩家分别使用不同 `player_id` 和 `name`。
- 第一个玩家创建房间，把 `room_id` 给其他玩家。
- 其他玩家加入房间。
- 满 4 人后点击“开始游戏”。
- 点击“连接 WebSocket”接收实时状态。
- 点击自己的手牌后可以出牌。
- “使用窥视牌墙”会查看牌墙顶 3 张，只在自己的视图中显示。
