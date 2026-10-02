from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class RuntimeStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.status_path = directory / "status.json"
        self.control_path = directory / "control.json"
        self.risk_state_path = directory / "risk_state.json"
        self._lock = threading.RLock()
        directory.mkdir(parents=True, exist_ok=True)
        if not self.control_path.exists():
            self.write_control(paused=False)

    def read_status(self) -> dict[str, Any]:
        return self._read_json(self.status_path, self.default_status())

    def write_status(self, status: dict[str, Any]) -> None:
        payload = dict(status)
        payload["updated_at"] = datetime.now(UTC).isoformat()
        self._atomic_write(self.status_path, payload)

    def read_control(self) -> dict[str, Any]:
        return self._read_json(self.control_path, {"paused": False})

    def write_control(self, paused: bool) -> None:
        self._atomic_write(
            self.control_path,
            {"paused": paused, "updated_at": datetime.now(UTC).isoformat()},
        )

    def read_risk_state(self) -> dict[str, Any]:
        return self._read_json(self.risk_state_path, {"day": None, "start_equity": 0.0})

    def write_risk_state(self, day: str, start_equity: float) -> None:
        self._atomic_write(
            self.risk_state_path,
            {"day": day, "start_equity": start_equity},
        )

    def append_event(self, event: dict[str, Any]) -> None:
        payload = dict(event)
        payload.setdefault("time", datetime.now(UTC).isoformat())
        with self._lock:
            with (self.directory / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    @staticmethod
    def default_status() -> dict[str, Any]:
        return {
            "state": "starting",
            "mode": "TESTNET",
            "message": "Bot hazırlanıyor",
            "equity": 0.0,
            "wallet_balance": 0.0,
            "available_balance": 0.0,
            "daily_pnl": 0.0,
            "daily_pnl_percent": 0.0,
            "daily_loss_used_percent": 0.0,
            "open_risk_percent": 0.0,
            "margin_used_percent": 0.0,
            "positions": [],
            "trade_history": [],
            "signals": [],
            "equity_curve": [],
            "last_candle_time": None,
            "next_check_seconds": 0,
            "next_scan_at": None,
            "execution_enabled": False,
            "scan_interval_minutes": 15,
            "confirmation_interval": "1h",
            "leverage": 10,
            "margin_mode": "ISOLATED",
            "reward_risk_ratio": 2.0,
            "entry_model": "CONFIRMATION_VOTE",
            "minimum_confirmations": 4,
            "minimum_margin_usdt": 5.0,
            "maximum_margin_usdt": 40.0,
            "updated_at": None,
        }

    def _read_json(self, path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                with path.open("r", encoding="utf-8") as handle:
                    value = json.load(handle)
                return value if isinstance(value, dict) else dict(fallback)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                return dict(fallback)

    def _atomic_write(self, path: Path, payload: dict[str, Any]) -> None:
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f"{path.stem}-",
                suffix=".tmp",
                dir=self.directory,
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                os.replace(temporary_name, path)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
