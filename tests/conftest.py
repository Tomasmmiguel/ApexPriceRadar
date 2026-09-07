from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.models import Base
from models.enums import AvailabilityStatus, RetailerEnum
from models.product import NormalizedProduct, RawProduct


@pytest.fixture
def sample_raw_product() -> RawProduct:
    return RawProduct(
        retailer=RetailerEnum.WORTEN,
        sku="TEST-SKU-001",
        name="Smartphone Galaxy S24 Ultra 256GB",
        raw_price="1.199,99 €",
        url="https://www.worten.pt/produtos/s24-ultra",
        category="smartphones",
        availability_raw="Em stock",
    )


@pytest.fixture
def sample_normalized_product() -> NormalizedProduct:
    return NormalizedProduct(
        retailer=RetailerEnum.WORTEN,
        sku="TEST-SKU-001",
        name="Smartphone Galaxy S24 Ultra 256GB",
        price=Decimal("1199.99"),
        currency="EUR",
        url="https://www.worten.pt/produtos/s24-ultra",
        category="smartphones",
        availability=AvailabilityStatus.IN_STOCK,
    )


@pytest.fixture
async def async_test_session() -> AsyncGenerator[AsyncSession, None]:
    """Cria uma base SQLite assíncrona isolada em memória para os testes."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await engine.dispose()
