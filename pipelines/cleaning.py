import logging

from models.product import NormalizedProduct, RawProduct

logger = logging.getLogger(__name__)


def clean_and_normalize_raw_batch(raw_items: list[RawProduct]) -> list[NormalizedProduct]:
    """
    Processa um lote de produtos brutos:
    1. Deduplica produtos idênticos no mesmo scrape (mesmo retailer e sku)
    2. Valida contratos de dados com Pydantic
    3. Descarta registos corrompidos com log defensivo
    """
    normalized: list[NormalizedProduct] = []
    seen_keys: set[tuple[str, str]] = set()

    for raw in raw_items:
        key = (raw.retailer.value, raw.sku)
        if key in seen_keys:
            logger.debug(f"Item duplicado descartado no lote: {key}")
            continue

        try:
            norm = NormalizedProduct.from_raw(raw)
            seen_keys.add(key)
            normalized.append(norm)
        except Exception as exc:
            logger.warning(
                f"Erro na normalização do produto [SKU: {raw.sku}, Loja: {raw.retailer}]: {exc}"
            )

    return normalized
