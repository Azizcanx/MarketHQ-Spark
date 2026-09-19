import json
import re
import sys
from pathlib import Path
from typing import Any


# =========================================================
# PROJECT ROOT
# =========================================================

PROJECT_ROOT = Path(
    __file__
).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )


# =========================================================
# DATABASE
# =========================================================

from database import (
    get_connection,
    init_db,
)


# =========================================================
# CONFIG
# =========================================================

VALIDATOR_VERSION = "method-validator-v2"

VALID_CATEGORIES = {
    "indicator",
    "filter",
    "algorithm",
    "tradingview_method",
    "python_method",
    "chart_method",
    "trend_method",
    "momentum_method",
    "volume_method",
    "scan_method",
    "system",
    "education",
    "other",
}

MIN_NAME_LENGTH = 2
MAX_NAME_LENGTH = 180
MIN_DESCRIPTION_LENGTH = 10


# =========================================================
# TABLE
# =========================================================

def init_validator_tables() -> None:

    conn = get_connection()

    try:

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS method_validation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                method_id INTEGER NOT NULL UNIQUE,

                validation_version TEXT NOT NULL,

                score INTEGER NOT NULL,

                status TEXT NOT NULL,

                category_valid INTEGER NOT NULL,

                name_valid INTEGER NOT NULL,

                description_valid INTEGER NOT NULL,

                content_valid INTEGER NOT NULL,

                hallucination_risk INTEGER NOT NULL,

                warnings_json TEXT,

                validation_notes TEXT,

                created_at TEXT NOT NULL,

                updated_at TEXT NOT NULL,

                FOREIGN KEY(method_id)
                REFERENCES method_registry(id)
                ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS
                idx_validation_status
                ON method_validation(status);

            CREATE INDEX IF NOT EXISTS
                idx_validation_score
                ON method_validation(score);
            """
        )

        conn.commit()

    finally:

        conn.close()


# =========================================================
# TIME
# =========================================================

def utc_now() -> str:

    from datetime import datetime, timezone

    return datetime.now(
        timezone.utc
    ).isoformat()


# =========================================================
# JSON
# =========================================================

def parse_json(
    value: Any,
    default: Any,
) -> Any:

    if isinstance(
        value,
        (dict, list),
    ):
        return value

    try:

        return json.loads(
            str(
                value
                or ""
            )
        )

    except (
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):

        return default


# =========================================================
# METHODS
# =========================================================

def get_methods() -> list[dict[str, Any]]:

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                canonical_name,
                category,
                description,
                source_count,
                confidence,
                status,
                registry_version
            FROM method_registry
            ORDER BY id
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


# =========================================================
# METHOD KNOWLEDGE
# =========================================================

def get_method_knowledge(
    method_id: int,
) -> list[dict[str, Any]]:

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                ki.id,
                ki.title,
                ki.content,
                ki.summary,
                ki.method,
                ki.symbols_json,
                ki.tags_json,
                ki.confidence
            FROM method_registry_items mri
            INNER JOIN knowledge_items ki
                ON ki.id = mri.knowledge_id
            WHERE mri.method_id = ?
            ORDER BY ki.id
            """,
            (
                method_id,
            ),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


# =========================================================
# NAME
# =========================================================

def validate_name(
    name: Any,
) -> tuple[bool, list[str]]:

    warnings = []

    name = str(
        name
        or ""
    ).strip()

    if len(name) < MIN_NAME_LENGTH:

        warnings.append(
            "Method adı çok kısa."
        )

        return False, warnings

    if len(name) > MAX_NAME_LENGTH:

        warnings.append(
            "Method adı aşırı uzun."
        )

    # Burada güçlü ifadeler artık otomatik
    # hallüsinasyon riski sayılmıyor.
    return True, warnings


# =========================================================
# CATEGORY
# =========================================================

def validate_category(
    category: Any,
) -> tuple[bool, list[str]]:

    warnings = []

    category = str(
        category
        or ""
    ).strip().lower()

    if category not in VALID_CATEGORIES:

        warnings.append(
            f"Geçersiz kategori: {category}"
        )

        return False, warnings

    return True, warnings


# =========================================================
# DESCRIPTION
# =========================================================

def validate_description(
    description: Any,
) -> tuple[bool, list[str]]:

    warnings = []

    description = str(
        description
        or ""
    ).strip()

    if len(description) < MIN_DESCRIPTION_LENGTH:

        warnings.append(
            "Açıklama çok kısa."
        )

        return False, warnings

    return True, warnings


# =========================================================
# CONTENT
# =========================================================

def validate_content(
    knowledge: dict[str, Any],
) -> tuple[bool, int, list[str]]:

    warnings = []

    raw_content = str(
        knowledge.get(
            "content"
        )
        or ""
    ).strip()

    if not raw_content:

        warnings.append(
            "Knowledge içeriği boş."
        )

        return False, 30, warnings

    structured = parse_json(
        raw_content,
        {},
    )

    if not isinstance(
        structured,
        dict,
    ):

        warnings.append(
            "Structured content JSON object değil."
        )

        return False, 40, warnings

    score = 100

    # -----------------------------------------------------
    # NAME
    # -----------------------------------------------------

    if not str(
        structured.get(
            "name"
            or ""
        )
    ).strip():

        warnings.append(
            "Structured content içinde name yok."
        )

        score -= 10

    # -----------------------------------------------------
    # TYPE
    # -----------------------------------------------------

    method_type = str(
        structured.get(
            "type"
            or ""
        )
    ).strip().lower()

    if method_type not in VALID_CATEGORIES:

        warnings.append(
            "Structured content içinde geçerli "
            "type bulunamadı."
        )

        score -= 20

    # -----------------------------------------------------
    # LOGIC
    # -----------------------------------------------------

    logic = str(
        structured.get(
            "logic"
            or ""
        )
    ).strip()

    if len(logic) < 10:

        warnings.append(
            "Logic alanı eksik veya çok kısa."
        )

        score -= 15

    # -----------------------------------------------------
    # EXPECTED ARRAY FIELDS
    # -----------------------------------------------------

    expected_lists = [
        "inputs",
        "parameters",
        "conditions",
        "signals",
        "timeframes",
        "visual_elements",
        "filters",
        "risk_notes",
        "failure_modes",
        "explicit_claims",
        "inferences",
    ]

    for field in expected_lists:

        value = structured.get(
            field
        )

        if (
            value is not None
            and not isinstance(
                value,
                list,
            )
        ):

            warnings.append(
                f"{field} alanı list değil."
            )

            score -= 3

    score = max(
        0,
        score,
    )

    return (
        score >= 60,
        score,
        warnings,
    )


# =========================================================
# HALLUCINATION RISK
# =========================================================

def detect_hallucination_risk(
    knowledge: dict[str, Any],
) -> tuple[int, list[str]]:

    warnings = []

    structured = parse_json(
        knowledge.get(
            "content"
        ),
        {},
    )

    if not isinstance(
        structured,
        dict,
    ):

        return (
            70,
            [
                "Structured content okunamadı."
            ],
        )

    risk = 0

    text = json.dumps(
        structured,
        ensure_ascii=False,
    ).lower()

    # -----------------------------------------------------
    # Number density
    # -----------------------------------------------------

    numbers = re.findall(
        r"\b\d+(?:[.,]\d+)?\b",
        text,
    )

    if len(numbers) >= 15:

        risk += 10

        warnings.append(
            "Çok sayıda sayısal değer var; "
            "kaynak doğrulaması önerilir."
        )

    elif len(numbers) >= 8:

        risk += 5

    # -----------------------------------------------------
    # Strong certainty language
    #
    # Artık sadece WARNING.
    # Hallucination riskine otomatik +10 yok.
    # -----------------------------------------------------

    certainty_phrases = [
        "kesin",
        "garanti",
        "mutlaka",
        "her zaman",
        "asla kaybettirmez",
        "kesin kazanç",
        "garantili kazanç",
    ]

    found = [
        phrase
        for phrase in certainty_phrases
        if phrase in text
    ]

    if found:

        warnings.append(
            "Güçlü kesinlik dili içeriyor; "
            "kaynakta gerçekten geçip geçmediği "
            "AI doğrulamasında kontrol edilmeli."
        )

    # -----------------------------------------------------
    # Formula density
    # -----------------------------------------------------

    formula_markers = [
        "=",
        "sqrt",
        "ln(",
        "log(",
        "ema(",
        "rsi(",
        "atr(",
    ]

    formula_count = sum(
        text.count(
            marker
        )
        for marker in formula_markers
    )

    if formula_count >= 10:

        risk += 10

        warnings.append(
            "Yüksek formül/parametre yoğunluğu; "
            "kaynak karşılaştırması gerekli."
        )

    elif formula_count >= 5:

        risk += 5

    return (
        min(
            100,
            risk,
        ),
        warnings,
    )


# =========================================================
# VALIDATE ONE METHOD
# =========================================================

def validate_method(
    method: dict[str, Any],
) -> dict[str, Any]:

    method_id = int(
        method["id"]
    )

    # -----------------------------------------------------
    # Basic checks
    # -----------------------------------------------------

    name_ok, name_warnings = (
        validate_name(
            method.get(
                "canonical_name"
            )
        )
    )

    category_ok, category_warnings = (
        validate_category(
            method.get(
                "category"
            )
        )
    )

    description_ok, description_warnings = (
        validate_description(
            method.get(
                "description"
            )
        )
    )

    knowledge = get_method_knowledge(
        method_id
    )

    warnings = [
        *name_warnings,
        *category_warnings,
        *description_warnings,
    ]

    content_scores = []

    content_ok = True

    highest_risk = 0

    for item in knowledge:

        item_ok, content_score, content_warnings = (
            validate_content(
                item
            )
        )

        hallucination_risk, risk_warnings = (
            detect_hallucination_risk(
                item
            )
        )

        content_scores.append(
            content_score
        )

        highest_risk = max(
            highest_risk,
            hallucination_risk,
        )

        if not item_ok:

            content_ok = False

        warnings.extend(
            content_warnings
        )

        warnings.extend(
            risk_warnings
        )

    if not knowledge:

        warnings.append(
            "Method için bağlı knowledge bulunamadı."
        )

        content_ok = False

    average_content_score = (
        sum(content_scores)
        /
        len(content_scores)
        if content_scores
        else 0
    )

    # -----------------------------------------------------
    # SCORE
    # -----------------------------------------------------

    score = 0

    if name_ok:
        score += 20

    if category_ok:
        score += 20

    if description_ok:
        score += 15

    if content_ok:
        score += 25
    else:
        score += 10

    source_count = int(
        method.get(
            "source_count"
        )
        or 0
    )

    if source_count >= 2:
        score += 5

    if source_count >= 5:
        score += 5

    extraction_confidence = float(
        method.get(
            "confidence"
        )
        or 0
    )

    if extraction_confidence >= 0.80:
        score += 5

    # Hallucination risk penalty is intentionally small.
    score -= int(
        highest_risk * 0.15
    )

    if average_content_score < 60:
        score -= 10

    score = max(
        0,
        min(
            100,
            score,
        ),
    )

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    if (
        score >= 85
        and highest_risk < 20
        and name_ok
        and category_ok
        and description_ok
        and content_ok
    ):

        status = "verified_candidate"

    elif (
        score >= 65
        and highest_risk < 50
    ):

        status = "needs_review"

    else:

        status = "low_confidence"

    notes = (
        f"Knowledge={len(knowledge)}, "
        f"avg_content_score="
        f"{average_content_score:.1f}, "
        f"hallucination_risk="
        f"{highest_risk}."
    )

    return {
        "method_id": method_id,

        "score": score,

        "status": status,

        "category_valid": category_ok,

        "name_valid": name_ok,

        "description_valid": description_ok,

        "content_valid": content_ok,

        "hallucination_risk": highest_risk,

        "warnings": list(
            dict.fromkeys(
                warnings
            )
        ),

        "notes": notes,
    }


# =========================================================
# SAVE
# =========================================================

def save_validation(
    result: dict[str, Any],
) -> None:

    conn = get_connection()

    try:

        now = utc_now()

        conn.execute(
            """
            INSERT INTO method_validation (

                method_id,

                validation_version,

                score,

                status,

                category_valid,

                name_valid,

                description_valid,

                content_valid,

                hallucination_risk,

                warnings_json,

                validation_notes,

                created_at,

                updated_at

            )

            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )

            ON CONFLICT(method_id)

            DO UPDATE SET

                validation_version =
                    excluded.validation_version,

                score =
                    excluded.score,

                status =
                    excluded.status,

                category_valid =
                    excluded.category_valid,

                name_valid =
                    excluded.name_valid,

                description_valid =
                    excluded.description_valid,

                content_valid =
                    excluded.content_valid,

                hallucination_risk =
                    excluded.hallucination_risk,

                warnings_json =
                    excluded.warnings_json,

                validation_notes =
                    excluded.validation_notes,

                updated_at =
                    excluded.updated_at
            """,
            (
                result[
                    "method_id"
                ],

                VALIDATOR_VERSION,

                result[
                    "score"
                ],

                result[
                    "status"
                ],

                1
                if result[
                    "category_valid"
                ]
                else 0,

                1
                if result[
                    "name_valid"
                ]
                else 0,

                1
                if result[
                    "description_valid"
                ]
                else 0,

                1
                if result[
                    "content_valid"
                ]
                else 0,

                result[
                    "hallucination_risk"
                ],

                json.dumps(
                    result[
                        "warnings"
                    ],
                    ensure_ascii=False,
                ),

                result[
                    "notes"
                ],

                now,

                now,
            ),
        )

        conn.commit()

    finally:

        conn.close()


# =========================================================
# UPDATE REGISTRY STATUS
# =========================================================

def update_method_status(
    method_id: int,
    validation_status: str,
) -> None:

    mapping = {
        "verified_candidate":
            "validated_candidate",

        "needs_review":
            "needs_review",

        "low_confidence":
            "low_confidence",
    }

    registry_status = mapping.get(
        validation_status,
        "needs_review",
    )

    conn = get_connection()

    try:

        conn.execute(
            """
            UPDATE method_registry

            SET status = ?,
                updated_at = ?

            WHERE id = ?
            """,
            (
                registry_status,
                utc_now(),
                method_id,
            ),
        )

        conn.commit()

    finally:

        conn.close()


# =========================================================
# PRINT SUMMARY
# =========================================================

def print_summary(
    results: list[dict[str, Any]],
) -> None:

    total = len(
        results
    )

    verified = sum(
        1
        for item in results
        if item["status"]
        == "verified_candidate"
    )

    review = sum(
        1
        for item in results
        if item["status"]
        == "needs_review"
    )

    low = sum(
        1
        for item in results
        if item["status"]
        == "low_confidence"
    )

    average_score = (
        sum(
            item["score"]
            for item in results
        )
        /
        total
        if total
        else 0
    )

    average_risk = (
        sum(
            item["hallucination_risk"]
            for item in results
        )
        /
        total
        if total
        else 0
    )

    print()

    print(
        "=========================================="
    )

    print(
        "📊 VALIDATOR V2 SONUCU"
    )

    print(
        "=========================================="
    )

    print(
        f"Toplam method: {total}"
    )

    print(
        f"Ortalama skor: "
        f"{average_score:.1f}/100"
    )

    print(
        f"Ortalama risk: "
        f"{average_risk:.1f}/100"
    )

    print(
        f"Verified candidate: {verified}"
    )

    print(
        f"Needs review: {review}"
    )

    print(
        f"Low confidence: {low}"
    )


# =========================================================
# SUSPICIOUS METHODS
# =========================================================

def print_suspicious(
    results: list[dict[str, Any]],
) -> None:

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                canonical_name,
                category
            FROM method_registry
            """
        ).fetchall()

        names = {
            int(row["id"]): (
                row["canonical_name"],
                row["category"],
            )
            for row in rows
        }

    finally:

        conn.close()

    suspicious = sorted(
        results,
        key=lambda item: (
            -item["hallucination_risk"],
            item["score"],
        ),
    )

    print()

    print(
        "EN ŞÜPHELİ KAYITLAR"
    )

    print(
        "------------------------------------------"
    )

    shown = 0

    for result in suspicious:

        if (
            result[
                "hallucination_risk"
            ] < 15
            and result[
                "score"
            ] >= 80
        ):

            continue

        method_name, category = names.get(
            result["method_id"],
            (
                "Unknown",
                "other",
            ),
        )

        print(
            f"[{category}] "
            f"{method_name} | "
            f"score={result['score']} | "
            f"risk="
            f"{result['hallucination_risk']} | "
            f"{result['status']}"
        )

        for warning in result[
            "warnings"
        ][:2]:

            print(
                f"   ⚠️ {warning}"
            )

        shown += 1

        if shown >= 20:

            break


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "=========================================="
    )

    print(
        "🔎 MARKET HQ METHOD VALIDATOR V2"
    )

    print(
        "=========================================="
    )

    init_db()

    init_validator_tables()

    methods = get_methods()

    print(
        f"Kontrol edilecek method: "
        f"{len(methods)}"
    )

    print(
        "API çağrısı kullanılmayacak."
    )

    results = []

    for index, method in enumerate(
        methods,
        start=1,
    ):

        print(
            f"[{index}/{len(methods)}] "
            f"{method['canonical_name']}"
        )

        try:

            result = validate_method(
                method
            )

            save_validation(
                result
            )

            update_method_status(
                method_id=result[
                    "method_id"
                ],

                validation_status=result[
                    "status"
                ],
            )

            results.append(
                result
            )

            print(
                f"   → "
                f"{result['status']} "
                f"| score="
                f"{result['score']} "
                f"| risk="
                f"{result['hallucination_risk']}"
            )

        except Exception as error:

            print(
                f"   ❌ Validation hatası: "
                f"{error}"
            )

    print_summary(
        results
    )

    print_suspicious(
        results
    )

    print()

    print(
        "✅ Method Validator V2 tamamlandı."
    )

    print(
        "Sonraki aşama:"
    )

    print(
        "Sadece şüpheli/önemli yöntemler "
        "AI ile kaynak karşılaştırmasına alınacak."
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
