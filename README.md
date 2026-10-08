# Atlas Trade

**English** | [Türkçe](README.tr.md)

> **Work in progress:** this project is under active development. Features and trading rules may change.

## Latest update — October 8, 2026

The dashboard now supports English and Turkish. This release also improves
paper-trade candle monitoring, recovery after interruptions, atomic state writes,
position monitoring alerts, and duplicate-order prevention. A private Tailscale
phone connection can show the dashboard away from the computer. See the
[bilingual update notes](docs/2026-10-08-update.md) for details and limitations.

Atlas Trade is a Binance USDⓈ-M Futures trading bot with a local Turkish-language dashboard. It scans liquid pairs, combines trend, momentum and volatility analysis, and calculates position risk. This documentation is available in English and Turkish; the dashboard itself is currently in Turkish.

> No strategy guarantees profit. The default configuration uses a simulated paper account, not real funds.

## 1. Requirements

- Python **3.12 or newer**, available as `python` in your terminal.
- Node.js **22.13 or newer**, with npm.
- Git to clone the repository, or download **Code → Download ZIP** on GitHub and extract it.
- Internet access for dependencies and Binance public market data.

The one-click launchers require Windows and PowerShell. On other systems, use the manual startup instructions below.

## 2. Download and install

Open PowerShell and run:

```powershell
git clone https://github.com/muhammetuyan/binance-futures-bot.git
cd binance-futures-bot
python --version
node --version
python -m pip install "fastapi>=0.115,<1" "uvicorn>=0.34,<1"
npm ci
Copy-Item .env.example .env
```

If you downloaded a ZIP, open a terminal in the extracted folder and start at the version checks. Copy `.env.example` only during initial setup; do not overwrite an existing `.env` containing your settings.

For an isolated Python setup, optionally create a virtual environment before installing dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

With a virtual environment, use manual startup from activated terminals so the backend uses the correct Python interpreter.

## 3. Start and stop

### Windows launchers

After installing dependencies, double-click **Atlas-Trade-Baslat.cmd** in the project folder. It starts the backend and dashboard, then opens the browser.

- Dashboard: <http://localhost:3000/>
- Backend health: <http://127.0.0.1:8788/api/health>

Double-click **Atlas-Trade-Durdur.cmd** to stop new entries and local processes. In exchange-backed modes, orders already placed on the exchange, including stop-loss and take-profit orders, remain there.

### Manual startup

Open two terminals in the project folder. If using a virtual environment, activate it in the backend terminal.

Terminal 1 — backend:

```powershell
python -m bot.service
```

Terminal 2 — dashboard:

```powershell
npm run dev
```

Open <http://localhost:3000/>. Stop each process with `Ctrl+C`. On macOS/Linux, create the environment with `python3 -m venv .venv`, activate with `source .venv/bin/activate`, and use `cp .env.example .env` for the initial environment copy.

## 4. Configuration and credentials

Paper mode works without API keys. Defaults are in [config.toml](config.toml); local environment variables and `.env` can override supported settings.

Keep API keys only in your local `.env`. Never paste them into issues, commits, screenshots, or chat. `.env`, private keys, logs, local Python environments and account/trade data under `runtime/` are ignored by Git. [.env.example](.env.example) contains blank credential fields.

### Paper mode — default

```dotenv
ATLAS_MODE=paper
ATLAS_PAPER_BALANCE=100
```

Paper trading uses real market data and simulated orders. The default configuration enables simulated execution; it does not submit real exchange orders.

### Binance Futures Testnet

Add testnet credentials to the local `.env` and restart the application:

```dotenv
BINANCE_API_KEY=YOUR_TESTNET_API_KEY
BINANCE_API_SECRET=YOUR_TESTNET_API_SECRET
ATLAS_MODE=testnet
ATLAS_DRY_RUN=false
```

Testnet uses the Binance Futures test environment, separate from the simulated paper balance.

### Live mode

Live mode is implemented. Evaluate paper and testnet behavior before considering real funds. Use a Futures-only API key, disable withdrawals and use IP restrictions where possible. Live execution requires credentials and all three settings:

```dotenv
ATLAS_MODE=live
ATLAS_DRY_RUN=false
ATLAS_ALLOW_LIVE=I_UNDERSTAND_THE_RISK
```

## 5. Trading defaults and strategy

- Universe: the 30 most liquid USDT perpetual pairs with at least 25 million USDT in 24-hour quote volume.
- Analysis: closed 15-minute candles with a 1-hour trend confirmation interval; scans every 15 minutes.
- Risk per trade: 2%; daily loss limit: 10%.
- Leverage: 10x isolated; target margin: 5–40 USDT, subject to risk and available funds.
- Normal open-position limit: four. Candidates with seven or more confirmations in the chosen direction can exceed this count; other risk checks still apply.

The current entry rule requires **four of nine confirmations**. LONG and SHORT are counted separately; a tie produces WAIT. The checks cover price/EMA20 with momentum, 1-hour EMA trend, combined RSI, market structure shifts (MSS), liquidity sweeps, fair value gap (FVG) reactions, ADX, volume and volatility. ADX, volume and volatility are shared conditions, not directional signals. The score is not a probability of success.

Stops use ATR and structural invalidation levels with a default 1:2 risk/reward target. Duplicate positions, repeated same-candle orders, daily loss limits, pause state and available margin are separate execution checks.

The chart displays 60 closed candles, FVG/MSS levels and draft entry/stop/target levels. Live unfinished candles and prices update through WebSocket for display without altering the closed-candle strategy. REST history refreshes after reconnection or symbol changes.

An empty `symbols = []` in `config.toml` enables dynamic scanning. To restrict the universe, set `symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]`.

### Order-book checks

Candidates and orders are checked against Binance public order-book snapshots. Defaults require a spread below 0.08%, estimated slippage below 0.05%, and depth on each side within 0.2% of the midpoint of at least 10,000 USDT and 20 times the planned order size. Price movement above 0.5 ATR, data older than 10 seconds, or data more than 5 seconds ahead blocks entry. Missing data also blocks entry. Visible liquidity does not guarantee execution.

## 6. Troubleshooting

- **Python or npm not found:** install the required versions, enable PATH integration and reopen the terminal.
- **Missing Python module:** run the dependency installation with the same Python interpreter used to start the backend.
- **PowerShell blocks npm.ps1:** use `npm.cmd ci` and `npm.cmd run dev` on Windows.
- **Ports 3000 or 8788 are busy:** stop the existing Atlas instance using the stop launcher; check whether another application owns the port.
- **Only half the application is running:** use the stop launcher, then start again. Check ignored logs in `runtime/`, especially `backend.err.log` and `dashboard.err.log`.
- **No candidates or entries:** check internet access, backend health, mode, pause state and risk/strategy filters. A successful startup does not guarantee a trade.
- **Binance requests fail:** verify connectivity and that the selected Binance environment is accessible from your location. For signed requests, also verify the correct environment's credentials, permissions and system clock.

## 7. Tests and backtesting

```powershell
python -m unittest discover -s tests -v
npm run build
npm audit --omit=dev
python -m bot.backtest --symbol BTCUSDT --days 90
```

The backtest allows one position per pair, enters after the signal candle and accounts for commission and estimated slippage. Historical order-book checks, funding and liquidation effects are not fully modeled; it is not a complete live-performance simulation.

The core `Broker` interface separates exchange execution from strategy logic for future integrations.

## References

- [Binance Kline Streams](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market)
- [Binance Order Book API](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book)
