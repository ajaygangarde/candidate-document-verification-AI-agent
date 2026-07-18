from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Always resolve .env relative to the project root, not the working directory
# __file__ = src/recruitment/shared/config.py -> up 4 levels to project root
ENV_FILE = Path(__file__).parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    aws_region: str = "us-east-1"
    aws_profile: str | None = None
    s3_bucket: str
    local_mode: bool = False
    cdv_verification_function_name: str = "CDV-ProcessVerification"
    database_url: str = "postgresql+psycopg://localhost:5432/recruitment"
    # NEED to Go to:
    # AWS Console → Bedrock → Model access (left sidebar) → Modify model access
    # Find and enable:
    # Claude Haiku 4.5
    # Claude Sonnet 4.6
    # Click Next → Submit. Access is usually granted within 1–5 minutes.
    # Upadate Master card to support International Transaction
    # bedrock_model_categorise: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    # bedrock_model_extract: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    # bedrock_model_analyse: str = "us.anthropic.claude-sonnet-4-6"
    bedrock_model_categorise: str = "amazon.nova-micro-v1:0"
    bedrock_model_extract: str = "amazon.nova-lite-v1:0"
    bedrock_model_analyse: str = "amazon.nova-pro-v1:0"






settings = Settings()
