from datetime import UTC, datetime

import pandas as pd

from models.enums import RetailerEnum
from models.product import RawProduct
from pipelines.cleaning import clean_and_normalize_raw_batch
from pipelines.metrics import compute_market_intelligence_signals


def test_clean_and_normalize_raw_batch_deduplication():
    item1 = RawProduct(
        retailer=RetailerEnum.WORTEN,
        sku="SKU-DUP-1",
        name="Produto Teste",
        raw_price="100.00 €",
        url="https://worten.pt/p/1",
    )
    # Cópia duplicada com mesmo retailer e SKU
    item2 = RawProduct(
        retailer=RetailerEnum.WORTEN,
        sku="SKU-DUP-1",
        name="Produto Teste Renomeado",
        raw_price="100.00 €",
        url="https://worten.pt/p/1",
    )
    item3 = RawProduct(
        retailer=RetailerEnum.WORTEN,
        sku="SKU-DUP-2",
        name="Produto Único",
        raw_price="200.00 €",
        url="https://worten.pt/p/2",
    )

    result = clean_and_normalize_raw_batch([item1, item2, item3])
    assert len(result) == 2
    assert [p.sku for p in result] == ["SKU-DUP-1", "SKU-DUP-2"]


def test_compute_market_intelligence_signals():
    now = datetime.now(UTC)
    # Simula 3 leituras do mesmo produto: histórico de 100€, 120€ e agora caiu para 80€
    history_data = [
        {
            "product_id": 1,
            "retailer": "worten",
            "sku": "PS5-SLIM",
            "name": "PlayStation 5 Slim",
            "category": "consoles",
            "url": "https://worten.pt/ps5",
            "price": 100.00,
            "availability": "in_stock",
            "recorded_at": now.replace(day=1),
        },
        {
            "product_id": 1,
            "retailer": "worten",
            "sku": "PS5-SLIM",
            "name": "PlayStation 5 Slim",
            "category": "consoles",
            "url": "https://worten.pt/ps5",
            "price": 120.00,
            "availability": "in_stock",
            "recorded_at": now.replace(day=2),
        },
        {
            "product_id": 1,
            "retailer": "worten",
            "sku": "PS5-SLIM",
            "name": "PlayStation 5 Slim",
            "category": "consoles",
            "url": "https://worten.pt/ps5",
            "price": 80.00,
            "availability": "in_stock",
            "recorded_at": now.replace(day=3),
        },
    ]
    df = pd.DataFrame(history_data)
    signals = compute_market_intelligence_signals(df, min_discount_threshold=15.0)

    assert len(signals) == 1
    row = signals.iloc[0]
    assert row["price"] == 80.00
    assert row["historical_min"] == 80.00
    assert row["historical_max"] == 120.00
    assert row["historical_avg"] == 100.00
    # Desconto: (100 - 80) / 100 = 20.0%
    assert row["discount_vs_avg_pct"] == 20.0
    assert bool(row["is_all_time_low"]) is True
    assert bool(row["is_deal_alert"]) is True
