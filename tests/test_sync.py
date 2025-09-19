"""Unit tests for the Linear-GitLab Synchronization Application."""

import os
import tempfile
import pytest
from unittest.mock import Mock, patch
from src.config_manager import ConfigManager
from src.db_manager import DatabaseManager
from src.sync_manager import SynchronizationManager
from src.linear_client import LinearClient
from src.gitlab_client import GitLabClient

def test_config_manager():
    """Test configuration manager loads values correctly."""
    # Create temporary .env file
    env_content = """
    LINEAR_API_KEY=test_linear_key
    GITLAB_TOKEN=test_gitlab_token
    GITLAB_PROJECT_ID=123
    SYNC_INTERVAL=300
    DATABASE_PATH=test.db
    LOG_LEVEL=INFO
    DRY_RUN=true
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write(env_content)
        env_file = f.name

    try:
        config = ConfigManager(env_file)
        assert config.linear_api_key == "test_linear_key"
        assert config.gitlab_token == "test_gitlab_token"
        assert config.gitlab_project_id == "123"
        assert config.sync_interval == 300
        assert config.database_path == "test.db"
        assert config.log_level == "INFO"
        assert config.dry_run == True
    finally:
        os.unlink(env_file)

def test_database_operations():
    """Test database operations."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as db_file:
        db_path = db_file.name

    try:
        # Mock config
        config = Mock()
        config.database_path = db_path

        db = DatabaseManager(config)
        db.initialize_database()  # Assuming modified to public for test

        # Test storing and retrieving mapping
        db.store_issue_mapping("LIN-123", "456")
        mapping = db.get_issue_mapping("LIN-123")
        assert mapping is not None
        assert mapping['linear_id'] == "LIN-123"
        assert mapping['gitlab_id'] == "456"

        # Test logging
        db.log_sync_operation("test_op", "success", "Test details")
        logs = db.get_recent_logs(1)
        assert len(logs) == 1
        assert logs[0]['operation'] == "test_op"

    finally:
        os.unlink(db_path)

@patch('src.gitlab_client.requests.post')
def test_gitlab_client_create_issue(mock_post):
    """Test GitLab client issue creation."""
    # Mock successful API response
    mock_response = Mock()
    mock_response.json.return_value = {
        'id': 123,
        'iid': 456,
        'title': '[MAU-LIN-123] Test Issue'
    }
    mock_post.return_value = mock_response

    config = Mock()
    config.gitlab_token = "test_token"
    config.gitlab_project_id = "123"

    client = GitLabClient(config)
    issue_id = client.create_issue("LIN-123", "Test Issue", "Test description")

    assert issue_id == "456"
    mock_post.assert_called_once()

@patch('src.linear_client.requests.post')
def test_linear_client_get_issues(mock_post):
    """Test Linear client issue fetching."""
    # Mock GraphQL response
    mock_response = Mock()
    mock_response.json.return_value = {
        'data': {
            'teams': {
                'nodes': [{'id': 'team_mau', 'name': 'MAU'}]
            }
        }
    }
    mock_post.return_value = mock_response

    config = Mock()
    config.linear_api_key = "test_key"

    client = LinearClient(config)
    team_id = client.get_mau_team_id()

    assert team_id == "team_mau"
    mock_post.assert_called_once_with(
        "https://api.linear.app/graphql",
        json={'query': '\n        query {\n          teams {\n            nodes {\n              id\n              name\n            }\n          }\n        }\n        ', 'variables': {}},
        timeout=15
    )

def test_sync_manager_get_new_issues():
    """Test sync manager filters new issues."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as db_file:
        db_path = db_file.name

    try:
        config = Mock()
        config.database_path = db_path

        # Mock LinearClient
        linear_client = Mock()
        linear_client.get_all_mau_issues_since.return_value = [
            {'id': 'LIN-1', 'title': 'New Issue'},
            {'id': 'LIN-2', 'title': 'Existing Issue'}
        ]

        # Mock GitLabClient
        gitlab_client = Mock()

        db = DatabaseManager(config)
        db.store_issue_mapping("LIN-2", "789")  # Mark as existing

        sync_manager = SynchronizationManager(config)
        sync_manager.linear_client = linear_client
        sync_manager.gitlab_client = gitlab_client

        # Should return only LIN-1
        new_issues = sync_manager.get_new_linear_issues()
        assert len(new_issues) == 1
        assert new_issues[0]['id'] == 'LIN-1'

    finally:
        os.unlink(db_path)

if __name__ == "__main__":
    pytest.main([__file__])