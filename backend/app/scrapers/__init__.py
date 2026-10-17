from app.scrapers.base import BaseScraper, ScrapedAuction, ScrapedItem, ScrapedSession
from app.scrapers.freitas import FreitasScraper
from app.scrapers.generic_html import GenericHtmlScraper
from app.scrapers.leilo import LeiloScraper
from app.scrapers.leiloesjudiciais import LeiloesJudiciaisScraper
from app.scrapers.megaleiloes import MegaLeiloesScraper
from app.scrapers.nakakogue import NakakogueScraper
from app.scrapers.palacio import PalacioScraper
from app.scrapers.parquedosleiloes import ParqueDosLeiloesScraper
from app.scrapers.pestana import PestanaScraper
from app.scrapers.rogeriomenezes import RogerioMenezesScraper

SCRAPERS: dict[str, type[BaseScraper]] = {
    "megaleiloes": MegaLeiloesScraper,
    "freitas": FreitasScraper,
    "leilo": LeiloScraper,
    "rogeriomenezes": RogerioMenezesScraper,
    "nakakogue": NakakogueScraper,
    "parquedosleiloes": ParqueDosLeiloesScraper,
    "pestana": PestanaScraper,
    "leiloesjudiciais": LeiloesJudiciaisScraper,
    "palacio": PalacioScraper,
    "generic_html": GenericHtmlScraper,
}


def get_scraper(parser_type: str) -> type[BaseScraper]:
    cls = SCRAPERS.get((parser_type or "").lower())
    if not cls:
        raise ValueError(f"Parser desconhecido: {parser_type}. Disponiveis: {list(SCRAPERS)}")
    return cls


def available_parsers() -> list[dict]:
    return [
        {"key": key, "name": cls.display_name, "default_config": cls.default_config}
        for key, cls in SCRAPERS.items()
    ]


__all__ = [
    "BaseScraper", "ScrapedAuction", "ScrapedItem", "ScrapedSession",
    "SCRAPERS", "get_scraper", "available_parsers",
]
