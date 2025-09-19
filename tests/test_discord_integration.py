"""Integration tests for Discord synchronization workflow."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import json
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.discord_sync_manager import DiscordSyncManager, DiscordThreadData
from src.config_manager import ConfigManager
from src.file_manager import FileManager
from src.error_logger import ErrorLogger


class TestDiscordIntegration(unittest.TestCase):
    """Integration tests for Discord synchronization workflow."""

    def setUp(self):
        """Set up integration test fixtures."""
        self.config = Mock(spec=ConfigManager)
        self.config.discord_enabled = True
        self.config.get_value = Mock(return_value="test_team")

        # Create a temporary directory for test data
        self.test_data_dir = Path("./test_data")
        self.test_data_dir.mkdir(exist_ok=True)

        # Mock file operations
        with patch('src.file_manager.Path') as mock_path:
            mock_path.return_value.mkdir = Mock()
            self.file_manager = FileManager(self.config)

        self.error_logger = Mock(spec=ErrorLogger)

    def tearDown(self):
        """Clean up test fixtures."""
        # Clean up test data directory
        if self.test_data_dir.exists():
            import shutil
            shutil.rmtree(self.test_data_dir)

    @patch('src.discord_sync_manager.DiscordClient')
    @patch('src.discord_sync_manager.LinearClient')
    @patch('src.discord_sync_manager.TagFilterEngine')
    def test_full_sync_workflow(self, mock_filter_engine, mock_linear_client, mock_discord_client):
        """Test the complete Discord synchronization workflow."""
        # Setup mocks
        mock_discord = mock_discord_client.return_value
        mock_linear = mock_linear_client.return_value
        mock_filter = mock_filter_engine.return_value

        # Mock Discord API responses
        mock_discord.get_forum_threads.return_value = [
            {
                'id': 'thread_1',
                'name': 'Bug Report Thread',
                'thread_metadata': {'create_timestamp': '2025-01-01T10:00:00Z'},
                'most_recent_message': {'timestamp': '2025-01-01T11:00:00Z'},
                'message_count': 5,
                'owner_id': 'user_123',
                'applied_tags': ['tag_bug'],
                'available_tags': [{'id': 'tag_bug', 'name': 'bug'}]
            }
        ]

        mock_discord.get_thread_messages.return_value = [
            {'content': 'This is a bug report', 'timestamp': '2025-01-01T10:00:00Z'}
        ]

        # Mock filter engine
        mock_filter.should_include_thread.return_value = Mock(should_include=True, reason="Included")

        # Mock Linear API responses
        mock_linear.create_issue.return_value = {'id': 'linear_1', 'identifier': 'TEST-1'}

        # Create sync manager
        with patch.object(DiscordSyncManager, 'file_manager', self.file_manager):
            sync_manager = DiscordSyncManager(self.config)
            sync_manager.discord_client = mock_discord
            sync_manager.linear_client = mock_linear
            sync_manager.filter_engine = mock_filter

            # Execute sync
            result = sync_manager.sync_discord_threads()

            # Verify results
            self.assertIsNotNone(result)
            self.assertEqual(result.threads_processed, 1)
            self.assertEqual(result.threads_created, 1)
            self.assertEqual(result.threads_filtered, 0)
            self.assertEqual(len(result.errors), 0)

            # Verify API calls
            mock_discord.get_forum_threads.assert_called_once()
            mock_discord.get_thread_messages.assert_called_once_with('thread_1', limit=1)
            mock_linear.create_issue.assert_called_once()
            mock_filter.should_include_thread.assert_called_once()

    @patch('src.discord_sync_manager.DiscordClient')
    @patch('src.discord_sync_manager.LinearClient')
    @patch('src.discord_sync_manager.TagFilterEngine')
    def test_sync_workflow_with_filtered_threads(self, mock_filter_engine, mock_linear_client, mock_discord_client):
        """Test sync workflow when threads are filtered out."""
        # Setup mocks
        mock_discord = mock_discord_client.return_value
        mock_linear = mock_linear_client.return_value
        mock_filter = mock_filter_engine.return_value

        # Mock Discord API responses
        mock_discord.get_forum_threads.return_value = [
            {
                'id': 'thread_1',
                'name': 'Spam Thread',
                'thread_metadata': {'create_timestamp': '2025-01-01T10:00:00Z'},
                'most_recent_message': {'timestamp': '2025-01-01T11:00:00Z'},
                'message_count': 1,
                'owner_id': 'user_123',
                'applied_tags': ['tag_spam'],
                'available_tags': [{'id': 'tag_spam', 'name': 'spam'}]
            }
        ]

        mock_discord.get_thread_messages.return_value = [
            {'content': 'Spam content', 'timestamp': '2025-01-01T10:00:00Z'}
        ]

        # Mock filter engine to exclude thread
        mock_filter.should_include_thread.return_value = Mock(
            should_include=False,
            reason="Contains excluded tag: spam"
        )

        # Create sync manager
        with patch.object(DiscordSyncManager, 'file_manager', self.file_manager):
            sync_manager = DiscordSyncManager(self.config)
            sync_manager.discord_client = mock_discord
            sync_manager.linear_client = mock_linear
            sync_manager.filter_engine = mock_filter

            # Execute sync
            result = sync_manager.sync_discord_threads()

            # Verify results
            self.assertEqual(result.threads_processed, 1)
            self.assertEqual(result.threads_created, 0)
            self.assertEqual(result.threads_filtered, 1)
            self.assertEqual(len(result.errors), 0)

            # Verify Linear was not called
            mock_linear.create_issue.assert_not_called()

    @patch('src.discord_sync_manager.DiscordClient')
    @patch('src.discord_sync_manager.LinearClient')
    @patch('src.discord_sync_manager.TagFilterEngine')
    def test_sync_workflow_with_existing_mapping(self, mock_filter_engine, mock_linear_client, mock_discord_client):
        """Test sync workflow when Discord thread already has Linear mapping."""
        # Setup mocks
        mock_discord = mock_discord_client.return_value
        mock_linear = mock_linear_client.return_value
        mock_filter = mock_filter_engine.return_value

        # Mock Discord API responses
        mock_discord.get_forum_threads.return_value = [
            {
                'id': 'thread_1',
                'name': 'Existing Thread',
                'thread_metadata': {'create_timestamp': '2025-01-01T10:00:00Z'},
                'most_recent_message': {'timestamp': '2025-01-01T11:00:00Z'},
                'message_count': 5,
                'owner_id': 'user_123',
                'applied_tags': ['tag_bug'],
                'available_tags': [{'id': 'tag_bug', 'name': 'bug'}]
            }
        ]

        mock_discord.get_thread_messages.return_value = [
            {'content': 'Updated content', 'timestamp': '2025-01-01T11:00:00Z'}
        ]

        # Mock filter engine
        mock_filter.should_include_thread.return_value = Mock(should_include=True, reason="Included")

        # Mock existing mapping
        existing_mapping = {
            'linear_id': 'linear_1',
            'thread_id': 'thread_1',
            'discord_updated_at': '2025-01-01T10:00:00Z'  # Older than current
        }

        with patch.object(DiscordSyncManager, 'file_manager', self.file_manager):
            sync_manager = DiscordSyncManager(self.config)
            sync_manager.discord_client = mock_discord
            sync_manager.linear_client = mock_linear
            sync_manager.filter_engine = mock_filter

            # Mock existing mapping lookup
            sync_manager.file_manager.get_discord_thread_mapping = Mock(return_value=existing_mapping)

            # Mock Linear update
            mock_linear.update_issue.return_value = {'id': 'linear_1'}

            # Execute sync
            result = sync_manager.sync_discord_threads()

            # Verify results
            self.assertEqual(result.threads_processed, 1)
            self.assertEqual(result.threads_created, 0)
            self.assertEqual(result.threads_updated, 1)
            self.assertEqual(result.threads_filtered, 0)

            # Verify update was called, not create
            mock_linear.create_issue.assert_not_called()
            mock_linear.update_issue.assert_called_once()

    @patch('src.discord_sync_manager.DiscordClient')
    @patch('src.discord_sync_manager.LinearClient')
    @patch('src.discord_sync_manager.TagFilterEngine')
    def test_sync_workflow_error_handling(self, mock_filter_engine, mock_linear_client, mock_discord_client):
        """Test sync workflow error handling."""
        # Setup mocks
        mock_discord = mock_discord_client.return_value
        mock_linear = mock_linear_client.return_value
        mock_filter = mock_filter_engine.return_value

        # Mock Discord API to raise exception
        mock_discord.get_forum_threads.side_effect = Exception("Discord API Error")

        # Mock filter engine
        mock_filter.should_include_thread.return_value = Mock(should_include=True, reason="Included")

        with patch.object(DiscordSyncManager, 'file_manager', self.file_manager):
            sync_manager = DiscordSyncManager(self.config)
            sync_manager.discord_client = mock_discord
            sync_manager.linear_client = mock_linear
            sync_manager.filter_engine = mock_filter

            # Execute sync
            result = sync_manager.sync_discord_threads()

            # Verify error was captured
            self.assertEqual(result.threads_processed, 0)
            self.assertEqual(result.threads_created, 0)
            self.assertEqual(result.threads_updated, 0)
            self.assertEqual(len(result.errors), 1)
            self.assertIn("Discord API Error", result.errors[0])

    def test_transform_discord_to_linear_comprehensive(self):
        """Test comprehensive Discord to Linear transformation."""
        with patch('src.discord_sync_manager.DiscordClient'), \
             patch('src.discord_sync_manager.LinearClient'), \
             patch('src.discord_sync_manager.TagFilterEngine'):

            sync_manager = DiscordSyncManager(self.config)

            thread_data = DiscordThreadData(
                thread_id="123456789",
                thread_name="🐛 Bug: Login page crashes on mobile",
                created_at="2025-01-15T14:30:00Z",
                updated_at="2025-01-15T16:45:00Z",
                message_count=12,
                author_id="987654321",
                tags=["bug", "mobile", "urgent", "frontend"],
                first_message_content="Steps to reproduce:\n1. Open login page on mobile\n2. Enter credentials\n3. Click login\n4. App crashes\n\nExpected: Should login successfully\nActual: App crashes"
            )

            # Mock team mapping
            sync_manager.file_manager.get_discord_setting = Mock(return_value="team-frontend")

            result = sync_manager.transform_discord_to_linear(thread_data)

            # Verify title
            self.assertEqual(result['title'], "🐛 Bug: Login page crashes on mobile")

            # Verify description contains all required elements
            description = result['description']
            self.assertIn("Steps to reproduce:", description)
            self.assertIn("Thread ID: 123456789", description)
            self.assertIn("Created: 2025-01-15T14:30:00Z", description)
            self.assertIn("Messages: 12", description)
            self.assertIn("Tags: bug, mobile, urgent, frontend", description)

            # Verify metadata
            self.assertEqual(result['team_id'], "team-frontend")
            self.assertEqual(result['labels'], ["bug", "mobile", "urgent", "frontend"])
            self.assertEqual(result['priority'], 3)
            self.assertEqual(result['state'], "Todo")
            self.assertEqual(result['discord_thread_id'], "123456789")
            self.assertEqual(result['discord_created_at'], "2025-01-15T14:30:00Z")
            self.assertEqual(result['discord_updated_at'], "2025-01-15T16:45:00Z")
            self.assertEqual(result['discord_author_id'], "987654321")
            self.assertEqual(result['discord_message_count'], 12)

    def test_data_persistence_integration(self):
        """Test data persistence integration."""
        with patch('src.discord_sync_manager.DiscordClient'), \
             patch('src.discord_sync_manager.LinearClient'), \
             patch('src.discord_sync_manager.TagFilterEngine'):

            sync_manager = DiscordSyncManager(self.config)

            # Test storing Discord mapping
            sync_manager.file_manager.store_discord_thread_mapping(
                linear_id="linear_123",
                thread_id="discord_456",
                thread_name="Test Thread",
                discord_updated_at="2025-01-01T12:00:00Z",
                discord_created_at="2025-01-01T10:00:00Z",
                discord_author_id="user_789",
                discord_message_count=5
            )

            # Verify mapping can be retrieved
            mapping = sync_manager.file_manager.get_discord_thread_mapping("discord_456")
            self.assertIsNotNone(mapping)
            self.assertEqual(mapping['linear_id'], "linear_123")
            self.assertEqual(mapping['thread_id'], "discord_456")
            self.assertEqual(mapping['discord_message_count'], 5)

            # Test updating sync timestamp
            sync_manager._update_discord_sync_timestamp()

            # Verify timestamp methods work
            timestamp = sync_manager.file_manager.get_discord_last_sync_timestamp()
            self.assertIsNotNone(timestamp)

    def test_filter_integration_with_sync_workflow(self):
        """Test filter engine integration with sync workflow."""
        with patch('src.discord_sync_manager.DiscordClient'), \
             patch('src.discord_sync_manager.LinearClient'), \
             patch('src.discord_sync_manager.TagFilterEngine') as mock_filter_class:

            mock_filter = Mock()
            mock_filter_class.return_value = mock_filter

            sync_manager = DiscordSyncManager(self.config)

            # Configure filter to include threads with 'bug' tag
            mock_filter.should_include_thread.return_value = Mock(should_include=True, reason="Included")

            thread_data = DiscordThreadData(
                thread_id="123",
                thread_name="Bug Report",
                created_at="2025-01-01T10:00:00Z",
                updated_at="2025-01-01T11:00:00Z",
                message_count=3,
                author_id="456",
                tags=["bug", "urgent"],
                first_message_content="Bug description"
            )

            # Test filtering
            result = sync_manager._should_filter_thread(thread_data)

            # Verify filter was called with correct parameters
            mock_filter.should_include_thread.assert_called_once()
            call_args = mock_filter.should_include_thread.call_args
            self.assertEqual(call_args[1]['thread_tags'], ["bug", "urgent"])
            self.assertEqual(call_args[1]['message_count'], 3)
            self.assertIsInstance(call_args[1]['thread_age_days'], int)


if __name__ == '__main__':
    unittest.main()