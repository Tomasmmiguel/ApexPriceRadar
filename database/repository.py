import logging
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PriceRecord, ProductRecord
from models.product import NormalizedProduct

logger = logging.getLogger(__name__)


class ProductRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_product(self, product: NormalizedProduct) -> ProductRecord:
        """
        Garante a idempotência do produto por (retailer, sku).
        Atualiza metadados mutáveis (nome, url, imagem) e 'last_updated'.
        """
        stmt = select(ProductRecord).where(
            ProductRecord.retailer == product.retailer.value,
            ProductRecord.sku == product.sku,
        )
        result = await self.session.execute(stmt)
        record = result.scalars().first()

        now = datetime.now(UTC)
        if record:
            record.name = product.name
            record.url = product.url
            record.category = product.category
            if product.brand:
                record.brand = product.brand
            if product.image_url:
                record.image_url = product.image_url
            record.last_updated = now
        else:
            record = ProductRecord(
                retailer=product.retailer.value,
                sku=product.sku,
                name=product.name,
                category=product.category,
                url=product.url,
                brand=product.brand,
                image_url=product.image_url,
                first_seen=now,
                last_updated=now,
            )
            self.session.add(record)

        await self.session.flush()
        return record

    async def record_price(
        self,
        product_id: int,
        price: Decimal,
        currency: str = "EUR",
        availability: str = "in_stock",
        recorded_at: datetime | None = None,
    ) -> PriceRecord:
        """Adiciona uma nova leitura na série temporal do produto."""
        record = PriceRecord(
            product_id=product_id,
            price=price,
            currency=currency,
            availability=availability,
            recorded_at=recorded_at or datetime.now(UTC),
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def save_normalized_product(
        self, product: NormalizedProduct
    ) -> tuple[ProductRecord, PriceRecord]:
        """Operação atómica para persistir produto e o seu preço atual."""
        prod_record = await self.upsert_product(product)
        price_record = await self.record_price(
            product_id=prod_record.id,
            price=product.price,
            currency=product.currency,
            availability=product.availability.value,
            recorded_at=product.scraped_at,
        )
        return prod_record, price_record

    async def get_price_history_dataframe(self) -> pd.DataFrame:
        """
        Extrai o histórico consolidado de preços para enriquecimento analítico no Pandas.
        """
        stmt = (
            select(
                ProductRecord.id.label("product_id"),
                ProductRecord.retailer,
                ProductRecord.sku,
                ProductRecord.name,
                ProductRecord.category,
                ProductRecord.url,
                PriceRecord.price,
                PriceRecord.availability,
                PriceRecord.recorded_at,
            )
            .join(PriceRecord, ProductRecord.id == PriceRecord.product_id)
            .order_by(ProductRecord.id, PriceRecord.recorded_at.asc())
        )
        result = await self.session.execute(stmt)
        rows = result.mappings().all()

        if not rows:
            return pd.DataFrame(
                columns=[
                    "product_id",
                    "retailer",
                    "sku",
                    "name",
                    "category",
                    "url",
                    "price",
                    "availability",
                    "recorded_at",
                ]
            )

        df = pd.DataFrame(rows)
        df["price"] = df["price"].astype(float)
        return df

    async def get_latest_product_stats(self, product_id: int) -> dict[str, float] | None:
        """Calcula métricas rápidas para um produto individual."""
        stmt = (
            select(PriceRecord.price)
            .where(PriceRecord.product_id == product_id)
            .order_by(desc(PriceRecord.recorded_at))
        )
        result = await self.session.execute(stmt)
        prices = [float(p) for p in result.scalars().all()]
        if not prices:
            return None

        current = prices[0]
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)

        return {
            "current_price": current,
            "avg_price": avg_price,
            "min_price": min_price,
            "max_price": max_price,
            "readings_count": len(prices),
        }
