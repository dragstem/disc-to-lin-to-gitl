"""Unit tests for Discord API client."""

import pytest
import requests
from unittest.mock import Mock, patch
from src.config_manager import ConfigManager
from src.discord_client import DiscordClient


def test_discord_client_initialization():
    """Test Discord client initializes correctly."""
    config = Mock()
    config.discord_bot_token = "test_bot_token"
    config.discord_guild_id = "123456789"
    config.discord_forum_channel_id = "987654321"
    config.discord_api_base_url = "https://discord.com/api/v10"

    client = DiscordClient(config)
    assert client.bot_token == "test_bot_token"
    assert client.guild_id == "123456789"
    assert client.forum_channel_id == "987654321"
    assert client.base_url == "https://discord.com/api/v10"
    assert "Bot test_bot_token" in client.session.headers["Authorization"]


@patch('src.discord_client.requests.Session.get')
def test_get_forum_threads(mock_get):
    """Test retrieving forum threads."""
    # Mock successful API response
    mock_response = Mock()
    mock_response.json.return_value = [
        {
            "id": "123456789012345678",
            "name": "Test Thread",
            "type": 11,
            "thread_metadata": {"archived": False}
        }
    ]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    config = Mock()
    config.discord_bot_token = "test_token"
    config.discord_guild_id = "guild_123"
    config.discord_forum_channel_id = "channel_456"
    config.discord_api_base_url = "https://discord.com/api/v10"

    client = DiscordClient(config)
    threads = client.get_forum_threads(limit=50)

    assert len(threads) == 1
    assert threads[0]["id"] == "123456789012345678"
    assert threads[0]["name"] == "Test Thread"
    mock_get.assert_called_once()


@patch('src.discord_client.requests.Session.get')
def test_get_archived_threads(mock_get):
    """Test retrieving archived threads."""
    # Mock successful API response
    mock_response = Mock()
    mock_response.json.return_value = {
        "threads": [
            {
                "id": "123456789012345679",
                "name": "Archived Thread",
                "type": 11,
                "thread_metadata": {"archived": True}
            }
        ],
        "has_more": False
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    config = Mock()
    config.discord_bot_token = "test_token"
    config.discord_guild_id = "guild_123"
    config.discord_forum_channel_id = "channel_456"
    config.discord_api_base_url = "https://discord.com/api/v10"

    client = DiscordClient(config)
    threads = client.get_archived_threads(limit=100)

    assert len(threads) == 1
    assert threads[0]["id"] == "123456789012345679"
    assert threads[0]["name"] == "Archived Thread"


@patch('src.discord_client.requests.Session.get')
def test_get_thread_messages(mock_get):
    """Test retrieving thread messages."""
    # Mock successful API response
    mock_response = Mock()
    mock_response.json.return_value = [
        {
            "id": "987654321098765432",
            "content": "Test message",
            "author": {"username": "testuser"},
            "timestamp": "2023-01-01T00:00:00.000Z"
        }
    ]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    config = Mock()
    config.discord_bot_token = "test_token"
    config.discord_guild_id = "guild_123"
    config.discord_forum_channel_id = "channel_456"
    config.discord_api_base_url = "https://discord.com/api/v10"

    client = DiscordClient(config)
    messages = client.get_thread_messages("thread_123", limit=50)

    assert len(messages) == 1
    assert messages[0]["id"] == "987654321098765432"
    assert messages[0]["content"] == "Test message"


@patch('src.discord_client.requests.Session.get')
def test_test_connectivity_success(mock_get):
    """Test connectivity test success."""
    # Mock successful API response
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "bot_user_id",
        "username": "test_bot",
        "discriminator": "1234"
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    config = Mock()
    config.discord_bot_token = "test_token"
    config.discord_guild_id = "guild_123"
    config.discord_forum_channel_id = "channel_456"
    config.discord_api_base_url = "https://discord.com/api/v10"

    client = DiscordClient(config)
    result = client.test_connectivity()

    assert result is True
    mock_get.assert_called_once()


@patch('src.discord_client.requests.Session.get')
def test_test_connectivity_failure(mock_get):
    """Test connectivity test failure."""
    # Mock failed API response
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = Exception("API Error")
    mock_get.return_value = mock_response

    config = Mock()
    config.discord_bot_token = "invalid_token"
    config.discord_guild_id = "guild_123"
    config.discord_forum_channel_id = "channel_456"
    config.discord_api_base_url = "https://discord.com/api/v10"

    client = DiscordClient(config)
    result = client.test_connectivity()

    assert result is False


@patch('src.discord_client.requests.Session.get')
def test_rate_limiting(mock_get):
    """Test rate limiting functionality."""
    # Mock successful API response
    mock_response = Mock()
    mock_response.json.return_value = {"test": "data"}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    config = Mock()
    config.discord_bot_token = "test_token"
    config.discord_guild_id = "guild_123"
    config.discord_forum_channel_id = "channel_456"
    config.discord_api_base_url = "https://discord.com/api/v10"

    client = DiscordClient(config)

    # Make multiple requests quickly
    client._make_request('GET', 'test/endpoint')
    client._make_request('GET', 'test/endpoint')
    client._make_request('GET', 'test/endpoint')

    # Should have called get 3 times
    assert mock_get.call_count == 3


@patch('src.discord_client.requests.Session.get')
def test_rate_limit_handling(mock_get):
    """Test handling of rate limit responses."""
    # Mock rate limited response first, then success
    rate_limit_response = Mock()
    rate_limit_response.status_code = 429
    rate_limit_response.headers = {"Retry-After": "1"}

    success_response = Mock()
    success_response.json.return_value = {"test": "data"}
    success_response.raise_for_status.return_value = None

    mock_get.side_effect = [rate_limit_response, success_response]

    config = Mock()
    config.discord_bot_token = "test_token"
    config.discord_guild_id = "guild_123"
    config.discord_forum_channel_id = "channel_456"
    config.discord_api_base_url = "https://discord.com/api/v10"

    client = DiscordClient(config)

    with patch('time.sleep') as mock_sleep:
        result = client._make_request('GET', 'test/endpoint')

    assert result == {"test": "data"}
    mock_sleep.assert_called_once_with(1)


if __name__ == "__main__":
    pytest.main([__file__])