# -*- coding: utf-8 -*-
"""
MarketHQ Paper Evidence -> Brain Research Bridge V1
====================================================

Amaç:
    Paper Evidence Aggregator çıktısını mevcut MarketHQ Brain
    research queue katmanına bağlamak.

Akış:
    paper_trading_results/*.json
            ↓
    Paper Evidence Aggregator V2.3
            ↓
    paper_evidence_results/*.json
            ↓
    THIS BRIDGE
            ↓
    brain_research_queue
            ↓
    Existing Brain Research Loop / Research Agent

GÜVENLİK:
    - Araştırma/paper katmanıdır.
    - Broker bağlantısı yoktur.
    - Gerçek emir yoktur.
    - Gerçek para ile işlem yoktur.
    - learned_rules tablosuna yazmaz.
    - brain_claims tablosuna yazmaz.
    - Mevcut Brain araştırma kuyruğunu kullanır.
    - Aynı evidence için aktif duplicate queue görevi oluşturmaz.

Kullanım:
    .\\.venv\\Scripts\\python.exe paper_evidence_brain_bridge_v1.py

Belirli evidence dosyası:
    .\\.venv\\Scripts\\python.exe paper_evidence_brain_bridge_v1.py --file <JSON>

Belirli strateji:
    .\\.venv\\Scripts\\python.exe paper_evidence_brain_bridge_v1.py --strategy-id STR-XXXX
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================================
# PATHS / CONFIG
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "market_hq.db"
EVIDENCE_DIR = PROJECT_ROOT / "paper_evidence_results"

ENGINE_NAME = "MARKETHQ_PAPER_EVIDENCE_BRAIN_BRIDGE"
ENGINE_VERSION = "V1.0"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False

QUEUE_PRIORITY_WEAK = 8
QUEUE_PRIORITY_MIXED = 7
QUEUE_PRIORITY_INSUFFICIENT = 7
QUEUE_PRIORITY_PROMISING = 5

SUPPORTED_CLASSIFICATIONS = {
    "WEAK_PAPER_EVIDENCE",
    "MIXED_PAPER_EVIDENCE",
    "INSUFFICIENT_PAPER_EVIDENCE",
    "PROMISING_PAPER_EVIDENCE",
}


# ============================================================================
# HELPERS
# ============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def compact_json(data: Any) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def table_exists(
    conn: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(
    conn: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute(
            f'PRAGMA table_info("{table_name}")'
        ).fetchall()
    }


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"market_hq.db bulunamadı: {DB_PATH}"
        )

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
    )
    conn.row_factory = sqlite3.Row
    return conn


def load_json(path: Path) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError(
            f"Evidence JSON object bekleniyordu: {path}"
        )

    return data


# ============================================================================
# EVIDENCE DISCOVERY
# ============================================================================

def evidence_files() -> list[Path]:
    if not EVIDENCE_DIR.exists():
        return []

    return sorted(
        [
            path
            for path in EVIDENCE_DIR.glob("*.json")
            if path.is_file()
        ],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )


def extract_strategy_id(data: dict[str, Any]) -> str:
    direct = safe_text(data.get("strategy_id"))
    if direct:
        return direct.upper()

    aggregate = data.get("aggregate")
    if isinstance(aggregate, dict):
        value = safe_text(aggregate.get("strategy_id"))
        if value:
            return value.upper()

    return ""


def extract_strategy_name(data: dict[str, Any]) -> str:
    direct = safe_text(data.get("strategy_name"))
    if direct:
        return direct

    aggregate = data.get("aggregate")
    if isinstance(aggregate, dict):
        return safe_text(
            aggregate.get("strategy_name"),
            "Unknown Strategy",
        )

    return "Unknown Strategy"


def extract_classification(data: dict[str, Any]) -> str:
    return safe_text(
        data.get("classification"),
        "UNKNOWN",
    ).upper()


def extract_aggregate(data: dict[str, Any]) -> dict[str, Any]:
    aggregate = data.get("aggregate")
    if isinstance(aggregate, dict):
        return aggregate
    return {}


def extract_symbols(data: dict[str, Any]) -> list[str]:
    breakdown = data.get("symbol_breakdown")

    if isinstance(breakdown, dict):
        return sorted(
            {
                safe_text(key).upper()
                for key in breakdown
                if safe_text(key)
            }
        )

    if isinstance(breakdown, list):
        symbols: set[str] = set()

        for item in breakdown:
            if isinstance(item, dict):
                symbol = safe_text(
                    item.get("symbol")
                ).upper()
                if symbol:
                    symbols.add(symbol)

        return sorted(symbols)

    diagnostics = data.get("diagnostics")
    if isinstance(diagnostics, dict):
        values = diagnostics.get(
            "unique_symbols_loaded",
            [],
        )
        if isinstance(values, list):
            return sorted(
                {
                    safe_text(value).upper()
                    for value in values
                    if safe_text(value)
                }
            )

    return []


def select_evidence_file(
    explicit_file: str | None = None,
    strategy_id: str | None = None,
) -> Path:
    if explicit_file:
        path = Path(explicit_file)

        if not path.is_absolute():
            path = PROJECT_ROOT / path

        if not path.exists():
            raise FileNotFoundError(
                f"Evidence dosyası bulunamadı: {path}"
            )

        return path

    wanted = (
        safe_text(strategy_id).upper()
        if strategy_id
        else ""
    )

    for path in evidence_files():
        try:
            data = load_json(path)
        except Exception:
            continue

        current_strategy = extract_strategy_id(data)

        if wanted and current_strategy != wanted:
            continue

        if (
            extract_classification(data)
            in SUPPORTED_CLASSIFICATIONS
        ):
            return path

    raise FileNotFoundError(
        "Kullanılabilir paper evidence raporu bulunamadı. "
        f"strategy_id={wanted or 'ALL'}, "
        f"directory={EVIDENCE_DIR}"
    )


# ============================================================================
# EVIDENCE NORMALIZATION
# ============================================================================

def normalize_evidence(
    path: Path,
    data: dict[str, Any],
) -> dict[str, Any]:
    aggregate = extract_aggregate(data)

    strategy_id = extract_strategy_id(data)
    strategy_name = extract_strategy_name(data)
    classification = extract_classification(data)

    if not strategy_id:
        raise ValueError(
            f"Evidence içinde strategy_id bulunamadı: {path}"
        )

    if classification not in SUPPORTED_CLASSIFICATIONS:
        raise ValueError(
            "Desteklenmeyen evidence classification: "
            f"{classification}"
        )

    symbols = extract_symbols(data)

    total_trades = safe_int(
        aggregate.get(
            "total_trades",
            aggregate.get("trades", 0),
        )
    )

    win_rate = safe_float(
        aggregate.get(
            "aggregate_win_rate_percent",
            aggregate.get(
                "win_rate_percent",
                0.0,
            ),
        )
    )

    net_pnl = safe_float(
        aggregate.get(
            "aggregate_net_pnl",
            aggregate.get("net_pnl", 0.0),
        )
    )

    aggregate_return = safe_float(
        aggregate.get(
            "aggregate_return_percent",
            aggregate.get("return_percent", 0.0),
        )
    )

    average_pf = safe_float(
        aggregate.get(
            "average_profit_factor",
            aggregate.get("avg_profit_factor", 0.0),
        )
    )

    worst_pf = safe_float(
        aggregate.get(
            "worst_profit_factor",
            0.0,
        )
    )

    average_dd = safe_float(
        aggregate.get(
            "average_max_drawdown_percent",
            aggregate.get("avg_max_drawdown_percent", 0.0),
        )
    )

    raw_runs = safe_int(
        data.get("raw_run_count", 0)
    )

    unique_runs = safe_int(
        data.get("unique_run_count", raw_runs)
    )

    duplicate_runs = safe_int(
        data.get("duplicate_run_count", 0)
    )

    reasons = data.get("reasons")
    if not isinstance(reasons, list):
        reasons = []

    actions = data.get("research_actions")
    if not isinstance(actions, list):
        actions = []

    return {
        "source_file": str(path),
        "source_name": path.name,
        "source_key": path.resolve().as_posix(),
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "classification": classification,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "raw_runs": raw_runs,
        "unique_runs": unique_runs,
        "duplicate_runs": duplicate_runs,
        "total_trades": total_trades,
        "win_rate_percent": win_rate,
        "aggregate_net_pnl": net_pnl,
        "aggregate_return_percent": aggregate_return,
        "average_profit_factor": average_pf,
        "worst_profit_factor": worst_pf,
        "average_max_drawdown_percent": average_dd,
        "reasons": [
            safe_text(item)
            for item in reasons
            if safe_text(item)
        ],
        "research_actions": [
            safe_text(item)
            for item in actions
            if safe_text(item)
        ],
        "aggregate": aggregate,
    }


# ============================================================================
# QUEUE DECISION
# ============================================================================

def build_task(
    evidence: dict[str, Any],
) -> tuple[str, str, int, str]:
    strategy = evidence["strategy_name"]
    strategy_id = evidence["strategy_id"]
    classification = evidence["classification"]
    symbols = evidence["symbols"]

    symbol_text = (
        ", ".join(symbols)
        if symbols
        else "sembol bilgisi yok"
    )

    if classification == "WEAK_PAPER_EVIDENCE":
        task_type = "PAPER_EVIDENCE_WEAK_REVIEW"
        priority = QUEUE_PRIORITY_WEAK

        question = (
            f"{strategy} ({strategy_id}) için paper evidence zayıf. "
            "Negatif aggregate sonucu hangi parametre, piyasa rejimi, "
            "giriş/çıkış kuralı veya maliyet varsayımının açıkladığını "
            "araştır ve sonraki bağımsız backtest/WFO çalışmasını tanımla."
        )

        reason = (
            "Paper evidence zayıf olarak sınıflandırıldı. "
            f"{evidence['symbol_count']} sembol, "
            f"{evidence['unique_runs']} unique replay ve "
            f"{evidence['total_trades']} toplam işlem kullanıldı. "
            f"Aggregate return={evidence['aggregate_return_percent']:.4f}%, "
            f"average PF={evidence['average_profit_factor']:.4f}. "
            f"İncelenen semboller: {symbol_text}."
        )

    elif classification == "MIXED_PAPER_EVIDENCE":
        task_type = "PAPER_EVIDENCE_MIXED_REVIEW"
        priority = QUEUE_PRIORITY_MIXED

        question = (
            f"{strategy} ({strategy_id}) için paper evidence karışık. "
            "Pozitif ve negatif sembol/rejim gruplarını ayır; "
            "robust davranışı ve kırılma noktalarını araştır."
        )

        reason = (
            "Paper evidence mixed olarak sınıflandırıldı. "
            f"Semboller: {symbol_text}. "
            f"Aggregate return={evidence['aggregate_return_percent']:.4f}%, "
            f"average PF={evidence['average_profit_factor']:.4f}."
        )

    elif classification == "INSUFFICIENT_PAPER_EVIDENCE":
        task_type = "PAPER_EVIDENCE_INSUFFICIENT_DATA"
        priority = QUEUE_PRIORITY_INSUFFICIENT

        question = (
            f"{strategy} ({strategy_id}) için paper evidence örneklemi "
            "yetersiz. Daha geniş sembol, dönem veya replay örneklemi "
            "tasarla ve bağımsız validation gereksinimini belirle."
        )

        reason = (
            "Paper evidence örneklemi bağımsız karar için yetersiz. "
            f"Unique replay={evidence['unique_runs']}, "
            f"symbols={evidence['symbol_count']}, "
            f"trades={evidence['total_trades']}."
        )

    else:
        task_type = "PAPER_EVIDENCE_PROMISING_VALIDATION"
        priority = QUEUE_PRIORITY_PROMISING

        question = (
            f"{strategy} ({strategy_id}) için pozitif paper evidence "
            "bağımsız WFO, validation ve cost-stress ile doğrulanıyor mu?"
        )

        reason = (
            "Paper evidence promising olarak sınıflandırıldı; "
            "Brain bunu doğrulanmış kural olarak kabul etmemeli. "
            f"Semboller: {symbol_text}, "
            f"aggregate return={evidence['aggregate_return_percent']:.4f}%, "
            f"average PF={evidence['average_profit_factor']:.4f}."
        )

    return (
        question,
        reason,
        priority,
        task_type,
    )


def queue_fingerprint(
    evidence: dict[str, Any],
    task_type: str,
) -> str:
    payload = {
        "engine": ENGINE_NAME,
        "strategy_id": evidence["strategy_id"],
        "classification": evidence["classification"],
        "source_key": evidence["source_key"],
        "unique_runs": evidence["unique_runs"],
        "symbols": evidence["symbols"],
        "task_type": task_type,
    }

    return hashlib.sha256(
        compact_json(payload).encode("utf-8")
    ).hexdigest()


# ============================================================================
# DUPLICATE CONTROL
# ============================================================================

def active_fingerprint_exists(
    conn: sqlite3.Connection,
    fingerprint: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM brain_research_queue
        WHERE status IN ('queued', 'working')
          AND metadata_json LIKE ?
        LIMIT 1
        """,
        (f'%"queue_fingerprint":"{fingerprint}"%',),
    ).fetchone()

    return row is not None


def active_strategy_task_exists(
    conn: sqlite3.Connection,
    strategy_id: str,
    task_type: str,
) -> bool:
    row = conn.execute(
        """
        SELECT metadata_json
        FROM brain_research_queue
        WHERE status IN ('queued', 'working')
        """
    ).fetchall()

    for item in row:
        metadata_text = safe_text(
            item["metadata_json"]
        )

        if (
            f'"strategy_id":"{strategy_id}"'
            in metadata_text
            and
            f'"task_type":"{task_type}"'
            in metadata_text
        ):
            return True

    return False


# ============================================================================
# QUEUE INSERT
# ============================================================================

def enqueue(
    conn: sqlite3.Connection,
    evidence: dict[str, Any],
) -> tuple[int | None, str]:
    question, reason, priority, task_type = build_task(
        evidence
    )

    fingerprint = queue_fingerprint(
        evidence,
        task_type,
    )

    if active_fingerprint_exists(
        conn,
        fingerprint,
    ):
        return None, "fingerprint_duplicate"

    if active_strategy_task_exists(
        conn,
        evidence["strategy_id"],
        task_type,
    ):
        return None, "active_strategy_task_duplicate"

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "created_at": utc_now(),
        "task_type": task_type,
        "queue_fingerprint": fingerprint,
        "strategy_id": evidence["strategy_id"],
        "strategy_name": evidence["strategy_name"],
        "classification": evidence["classification"],
        "paper_evidence_source": evidence["source_file"],
        "paper_evidence_source_name": evidence["source_name"],
        "symbol_count": evidence["symbol_count"],
        "symbols": evidence["symbols"],
        "raw_runs": evidence["raw_runs"],
        "unique_runs": evidence["unique_runs"],
        "duplicate_runs": evidence["duplicate_runs"],
        "total_trades": evidence["total_trades"],
        "win_rate_percent": evidence["win_rate_percent"],
        "aggregate_net_pnl": evidence["aggregate_net_pnl"],
        "aggregate_return_percent": evidence[
            "aggregate_return_percent"
        ],
        "average_profit_factor": evidence[
            "average_profit_factor"
        ],
        "worst_profit_factor": evidence[
            "worst_profit_factor"
        ],
        "average_max_drawdown_percent": evidence[
            "average_max_drawdown_percent"
        ],
        "evidence_reasons": evidence["reasons"],
        "research_actions": evidence["research_actions"],
        "research_only": True,
        "execution_enabled": False,
    }

    now = utc_now()

    cursor = conn.execute(
        """
        INSERT INTO brain_research_queue (
            question,
            reason,
            priority,
            target_node_id,
            target_claim_id,
            status,
            created_at,
            updated_at,
            metadata_json
        )
        VALUES (?, ?, ?, NULL, NULL, 'queued', ?, ?, ?)
        """,
        (
            question,
            reason,
            priority,
            now,
            now,
            compact_json(metadata),
        ),
    )

    return safe_int(cursor.lastrowid), "created"


# ============================================================================
# REPORT
# ============================================================================

def print_report(
    evidence: dict[str, Any],
    evidence_path: Path,
    queue_id: int | None,
    queue_status: str,
) -> None:
    print()
    print("=" * 82)
    print(
        "🧠 MARKET HQ PAPER EVIDENCE → BRAIN RESEARCH BRIDGE V1.0"
    )
    print("=" * 82)
    print()
    print(f"Research Only       : {RESEARCH_ONLY}")
    print(f"Execution Enabled   : {EXECUTION_ENABLED}")
    print()
    print(f"Evidence File       : {evidence_path}")
    print(f"Strategy ID         : {evidence['strategy_id']}")
    print(f"Strategy            : {evidence['strategy_name']}")
    print(f"Classification      : {evidence['classification']}")
    print()
    print("-" * 82)
    print("PAPER EVIDENCE")
    print("-" * 82)
    print(
        f"Symbols             : {evidence['symbol_count']} "
        f"({', '.join(evidence['symbols'])})"
    )
    print(f"Raw Runs            : {evidence['raw_runs']}")
    print(f"Unique Runs         : {evidence['unique_runs']}")
    print(f"Duplicate Runs      : {evidence['duplicate_runs']}")
    print(f"Total Trades        : {evidence['total_trades']}")
    print(
        f"Win Rate            : "
        f"{evidence['win_rate_percent']:.2f}%"
    )
    print(
        f"Aggregate Net PnL   : "
        f"{evidence['aggregate_net_pnl']:.2f}"
    )
    print(
        f"Aggregate Return    : "
        f"{evidence['aggregate_return_percent']:.4f}%"
    )
    print(
        f"Average Profit Factor: "
        f"{evidence['average_profit_factor']:.4f}"
    )
    print(
        f"Worst Profit Factor : "
        f"{evidence['worst_profit_factor']:.4f}"
    )
    print()
    print("-" * 82)
    print("BRAIN QUEUE")
    print("-" * 82)

    if queue_status == "created":
        print("Status              : CREATED")
        print(f"Queue ID            : {queue_id}")
        print("Queue Status        : queued")
    elif queue_status == "fingerprint_duplicate":
        print("Status              : SKIPPED")
        print("Reason              : aynı evidence fingerprint zaten aktif")
    elif queue_status == "active_strategy_task_duplicate":
        print("Status              : SKIPPED")
        print("Reason              : aynı strategy/task aktif durumda")
    else:
        print(f"Status              : {queue_status}")

    print()
    print("-" * 82)
    print("SAFETY")
    print("-" * 82)
    print("• brain_research_queue kullanıldı.")
    print("• learned_rules değiştirilmedi.")
    print("• brain_claims değiştirilmedi.")
    print("• Broker bağlantısı yok.")
    print("• Gerçek emir yok.")
    print("• Execution Enabled = False.")
    print("=" * 82)
    print()


# ============================================================================
# MAIN
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "MarketHQ Paper Evidence -> Brain Research Queue Bridge"
        )
    )

    parser.add_argument(
        "--file",
        default=None,
        help="Belirli paper evidence JSON dosyası.",
    )

    parser.add_argument(
        "--strategy-id",
        default=None,
        help="Belirli strategy ID.",
    )

    return parser


def run(
    explicit_file: str | None = None,
    strategy_id: str | None = None,
) -> int | None:
    if not RESEARCH_ONLY:
        raise RuntimeError(
            "Safety gate: RESEARCH_ONLY=False."
        )

    if EXECUTION_ENABLED:
        raise RuntimeError(
            "Safety gate: EXECUTION_ENABLED=True."
        )

    required_tables = {
        "brain_research_queue",
    }

    conn = open_db()

    try:
        missing = sorted(
            table
            for table in required_tables
            if not table_exists(conn, table)
        )

        if missing:
            raise RuntimeError(
                "Brain queue şeması eksik: "
                + ", ".join(missing)
            )

        columns = table_columns(
            conn,
            "brain_research_queue",
        )

        required_columns = {
            "id",
            "question",
            "reason",
            "priority",
            "target_node_id",
            "target_claim_id",
            "status",
            "created_at",
            "updated_at",
            "metadata_json",
        }

        missing_columns = sorted(
            required_columns - columns
        )

        if missing_columns:
            raise RuntimeError(
                "brain_research_queue şeması uyumsuz. "
                "Eksik kolonlar: "
                + ", ".join(missing_columns)
            )

        evidence_path = select_evidence_file(
            explicit_file=explicit_file,
            strategy_id=strategy_id,
        )

        raw_data = load_json(evidence_path)

        evidence = normalize_evidence(
            evidence_path,
            raw_data,
        )

        if (
            strategy_id
            and evidence["strategy_id"]
            != safe_text(strategy_id).upper()
        ):
            raise ValueError(
                "İstenen strategy_id ile evidence strategy_id "
                "eşleşmiyor."
            )

        queue_id, status = enqueue(
            conn,
            evidence,
        )

        conn.commit()

        print_report(
            evidence=evidence,
            evidence_path=evidence_path,
            queue_id=queue_id,
            queue_status=status,
        )

        return queue_id

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        run(
            explicit_file=args.file,
            strategy_id=args.strategy_id,
        )

    except KeyboardInterrupt:
        print()
        print("İşlem kullanıcı tarafından durduruldu.")

    except Exception as exc:
        print()
        print("=" * 82)
        print("❌ PAPER EVIDENCE → BRAIN BRIDGE HATASI")
        print("=" * 82)
        print(f"{type(exc).__name__}: {exc}")
        print("=" * 82)
        raise SystemExit(1)


if __name__ == "__main__":
    main()


