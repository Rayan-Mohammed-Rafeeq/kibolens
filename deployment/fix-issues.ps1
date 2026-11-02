# KiboLens Issue Fix Script
# Fixes: AI token limits, database migrations, infrastructure errors
# Requires: Docker Desktop running

param(
    [switch]$SkipMigrations = $false,
    [switch]$SkipTokenAdjust = $false,
    [switch]$Verbose = $false
)

$ErrorActionPreference = "Stop"

function Write-FixHeader {
    param([string]$Title)
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

function Write-FixResult {
    param([string]$Name, [bool]$Success, [string]$Message = "")
    if ($Success) {
        Write-Host "[✓] $Name" -ForegroundColor Green
    } else {
        Write-Host "[✗] $Name" -ForegroundColor Red
    }
    if ($Message) {
        Write-Host "    $Message" -ForegroundColor Gray
    }
}

function Test-DockerRunning {
    try {
        docker info | Out-Null
        return $true
    } catch {
        Write-Host "ERROR: Docker Desktop is not running" -ForegroundColor Red
        Write-Host "Please start Docker Desktop and try again" -ForegroundColor Yellow
        return $false
    }
}

function Test-BackendRunning {
    try {
        $status = docker compose ps backend --format json 2>$null | ConvertFrom-Json
        return $status.State -eq "running"
    } catch {
        return $false
    }
}

function Fix-DatabaseMigrations {
    Write-FixHeader "Fix 1: Database Migrations"
    
    if (-not (Test-BackendRunning)) {
        Write-FixResult "Backend container running" $false "Backend must be running"
        Write-Host "`nStart backend first:" -ForegroundColor Yellow
        Write-Host "  docker compose up -d backend" -ForegroundColor White
        return $false
    }
    
    Write-Host "Checking current migration status..." -ForegroundColor Yellow
    
    try {
        $current = docker compose exec -T backend alembic current 2>&1
        if ($Verbose) {
            Write-Host "Current migration:" -ForegroundColor Gray
            Write-Host $current -ForegroundColor Gray
        }
    } catch {
        Write-FixResult "Check migration status" $false $_.Exception.Message
        return $false
    }
    
    Write-Host "Running pending migrations..." -ForegroundColor Yellow
    
    try {
        $result = docker compose exec -T backend alembic upgrade head 2>&1
        
        if ($Verbose) {
            Write-Host $result -ForegroundColor Gray
        }
        
        if ($result -match "error|failed") {
            Write-FixResult "Run database migrations" $false "Migration failed"
            Write-Host $result -ForegroundColor Red
            return $false
        }
        
        Write-FixResult "Run database migrations" $true
    } catch {
        Write-FixResult "Run database migrations" $false $_.Exception.Message
        return $false
    }
    
    Write-Host "Verifying incident tables..." -ForegroundColor Yellow
    
    try {
        $tables = docker compose exec -T postgres psql -U kibolens -d kibolens -c "\dt incident*" 2>&1
        
        if ($tables -match "incident_events|incidents|incident_sequences") {
            Write-FixResult "Incident tables exist" $true
            if ($Verbose) {
                Write-Host $tables -ForegroundColor Gray
            }
            return $true
        } else {
            Write-FixResult "Incident tables exist" $false "Tables not found"
            return $false
        }
    } catch {
        Write-FixResult "Incident tables exist" $false $_.Exception.Message
        return $false
    }
}

function Fix-TokenLimits {
    Write-FixHeader "Fix 2: AI Token Limits"
    
    $envFile = ".env"
    $backupFile = ".env.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    
    if (-not (Test-Path $envFile)) {
        Write-Host "Creating new .env file..." -ForegroundColor Yellow
        Write-FixResult "Backup .env file" $true "No existing file"
    } else {
        Write-Host "Backing up existing .env..." -ForegroundColor Yellow
        Copy-Item $envFile $backupFile
        Write-FixResult "Backup .env file" $true "Saved as $backupFile"
    }
    
    $envContent = if (Test-Path $envFile) { Get-Content $envFile -Raw } else { "" }
    
    $tokenPattern = "KIBOLENS_LLM_MAX_TOKENS\s*=\s*\d+"
    $newTokenLine = "KIBOLENS_LLM_MAX_TOKENS=4000"
    
    if ($envContent -match $tokenPattern) {
        Write-Host "Updating existing token limit..." -ForegroundColor Yellow
        $envContent = $envContent -replace $tokenPattern, $newTokenLine
        Write-FixResult "Update token limit" $true "Changed to 4000"
    } else {
        Write-Host "Adding token limit configuration..." -ForegroundColor Yellow
        if ($envContent -and -not $envContent.EndsWith("`n")) {
            $envContent += "`n"
        }
        $envContent += "`n# AI Token Limits`n"
        $envContent += "$newTokenLine`n"
        Write-FixResult "Add token limit" $true "Set to 4000"
    }
    
    $envContent | Set-Content $envFile -NoNewline
    
    Write-Host "Restarting backend to apply changes..." -ForegroundColor Yellow
    
    try {
        docker compose restart backend | Out-Null
        Start-Sleep -Seconds 3
        
        if (Test-BackendRunning) {
            Write-FixResult "Restart backend" $true
            return $true
        } else {
            Write-FixResult "Restart backend" $false "Backend not running after restart"
            return $false
        }
    } catch {
        Write-FixResult "Restart backend" $false $_.Exception.Message
        return $false
    }
}

function Test-IncidentsAPI {
    Write-Host "`nTesting Incidents API..." -ForegroundColor Yellow
    
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/incidents?offset=0&limit=10" -Method Get -TimeoutSec 5 2>$null
        Write-FixResult "Incidents API responds" $true
        return $true
    } catch {
        if ($_.Exception.Message -match "401|403") {
            Write-FixResult "Incidents API responds" $true "Requires authentication (expected)"
            return $true
        }
        Write-FixResult "Incidents API responds" $false $_.Exception.Message
        return $false
    }
}

function Show-Summary {
    param([bool]$MigrationsOk, [bool]$TokensOk)
    
    Write-FixHeader "Summary"
    
    if ($MigrationsOk) {
        Write-Host "✓ Database migrations complete" -ForegroundColor Green
        Write-Host "  - Incident tables created" -ForegroundColor Gray
        Write-Host "  - Incidents page should work" -ForegroundColor Gray
    } else {
        Write-Host "✗ Database migrations failed" -ForegroundColor Red
        Write-Host "  - Incidents page may not work" -ForegroundColor Gray
    }
    
    if ($TokensOk) {
        Write-Host "✓ Token limits adjusted" -ForegroundColor Green
        Write-Host "  - LLM_MAX_TOKENS set to 4000" -ForegroundColor Gray
        Write-Host "  - AI responses should complete" -ForegroundColor Gray
    } else {
        Write-Host "✗ Token limits not adjusted" -ForegroundColor Red
        Write-Host "  - AI responses may truncate" -ForegroundColor Gray
    }
    
    Write-Host "`nNext Steps:" -ForegroundColor Cyan
    Write-Host "1. Test incidents page: http://localhost:5173/incidents" -ForegroundColor White
    Write-Host "2. Test AI chat: http://localhost:5173/ai-chat" -ForegroundColor White
    Write-Host "3. Check infrastructure: http://localhost:5173/infrastructure" -ForegroundColor White
    
    Write-Host "`nNote on VM monitoring:" -ForegroundColor Yellow
    Write-Host "  'Optional libvirt Python binding is unavailable' is expected on Windows" -ForegroundColor Gray
    Write-Host "  This is not an error - VM monitoring requires libvirt (Linux/WSL2 only)" -ForegroundColor Gray
}

# Main execution
Write-Host "`nKiboLens Issue Fix Script" -ForegroundColor Magenta
Write-Host "========================`n" -ForegroundColor Magenta

if (-not (Test-DockerRunning)) {
    exit 1
}

Write-FixResult "Docker Desktop running" $true

$migrationsOk = $false
$tokensOk = $false

if (-not $SkipMigrations) {
    $migrationsOk = Fix-DatabaseMigrations
} else {
    Write-Host "`nSkipping database migrations (-SkipMigrations flag)" -ForegroundColor Yellow
}

if (-not $SkipTokenAdjust) {
    $tokensOk = Fix-TokenLimits
} else {
    Write-Host "`nSkipping token adjustment (-SkipTokenAdjust flag)" -ForegroundColor Yellow
}

if ($migrationsOk) {
    Test-IncidentsAPI | Out-Null
}

Show-Summary -MigrationsOk $migrationsOk -TokensOk $tokensOk

if ($migrationsOk -and $tokensOk) {
    Write-Host "`n✓ All fixes applied successfully`n" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n⚠ Some fixes failed - see errors above`n" -ForegroundColor Yellow
    exit 1
}
