from enum import StrEnum


class RetailerEnum(StrEnum):
    WORTEN = "worten"
    AMAZON = "amazon"
    PCCOMPONENTES = "pccomponentes"


class AvailabilityStatus(StrEnum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PRE_ORDER = "pre_order"
    UNKNOWN = "unknown"


class CategoryEnum(StrEnum):
    SMARTPHONES = "smartphones"
    LAPTOPS = "laptops"
    CONSOLES = "consoles"
    HARDWARE = "hardware"
    AUDIO = "audio"
    OTHER = "other"
