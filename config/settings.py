from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ServiceNow
    servicenow_instance: str = Field(..., env="SERVICENOW_INSTANCE")
    sn_user: str = Field(..., env="SN_USER")
    sn_pass: str = Field(..., env="SN_PASS")
    sn_group: str = Field(..., env="SN_GROUP")

    # Anthropic / Claude
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")

    # Order cancellation API
    order_api_base_url: str = Field("http://localhost:9999", env="ORDER_API_BASE_URL")
    order_api_key: str = Field("", env="ORDER_API_KEY")

    # ServiceNow API field name for "Problem Correlation Code (PCC)".
    # To find the exact name: open an incident → right-click the PCC field label
    # → "Show Field Name".  Common values: u_problem_correlation_code, u_pcc.
    sn_pcc_field: str = Field("u_problem_correlation_code", env="SN_PCC_FIELD")

    # Orchestrator
    engineer_name: str = Field("Incident Orchestrator Bot", env="ENGINEER_NAME")
    poll_interval_seconds: int = Field(60, env="POLL_INTERVAL_SECONDS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
