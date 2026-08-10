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

    @property
    def live_datahub(self) -> bool:
        return self.doppel_mode.lower() == "datahub"

    @property
    def source_dataset_urns(self) -> list[str]:
        return [urn.strip() for urn in self.datahub_source_dataset_urns.split(";") if urn.strip()]


settings = Settings()
settings.doppel_artifact_dir.mkdir(parents=True, exist_ok=True)
