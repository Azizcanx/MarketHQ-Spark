import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from strategy_knowledge_base import (
    add_strategy,
)


# ============================================================
# MARKET HQ
# RESEARCH STRATEGY DISCOVERY ENGINE V1.1
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

OUTPUT_DIR = PROJECT_ROOT / "research_discovery_results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DISCOVERY_MODEL = "gpt-5.6-luna"

MAX_SOURCE_CHARS = 30000
MAX_STRATEGIES_PER_SOURCE = 20


# ============================================================
# OPENAI
# ============================================================

load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("OPENAI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY bulunamadı. "
        "MarketHQ/.env dosyanı kontrol et."
    )

client = OpenAI(api_key=API_KEY)


# ============================================================
# SUPPORTED SOURCE TYPES
# ============================================================

SUPPORTED_SOURCE_TYPES = {
    "article",
    "paper",
    "book",
    "research",
    "documentation",
    "strategy",
    "unknown",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(text: Any) -> str:
    if not isinstance(text, str):
        return ""

    text = text.replace("\x00", " ")
    text = text.strip()

    if len(text) > MAX_SOURCE_CHARS:
        text = text[:MAX_SOURCE_CHARS]

    return text


def safe_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value

    return {}


def safe_list(value: Any) -> list:
    if isinstance(value, list):
        return value

    return []


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    result = []

    for item in value:
        if item is None:
            continue

        text = str(item).strip()

        if text:
            result.append(text)

    return result


# ============================================================
# SOURCE FILE READER
# ============================================================

def read_source_file(file_path: str | Path) -> str:
    """
    Metin tabanlı kaynakları okur.

    Desteklenen:
    - TXT
    - MD
    - MARKDOWN
    - CSV
    - JSON
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Kaynak dosyası bulunamadı: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Kaynak yolu bir dosya değil: {path}"
        )

    suffix = path.suffix.lower()

    supported = {
        ".txt",
        ".md",
        ".markdown",
        ".csv",
        ".json",
    }

    if suffix not in supported:
        raise ValueError(
            f"Desteklenmeyen kaynak formatı: {suffix}\n"
            f"Desteklenen formatlar: "
            f"{', '.join(sorted(supported))}"
        )

    text = path.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    return clean_text(text)


# ============================================================
# AI SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
Sen MarketHQ Research Strategy Discovery Engine'sin.

Görevin, verilen araştırma veya finansal kaynak metninden
açıkça desteklenen strateji fikirlerini çıkarmaktır.

TEMEL PRENSİPLER:

1. Kaynakta bulunmayan bir stratejiyi uydurma.

2. Kaynakta açıkça belirtilmeyen parametreleri UNKNOWN olarak
   bırak veya uncertainties alanına ekle.

3. Kaynakta anlatılan bilgi ile kendi finansal yorumunu
   birbirine karıştırma.

4. Bir stratejinin başarılı olduğunu varsayma.

5. Kârlılık garantisi verme.

6. Backtest sonucu uydurma.

7. Gelecekteki performans hakkında kesin hüküm verme.

8. Gerçek para işlemi veya broker emri üretme.

9. Her strateji araştırma amaçlı adaydır.

10. Kaynak birden fazla strateji içeriyorsa bunları ayrı
    strateji adayları olarak çıkar.

11. Aynı stratejinin gereksiz küçük varyasyonlarını
    çoğaltma.

12. Mümkün olduğu kadar şu bilgileri ayrı ayrı çıkar:
    - giriş koşulları
    - confirmation koşulları
    - çıkış koşulları
    - risk kuralları
    - filtreler
    - göstergeler
    - parametreler
    - timeframe
    - market
    - logic

13. Belirsizlikleri mutlaka uncertainties alanına yaz.

14. Kaynak yalnızca genel bir fikir anlatıyorsa bunu
    kesin kurallara dönüştürme.

15. Kaynakta sayısal değer yoksa sayısal değer uydurma.

16. "UNKNOWN" kullanmak, tahmin yapmaktan daha doğrudur.

17. Sadece kaynak tarafından desteklenen strateji adaylarını
    döndür.

ÇIKTI:
Sadece geçerli JSON döndür.
Markdown kullanma.
Açıklama yazma.
"""


# ============================================================
# USER PROMPT
# ============================================================

def build_user_prompt(
    source_text: str,
    source_title: str,
    source_type: str,
) -> str:

    return f"""
KAYNAK BAŞLIĞI:
{source_title}

KAYNAK TÜRÜ:
{source_type}

KAYNAK METNİ:
============================================================
{source_text}
============================================================

Bu kaynaktan desteklenen strateji adaylarını çıkar.

Aşağıdaki JSON yapısını kullan:

{{
  "source_title": "{source_title}",
  "source_type": "{source_type}",
  "strategies": [
    {{
      "name": "...",
      "description": "...",
      "market": "BIST/US/FOREX/CRYPTO/UNKNOWN",
      "symbols": [],
      "timeframe": "UNKNOWN",

      "indicators": [
        {{
          "name": "...",
          "parameters": {{}},
          "purpose": "..."
        }}
      ],

      "entry_rules": [
        "..."
      ],

      "confirmation_rules": [
        "..."
      ],

      "exit_rules": [
        "..."
      ],

      "risk_rules": [
        "..."
      ],

      "filter_rules": [
        "..."
      ],

      "parameters": {{}},

      "logic": "LONG/SHORT/LONG_SHORT/UNKNOWN",

      "source_evidence": [
        "Kaynakta desteklenen ifade veya özet"
      ],

      "uncertainties": [
        "Kaynakta belirtilmeyen veya belirsiz kalan nokta"
      ],

      "research_only": true
    }}
  ]
}}

Eğer kaynakta strateji yoksa:

{{
  "source_title": "{source_title}",
  "source_type": "{source_type}",
  "strategies": []
}}
"""


# ============================================================
# JSON EXTRACTION
# ============================================================

def extract_json(text: str) -> dict:
    if not isinstance(text, str):
        raise ValueError(
            "AI çıktısı metin değil."
        )

    text = text.strip()

    if not text:
        raise ValueError(
            "AI boş cevap döndürdü."
        )

    # Markdown code fence temizliği
    if text.startswith("```"):
        lines = text.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    # Önce doğrudan JSON dene
    try:
        result = json.loads(text)

        if not isinstance(result, dict):
            raise ValueError(
                "AI çıktısı JSON object değil."
            )

        return result

    except json.JSONDecodeError:
        pass

    # JSON bloğunu bul
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError(
            "AI çıktısında geçerli JSON bulunamadı."
        )

    json_text = text[start:end + 1]

    try:
        result = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"AI JSON çıktısı parse edilemedi: {exc}"
        ) from exc

    if not isinstance(result, dict):
        raise ValueError(
            "AI çıktısı JSON object değil."
        )

    return result


# ============================================================
# AI DISCOVERY
# ============================================================

def discover_strategies(
    source_text: str,
    source_title: str = "Unknown Source",
    source_type: str = "unknown",
) -> dict:

    source_text = clean_text(source_text)

    if not source_text:
        raise ValueError(
            "Kaynak metni boş."
        )

    source_type = str(
        source_type
    ).strip().lower()

    if source_type not in SUPPORTED_SOURCE_TYPES:
        source_type = "unknown"

    user_prompt = build_user_prompt(
        source_text=source_text,
        source_title=source_title,
        source_type=source_type,
    )

    response = client.chat.completions.create(
        model=DISCOVERY_MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    )

    if not response.choices:
        raise RuntimeError(
            "AI response içinde choices bulunamadı."
        )

    content = response.choices[0].message.content

    if not content:
        raise RuntimeError(
            "AI boş cevap döndürdü."
        )

    return extract_json(content)


# ============================================================
# STRATEGY NORMALIZATION
# ============================================================

def normalize_strategy(
    strategy: dict,
    source_title: str,
    source_type: str,
) -> dict:

    strategy = safe_dict(strategy)

    name = str(
        strategy.get(
            "name",
            "Unnamed Strategy",
        )
    ).strip()

    if not name:
        name = "Unnamed Strategy"

    description = str(
        strategy.get(
            "description",
            "",
        )
    ).strip()

    market = str(
        strategy.get(
            "market",
            "UNKNOWN",
        )
    ).strip().upper()

    symbols = normalize_string_list(
        strategy.get("symbols")
    )

    timeframe = str(
        strategy.get(
            "timeframe",
            "UNKNOWN",
        )
    ).strip()

    logic = str(
        strategy.get(
            "logic",
            "UNKNOWN",
        )
    ).strip().upper()

    if logic not in {
        "LONG",
        "SHORT",
        "LONG_SHORT",
        "UNKNOWN",
    }:
        logic = "UNKNOWN"

    # --------------------------------------------------------
    # Indicators
    # --------------------------------------------------------

    indicators = []

    for item in safe_list(
        strategy.get("indicators")
    ):
        item = safe_dict(item)

        indicator_name = str(
            item.get(
                "name",
                "UNKNOWN",
            )
        ).strip()

        indicator_parameters = safe_dict(
            item.get(
                "parameters",
                {},
            )
        )

        purpose = str(
            item.get(
                "purpose",
                "",
            )
        ).strip()

        indicators.append(
            {
                "name": indicator_name,
                "parameters": indicator_parameters,
                "purpose": purpose,
            }
        )

    # --------------------------------------------------------
    # Rules
    # --------------------------------------------------------

    entry_rules = normalize_string_list(
        strategy.get("entry_rules")
    )

    confirmation_rules = normalize_string_list(
        strategy.get(
            "confirmation_rules"
        )
    )

    exit_rules = normalize_string_list(
        strategy.get("exit_rules")
    )

    risk_rules = normalize_string_list(
        strategy.get("risk_rules")
    )

    filter_rules = normalize_string_list(
        strategy.get("filter_rules")
    )

    source_evidence = normalize_string_list(
        strategy.get("source_evidence")
    )

    uncertainties = normalize_string_list(
        strategy.get("uncertainties")
    )

    parameters = safe_dict(
        strategy.get("parameters")
    )

    # --------------------------------------------------------
    # Automatic uncertainty checks
    # --------------------------------------------------------

    if not timeframe:
        timeframe = "UNKNOWN"

    if timeframe.upper() == "UNKNOWN":
        if "timeframe" not in uncertainties:
            uncertainties.append(
                "Timeframe kaynakta kesin belirtilmemiş."
            )

    if not entry_rules:
        uncertainties.append(
            "Açık giriş kuralı bulunamadı."
        )

    if not exit_rules:
        uncertainties.append(
            "Açık çıkış kuralı bulunamadı."
        )

    if not risk_rules:
        uncertainties.append(
            "Açık risk yönetimi kuralı bulunamadı."
        )

    # Duplicate uncertainty temizliği
    uncertainties = list(
        dict.fromkeys(uncertainties)
    )

    return {
        "name": name,
        "description": description,
        "market": market,
        "symbols": symbols,
        "timeframe": timeframe,
        "indicators": indicators,
        "entry_rules": entry_rules,
        "confirmation_rules": confirmation_rules,
        "exit_rules": exit_rules,
        "risk_rules": risk_rules,
        "filter_rules": filter_rules,
        "parameters": parameters,
        "logic": logic,
        "source_evidence": source_evidence,
        "uncertainties": uncertainties,
        "research_only": True,
        "execution_enabled": False,
        "source": {
            "title": source_title,
            "type": source_type,
        },
        "discovered_at": utc_timestamp(),
    }


# ============================================================
# KB FORMAT
# ============================================================

def convert_to_knowledge_base_strategy(
    strategy: dict,
) -> dict:

    rules = []

    # Entry
    for rule in strategy.get(
        "entry_rules",
        [],
    ):
        rules.append(
            {
                "type": "entry",
                "rule": rule,
            }
        )

    # Exit
    for rule in strategy.get(
        "exit_rules",
        [],
    ):
        rules.append(
            {
                "type": "exit",
                "rule": rule,
            }
        )

    # Risk
    for rule in strategy.get(
        "risk_rules",
        [],
    ):
        rules.append(
            {
                "type": "risk",
                "rule": rule,
            }
        )

    # Filters
    for rule in strategy.get(
        "filter_rules",
        [],
    ):
        rules.append(
            {
                "type": "filters",
                "rule": rule,
            }
        )

    observations = []

    # Confirmation
    confirmation_rules = strategy.get(
        "confirmation_rules",
        [],
    )

    if confirmation_rules:
        observations.append(
            {
                "type": "confirmation",
                "observation": confirmation_rules,
            }
        )

    # Evidence
    source_evidence = strategy.get(
        "source_evidence",
        [],
    )

    if source_evidence:
        observations.append(
            {
                "type": "source_evidence",
                "observation": source_evidence,
            }
        )

    # Uncertainties
    uncertainties = strategy.get(
        "uncertainties",
        [],
    )

    if uncertainties:
        observations.append(
            {
                "type": "uncertainty",
                "observation": uncertainties,
            }
        )

    return {
        "name": strategy.get(
            "name",
            "Unnamed Strategy",
        ),
        "description": strategy.get(
            "description",
            "",
        ),
        "market": strategy.get(
            "market",
            "UNKNOWN",
        ),
        "symbols": strategy.get(
            "symbols",
            [],
        ),
        "timeframe": strategy.get(
            "timeframe",
            "UNKNOWN",
        ),
        "status": "HYPOTHESIS",
        "research_only": True,
        "execution_enabled": False,
        "parameters": strategy.get(
            "parameters",
            {},
        ),
        "rules": rules,
        "observations": observations,
        "source": strategy.get(
            "source",
            {},
        ),
        "discovered_at": strategy.get(
            "discovered_at",
            utc_timestamp(),
        ),
    }


# ============================================================
# KNOWLEDGE BASE SAVE
# ============================================================

def save_to_knowledge_base(
    strategy: dict,
) -> dict:

    kb_strategy = (
        convert_to_knowledge_base_strategy(
            strategy
        )
    )

    # --------------------------------------------------------
    # Mevcut KB API'ye dict göndermeyi deniyoruz.
    # --------------------------------------------------------

    try:
        result = add_strategy(
            kb_strategy
        )

    except TypeError:

        # ----------------------------------------------------
        # Alternatif API imzası
        # ----------------------------------------------------

        try:
            result = add_strategy(
                name=kb_strategy["name"],
                description=kb_strategy[
                    "description"
                ],
                market=kb_strategy["market"],
                symbols=kb_strategy["symbols"],
                timeframe=kb_strategy[
                    "timeframe"
                ],
            )

        except Exception as exc:
            raise RuntimeError(
                "Strategy Knowledge Base "
                f"add_strategy çağrısı başarısız: {exc}"
            ) from exc

    except Exception as exc:
        raise RuntimeError(
            "Strategy Knowledge Base kayıt hatası: "
            f"{exc}"
        ) from exc

    strategy_id = None

    if isinstance(result, str):
        strategy_id = result

    elif isinstance(result, dict):
        strategy_id = (
            result.get("strategy_id")
            or result.get("id")
            or result.get("strategyId")
        )

    return {
        "saved": True,
        "strategy_id": strategy_id,
        "result": result,
    }


# ============================================================
# DISCOVERY RESULT
# ============================================================

def build_discovery_result(
    source_title: str,
    source_type: str,
    strategies: list[dict],
) -> dict:

    return {
        "engine": (
            "MarketHQ Research "
            "Strategy Discovery Engine V1.1"
        ),
        "timestamp": utc_timestamp(),
        "source": {
            "title": source_title,
            "type": source_type,
        },
        "strategy_count": len(strategies),
        "strategies": strategies,
        "safety": {
            "research_only": True,
            "execution_enabled": False,
        },
    }


# ============================================================
# RESULT FILE SAVE
# ============================================================

def make_safe_filename(
    text: str,
) -> str:

    text = str(text).strip()

    if not text:
        text = "unknown_source"

    result = []

    for char in text:
        if char.isalnum():
            result.append(char)
        elif char in {
            " ",
            "-",
            "_",
        }:
            result.append("_")

    filename = "".join(result)

    while "__" in filename:
        filename = filename.replace(
            "__",
            "_",
        )

    filename = filename.strip("_")

    if not filename:
        filename = "unknown_source"

    return filename[:80]


def save_discovery_result(
    result: dict,
    source_title: str,
) -> Path:

    safe_name = make_safe_filename(
        source_title
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    output_path = (
        OUTPUT_DIR
        / f"{safe_name}_{timestamp}.json"
    )

    output_path.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return output_path


# ============================================================
# PRINT STRATEGY
# ============================================================

def print_strategy(
    strategy: dict,
    index: int,
) -> None:

    print()
    print(
        f"  [{index}] {strategy['name']}"
    )

    print(
        f"      Market      : "
        f"{strategy['market']}"
    )

    print(
        f"      Logic       : "
        f"{strategy['logic']}"
    )

    print(
        f"      Timeframe   : "
        f"{strategy['timeframe']}"
    )

    print(
        f"      Indicators  : "
        f"{len(strategy['indicators'])}"
    )

    print(
        f"      Entry       : "
        f"{len(strategy['entry_rules'])}"
    )

    print(
        f"      Confirmation: "
        f"{len(strategy['confirmation_rules'])}"
    )

    print(
        f"      Exit        : "
        f"{len(strategy['exit_rules'])}"
    )

    print(
        f"      Risk        : "
        f"{len(strategy['risk_rules'])}"
    )

    print(
        f"      Filters     : "
        f"{len(strategy['filter_rules'])}"
    )

    print(
        f"      Uncertainties: "
        f"{len(strategy['uncertainties'])}"
    )


# ============================================================
# FULL DISCOVERY PIPELINE
# ============================================================

def run_discovery(
    source_text: str,
    source_title: str = "Unknown Source",
    source_type: str = "unknown",
    save_to_kb: bool = True,
) -> dict:

    print()
    print("=" * 70)
    print(
        "📚 MARKET HQ RESEARCH STRATEGY "
        "DISCOVERY ENGINE V1.1"
    )
    print("=" * 70)

    print()
    print(
        f"Source      : {source_title}"
    )

    print(
        f"Source Type : {source_type}"
    )

    print(
        f"Model       : {DISCOVERY_MODEL}"
    )

    print()
    print(
        "🔎 Kaynak analiz ediliyor..."
    )

    discovered = discover_strategies(
        source_text=source_text,
        source_title=source_title,
        source_type=source_type,
    )

    raw_strategies = safe_list(
        discovered.get("strategies")
    )

    raw_strategies = raw_strategies[
        :MAX_STRATEGIES_PER_SOURCE
    ]

    print()
    print(
        f"🧠 Bulunan strateji adayı : "
        f"{len(raw_strategies)}"
    )

    normalized_strategies = []

    for index, raw_strategy in enumerate(
        raw_strategies,
        start=1,
    ):

        strategy = normalize_strategy(
            strategy=raw_strategy,
            source_title=source_title,
            source_type=source_type,
        )

        normalized_strategies.append(
            strategy
        )

        print_strategy(
            strategy,
            index,
        )

        # ----------------------------------------------------
        # Knowledge Base
        # ----------------------------------------------------

        if save_to_kb:

            try:
                kb_result = (
                    save_to_knowledge_base(
                        strategy
                    )
                )

                strategy[
                    "knowledge_base"
                ] = {
                    "saved": True,
                    "strategy_id": kb_result.get(
                        "strategy_id"
                    ),
                }

                print(
                    "      KB          : DONE"
                )

                if kb_result.get(
                    "strategy_id"
                ):
                    print(
                        "      Strategy ID : "
                        f"{kb_result['strategy_id']}"
                    )

            except Exception as exc:

                strategy[
                    "knowledge_base"
                ] = {
                    "saved": False,
                    "error": str(exc),
                }

                print(
                    "      KB          : ERROR"
                )

                print(
                    f"      Error       : {exc}"
                )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    result = build_discovery_result(
        source_title=source_title,
        source_type=source_type,
        strategies=normalized_strategies,
    )

    output_path = save_discovery_result(
        result=result,
        source_title=source_title,
    )

    saved_count = sum(
        1
        for strategy in normalized_strategies
        if strategy.get(
            "knowledge_base",
            {},
        ).get(
            "saved",
            False,
        )
    )

    print()
    print("=" * 70)
    print("📊 DISCOVERY SUMMARY")
    print("=" * 70)

    print(
        f"Strategies Found : "
        f"{len(normalized_strategies)}"
    )

    print(
        f"Saved to KB      : "
        f"{saved_count}"
    )

    print()
    print("SAFETY")
    print(
        "Research Only     : True"
    )

    print(
        "Execution Enabled : False"
    )

    print()
    print(
        "💾 Result saved:"
    )

    print(
        output_path
    )

    print("=" * 70)
    print()

    return result


# ============================================================
# DEMO SOURCE
# ============================================================

DEMO_SOURCE = """
Örnek araştırma metni:

Strateji, kısa vadeli hareketli ortalamanın uzun vadeli
hareketli ortalamayı yukarı kesmesi durumunda uzun pozisyon
açılmasını kullanır.

Onay için RSI göstergesinin 50 seviyesinin üzerinde olması
aranır.

Pozisyon, kısa hareketli ortalamanın tekrar uzun hareketli
ortalamanın altına gelmesi durumunda kapatılır.

Risk yönetimi için ATR tabanlı zarar durdurma kullanılabilir.

Metin, ATR katsayısını veya pozisyon büyüklüğünü kesin olarak
belirtmemektedir.
"""


# ============================================================
# CLI
# ============================================================

def print_usage() -> None:

    print()
    print("=" * 70)
    print("MARKET HQ STRATEGY DISCOVERY")
    print("=" * 70)

    print()
    print("DEMO:")
    print(
        r".\.venv\Scripts\python.exe "
        r"research_strategy_discovery.py"
    )

    print()
    print("KAYNAK DOSYASI:")
    print(
        r'.\.venv\Scripts\python.exe '
        r'research_strategy_discovery.py '
        r'"kaynak.md" '
        r'"Kaynak Başlığı" '
        r'"research"'
    )

    print()


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    args = sys.argv[1:]

    # --------------------------------------------------------
    # Parametresiz çalıştırılırsa demo
    # --------------------------------------------------------

    if len(args) == 0:

        run_discovery(
            source_text=DEMO_SOURCE,
            source_title=(
                "MarketHQ Discovery Demo"
            ),
            source_type="research",
            save_to_kb=True,
        )

        return

    # --------------------------------------------------------
    # Help
    # --------------------------------------------------------

    if args[0] in {
        "-h",
        "--help",
        "help",
    }:

        print_usage()
        return

    # --------------------------------------------------------
    # File mode
    # --------------------------------------------------------

    file_path = args[0]

    source_title = (
        args[1]
        if len(args) >= 2
        else Path(file_path).stem
    )

    source_type = (
        args[2]
        if len(args) >= 3
        else "unknown"
    )

    print()
    print(
        f"📄 Kaynak okunuyor: {file_path}"
    )

    source_text = read_source_file(
        file_path
    )

    if not source_text:
        raise ValueError(
            "Kaynak dosyası boş."
        )

    run_discovery(
        source_text=source_text,
        source_title=source_title,
        source_type=source_type,
        save_to_kb=True,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
