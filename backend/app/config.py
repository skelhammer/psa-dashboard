from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SuperOpsConfig:
    api_url: str = "https://api.superops.ai/msp"
    api_token: str = ""
    subdomain: str = ""


@dataclass
class HaloPSAConfig:
    api_url: str = ""
    client_id: str = ""
    client_secret: str = ""


@dataclass
class PSAConfig:
    provider: str = "mock"
    superops: SuperOpsConfig = field(default_factory=SuperOpsConfig)
    halopsa: HaloPSAConfig = field(default_factory=HaloPSAConfig)


@dataclass
class SyncConfig:
    interval_minutes: int = 15
    full_sync_on_first_run: bool = True


@dataclass
class DatabaseConfig:
    path: str = "./data/metrics.db"


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    timezone: str = "America/Los_Angeles"


@dataclass
class BillingConfig:
    hourly_plans: list[str] = field(default_factory=list)
    unlimited_plans: list[str] = field(default_factory=list)


@dataclass
class ThresholdsConfig:
    stale_ticket_days: int = 3
    sla_warning_minutes: int = 30
    max_tickets_per_tech: int = 20
    utilization_target_min: int = 60
    utilization_target_max: int = 85


@dataclass
class BusinessHoursConfig:
    enabled: bool = True
    start_hour: int = 8
    end_hour: int = 17
    work_days: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 5])
    holidays: list[str] = field(default_factory=list)


@dataclass
class Settings:
    psa: PSAConfig = field(default_factory=PSAConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    billing: BillingConfig = field(default_factory=BillingConfig)
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    business_hours: BusinessHoursConfig = field(default_factory=BusinessHoursConfig)

    @property
    def db_path(self) -> Path:
        return Path(self.database.path)


def _build_nested(cls, data: dict | None):
    if data is None:
        return cls()
    kwargs = {}
    for f_name, f_type in cls.__dataclass_fields__.items():
        if f_name in data:
            val = data[f_name]
            if hasattr(f_type.type, "__dataclass_fields__") if isinstance(f_type.type, type) else False:
                val = _build_nested(f_type.type, val)
            kwargs[f_name] = val
    return cls(**kwargs)


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from config.yaml, falling back to defaults."""
    if config_path is None:
        config_path = Path(os.environ.get("CONFIG_PATH", "config.yaml"))

    if not config_path.exists():
        # Try relative to project root
        root = Path(__file__).parent.parent.parent
        config_path = root / "config.yaml"

    if config_path.exists():
        with open(config_path, "r") as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    psa_raw = raw.get("psa", {})
    psa = PSAConfig(
        provider=psa_raw.get("provider", "mock"),
        superops=_build_nested(SuperOpsConfig, psa_raw.get("superops")),
        halopsa=_build_nested(HaloPSAConfig, psa_raw.get("halopsa")),
    )

    billing_raw = raw.get("billing", {})
    billing = BillingConfig(
        hourly_plans=billing_raw.get("hourly_plans", []),
        unlimited_plans=billing_raw.get("unlimited_plans", []),
    )

    return Settings(
        psa=psa,
        sync=_build_nested(SyncConfig, raw.get("sync")),
        database=_build_nested(DatabaseConfig, raw.get("database")),
        server=_build_nested(ServerConfig, raw.get("server")),
        billing=billing,
        thresholds=_build_nested(ThresholdsConfig, raw.get("thresholds")),
        business_hours=_build_nested(BusinessHoursConfig, raw.get("business_hours")),
    )


# Singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
