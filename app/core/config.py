from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str
    admin_email: str
    database_url: str
    database_ram_url: str
    url_localhost_frontend: str
    url_alternativa_frontend: str
    url_frontend_produccion: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    templates_dir: str
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

settings = Settings()

def get_settings():
    return settings