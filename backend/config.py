"""
Central configuration for the AI Finance Controller backend.
Loads environment variables once and exposes typed settings.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- LLM provider keys (whichever is present is used, in this priority order) ---
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")

    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")

    # --- Database ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./reconcile.db")

    # --- Rule-based pre-filters (used before/alongside the LLM to cut cost & hallucination risk) ---
    ANOMALY_AMOUNT_THRESHOLD: float = float(os.getenv("ANOMALY_AMOUNT_THRESHOLD", 50000))
    ANOMALY_ZSCORE_THRESHOLD: float = float(os.getenv("ANOMALY_ZSCORE_THRESHOLD", 3.0))

    def active_provider(self) -> str:
        """Returns which LLM provider will be used based on available keys."""
        if self.OPENAI_API_KEY:
            return "openai"
        if self.ANTHROPIC_API_KEY:
            return "anthropic"
        if self.GEMINI_API_KEY:
            return "gemini"
        return "none"


settings = Settings()
