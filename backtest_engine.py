import os
import ssl
import json
import math
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import pandas as pd
import yfinance as yf

# --------------------------------------------------------------------
# SSL handling (keeps working on Windows & Render)
# --------------------------------------------------------------------
os.environ.setdefault("CURL_CA_BUNDLE", "")
ssl._create_default_https_context = ssl._create_unverified_context

# --------------------------------------------------------------------
# Paths & config
# --------------------------------------------------------------------
ROOT = Path(__file__).parent
STATE_FILE = ROOT / "state.json"
TICKERS_FILE = ROOT / "tickers.txt"

# Tuning knobs (safe defaults for Render Free)
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))          # how many tickers per batch
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))           # threads per batch
RETRIES = int(os.getenv("RETRIES", "2"))                   # retries per ticker on failures
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "365"))     # timeframe

# --------------------------------------------------------------------
# State helpers
# --------------------------------------------------------------------
def _load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save_state(data: Dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def _save_progress(partial_results: List[Dict[str, Any]], meta: Dict[str, Any]) -> None:
    payload = {
        "last_update": datetime.now().isoformat(),
        "results": sorted(partial_results, key=lambda x: x["return"], reverse=True),
        "meta": meta,
    }
    _save_state(payload)

# --------------------------------------------------------------------
# Data + backtest
# --------------------------------------------------------------------
def read_tickers() -> List[str]:
    """
    Load tickers from tickers.txt (one per line, commas allowed).
    If file is missing/empty, use a sane default small set.
    """
    if TICKERS_FILE.exists():
        raw = TICKERS_FILE.read_text(encoding="utf-8")
        lines = []
        for line in raw.splitlines():
            parts = [p.strip() for p in line.replace(",", " ").split()]
            lines.extend([p for p in parts if p])
        # Deduplicate while preserving order
        seen = set()
        uniq = []
        for t in lines:
            if t not in seen:
                seen.add(t)
                uniq.append(t.upper())
        if uniq:
            return uniq
    # Fallback minimal set (still real)
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"]

def _compute_returns(df: pd.DataFrame) -> Optional[Dict[str, float]]:
    if df.empty or "Close" not in df:
        return None
    df = df.copy()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA200"] = df["Close"].rolling(200).mean()
    df["Signal"] = (df["MA50"] > df["MA200"]).astype(int)
    df["Return"] = df["Close"].pct_change()
    df["Strategy"] = df["Signal"].shift(1) * df["Return"]
    buy_hold = (1 + df["Return"]).prod() - 1
    strategy = (1 + df["Strategy"]).prod() - 1
    diff = (strategy - buy_hold) * 100
    return {
        "return": float(diff),
        "buy_hold": float(buy_hold * 100),
        "strategy": float(strategy * 100),
    }

def _download_and_backtest_one(ticker: str, start_date: str, end_date: str) -> Optional[Dict[str, Any]]:
    """
    Download with retries; compute MA50/200 crossover delta vs buy-and-hold.
    """
    last_exc = None
    for attempt in range(RETRIES + 1):
        try:
            data = yf.download(ticker, start=start_date, end=end_date, interval="1d", progress=False, threads=False)
            metrics = _compute_returns(data)
            if metrics is None:
                return None
            return {"ticker": ticker, **metrics}
        except Exception as e:
            last_exc = e
            time.sleep(0.8 * (attempt + 1))  # backoff
    # Optionally, log last_exc
    return None

def _chunked(seq: List[str], n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i+n]

def backtest_tickers(tickers: Optional[List[str]] = None, start_days_ago: Optional[int] = None) -> None:
    """
    Batch + concurrent backtester.
    - Reads tickers from tickers.txt if not provided.
    - Runs in batches, each batch concurrent with ThreadPoolExecutor.
    - Saves incremental progress to state.json so UI can show partial results.
    """
    if tickers is None:
        tickers = read_tickers()
    days = start_days_ago if start_days_ago is not None else LOOKBACK_DAYS

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    total = len(tickers)
    partial: List[Dict[str, Any]] = []
    meta = {
        "total_tickers": total,
        "batch_size": BATCH_SIZE,
        "max_workers": MAX_WORKERS,
        "retries": RETRIES,
        "lookback_days": days,
        "batches": math.ceil(total / BATCH_SIZE),
        "completed_batches": 0,
        "completed_count": 0,
        "failed_count": 0,
        "source": "tickers.txt" if TICKERS_FILE.exists() else "default_list",
    }
    _save_progress(partial, meta)  # clear & initialize state with zero results

    for batch_index, batch in enumerate(_chunked(tickers, BATCH_SIZE), start=1):
        results_batch: List[Dict[str, Any]] = []
        failed = 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(_download_and_backtest_one, t, start_date, end_date): t
                for t in batch
            }
            for fut in as_completed(futures):
                t = futures[fut]
                try:
                    res = fut.result()
                    if res:
                        results_batch.append(res)
                    else:
                        failed += 1
                except Exception:
                    failed += 1

        # Merge + save incremental progress
        partial.extend(results_batch)
        meta["completed_batches"] = batch_index
        meta["completed_count"] = len(partial)
        meta["failed_count"] = meta.get("failed_count", 0) + failed
        _save_progress(partial, meta)

    # Final save with sorted results
    _save_progress(partial, meta)
    print(f"✅ Saved {len(partial)} results to {STATE_FILE} (failures: {meta['failed_count']})")

# Run manually (optional local run)
if __name__ == "__main__":
    backtest_tickers()
