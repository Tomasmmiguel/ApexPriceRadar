import json
import logging
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup

from models.enums import RetailerEnum
from models.product import RawProduct
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class WortenScraper(BaseScraper):
    """
    Scraper de alto desempenho para Worten (Portugal).
    Utiliza prioritariamente a API interna oficial (/worten-api/search-products),
    com fallback para __NEXT_DATA__ legado e seletores HTML defensivos.
    """

    def __init__(
        self,
        base_url: str = "https://www.worten.pt",
        min_delay: float = 0.5,
        max_delay: float = 1.5,
    ):
        super().__init__(base_url=base_url, min_delay=min_delay, max_delay=max_delay)

    async def _fetch_from_worten_api(
        self, query: str | None = None, contexts: list[str] | None = None, max_results: int = 100
    ) -> list[RawProduct]:
        """Consulta a API interna de catálogo e pesquisa da Worten com suporte a paginação."""
        api_url = f"{self.base_url}/worten-api/search-products"

        custom_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{self.base_url}/",
        }

        products: list[RawProduct] = []
        seen_skus: set[str] = set()
        page_number = 1
        max_pages = max(1, (max_results + 23) // 24)

        while len(products) < max_results and page_number <= max_pages:
            payload: dict[str, object] = {"params": {"pageNumber": page_number}}
            if contexts:
                payload["contexts"] = contexts
            elif query:
                payload["query"] = query
            else:
                return []

            try:
                await self._enforce_rate_limit()
                resp = await self.client.post(
                    api_url,
                    headers=custom_headers,
                    json=payload,
                    timeout=15.0,
                )
                if resp.status_code != 200:
                    logger.debug(
                        f"Worten API retornou HTTP {resp.status_code} na página {page_number}"
                    )
                    break

                data = resp.json()
                details = data.get("detailsResponse", {})
                prods_data = details.get("productsData", {}).get("products", [])
                offers_data = details.get("offersData", {}).get("offers", [])
                canonicals = details.get("productsCanonicalsData", {}).get("web_items", [])
                search_resp = data.get("searchResponse", {})

                if not prods_data:
                    break

                # Mapeamento de ofertas por offer_id
                offers_map = {}
                for off in offers_data:
                    off_id = off.get("offer_id")
                    if off_id:
                        offers_map[off_id] = off

                # Mapeamento de URLs canónicas por id (webitem_id)
                canon_map = {}
                for c in canonicals:
                    c_id = c.get("id")
                    c_url = c.get("url")
                    if c_id and c_url:
                        canon_map[c_id] = c_url

                for p in prods_data:
                    meta = p.get("meta", {})
                    refs = meta.get("refs", {})
                    sku = str(refs.get("sku") or refs.get("webitem_id") or p.get("id") or "")
                    if not sku or sku in seen_skus:
                        continue

                    webitem_id = refs.get("webitem_id")
                    url_slug = canon_map.get(webitem_id, "")

                    # Extração do nome com múltiplos níveis de resiliência
                    properties = p.get("properties") or {}
                    text_props = properties.get("text") if isinstance(properties, dict) else {}
                    name = ""
                    if isinstance(text_props, dict):
                        name = str(text_props.get("name") or text_props.get("title") or "").strip()
                    if not name:
                        name = str(p.get("name") or p.get("title") or "").strip()
                    if not name and isinstance(meta, dict):
                        name = str(meta.get("title") or meta.get("name") or "").strip()
                    if not name and url_slug:
                        clean_slug = url_slug.strip("/").split("/")[-1].replace("-", " ")
                        name = clean_slug.title()
                    if not name:
                        name = f"Produto Worten {sku}"

                    woffer_id = (
                        p.get("woffer", {}).get("offer_id")
                        if isinstance(p.get("woffer"), dict)
                        else None
                    )
                    if not woffer_id and isinstance(p.get("woffers"), list):
                        for w in p["woffers"]:
                            if isinstance(w, dict) and w.get("offer_id") in offers_map:
                                woffer_id = w.get("offer_id")
                                break

                    offer = offers_map.get(woffer_id) if woffer_id else None

                    raw_price = "0.00"
                    if offer and isinstance(offer.get("price"), dict):
                        raw_price = str(
                            offer["price"].get("final") or offer["price"].get("original") or "0.00"
                        )
                    elif isinstance(p.get("woffer"), dict) and p["woffer"].get("second_offer_price"):
                        raw_price = str(p["woffer"]["second_offer_price"])

                    if url_slug:
                        url = (
                            f"{self.base_url}/{url_slug.lstrip('/')}"
                            if not url_slug.startswith("http")
                            else url_slug
                        )
                    else:
                        url = f"{self.base_url}/produtos/{sku}"

                    if sku:
                        seen_skus.add(sku)
                        products.append(
                            RawProduct(
                                retailer=RetailerEnum.WORTEN,
                                sku=sku,
                                name=name,
                                raw_price=raw_price,
                                url=url,
                                category="technology",
                            )
                        )
                        if len(products) >= max_results:
                            break

                has_next = search_resp.get("hasNextPage", False)
                if not has_next:
                    break
                page_number += 1
            except Exception as exc:
                logger.debug(f"Falha na consulta à Worten API na página {page_number}: {exc}")
                break

        return products[:max_results]

    def _extract_from_next_data(self, html: str) -> list[RawProduct]:
        """Tenta extrair produtos a partir do JSON serializado pelo Next.js (__NEXT_DATA__)."""
        soup = BeautifulSoup(html, "html.parser")
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if not script_tag or not script_tag.string:
            return []

        products: list[RawProduct] = []
        try:
            data = json.loads(script_tag.string)
            page_props = data.get("props", {}).get("pageProps", {})

            items = (
                page_props.get("products", [])
                or page_props.get("initialData", {}).get("products", [])
                or page_props.get("catalog", {}).get("products", [])
            )
            if not items and "results" in page_props:
                items = page_props["results"]

            for item in items:
                sku = str(item.get("sku") or item.get("id") or item.get("code") or "")
                name = item.get("name") or item.get("title") or ""
                price_val = (
                    item.get("price")
                    or item.get("currentPrice")
                    or item.get("salePrice")
                    or item.get("finalPrice")
                )
                url_slug = item.get("url") or item.get("slug") or ""
                if not url_slug.startswith("http"):
                    url = f"{self.base_url}/{url_slug.lstrip('/')}"
                else:
                    url = url_slug

                if sku and name and price_val:
                    products.append(
                        RawProduct(
                            retailer=RetailerEnum.WORTEN,
                            sku=sku,
                            name=name,
                            raw_price=str(price_val),
                            url=url,
                            category=item.get("category", "technology"),
                            brand=item.get("brand"),
                            image_url=item.get("image") or item.get("imageUrl"),
                            availability_raw=item.get("availability"),
                        )
                    )
        except Exception as exc:
            logger.debug(f"Falha ao interpretar __NEXT_DATA__ da Worten: {exc}")

        return products

    def _extract_from_html_fallback(self, html: str) -> list[RawProduct]:
        """Fallback tradicional caso a API interna ou o JSON não estejam disponíveis."""
        soup = BeautifulSoup(html, "html.parser")
        products: list[RawProduct] = []

        cards = soup.select("article, .product-card, [data-product-sku], .w-product-card")
        for card in cards:
            sku = card.get("data-product-sku") or card.get("data-sku") or card.get("id")
            for strike in card.select("s, del, strike, .price__scratched-price, [class*='scratched'], [class*='old']"):
                strike.decompose()

            name_el = card.select_one(
                "h3, .product-card__title, [data-testid='product-title'], a.product-name"
            )
            price_el = card.select_one(
                ".price__numbers--bold, .price__numbers, [data-testid='product-price'], .w-product-price__current, .price, span.text-primary"
            )
            link_el = card.select_one("a[href]")

            if name_el and price_el:
                name = name_el.get_text(strip=True)
                raw_price = price_el.get_text(strip=True)
                href_attr = link_el.get("href") if link_el else None
                href = str(href_attr) if href_attr else ""
                url = href if href.startswith("http") else f"{self.base_url}/{href.lstrip('/')}"

                if not sku and "/p/" in url:
                    sku = url.split("/p/")[-1].split("?")[0].strip("/")
                elif not sku:
                    sku = str(abs(hash(name)))

                products.append(
                    RawProduct(
                        retailer=RetailerEnum.WORTEN,
                        sku=str(sku),
                        name=name,
                        raw_price=raw_price,
                        url=url,
                        category="technology",
                    )
                )

        return products

    async def search_products(self, query: str, max_results: int = 100) -> list[RawProduct]:
        """Busca produtos na Worten usando rotas de pesquisa e a API oficial interna."""
        logger.info(f"[Worten] A consultar catálogo para: '{query}'")

        # 1. Tenta API oficial interna
        products = await self._fetch_from_worten_api(query=query, max_results=max_results)
        if products:
            logger.info(f"[Worten] {len(products)} produtos obtidos via API oficial.")
            return products

        # 2. Fallback via página de busca
        search_url = f"{self.base_url}/search?query={quote_plus(query)}"
        try:
            html = await self.fetch_html(search_url)
            products = self._extract_from_next_data(html)
            if not products:
                products = self._extract_from_html_fallback(html)
        except Exception as e:
            logger.debug(f"[Worten] Falha no fallback HTML: {e}")

        logger.info(f"[Worten] {len(products)} produtos brutos identificados para '{query}'.")
        return products[:max_results]

    async def scrape_category_url(
        self, category_url: str, max_results: int = 100
    ) -> list[RawProduct]:
        """Extrai todos os produtos de uma página de categoria da Worten."""
        path = urlparse(category_url).path.strip("/")
        segments = [s for s in path.split("/") if s]

        # Extrai termo semântico (ex.: 'monitores' -> 'monitor')
        target_term = segments[-1].replace("-", " ") if segments else "tecnologia"
        if target_term.endswith("es"):
            target_term = target_term[:-2]
        elif target_term.endswith("s") and not target_term.endswith("ss"):
            target_term = target_term[:-1]

        logger.info(
            f"[Worten] A extrair produtos reais para a categoria '{path}' (termo: '{target_term}')..."
        )

        # 1. Consulta prioritária por termo semântico da categoria na API oficial
        products = await self._fetch_from_worten_api(query=target_term, max_results=max_results)

        # 2. Se vazio, tenta por contextos de URL
        if not products:
            products = await self._fetch_from_worten_api(contexts=segments, max_results=max_results)

        return products[:max_results]
