# -*- coding: utf-8 -*-
"""
MarketHQ Setup Feedback V1 (research-only).

Her setup + sonucu JSONL'ye yazar:
  agentspace/logs/setup_feedback.jsonl
Brain/ogrenme dongusu bu dosyayi okuyarak strateji bazinda
destek/karsit skorlarini guncelleyebilir. Canli islem yok.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FEEDBACK_PATH = Path(__file__).resolve().parent / "agentspace" / "agentspace" / "logs" / "setup_feedback.jsonl"
# /opt/markethq/agentspace/agentspace/logs yoksa /opt/markethq/agentspace/logs kullan
if not FEEDBACK_PATH.parent.exists():
    FEEDBACK_PATH = Path(__file__).resolve().parent / "agentspace" / "logs" / "setup_feedback.jsonl"


def log_setup_feedback(setup: dict[str, Any], outcome: str = "PENDING", note: str = "") -> Path:
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "setup_id": setup.get("setup_id"),
        "symbol": setup.get("symbol", "UNKNOWN"),
        "direction": setup.get("direction"),
        "regime": setup.get("regime"),
        "timeframe": setup.get("timeframe"),
        "supporting": setup.get("supporting"),
        "opposing": setup.get("opposing"),
        "agreement": setup.get("agreement"),
        "outcome": outcome,  # PENDING / CONFIRMED / INVALIDATED
        "note": note,
        "research_only": True,
    }
    with open(FEEDBACK_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return FEEDBACK_PATH
