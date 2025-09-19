"""Tests for Discord scheduling functionality in Scheduler."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
from src.scheduler import Scheduler
from src.config_manager import ConfigManager


class TestSchedulerDiscord(unittest.TestCase):
    """Test cases for Discord scheduling features."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary config with Discord enabled
        self.temp_env = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env')
        self.temp_env.write("""
DISCORD_ENABLED=true
DISCORD_BOT_TOKEN=test_token
DISCORD_GUILD_ID=123456789
DISCORD_FORUM_CHANNEL_ID=987654321
DISCORD_SYNC_INTERVAL=10
SYNC_INTERVAL=5
LOG_LEVEL=INFO
LINEAR_API_KEY=test
GITLAB_TOKEN=test
GITLAB_PROJECT_ID=test
""")
        self.temp_env.close()

        # Mock config
        with patch('src.config_manager.load_dotenv'):
            with patch('src.config_manager.ConfigManager.get_value') as mock_get:
                with patch('src.config_manager.ConfigManager.get_int_value') as mock_get_int:
                    with patch('src.config_manager.ConfigManager.discord_enabled', True):
                        mock_get.side_effect = lambda key, default=None: {
                            'LINEAR_API_KEY': 'test',
                            'GITLAB_TOKEN': 'test',
                            'GITLAB_PROJECT_ID': 'test',
                            'LOG_LEVEL': 'INFO',
                            'DISCORD_BOT_TOKEN': 'test_token',
                            'DISCORD_GUILD_ID': '123456789',
                            'DISCORD_FORUM_CHANNEL_ID': '987654321'
                        }.get(key, default)
                        mock_get_int.side_effect = lambda key, default: {
                            'SYNC_INTERVAL': 5,
                            'DISCORD_SYNC_INTERVAL': 10
                        }.get(key, default)

                        self.config = ConfigManager(self.temp_env.name)

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_env.name):
            os.unlink(self.temp_env.name)

    @patch('src.scheduler.BackgroundScheduler')
    @patch('src.scheduler.DiscordSyncManager')
    @patch('src.scheduler.SynchronizationManager')
    def test_scheduler_initializes_discord_job(self, mock_sync_manager, mock_discord_sync, mock_scheduler):
        """Test that scheduler initializes Discord job when enabled."""
        mock_scheduler_instance = Mock()
        mock_scheduler.return_value = mock_scheduler_instance

        scheduler = Scheduler(self.config)

        # Verify Discord sync manager is created
        mock_discord_sync.assert_called_once_with(self.config)

        # Verify Discord job is added
        mock_scheduler_instance.add_job.assert_any_call(
            func=scheduler._run_discord_sync,
            trigger=unittest.mock.ANY,  # IntervalTrigger
            id='discord_sync_job',
            name='Discord-Linear Sync',
            max_instances=1,
            replace_existing=True
        )

    @patch('src.scheduler.BackgroundScheduler')
    @patch('src.scheduler.DiscordSyncManager')
    @patch('src.scheduler.SynchronizationManager')
    def test_manual_discord_trigger(self, mock_sync_manager, mock_discord_sync, mock_scheduler):
        """Test manual Discord sync trigger."""
        mock_scheduler_instance = Mock()
        mock_scheduler.return_value = mock_scheduler_instance
        mock_discord_manager = Mock()
        mock_discord_sync.return_value = mock_discord_manager

        scheduler = Scheduler(self.config)

        # Mock lock acquisition
        with patch.object(scheduler, '_acquire_discord_lock', return_value=True):
            with patch.object(scheduler, '_release_discord_lock'):
                scheduler.trigger_manual_discord_sync()

                # Verify Discord sync is called
                mock_discord_manager.sync_discord_threads.assert_called_once()

    @patch('src.scheduler.BackgroundScheduler')
    @patch('src.scheduler.DiscordSyncManager')
    @patch('src.scheduler.SynchronizationManager')
    def test_pause_discord_job(self, mock_sync_manager, mock_discord_sync, mock_scheduler):
        """Test pausing Discord job."""
        mock_scheduler_instance = Mock()
        mock_job = Mock()
        mock_scheduler_instance.get_job.return_value = mock_job
        mock_scheduler.return_value = mock_scheduler_instance

        scheduler = Scheduler(self.config)

        result = scheduler.pause_discord_job()

        self.assertTrue(result)
        mock_job.pause.assert_called_once()

    @patch('src.scheduler.BackgroundScheduler')
    @patch('src.scheduler.DiscordSyncManager')
    @patch('src.scheduler.SynchronizationManager')
    def test_resume_discord_job(self, mock_sync_manager, mock_discord_sync, mock_scheduler):
        """Test resuming Discord job."""
        mock_scheduler_instance = Mock()
        mock_job = Mock()
        mock_scheduler_instance.get_job.return_value = mock_job
        mock_scheduler.return_value = mock_scheduler_instance

        scheduler = Scheduler(self.config)

        result = scheduler.resume_discord_job()

        self.assertTrue(result)
        mock_job.resume.assert_called_once()

    @patch('src.scheduler.BackgroundScheduler')
    @patch('src.scheduler.DiscordSyncManager')
    @patch('src.scheduler.SynchronizationManager')
    def test_get_discord_job_status(self, mock_sync_manager, mock_discord_sync, mock_scheduler):
        """Test getting Discord job status."""
        mock_scheduler_instance = Mock()
        mock_job = Mock()
        mock_job.running = True
        mock_job.next_run_time = None
        mock_scheduler_instance.get_job.return_value = mock_job
        mock_scheduler.return_value = mock_scheduler_instance

        scheduler = Scheduler(self.config)

        status = scheduler.get_discord_job_status()

        self.assertTrue(status['enabled'])
        self.assertTrue(status['exists'])
        self.assertTrue(status['running'])

    @patch('src.scheduler.BackgroundScheduler')
    @patch('src.scheduler.DiscordSyncManager')
    @patch('src.scheduler.SynchronizationManager')
    @patch('src.scheduler.time.sleep')
    def test_discord_sync_with_retry(self, mock_sleep, mock_sync_manager, mock_discord_sync, mock_scheduler):
        """Test Discord sync with retry mechanism."""
        mock_scheduler_instance = Mock()
        mock_scheduler.return_value = mock_scheduler_instance
        mock_discord_manager = Mock()

        # First two calls fail, third succeeds
        mock_discord_manager.sync_discord_threads.side_effect = [Exception("Fail"), Exception("Fail"), None]
        mock_discord_sync.return_value = mock_discord_manager

        scheduler = Scheduler(self.config)

        # Mock lock methods
        with patch.object(scheduler, '_acquire_discord_lock', return_value=True):
            with patch.object(scheduler, '_release_discord_lock'):
                scheduler._run_discord_sync_with_retry()

                # Verify retry attempts
                self.assertEqual(mock_discord_manager.sync_discord_threads.call_count, 3)
                # Verify sleep calls for backoff
                self.assertEqual(mock_sleep.call_count, 2)

    @patch('src.scheduler.BackgroundScheduler')
    @patch('src.scheduler.DiscordSyncManager')
    @patch('src.scheduler.SynchronizationManager')
    def test_discord_lock_mechanism(self, mock_sync_manager, mock_discord_sync, mock_scheduler):
        """Test Discord-specific lock mechanism."""
        mock_scheduler_instance = Mock()
        mock_scheduler.return_value = mock_scheduler_instance

        scheduler = Scheduler(self.config)

        # Test acquiring lock
        with patch('src.scheduler.os.path.exists', return_value=False):
            with patch('src.scheduler.open', unittest.mock.mock_open()) as mock_file:
                with patch('src.scheduler.os.getpid', return_value=12345):
                    result = scheduler._acquire_discord_lock()
                    self.assertTrue(result)
                    mock_file().write.assert_called_with('12345')

        # Test releasing lock
        with patch('src.scheduler.os.path.exists', return_value=True):
            with patch('src.scheduler.os.remove') as mock_remove:
                scheduler._release_discord_lock()
                mock_remove.assert_called_once_with('.discord_sync_lock')


if __name__ == '__main__':
    unittest.main()