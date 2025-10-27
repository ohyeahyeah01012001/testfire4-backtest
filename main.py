from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
import json
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor
from backtest_engine import backtest_tickers

app = FastAPI(title="Testfire 4", version="0.3.2")

# --------------------------------------------------
# File paths
# --------------------------------------------------
STATE_FILE = Path(__file__).parent / "state.json"

# --------------------------------------------------
# Helper functions
# --------------------------------------------------
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

# --------------------------------------------------
# Background tasks
# --------------------------------------------------
executor = ThreadPoolExecutor(max_workers=1)

async def run_backtest_background():
    """Run the backtest in a separate thread so it doesn’t block FastAPI."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, lambda: backtest_tickers())
    print("✅ Background backtest completed")

@app.on_event("startup")
async def startup_event():
    """Automatically run a backtest once when the API starts."""
    print("🚀 Starting initial backtest ...")
    asyncio.create_task(run_backtest_background())

# --------------------------------------------------
# Routes
# --------------------------------------------------
@app.api_route("/health", methods=["GET", "POST", "HEAD", "PUT", "DELETE", "OPTIONS", "PATCH"])
async def health(request: Request):
    """Universal health endpoint for Render + UptimeRobot."""
    return PlainTextResponse("OK", status_code=200)

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

# --------------------------------------------------
# /ranking with Chart.js visualization (Step 5C)
# --------------------------------------------------
@app.get("/ranking", response_class=HTMLResponse)
def ranking():
    state = load_state()
    results = state.get("results", [])
    if not results:
        return """
        <!doctype html><html><body style="font-family:system-ui;margin:2rem">
        <h2>Ranking</h2><p>No results yet. Waiting for first backtest...</p>
        </body></html>"""

    last = state.get("last_update", "unknown")

    # Prepare data for Chart.js
    tickers = [r["ticker"] for r in results]
    returns = [r["return"] for r in results]
    colors = ["#4CAF50" if r >= 0 else "#F44336" for r in returns]

    chart_data = {
        "labels": tickers,
        "datasets": [{
            "label": "Strategy Outperformance (%)",
            "data": returns,
            "backgroundColor": colors,
        }]
    }

    # Build table rows (retain bar visualization)
    max_ret = max(abs(r["return"]) for r in results) or 1
    rows = ""
    for r in results:
        color = "#9ef89e" if r["return"] >= 0 else "#f89e9e"
        width = int(abs(r["return"]) / max_ret * 150)
        rows += f"""
          <tr>
            <td>{r['ticker']}</td>
            <td>{r['return']:.2f}%</td>
            <td>
              <div style='background:{color};width:{width}px;height:12px;border-radius:4px'></div>
            </td>
          </tr>"""

    # Final HTML page
    html = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <title>Testfire 4 — Ranking</title>
      <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
      <style>
        body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; }}
        canvas {{ max-width: 900px; margin-bottom: 2rem; }}
        table {{ border-collapse: collapse; }}
        th, td {{ padding: 6px 10px; text-align: left; }}
        th {{ background: #f0f0f0; }}
      </style>
    </head>
    <body>
      <h2>Ranking (last update: {last})</h2>

      <!-- Chart.js Canvas -->
      <canvas id="rankingChart"></canvas>

      <table border="1" cellspacing="0" cellpadding="6">
        <tr><th>Ticker</th><th>Return (%)</th><th>Visual</th></tr>
        {rows}
      </table>

      <script>
        const ctx = document.getElementById('rankingChart');
        const data = {json.dumps(chart_data)};
        new Chart(ctx, {{
          type: 'bar',
          data: data,
          options: {{
            responsive: true,
            plugins: {{
              legend: {{ display: false }},
              title: {{
                display: true,
                text: 'Strategy Performance by Ticker'
              }}
            }},
            scales: {{
              x: {{ ticks: {{ autoSkip: false, maxRotation: 60, minRotation: 60 }} }},
              y: {{ title: {{ display: true, text: 'Return (%)' }} }}
            }}
          }}
        }});
      </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

# --------------------------------------------------
# Manual refresh trigger
# --------------------------------------------------
@app.get("/refresh")
async def refresh():
    """Manually trigger a new background backtest."""
    asyncio.create_task(run_backtest_background())
    return {"status": "refresh started"}
