from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.repository import ProductRepository
from models.enums import AvailabilityStatus, RetailerEnum
from models.product import NormalizedProduct


@pytest.mark.asyncio
async def test_repository_upsert_and_history(async_test_session: AsyncSession):
    repo = ProductRepository(async_test_session)

    prod = NormalizedProduct(
        retailer=RetailerEnum.WORTEN,
        sku="TEST-SKU-REPO",
        name="Monitor Gaming 144Hz",
        price=Decimal("199.99"),
        url="https://worten.pt/p/monitor",
        availability=AvailabilityStatus.IN_STOCK,
    )

    # 1. Primeira inserção
    prod_rec, price_rec = await repo.save_normalized_product(prod)
    await async_test_session.commit()

    assert prod_rec.id is not None
    assert price_rec.price == Decimal("199.99")

    # 2. Segunda inserção (Preço baixou para 179.99)
    prod_updated = NormalizedProduct(
        retailer=RetailerEnum.WORTEN,
        sku="TEST-SKU-REPO",
        name="Monitor Gaming 144Hz (Novo Nome)",
        price=Decimal("179.99"),
        url="https://worten.pt/p/monitor",
        availability=AvailabilityStatus.IN_STOCK,
    )
    prod_rec2, price_rec2 = await repo.save_normalized_product(prod_updated)
    await async_test_session.commit()

    # O ID do produto deve ser o mesmo (Idempotência / UPSERT)
    assert prod_rec2.id == prod_rec.id
    assert prod_rec2.name == "Monitor Gaming 144Hz (Novo Nome)"

    # Deve haver 2 registos no histórico
    stats = await repo.get_latest_product_stats(prod_rec.id)
    assert stats is not None
    assert stats["readings_count"] == 2
    assert stats["current_price"] == 179.99
    assert stats["min_price"] == 179.99
    assert stats["max_price"] == 199.99
