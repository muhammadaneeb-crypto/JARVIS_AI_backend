# Starts the JARVIS_AI backend (run from the JARVIS_AI folder).
$root = $PSScriptRoot
Set-Location "$root\python_backend"
& "$root\.venv\Scripts\python.exe" -m app.main
