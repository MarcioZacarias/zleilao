"""Configuracao de BOOT (lida do .env pelo pydantic).

Aqui fica SOMENTE o que o processo precisa para subir: banco e chave de
assinatura do JWT. Toda configuracao operacional (LLM, limites do pipeline,
textos do portal, etc.) vive na tabela `system_settings`, editavel pela tela
de Configuracoes do admin — ver `settings_service.py`. Mesma regra do Promo:
editar o .env esperando efeito em runtime e' perda de tempo.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Banco
    DATABASE_URL: str = "postgresql+asyncpg://zleilao:zleilaopass@localhost:5434/zleilao"
    DATABASE_URL_SYNC: str = "postgresql://zleilao:zleilaopass@localhost:5434/zleilao"

    # Auth
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Admin inicial (semeado no primeiro boot; troque a senha depois)
    ADMIN_EMAIL: str = "admin@zconnect.ia.br"
    ADMIN_PASSWORD: str = "admin123"

    # Scheduler: desligue em testes / scripts one-off
    SCHEDULER_ENABLED: bool = True

    # Fixtures locais: quando True, a fonte `parser_type=fixture` fica
    # disponivel para desenvolvimento sem bater em site nenhum.
    DEBUG: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
