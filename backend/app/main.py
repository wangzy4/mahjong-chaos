import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"
FRONTEND_SOURCE_DIR = ROOT_DIR / "frontend"


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
    app.include_router(router, prefix="/api")

    frontend_dir = FRONTEND_DIST_DIR if FRONTEND_DIST_DIR.exists() else FRONTEND_SOURCE_DIR
    if frontend_dir.exists() and (frontend_dir / "index.html").exists():
        assets_dir = frontend_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_frontend(full_path: str) -> FileResponse:
            no_cache_headers = {
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            }
            requested_file = frontend_dir / full_path
            if full_path and requested_file.is_file():
                return FileResponse(requested_file, headers=no_cache_headers)
            return FileResponse(frontend_dir / "index.html", headers=no_cache_headers)

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )
