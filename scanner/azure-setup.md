# Azure Setup & Deployment Guide

## Overview

This document outlines the complete Azure deployment setup for the Swiss Parking Crawler application. The application is containerized and deployed to Azure Container Instances (ACI) with continuous data collection running every 15 minutes.

---

## Architecture

```
Local Development
    ↓
Docker Image Build (swissparkingcrawler:latest)
    ↓
Azure Container Registry (swissparkingregistry.azurecr.io)
    ↓
Azure Container Instances (swiss-parking-container)
    ↓
Continuous Parking Data Collection (Every 15 minutes)
```

---

## Azure Resources Created

### 1. Resource Group
- **Name:** `swiss-parking-rg`
- **Location:** West Europe
- **Purpose:** Container for all parking crawler resources

### 2. Azure Container Registry (ACR)
- **Name:** `swissparkingregistry`
- **SKU:** Basic
- **Login Server:** `swissparkingregistry.azurecr.io`
- **Admin:** Enabled
- **Purpose:** Stores and manages Docker images

### 3. Azure Container Instance (ACI)
- **Name:** `swiss-parking-container`
- **Image:** `swissparkingregistry.azurecr.io/swissparkingcrawler:latest`
- **OS:** Linux
- **CPU:** 1 core
- **Memory:** 1 GB
- **Port:** 80 (HTTP)
- **DNS Label:** `swiss-parking-crawler`
- **FQDN:** `swiss-parking-crawler.westeurope.azurecontainer.io`
- **Status:** Running
- **Purpose:** Executes the scheduler and data collection with web server

### Database Configuration
- **Host:** `parkhaus.roil.ch`
- **User:** `crawler`
- **Database:** `ph_fetch`
- **Port:** 3306 (MySQL)

---

## Setup Process (Completed)

### Step 1: Docker Image Build
Built a Docker image locally with all dependencies:
```bash
docker build --pull --rm -f 'Dockerfile' -t 'swissparkingcrawler:latest' '.'
```

### Step 2: Azure Authentication
Logged in to Azure:
```bash
az login
```

### Step 3: Create Resource Group
```bash
az group create --name swiss-parking-rg --location westeurope
```

### Step 4: Register Azure Providers
Registered required resource providers:
```bash
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.ContainerInstance
```

### Step 5: Create Azure Container Registry
```bash
az acr create --resource-group swiss-parking-rg --name swissparkingregistry --sku Basic
```

### Step 6: Enable Admin Access
```bash
az acr update -n swissparkingregistry --admin-enabled true
```

### Step 7: Login to ACR
```bash
az acr login --name swissparkingregistry
```

### Step 8: Tag Docker Image
```bash
docker tag swissparkingcrawler:latest swissparkingregistry.azurecr.io/swissparkingcrawler:latest
```

### Step 9: Push to Azure Container Registry
```bash
docker push swissparkingregistry.azurecr.io/swissparkingcrawler:latest
```

### Step 10: Deploy to Azure Container Instances
```powershell
$password = az acr credential show --name swissparkingregistry --query passwords[0].value -o tsv
az container create `
  --resource-group swiss-parking-rg `
  --name swiss-parking-container `
  --image swissparkingregistry.azurecr.io/swissparkingcrawler:latest `
  --os-type Linux `
  --cpu 1 `
  --memory 1 `
  --ports 80 `
  --dns-name-label swiss-parking-crawler `
  --registry-login-server swissparkingregistry.azurecr.io `
  --registry-username swissparkingregistry `
  --registry-password $password `
  --environment-variables DB_HOST=parkhaus.roil.ch DB_USER=crawler DB_PASSWORD='xxxx' DB_NAME=ph_fetch DB_PORT=3306
```

**Important:** The container now:
- Exposes **port 80** for HTTP traffic
- Creates DNS name label `swiss-parking-crawler` for FQDN access
- Passes database credentials as environment variables

---

## Container Management Commands

### View Container Status
```bash
az container show --resource-group swiss-parking-rg --name swiss-parking-container --query "instanceView.state" -o tsv
```

### View Container Logs
```bash
az container logs --resource-group swiss-parking-rg --name swiss-parking-container
```

### Stop Container
```bash
az container stop --resource-group swiss-parking-rg --name swiss-parking-container
```

### Restart Container
```bash
az container restart --resource-group swiss-parking-rg --name swiss-parking-container
```

### View Full Container Details
```bash
az container show --resource-group swiss-parking-rg --name swiss-parking-container
```

### List All Resources in Resource Group
```bash
az resource list --resource-group swiss-parking-rg
```

---

## Scheduler Implementation

### Scheduler Script: `scheduler.py`

A Python scheduler runs inside the container that executes `collect_data.py` every 15 minutes.

**Features:**
- Runs `collect_data.py` on startup
- Schedules data collection every 15 minutes
- Logs execution timestamps
- Reports success/failure status
- Handles errors gracefully
- Continuous operation with keyboard interrupt handling

**Dependencies:**
- `schedule` library (added to `requirements.txt`)

**Key Components:**
```python
# Schedule the job to run every 15 minutes
schedule.every(15).minutes.do(run_collect_data)

# Run the first collection immediately
run_collect_data()

# Keep the scheduler running
while True:
    schedule.run_pending()
    time.sleep(1)
```

---

## Data Collection Details

### Data Collection Process
The scheduler runs the multi-city parking data collection which:
1. Fetches parking data from 5 Swiss cities:
   - Luzern
   - Basel
   - St. Gallen
   - Zürich
   - Bern

2. Normalizes the data according to city-specific formats

3. Saves data to configured database (MySQL)

4. Generates collection summary with statistics:
   - Records inserted
   - Duplicates skipped
   - Failed records

### Last Execution Summary
```
City            Status     Inserted   Duplicates   Failed
------------------------------------------------------------
luzern          ✓ Success  15         0            0
basel           ✓ Success  16         0            0
stgallen        ✓ Success  16         0            0
zurich          ✓ Success  36         0            0
bern            ✓ Success  15         0            0
------------------------------------------------------------
TOTAL                      98         0            0
```

---

## Database Configuration

The container uses the database configuration from `db_config.json`:
```json
{
  "host": "your-db-host",
  "user": "your-db-user",
  "password": "your-db-password",
  "database": "parking_db"
}
```

**Note:** Ensure the database connection is properly configured in `db_config.json` before deploying.

---

## Docker Configuration

### Dockerfile Details
- **Base Image:** Python (compatible with application requirements)
- **Working Directory:** `/app`
- **Entrypoint:** Runs the scheduler script
- **Exposed Ports:** None (background process)

### Requirements
The following packages are installed:
- `requests` - HTTP client for API calls
- `mysql-connector-python` - Database connectivity
- `schedule` - Job scheduling library

---

## Monitoring & Logging

### View Recent Logs
```bash
az container logs --resource-group swiss-parking-rg --name swiss-parking-container --tail 50
```

### Check Container Status
```bash
az container show --resource-group swiss-parking-rg --name swiss-parking-container --query "containers[0].instanceView"
```

### Monitor Resource Usage
The container is configured with:
- **CPU Limit:** 1 core
- **Memory Limit:** 1 GB

These settings can be adjusted based on actual usage patterns.

---

## Troubleshooting

### Container Won't Start
1. Check image exists in registry:
   ```bash
   az acr repository show --name swissparkingregistry --repository swissparkingcrawler
   ```

2. Verify credentials:
   ```bash
   az acr credential show --name swissparkingregistry
   ```

3. Check deployment logs:
   ```bash
   az container logs --resource-group swiss-parking-rg --name swiss-parking-container
   ```

### Database Connection Issues
1. Verify `db_config.json` is correct
2. Check database is accessible from Azure
3. Review container logs for connection errors

### Out of Memory
Increase memory allocation:
```bash
az container delete --resource-group swiss-parking-rg --name swiss-parking-container
# Recreate with more memory
```

---

## Cost Optimization

### Current Configuration Costs
- **Azure Container Instances:** ~$0.0000015 per second (Linux)
- **Azure Container Registry:** ~$5/month (Basic SKU)

### Cost Reduction Options
1. Use Azure Functions instead of ACI for scheduled tasks
2. Adjust CPU/Memory based on actual needs
3. Use spot instances when available

---

## Future Improvements

1. **Add Application Insights** for better monitoring
2. **Implement Azure Key Vault** for secure credential storage
3. **Create CI/CD Pipeline** using Azure DevOps or GitHub Actions
4. **Add Health Checks** to container
5. **Implement Email Alerts** for failures
6. **Add Backup Strategy** for collected data
7. **Consider Azure App Service** if web interface is added

---

## Important Endpoints & URLs

### Azure Portal
- Resource Group: https://portal.azure.com/#resource/subscriptions/4e4e8e02-57a2-4482-9fd4-52c760203617/resourceGroups/swiss-parking-rg

### Container Registry
- Login Server: `swissparkingregistry.azurecr.io`
- Repository: `swissparkingcrawler`
- Tag: `latest`

---

## Contact & Support

For questions or issues:
1. Check Azure Portal for resource health
2. Review container logs
3. Verify database connectivity
4. Ensure all configuration files are present

---

## Deployment History

- **Date:** January 15, 2026
- **Deployed By:** Parking Crawler Team
- **Initial Status:** ✅ Running
- **First Execution:** Successful (98 records collected)
- **Next Execution:** Every 15 minutes (automatic)

---

**Last Updated:** January 15, 2026
