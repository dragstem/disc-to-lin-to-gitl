# 🚀 Linear-GitLab Sync Deployment Guide

## Single-Command Deployments

### Docker Compose (Recommended)

```bash
# Production deployment
docker-compose up -d

# View logs
docker-compose logs -f

# Stop service
docker-compose down
```

### Docker Run (Alternative)

```bash
# Production deployment with all optimizations
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

## Prerequisites

1. **Docker**: Version 20+ installed
2. **Environment File**: `.env` with API credentials
3. **Data Directory**: `./data/` for persistence
4. **Logs Directory**: `./logs/` for logging

## Configuration

Create `.env` file:

```bash
# Required
LINEAR_API_KEY=your_linear_api_key
GITLAB_TOKEN=your_gitlab_token
GITLAB_PROJECT_ID=your_project_id

# Optional
LINEAR_TEAM_NAME=your_team
SYNC_INTERVAL=300
LOG_LEVEL=INFO
```

## Access Points

- **Web Dashboard**: http://localhost:5000
- **Health Check**: http://localhost:5000/health
- **Container Logs**: `docker-compose logs -f`

## Production Features

- ✅ Multi-stage build (smaller image)
- ✅ Non-root user (security)
- ✅ Health checks (monitoring)
- ✅ Volume persistence (data safety)
- ✅ Auto-restart (reliability)
- ✅ Log rotation (maintenance)
- ✅ Network isolation (security)

## Troubleshooting

```bash
# Check container status
docker-compose ps

# View recent logs
docker-compose logs --tail=50

# Test health
curl http://localhost:5000/health

# Restart service
docker-compose restart
```

## Data Persistence

Data is stored in:
- `./data/mappings.json` - Issue mappings
- `./data/settings.json` - Configuration
- `./logs/sync.log` - Application logs

**Important**: Backup `./data/` directory regularly.