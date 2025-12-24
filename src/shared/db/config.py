"""Database configuration and async engine management."""
import os
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseConfig(BaseSettings):
    """Database configuration with connection pooling settings.

    Settings are loaded from environment variables with sensible defaults.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database connection parameters
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    user: str = Field(default="postgres", description="Database user")
    password: str = Field(default="postgres", description="Database password")
    name: str = Field(default="researcher_agent", description="Database name")

    # Connection pool settings
    pool_size: int = Field(
        default=5,
        description="Number of connections to maintain in pool"
    )
    max_overflow: int = Field(
        default=10,
        description="Maximum overflow connections beyond pool_size"
    )
    pool_recycle: int = Field(
        default=3600,
        description="Recycle connections after this many seconds (1 hour)"
    )
    pool_timeout: int = Field(
        default=30,
        description="Seconds to wait before giving up on getting a connection"
    )
    pool_pre_ping: bool = Field(
        default=True,
        description="Test connections for liveness before using them"
    )

    # SQL logging
    echo: bool = Field(
        default=False,
        description="Echo SQL statements to stdout (DEBUG mode)"
    )

    @property
    def database_url(self) -> str:
        """Construct async PostgreSQL connection URL."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        """Validate database host.

        Use 'postgres' when running in Docker (service name),
        use 'localhost' when running locally.
        """
        return v

    def create_async_engine(self) -> AsyncEngine:
        """Create configured async database engine with connection pooling."""
        return create_async_engine(
            self.database_url,
            echo=self.echo,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_recycle=self.pool_recycle,
            pool_timeout=self.pool_timeout,
            pool_pre_ping=self.pool_pre_ping,
        )


# Global configuration instance (loaded from environment)
db_config = DatabaseConfig()


# Global async engine and session factory (initialized on first use)
_async_engine: Optional[AsyncEngine] = None
_async_session_maker: Optional[async_sessionmaker[AsyncSession]] = None


def get_async_engine() -> AsyncEngine:
    """Get or create global async engine.

    Engine is created lazily on first call and reused thereafter.
    This ensures single engine instance per application.
    """
    global _async_engine, _async_session_maker

    if _async_engine is None:
        _async_engine = db_config.create_async_engine()
        _async_session_maker = async_sessionmaker(
            _async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _async_engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create global async session factory.

    Session factory is created lazily on first call and reused.
    """
    global _async_session_maker

    if _async_session_maker is None:
        # Ensure engine exists first
        get_async_engine()

    return _async_session_maker


async def dispose_engine() -> None:
    """Dispose of global engine and session factory.

    Call this when shutting down the application to clean up connections.
    """
    global _async_engine, _async_session_maker

    if _async_engine is not None:
        await _async_engine.dispose()
        _async_engine = None
        _async_session_maker = None

