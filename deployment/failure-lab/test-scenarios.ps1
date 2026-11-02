# Docker Failure Lab - Scenario Test Script
# Tests all 7 failure scenarios individually
# Requires: Docker Desktop running

param(
    [string]$Scenario = "all",
    [switch]$Build = $false,
    [switch]$Verbose = $false
)

$ErrorActionPreference = "Stop"
$LAB_DIR = $PSScriptRoot

function Write-TestHeader {
    param([string]$Title)
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

function Write-TestResult {
    param([string]$Name, [bool]$Passed, [string]$Message = "")
    if ($Passed) {
        Write-Host "[✓] $Name" -ForegroundColor Green
    } else {
        Write-Host "[✗] $Name" -ForegroundColor Red
    }
    if ($Message) {
        Write-Host "    $Message" -ForegroundColor Gray
    }
}

function Test-DockerRunning {
    Write-TestHeader "Pre-Flight Checks"
    
    try {
        docker info | Out-Null
        Write-TestResult "Docker daemon is running" $true
        return $true
    } catch {
        Write-TestResult "Docker daemon is running" $false "Docker Desktop must be started"
        return $false
    }
}

function Build-LabImages {
    Write-TestHeader "Building Lab Images"
    
    Push-Location $LAB_DIR
    try {
        Write-Host "Building all scenario images..." -ForegroundColor Yellow
        docker compose --profile lab build --no-cache
        Write-TestResult "Build all scenario images" $?
    } finally {
        Pop-Location
    }
}

function Test-Crasher {
    Write-TestHeader "Test 1: Crasher Scenario"
    
    Push-Location $LAB_DIR
    try {
        Write-Host "Starting crasher container..." -ForegroundColor Yellow
        docker compose --profile lab up lab-crasher 2>&1 | Out-Null
        
        $exitCode = $LASTEXITCODE
        $expectedExit = 137
        
        if ($exitCode -eq $expectedExit) {
            Write-TestResult "Crasher exits with code $expectedExit" $true
        } else {
            Write-TestResult "Crasher exits with code $expectedExit" $false "Got exit code: $exitCode"
        }
        
        # Clean up
        docker compose --profile lab down 2>&1 | Out-Null
    } finally {
        Pop-Location
    }
}

function Test-Unhealthy {
    Write-TestHeader "Test 2: Unhealthy Scenario"
    
    Push-Location $LAB_DIR
    try {
        Write-Host "Starting unhealthy container..." -ForegroundColor Yellow
        docker compose --profile lab up -d lab-unhealthy 2>&1 | Out-Null
        
        Write-Host "Waiting for health check failures (20s)..." -ForegroundColor Yellow
        Start-Sleep -Seconds 20
        
        $health = docker inspect kibolens-lab-unhealthy --format='{{.State.Health.Status}}' 2>$null
        
        if ($health -eq "unhealthy") {
            Write-TestResult "Container becomes unhealthy" $true
        } else {
            Write-TestResult "Container becomes unhealthy" $false "Health status: $health"
        }
        
        # Clean up
        docker compose --profile lab down 2>&1 | Out-Null
    } finally {
        Pop-Location
    }
}

function Test-RestartLoop {
    Write-TestHeader "Test 3: Restart Loop Scenario"
    
    Push-Location $LAB_DIR
    try {
        Write-Host "Starting restart-loop container..." -ForegroundColor Yellow
        docker compose --profile lab up -d lab-restart-loop 2>&1 | Out-Null
        
        Write-Host "Waiting for restart events (30s)..." -ForegroundColor Yellow
        Start-Sleep -Seconds 30
        
        $restartCount = docker inspect kibolens-lab-restart-loop --format='{{.RestartCount}}' 2>$null
        
        if ([int]$restartCount -gt 0) {
            Write-TestResult "Container restarts after crashes" $true "Restart count: $restartCount"
        } else {
            Write-TestResult "Container restarts after crashes" $false "Restart count: $restartCount"
        }
        
        # Clean up
        docker compose --profile lab down 2>&1 | Out-Null
    } finally {
        Pop-Location
    }
}

function Test-CPUStress {
    Write-TestHeader "Test 4: CPU Stress Scenario"
    
    Push-Location $LAB_DIR
    try {
        Write-Host "Starting CPU stress container (60s duration)..." -ForegroundColor Yellow
        
        $startTime = Get-Date
        docker compose --profile lab up lab-cpu-stress 2>&1 | Out-Null
        $duration = ((Get-Date) - $startTime).TotalSeconds
        
        $exitCode = docker inspect kibolens-lab-cpu-stress --format='{{.State.ExitCode}}' 2>$null
        
        if ($exitCode -eq "0" -and $duration -ge 50) {
            Write-TestResult "CPU stress completes successfully" $true "Duration: ${duration}s"
        } else {
            Write-TestResult "CPU stress completes successfully" $false "Exit: $exitCode, Duration: ${duration}s"
        }
        
        # Clean up
        docker compose --profile lab down 2>&1 | Out-Null
    } finally {
        Pop-Location
    }
}

function Test-MemoryPressure {
    Write-TestHeader "Test 5: Memory Pressure Scenario"
    
    Push-Location $LAB_DIR
    try {
        Write-Host "Starting memory pressure container (60s duration)..." -ForegroundColor Yellow
        docker compose --profile lab up lab-memory-pressure 2>&1 | Out-Null
        
        $exitCode = docker inspect kibolens-lab-memory-pressure --format='{{.State.ExitCode}}' 2>$null
        
        # Exit 0 (clean) or 137 (OOM killed) are both acceptable
        if ($exitCode -eq "0" -or $exitCode -eq "137") {
            Write-TestResult "Memory pressure behaves as expected" $true "Exit code: $exitCode"
        } else {
            Write-TestResult "Memory pressure behaves as expected" $false "Exit code: $exitCode"
        }
        
        # Clean up
        docker compose --profile lab down 2>&1 | Out-Null
    } finally {
        Pop-Location
    }
}

function Test-MissingDependency {
    Write-TestHeader "Test 6: Missing Dependency Scenario"
    
    Push-Location $LAB_DIR
    try {
        Write-Host "Starting missing-dependency container..." -ForegroundColor Yellow
        docker compose --profile lab up lab-missing-dependency 2>&1 | Out-Null
        
        $exitCode = docker inspect kibolens-lab-missing-dependency --format='{{.State.ExitCode}}' 2>$null
        $logs = docker logs kibolens-lab-missing-dependency 2>&1
        
        $hasError = $logs -match "not found|connection refused|failed"
        
        if ($exitCode -eq "127" -or ($exitCode -eq "1" -and $hasError)) {
            Write-TestResult "Missing dependency fails as expected" $true "Exit code: $exitCode"
        } else {
            Write-TestResult "Missing dependency fails as expected" $false "Exit code: $exitCode"
        }
        
        # Clean up
        docker compose --profile lab down 2>&1 | Out-Null
    } finally {
        Pop-Location
    }
}

function Test-ConfigError {
    Write-TestHeader "Test 7: Configuration Error Scenario"
    
    Push-Location $LAB_DIR
    try {
        Write-Host "Starting config-error container..." -ForegroundColor Yellow
        docker compose --profile lab up lab-config-error 2>&1 | Out-Null
        
        $exitCode = docker inspect kibolens-lab-config-error --format='{{.State.ExitCode}}' 2>$null
        $logs = docker logs kibolens-lab-config-error 2>&1
        
        $hasConfigError = $logs -match "Configuration validation failed|REQUIRED_ENV_VAR"
        
        if ($exitCode -eq "78" -and $hasConfigError) {
            Write-TestResult "Config error detected correctly" $true "Exit code: $exitCode"
        } else {
            Write-TestResult "Config error detected correctly" $false "Exit code: $exitCode"
        }
        
        # Clean up
        docker compose --profile lab down 2>&1 | Out-Null
    } finally {
        Pop-Location
    }
}

function Test-Isolation {
    Write-TestHeader "Isolation Verification"
    
    Push-Location $LAB_DIR
    try {
        # Start one container
        docker compose --profile lab up -d lab-crasher 2>&1 | Out-Null
        Start-Sleep -Seconds 5
        
        # Check network is internal
        $networkInfo = docker network inspect failure-lab_lab 2>$null | ConvertFrom-Json
        $isInternal = $networkInfo[0].Internal
        
        Write-TestResult "Lab network is internal" $isInternal
        
        # Check labels
        $labels = docker inspect kibolens-lab-crasher --format='{{json .Config.Labels}}' 2>$null | ConvertFrom-Json
        $hasLabLabel = $labels.'kibolens.lab' -eq "true"
        
        Write-TestResult "Container has lab label" $hasLabLabel
        
        # Check resource limits
        $cpuQuota = docker inspect kibolens-lab-crasher --format='{{.HostConfig.NanoCpus}}' 2>$null
        $memLimit = docker inspect kibolens-lab-crasher --format='{{.HostConfig.Memory}}' 2>$null
        
        $hasCPULimit = [int64]$cpuQuota -gt 0
        $hasMemLimit = [int64]$memLimit -gt 0
        
        Write-TestResult "CPU limit enforced" $hasCPULimit "NanoCPUs: $cpuQuota"
        Write-TestResult "Memory limit enforced" $hasMemLimit "Bytes: $memLimit"
        
        # Check user
        $user = docker inspect kibolens-lab-crasher --format='{{.Config.User}}' 2>$null
        $isNonRoot = $user -eq "1001:1001"
        
        Write-TestResult "Runs as non-root user" $isNonRoot "User: $user"
        
        # Clean up
        docker compose --profile lab down 2>&1 | Out-Null
    } finally {
        Pop-Location
    }
}

# Main execution
Write-Host "`nDocker Failure Lab - Test Suite" -ForegroundColor Magenta
Write-Host "================================`n" -ForegroundColor Magenta

if (-not (Test-DockerRunning)) {
    Write-Host "`nPlease start Docker Desktop and try again.`n" -ForegroundColor Red
    exit 1
}

if ($Build) {
    Build-LabImages
}

switch ($Scenario.ToLower()) {
    "crasher" { Test-Crasher }
    "unhealthy" { Test-Unhealthy }
    "restart-loop" { Test-RestartLoop }
    "cpu-stress" { Test-CPUStress }
    "memory-pressure" { Test-MemoryPressure }
    "missing-dependency" { Test-MissingDependency }
    "config-error" { Test-ConfigError }
    "isolation" { Test-Isolation }
    "all" {
        Test-Crasher
        Test-Unhealthy
        Test-RestartLoop
        Test-CPUStress
        Test-MemoryPressure
        Test-MissingDependency
        Test-ConfigError
        Test-Isolation
    }
    default {
        Write-Host "Unknown scenario: $Scenario" -ForegroundColor Red
        Write-Host "Available: crasher, unhealthy, restart-loop, cpu-stress, memory-pressure, missing-dependency, config-error, isolation, all" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "`n✓ Test suite completed`n" -ForegroundColor Green
