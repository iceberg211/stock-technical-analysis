#!/usr/bin/env python3
"""无缓存多市场确定性行情取数、清洗、完整性判定与指标预计算工具。"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, time as datetime_time, timedelta, timezone
from email.utils import parsedate_to_datetime
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import ProxyHandler, Request, build_opener
from zoneinfo import ZoneInfo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from indicators import build_timeframe_package  # noqa: E402


# 统一双层 K 线规则：脚本内部拉取足够历史算指标（fetch_bars），
# 裁剪后按受控预算（analysis_bars / detail_bars）交给上层分析 Skill。
TIMEFRAME_POLICY: dict[str, dict[str, Any]] = {
    "1w": {"seconds": 604800, "fetch_bars": 150, "analysis_bars": 100, "detail_bars": 12, "min_bars": 60, "yahoo_range": "3y", "yahoo_interval": "1wk"},
    "1d": {"seconds": 86400, "fetch_bars": 250, "analysis_bars": 120, "detail_bars": 12, "min_bars": 80, "yahoo_range": "1y", "yahoo_interval": "1d"},
    "4h": {"seconds": 14400, "fetch_bars": 180, "analysis_bars": 100, "detail_bars": 12, "min_bars": 60, "yahoo_range": "6mo", "yahoo_interval": "1h"},
    "60m": {"seconds": 3600, "fetch_bars": 180, "analysis_bars": 80, "detail_bars": 12, "min_bars": 50, "yahoo_range": "3mo", "yahoo_interval": "60m"},
    "1h": {"seconds": 3600, "fetch_bars": 180, "analysis_bars": 80, "detail_bars": 12, "min_bars": 50, "yahoo_range": "3mo", "yahoo_interval": "60m"},
    "30m": {"seconds": 1800, "fetch_bars": 180, "analysis_bars": 96, "detail_bars": 12, "min_bars": 60, "yahoo_range": "1mo", "yahoo_interval": "30m"},
    "15m": {"seconds": 900, "fetch_bars": 200, "analysis_bars": 96, "detail_bars": 16, "min_bars": 60, "yahoo_range": "1mo", "yahoo_interval": "15m"},
    "5m": {"seconds": 300, "fetch_bars": 240, "analysis_bars": 120, "detail_bars": 20, "min_bars": 80, "yahoo_range": "1mo", "yahoo_interval": "5m"},
}

DEFAULT_INTERVALS_BY_MARKET = {
    "cn": ("1d", "60m", "15m"),
    "hk": ("1d", "60m", "15m"),
    "us": ("1d", "60m", "15m"),
    "crypto": ("4h", "1h", "15m"),
}

INTRADAY_INTERVALS = ("60m", "15m", "5m")

MARKET_TIMEZONE = {
    "cn": "Asia/Shanghai",
    "hk": "Asia/Hong_Kong",
    "us": "America/New_York",
    "crypto": "UTC",
}

MARKET_OPEN_TIME = {
    "cn": datetime_time(9, 30),
    "hk": datetime_time(9, 30),
    "us": datetime_time(9, 30),
    "crypto": datetime_time(0, 0),
}

MARKET_CLOSE_TIME = {
    "cn": datetime_time(15, 0),
    "hk": datetime_time(16, 0),
    "us": datetime_time(16, 0),
    "crypto": datetime_time(23, 59, 59),
}

YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
BINANCE_HOSTS = ("api.binance.com", "data-api.binance.vision")
COMMON_CRYPTO_BASES = {
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "DOT", "LINK",
    "SUI", "ARB", "OP", "PEPE", "TON", "LTC", "BCH", "UNI", "AAVE", "APT",
}
DEFAULT_TIMEOUT_SECONDS = 5
_DIRECT_OPENER = build_opener(ProxyHandler({}))


@dataclass(frozen=True)
class SymbolSpec:
    query: str
    market: str  # cn | hk | us | crypto
    name: str | None
    canonical: str
    tencent_code: str
    sina_code: str
    yahoo_code: str
    binance_code: str | None
    exchange_timezone: str


def normalize_interval(interval: str) -> str:
    value = interval.strip().lower()
    aliases = {"1w": "1w", "w": "1w", "wk": "1w", "1wk": "1w", "1d": "1d", "d": "1d", "1h": "1h", "60m": "60m", "4h": "4h", "30m": "30m", "15m": "15m", "5m": "5m"}
    if value not in aliases:
        raise ValueError(f"不支持的周期: {interval}")
    return aliases[value]


def parse_timestamp(value: Any) -> int:
    if isinstance(value, (int, float)):
        ts = int(value)
        return ts // 1000 if ts > 10_000_000_000 else ts
    text = str(value).strip()
    if text.isdigit():
        ts = int(text)
        return ts // 1000 if ts > 10_000_000_000 else ts
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def iso_timestamp(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def format_local_time(ts: int, tz_name: str, interval: str) -> str:
    tz = ZoneInfo(tz_name)
    dt = datetime.fromtimestamp(ts, tz=tz)
    if normalize_interval(interval) in {"1d", "1w"}:
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d %H:%M")


def detect_proxy() -> str | None:
    """优先读环境变量，其次读取系统代理配置（支持 macOS MacPacket/系统代理）。"""
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        val = os.environ.get(key)
        if val and val.strip():
            return val.strip()
    try:
        from urllib.request import getproxies
        proxies = getproxies()
        for scheme in ("https", "http"):
            if proxies.get(scheme):
                return proxies[scheme]
    except Exception:  # noqa: BLE001
        pass
    return None


def longbridge_status() -> dict[str, Any]:
    """检测是否已配置可选的长桥 OpenAPI 环境（仅探测，不强依赖）。"""
    has_sdk = importlib.util.find_spec("longport") is not None
    has_creds = bool(
        os.environ.get("LONGBRIDGE_APP_KEY") and os.environ.get("LONGBRIDGE_ACCESS_TOKEN")
    )
    return {
        "sdk_installed": has_sdk,
        "credentials_configured": has_creds,
        "ready": has_sdk and has_creds,
    }


def http_get_text(
    url: str,
    *,
    encoding: str = "utf-8",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    use_proxy: bool = False,
    proxy_url: str | None = None,
) -> tuple[str, dict[str, str]]:
    """统一 HTTP GET：国内源直连不走代理，海外源优先自动走检测代理的 curl/urllib。"""
    headers = {"User-Agent": "Mozilla/5.0"}
    if not use_proxy:
        req = Request(url, headers=headers)
        with _DIRECT_OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read()
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        return raw.decode(encoding, errors="ignore"), resp_headers

    effective_proxy = proxy_url if proxy_url is not None else detect_proxy()
    # macOS 上原生 curl + 系统代理访问海外 TLS/HTTP2 端点远比 Python urllib 稳定快速
    cmd = ["curl", "-sS", "-i", "--max-time", str(timeout), "-A", "Mozilla/5.0"]
    if effective_proxy:
        cmd.extend(["-x", effective_proxy])
    cmd.append(url)
    try:
        completed = subprocess.run(cmd, capture_output=True, check=False, timeout=timeout + 2)
        if completed.returncode == 0 and completed.stdout:
            raw_bytes = completed.stdout
            sep = b"\r\n\r\n" if b"\r\n\r\n" in raw_bytes else b"\n\n"
            # curl 走 HTTP CONNECT 代理时会先输出代理握手头，取最后一个 HTTP 响应段
            parts = raw_bytes.split(sep)
            if len(parts) >= 2:
                # 寻找最后一个正文起始（在头部之后）
                header_idx = 0
                for idx in range(len(parts) - 1):
                    if parts[idx].lstrip().startswith(b"HTTP/"):
                        header_idx = idx
                header_block = parts[header_idx].decode("latin1", errors="ignore")
                body_bytes = sep.join(parts[header_idx + 1 :])
                resp_headers: dict[str, str] = {}
                for line in header_block.splitlines()[1:]:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        resp_headers[k.strip().lower()] = v.strip()
                return body_bytes.decode(encoding, errors="ignore"), resp_headers
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    # 若无 curl，则回退默认 urllib opener（自动继承系统代理）
    req = Request(url, headers=headers)
    from urllib.request import urlopen

    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
    return raw.decode(encoding, errors="ignore"), resp_headers


def _decode_unicode_escape(text: str) -> str:
    try:
        return text.encode("utf-8").decode("unicode_escape")
    except Exception:  # noqa: BLE001
        return text


def query_tencent_smartbox(
    query: str, *, fetcher: Callable[..., tuple[str, dict[str, str]]] = http_get_text
) -> list[dict[str, str]]:
    """通过腾讯 smartbox 反查中文名/简称对应的各市场代码。"""
    url = f"https://smartbox.gtimg.cn/s3/?v=2&q={quote(query)}&t=all"
    text, _ = fetcher(url, encoding="utf-8", timeout=4, use_proxy=False)
    match = re.search(r'v_hint="([^"]*)"', text)
    if not match or not match.group(1):
        return []
    raw_items = match.group(1).split("^")
    parsed: list[dict[str, str]] = []
    for item in raw_items:
        cols = item.split("~")
        if len(cols) < 3:
            continue
        mkt = cols[0].lower()
        code = cols[1]
        name = _decode_unicode_escape(cols[2])
        sec_type = cols[4] if len(cols) > 4 else ""
        if mkt not in {"sh", "sz", "bj", "hk", "us"}:
            continue
        parsed.append({"mkt": mkt, "code": code, "name": name, "type": sec_type})
    return parsed


def _cn_prefix(six_digits: str) -> str:
    if six_digits.startswith(("4", "8", "92")):
        return "bj"
    if six_digits.startswith(("5", "6", "9")):
        return "sh"
    return "sz"


def _cn_yahoo_suffix(prefix: str) -> str:
    return {"sh": "SS", "sz": "SZ", "bj": "BJ"}[prefix]


def _hk_yahoo_symbol(digits: str) -> str:
    num = digits.lstrip("0") or "0"
    return f"{num.zfill(4)}.HK"


def resolve_symbol(
    raw_symbol: str,
    market: str = "auto",
    *,
    smartbox_fn: Callable[[str], list[dict[str, str]]] | None = None,
) -> SymbolSpec:
    """将中文名、数字代码、后缀符号或币对解析为各数据源标准代码。"""
    q = raw_symbol.strip()
    if not q:
        raise ValueError("标的不能为空")

    mkt_hint = market.strip().lower()
    upper = q.upper()
    lower = q.lower()

    # 1. 加密货币显式识别
    cleaned_crypto = re.sub(r"[-/]", "", upper)
    if mkt_hint == "crypto" or cleaned_crypto.endswith(("USDT", "USDC", "BUSD")):
        pair = cleaned_crypto if cleaned_crypto.endswith(("USDT", "USDC", "BUSD", "BTC", "ETH")) else f"{cleaned_crypto}USDT"
        base = re.sub(r"(USDT|USDC|BUSD)$", "", pair)
        return SymbolSpec(
            query=q, market="crypto", name=pair, canonical=pair,
            tencent_code=pair, sina_code=pair, yahoo_code=f"{base}-USD",
            binance_code=pair, exchange_timezone="UTC",
        )
    if mkt_hint == "auto" and upper in COMMON_CRYPTO_BASES:
        pair = f"{upper}USDT"
        return SymbolSpec(
            query=q, market="crypto", name=pair, canonical=pair,
            tencent_code=pair, sina_code=pair, yahoo_code=f"{upper}-USD",
            binance_code=pair, exchange_timezone="UTC",
        )

    # 2. A股标准前/后缀
    m_cn_pref = re.fullmatch(r"(sh|sz|bj)(\d{6})", lower)
    if m_cn_pref:
        pref, code = m_cn_pref.groups()
        return SymbolSpec(
            query=q, market="cn", name=None, canonical=f"{pref}{code}",
            tencent_code=f"{pref}{code}", sina_code=f"{pref}{code}",
            yahoo_code=f"{code}.{_cn_yahoo_suffix(pref)}",
            binance_code=None, exchange_timezone=MARKET_TIMEZONE["cn"],
        )

    m_cn_suf = re.fullmatch(r"(\d{6})\.(SS|SH|SZ|BJ)", upper)
    if m_cn_suf:
        code, suf = m_cn_suf.groups()
        pref = "sh" if suf in {"SS", "SH"} else suf.lower()
        return SymbolSpec(
            query=q, market="cn", name=None, canonical=f"{pref}{code}",
            tencent_code=f"{pref}{code}", sina_code=f"{pref}{code}",
            yahoo_code=f"{code}.{_cn_yahoo_suffix(pref)}",
            binance_code=None, exchange_timezone=MARKET_TIMEZONE["cn"],
        )

    # 3. 港股标准前/后缀
    m_hk = re.fullmatch(r"(?:hk(\d{4,5})|(\d{4,5})\.HK)", q, re.IGNORECASE)
    if m_hk:
        digits = (m_hk.group(1) or m_hk.group(2)).zfill(5)
        return SymbolSpec(
            query=q, market="hk", name=None, canonical=f"hk{digits}",
            tencent_code=f"hk{digits}", sina_code=digits,
            yahoo_code=_hk_yahoo_symbol(digits),
            binance_code=None, exchange_timezone=MARKET_TIMEZONE["hk"],
        )

    # 4. 纯数字识别（6位 A股 / 5位 港股）
    if re.fullmatch(r"\d{6}", q) and mkt_hint in {"auto", "cn"}:
        pref = _cn_prefix(q)
        return SymbolSpec(
            query=q, market="cn", name=None, canonical=f"{pref}{q}",
            tencent_code=f"{pref}{q}", sina_code=f"{pref}{q}",
            yahoo_code=f"{q}.{_cn_yahoo_suffix(pref)}",
            binance_code=None, exchange_timezone=MARKET_TIMEZONE["cn"],
        )
    if re.fullmatch(r"\d{4,5}", q) and mkt_hint in {"auto", "hk"}:
        digits = q.zfill(5)
        return SymbolSpec(
            query=q, market="hk", name=None, canonical=f"hk{digits}",
            tencent_code=f"hk{digits}", sina_code=digits,
            yahoo_code=_hk_yahoo_symbol(digits),
            binance_code=None, exchange_timezone=MARKET_TIMEZONE["hk"],
        )

    # 5. 腾讯智能反查（支持中文名称及美股精确后缀如 usSNDK.OQ）
    lookup = smartbox_fn or query_tencent_smartbox
    has_non_ascii = any(ord(ch) > 127 for ch in q)
    if has_non_ascii or mkt_hint == "auto":
        try:
            candidates = lookup(q)
        except Exception:  # noqa: BLE001
            candidates = []

        if candidates:
            # 若指定了市场，优先过滤；否则按精确匹配、A股->美股->港股排序
            if mkt_hint in {"cn", "hk", "us"}:
                if mkt_hint == "cn":
                    filtered = [c for c in candidates if c["mkt"] in {"sh", "sz", "bj"}]
                else:
                    filtered = [c for c in candidates if c["mkt"] == mkt_hint]
                if filtered:
                    candidates = filtered
            else:
                # 若输入纯英文字母代码，优先匹配代码完全相同的记录
                if re.fullmatch(r"[A-Za-z.\-]+", q):
                    exact = [
                        c for c in candidates
                        if c["mkt"] == "us" and c["code"].split(".")[0].upper() == upper
                    ]
                    if exact:
                        candidates = exact

            chosen = candidates[0]
            mkt = chosen["mkt"]
            code = chosen["code"]
            cname = chosen["name"]
            if mkt in {"sh", "sz", "bj"}:
                return SymbolSpec(
                    query=q, market="cn", name=cname, canonical=f"{mkt}{code}",
                    tencent_code=f"{mkt}{code}", sina_code=f"{mkt}{code}",
                    yahoo_code=f"{code}.{_cn_yahoo_suffix(mkt)}",
                    binance_code=None, exchange_timezone=MARKET_TIMEZONE["cn"],
                )
            if mkt == "hk":
                digits = code.zfill(5)
                return SymbolSpec(
                    query=q, market="hk", name=cname, canonical=f"hk{digits}",
                    tencent_code=f"hk{digits}", sina_code=digits,
                    yahoo_code=_hk_yahoo_symbol(digits),
                    binance_code=None, exchange_timezone=MARKET_TIMEZONE["hk"],
                )
            if mkt == "us":
                base_us = code.split(".")[0].upper()
                tx_us = f"us{base_us}.{code.split('.')[1].upper()}" if "." in code else f"us{base_us}"
                return SymbolSpec(
                    query=q, market="us", name=cname, canonical=base_us,
                    tencent_code=tx_us, sina_code=base_us,
                    yahoo_code=base_us.replace("_", "-"),
                    binance_code=None, exchange_timezone=MARKET_TIMEZONE["us"],
                )

    # 6. 纯字母回退为美股代码
    m_us = re.fullmatch(r"(?:us)?([A-Za-z][A-Za-z0-9.\-]{0,11})(?:\.(OQ|N|AM|PK))?", q, re.IGNORECASE)
    if m_us and not has_non_ascii and mkt_hint in {"auto", "us"}:
        base_us = m_us.group(1).upper()
        suf_us = m_us.group(2).upper() if m_us.group(2) else None
        tx_code = f"us{base_us}.{suf_us}" if suf_us else f"us{base_us}"
        return SymbolSpec(
            query=q, market="us", name=None, canonical=base_us,
            tencent_code=tx_code, sina_code=base_us,
            yahoo_code=base_us.replace(".", "-"),
            binance_code=None, exchange_timezone=MARKET_TIMEZONE["us"],
        )

    raise ValueError(f"无法识别标的: {raw_symbol}")


def normalize_bar(bar: dict[str, Any], tz_name: str, interval: str) -> dict[str, Any]:
    """校验单根 K 线 OHLC 合法性并保留内部完整时间戳判断依据。"""
    ts = parse_timestamp(bar["timestamp"])
    o = float(bar["open"])
    h = float(bar["high"])
    l = float(bar["low"])
    c = float(bar["close"])
    if min(o, h, l, c) <= 0:
        raise ValueError("OHLC 价格必须大于 0")
    if not (l <= o <= h and l <= c <= h):
        raise ValueError("K线不满足 low <= open/close <= high")

    out: dict[str, Any] = {
        "timestamp": iso_timestamp(ts),
        "local_time": format_local_time(ts, tz_name, interval),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
    }
    if bar.get("volume") is not None:
        out["volume"] = float(bar["volume"])
    if "_close_ts" in bar and bar["_close_ts"] is not None:
        out["_close_ts"] = int(bar["_close_ts"])
    return out


def split_complete_bars(
    bars: list[dict[str, Any]],
    interval: str,
    source_time: int,
    *,
    market: str,
    tz_name: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """根据精确收盘时间戳或交易所收盘规则剥离仍在形成的 K 线。"""
    norm_iv = normalize_interval(interval)
    seconds = TIMEFRAME_POLICY[norm_iv]["seconds"]
    tz = ZoneInfo(tz_name)
    source_local = datetime.fromtimestamp(source_time, tz=tz)
    close_t = MARKET_CLOSE_TIME[market]

    sorted_bars = sorted(
        (normalize_bar(b, tz_name, norm_iv) for b in bars),
        key=lambda item: parse_timestamp(item["timestamp"]),
    )
    # 按时间戳去重（后者覆盖前者）
    dedup: dict[str, dict[str, Any]] = {}
    for b in sorted_bars:
        dedup[b["timestamp"]] = b
    ordered = list(dedup.values())

    complete: list[dict[str, Any]] = []
    forming: list[dict[str, Any]] = []

    for idx, bar in enumerate(ordered):
        bar_ts = parse_timestamp(bar["timestamp"])
        explicit_close = bar.pop("_close_ts", None)

        if explicit_close is not None:
            is_complete = source_time >= explicit_close
        elif norm_iv == "1d" and market != "crypto":
            bar_local_date = datetime.fromtimestamp(bar_ts, tz=tz).date()
            if source_local.date() > bar_local_date:
                is_complete = True
            elif source_local.date() < bar_local_date:
                is_complete = False
            else:
                is_complete = source_local.time() >= close_t
        elif norm_iv == "1w" and market != "crypto":
            # 若已有更晚一周的 K 线，当前这周必定已结束；否则检查本周五收盘时刻
            bar_local_date = datetime.fromtimestamp(bar_ts, tz=tz).date()
            friday = bar_local_date + timedelta(days=max(0, 4 - bar_local_date.weekday()))
            friday_close = datetime.combine(friday, close_t, tzinfo=tz)
            has_later_bar = idx < len(ordered) - 1
            is_complete = has_later_bar or (source_local >= friday_close)
        else:
            # 分钟级：美股常规时段 15:30 起始的 60m bar 实际在 16:00 收盘
            bar_local = datetime.fromtimestamp(bar_ts, tz=tz)
            if market == "us" and norm_iv == "60m" and bar_local.time() == datetime_time(15, 30):
                bar_close_ts = int(datetime.combine(bar_local.date(), datetime_time(16, 0), tzinfo=tz).timestamp())
            else:
                bar_close_ts = bar_ts + seconds
            is_complete = source_time >= bar_close_ts

        bar["is_complete"] = is_complete
        (complete if is_complete else forming).append(bar)

    return complete, forming


def _source_time_from_headers(headers: dict[str, str], fallback_now: int | None = None) -> int:
    date_hdr = headers.get("date")
    if date_hdr:
        try:
            dt = parsedate_to_datetime(date_hdr)
            return int(dt.timestamp())
        except Exception:  # noqa: BLE001
            pass
    return fallback_now if fallback_now is not None else int(time.time())


# ---------------- 数据源抓取与解析器 ----------------

def parse_tencent_fqkline(
    raw_text: str,
    symbol_code: str,
    interval: str,
    spec: SymbolSpec,
    source_time: int,
) -> dict[str, Any]:
    """解析腾讯 fqkline 日线/周线（优先前复权字段 qfqday / qfqweek）。"""
    payload = json.loads(raw_text)
    data = payload.get("data") or {}
    if not isinstance(data, dict) or symbol_code not in data:
        # 有时返回字典 key 大小写略异，尝试首个匹配 key
        node = next(iter(data.values()), None) if isinstance(data, dict) else None
    else:
        node = data[symbol_code]
    if not isinstance(node, dict):
        raise ValueError("tencent_empty_data")

    norm_iv = normalize_interval(interval)
    preferred_keys = ("qfqday", "day") if norm_iv == "1d" else ("qfqweek", "week")
    used_field = next((k for k in preferred_keys if node.get(k)), None)
    if not used_field:
        raise ValueError(f"tencent_missing_{norm_iv}_bars")

    tz = ZoneInfo(spec.exchange_timezone)
    open_t = MARKET_OPEN_TIME[spec.market]
    bars: list[dict[str, Any]] = []
    dropped = 0
    for row in node[used_field]:
        if not isinstance(row, list) or len(row) < 6:
            dropped += 1
            continue
        try:
            d_obj = datetime.strptime(str(row[0])[:10], "%Y-%m-%d").date()
            open_dt = datetime.combine(d_obj, open_t, tzinfo=tz)
            o, c, h, l, vol = float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])
            if min(o, h, l, c) <= 0:
                dropped += 1
                continue
            bars.append({
                "timestamp": int(open_dt.timestamp()),
                "open": o, "high": h, "low": l, "close": c, "volume": vol,
            })
        except (ValueError, TypeError):
            dropped += 1

    if not bars:
        raise ValueError("tencent_no_valid_bars")

    adjust = "forward_adjust" if used_field.startswith("qfq") else "unadjusted_or_split"
    warnings = []
    if not used_field.startswith("qfq"):
        warnings.append("tencent_non_qfq_field_used")
    if dropped:
        warnings.append(f"dropped_invalid_bars:{dropped}")

    return {
        "source": "tencent_fqkline",
        "data_channel": f"tencent:fqkline:{used_field}",
        "provider_symbol": symbol_code,
        "adjust_type": adjust,
        "trade_session": "intraday",
        "source_time": source_time,
        "bars": bars,
        "data_quality_warning": warnings or None,
    }


def fetch_tencent_fqkline(
    spec: SymbolSpec,
    interval: str,
    count: int,
    *,
    adjust_type: str = "forward_adjust",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    fetcher: Callable[..., tuple[str, dict[str, str]]] = http_get_text,
) -> dict[str, Any]:
    norm_iv = normalize_interval(interval)
    kind = "day" if norm_iv == "1d" else "week"
    adj_flag = "qfq" if adjust_type == "forward_adjust" else ""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={spec.tencent_code},{kind},,,{count},{adj_flag}"
    text, headers = fetcher(url, encoding="utf-8", timeout=timeout, use_proxy=False)
    return parse_tencent_fqkline(text, spec.tencent_code, norm_iv, spec, _source_time_from_headers(headers))


def parse_sina_cn_kline(
    raw_text: str, interval: str, spec: SymbolSpec, source_time: int
) -> dict[str, Any]:
    """解析新浪 A 股分钟线（day 字段是 bar 结束时间）。"""
    rows = json.loads(raw_text)
    if not isinstance(rows, list) or not rows:
        raise ValueError("sina_cn_empty_bars")

    norm_iv = normalize_interval(interval)
    seconds = TIMEFRAME_POLICY[norm_iv]["seconds"]
    tz = ZoneInfo(spec.exchange_timezone)
    bars: list[dict[str, Any]] = []
    dropped = 0
    for row in rows:
        try:
            end_dt = datetime.strptime(str(row["day"]).strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
            start_dt = end_dt - timedelta(seconds=seconds)
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            v = float(row.get("volume", 0))
            if min(o, h, l, c) <= 0:
                dropped += 1
                continue
            bars.append({
                "timestamp": int(start_dt.timestamp()),
                "_close_ts": int(end_dt.timestamp()),
                "open": o, "high": h, "low": l, "close": c, "volume": v,
            })
        except (KeyError, ValueError, TypeError):
            dropped += 1

    if not bars:
        raise ValueError("sina_cn_no_valid_bars")

    return {
        "source": "sina_cn_kline",
        "data_channel": f"sina:cn:{norm_iv}",
        "provider_symbol": spec.sina_code,
        "adjust_type": "unadjusted",
        "trade_session": "intraday",
        "source_time": source_time,
        "bars": bars,
        "data_quality_warning": ([f"dropped_invalid_bars:{dropped}"] if dropped else None),
    }


def fetch_sina_cn_kline(
    spec: SymbolSpec,
    interval: str,
    count: int,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    fetcher: Callable[..., tuple[str, dict[str, str]]] = http_get_text,
) -> dict[str, Any]:
    norm_iv = normalize_interval(interval)
    scale_map = {"5m": 5, "15m": 15, "30m": 30, "60m": 60, "1h": 60}
    scale = scale_map[norm_iv]
    url = (
        f"https://quotes.sina.cn/cn/api/json_v2.php/"
        f"CN_MarketDataService.getKLineData?symbol={spec.sina_code}&scale={scale}&ma=no&datalen={count}"
    )
    text, headers = fetcher(url, encoding="utf-8", timeout=timeout, use_proxy=False)
    return parse_sina_cn_kline(text, norm_iv, spec, _source_time_from_headers(headers))


def parse_sina_us_kline(
    raw_text: str, interval: str, spec: SymbolSpec, source_time: int
) -> dict[str, Any]:
    """解析新浪美股分钟线（d 字段为美东结束时间，60m 尾盘 16:00 实为 15:30~16:00 半小时段）。"""
    match = re.search(r"var d=\(\[(.*)\]\);", raw_text, re.DOTALL)
    if not match:
        raise ValueError("sina_us_invalid_payload")
    rows = json.loads("[" + match.group(1) + "]")
    if not rows:
        raise ValueError("sina_us_empty_bars")

    norm_iv = normalize_interval(interval)
    seconds = TIMEFRAME_POLICY[norm_iv]["seconds"]
    tz = ZoneInfo(spec.exchange_timezone)
    bars: list[dict[str, Any]] = []
    dropped = 0
    prev_end_dt: datetime | None = None

    for row in rows:
        try:
            end_dt = datetime.strptime(str(row["d"]).strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
            if (
                norm_iv in {"60m", "1h"}
                and end_dt.time() == datetime_time(16, 0)
                and prev_end_dt is not None
                and (end_dt - prev_end_dt) == timedelta(minutes=30)
            ):
                start_dt = end_dt - timedelta(minutes=30)
            else:
                start_dt = end_dt - timedelta(seconds=seconds)
            prev_end_dt = end_dt

            o, h, l, c = float(row["o"]), float(row["h"]), float(row["l"]), float(row["c"])
            v = float(row.get("v", 0))
            if min(o, h, l, c) <= 0:
                dropped += 1
                continue
            bars.append({
                "timestamp": int(start_dt.timestamp()),
                "_close_ts": int(end_dt.timestamp()),
                "open": o, "high": h, "low": l, "close": c, "volume": v,
            })
        except (KeyError, ValueError, TypeError):
            dropped += 1

    if not bars:
        raise ValueError("sina_us_no_valid_bars")

    return {
        "source": "sina_us_mink",
        "data_channel": f"sina:us:{norm_iv}",
        "provider_symbol": spec.sina_code,
        "adjust_type": "unadjusted",
        "trade_session": "intraday",
        "source_time": source_time,
        "bars": bars,
        "data_quality_warning": ([f"dropped_invalid_bars:{dropped}"] if dropped else None),
    }


def fetch_sina_us_kline(
    spec: SymbolSpec,
    interval: str,
    count: int,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    fetcher: Callable[..., tuple[str, dict[str, str]]] = http_get_text,
) -> dict[str, Any]:
    norm_iv = normalize_interval(interval)
    scale_map = {"5m": 5, "15m": 15, "30m": 30, "60m": 60, "1h": 60}
    scale = scale_map[norm_iv]
    url = f"https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20d=/US_MinKService.getMinK?symbol={spec.sina_code}&type={scale}"
    text, headers = fetcher(url, encoding="gbk", timeout=timeout, use_proxy=False)
    parsed = parse_sina_us_kline(text, norm_iv, spec, _source_time_from_headers(headers))
    parsed["bars"] = parsed["bars"][-(count + 2) :]
    return parsed


def parse_tencent_cn_mkline(
    raw_text: str, interval: str, spec: SymbolSpec, source_time: int
) -> dict[str, Any]:
    """解析腾讯 A 股分钟线 mkline（备用）。"""
    payload = json.loads(raw_text)
    node = (payload.get("data") or {}).get(spec.tencent_code) or {}
    norm_iv = normalize_interval(interval)
    key = {"5m": "m5", "15m": "m15", "30m": "m30", "60m": "m60", "1h": "m60"}[norm_iv]
    rows = node.get(key) or []
    if not rows:
        raise ValueError("tencent_mkline_empty")
    seconds = TIMEFRAME_POLICY[norm_iv]["seconds"]
    tz = ZoneInfo(spec.exchange_timezone)
    bars: list[dict[str, Any]] = []
    for row in rows:
        end_dt = datetime.strptime(str(row[0])[:12], "%Y%m%d%H%M").replace(tzinfo=tz)
        start_dt = end_dt - timedelta(seconds=seconds)
        o, c, h, l, vol = float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])
        if min(o, h, l, c) <= 0:
            continue
        bars.append({
            "timestamp": int(start_dt.timestamp()),
            "_close_ts": int(end_dt.timestamp()),
            "open": o, "high": h, "low": l, "close": c, "volume": vol,
        })
    if not bars:
        raise ValueError("tencent_mkline_no_valid_bars")
    return {
        "source": "tencent_mkline",
        "data_channel": f"tencent:mkline:{key}",
        "provider_symbol": spec.tencent_code,
        "adjust_type": "unadjusted",
        "trade_session": "intraday",
        "source_time": source_time,
        "bars": bars,
        "data_quality_warning": None,
    }


def fetch_tencent_cn_mkline(
    spec: SymbolSpec,
    interval: str,
    count: int,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    fetcher: Callable[..., tuple[str, dict[str, str]]] = http_get_text,
) -> dict[str, Any]:
    norm_iv = normalize_interval(interval)
    key = {"5m": "m5", "15m": "m15", "30m": "m30", "60m": "m60", "1h": "m60"}[norm_iv]
    url = f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={spec.tencent_code},{key},,{count}"
    text, headers = fetcher(url, encoding="utf-8", timeout=timeout, use_proxy=False)
    return parse_tencent_cn_mkline(text, norm_iv, spec, _source_time_from_headers(headers))


def parse_yahoo_chart_payload(
    payload: dict[str, Any],
    interval: str,
    spec: SymbolSpec,
    *,
    adjust_type: str = "forward_adjust",
    source_time: Any | None = None,
) -> dict[str, Any]:
    """解析 Yahoo chart 响应，按 adjclose 前复权并过滤收盘零量标记点。"""
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise ValueError(f"yahoo_chart_error:{chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise ValueError("yahoo_empty_result")
    result = results[0]
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote_obj = (indicators.get("quote") or [{}])[0] or {}
    adjclose_list = ((indicators.get("adjclose") or [{}])[0] or {}).get("adjclose") or []

    opens = quote_obj.get("open") or []
    highs = quote_obj.get("high") or []
    lows = quote_obj.get("low") or []
    closes = quote_obj.get("close") or []
    volumes = quote_obj.get("volume") or []

    norm_iv = normalize_interval(interval)
    tz_name = meta.get("exchangeTimezoneName") or spec.exchange_timezone
    tz = ZoneInfo(tz_name)
    close_t = MARKET_CLOSE_TIME.get(spec.market, datetime_time(16, 0))

    bars: list[dict[str, Any]] = []
    dropped = 0
    warnings: list[str] = []

    for idx, raw_ts in enumerate(timestamps):
        try:
            o, h, l, c = opens[idx], highs[idx], lows[idx], closes[idx]
        except IndexError:
            dropped += 1
            continue
        if None in (o, h, l, c) or min(float(o), float(h), float(l), float(c)) <= 0:
            dropped += 1
            continue

        vol = float(volumes[idx]) if idx < len(volumes) and volumes[idx] is not None else None
        # 仅保留交易所连续交易时段 [开盘, 收盘) 内的分钟线，过滤收盘竞价或零量收盘占位标记
        if norm_iv in {"5m", "15m", "30m", "60m", "1h"} and spec.market != "crypto":
            bar_local = datetime.fromtimestamp(int(raw_ts), tz=tz)
            if bar_local.time() >= close_t:
                dropped += 1
                continue

        factor = 1.0
        if adjust_type == "forward_adjust" and idx < len(adjclose_list) and adjclose_list[idx] not in (None, 0) and float(c) > 0:
            factor = float(adjclose_list[idx]) / float(c)

        bar: dict[str, Any] = {
            "timestamp": int(raw_ts),
            "open": float(o) * factor,
            "high": float(h) * factor,
            "low": float(l) * factor,
            "close": float(c) * factor,
        }
        if vol is not None:
            bar["volume"] = vol
        bars.append(bar)

    if not bars:
        raise ValueError("yahoo_no_valid_bars")
    if dropped:
        warnings.append(f"dropped_invalid_or_marker_bars:{dropped}")
    if adjust_type == "forward_adjust" and not adjclose_list:
        warnings.append("yahoo_missing_adjclose_unadjusted")

    src_ts = parse_timestamp(source_time) if source_time is not None else parse_timestamp(meta.get("regularMarketTime") or timestamps[-1])

    # 若请求 4h 而 Yahoo 返回 1h，则在内存聚合（无磁盘缓存）
    if norm_iv == "4h" and meta.get("dataGranularity") == "60m":
        bars = _aggregate_to_4h(bars)

    return {
        "source": "yahoo_finance_chart_api",
        "data_channel": "yahoo:chart",
        "provider_symbol": spec.yahoo_code,
        "adjust_type": adjust_type if adjclose_list else "unadjusted",
        "trade_session": "intraday",
        "source_time": src_ts,
        "bars": bars,
        "data_quality_warning": sorted(set(warnings)) or None,
    }


def _aggregate_to_4h(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[int, list[dict[str, Any]]] = {}
    for b in bars:
        ts = parse_timestamp(b["timestamp"])
        bucket = (ts // 14400) * 14400
        buckets.setdefault(bucket, []).append(b)
    out: list[dict[str, Any]] = []
    for bucket, members in sorted(buckets.items()):
        if len(members) < 4:
            # 正在进行中或不足 4 根的桶标记结束时间为桶末尾，交由 split_complete_bars 处理
            close_ts = bucket + 14400
        else:
            close_ts = bucket + 14400
        item: dict[str, Any] = {
            "timestamp": bucket,
            "_close_ts": close_ts if len(members) == 4 else bucket + 9999999,
            "open": members[0]["open"],
            "high": max(m["high"] for m in members),
            "low": min(m["low"] for m in members),
            "close": members[-1]["close"],
        }
        vols = [m.get("volume") for m in members]
        if all(v is not None for v in vols):
            item["volume"] = sum(float(v) for v in vols if v is not None)
        out.append(item)
    return out


def fetch_yahoo_chart(
    spec: SymbolSpec,
    interval: str,
    *,
    adjust_type: str = "forward_adjust",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    fetcher: Callable[..., tuple[str, dict[str, str]]] = http_get_text,
) -> dict[str, Any]:
    norm_iv = normalize_interval(interval)
    conf = TIMEFRAME_POLICY[norm_iv]
    errors: list[str] = []
    for host in YAHOO_HOSTS:
        url = (
            f"https://{host}/v8/finance/chart/{quote(spec.yahoo_code)}"
            f"?interval={conf['yahoo_interval']}&range={conf['yahoo_range']}"
            f"&includePrePost=false&events=div%2Csplits"
        )
        try:
            text, headers = fetcher(url, encoding="utf-8", timeout=timeout, use_proxy=True)
            parsed = parse_yahoo_chart_payload(
                json.loads(text),
                norm_iv,
                spec,
                adjust_type=adjust_type,
                source_time=_source_time_from_headers(headers) if "headers" in locals() else None,
            )
            parsed["data_channel"] = f"yahoo:chart:{host}"
            return parsed
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{host}:{type(exc).__name__}:{exc}")
    raise RuntimeError("yahoo_unavailable:" + ";".join(errors))


def parse_binance_klines(
    raw_text: str, interval: str, spec: SymbolSpec, source_time: int
) -> dict[str, Any]:
    """解析 Binance 公共 REST K 线（原生包含精确 openTime / closeTime）。"""
    rows = json.loads(raw_text)
    if not isinstance(rows, list) or not rows:
        raise ValueError("binance_empty_bars")
    norm_iv = normalize_interval(interval)
    bars: list[dict[str, Any]] = []
    for row in rows:
        bars.append({
            "timestamp": int(row[0]) // 1000,
            "_close_ts": (int(row[6]) + 1) // 1000,
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        })
    return {
        "source": "binance_public_klines",
        "data_channel": f"binance:spot:{norm_iv}",
        "provider_symbol": spec.binance_code or spec.canonical,
        "adjust_type": "none",
        "trade_session": "24x7",
        "source_time": source_time,
        "bars": bars,
        "data_quality_warning": None,
    }


def fetch_binance_klines(
    spec: SymbolSpec,
    interval: str,
    count: int,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    fetcher: Callable[..., tuple[str, dict[str, str]]] = http_get_text,
) -> dict[str, Any]:
    norm_iv = normalize_interval(interval)
    bn_interval = {"1w": "1w", "1d": "1d", "4h": "4h", "1h": "1h", "60m": "1h", "30m": "30m", "15m": "15m", "5m": "5m"}[norm_iv]
    symbol = spec.binance_code or spec.canonical
    errors: list[str] = []
    for host in BINANCE_HOSTS:
        url = f"https://{host}/api/v3/klines?symbol={symbol}&interval={bn_interval}&limit={count}"
        try:
            text, headers = fetcher(url, encoding="utf-8", timeout=timeout, use_proxy=True)
            parsed = parse_binance_klines(text, norm_iv, spec, _source_time_from_headers(headers))
            parsed["data_channel"] = f"binance:{host}:{bn_interval}"
            return parsed
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{host}:{type(exc).__name__}:{exc}")
    raise RuntimeError("binance_unavailable:" + ";".join(errors))


# ---------------- 分市场主备路由编排 ----------------

def _fetch_single_timeframe(
    spec: SymbolSpec,
    interval: str,
    *,
    adjust_type: str = "forward_adjust",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    mode: str = "full",
    include_bars: bool = False,
) -> dict[str, Any]:
    norm_iv = normalize_interval(interval)
    policy = TIMEFRAME_POLICY[norm_iv]
    fetch_count = policy["fetch_bars"]

    attempts: list[tuple[str, Callable[[], dict[str, Any]]]] = []
    if spec.market == "cn":
        if norm_iv in {"1d", "1w"}:
            attempts.append(("tencent_fqkline", lambda: fetch_tencent_fqkline(spec, norm_iv, fetch_count, adjust_type=adjust_type, timeout=timeout)))
            attempts.append(("yahoo_chart", lambda: fetch_yahoo_chart(spec, norm_iv, adjust_type=adjust_type, timeout=timeout)))
        else:
            attempts.append(("sina_cn_kline", lambda: fetch_sina_cn_kline(spec, norm_iv, fetch_count, timeout=timeout)))
            attempts.append(("tencent_mkline", lambda: fetch_tencent_cn_mkline(spec, norm_iv, fetch_count, timeout=timeout)))
            attempts.append(("yahoo_chart", lambda: fetch_yahoo_chart(spec, norm_iv, adjust_type=adjust_type, timeout=timeout)))
    elif spec.market == "us":
        if norm_iv in {"1d", "1w"}:
            attempts.append(("tencent_fqkline", lambda: fetch_tencent_fqkline(spec, norm_iv, fetch_count, adjust_type=adjust_type, timeout=timeout)))
            attempts.append(("yahoo_chart", lambda: fetch_yahoo_chart(spec, norm_iv, adjust_type=adjust_type, timeout=timeout)))
        else:
            attempts.append(("sina_us_mink", lambda: fetch_sina_us_kline(spec, norm_iv, fetch_count, timeout=timeout)))
            attempts.append(("yahoo_chart", lambda: fetch_yahoo_chart(spec, norm_iv, adjust_type=adjust_type, timeout=timeout)))
    elif spec.market == "hk":
        attempts.append(("yahoo_chart", lambda: fetch_yahoo_chart(spec, norm_iv, adjust_type=adjust_type, timeout=timeout)))
        if norm_iv in {"1d", "1w"}:
            attempts.append(("tencent_fqkline", lambda: fetch_tencent_fqkline(spec, norm_iv, fetch_count, adjust_type=adjust_type, timeout=timeout)))
    elif spec.market == "crypto":
        attempts.append(("binance_public", lambda: fetch_binance_klines(spec, norm_iv, fetch_count, timeout=timeout)))
        attempts.append(("yahoo_chart", lambda: fetch_yahoo_chart(spec, norm_iv, adjust_type="none", timeout=timeout)))

    fallback_reasons: list[str] = []
    started = time.perf_counter()
    raw_result: dict[str, Any] | None = None
    for idx, (provider_name, fn) in enumerate(attempts):
        try:
            raw_result = fn()
            if idx > 0:
                raw_result["source_fallback_reason"] = "; ".join(fallback_reasons)
            break
        except Exception as exc:  # noqa: BLE001
            fallback_reasons.append(f"{provider_name}_failed:{exc}")

    if raw_result is None:
        return {
            "interval": norm_iv,
            "timeframe_status": "unavailable",
            "errors": fallback_reasons,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }

    # 港股 Yahoo 1d/1w 在收盘当晚偶发末尾 close=None 被丢弃，校验后可用腾讯最新交易日补齐（今日前复权因子=1.0）
    if (
        spec.market == "hk"
        and norm_iv in {"1d", "1w"}
        and raw_result["source"] == "yahoo_finance_chart_api"
        and raw_result["bars"]
    ):
        tz = ZoneInfo(spec.exchange_timezone)
        last_y_date = datetime.fromtimestamp(parse_timestamp(raw_result["bars"][-1]["timestamp"]), tz=tz).date()
        src_date = datetime.fromtimestamp(int(raw_result["source_time"]), tz=tz).date()
        if last_y_date < src_date:
            try:
                tx = fetch_tencent_fqkline(spec, norm_iv, 10, adjust_type="unadjusted", timeout=min(timeout, 3))
                y_by_date = {
                    datetime.fromtimestamp(parse_timestamp(b["timestamp"]), tz=tz).date(): b
                    for b in raw_result["bars"]
                }
                newer = []
                overlap_ok = False
                for tb in tx["bars"]:
                    t_date = datetime.fromtimestamp(parse_timestamp(tb["timestamp"]), tz=tz).date()
                    if t_date in y_by_date:
                        yc = float(y_by_date[t_date]["close"])
                        tc = float(tb["close"])
                        if yc > 0 and abs(tc - yc) / yc <= 0.005:
                            overlap_ok = True
                    elif t_date > last_y_date:
                        newer.append(tb)
                if overlap_ok and newer:
                    raw_result["bars"].extend(newer)
                    warns = list(raw_result.get("data_quality_warning") or [])
                    warns.append("stitched_latest_bar_from_tencent_fqkline")
                    raw_result["data_quality_warning"] = warns
            except Exception:  # noqa: BLE001
                pass

    complete, forming = split_complete_bars(
        raw_result["bars"],
        norm_iv,
        raw_result["source_time"],
        market=spec.market,
        tz_name=spec.exchange_timezone,
    )
    complete = complete[-fetch_count:]

    package = build_timeframe_package(
        complete,
        forming,
        analysis_limit=policy["analysis_bars"],
        detail_limit=policy["detail_bars"],
        min_bars=policy["min_bars"],
        mode=mode,
        include_bars=include_bars,
    )
    package.update(
        {
            "interval": norm_iv,
            "source": raw_result["source"],
            "data_channel": raw_result["data_channel"],
            "provider_symbol": raw_result["provider_symbol"],
            "adjust_type": raw_result["adjust_type"],
            "trade_session": raw_result["trade_session"],
            "source_time": iso_timestamp(raw_result["source_time"]),
            "source_fallback_reason": raw_result.get("source_fallback_reason"),
            "data_quality_warning": raw_result.get("data_quality_warning"),
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    )
    return package


def _check_cross_timeframe_adjust_gap(frames: dict[str, dict[str, Any]]) -> str | None:
    """检查 A 股前复权日线与未复权分钟线在重合交易日是否出现除权跳空差异。"""
    daily = frames.get("1d")
    if not daily or daily.get("adjust_type") != "forward_adjust":
        return None
    d_bar = daily.get("last_complete_bar")
    if not d_bar:
        return None
    d_date = str(d_bar["local_time"])[:10]
    d_close = float(d_bar["close"])

    for iv, frame in frames.items():
        if iv in {"1d", "1w"} or frame.get("timeframe_status") == "unavailable":
            continue
        if frame.get("adjust_type") != "unadjusted":
            continue
        # 寻找分钟线里同日期或最近完整日的最后一根收盘价
        detail = frame.get("recent_detail_bars") or []
        same_day = [b for b in detail if str(b["local_time"]).startswith(d_date)]
        if same_day and d_close > 0:
            m_close = float(same_day[-1]["c"])
            diff_ratio = abs(m_close - d_close) / d_close
            if diff_ratio > 0.01:
                return (
                    f"intraday_unadjusted_mismatch_with_1d_qfq({iv}={m_close},1d={d_close})"
                )
    return None


def fetch_market_snapshot(
    symbol: str,
    *,
    market: str = "auto",
    intervals: list[str] | None = None,
    style: str = "swing",
    mode: str = "full",
    adjust_type: str = "forward_adjust",
    include_bars: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """一次调用并发获取单标的多周期实时行情快照与预计算指标（无磁盘缓存）。"""
    started = time.perf_counter()
    spec = resolve_symbol(symbol, market=market)
    if intervals:
        interval_list = list(dict.fromkeys(normalize_interval(iv) for iv in intervals))
    elif style == "intraday" and spec.market != "crypto":
        interval_list = list(INTRADAY_INTERVALS)
    else:
        interval_list = list(DEFAULT_INTERVALS_BY_MARKET[spec.market])

    frames: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(interval_list) or 1)) as pool:
        futures = {
            pool.submit(
                _fetch_single_timeframe,
                spec,
                iv,
                adjust_type=adjust_type,
                timeout=timeout,
                mode=mode,
                include_bars=include_bars,
            ): iv
            for iv in interval_list
        }
        for fut in as_completed(futures):
            iv = futures[fut]
            frames[iv] = fut.result()

    # 按请求顺序排列输出
    ordered_frames = {iv: frames[iv] for iv in interval_list}
    cross_warning = _check_cross_timeframe_adjust_gap(ordered_frames) if spec.market == "cn" else None

    timeframe_status = {iv: f.get("timeframe_status") for iv, f in ordered_frames.items()}
    return {
        "query": spec.query,
        "name": spec.name,
        "market": spec.market,
        "canonical_symbol": spec.canonical,
        "exchange_timezone": spec.exchange_timezone,
        "intervals_requested": interval_list,
        "mode": mode,
        "cache_enabled": False,
        "timeframe_status": timeframe_status,
        "cross_timeframe_warning": cross_warning,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "timeframes": ordered_frames,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    res_cmd = subparsers.add_parser("resolve", help="解析标的代码与所属市场")
    res_cmd.add_argument("--symbol", required=True)
    res_cmd.add_argument("--market", default="auto", choices=["auto", "cn", "hk", "us", "crypto"])

    snap_cmd = subparsers.add_parser("snapshot", help="获取无缓存多周期行情快照与预计算指标")
    snap_cmd.add_argument("--symbol", required=True, help="标的中文名或代码，如 紫金矿业 / 601899 / 159509 / 闪迪 / 00700 / BTCUSDT")
    snap_cmd.add_argument("--market", default="auto", choices=["auto", "cn", "hk", "us", "crypto"])
    snap_cmd.add_argument("--intervals", help="逗号分隔周期，默认股票 1d,60m,15m，币圈 4h,1h,15m")
    snap_cmd.add_argument("--style", default="swing", choices=["swing", "intraday"], help="swing=默认日+小时+15m；intraday=60m+15m+5m")
    snap_cmd.add_argument("--mode", default="full", choices=["full", "pa", "tech"], help="输出聚焦：full / pa / tech")
    snap_cmd.add_argument("--adjust", default="forward_adjust", choices=["forward_adjust", "unadjusted"])
    snap_cmd.add_argument("--include-bars", action="store_true", help="附加完整裁剪后 analysis_bars")
    snap_cmd.add_argument("--pretty", action="store_true", help="输出缩进格式化 JSON（默认紧凑 JSON 省上下文）")
    snap_cmd.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)

    args = parser.parse_args()
    if args.command == "resolve":
        spec = resolve_symbol(args.symbol, market=args.market)
        print(json.dumps({
            "query": spec.query,
            "market": spec.market,
            "name": spec.name,
            "canonical": spec.canonical,
            "tencent_code": spec.tencent_code,
            "sina_code": spec.sina_code,
            "yahoo_code": spec.yahoo_code,
            "binance_code": spec.binance_code,
            "exchange_timezone": spec.exchange_timezone,
            "longbridge": longbridge_status(),
        }, ensure_ascii=False, indent=2))
        return

    intervals = (
        [item.strip() for item in args.intervals.split(",") if item.strip()]
        if args.intervals
        else None
    )
    result = fetch_market_snapshot(
        args.symbol,
        market=args.market,
        intervals=intervals,
        style=args.style,
        mode=args.mode,
        adjust_type=args.adjust,
        include_bars=args.include_bars,
        timeout=args.timeout,
    )
    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
