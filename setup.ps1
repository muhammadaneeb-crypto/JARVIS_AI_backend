# JARVIS_AI - Phase 1 setup. Run in PowerShell from the JARVIS_AI folder:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

Write-Host "== 1/4 Checking Python ==" -ForegroundColor Cyan
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python not found. Install Python 3.11+ from https://www.python.org/downloads/ (tick 'Add to PATH')." -ForegroundColor Red
    exit 1
}
python --version

Write-Host "== 2/4 Creating virtual environment and installing packages ==" -ForegroundColor Cyan
if (-not (Test-Path "$root\.venv")) { python -m venv "$root\.venv" }
& "$root\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$root\.venv\Scripts\python.exe" -m pip install -r "$root\python_backend\requirements.txt"

Write-Host "== 3/4 Creating .env ==" -ForegroundColor Cyan
if (-not (Test-Path "$root\.env")) { Copy-Item "$root\.env.example" "$root\.env"; Write-Host ".env created (API keys are optional for Phase 1)." }

Write-Host "== 4/4 Preparing Flutter Windows project ==" -ForegroundColor Cyan
if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
    Write-Host "Flutter not found. Install it from https://docs.flutter.dev/get-started/install/windows/desktop (also needs Visual Studio with 'Desktop development with C++')." -ForegroundColor Yellow
    Write-Host "Backend setup is complete. Re-run this script after installing Flutter."
    exit 0
}
if (-not (Test-Path "$root\flutter_app\windows")) {
    flutter create --platforms=windows --project-name jarvis_ai "$root\_tmp_runner"
    Copy-Item "$root\_tmp_runner\windows" "$root\flutter_app\windows" -Recurse
    Remove-Item "$root\_tmp_runner" -Recurse -Force
}
Set-Location "$root\flutter_app"
flutter pub get
Write-Host "`nSetup finished. Next: .\run_backend.ps1  (terminal 1)  and  .\run_app.ps1  (terminal 2)" -ForegroundColor Green
