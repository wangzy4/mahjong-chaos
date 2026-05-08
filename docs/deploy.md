# 公网部署说明

## 目标形态

当前版本采用单服务部署：

1. FastAPI 提供 HTTP API。
2. FastAPI 提供 WebSocket。
3. 前端构建到 `frontend/dist`。
4. FastAPI 托管前端静态文件。
5. 最终只有一个公网 HTTPS 地址，例如 `https://mahjong-chaos.example.com`。

用户把 `https://公网域名/?room_id=房间号` 发到微信，朋友点开后输入昵称即可加入房间。

## 本地开发

后端：

```powershell
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

前端源码可以直接由后端托管，也可以单独开静态服务调试。公网版前端默认使用相对 `/api`，WebSocket 会根据当前页面协议自动选择 `ws://` 或 `wss://`。

## 构建前端

需要安装 Node.js。然后运行：

```powershell
cd frontend
npm run build
```

构建产物会输出到：

```text
frontend/dist/
```

## 单服务启动

构建前端后，在项目根目录启动：

```powershell
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

访问：

```text
http://127.0.0.1:8000
```

打开 `/?room_id=TEST01` 也会返回前端页面，不会 404。

## Docker 启动

```powershell
docker build -t mahjong-chaos .
docker run --rm -p 8000:8000 -e PORT=8000 mahjong-chaos
```

然后访问：

```text
http://127.0.0.1:8000
```

## Render 部署

仓库内提供了 `render.yaml`。在 Render 中连接 GitHub 仓库后选择 Blueprint 或 Docker Web Service。

部署后 Render 会提供一个 HTTPS 域名，例如：

```text
https://mahjong-chaos.onrender.com
```

前端会自动把 WebSocket 地址生成为：

```text
wss://mahjong-chaos.onrender.com/ws/{room_id}/{player_id}
```

## 分享房间

1. 打开公网网址。
2. 输入昵称。
3. 点击创建房间。
4. 页面会显示房间号和分享链接。
5. 点击复制房间链接。
6. 把链接发给朋友。
7. 朋友打开链接后，房间号会自动填入，只需要输入昵称并加入。

## 如何确认 WebSocket 是 WSS

公网 HTTPS 页面下，前端使用：

```js
const protocol = window.location.protocol === "https:" ? "wss" : "ws";
```

因此 HTTPS 页面会连接 `wss://当前域名/ws/...`。

可以在浏览器开发者工具的 Network 面板中过滤 `WS`，查看连接地址是否以 `wss://` 开头。

## 当前限制

- 房间保存在内存中，服务重启后房间会消失。
- 免费部署平台可能会休眠，休眠后房间也会丢失。
- 没有账号登录。
- 没有房间密码。
- 没有防刷和限流。
- 没有持久化战绩。
- 不支持多服务器实例共享房间。
- 当前版本适合朋友临时娱乐局。

后续如果需要长期稳定运行，建议接入 Redis 或数据库保存房间和连接状态。
