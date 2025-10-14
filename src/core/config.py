"""
Configuración de la aplicación.
Lee variables desde el archivo .env con validación.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- Base de datos ---
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str

    # --- JWT ---
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # --- Config Pydantic ---
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def DATABASE_URL(self) -> str:
        """Construye la URL de conexión para SQLAlchemy (SQL Server)."""
        password = self.DB_PASSWORD.replace("@", "%40")
        return (
            f"mssql+pyodbc://{self.DB_USER}:{password}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?driver=ODBC+Driver+17+for+SQL+Server"
        )

settings = Settings() #type: ignore
