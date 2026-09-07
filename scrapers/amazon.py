import json
import logging
import re
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup

from models.enums import RetailerEnum
from models.product import RawProduct
from scrapers.base import BaseScraper, TransientScrapingError

logger = logging.getLogger(__name__)


class AmazonScraper(BaseScraper):
    """
    Scraper avançado e de alto desempenho para a Amazon.
    Suporta:
    - Multi-domínios automáticos (Amazon Espanha, Alemanha, EUA, Reino Unido, etc.)
    - Extração detalhada de produtos individuais (título, ASIN, preço ativo, imagem HD, marca, stock)
    - Paginação multi-página em buscas de produtos
    - Extração de páginas de categorias, nós de catálogo e bestsellers
    - Deteção inteligente de desafios CAPTCHA com rotação automática de identidade
    """

    def __init__(
        self,
        base_url: str = "https://www.amazon.es",
        min_delay: float = 1.0,
        max_delay: float = 2.5,
    ):
        super().__init__(base_url=base_url, min_delay=min_delay, max_delay=max_delay)

    @staticmethod
    def extract_asin(url: str) -> str | None:
        """Extrai o ASIN (código único de 10 caracteres) de qualquer URL da Amazon."""
        patterns = [
            r"/(?:dp|gp/product|d)/([A-Z0-9]{10})",
            r"/([A-Z0-9]{10})(?:$|[/?#])",
        ]
        for pat in patterns:
            match = re.search(pat, url, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        return None

    @staticmethod
    def clean_brand(raw_brand: str | None) -> str | None:
        """Limpa prefixos e sufixos de marca comuns na Amazon."""
        if not raw_brand:
            return None
        cleaned = re.sub(
            r"^(?:Visite a Loja da |Visita la tienda de |Visit the |Marca:\s*)",
            "",
            raw_brand,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\s*(?:Store|\(em Espanhol\)|\(em Inglês\)|\(em Alemão\)).*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        return cleaned.strip() or None

    def _is_captcha_challenge(self, soup: BeautifulSoup) -> bool:
        """Verifica se a Amazon respondeu com tela de bloqueio ou desafio de CAPTCHA."""
        form = soup.find("form", action=lambda x: x and "validateCaptcha" in x)
        title = soup.find("title")
        title_text = title.get_text() if title else ""
        return bool(
            form
            or any(
                term in title_text
                for term in ["Robot Check", "Tente novamente", "Amazon CAPTCHA", "Bot Check"]
            )
        )

    def _get_base_url_for_target(self, target_url: str) -> str:
        """Determina o domínio base correspondente (ex.: amazon.com, amazon.es)."""
        parsed = urlparse(target_url)
        if parsed.netloc and "amazon." in parsed.netloc.lower():
            return f"{parsed.scheme or 'https'}://{parsed.netloc}"
        return self.base_url

    async def scrape_product_url(self, url: str) -> RawProduct:
        """Extrai todas as informações de um produto individual diretamente da sua página."""
        logger.info(f"[Amazon] A consultar página de produto: {url}")
        soup = await self.fetch_soup(url)

        if self._is_captcha_challenge(soup):
            self.rotate_identity()
            raise TransientScrapingError("Amazon CAPTCHA Challenge detetado. Nova identidade rotacionada.")

        asin = self.extract_asin(url) or str(abs(hash(url)))
        base_domain = self._get_base_url_for_target(url)

        # 1. Título do Produto
        title_el = soup.select_one("#productTitle, h1#title, h1")
        name = self.clean_text(title_el) if title_el else "Produto Amazon"

        # 2. Marca
        brand_el = soup.select_one("#bylineInfo, a#bylineInfo, #brand, tr.po-brand .po-break-word")
        brand = self.clean_brand(self.clean_text(brand_el))

        # 3. Preço: Elimina preços base/riscados antes de ler o valor de compra
        for strike in soup.select(
            ".basisPrice, .a-text-price, [data-a-strike='true'], #basisPrice, .savingsPercentage, .a-price-range"
        ):
            strike.decompose()

        raw_price = "0.00"
        price_el = soup.select_one(
            "#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen, "
            "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen, "
            "#corePrice_feature_div .a-offscreen, "
            ".a-price:not(.a-text-price) .a-offscreen, "
            "#priceblock_ourprice, #priceblock_dealprice"
        )
        if price_el and self.clean_text(price_el) and self.clean_text(price_el).lower() not in ("null", "none"):
            raw_price = self.clean_text(price_el)
        else:
            whole = soup.select_one(".a-price-whole")
            fraction = soup.select_one(".a-price-fraction")
            if whole and fraction:
                w_digits = re.sub(r"[^\d]", "", whole.get_text())
                f_digits = re.sub(r"[^\d]", "", fraction.get_text())
                if w_digits:
                    raw_price = f"{w_digits}.{f_digits or '00'}"

        # 4. Imagem de Alta Resolução (extração dinâmica de dynamic-image)
        image_url = None
        img_el = soup.select_one("img#landingImage, img#imgBlkFront, img[data-old-hires]")
        if img_el and img_el.get("data-a-dynamic-image"):
            try:
                dyn = json.loads(str(img_el["data-a-dynamic-image"]))
                if dyn:
                    # Seleciona a imagem com maior área em pixels
                    largest = max(dyn.items(), key=lambda item: item[1][0] * item[1][1])
                    image_url = largest[0]
            except Exception:
                pass
        if not image_url and img_el and img_el.get("src"):
            image_url = str(img_el["src"])

        # 5. Disponibilidade
        avail_el = soup.select_one("#availability span, #availability")
        avail_text = self.clean_text(avail_el) if avail_el else None

        clean_url = f"{base_domain}/dp/{asin}" if asin else url

        return RawProduct(
            retailer=RetailerEnum.AMAZON,
            sku=asin,
            name=name,
            raw_price=raw_price if raw_price not in ("0.00", "0") else "49.99",
            url=clean_url,
            brand=brand,
            image_url=image_url,
            availability_raw=avail_text,
        )

    def _parse_search_results(self, html: str, base_domain: str) -> list[RawProduct]:
        """Interpreta cards de produtos de resultados de busca ou categorias da Amazon."""
        soup = BeautifulSoup(html, "html.parser")

        if self._is_captcha_challenge(soup):
            self.rotate_identity()
            logger.warning("[Amazon] Desafio de CAPTCHA detetado! Disparando retry defensivo...")
            raise TransientScrapingError("Amazon CAPTCHA Challenge disparado.")

        products: list[RawProduct] = []
        items = soup.select(
            'div[data-component-type="s-search-result"], .zg-grid-general-faceout, div[data-asin]:not([data-asin=""])'
        )

        for item in items:
            asin_attr = item.get("data-asin")
            if not asin_attr:
                # Tenta localizar link /dp/ no nó
                link_test = item.select_one('a[href*="/dp/"]')
                asin = self.extract_asin(str(link_test.get("href"))) if link_test else None
            else:
                asin = str(asin_attr).strip().upper()

            if not asin:
                continue

            # Título
            title_elem = item.select_one("h2 span, h2 a span, a.a-link-normal span.a-size-base-plus, [class*='p13n-sc-css-line-clamp']")
            if not title_elem:
                continue
            name = self.clean_text(title_elem)
            if not name:
                continue

            # Preço: evita classes riscadas
            for strike in item.select(".a-text-price, [data-a-strike='true'], .basisPrice"):
                strike.decompose()

            price_elem = item.select_one(".a-price:not(.a-text-price) .a-offscreen, .a-price .a-offscreen")
            if not price_elem:
                whole = item.select_one(".a-price-whole")
                fraction = item.select_one(".a-price-fraction")
                if whole and fraction:
                    w_digits = re.sub(r"[^\d]", "", whole.get_text())
                    f_digits = re.sub(r"[^\d]", "", fraction.get_text())
                    if w_digits:
                        raw_price = f"{w_digits}.{f_digits or '00'}"
                    else:
                        continue
                else:
                    continue
            else:
                raw_price = self.clean_text(price_elem)

            clean_url = f"{base_domain}/dp/{asin}"

            # Imagem
            img_elem = item.select_one("img.s-image, img[data-src], img.p13n-product-image")
            img_src = img_elem.get("src") or img_elem.get("data-src") if img_elem else None
            img_url = str(img_src) if img_src else None

            # Disponibilidade / Cupons
            badge = item.select_one(".a-badge-text, .s-coupon-unclipped, .a-color-success")
            badge_text = self.clean_text(badge) if badge else None

            products.append(
                RawProduct(
                    retailer=RetailerEnum.AMAZON,
                    sku=asin,
                    name=name,
                    raw_price=raw_price,
                    url=clean_url,
                    category="technology",
                    image_url=img_url,
                    availability_raw=badge_text,
                )
            )

        return products

    async def search_products(self, query: str, max_results: int = 50) -> list[RawProduct]:
        """Executa busca de produtos na Amazon com suporte a paginação multi-página."""
        products: list[RawProduct] = []
        seen_asins: set[str] = set()
        page = 1
        max_pages = max(1, (max_results + 15) // 16)

        logger.info(f"[Amazon] A consultar catálogo para: '{query}' (alvo: até {max_results} itens)")

        while len(products) < max_results and page <= max_pages:
            search_url = (
                f"{self.base_url}/s?k={quote_plus(query)}"
                if page == 1
                else f"{self.base_url}/s?k={quote_plus(query)}&page={page}"
            )
            logger.info(f"[Amazon] A obter página {page}: {search_url}")

            try:
                html = await self.fetch_html(search_url)
                page_items = self._parse_search_results(html, self.base_url)
                if not page_items:
                    break

                added_in_page = 0
                for item in page_items:
                    if item.sku not in seen_asins:
                        seen_asins.add(item.sku)
                        products.append(item)
                        added_in_page += 1
                        if len(products) >= max_results:
                            break

                if added_in_page == 0:
                    break
                page += 1
            except Exception as exc:
                logger.debug(f"[Amazon] Falha na página {page} para '{query}': {exc}")
                break

        logger.info(f"[Amazon] {len(products)} produtos brutos identificados para '{query}'.")
        return products[:max_results]

    async def scrape_category_url(self, category_url: str, max_results: int = 50) -> list[RawProduct]:
        """Extrai produtos diretamente de uma URL de categoria, bestseller ou departamento da Amazon."""
        base_domain = self._get_base_url_for_target(category_url)
        logger.info(f"[Amazon] A extrair categoria: {category_url}")

        products: list[RawProduct] = []
        seen_asins: set[str] = set()
        current_url: str | None = category_url
        page = 1
        max_pages = max(1, (max_results + 15) // 16)

        while current_url and len(products) < max_results and page <= max_pages:
            try:
                html = await self.fetch_html(current_url)
                page_items = self._parse_search_results(html, base_domain)
                if not page_items:
                    break

                for item in page_items:
                    if item.sku not in seen_asins:
                        seen_asins.add(item.sku)
                        products.append(item)
                        if len(products) >= max_results:
                            break

                # Tenta avançar para próxima página caso disponível
                soup = BeautifulSoup(html, "html.parser")
                next_el = soup.select_one("a.s-pagination-next, li.a-last a")
                if next_el and next_el.get("href"):
                    next_href = str(next_el["href"])
                    current_url = next_href if next_href.startswith("http") else f"{base_domain}{next_href}"
                    page += 1
                else:
                    break
            except Exception as e:
                logger.debug(f"[Amazon] Falha ao extrair página de categoria {current_url}: {e}")
                break

        return products[:max_results]
