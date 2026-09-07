import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.enums import AvailabilityStatus, RetailerEnum


def clean_currency_to_decimal(raw_value: str | float | int | Decimal) -> Decimal:
    """
    Sanitiza strings de preços no formato europeu e americano para Decimal exato.
    Trata casos complexos e defensivos:
      - "1.249,99 €" -> Decimal("1249.99")
      - "€ 449.00"    -> Decimal("449.00")
      - "89,90"       -> Decimal("89.90")
      - "1,499.99 €"  -> Decimal("1499.99")
      - "€94,99€99,99" -> Decimal("94.99") (preço promocional concatenado com riscado)
      - "38,.28"      -> Decimal("38.28") (separador duplo)
      - "1.299 €"     -> Decimal("1299.00") (milhar europeu sem centavos)
      - "1 299,00 €"  -> Decimal("1299.00") (espaços de milhar)
      - "1799"        -> Decimal("1799.00")
    """
    if isinstance(raw_value, Decimal):
        return raw_value.quantize(Decimal("0.01"))
    if isinstance(raw_value, (int, float)):
        return Decimal(str(raw_value)).quantize(Decimal("0.01"))

    val = str(raw_value).strip()
    if not val:
        raise ValueError(f"Não foi possível extrair um valor numérico de '{raw_value}'")

    # Normaliza espaços (incluindo espaços insecáveis &nbsp; / \xa0)
    val = val.replace("\xa0", " ").replace("&nbsp;", " ")

    # Corrige separadores consecutivos corrompidos (ex: '38,.28' -> '38.28', '38..28' -> '38.28')
    val = re.sub(r"[,\.]+", lambda m: m.group(0)[-1] if len(m.group(0)) > 1 else m.group(0), val)

    # Isola símbolos monetários para evitar colagem com números
    val = re.sub(r"([€$£])", r" \1 ", val)

    # Identifica blocos numéricos formatados como preços
    pattern = re.compile(
        r"(\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})|\d{1,3}(?:,\d{3})+(?:\.\d{1,2})|\d{1,3}(?:[.\s]\d{3})+(?!\d)|\d+(?:[,\.]\d{1,2})(?!\d)|\d+)"
    )
    matches = pattern.findall(val)
    candidate = matches[0].strip() if matches else re.sub(r"[^\d,\.]", "", val)

    if not candidate:
        raise ValueError(f"Não foi possível extrair um valor numérico de '{raw_value}'")

    candidate = re.sub(r"\s+", "", candidate)

    # Conversão de formatos europeus vs americanos
    if "," in candidate and "." in candidate:
        if candidate.rfind(",") > candidate.rfind("."):
            # Formato europeu: 1.299,99 -> 1299.99
            candidate = candidate.replace(".", "").replace(",", ".")
        else:
            # Formato americano: 1,299.99 -> 1299.99
            candidate = candidate.replace(",", "")
    elif "," in candidate:
        parts = candidate.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and not candidate.startswith("0"):
            # Milhar com vírgula (ex: 1,299)
            candidate = candidate.replace(",", "")
        else:
            candidate = candidate.replace(",", ".")
    elif "." in candidate:
        parts = candidate.split(".")
        if len(parts) == 2 and len(parts[1]) == 3 and not candidate.startswith("0"):
            # Milhar europeu com ponto (ex: 1.299)
            candidate = candidate.replace(".", "")

    try:
        return Decimal(candidate).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        digits = re.findall(r"\d+", candidate)
        if digits:
            return Decimal(digits[0]).quantize(Decimal("0.01"))
        raise ValueError(f"Não foi possível extrair um valor numérico de '{raw_value}'") from None


class RawProduct(BaseModel):
    """Representa o dado bruto extraído diretamente do scraper antes da normalização."""

    retailer: RetailerEnum
    sku: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=2)
    raw_price: str
    url: str
    category: str = "technology"
    availability_raw: str | None = None
    brand: str | None = None
    image_url: str | None = None

    model_config = ConfigDict(extra="ignore")


class NormalizedProduct(BaseModel):
    """Contrato de dados validado para uso nos pipelines e armazenamento."""

    retailer: RetailerEnum
    sku: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=2)
    price: Decimal = Field(..., gt=Decimal("0.00"))
    currency: str = Field(default="EUR", max_length=3)
    url: str
    category: str = "technology"
    availability: AvailabilityStatus = AvailabilityStatus.IN_STOCK
    brand: str | None = None
    image_url: str | None = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="ignore")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        # Normaliza múltiplos espaços e quebras de linha
        return re.sub(r"\s+", " ", v).strip()

    @field_validator("price", mode="before")
    @classmethod
    def parse_price(cls, v: Any) -> Decimal:
        return clean_currency_to_decimal(v)

    @classmethod
    def from_raw(cls, raw: RawProduct) -> "NormalizedProduct":
        price = clean_currency_to_decimal(raw.raw_price)

        # Avaliação de disponibilidade baseada no texto bruto
        availability = AvailabilityStatus.IN_STOCK
        if raw.availability_raw:
            raw_avail_lower = raw.availability_raw.lower()
            if any(
                term in raw_avail_lower
                for term in [
                    "esgotado",
                    "indisponível",
                    "out of stock",
                    "temporariamente indisponível",
                ]
            ):
                availability = AvailabilityStatus.OUT_OF_STOCK
            elif any(term in raw_avail_lower for term in ["pré-venda", "pre-order", "reserva"]):
                availability = AvailabilityStatus.PRE_ORDER

        return cls(
            retailer=raw.retailer,
            sku=raw.sku.strip(),
            name=raw.name,
            price=price,
            currency="EUR",
            url=raw.url.strip(),
            category=raw.category,
            availability=availability,
            brand=raw.brand.strip() if raw.brand else None,
            image_url=raw.image_url.strip() if raw.image_url else None,
        )
