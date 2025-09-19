"""Tests for Discord web interface functionality."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from flask import Flask

from src.web_interface import WebInterface
from src.config_manager import ConfigManager
from src.sync_manager import SynchronizationManager
from src.file_manager import FileManager
from src.scheduler import Scheduler
from src.discord_sync_manager import DiscordSyncManager
from src.discord_client import DiscordClient


class TestDiscordWebInterface(unittest.TestCase):
    """Test cases for Discord web interface routes and functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock dependencies
        self.config = Mock(spec=ConfigManager)
        self.config.discord_enabled = True

        self.sync_manager = Mock(spec=SynchronizationManager)
        self.file_manager = Mock(spec=FileManager)
        self.scheduler = Mock(spec=Scheduler)

        # Mock Discord components
        self.discord_sync_manager = Mock(spec=DiscordSyncManager)
        self.discord_client = Mock(spec=DiscordClient)

        # Create web interface with mocked Discord components
        self.web_interface = WebInterface(
            config=self.config,
            sync_manager=self.sync_manager,
            file_manager=self.file_manager,
            scheduler=self.scheduler,
            discord_sync_manager=self.discord_sync_manager,
            discord_client=self.discord_client
        )

        self.app = self.web_interface.app
        self.client = self.app.test_client()

    def test_discord_routes_exist(self):
        """Test that Discord routes are properly registered."""
        # Mock mappings for /discord-mappings
        self.file_manager.get_all_discord_mappings.return_value = []

        # Test Discord settings route
        response = self.client.get('/discord-settings')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Discord Settings', response.data)

        # Test Discord mappings route
        response = self.client.get('/discord-mappings')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Discord Thread Mappings', response.data)

        # Test Discord status route
        response = self.client.get('/discord-status')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Discord Integration Status', response.data)

    def test_discord_api_routes(self):
        """Test Discord API endpoints."""
        # Mock return values
        self.discord_sync_manager.get_discord_sync_status.return_value = {
            'total_discord_mappings': 5,
            'last_discord_sync_timestamp': '2025-01-01T00:00:00Z',
            'discord_enabled': True
        }
        self.discord_client.test_connectivity.return_value = True
        self.scheduler.get_discord_job_status.return_value = {
            'enabled': True,
            'exists': True,
            'running': False,
            'next_run': '2025-01-01T01:00:00Z',
            'paused': False
        }

        # Test Discord status API
        response = self.client.get('/api/discord-status')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['enabled'])
        self.assertTrue(data['connectivity'])
        self.assertEqual(data['sync_status']['total_discord_mappings'], 5)

        # Test Discord settings API
        self.file_manager.get_all_discord_settings.return_value = {
            'DISCORD_TEAM_MAPPINGS': {'value': {'bug': 'team-bugs'}, 'description': 'Team mappings'},
            'DISCORD_SYNC_ENABLED': {'value': 'true', 'description': 'Sync enabled'}
        }

        response = self.client.get('/api/discord-settings')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['enabled'])
        self.assertIn('DISCORD_TEAM_MAPPINGS', data['settings'])

    def test_discord_settings_post_endpoints(self):
        """Test Discord settings POST endpoints."""
        # Test team mappings update
        self.file_manager.set_discord_setting.return_value = None

        response = self.client.post('/discord-settings',
                                  data={'action': 'update_team_mappings', 'tag_bug': 'team-bugs'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('Team mappings updated', data['message'])

        # Test filter rules update
        response = self.client.post('/discord-settings',
                                  data={
                                      'action': 'update_filter_rules',
                                      'min_message_count': '1',
                                      'max_age_days': '365',
                                      'exclude_tags': 'spam,test'
                                  })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')

        # Test general settings update
        response = self.client.post('/discord-settings',
                                  data={
                                      'action': 'update_general_settings',
                                      'default_team': 'default_team',
                                      'sync_enabled': 'true'
                                  })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')

    def test_discord_sync_trigger(self):
        """Test Discord sync trigger endpoint."""
        # Mock scheduler trigger
        self.scheduler.trigger_manual_discord_sync.return_value = None

        response = self.client.post('/trigger-discord-sync')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('Discord sync triggered', data['message'])

    def test_discord_mapping_delete(self):
        """Test Discord mapping deletion."""
        # Mock mapping lookup
        self.file_manager.get_all_discord_mappings.return_value = [
            {'thread_id': '123456789', 'linear_id': 'linear-123'}
        ]
        self.file_manager.remove_discord_thread_mapping.return_value = True

        response = self.client.delete('/api/discord-mappings/123456789')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')

        # Test mapping not found
        self.file_manager.get_all_discord_mappings.return_value = []
        response = self.client.delete('/api/discord-mappings/nonexistent')
        self.assertEqual(response.status_code, 404)

    def test_discord_connectivity_test(self):
        """Test Discord connectivity test endpoint."""
        self.discord_client.test_connectivity.return_value = True

        response = self.client.get('/api/discord-test-connectivity')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('latency', data)

    def test_discord_diagnostics(self):
        """Test Discord diagnostics endpoint."""
        # Mock all diagnostic components
        self.discord_client.test_connectivity.return_value = True
        self.file_manager.get_all_discord_settings.return_value = {'setting1': 'value1'}
        self.file_manager.get_all_discord_mappings.return_value = [{'mapping1': 'value1'}]
        self.discord_sync_manager.get_discord_sync_status.return_value = {
            'last_discord_sync_timestamp': '2025-01-01T00:00:00Z'
        }

        response = self.client.get('/api/discord-diagnostics')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('results', data)
        self.assertIn('api_connectivity', data['results'])
        self.assertIn('settings_configured', data['results'])
        self.assertIn('mappings_exist', data['results'])
        self.assertIn('sync_status', data['results'])

    def test_discord_error_handling(self):
        """Test error handling when Discord components are not available."""
        # Create web interface without Discord components
        web_interface_no_discord = WebInterface(
            config=self.config,
            sync_manager=self.sync_manager,
            file_manager=self.file_manager,
            scheduler=self.scheduler,
            discord_sync_manager=None,
            discord_client=None
        )

        client_no_discord = web_interface_no_discord.app.test_client()

        # Test routes return error when Discord not enabled
        response = client_no_discord.get('/discord-settings')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Discord integration not enabled', response.data)

        # Test API endpoints return error
        response = client_no_discord.get('/api/discord-status')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertFalse(data['enabled'])
        self.assertIn('not configured', data['error'])

    def test_template_rendering(self):
        """Test that templates render without errors."""
        # Mock data for template rendering
        self.file_manager.get_all_discord_mappings.return_value = [
            {
                'thread_id': '123456789',
                'thread_name': 'Test Thread',
                'linear_id': 'linear-123',
                'discord_created_at': '2025-01-01T00:00:00Z',
                'discord_updated_at': '2025-01-01T01:00:00Z',
                'discord_message_count': 5,
                'discord_author_id': '987654321'
            }
        ]

        # Test Discord mappings template
        response = self.client.get('/discord-mappings')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Test Thread', response.data)
        self.assertIn(b'linear-123', response.data)

        # Test Discord status template
        response = self.client.get('/discord-status')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Discord Integration Status', response.data)

    def test_form_validation(self):
        """Test form validation for Discord settings."""
        # Test invalid numeric values
        response = self.client.post('/discord-settings',
                                  data={
                                      'action': 'update_filter_rules',
                                      'min_message_count': 'invalid',
                                      'max_age_days': '365',
                                      'exclude_tags': ''
                                  })
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
        self.assertIn('Invalid numeric values', data['message'])

        # Test negative values
        response = self.client.post('/discord-settings',
                                  data={
                                      'action': 'update_filter_rules',
                                      'min_message_count': '-1',
                                      'max_age_days': '365',
                                      'exclude_tags': ''
                                  })
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')


if __name__ == '__main__':
    unittest.main()