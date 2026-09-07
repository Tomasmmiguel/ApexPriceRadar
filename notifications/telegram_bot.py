import logging
import re

import httpx

logger = logging.getLogger(__name__)


def escape_markdown_v2(text: str) -> str:
    """Escapa os caracteres reservados pelo Telegram MarkdownV2."""
    special_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special_chars)}])", r"\\\1", text)


class TelegramNotifier:
    """
    Notificador assíncrono para Telegram usando requisições HTTP directas.
    Funciona em modo mock/logger se desativado nas configurações.
    """

    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled and bool(bot_token) and bool(chat_id)
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    async def send_deal_alert(
        self,
        product_name: str,
        retailer: str,
        current_price: float,
        avg_price: float,
        discount_pct: float,
        is_all_time_low: bool,
        url: str,
    ) -> bool:
        if not self.enabled:
            logger.info(
                f"[Telegram MOCK Alert] Deal em {retailer.upper()}: {product_name} "
                f"a €{current_price:.2f} (-{discount_pct:.1f}%)"
            )
            return True

        badge = (
            "🚨 *NOVO MÍNIMO HISTÓRICO* 🚨\n"
            if is_all_time_low
            else "🔥 *OPORTUNIDADE DE PREÇO* 🔥\n"
        )

        message = (
            f"{badge}\n"
            f"📦 *Produto:* {escape_markdown_v2(product_name[:70])}\n"
            f"🏪 *Loja:* `{escape_markdown_v2(retailer.upper())}`\n"
            f"💰 *Preço Atual:* €{escape_markdown_v2(f'{current_price:.2f}')}\n"
            f"📊 *Média Histórica:* €{escape_markdown_v2(f'{avg_price:.2f}')}\n"
            f"📉 *Desconto Real:* *{escape_markdown_v2(f'{discount_pct:.1f}%')}*\n\n"
            f"🔗 [Aceder à Oferta Direta]({escape_markdown_v2(url)})"
        )

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": False,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.api_url, json=payload)
                if response.status_code == 200:
                    logger.info(f"Alerta Telegram enviado com sucesso para: {product_name[:30]}")
                    return True
                logger.error(f"Erro ao disparar Telegram ({response.status_code}): {response.text}")
                return False
        except Exception as exc:
            logger.error(f"Falha de conexão com a API do Telegram: {exc}")
            return False
