#Requires -RunAsAdministrator

param(
    [ValidateSet("listing_backrun", "mrat_zscore")]
    [string]$Strategy = "listing_backrun",
    
    [ValidateSet("dev", "preprod", "prod")]
    [string]$Env = "dev",
    
    [ValidateSet("install", "start", "stop", "restart", "status", "uninstall", "logs")]
    [string]$Action = "install"
)

# Configuration
$ServiceName = "Otomai"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# --- Detection de NSSM ---
$nssmCmd = Get-Command "nssm" -ErrorAction SilentlyContinue
$systemNssm = if ($nssmCmd) { $nssmCmd.Source } else { $null }

$PossibleNssmPaths = @(
    "C:\ProgramData\chocolatey\bin\nssm.exe",
    "C:\nssm\win64\nssm.exe",
    $systemNssm
)

$NssmPath = $null
foreach ($path in $PossibleNssmPaths) {
    if ($path -and (Test-Path $path)) {
        $NssmPath = $path
        break
    }
}

if ($NssmPath) {
    Write-Host "[OK] NSSM found: $NssmPath" -ForegroundColor Green
}
else {
    Write-Error "NSSM not found. Installed? (choco install nssm -y)"
    exit 1
}

# --- Detection de UV ---
$uvCmd = Get-Command "uv" -ErrorAction SilentlyContinue
$systemUv = if ($uvCmd) { $uvCmd.Source } else { $null }

$PossibleUvPaths = @(
    "$env:USERPROFILE\.local\bin\uv.exe",
    "C:\Users\Thomas Clement\.local\bin\uv.exe",
    $systemUv
)

$UvPath = $null
foreach ($path in $PossibleUvPaths) {
    if ($path -and (Test-Path $path)) {
        $UvPath = $path
        break
    }
}

$LogDir = Join-Path $ProjectDir "logs"

# Checks
if (-not $UvPath) {
    Write-Error "UV not found. Check installation (irm https://astral.sh/uv/install.ps1 | iex)"
    exit 1
}
else {
    Write-Host "[OK] UV found: $UvPath" -ForegroundColor Green
}

# Create logs dir
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Write-Host "[OK] Logs dir created: $LogDir" -ForegroundColor Green
}

# --- Functions ---

function Install-Service {
    Write-Host "`n=== Installing Service $ServiceName ===" -ForegroundColor Cyan
    
    # Check existing
    $existingService = & $NssmPath status $ServiceName 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[WARN] Existing service detected, removing..." -ForegroundColor Yellow
        & $NssmPath stop $ServiceName 2>$null
        & $NssmPath remove $ServiceName confirm
    }
    
    # Config File
    $ConfigFile = Join-Path $ProjectDir "conf\$Env\$Strategy.yml"
    if (-not (Test-Path $ConfigFile)) {
        Write-Error "Config not found: $ConfigFile"
        exit 1
    }
    # Configurer le chemin Python direct (plus robuste pour les services)
    $PythonPath = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $PythonPath)) {
        Write-Error "Python introuvable dans .venv: $PythonPath"
        exit 1
    }

    # Install Service
    $ScriptPath = Join-Path $ProjectDir "src\otomai\scripts.py"
    # Use simple quotes for paths - NSSM and cmd handle this better than escaped backslashes
    $Arguments = '-u "{0}" --files "{1}"' -f $ScriptPath, $ConfigFile
    
    Write-Host "-> Installing service..." -ForegroundColor White
    
    # Install service targeting Python EXE directly
    & $NssmPath install $ServiceName $PythonPath
    
    # Configure parameters via Registry to avoid PowerShell quote stripping issues
    # This is the most robust way to handle paths with spaces/quotes
    $RegPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName\Parameters"
    
    # Create Parameters key if it doesn't exist (though install usually creates it)
    if (-not (Test-Path $RegPath)) {
        New-Item -Path $RegPath -Force | Out-Null
    }
    
    # Set arguments directly in registry
    Set-ItemProperty -Path $RegPath -Name "AppParameters" -Value $Arguments
    
    # Use NSSM for the rest
    & $NssmPath set $ServiceName AppDirectory $ProjectDir
    & $NssmPath set $ServiceName Start SERVICE_AUTO_START
    
    # Simpler logging: Single file, no rotation (easier to debug)
    $GlobalLog = Join-Path $LogDir "service.log"
    & $NssmPath set $ServiceName AppStdout $GlobalLog
    & $NssmPath set $ServiceName AppStderr $GlobalLog
    & $NssmPath set $ServiceName AppRotateFiles 0
    
    Write-Host "[OK] Service installed" -ForegroundColor Green
    
    # Env Vars
    Write-Host "-> Configuring environment variables..." -ForegroundColor White
    
    # Reset Environment first to avoid concatenation issues
    & $NssmPath set $ServiceName AppEnvironmentExtra ""
    
    $envFiles = @(
        (Join-Path $ProjectDir "env\base.env"),
        (Join-Path $ProjectDir "env\$Strategy\$Env.env")
    )
    
    foreach ($file in $envFiles) {
        if (Test-Path $file) {
            Write-Host "  Loading: $file" -ForegroundColor Gray
            Get-Content $file | Where-Object { 
                $_ -match "^[^#]" -and $_.Trim() -ne "" 
            } | ForEach-Object {
                $envLine = $_.Trim()
                & $NssmPath set $ServiceName AppEnvironmentExtra "+$envLine" | Out-Null
            }
        }
        else {
            Write-Warning "File not found: $file"
        }
    }
    
    # Add ENV and STRATEGY
    & $NssmPath set $ServiceName AppEnvironmentExtra "+ENV=$Env"
    & $NssmPath set $ServiceName AppEnvironmentExtra "+STRATEGY=$Strategy"
    
    Write-Host "[OK] Env vars configured" -ForegroundColor Green
    
    # Power Management
    Write-Host "-> Configuring power management..." -ForegroundColor White
    powercfg -change -standby-timeout-ac 0
    powercfg -change -hibernate-timeout-ac 0
    Write-Host "[OK] Standby disabled" -ForegroundColor Green
    
    Write-Host "`n[SUCCESS] Installation complete!" -ForegroundColor Green
    Write-Host "   Start with: .\install-service.ps1 -Action start" -ForegroundColor White
}

function Start-OtomaiService {
    Write-Host "Starting service $ServiceName..." -ForegroundColor Cyan
    & $NssmPath start $ServiceName
    Start-Sleep -Seconds 2
    Get-ServiceStatus
}

function Stop-OtomaiService {
    Write-Host "Stopping service $ServiceName..." -ForegroundColor Cyan
    & $NssmPath stop $ServiceName
}

function Restart-OtomaiService {
    Write-Host "Restarting service $ServiceName..." -ForegroundColor Cyan
    & $NssmPath restart $ServiceName
    Start-Sleep -Seconds 2
    Get-ServiceStatus
}

function Get-ServiceStatus {
    Write-Host "`n=== Service Status $ServiceName ===" -ForegroundColor Cyan
    $status = & $NssmPath status $ServiceName
    
    switch ($status) {
        "SERVICE_RUNNING" { 
            Write-Host "* $ServiceName is RUNNING" -ForegroundColor Green 
        }
        "SERVICE_STOPPED" { 
            Write-Host "o $ServiceName is STOPPED" -ForegroundColor Yellow 
        }
        "SERVICE_PAUSED" { 
            Write-Host "~ $ServiceName is PAUSED" -ForegroundColor Yellow 
        }
        default { 
            Write-Host "? Status: $status" -ForegroundColor Gray 
        }
    }
}

function Uninstall-Service {
    Write-Host "Uninstalling service $ServiceName..." -ForegroundColor Cyan
    & $NssmPath stop $ServiceName 2>$null
    & $NssmPath remove $ServiceName confirm
    Write-Host "[OK] Service uninstalled" -ForegroundColor Green
}

function Show-Logs {
    $logFile = Join-Path $LogDir "service.log"
    if (Test-Path $logFile) {
        Write-Host "=== Last log lines ($logFile) ===" -ForegroundColor Cyan
        Get-Content $logFile -Tail 50 -Wait
    }
    else {
        Write-Warning "No logs found at $logFile"
    }
}

# Execution
switch ($Action) {
    "install" { Install-Service }
    "start" { Start-OtomaiService }
    "stop" { Stop-OtomaiService }
    "restart" { Restart-OtomaiService }
    "status" { Get-ServiceStatus }
    "uninstall" { Uninstall-Service }
    "logs" { Show-Logs }
}
