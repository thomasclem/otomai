# Windows Server Deployment Guide

Complete guide for deploying Otomai on your Windows home server.

## Prerequisites

- Windows Server 2016+ or Windows 10/11
- Python 3.11+
- UV package manager installed
- Administrator access

## Setup Steps

### 1. Install UV and Dependencies

```powershell
# Install UV
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Clone repository
cd C:\
git clone https://github.com/your-repo/otomai.git
cd otomai

# Install dependencies
uv sync
```

### 2. Configure Environment

Create `env/prod.env`:
```env
ENV=prod
BITGET_API_KEY=your_api_key
BITGET_SECRET=your_secret
BITGET_PASSWORD=your_password
TELEGRAM_BOT_TOKEN=your_telegram_token
```

## Running as Windows Service

### Option 1: NSSM (Recommended)

NSSM (Non-Sucking Service Manager) is the easiest way to run Python scripts as Windows services.

#### Install NSSM

```powershell
# Download NSSM
https://nssm.cc/release/nssm-2.24.zip directory
https://nssm.cc/download

# Extract to C:\nssm
```

#### Create Service

```powershell
# Open Command Prompt as Administrator
cd C:\nssm\win64

# Install service
.\nssm.exe install Otomai "C:\Users\YOUR_USERNAME\.local\bin\uv.exe" `
  "run python C:\otomai\src\otomai\scripts.py --files C:\otomai\conf\prod\listing_backrun.yml"

# Set working directory
.\nssm.exe set Otomai AppDirectory "C:\otomai"

# Set service to auto-start
.\nssm.exe set Otomai Start SERVICE_AUTO_START
```

#### Configure Environment Variables

Même logique que le `docker-compose.yml` : source `base.env` + `${STRATEGY}/${ENV}.env`

```powershell
# Définir la stratégie et l'environnement
$STRATEGY = "listing_backrun"  # ou "mrat_zscore"
$ENV = "prod"                   # ou "dev", "preprod"

# Sourcer les fichiers .env (depuis C:\nssm\win64)
$envFiles = @(
    "C:\otomai\env\base.env",
    "C:\otomai\env\$STRATEGY\$ENV.env"
)

Get-Content $envFiles | `
  Where-Object { $_ -match "^[^#]" -and $_.Trim() -ne "" } | `
  ForEach-Object { .\nssm.exe set Otomai AppEnvironmentExtra "+$_" }

# Ajouter ENV et STRATEGY explicitement
.\nssm.exe set Otomai AppEnvironmentExtra "+ENV=$ENV"
.\nssm.exe set Otomai AppEnvironmentExtra "+STRATEGY=$STRATEGY"
```

#### Prevent Sleep Mode (24/7 Operation)

Pour que le bot tourne même en veille :

```powershell
# Désactiver la mise en veille sur secteur
powercfg -change -standby-timeout-ac 0
powercfg -change -hibernate-timeout-ac 0
powercfg -change -monitor-timeout-ac 0

# Ou utiliser le mode "High Performance"
powercfg /setactive SCHEME_MIN
```

#### Start the Service

```powershell
.\nssm.exe start Otomai
```

#### Manage Service

```powershell
# Stop service
.\nssm.exe stop Otomai

# Restart service
.\nssm.exe restart Otomai

# Check status
.\nssm.exe status Otomai

# View logs
.\nssm.exe set Otomai AppStdout "C:\otomai\logs\stdout.log"
.\nssm.exe set Otomai AppStderr "C:\otomai\logs\stderr.log"

# Uninstall service
.\nssm.exe remove Otomai confirm
```

### Option 2: Task Scheduler

For simpler setup without external tools:

1. Open **Task Scheduler** (taskschd.msc)
2. Create Task → **General** tab:
   - Name: Otomai Trading Bot
   - Run whether user is logged on or not
   - Run with highest privileges
3. **Triggers** tab:
   - New → At startup
4. **Actions** tab:
   - New → Start a program
   - Program: `C:\Users\YOUR_USERNAME\.local\bin\uv.exe`
   - Arguments: `run python C:\otomai\src\otomai\scripts.py --files C:\otomai\conf\prod\listing_backrun.yml`
   - Start in: `C:\otomai`
5. **Settings** tab:
   - If task fails, restart every: 1 minute
   - Attempt to restart up to: 3 times

## Firewall Configuration

```powershell
# Allow Python through Windows Firewall (if needed)
New-NetFirewallRule -DisplayName "Otomai Bot" `
  -Direction Outbound `
  -Program "C:\Users\YOUR_USERNAME\.local\bin\uv.exe" `
  -Action Allow
```

## Remote Management

### Enable Remote Desktop

```powershell
# PowerShell as Administrator
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -name "fDenyTSConnections" -value 0
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"
```

### PowerShell Remoting

```powershell
# On server
Enable-PSRemoting -Force

# From remote machine
Enter-PSSession -ComputerName YOUR_SERVER_IP -Credential (Get-Credential)
```

## Monitoring & Logging

### View Logs

```powershell
# If using NSSM with log files
Get-Content C:\otomai\logs\stdout.log -Tail 50 -Wait

# Check Windows Event Viewer
eventvwr.msc
# Navigate to: Applications and Services Logs
```

### Monitor Service Health

```powershell
# Check service status
Get-Service -Name "Otomai"

# Check process
Get-Process -Name "python" | Where-Object {$_.Path -like "*otomai*"}
```

## Auto-Update Script

Create `C:\otomai\update.ps1`:

```powershell
# Stop service
Stop-Service -Name "Otomai"

# Update code
cd C:\otomai
git pull origin main

# Update dependencies
uv sync

# Restart service
Start-Service -Name "Otomai"

Write-Host "Otomai updated and restarted"
```

Schedule this script weekly using Task Scheduler.

## Troubleshooting

### Service Won't Start

1. Check logs: `C:\otomai\logs\stderr.log`
2. Verify PATH in service configuration
3. Test manual run: `cd C:\otomai && uv run python src/otomai/scripts.py --files conf/prod/listing_backrun.yml`

### Permission Issues

- Run NSSM as Administrator
- Ensure service runs under account with folder access

### Network Issues

- Check Windows Firewall rules
- Verify outbound HTTPS (port 443) is allowed

## Security Best Practices

1. **Dedicated User Account**: Create a service account with minimal permissions
2. **Environment Variables**: Store secrets in Windows Credential Manager
3. **Firewall**: Only allow required outbound connections
4. **Updates**: Enable Windows Update for security patches
5. **Backups**: Schedule regular backups of configuration and database

## Performance Optimization

```powershell
# Set process priority
.\nssm.exe set Otomai AppPriority ABOVE_NORMAL_PRIORITY_CLASS

# Limit CPU usage (if needed)
.\nssm.exe set Otomai AppThrottle 1000
```

## Support

For issues specific to Windows deployment, see [Troubleshooting](../troubleshooting.md).
