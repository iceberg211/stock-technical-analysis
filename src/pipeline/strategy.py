"""策略配置加载器 — 从 strategies/ 目录读取 YAML Playbook 配置。"""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

_STRATEGIES_DIR = Path(__file__).resolve().parent.parent.parent / "strategies"
_cache: dict[str, dict[str, Any]] = {}


def _load_yaml(name: str) -> dict[str, Any]:
    path = _STRATEGIES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Strategy not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_strategy(name: str) -> dict[str, Any]:
    if name in _cache:
        return _cache[name]
    raw = _load_yaml(name)
    extends = raw.pop("extends", None)
    if extends and extends != name:
        base = load_strategy(extends)
        merged = _deep_merge(base, raw)
    else:
        merged = raw
    _cache[name] = merged
    return merged


def list_strategies() -> list[str]:
    return sorted(p.stem for p in _STRATEGIES_DIR.glob("*.yaml") if not p.stem.startswith("_"))


def get_conditions(name: str, direction: str) -> dict[str, Any]:
    s = load_strategy(name)
    return s.get("conditions", {}).get(direction, {})


def get_stop_loss_atr(name: str) -> float:
    return load_strategy(name).get("stop_loss", {}).get("atr_multiplier", 1.0)


def get_targets(name: str) -> tuple[float, float]:
    t = load_strategy(name).get("targets", {})
    return t.get("t1_atr_multiplier", 1.6), t.get("t2_atr_multiplier", 3.0)
