import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    FISCAL_DATA_BASE_URL = os.getenv(
        "FISCAL_DATA_BASE_URL",
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service",
    )
