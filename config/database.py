from pydantic import BaseModel


class DbConfig(BaseModel):
    DB_ECHO: bool = False

    POSTGRES_USER: str = "vkorni_user"
    POSTGRES_PASSWORD: str = "123"
    POSTGRES_DB: str = "vkorni_db"
    POSTGRES_PORT: int = 5432
    POSTGRES_HOST: str = "db"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
