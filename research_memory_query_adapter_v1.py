from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


def find_project_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    candidates = [script_dir, script_dir.parent, Path.cwd(), Path.cwd().parent]
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "market_hq.db").exists():
            return candidate
    if script_dir.name.lower() == "agents":
        return script_dir.parent
    return script_dir


BASE_DIR = find_project_root()
DB_PATH = BASE_DIR / "market_hq.db"


def safe_json(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def normalize_decision(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    strategy_id = str(payload.get("strategyId") or "").strip() or None
    current_experiment_id = str(payload.get("currentExperimentId") or "").strip() or None
    symbol = str(payload.get("symbol") or "").strip() or None
    timeframe = str(payload.get("timeframe") or "").strip() or None
    limit = max(1, min(100, int(payload.get("limit") or 20)))

    if not DB_PATH.exists():
        print(json.dumps({
            "success": False,
            "enabled": True,
            "status": "FAILED",
            "reason": f"Research database not found: {DB_PATH}",
            "strategyId": strategy_id,
            "currentExperimentId": current_experiment_id,
            "count": 0,
            "records": [],
            "summary": {
                "total": 0, "promising": 0, "mixed": 0,
                "reject": 0, "inconclusive": 0, "averageConfidence": None,
            },
        }, ensure_ascii=False))
        raise SystemExit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        required = ("research_memory", "research_experiments")
        missing = [name for name in required if not table_exists(conn, name)]
        if missing:
            raise RuntimeError("Research Memory schema missing: " + ", ".join(missing))

        where = ["1 = 1"]
        params: list[Any] = []
        if strategy_id:
            where.append("re.strategy_id = ?")
            params.append(strategy_id)
        if current_experiment_id:
            where.append("re.experiment_id <> ?")
            params.append(current_experiment_id)
        query = f"""
            SELECT
                rm.id,
                rm.memory_key,
                rm.experiment_id AS experiment_db_id,
                rm.result_id AS result_db_id,
                rr.result_id AS external_result_id,
                re.experiment_id,
                re.strategy_id,
                re.symbol,
                re.timeframe,
                rm.memory_type,
                rm.title,
                rm.summary,
                rm.decision,
                rm.confidence,
                rm.status,
                rm.evidence_json,
                rm.learning_json,
                rm.metadata_json,
                rm.created_at,
                rm.updated_at
            FROM research_memory rm
            INNER JOIN research_experiments re
                ON re.id = rm.experiment_id
            LEFT JOIN research_results rr
                ON rr.id = rm.result_id
            WHERE {' AND '.join(where)}
            ORDER BY rm.updated_at DESC, rm.id DESC
            LIMIT ?
        """
        params.append(limit)
        rows = conn.execute(query, params).fetchall()

        records: list[dict[str, Any]] = []
        confidence_values: list[float] = []
        summary = {
            "total": len(rows),
            "promising": 0,
            "mixed": 0,
            "reject": 0,
            "inconclusive": 0,
            "averageConfidence": None,
        }

        for row in rows:
            learning = safe_json(row["learning_json"])
            evidence = safe_json(row["evidence_json"])
            metadata = safe_json(row["metadata_json"])

            learning_dict = learning if isinstance(learning, dict) else {}
            evidence_dict = evidence if isinstance(evidence, dict) else {}

            decision_value = row["decision"]
            if decision_value is None:
                decision_value = learning_dict.get("decision")
            if decision_value is None:
                decision_value = evidence_dict.get("decision")
            decision = normalize_decision(decision_value)

            if "PROMISING" in decision:
                summary["promising"] += 1
            elif "MIXED" in decision or "WEAK" in decision:
                summary["mixed"] += 1
            elif "REJECT" in decision:
                summary["reject"] += 1
            else:
                summary["inconclusive"] += 1

            confidence = None
            confidence_value = row["confidence"]
            if confidence_value is None:
                confidence_value = learning_dict.get("confidence")
            if confidence_value is None:
                confidence_value = evidence_dict.get("confidence")
            if confidence_value is not None:
                try:
                    confidence = float(confidence_value)
                    confidence = max(0.0, min(1.0, confidence))
                    confidence_values.append(confidence)
                except (TypeError, ValueError):
                    confidence = None

            records.append({
                "id": int(row["id"]) if row["id"] is not None else None,
                "memoryKey": row["memory_key"],
                "experimentId": row["experiment_id"],
                "resultId": row["external_result_id"],
                "strategyId": row["strategy_id"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "memoryType": row["memory_type"],
                "title": row["title"],
                "summary": row["summary"],
                "decision": decision_value,
                "confidence": confidence,
                "status": row["status"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "evidence": evidence,
                "learning": learning,
                "metadata": metadata,
                "performance": learning_dict.get("performance"),
                "validation": learning_dict.get("validation"),
                "robustness": learning_dict.get("robustness"),
                "wfo": learning_dict.get("wfo"),
            })

        if confidence_values:
            summary["averageConfidence"] = round(
                sum(confidence_values) / len(confidence_values), 4
            )

        print(json.dumps({
            "success": True,
            "enabled": True,
            "status": "COMPLETED",
            "reason": None,
            "adapterPath": str(Path(__file__).resolve()),
            "strategyId": strategy_id,
            "currentExperimentId": current_experiment_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "count": len(records),
            "records": records,
            "summary": summary,
            "safety": {
                "researchOnly": True,
                "databaseWritePerformed": False,
                "liveExecutionEnabled": False,
                "brokerExecutionEnabled": False,
            },
        }, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "success": False,
            "enabled": True,
            "status": "FAILED",
            "reason": str(exc),
            "count": 0,
            "records": [],
            "summary": {
                "total": 0, "promising": 0, "mixed": 0,
                "reject": 0, "inconclusive": 0, "averageConfidence": None,
            },
            "safety": {
                "researchOnly": True,
                "databaseWritePerformed": False,
                "liveExecutionEnabled": False,
                "brokerExecutionEnabled": False,
            },
        }, ensure_ascii=False))
        raise SystemExit(1)

