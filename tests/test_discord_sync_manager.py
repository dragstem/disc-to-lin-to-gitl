"""Unit tests for DiscordSyncManager."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.discord_sync_manager import DiscordSyncManager, DiscordThreadData, SyncState
from src.config_manager import ConfigManager
from src.file_manager import FileManager
from src.error_logger import ErrorLogger


class TestDiscordSyncManager(unittest.TestCase):
    """Test cases for DiscordSyncManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = Mock(spec=ConfigManager)
        self.config.discord_enabled = True
        self.config.get_value = Mock(return_value="test_value")

        self.file_manager = Mock(spec=FileManager)
        self.error_logger = Mock(spec=ErrorLogger)

        # Mock LinearClient with get_team_id
        mock_linear = Mock()
        mock_linear.get_team_id.return_value = ("mock-team-id", "MOCK")

        # Create DiscordSyncManager with mocked dependencies
        with patch('src.discord_sync_manager.DiscordClient'), \
             patch('src.discord_sync_manager.LinearClient', return_value=mock_linear), \
             patch('src.discord_sync_manager.TagFilterEngine'):
            self.sync_manager = DiscordSyncManager(self.config)
            self.sync_manager.file_manager = self.file_manager
            self.sync_manager.error_logger = self.error_logger
            self.sync_manager.linear_client = mock_linear

    def test_initialization(self):
        """Test DiscordSyncManager initialization."""
        with patch('src.discord_sync_manager.DiscordClient') as mock_discord, \
             patch('src.discord_sync_manager.LinearClient') as mock_linear, \
             patch('src.discord_sync_manager.TagFilterEngine') as mock_filter:
            manager = DiscordSyncManager(self.config)

            mock_discord.assert_called_once_with(self.config)
            mock_linear.assert_called_once_with(self.config)
            mock_filter.assert_called_once()
            self.assertIsNotNone(manager.filter_engine)

    def test_transform_discord_to_linear(self):
        """Test Discord to Linear transformation."""
        thread_data = DiscordThreadData(
            thread_id="123456",
            thread_name="Test Thread",
            created_at="2025-01-01T10:00:00Z",
            updated_at="2025-01-01T11:00:00Z",
            message_count=5,
            author_id="789",
            tags=["bug", "urgent"],
            first_message_content="This is a test thread"
        )

        # Mock team mapping
        self.sync_manager.file_manager.get_discord_setting = Mock(side_effect=lambda key: {
            'DISCORD_TEAM_MAPPINGS': {"bug": "team-bugs", "urgent": "team-urgent"},
            'DISCORD_DEFAULT_TEAM': "team-default"
        }.get(key, "team-default"))

        result = self.sync_manager.transform_discord_to_linear(thread_data)

        self.assertEqual(result['title'], "[bug] [urgent] Test Thread")
        self.assertIn("This is a test thread", result['description'])
        self.assertIn("Thread ID: 123456", result['description'])
        self.assertEqual(result['team_id'], "team-bugs")
        self.assertEqual(result['labels'], ["bug", "urgent"])
        self.assertEqual(result['priority'], 3)

    def test_should_filter_thread_with_content(self):
        """Test thread filtering with valid content."""
        thread_data = DiscordThreadData(
            thread_id="123",
            thread_name="Valid Thread",
            created_at="2025-01-01T10:00:00Z",
            updated_at="2025-01-01T11:00:00Z",
            message_count=3,
            author_id="789",
            tags=[],
            first_message_content="Valid content here"
        )

        # Mock filter engine
        self.sync_manager.filter_engine.should_include_thread = Mock(return_value=Mock(should_include=True))

        result = self.sync_manager._should_filter_thread(thread_data)

        self.assertFalse(result)  # Should not be filtered
        self.sync_manager.filter_engine.should_include_thread.assert_called_once()

    def test_should_filter_thread_without_content(self):
        """Test thread filtering without content."""
        thread_data = DiscordThreadData(
            thread_id="123",
            thread_name="Empty Thread",
            created_at="2025-01-01T10:00:00Z",
            updated_at="2025-01-01T11:00:00Z",
            message_count=0,
            author_id="789",
            tags=[],
            first_message_content=""
        )

        # Mock filter engine to exclude
        mock_result = Mock()
        mock_result.should_include = False
        mock_result.reason = "No content"
        self.sync_manager.filter_engine.should_include_thread = Mock(return_value=mock_result)

        result = self.sync_manager._should_filter_thread(thread_data)

        self.assertTrue(result)  # Should be filtered

    def test_get_team_mapping_for_tags(self):
        """Test team mapping based on tags."""
        # Mock settings
        self.sync_manager.file_manager.get_discord_setting = Mock(side_effect=lambda key: {
            'DISCORD_TEAM_MAPPINGS': {"bug": "team-bugs", "feature": "team-features"},
            'DISCORD_DEFAULT_TEAM': None
        }.get(key, None))

        result = self.sync_manager._get_team_mapping_for_tags(["bug", "urgent"])
        self.assertEqual(result, "team-bugs")

        result = self.sync_manager._get_team_mapping_for_tags(["feature"])
        self.assertEqual(result, "team-features")

        result = self.sync_manager._get_team_mapping_for_tags(["unknown"])
        self.assertEqual(result, "mock-team-id")  # From mocked get_team_id

    @patch('src.discord_sync_manager.datetime')
    def test_update_discord_sync_timestamp(self, mock_datetime):
        """Test sync timestamp update."""
        mock_datetime.utcnow.return_value = Mock()
        mock_datetime.utcnow.return_value.isoformat.return_value = "2025-01-01T12:00:00"

        self.sync_manager._update_discord_sync_timestamp()

        self.file_manager.set_discord_last_sync_timestamp.assert_called_once()

    def test_get_discord_sync_status(self):
        """Test getting Discord sync status."""
        self.file_manager.get_discord_last_sync_timestamp = Mock(return_value="2025-01-01T12:00:00Z")
        self.file_manager.get_all_discord_mappings = Mock(return_value=[{"id": "1"}, {"id": "2"}])

        result = self.sync_manager.get_discord_sync_status()

        self.assertEqual(result['total_discord_mappings'], 2)
        self.assertEqual(result['last_discord_sync_timestamp'], "2025-01-01T12:00:00Z")
        self.assertTrue(result['discord_enabled'])

    def test_sync_state_dataclass(self):
        """Test SyncState dataclass functionality."""
        state = SyncState()
        self.assertEqual(state.threads_processed, 0)
        self.assertEqual(state.threads_created, 0)
        self.assertEqual(state.threads_updated, 0)
        self.assertEqual(state.threads_filtered, 0)
        self.assertEqual(state.errors, [])

        # Test with values
        state = SyncState(
            last_sync_timestamp="2025-01-01T00:00:00Z",
            threads_processed=10,
            threads_created=3,
            threads_updated=2,
            threads_filtered=5,
            errors=["Error 1", "Error 2"]
        )
        self.assertEqual(state.threads_processed, 10)
        self.assertEqual(state.threads_created, 3)
        self.assertEqual(state.threads_updated, 2)
        self.assertEqual(state.threads_filtered, 5)
        self.assertEqual(state.errors, ["Error 1", "Error 2"])

    def test_thread_needs_update(self):
        """Test thread update detection."""
        linear_data = {
            'discord_thread_id': '123',
            'discord_updated_at': '2025-01-01T11:00:00Z'
        }

        existing_mapping = {
            'linear_id': 'linear_1',
            'discord_updated_at': '2025-01-01T10:00:00Z'  # Older timestamp
        }

        result = self.sync_manager._thread_needs_update(linear_data, existing_mapping)
        self.assertTrue(result)  # Should need update

        # Test with same timestamp
        existing_mapping['discord_updated_at'] = '2025-01-01T11:00:00Z'
        result = self.sync_manager._thread_needs_update(linear_data, existing_mapping)
        self.assertFalse(result)  # Should not need update


    def test_extract_thread_data_with_tags(self):
        """Test thread data extraction with tags."""
        mock_thread = {
            'id': '123456',
            'name': 'Test Thread with Tags',
            'owner_id': '789',
            'message_count': 5,
            'applied_tags': ['tag1_id', 'tag2_id'],
            'available_tags': [
                {'id': 'tag1_id', 'name': 'bug'},
                {'id': 'tag2_id', 'name': 'urgent'},
                {'id': 'tag3_id', 'name': 'feature'}
            ],
            'thread_metadata': {'create_timestamp': '2025-01-01T10:00:00.000+00:00'}
        }

        # Mock get_thread_messages to return a message
        self.sync_manager.discord_client.get_thread_messages.return_value = [
            {'content': 'Test message content'}
        ]

        # Mock _get_discord_user_info
        with patch.object(self.sync_manager, '_get_discord_user_info', return_value='TestUser#1234'):
            thread_data = self.sync_manager._extract_thread_data(mock_thread)

        self.assertIsNotNone(thread_data)
        self.assertEqual(thread_data.thread_id, '123456')
        self.assertEqual(thread_data.thread_name, 'Test Thread with Tags')
        self.assertEqual(thread_data.tags, ['bug', 'urgent'])
        self.assertEqual(thread_data.first_message_content, 'Test message content')
        self.assertEqual(thread_data.author_id, '789')


if __name__ == '__main__':
    unittest.main()