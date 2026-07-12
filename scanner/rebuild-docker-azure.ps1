# rebuild-docker-azure.ps1
# This script rebuilds the Docker image, pushes it to Azure Container Registry (ACR),
# and redeploys the Azure Container Instance (ACI).

## IMPORTANT: Docker Desktop for Windows must be running! ##

# 1. Check current status of the container
Write-Host "Checking current container status..." -ForegroundColor Cyan
az container show --resource-group swiss-parking-rg --name swiss-parking-container --query "instanceView.state" -o tsv

# 2. Stop and Delete the existing container to ensure a fresh deployment
Write-Host "Stopping and deleting existing container..." -ForegroundColor Yellow
az container stop --resource-group swiss-parking-rg --name swiss-parking-container
az container delete --resource-group swiss-parking-rg --name swiss-parking-container --yes

# 3. Log in to Azure Container Registry (ACR)
# This is crucial for the 'docker push' command to work.
Write-Host "Logging into Azure Container Registry..." -ForegroundColor Cyan
az acr login --name swissparkingregistry

# 4. Build the local Docker image
Write-Host "Building Docker image..." -ForegroundColor Cyan
docker build -t swissparkingcrawler:latest .
if ($LASTEXITCODE -ne 0) { 
  Write-Host "Docker build failed! Exiting." -ForegroundColor Red
  exit $LASTEXITCODE 
}

# 5. Tag and Push the image to ACR
Write-Host "Tagging and pushing image to ACR..." -ForegroundColor Cyan
docker tag swissparkingcrawler:latest swissparkingregistry.azurecr.io/swissparkingcrawler:latest
docker push swissparkingregistry.azurecr.io/swissparkingcrawler:latest
if ($LASTEXITCODE -ne 0) { 
  Write-Host "Docker push failed! Exiting." -ForegroundColor Red
  exit $LASTEXITCODE 
}

# 6. Retrieve ACR credentials for ACI deployment
Write-Host "Fetching registry credentials..." -ForegroundColor Cyan
$password = az acr credential show --name swissparkingregistry --query passwords[0].value -o tsv

# 7. Create/Redeploy the container in Azure
# We use the $password variable retrieved above instead of a hardcoded string.
Write-Host "Creating new container instance..." -ForegroundColor Green
az container create `
  --resource-group swiss-parking-rg `
  --name swiss-parking-container `
  --image swissparkingregistry.azurecr.io/swissparkingcrawler:latest `
  --os-type Linux `
  --cpu 1 `
  --memory 1 `
  --ports 443 `
  --ports 80 `
  --dns-name-label swiss-parking-crawler `
  --registry-login-server swissparkingregistry.azurecr.io `
  --registry-username swissparkingregistry `
  --registry-password $password `
  --environment-variables PORT=80 DB_HOST=parkhaus.roil.ch DB_USER=crawler DB_PASSWORD='t$bM9y317' DB_NAME=ph_fetch DB_PORT=3306

# Note: 'az container create' automatically starts the container, so 'az container start' is redundant.

# 8. Verify the status and show logs
Write-Host "Deployment complete. Final status:" -ForegroundColor Green
$containerData = az container show --resource-group swiss-parking-rg --name swiss-parking-container --query "{FQDN:ipAddress.fqdn, IP:ipAddress.ip}" -o json | ConvertFrom-Json
$fqdn = $containerData.FQDN
$ip = $containerData.IP

# Explicitly start the container group just to be sure
az container start --resource-group swiss-parking-rg --name swiss-parking-container

#az containerapp up --resource-group web-flask-aca-rg --name web-aca-app --ingress external --target-port 50505 --source .
Write-Host "Application is now available at: http://$fqdn" -ForegroundColor Cyan
Write-Host "Direct IP Access: http://$ip" -ForegroundColor Gray

#Write-Host "Fetching initial logs..." -ForegroundColor Gray
#az container logs --resource-group swiss-parking-rg --name swiss-parking-container


# Reserve Commands
# az container restart --resource-group swiss-parking-rg --name swiss-parking-container --query "instanceView.state" -o tsv
# az container show --resource-group swiss-parking-rg --name swiss-parking-container

