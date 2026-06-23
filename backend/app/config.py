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

    # Catalog image/text embeddings (Phase 1). Product-tuned, text+image in one shared space.
    # Swappable like render_model (e.g. SigLIP2 / marqo-ecommerce-L) without touching callers.
    embed_model: str = "hf-hub:Marqo/marqo-ecommerce-embeddings-B"
    embed_dim: int = 768

    # Match-confidence bands per query modality (cosine). text<->image cosines sit far lower
    # than image<->image (the CLIP/SigLIP modality gap), so they are calibrated SEPARATELY on
    # the seed catalog. Below the close band => "no real match" (never returns the nearest).
    # text bands derived from the seed (true-match median 0.124 vs wrong-match p90 0.103);
    # image bands are conservative pending cleaner (less category-noisy) calibration.
    match_text_exact: float = 0.16
    match_text_close: float = 0.10
    match_image_exact: float = 0.85
    match_image_close: float = 0.72

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
