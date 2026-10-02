from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, fallback: float) -> float:
    value = os.getenv(name)
    return float(value) if value else fallback


def _env_int(name: str, fallback: int) -> int:
    value = os.getenv(name)
    return int(value) if value else fallback


@dataclass(frozen=True, slots=True)
class Settings:
    symbols: tuple[str, ...]
    mode: str
    paper_balance: float
    universe_limit: int
    minimum_24h_quote_volume: float
    interval: str
    confirmation_interval: str
    scan_interval_minutes: int
    candle_limit: int
    poll_seconds: int
    leverage: int
    risk_per_trade: float
    daily_loss_limit: float
    max_margin_fraction: float
    minimum_margin_usdt: float
    maximum_margin_usdt: float
    max_open_positions: int
    position_limit_override_confirmations: int
    atr_stop_multiple: float
    reward_risk_ratio: float
    minimum_signal_score: int
    minimum_confirmations: int
    minimum_adx: float
    minimum_volume_ratio: float
    minimum_stop_percent: float
    long_rsi_min: float
    long_rsi_max: float
    short_rsi_min: float
    short_rsi_max: float
    dry_run: bool
    testnet: bool
    market_base_url: str
    trading_base_url: str
    api_key: str
    api_secret: str
    runtime_dir: Path

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key and self.api_secret)

    @property
    def paper_mode(self) -> bool:
        return self.mode == "paper"

    @property
    def order_execution_enabled(self) -> bool:
        if self.dry_run:
            return False
        if self.paper_mode:
            return True
        if not self.has_credentials:
            return False
        if self.testnet:
            return True
        return os.getenv("ATLAS_ALLOW_LIVE", "") == "I_UNDERSTAND_THE_RISK"

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        config_path = path or PROJECT_ROOT / "config.toml"
        _load_env_file(PROJECT_ROOT / ".env")
        raw: dict[str, object] = {}
        if config_path.exists():
            with config_path.open("rb") as handle:
                raw = tomllib.load(handle)

        trading = raw.get("trading", {})
        risk = raw.get("risk", {})
        strategy = raw.get("strategy", {})
        if not isinstance(trading, dict) or not isinstance(risk, dict) or not isinstance(strategy, dict):
            raise ValueError("config.toml bölümleri geçerli tablo olmalı")

        symbols_value = os.getenv("ATLAS_SYMBOLS")
        symbols = tuple(
            item.strip().upper()
            for item in (symbols_value.split(",") if symbols_value is not None else trading.get("symbols", []))
            if item.strip()
        )
        mode = str(os.getenv("ATLAS_MODE", trading.get("mode", "paper"))).lower()
        if mode == "live":
            testnet = False
        elif mode == "testnet":
            testnet = True
        else:
            testnet = _as_bool(os.getenv("ATLAS_TESTNET", trading.get("testnet")), True)
        default_trade_url = "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"
        settings = cls(
            symbols=symbols,
            mode=mode,
            paper_balance=_env_float("ATLAS_PAPER_BALANCE", float(trading.get("paper_balance", 100.0))),
            universe_limit=_env_int("ATLAS_UNIVERSE_LIMIT", int(trading.get("universe_limit", 30))),
            minimum_24h_quote_volume=_env_float("ATLAS_MIN_24H_VOLUME", float(trading.get("minimum_24h_quote_volume", 25_000_000))),
            interval=str(os.getenv("ATLAS_INTERVAL", trading.get("interval", "15m"))),
            confirmation_interval=str(os.getenv("ATLAS_CONFIRMATION_INTERVAL", trading.get("confirmation_interval", "1h"))),
            scan_interval_minutes=_env_int("ATLAS_SCAN_INTERVAL_MINUTES", int(trading.get("scan_interval_minutes", 15))),
            candle_limit=_env_int("ATLAS_CANDLE_LIMIT", int(trading.get("candle_limit", 500))),
            poll_seconds=_env_int("ATLAS_POLL_SECONDS", int(trading.get("poll_seconds", 20))),
            leverage=_env_int("ATLAS_LEVERAGE", int(risk.get("leverage", 10))),
            risk_per_trade=_env_float("ATLAS_RISK_PER_TRADE", float(risk.get("risk_per_trade", 0.02))),
            daily_loss_limit=_env_float("ATLAS_DAILY_LOSS_LIMIT", float(risk.get("daily_loss_limit", 0.10))),
            max_margin_fraction=_env_float("ATLAS_MAX_MARGIN_FRACTION", float(risk.get("max_margin_fraction", 0.40))),
            minimum_margin_usdt=_env_float("ATLAS_MIN_MARGIN_USDT", float(risk.get("minimum_margin_usdt", 5.0))),
            maximum_margin_usdt=_env_float("ATLAS_MAX_MARGIN_USDT", float(risk.get("maximum_margin_usdt", 40.0))),
            max_open_positions=_env_int("ATLAS_MAX_OPEN_POSITIONS", int(risk.get("max_open_positions", 4))),
            position_limit_override_confirmations=_env_int("ATLAS_POSITION_LIMIT_OVERRIDE_CONFIRMATIONS", int(risk.get("position_limit_override_confirmations", 7))),
            atr_stop_multiple=_env_float("ATLAS_ATR_STOP_MULTIPLE", float(strategy.get("atr_stop_multiple", 2.2))),
            reward_risk_ratio=_env_float("ATLAS_REWARD_RISK_RATIO", float(strategy.get("reward_risk_ratio", 2.0))),
            minimum_confirmations=_env_int("ATLAS_MIN_CONFIRMATIONS", int(strategy.get("minimum_confirmations", 4))),
            minimum_signal_score=_env_int("ATLAS_MIN_SIGNAL_SCORE", int(strategy.get("minimum_signal_score", 85))),
            minimum_adx=_env_float("ATLAS_MIN_ADX", float(strategy.get("minimum_adx", 20.0))),
            minimum_volume_ratio=_env_float("ATLAS_MIN_VOLUME_RATIO", float(strategy.get("minimum_volume_ratio", 0.8))),
            minimum_stop_percent=_env_float("ATLAS_MIN_STOP_PERCENT", float(strategy.get("minimum_stop_percent", 0.8))),
            long_rsi_min=_env_float("ATLAS_LONG_RSI_MIN", float(strategy.get("long_rsi_min", 45.0))),
            long_rsi_max=_env_float("ATLAS_LONG_RSI_MAX", float(strategy.get("long_rsi_max", 72.0))),
            short_rsi_min=_env_float("ATLAS_SHORT_RSI_MIN", float(strategy.get("short_rsi_min", 28.0))),
            short_rsi_max=_env_float("ATLAS_SHORT_RSI_MAX", float(strategy.get("short_rsi_max", 55.0))),
            dry_run=_as_bool(os.getenv("ATLAS_DRY_RUN", trading.get("dry_run")), True),
            testnet=testnet,
            market_base_url=str(os.getenv("ATLAS_MARKET_URL", trading.get("market_base_url", "https://fapi.binance.com"))).rstrip("/"),
            trading_base_url=str(os.getenv("ATLAS_TRADING_URL", default_trade_url)).rstrip("/"),
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_API_SECRET", ""),
            runtime_dir=PROJECT_ROOT / "runtime",
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not 1 <= self.minimum_confirmations <= 9:
            raise ValueError("Onay eşiği 1-9 arasında olmalı")
        if self.mode not in {"paper", "testnet", "live"}:
            raise ValueError("ATLAS_MODE paper, testnet veya live olmalı")
        if not self.symbols and not 1 <= self.universe_limit <= 100:
            raise ValueError("Dinamik tarama limiti 1-100 arasında olmalı")
        if self.paper_balance <= 0:
            raise ValueError("Paper bakiyesi pozitif olmalı")
        if not 1 <= self.leverage <= 20:
            raise ValueError("Güvenlik sınırı: kaldıraç 1-20 arasında olmalı")
        if not 0 < self.risk_per_trade <= 0.02:
            raise ValueError("İşlem riski 0-%2 arasında olmalı")
        if not 0 < self.daily_loss_limit <= 0.10:
            raise ValueError("Günlük zarar limiti 0-%10 arasında olmalı")
        if not 0 < self.max_margin_fraction <= 0.5:
            raise ValueError("Maksimum marjin oranı 0-%50 arasında olmalı")
        if self.minimum_margin_usdt <= 0:
            raise ValueError("Minimum ana teminat pozitif olmalı")
        if self.maximum_margin_usdt < self.minimum_margin_usdt:
            raise ValueError("Maksimum ana teminat minimumdan küçük olamaz")
        if not 1 <= self.max_open_positions <= 5:
            raise ValueError("Açık pozisyon sınırı 1-5 arasında olmalı")
        if not 7 <= self.position_limit_override_confirmations <= 9:
            raise ValueError("Pozisyon sınırı istisnası 7-9 onay arasında olmalı")
        if self.candle_limit < 100:
            raise ValueError("Analiz için en az 100 mum gerekli")
        if not 0 <= self.minimum_adx <= 100:
            raise ValueError("Minimum ADX 0-100 arasında olmalı")
        if not 0 <= self.minimum_volume_ratio <= 5:
            raise ValueError("Minimum hacim oranı 0-5 arasında olmalı")
        if not 0 <= self.minimum_stop_percent <= 10:
            raise ValueError("Minimum stop yüzdesi 0-%10 arasında olmalı")
        if not 0 <= self.long_rsi_min < self.long_rsi_max <= 100:
            raise ValueError("LONG RSI aralığı geçersiz")
        if not 0 <= self.short_rsi_min < self.short_rsi_max <= 100:
            raise ValueError("SHORT RSI aralığı geçersiz")
        if not 1 <= self.scan_interval_minutes <= 1440:
            raise ValueError("Tarama aralığı 1-1440 dakika arasında olmalı")
