import os

from dotenv import load_dotenv

from kronos.configuration.settings import Settings


DEFAULT_PROVIDER = "KITE"
DEFAULT_KITE_REDIRECT_URL = "http://localhost:8000/callback"


def load_settings() -> Settings:
    """Load KRONOS configuration from the environment and an optional `.env`."""

    load_dotenv()

    return Settings(
        provider=os.getenv("KRONOS_PROVIDER", DEFAULT_PROVIDER).strip(),
        kite_api_key=os.getenv("KRONOS_KITE_API_KEY", ""),
        kite_api_secret=os.getenv("KRONOS_KITE_API_SECRET", ""),
        kite_redirect_url=os.getenv(
            "KRONOS_KITE_REDIRECT_URL",
            DEFAULT_KITE_REDIRECT_URL,
        ).strip(),
    )
