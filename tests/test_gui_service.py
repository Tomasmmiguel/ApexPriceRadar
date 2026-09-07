from gui.service import detect_retailer_from_input
from models.enums import RetailerEnum


def test_detect_retailer_from_dropdown():
    assert detect_retailer_from_input("https://qualquer.com", "Amazon") == RetailerEnum.AMAZON
    assert detect_retailer_from_input("https://qualquer.com", "Worten") == RetailerEnum.WORTEN


def test_detect_retailer_from_url_auto():
    assert (
        detect_retailer_from_input("https://www.amazon.es/dp/B0CLTBHXWQ", "Automático")
        == RetailerEnum.AMAZON
    )
    assert (
        detect_retailer_from_input("https://www.worten.pt/produtos/ps5-slim-12345", "Automático")
        == RetailerEnum.WORTEN
    )
    # Default para termo genérico
    assert detect_retailer_from_input("PlayStation 5", "Automático") == RetailerEnum.AMAZON
