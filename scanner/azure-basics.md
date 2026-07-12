az container stop --resource-group swiss-parking-rg --name swiss-parking-container

docker build -t swissparkingcrawler:latest .
docker tag swissparkingcrawler:latest swissparkingregistry.azurecr.io/swissparkingcrawler:latest
docker push swissparkingregistry.azurecr.io/swissparkingcrawler:latest

ACHTUNG- scheint nicht alles zu sein!!!

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
  --registry-password dQcaGin0Yt7uWL0PJoS2ebstilW6wX1RFBJVcczUz3+ACRDJLGwJ `
  --environment-variables DB_HOST=parkhaus.roil.ch DB_USER=crawler DB_PASSWORD='t$bM9y317' DB_NAME=ph_fetch DB_PORT=3306

az container start --resource-group swiss-parking-rg --name swiss-parking-container

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
