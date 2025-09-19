# Linear-GitLab Synchronization Application

A **database-free**, **Docker-first** Python application that synchronizes issues between Linear (issue tracking) and GitLab (Git repository platform) using event-driven webhooks and JSON-based file persistence. Designed for minimal dependencies, reliable containerized deployment, and seamless integration with development workflows.

[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://docker.com)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

## 🏆 Key Highlights

- **🚀 Docker-Ready**: Optimized for containerized deployment with automated builds and persistent volumes
- **💾 Database-Free**: Lightweight JSON file persistence — no database setup required
- **⚡ Webhook-Driven**: Real-time synchronization triggered by Linear issue events
- **🔧 Configurable**: Environment-based configuration with web interface for runtime updates
- **📊 Monitoring**: Built-in web dashboard for status monitoring and manual operations
- **🛠️ CLI Interface**: Command-line tools for manual sync and configuration management
- **🔄 Reliable**: Exponential backoff retries and circuit breaker patterns for API resilience
- **📝 Structured Logging**: Comprehensive logging with file rotation and multiple verbosity levels

## 📋 Features

### Core Synchronization
- **Bi-directional Issue Sync**: Automatic creation of GitLab issues from Linear issues
- **Smart Filtering**: Prevents duplicate issues using JSON-based mapping system
- **Team-Based Sync**: Configurable team selection for targeted synchronization
- **Title Formatting**: Consistent issue titles with Linear ID prefixes
- **Label Assignment**: Automatic tagging with team and sync labels

### Comprehensive Field Synchronization
- **Assignee Sync**: Maps Linear assignees to GitLab users by email/name
- **Labels & Tags**: Syncs all Linear labels to GitLab
- **Priority & Weight**: Maps Linear priority to GitLab weight
- **Due Dates**: Syncs due dates between platforms
- **Estimates**: Uses Linear estimates as GitLab weight
- **Status Tracking**: Maintains issue state consistency
- **Parent-Child Relationships**: Links sub-issues in descriptions
- **Comments**: Syncs discussion threads with author attribution
- **Attachments**: Downloads Linear attachments and uploads to GitLab
- **Rich Descriptions**: Includes parent/child links and structured content

### Data Management
- **File-Based Persistence**: JSON files for mappings, settings, and timestamps
- **Configurable Settings**: Runtime configuration updates via web interface
- **Data Portability**: Easy backup and migration of synchronization data
- **Attachment Handling**: Automatic download and temporary file management
- **Comment Tracking**: Preserves full discussion history with metadata
- **User Mapping**: Cached assignee mappings between Linear and GitLab users

### Monitoring & Control
- **Web Dashboard**: Real-time status monitoring with statistics
- **Manual Operations**: Web-based controls for triggering syncs
- **API Endpoints**: RESTful health checks and status information
- **Webhook Integration**: Linear webhook support for immediate sync triggers

### Container Features
- **Docker Compose**: One-command deployment with volume mounting
- **Health Checks**: Automated container health monitoring
- **Volume Persistence**: Data survives container restarts
- **Port Management**: Exposed web interface on configurable ports

## 🚀 Quick Docker Start

```bash
# Clone and navigate
git clone <repository-url>
cd linear-gitlab-sync

# Configure API credentials
cp .env.example .env
# Edit .env with your Linear API key, GitLab token, and project ID

# Single-command deployment (recommended)
docker-compose up -d

# Access dashboard at http://localhost:5000
```

**🎯 That's it!** Your optimized sync service is running with:
- ✅ Multi-stage build for smaller image size
- ✅ Non-root user for security
- ✅ Persistent data volumes
- ✅ Automated health checks
- ✅ Production-ready logging and monitoring

## 📋 Prerequisites

- **Docker**: Version 20+ installed and running
- **Linear Access**: API key with read permissions for issues
- **GitLab Access**: Personal access token with project write permissions
- **GitLab Project**: Target project ID for issue creation

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in your project root:

```bash
# Required API Credentials
LINEAR_API_KEY=your_linear_api_key_here
GITLAB_TOKEN=your_gitlab_personal_access_token_here
GITLAB_PROJECT_ID=your_gitlab_project_id_here

# Optional Configuration
LINEAR_TEAM_NAME=MAU
SYNC_INTERVAL=300
LOG_LEVEL=INFO
DRY_RUN=false

# Feature Toggles (all default to true)
SYNC_ASSIGNMENTS=true
SYNC_LABELS=true
SYNC_ATTACHMENTS=true
SYNC_COMMENTS=true
SYNC_DUE_DATES=true
SYNC_PRIORITY=true
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LINEAR_API_KEY` | ✅ | - | Linear API key with issue read permissions |
| `GITLAB_TOKEN` | ✅ | - | GitLab personal access token with issue write permissions |
| `GITLAB_PROJECT_ID` | ✅ | - | Target GitLab project ID for issue creation |
| `LINEAR_TEAM_NAME` | ❌ | MAU | Linear team identifier to sync |
| `SYNC_INTERVAL` | ❌ | 300 | Automatic sync interval in seconds |
| `LOG_LEVEL` | ❌ | INFO | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |
| `DRY_RUN` | ❌ | false | Set to `true` for testing mode without creating GitLab issues |
| `SYNC_ASSIGNMENTS` | ❌ | true | Enable/disable assignee synchronization |
| `SYNC_LABELS` | ❌ | true | Enable/disable label synchronization |
| `SYNC_ATTACHMENTS` | ❌ | true | Enable/disable attachment synchronization |
| `SYNC_COMMENTS` | ❌ | true | Enable/disable comment synchronization |
| `SYNC_DUE_DATES` | ❌ | true | Enable/disable due date synchronization |
| `SYNC_PRIORITY` | ❌ | true | Enable/disable priority/weight synchronization |

### Data Persistence

The application stores all synchronization data in the mounted `/app/data` directory:

```
data/
├── mappings.json       # Issue ID mappings between Linear and GitLab
├── settings.json       # Runtime configuration and overrides
├── last_sync.txt       # Last synchronization timestamp
└── logs/
    └── sync.log        # Structured application logs
```

**Important**: Always mount a volume for data persistence:

```bash
docker run -v ./data:/app/data --env-file .env linear-gitlab-sync
```

## 🐳 Docker Deployment

### Using Docker Compose (Recommended)

```yaml
# docker-compose.yml (Updated with production optimizations)
version: '3.8'
services:
  linear-gitlab-sync:
    build: .
    container_name: linear-gitlab-sync
    env_file: .env
    environment:
      - PYTHONUNBUFFERED=1
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data:rw
      - ./logs:/app/logs:rw
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    security_opt:
      - no-new-privileges:true
    networks:
      - sync-network

networks:
  sync-network:
    driver: bridge
```

```bash
# Deploy
docker-compose up -d

# View logs
docker-compose logs -f

# Stop service
docker-compose down
```

### Manual Docker Commands

#### Single-Command Production Deployment

```bash
# Production-ready single command with all optimizations
docker run -d \
  --name linear-gitlab-sync \
  --env-file .env \
  --restart unless-stopped \
  --security-opt no-new-privileges:true \
  -v ./data:/app/data:rw \
  -v ./logs:/app/logs:rw \
  -p 5000:5000 \
  --health-cmd "curl -f http://localhost:5000/health" \
  --health-interval 30s \
  --health-timeout 10s \
  --health-retries 3 \
  --health-start-period 40s \
  linear-gitlab-sync
```

#### Development Deployment

```bash
# Build the image
docker build -t linear-gitlab-sync .

# Run with basic volume mounting
docker run -d \
  --name linear-sync \
  --env-file .env \
  -v ./data:/app/data \
  -p 5000:5000 \
  linear-gitlab-sync

# Execute commands within container
docker exec linear-sync python src/main.py status
docker exec linear-sync python src/main.py sync

# View container logs
docker logs -f linear-sync
```

### Building from Source

```bash
# Custom image build
docker build \
  --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
  -t linear-gitlab-sync:latest .
```

### Production Optimizations

The containerization setup includes several production-ready optimizations:

- **🚀 Multi-Stage Build**: Reduces final image size by separating build and runtime dependencies
- **🔒 Security**: Non-root user execution with `no-new-privileges` security option
- **📊 Health Monitoring**: Automated health checks with curl to `/health` endpoint
- **💾 Persistent Storage**: Proper volume mounting for data and logs
- **🔄 Restart Policies**: `unless-stopped` for reliable service management
- **📝 Structured Logging**: JSON-file driver with size limits and rotation
- **🌐 Network Isolation**: Dedicated Docker network for service communication

## 🌐 Web Interface

### Dashboard Features

Access the web interface at `http://localhost:5000` after deployment:

- **📊 Real-time Status**: Sync statistics, last run time, next scheduled sync
- **🔧 Configuration Management**: Update team and project settings via web form
- **📋 Issue Mappings**: View all synchronized issues with direct links
- **🚀 Manual Sync**: Trigger synchronization on demand
- **📝 Log Viewing**: Access recent activity logs
- **❤️ Health Monitoring**: Container health and API connectivity status

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard with full interface |
| `/status` | GET | JSON sync status and statistics |
| `/trigger-sync` | POST | Manual synchronization trigger |
| `/mappings` | GET | View all issue mappings with links |
| `/settings` | GET/POST | View and update configuration |
| `/logs` | GET | Recent synchronization logs |
| `/health` | GET | Basic health check |
| `/webhooks/linear/issue` | POST | Linear webhook handler |

### Webhook Integration

Configure Linear webhooks to point to your container's webhook endpoint:

1. In Linear, navigate to **Team Settings** → **Webhooks**
2. Create new webhook with URL: `https://your-domain.com/webhooks/linear/issue`
3. Select events: **Issue Created** and **Issue Updated**
4. The container will automatically trigger sync when issues change

## 🖥️ CLI Interface

### Container Commands

```bash
# Interactive CLI mode
docker exec -it linear-sync python src/main.py

# Manual synchronization
docker exec linear-sync python src/main.py sync

# View current status
docker exec linear-sync python src/main.py status

# Display logs location
docker exec linear-sync python src/main.py logs

# Show current configuration
docker exec linear-sync python src/main.py config
```

### CLI Usage Examples

```bash
# Status with JSON output
docker exec linear-sync python src/main.py status --json

# Manual sync with progress
docker exec linear-sync python src/main.py sync --json

# Configuration details
docker exec linear-sync python src/main.py config
```

## 🔄 Synchronization Logic

The sync process follows these steps for full synchronization:

### Sync Process Flow:

1. **Full Retrieval**: Query Linear API for all issues in the team (not just new ones)

2. **Per-Issue Processing**: For each Linear issue:
   ```python
   - Check if Linear ID exists in mappings.json
   - If NO mapping: Create new GitLab issue
   - If mapping exists: Compare with stored data
   - If Linear updatedAt > stored linear_updated_at: Update GitLab issue
   - If titles/descriptions differ: Update GitLab issue
   - If everything matches: Skip (no action needed)
   ```

3. **Change Detection Details**:
   - **Timestamp Comparison**: Linear's `updatedAt` vs stored `linear_updated_at` in mapping
   - **Content Comparison**: Clean title (remove `[LINEAR-ID]` prefix) and description
   - **Smart Updates**: Only updates GitLab when actual changes detected

4. **Mapping Storage**: Store/update mappings with Linear timestamps for future comparisons

5. **Actions Logged**: Each sync action categorized as 'created', 'updated', 'skip', or 'error'

### Why Each Issue Syncs or Doesn't:

| Scenario | Mapping Exists? | Linear Changed? | Content Different? | Action | Reason |
|----------|----------------|-----------------|-------------------|--------|---------|
| New Linear Issue | ❌ | - | - | **Create** | Not seen before, needs GitLab equivalent |
| Linear Updated | ✅ | ✅ | ❌ | **Update** | Timestamp shows recent change |
| Content Changed | ✅ | ❌ | ✅ | **Update** | Title/description modified |
| No Changes | ✅ | ❌ | ❌ | **Skip** | Everything matches, no sync needed |
| GitLab Issue Missing | ✅ | - | - | **Recreate** | GitLab issue was deleted, needs recreation |

### Detailed Decision Logging:

For each fetched issue, the system now logs a clear decision:

```
INFO: Linear issue LIN-123: CREATED - New Linear issue - no existing mapping found -> GitLab #456
INFO: Linear issue LIN-456: UPDATED - Linear issue has changes (timestamp/content) that need sync -> GitLab #789
INFO: Linear issue LIN-789: SKIP - No changes detected - Linear and GitLab are in sync
INFO: Linear issue LIN-999: RECREATED - GitLab issue missing - recreating based on mapping -> GitLab #123
```

### Prevention of Duplicates:
- **ID-Based Mapping**: Each Linear issue maps to exactly one GitLab issue by ID
- **Title Check**: During creation, searches GitLab for matching titles to avoid accidental duplicates
- **No Name-Based Creation**: Never creates based on title alone, only Linear ID guarantees uniqueness

### Full vs Incremental:
- **Previous**: Only synced issues newer than last sync timestamp
- **Current**: Syncs ALL issues every time, ensures no missed changes
- **Benefit**: Catches any updates that might have been missed, maintains synchronization

### Issue Title Format

GitLab issues are created with standardized titles:

```
[LINEAR-{issue_id}] {original_title}
```

## 🏗️ Project Architecture

```
linear-gitlab-sync/
├── Dockerfile                      # Container build configuration
├── docker-compose.yml             # Orchestration and deployment
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment template
├── src/                           # Application source
│   ├── main.py                   # Entry point and orchestrator
│   ├── sync_manager.py           # Core sync logic
│   ├── linear_client.py          # Linear API client
│   ├── gitlab_client.py          # GitLab API client
│   ├── file_manager.py           # JSON file operations
│   ├── config_manager.py         # Environment configuration
│   ├── web_interface.py          # Flask dashboard
│   ├── cli_interface.py          # Command-line interface
│   ├── error_logger.py           # Logging and error handling
│   └── scheduler.py              # Background sync scheduling
├── tests/                         # Unit and integration tests
└── data/                          # Container-mounted data (persistent)
    ├── mappings.json
    ├── settings.json
    ├── last_sync.txt
    └── logs/
```

## 🔗 API Integrations

### Linear API Integration
- **Protocol**: GraphQL over HTTPS
- **Endpoint**: `https://api.linear.app/graphql`
- **Scope**: Team-based issue queries with pagination
- **Authentication**: Bearer token authentication
- **Rate Limits**: Built-in retry logic with exponential backoff
- **Data**: Full issue details including title, description, status, labels

### GitLab API Integration
- **Protocol**: REST API v4 over HTTPS
- **Endpoint**: `https://gitlab.com/api/v4`
- **Scope**: Project-level issue creation and management
- **Authentication**: Personal access token
- **Rate Limits**: Respect GitLab's rate limiting policies
- **Data**: Issue creation with titles, descriptions, and labels

## 🛡️ Error Handling & Reliability

### Resilience Features
- **Exponential Backoff**: Automatic retry with increasing delays
- **Circuit Breaker**: Prevents cascade failures during API outages
- **Timeout Management**: Configurable request timeouts
- **Network Recovery**: Graceful handling of connection issues

### Logging Strategy
- **Structured Logging**: JSON format with consistent fields
- **Severity Levels**: DEBUG, INFO, WARNING, ERROR
- **File Rotation**: Automatic log file rotation
- **Performance**: Minimal I/O impact for operational logging

### Health Monitoring
- **Application Health**: Internal status checks
- **API Connectivity**: Linear and GitLab API availability
- **Container Health**: Docker health checks enabled
- **Metrics**: Basic sync statistics and error counts

## 🔍 Monitoring & Observability

### Container Logs
```bash
# View real-time application logs
docker-compose logs -f linear-gitlab-sync

# Filter specific log levels
docker logs linear-sync 2>&1 | grep ERROR
```

### Health Checks
```bash
# Container health status
docker ps --filter "name=linear-sync"

# Health endpoint
curl http://localhost:5000/health
```

### Metrics & Statistics
- **Sync Count**: Total issues processed
- **Last Sync Time**: Timestamp of most recent sync
- **API Status**: Connectivity health to both services
- **Error Rate**: Recent synchronization failures

## 🐛 Troubleshooting

### Common Issues

| Issue | Symptom | Solution |
|-------|---------|----------|
| **Sync Not Running** | No issues being created | Check container logs, verify API credentials |
| **API Permission Error** | 403 errors in logs | Ensure Linear read and GitLab write permissions |
| **Webhook Not Triggering** | Manual sync works, webhook doesn't | Verify webhook URL and event selection |
| **File Permission Error** | Data not persisting | Check volume mount and file permissions |
| **Container Not Starting** | `docker ps` shows unhealthy | Review environment variables and logs |

### Diagnostic Commands

```bash
# Check container status
docker-compose ps

# View detailed logs
docker-compose logs --tail=100 linear-gitlab-sync

# Test API connectivity
docker exec linear-sync python -c "
from src.config_manager import ConfigManager
from src.linear_client import LinearClient
import json
config = ConfigManager()
client = LinearClient(config)
try:
    issues = client.get_issues_since()
    print(f'Success: Retrieved {len(issues)} issues')
except Exception as e:
    print(f'Error: {e}')
"

# Validate JSON file integrity
docker exec linear-sync python -c "
import json
try:
    with open('/app/data/mappings.json', 'r') as f:
        data = json.load(f)
        print(f'Mappings file OK: {len(data)} entries')
except Exception as e:
    print(f'Mappings file error: {e}')
"
```

### Performance Considerations
- **Memory Usage**: Monitor container memory consumption
- **API Rate Limits**: Linear and GitLab have rate limits
- **Disk Space**: Logs and JSON files grow over time
- **Network Latency**: Webhooks may add network delay
- **Backup Strategy**: Regular data backup for the `/app/data` volume

## 🛠️ Development

### Local Development Setup

For development outside Docker (not recommended for production):

```bash
# Clone repository
git clone <repository-url>
cd linear-gitlab-sync

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Create data directory
mkdir data
mkdir data/logs

# Run application
python src/main.py --daemon

# Access web interface at http://localhost:5000
```

### Testing

```bash
# Run unit tests
pytest tests/

# Run with specific test
pytest tests/test_sync.py -v

# Test with coverage
pytest --cov=src --cov-report=html
```

## 📈 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for new functionality
4. Ensure all tests pass (`pytest`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Development Guidelines
- Follow existing code style and patterns
- Add comprehensive tests for new features
- Update documentation for configuration changes
- Ensure Docker compatibility
- Test with various sync scenarios
- Consider edge cases and error conditions

## 📄 License

This project is provided as-is without warranty. Use at your own risk.

Distributed under the MIT License. See LICENSE file for details.

## 🤝 Support

For issues and questions:
1. Check this README's troubleshooting section
2. Review container logs for error details
3. Verify API credentials and permissions
4. Try manual sync to isolate issues
5. Check webhook configuration if using webhooks

---

**🚀 Happy synchronizing!** Automate your Linear-GitLab workflow with this reliable, containerized solution.
