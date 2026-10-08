from __future__ import annotations

import hashlib
import hmac
import json
import socket
import time
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..config import Settings
from ..models import Candle, Position, SymbolRules


class BinanceAPIError(RuntimeError):
    def __init__(self, status: int, code: int | None, message: str) -> None:
        super().__init__(f"Binance HTTP {status}, kod {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


class AmbiguousExecutionError(RuntimeError):
    """Borsa 5xx/timeout verdiğinde emrin sonucu kesin bilinmiyor."""


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


class BinanceFuturesClient:
    def __init__(self, settings: Settings, timeout: float = 10.0) -> None:
        self.settings = settings
        self.timeout = timeout
        self._time_offset_ms = 0
        self._rules_cache: dict[str, SymbolRules] = {}

    def ping(self) -> bool:
        self._request("GET", "/fapi/v1/ping", base_url=self.settings.market_base_url)
        return True

    def sync_time(self) -> int:
        started = int(time.time() * 1000)
        response = self._request("GET", "/fapi/v1/time", base_url=self.settings.trading_base_url)
        ended = int(time.time() * 1000)
        midpoint = (started + ended) // 2
        self._time_offset_ms = int(response["serverTime"]) - midpoint
        return self._time_offset_ms

    def get_candles(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        rows = self._request(
            "GET",
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": interval, "limit": min(limit, 1500)},
            base_url=self.settings.market_base_url,
        )
        return [
            Candle(
                open_time=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
                close_time=int(row[6]),
            )
            for row in rows
        ]

    def get_order_book(self, symbol: str) -> dict[str, Any]:
        # Public USD-M snapshot; no credentials needed.
        return self._request("GET", "/fapi/v1/depth", {"symbol": symbol, "limit": 100}, base_url=self.settings.market_base_url)

    def get_monitoring_candles(self, symbol: str, start_time: int) -> list[Candle]:
        rows = self._request("GET", "/fapi/v1/klines", {
            "symbol": symbol, "interval": "1m", "startTime": start_time, "limit": 1000,
        }, base_url=self.settings.market_base_url)
        return [Candle(int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]), int(row[6])) for row in rows]

    def discover_symbols(self, limit: int, minimum_quote_volume: float) -> list[str]:
        exchange = self._request("GET", "/fapi/v1/exchangeInfo", base_url=self.settings.market_base_url)
        tickers = self._request("GET", "/fapi/v1/ticker/24hr", base_url=self.settings.market_base_url)
        excluded_bases = {
            "USDC", "FDUSD", "TUSD", "USDP", "DAI", "EUR", "TRY", "BUSD",
            "USDE", "XUSD", "BFUSD",
        }
        eligible = {
            item["symbol"]
            for item in exchange.get("symbols", [])
            if item.get("status") == "TRADING"
            and item.get("contractType") == "PERPETUAL"
            and item.get("quoteAsset") == "USDT"
            and item.get("baseAsset") not in excluded_bases
        }
        ranked = sorted(
            (
                (str(item.get("symbol")), float(item.get("quoteVolume", 0.0)))
                for item in tickers
                if item.get("symbol") in eligible
                and float(item.get("quoteVolume", 0.0)) >= minimum_quote_volume
            ),
            key=lambda pair: pair[1],
            reverse=True,
        )
        return [symbol for symbol, _ in ranked[:limit]]

    def get_historical_candles(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int | None = None,
    ) -> list[Candle]:
        candles: list[Candle] = []
        cursor = start_time
        final_time = end_time or int(time.time() * 1000)
        while cursor < final_time:
            rows = self._request(
                "GET",
                "/fapi/v1/klines",
                {
                    "symbol": symbol,
                    "interval": interval,
                    "limit": 1500,
                    "startTime": cursor,
                    "endTime": final_time,
                },
                base_url=self.settings.market_base_url,
            )
            if not rows:
                break
            page = [
                Candle(int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]), int(row[6]))
                for row in rows
            ]
            candles.extend(page)
            next_cursor = page[-1].close_time + 1
            if next_cursor <= cursor:
                break
            cursor = next_cursor
            if len(rows) < 1500:
                break
            time.sleep(0.08)
        unique = {candle.open_time: candle for candle in candles}
        return [unique[key] for key in sorted(unique)]

    def get_symbol_rules(self, symbol: str) -> SymbolRules:
        if symbol in self._rules_cache:
            return self._rules_cache[symbol]
        info = self._request("GET", "/fapi/v1/exchangeInfo", base_url=self.settings.market_base_url)
        item = next((entry for entry in info["symbols"] if entry["symbol"] == symbol), None)
        if not item or item.get("status") != "TRADING":
            raise ValueError(f"{symbol} Binance Futures üzerinde işlemde değil")
        filters = {entry["filterType"]: entry for entry in item["filters"]}
        lot = filters["LOT_SIZE"]
        price = filters["PRICE_FILTER"]
        notional = filters.get("MIN_NOTIONAL", {})
        rules = SymbolRules(
            symbol=symbol,
            tick_size=Decimal(price["tickSize"]),
            step_size=Decimal(lot["stepSize"]),
            min_quantity=Decimal(lot["minQty"]),
            max_quantity=Decimal(lot["maxQty"]),
            min_notional=Decimal(str(notional.get("notional", "0"))),
        )
        self._rules_cache[symbol] = rules
        return rules

    def get_account_snapshot(self) -> dict[str, float]:
        account = self._signed_with_fallback("GET", "/fapi/v3/account", "/fapi/v2/account")
        wallet = float(account.get("totalWalletBalance", 0.0))
        unrealized = float(account.get("totalUnrealizedProfit", 0.0))
        return {
            "wallet_balance": wallet,
            "unrealized_pnl": unrealized,
            "equity": wallet + unrealized,
            "available_balance": float(account.get("availableBalance", 0.0)),
            "margin_balance": float(account.get("totalMarginBalance", wallet + unrealized)),
            "initial_margin": float(account.get("totalInitialMargin", 0.0)),
        }

    def get_api_key_restrictions(self) -> dict[str, Any]:
        """Read API-key permissions without placing an order."""
        return self._signed(
            "GET", "/sapi/v1/account/apiRestrictions", base_url="https://api.binance.com"
        )

    def get_positions(self) -> list[Position]:
        account = self._signed_with_fallback("GET", "/fapi/v3/account", "/fapi/v2/account")
        output: list[Position] = []
        for item in account.get("positions", []):
            amount = float(item.get("positionAmt", 0.0))
            if amount == 0:
                continue
            output.append(
                Position(
                    symbol=str(item["symbol"]),
                    amount=amount,
                    entry_price=float(item.get("entryPrice", 0.0)),
                    mark_price=float(item.get("markPrice", 0.0)),
                    unrealized_pnl=float(item.get("unrealizedProfit", 0.0)),
                )
            )
        return output

    def get_trade_history(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._signed(
            "GET",
            "/fapi/v1/income",
            {"incomeType": "REALIZED_PNL", "limit": min(max(1, limit), 1000)},
        )
        return [
            {
                "symbol": str(item.get("symbol") or "—"),
                "side": "—",
                "entry": None,
                "exit": None,
                "pnl": float(item.get("income", 0.0)),
                "reason": "REALIZED_PNL",
                "closed_at": int(item.get("time", 0)),
            }
            for item in reversed(rows)
            if float(item.get("income", 0.0)) != 0.0
        ]

    def prepare_symbol(self, symbol: str, leverage: int) -> None:
        position_mode = self._signed("GET", "/fapi/v1/positionSide/dual")
        if bool(position_mode.get("dualSidePosition")):
            raise RuntimeError("Bot güvenlik nedeniyle yalnızca One-way Mode destekliyor")
        self._signed("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage})
        try:
            self._signed("POST", "/fapi/v1/marginType", {"symbol": symbol, "marginType": "ISOLATED"})
        except BinanceAPIError as exc:
            if exc.code != -4046:
                raise

    def place_market_order(self, symbol: str, side: str, quantity: Decimal, client_id: str) -> dict[str, Any]:
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
            "newClientOrderId": client_id,
            "newOrderRespType": "RESULT",
        }
        try:
            return self._signed("POST", "/fapi/v1/order", params, trade=True)
        except AmbiguousExecutionError:
            return self._recover_order(symbol, client_id)

    def place_protection_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        trigger_price: Decimal,
        client_id: str,
    ) -> dict[str, Any]:
        return self._signed(
            "POST",
            "/fapi/v1/algoOrder",
            {
                "algoType": "CONDITIONAL",
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "triggerPrice": trigger_price,
                "workingType": "MARK_PRICE",
                "closePosition": True,
                "priceProtect": True,
                "clientAlgoId": client_id,
                "newOrderRespType": "RESULT",
            },
            trade=True,
        )

    def close_position(self, symbol: str, side: str, quantity: Decimal, client_id: str) -> dict[str, Any]:
        return self._signed(
            "POST",
            "/fapi/v1/order",
            {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": quantity,
                "reduceOnly": True,
                "newClientOrderId": client_id,
                "newOrderRespType": "RESULT",
            },
            trade=True,
        )

    def _recover_order(self, symbol: str, client_id: str) -> dict[str, Any]:
        for attempt in range(3):
            time.sleep(0.5 * (attempt + 1))
            try:
                return self._signed(
                    "GET",
                    "/fapi/v1/order",
                    {"symbol": symbol, "origClientOrderId": client_id},
                )
            except BinanceAPIError as exc:
                if exc.code != -2013:
                    raise
        raise AmbiguousExecutionError(
            f"{symbol} emrinin sonucu kesinleşmedi; otomatik tekrar gönderilmedi"
        )

    def _signed_with_fallback(self, method: str, primary: str, fallback: str) -> Any:
        try:
            return self._signed(method, primary)
        except BinanceAPIError as exc:
            if exc.status not in {400, 404}:
                raise
            return self._signed(method, fallback)

    def _signed(
        self,
        method: str,
        path: str,
        params: dict[str, object] | None = None,
        trade: bool = False,
        base_url: str | None = None,
    ) -> Any:
        if not self.settings.has_credentials:
            raise RuntimeError("Binance testnet API anahtarları ayarlanmamış")
        payload = dict(params or {})
        payload["timestamp"] = int(time.time() * 1000) + self._time_offset_ms
        payload["recvWindow"] = 5000
        query = urlencode({key: _format_value(value) for key, value in payload.items()})
        signature = hmac.new(
            self.settings.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        payload["signature"] = signature
        return self._request(method, path, payload, signed=True, trade=trade,
                             base_url=base_url or self.settings.trading_base_url)

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, object] | None = None,
        *,
        signed: bool = False,
        trade: bool = False,
        base_url: str,
    ) -> Any:
        payload = {key: _format_value(value) for key, value in (params or {}).items()}
        encoded = urlencode(payload).encode("utf-8")
        url = f"{base_url}{path}"
        data: bytes | None = None
        if method in {"GET", "DELETE"} and encoded:
            url = f"{url}?{encoded.decode('utf-8')}"
        elif method in {"POST", "PUT"}:
            data = encoded
        headers = {"Accept": "application/json", "User-Agent": "AtlasTrade/0.1"}
        if signed:
            headers["X-MBX-APIKEY"] = self.settings.api_key
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        attempts = 1 if trade or method != "GET" else 3
        for attempt in range(attempts):
            request = Request(url=url, data=data, method=method, headers=headers)
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8")
                    return json.loads(body) if body else {}
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                try:
                    error = json.loads(body)
                except json.JSONDecodeError:
                    error = {"code": None, "msg": body or exc.reason}
                if trade and exc.code >= 500:
                    raise AmbiguousExecutionError(str(error.get("msg", "Borsa yanıtı belirsiz"))) from exc
                if exc.code in {418, 429} and attempt + 1 < attempts:
                    delay = float(exc.headers.get("Retry-After", 2 ** attempt))
                    time.sleep(min(delay, 10.0))
                    continue
                if exc.code >= 500 and attempt + 1 < attempts:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise BinanceAPIError(exc.code, error.get("code"), str(error.get("msg", exc.reason))) from exc
            except (URLError, TimeoutError, socket.timeout) as exc:
                if trade:
                    raise AmbiguousExecutionError("Emir gönderilirken bağlantı sonucu belirsiz") from exc
                if attempt + 1 >= attempts:
                    raise RuntimeError(f"Binance bağlantı hatası: {exc}") from exc
                time.sleep(0.5 * (2 ** attempt))
        raise RuntimeError("Binance isteği tamamlanamadı")
