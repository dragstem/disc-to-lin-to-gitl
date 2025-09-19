"""Core synchronization manager orchestrating Linear to GitLab issue sync."""

from typing import List, Tuple, Optional, Dict
from src.config_manager import ConfigManager
from src.file_manager import FileManager
from src.linear_client import LinearClient
from src.gitlab_client import GitLabClient
from src.error_logger import ErrorLogger

class SynchronizationManager:
    """Manages the synchronization process between Linear and GitLab."""

    def __init__(self, config: ConfigManager) -> None:
        """Initialize synchronization manager.

        Args:
            config: Configuration manager instance
        """
        self.config = config
        # Use file-based storage instead of database
        self.file_manager = FileManager(config)
        self.linear_client = LinearClient(config)
        # Initialize GitLab client without project ID - will set it based on configuration
        self.gitlab_client = GitLabClient(config)
        self.error_logger = ErrorLogger(config)

        # Initialize configurable settings from environment
        self.team_name = self.config.linear_team_name
        self.gitlab_project_id = self.config.get_value('GITLAB_PROJECT_ID')
        if self.gitlab_project_id:
            self.gitlab_client.set_project_id(self.gitlab_project_id)

        # Cache for user mappings (Linear user -> GitLab user ID)
        self._user_mapping_cache = {}

    def _get_gitlab_user_id(self, linear_assignee: Optional[Dict]) -> Optional[int]:
        """Get GitLab user ID for Linear assignee.

        Args:
            linear_assignee: Linear assignee dictionary with name/email

        Returns:
            GitLab user ID or None if not found
        """
        if not linear_assignee:
            return None

        user_key = linear_assignee.get('email') or linear_assignee.get('name')
        if not user_key:
            return None

        # Check cache first
        if user_key in self._user_mapping_cache:
            return self._user_mapping_cache[user_key]

        # Search GitLab users by email or name
        try:
            gitlab_users = self.gitlab_client.get_users(search=user_key)
            if gitlab_users:
                # Use first match (assuming email/name is unique enough)
                gitlab_user_id = gitlab_users[0].get('id')
                self._user_mapping_cache[user_key] = gitlab_user_id
                return gitlab_user_id
        except Exception as e:
            self.error_logger.log('debug', f"Failed to find GitLab user for {user_key}: {str(e)}")

        # If no match found, cache None to avoid repeated searches
        self._user_mapping_cache[user_key] = None
        return None

    def _sync_attachments(self, gitlab_issue_iid: str, attachments: List[Dict]) -> None:
        """Sync attachments from Linear to GitLab issue.

        Args:
            gitlab_issue_iid: GitLab issue IID
            attachments: List of Linear attachment dictionaries
        """
        for attachment in attachments:
            try:
                attachment_url = attachment.get('assetUrl') or attachment.get('url')
                if not attachment_url:
                    continue

                filename = attachment.get('title', 'attachment')
                self.error_logger.log('debug', f"Downloading attachment: {filename}")

                # Download attachment
                temp_path = self.linear_client.download_attachment(attachment_url, filename)

                # Upload to GitLab
                upload_result = self.gitlab_client.upload_attachment(gitlab_issue_iid, temp_path, filename)

                # Add attachment link to issue description or as comment
                if upload_result and 'markdown' in upload_result:
                    comment_body = f"Attachment: {upload_result['markdown']}"
                    self.gitlab_client.create_comment(gitlab_issue_iid, comment_body)

                # Clean up temp file
                import os
                os.unlink(temp_path)

                self.error_logger.log('debug', f"Uploaded attachment {filename} to GitLab issue #{gitlab_issue_iid}")

            except Exception as e:
                self.error_logger.log('warning', f"Failed to sync attachment {attachment.get('id', 'unknown')}: {str(e)}")

    def _sync_comments(self, gitlab_issue_iid: str, comments: List[Dict]) -> None:
        """Sync comments from Linear to GitLab issue.

        Args:
            gitlab_issue_iid: GitLab issue IID
            comments: List of Linear comment dictionaries
        """
        for comment in comments:
            try:
                # Skip if comment has no body
                body = comment.get('body', '').strip()
                if not body:
                    continue

                # Format comment with author info (author field not available in current Linear API)
                author_name = 'Linear User'  # Default since author field isn't available
                created_at = comment.get('createdAt', '')
                updated_at = comment.get('updatedAt', '')

                # Add header to distinguish from regular comments
                formatted_comment = f"**Comment from Linear** (Linear)\n"
                if created_at:
                    formatted_comment += f"*Created: {created_at}*\n"
                if updated_at and updated_at != created_at:
                    formatted_comment += f"*Updated: {updated_at}*\n"
                formatted_comment += f"\n{body}"

                self.gitlab_client.create_comment(gitlab_issue_iid, formatted_comment)
                self.error_logger.log('debug', f"Created comment in GitLab issue #{gitlab_issue_iid}")

            except Exception as e:
                self.error_logger.log('warning', f"Failed to sync comment {comment.get('id', 'unknown')}: {str(e)}")

    def _sync_issue_updates(self, gitlab_issue_iid: str, linear_issue: Dict, gitlab_issue: Dict) -> bool:
        """Check if issue needs updates and sync changes.

        Args:
            gitlab_issue_iid: GitLab issue IID
            linear_issue: Linear issue data
            gitlab_issue: Current GitLab issue data

        Returns:
            True if updates were made, False otherwise
        """
        # Get configuration settings
        sync_assignments = self.config.get_value('SYNC_ASSIGNMENTS', 'true').lower() == 'true'
        sync_labels = self.config.get_value('SYNC_LABELS', 'true').lower() == 'true'
        sync_due_dates = self.config.get_value('SYNC_DUE_DATES', 'true').lower() == 'true'
        sync_priority = self.config.get_value('SYNC_PRIORITY', 'true').lower() == 'true'

        updates_needed = False
        update_data = {}

        identifier = linear_issue.get('identifier', linear_issue['id'])

        # Compare title
        expected_title = f"[{identifier}] {linear_issue['title']}"
        current_title = gitlab_issue.get('title', '')
        if current_title != expected_title:
            update_data['title'] = expected_title
            updates_needed = True

        # Compare assignee
        if sync_assignments:
            linear_assignee_id = self._get_gitlab_user_id(linear_issue.get('assignee'))
            current_assignees = gitlab_issue.get('assignees', [])
            current_assignee_id = current_assignees[0].get('id') if current_assignees else None

            if linear_assignee_id != current_assignee_id:
                update_data['assignee_id'] = linear_assignee_id
                updates_needed = True

        # Compare labels
        if sync_labels:
            linear_labels = [label['name'] for label in linear_issue.get('labels', {}).get('nodes', [])]
            current_labels = gitlab_issue.get('labels', [])
            if set(linear_labels) != set(current_labels):
                update_data['labels'] = linear_labels + [self.team_name, 'auto-sync']
                updates_needed = True

        # Compare due date
        if sync_due_dates:
            linear_due_date = linear_issue.get('dueDate')
            if linear_due_date:
                linear_due_date = linear_due_date[:10]  # Format to YYYY-MM-DD
            current_due_date = gitlab_issue.get('due_date')
            if linear_due_date != current_due_date:
                update_data['due_date'] = linear_due_date
                updates_needed = True

        # Compare weight (priority/estimate)
        if sync_priority:
            linear_priority = linear_issue.get('priority')
            linear_estimate = linear_issue.get('estimate')
            expected_weight = linear_priority if linear_priority is not None else (linear_estimate if linear_estimate else None)
            current_weight = gitlab_issue.get('weight')
            if expected_weight != current_weight:
                update_data['weight'] = expected_weight
                updates_needed = True

        # Updated description comparison (includes parent/child links)
        # This is more complex due to dynamic content, so we'll rebuild it
        description = linear_issue.get('description', '')
        link = f"https://linear.app/blockchainlabs/issue/{identifier}"
        expected_description = f"Linear Issue: {link}\n\n"

        parent = linear_issue.get('parent')
        if parent:
            parent_link = f"https://linear.app/blockchainlabs/issue/{parent['identifier']}"
            expected_description += f"**Parent Issue:** [{parent['title']}]({parent_link})\n\n"

        children = linear_issue.get('children', {}).get('nodes', [])
        if children:
            expected_description += "**Sub-issues:**\n"
            for child in children:
                child_link = f"https://linear.app/blockchainlabs/issue/{child['identifier']}"
                expected_description += f"- [{child['title']}]({child_link})\n"
            expected_description += "\n"

        expected_description += description if description.strip() else ""

        current_description = gitlab_issue.get('description', '')
        if expected_description.strip() != current_description.strip():
            update_data['description'] = expected_description
            updates_needed = True

        if updates_needed:
            self.gitlab_client.update_issue(gitlab_issue_iid, update_data)
            return True

        return False

    def sync_issues(self, manual_trigger: bool = False) -> None:
        """Execute the full synchronization process for all Linear issues.

        Args:
            manual_trigger: Whether this is a manual sync trigger
        """
        try:
            self.error_logger.log('info', f"Starting full synchronization (manual: {manual_trigger})")

            # Get all Linear issues for the team
            all_issues = self.linear_client.get_issues_since_by_team(self.team_name, since_timestamp=None)
            self.error_logger.log('info', f"Fetched {len(all_issues)} issues from Linear")

            if not all_issues:
                self.error_logger.log('info', "No issues to sync")
                return

            # Process each issue from Linear
            action_counts = {'created': 0, 'updated': 0, 'skip': 0, 'recreated': 0, 'error': 0}
            for issue in all_issues:
                try:
                    action, gitlab_id = self.sync_linear_issue_to_gitlab(issue)
                    action_counts[action] += 1

                    # Log the decision for each issue
                    if action == 'created':
                        reason = f"New Linear issue - no existing mapping found"
                    elif action == 'updated':
                        reason = f"Linear issue has changes (timestamp/content) that need sync"
                    elif action == 'recreated':
                        reason = f"GitLab issue missing - recreating based on mapping"
                    elif action == 'skip':
                        reason = f"No changes detected - Linear and GitLab are in sync"
                    else:  # error
                        reason = f"Sync failed due to error"

                    decision = f"Linear issue {issue['id']}: {action.upper()} - {reason}"
                    if action != 'skip':
                        self.error_logger.log('info', f"{decision} -> GitLab #{gitlab_id}")
                    else:
                        self.error_logger.log('info', decision)

                except Exception as e:
                    action_counts['error'] += 1
                    decision = f"Linear issue {issue['id']}: ERROR - Sync failed due to error"
                    self.error_logger.log('info', decision)

            self.error_logger.log('info', f"Sync summary: {action_counts['created']} created, {action_counts['updated']} updated, {action_counts['recreated']} recreated, {action_counts['skip']} skipped, {action_counts['error']} errors")

            # Update last sync timestamp
            self.file_manager.update_last_sync_timestamp()
            total_processed = sum(action_counts.values())
            self.error_logger.log('info', f"Synchronization completed. Processed {total_processed} issues")

        except Exception as e:
            self.error_logger.handle_api_error("sync", e, "Synchronization process failed")
            raise


    def sync_linear_issue_to_gitlab(self, linear_issue: dict) -> Tuple[str, str]:
        """Sync a Linear issue to GitLab with comprehensive field support.

        Args:
            linear_issue: Linear issue dictionary with all fields

        Returns:
            Tuple of (action, gitlab_id)
        """
        linear_id = linear_issue['id']
        linear_updated_at = linear_issue.get('updatedAt', '')
        identifier = linear_issue.get('identifier', linear_id)
        title = linear_issue['title']
        description = linear_issue.get('description', '')

        # Extract all additional fields
        assignee = linear_issue.get('assignee')
        labels = linear_issue.get('labels', {}).get('nodes', [])
        priority = linear_issue.get('priority')
        state = linear_issue.get('state')
        due_date = linear_issue.get('dueDate')
        estimate = linear_issue.get('estimate')
        parent = linear_issue.get('parent')
        attachments = linear_issue.get('attachments', {}).get('nodes', [])
        comments = linear_issue.get('comments', {}).get('nodes', [])
        children = linear_issue.get('children', {}).get('nodes', [])

        # Build enhanced description
        link = f"https://linear.app/blockchainlabs/issue/{identifier}"
        full_description = f"Linear Issue: {link}\n\n"

        # Add parent/child info
        if parent:
            parent_link = f"https://linear.app/blockchainlabs/issue/{parent['identifier']}"
            full_description += f"**Parent Issue:** [{parent['title']}]({parent_link})\n\n"

        if children:
            full_description += "**Sub-issues:**\n"
            for child in children:
                child_link = f"https://linear.app/blockchainlabs/issue/{child['identifier']}"
                full_description += f"- [{child['title']}]({child_link})\n"
            full_description += "\n"

        full_description += description if description.strip() else ""

        # Get configuration settings
        sync_assignments = self.config.get_value('SYNC_ASSIGNMENTS', 'true').lower() == 'true'
        sync_labels = self.config.get_value('SYNC_LABELS', 'true').lower() == 'true'
        sync_attachments = self.config.get_value('SYNC_ATTACHMENTS', 'true').lower() == 'true'
        sync_comments = self.config.get_value('SYNC_COMMENTS', 'true').lower() == 'true'
        sync_due_dates = self.config.get_value('SYNC_DUE_DATES', 'true').lower() == 'true'
        sync_priority = self.config.get_value('SYNC_PRIORITY', 'true').lower() == 'true'

        # Convert Linear data to GitLab format with config checks
        gitlab_assignee_id = self._get_gitlab_user_id(assignee) if sync_assignments else None
        gitlab_labels = [self.team_name, 'auto-sync']
        if sync_labels:
            gitlab_labels.extend([label['name'] for label in labels])

        gitlab_weight = None
        if sync_priority:
            gitlab_weight = priority if priority is not None else (estimate if estimate else None)

        gitlab_due_date = due_date[:10] if due_date and sync_due_dates else None  # Format to YYYY-MM-DD

        # Check existing mapping
        existing_mapping = self.file_manager.get_issue_mapping(linear_id)

        if not existing_mapping:
            # New issue: create in GitLab with all fields
            self.error_logger.log('debug', f"Linear issue {linear_id} not mapped - creating new GitLab issue")
            gitlab_id = self.gitlab_client.create_issue(
                identifier=identifier,
                title=title,
                description=full_description,
                labels=gitlab_labels,
                assignee_id=gitlab_assignee_id,
                due_date=gitlab_due_date,
                weight=gitlab_weight
            )

            # Sync attachments for new issue
            if sync_attachments and attachments:
                self._sync_attachments(gitlab_id, attachments)

            # Sync comments for new issue
            if sync_comments and comments:
                self._sync_comments(gitlab_id, comments)

            # Store mapping with linear_updated_at
            self.file_manager.store_issue_mapping(linear_id, gitlab_id, linear_updated_at)
            self.error_logger.log('debug', f"Created mapping: Linear {linear_id} -> GitLab #{gitlab_id}")
            return 'created', gitlab_id

        # Existing mapping: check for updates
        gitlab_id = existing_mapping['gitlab_id']
        stored_updated_at = existing_mapping.get('linear_updated_at', '')

        self.error_logger.log('debug', f"Linear issue {linear_id} mapped to GitLab #{gitlab_id}")

        if linear_updated_at != stored_updated_at:
            self.error_logger.log('debug', f"Linear issue {linear_id} timestamp changed (stored: {stored_updated_at}, current: {linear_updated_at})")
            # Fetch current GitLab issue to compare
            try:
                gitlab_issue = self.gitlab_client.get_issue(gitlab_id)
                if gitlab_issue:
                    # Check for any field changes that need syncing
                    updates_made = self._sync_issue_updates(gitlab_id, linear_issue, gitlab_issue)

                    # Sync attachments (new ones might have been added)
                    if sync_attachments and attachments:
                        self._sync_attachments(gitlab_id, attachments)

                    # Sync comments (new ones might have been added)
                    if sync_comments and comments:
                        self._sync_comments(gitlab_id, comments)

                    if updates_made:
                        self.error_logger.log('info', f"Linear issue {linear_id} updated in GitLab #{gitlab_id}")
                        # Update mapping with new updated_at
                        self.file_manager.store_issue_mapping(linear_id, gitlab_id, linear_updated_at)
                        return 'updated', gitlab_id
                    else:
                        # Same content, just update stored updated_at if different
                        if not stored_updated_at:
                            self.file_manager.store_issue_mapping(linear_id, gitlab_id, linear_updated_at)
                            self.error_logger.log('debug', f"Updated timestamp for Linear {linear_id} mapping")
                        self.error_logger.log('debug', f"Linear issue {linear_id} content unchanged despite timestamp change")
                        return 'skip', gitlab_id
                else:
                    self.error_logger.log('warning', f"GitLab issue #{gitlab_id} not found for Linear {linear_id} - recreating")
                    # GitLab issue missing, recreate
                    gitlab_id = self.gitlab_client.create_issue(
                        identifier=identifier,
                        title=title,
                        description=full_description,
                        labels=gitlab_labels,
                        assignee_id=gitlab_assignee_id,
                        due_date=gitlab_due_date,
                        weight=gitlab_weight
                    )

                    # Sync attachments and comments for recreated issue
                    if sync_attachments and attachments:
                        self._sync_attachments(gitlab_id, attachments)
                    if sync_comments and comments:
                        self._sync_comments(gitlab_id, comments)

                    self.file_manager.store_issue_mapping(linear_id, gitlab_id, linear_updated_at)
                    self.error_logger.log('info', f"Recreated GitLab issue #{gitlab_id} for Linear {linear_id}")
                    return 'recreated', gitlab_id
            except Exception as e:
                self.error_logger.log('warning', f"Failed to check/update GitLab issue {gitlab_id}: {str(e)}")
                return 'error', gitlab_id
        else:
            # No change detected
            self.error_logger.log('debug', f"Linear issue {linear_id} unchanged - skipping sync")
            return 'skip', gitlab_id

    def get_sync_status(self) -> dict:
        """Get current synchronization status.

        Returns:
            Dictionary with sync statistics
        """
        total_mappings = len(self.file_manager.get_all_mappings())
        last_sync = self.file_manager.get_last_sync_timestamp()
        recent_logs = []  # Database-free: no recent logs stored

        return {
            'total_synced_issues': total_mappings,
            'last_sync_timestamp': last_sync,
            'recent_sync_logs': recent_logs
        }

    def get_all_mappings(self) -> List[dict]:
        """Get all issue mappings.

        Returns:
            List of mapping dictionaries
        """
        return self.file_manager.get_all_mappings()

    def reload_configurable_settings(self) -> None:
        """Reload configurable settings from files."""
        # Get team name from file manager or default to "MAU"
        self.team_name = self.file_manager.get_setting('LINEAR_TEAM_NAME') or self.config.get_value('LINEAR_TEAM_NAME', 'MAU')

        # Get GitLab project ID override if set
        project_id_override = self.file_manager.get_setting('GITLAB_PROJECT_ID_OVERRIDE')
        if project_id_override:
            self.gitlab_client.set_project_id(project_id_override)

    def get_configurable_settings(self) -> dict:
        """Get current configurable settings.

        Returns:
            Dictionary with current setting values
        """
        return {
            'team_name': self.team_name,
            'gitlab_project_id': self.gitlab_client.project_id,
            'sync_interval': self.config.get_value('SYNC_INTERVAL', '300'),
            'log_level': self.config.get_value('LOG_LEVEL', 'INFO'),
            'dry_run': self.config.get_value('DRY_RUN', 'false').lower() == 'true',
            'sync_assignments': self.config.get_value('SYNC_ASSIGNMENTS', 'true').lower() == 'true',
            'sync_labels': self.config.get_value('SYNC_LABELS', 'true').lower() == 'true',
            'sync_attachments': self.config.get_value('SYNC_ATTACHMENTS', 'true').lower() == 'true',
            'sync_comments': self.config.get_value('SYNC_COMMENTS', 'true').lower() == 'true',
            'sync_due_dates': self.config.get_value('SYNC_DUE_DATES', 'true').lower() == 'true',
            'sync_priority': self.config.get_value('SYNC_PRIORITY', 'true').lower() == 'true'
        }
