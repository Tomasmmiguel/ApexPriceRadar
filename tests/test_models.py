from decimal import Decimal

import pytest

from models.enums import AvailabilityStatus, RetailerEnum
from models.product import NormalizedProduct, RawProduct, clean_currency_to_decimal


def test_clean_currency_formats():
    assert clean_currency_to_decimal("1.299,99 €") == Decimal("1299.99")
    assert clean_currency_to_decimal("€ 449.00") == Decimal("449.00")
    assert clean_currency_to_decimal("89,50") == Decimal("89.50")
    assert clean_currency_to_decimal("2,499.00 €") == Decimal("2499.00")
    assert clean_currency_to_decimal(199.99) == Decimal("199.99")
    # Casos reais de scraping defensivo
    assert clean_currency_to_decimal("€94,99€99,99") == Decimal("94.99")
    assert clean_currency_to_decimal("94,99 € 99,99 €") == Decimal("94.99")
    assert clean_currency_to_decimal("38,.28") == Decimal("38.28")
    assert clean_currency_to_decimal("38,28 \xa0€") == Decimal("38.28")
    assert clean_currency_to_decimal("1.299 €") == Decimal("1299.00")
    assert clean_currency_to_decimal("1 299,00 €") == Decimal("1299.00")
    assert clean_currency_to_decimal("1799") == Decimal("1799.00")
    assert clean_currency_to_decimal(1799) == Decimal("1799.00")
    assert clean_currency_to_decimal(84.3) == Decimal("84.30")


def test_normalized_product_from_raw(sample_raw_product: RawProduct):
    norm = NormalizedProduct.from_raw(sample_raw_product)
    assert norm.retailer == RetailerEnum.WORTEN
    assert norm.sku == "TEST-SKU-001"
    assert norm.price == Decimal("1199.99")
    assert norm.availability == AvailabilityStatus.IN_STOCK
    assert norm.currency == "EUR"


def test_normalized_product_out_of_stock():
    raw = RawProduct(
        retailer=RetailerEnum.AMAZON,
        sku="B08N5WRWNW",
        name="PlayStation 5 Console",
        raw_price="549,99 €",
        url="https://www.amazon.es/dp/B08N5WRWNW",
        availability_raw="Artigo esgotado ou temporariamente indisponível",
    )
    norm = NormalizedProduct.from_raw(raw)
    assert norm.availability == AvailabilityStatus.OUT_OF_STOCK


def test_invalid_raw_price_raises_error():
    raw = RawProduct(
        retailer=RetailerEnum.WORTEN,
        sku="SKU-ERR",
        name="Produto Sem Preco",
        raw_price="Gratis / Nao informado",
        url="https://www.worten.pt/p/123",
    )
    with pytest.raises(ValueError):
        NormalizedProduct.from_raw(raw)
