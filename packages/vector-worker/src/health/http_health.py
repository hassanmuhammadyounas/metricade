"""
GET /health → {status, last_inference_ms, queue_depth, version}
Serves on port 8080 (Fly.io internal health check endpoint).
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .. import subscriber


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    async def health():
        stats = subscriber.get_stats()
        return JSONResponse({
            "status": "ok",
            "last_inference_ms": round(stats["last_inference_ms"], 2),
            "queue_depth": stats["queue_depth"],
            "version": "1.0.0",
        })

    return app
