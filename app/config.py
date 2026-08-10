import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    doppel_mode: str = "fixture"
    doppel_data_dir: Path = Path("data")
    doppel_artifact_dir: Path = Path("artifacts/runs")
    doppel_target_env: str = "NON_PROD"
    datahub_gms_url: str = "http://localhost:8080"
    datahub_token: str | None = None
    datahub_platform: str = "file"
    datahub_env: str = "PROD"
    # Semicolon-separated source dataset URNs used when DOPPEL_MODE=datahub.
    # Semicolons are used because DataHub dataset URNs contain commas.
    datahub_source_dataset_urns: str = (
        "urn:li:dataset:(urn:li:dataPlatform:postgres,clinical.patients,PROD);"
        "urn:li:dataset:(urn:li:dataPlatform:postgres,clinical.encounters,PROD)"
    )

    # LLM planner (OpenAI-compatible gateway) for the DOPPEL agent.
    opencode_api_key: str | None = None
    opencode_base_url: str = "https://opencode.ai/zen/go/v1"
    opencode_model: str = "deepseek-v4-pro"

    @property
    def live_datahub(self) -> bool:
        return self.doppel_mode.lower() == "datahub"

    @property
    def source_dataset_urns(self) -> list[str]:
        return [urn.strip() for urn in self.datahub_source_dataset_urns.split(";") if urn.strip()]


settings = Settings()

# On Vercel (and any read-only serverless filesystem) only /tmp is writable.
# Redirect run artifacts there unless the operator set an explicit override.
if os.environ.get("VERCEL") and settings.doppel_artifact_dir == Path("artifacts/runs"):
    settings.doppel_artifact_dir = Path("/tmp/doppel-runs")

# Creating the directory must never crash import on a read-only filesystem.
try:
    settings.doppel_artifact_dir.mkdir(parents=True, exist_ok=True)
except OSError:
    pass
