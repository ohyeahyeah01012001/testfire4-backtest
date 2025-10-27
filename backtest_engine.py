import os
import ssl
import json
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

# --------------------------------------------------------------------
# SSL / certificate handling (fixes curl: (35) TLS connect errors)
# --------------------------------------------------------------------
os.environ["CURL_CA_BUNDLE"] = ""          # Disable broken CA bundle
ssl._create_default_https_context = ssl._create_unverified_context  # Disable strict SSL checking

# --------------------------------------------------------------------
# State management
# --------------------------------------------------------------------
STATE_FILE = Path(__file__).parent / "state.json"

def save_state(data: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)

# --------------------------------------------------------------------
# Backtest engine
# --------------------------------------------------------------------
def backtest_tickers(tickers, start_days_ago=365):
    """
    Download real Yahoo Finance data for each ticker,
    calculate simple 50/200-day MA crossover return,
    and save results to state.json.
    """
    results = []
    start_date = (datetime.now() - timedelta(days=start_days_ago)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    for t in tickers:
        try:
            print(f"Downloading {t} ...")
            data = yf.download(t, start=start_date, end=end_date, interval="1d", progress=False)
            if data.empty or "Close" not in data:
                print(f"No data for {t}")
                continue

            data["MA50"] = data["Close"].rolling(50).mean()
            data["MA200"] = data["Close"].rolling(200).mean()
            data["Signal"] = (data["MA50"] > data["MA200"]).astype(int)
            data["Return"] = data["Close"].pct_change()
            data["Strategy"] = data["Signal"].shift(1) * data["Return"]

            buy_hold = (1 + data["Return"]).prod() - 1
            strategy = (1 + data["Strategy"]).prod() - 1
            diff = (strategy - buy_hold) * 100

            results.append({
                "ticker": t,
                "return": diff,
                "buy_hold": buy_hold * 100,
                "strategy": strategy * 100
            })

        except Exception as e:
            print(f"Failed {t}: {e}")

    results = sorted(results, key=lambda x: x["return"], reverse=True)
    save_state({"last_update": datetime.now().isoformat(), "results": results})
    print(f"✅ Saved {len(results)} results to {STATE_FILE}")

# --------------------------------------------------------------------
# Run manually
# --------------------------------------------------------------------
if __name__ == "__main__":
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"]
    backtest_tickers(tickers)
