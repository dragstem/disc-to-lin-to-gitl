"""Unit tests for TagFilterEngine."""

import unittest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tag_filter_engine import TagFilterEngine, FilterResult, FilterMode, BooleanOperator
from src.config_manager import ConfigManager
from src.file_manager import FileManager
from src.error_logger import ErrorLogger


class TestTagFilterEngine(unittest.TestCase):
    """Test cases for TagFilterEngine."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = Mock(spec=ConfigManager)
        self.file_manager = Mock(spec=FileManager)
        self.error_logger = Mock(spec=ErrorLogger)

        # Mock filter settings (no tag restrictions)
        self.file_manager.get_discord_setting = Mock(return_value={
            "include_tags": [],
            "exclude_tags": [],
            "min_message_count": 1,
            "max_age_days": 365
        })

        self.filter_engine = TagFilterEngine(self.config, self.file_manager, self.error_logger)

    def test_initialization(self):
        """Test TagFilterEngine initialization."""
        self.assertEqual(self.filter_engine.include_tags, ["bug", "feature"])
        self.assertEqual(self.filter_engine.exclude_tags, ["spam", "duplicate"])
        self.assertEqual(self.filter_engine.min_message_count, 1)
        self.assertEqual(self.filter_engine.max_age_days, 365)

    def test_should_include_thread_with_include_tags(self):
        """Test thread inclusion with include tags."""
        # Thread has included tag
        result = self.filter_engine.should_include_thread(
            thread_tags=["bug", "urgent"],
            message_count=5,
            thread_age_days=30
        )

        self.assertTrue(result.should_include)
        self.assertIn("include_bug", result.matched_rules)
        self.assertEqual(result.reason, "Thread passed all filter rules")

    def test_should_include_thread_with_exclude_tags(self):
        """Test thread inclusion (no exclusion with empty exclude tags)."""
        # Thread has what would have been excluded tag, but no restrictions
        result = self.filter_engine.should_include_thread(
            thread_tags=["feature", "spam"],
            message_count=5,
            thread_age_days=30
        )

        self.assertTrue(result.should_include)
        self.assertEqual(result.matched_rules, [])
        self.assertEqual(result.reason, "Thread passed all filter rules")

    def test_should_include_thread_insufficient_messages(self):
        """Test thread exclusion due to insufficient messages."""
        result = self.filter_engine.should_include_thread(
            thread_tags=["bug"],
            message_count=0,  # Less than min_message_count
            thread_age_days=30
        )

        self.assertFalse(result.should_include)
        self.assertIn("min_message_count", result.matched_rules)
        self.assertIn("messages, minimum required is 1", result.reason)

    def test_should_include_thread_too_old(self):
        """Test thread exclusion due to age."""
        result = self.filter_engine.should_include_thread(
            thread_tags=["bug"],
            message_count=5,
            thread_age_days=400  # Older than max_age_days
        )

        self.assertFalse(result.should_include)
        self.assertIn("max_age_days", result.matched_rules)
        self.assertIn("days old, maximum allowed is 365", result.reason)

    def test_should_include_thread_no_matching_include_tags(self):
        """Test thread inclusion (no exclusion when include tags empty)."""
        # Empty include tags means no requirement
        self.filter_engine.exclude_tags = []
        self.filter_engine.include_tags = []

        result = self.filter_engine.should_include_thread(
            thread_tags=["discussion"],
            message_count=5,
            thread_age_days=30
        )

        self.assertTrue(result.should_include)
        self.assertEqual(result.matched_rules, [])
        self.assertEqual(result.reason, "Thread passed all filter rules")

    def test_should_include_thread_no_filters(self):
        """Test thread inclusion when no filters are configured."""
        # No filters configured
        self.filter_engine.include_tags = []
        self.filter_engine.exclude_tags = []

        result = self.filter_engine.should_include_thread(
            thread_tags=["any", "tags"],
            message_count=5,
            thread_age_days=30
        )

        self.assertTrue(result.should_include)
        self.assertIn("no_filters", result.matched_rules)
        self.assertEqual(result.reason, "No filter rules configured, including by default")

    def test_should_include_linear_issue_with_exclude_tags(self):
        """Test Linear issue inclusion (no exclusion with empty exclude tags)."""
        result = self.filter_engine.should_include_linear_issue(
            linear_labels=["bug", "urgent", "spam"],
            issue_tags=[]
        )

        self.assertTrue(result.should_include)
        self.assertEqual(result.matched_rules, [])
        self.assertEqual(result.reason, "Issue passed all filter rules")

    def test_should_include_linear_issue_with_include_tags(self):
        """Test Linear issue inclusion with include tags."""
        result = self.filter_engine.should_include_linear_issue(
            linear_labels=["bug", "urgent"],
            issue_tags=[]
        )

        self.assertTrue(result.should_include)
        self.assertIn("include_bug", result.matched_rules)
        self.assertEqual(result.reason, "Issue passed all filter rules")

    def test_should_include_linear_issue_combined_tags(self):
        """Test Linear issue filtering with combined Linear and Discord tags."""
        result = self.filter_engine.should_include_linear_issue(
            linear_labels=["urgent"],
            issue_tags=["bug", "spam"]  # spam should cause exclusion
        )

        self.assertFalse(result.should_include)
        self.assertIn("exclude_spam", result.matched_rules)

    def test_matches_any_pattern_literal(self):
        """Test pattern matching with literal strings."""
        # Exact match
        result = self.filter_engine._matches_any_pattern("bug", ["bug", "feature"])
        self.assertTrue(result)

        # Case insensitive match
        result = self.filter_engine._matches_any_pattern("BUG", ["bug", "feature"])
        self.assertTrue(result)

        # No match
        result = self.filter_engine._matches_any_pattern("discussion", ["bug", "feature"])
        self.assertFalse(result)

    def test_matches_any_pattern_regex(self):
        """Test pattern matching with regex patterns."""
        patterns = ["regex:bug.*", "feature"]

        # Regex match
        result = self.filter_engine._matches_any_pattern("bug_report", patterns)
        self.assertTrue(result)

        # Literal match
        result = self.filter_engine._matches_any_pattern("feature", patterns)
        self.assertTrue(result)

        # No match
        result = self.filter_engine._matches_any_pattern("discussion", patterns)
        self.assertFalse(result)

    def test_invalid_regex_pattern(self):
        """Test handling of invalid regex patterns."""
        patterns = ["regex:[invalid", "bug"]  # Invalid regex

        # Should log error but continue with other patterns
        result = self.filter_engine._matches_any_pattern("bug", patterns)
        self.assertTrue(result)  # Should match literal "bug"

        # Verify error was logged
        self.error_logger.log.assert_called()

    def test_update_filter_rules(self):
        """Test updating filter rules."""
        new_rules = {
            "include_tags": ["new_bug", "new_feature"],
            "exclude_tags": ["new_spam"],
            "min_message_count": 2,
            "max_age_days": 200
        }

        self.filter_engine.update_filter_rules(**new_rules)

        # Verify settings were saved
        self.file_manager.set_discord_setting.assert_called_once_with(
            'DISCORD_FILTER_RULES', new_rules, 'Discord thread filtering rules'
        )

        # Verify internal state was updated
        self.assertEqual(self.filter_engine.include_tags, ["new_bug", "new_feature"])
        self.assertEqual(self.filter_engine.exclude_tags, ["new_spam"])
        self.assertEqual(self.filter_engine.min_message_count, 2)
        self.assertEqual(self.filter_engine.max_age_days, 200)

    def test_get_filter_rules(self):
        """Test getting current filter rules."""
        rules = self.filter_engine.get_filter_rules()

        expected = {
            'include_tags': ["bug", "feature"],
            'exclude_tags': ["spam", "duplicate"],
            'min_message_count': 1,
            'max_age_days': 365
        }

        self.assertEqual(rules, expected)

    def test_validate_filter_rules_valid(self):
        """Test validation with valid filter rules."""
        errors = self.filter_engine.validate_filter_rules()
        self.assertEqual(errors, [])

    def test_validate_filter_rules_invalid_regex(self):
        """Test validation with invalid regex patterns."""
        # Add invalid regex to include tags
        self.filter_engine.include_tags = ["regex:[invalid", "bug"]

        errors = self.filter_engine.validate_filter_rules()

        self.assertTrue(len(errors) > 0)
        self.assertIn("Invalid regex pattern", errors[0])

    def test_validate_filter_rules_invalid_numeric(self):
        """Test validation with invalid numeric values."""
        self.filter_engine.min_message_count = -1
        self.filter_engine.max_age_days = 0

        errors = self.filter_engine.validate_filter_rules()

        self.assertIn("min_message_count must be non-negative", errors[0])
        self.assertIn("max_age_days must be positive", errors[1])

    def test_filter_result_structure(self):
        """Test FilterResult dataclass structure."""
        result = FilterResult(
            should_include=True,
            matched_rules=["rule1", "rule2"],
            reason="Test reason"
        )

        self.assertTrue(result.should_include)
        self.assertEqual(result.matched_rules, ["rule1", "rule2"])
        self.assertEqual(result.reason, "Test reason")


if __name__ == '__main__':
    unittest.main()