from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.pipeline.adapters import get_adapter, normalize_symbol_for_source
from src.pipeline.layout import REPO_ROOT


def _repo_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


def _clean_file(root: Path, symbol: str, interval: str) -> Path:
    return root / "data" / "clean" / symbol.upper() / f"{interval}.parquet"


def _raw_file(root: Path, source: str, symbol: str, interval: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return root / "data" / "raw" / source / symbol.upper() / interval / f"{ts}.json"


def _read_clean(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = pd.read_parquet(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    return df


def _merge_frames(*frames: pd.DataFrame) -> pd.DataFrame:
    valid = [f for f in frames if f is not None and not f.empty]
    if not valid:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    merged = pd.concat(valid, ignore_index=True)
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], errors="coerce", utc=True)
    for c in ("open", "high", "low", "close", "volume"):
        merged[c] = pd.to_numeric(merged[c], errors="coerce")
    merged = (
        merged.dropna(subset=["timestamp", "open", "high", "low", "close"])
        .sort_values("timestamp")
        .drop_duplicates(subset=["timestamp"], keep="last")
        .reset_index(drop=True)
    )
    return merged[["timestamp", "open", "high", "low", "close", "volume"]]


def _write_catalog(root: Path, symbol: str, interval: str, df: pd.DataFrame, source: str, file_path: Path) -> Path:
    catalog_path = root / "data" / "catalog.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)

    catalog: dict[str, Any] = {"version": 1, "symbols": {}}
    if catalog_path.exists():
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        except Exception:
            catalog = {"version": 1, "symbols": {}}

    symbols = catalog.setdefault("symbols", {})
    by_symbol = symbols.setdefault(symbol.upper(), {})

    start_ts = None
    end_ts = None
    if not df.empty:
        start_ts = pd.to_datetime(df["timestamp"].iloc[0], utc=True).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_ts = pd.to_datetime(df["timestamp"].iloc[-1], utc=True).strftime("%Y-%m-%dT%H:%M:%SZ")

    by_symbol[interval] = {
        "rows": int(len(df)),
        "start": start_ts,
        "end": end_ts,
        "file": _repo_rel(file_path, root),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
    }

    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return catalog_path


def _bootstrap_legacy(root: Path, symbol: str, interval: str) -> tuple[pd.DataFrame, list[str]]:
    symbol_u = symbol.upper()
    candidates = [
        root / "data" / "binance_kline" / symbol_u / f"kline_{interval}_accum.csv",
        root / "data" / "mcp_kline" / symbol_u / f"kline_{interval}_accum.csv",
        root / "data" / "opend_kline" / symbol_u / f"kline_{interval}_accum.csv",
        root / "data" / "binance_kline" / symbol_u / f"kline_{interval}.csv",
        root / "data" / "mcp_kline" / symbol_u / f"kline_{interval}.csv",
        root / "data" / "opend_kline" / symbol_u / f"kline_{interval}.csv",
    ]

    frames: list[pd.DataFrame] = []
    used: list[str] = []
    for p in candidates:
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p)
        except Exception:
            continue
        if "time" in df.columns and "timestamp" not in df.columns:
            df = df.rename(columns={"time": "timestamp"})
        if "timestamp" not in df.columns:
            continue
        for c in ("open", "high", "low", "close", "volume"):
            if c not in df.columns:
                df[c] = None
        frames.append(df[["timestamp", "open", "high", "low", "close", "volume"]].copy())
        used.append(_repo_rel(p, root))

    if not frames:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"]), []

    merged = _merge_frames(*frames)
    return merged, used


def _write_compat_manifest(root: Path, symbol: str, interval: str, used_files: list[str], reason: str) -> None:
    if not used_files:
        return
    target = root / "data" / "clean" / symbol.upper() / "compat_manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)

    old: dict[str, Any] = {"events": []}
    if target.exists():
        try:
            old = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            old = {"events": []}

    events = old.setdefault("events", [])
    events.append(
        {
            "time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "symbol": symbol.upper(),
            "interval": interval,
            "reason": reason,
            "legacy_files": used_files,
        }
    )
    target.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="行情摄入：source -> raw -> clean(parquet) + catalog")
    parser.add_argument("--source", required=True, choices=["akshare", "binance", "futu", "yahoo"], help="数据源")
    parser.add_argument("--symbol", required=True, help="标的代码，如 BTCUSDT / SH.600410 / US.AAPL")
    parser.add_argument("--interval", required=True, help="周期，如 1h / 4h / 1d")
    parser.add_argument("--start", default=None, help="开始时间（ISO）")
    parser.add_argument("--end", default=None, help="结束时间（ISO）")
    parser.add_argument("--limit", type=int, default=1000, help="最多拉取条数")
    parser.add_argument("--bootstrap-legacy", action="store_true", help="clean 缺失时从旧 CSV 导入历史")
    parser.add_argument("--dry-run", action="store_true", help="只拉取和预览，不落盘")
    return parser.parse_args()


def run_ingest(
    source: str,
    symbol: str,
    interval: str,
    start: str | None,
    end: str | None,
    limit: int,
    bootstrap_legacy: bool,
    dry_run: bool,
    root: Path | None = None,
) -> dict[str, Any]:
    root = root or REPO_ROOT
    source_l = source.lower().strip()
    requested_symbol = symbol.strip()
    symbol_u = normalize_symbol_for_source(source_l, requested_symbol)

    clean_path = _clean_file(root, symbol_u, interval)
    clean_path.parent.mkdir(parents=True, exist_ok=True)

    existing_df = _read_clean(clean_path)

    legacy_df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    legacy_used: list[str] = []
    if bootstrap_legacy and existing_df.empty:
        legacy_df, legacy_used = _bootstrap_legacy(root, symbol_u, interval)

    fetched_df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    raw_payload: dict[str, Any] = {}
    fetch_error: str | None = None

    adapter = get_adapter(source_l)
    try:
        fetched_df, raw_payload = adapter.fetch(
            symbol=symbol_u,
            interval=interval,
            start=start,
            end=end,
            limit=limit,
        )
    except Exception as e:
        fetch_error = str(e)

    merged_df = _merge_frames(existing_df, legacy_df, fetched_df)

    if merged_df.empty:
        reason = f"拉取失败且无可用数据: {fetch_error}" if fetch_error else "无可用数据"
        raise RuntimeError(reason)

    raw_path = _raw_file(root, source_l, symbol_u, interval)

    if not dry_run:
        merged_df.to_parquet(clean_path, index=False)
        catalog_path = _write_catalog(root, symbol_u, interval, merged_df, source_l, clean_path)

        # raw JSON 仅在 clean parquet 写入成功后才需要，不再保留
        # （clean parquet 是唯一数据源，raw 是可重新拉取的中间产物）

        if legacy_used:
            _write_compat_manifest(
                root=root,
                symbol=symbol_u,
                interval=interval,
                used_files=legacy_used,
                reason="bootstrap_legacy",
            )
    else:
        catalog_path = root / "data" / "catalog.json"

    return {
        "source": source_l,
        "requested_symbol": requested_symbol,
        "symbol": symbol_u,
        "interval": interval,
        "existing_rows": int(len(existing_df)),
        "legacy_rows": int(len(legacy_df)),
        "fetched_rows": int(len(fetched_df)),
        "merged_rows": int(len(merged_df)),
        "fetch_error": fetch_error,
        "clean_path": _repo_rel(clean_path, root),
        "catalog_path": _repo_rel(catalog_path, root),
        "legacy_files": legacy_used,
        "dry_run": dry_run,
    }


def main() -> None:
    args = parse_args()
    result = run_ingest(
        source=args.source,
        symbol=args.symbol,
        interval=args.interval,
        start=args.start,
        end=args.end,
        limit=args.limit,
        bootstrap_legacy=args.bootstrap_legacy,
        dry_run=args.dry_run,
    )

    print("✅ ingest 完成")
    for k in (
        "source",
        "symbol",
        "interval",
        "existing_rows",
        "legacy_rows",
        "fetched_rows",
        "merged_rows",
        "clean_path",
        "catalog_path",
        "fetch_error",
    ):
        print(f"- {k}: {result.get(k)}")


if __name__ == "__main__":
    main()
