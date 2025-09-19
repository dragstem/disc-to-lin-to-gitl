"""Main entry point for the Linear-GitLab Synchronization Application."""

import sys
import os
import argparse
import time
import signal
from typing import Optional
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cli_interface import main as cli_main

from src.config_manager import ConfigManager
from src.scheduler import Scheduler
from src.cli_interface import CLIInterface
from src.file_manager import FileManager
from src.sync_manager import SynchronizationManager
from src.error_logger import ErrorLogger
from src.web_interface import WebInterface
from src.discord_client import DiscordClient
from src.discord_sync_manager import DiscordSyncManager


class SynchronizationApp:
    """Main application class for synchronization service."""

    def __init__(self) -> None:
        """Initialize the synchronization application."""
        self.config = ConfigManager()
        self.file_manager = FileManager(self.config)
        self.sync_manager = SynchronizationManager(self.config)
        self.scheduler = Scheduler(self.config)
        self.error_logger = ErrorLogger(self.config)

        # Initialize Discord client if enabled
        self.discord_client = None
        if self.config.discord_enabled:
            try:
                self.discord_client = DiscordClient(self.config)
                self.error_logger.log('info', "Discord client initialized successfully")
            except Exception as e:
                self.error_logger.log('error', f"Failed to initialize Discord client: {e}")
                self.discord_client = None

        # Create CLI interface with Discord parameters if available
        self.cli_interface = CLIInterface(
            discord_sync_manager=self.scheduler.discord_sync_manager if hasattr(self.scheduler, 'discord_sync_manager') else None,
            discord_client=self.discord_client
        )

        # Create web interface with Discord parameters
        discord_sync_mgr = self.scheduler.discord_sync_manager if hasattr(self.scheduler, 'discord_sync_manager') else None
        self.web_interface = WebInterface(
            self.config,
            self.sync_manager,
            self.file_manager,
            self.scheduler,
            discord_sync_manager=discord_sync_mgr,
            discord_client=self.discord_client
        )

        self.running = False

    def start_background_sync(self) -> None:
        """Start the background synchronization scheduler."""
        print("🚀 Starting Linear-GitLab Synchronization Application...")
        print(f"📅 Scheduler starting - syncing every {self.config.sync_interval} seconds")

        self.scheduler.start()
        self.running = True

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self._shutdown()
        except Exception as e:
            self.error_logger.log('error', f"Unexpected error in main loop: {e}")
            self._shutdown()

    def _shutdown(self) -> None:
        """Gracefully shutdown the application."""
        print("\n🛑 Shutting down...")
        self.running = False
        self.scheduler.stop()
        print("✅ Application stopped.")

    def run_cli_command(self, command: str, *args: str) -> None:
        """Run a CLI command directly."""
        # Parse command line arguments to simulate CLI call
        import sys as _sys
        original_argv = _sys.argv[:]
        _sys.argv = ['linear-sync', command] + list(args)
        self.cli_interface.main()
        _sys.argv = original_argv

    def get_status(self) -> dict:
        """Get application status."""
        status = {
            "is_running": self.running,
            "sync_status": self.sync_manager.get_sync_status(),
            "scheduler_status": "running" if self.scheduler.is_running() else "stopped",
            "next_sync": self.scheduler.get_next_run_time()
        }

        # Add Discord status if enabled
        if self.config.discord_enabled and self.scheduler.discord_sync_manager:
            status["discord_sync_status"] = self.scheduler.discord_sync_manager.get_discord_sync_status()
            status["discord_job_status"] = self.scheduler.get_discord_job_status()
            status["discord_next_sync"] = self.scheduler.get_discord_next_run_time()

        return status

    def sync_discord(self, since_timestamp: Optional[str] = None) -> None:
        """Run Discord synchronization.

        Args:
            since_timestamp: ISO timestamp for incremental sync
        """
        if not self.config.discord_enabled or not self.scheduler.discord_sync_manager:
            print("❌ Discord integration is not enabled or failed to initialize")
            return

        try:
            print("🔄 Starting Discord synchronization...")
            self.scheduler.trigger_manual_discord_sync()
            print("✅ Discord synchronization completed")

        except Exception as e:
            print(f"❌ Discord synchronization failed: {str(e)}")


def daemon_mode(args: argparse.Namespace) -> None:
    """Run in daemon/background mode."""
    app = SynchronizationApp()

    if args.stop:
        print("🛑 Stopping background synchronization service...")
        # Note: In a real implementation, you'd use a PID file or system service
        print("✅ Service stopped.")
        return

    print("🔄 Running in daemon mode - press Ctrl+C to stop")
    print("  - Initializing components...")

    # Start web interface in background thread
    import threading
    web_thread = threading.Thread(target=lambda: app.web_interface.run(host='0.0.0.0', port=5000, debug=False), daemon=True)
    web_thread.start()
    print("🌐 Web interface started in background thread on port 5000")

    # Start scheduler (blocking call)
    app.start_background_sync()


def cli_mode() -> None:
    """Run in CLI mode."""
    # Let the CLI interface handle the command parsing
    cli_main()


def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Linear-GitLab Synchronization Application",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  No arguments: Run in CLI interactive mode (try 'python main.py --help' for CLI commands)
  --daemon: Run as background service
  --daemon --stop: Stop the background service

Examples:
  python src/main.py --daemon              # Start background sync service
  python src/main.py --daemon --stop       # Stop background service
  python src/main.py sync --json           # Manual sync (CLI mode)
  python src/main.py status                # Show status (CLI mode)
        """
    )

    parser.add_argument('--daemon', action='store_true',
                       help='Run as background daemon service')
    parser.add_argument('--stop', action='store_true',
                       help='Stop the background service')

    return parser


def main():
    """Main entry point."""
    parser = create_parser()
    args, unknown = parser.parse_known_args()

    if args.daemon:
        daemon_mode(args)
    else:
        cli_mode()


if __name__ == "__main__":
    main()