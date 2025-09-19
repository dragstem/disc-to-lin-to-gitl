#!/usr/bin/env python3
"""File-based data manager for storing mappings and sync state."""

import os
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from src.config_manager import ConfigManager


class FileManager:
    """Manages persistence using JSON files instead of database."""

    def __init__(self, config: ConfigManager) -> None:
        """Initialize file manager.

        Args:
            config: Configuration manager instance
        """
        # Create data directory if it doesn't exist
        self.data_dir = Path("./data")
        self.data_dir.mkdir(exist_ok=True)

        # File paths
        self.mappings_file = self.data_dir / "mappings.json"
        self.discord_mappings_file = self.data_dir / "discord_mappings.json"
        self.last_sync_file = self.data_dir / "last_sync.txt"
        self.logs_dir = Path("./logs")
        self.logs_dir.mkdir(exist_ok=True)

        # Threading lock for file operations
        self.settings_file = self.data_dir / "settings.json"

        # Threading lock for file operations
        self._file_lock = threading.RLock()

        # Initialize files if they don't exist
        self._ensure_files_exist()
        self._migrate_legacy_data()

    def _ensure_files_exist(self) -> None:
        """Ensure all data files exist with basic structure."""
        # Initialize mappings file
        if not self.mappings_file.exists():
            self._write_json_file(self.mappings_file, {"mappings": {}, "metadata": {"version": "1.0"}})

        # Initialize Discord mappings file
        if not self.discord_mappings_file.exists():
            self._write_json_file(self.discord_mappings_file, {
                "mappings": {},
                "metadata": {
                    "version": "1.0",
                    "description": "Mappings between Linear issues and Discord forum threads"
                }
            })

        # Initialize settings file
        if not self.settings_file.exists():
            self._write_json_file(self.settings_file, {"settings": {}})

    def _migrate_legacy_data(self) -> None:
        """Migrate any legacy data from old formats."""
        # This could be extended to handle upgrades from previous versions
        pass

    def _write_json_file(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Write data to JSON file with atomic operations.

        Args:
            file_path: Path to the JSON file
            data: Data to write
        """
        with self._file_lock:
            # Write to temporary file first, then atomic move
            temp_file = file_path.with_suffix('.tmp')
            try:
                with temp_file.open('w') as f:
                    json.dump(data, f, indent=2, sort_keys=True)
                temp_file.replace(file_path)
            except Exception as e:
                # Clean up temp file if something went wrong
                if temp_file.exists():
                    temp_file.unlink()
                raise e

    def _read_json_file(self, file_path: Path, default: Dict[str, Any] = None) -> Dict[str, Any]:
        """Read data from JSON file.

        Args:
            file_path: Path to the JSON file
            default: Default data to return if file doesn't exist

        Returns:
            Parsed JSON data
        """
        if default is None:
            default = {}

        with self._file_lock:
            if not file_path.exists():
                return default.copy()

            try:
                with file_path.open('r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"Warning: Could not read {file_path}, using defaults. Error: {e}")
                return default.copy()

    # ====== MAPPINGS MANAGEMENT ======

    def store_issue_mapping(self, linear_id: str, gitlab_id: str, linear_updated_at: str = None) -> None:
        """Store Linear ↔ GitLab issue mapping.

        Args:
            linear_id: Linear issue ID
            gitlab_id: GitLab issue ID
            linear_updated_at: Linear issue updated timestamp
        """
        data = self._read_json_file(self.mappings_file)
        if "mappings" not in data:
            data["mappings"] = {}

        mapping = {
            "gitlab_id": gitlab_id,
            "created_at": datetime.now().isoformat(),
            "status": "active"
        }
        if linear_updated_at:
            mapping["linear_updated_at"] = linear_updated_at

        data["mappings"][linear_id] = mapping

        self._write_json_file(self.mappings_file, data)

    def get_issue_mapping(self, linear_id: str) -> Optional[Dict[str, Any]]:
        """Get GitLab mapping for Linear issue.

        Args:
            linear_id: Linear issue ID

        Returns:
            Mapping dictionary or None if not found
        """
        data = self._read_json_file(self.mappings_file)
        mappings = data.get("mappings", {})

        if linear_id in mappings:
            return mappings[linear_id]
        return None

    def get_all_mappings(self) -> List[Dict[str, Any]]:
        """Get all active issue mappings.

        Returns:
            List of mapping dictionaries
        """
        data = self._read_json_file(self.mappings_file)
        mappings = data.get("mappings", {})

        result = []
        for linear_id, mapping in mappings.items():
            result.append({
                "linear_id": linear_id,
                "gitlab_id": mapping.get("gitlab_id"),
                "sync_timestamp": mapping.get("created_at"),
                "status": mapping.get("status", "active")
            })

        return result

    def remove_issue_mapping(self, linear_id: str) -> bool:
        """Remove issue mapping.

        Args:
            linear_id: Linear issue ID to remove

        Returns:
            True if mapping was removed, False if not found
        """
        data = self._read_json_file(self.mappings_file)
        mappings = data.get("mappings", {})

        if linear_id in mappings:
            del mappings[linear_id]
            self._write_json_file(self.mappings_file, data)
            return True
        return False

    # ====== DISCORD MAPPINGS MANAGEMENT ======

    def store_discord_thread_mapping(self, linear_id: str, thread_id: str, thread_name: str = None,
                                   discord_updated_at: str = None, discord_created_at: str = None,
                                   discord_author_id: str = None, discord_message_count: int = 0) -> None:
        """Store Linear ↔ Discord thread mapping with extended metadata.

        Args:
            linear_id: Linear issue ID
            thread_id: Discord thread ID
            thread_name: Discord thread name
            discord_updated_at: Discord thread last updated timestamp
            discord_created_at: Discord thread creation timestamp
            discord_author_id: Discord thread author ID
            discord_message_count: Number of messages in Discord thread
        """
        data = self._read_json_file(self.discord_mappings_file)
        if "mappings" not in data:
            data["mappings"] = {}

        mapping = {
            "thread_id": thread_id,
            "created_at": datetime.now().isoformat(),
            "status": "active"
        }
        if thread_name:
            mapping["thread_name"] = thread_name
        if discord_updated_at:
            mapping["discord_updated_at"] = discord_updated_at
        if discord_created_at:
            mapping["discord_created_at"] = discord_created_at
        if discord_author_id:
            mapping["discord_author_id"] = discord_author_id
        if discord_message_count > 0:
            mapping["discord_message_count"] = discord_message_count

        data["mappings"][linear_id] = mapping

        self._write_json_file(self.discord_mappings_file, data)

    def get_discord_thread_mapping(self, linear_id: str) -> Optional[Dict[str, Any]]:
        """Get Discord thread mapping for Linear issue.

        Args:
            linear_id: Linear issue ID

        Returns:
            Mapping dictionary or None if not found
        """
        data = self._read_json_file(self.discord_mappings_file)
        mappings = data.get("mappings", {})

        if linear_id in mappings:
            return mappings[linear_id]
        return None

    def get_all_discord_mappings(self) -> List[Dict[str, Any]]:
        """Get all active Discord thread mappings.

        Returns:
            List of Discord mapping dictionaries
        """
        data = self._read_json_file(self.discord_mappings_file)
        mappings = data.get("mappings", {})

        result = []
        for linear_id, mapping in mappings.items():
            result.append({
                "linear_id": linear_id,
                "thread_id": mapping.get("thread_id"),
                "thread_name": mapping.get("thread_name"),
                "sync_timestamp": mapping.get("created_at"),
                "status": mapping.get("status", "active"),
                "discord_updated_at": mapping.get("discord_updated_at"),
                "discord_created_at": mapping.get("discord_created_at"),
                "discord_author_id": mapping.get("discord_author_id"),
                "discord_message_count": mapping.get("discord_message_count", 0)
            })

        return result

    def remove_discord_thread_mapping(self, linear_id: str) -> bool:
        """Remove Discord thread mapping.

        Args:
            linear_id: Linear issue ID to remove

        Returns:
            True if mapping was removed, False if not found
        """
        data = self._read_json_file(self.discord_mappings_file)
        mappings = data.get("mappings", {})

        if linear_id in mappings:
            del mappings[linear_id]
            self._write_json_file(self.discord_mappings_file, data)
            return True
        return False
        """Remove issue mapping.

        Args:
            linear_id: Linear issue ID to remove

        Returns:
            True if mapping was removed, False if not found
        """
        data = self._read_json_file(self.mappings_file)
        mappings = data.get("mappings", {})

        if linear_id in mappings:
            del mappings[linear_id]
            self._write_json_file(self.mappings_file, data)
            return True
        return False

    # ====== SYNC TIMESTAMP MANAGEMENT ======

    def get_last_sync_timestamp(self) -> Optional[str]:
        """Get last synchronization timestamp.

        Returns:
            ISO timestamp string in UTC with Z, or None
        """
        if not self.last_sync_file.exists():
            return None

        try:
            with open(self.last_sync_file, 'r') as f:
                timestamp = f.read().strip()

            # Handle empty or invalid timestamp
            if not timestamp:
                return None

            # If timestamp has no Z, treat as local and convert to UTC
            if not timestamp.endswith('Z'):
                try:
                    local_dt = datetime.fromisoformat(timestamp)
                    # Assume local time is UTC+5, convert to UTC by subtracting 5 hours
                    from datetime import timedelta
                    utc_dt = local_dt - timedelta(hours=5)
                    return utc_dt.isoformat() + 'Z'
                except (ValueError, TypeError):
                    return None

            return timestamp

        except OSError:
            return None

    def update_last_sync_timestamp(self) -> None:
        """Update last synchronization timestamp."""
        timestamp = datetime.utcnow().isoformat() + 'Z'
        try:
            with open(self.last_sync_file, 'w') as f:
                f.write(timestamp)
        except OSError as e:
            print(f"Warning: Could not write sync timestamp: {e}")

    # ====== SETTINGS MANAGEMENT ======

    def set_setting(self, key: str, value: Any, description: str = "") -> None:
        """Store application setting.

        Args:
            key: Setting key
            value: Setting value (will be JSON serialized)
            description: Human-readable description
        """
        try:
            json_value = json.dumps(value)
        except TypeError:
            # Store as string if not JSON serializable
            json_value = str(value)

        data = self._read_json_file(self.settings_file)
        if "settings" not in data:
            data["settings"] = {}

        data["settings"][key] = {
            "value": json_value,
            "description": description,
            "updated_at": datetime.now().isoformat()
        }

        self._write_json_file(self.settings_file, data)

    def get_setting(self, key: str) -> Optional[Any]:
        """Get application setting.

        Args:
            key: Setting key

        Returns:
            Setting value or None if not found
        """
        data = self._read_json_file(self.settings_file)
        settings = data.get("settings", {})

        if key in settings:
            setting = settings[key]
            try:
                return json.loads(setting["value"])
            except (json.JSONDecodeError, TypeError):
                return setting["value"]

        return None

    # ====== STATISTICS AND MONITORING ======

    def get_sync_statistics(self) -> Dict[str, Any]:
        """Get synchronization statistics.

        Returns:
            Dictionary with sync stats
        """
        mappings_count = len([m for m in self.get_all_mappings() if m.get("status") == "active"])
        discord_mappings_count = len([m for m in self.get_all_discord_mappings() if m.get("status") == "active"])
        last_sync = self.get_last_sync_timestamp()

        # Read metadata
        data = self._read_json_file(self.mappings_file)
        metadata = data.get("metadata", {})

        return {
            "total_mappings": mappings_count,
            "total_discord_mappings": discord_mappings_count,
            "last_sync_timestamp": last_sync,
            "data_version": metadata.get("version", "unknown"),
            "data_file_exists": self.mappings_file.exists()
        }

    def cleanup_old_mappings(self, days_old: int = 365) -> int:
        """Remove mappings older than specified days.

        Args:
            days_old: Remove mappings older than this many days

        Returns:
            Number of mappings removed
        """
        # This is a simple cleanup that could be called periodically
        try:
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=days_old)

            data = self._read_json_file(self.mappings_file)
            mappings = data.get("mappings", {})
            original_count = len(mappings)
            removed_count = 0

            for linear_id, mapping in list(mappings.items()):
                created_at = mapping.get("created_at")
                if created_at:
                    try:
                        if datetime.fromisoformat(created_at) < cutoff_date:
                            del mappings[linear_id]
                            removed_count += 1
                    except (ValueError, TypeError):
                        continue  # Skip invalid timestamps

            if removed_count > 0:
                self._write_json_file(self.mappings_file, data)

            return removed_count

        except Exception as e:
            print(f"Warning: Cleanup failed: {e}")
            return 0

    def get_recent_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent log entries for the web interface.

        Args:
            limit: Maximum number of log entries to return

        Returns:
            List of log dictionaries with timestamp, operation, result
        """
        logs_path = self.logs_dir / "sync.log"

        if not logs_path.exists():
            return []

        logs = []
        try:
            with self._file_lock:
                with open(logs_path, 'r') as f:
                    lines = f.readlines()[-limit:]  # Get last limit lines

            for line in lines:
                parts = line.strip().split(' - ', 3)
                if len(parts) == 4:
                    timestamp = parts[0]
                    level = parts[2]
                    message = parts[3]

                    # Map level to result for CSS classes
                    if level == 'WARNING':
                        result = 'warning'
                    elif level == 'ERROR' or level == 'CRITICAL':
                        result = 'error'
                    else:
                        result = 'success'  # INFO, DEBUG mapped to success

                    logs.append({
                        'timestamp': timestamp,
                        'operation': message.strip(),
                        'result': result,
                        'details': None
                    })
        except Exception as e:
            print(f"Error reading logs: {e}")

        return logs

    # ====== DISCORD SPECIFIC METHODS ======

    def get_discord_last_sync_timestamp(self) -> Optional[str]:
        """Get last Discord synchronization timestamp.

        Returns:
            ISO timestamp string in UTC with Z, or None
        """
        discord_sync_file = self.data_dir / "discord_last_sync.txt"
        if not discord_sync_file.exists():
            return None

        try:
            with open(discord_sync_file, 'r') as f:
                timestamp = f.read().strip()

            # Handle empty or invalid timestamp
            if not timestamp:
                return None

            # If timestamp has no Z, treat as local and convert to UTC
            if not timestamp.endswith('Z'):
                try:
                    local_dt = datetime.fromisoformat(timestamp)
                    # Assume local time is UTC+5, convert to UTC by subtracting 5 hours
                    from datetime import timedelta
                    utc_dt = local_dt - timedelta(hours=5)
                    return utc_dt.isoformat() + 'Z'
                except (ValueError, TypeError):
                    return None

            return timestamp

        except OSError:
            return None

    def set_discord_last_sync_timestamp(self) -> None:
        """Update Discord last synchronization timestamp."""
        discord_sync_file = self.data_dir / "discord_last_sync.txt"
        timestamp = datetime.utcnow().isoformat() + 'Z'
        try:
            with open(discord_sync_file, 'w') as f:
                f.write(timestamp)
        except OSError as e:
            print(f"Warning: Could not write Discord sync timestamp: {e}")

    def get_discord_settings(self) -> Dict[str, Any]:
        """Get Discord-specific settings.

        Returns:
            Dictionary with Discord settings
        """
        discord_settings_file = self.data_dir / "discord_settings.json"
        return self._read_json_file(discord_settings_file, {"settings": {}})

    def set_discord_setting(self, key: str, value: Any, description: str = "") -> None:
        """Store Discord-specific setting.

        Args:
            key: Setting key
            value: Setting value (will be JSON serialized)
            description: Human-readable description
        """
        discord_settings_file = self.data_dir / "discord_settings.json"
        data = self._read_json_file(discord_settings_file, {"settings": {}})

        try:
            json_value = json.dumps(value)
        except TypeError:
            # Store as string if not JSON serializable
            json_value = str(value)

        data["settings"][key] = {
            "value": json_value,
            "description": description,
            "updated_at": datetime.now().isoformat()
        }

        self._write_json_file(discord_settings_file, data)

    def get_discord_setting(self, key: str) -> Optional[Any]:
        """Get Discord-specific setting.

        Args:
            key: Setting key

        Returns:
            Setting value or None if not found
        """
        data = self.get_discord_settings()
        settings = data.get("settings", {})

        if key in settings:
            setting = settings[key]
            try:
                return json.loads(setting["value"])
            except (json.JSONDecodeError, TypeError):
                return setting["value"]

        return None

    def get_all_discord_settings(self) -> Dict[str, Any]:
        """Get all Discord-specific settings.

        Returns:
            Dictionary with all Discord settings
        """
        data = self.get_discord_settings()
        return data.get("settings", {})