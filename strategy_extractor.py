import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from strategy_knowledge_base import (
    VALID_SOURCE_TYPES,
    add_observation,
    add_rule,
    add_strategy,
    create_strategy,
    set_strategy_parameters,
    update_learning_status,
)


# ============================================================
# MARKET HQ - STRATEGY EXTRACTOR V2
# ============================================================

MODEL_NAME = "gpt-5.6-luna"
MAX_SOURCE_CHARS = 40000

DEFAULT_SOURCE_TYPE = "manual"

VALID_RULE_TYPES = {
    "entry",
    "confirmation",
    "exit",
    "risk",
    "filters",
}

# Knowledge Base'in mevcut rule API'sinde confirmation tipi
# olmayabilir. Bu nedenle confirmation bilgisi ayrıca
# strategy metadata / observation olarak korunur.
KB_RULE_TYPES = {
    "entry",
    "exit",
    "risk",
    "filters",
}


# ============================================================
# OPENAI
# ============================================================

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise RuntimeError(
        "OPENAI_API_KEY bulunamadı. "
        "MarketHQ .env dosyanı kontrol et."
    )

client = OpenAI(
    api_key=api_key
)


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_string(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    if isinstance(value, str):
        return value.strip()

    return str(value).strip()


def clean_list(
    value: Any,
) -> List[str]:
    if value is None:
        return []

    if isinstance(value, str):
        value = [value]

    if not isinstance(value, list):
        return []

    result = []

    for item in value:
        text = clean_string(item)

        if text and text not in result:
            result.append(text)

    return result


def clean_dict(
    value: Any,
) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    return value


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_source_type(
    value: Any,
) -> str:
    source_type = clean_string(
        value,
        DEFAULT_SOURCE_TYPE,
    ).lower()

    aliases = {
        "video": "youtube",
        "yt": "youtube",
        "youtube video": "youtube",
        "makale": "article",
        "yazı": "article",
        "kitap": "book",
        "araştırma": "research",
        "research paper": "research",
        "röportaj": "interview",
        "manuel": "manual",
        "walk forward": "walk_forward",
        "walk-forward": "walk_forward",
        "market hq": "market_hq",
    }

    source_type = aliases.get(
        source_type,
        source_type,
    )

    if source_type not in VALID_SOURCE_TYPES:
        return DEFAULT_SOURCE_TYPE

    return source_type


def normalize_market(
    value: Any,
) -> str:
    market = clean_string(
        value,
        "Unknown",
    )

    aliases = {
        "bist": "BIST",
        "borsa istanbul": "BIST",
        "türkiye": "BIST",
        "turkey": "BIST",
        "us": "US",
        "usa": "US",
        "amerika": "US",
        "american stocks": "US",
        "global": "Global",
        "forex": "Forex",
        "fx": "Forex",
        "crypto": "Crypto",
        "cryptocurrency": "Crypto",
        "kripto": "Crypto",
        "commodities": "Commodities",
        "emtia": "Commodities",
        "indices": "Indices",
        "index": "Indices",
        "endeks": "Indices",
        "unknown": "Unknown",
        "bilinmiyor": "Unknown",
    }

    return aliases.get(
        market.lower(),
        market,
    )


def normalize_symbols(
    value: Any,
) -> List[str]:
    symbols = clean_list(value)

    result = []

    for symbol in symbols:
        symbol = symbol.strip().upper()

        if symbol and symbol not in result:
            result.append(symbol)

    return result


# ============================================================
# PARAMETER SANITIZATION
# ============================================================

def sanitize_parameters(
    value: Any,
) -> Dict[str, Any]:
    parameters = clean_dict(value)

    result = {}

    for key, value in parameters.items():
        key = clean_string(key)

        if not key:
            continue

        if isinstance(
            value,
            (
                str,
                int,
                float,
                bool,
            ),
        ):
            result[key] = value

        elif isinstance(value, list):
            result[key] = clean_list(value)

        elif isinstance(value, dict):
            result[key] = value

    return result


# ============================================================
# RULE SANITIZATION
# ============================================================

def sanitize_rule_list(
    value: Any,
) -> List[str]:
    return clean_list(value)


def sanitize_rules(
    value: Any,
) -> Dict[str, List[str]]:
    rules = clean_dict(value)

    result = {
        "entry": [],
        "confirmation": [],
        "exit": [],
        "risk": [],
        "filters": [],
    }

    for rule_type in VALID_RULE_TYPES:
        result[rule_type] = sanitize_rule_list(
            rules.get(rule_type)
        )

    return result


# ============================================================
# CONDITION STRUCTURE
# ============================================================

def sanitize_conditions(
    value: Any,
) -> Dict[str, Any]:
    """
    V2'nin önemli kısmı.

    Kaynak stratejisindeki koşulların:
    - required
    - confirmation
    - optional
    şeklinde ayrılmasını sağlar.
    """

    conditions = clean_dict(value)

    required = clean_list(
        conditions.get("required")
    )

    confirmation = clean_list(
        conditions.get("confirmation")
    )

    optional = clean_list(
        conditions.get("optional")
    )

    logic = clean_string(
        conditions.get("logic"),
        "AND",
    ).upper()

    if logic not in {
        "AND",
        "OR",
        "MIXED",
        "UNKNOWN",
    }:
        logic = "UNKNOWN"

    return {
        "logic": logic,
        "required": required,
        "confirmation": confirmation,
        "optional": optional,
    }


# ============================================================
# FULL EXTRACTION SANITIZATION
# ============================================================

def sanitize_extraction(
    extracted: Any,
) -> Dict[str, Any]:

    if not isinstance(extracted, dict):
        extracted = {}

    source = clean_dict(
        extracted.get("source")
    )

    result = {
        "name": clean_string(
            extracted.get("name"),
            "Unnamed Strategy",
        ),

        "description": clean_string(
            extracted.get("description")
        ),

        "hypothesis": clean_string(
            extracted.get("hypothesis")
        ),

        "source": {
            "type": normalize_source_type(
                source.get("type")
            ),
            "name": clean_string(
                source.get("name")
            ),
            "url": clean_string(
                source.get("url")
            ),
            "author": clean_string(
                source.get("author")
            ),
        },

        "market": normalize_market(
            extracted.get("market")
        ),

        "symbols": normalize_symbols(
            extracted.get("symbols")
        ),

        "tags": clean_list(
            extracted.get("tags")
        ),

        "parameters": sanitize_parameters(
            extracted.get("parameters")
        ),

        "rules": sanitize_rules(
            extracted.get("rules")
        ),

        "conditions": sanitize_conditions(
            extracted.get("conditions")
        ),

        "notes": clean_string(
            extracted.get("notes")
        ),

        "uncertainties": clean_list(
            extracted.get("uncertainties")
        ),
    }

    return result


# ============================================================
# JSON PARSER
# ============================================================

def parse_json_response(
    text: str,
) -> Dict[str, Any]:

    text = clean_string(text)

    if not text:
        return {}

    # Direct JSON
    try:
        parsed = json.loads(text)

        if isinstance(parsed, dict):
            return parsed

    except json.JSONDecodeError:
        pass

    # Markdown code block
    if "```" in text:
        parts = text.split("```")

        for part in parts:
            candidate = part.strip()

            if candidate.startswith("json"):
                candidate = candidate[4:].strip()

            try:
                parsed = json.loads(candidate)

                if isinstance(parsed, dict):
                    return parsed

            except json.JSONDecodeError:
                continue

    # JSON object extraction
    first = text.find("{")
    last = text.rfind("}")

    if first != -1 and last != -1:
        candidate = text[first:last + 1]

        try:
            parsed = json.loads(candidate)

            if isinstance(parsed, dict):
                return parsed

        except json.JSONDecodeError:
            pass

    return {}


# ============================================================
# SOURCE TEXT
# ============================================================

def prepare_source_text(
    source_text: str,
) -> str:

    source_text = clean_string(
        source_text
    )

    if not source_text:
        raise ValueError(
            "Kaynak metni boş."
        )

    if len(source_text) <= MAX_SOURCE_CHARS:
        return source_text

    print(
        f"⚠️ Kaynak çok uzun: "
        f"{len(source_text):,} karakter"
    )

    print(
        f"✂️ İlk {MAX_SOURCE_CHARS:,} karakter kullanılacak."
    )

    return source_text[
        :MAX_SOURCE_CHARS
    ]


# ============================================================
# AI PROMPT V2
# ============================================================

def build_extraction_prompt(
    source_text: str,
    source_metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> str:

    source_metadata = (
        source_metadata
        if isinstance(
            source_metadata,
            dict,
        )
        else {}
    )

    metadata_json = json.dumps(
        source_metadata,
        ensure_ascii=False,
        indent=2,
    )

    return f"""
Sen MarketHQ Strategy Extractor V2'sin.

Görevin, verilen kaynak metinden bir trading stratejisinin
mantığını mümkün olduğunca kaynakta anlatıldığı şekliyle
yapılandırmaktır.

ANA PRENSİP:

Kaynakta yazan şey = kaynak iddiası.

Kaynakta yazan şey ≠ doğrulanmış strateji.

Bu nedenle:
- backtest uydurma,
- win rate uydurma,
- profit factor uydurma,
- getiri uydurma,
- drawdown uydurma,
- işlem sonucu uydurma,
- broker/order execution bilgisi uydurma.

Strateji daha sonra MarketHQ tarafından test edilecektir.

============================================================
KURAL SINIFLANDIRMASI
============================================================

ENTRY:
Pozisyona giriş için doğrudan kullanılan koşullar.

CONFIRMATION:
Girişi teyit eden fakat tek başına giriş anlamına gelmeyen
koşullar.

FILTERS:
İşlem yapılmasını kısıtlayan piyasa/zaman/trend koşulları.

EXIT:
Pozisyon kapatma koşulları.

RISK:
Stop, target, risk yüzdesi, pozisyon büyüklüğü gibi risk
yönetimi kuralları.

============================================================
ZORUNLU / TEYİT AYRIMI
============================================================

Ayrıca conditions alanını doldur:

"required":
Kaynağın açıkça zorunlu olduğunu söylediği koşullar.

"confirmation":
Kaynağın teyit olarak kullandığı koşullar.

"optional":
Kaynağın opsiyonel veya tercihe bağlı olduğunu söylediği
koşullar.

"logic":
Koşulların mantığı:

AND
OR
MIXED
UNKNOWN

Kaynak bu ayrımı açıkça vermiyorsa UNKNOWN kullan.

KESİNLİKLE tahmin ederek AND veya OR seçme.

============================================================
PARAMETRELER
============================================================

Kaynakta sayı varsa çıkar.

Örnek:

"SMA 10 ve SMA 100 kullanılır."

çıktı:

"parameters":
{{
    "sma_fast": 10,
    "sma_slow": 100
}}

Ancak kaynak sadece:

"SMA kullanılır."

diyorsa sayı uydurma.

============================================================
BELİRSİZLİK
============================================================

Kaynakta açık olmayan her önemli noktayı:

"uncertainties"

alanına yaz.

Örneğin:

- SMA ve RSI koşullarının aynı anda zorunlu olup olmadığı
- bar kapanışı gerekip gerekmediği
- ATR periyodu
- short koşullarının bulunup bulunmadığı
- pozisyon büyüklüğü
- komisyon/slippage
- zaman dilimi

============================================================
ÇOK ÖNEMLİ
============================================================

Kaynakta long anlatılıyorsa short tarafını uydurma.

Kaynakta stop yoksa stop uydurma.

Kaynakta target yoksa target uydurma.

Kaynakta zaman dilimi yoksa zaman dilimi uydurma.

Kaynakta ATR periyodu yoksa ATR periyodu uydurma.

Kaynakta performans sonucu yoksa performans sonucu üretme.

============================================================
ÇIKTI
============================================================

SADECE GEÇERLİ JSON DÖNDÜR.

Şu yapıyı kullan:

{{
  "name": "strateji adı",

  "description": "kısa açıklama",

  "hypothesis":
    "test edilmesi gereken temel strateji hipotezi",

  "source": {{
    "type": "manual | youtube | article | book | research | interview | backtest | walk_forward | market_hq | unknown",
    "name": "",
    "url": "",
    "author": ""
  }},

  "market": "BIST | US | Global | Forex | Crypto | Commodities | Indices | Unknown",

  "symbols": [],

  "tags": [],

  "parameters": {{}},

  "conditions": {{
    "logic": "AND | OR | MIXED | UNKNOWN",

    "required": [],

    "confirmation": [],

    "optional": []
  }},

  "rules": {{
    "entry": [],

    "confirmation": [],

    "exit": [],

    "risk": [],

    "filters": []
  }},

  "notes": "",

  "uncertainties": []
}}

============================================================
KAYNAK METADATA
============================================================

{metadata_json}

============================================================
KAYNAK METNİ
============================================================

---------------- SOURCE START ----------------

{source_text}

---------------- SOURCE END ----------------
"""


# ============================================================
# EXTRACTION
# ============================================================

def extract_strategy_from_text(
    source_text: str,
    source_metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> Dict[str, Any]:

    source_text = prepare_source_text(
        source_text
    )

    prompt = build_extraction_prompt(
        source_text,
        source_metadata,
    )

    print()
    print("=" * 70)
    print("🧠 STRATEGY EXTRACTOR V2")
    print("=" * 70)

    print(
        f"📄 Kaynak karakteri : "
        f"{len(source_text):,}"
    )

    print(
        f"🤖 Model            : "
        f"{MODEL_NAME}"
    )

    print()
    print(
        "⏳ Strateji çıkarılıyor..."
    )

    try:
        response = client.responses.create(
            model=MODEL_NAME,
            input=prompt,
        )

    except Exception as exc:
        raise RuntimeError(
            "OpenAI Strategy Extractor hatası: "
            f"{exc}"
        ) from exc

    output_text = getattr(
        response,
        "output_text",
        "",
    )

    parsed = parse_json_response(
        output_text
    )

    if not parsed:
        raise RuntimeError(
            "AI geçerli JSON döndürmedi.\n\n"
            "Model çıktısı:\n"
            f"{output_text[:5000]}"
        )

    return sanitize_extraction(
        parsed
    )


# ============================================================
# SAVE TO KNOWLEDGE BASE
# ============================================================

def save_extracted_strategy(
    extracted: Dict[str, Any],
    source_metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> str:

    extracted = sanitize_extraction(
        extracted
    )

    source_metadata = (
        source_metadata
        if isinstance(
            source_metadata,
            dict,
        )
        else {}
    )

    source = extracted[
        "source"
    ]

    source_type = normalize_source_type(
        source.get("type")
        or source_metadata.get("type")
    )

    source_name = (
        source.get("name")
        or clean_string(
            source_metadata.get("name")
        )
    )

    source_url = (
        source.get("url")
        or clean_string(
            source_metadata.get("url")
        )
    )

    source_author = (
        source.get("author")
        or clean_string(
            source_metadata.get("author")
        )
    )

    market = extracted[
        "market"
    ]

    if market == "Unknown":
        market = normalize_market(
            source_metadata.get("market")
        )

    symbols = extracted[
        "symbols"
    ]

    if not symbols:
        symbols = normalize_symbols(
            source_metadata.get("symbols")
        )

    print()
    print("=" * 70)
    print("💾 KNOWLEDGE BASE KAYDI")
    print("=" * 70)

    print(
        f"📌 Strateji : "
        f"{extracted['name']}"
    )

    print(
        f"🌍 Market   : "
        f"{market}"
    )

    print(
        "📊 Sembol   : "
        + (
            ", ".join(symbols)
            if symbols
            else "Belirtilmemiş"
        )
    )

    print(
        f"📚 Kaynak   : "
        f"{source_type}"
    )

    # --------------------------------------------------------
    # 1. CREATE STRATEGY
    # --------------------------------------------------------

    strategy = create_strategy(
        name=extracted["name"],
        description=extracted["description"],
        source_type=source_type,
        source_name=source_name,
        source_url=source_url,
        source_author=source_author,
        market=market,
        symbols=symbols,
        tags=extracted["tags"],
        hypothesis=extracted["hypothesis"],
        notes=extracted["notes"],
    )

    strategy_id = add_strategy(
        strategy
    )

    if not strategy_id:
        raise RuntimeError(
            "Strategy Knowledge Base'e eklenemedi."
        )

    print(
        f"🆔 Strategy ID: "
        f"{strategy_id}"
    )

    # --------------------------------------------------------
    # 2. PARAMETERS
    # --------------------------------------------------------

    parameters = extracted[
        "parameters"
    ]

    if parameters:
        success = set_strategy_parameters(
            strategy_id,
            parameters,
        )

        if success:
            print(
                f"⚙️ Parametre sayısı: "
                f"{len(parameters)}"
            )
        else:
            print(
                "⚠️ Parametreler kaydedilemedi."
            )

    # --------------------------------------------------------
    # 3. NORMAL RULES
    # --------------------------------------------------------

    rule_count = 0

    for rule_type in (
        "entry",
        "exit",
        "risk",
        "filters",
    ):
        rules = extracted[
            "rules"
        ].get(
            rule_type,
            [],
        )

        for rule in rules:

            if not rule:
                continue

            success = add_rule(
                strategy_id,
                rule_type,
                rule,
            )

            if success:
                rule_count += 1

    print(
        f"📋 KB kural sayısı: "
        f"{rule_count}"
    )

    # --------------------------------------------------------
    # 4. CONFIRMATION RULES
    # --------------------------------------------------------
    #
    # Knowledge Base'in add_rule API'sinde confirmation
    # tipi olmadığı için bunları filters içine zorla
    # yazmıyoruz.
    #
    # Ayrı observation olarak saklıyoruz.
    # --------------------------------------------------------

    confirmation_rules = extracted[
        "rules"
    ].get(
        "confirmation",
        [],
    )

    conditions = extracted[
        "conditions"
    ]

    required_conditions = conditions[
        "required"
    ]

    confirmation_conditions = conditions[
        "confirmation"
    ]

    optional_conditions = conditions[
        "optional"
    ]

    logic = conditions[
        "logic"
    ]

    if (
        confirmation_rules
        or required_conditions
        or confirmation_conditions
        or optional_conditions
    ):

        confirmation_payload = {
            "logic": logic,
            "required": required_conditions,
            "confirmation": (
                confirmation_conditions
                or confirmation_rules
            ),
            "optional": optional_conditions,
        }

        add_observation(
            strategy_id,
            (
                "Strategy Extractor V2 koşul sınıflandırması: "
                + json.dumps(
                    confirmation_payload,
                    ensure_ascii=False,
                )
            ),
            observation_type="condition_structure",
        )

    # --------------------------------------------------------
    # 5. UNCERTAINTIES
    # --------------------------------------------------------

    uncertainties = extracted[
        "uncertainties"
    ]

    for uncertainty in uncertainties:

        if not uncertainty:
            continue

        add_observation(
            strategy_id,
            (
                "Strategy Extractor V2 belirsizliği: "
                f"{uncertainty}"
            ),
            observation_type="uncertainty",
        )

    # --------------------------------------------------------
    # 6. EXTRACTION OBSERVATION
    # --------------------------------------------------------

    add_observation(
        strategy_id,
        (
            "Strateji kaynak metninden "
            "Strategy Extractor V2 tarafından çıkarıldı. "
            "Kaynak iddiaları henüz MarketHQ tarafından "
            "backtest veya walk-forward ile doğrulanmamıştır."
        ),
        observation_type="extraction",
    )

    # --------------------------------------------------------
    # 7. LEARNING STATUS
    # --------------------------------------------------------

    update_learning_status(
        strategy_id
    )

    print()
    print(
        "✅ Strateji Knowledge Base'e kaydedildi."
    )

    print(
        "🧪 Durum: "
        "HYPOTHESIS / TESTING sürecine hazır."
    )

    return strategy_id


# ============================================================
# EXTRACT + SAVE
# ============================================================

def extract_and_save(
    source_text: str,
    source_metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> Dict[str, Any]:

    extracted = extract_strategy_from_text(
        source_text,
        source_metadata,
    )

    strategy_id = save_extracted_strategy(
        extracted,
        source_metadata,
    )

    return {
        "strategy_id": strategy_id,
        "strategy": extracted,
    }


# ============================================================
# FILE READER
# ============================================================

def read_text_file(
    file_path: str,
) -> str:

    path = Path(
        file_path
    ).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(
            f"Dosya bulunamadı: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Dosya değil: {path}"
        )

    try:
        return path.read_text(
            encoding="utf-8"
        )

    except UnicodeDecodeError:
        return path.read_text(
            encoding="utf-8-sig"
        )


# ============================================================
# FILE EXTRACTION
# ============================================================

def extract_from_file(
    file_path: str,
    source_metadata: Optional[
        Dict[str, Any]
    ] = None,
) -> Dict[str, Any]:

    path = Path(
        file_path
    ).expanduser().resolve()

    source_text = read_text_file(
        str(path)
    )

    metadata = (
        dict(source_metadata)
        if isinstance(
            source_metadata,
            dict,
        )
        else {}
    )

    if not metadata.get("name"):
        metadata["name"] = path.stem

    if not metadata.get("type"):
        metadata["type"] = "manual"

    return extract_and_save(
        source_text,
        metadata,
    )


# ============================================================
# PRINT RESULT
# ============================================================

def print_extraction_result(
    result: Dict[str, Any],
) -> None:

    strategy = result.get(
        "strategy",
        {},
    )

    print()
    print("=" * 70)
    print("📊 STRATEGY EXTRACTION V2 SONUCU")
    print("=" * 70)

    print(
        f"Strategy ID : "
        f"{result.get('strategy_id', '-')}"
    )

    print(
        f"Name        : "
        f"{strategy.get('name', '-')}"
    )

    print(
        f"Market      : "
        f"{strategy.get('market', '-')}"
    )

    symbols = strategy.get(
        "symbols",
        [],
    )

    print(
        "Symbols     : "
        + (
            ", ".join(symbols)
            if symbols
            else "-"
        )
    )

    source = strategy.get(
        "source",
        {},
    )

    print(
        f"Source      : "
        f"{source.get('type', '-')}"
    )

    # --------------------------------------------------------
    # PARAMETERS
    # --------------------------------------------------------

    print()
    print("PARAMETERS:")

    parameters = strategy.get(
        "parameters",
        {},
    )

    if parameters:

        for key, value in parameters.items():
            print(
                f"  - {key}: {value}"
            )

    else:
        print(
            "  - Yok"
        )

    # --------------------------------------------------------
    # CONDITIONS
    # --------------------------------------------------------

    print()
    print("CONDITION STRUCTURE:")

    conditions = strategy.get(
        "conditions",
        {},
    )

    print(
        f"  Logic: "
        f"{conditions.get('logic', 'UNKNOWN')}"
    )

    print()
    print("  REQUIRED:")

    required = conditions.get(
        "required",
        [],
    )

    if required:
        for item in required:
            print(
                f"    - {item}"
            )
    else:
        print(
            "    - Yok"
        )

    print()
    print("  CONFIRMATION:")

    confirmation = conditions.get(
        "confirmation",
        [],
    )

    if confirmation:
        for item in confirmation:
            print(
                f"    - {item}"
            )
    else:
        print(
            "    - Yok"
        )

    print()
    print("  OPTIONAL:")

    optional = conditions.get(
        "optional",
        [],
    )

    if optional:
        for item in optional:
            print(
                f"    - {item}"
            )
    else:
        print(
            "    - Yok"
        )

    # --------------------------------------------------------
    # RULES
    # --------------------------------------------------------

    print()
    print("RULES:")

    rules = strategy.get(
        "rules",
        {},
    )

    for rule_type in (
        "entry",
        "confirmation",
        "exit",
        "risk",
        "filters",
    ):

        print(
            f"  {rule_type.upper()}:"
        )

        rule_list = rules.get(
            rule_type,
            [],
        )

        if rule_list:

            for rule in rule_list:
                print(
                    f"    - {rule}"
                )

        else:
            print(
                "    - Yok"
            )

    # --------------------------------------------------------
    # UNCERTAINTIES
    # --------------------------------------------------------

    print()
    print("UNCERTAINTIES:")

    uncertainties = strategy.get(
        "uncertainties",
        [],
    )

    if uncertainties:

        for item in uncertainties:
            print(
                f"  - {item}"
            )

    else:
        print(
            "  - Yok"
        )

    print(
        "=" * 70
    )


# ============================================================
# DEMO
# ============================================================

DEMO_SOURCE = """
Bu örnek strateji trend takip mantığı kullanır.

SMA 10 ile SMA 100 trend yönünü belirlemek için kullanılır.
SMA 10, SMA 100'ün üzerine çıktığında long giriş düşünülür.

EMA 20 ve EMA 30 ek trend filtresi olarak kullanılır.
EMA 20, EMA 30'un üzerinde olduğunda long taraf tercih edilir.

RSI 14 kullanılır.
RSI 30'un altından toparlanıp 50 seviyesinin üzerine çıkarsa
momentum teyidi olarak değerlendirilir.

Risk yönetiminde giriş fiyatından 1.5 ATR uzaklıkta stop,
3 ATR uzaklıkta hedef kullanılır.

SMA kesişimi ana giriş koşuludur.
EMA trend filtresi olarak kullanılmalıdır.
RSI ise giriş için momentum teyidi sağlar.

Bu strateji henüz backtest edilmemiştir.
"""


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print()
    print("=" * 70)
    print("MARKETHQ STRATEGY EXTRACTOR V2")
    print("=" * 70)

    # --------------------------------------------------------
    # FILE MODE
    # --------------------------------------------------------

    if len(sys.argv) > 1:

        file_path = sys.argv[1]

        print(
            f"📄 Kaynak dosya: "
            f"{file_path}"
        )

        result = extract_from_file(
            file_path,
            {
                "type": "manual",
                "name": Path(
                    file_path
                ).stem,
            },
        )

        print_extraction_result(
            result
        )

        return

    # --------------------------------------------------------
    # DEMO MODE
    # --------------------------------------------------------

    print(
        "🧪 Demo kaynak kullanılıyor."
    )

    result = extract_and_save(
        DEMO_SOURCE,
        {
            "type": "manual",
            "name": (
                "MarketHQ "
                "Strategy Extractor V2 Demo"
            ),
            "market": "BIST",
            "symbols": [
                "THYAO.IS"
            ],
        },
    )

    print_extraction_result(
        result
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
