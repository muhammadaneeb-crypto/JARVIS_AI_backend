# JARVIS_AI — Phase 1 + Supabase login

Windows desktop AI assistant. **Phase 1** = project structure + Flutter dashboard with animated orb + FastAPI backend + secured local connection.
Voice, AI, automation, browser, files, database come in later phases. Their buttons/endpoints say "not implemented yet" instead of pretending.

## Login / Signup / Logout (Supabase)
Supabase setup guide: `supabase/SUPABASE_SETUP.md`. Short version: run `supabase/schema.sql` in the Supabase SQL Editor, then put `SUPABASE_URL` and `SUPABASE_ANON_KEY` in `.env`.
- Without Supabase keys the app still starts; the login screen offers "Bina login ke chalayein".
- Passwords go only from the app to the local backend to Supabase. They are never stored by JARVIS_AI.
- The login session lives in backend memory only, so you log in again after restarting the backend.
- Database tables use Row Level Security: every user sees only their own rows. `/history` (GET/POST) already uses the `task_history` table.

## Requirements (install once)
1. Python 3.11+ — https://www.python.org/downloads/ (tick "Add Python to PATH")
2. Flutter SDK — https://docs.flutter.dev/get-started/install/windows/desktop
3. Visual Studio 2022 with "Desktop development with C++" (Flutter needs it for Windows apps)

## Setup (PowerShell, inside the JARVIS_AI folder)
```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

## Run (two PowerShell windows)
Window 1 (backend):
```powershell
.\run_backend.ps1
```
Window 2 (app):
```powershell
.\run_app.ps1
```
The green dot at top right means the app is connected. CPU/RAM/Disk rings show live data from the backend.

## Run tests
```powershell
cd python_backend
..\.venv\Scripts\python.exe -m pytest -q
cd ..\flutter_app
flutter test
```

## How security works (Phase 1)
- Backend listens on 127.0.0.1 only (non-local hosts are refused).
- On first start the backend creates a random token at `%APPDATA%\JARVIS_AI\api_token.txt`. The app reads that file and sends it as `Authorization: Bearer ...`. Only `/health` is public.
- API keys live in `.env` only (optional in Phase 1).

## Troubleshooting
- Red dot / "Backend offline": start `.\run_backend.ps1` first.
- `flutter` not found: reopen PowerShell after installing Flutter. Run `flutter doctor`.
- Script blocked: use the `-ExecutionPolicy Bypass` command shown above.
