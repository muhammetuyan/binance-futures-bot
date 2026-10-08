from __future__ import annotations

import logging
import ctypes
import json
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import Settings
from .engine import TradingEngine
from .exchange.binance_futures import BinanceFuturesClient
from .exchange.paper import PaperBroker
from .store import RuntimeStore


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("atlas.service")
RUNTIME_DIR = Settings.load().runtime_dir
PROFILE_PATH = RUNTIME_DIR / "connection.json"
SECRET_PATH = RUNTIME_DIR / "binance_credentials.dpapi"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Güvenli API anahtarı kaydı Windows DPAPI gerektiriyor")
    source = ctypes.create_string_buffer(data)
    source_blob = _DataBlob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    result_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    local_free = ctypes.windll.kernel32.LocalFree
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_wchar_p, ctypes.c_void_p,
                                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                         ctypes.POINTER(_DataBlob)]
    crypt32.CryptProtectData.restype = ctypes.c_int
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                           ctypes.POINTER(_DataBlob)]
    crypt32.CryptUnprotectData.restype = ctypes.c_int
    local_free.argtypes = [ctypes.c_void_p]
    api = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    if decrypt:
        ok = api(ctypes.byref(source_blob), None, None, None, None, 0, ctypes.byref(result_blob))
    else:
        ok = api(ctypes.byref(source_blob), "Atlas Trade API credentials", None, None, None, 0, ctypes.byref(result_blob))
    if not ok:
        raise RuntimeError("Windows güvenli anahtar kasası açılamadı")
    try:
        return ctypes.string_at(result_blob.pbData, result_blob.cbData)
    finally:
        local_free(result_blob.pbData)


def _read_saved_credentials() -> tuple[str, str] | None:
    if not SECRET_PATH.exists():
        return None
    value = json.loads(_dpapi(SECRET_PATH.read_bytes(), decrypt=True).decode("utf-8"))
    key, secret = value.get("api_key"), value.get("api_secret")
    return (key, secret) if isinstance(key, str) and isinstance(secret, str) and key and secret else None


def _save_credentials(api_key: str, api_secret: str) -> None:
    encrypted = _dpapi(json.dumps({"api_key": api_key, "api_secret": api_secret}).encode("utf-8"), decrypt=False)
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRET_PATH.write_bytes(encrypted)


def _load_startup_mode() -> None:
    """Enable live mode on restart only when the local encrypted profile is intact."""
    try:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        if profile.get("mode") != "live":
            return
        credentials = _read_saved_credentials()
        if not credentials:
            raise RuntimeError("Şifreli API anahtarı bulunamadı")
        os.environ.update({"ATLAS_MODE": "live", "ATLAS_TESTNET": "false", "ATLAS_DRY_RUN": "false",
                           "ATLAS_ALLOW_LIVE": "I_UNDERSTAND_THE_RISK", "BINANCE_API_KEY": credentials[0],
                           "BINANCE_API_SECRET": credentials[1]})
    except FileNotFoundError:
        return
    except Exception:
        logger.exception("Kaydedilmiş Live bağlantısı güvenli biçimde açılamadı; Paper modunda başlatılıyor")
        os.environ.update({"ATLAS_MODE": "paper", "ATLAS_DRY_RUN": "true"})


_load_startup_mode()
settings = Settings.load()
store = RuntimeStore(settings.runtime_dir)
stop_event = threading.Event()
engine_thread: threading.Thread | None = None
engine: TradingEngine | None = None
pending_live: dict[str, tuple[str, str, float]] = {}
pending_lock = threading.Lock()


class LiveCheckRequest(BaseModel):
    api_key: str = ""
    api_secret: str = ""


class LiveActivateRequest(BaseModel):
    token: str
    acknowledged: bool


def _live_client(api_key: str, api_secret: str) -> tuple[Settings, BinanceFuturesClient]:
    candidate = replace(settings, mode="live", testnet=False, dry_run=False,
                        trading_base_url="https://fapi.binance.com", api_key=api_key, api_secret=api_secret)
    client = BinanceFuturesClient(candidate)
    client.sync_time()
    permissions = client.get_api_key_restrictions()
    if not permissions.get("enableFutures"):
        raise RuntimeError("Bu API anahtarında Binance Futures işlem iznini açın")
    if permissions.get("enableWithdrawals"):
        raise RuntimeError("Güvenlik için API anahtarındaki para çekme iznini kapatın")
    account = client._signed_with_fallback("GET", "/fapi/v3/account", "/fapi/v2/account")
    if account.get("canTrade") is False:
        raise RuntimeError("Bu Binance Futures API anahtarında işlem izni kapalı")
    snapshot = client.get_account_snapshot()
    if snapshot["equity"] <= 0 or snapshot["available_balance"] < candidate.minimum_margin_usdt:
        raise RuntimeError("Futures hesabında yeterli kullanılabilir USDT bulunamadı")
    return candidate, client


@asynccontextmanager
async def lifespan(_: FastAPI):
    global engine_thread, engine
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
    current = store.read_status()
    current["remote_access"] = store._read_json(settings.runtime_dir / "remote_access.json", {})
    current["live_access"] = {"active": settings.mode == "live", "credentials_configured": SECRET_PATH.exists(),
                               "platform": "Windows güvenli kasa" if os.name == "nt" else "desteklenmiyor"}
    return current


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


@app.post("/api/live/check")
def check_live_access(payload: LiveCheckRequest, request: Request) -> dict[str, object]:
    _require_local(request)
    if request.headers.get("x-atlas-control") != "1":
        raise HTTPException(status_code=403, detail="Dashboard doğrulaması gerekli")
    api_key, api_secret = payload.api_key.strip(), payload.api_secret.strip()
    if not api_key and not api_secret:
        try:
            saved = _read_saved_credentials()
        except Exception:
            raise HTTPException(status_code=400, detail="Kaydedilmiş anahtar okunamadı; yenisini girin") from None
        if saved:
            api_key, api_secret = saved
    if not api_key or not api_secret:
        raise HTTPException(status_code=400, detail="Binance API key ve secret gerekli")
    try:
        _, candidate = _live_client(api_key, api_secret)
        positions = candidate.get_positions()
    except Exception as exc:
        # Binance errors can contain request diagnostics; never forward those verbatim.
        safe_details = ("API anahtarında", "API anahtarındaki", "Futures hesabında")
        message = str(exc) if isinstance(exc, RuntimeError) and str(exc).startswith(safe_details) else "Binance bağlantısı kurulamadı. API izinlerini ve IP kısıtını kontrol edin."
        raise HTTPException(status_code=400, detail=message) from None
    if positions:
        raise HTTPException(status_code=409, detail="Bu Futures hesabında açık pozisyon var. Önce onları güvenli biçimde kapatın.")
    token = secrets.token_urlsafe(32)
    with pending_lock:
        pending_live[token] = (api_key, api_secret, time.monotonic() + 600)
    return {"ok": True, "token": token, "equity": round(candidate.get_account_snapshot()["equity"], 2),
            "saved": SECRET_PATH.exists(), "message": "API bağlantısı ve Futures hesabı doğrulandı; henüz emir gönderilmedi."}


@app.post("/api/live/activate")
def activate_live(payload: LiveActivateRequest, request: Request) -> dict[str, object]:
    global settings
    _require_local(request)
    if request.headers.get("x-atlas-control") != "1":
        raise HTTPException(status_code=403, detail="Dashboard doğrulaması gerekli")
    if not payload.acknowledged:
        raise HTTPException(status_code=400, detail="Gerçek para riski ayrıca onaylanmalı")
    with pending_lock:
        item = pending_live.pop(payload.token, None)
    if not item or item[2] < time.monotonic():
        raise HTTPException(status_code=400, detail="Onay süresi doldu; Binance bağlantısını yeniden doğrulayın")
    if engine is None:
        raise HTTPException(status_code=503, detail="Bot motoru hazır değil")
    api_key, api_secret, _ = item
    try:
        candidate, client = _live_client(api_key, api_secret)
        if engine.broker.get_positions():
            raise RuntimeError("Paper hesabında açık pozisyon var; geçiş engellendi")
        store.write_control(paused=True)
        _save_credentials(api_key, api_secret)
        PROFILE_PATH.write_text(json.dumps({"mode": "live"}), encoding="utf-8")
        os.environ.update({"ATLAS_MODE": "live", "ATLAS_TESTNET": "false", "ATLAS_DRY_RUN": "false",
                           "ATLAS_ALLOW_LIVE": "I_UNDERSTAND_THE_RISK", "BINANCE_API_KEY": api_key,
                           "BINANCE_API_SECRET": api_secret})
        settings = candidate
        engine.request_reconfigure(candidate, client)
    except Exception as exc:
        store.write_control(paused=True)
        os.environ.update({"ATLAS_MODE": "paper", "ATLAS_DRY_RUN": "true"})
        os.environ.pop("ATLAS_ALLOW_LIVE", None)
        PROFILE_PATH.write_text(json.dumps({"mode": "paper"}), encoding="utf-8")
        message = str(exc) if "Paper hesabında" in str(exc) else "Live etkinleştirilemedi; bot Paper modunda ve duraklatılmış durumda."
        raise HTTPException(status_code=409, detail=message) from None
    return {"ok": True, "mode": "LIVE", "message": "Live mod onaylandı. Bot bir sonraki döngüde gerçek hesapla çalışmaya başlayacak."}


def main() -> None:
    # This API is loopback-only. Do not reinterpret browser-supplied forwarded
    # headers as the client address; the dashboard proxy is the actual client.
    uvicorn.run(app, host="127.0.0.1", port=8788, log_level="info", proxy_headers=False)


if __name__ == "__main__":
    main()
