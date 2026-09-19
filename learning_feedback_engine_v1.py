import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "market_hq.db"
STATE_FILE = BASE_DIR / "learning_feedback_state.json"

QUEUE_OPEN_STATUSES = {"", "OPEN", "QUEUED", "PENDING", "READY", "NEW", "ACTIVE", "WORKING"}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path, fallback):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(fallback)) else fallback
    except Exception:
        return fallback


def write_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def connect():
    conn = sqlite3.connect(DB_FILE, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn, table):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone()
    return row is not None


def column_names(conn, table):
    return {
        row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')
    }


def queue_is_open(status):
    return str(status or "").upper() in QUEUE_OPEN_STATUSES


def queue_exists_for_update(conn, update_id):
    if not table_exists(conn, "brain_research_queue"):
        return False
    row = conn.execute(
        """
        SELECT 1
        FROM brain_research_queue
        WHERE metadata_json LIKE ?
          AND UPPER(COALESCE(status,'')) NOT IN ('COMPLETED','CANCELLED','DONE','CLOSED')
        LIMIT 1
        """,
        (f'%"source_brain_update_id": {int(update_id)}%',),
    ).fetchone()
    return row is not None


def queue_exists_for_question(conn, question):
    row = conn.execute(
        """
        SELECT 1
        FROM brain_research_queue
        WHERE question = ?
          AND UPPER(COALESCE(status,'')) NOT IN ('COMPLETED','CANCELLED','DONE','CLOSED')
        LIMIT 1
        """,
        (question,),
    ).fetchone()
    return row is not None


def build_follow_up(row):
    verdict = str(row["verdict"] or "").upper()
    subject = str(row["subject_name"] or row["subject_key"] or "bilinmeyen konu")
    claim_text = str(row["claim_text"] or "")
    review_id = int(row["review_id"])
    score = row["support_score"]

    if verdict == "CONTRADICTORY":
        question = f"{subject} için çelişkili kanıtı bağımsız kaynaklarla yeniden test et: {claim_text}"
        reason = "Evidence review CONTRADICTORY; bağımsız yeniden araştırma gerekli."
        priority = 100
        mode = "CONTRADICTION_RECHECK"
    elif verdict == "PARTIALLY_SUPPORTIVE":
        question = f"{subject} bulgusunun hangi koşullarda geçerli olduğunu araştır: {claim_text}"
        reason = "Evidence review PARTIALLY_SUPPORTIVE; koşul ve sınırları netleştir."
        priority = 80
        mode = "CONDITION_DISCOVERY"
    elif verdict == "INSUFFICIENT":
        question = f"{subject} için eksik kanıtı tamamla ve ölçülebilir veri ara: {claim_text}"
        reason = "Evidence review INSUFFICIENT; evidence gap kapatılmalı."
        priority = 70
        mode = "EVIDENCE_GAP"
    else:
        return None

    return {
        "question": question,
        "reason": reason,
        "priority": priority,
        "mode": mode,
        "review_id": review_id,
        "support_score": score,
    }


def run_once():
    started_at = utc_now()
    state = read_json(STATE_FILE, {})
    result = {
        "engine": "learning_feedback_engine_v4",
        "started_at": started_at,
        "finished_at": None,
        "status": "STARTING",
        "updates_seen": 0,
        "follow_up_candidates": 0,
        "queue_created": 0,
        "already_present": 0,
        "skipped": 0,
        "errors": [],
    }

    if not DB_FILE.exists():
        result["status"] = "ERROR"
        result["errors"].append("market_hq.db bulunamadı.")
        result["finished_at"] = utc_now()
        write_json(STATE_FILE, result)
        return result

    conn = None
    try:
        conn = connect()

        required_tables = [
            "brain_research_queue",
            "brain_research_brain_updates",
            "brain_research_evidence_reviews",
        ]
        missing = [
            t for t in required_tables
            if not table_exists(conn, t)
        ]
        if missing:
            result["status"] = "BLOCKED"
            result["errors"].append(
                f"Eksik tablo: {', '.join(missing)}"
            )
            result["finished_at"] = utc_now()
            write_json(STATE_FILE, result)
            return result

        update_cols = column_names(
            conn,
            "brain_research_brain_updates",
        )
        review_cols = column_names(
            conn,
            "brain_research_evidence_reviews",
        )
        queue_cols = column_names(
            conn,
            "brain_research_queue",
        )

        required_update_cols = {"id", "review_id"}
        required_review_cols = {
            "id",
            "verdict",
            "score",
            "knowledge_item_id",
        }
        required_queue_cols = {
            "question",
            "reason",
            "priority",
            "status",
            "created_at",
            "updated_at",
            "metadata_json",
        }

        if not required_update_cols.issubset(update_cols):
            result["status"] = "BLOCKED"
            result["errors"].append(
                "brain_research_brain_updates review_id şemada yok."
            )
            result["finished_at"] = utc_now()
            write_json(STATE_FILE, result)
            return result

        if not required_review_cols.issubset(review_cols):
            result["status"] = "BLOCKED"
            result["errors"].append(
                "brain_research_evidence_reviews için gereken alanlar eksik."
            )
            result["finished_at"] = utc_now()
            write_json(STATE_FILE, result)
            return result

        if not required_queue_cols.issubset(queue_cols):
            result["status"] = "BLOCKED"
            result["errors"].append(
                "brain_research_queue şeması beklenen alanları içermiyor."
            )
            result["finished_at"] = utc_now()
            write_json(STATE_FILE, result)
            return result

        # The real review table has `score`, not `support_score`, and
        # has no claim_id. Follow-up research can still be generated
        # from knowledge_item_id + observation_id + review_text.
        knowledge_exists = table_exists(conn, "knowledge_items")
        knowledge_cols = (
            column_names(conn, "knowledge_items")
            if knowledge_exists
            else set()
        )

        observation_exists = table_exists(conn, "brain_observations")
        observation_cols = (
            column_names(conn, "brain_observations")
            if observation_exists
            else set()
        )

        title_expr = (
            "k.title"
            if knowledge_exists and "title" in knowledge_cols
            else "''"
        )
        summary_expr = (
            "k.summary"
            if knowledge_exists and "summary" in knowledge_cols
            else "''"
        )
        method_expr = (
            "k.method"
            if knowledge_exists and "method" in knowledge_cols
            else "''"
        )
        observation_text_candidates = []
        for col in (
            "observation_text",
            "summary",
            "description",
            "condition_text",
            "market_regime",
        ):
            if col in observation_cols:
                observation_text_candidates.append(
                    f"o.{col}"
                )
        observation_expr = (
            "COALESCE("
            + ", ".join(observation_text_candidates)
            + ")"
            if observation_text_candidates
            else "''"
        )

        knowledge_join = (
            "LEFT JOIN knowledge_items k "
            "ON k.id = r.knowledge_item_id"
            if knowledge_exists
            and "id" in knowledge_cols
            and "knowledge_item_id" in review_cols
            else ""
        )

        observation_join = ""
        observation_expr_sql = "''"
        if (
            observation_exists
            and "id" in observation_cols
            and "observation_id" in review_cols
        ):
            observation_join = (
                "LEFT JOIN brain_observations o "
                "ON o.id = r.observation_id"
            )
            observation_expr_sql = observation_expr

        rows = conn.execute(
            f"""
            SELECT
                u.id AS update_id,
                u.created_at AS update_created_at,
                r.id AS review_id,
                r.verdict AS verdict,
                r.score AS support_score,
                r.knowledge_item_id AS knowledge_item_id,
                r.observation_id AS observation_id,
                r.review_text AS review_text,
                r.next_question AS next_question,
                {title_expr} AS knowledge_title,
                {summary_expr} AS knowledge_summary,
                {method_expr} AS knowledge_method,
                {observation_expr_sql} AS observation_context
            FROM brain_research_brain_updates u
            INNER JOIN brain_research_evidence_reviews r
                ON r.id = u.review_id
            {knowledge_join}
            {observation_join}
            WHERE UPPER(COALESCE(r.verdict,'')) IN
                ('CONTRADICTORY','PARTIALLY_SUPPORTIVE','INSUFFICIENT')
            ORDER BY u.id ASC
            LIMIT 500
            """
        ).fetchall()

        print(
            "Schema: updates.review_id=True, "
            f"review_columns={sorted(review_cols)}"
        )
        print(
            f"Knowledge join={'ON' if knowledge_join else 'OFF'}, "
            f"Observation join={'ON' if observation_join else 'OFF'}"
        )

        result["updates_seen"] = len(rows)
        result["schema"] = {
            "brain_research_brain_updates": sorted(update_cols),
            "brain_research_evidence_reviews": sorted(review_cols),
            "brain_research_queue": sorted(queue_cols),
            "knowledge_items": sorted(knowledge_cols),
            "brain_observations": sorted(observation_cols),
        }

        inserts = []

        for row in rows:
            try:
                verdict = str(
                    row["verdict"] or ""
                ).upper()

                knowledge_title = str(
                    row["knowledge_title"]
                    or row["knowledge_method"]
                    or f"knowledge #{row['knowledge_item_id']}"
                )
                claim_text = str(
                    row["knowledge_summary"]
                    or row["review_text"]
                    or ""
                )
                observation_context = str(
                    row["observation_context"]
                    or ""
                )
                explicit_next_question = str(
                    row["next_question"]
                    or ""
                ).strip()

                review_id = int(row["review_id"])
                score = row["support_score"]

                # Prefer the review's own next_question when available.
                if explicit_next_question:
                    question = explicit_next_question
                    mode = "REVIEW_NEXT_QUESTION"
                    reason = (
                        f"Evidence review #{review_id} follow-up "
                        "sorusu doğrudan review kaydından alındı."
                    )
                    priority = 80
                elif verdict == "CONTRADICTORY":
                    question = (
                        f"{knowledge_title} için çelişkili kanıtı "
                        f"bağımsız kaynaklarla yeniden test et. "
                        f"{claim_text}"
                    )
                    mode = "CONTRADICTION_RECHECK"
                    reason = (
                        "Evidence review CONTRADICTORY; "
                        "bağımsız yeniden araştırma gerekli."
                    )
                    priority = 100
                elif verdict == "PARTIALLY_SUPPORTIVE":
                    question = (
                        f"{knowledge_title} bulgusunun hangi koşullarda "
                        f"geçerli olduğunu araştır. {claim_text}"
                    )
                    mode = "CONDITION_DISCOVERY"
                    reason = (
                        "Evidence review PARTIALLY_SUPPORTIVE; "
                        "koşul ve sınırları netleştir."
                    )
                    priority = 80
                elif verdict == "INSUFFICIENT":
                    question = (
                        f"{knowledge_title} için eksik kanıtı tamamla "
                        f"ve ölçülebilir veri ara. {claim_text}"
                    )
                    mode = "EVIDENCE_GAP"
                    reason = (
                        "Evidence review INSUFFICIENT; "
                        "evidence gap kapatılmalı."
                    )
                    priority = 70
                else:
                    result["skipped"] += 1
                    continue

                result["follow_up_candidates"] += 1

                update_id = int(row["update_id"])
                if (
                    queue_exists_for_update(conn, update_id)
                    or queue_exists_for_question(conn, question)
                ):
                    result["already_present"] += 1
                    continue

                metadata = {
                    "generated_by": "learning_feedback_engine_v4",
                    "source_brain_update_id": update_id,
                    "source_evidence_review_id": review_id,
                    "knowledge_item_id": (
                        int(row["knowledge_item_id"])
                        if row["knowledge_item_id"] is not None
                        else None
                    ),
                    "observation_id": (
                        int(row["observation_id"])
                        if row["observation_id"] is not None
                        else None
                    ),
                    "mode": mode,
                    "verdict": verdict,
                    "score": score,
                    "observation_context": observation_context[:1000],
                    "generated_at": utc_now(),
                }

                fields = {
                    "question": question,
                    "reason": reason,
                    "priority": priority,
                    "status": "QUEUED",
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                    "metadata_json": json.dumps(
                        metadata,
                        ensure_ascii=False,
                    ),
                }

                columns = [
                    k for k in fields
                    if k in queue_cols
                ]
                values = [
                    fields[k] for k in columns
                ]

                # Use only queue columns that actually exist.
                optional = {
                    "target_node_id": None,
                    "target_claim_id": None,
                }
                for name, value in optional.items():
                    if (
                        name in queue_cols
                        and value is not None
                    ):
                        columns.append(name)
                        values.append(int(value))

                placeholders = ", ".join(
                    "?" for _ in values
                )

                conn.execute(
                    f"""
                    INSERT INTO brain_research_queue
                    ({", ".join(columns)})
                    VALUES ({placeholders})
                    """,
                    values,
                )

                result["queue_created"] += 1
                inserts.append(
                    {
                        "update_id": update_id,
                        "review_id": review_id,
                        "question": question,
                        "priority": priority,
                    }
                )

            except Exception as exc:
                result["errors"].append(
                    f"update işlenemedi: {exc}"
                )

        conn.commit()

        result["status"] = "COMPLETED"
        result["created"] = inserts[-50:]
        result["finished_at"] = utc_now()
        result["previous_state"] = (
            state.get("status")
            if isinstance(state, dict)
            else None
        )

        write_json(STATE_FILE, result)
        return result

    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()

        result["status"] = "ERROR"
        result["errors"].append(
            f"SQLite: {exc}"
        )
        result["finished_at"] = utc_now()
        write_json(STATE_FILE, result)
        return result

    except Exception as exc:
        if conn is not None:
            conn.rollback()

        result["status"] = "ERROR"
        result["errors"].append(str(exc))
        result["finished_at"] = utc_now()
        write_json(STATE_FILE, result)
        return result

    finally:
        if conn is not None:
            conn.close()

def main():
    result = run_once()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"COMPLETED", "BLOCKED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
