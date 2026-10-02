from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .engine import TradingEngine
from .exchange.binance_futures import BinanceFuturesClient
from .exchange.paper import PaperBroker
from .store import RuntimeStore


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
settings = Settings.load()
store = RuntimeStore(settings.runtime_dir)
stop_event = threading.Event()
engine_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global engine_thread
    market = BinanceFuturesClient(settings)
    broker = PaperBroker(settings, market) if settings.paper_mode else market
    engine = TradingEngine(settings, broker, store)
    engine_thread = threading.Thread(target=engine.run, args=(stop_event,), daemon=True, name="atlas-engine")
    engine_thread.start()
    yield
    stop_event.set()
    if engine_thread:
        engine_thread.join(timeout=5)


app = FastAPI(title="Atlas Trade API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _require_local(request: Request) -> None:
    host = request.client.host if request.client else ""
    origin = request.headers.get("origin")
    allowed_origins = {None, "http://localhost:3000", "http://127.0.0.1:3000"}
    if host not in {"127.0.0.1", "::1", "localhost"} or origin not in allowed_origins:
        raise HTTPException(status_code=403, detail="Bu kontrol yalnızca yerel dashboarddan kullanılabilir")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def status() -> dict[str, object]:
    return store.read_status()


@app.post("/api/control/pause")
def pause(request: Request) -> dict[str, object]:
    _require_local(request)
    store.write_control(paused=True)
    current = store.read_status()
    current.update({"state": "paused", "message": "Yeni işlem açma durduruldu"})
    store.write_status(current)
    return {"ok": True, "paused": True, "message": "Yeni işlem açma durduruldu"}


@app.post("/api/control/resume")
def resume(request: Request) -> dict[str, object]:
    _require_local(request)
    store.write_control(paused=False)
    current = store.read_status()
    current.update({"state": "starting", "message": "Bot yeniden başlatılıyor"})
    store.write_status(current)
    return {"ok": True, "paused": False, "message": "Bot devam ediyor"}


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8788, log_level="info")


if __name__ == "__main__":
    main()
