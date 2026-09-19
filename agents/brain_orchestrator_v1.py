# -*- coding: utf-8 -*-
"""
MarketHQ Brain Orchestrator V1
------------------------------
Tek komutla MarketHQ Brain öğrenme/research döngüsünü sıralı olarak çalıştırır.

PIPELINE
--------
1) Research Queue Hygiene V2
2) Queue Enrichment V2
3) Research Agent V4
4) Research Knowledge Ingest V3
5) Knowledge Repair V2
6) Observation Bridge V2
7) Evidence Review V4
8) Evidence Flag Repair V1
9) Evidence Update V1
10) Final Brain Health Check V1

TASARIM
-------
- Her aşama ayrı Python process olarak çalışır.
- Bir aşama hata verirse pipeline durur.
- Sonraki aşama yarım veri üzerinde çalıştırılmaz.
- stdout/stderr terminale canlı aktarılır.
- Her aşama süre ve exit code ile raporlanır.
- Orchestrator DB'ye doğrudan yazmaz.
- Mevcut engine'lerin kendi güvenlik mantıkları korunur.
- Tek tur çalışır; sonsuz loop oluşturmaz.

Çalıştırma
----------
    python agents/brain_orchestrator_v1.py

Not
---
Bu bir historical research / paper-test orchestration katmanıdır.
Canlı işlem veya otomatik emir göndermez.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = sys.executable

ENGINE_NAME = "MARKETHQ_BRAIN_ORCHESTRATOR"
ENGINE_VERSION = "V1"

# Mevcut çalışan pipeline dosyaları.
PIPELINE = [
    ("QUEUE_HYGIENE_V2", "brain_research_queue_hygiene_v2.py"),
    ("QUEUE_ENRICHMENT_V2", "brain_research_queue_enrichment_v2.py"),
    ("RESEARCH_AGENT_V4", "brain_research_agent_v4.py"),
    ("KNOWLEDGE_INGEST_V3", "brain_research_knowledge_ingest_v3.py"),
    ("KNOWLEDGE_REPAIR_V2", "brain_research_knowledge_repair_v2.py"),
    ("OBSERVATION_BRIDGE_V2", "brain_research_observation_bridge_v2.py"),
    ("EVIDENCE_REVIEW_V4", "brain_research_evidence_review_v4.py"),
    ("EVIDENCE_FLAG_REPAIR_V1", "brain_research_evidence_flag_repair_v1.py"),
    ("EVIDENCE_UPDATE_V1", "brain_research_evidence_update_v1.py"),
    ("BRAIN_HEALTH_CHECK_V1", "brain_health_check_v1.py"),
]

# Subprocess timeout. Tek bir engine sonsuza kadar takılı kalmasın.
STAGE_TIMEOUT_SECONDS = int(
    os.getenv(
        "MARKETHQ_ORCHESTRATOR_STAGE_TIMEOUT",
        "900",
    )
)


# ---------------------------------------------------------------------------
# RESULT
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    name: str
    script: str
    return_code: int
    elapsed_seconds: float
    status: str


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def banner(text: str) -> None:
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)
    print()


def print_header() -> None:
    banner(
        "MARKETHQ BRAIN ORCHESTRATOR V1"
    )

    print(
        f"Project  : {PROJECT_ROOT}"
    )
    print(
        f"Python   : {PYTHON_EXE}"
    )
    print(
        f"Engine   : {ENGINE_NAME}"
    )
    print(
        f"Version  : {ENGINE_VERSION}"
    )
    print(
        f"Timeout  : {STAGE_TIMEOUT_SECONDS}s / stage"
    )

    print()
    print("PIPELINE")
    print("-" * 78)

    for index, (
        name,
        script,
    ) in enumerate(
        PIPELINE,
        start=1,
    ):
        print(
            f"{index:02d}. {name:28s} -> {script}"
        )

    print()


def run_stage(
    stage_no: int,
    total_stages: int,
    name: str,
    script_name: str,
) -> StageResult:
    script_path = PROJECT_ROOT / "agents" / script_name

    print()
    print("#" * 78)
    print(
        f"STAGE {stage_no}/{total_stages} | {name}"
    )
    print(
        f"SCRIPT: {script_path}"
    )
    print("#" * 78)

    if not script_path.exists():
        print(
            f"ERROR: Script bulunamadı: {script_path}"
        )

        return StageResult(
            name=name,
            script=script_name,
            return_code=2,
            elapsed_seconds=0.0,
            status="MISSING",
        )

    started = time.perf_counter()

    try:
        completed = subprocess.run(
            [
                str(PYTHON_EXE),
                "-u",
                str(script_path),
            ],
            cwd=str(PROJECT_ROOT),
            check=False,
            timeout=STAGE_TIMEOUT_SECONDS,
        )

        elapsed = (
            time.perf_counter()
            - started
        )

        if completed.returncode == 0:
            status = "OK"
        else:
            status = "ERROR"

        print()
        print(
            f"STAGE_RESULT | "
            f"{name} | "
            f"return_code={completed.returncode} | "
            f"elapsed={elapsed:.2f}s | "
            f"status={status}"
        )

        return StageResult(
            name=name,
            script=script_name,
            return_code=completed.returncode,
            elapsed_seconds=elapsed,
            status=status,
        )

    except subprocess.TimeoutExpired:
        elapsed = (
            time.perf_counter()
            - started
        )

        print()
        print(
            f"STAGE_RESULT | "
            f"{name} | "
            f"return_code=124 | "
            f"elapsed={elapsed:.2f}s | "
            "status=TIMEOUT"
        )

        return StageResult(
            name=name,
            script=script_name,
            return_code=124,
            elapsed_seconds=elapsed,
            status="TIMEOUT",
        )

    except Exception as exc:
        elapsed = (
            time.perf_counter()
            - started
        )

        print()
        print(
            f"STAGE_RESULT | "
            f"{name} | "
            f"return_code=1 | "
            f"elapsed={elapsed:.2f}s | "
            f"status=EXCEPTION | "
            f"{type(exc).__name__}: {exc}"
        )

        return StageResult(
            name=name,
            script=script_name,
            return_code=1,
            elapsed_seconds=elapsed,
            status="EXCEPTION",
        )


def print_summary(
    results: list[StageResult],
) -> None:
    banner(
        "MARKETHQ BRAIN ORCHESTRATOR SUMMARY"
    )

    ok_count = sum(
        1
        for result in results
        if result.status == "OK"
    )

    failed_count = len(results) - ok_count

    print(
        f"Stages completed : {len(results)}"
    )
    print(
        f"Stages OK        : {ok_count}"
    )
    print(
        f"Stages failed    : {failed_count}"
    )
    print()

    print(
        "STAGE RESULTS"
    )
    print("-" * 78)

    for index, result in enumerate(
        results,
        start=1,
    ):
        print(
            f"{index:02d}. "
            f"{result.name:28s} | "
            f"{result.status:9s} | "
            f"rc={result.return_code:3d} | "
            f"{result.elapsed_seconds:7.2f}s"
        )

    print()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    print_header()

    if not PROJECT_ROOT.exists():
        print(
            f"FATAL: Project root bulunamadı: {PROJECT_ROOT}"
        )
        return 2

    results: list[StageResult] = []

    total_stages = len(
        PIPELINE
    )

    pipeline_started = time.perf_counter()

    for stage_no, (
        name,
        script_name,
    ) in enumerate(
        PIPELINE,
        start=1,
    ):
        result = run_stage(
            stage_no,
            total_stages,
            name,
            script_name,
        )

        results.append(
            result
        )

        if result.status != "OK":
            print()
            print(
                "PIPELINE STOPPED"
            )
            print(
                f"Failed stage: {name}"
            )
            print(
                "Sonraki stage'ler kasıtlı olarak çalıştırılmadı."
            )

            print_summary(
                results
            )

            total_elapsed = (
                time.perf_counter()
                - pipeline_started
            )

            print(
                f"TOTAL_ELAPSED={total_elapsed:.2f}s"
            )

            return result.return_code or 1

    total_elapsed = (
        time.perf_counter()
        - pipeline_started
    )

    print_summary(
        results
    )

    print("=" * 78)
    print(
        "PIPELINE_STATUS = COMPLETED"
    )
    print(
        f"TOTAL_ELAPSED={total_elapsed:.2f}s"
    )
    print("=" * 78)
    print()
    print(
        "Brain research loop tek tur olarak başarıyla orkestre edildi."
    )
    print(
        "Canlı işlem / emir yürütme yapılmadı."
    )
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
