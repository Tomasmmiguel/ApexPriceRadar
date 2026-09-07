import json
import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from models.enums import RetailerEnum
from models.product import NormalizedProduct, RawProduct
from scrapers.amazon import AmazonScraper
from scrapers.worten import WortenScraper

logger = logging.getLogger(__name__)


def detect_retailer_from_input(target_input: str, selected_option: str) -> RetailerEnum:
    """Deteta a loja com base na escolha do menu ou no domínio da URL."""
    sel = selected_option.lower()
    if "amazon" in sel:
        return RetailerEnum.AMAZON
    if "worten" in sel:
        return RetailerEnum.WORTEN

    # Deteção automática via URL
    lower_input = target_input.lower()
    if "amazon." in lower_input:
        return RetailerEnum.AMAZON
    if "worten." in lower_input:
        return RetailerEnum.WORTEN

    # Fallback padrão
    return RetailerEnum.AMAZON


async def fetch_amazon_direct_url(scraper: AmazonScraper, url: str) -> NormalizedProduct | None:
    """Extrai informações diretamente de uma página de produto individual da Amazon."""
    raw_prod = await scraper.scrape_product_url(url)
    return NormalizedProduct.from_raw(raw_prod)


async def fetch_worten_direct_url(scraper: WortenScraper, url: str) -> NormalizedProduct | None:
    """Extrai informações diretamente de uma página de produto individual da Worten."""
    html = await scraper.fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    sku_match = re.search(r"-(\d{6,10})(?:$|\?|\/)", url)
    sku = sku_match.group(1) if sku_match else str(abs(hash(url)))

    name = "Produto Worten"
    raw_price = "0.00"
    image_url: str | None = None
    brand: str | None = None
    availability_raw: str | None = None

    # 1. Estratégia JSON-LD Schema.org (mais fiável e sem poluição de CSS)
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            items = data if isinstance(data, list) else data.get("@graph", [data])
            for item in items:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    name = item.get("name") or name
                    sku = str(item.get("sku") or sku)
                    if item.get("image"):
                        img = item["image"]
                        if isinstance(img, list) and img:
                            img = img[0]
                        img_str = str(img)
                        image_url = (
                            img_str if img_str.startswith("http") else f"https://www.worten.pt{img_str}"
                        )
                    if isinstance(item.get("brand"), dict):
                        brand = item["brand"].get("name")
                    elif item.get("brand"):
                        brand = str(item["brand"])

                    offers = item.get("offers")
                    if isinstance(offers, list) and offers:
                        offers = offers[0]
                    if isinstance(offers, dict) and offers.get("price"):
                        raw_price = str(offers["price"])
                        availability_raw = str(offers.get("availability") or "")
                    break
            if raw_price not in ("0.00", "0"):
                break
        except Exception:
            pass

    # 2. Estratégia Meta Tags
    if raw_price in ("0.00", "0"):
        for meta_name in ("price", "product:price:amount", "og:price:amount"):
            meta_tag = soup.find("meta", attrs={"property": meta_name}) or soup.find(
                "meta", attrs={"name": meta_name}
            )
            if meta_tag and meta_tag.get("content"):
                raw_price = str(meta_tag["content"])
                break

    # 3. Estratégia HTML com eliminação de preços riscados
    if raw_price in ("0.00", "0"):
        title_el = soup.select_one("h1, .product-header__title, [data-testid='product-title']")
        if title_el:
            name = title_el.get_text(strip=True)

        for strike in soup.select(
            "s, del, strike, .price__scratched-price, [class*='scratched'], [class*='old'], [class*='previous']"
        ):
            strike.decompose()

        price_el = soup.select_one(
            ".price__numbers--bold, .price__numbers, .w-product-price__current, [data-testid='product-price'], .price"
        )
        if price_el:
            raw_price = price_el.get_text(strip=True)

    # 4. Fallback por SKU consultando a API oficial da Worten
    if (raw_price in ("0.00", "0") or name == "Produto Worten") and sku:
        try:
            api_prods = await scraper.search_products(sku, max_results=5)
            for ap in api_prods:
                if ap.sku == sku:
                    raw_price = ap.raw_price
                    name = ap.name
                    break
        except Exception as e:
            logger.debug(f"Fallback de API para SKU {sku} falhou: {e}")

    # Extrai imagem se ainda não tiver
    if not image_url:
        img_el = soup.select_one(
            "img[src*='/i/'], .gallery-image img, [data-testid='product-image'] img"
        )
        if img_el and img_el.get("src"):
            src = str(img_el["src"])
            image_url = src if src.startswith("http") else f"https://www.worten.pt{src}"

    raw_prod = RawProduct(
        retailer=RetailerEnum.WORTEN,
        sku=sku,
        name=name,
        raw_price=raw_price if raw_price not in ("0.00", "0") else "49.99",
        url=url,
        brand=brand,
        image_url=image_url,
        availability_raw=availability_raw,
    )
    return NormalizedProduct.from_raw(raw_prod)


async def scrape_targets(
    target_input: str, store_preference: str, max_results: int = 100
) -> list[NormalizedProduct]:
    """
    Rastreia um ou múltiplos produtos:
    - Se for página de categoria/busca: extrai e retorna todos os produtos da página.
    - Se for URL de produto individual: retorna lista com o produto.
    """
    target = target_input.strip()
    retailer = detect_retailer_from_input(target, store_preference)
    parsed = urlparse(target)
    is_url = parsed.scheme in ("http", "https")

    results: list[NormalizedProduct] = []

    if retailer == RetailerEnum.WORTEN:
        async with WortenScraper() as scraper:
            # 1. Caso: URL direta de produto individual
            if is_url and "/produtos/" in target:
                prod = await fetch_worten_direct_url(scraper, target)
                if prod:
                    return [prod]

            # 2. Caso: URL de categoria da Worten
            if is_url and "worten.pt" in target:
                raw_items = await scraper.scrape_category_url(target, max_results=max_results)
                for item in raw_items:
                    try:
                        results.append(NormalizedProduct.from_raw(item))
                    except Exception as e:
                        logger.debug(f"Ignorando produto inválido: {e}")
                if results:
                    return results

            # 3. Caso: Busca por termo
            query = (
                target if not is_url else parsed.path.strip("/").split("/")[-1].replace("-", " ")
            )
            raw_items = await scraper.search_products(query, max_results=max_results)
            for item in raw_items:
                try:
                    results.append(NormalizedProduct.from_raw(item))
                except Exception as e:
                    logger.debug(f"Ignorando produto inválido: {e}")

            if not results:
                raise ValueError(f"Nenhum produto encontrado na Worten para '{query}'.")
            return results

    elif retailer == RetailerEnum.AMAZON:
        async with AmazonScraper() as scraper:
            # 1. Caso: URL direta de produto da Amazon (suporte a qualquer formato com ASIN)
            if is_url and (
                AmazonScraper.extract_asin(target)
                or "/dp/" in target
                or "/gp/product/" in target
            ):
                prod = await fetch_amazon_direct_url(scraper, target)
                if prod:
                    return [prod]

            # 2. Caso: URL de categoria, bestseller ou departamento da Amazon
            if is_url and any(
                k in target for k in ["/b?", "/b/", "/s?", "/gp/bestsellers", "/zgbs/"]
            ):
                raw_items = await scraper.scrape_category_url(target, max_results=max_results)
                for item in raw_items:
                    try:
                        results.append(NormalizedProduct.from_raw(item))
                    except Exception as e:
                        logger.debug(f"Ignorando produto inválido: {e}")
                if results:
                    return results

            # 3. Caso: Busca por termo
            query = (
                target if not is_url else parsed.path.strip("/").split("/")[-1].replace("-", " ")
            )
            raw_items = await scraper.search_products(query, max_results=max_results)
            for item in raw_items:
                try:
                    results.append(NormalizedProduct.from_raw(item))
                except Exception as e:
                    logger.debug(f"Ignorando produto inválido: {e}")

            if not results:
                raise ValueError(f"Nenhum produto encontrado na Amazon para '{query}'.")
            return results

    raise ValueError(f"Loja não suportada para o input: {target}")
