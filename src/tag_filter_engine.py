"""Tag-based filtering engine for Discord threads and Linear issues."""

import re
from typing import List, Dict, Any, Optional, Set
from enum import Enum
from dataclasses import dataclass

from src.config_manager import ConfigManager
from src.file_manager import FileManager
from src.error_logger import ErrorLogger


class FilterMode(Enum):
    """Filter mode enumeration."""
    INCLUDE = "include"
    EXCLUDE = "exclude"


class BooleanOperator(Enum):
    """Boolean operator enumeration."""
    AND = "and"
    OR = "or"


@dataclass
class FilterRule:
    """Data structure for filter rules."""
    tags: List[str]
    mode: FilterMode
    operator: BooleanOperator = BooleanOperator.AND
    case_sensitive: bool = False
    use_regex: bool = False


@dataclass
class FilterResult:
    """Data structure for filter evaluation results."""
    should_include: bool
    matched_rules: List[str]
    reason: str


class TagFilterEngine:
    """Engine for filtering Discord threads and Linear issues (tags optional via config)."""

    def __init__(self, config: ConfigManager, file_manager: FileManager, error_logger: ErrorLogger) -> None:
        """Initialize Tag Filter Engine.

        Args:
            config: Configuration manager instance
            file_manager: File manager instance
            error_logger: Error logger instance
        """
        self.config = config
        self.file_manager = file_manager
        self.error_logger = error_logger

        # Load filter rules from settings
        self._load_filter_rules()

    def _load_filter_rules(self) -> None:
        """Load filter rules from settings."""
        filter_rules_data = self.file_manager.get_discord_setting('DISCORD_FILTER_RULES')
        if not filter_rules_data:
            # Default filter rules (no tag restrictions)
            filter_rules_data = {
                "include_tags": [],
                "exclude_tags": [],
                "min_message_count": 1,
                "max_age_days": 365
            }

        self.include_tags = filter_rules_data.get('include_tags', [])
        self.exclude_tags = filter_rules_data.get('exclude_tags', [])
        self.min_message_count = filter_rules_data.get('min_message_count', 1)
        self.max_age_days = filter_rules_data.get('max_age_days', 365)

    def should_include_thread(self, thread_tags: List[str], message_count: int = 0,
                            thread_age_days: int = 0) -> FilterResult:
        """Determine if a Discord thread should be included based on filter rules.

        Args:
            thread_tags: List of tags from the Discord thread
            message_count: Number of messages in the thread
            thread_age_days: Age of thread in days

        Returns:
            FilterResult with decision and reasoning
        """
        try:
            matched_rules = []
            reason_parts = []

            # Check message count filter
            if message_count < self.min_message_count:
                return FilterResult(
                    should_include=False,
                    matched_rules=["min_message_count"],
                    reason=f"Thread has {message_count} messages, minimum required is {self.min_message_count}"
                )

            # Check age filter
            if thread_age_days > self.max_age_days:
                return FilterResult(
                    should_include=False,
                    matched_rules=["max_age_days"],
                    reason=f"Thread is {thread_age_days} days old, maximum allowed is {self.max_age_days}"
                )

            # Check exclude tags (higher priority)
            if self.exclude_tags:
                for tag in thread_tags:
                    if self._matches_any_pattern(tag, self.exclude_tags):
                        matched_rules.append(f"exclude_{tag}")
                        reason_parts.append(f"Thread contains excluded tag: {tag}")

            if matched_rules:
                return FilterResult(
                    should_include=False,
                    matched_rules=matched_rules,
                    reason=" | ".join(reason_parts)
                )

            # Check include tags (if specified, thread must have at least one)
            if self.include_tags:
                has_included_tag = False
                for tag in thread_tags:
                    if self._matches_any_pattern(tag, self.include_tags):
                        has_included_tag = True
                        matched_rules.append(f"include_{tag}")
                        reason_parts.append(f"Thread contains included tag: {tag}")

                if not has_included_tag:
                    return FilterResult(
                        should_include=False,
                        matched_rules=["include_required"],
                        reason=f"Thread tags {thread_tags} do not match any include patterns {self.include_tags}"
                    )

            # If no specific tags to check or all checks passed
            if not self.include_tags and not self.exclude_tags:
                return FilterResult(
                    should_include=True,
                    matched_rules=["no_filters"],
                    reason="No filter rules configured, including by default"
                )

            return FilterResult(
                should_include=True,
                matched_rules=matched_rules,
                reason="Thread passed all filter rules"
            )

        except Exception as e:
            error_msg = f"Error filtering thread with tags {thread_tags}: {str(e)}"
            self.error_logger.log('error', error_msg)
            return FilterResult(
                should_include=False,
                matched_rules=["error"],
                reason=error_msg
            )

    def _matches_any_pattern(self, tag: str, patterns: List[str]) -> bool:
        """Check if a tag matches any of the given patterns.

        Args:
            tag: Tag to check
            patterns: List of patterns (can be regex or literal)

        Returns:
            True if tag matches any pattern, False otherwise
        """
        for pattern in patterns:
            try:
                if pattern.startswith('regex:'):
                    # Regex pattern
                    regex_pattern = pattern[6:]  # Remove 'regex:' prefix
                    if re.search(regex_pattern, tag, re.IGNORECASE):
                        return True
                else:
                    # Literal match (case-insensitive)
                    if pattern.lower() == tag.lower():
                        return True
            except re.error as e:
                self.error_logger.log('warning', f"Invalid regex pattern '{pattern}': {str(e)}")
                continue

        return False

    def should_include_linear_issue(self, linear_labels: List[str], issue_tags: List[str] = None) -> FilterResult:
        """Determine if a Linear issue should be included based on filter rules.

        Args:
            linear_labels: Labels from the Linear issue
            issue_tags: Additional tags from Discord mapping

        Returns:
            FilterResult with decision and reasoning
        """
        try:
            # Combine Linear labels and Discord tags for filtering
            all_tags = linear_labels + (issue_tags or [])
            matched_rules = []
            reason_parts = []

            # Check exclude tags
            if self.exclude_tags:
                for tag in all_tags:
                    if self._matches_any_pattern(tag, self.exclude_tags):
                        matched_rules.append(f"exclude_{tag}")
                        reason_parts.append(f"Issue contains excluded tag: {tag}")

            if matched_rules:
                return FilterResult(
                    should_include=False,
                    matched_rules=matched_rules,
                    reason=" | ".join(reason_parts)
                )

            # Check include tags
            if self.include_tags:
                has_included_tag = False
                for tag in all_tags:
                    if self._matches_any_pattern(tag, self.include_tags):
                        has_included_tag = True
                        matched_rules.append(f"include_{tag}")
                        reason_parts.append(f"Issue contains included tag: {tag}")

                if not has_included_tag:
                    return FilterResult(
                        should_include=False,
                        matched_rules=["include_required"],
                        reason=f"Issue tags {all_tags} do not match any include patterns {self.include_tags}"
                    )

            return FilterResult(
                should_include=True,
                matched_rules=matched_rules,
                reason="Issue passed all filter rules"
            )

        except Exception as e:
            error_msg = f"Error filtering Linear issue with labels {linear_labels}: {str(e)}"
            self.error_logger.log('error', error_msg)
            return FilterResult(
                should_include=False,
                matched_rules=["error"],
                reason=error_msg
            )

    def update_filter_rules(self, include_tags: List[str] = None, exclude_tags: List[str] = None,
                          min_message_count: int = None, max_age_days: int = None) -> None:
        """Update filter rules and save to settings.

        Args:
            include_tags: List of tags that must be present for inclusion
            exclude_tags: List of tags that cause exclusion
            min_message_count: Minimum messages required
            max_age_days: Maximum thread age in days
        """
        try:
            current_rules = self.file_manager.get_discord_setting('DISCORD_FILTER_RULES') or {}

            if include_tags is not None:
                current_rules['include_tags'] = include_tags
                self.include_tags = include_tags

            if exclude_tags is not None:
                current_rules['exclude_tags'] = exclude_tags
                self.exclude_tags = exclude_tags

            if min_message_count is not None:
                current_rules['min_message_count'] = min_message_count
                self.min_message_count = min_message_count

            if max_age_days is not None:
                current_rules['max_age_days'] = max_age_days
                self.max_age_days = max_age_days

            self.file_manager.set_discord_setting('DISCORD_FILTER_RULES', current_rules, 'Discord thread filtering rules')

            self.error_logger.log('info', "Updated Discord filter rules")

        except Exception as e:
            self.error_logger.log('error', f"Failed to update filter rules: {str(e)}")
            raise

    def get_filter_rules(self) -> Dict[str, Any]:
        """Get current filter rules.

        Returns:
            Dictionary with current filter configuration
        """
        return {
            'include_tags': self.include_tags,
            'exclude_tags': self.exclude_tags,
            'min_message_count': self.min_message_count,
            'max_age_days': self.max_age_days
        }

    def validate_filter_rules(self) -> List[str]:
        """Validate current filter rules for errors.

        Returns:
            List of validation error messages
        """
        errors = []

        # Check regex patterns
        all_patterns = self.include_tags + self.exclude_tags
        for pattern in all_patterns:
            if pattern.startswith('regex:'):
                try:
                    regex_pattern = pattern[6:]
                    re.compile(regex_pattern)
                except re.error as e:
                    errors.append(f"Invalid regex pattern '{pattern}': {str(e)}")

        # Check numeric values
        if self.min_message_count < 0:
            errors.append(f"min_message_count must be non-negative, got {self.min_message_count}")

        if self.max_age_days <= 0:
            errors.append(f"max_age_days must be positive, got {self.max_age_days}")

        return errors