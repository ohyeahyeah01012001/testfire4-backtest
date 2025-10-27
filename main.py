from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import json
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor
from backtest_engine import backtest_tickers

app = FastAPI(title="Testfire 4", version="0.2.1")

# -------------------------------
# State management
# -------------------------------

STATE_FILE = Path(__file__).parent / "state.json"

def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)

# -------------------------------
# Background tasks
# -------------------------------

executor = ThreadPoolExecutor(max_workers=1)

async def run_backtest_background():
    """Run the backtest in a separate thread so it doesn’t block FastAPI."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        executor,
        lambda: backtest_tickers(["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"])
    )
    print("✅ Background backtest completed")

@app.on_event("startup")
async def startup_event():
    """Automatically run a backtest once when the API starts."""
    print("🚀 Starting initial backtest ...")
    asyncio.create_task(run_backtest_background())

# -------------------------------
# Routes
# -------------------------------

@app.api_route("/health", methods=["GET", "POST", "HEAD", "PUT", "DELETE", "OPTIONS"])
async def health(request: Request):
    """Universal health check for Render + UptimeRobot."""
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <title>Testfire 4</title>
      <style>
        body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; }
        .ok { display:inline-block; padding:.4rem .6rem; border-radius:.4rem;
              background:#e8fff0; border:1px solid #bfe8cf; color:#0b6b2c; }
      </style>
    </head>
    <body>
      <h1>Testfire 4</h1>
      <p class="ok">Backend is running ✅</p>
      <p><a href="/ranking">Open ranking page</a></p>
      <p><a href="/refresh">Refresh data</a> (manual trigger)</p>
    </body>
    </html>
    """

@app.get("/ranking", response_class=HTMLResponse)
def ranking():
    state = load_state()
    if not state.get("results"):
        return """
        <!doctype html>
        <html><body style="font-family:system-ui;margin:2rem">
          <h2>Ranking</h2>
          <p>No results yet. Waiting for first backtest...</p>
        </body></html>
        """

    table_rows = "".join(
        f"<tr><td>{r['ticker']}</td><td>{r['return']:.2f}%</td></tr>"
        for r in state["results"]
    )

    html = f"""
    <!doctype html>
    <html><body style="font-family:system-ui;margin:2rem">
      <h2>Ranking (last update: {state.get('last_update','unknown')})</h2>
      <table border="1" cellspacing="0" cellpadding="6">
        <tr><th>Ticker</th><th>Return (%)</th></tr>
        {table_rows}
      </table>
    </body></html>
    """
    return html

@app.get("/refresh")
async def refresh():
    """Manually trigger a new background backtest."""
    asyncio.create_task(run_backtest_background())
    return {"status": "refresh started"}
