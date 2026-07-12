# run_locally_forever.ps1
# Script to run the parking data collector locally at high frequency
# and automatically sync data to GitHub to bypass Action limits.

param (
    [int]$IntervalMinutes = 15
)

$ErrorActionPreference = "Continue"

Clear-Host
Write-Host "=========================================================" -ForegroundColor White
Write-Host "   Swiss Parking Monitor - Local High-Frequency Sync" -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor White
Write-Host "Interval: $IntervalMinutes minutes" -ForegroundColor Gray
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

while ($true) {
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$now] Starting collection run..." -ForegroundColor Yellow
    
    try {
        # 1. Run the collector
        # Assuming python is in PATH. If using a specific venv, adjust here.
        python collect_data.py
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[$now] Data collected successfully." -ForegroundColor Green
            
            # 2. Sync to GitHub (optional, if there are other changes)
            Write-Host "[$now] Checking for other changes to sync..." -ForegroundColor Gray
            
            $changes = git status --porcelain
            if ($changes) {
                git add .
                $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                git commit -m "update: $timestamp"
                git push
                Write-Host "[$now] Sync complete. Changes pushed to GitHub." -ForegroundColor Green
            } else {
                Write-Host "[$now] No changes to sync." -ForegroundColor Gray
            }
        } else {
            Write-Host "[$now] collection failed with exit code $LASTEXITCODE" -ForegroundColor Red
        }
    }
    catch {
        Write-Host "[$now] An unexpected error occurred: $_" -ForegroundColor Red
    }
    
    Write-Host "`nWaiting $IntervalMinutes minutes for next run..." -ForegroundColor Gray
    Start-Sleep -Seconds ($IntervalMinutes * 60)
}
