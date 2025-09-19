#!/usr/bin/env python3
"""Command-line interface for Linear-GitLab synchronization."""

import argparse
import json
import sys
import os
from typing import Optional
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config_manager import ConfigManager
from src.sync_manager import SynchronizationManager
from src.file_manager import FileManager
from src.error_logger import ErrorLogger
from src.discord_sync_manager import DiscordSyncManager
from src.discord_client import DiscordClient
from src.scheduler import Scheduler


class CLIInterface:
    """Command-line interface for the synchronization application."""

    def __init__(self, discord_sync_manager: Optional[DiscordSyncManager] = None, discord_client: Optional[DiscordClient] = None) -> None:
        """Initialize CLI interface."""
        self.config = ConfigManager()
        self.file_manager = FileManager(self.config)
        self.sync_manager = SynchronizationManager(self.config)
        self.error_logger = ErrorLogger(self.config)
        self.scheduler = Scheduler(self.config)

        # Initialize Discord components
        self.discord_client = discord_client
        self.discord_sync_manager = discord_sync_manager

        # If not provided, initialize Discord sync manager if enabled
        if self.discord_sync_manager is None and self.config.discord_enabled:
            try:
                self.discord_sync_manager = self.scheduler.discord_sync_manager
            except Exception as e:
                self.error_logger.log('warning', f"Discord sync manager initialization failed: {e}")

    def sync(self, args: argparse.Namespace) -> None:
        """Execute manual synchronization."""
        try:
            print("🚀 Starting manual synchronization...", file=sys.stderr)
            if hasattr(args, 'force') and args.force:
                print("🔄 Force full sync enabled", file=sys.stderr)
            self.sync_manager.sync_issues(manual_trigger=True, force_full_sync=getattr(args, 'force', False))

            # Get updated status
            status = self.sync_manager.get_sync_status()

            print("✅ Synchronization completed successfully!", file=sys.stderr)
            print(f"📊 Synced issues: {status['total_synced_issues']}", file=sys.stderr)

            if args.json:
                print(json.dumps({
                    "success": True,
                    "total_synced_issues": status['total_synced_issues'],
                    "last_sync_timestamp": status['last_sync_timestamp']
                }, indent=2))

        except Exception as e:
            self.error_logger.log('error', f"Manual sync failed: {e}")
            print(f"❌ Synchronization failed: {e}", file=sys.stderr)
            if args.json:
                print(json.dumps({"success": False, "error": str(e)}, indent=2))
            sys.exit(1)

    def status(self, args: argparse.Namespace) -> None:
        """Display synchronization status and statistics."""
        try:
            status = self.sync_manager.get_sync_status()
            config = self.sync_manager.get_configurable_settings()

            output = {
                "total_synced_issues": status['total_synced_issues'],
                "last_sync_timestamp": status['last_sync_timestamp'],
                "team_name": config['team_name'],
                "sync_interval": config['sync_interval'],
                "log_level": config['log_level'],
                "dry_run": config['dry_run'],
                "recent_logs": status.get('recent_sync_logs', [])[:5]  # Last 5 logs
            }

            # Add Discord status if available
            if self.discord_sync_manager:
                discord_status = self.discord_sync_manager.get_discord_sync_status()
                output["discord_mappings"] = discord_status.get("total_discord_mappings", 0)
                output["discord_last_sync"] = discord_status.get("last_discord_sync_timestamp")
                output["discord_enabled"] = True
            else:
                output["discord_enabled"] = False

            if args.json:
                print(json.dumps(output, indent=2))
            else:
                print("📊 Linear-GitLab Sync Status")
                print("=" * 30)
                print(f"Total Synced Issues: {output['total_synced_issues']}")
                print(f"Last Sync: {output['last_sync_timestamp'] or 'Never'}")
                print(f"Team: {output['team_name']}")
                print(f"GitLab Project: {config['gitlab_project_id']}")
                print(f"Sync Interval: {output['sync_interval']}s")
                print(f"Dry Run: {'Enabled' if output['dry_run'] else 'Disabled'}")

                if output.get('discord_enabled'):
                    print(f"Discord Mappings: {output.get('discord_mappings', 0)}")
                    print(f"Discord Last Sync: {output.get('discord_last_sync', 'Never')}")
                else:
                    print("Discord Integration: Disabled")

                if output['recent_logs']:
                    print("\nRecent Activity:")
                    for log in output['recent_logs']:
                        print(f"  {log.get('timestamp', '')}: {log.get('operation', '')}")

        except Exception as e:
            self.error_logger.handle_api_error('status', e)
            print(f"❌ Failed to get status: {e}", file=sys.stderr)
            sys.exit(1)

    def logs(self, args: argparse.Namespace) -> None:
        """Display recent synchronization logs."""
        try:
            print("📝 Logs are stored in the logs/ directory as specified in README.md")
            print("Use a file viewer or editor to check sync.log for recent activity.")

        except Exception as e:
            print(f"❌ Could not access logs: {e}", file=sys.stderr)
            sys.exit(1)

    def discord_sync(self, args: argparse.Namespace) -> None:
        """Execute Discord synchronization."""
        if not self.discord_sync_manager:
            print("❌ Discord integration is not available or failed to initialize", file=sys.stderr)
            if args.json:
                print(json.dumps({"success": False, "error": "Discord integration not available"}, indent=2))
            sys.exit(1)

        try:
            print("🔄 Starting Discord synchronization...", file=sys.stderr)
            self.scheduler.trigger_manual_discord_sync()
            print("✅ Discord synchronization completed!", file=sys.stderr)

            if args.json:
                print(json.dumps({"success": True}, indent=2))

        except Exception as e:
            self.error_logger.log('error', f"Discord sync failed: {e}")
            print(f"❌ Discord synchronization failed: {e}", file=sys.stderr)
            if args.json:
                print(json.dumps({"success": False, "error": str(e)}, indent=2))
            sys.exit(1)

    def config(self, args: argparse.Namespace) -> None:
        """Display current configuration settings."""
        try:
            config = self.sync_manager.get_configurable_settings()

            output = {
                "team_name": config['team_name'],
                "gitlab_project_id": config['gitlab_project_id'],
                "sync_interval": config['sync_interval'],
                "log_level": config['log_level'],
                "dry_run": config['dry_run'],
                "database_path": self.config.database_path,
                "api_endpoints": {
                    "linear": "https://api.linear.app/graphql",
                    "gitlab": "https://gitlab.com/api/v4"
                }
            }

            # Add Discord config if available
            if self.discord_sync_manager:
                discord_status = self.discord_sync_manager.get_discord_sync_status()
                output["discord_enabled"] = True
                output["discord_mappings"] = discord_status.get("total_discord_mappings", 0)
                output["discord_last_sync"] = discord_status.get("last_discord_sync_timestamp")
            else:
                output["discord_enabled"] = False

            if args.json:
                print(json.dumps(output, indent=2))
            else:
                print("⚙️  Configuration Settings")
                print("=" * 25)
                print(f"Team Name: {output['team_name']}")
                print(f"GitLab Project ID: {output['gitlab_project_id']}")
                print(f"Sync Interval: {output['sync_interval']} seconds")
                print(f"Log Level: {output['log_level']}")
                print(f"Dry Run Mode: {'Enabled' if output['dry_run'] else 'Disabled'}")
                print(f"Database Path: {output['database_path']}")
                print(f"Discord Enabled: {'Yes' if output.get('discord_enabled', False) else 'No'}")

                if output.get('discord_enabled'):
                    print(f"Discord Mappings: {output.get('discord_mappings', 0)}")
                    print(f"Discord Last Sync: {output.get('discord_last_sync', 'Never')}")

                print(f"\nAPI Endpoints:")
                print(f"  Linear: {output['api_endpoints']['linear']}")
                print(f"  GitLab: {output['api_endpoints']['gitlab']}")

        except Exception as e:
            print(f"❌ Failed to get configuration: {e}", file=sys.stderr)
            sys.exit(1)

    def pause_discord_job(self, args: argparse.Namespace) -> None:
        """Pause the Discord sync job."""
        if not self.config.discord_enabled:
            print("❌ Discord integration is not available", file=sys.stderr)
            if args.json:
                print(json.dumps({"success": False, "error": "Discord not available"}, indent=2))
            sys.exit(1)

        try:
            success = self.scheduler.pause_discord_job()
            if success:
                print("✅ Discord sync job paused", file=sys.stderr)
                if args.json:
                    print(json.dumps({"success": True}, indent=2))
            else:
                print("❌ Failed to pause Discord sync job", file=sys.stderr)
                if args.json:
                    print(json.dumps({"success": False, "error": "Failed to pause"}, indent=2))
                sys.exit(1)
        except Exception as e:
            print(f"❌ Error pausing Discord job: {e}", file=sys.stderr)
            if args.json:
                print(json.dumps({"success": False, "error": str(e)}, indent=2))
            sys.exit(1)

    def resume_discord_job(self, args: argparse.Namespace) -> None:
        """Resume the Discord sync job."""
        if not self.config.discord_enabled:
            print("❌ Discord integration is not available", file=sys.stderr)
            if args.json:
                print(json.dumps({"success": False, "error": "Discord not available"}, indent=2))
            sys.exit(1)

        try:
            success = self.scheduler.resume_discord_job()
            if success:
                print("✅ Discord sync job resumed", file=sys.stderr)
                if args.json:
                    print(json.dumps({"success": True}, indent=2))
            else:
                print("❌ Failed to resume Discord sync job", file=sys.stderr)
                if args.json:
                    print(json.dumps({"success": False, "error": "Failed to resume"}, indent=2))
                sys.exit(1)
        except Exception as e:
            print(f"❌ Error resuming Discord job: {e}", file=sys.stderr)
            if args.json:
                print(json.dumps({"success": False, "error": str(e)}, indent=2))
            sys.exit(1)

    def discord_job_status(self, args: argparse.Namespace) -> None:
        """Get Discord job status."""
        if not self.config.discord_enabled:
            output = {"enabled": False}
        else:
            output = self.scheduler.get_discord_job_status()

        if args.json:
            print(json.dumps(output, indent=2))
        else:
            print("📊 Discord Job Status")
            print("=" * 20)
            print(f"Enabled: {output.get('enabled', False)}")
            if output.get('enabled'):
                print(f"Job Exists: {output.get('exists', False)}")
                if output.get('exists'):
                    print(f"Running: {output.get('running', False)}")
                    print(f"Next Run: {output.get('next_run', 'N/A')}")
                    print(f"Paused: {output.get('paused', False)}")

    def web(self, args: argparse.Namespace) -> None:
        """Start the web interface for manual operations and monitoring."""
        print("🌟 Starting web interface on http://0.0.0.0:5000")
        print("Available endpoints:")
        print("  GET /api/status         - Sync status")
        print("  GET /health             - Health check")
        print("  POST /trigger-sync      - Manual sync trigger")
        print("  POST /webhooks/linear/issue - Webhook handler")
        print("  GET /                   - Dashboard")
        print("Use Ctrl+C to stop.")
        print("-" * 50)

        # Import here to avoid circular imports
        from src.web_interface import WebInterface

        # Create web interface
        web_interface = WebInterface(
            self.config,
            self.sync_manager,
            self.file_manager,  # Pass file_manager instead of db_manager
            self.scheduler
        )

        try:
            web_interface.run()
        except KeyboardInterrupt:
            print("\n🛑 Web interface stopped.")


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Linear-GitLab Synchronization CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.cli_interface sync --json    # Manual sync with JSON output
  python -m src.cli_interface status         # View sync status
  python -m src.cli_interface logs --limit 10  # Show last 10 log entries
  python -m src.cli_interface config --json     # View config as JSON
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Trigger manual synchronization')
    sync_parser.add_argument('--json', action='store_true', help='Output results as JSON')
    sync_parser.add_argument('--force', action='store_true', help='Force full sync of all issues')
    sync_parser.set_defaults(func='sync')

    # Status command
    status_parser = subparsers.add_parser('status', help='Show synchronization status')
    status_parser.add_argument('--json', action='store_true', help='Output results as JSON')
    status_parser.set_defaults(func='status')

    # Logs command
    logs_parser = subparsers.add_parser('logs', help='Show synchronization logs location')
    logs_parser.set_defaults(func='logs')

    # Web command to start web interface
    web_parser = subparsers.add_parser('web', help='Start web interface')
    web_parser.set_defaults(func='web')

    # Discord sync command
    discord_parser = subparsers.add_parser('discord-sync', help='Trigger Discord synchronization')
    discord_parser.add_argument('--json', action='store_true', help='Output results as JSON')
    discord_parser.add_argument('--since', type=str, help='ISO timestamp for incremental sync (e.g., 2025-01-01T00:00:00Z)')
    discord_parser.set_defaults(func='discord_sync')

    # Pause Discord job
    pause_discord_parser = subparsers.add_parser('pause-discord', help='Pause Discord sync job')
    pause_discord_parser.add_argument('--json', action='store_true', help='Output results as JSON')
    pause_discord_parser.set_defaults(func='pause_discord_job')

    # Resume Discord job
    resume_discord_parser = subparsers.add_parser('resume-discord', help='Resume Discord sync job')
    resume_discord_parser.add_argument('--json', action='store_true', help='Output results as JSON')
    resume_discord_parser.set_defaults(func='resume_discord_job')

    # Discord job status
    discord_status_parser = subparsers.add_parser('discord-status', help='Show Discord job status')
    discord_status_parser.add_argument('--json', action='store_true', help='Output results as JSON')
    discord_status_parser.set_defaults(func='discord_job_status')

    # Config command
    config_parser = subparsers.add_parser('config', help='Show current configuration')
    config_parser.add_argument('--json', action='store_true', help='Output results as JSON')
    config_parser.set_defaults(func='config')

    return parser


def main() -> None:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cli = CLIInterface()

    # Call the appropriate method
    getattr(cli, args.func)(args)


if __name__ == "__main__":
    main()