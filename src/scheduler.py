"""Background scheduler for periodic synchronization runs."""

import atexit
import signal
import time
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.triggers.interval import IntervalTrigger
from src.config_manager import ConfigManager
from src.sync_manager import SynchronizationManager
from src.discord_sync_manager import DiscordSyncManager

class Scheduler:
    """Manages background scheduling for synchronization jobs."""

    def __init__(self, config: ConfigManager) -> None:
        """Initialize scheduler.

        Args:
            config: Configuration manager instance
        """
        self.config = config
        self.sync_manager = SynchronizationManager(config)
        self.discord_sync_manager = DiscordSyncManager(config) if config.discord_enabled else None
        self.scheduler = None
        self._running = False
        self._lock_file = '.sync_lock'
        self._discord_lock_file = '.discord_sync_lock'
        self._setup_scheduler()

    def _setup_scheduler(self) -> None:
        """Setup APScheduler with interval job."""
        # Configure scheduler
        self.scheduler = BackgroundScheduler(
            timezone='UTC'
        )

        # Add sync job
        sync_interval = self.config.sync_interval
        trigger = IntervalTrigger(seconds=sync_interval)

        self.scheduler.add_job(
            func=self._run_sync,
            trigger=trigger,
            id='sync_job',
            name='Linear-GitLab Sync',
            max_instances=1,
            replace_existing=True
        )

        # Add Discord sync job if enabled
        if self.config.discord_enabled and self.discord_sync_manager:
            discord_sync_interval = self.config.get_int_value('DISCORD_SYNC_INTERVAL', 600)  # Default 10 minutes
            discord_trigger = IntervalTrigger(seconds=discord_sync_interval)

            self.scheduler.add_job(
                func=self._run_discord_sync,
                trigger=discord_trigger,
                id='discord_sync_job',
                name='Discord-Linear Sync',
                max_instances=1,
                replace_existing=True
            )

    def _run_sync(self) -> None:
        """Run synchronization task (called by scheduler)."""
        if self._acquire_lock():
            try:
                if not self.config.dry_run:
                    print("🕒 Starting scheduled synchronization...")
                    self.sync_manager.sync_issues()
                    print("✅ Synchronization completed.")
                else:
                    print("Dry run mode: would sync issues.")
            finally:
                self._release_lock()
        else:
            print("⏳ Skipping sync - another instance is running (lock file exists).")

    def _run_discord_sync(self) -> None:
        """Run Discord synchronization task (called by scheduler)."""
        if self._acquire_discord_lock():
            try:
                if self.discord_sync_manager:
                    if not self.config.dry_run:
                        print("🕒 Starting scheduled Discord synchronization...")
                        self._run_discord_sync_with_retry()
                    else:
                        print("Dry run mode: would sync Discord threads.")
            except Exception as e:
                print(f"❌ Discord sync failed: {str(e)}")
            finally:
                self._release_discord_lock()
        else:
            print("⏳ Skipping Discord sync - another instance is running (lock file exists).")

    def _run_discord_sync_with_retry(self) -> None:
        """Run Discord sync with retry mechanism."""
        max_retries = 3
        base_delay = 5  # seconds

        for attempt in range(max_retries):
            try:
                self.discord_sync_manager.sync_discord_threads()
                print("✅ Discord synchronization completed.")
                return
            except Exception as e:
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                if attempt < max_retries - 1:
                    print(f"❌ Discord sync attempt {attempt + 1} failed: {str(e)}")
                    print(f"⏳ Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    print(f"❌ Discord sync failed after {max_retries} attempts: {str(e)}")
                    raise

    def _acquire_lock(self) -> bool:
        """Acquire lock file for single instance execution.

        Returns:
            True if lock acquired, False otherwise
        """
        try:
            if os.path.exists(self._lock_file):
                # Check if lock file is recent (within last 5 minutes)
                # If it's older, assume the process crashed and remove stale lock
                lock_time = os.path.getmtime(self._lock_file)
                current_time = time.time()
                if current_time - lock_time < 300:  # 5 minutes
                    return False  # Another process is likely running
                else:
                    os.remove(self._lock_file)  # Stale lock

            with open(self._lock_file, 'w') as f:
                f.write(str(os.getpid()))
            return True
        except OSError:
            return False

    def _release_lock(self) -> None:
        """Release lock file."""
        try:
            if os.path.exists(self._lock_file):
                os.remove(self._lock_file)
        except OSError:
            pass

    def _acquire_discord_lock(self) -> bool:
        """Acquire Discord lock file for single instance execution.

        Returns:
            True if lock acquired, False otherwise
        """
        try:
            if os.path.exists(self._discord_lock_file):
                # Check if lock file is recent (within last 5 minutes)
                # If it's older, assume the process crashed and remove stale lock
                lock_time = os.path.getmtime(self._discord_lock_file)
                current_time = time.time()
                if current_time - lock_time < 300:  # 5 minutes
                    return False  # Another process is likely running
                else:
                    os.remove(self._discord_lock_file)  # Stale lock

            with open(self._discord_lock_file, 'w') as f:
                f.write(str(os.getpid()))
            return True
        except OSError:
            return False

    def _release_discord_lock(self) -> None:
        """Release Discord lock file."""
        try:
            if os.path.exists(self._discord_lock_file):
                os.remove(self._discord_lock_file)
        except OSError:
            pass

    def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return

        self._running = True
        self.scheduler.start()

        # Register cleanup on exit
        atexit.register(self.stop)
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        signal.signal(signal.SIGINT, self._shutdown_handler)

    def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running:
            return

        self.scheduler.shutdown(wait=True)
        self._running = False
        self._release_lock()
        self._release_discord_lock()

    def _shutdown_handler(self, signum, frame) -> None:
        """Handle shutdown signals."""
        self.stop()

    def trigger_manual_discord_sync(self) -> None:
        """Trigger a manual Discord synchronization run."""
        if self.discord_sync_manager and self._acquire_discord_lock():
            try:
                self.discord_sync_manager.sync_discord_threads()
            finally:
                self._release_discord_lock()

    def trigger_manual_sync(self) -> None:
        """Trigger a manual synchronization run."""
        if self._acquire_lock():
            try:
                if not self.config.dry_run:
                    print("🕒 Starting manual synchronization...")
                    self.sync_manager.sync_issues(manual_trigger=True)
                    print("✅ Manual synchronization completed.")
                else:
                    print("Dry run mode: would sync issues manually.")
            finally:
                self._release_lock()

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running and self.scheduler.running

    def get_next_run_time(self) -> str:
        """Get the next scheduled run time.

        Returns:
            ISO timestamp string or None
        """
        job = self.scheduler.get_job('sync_job')
        if job:
            next_run = job.next_run_time
            return next_run.isoformat() if next_run else None
        return None

    def get_discord_next_run_time(self) -> str:
        """Get the next scheduled Discord sync run time.

        Returns:
            ISO timestamp string or None
        """
        if not self.config.discord_enabled:
            return None
        job = self.scheduler.get_job('discord_sync_job')
        if job:
            next_run = job.next_run_time
            return next_run.isoformat() if next_run else None
        return None

    def pause_discord_job(self) -> bool:
        """Pause the Discord sync job.

        Returns:
            True if paused successfully, False otherwise
        """
        if not self.config.discord_enabled:
            return False
        try:
            job = self.scheduler.get_job('discord_sync_job')
            if job:
                job.pause()
                return True
        except Exception:
            pass
        return False

    def resume_discord_job(self) -> bool:
        """Resume the Discord sync job.

        Returns:
            True if resumed successfully, False otherwise
        """
        if not self.config.discord_enabled:
            return False
        try:
            job = self.scheduler.get_job('discord_sync_job')
            if job:
                job.resume()
                return True
        except Exception:
            pass
        return False

    def update_discord_sync_interval(self, new_interval_seconds: int) -> bool:
        """Update the Discord sync interval dynamically.

        Args:
            new_interval_seconds: New interval in seconds

        Returns:
            True if updated successfully, False otherwise
        """
        if not self.config.discord_enabled:
            return False
        try:
            job = self.scheduler.get_job('discord_sync_job')
            if job:
                new_trigger = IntervalTrigger(seconds=new_interval_seconds)
                job.reschedule(trigger=new_trigger)
                return True
        except Exception:
            pass
        return False

    def get_discord_job_status(self) -> dict:
        """Get status information for the Discord sync job.

        Returns:
            Dictionary with job status information
        """
        if not self.config.discord_enabled:
            return {'enabled': False}

        job = self.scheduler.get_job('discord_sync_job')
        if not job:
            return {'enabled': True, 'exists': False}

        return {
            'enabled': True,
            'exists': True,
            'running': False,  # APScheduler Job doesn't have a running attribute
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
            'paused': False  # APScheduler Job doesn't have a paused attribute in this version
        }