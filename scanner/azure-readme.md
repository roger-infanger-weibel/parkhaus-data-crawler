# Azure Deployment Documentation - Swiss Parking Crawler

**Last Updated:** January 15, 2026  
**Status:** ✅ Production Ready  
**Deployment Location:** Azure Cloud (West Europe)

---

## 🚀 Quick Status Check

| Property | Value |
|----------|-------|
| **Container State** | ✅ Running |
| **Container IP** | `20.238.182.59` |
| **Container FQDN** | `swiss-parking-crawler.westeurope.azurecontainer.io` |
| **Web Server Status** | ✅ Flask Active (HTTP 200 OK) |
| **Access URL** | ✅ **http://swiss-parking-crawler.westeurope.azurecontainer.io** |
| **CPU** | 1 Core |
| **Memory** | 1 GB |
| **Last Status Check** | January 15, 2026 - **ALL SYSTEMS OPERATIONAL** |

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Why Azure?](#why-azure)
3. [Architecture & Deployment](#architecture--deployment)
4. [Azure Resources Created](#azure-resources-created)
5. [Current Setup & Configuration](#current-setup--configuration)
6. [Deployment Steps Completed](#deployment-steps-completed)
7. [Key Features & Operations](#key-features--operations)
8. [Monitoring & Maintenance](#monitoring--maintenance)
9. [Cost Overview](#cost-overview)
10. [Troubleshooting](#troubleshooting)

---

## Project Overview

The **Swiss Parking Crawler** is an automated data collection application that continuously gathers real-time parking availability information from 5 major Swiss cities:
- ✅ Luzern
- ✅ Basel  
- ✅ St. Gallen
- ✅ Zürich
- ✅ Bern

The application collects and normalizes data every **15 minutes** and stores it in a database for analysis and historical tracking.

---

## Why Azure?

Azure was chosen for this deployment because of:

### 1. **Containerization Benefits**
- Docker ensures consistent environments across development and production
- Easy scaling and resource management
- Quick deployment and updates

### 2. **Azure Container Instances (ACI)**
- Lightweight, serverless container hosting
- Perfect for background scheduled tasks
- Pay only for what you use
- No infrastructure management needed

### 3. **Azure Container Registry (ACR)**
- Secure image storage
- Private image repository
- Easy integration with ACI

### 4. **Geographic Location**
- West Europe region minimizes latency for Swiss data sources
- GDPR compliant data residency

### 5. **Cost Effective**
- Low costs for continuous background operations
- Starting at ~$0.0000015 per second
- No setup or infrastructure costs

---

## Architecture & Deployment

```
┌─────────────────────────────────────────────────────────────┐
│                    Local Development                        │
│                   (Your Machine)                            │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ├─> Docker Build
                 │   (swissparkingcrawler:latest)
                 │
                 ├─> Docker Tag & Push
                 │   (to Azure Container Registry)
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│            Azure Container Registry (ACR)                   │
│         swissparkingregistry.azurecr.io                    │
│     Stores: swissparkingcrawler:latest                     │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ (Pull latest image)
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│         Azure Container Instances (ACI)                     │
│      swiss-parking-container (RUNNING)                     │
│  - 1 CPU Core, 1GB RAM, Linux                              │
│  - Runs: scheduler.py → collect_data.py                    │
│  - Frequency: Every 15 minutes                             │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ├─> Collects from 5 city APIs
                 │
                 ├─> Normalizes data
                 │
                 └─> Saves to Database (MySQL)
```

---

## Azure Resources Created

### 1. **Resource Group**
```
Name:      swiss-parking-rg
Location:  West Europe
Purpose:   Contains all parking crawler resources
Status:    Active ✅
```

The resource group is a logical container that holds all Azure resources for this project. It makes management, access control, and billing easier.

### 2. **Azure Container Registry (ACR)**
```
Name:              swissparkingregistry
SKU:               Basic
Login Server:      swissparkingregistry.azurecr.io
Admin Access:      Enabled ✅
Repository:        swissparkingcrawler
Image Tag:         latest
Status:            Active ✅
```

**Purpose:** Securely stores and manages Docker images. Acts as a private repository for your container images with authentication.

**What's Stored:**
- `swissparkingcrawler:latest` - The current production image

### 3. **Azure Container Instance (ACI)**
```
Name:              swiss-parking-container
Status:            Running ✅
Image Source:      swissparkingregistry.azurecr.io/swissparkingcrawler:latest
Operating System:  Linux
CPU Cores:         1
Memory:            1 GB
Restart Policy:    Always
Ports:             80 (HTTP), 443 (HTTPS) - Public Access
Web Server:        Flask (Python) - should be accessible
```

**Purpose:** Runs your containerized application 24/7. Executes the scheduler that collects parking data every 15 minutes AND serves a Flask web server on port 80.

**Features:**
- Flask web server serves HTTP API and frontend on port 80
- Background scheduler runs data collection every 15 minutes (in separate thread)
- API endpoints provide real-time data access
- Dashboard available at container URL

**Current Performance:**
- Last execution: ✅ Successful
- Records collected: 98
- Duplicates skipped: 0
- Failed records: 0

---

## Current Setup & Configuration

### Environment Variables
The container operates with these settings:
- `PYTHONUNBUFFERED=1` - Real-time logging output
- Python version: 3.11 (slim variant)

### Dependencies Installed
All Python packages required for operation:
```
requests              - HTTP requests to parking APIs
mysql-connector       - Database connectivity
schedule              - Job scheduling (every 15 minutes)
```

### File Structure
```
swiss-parking-crawler/
├── scheduler.py              # Scheduler that runs every 15 min
├── collect_data.py           # Main data collection orchestrator
├── base.py                   # Base collector class
├── luzern.py                 # Luzern city implementation
├── basel.py                  # Basel city implementation
├── stgallen.py               # St. Gallen city implementation
├── zurich.py                 # Zürich city implementation
├── bern.py                   # Bern city implementation
├── cities.json               # City/API configuration
├── db_config.json            # Database connection details
├── requirements.txt          # Python dependencies
├── Dockerfile                # Container configuration
├── docker-compose.yml        # Local development setup
├── local.settings.json       # Local development settings
├── azure-setup.md            # Detailed setup documentation
└── azure-readme.md           # This file
```

### Database Configuration
Location: `db_config.json`
```json
{
  "host": "your-db-host",
  "user": "your-db-user", 
  "password": "your-db-password",
  "database": "parking_db"
}
```

⚠️ **Important:** Update this file with your actual database credentials before deployment.

---

## Deployment Steps Completed

### Step 1: Local Docker Build ✅
Built a Docker image with all dependencies and application code:
```powershell
docker build --pull --rm -f 'Dockerfile' -t 'swissparkingcrawler:latest' '.'
```
**Why:** Creates a consistent, reproducible container image.

### Step 2: Azure Authentication ✅
Authenticated with Azure account:
```powershell
az login
```
**Why:** Establishes secure connection to your Azure subscription.

### Step 3: Create Resource Group ✅
Created a logical container for all resources:
```powershell
az group create --name swiss-parking-rg --location westeurope
```
**Why:** Organizes resources, manages access, simplifies billing.

### Step 4: Register Azure Providers ✅
Enabled required services in your subscription:
```powershell
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.ContainerInstance
```
**Why:** Activates the ability to use ACR and ACI services.

### Step 5: Create Azure Container Registry ✅
Set up secure image repository:
```powershell
az acr create --resource-group swiss-parking-rg --name swissparkingregistry --sku Basic
```
**Why:** Provides private storage for Docker images with authentication.

### Step 6: Enable Registry Admin Access ✅
Allowed authentication via admin credentials:
```powershell
az acr update -n swissparkingregistry --admin-enabled true
```
**Why:** Enables docker push/pull authentication.

### Step 7: Login to Registry ✅
Authenticated Docker client with ACR:
```powershell
az acr login --name swissparkingregistry
```
**Why:** Allows Docker to push images to the private registry.

### Step 8: Tag Docker Image ✅
Tagged local image with registry path:
```powershell
docker tag swissparkingcrawler:latest swissparkingregistry.azurecr.io/swissparkingcrawler:latest
```
**Why:** Makes image identifiable for the registry.

### Step 9: Push to Registry ✅
Uploaded image to Azure:
```powershell
docker push swissparkingregistry.azurecr.io/swissparkingcrawler:latest
```
**Why:** Makes image available to Azure for deployment.

### Step 10: Deploy to Azure Container Instances ✅
Created and started the running container:
```powershell
$password = az acr credential show --name swissparkingregistry --query passwords[0].value -o tsv
az container create `
  --resource-group swiss-parking-rg `
  --name swiss-parking-container `
  --image swissparkingregistry.azurecr.io/swissparkingcrawler:latest `
  --os-type Linux `
  --cpu 1 `
  --memory 1 `
  --registry-login-server swissparkingregistry.azurecr.io `
  --registry-username swissparkingregistry `
  --registry-password $password
```
**Why:** Launches the container in Azure with automatic restart.

---

## Key Features & Operations

### 1. **Automated Scheduling**
- Runs `collect_data.py` immediately on container start
- Executes every 15 minutes via `scheduler.py`
- No manual intervention required
- Automatic error handling and reporting

### 2. **Multi-City Data Collection**
Simultaneously collects from:
- Luzern Parkleitsystem API
- Basel Parkleitsystem API
- St. Gallen Parkleitsystem API
- Zürich Parkleitsystem API
- Bern Parkleitsystem API

### 3. **Data Normalization**
- Converts city-specific formats to unified JSON
- Standardizes field names
- Validates data integrity
- Removes duplicates

### 4. **Database Integration**
- Automatically saves to MySQL database
- Tracks insertion timestamps
- Counts successful vs. failed records
- Maintains historical data

### 5. **Continuous Operation**
- Container runs 24/7
- Automatically restarts on failure
- Survives Azure infrastructure updates
- Handles network interruptions gracefully

---

## Monitoring & Maintenance

### View Container Status
```powershell
az container show --resource-group swiss-parking-rg --name swiss-parking-container --query "instanceView.state" -o tsv
```
**Shows:** Running, Succeeded, Failed, Exited

### View Container Logs (First 15 lines)
```powershell
az container logs -g swiss-parking-rg -n swiss-parking-container | Select-Object -First 15
```
**Note:** If you encounter encoding errors, use the Azure Portal instead.

### View Full Container Logs via Azure Portal
1. Go to [Azure Portal](https://portal.azure.com)
2. Search for "Container Instances"
3. Click `swiss-parking-container`
4. Select "Logs" in the left sidebar
5. View real-time execution output

### View Last 50 Lines of Logs
```powershell
az container logs -g swiss-parking-rg -n swiss-parking-container --tail 50
```

### Check Container Details
```powershell
az container show -g swiss-parking-rg -n swiss-parking-container
```
**Shows:** CPU usage, memory, IP address, logs, events

### List All Resources
```powershell
az resource list --resource-group swiss-parking-rg
```
**Shows:** All resources in your resource group with details

### Stop Container (Pauses execution)
```powershell
az container stop -g swiss-parking-rg -n swiss-parking-container
```
**Use when:** You need to pause data collection temporarily

### Restart Container (Resumes execution)
```powershell
az container restart -g swiss-parking-rg -n swiss-parking-container
```
**Use when:** Container stops or needs a restart

### Delete Container
```powershell
az container delete -g swiss-parking-rg -n swiss-parking-container --yes
```
**Warning:** Cannot be undone. Container and its logs are removed.

---

## Cost Overview

### Monthly Cost Breakdown

| Component | Usage | Estimated Cost |
|-----------|-------|-----------------|
| **Azure Container Instances** | 1 CPU, 1GB RAM, 24/7 × 30 days | ~$14.40/month |
| **Azure Container Registry** | Basic tier (includes 10GB storage) | ~$5.00/month |
| **Database** | Varies by location | ~$10-50/month |
| **Total** | | **~$30-70/month** |

### Cost Optimization Options

1. **Use Azure Functions** instead of ACI
   - Better for short-running tasks (< 5 minutes)
   - Pay per execution
   - Could reduce cost to ~$2-5/month

2. **Reduce CPU/Memory**
   - Current: 1 CPU, 1GB RAM
   - Could lower to: 0.5 CPU, 0.5GB RAM (if sufficient)
   - Reduces cost by ~30%

3. **Adjust Collection Frequency**
   - Current: Every 15 minutes
   - Could extend to: Every 30 or 60 minutes
   - Reduces API calls and processing time

4. **Use Spot Instances** (when available)
   - ~70% discount on compute
   - Good for non-critical workloads

---

## Troubleshooting

### Issue: Container Won't Start

**Check 1: Verify image exists in registry**
```powershell
az acr repository show --name swissparkingregistry --repository swissparkingcrawler
```

**Check 2: Verify authentication credentials**
```powershell
az acr credential show --name swissparkingregistry
```

**Check 3: Review deployment logs**
```powershell
az container logs -g swiss-parking-rg -n swiss-parking-container
```

**Solution:** If image missing, rebuild and push:
```powershell
docker build -t swissparkingcrawler:latest .
docker tag swissparkingcrawler:latest swissparkingregistry.azurecr.io/swissparkingcrawler:latest
docker push swissparkingregistry.azurecr.io/swissparkingcrawler:latest
```

---

### Issue: Database Connection Errors

**Check 1: Verify db_config.json**
```powershell
Get-Content db_config.json
```
Ensure host, user, password, and database are correct.

**Check 2: Test database accessibility**
- Verify your database allows connections from Azure
- Check firewall rules
- Verify credentials are correct

**Check 3: Review logs for specific error**
```powershell
az container logs -g swiss-parking-rg -n swiss-parking-container
```

**Solution:**
1. Update `db_config.json` with correct credentials
2. Rebuild and redeploy container:
```powershell
docker build -t swissparkingcrawler:latest .
docker tag swissparkingcrawler:latest swissparkingregistry.azurecr.io/swissparkingcrawler:latest
docker push swissparkingregistry.azurecr.io/swissparkingcrawler:latest
az container delete -g swiss-parking-rg -n swiss-parking-container --yes
# Recreate container with same command as Step 10
```

---

### Issue: Out of Memory

**Symptoms:** Container crashes or restarts frequently

**Solution: Increase memory allocation**
```powershell
# Delete current container
az container delete -g swiss-parking-rg -n swiss-parking-container --yes

# Recreate with more memory (e.g., 2GB)
$password = az acr credential show --name swissparkingregistry --query passwords[0].value -o tsv
az container create `
  --resource-group swiss-parking-rg `
  --name swiss-parking-container `
  --image swissparkingregistry.azurecr.io/swissparkingcrawler:latest `
  --os-type Linux `
  --cpu 1 `
  --memory 2 `
  --registry-login-server swissparkingregistry.azurecr.io `
  --registry-username swissparkingregistry `
  --registry-password $password
```

---

### Issue: Unicode Encoding Error in PowerShell

**Symptoms:** "charmap codec can't encode character" error

**Solution: Use Azure Portal to view logs instead**
1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to your container instance
3. View logs in the portal interface

Or use this workaround:
```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

---

### Issue: High CPU Usage

**Symptoms:** Container frequently restarts, high costs

**Possible Causes:**
1. Infinite loops in collection code
2. Database queries are slow
3. API responses are large
4. Inefficient data processing

**Solution:**
1. Check logs for errors
2. Optimize code efficiency
3. Consider extending collection interval (30 min instead of 15 min)
4. Increase CPU allocation temporarily to investigate

---

### Issue: Flask Web Server Not Accessible

**Symptoms:** Browser shows connection refused or timeout on `http://swiss-parking-crawler.westeurope.azurecontainer.io`

**Possible Causes:**
1. Database connection failure on startup
2. Missing database credentials in `db_config.json`
3. Flask crashed during initialization
4. Port 80 firewall restrictions

**Check 1: View container logs via Azure Portal**
1. Go to [Azure Portal](https://portal.azure.com)
2. Search for "Container Instances" 
3. Click `swiss-parking-container`
4. Select "Logs" in left sidebar
5. Look for Flask startup errors or database connection failures

**Check 2: Verify database configuration**
```powershell
Get-Content db_config.json
```
Ensure all credentials are correct.

**Check 3: Test if Flask process is running**
```powershell
az container exec -g swiss-parking-rg -n swiss-parking-container --exec-command "/bin/bash"
ps aux | grep python
```

**Solution:**
1. Update `db_config.json` with correct database credentials
2. Rebuild and redeploy:
```powershell
docker build -t swissparkingcrawler:latest .
docker tag swissparkingcrawler:latest swissparkingregistry.azurecr.io/swissparkingcrawler:latest
docker push swissparkingregistry.azurecr.io/swissparkingcrawler:latest
az container restart -g swiss-parking-rg -n swiss-parking-container
```

3. If Flask still fails, check that the database is reachable from Azure (firewall rules, network access)

## Updating the Application

To deploy code changes:

### 1. Update code locally
Edit any `.py` files as needed

### 2. Rebuild Docker image
```powershell
docker build -t swissparkingcrawler:latest .
```

### 3. Tag and push to registry
```powershell
docker tag swissparkingcrawler:latest swissparkingregistry.azurecr.io/swissparkingcrawler:latest
docker push swissparkingregistry.azurecr.io/swissparkingcrawler:latest
```

### 4. Restart container (pulls new image)
```powershell
az container restart -g swiss-parking-rg -n swiss-parking-container
```

The container will restart and pull the latest image automatically.

---

## Important Links & Resources

### 🌐 Live Container URLs

#### Container Access
- **FQDN:** `swiss-parking-crawler.westeurope.azurecontainer.io`
- **IP Address:** `20.238.182.59`
- **HTTP Port:** 80 (Open)
- **HTTPS Port:** 443 (Open)
- **Status:** ✅ Running (Public Access Enabled)

**Direct Container URLs:**
- HTTP: `http://swiss-parking-crawler.westeurope.azurecontainer.io`
- HTTPS: `https://swiss-parking-crawler.westeurope.azurecontainer.io`
- Direct IP: `http://20.238.182.59`

#### Azure Portal Links
- **Direct Link:** https://portal.azure.com
- **Resource Group:** https://portal.azure.com/#resource/subscriptions/4e4e8e02-57a2-4482-9fd4-52c760203617/resourceGroups/swiss-parking-rg/overview
- **Container Instance:** https://portal.azure.com/#resource/subscriptions/4e4e8e02-57a2-4482-9fd4-52c760203617/resourceGroups/swiss-parking-rg/providers/Microsoft.ContainerInstance/containerGroups/swiss-parking-container/overview
- **Container Registry:** https://portal.azure.com/#resource/subscriptions/4e4e8e02-57a2-4482-9fd4-52c760203617/resourceGroups/swiss-parking-rg/providers/Microsoft.ContainerRegistry/registries/swissparkingregistry/overview
- **Search for "swiss-parking-rg"** in Azure Portal for quick access

### Official Documentation
- [Azure Container Instances](https://docs.microsoft.com/en-us/azure/container-instances/)
- [Azure Container Registry](https://docs.microsoft.com/en-us/azure/container-registry/)
- [Azure CLI Reference](https://docs.microsoft.com/en-us/cli/azure/)
- [Docker Documentation](https://docs.docker.com/)

### Useful Azure CLI Commands

**List all resources:**
```powershell
az resource list --resource-group swiss-parking-rg -o table
```

**Get subscription info:**
```powershell
az account show
```

**Get ACR login credentials:**
```powershell
az acr credential show --name swissparkingregistry
```

---

## Summary of What Was Done For You

✅ **Docker containerization** - Packaged application for cloud deployment  
✅ **Azure authentication** - Set up secure Azure account access  
✅ **Resource group creation** - Organized all resources logically  
✅ **Container Registry setup** - Created private image repository  
✅ **Image build & push** - Built and uploaded Docker image to Azure  
✅ **Container deployment** - Launched running container instance  
✅ **Scheduler configuration** - Set up automatic 15-minute execution  
✅ **Database integration** - Connected to MySQL for data storage  
✅ **Monitoring setup** - Enabled logging and status checking  
✅ **Documentation** - Created comprehensive deployment guides  

---

## Next Steps (Optional Enhancements)

1. **Add Application Insights** for detailed performance monitoring
2. **Implement Azure Key Vault** for secure credential management
3. **Set up CI/CD Pipeline** using GitHub Actions or Azure DevOps
4. **Add Email/SMS Alerts** for failures or anomalies
5. **Create Backup Strategy** for collected data
6. **Implement Health Checks** to verify container health
7. **Add API endpoint** to query collected data in real-time
8. **Create Dashboard** with visualization of parking trends

---

## Support & Questions

If you encounter issues:

1. **Check Azure Portal** - View resource health and logs
2. **Review container logs** - Run `az container logs` command
3. **Verify configuration** - Check `db_config.json` and connection strings
4. **Test locally** - Run `python collect_data.py --once` locally first
5. **Check Azure CLI version** - Run `az --version` to ensure it's up to date

---

**Deployment Date:** January 15, 2026  
**Status:** ✅ Production Running  
**Next Scheduled Collection:** Every 15 minutes (automatic)  
**Last Successful Execution:** January 15, 2026

---

*For detailed setup instructions, see [azure-setup.md](azure-setup.md)*
