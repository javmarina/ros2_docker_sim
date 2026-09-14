# Build script for ROS 2 Simulation Launcher
# Clean PyInstaller packaging pipeline

$ErrorActionPreference = "Stop"

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  Compilando ROS 2 Simulation Launcher (.exe)" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

# 1. Limpieza de artefactos previos
Write-Host "`n[1/3] Limpiando carpetas build y dist..." -ForegroundColor Yellow
if (Test-Path "build") {
    Remove-Item -Path "build" -Recurse -Force
    Write-Host "  - Carpeta build/ eliminada." -ForegroundColor DarkGray
}
if (Test-Path "dist") {
    Remove-Item -Path "dist" -Recurse -Force
    Write-Host "  - Carpeta dist/ eliminada." -ForegroundColor DarkGray
}

# 2. Localizar interprete de Python / PyInstaller
Write-Host "`n[2/3] Verificando entorno de compilacion..." -ForegroundColor Yellow
$PY_CMD = ""
$USE_MODULE = $false

if (Test-Path ".venv\Scripts\pyinstaller.exe") {
    $PY_CMD = ".venv\Scripts\pyinstaller.exe"
} elseif (Get-Command pyinstaller -ErrorAction SilentlyContinue) {
    $PY_CMD = "pyinstaller"
} elseif (Test-Path "C:\Users\$env:USERNAME\AppData\Local\Python\bin\python.exe") {
    $PY_CMD = "C:\Users\$env:USERNAME\AppData\Local\Python\bin\python.exe"
    $USE_MODULE = $true
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PY_CMD = "python"
    $USE_MODULE = $true
} else {
    Write-Host "ERROR: No se encontro Python ni PyInstaller." -ForegroundColor Red
    exit 1
}

Write-Host "  Usando ejecutable: $PY_CMD" -ForegroundColor Green

# 3. Ejecutar compilacion con ros2_sim_launcher.spec
Write-Host "`n[3/3] Ejecutando PyInstaller (--clean ros2_sim_launcher.spec)..." -ForegroundColor Yellow
if ($USE_MODULE) {
    & $PY_CMD -m PyInstaller --clean ros2_sim_launcher.spec
} else {
    & $PY_CMD --clean ros2_sim_launcher.spec
}

$EXE_OUT = "dist\ros2_sim_launcher.exe"
if (Test-Path $EXE_OUT) {
    $EXE_ITEM = Get-Item $EXE_OUT
    $SIZE_MB = [math]::Round($EXE_ITEM.Length / 1MB, 2)
    Write-Host "`n===================================================" -ForegroundColor Green
    Write-Host "  COMPILACION COMPLETADA CON EXITO" -ForegroundColor Green
    Write-Host "  Ejecutable: $($EXE_ITEM.FullName)" -ForegroundColor White
    Write-Host "  Tamano:     $SIZE_MB MB" -ForegroundColor White
    Write-Host "  Fecha:      $($EXE_ITEM.LastWriteTime)" -ForegroundColor White
    Write-Host "===================================================" -ForegroundColor Green
} else {
    Write-Host "`nERROR: No se genero el ejecutable en $EXE_OUT." -ForegroundColor Red
    exit 1
}
