"""Discord Synchronization Manager for syncing Discord forum threads to Linear issues."""

import threading
import time
import difflib
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from src.config_manager import ConfigManager
from src.file_manager import FileManager
from src.discord_client import DiscordClient
from src.linear_client import LinearClient
from src.error_logger import ErrorLogger
from src.tag_filter_engine import TagFilterEngine


@dataclass
class DiscordThreadData:
    """Data structure for Discord thread information."""
    thread_id: str
    thread_name: str
    created_at: str
    updated_at: str
    message_count: int
    author_id: str
    tags: List[str]
    first_message_content: str


@dataclass
class SyncState:
    """Data structure for synchronization state management."""
    last_sync_timestamp: Optional[str] = None
    threads_processed: int = 0
    threads_created: int = 0
    threads_updated: int = 0
    threads_filtered: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def descriptions_equal(desc1: str, desc2: str, threshold: float = 0.95) -> bool:
    """Compare two descriptions using fuzzy matching to avoid false updates.

    Args:
        desc1: First description
        desc2: Second description
        threshold: Similarity threshold (0.0 to 1.0)

    Returns:
        True if descriptions are similar enough, False otherwise
    """
    if not desc1 and not desc2:
        return True
    if not desc1 or not desc2:
        return False

    # Normalize descriptions by stripping whitespace
    desc1 = desc1.strip()
    desc2 = desc2.strip()

    # Use difflib's SequenceMatcher for fuzzy comparison
    ratio = difflib.SequenceMatcher(None, desc1, desc2).ratio()
    return ratio >= threshold


class DiscordSyncManager:
    """Manages synchronization of Discord forum threads to Linear issues."""

    def __init__(self, config: ConfigManager) -> None:
        """Initialize Discord Sync Manager.

        Args:
            config: Configuration manager instance
        """
        self.config = config
        self.file_manager = FileManager(config)
        self.discord_client = DiscordClient(config)
        self.linear_client = LinearClient(config)
        self.error_logger = ErrorLogger(config)
        self.filter_engine = TagFilterEngine(config, self.file_manager, self.error_logger)

        # Threading lock for sync operations
        self._sync_lock = threading.RLock()

        # Initialize sync state
        self.sync_state = SyncState()

    def sync_discord_threads(self, since_timestamp: Optional[str] = None) -> SyncState:
        """Orchestrate the full synchronization process for Discord threads to Linear issues.

        Args:
            since_timestamp: ISO timestamp string for incremental sync (optional)

        Returns:
            SyncState object with operation results
        """
        with self._sync_lock:
            try:
                self.error_logger.log('info', "Starting Discord thread synchronization")
                self.sync_state = SyncState(last_sync_timestamp=since_timestamp)

                # Get Discord threads
                threads = self._get_discord_threads_since(since_timestamp)
                self.sync_state.threads_processed = len(threads)
                self.error_logger.log('info', f"Retrieved {len(threads)} threads from Discord forum")

                # Get team ID for Linear
                team_name = self.config.get_value('LINEAR_TEAM_NAME', 'default_team')
                team_id, _ = self.linear_client.get_team_id(team_name)

                # Get all existing Linear issues for comparison
                linear_issues = self.linear_client.get_linear_issues_for_team_all_states(team_id)
                self.error_logger.log('info', f"Fetched {len(linear_issues)} existing Linear issues for comparison")

                # Process each thread
                created = []
                updated = []
                skipped = []

                for thread_data in threads:
                    try:
                        # Apply filtering
                        if self._should_filter_thread(thread_data):
                            self.sync_state.threads_filtered += 1
                            continue

                        # Transform to Linear format
                        linear_issue_data = self.transform_discord_to_linear(thread_data)

                        # Sync to Linear with comparison logic
                        action, linear_id = self._sync_thread_to_linear_with_comparison(linear_issue_data, linear_issues)

                        if action == 'created':
                            self.sync_state.threads_created += 1
                            created.append(thread_data.thread_name)
                        elif action == 'updated':
                            self.sync_state.threads_updated += 1
                            updated.append(thread_data.thread_name)
                        elif action == 'skipped':
                            skipped.append(thread_data.thread_name)

                        self.error_logger.log('debug', f"Thread '{thread_data.thread_name}': {action}")

                    except Exception as e:
                        error_msg = f"Failed to sync thread {thread_data.thread_id}: {str(e)}"
                        self.sync_state.errors.append(error_msg)
                        self.error_logger.log('error', error_msg)

                # Update sync timestamp
                self._update_discord_sync_timestamp()

                # Log summary
                total_actions = len(created) + len(updated)
                self.error_logger.log('info',
                    f"Discord sync completed: {len(created)} created, {len(updated)} updated, "
                    f"{len(skipped)} skipped, {self.sync_state.threads_filtered} filtered, "
                    f"{len(self.sync_state.errors)} errors")

                return self.sync_state

            except Exception as e:
                self.error_logger.log('error', f"Discord sync orchestration failed: {str(e)}")
                raise

    def transform_discord_to_linear(self, thread_data: DiscordThreadData) -> Dict[str, Any]:
        """Transform Discord thread data to Linear issue format.

        Args:
            thread_data: Discord thread data structure

        Returns:
            Dictionary with Linear issue fields
        """
        try:
            # Build title with tags as prefix
            tag_prefix = ' '.join(f"[{tag}]" for tag in thread_data.tags) if thread_data.tags else ''
            title = f"{tag_prefix} {thread_data.thread_name}".strip() if tag_prefix else thread_data.thread_name
            if not title:
                title = f"Discord Thread {thread_data.thread_id}"

            # Build description from first message and metadata
            description = thread_data.first_message_content or ""

            # Add Discord metadata section
            description += f"\n\n--- Imported from Discord ---\n"
            if thread_data.author_id:
                creator_name = "Unknown"
                try:
                    user_info = self._get_discord_user_info(thread_data.author_id)
                    creator_name = user_info or f"ID: {thread_data.author_id}"
                except Exception:
                    creator_name = f"ID: {thread_data.author_id}"
                description += f"Creator: {creator_name}\n"
            description += f"Date Created: {thread_data.created_at}\n"
            description += f"Tags: {', '.join(thread_data.tags) if thread_data.tags else 'None'}\n"
            description += f"Thread ID: {thread_data.thread_id}\n"
            description += f"Message Count: {thread_data.message_count}\n"

            # Map Discord tags to Linear labels (disabled to avoid UUID validation errors)
            linear_labels = []
            # if thread_data.tags:
            #     linear_labels = thread_data.tags

            # Determine team and project mappings
            team_id = self._get_team_mapping_for_tags(thread_data.tags)

            return {
                'title': title,
                'description': description,
                'team_id': team_id,
                'labels': linear_labels,
                'priority': 3,  # Default priority
                'discord_thread_id': thread_data.thread_id,
                'discord_created_at': thread_data.created_at,
                'discord_updated_at': thread_data.updated_at,
                'discord_author_id': thread_data.author_id,
                'discord_message_count': thread_data.message_count
            }

        except Exception as e:
            self.error_logger.log('error', f"Failed to transform Discord thread {thread_data.thread_id}: {str(e)}")
            raise

    def _get_discord_threads_since(self, since_timestamp: Optional[str] = None) -> List[DiscordThreadData]:
        """Retrieve Discord threads since the specified timestamp.

        Args:
            since_timestamp: ISO timestamp string

        Returns:
            List of DiscordThreadData objects
        """
        threads = []

        try:
            # Get active forum threads
            active_threads = self.discord_client.get_forum_threads()

            # Get archived threads if doing full sync
            if not since_timestamp:
                archived_threads = self.discord_client.get_archived_threads()
                all_threads = active_threads + archived_threads
            else:
                all_threads = active_threads

            for thread in all_threads:
                try:
                    thread_data = self._extract_thread_data(thread, since_timestamp)
                    if thread_data:
                        threads.append(thread_data)
                except Exception as e:
                    self.error_logger.log('warning', f"Failed to extract data from thread {thread.get('id', 'unknown')}: {str(e)}")

        except Exception as e:
            self.error_logger.log('error', f"Failed to retrieve Discord threads: {str(e)}")
            raise

        return threads

    def _extract_thread_data(self, thread: Dict, since_timestamp: Optional[str] = None) -> Optional[DiscordThreadData]:
        """Extract DiscordThreadData from raw Discord API response.

        Args:
            thread: Raw Discord thread dictionary
            since_timestamp: Timestamp filter

        Returns:
            DiscordThreadData object or None if filtered out
        """
        thread_id = thread.get('id')
        if not thread_id:
            return None

        # Apply timestamp filter if provided
        if since_timestamp:
            thread_timestamp = thread.get('thread_metadata', {}).get('create_timestamp')
            if thread_timestamp and thread_timestamp < since_timestamp:
                return None

        # Get thread messages for content
        messages = self.discord_client.get_thread_messages(thread_id, limit=1)
        first_message_content = ""
        if messages:
            first_message = messages[0]
            first_message_content = first_message.get('content', '')

        # Extract tags from applied_tags
        tags = []
        applied_tags = thread.get('applied_tags', [])
        for tag_id in applied_tags:
            tag_info = thread.get('available_tags', [])
            for tag in tag_info:
                if tag.get('id') == tag_id:
                    tags.append(tag.get('name', f'tag_{tag_id}'))
                    break

        # Get creator information
        creator_name = "Unknown"
        author_id = thread.get('owner_id', '')
        if author_id:
            try:
                # Get user info from Discord API
                user_info = self._get_discord_user_info(author_id)
                creator_name = user_info or f"ID: {author_id}"
            except Exception as e:
                self.error_logger.log('warning', f"Failed to get user info for {author_id}: {str(e)}")
                creator_name = f"ID: {author_id}"

        # Get creation date
        creation_date = ""
        create_timestamp = thread.get('thread_metadata', {}).get('create_timestamp')
        if create_timestamp:
            try:
                # Parse ISO timestamp
                dt = datetime.fromisoformat(create_timestamp.replace('Z', '+00:00'))
                creation_date = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            except (ValueError, TypeError):
                creation_date = create_timestamp

        return DiscordThreadData(
            thread_id=thread_id,
            thread_name=thread.get('name', ''),
            created_at=creation_date,
            updated_at=thread.get('most_recent_message', {}).get('timestamp', ''),
            message_count=thread.get('message_count', 0),
            author_id=author_id,
            tags=tags,
            first_message_content=first_message_content
        )

    def _should_filter_thread(self, thread_data: DiscordThreadData) -> bool:
        """Determine if a thread should be filtered out based on rules.

        Args:
            thread_data: Thread data to evaluate

        Returns:
            True if thread should be filtered out, False otherwise
        """
        # Allow threads with content even if message_count is 0
        if thread_data.first_message_content and thread_data.message_count == 0:
            return False

        # Use TagFilterEngine for filtering
        from datetime import datetime, timedelta

        # Calculate thread age in days
        thread_age_days = 0
        if thread_data.created_at:
            try:
                created_dt = datetime.fromisoformat(thread_data.created_at.replace('Z', '+00:00'))
                thread_age_days = (datetime.utcnow() - created_dt).days
            except (ValueError, TypeError):
                thread_age_days = 0

        filter_result = self.filter_engine.should_include_thread(
            thread_tags=thread_data.tags,
            message_count=thread_data.message_count,
            thread_age_days=thread_age_days
        )

        # Log filtering decision
        if not filter_result.should_include:
            self.error_logger.log('debug', f"Thread {thread_data.thread_id} filtered: {filter_result.reason}")

        return not filter_result.should_include

    def _get_team_mapping_for_tags(self, tags: List[str]) -> str:
        """Get Linear team ID based on Discord thread tags.

        Args:
            tags: List of Discord tags

        Returns:
            Linear team ID string
        """
        # Get team mappings from Discord settings
        team_mappings = self.file_manager.get_discord_setting('DISCORD_TEAM_MAPPINGS')
        if team_mappings and tags:
            for tag in tags:
                if tag in team_mappings:
                    # Ensure it's a UUID, if it's a name, resolve it
                    team_value = team_mappings[tag]
                    if not team_value.startswith('team-'):  # Assume UUID starts with team-
                        try:
                            resolved_id, _ = self.linear_client.get_team_id(team_value)
                            team_mappings[tag] = resolved_id
                            return resolved_id
                        except Exception:
                            self.error_logger.log('warning', f"Could not resolve team name {team_value} to ID")
                    return team_value

        # Default team from Discord settings or config
        default_team_name = self.file_manager.get_discord_setting('DISCORD_DEFAULT_TEAM')
        if default_team_name:
            try:
                default_team_id, _ = self.linear_client.get_team_id(default_team_name)
                return default_team_id
            except Exception as e:
                self.error_logger.log('warning', f"Could not resolve default team {default_team_name}: {e}")

        # Fallback to configured team name
        default_name = self.config.get_value('LINEAR_TEAM_NAME', 'Abobatest')
        try:
            default_team_id, _ = self.linear_client.get_team_id(default_name)
            return default_team_id
        except Exception as e:
            self.error_logger.log('error', f"Failed to get team ID for {default_name}: {e}")
            raise Exception(f"Cannot determine valid Linear team ID: {e}")

    def _sync_thread_to_linear(self, linear_issue_data: Dict[str, Any]) -> Tuple[str, str]:
        """Sync transformed Discord data to Linear issue.

        Args:
            linear_issue_data: Transformed Linear issue data

        Returns:
            Tuple of (action, linear_id)
        """
        thread_id = linear_issue_data['discord_thread_id']

        # Check if we already have a mapping for this thread
        existing_mapping = self.file_manager.get_discord_thread_mapping(thread_id)

        if existing_mapping:
            linear_id = existing_mapping['linear_id']
            # Check if thread has been updated since last sync
            if self._thread_needs_update(linear_issue_data, existing_mapping):
                return self._update_linear_issue(linear_id, linear_issue_data)
            else:
                return 'skip', linear_id
        else:
            return self._create_linear_issue(linear_issue_data)

    def _sync_thread_to_linear_with_comparison(self, linear_issue_data: Dict[str, Any], linear_issues: Dict[str, Dict]) -> Tuple[str, str]:
        """Sync Discord thread to Linear with comparison against existing issues.

        Args:
            linear_issue_data: Transformed Linear issue data
            linear_issues: Dictionary of existing Linear issues keyed by title

        Returns:
            Tuple of (action, linear_id)
        """
        thread_title = linear_issue_data['title']
        thread_description = linear_issue_data['description']
        thread_id = linear_issue_data['discord_thread_id']

        # Check if we already have a mapping for this thread
        existing_mapping = self.file_manager.get_discord_thread_mapping(thread_id)

        if existing_mapping:
            # Existing mapping - check if it still exists in Linear
            linear_id = existing_mapping['linear_id']
            existing_issue = linear_issues.get(thread_title)

            if existing_issue and existing_issue['id'] == linear_id:
                # Issue still exists, check if description changed
                existing_desc = existing_issue.get('description', '')
                if not descriptions_equal(existing_desc, thread_description):
                    self.error_logger.log('info', f"Updating '{thread_title}' - descriptions differ")
                    return self._update_linear_issue(linear_id, linear_issue_data)
                else:
                    self.error_logger.log('debug', f"Skipping '{thread_title}' - descriptions match")
                    return 'skipped', linear_id
            else:
                # Mapping exists but issue not found or title changed - recreate
                self.error_logger.log('warning', f"Recreating '{thread_title}' - existing issue not found")
                return self._create_linear_issue(linear_issue_data)

        else:
            # No existing mapping - check if title matches existing issue
            if thread_title in linear_issues:
                existing_issue = linear_issues[thread_title]
                existing_desc = existing_issue.get('description', '')

                # Check if descriptions are similar
                if descriptions_equal(existing_desc, thread_description):
                    # Similar content - create mapping to existing issue
                    linear_id = existing_issue['id']
                    self.file_manager.store_discord_thread_mapping(
                        linear_id=linear_id,
                        thread_id=thread_id,
                        thread_name=thread_title,
                        discord_updated_at=linear_issue_data.get('discord_updated_at', ''),
                        discord_created_at=linear_issue_data.get('discord_created_at', ''),
                        discord_author_id=linear_issue_data.get('discord_author_id', ''),
                        discord_message_count=linear_issue_data.get('discord_message_count', 0)
                    )
                    self.error_logger.log('info', f"Mapped '{thread_title}' to existing Linear issue")
                    return 'skipped', linear_id
                else:
                    # Different content - update existing issue
                    self.error_logger.log('info', f"Updating existing '{thread_title}' - different content")
                    linear_id = existing_issue['id']
                    updated_issue = self._update_linear_issue(linear_id, linear_issue_data)
                    return updated_issue
            else:
                # No matching title - create new issue
                self.error_logger.log('info', f"Creating new issue '{thread_title}'")
                return self._create_linear_issue(linear_issue_data)

    def _thread_needs_update(self, linear_issue_data: Dict[str, Any], existing_mapping: Dict[str, Any]) -> bool:
        """Check if a Discord thread needs to be updated in Linear.

        Args:
            linear_issue_data: Current thread data
            existing_mapping: Existing mapping data

        Returns:
            True if update is needed, False otherwise
        """
        # Compare updated timestamps
        current_updated = linear_issue_data.get('discord_updated_at', '')
        stored_updated = existing_mapping.get('discord_updated_at', '')

        return current_updated != stored_updated

    def _create_linear_issue(self, linear_issue_data: Dict[str, Any]) -> Tuple[str, str]:
        """Create a new Linear issue from Discord thread data.

        Args:
            linear_issue_data: Issue data for creation

        Returns:
            Tuple of (action, linear_id)
        """
        try:
            # Create issue in Linear
            linear_issue = self.linear_client.create_issue(
                team_id=linear_issue_data['team_id'],
                title=linear_issue_data['title'],
                description=linear_issue_data['description'],
                priority=linear_issue_data.get('priority', 3)
                # labels=linear_issue_data.get('labels', [])  # Disabled to avoid UUID validation errors
            )

            linear_id = linear_issue['id']

            # Store mapping with Discord metadata
            self.file_manager.store_discord_thread_mapping(
                linear_id=linear_id,
                thread_id=linear_issue_data['discord_thread_id'],
                thread_name=linear_issue_data.get('title', ''),
                discord_updated_at=linear_issue_data.get('discord_updated_at', ''),
                discord_created_at=linear_issue_data.get('discord_created_at', ''),
                discord_author_id=linear_issue_data.get('discord_author_id', ''),
                discord_message_count=linear_issue_data.get('discord_message_count', 0)
            )

            return 'created', linear_id

        except Exception as e:
            self.error_logger.log('error', f"Failed to create Linear issue for Discord thread: {str(e)}")
            raise

    def _update_linear_issue(self, linear_id: str, linear_issue_data: Dict[str, Any]) -> Tuple[str, str]:
        """Update an existing Linear issue with Discord thread changes.

        Args:
            linear_id: Linear issue ID
            linear_issue_data: Updated issue data

        Returns:
            Tuple of (action, linear_id)
        """
        try:
            # Update the Linear issue (no state change)
            self.linear_client.update_issue(
                issue_id=linear_id,
                title=linear_issue_data['title'],
                description=linear_issue_data['description'],
                priority=linear_issue_data.get('priority', 3)
                # labels=linear_issue_data.get('labels', [])  # Disabled to avoid UUID validation errors
            )

            # Update mapping with new Discord metadata
            self.file_manager.store_discord_thread_mapping(
                linear_id=linear_id,
                thread_id=linear_issue_data['discord_thread_id'],
                thread_name=linear_issue_data.get('title', ''),
                discord_updated_at=linear_issue_data.get('discord_updated_at', ''),
                discord_created_at=linear_issue_data.get('discord_created_at', ''),
                discord_author_id=linear_issue_data.get('discord_author_id', ''),
                discord_message_count=linear_issue_data.get('discord_message_count', 0)
            )

            return 'updated', linear_id

        except Exception as e:
            self.error_logger.log('error', f"Failed to update Linear issue {linear_id}: {str(e)}")
            raise

    def _update_discord_sync_timestamp(self) -> None:
        """Update the last Discord synchronization timestamp."""
        self.file_manager.set_discord_last_sync_timestamp()

    def get_discord_sync_status(self) -> Dict[str, Any]:
        """Get current Discord synchronization status.

        Returns:
            Dictionary with sync statistics
        """
        last_sync = self.file_manager.get_discord_last_sync_timestamp()
        total_mappings = len(self.file_manager.get_all_discord_mappings())

        return {
            'total_discord_mappings': total_mappings,
            'last_discord_sync_timestamp': last_sync,
            'discord_enabled': self.config.discord_enabled
        }

    def _get_discord_user_info(self, user_id: str) -> Optional[str]:
        """Get Discord user information.

        Args:
            user_id: Discord user ID

        Returns:
            Formatted username string or None if failed
        """
        try:
            # Use Discord API to get user info
            import requests
            url = f"https://discord.com/api/v10/users/{user_id}"
            headers = {
                "Authorization": f"Bot {self.config.discord_bot_token}",
                "User-Agent": "DiscordBot (https://example.com, v1.0)"
            }

            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                user = response.json()
                username = user.get('username', 'Unknown')
                discriminator = user.get('discriminator', '0000')
                return f"{username}#{discriminator}"
            else:
                self.error_logger.log('warning', f"Failed to get Discord user {user_id}: {response.status_code}")
                return None
        except Exception as e:
            self.error_logger.log('warning', f"Error getting Discord user {user_id}: {str(e)}")
            return None