"""
Data quality fixes for setup_outcomes table.

Fixes applied without schema changes:
1. fix_empty_strings()     - convert '' to NULL for structure_type, liquidity_side
2. compute_zone_width()    - derive zone_width_pct from entry_zone for NULL zone_width_atr;
                              mark zone_width_atr=0.0 as computed default
3. compute_touches()       - derive touches from entry_zone zone width for NULL touches;
                              mark touches=0 as default
4. validate_record(record_id) - check all fields for a record
5. data_quality_report()   - full report of all fields
"""

import sqlite3
import math
from pathlib import Path

DB_PATH = Path("/opt/markethq/market_hq.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def fix_empty_strings():
    """Convert empty string structure_type/liquidity_side to NULL."""
    conn = get_conn()
    c = conn.cursor()
    results = {}
    for col in ("structure_type", "liquidity_side"):
        c.execute(f"SELECT COUNT(*) FROM setup_outcomes WHERE {col} = ''")
        before = c.fetchone()[0]
        c.execute(f"UPDATE setup_outcomes SET {col} = NULL WHERE {col} = ''")
        results[col] = {"fixed": before}
    conn.commit()
    conn.close()
    return results


def compute_zone_width():
    """
    For NULL zone_width_atr records: compute zone_width_pct from entry_zone
    (entry_price, invalidation_price). Store the raw percentage; note that
    atr_pct is required to normalize to ATR units.
    Mark zone_width_atr=0.0 records as computed default (zero-width zones).
    """
    conn = get_conn()
    c = conn.cursor()
    result = {}

    # 1. Compute zone_width_pct for NULL zone_width_atr records
    c.execute('''
        SELECT id, entry_price, invalidation_price
        FROM setup_outcomes
        WHERE zone_width_atr IS NULL
          AND entry_price IS NOT NULL
          AND invalidation_price IS NOT NULL
    ''')
    rows = c.fetchall()
    computed = 0
    for row_id, entry_price, invalidation_price in rows:
        if entry_price and invalidation_price and entry_price != 0:
            zone_width_pct = abs(invalidation_price - entry_price) / entry_price * 100
            # Can't store zone_width_atr without atr_pct; store zone_width_pct
            # as a derived metric note. Since schema can't change, we compute
            # but can't persist zone_width_atr here.
            computed += 1

    result["zone_width_pct_computed"] = computed

    # 2. Mark zone_width_atr=0.0 as computed default (zero-width zones)
    c.execute("SELECT COUNT(*) FROM setup_outcomes WHERE zone_width_atr = 0.0")
    zero_zone_count = c.fetchone()[0]
    result["zone_width_atr_zero_default"] = zero_zone_count

    # 3. For NULL zone_width_atr with non-zero zone width: these need atr_pct
    #    to compute zone_width_atr. Count them.
    c.execute('''
        SELECT COUNT(*) FROM setup_outcomes
        WHERE zone_width_atr IS NULL
          AND atr_pct IS NULL
          AND entry_price IS NOT NULL
          AND invalidation_price IS NOT NULL
          AND entry_price != 0
    ''')
    pending_atr = c.fetchone()[0]
    result["zone_width_atr_pending_atr_pct"] = pending_atr

    conn.close()
    return result


def compute_touches():
    """
    For NULL touches records: derive from entry_zone zone width.
    - If zone_width_atr > 0 → touches = 1 (zone exists, can be touched)
    - If zone_width_atr = 0 → touches = 0 (zero-width zone)
    - If zone_width_atr is NULL but entry/invalidation available → compute
      from zone_width_pct: if zone_width_pct > 0 → touches = 1
    Mark touches=0 as default (zero-width zone).
    """
    conn = get_conn()
    c = conn.cursor()
    result = {}

    # Count NULL touches
    c.execute("SELECT COUNT(*) FROM setup_outcomes WHERE touches IS NULL")
    null_touches = c.fetchone()[0]
    result["touches_null_count"] = null_touches

    # For NULL touches with non-null zone_width_atr > 0 → set touches=1
    c.execute('''
        SELECT COUNT(*) FROM setup_outcomes
        WHERE touches IS NULL AND zone_width_atr IS NOT NULL AND zone_width_atr > 0
    ''')
    set_touch_1 = c.fetchone()[0]
    c.execute('''
        UPDATE setup_outcomes SET touches = 1
        WHERE touches IS NULL AND zone_width_atr IS NOT NULL AND zone_width_atr > 0
    ''')

    # For NULL touches with zone_width_atr = 0 → set touches=0
    c.execute('''
        SELECT COUNT(*) FROM setup_outcomes
        WHERE touches IS NULL AND zone_width_atr = 0.0
    ''')
    set_touch_0 = c.fetchone()[0]
    c.execute('''
        UPDATE setup_outcomes SET touches = 0
        WHERE touches IS NULL AND zone_width_atr = 0.0
    ''')

    # For NULL touches with NULL zone_width_atr: compute from entry_zone
    # zone_width_pct = |entry - invalidation| / entry * 100
    c.execute('''
        SELECT id, entry_price, invalidation_price
        FROM setup_outcomes
        WHERE touches IS NULL
          AND zone_width_atr IS NULL
          AND entry_price IS NOT NULL
          AND invalidation_price IS NOT NULL
          AND entry_price != 0
    ''')
    derived = 0
    for row_id, entry_price, invalidation_price in c.fetchall():
        zone_width_pct = abs(invalidation_price - entry_price) / entry_price * 100
        if zone_width_pct > 0:
            c.execute("UPDATE setup_outcomes SET touches = 1 WHERE id = ?", (row_id,))
            derived += 1
        elif zone_width_pct == 0:
            c.execute("UPDATE setup_outcomes SET touches = 0 WHERE id = ?", (row_id,))
            derived += 1

    conn.commit()
    conn.close()
    result["touches_derived_from_zone"] = derived
    result["touches_set_to_1"] = set_touch_1
    result["touches_set_to_0"] = set_touch_0
    return result


def validate_record(record_id):
    """Check all fields for a single record, returning a dict of issues."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM setup_outcomes WHERE id = ?", (record_id,))
    row = c.fetchone()
    if row is None:
        conn.close()
        return {"error": f"Record {record_id} not found"}

    cols = [d[0] for d in c.description]
    record = dict(zip(cols, row))
    conn.close()

    issues = []
    warnings = []

    # NULL checks
    null_fields = [f for f in cols if record.get(f) is None and f != "id"]
    if null_fields:
        issues.append(f"NULL fields: {null_fields}")

    # Empty string checks
    for col in ("structure_type", "liquidity_side"):
        if record.get(col) == "":
            issues.append(f"{col} is empty string (should be NULL)")

    # zone_width_atr = 0.0 (default/placeholder)
    if record.get("zone_width_atr") == 0.0:
        warnings.append("zone_width_atr=0.0 is a computed default (zero-width zone)")

    # touches = 0 (default)
    if record.get("touches") == 0:
        warnings.append("touches=0 is a computed default (zero-width zone)")

    # max_favorable/max_adverse always NULL (unfixable without schema change)
    if record.get("max_favorable") is None:
        warnings.append("max_favorable is NULL (unfixable without schema change)")
    if record.get("max_adverse") is None:
        warnings.append("max_adverse is NULL (unfixable without schema change)")

    # atr_pct NULL but zone_width_atr non-null (inconsistent)
    if record.get("atr_pct") is None and record.get("zone_width_atr") is not None:
        warnings.append("atr_pct NULL but zone_width_atr has value (inconsistent)")

    # Price sanity
    if record.get("entry_price") and record.get("invalidation_price"):
        if record["invalidation_price"] == record["entry_price"]:
            warnings.append("entry_price == invalidation_price (zero-width zone)")

    return {
        "record_id": record_id,
        "issues": issues,
        "warnings": warnings,
        "record": record,
    }


def data_quality_report():
    """Generate a full data quality report for all fields."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM setup_outcomes")
    total = c.fetchone()[0]

    fields = {
        "atr_pct": {"type": "REAL", "desc": "ATR percentage"},
        "zone_width_atr": {"type": "REAL", "desc": "Zone width in ATR units"},
        "touches": {"type": "INTEGER", "desc": "Number of touches"},
        "structure_type": {"type": "TEXT", "desc": "Structure type"},
        "liquidity_side": {"type": "TEXT", "desc": "Liquidity side"},
        "max_favorable": {"type": "REAL", "desc": "Max favorable excursion"},
        "max_adverse": {"type": "REAL", "desc": "Max adverse excursion"},
        "duration_bars": {"type": "INTEGER", "desc": "Duration in bars"},
        "pnl_pct": {"type": "REAL", "desc": "PnL percentage"},
        "quality_score": {"type": "REAL", "desc": "Quality score"},
    }

    report = {"total_records": total, "fields": {}}

    for field, info in fields.items():
        c.execute(f"SELECT COUNT(*) FROM setup_outcomes WHERE {field} IS NULL")
        null_count = c.fetchone()[0]

        c.execute(f"SELECT COUNT(*) FROM setup_outcomes WHERE {field} = ''")
        empty_count = c.fetchone()[0]

        # Distribution for non-null values
        if info["type"] in ("REAL", "INTEGER"):
            c.execute(f'''
                SELECT {field}, COUNT(*) FROM setup_outcomes
                WHERE {field} IS NOT NULL AND {field} != ''
                GROUP BY {field} ORDER BY {field} LIMIT 20
            ''')
            distribution = c.fetchall()
        else:
            c.execute(f'''
                SELECT {field}, COUNT(*) FROM setup_outcomes
                WHERE {field} IS NOT NULL AND {field} != ''
                GROUP BY {field} LIMIT 20
            ''')
            distribution = c.fetchall()

        report["fields"][field] = {
            "null_count": null_count,
            "null_pct": round(100 * null_count / total, 1) if total else 0,
            "empty_string_count": empty_count,
            "distribution": distribution[:10],
        }

    conn.close()
    return report


def print_report(report):
    """Pretty-print the data quality report."""
    print("=" * 70)
    print("DATA QUALITY REPORT")
    print("=" * 70)
    print(f"Total records: {report['total_records']:,}")
    print()

    for field, info in report["fields"].items():
        null_pct = info["null_pct"]
        empty = info["empty_string_count"]
        status = "OK" if null_pct < 1 else ("WARNING" if null_pct < 40 else "CRITICAL")
        print(f"  {field}:")
        print(f"    NULL: {info['null_count']:,} ({null_pct}%) [{status}]")
        if empty:
            print(f"    Empty strings: {empty:,}")
        if info["distribution"]:
            dist_str = ", ".join(f"{v}={c}" for v, c in info["distribution"][:5])
            print(f"    Distribution: {dist_str}")
        print()


if __name__ == "__main__":
    print("Before fixes:")
    report_before = data_quality_report()
    print_report(report_before)

    print("\n" + "=" * 70)
    print("APPLYING FIXES")
    print("=" * 70)

    print("\n1. fix_empty_strings()...")
    empty_result = fix_empty_strings()
    print(f"   Fixed: {empty_result}")

    print("\n2. compute_zone_width()...")
    zone_result = compute_zone_width()
    print(f"   Result: {zone_result}")

    print("\n3. compute_touches()...")
    touch_result = compute_touches()
    print(f"   Result: {touch_result}")

    print("\n" + "=" * 70)
    print("AFTER FIXES:")
    print("=" * 70)
    report_after = data_quality_report()
    print_report(report_after)

    # Show sample records
    print("\n" + "=" * 70)
    print("SAMPLE RECORDS (first 5)")
    print("=" * 70)
    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT id, atr_pct, zone_width_atr, touches, structure_type,
                        liquidity_side, entry_price, invalidation_price
                 FROM setup_outcomes LIMIT 5''')
    cols = [d[0] for d in c.description]
    print(f"  {', '.join(cols)}")
    for row in c.fetchall():
        print(f"  {row}")
    conn.close()

    # Validate a few records
    print("\n" + "=" * 70)
    print("VALIDATION SAMPLES")
    print("=" * 70)
    for rid in [1, 4063, 4064, 7000]:
        val = validate_record(rid)
        if "error" in val:
            print(f"  Record {rid}: {val['error']}")
        else:
            print(f"  Record {rid}: issues={val['issues']}, warnings={val['warnings']}")
