from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.pipeline.layout import REPO_ROOT
from src.pipeline.signals import append_signal


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_slug(value: str, max_len: int = 24) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in text:
        text = text.replace("--", "-")
    text = text.strip("-")
    if not text:
        text = "untitled"
    return text[:max_len]


def _load_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _unique_dir(parent: Path, base_name: str) -> Path:
    candidate = parent / base_name
    if not candidate.exists():
        return candidate
    idx = 1
    while True:
        candidate = parent / f"{base_name}_{idx:03d}"
        if not candidate.exists():
            return candidate
        idx += 1


def _derive_signal_meta(snapshot: dict[str, Any]) -> dict[str, Any]:
    decision = snapshot.get("decision")
    if isinstance(decision, dict):
        action = decision.get("action")
        playbook = decision.get("playbook")
    else:
        action = decision
        playbook = snapshot.get("playbook")

    verdict = snapshot.get("verdict") if isinstance(snapshot.get("verdict"), dict) else {}
    trade = snapshot.get("trade") if isinstance(snapshot.get("trade"), dict) else {}

    return {
        "decision": action,
        "bias": snapshot.get("bias") or verdict.get("bias"),
        "confidence": snapshot.get("confidence") or verdict.get("confidence"),
        "playbook": playbook,
        "conditional_entry": snapshot.get("conditional_entry") or snapshot.get("entry_price") or trade.get("entry_price"),
        "stop_loss": snapshot.get("stop_loss") or trade.get("stop_loss"),
        "t1": snapshot.get("t1") or trade.get("t1"),
        "t2": snapshot.get("t2") or trade.get("t2"),
    }


def archive_conversation(
    *,
    symbol: str,
    source: str,
    title: str,
    transcript_md: str,
    metadata: dict[str, Any] | None = None,
    timestamp_utc: str | None = None,
    outputs_root: Path | None = None,
) -> dict[str, Any]:
    outputs_root = outputs_root or (REPO_ROOT / "outputs")
    symbol_u = symbol.upper().strip()
    ts = timestamp_utc or _now_utc_iso()
    ts_compact = ts.replace("-", "").replace(":", "").replace("T", "_").replace("Z", "")
    conv_base = outputs_root / "conversations" / symbol_u
    conv_base.mkdir(parents=True, exist_ok=True)

    base_name = f"{ts_compact}_{_safe_slug(source)}_{_safe_slug(title)}"
    conv_dir = _unique_dir(conv_base, base_name)
    conv_dir.mkdir(parents=True, exist_ok=True)

    transcript_path = conv_dir / "conversation.md"
    metadata_path = conv_dir / "metadata.json"
    transcript_path.write_text(transcript_md, encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata or {}, ensure_ascii=False, indent=2), encoding="utf-8")

    row = {
        "conversation_id": conv_dir.name,
        "symbol": symbol_u,
        "source": source,
        "title": title,
        "timestamp_utc": ts,
        "path": f"{symbol_u}/{conv_dir.name}/",
        "created_at": _now_utc_iso(),
        "metadata_file": "metadata.json",
        "transcript_file": "conversation.md",
    }

    _append_jsonl(outputs_root / "conversations" / "index.jsonl", row)
    _append_jsonl(conv_base / "index.jsonl", row)

    return {
        "conversation_id": conv_dir.name,
        "conversation_dir": conv_dir,
        "transcript_path": transcript_path,
        "metadata_path": metadata_path,
        "index_path": outputs_root / "conversations" / "index.jsonl",
        "symbol_index_path": conv_base / "index.jsonl",
    }


def archive_signal_record(
    *,
    symbol: str,
    snapshot: dict[str, Any],
    report_md: str,
    signal_meta: dict[str, Any] | None = None,
    outputs_root: Path | None = None,
) -> dict[str, Any]:
    meta = signal_meta or _derive_signal_meta(snapshot)
    return append_signal(
        symbol=symbol,
        snapshot=snapshot,
        report_md=report_md,
        signal_meta=meta,
        outputs_root=outputs_root,
    )


def import_conversations(
    *,
    import_file: Path,
    default_source: str = "import",
    default_symbol: str = "UNKNOWN",
    outputs_root: Path | None = None,
) -> dict[str, Any]:
    outputs_root = outputs_root or (REPO_ROOT / "outputs")
    imported = 0
    failed = 0
    details: list[dict[str, Any]] = []

    with import_file.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                symbol = str(row.get("symbol") or default_symbol).upper()
                source = str(row.get("source") or default_source)
                title = str(row.get("title") or f"import_{lineno}")
                timestamp_utc = row.get("timestamp_utc")
                metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}

                transcript_md = row.get("transcript_md")
                if transcript_md is None and row.get("transcript_file"):
                    transcript_md = _load_text(row["transcript_file"])
                if transcript_md is None:
                    raise ValueError("缺少 transcript_md/transcript_file")

                conv_result = archive_conversation(
                    symbol=symbol,
                    source=source,
                    title=title,
                    transcript_md=str(transcript_md),
                    metadata=metadata,
                    timestamp_utc=timestamp_utc,
                    outputs_root=outputs_root,
                )

                signal_result = None
                snapshot = row.get("signal_snapshot")
                if snapshot is None and row.get("signal_snapshot_file"):
                    snapshot = _load_json(row["signal_snapshot_file"])

                if snapshot is not None:
                    report_md = row.get("signal_report_md")
                    if report_md is None and row.get("signal_report_file"):
                        report_md = _load_text(row["signal_report_file"])
                    if report_md is None:
                        raise ValueError("存在 signal_snapshot，但缺少 signal_report_md/signal_report_file")

                    signal_meta = row.get("signal_meta")
                    if signal_meta is None and row.get("signal_meta_file"):
                        signal_meta = _load_json(row["signal_meta_file"])
                    if signal_meta is not None and not isinstance(signal_meta, dict):
                        raise ValueError("signal_meta 必须是对象")

                    signal_result = archive_signal_record(
                        symbol=symbol,
                        snapshot=snapshot,
                        report_md=str(report_md),
                        signal_meta=signal_meta,
                        outputs_root=outputs_root,
                    )

                imported += 1
                details.append(
                    {
                        "line": lineno,
                        "conversation_id": conv_result["conversation_id"],
                        "signal_id": signal_result["signal_id"] if signal_result else None,
                    }
                )
            except Exception as e:
                failed += 1
                details.append({"line": lineno, "error": str(e)})

    return {
        "imported": imported,
        "failed": failed,
        "details": details,
        "time_utc": _now_utc_iso(),
    }


def list_conversations(
    *,
    symbol: str | None = None,
    limit: int = 20,
    outputs_root: Path | None = None,
) -> list[dict[str, Any]]:
    outputs_root = outputs_root or (REPO_ROOT / "outputs")
    idx = outputs_root / "conversations" / "index.jsonl"
    if not idx.exists():
        return []

    symbol_u = symbol.upper() if symbol else None
    rows: list[dict[str, Any]] = []
    with idx.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if symbol_u and str(row.get("symbol", "")).upper() != symbol_u:
                continue
            rows.append(row)

    rows.sort(key=lambda x: (str(x.get("timestamp_utc") or ""), str(x.get("conversation_id") or "")), reverse=True)
    if limit > 0:
        rows = rows[:limit]
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="历史对话归档与导入工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="新增一条历史对话，可选同时归档信号")
    p_add.add_argument("--symbol", required=True, help="标的代码，如 BTCUSDT")
    p_add.add_argument("--source", required=True, help="来源，如 claude / chatgpt / gemini")
    p_add.add_argument("--title", required=True, help="对话标题")
    p_add.add_argument("--transcript-file", required=True, help="对话 Markdown 文件")
    p_add.add_argument("--metadata-file", default=None, help="可选，metadata JSON 文件")
    p_add.add_argument("--timestamp-utc", default=None, help="可选，UTC 时间，例 2026-03-30T10:00:00Z")
    p_add.add_argument("--signal-snapshot-file", default=None, help="可选，signal snapshot JSON")
    p_add.add_argument("--signal-report-file", default=None, help="可选，signal report Markdown")
    p_add.add_argument("--signal-meta-file", default=None, help="可选，signal meta JSON")

    p_import = sub.add_parser("import", help="从 JSONL 批量导入历史对话")
    p_import.add_argument("--file", required=True, help="JSONL 文件路径")
    p_import.add_argument("--default-source", default="import", help="默认来源")
    p_import.add_argument("--default-symbol", default="UNKNOWN", help="默认标的")

    p_list = sub.add_parser("list", help="查看已归档历史对话")
    p_list.add_argument("--symbol", default=None, help="可选，按标的过滤")
    p_list.add_argument("--limit", type=int, default=20, help="最多返回条数，0=全部")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "add":
        transcript_md = _load_text(args.transcript_file)
        metadata = _load_json(args.metadata_file) if args.metadata_file else {}

        conv = archive_conversation(
            symbol=args.symbol,
            source=args.source,
            title=args.title,
            transcript_md=transcript_md,
            metadata=metadata,
            timestamp_utc=args.timestamp_utc,
        )

        signal = None
        if args.signal_snapshot_file:
            snapshot = _load_json(args.signal_snapshot_file)
            report_md = _load_text(args.signal_report_file) if args.signal_report_file else ""
            signal_meta = _load_json(args.signal_meta_file) if args.signal_meta_file else None
            signal = archive_signal_record(
                symbol=args.symbol,
                snapshot=snapshot,
                report_md=report_md,
                signal_meta=signal_meta,
            )

        print(
            json.dumps(
                {
                    "conversation_id": conv["conversation_id"],
                    "conversation_dir": str(conv["conversation_dir"]),
                    "signal_id": signal["signal_id"] if signal else None,
                    "signal_dir": str(signal["signal_dir"]) if signal else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.command == "import":
        result = import_conversations(
            import_file=Path(args.file),
            default_source=args.default_source,
            default_symbol=args.default_symbol,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "list":
        rows = list_conversations(symbol=args.symbol, limit=args.limit)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    raise ValueError(f"未知命令: {args.command}")


if __name__ == "__main__":
    main()
