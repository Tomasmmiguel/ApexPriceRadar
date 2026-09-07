import argparse
import asyncio
import logging

from config.settings import get_settings
from database.connection import get_session, init_db
from database.repository import ProductRepository
from models.product import RawProduct
from notifications.reporter import ExcelReportGenerator
from notifications.telegram_bot import TelegramNotifier
from pipelines.cleaning import clean_and_normalize_raw_batch
from pipelines.metrics import compute_market_intelligence_signals
from scrapers.amazon import AmazonScraper
from scrapers.worten import WortenScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ApexPriceEngine")


async def run_pipeline(
    queries: list[str],
    retailers: list[str],
    generate_excel: bool = True,
    dispatch_alerts: bool = True,
) -> None:
    settings = get_settings()
    logger.info("=== Iniciando ApexPrice Engine Pipeline ===")
    logger.info(f"Ambiente: {settings.ENVIRONMENT} | Consultas: {queries}")

    # 1. Inicializa banco de dados
    await init_db()
    logger.info("Base de dados relacional inicializada e verificada.")

    # 2. Executa Extração com os Scrapers Configurados
    raw_products: list[RawProduct] = []

    for query in queries:
        if "worten" in retailers:
            try:
                async with WortenScraper() as scraper:
                    items = await scraper.search_products(query, max_results=10)
                    raw_products.extend(items)
            except Exception as e:
                logger.error(f"Erro na extração da Worten para '{query}': {e}")

        if "amazon" in retailers:
            try:
                async with AmazonScraper() as scraper:
                    items = await scraper.search_products(query, max_results=10)
                    raw_products.extend(items)
            except Exception as e:
                logger.error(f"Erro na extração da Amazon para '{query}': {e}")

    logger.info(f"Total de produtos brutos recolhidos: {len(raw_products)}")

    # 3. Pipeline de Limpeza, Normalização e Deduplicação
    normalized_batch = clean_and_normalize_raw_batch(raw_products)
    logger.info(f"Total de produtos após validação e deduplicação: {len(normalized_batch)}")

    if not normalized_batch:
        logger.warning("Nenhum produto válido após normalização. Encerrando pipeline.")
        return

    # 4. Persistência Idempotente no Banco de Dados
    async for session in get_session():
        repo = ProductRepository(session)
        for prod in normalized_batch:
            await repo.save_normalized_product(prod)
        await session.commit()
        logger.info("Lote de produtos persistido no banco com sucesso.")

        # 5. Extração do Histórico e Cálculo de Inteligência de Mercado
        history_df = await repo.get_price_history_dataframe()

    if history_df.empty:
        logger.warning("Histórico de preços indisponível.")
        return

    signals_df = compute_market_intelligence_signals(
        history_df, min_discount_threshold=settings.MIN_DISCOUNT_PERCENT_ALERT
    )
    logger.info(f"Sinais de mercado calculados para {len(signals_df)} produtos únicos.")

    # 6. Avaliação de Gatilhos e Disparo de Alertas
    if dispatch_alerts:
        notifier = TelegramNotifier(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            chat_id=settings.TELEGRAM_CHAT_ID,
            enabled=settings.TELEGRAM_ENABLED,
        )

        deals = signals_df[signals_df["is_deal_alert"]]
        logger.info(f"Oportunidades que atendem ao critério de alerta: {len(deals)}")

        for _, deal in deals.iterrows():
            await notifier.send_deal_alert(
                product_name=str(deal["name"]),
                retailer=str(deal["retailer"]),
                current_price=float(deal["price"]),
                avg_price=float(deal["historical_avg"]),
                discount_pct=float(deal["discount_vs_avg_pct"]),
                is_all_time_low=bool(deal["is_all_time_low"]),
                url=str(deal["url"]),
            )

    # 7. Geração de Relatório Executivo Excel
    if generate_excel:
        reporter = ExcelReportGenerator(output_dir=settings.REPORTS_DIR)
        report_path = reporter.generate_intelligence_report(signals_df)
        logger.info(f"Relatório gerado com sucesso: {report_path}")

    # 8. Síntese no Terminal
    print("\n" + "=" * 90)
    print("RESUMO DE SINAIS DE PREÇO & INTELIGÊNCIA DE MERCADO (TOP 10)")
    print("=" * 90)
    summary_cols = ["retailer", "sku", "price", "historical_avg", "discount_vs_avg_pct", "name"]
    display_df = signals_df[[c for c in summary_cols if c in signals_df.columns]].head(10)
    print(display_df.to_string(index=False))
    print("=" * 90 + "\n")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ApexPrice Engine - Production Web Scraping & Market Intelligence CLI"
    )
    parser.add_argument(
        "-q",
        "--query",
        type=str,
        default="PlayStation 5",
        help="Termo de pesquisa para busca de produtos (ex: 'PlayStation 5', 'MacBook')",
    )
    parser.add_argument(
        "-r",
        "--retailer",
        choices=["all", "worten", "amazon"],
        default="all",
        help="Varejista a ser consultado (padrão: all)",
    )
    parser.add_argument(
        "--no-excel",
        action="store_true",
        help="Desativa a exportação do relatório Excel",
    )
    parser.add_argument(
        "--no-alerts",
        action="store_true",
        help="Desativa o envio de alertas",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    retailers = ["worten", "amazon"] if args.retailer == "all" else [args.retailer]
    queries = [q.strip() for q in args.query.split(",") if q.strip()]

    asyncio.run(
        run_pipeline(
            queries=queries,
            retailers=retailers,
            generate_excel=not args.no_excel,
            dispatch_alerts=not args.no_alerts,
        )
    )


if __name__ == "__main__":
    main()
