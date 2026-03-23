"""
示例数据生成器：下载 BTC 4H 历史 OHLCV 数据。

用法:
    python -m eval.generate_sample_data --symbol BTCUSDT --interval 4h --days 180

依赖: ccxt (pip install ccxt)
回退: 如果 ccxt 不可用，尝试 yfinance
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def fetch_with_ccxt(symbol: str, interval: str, days: int) -> list[dict]:
    """使用 ccxt 从 Binance 下载 OHLCV 数据。"""
    try:
        import ccxt
    except ImportError:
        raise ImportError("ccxt 未安装, 请运行: pip install ccxt")

    exchange = ccxt.binance({"enableRateLimit": True})

    # ccxt 的 timeframe 映射
    tf_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w"}
    timeframe = tf_map.get(interval)
    if not timeframe:
        print(f"❌ 不支持的周期: {interval}", file=sys.stderr)
        sys.exit(1)

    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    all_ohlcv = []
    limit = 1000

    print(f"📡 从 Binance 下载 {symbol} {interval} 数据 (最近 {days} 天) ...")

    while True:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        since = ohlcv[-1][0] + 1  # 下一个时间戳
        if len(ohlcv) < limit:
            break
        print(f"   已获取 {len(all_ohlcv)} 根 ...", flush=True)

    rows = []
    for candle in all_ohlcv:
        ts = datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc)
        rows.append({
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "open": candle[1],
            "high": candle[2],
            "low": candle[3],
            "close": candle[4],
            "volume": candle[5],
        })

    return rows


def fetch_with_yfinance(symbol: str, interval: str, days: int) -> list[dict]:
    """使用 yfinance 下载数据（备选方案）。"""
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("yfinance 未安装, 请运行: pip install yfinance")

    # yfinance 的 interval 映射
    yf_interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "1h", "1d": "1d", "1w": "1wk"}
    yf_interval = yf_interval_map.get(interval)

    # yfinance 对 BTC 的 ticker
    yf_symbol = "BTC-USD" if "BTC" in symbol.upper() else symbol

    print(f"📡 从 Yahoo Finance 下载 {yf_symbol} {yf_interval} 数据 ...")
    ticker = yf.Ticker(yf_symbol)
    df = ticker.history(period=f"{days}d", interval=yf_interval)

    if df.empty:
        raise ValueError("yfinance 返回空数据")

    rows = []
    for ts, row in df.iterrows():
        rows.append({
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "open": round(row["Open"], 2),
            "high": round(row["High"], 2),
            "low": round(row["Low"], 2),
            "close": round(row["Close"], 2),
            "volume": round(row["Volume"], 2),
        })

    return rows


def save_csv(rows: list[dict], output: Path):
    """保存为标准 CSV。"""
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write("timestamp,open,high,low,close,volume\n")
        for r in rows:
            f.write(f"{r['timestamp']},{r['open']},{r['high']},{r['low']},{r['close']},{r['volume']}\n")


def main():
    parser = argparse.ArgumentParser(description="下载 OHLCV 示例数据")
    parser.add_argument("--symbol", default="BTC/USDT", help="交易对 (ccxt 格式, 如 BTC/USDT)")
    parser.add_argument("--interval", default="4h", help="K 线周期")
    parser.add_argument("--days", type=int, default=180, help="下载天数")
    parser.add_argument("--output", default=None, help="输出 CSV 路径")
    parser.add_argument("--source", choices=["ccxt", "yfinance"], default="ccxt", help="数据源")
    args = parser.parse_args()

    # 默认输出路径
    if args.output is None:
        safe_symbol = args.symbol.replace("/", "").lower()
        args.output = f"eval/data/{safe_symbol}_{args.interval}.csv"

    try:
        if args.source == "ccxt":
            rows = fetch_with_ccxt(args.symbol, args.interval, args.days)
        else:
            rows = fetch_with_yfinance(args.symbol, args.interval, args.days)
    except ImportError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    if not rows:
        print("❌ 没有获取到数据", file=sys.stderr)
        sys.exit(1)

    output = Path(args.output)
    save_csv(rows, output)
    print(f"✅ 保存 {len(rows)} 根 K 线到: {output}")

    # 验证窗口够不够
    from eval.config import LOOKBACK_BARS, FORWARD_BARS
    min_required = LOOKBACK_BARS + FORWARD_BARS
    if len(rows) < min_required:
        print(f"⚠️  数据 {len(rows)} 根 < 最低要求 {min_required} 根, 可能需要更多天数")
    else:
        max_cases = (len(rows) - min_required) // 10 + 1
        print(f"📊 可切出约 {max_cases} 个 case (step=10)")


if __name__ == "__main__":
    main()
