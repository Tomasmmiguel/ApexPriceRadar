import logging

import pandas as pd

logger = logging.getLogger(__name__)


def compute_market_intelligence_signals(
    df: pd.DataFrame, min_discount_threshold: float = 10.0
) -> pd.DataFrame:
    """
    Recebe um DataFrame com o histórico de preços:
      ['product_id', 'retailer', 'sku', 'name', 'category', 'url', 'price', 'availability', 'recorded_at']

    Computa:
      - historical_min: Menor preço registado para o produto
      - historical_max: Maior preço registado
      - historical_avg: Média aritmética de preços observados
      - observations_count: Quantidade de leituras registadas
      - discount_vs_avg_pct: Desconto percentual em relação à média histórica
      - is_all_time_low: Se o preço atual iguala ou bate o menor histórico
      - is_deal_alert: Se atinge o limiar mínimo de desconto configurado
    """
    if df.empty:
        return df

    # Assegura conversão de tipos
    df = df.copy()
    df["recorded_at"] = pd.to_datetime(df["recorded_at"])
    df = df.sort_values(by=["product_id", "recorded_at"])

    # 1. Agrupamento por produto para métricas históricas globais
    metrics = (
        df.groupby("product_id")
        .agg(
            historical_min=("price", "min"),
            historical_max=("price", "max"),
            historical_avg=("price", "mean"),
            observations_count=("price", "count"),
        )
        .reset_index()
    )
    metrics["historical_avg"] = metrics["historical_avg"].round(2)

    # 2. Obtém apenas o registo mais recente de cada produto (estado atual)
    latest_df = df.sort_values("recorded_at").groupby("product_id").last().reset_index()

    # 3. Mescla estado atual com métricas históricas
    merged = pd.merge(latest_df, metrics, on="product_id", how="left")

    # 4. Cálculo de sinais analíticos
    merged["discount_vs_avg_pct"] = (
        ((merged["historical_avg"] - merged["price"]) / merged["historical_avg"]) * 100
    ).round(1)

    merged["is_all_time_low"] = merged["price"] <= merged["historical_min"]
    merged["is_deal_alert"] = (merged["discount_vs_avg_pct"] >= min_discount_threshold) & (
        merged["availability"] == "in_stock"
    )

    return merged
