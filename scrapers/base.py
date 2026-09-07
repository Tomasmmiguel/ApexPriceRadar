import asyncio
import json
import logging
import random
import re
from abc import ABC, abstractmethod
from typing import Any, Self

import httpx
from bs4 import BeautifulSoup, Tag
from fake_useragent import UserAgent
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

logger = logging.getLogger(__name__)


class TransientScrapingError(Exception):
    """Exceção levantada para códigos de status ou falhas de rede recuperáveis (incluindo CAPTCHA)."""


class BrowserSessionProfile:
    """
    Mantém uma identidade de navegador consistente durante a sessão de scraping.
    Evita a rotação errática de User-Agent entre requisições da mesma sessão que ativa WAFs.
    """

    def __init__(self, platform: str = "pc") -> None:
        self.platform = platform
        self.rotate()

    def rotate(self) -> None:
        """Gera uma nova identidade de navegador coerente."""
        try:
            ua = UserAgent(platforms=self.platform, browsers=["chrome", "edge"]).random
        except Exception:
            ua = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            )

        self.user_agent = ua
        self.sec_ch_ua = '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"'
        self.sec_ch_ua_mobile = "?0"
        self.sec_ch_ua_platform = '"Windows"'

    def get_headers(self, lang: str = "pt-PT,pt;q=0.9,es-ES;q=0.8,en;q=0.7") -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": lang,
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://www.google.com/",
            "Sec-Ch-Ua": self.sec_ch_ua,
            "Sec-Ch-Ua-Mobile": self.sec_ch_ua_mobile,
            "Sec-Ch-Ua-Platform": self.sec_ch_ua_platform,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }


def get_realistic_headers() -> dict[str, str]:
    """Fallback funcional retrocompatível para cabeçalhos realistas pontuais."""
    return BrowserSessionProfile().get_headers()


class BaseScraper(ABC):
    """
    Classe base assíncrona robusta para web scraping de e-commerce:
    - Identidade de navegador consistente com evasão de fingerprinting.
    - Retry exponencial inteligente com Jitter.
    - Suporte direto a parsing BeautifulSoup e Schema.org JSON-LD.
    - Gestão de rate-limit e pool de conexões HTTP/2.
    """

    def __init__(
        self,
        base_url: str,
        min_delay: float = 1.0,
        max_delay: float = 2.5,
    ):
        self.base_url = base_url.rstrip("/")
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.profile = BrowserSessionProfile()
        self.client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(20.0, connect=10.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )

    def rotate_identity(self) -> None:
        """Gera uma nova identidade de cliente HTTP quando desafiado por anti-bot."""
        self.profile.rotate()
        logger.info(f"[{self.__class__.__name__}] Identidade rotacionada para novo User-Agent.")

    async def _enforce_rate_limit(self) -> None:
        """Aplica um jitter aleatório para evitar padrão robótico previsível."""
        sleep_time = random.uniform(self.min_delay, self.max_delay)
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)

    @retry(
        retry=retry_if_exception_type((TransientScrapingError, httpx.RequestError)),
        wait=wait_random_exponential(multiplier=1.2, min=2, max=25),
        stop=stop_after_attempt(4),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def fetch_html(self, url: str, custom_headers: dict[str, str] | None = None) -> str:
        """Executa requisição GET com evasão de rate-limit e tolerância a falhas transitórias."""
        await self._enforce_rate_limit()

        headers = self.profile.get_headers()
        if custom_headers:
            headers.update(custom_headers)

        try:
            response = await self.client.get(url, headers=headers)

            # Detecta bloqueios temporários ou erros de servidor
            if response.status_code in (429, 500, 502, 503, 504):
                self.rotate_identity()
                raise TransientScrapingError(
                    f"Status transitório HTTP {response.status_code} recebido de {url}"
                )

            response.raise_for_status()
            return response.text

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                self.rotate_identity()
                logger.error(f"Acesso negado (403 Forbidden) em {url}. Possível detecção de bot.")
            raise

    async def fetch_soup(
        self, url: str, custom_headers: dict[str, str] | None = None
    ) -> BeautifulSoup:
        """Descarrega a página e devolve um documento BeautifulSoup pronto a consultar."""
        html = await self.fetch_html(url, custom_headers=custom_headers)
        return BeautifulSoup(html, "html.parser")

    @staticmethod
    def clean_text(text_or_elem: str | Tag | None) -> str:
        """Limpa espaços múltiplos, quebras de linha e caracteres invisíveis de um nó ou string."""
        if text_or_elem is None:
            return ""
        raw = text_or_elem.get_text(strip=True) if isinstance(text_or_elem, Tag) else str(text_or_elem)
        cleaned = raw.replace("\xa0", " ").replace("&nbsp;", " ")
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def extract_json_ld(soup: BeautifulSoup, target_type: str = "Product") -> list[dict[str, Any]]:
        """Extrai todos os objetos de um tipo Schema.org embutidos em tags <script type='application/ld+json'>."""
        matches: list[dict[str, Any]] = []
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else data.get("@graph", [data])
                for item in items:
                    if isinstance(item, dict) and item.get("@type") == target_type:
                        matches.append(item)
            except Exception:
                continue
        return matches

    @staticmethod
    def extract_meta_content(soup: BeautifulSoup, *property_names: str) -> str | None:
        """Busca o atributo 'content' entre várias meta tags candidatas (OpenGraph, itemprop, name)."""
        for prop in property_names:
            meta = (
                soup.find("meta", attrs={"property": prop})
                or soup.find("meta", attrs={"name": prop})
                or soup.find("meta", attrs={"itemprop": prop})
            )
            if meta and meta.get("content"):
                return str(meta["content"]).strip()
        return None

    @abstractmethod
    async def search_products(self, query: str, max_results: int = 10) -> list[Any]:
        """Método de busca padronizado para cada varejista."""
        pass

    async def close(self) -> None:
        """Libera o pool de conexões do cliente HTTP."""
        if not self.client.is_closed:
            await self.client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
