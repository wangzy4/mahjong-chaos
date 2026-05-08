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
- 公网页面使用简单 HTML + JavaScript，构建后由 FastAPI 托管

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

代码检查：

```powershell
python -m ruff check .
```

## 本地启动后端

```powershell
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：

```text
http://127.0.0.1:8000/health
```

## 公网版单服务页面

公网版前端位于 `frontend/`。构建后由 FastAPI 直接托管：

```powershell
cd frontend
npm run build
cd ..
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

然后打开：

```text
http://127.0.0.1:8000
```

前端 API 使用相对路径 `/api`，WebSocket 会根据页面协议自动选择：

- `http://` 页面使用 `ws://`
- `https://` 页面使用 `wss://`

因此部署到公网 HTTPS 域名后，不需要把地址改成 localhost 或局域网 IP。

## 旧调试页

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
- 4 个浏览器窗口分别填入 `p1`、`p2`、`p3`、`p4`，使用同一个 `room_id`。
- 每个玩家点击“准备下一局/准备”。
- 房主点击“开始游戏”。
- 点击“连接 WebSocket”接收实时状态。
- 点击自己的手牌后可以出牌。
- “使用窥视牌墙”会查看牌墙顶 3 张，只在自己的视图中显示。

更多联网协议说明见 `docs/online.md`。

## 技能选择

每局开始后会先进入技能选择阶段。每名玩家随机获得 3 个候选技能，只能自己看到；选择其中 2 个后等待其他玩家。所有人都完成选择后，游戏进入正式 `playing` 阶段。

技能说明见 `docs/skills.md`。技能相关测试可以直接运行：

```powershell
python -m pytest backend/tests/test_new_skill_system.py
```

## Docker 部署

```powershell
docker build -t mahjong-chaos .
docker run --rm -p 8000:8000 -e PORT=8000 mahjong-chaos
```

## 公网分享

部署到公网后，打开你的 HTTPS 域名，创建房间后页面会生成分享链接：

```text
https://你的域名/?room_id=房间号
```

把这个链接发到微信，朋友打开后会自动填入房间号，只需要输入昵称并加入。

部署细节见 `docs/deploy.md`。

## 当前公网版本限制

- 房间使用内存存储，服务重启后房间会消失。
- 免费部署平台可能休眠，休眠后房间会丢失。
- 暂无账号登录、房间密码、防刷和战绩持久化。
