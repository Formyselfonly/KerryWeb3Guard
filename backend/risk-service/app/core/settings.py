from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "KerryChainGuard Risk Service"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_allow_origins: str = "http://localhost:5173"

    openai_api_key: str = Field(default="")
    openai_base_url: str = "https://openrouter.ai/api/v1"
    openai_model: str = "gpt-4o-mini"

    dexscreener_base_url: str = "https://api.dexscreener.com"
    bitquery_api_key: str = Field(default="")
    bitquery_endpoint: str = "https://streaming.bitquery.io/graphql"
    dexscreener_supported_chains: str = (
        "ethereum,bsc,solana,base,arbitrum,polygon,avalanche,optimism,"
        "fantom,tron,sui,aptos,linea,blast,zksync,mantle,scroll,sei,"
        "pulsechain,berachain"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
