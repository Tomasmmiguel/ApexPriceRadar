from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ProductRecord(Base):
    """
    Dimensão de Produto.
    Contém a identidade do produto e os metadados fixos.
    """

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    retailer: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="technology")
    url: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relação com séries temporais
    price_records: Mapped[list["PriceRecord"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="PriceRecord.recorded_at.desc()",
    )

    __table_args__ = (
        UniqueConstraint("retailer", "sku", name="uq_products_retailer_sku"),
        Index("ix_retailer_category", "retailer", "category"),
    )


class PriceRecord(Base):
    """
    Tabela de Fato: Histórico de Preços (Série Temporal).
    Nunca sobrescreve; registra a evolução pontual de preços e disponibilidade.
    """

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    availability: Mapped[str] = mapped_column(String(32), default="in_stock", nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    product: Mapped[ProductRecord] = relationship(back_populates="price_records")

    __table_args__ = (Index("ix_price_product_recorded", "product_id", "recorded_at"),)
