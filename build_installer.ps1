# Build Installer Script for Moria MOD Creator
# This script:
# 1. Cleans mymodfiles (removes subdirs without .ini files)
# 2. Creates Definitions.zip and mymodfiles.zip
# 3. Builds the installer with Inno Setup
# 4. Signs the installer

param(
    [switch]$SkipSign,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

# Paths
$ProjectRoot = $PSScriptRoot
$AppDataDir = "$env:APPDATA\MoriaMODCreator"
$ReleaseDir = "$ProjectRoot\release"
$InstallerScript = "$ProjectRoot\installer\MoriaMODCreator.iss"
$SignTool = "$env:USERPROFILE\Tools\CodeSignTool\sign.bat"
$InnoSetup = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Moria MOD Creator - Build Installer  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Clean mymodfiles - remove subdirs without .ini files
Write-Host "[1/5] Cleaning mymodfiles directory..." -ForegroundColor Yellow
$mymodfilesDir = "$AppDataDir\mymodfiles"

if (Test-Path $mymodfilesDir) {
    # Get all subdirectories recursively (deepest first for proper cleanup)
    $subdirs = Get-ChildItem $mymodfilesDir -Directory -Recurse | Sort-Object { $_.FullName.Length } -Descending
    
    $removed = 0
    $kept = 0
    
    foreach ($dir in $subdirs) {
        # Check if this directory or any subdirectory contains .ini files
        $hasIniFiles = Get-ChildItem $dir.FullName -Filter "*.ini" -Recurse -File -ErrorAction SilentlyContinue
        
        if (-not $hasIniFiles) {
            # No .ini files - remove the directory
            Remove-Item $dir.FullName -Recurse -Force -ErrorAction SilentlyContinue
            $removed++
        } else {
            # Has .ini files - remove non-.ini files but keep the directory structure
            Get-ChildItem $dir.FullName -File -Recurse | Where-Object { $_.Extension -ne ".ini" } | Remove-Item -Force -ErrorAction SilentlyContinue
            $kept++
        }
    }
    
    Write-Host "   Removed $removed empty subdirectories, kept $kept with .ini files" -ForegroundColor Green
} else {
    Write-Host "   mymodfiles directory not found, skipping cleanup" -ForegroundColor DarkYellow
}

# Step 2: Create Definitions.zip
Write-Host "[2/5] Creating Definitions.zip..." -ForegroundColor Yellow
$definitionsDir = "$AppDataDir\Definitions"
$definitionsZip = "$ReleaseDir\Definitions.zip"

if (Test-Path $definitionsDir) {
    if (Test-Path $definitionsZip) { Remove-Item $definitionsZip -Force }
    Compress-Archive -Path "$definitionsDir\*" -DestinationPath $definitionsZip -CompressionLevel Optimal
    $zipSize = [math]::Round((Get-Item $definitionsZip).Length / 1KB)
    Write-Host "   Created Definitions.zip ($zipSize KB)" -ForegroundColor Green
} else {
    Write-Host "   Definitions directory not found!" -ForegroundColor Red
    exit 1
}

# Step 3: Create mymodfiles.zip
Write-Host "[3/5] Creating mymodfiles.zip..." -ForegroundColor Yellow
$mymodfilesZip = "$ReleaseDir\mymodfiles.zip"

if (Test-Path $mymodfilesDir) {
    if (Test-Path $mymodfilesZip) { Remove-Item $mymodfilesZip -Force }
    Compress-Archive -Path "$mymodfilesDir\*" -DestinationPath $mymodfilesZip -CompressionLevel Optimal
    $zipSize = [math]::Round((Get-Item $mymodfilesZip).Length / 1KB)
    Write-Host "   Created mymodfiles.zip ($zipSize KB)" -ForegroundColor Green
} else {
    Write-Host "   mymodfiles directory not found!" -ForegroundColor Red
    exit 1
}

# Step 4: Build installer with Inno Setup
if (-not $SkipBuild) {
    Write-Host "[4/5] Building installer with Inno Setup..." -ForegroundColor Yellow
    
    if (-not (Test-Path $InnoSetup)) {
        Write-Host "   Inno Setup not found at: $InnoSetup" -ForegroundColor Red
        exit 1
    }
    
    & $InnoSetup $InstallerScript
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   Installer build failed!" -ForegroundColor Red
        exit 1
    }
    
    # Find the generated installer
    $installer = Get-ChildItem $ReleaseDir -Filter "MoriaMODCreator_Setup_*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Write-Host "   Built: $($installer.Name)" -ForegroundColor Green
} else {
    Write-Host "[4/5] Skipping installer build (--SkipBuild)" -ForegroundColor DarkYellow
    $installer = Get-ChildItem $ReleaseDir -Filter "MoriaMODCreator_Setup_*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

# Step 5: Sign the installer
if (-not $SkipSign -and $installer) {
    Write-Host "[5/5] Signing installer..." -ForegroundColor Yellow
    
    if (-not (Test-Path $SignTool)) {
        Write-Host "   Sign tool not found at: $SignTool" -ForegroundColor Red
        Write-Host "   Skipping signing" -ForegroundColor DarkYellow
    } else {
        # Run sign tool from its directory
        Push-Location (Split-Path $SignTool)
        & $SignTool $installer.FullName
        Pop-Location
        
        # Verify signature
        $sig = Get-AuthenticodeSignature $installer.FullName
        if ($sig.Status -eq "Valid") {
            Write-Host "   Signed successfully by: $(($sig.SignerCertificate.Subject -split ',')[0] -replace 'CN=')" -ForegroundColor Green
        } else {
            Write-Host "   Signing failed or not verified" -ForegroundColor Red
        }
    }
} else {
    Write-Host "[5/5] Skipping signing (--SkipSign or no installer)" -ForegroundColor DarkYellow
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Build Complete!                      " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Output files in: $ReleaseDir" -ForegroundColor White
Get-ChildItem $ReleaseDir -File | ForEach-Object {
    $size = if ($_.Length -gt 1MB) { "{0:N2} MB" -f ($_.Length / 1MB) } else { "{0:N0} KB" -f ($_.Length / 1KB) }
    Write-Host "  - $($_.Name) ($size)"
}
