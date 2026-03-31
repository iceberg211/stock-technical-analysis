from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlencode

import pandas as pd


def _make_opener() -> urllib.request.OpenerDirector:
    """Build URL opener respecting system proxy (env vars or macOS system proxy)."""
    proxies: dict[str, str] = {}
    for key in ("ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "all_proxy", "https_proxy", "http_proxy"):
        val = os.environ.get(key, "").strip()
        if val:
            proxies["https"] = val
            proxies["http"] = val
            break
    if not proxies:
        proxies = urllib.request.getproxies()
    if proxies:
        return urllib.request.build_opener(urllib.request.ProxyHandler(proxies))
    return urllib.request.build_opener()


_opener = _make_opener()


def _fetch_url(url: str, timeout: int = 20) -> bytes:
    """Fetch URL via opener (system proxy) with fallback to curl."""
    try:
        with _opener.open(url, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        # fallback: curl respects macOS system SOCKS/HTTP proxy natively
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", str(timeout), url],
                capture_output=True, timeout=timeout + 5,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception:
            pass
        raise e


REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


class KlineAdapter(Protocol):
    """统一 K 线适配器接口。"""

    source: str

    def fetch(
        self,
        symbol: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """拉取并标准化 K 线，返回 (df, raw_payload)。"""

def _to_utc_ts(value: str | None) -> int | None:
    if not value:
        return None
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return int(ts.timestamp())


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    out = df.copy()
    rename_map = {"time": "timestamp", "datetime": "timestamp"}
    out = out.rename(columns=rename_map)

    if "timestamp" not in out.columns:
        raise ValueError("缺少 timestamp/time 列，无法标准化")

    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce", utc=True)

    for c in ("open", "high", "low", "close", "volume"):
        if c not in out.columns:
            out[c] = None
        out[c] = pd.to_numeric(out[c], errors="coerce")

    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"])\
             .sort_values("timestamp")\
             .drop_duplicates(subset=["timestamp"], keep="last")\
             .reset_index(drop=True)

    return out[list(REQUIRED_COLUMNS)]


def _safe_json_load(resp_bytes: bytes) -> Any:
    try:
        return json.loads(resp_bytes.decode("utf-8"))
    except Exception:
        return {"raw_text": resp_bytes.decode("utf-8", errors="replace")}


class BinanceKlineAdapter:
    source = "binance"
    # api2 在国内网络更可达；api.binance.com 主域可能被封
    _base_url = "https://api2.binance.com/api/v3/klines"

    def fetch(
        self,
        symbol: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": int(max(1, min(limit, 1500))),
        }
        start_ms = _to_utc_ts(start)
        end_ms = _to_utc_ts(end)
        if start_ms is not None:
            params["startTime"] = start_ms * 1000
        if end_ms is not None:
            params["endTime"] = end_ms * 1000

        url = f"{self._base_url}?{urlencode(params)}"
        raw_bytes = _fetch_url(url, timeout=20)

        payload = _safe_json_load(raw_bytes)
        rows: list[list[Any]] = payload if isinstance(payload, list) else []
        data = []
        for r in rows:
            if not isinstance(r, list) or len(r) < 6:
                continue
            data.append(
                {
                    "timestamp": pd.to_datetime(int(r[0]), unit="ms", utc=True),
                    "open": r[1],
                    "high": r[2],
                    "low": r[3],
                    "close": r[4],
                    "volume": r[5],
                }
            )

        df = _normalize_ohlcv(pd.DataFrame(data))
        raw_payload = {
            "source": self.source,
            "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "request": params,
            "response": payload,
        }
        return df, raw_payload


class YahooKlineAdapter:
    source = "yahoo"
    _base_url = "https://query1.finance.yahoo.com/v8/finance/chart"

    @staticmethod
    def _to_yahoo_symbol(symbol: str) -> str:
        s = symbol.strip().upper()
        if s.startswith("US."):
            return s.split(".", 1)[1]
        if s.startswith("SH."):
            return s.split(".", 1)[1] + ".SS"
        if s.startswith("SZ."):
            return s.split(".", 1)[1] + ".SZ"
        if s.endswith("USDT") and len(s) > 4:
            return s[:-4] + "-USD"
        return s

    def fetch(
        self,
        symbol: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        yahoo_symbol = self._to_yahoo_symbol(symbol)
        params: dict[str, Any] = {"interval": interval}

        start_ts = _to_utc_ts(start)
        end_ts = _to_utc_ts(end)
        if start_ts is not None and end_ts is not None:
            params["period1"] = start_ts
            params["period2"] = max(start_ts + 1, end_ts)
        else:
            params["range"] = "1y"

        url = f"{self._base_url}/{yahoo_symbol}?{urlencode(params)}"
        raw_bytes = _fetch_url(url, timeout=20)

        payload = _safe_json_load(raw_bytes)
        result = ((payload or {}).get("chart", {}) or {}).get("result") or []

        data: list[dict[str, Any]] = []
        if result:
            first = result[0]
            ts_list = first.get("timestamp") or []
            quote_list = ((first.get("indicators") or {}).get("quote") or [{}])[0]
            opens = quote_list.get("open") or []
            highs = quote_list.get("high") or []
            lows = quote_list.get("low") or []
            closes = quote_list.get("close") or []
            volumes = quote_list.get("volume") or []

            n = min(len(ts_list), len(opens), len(highs), len(lows), len(closes), len(volumes))
            for i in range(n):
                data.append(
                    {
                        "timestamp": pd.to_datetime(int(ts_list[i]), unit="s", utc=True),
                        "open": opens[i],
                        "high": highs[i],
                        "low": lows[i],
                        "close": closes[i],
                        "volume": volumes[i],
                    }
                )

        df = _normalize_ohlcv(pd.DataFrame(data))
        if limit > 0 and len(df) > limit:
            df = df.tail(limit).reset_index(drop=True)

        raw_payload = {
            "source": self.source,
            "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "symbol": yahoo_symbol,
            "request": params,
            "response": payload,
        }
        return df, raw_payload


class FutuKlineAdapter:
    source = "futu"

    _interval_map = {
        "1m": "K_1M",
        "3m": "K_3M",
        "5m": "K_5M",
        "15m": "K_15M",
        "30m": "K_30M",
        "60m": "K_60M",
        "1h": "K_60M",
        "4h": "K_240M",
        "1d": "K_DAY",
        "1w": "K_WEEK",
        "1mo": "K_MON",
    }

    def fetch(
        self,
        symbol: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        try:
            from futu import AuType, KLType, OpenQuoteContext, RET_OK
        except Exception as e:
            raise RuntimeError(
                "未安装或无法导入 futu SDK，请先安装并启动 OpenD（futu-api）。"
            ) from e

        ktype_name = self._interval_map.get(interval, "K_60M")
        ktype = getattr(KLType, ktype_name)
        host = os.getenv("FUTU_HOST", "127.0.0.1")
        port = int(os.getenv("FUTU_PORT", "11111"))

        start_str = start or ""
        end_str = end or ""

        quote_ctx = OpenQuoteContext(host=host, port=port)
        try:
            ret, data, page_req_key = quote_ctx.request_history_kline(
                code=symbol,
                start=start_str,
                end=end_str,
                ktype=ktype,
                autype=AuType.QFQ,
                max_count=max(1, min(int(limit), 1000)),
                page_req_key=None,
            )
            if ret != RET_OK:
                raise RuntimeError(f"Futu request_history_kline 失败: {data}")

            # data 列常见为 time_key/open/high/low/close/volume
            rows_df = pd.DataFrame(data)
            rows_df = rows_df.rename(columns={"time_key": "timestamp"})
            df = _normalize_ohlcv(rows_df)
            raw_payload = {
                "source": self.source,
                "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "request": {
                    "code": symbol,
                    "interval": interval,
                    "ktype": ktype_name,
                    "start": start_str,
                    "end": end_str,
                    "limit": limit,
                },
                "response_meta": {
                    "rows": int(len(df)),
                    "page_req_key": str(page_req_key) if page_req_key is not None else None,
                },
            }
            return df, raw_payload
        finally:
            quote_ctx.close()


def get_adapter(source: str) -> KlineAdapter:
    s = source.strip().lower()
    if s == "binance":
        return BinanceKlineAdapter()
    if s == "futu":
        return FutuKlineAdapter()
    if s == "yahoo":
        return YahooKlineAdapter()
    raise ValueError(f"不支持的数据源: {source}")
