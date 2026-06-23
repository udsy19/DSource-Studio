from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite by default => zero setup. Swap to Postgres via DATABASE_URL.
    database_url: str = "sqlite:///./dsource.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Gate A tolerance: our budgetary total must land within this of the dealer's real quote.
    gate_a_tolerance: float = 0.15

    # AI photoreal render proxy (optional).
    # provider="gemini" (Nano Banana) needs only render_api_key (a Google AI / Gemini key).
    # provider="generic" forwards {image,prompt} to render_api_url with a Bearer key.
    render_provider: str = "gemini"   # gemini | replicate | generic
    render_api_key: str = ""          # gemini key
    render_model: str = "gemini-2.5-flash-image"
    render_api_url: str = ""          # only for provider="generic"
    replicate_api_token: str = ""     # for provider="replicate" (ControlNet, layout-faithful)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
