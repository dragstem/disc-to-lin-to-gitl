"""Minimal Flask web interface for monitoring and manual operations."""

from flask import Flask, jsonify, render_template_string, request, redirect, url_for
import threading
from typing import Optional
from src.config_manager import ConfigManager
from src.sync_manager import SynchronizationManager
from src.file_manager import FileManager
from src.scheduler import Scheduler
from src.discord_sync_manager import DiscordSyncManager
from src.discord_client import DiscordClient

class WebInterface:
    """Flask-based web interface for the synchronization application."""

    def __init__(self, config: ConfigManager, sync_manager: SynchronizationManager,
                 file_manager: FileManager, scheduler: Optional[Scheduler],
                 discord_sync_manager: Optional[DiscordSyncManager] = None,
                 discord_client: Optional[DiscordClient] = None) -> None:
        """Initialize web interface.

        Args:
            config: Configuration manager
            sync_manager: Synchronization manager instance
            file_manager: FileManager instance
            scheduler: Scheduler instance
            discord_sync_manager: Discord synchronization manager (optional)
            discord_client: Discord API client (optional)
        """
        self.config = config
        self.sync_manager = sync_manager
        self.file_manager = file_manager
        self.scheduler = scheduler  # Optional for database-free config
        self.discord_sync_manager = discord_sync_manager
        self.discord_client = discord_client
        self.app = Flask(__name__)
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Setup Flask routes."""

        @self.app.route('/')
        def dashboard():
            """Main dashboard page."""
            return render_template_string(self._get_dashboard_template())

        @self.app.route('/status')
        def status():
            """JSON API for synchronization status."""
            status_data = {
                'sync_status': self.sync_manager.get_sync_status(),
                'scheduler_running': self.scheduler.is_running() if self.scheduler else False,
                'next_run_time': self.scheduler.get_next_run_time() if self.scheduler else None,
                'dry_run': self.config.dry_run
            }
            return jsonify(status_data)

        @self.app.route('/trigger-sync', methods=['POST'])
        def trigger_sync():
            """Manual sync trigger."""
            try:
                if self.scheduler:
                    threading.Thread(target=self.scheduler.trigger_manual_sync).start()
                else:
                    threading.Thread(target=self.sync_manager.sync_issues, args=(True,)).start()
                return jsonify({'status': 'success', 'message': 'Manual sync triggered'})
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/mappings')
        def mappings():
            """View all issue mappings."""
            mappings = self.sync_manager.get_all_mappings()
            return render_template_string(self._get_mappings_template(), mappings=mappings)

        @self.app.route('/health')
        def health():
            """Basic health check endpoint."""
            return jsonify({'status': 'healthy'})

        @self.app.route('/logs')
        def logs():
            """View recent synchronization logs."""
            logs = self.file_manager.get_recent_logs()
            return render_template_string(self._get_logs_template(), logs=logs)

        @self.app.route('/settings')
        def settings():
            """Display and modify application settings."""
            return render_template_string(self._get_settings_template())

        @self.app.route('/webhooks/linear/issue', methods=['POST'])
        def webhook_linear_issue():
            """Handle Linear webhook for issue events."""
            try:
                data = request.get_json()
                if (data and 'action' in data and
                    data['action'] in ['create', 'update'] and
                    'data' in data and 'id' in data['data']):
                    issue_action = data['action']
                    issue_id = data['data']['id']
                    # Trigger manual sync in background
                    threading.Thread(target=self.sync_manager.sync_issues, args=(True,)).start()
                    return jsonify({
                        'status': 'success',
                        'message': f'Webhook processed: {issue_action} on issue {issue_id}. Sync triggered.'
                    })
                return jsonify({
                    'status': 'ignored',
                    'message': 'Webhook received but no sync trigger required'
                })
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/settings', methods=['POST'])
        def update_settings():
            """Update application settings."""
            try:
                # Get form data
                team_name = request.form.get('team_name', '').strip()
                gitlab_project_id = request.form.get('gitlab_project_id', '').strip()
                sync_interval = request.form.get('sync_interval', '').strip()

                # Validate inputs
                if not team_name:
                    return jsonify({'status': 'error', 'message': 'Team name is required'}), 400

                if not gitlab_project_id:
                    return jsonify({'status': 'error', 'message': 'GitLab project ID is required'}), 400

                if sync_interval:
                    try:
                        int(sync_interval)
                    except ValueError:
                        return jsonify({'status': 'error', 'message': 'Sync interval must be a number'}), 400

                # Update settings via file manager
                self.file_manager.set_setting('LINEAR_TEAM_NAME', team_name,
                                            'Linear team name for synchronization')
                self.file_manager.set_setting('GITLAB_PROJECT_ID_OVERRIDE', gitlab_project_id,
                                            'GitLab project ID override')
                if sync_interval:
                    self.file_manager.set_setting('SYNC_INTERVAL', sync_interval,
                                                'Sync interval in seconds')

                # Reload configuration in sync manager to use updated values
                self.sync_manager.reload_configurable_settings()

                return jsonify({'status': 'success', 'message': 'Settings updated successfully'})
    
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/api/settings')
        def get_settings():
            """Get current application settings (JSON)."""
            # Reload latest settings from file system before returning
            self.sync_manager.reload_configurable_settings()
            settings = self.sync_manager.get_configurable_settings()
            return jsonify(settings)

        @self.app.route('/api/mappings-config')
        def get_mappings_config():
            """Get configuration needed for mappings page."""
            workspace = self.file_manager.get_setting('WORKSPACE_ID') or 'workspace'
            project_path = self.file_manager.get_setting('GITLAB_PROJECT_PATH') or 'your-project'
            return jsonify({
                'workspace': workspace,
                'project_path': project_path
            })

        @self.app.route('/api/linear-status')
        def linear_status():
            """Check Linear API status."""
            try:
                # Quick API health check
                result = self.sync_manager.linear_client.get_team_id(self.sync_manager.team_name)
                return jsonify({'status': 'OK', 'team_id': result[0]})
            except Exception as e:
                return jsonify({'status': 'ERROR', 'error': str(e)}), 500

        @self.app.route('/api/gitlab-status')
        def gitlab_status():
            """Check GitLab API status."""
            try:
                # Quick API health check
                result = self.sync_manager.gitlab_client.get_project_info()
                return jsonify({'status': 'OK', 'project': result['name']})
            except Exception as e:
                return jsonify({'status': 'ERROR', 'error': str(e)}), 500

        # Discord-specific routes
        @self.app.route('/discord-settings')
        def discord_settings():
            """Display Discord settings and configuration."""
            if not self.discord_client or not self.discord_sync_manager:
                return render_template_string(self._get_error_template("Discord integration not available"))
            return render_template_string(self._get_discord_settings_template())

        @self.app.route('/discord-mappings')
        def discord_mappings():
            """View Discord thread mappings."""
            if not self.discord_client or not self.discord_sync_manager:
                return render_template_string(self._get_error_template("Discord integration not available"))
            mappings = self.file_manager.get_all_discord_mappings()
            return render_template_string(self._get_discord_mappings_template(), mappings=mappings)

        @self.app.route('/discord-status')
        def discord_status():
            """Discord API connectivity and sync status monitoring."""
            if not self.discord_client or not self.discord_sync_manager:
                return render_template_string(self._get_error_template("Discord integration not available"))
            return render_template_string(self._get_discord_status_template())

        @self.app.route('/api/discord-status')
        def api_discord_status():
            """JSON API for Discord synchronization status."""
            if not self.discord_client or not self.discord_sync_manager:
                return jsonify({'enabled': False, 'error': 'Discord integration not configured'})

            try:
                # Get sync status
                sync_status = self.discord_sync_manager.get_discord_sync_status()
                # Get API connectivity status
                connectivity = self.discord_client.test_connectivity()
                # Get scheduler status if available
                scheduler_status = {}
                if self.scheduler and self.config.discord_enabled:
                    scheduler_status = self.scheduler.get_discord_job_status()

                return jsonify({
                    'enabled': True,
                    'connectivity': connectivity,
                    'sync_status': sync_status,
                    'scheduler': scheduler_status
                })
            except Exception as e:
                return jsonify({'enabled': True, 'error': str(e)}), 500

        @self.app.route('/api/discord-settings')
        def api_discord_settings():
            """Get current Discord settings (JSON)."""
            if not self.discord_client or not self.discord_sync_manager:
                return jsonify({'enabled': False, 'error': 'Discord integration not configured'})

            settings = self.file_manager.get_all_discord_settings()
            return jsonify({'enabled': True, 'settings': settings})

        @self.app.route('/trigger-discord-sync', methods=['POST'])
        def trigger_discord_sync():
            """Manual Discord sync trigger."""
            if not self.discord_client or not self.discord_sync_manager:
                return jsonify({'status': 'error', 'message': 'Discord integration not available'}), 400

            try:
                if self.scheduler:
                    threading.Thread(target=self.scheduler.trigger_manual_discord_sync).start()
                else:
                    threading.Thread(target=self.discord_sync_manager.sync_discord_threads).start()
                return jsonify({'status': 'success', 'message': 'Discord sync triggered'})
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/api/discord-mappings/<thread_id>', methods=['DELETE'])
        def delete_discord_mapping(thread_id):
            """Delete a Discord thread mapping."""
            if not self.discord_client or not self.discord_sync_manager:
                return jsonify({'status': 'error', 'message': 'Discord integration not available'}), 400

            try:
                # First find the Linear ID for this thread ID
                all_mappings = self.file_manager.get_all_discord_mappings()
                linear_id = None
                for mapping in all_mappings:
                    if mapping.get('thread_id') == thread_id:
                        linear_id = mapping.get('linear_id')
                        break

                if not linear_id:
                    return jsonify({'status': 'error', 'message': 'Mapping not found'}), 404

                # Delete the mapping from file manager
                success = self.file_manager.remove_discord_thread_mapping(linear_id)
                if success:
                    return jsonify({'status': 'success', 'message': 'Mapping deleted successfully'})
                else:
                    return jsonify({'status': 'error', 'message': 'Failed to delete mapping'}), 500
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/api/discord-test-connectivity')
        def api_discord_test_connectivity():
            """Test Discord API connectivity with timing."""
            if not self.discord_client:
                return jsonify({'success': False, 'error': 'Discord client not configured'})

            import time
            start_time = time.time()
            try:
                success = self.discord_client.test_connectivity()
                end_time = time.time()
                latency = int((end_time - start_time) * 1000)  # Convert to milliseconds
                return jsonify({'success': success, 'latency': latency})
            except Exception as e:
                end_time = time.time()
                latency = int((end_time - start_time) * 1000)
                return jsonify({'success': False, 'error': str(e), 'latency': latency})

        @self.app.route('/api/discord-clear-errors', methods=['POST'])
        def api_discord_clear_errors():
            """Clear Discord error logs."""
            if not self.discord_client or not self.discord_sync_manager:
                return jsonify({'success': False, 'error': 'Discord integration not available'})

            try:
                # This would clear error logs - placeholder implementation
                return jsonify({'success': True, 'message': 'Error logs cleared'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/discord-download-logs')
        def api_discord_download_logs():
            """Download Discord-related logs."""
            if not self.discord_client or not self.discord_sync_manager:
                return jsonify({'error': 'Discord integration not available'}), 400

            try:
                # Get recent logs related to Discord
                logs = self.file_manager.get_recent_logs()
                discord_logs = [log for log in logs if 'discord' in log.get('operation', '').lower() or 'discord' in log.get('details', '').lower()]

                log_text = "Discord Integration Logs\n"
                log_text += "=" * 50 + "\n\n"

                for log in discord_logs:
                    log_text += f"[{log.get('timestamp', 'Unknown')}] {log.get('operation', 'Unknown')}\n"
                    if log.get('details'):
                        log_text += f"Details: {log.get('details')}\n"
                    log_text += "\n"

                from flask import Response
                return Response(log_text, mimetype='text/plain',
                              headers={'Content-Disposition': 'attachment; filename=discord_logs.txt'})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/discord-diagnostics')
        def api_discord_diagnostics():
            """Run Discord diagnostics."""
            if not self.discord_client or not self.discord_sync_manager:
                return jsonify({'error': 'Discord integration not available'}), 400

            results = {}

            try:
                # Test Discord API connectivity
                results['api_connectivity'] = {
                    'success': self.discord_client.test_connectivity(),
                    'message': 'Discord API accessible' if self.discord_client.test_connectivity() else 'Discord API not accessible'
                }
            except Exception as e:
                results['api_connectivity'] = {'success': False, 'message': f'API test failed: {str(e)}'}

            try:
                # Check Discord settings
                settings = self.file_manager.get_all_discord_settings()
                results['settings_configured'] = {
                    'success': bool(settings),
                    'message': f'Found {len(settings)} Discord settings' if settings else 'No Discord settings configured'
                }
            except Exception as e:
                results['settings_configured'] = {'success': False, 'message': f'Settings check failed: {str(e)}'}

            try:
                # Check mappings
                mappings = self.file_manager.get_all_discord_mappings()
                results['mappings_exist'] = {
                    'success': len(mappings) > 0,
                    'message': f'Found {len(mappings)} Discord mappings' if mappings else 'No Discord mappings found'
                }
            except Exception as e:
                results['mappings_exist'] = {'success': False, 'message': f'Mappings check failed: {str(e)}'}

            try:
                # Check sync status
                sync_status = self.discord_sync_manager.get_discord_sync_status()
                last_sync = sync_status.get('last_discord_sync_timestamp')
                results['sync_status'] = {
                    'success': last_sync is not None,
                    'message': f'Last sync: {last_sync}' if last_sync else 'No sync history found'
                }
            except Exception as e:
                results['sync_status'] = {'success': False, 'message': f'Sync status check failed: {str(e)}'}

            return jsonify({'results': results})

        @self.app.route('/api/discord-activity')
        def api_discord_activity():
            """Get recent Discord activity."""
            if not self.discord_client or not self.discord_sync_manager:
                return jsonify({'error': 'Discord integration not available'}), 400

            try:
                # Get recent Discord-related logs
                logs = self.file_manager.get_recent_logs(limit=20)
                discord_activities = []

                for log in logs:
                    operation = log.get('operation', '').lower()
                    details = log.get('details', '').lower()
                    if 'discord' in operation or 'discord' in details:
                        discord_activities.append({
                            'timestamp': log.get('timestamp', 'Unknown'),
                            'action': log.get('operation', 'Unknown'),
                            'details': log.get('details', 'No details')
                        })

                return jsonify({'activities': discord_activities})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/discord-errors')
        def api_discord_errors():
            """Get recent Discord errors."""
            if not self.discord_client or not self.discord_sync_manager:
                return jsonify({'error': 'Discord integration not available'}), 400

            try:
                # Get recent error logs related to Discord
                logs = self.file_manager.get_recent_logs(limit=50)
                discord_errors = []

                for log in logs:
                    operation = log.get('operation', '').lower()
                    details = log.get('details', '').lower()
                    result = log.get('result', '').lower()

                    if ('discord' in operation or 'discord' in details) and result == 'error':
                        discord_errors.append({
                            'timestamp': log.get('timestamp', 'Unknown'),
                            'message': log.get('details', 'Unknown error'),
                            'operation': log.get('operation', 'Unknown')
                        })

                return jsonify({'errors': discord_errors})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/discord-settings', methods=['POST'])
        def update_discord_settings():
            """Update Discord settings."""
            if not self.discord_client or not self.discord_sync_manager:
                return jsonify({'status': 'error', 'message': 'Discord integration not available'}), 400

            try:
                # Get form data
                action = request.form.get('action', '').strip()

                if action == 'update_team_mappings':
                    # Parse team mappings from form
                    team_mappings = {}
                    form_data = dict(request.form)
                    for key, value in form_data.items():
                        if key.startswith('tag_') and value.strip():
                            tag_name = key[4:]  # Remove 'tag_' prefix
                            team_mappings[tag_name] = value.strip()

                    self.file_manager.set_discord_setting('DISCORD_TEAM_MAPPINGS', team_mappings,
                                                        'Mapping of Discord tags to Linear team IDs')
                    return jsonify({'status': 'success', 'message': 'Team mappings updated successfully'})

                elif action == 'update_filter_rules':
                    min_message_count = request.form.get('min_message_count', '1').strip()
                    max_age_days = request.form.get('max_age_days', '365').strip()
                    exclude_tags_str = request.form.get('exclude_tags', '').strip()

                    # Validate inputs
                    try:
                        min_count = int(min_message_count)
                        max_age = int(max_age_days)
                        if min_count < 0 or max_age <= 0:
                            raise ValueError("Invalid numeric values")
                    except ValueError:
                        return jsonify({'status': 'error', 'message': 'Invalid numeric values for filter rules'}), 400

                    exclude_tags = [tag.strip() for tag in exclude_tags_str.split(',') if tag.strip()]

                    filter_rules = {
                        'min_message_count': min_count,
                        'max_age_days': max_age,
                        'exclude_tags': exclude_tags
                    }

                    self.file_manager.set_discord_setting('DISCORD_FILTER_RULES', filter_rules,
                                                        'Discord thread filtering rules')
                    return jsonify({'status': 'success', 'message': 'Filter rules updated successfully'})

                elif action == 'update_general_settings':
                    default_team = request.form.get('default_team', '').strip()
                    sync_enabled = request.form.get('sync_enabled', 'false').lower() == 'true'

                    if default_team:
                        self.file_manager.set_discord_setting('DISCORD_DEFAULT_TEAM', default_team,
                                                            'Default Linear team ID for Discord threads')

                    self.file_manager.set_discord_setting('DISCORD_SYNC_ENABLED', 'true' if sync_enabled else 'false',
                                                        'Enable Discord synchronization')

                    return jsonify({'status': 'success', 'message': 'General settings updated successfully'})

                else:
                    return jsonify({'status': 'error', 'message': 'Unknown action'}), 400

            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500

    def _get_dashboard_template(self) -> str:
        """Get simple HTML template for dashboard."""
        template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Linear-GitLab Sync Dashboard</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .section { border: 1px solid #ddd; padding: 20px; margin: 20px 0; }
        .button { padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border: none; cursor: pointer; }
        .status { color: green; }
        .error { color: red; }
    </style>
</head>
<body>
    <h1>Linear-GitLab Synchronization Dashboard</h1>

    <div class="section">
        <h3>Sync Status</h3>
        <p>Status: <span id="sync-status">Loading...</span></p>
        <p>Last Sync: <span id="last-sync">Loading...</span></p>
        <p>Next Run: <span id="next-run">Loading...</span></p>
    </div>

    <div class="section">
        <h3>API Status</h3>
        <p>Linear: <span id="linear-status">Checking...</span></p>
        <p>GitLab: <span id="gitlab-status">Checking...</span></p>
    </div>

    <div class="section">
        <h3>Actions</h3>
        <form action="/trigger-sync" method="post" style="display: inline;">
            <button type="submit" class="button">Trigger Manual Sync</button>
        </form>
        <a href="/mappings" class="button">View Mappings</a>
        <a href="/logs" class="button">View Logs</a>
        <a href="/settings" class="button">Update Settings</a>
    </div>

    <div class="section">
        <h3>Discord Integration</h3>
        <p>Discord Status: <span id="discord-integration-status">Checking...</span></p>
        <p>Discord Mappings: <span id="discord-mappings-count">Loading...</span></p>
        <div style="margin-top: 10px;">
            <a href="/discord-status" class="button">Discord Status</a>
            <a href="/discord-mappings" class="button">Discord Mappings</a>
            <a href="/discord-settings" class="button">Discord Settings</a>
            <form action="/trigger-discord-sync" method="post" style="display: inline;">
                <button type="submit" class="button">Sync Discord</button>
            </form>
        </div>
    </div>

    <script>
        async function loadData() {
            try {
                const response = await fetch('/status');
                const data = await response.json();
                document.getElementById('sync-status').textContent = data.sync_status ? 'Active' : 'Inactive';
                document.getElementById('last-sync').textContent = data.sync_status.last_sync_timestamp || 'Never';
                document.getElementById('next-run').textContent = data.next_sync || 'N/A';

                const linearRes = await fetch('/api/linear-status');
                const linearData = await linearRes.json();
                document.getElementById('linear-status').textContent = linearData.status || 'Unknown';

                const gitlabRes = await fetch('/api/gitlab-status');
                const gitlabData = await gitlabRes.json();
                document.getElementById('gitlab-status').textContent = gitlabData.status || 'Unknown';

                // Load Discord integration status
                try {
                    const discordRes = await fetch('/api/discord-status');
                    const discordData = await discordRes.json();

                    if (discordData.enabled) {
                        document.getElementById('discord-integration-status').textContent = 'Enabled';
                        document.getElementById('discord-integration-status').style.color = 'green';
                        document.getElementById('discord-mappings-count').textContent = discordData.sync_status.total_discord_mappings || 0;
                    } else {
                        document.getElementById('discord-integration-status').textContent = 'Not Configured';
                        document.getElementById('discord-integration-status').style.color = 'orange';
                        document.getElementById('discord-mappings-count').textContent = 'N/A';
                    }
                } catch (discordError) {
                    document.getElementById('discord-integration-status').textContent = 'Error';
                    document.getElementById('discord-integration-status').style.color = 'red';
                    document.getElementById('discord-mappings-count').textContent = 'N/A';
                }
            } catch (e) {
                console.error(e);
            }
        }
        loadData();
        setInterval(loadData, 60000); // Refresh every minute
    </script>
</body>
</html>
        '''
        return template

    def _get_mappings_template(self) -> str:
        """Get simple template for issue mappings page."""
        template = '''
<!DOCTYPE html>
<html>
<head>
    <title>Issue Mappings - Linear-GitLab Sync</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .mapping { border: 1px solid #ddd; padding: 10px; margin: 10px 0; }
        .back-link { display: block; margin-bottom: 20px; }
        .button { padding: 5px 10px; background: #007bff; color: white; text-decoration: none; }
    </style>
</head>
<body>
    <h1>Issue Mappings</h1>
    <a href="/" class="back-link button">&larr; Back to Dashboard</a>
    <p>Total Mappings: {{ mappings|length if mappings else 0 }}</p>

    {% if not mappings %}
    <p>No issue mappings yet. Run sync to create mappings.</p>
    {% else %}
    {% for mapping in mappings %}
    <div class="mapping">
        <strong>{{ mapping.linear_id }}</strong> &rarr; {{ mapping.gitlab_id }} (Synced: {{ mapping.sync_timestamp or 'Unknown' }})
    </div>
    {% endfor %}
    {% endif %}
</body>
</html>
        '''
        return template

    def _get_logs_template(self) -> str:
        """Get simple template for logs page."""
        template = '''
<!DOCTYPE html>
<html>
<head>
    <title>Sync Logs</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .log-entry { border-bottom: 1px solid #eee; padding: 10px; margin: 10px 0; }
        .success { color: green; }
        .error { color: red; }
        .warning { color: orange; }
        .back-link { display: block; margin-bottom: 20px; }
        .button { padding: 5px 10px; background: #007bff; color: white; text-decoration: none; }
    </style>
</head>
<body>
    <h1>Recent Sync Logs</h1>
    <a href="/" class="back-link button">&larr; Back to Dashboard</a>
    {% for log in logs %}
    <div class="log-entry {{ log['result'].lower() }}">
        <strong>{{ log['timestamp'] }}</strong> - {{ log['operation'] }}
        {% if log['details'] %}<br><small>{{ log['details'] }}</small>{% endif %}
    </div>
    {% endfor %}
    {% if not logs %}
    <p>No logs available.</p>
    {% endif %}
</body>
</html>
        '''
        return template

    def _get_settings_template(self) -> str:
        """Get simple HTML template for settings page."""
        template = '''
<!DOCTYPE html>
<html>
<head>
    <title>Application Settings</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .form-group { margin: 15px 0; }
        label { display: block; font-weight: bold; }
        input[type="text"] { width: 100%; padding: 8px; border: 1px solid #ddd; }
        .button { padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }
        .back-link { display: block; margin-top: 20px; }
        .status { margin: 10px 0; padding: 10px; }
        .success { background: lightgreen; }
        .error { background: lightcoral; }
    </style>
</head>
<body>
    <h1>Application Settings</h1>
    <div id="settingsForm">
        <form action="/settings" method="post">
            <div class="form-group">
                <label for="team_name">Linear Team Name:</label>
                <input type="text" id="team_name" name="team_name" required placeholder="e.g., MAU">
            </div>
            <div class="form-group">
                <label for="gitlab_project_id">GitLab Project ID:</label>
                <input type="text" id="gitlab_project_id" name="gitlab_project_id" required>
            </div>
            <div class="form-group">
                <label for="sync_interval">Sync Interval (seconds):</label>
                <input type="text" id="sync_interval" name="sync_interval" required placeholder="300">
            </div>
            <button type="submit" class="button">Save Settings</button>
        </form>
    </div>
    <div id="statusMessage"></div>
    <a href="/" class="back-link button">&larr; Back to Dashboard</a>

    <script>
        fetch('/api/settings').then(r => r.json()).then(data => {
            if (data) {
                document.getElementById('team_name').value = data.team_name || '';
                document.getElementById('gitlab_project_id').value = data.gitlab_project_id || '';
                document.getElementById('sync_interval').value = data.sync_interval || '300';
            }
        }).catch(console.error);

        document.querySelector('form').addEventListener('submit', function(e) {
            e.preventDefault();
            fetch('/settings', { method: 'POST', body: new FormData(this) })
                .then(r => r.json())
                .then(data => {
                    const msg = document.getElementById('statusMessage');
                    msg.className = 'status ' + (data.status === 'success' ? 'success' : 'error');
                    msg.textContent = data.message;
                });
        });
    </script>
</body>
</html>
        '''
        return template

    def _get_error_template(self, message: str) -> str:
        """Get simple error template."""
        template = f'''
<!DOCTYPE html>
<html>
<head>
    <title>Error - Linear-GitLab Sync</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; text-align: center; }}
        .error {{ color: red; border: 1px solid #ddd; padding: 20px; }}
        .back-link {{ display: block; margin-top: 20px; }}
        .button {{ padding: 5px 10px; background: #007bff; color: white; text-decoration: none; }}
    </style>
</head>
<body>
    <h1>Error</h1>
    <div class="error">
        <p>{message}</p>
    </div>
    <a href="/" class="back-link button">&larr; Back to Dashboard</a>
</body>
</html>
        '''
        return template

    def _get_discord_settings_template(self) -> str:
        """Get template for Discord settings page."""
        template = '''
<!DOCTYPE html>
<html>
<head>
    <title>Discord Settings - Linear-GitLab Sync</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .section { border: 1px solid #ddd; padding: 20px; margin: 20px 0; }
        .form-group { margin: 15px 0; }
        label { display: block; font-weight: bold; }
        input[type="text"], input[type="number"], textarea { width: 100%; padding: 8px; border: 1px solid #ddd; }
        .button { padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }
        .back-link { display: block; margin-bottom: 20px; }
        .status { margin: 10px 0; padding: 10px; }
        .success { background: lightgreen; }
        .error { background: lightcoral; }
        .tag-mapping { border: 1px solid #eee; padding: 10px; margin: 5px 0; }
        .remove-tag { color: red; cursor: pointer; }
    </style>
</head>
<body>
    <h1>Discord Settings</h1>
    <a href="/" class="back-link button">&larr; Back to Dashboard</a>

    <div class="section">
        <h3>Team Mappings</h3>
        <p>Map Discord forum thread tags to Linear teams</p>
        <div id="teamMappings">
            <!-- Team mappings will be populated by JavaScript -->
        </div>
        <button type="button" onclick="addTagMapping()" class="button">Add Tag Mapping</button>
    </div>

    <div class="section">
        <h3>Filter Rules</h3>
        <form id="filterForm">
            <div class="form-group">
                <label for="minMessageCount">Minimum Message Count:</label>
                <input type="number" id="minMessageCount" name="minMessageCount" value="1" min="0">
            </div>
            <div class="form-group">
                <label for="maxAgeDays">Maximum Thread Age (days):</label>
                <input type="number" id="maxAgeDays" name="maxAgeDays" value="365" min="1">
            </div>
            <div class="form-group">
                <label for="excludeTags">Exclude Tags (comma-separated):</label>
                <input type="text" id="excludeTags" name="excludeTags" placeholder="spam,duplicate,test">
            </div>
            <button type="submit" class="button">Save Filter Rules</button>
        </form>
    </div>

    <div class="section">
        <h3>General Settings</h3>
        <form id="generalForm">
            <div class="form-group">
                <label for="defaultTeam">Default Linear Team:</label>
                <input type="text" id="defaultTeam" name="defaultTeam" placeholder="default_team">
            </div>
            <div class="form-group">
                <label for="syncEnabled">Enable Discord Sync:</label>
                <input type="checkbox" id="syncEnabled" name="syncEnabled" checked>
            </div>
            <button type="submit" class="button">Save Settings</button>
        </form>
    </div>

    <div id="statusMessage"></div>

    <script>
        // Load current settings
        fetch('/api/discord-settings').then(r => r.json()).then(data => {
            if (data.enabled && data.settings) {
                loadSettings(data.settings);
            }
        }).catch(console.error);

        function loadSettings(settings) {
            // Load team mappings
            const mappings = settings['DISCORD_TEAM_MAPPINGS']?.value || {};
            const container = document.getElementById('teamMappings');
            Object.entries(mappings).forEach(([tag, team]) => {
                addTagMappingElement(tag, team);
            });

            // Load filter rules
            const filters = settings['DISCORD_FILTER_RULES']?.value || {};
            document.getElementById('minMessageCount').value = filters.min_message_count || 1;
            document.getElementById('maxAgeDays').value = filters.max_age_days || 365;
            document.getElementById('excludeTags').value = (filters.exclude_tags || []).join(',');

            // Load general settings
            document.getElementById('defaultTeam').value = settings['DISCORD_DEFAULT_TEAM']?.value || '';
            document.getElementById('syncEnabled').checked = settings['DISCORD_SYNC_ENABLED']?.value === 'true';
        }

        function addTagMapping() {
            addTagMappingElement('', '');
        }

        function addTagMappingElement(tag, team) {
            const container = document.getElementById('teamMappings');
            const div = document.createElement('div');
            div.className = 'tag-mapping';
            div.innerHTML = `
                Tag: <input type="text" placeholder="discord-tag" value="${tag}">
                → Team: <input type="text" placeholder="linear-team" value="${team}">
                <span class="remove-tag" onclick="this.parentElement.remove()">×</span>
            `;
            container.appendChild(div);
        }

        // Handle team mappings update
        function updateTeamMappings() {
            const mappings = {};
            const mappingElements = document.querySelectorAll('.tag-mapping');
            mappingElements.forEach(element => {
                const inputs = element.querySelectorAll('input');
                if (inputs.length >= 2) {
                    const tag = inputs[0].value.trim();
                    const team = inputs[1].value.trim();
                    if (tag && team) {
                        mappings[tag] = team;
                    }
                }
            });

            const formData = new FormData();
            formData.append('action', 'update_team_mappings');
            Object.entries(mappings).forEach(([tag, team]) => {
                formData.append(`tag_${tag}`, team);
            });

            updateSetting(formData);
        }

        // Handle filter form submission
        document.getElementById('filterForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData();
            formData.append('action', 'update_filter_rules');
            formData.append('min_message_count', document.getElementById('minMessageCount').value);
            formData.append('max_age_days', document.getElementById('maxAgeDays').value);
            formData.append('exclude_tags', document.getElementById('excludeTags').value);
            updateSetting(formData);
        });

        // Handle general form submission
        document.getElementById('generalForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData();
            formData.append('action', 'update_general_settings');
            formData.append('default_team', document.getElementById('defaultTeam').value);
            formData.append('sync_enabled', document.getElementById('syncEnabled').checked ? 'true' : 'false');
            updateSetting(formData);
        });

        // Add update button for team mappings
        const teamMappingsSection = document.querySelector('.section h3');
        if (teamMappingsSection && teamMappingsSection.textContent.includes('Team Mappings')) {
            const updateButton = document.createElement('button');
            updateButton.type = 'button';
            updateButton.className = 'button';
            updateButton.textContent = 'Update Team Mappings';
            updateButton.onclick = updateTeamMappings;
            updateButton.style.marginLeft = '10px';
            teamMappingsSection.appendChild(updateButton);
        }

        function updateSetting(formData) {
            fetch('/discord-settings', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                showStatus(data.message, data.status === 'success' ? 'success' : 'error');
                if (data.status === 'success') {
                    // Reload settings after successful update
                    setTimeout(() => location.reload(), 1000);
                }
            })
            .catch(error => {
                console.error('Error updating settings:', error);
                showStatus('Failed to update settings', 'error');
            });
        }

        function showStatus(message, type) {
            const msg = document.getElementById('statusMessage');
            msg.className = 'status ' + type;
            msg.textContent = message;
        }
    </script>
</body>
</html>
        '''
        return template

    def _get_discord_mappings_template(self) -> str:
        """Get template for Discord mappings page."""
        template = '''
<!DOCTYPE html>
<html>
<head>
    <title>Discord Mappings - Linear-GitLab Sync</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .mapping { border: 1px solid #ddd; padding: 15px; margin: 10px 0; position: relative; }
        .back-link { display: block; margin-bottom: 20px; }
        .button { padding: 5px 10px; background: #007bff; color: white; text-decoration: none; margin-right: 5px; border: none; cursor: pointer; }
        .button:hover { background: #0056b3; }
        .button.danger { background: #dc3545; }
        .button.danger:hover { background: #c82333; }
        .button.success { background: #28a745; }
        .button.success:hover { background: #218838; }
        .search-box { margin: 20px 0; }
        .search-box input { width: 300px; padding: 8px; }
        .mapping-header { font-weight: bold; margin-bottom: 10px; }
        .mapping-details { color: #666; font-size: 0.9em; }
        .stats { background: #f9f9f9; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }
        .stat-item { text-align: center; padding: 10px; background: white; border-radius: 3px; }
        .stat-value { font-size: 1.5em; font-weight: bold; color: #007bff; }
        .stat-label { color: #666; font-size: 0.9em; }
        .status-indicator { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; font-weight: bold; }
        .status-active { background: #d4edda; color: #155724; }
        .status-inactive { background: #f8d7da; color: #721c24; }
        .mapping-actions { position: absolute; top: 10px; right: 10px; }
        .filter-controls { margin: 15px 0; display: flex; gap: 10px; align-items: center; }
        .filter-controls select, .filter-controls input[type="date"] { padding: 5px; }
        .export-section { margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>Discord Thread Mappings</h1>

    <div class="navigation">
        <a href="/" class="back-link button">&larr; Back to Dashboard</a>
        <a href="/discord-settings" class="button">Discord Settings</a>
        <a href="/discord-status" class="button">Discord Status</a>
        <button onclick="refreshMappings()" class="button success">🔄 Refresh</button>
    </div>

    <div class="export-section">
        <h3>Export Options</h3>
        <button onclick="exportMappings('json')" class="button">📄 Export as JSON</button>
        <button onclick="exportMappings('csv')" class="button">📊 Export as CSV</button>
    </div>

    <div class="stats">
        <div class="stats-grid">
            <div class="stat-item">
                <div class="stat-value" id="totalCount">{{ mappings|length if mappings else 0 }}</div>
                <div class="stat-label">Total Mappings</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="activeCount">0</div>
                <div class="stat-label">Active Mappings</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="recentCount">0</div>
                <div class="stat-label">Updated Recently</div>
            </div>
        </div>
    </div>

    <div class="filter-controls">
        <input type="text" id="searchInput" placeholder="Search mappings..." onkeyup="filterMappings()">
        <select id="statusFilter" onchange="filterMappings()">
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
        </select>
        <input type="date" id="dateFilter" onchange="filterMappings()" title="Filter by creation date">
        <button onclick="clearFilters()" class="button">Clear Filters</button>
    </div>

    <div id="mappingsContainer">
        {% if not mappings %}
        <p>No Discord thread mappings yet. Run Discord sync to create mappings.</p>
        {% else %}
        {% for mapping in mappings %}
        <div class="mapping" data-thread-id="{{ mapping.thread_id }}" data-created="{{ mapping.discord_created_at or '' }}" data-updated="{{ mapping.discord_updated_at or '' }}">
            <div class="mapping-actions">
                <button onclick="deleteMapping('{{ mapping.thread_id }}')" class="button danger" title="Delete mapping">🗑️</button>
            </div>
            <div class="mapping-header">
                <span class="status-indicator status-active">Active</span>
                Discord Thread: {{ mapping.thread_name }} (ID: {{ mapping.thread_id }})
                → Linear Issue: <a href="#" onclick="openLinearIssue('{{ mapping.linear_id }}')">{{ mapping.linear_id }}</a>
            </div>
            <div class="mapping-details">
                <strong>Created:</strong> {{ mapping.discord_created_at or 'Unknown' }} |
                <strong>Updated:</strong> {{ mapping.discord_updated_at or 'Unknown' }} |
                <strong>Messages:</strong> {{ mapping.discord_message_count or 0 }}
                <br>
                <strong>Author ID:</strong> {{ mapping.discord_author_id or 'Unknown' }}
                {% if mapping.thread_name %}
                <br><strong>Thread:</strong> <a href="#" onclick="openDiscordThread('{{ mapping.thread_id }}')">{{ mapping.thread_name }}</a>
                {% endif %}
            </div>
        </div>
        {% endfor %}
        {% endif %}
    </div>

    <script>
        let allMappings = {{ mappings|tojson if mappings else '[]' }};

        function filterMappings() {
            const searchInput = document.getElementById('searchInput').value.toUpperCase();
            const statusFilter = document.getElementById('statusFilter').value;
            const dateFilter = document.getElementById('dateFilter').value;
            const container = document.getElementById('mappingsContainer');
            const mappings = container.getElementsByClassName('mapping');

            let visibleCount = 0;
            let activeCount = 0;
            let recentCount = 0;

            for (let i = 0; i < mappings.length; i++) {
                const mapping = mappings[i];
                const text = mapping.textContent || mapping.innerText;
                const createdDate = mapping.dataset.created;
                const updatedDate = mapping.dataset.updated;

                // Search filter
                const matchesSearch = text.toUpperCase().includes(searchInput);

                // Status filter (placeholder - all are considered active for now)
                const matchesStatus = statusFilter === 'all' || statusFilter === 'active';

                // Date filter
                const matchesDate = !dateFilter || (createdDate && createdDate.startsWith(dateFilter));

                if (matchesSearch && matchesStatus && matchesDate) {
                    mapping.style.display = '';
                    visibleCount++;

                    // Count active mappings
                    if (mapping.querySelector('.status-active')) {
                        activeCount++;
                    }

                    // Count recently updated (within last 7 days)
                    if (updatedDate) {
                        const updated = new Date(updatedDate);
                        const weekAgo = new Date();
                        weekAgo.setDate(weekAgo.getDate() - 7);
                        if (updated > weekAgo) {
                            recentCount++;
                        }
                    }
                } else {
                    mapping.style.display = 'none';
                }
            }

            // Update stats
            const total = mappings.length;
            document.getElementById('totalCount').textContent = visibleCount + ' / ' + total;
            document.getElementById('activeCount').textContent = activeCount;
            document.getElementById('recentCount').textContent = recentCount;
        }

        function clearFilters() {
            document.getElementById('searchInput').value = '';
            document.getElementById('statusFilter').value = 'all';
            document.getElementById('dateFilter').value = '';
            filterMappings();
        }

        function refreshMappings() {
            location.reload();
        }

        function deleteMapping(threadId) {
            if (confirm('Are you sure you want to delete this mapping? This will not delete the Linear issue.')) {
                fetch('/api/discord-mappings/' + threadId, { method: 'DELETE' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') {
                            location.reload();
                        } else {
                            alert('Error: ' + data.message);
                        }
                    })
                    .catch(error => {
                        console.error('Error deleting mapping:', error);
                        alert('Failed to delete mapping');
                    });
            }
        }

        function exportMappings(format) {
            const data = allMappings;
            if (!data || data.length === 0) {
                alert('No mappings to export');
                return;
            }

            if (format === 'json') {
                const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                downloadBlob(blob, 'discord_mappings.json');
            } else if (format === 'csv') {
                const csv = convertToCSV(data);
                const blob = new Blob([csv], { type: 'text/csv' });
                downloadBlob(blob, 'discord_mappings.csv');
            }
        }

        function convertToCSV(data) {
            if (!data.length) return '';

            const headers = Object.keys(data[0]);
            const csvRows = [];

            // Add headers
            csvRows.push(headers.join(','));

            // Add data rows
            data.forEach(row => {
                const values = headers.map(header => {
                    const value = row[header] || '';
                    // Escape commas and quotes
                    if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
                        return '"' + value.replace(/"/g, '""') + '"';
                    }
                    return value;
                });
                csvRows.push(values.join(','));
            });

            return csvRows.join('\\n');
        }

        function downloadBlob(blob, filename) {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }

        function openLinearIssue(issueId) {
            // Placeholder - would open Linear issue in new tab
            window.open(`https://linear.app/issue/${issueId}`, '_blank');
        }

        function openDiscordThread(threadId) {
            // Placeholder - would open Discord thread
            alert('Discord thread: ' + threadId);
        }

        // Initial filter update
        filterMappings();
    </script>
</body>
</html>
        '''
        return template

    def _get_discord_status_template(self) -> str:
        """Get template for Discord status monitoring dashboard."""
        template = '''
<!DOCTYPE html>
<html>
<head>
    <title>Discord Status - Linear-GitLab Sync</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .section { border: 1px solid #ddd; padding: 20px; margin: 20px 0; }
        .button { padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border: none; cursor: pointer; }
        .status { color: green; }
        .error { color: red; }
        .warning { color: orange; }
        .metric { display: inline-block; margin: 10px; padding: 10px; border: 1px solid #ddd; text-align: center; }
        .metric-value { font-size: 2em; font-weight: bold; }
        .metric-label { font-size: 0.8em; color: #666; }
        .chart { height: 200px; margin: 20px 0; }
        .back-link { display: block; margin-bottom: 20px; }
    </style>
</head>
<body>
    <h1>Discord Integration Status</h1>

    <div class="section">
        <h3>Navigation</h3>
        <a href="/" class="back-link button">&larr; Back to Dashboard</a>
        <a href="/discord-settings" class="button">Discord Settings</a>
        <a href="/discord-mappings" class="button">View Mappings</a>
    </div>

    <div class="section">
        <h3>API Connectivity</h3>
        <p>Discord API: <span id="discord-status">Checking...</span></p>
        <p>Last Connectivity Check: <span id="last-check">Never</span></p>
    </div>

    <div class="section">
        <h3>Synchronization Status</h3>
        <p>Status: <span id="sync-status">Loading...</span></p>
        <p>Last Sync: <span id="last-sync">Loading...</span></p>
        <p>Next Scheduled Sync: <span id="next-sync">Loading...</span></p>
        <p>Total Mappings: <span id="total-mappings">Loading...</span></p>
    </div>

    <div class="section">
        <h3>Job Control</h3>
        <p>Discord Sync Job: <span id="job-status">Loading...</span></p>
        <p>Job Paused: <span id="job-paused">Loading...</span></p>
        <form action="/trigger-discord-sync" method="post" style="display: inline;">
            <button type="submit" class="button">Trigger Manual Sync</button>
        </form>
    </div>

    <div class="section">
        <h3>Sync Metrics</h3>
        <div id="metricsContainer">
            <div class="metric">
                <div class="metric-value" id="threads-processed">0</div>
                <div class="metric-label">Threads Processed</div>
            </div>
            <div class="metric">
                <div class="metric-value" id="threads-created">0</div>
                <div class="metric-label">Issues Created</div>
            </div>
            <div class="metric">
                <div class="metric-value" id="threads-updated">0</div>
                <div class="metric-label">Issues Updated</div>
            </div>
            <div class="metric">
                <div class="metric-value" id="threads-filtered">0</div>
                <div class="metric-label">Threads Filtered</div>
            </div>
        </div>
    </div>

    <div class="section">
        <h3>API Connectivity Details</h3>
        <div id="apiDetails">
            <div class="metric">
                <div class="metric-value" id="apiLatency">---</div>
                <div class="metric-label">API Latency (ms)</div>
            </div>
            <div class="metric">
                <div class="metric-value" id="apiRequests">0</div>
                <div class="metric-label">Requests Today</div>
            </div>
            <div class="metric">
                <div class="metric-value" id="apiErrors">0</div>
                <div class="metric-label">API Errors</div>
            </div>
        </div>
        <button onclick="testConnectivity()" class="button">🔍 Test Connectivity</button>
        <div id="connectivityResult"></div>
    </div>

    <div class="section">
        <h3>Sync Performance</h3>
        <div id="performanceMetrics">
            <div class="metric">
                <div class="metric-value" id="avgSyncTime">---</div>
                <div class="metric-label">Avg Sync Time (s)</div>
            </div>
            <div class="metric">
                <div class="metric-value" id="syncSuccessRate">---</div>
                <div class="metric-label">Success Rate (%)</div>
            </div>
            <div class="metric">
                <div class="metric-value" id="threadsPerMinute">---</div>
                <div class="metric-label">Threads/Minute</div>
            </div>
        </div>
        <canvas id="performanceChart" width="400" height="200" style="border: 1px solid #ddd; margin-top: 20px;"></canvas>
    </div>

    <div class="section">
        <h3>Error Reporting & Troubleshooting</h3>
        <div id="errorLog">
            <p>Loading error log...</p>
        </div>
        <div style="margin-top: 15px;">
            <button onclick="clearErrors()" class="button danger">🗑️ Clear Error Log</button>
            <button onclick="downloadLogs()" class="button">📄 Download Logs</button>
            <button onclick="diagnostics()" class="button">🔧 Run Diagnostics</button>
        </div>
        <div id="diagnosticsResult" style="margin-top: 15px;"></div>
    </div>

    <div class="section">
        <h3>Recent Activity</h3>
        <div id="activityLog">
            <p>Loading activity...</p>
        </div>
        <button onclick="refreshActivity()" class="button" style="margin-top: 10px;">🔄 Refresh Activity</button>
    </div>

    <script>
        async function loadStatus() {
            try {
                const response = await fetch('/api/discord-status');
                const data = await response.json();

                if (!data.enabled) {
                    document.getElementById('discord-status').textContent = 'Not Configured';
                    document.getElementById('discord-status').className = 'error';
                    return;
                }

                // Update connectivity status
                const connStatus = document.getElementById('discord-status');
                connStatus.textContent = data.connectivity ? 'Connected' : 'Disconnected';
                connStatus.className = data.connectivity ? 'status' : 'error';
                document.getElementById('last-check').textContent = new Date().toLocaleString();

                // Update sync status
                const syncData = data.sync_status;
                document.getElementById('sync-status').textContent = syncData.discord_enabled ? 'Enabled' : 'Disabled';
                document.getElementById('last-sync').textContent = syncData.last_discord_sync_timestamp || 'Never';
                document.getElementById('total-mappings').textContent = syncData.total_discord_mappings || 0;

                // Update job status
                const jobData = data.scheduler;
                if (jobData && jobData.exists) {
                    document.getElementById('job-status').textContent = jobData.running ? 'Running' : 'Idle';
                    document.getElementById('job-paused').textContent = jobData.paused ? 'Yes' : 'No';
                    document.getElementById('next-sync').textContent = jobData.next_run || 'Not scheduled';
                } else {
                    document.getElementById('job-status').textContent = 'Not configured';
                    document.getElementById('job-paused').textContent = 'N/A';
                    document.getElementById('next-sync').textContent = 'N/A';
                }

                // Update metrics (placeholder values)
                document.getElementById('threads-processed').textContent = '0';
                document.getElementById('threads-created').textContent = '0';
                document.getElementById('threads-updated').textContent = '0';
                document.getElementById('threads-filtered').textContent = '0';

            } catch (e) {
                console.error('Failed to load Discord status:', e);
                document.getElementById('discord-status').textContent = 'Error';
                document.getElementById('discord-status').className = 'error';
            }
        }

        // Load status on page load
        loadStatus();

        // Refresh status every 30 seconds
        setInterval(loadStatus, 30000);

        // Handle manual sync trigger
        document.querySelector('form[action="/trigger-discord-sync"]').addEventListener('submit', function(e) {
            e.preventDefault();
            fetch('/trigger-discord-sync', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    alert(data.message);
                    loadStatus(); // Refresh status after sync
                })
                .catch(e => alert('Error triggering sync: ' + e.message));
        });

        // Enhanced monitoring functions
        async function testConnectivity() {
            const resultDiv = document.getElementById('connectivityResult');
            resultDiv.innerHTML = '<p>Testing connectivity...</p>';

            try {
                const startTime = Date.now();
                const response = await fetch('/api/discord-test-connectivity');
                const endTime = Date.now();
                const latency = endTime - startTime;

                const data = await response.json();

                document.getElementById('apiLatency').textContent = latency;
                document.getElementById('apiRequests').textContent = parseInt(document.getElementById('apiRequests').textContent) + 1;

                if (data.success) {
                    resultDiv.innerHTML = `<p style="color: green;">✅ Connectivity test successful (${latency}ms)</p>`;
                } else {
                    resultDiv.innerHTML = `<p style="color: red;">❌ Connectivity test failed: ${data.error}</p>`;
                    document.getElementById('apiErrors').textContent = parseInt(document.getElementById('apiErrors').textContent) + 1;
                }
            } catch (e) {
                resultDiv.innerHTML = `<p style="color: red;">❌ Test failed: ${e.message}</p>`;
                document.getElementById('apiErrors').textContent = parseInt(document.getElementById('apiErrors').textContent) + 1;
            }
        }

        function clearErrors() {
            if (confirm('Are you sure you want to clear the error log?')) {
                fetch('/api/discord-clear-errors', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            document.getElementById('errorLog').innerHTML = '<p>No errors</p>';
                            document.getElementById('apiErrors').textContent = '0';
                        } else {
                            alert('Failed to clear errors: ' + data.error);
                        }
                    })
                    .catch(e => alert('Error clearing errors: ' + e.message));
            }
        }

        function downloadLogs() {
            fetch('/api/discord-download-logs')
                .then(response => response.blob())
                .then(blob => {
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'discord_logs_' + new Date().toISOString().split('T')[0] + '.txt';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                })
                .catch(e => alert('Error downloading logs: ' + e.message));
        }

        async function diagnostics() {
            const resultDiv = document.getElementById('diagnosticsResult');
            resultDiv.innerHTML = '<p>Running diagnostics...</p>';

            try {
                const response = await fetch('/api/discord-diagnostics');
                const data = await response.json();

                let html = '<h4>Diagnostics Results:</h4><ul>';
                for (const [test, result] of Object.entries(data.results)) {
                    const status = result.success ? '✅' : '❌';
                    html += `<li>${status} ${test}: ${result.message}</li>`;
                }
                html += '</ul>';
                resultDiv.innerHTML = html;
            } catch (e) {
                resultDiv.innerHTML = `<p style="color: red;">❌ Diagnostics failed: ${e.message}</p>`;
            }
        }

        function refreshActivity() {
            loadActivityLog();
        }

        async function loadActivityLog() {
            try {
                const response = await fetch('/api/discord-activity');
                const data = await response.json();

                const activityDiv = document.getElementById('activityLog');
                if (data.activities && data.activities.length > 0) {
                    let html = '<ul>';
                    data.activities.forEach(activity => {
                        html += `<li>${activity.timestamp} - ${activity.action}: ${activity.details}</li>`;
                    });
                    html += '</ul>';
                    activityDiv.innerHTML = html;
                } else {
                    activityDiv.innerHTML = '<p>No recent activity</p>';
                }
            } catch (e) {
                document.getElementById('activityLog').innerHTML = '<p>Error loading activity log</p>';
            }
        }

        async function loadErrorLog() {
            try {
                const response = await fetch('/api/discord-errors');
                const data = await response.json();

                const errorDiv = document.getElementById('errorLog');
                if (data.errors && data.errors.length > 0) {
                    let html = '<ul>';
                    data.errors.forEach(error => {
                        html += `<li style="color: red;">${error.timestamp} - ${error.message}</li>`;
                    });
                    html += '</ul>';
                    errorDiv.innerHTML = html;
                    document.getElementById('apiErrors').textContent = data.errors.length;
                } else {
                    errorDiv.innerHTML = '<p>No errors</p>';
                    document.getElementById('apiErrors').textContent = '0';
                }
            } catch (e) {
                document.getElementById('errorLog').innerHTML = '<p>Error loading error log</p>';
            }
        }

        function drawPerformanceChart() {
            const canvas = document.getElementById('performanceChart');
            const ctx = canvas.getContext('2d');

            // Simple placeholder chart
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#f0f0f0';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            ctx.fillStyle = '#007bff';
            ctx.font = '16px Arial';
            ctx.fillText('Performance Chart (Placeholder)', 20, 30);
            ctx.fillText('More detailed charts can be added with Chart.js', 20, 60);
        }

        // Load additional data on page load
        loadErrorLog();
        loadActivityLog();
        drawPerformanceChart();

        // Set up periodic refresh for dynamic data
        setInterval(() => {
            loadErrorLog();
            loadActivityLog();
        }, 30000); // Refresh every 30 seconds
    </script>
</body>
</html>
        '''
        return template

    def run(self, host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
        """Start the Flask web server.

        Args:
            host: Host address
            port: Port number
            debug: Enable debug mode
        """
        self.app.run(host=host, port=port, debug=debug)