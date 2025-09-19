"""Configuration management using environment variables and python-dotenv."""

import os
from typing import Optional
from dotenv import load_dotenv
from dotenv import load_dotenv, find_dotenv
from pathlib import Path


class ConfigManager:
    """Manages application configuration from environment variables."""

    def __init__(self, env_file: str = ".env") -> None:
        # 1) Try the provided path (keeps current behavior)
        loaded = load_dotenv(env_file)

        # 2) If not loaded, try project-root-level .env relative to this file
        if not loaded:
            project_root_env = Path(__file__).resolve().parents[1] / ".env"
            loaded = load_dotenv(project_root_env)

        # 3) If still not loaded, auto-discover with find_dotenv (walk up dirs)
        if not loaded:
            load_dotenv(find_dotenv(), override=False)

        self._validate_config()

    def _validate_config(self) -> None:
        """Validate required configuration values."""
        required_vars = [
            'LINEAR_API_KEY',
            'GITLAB_TOKEN',
            'GITLAB_PROJECT_ID',
            'SYNC_INTERVAL',
            'LOG_LEVEL'
        ]
        missing = [var for var in required_vars if not self.get_value(var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        # Validate Discord configuration if enabled
        if self.discord_enabled:
            discord_required = [
                'DISCORD_BOT_TOKEN',
                'DISCORD_GUILD_ID',
                'DISCORD_FORUM_CHANNEL_ID',
                'DISCORD_SYNC_INTERVAL'
            ]
            missing_discord = [var for var in discord_required if not self.get_value(var)]
            if missing_discord:
                raise ValueError(f"Discord is enabled but missing required environment variables: {', '.join(missing_discord)}")

    def get_value(self, key: str, default: Optional[str] = None) -> str:
        """Get configuration value by key.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value as string
        """
        return os.getenv(key, default)

    def get_int_value(self, key: str, default: int) -> int:
        """Get configuration value as integer.

        Args:
            key: Configuration key
            default: Default integer value

        Returns:
            Configuration value as integer
        """
        value = self.get_value(key)
        if value:
            try:
                return int(value)
            except ValueError:
                pass
        return default

    def get_bool_value(self, key: str, default: bool = False) -> bool:
        """Get configuration value as boolean.

        Args:
            key: Configuration key
            default: Default boolean value

        Returns:
            Configuration value as boolean
        """
        value = self.get_value(key, '').lower()
        return value in ('true', '1', 'yes', 'on')

    @property
    def linear_api_key(self) -> str:
        """Linear API key."""
        return self.get_value('LINEAR_API_KEY')

    @property
    def gitlab_token(self) -> str:
        """GitLab personal access token."""
        return self.get_value('GITLAB_TOKEN')

    @property
    def gitlab_project_id(self) -> str:
        """GitLab project ID."""
        return self.get_value('GITLAB_PROJECT_ID')

    @property
    def gitlab_base_url(self) -> str:
        """GitLab base URL."""
        return self.get_value('GITLAB_BASE_URL', 'https://gitlab.com/api/v4')

    @property
    def sync_interval(self) -> int:
        """Synchronization interval in seconds."""
        return self.get_int_value('SYNC_INTERVAL', 300)


    @property
    def log_level(self) -> str:
        """Logging level."""
        return self.get_value('LOG_LEVEL', 'INFO')

    @property
    def dry_run(self) -> bool:
        """Whether to run in dry-run mode."""
        return self.get_bool_value('DRY_RUN', False)

    @property
    def linear_team_name(self) -> str:
        """Linear team name (configurable)."""
        return self.get_value('LINEAR_TEAM_NAME', 'MAU')

    @property
    def gitlab_project_id_full(self) -> str:
        """GitLab project ID (configurable)."""
        return self.get_value('GITLAB_PROJECT_ID_OVERRIDE', self.gitlab_project_id)

    @property
    def discord_enabled(self) -> bool:
        """Whether Discord integration is enabled."""
        return self.get_bool_value('DISCORD_ENABLED', False)

    @property
    def discord_bot_token(self) -> str:
        """Discord bot token."""
        return self.get_value('DISCORD_BOT_TOKEN')

    @property
    def discord_guild_id(self) -> str:
        """Discord guild (server) ID."""
        return self.get_value('DISCORD_GUILD_ID')

    @property
    def discord_forum_channel_id(self) -> str:
        """Discord forum channel ID."""
        return self.get_value('DISCORD_FORUM_CHANNEL_ID')

    @property
    def discord_api_base_url(self) -> str:
        """Discord API base URL."""
        return self.get_value('DISCORD_API_BASE_URL', 'https://discord.com/api/v10')

    @property
    def discord_sync_interval(self) -> int:
        """Discord synchronization interval in seconds."""
        return self.get_int_value('DISCORD_SYNC_INTERVAL', 600)