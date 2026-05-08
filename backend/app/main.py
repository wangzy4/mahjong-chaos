from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="老千麻将后端接口",
        summary="技能麻将调试原型的 HTTP 与 WebSocket 服务",
        description=(
            "这是朋友娱乐用“技能麻将”项目的后端接口文档。"
            "当前后端负责房间管理、服务端权威游戏状态、摸牌出牌、吃碰杠胡、技能使用和公开状态脱敏。"
        ),
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get(
        "/health",
        summary="健康检查",
        description="用于确认后端服务是否正在运行。",
        tags=["系统"],
    )
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)

    return app


app = create_app()
