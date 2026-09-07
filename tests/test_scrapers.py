import httpx
import pytest
import respx

from scrapers.amazon import AmazonScraper
from scrapers.worten import WortenScraper


@pytest.mark.asyncio
@respx.mock
async def test_worten_scraper_parses_next_data():
    mock_html = """
    <!DOCTYPE html>
    <html>
      <head><title>Worten Test</title></head>
      <body>
        <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "products": [
                {
                  "sku": "W-998877",
                  "name": "PlayStation 5 Digital Edition",
                  "price": "399.99 €",
                  "url": "/produtos/ps5-digital",
                  "category": "consoles",
                  "availability": "Em stock"
                }
              ]
            }
          }
        }
        </script>
      </body>
    </html>
    """
    respx.get("https://www.worten.pt/search?query=PlayStation").mock(
        return_value=httpx.Response(200, text=mock_html)
    )

    scraper = WortenScraper(base_url="https://www.worten.pt", min_delay=0.0, max_delay=0.0)
    products = await scraper.search_products("PlayStation")
    await scraper.close()

    assert len(products) == 1
    assert products[0].sku == "W-998877"
    assert products[0].name == "PlayStation 5 Digital Edition"
    assert products[0].raw_price == "399.99 €"


@pytest.mark.asyncio
@respx.mock
async def test_amazon_scraper_parses_html_cards():
    mock_html = """
    <html>
      <body>
        <div data-component-type="s-search-result" data-asin="B09G9FPHP6">
          <h2><a href="/dp/B09G9FPHP6"><span>Apple iPad 10.2 Wi-Fi 64GB</span></a></h2>
          <span class="a-price"><span class="a-offscreen">349,00 €</span></span>
        </div>
      </body>
    </html>
    """
    respx.get("https://www.amazon.es/s?k=iPad").mock(
        return_value=httpx.Response(200, text=mock_html)
    )

    scraper = AmazonScraper(base_url="https://www.amazon.es", min_delay=0.0, max_delay=0.0)
    products = await scraper.search_products("iPad")
    await scraper.close()

    assert len(products) == 1
    assert products[0].sku == "B09G9FPHP6"
    assert products[0].name == "Apple iPad 10.2 Wi-Fi 64GB"
    assert products[0].raw_price == "349,00 €"


def test_amazon_asin_and_brand_helpers():
    # Teste de extração de ASIN
    assert AmazonScraper.extract_asin("https://www.amazon.es/dp/B07FNHV4MW") == "B07FNHV4MW"
    assert AmazonScraper.extract_asin("https://www.amazon.com/gp/product/B09G9FPHP6?ref=123") == "B09G9FPHP6"
    assert AmazonScraper.extract_asin("https://www.amazon.de/d/B07FNHV4MW/") == "B07FNHV4MW"

    # Teste de limpeza de marca
    assert AmazonScraper.clean_brand("Visite a Loja da Logitech (em Espanhol)") == "Logitech"
    assert AmazonScraper.clean_brand("Visit the Apple Store") == "Apple"
    assert AmazonScraper.clean_brand("Marca: Sony") == "Sony"


@pytest.mark.asyncio
@respx.mock
async def test_amazon_scrape_product_url():
    mock_product_html = """
    <html>
      <head><title>Logitech MX Vertical</title></head>
      <body>
        <span id="productTitle">Logitech MX Vertical Wireless Mouse</span>
        <a id="bylineInfo">Visite a Loja da Logitech</a>
        <div id="corePriceDisplay_desktop_feature_div">
          <span class="priceToPay"><span class="a-offscreen">89,90 €</span></span>
        </div>
        <img id="landingImage" data-a-dynamic-image='{"https://img.jpg":[800,800]}' src="https://img_thumb.jpg" />
        <div id="availability"><span>Em stock</span></div>
      </body>
    </html>
    """
    respx.get("https://www.amazon.es/dp/B07FNHV4MW").mock(
        return_value=httpx.Response(200, text=mock_product_html)
    )

    scraper = AmazonScraper(base_url="https://www.amazon.es", min_delay=0.0, max_delay=0.0)
    product = await scraper.scrape_product_url("https://www.amazon.es/dp/B07FNHV4MW")
    await scraper.close()

    assert product.sku == "B07FNHV4MW"
    assert product.name == "Logitech MX Vertical Wireless Mouse"
    assert product.raw_price == "89,90 €"
    assert product.brand == "Logitech"
    assert product.image_url == "https://img.jpg"
    assert product.availability_raw == "Em stock"
