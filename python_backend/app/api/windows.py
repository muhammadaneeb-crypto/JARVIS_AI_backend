
"""Safe Windows desktop operations for JARVIS AI."""

import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

import psutil
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import verify_token


router = APIRouter(
    prefix="/windows",
    tags=["Windows"],
    dependencies=[Depends(verify_token)],
)


# ---------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------

ApprovedApp = Literal[
    "notepad",
    "calculator",
    "explorer",
    "chrome",
    "edge",
    "vscode",
    "whatsapp",
    "linkedin",
    "facebook",
    "microsoft_store",
    "copilot",
    "wps_office",
    "word",
    "excel",
    "powerpoint",
]


class OpenAppRequest(BaseModel):
    app: ApprovedApp


class CloseAppRequest(BaseModel):
    app: ApprovedApp


class OpenFolderRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


class SearchFilesRequest(BaseModel):
    query: str = Field(min_length=1, max_length=100)
    directory: str = Field(min_length=1, max_length=1000)
    recursive: bool = True
    max_results: int = Field(default=50, ge=1, le=100)


# ---------------------------------------------------------
# APP CONFIGURATION
# ---------------------------------------------------------

APP_PATHS = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "chrome": [
        "chrome.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "edge": [
        "msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "vscode": [
        "code",
        "code.exe",
        r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
    ],
    "whatsapp": [
        "WhatsApp.exe",
        r"%LOCALAPPDATA%\WhatsApp\WhatsApp.exe",
    ],
    "word": [
        "WINWORD.EXE",
        r"C:\Program Files\Microsoft Office\Office15\WINWORD.EXE",
    ],
    "excel": [
        "EXCEL.EXE",
        r"C:\Program Files\Microsoft Office\Office15\EXCEL.EXE",
    ],
    "powerpoint": [
        "POWERPNT.EXE",
        r"C:\Program Files\Microsoft Office\Office15\POWERPNT.EXE",
    ],
    "wps_office": ["wps.exe"],
    "microsoft_store": ["ms-windows-store:"],
    "copilot": ["ms-copilot:"],
}

APP_URLS = {
    "linkedin": "https://www.linkedin.com",
    "facebook": "https://www.facebook.com",
}


PROCESS_NAMES = {
    "notepad": ["notepad.exe"],
    "calculator": ["CalculatorApp.exe", "Calculator.exe"],
    "chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "vscode": ["Code.exe"],
    "whatsapp": ["WhatsApp.exe"],
    "linkedin": [],
    "facebook": [],
    "word": ["WINWORD.EXE"],
    "excel": ["EXCEL.EXE"],
    "powerpoint": ["POWERPNT.EXE"],
    "wps_office": ["wps.exe", "et.exe", "wpp.exe"],
    "microsoft_store": ["WinStore.App.exe"],
    "copilot": [],
    "explorer": ["explorer.exe"],
}


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def find_executable(candidates: list[str]) -> str | None:
    """Find an executable from approved candidates."""

    for candidate in candidates:
        expanded = os.path.expandvars(candidate)

        if os.path.isabs(expanded) and os.path.isfile(expanded):
            return expanded

        found = shutil.which(expanded)
        if found:
            return found

    return None


# ---------------------------------------------------------
# OPEN APP
# ---------------------------------------------------------

def open_app(body: OpenAppRequest):
    """Open an approved Windows application."""

    if sys.platform != "win32":
        raise HTTPException(
            status_code=501,
            detail="Windows app opening is only supported on Windows.",
        )

    app = body.app

    if app in APP_URLS:
        try:
            os.startfile(APP_URLS[app])
            return {
                "status": "success",
                "app": app,
                "message": f"{app} website opened successfully.",
            }
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    if app == "whatsapp":
        # Try installed desktop application first.
        executable = find_executable(APP_PATHS[app])
        if executable:
            subprocess.Popen([executable], shell=False)
            return {
                "status": "success",
                "app": app,
                "message": "WhatsApp opened.",
            }

        os.startfile("https://web.whatsapp.com")
        return {
            "status": "success",
            "app": app,
            "message": "WhatsApp Web opened.",
        }

    candidates = APP_PATHS.get(app, [])
    executable = find_executable(candidates)

    if not executable:
        # Windows URI protocol applications.
        if app in ("microsoft_store", "copilot"):
            uri = candidates[0]
            try:
                os.startfile(uri)
                return {
                    "status": "success",
                    "app": app,
                    "message": f"{app} opened.",
                }
            except OSError as exc:
                raise HTTPException(status_code=500, detail=str(exc))

        raise HTTPException(
            status_code=404,
            detail=f"{app} application executable was not found.",
        )

    try:
        subprocess.Popen([executable], shell=False)
        return {
            "status": "success",
            "app": app,
            "message": f"{app} opened successfully.",
        }
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not open {app}: {str(exc)}",
        )


@router.post("/open-app")
def open_app_endpoint(body: OpenAppRequest):
    return open_app(body)


# ---------------------------------------------------------
# CLOSE APP
# ---------------------------------------------------------

def request_windows_close(process_id: int) -> bool:
    """Send WM_CLOSE to visible windows belonging to a process."""

    if sys.platform != "win32":
        return False

    user32 = ctypes.windll.user32
    WM_CLOSE = 0x0010
    closed = False

    EnumWindows = user32.EnumWindows
    EnumWindows.restype = ctypes.c_bool

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )

    def callback(hwnd, _lparam):
        nonlocal closed

        window_pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(
            hwnd,
            ctypes.byref(window_pid),
        )

        if window_pid.value == process_id and user32.IsWindowVisible(hwnd):
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            closed = True

        return True

    EnumWindows(EnumWindowsProc(callback), 0)
    return closed


@router.post("/close-app")
def close_app(body: CloseAppRequest):
    """Ask an approved application to close gracefully."""

    if sys.platform != "win32":
        raise HTTPException(
            status_code=501,
            detail="This operation is only supported on Windows.",
        )

    if body.app == "explorer":
        raise HTTPException(
            status_code=400,
            detail="Closing Windows Explorer is not allowed.",
        )

    process_names = PROCESS_NAMES.get(body.app, [])

    if not process_names:
        raise HTTPException(
            status_code=400,
            detail=f"Closing {body.app} is not supported.",
        )

    matching_processes = []

    for process in psutil.process_iter(["pid", "name"]):
        try:
            process_name = process.info["name"]

            if process_name and process_name.casefold() in [
                name.casefold() for name in process_names
            ]:
                matching_processes.append(process)

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not matching_processes:
        return {
            "status": "not_running",
            "app": body.app,
            "message": f"{body.app} is not running.",
        }

    closed_windows = 0

    for process in matching_processes:
        try:
            if request_windows_close(process.pid):
                closed_windows += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue

    return {
        "status": "success" if closed_windows else "no_visible_window",
        "app": body.app,
        "windows_close_requested": closed_windows,
        "message": (
            "Close request sent. Save your work if prompted."
            if closed_windows
            else "No visible application window was found."
        ),
    }


# ---------------------------------------------------------
# OPEN FOLDER
# ---------------------------------------------------------

@router.post("/open-folder")
def open_folder(body: OpenFolderRequest):
    """Open an existing local folder in Windows Explorer."""

    if sys.platform != "win32":
        raise HTTPException(
            status_code=501,
            detail="Folder opening is only supported on Windows.",
        )

    raw_path = body.path.strip()

    if raw_path.startswith("\\\\") or raw_path.startswith("//"):
        raise HTTPException(
            status_code=400,
            detail="Network and UNC paths are not allowed.",
        )

    folder = Path(raw_path)

    if not folder.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="Please provide an absolute folder path.",
        )

    try:
        folder = folder.resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(
            status_code=404,
            detail="Folder does not exist.",
        )

    if not folder.is_dir():
        raise HTTPException(
            status_code=400,
            detail="Provided path is not a folder.",
        )

    try:
        subprocess.Popen(
            ["explorer.exe", str(folder)],
            shell=False,
            close_fds=True,
        )

        return {
            "status": "success",
            "path": str(folder),
            "message": "Folder opened successfully.",
        }

    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not open folder: {str(exc)}",
        )


# ---------------------------------------------------------
# SEARCH FILES
# ---------------------------------------------------------

@router.post("/search-files")
def search_files(body: SearchFilesRequest):
    """Search files and folders by name in a selected directory."""

    if sys.platform != "win32":
        raise HTTPException(
            status_code=501,
            detail="File search is only supported on Windows.",
        )

    query = body.query.strip().casefold()

    if not query:
        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty.",
        )

    raw_directory = body.directory.strip()

    if raw_directory.startswith("\\\\") or raw_directory.startswith("//"):
        raise HTTPException(
            status_code=400,
            detail="Network and UNC paths are not allowed.",
        )

    directory = Path(raw_directory)

    if not directory.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="Please provide an absolute directory path.",
        )

    try:
        directory = directory.resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(
            status_code=404,
            detail="Directory does not exist.",
        )

    if not directory.is_dir():
        raise HTTPException(
            status_code=400,
            detail="Provided path is not a directory.",
        )

    results: list[dict] = []
    scanned_entries = 0
    reached_limit = False

    def ignore_walk_error(_error: OSError) -> None:
        return None

    try:
        for current_root, dirs, filenames in os.walk(
            directory,
            topdown=True,
            onerror=ignore_walk_error,
            followlinks=False,
        ):
            current_folder = Path(current_root)

            safe_dirs = []

            for folder_name in dirs:
                folder_path = current_folder / folder_name

                try:
                    if not folder_path.is_symlink():
                        safe_dirs.append(folder_name)
                except OSError:
                    continue

            dirs[:] = safe_dirs

            entries = [(name, "folder") for name in dirs]
            entries.extend((name, "file") for name in filenames)

            for name, item_type in entries:
                scanned_entries += 1

                if query not in name.casefold():
                    continue

                item_path = current_folder / name

                try:
                    if item_path.is_symlink():
                        continue

                    item_stat = item_path.stat()

                    results.append({
                        "name": name,
                        "path": str(item_path),
                        "type": item_type,
                        "extension": (
                            item_path.suffix.lower()
                            if item_type == "file"
                            else None
                        ),
                        "size_bytes": (
                            item_stat.st_size
                            if item_type == "file"
                            else None
                        ),
                        "modified_timestamp": item_stat.st_mtime,
                    })

                except (OSError, PermissionError):
                    continue

                if len(results) >= body.max_results:
                    reached_limit = True
                    break

            if reached_limit:
                break

            if not body.recursive:
                break

    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"File search failed: {str(exc)}",
        )

    return {
        "status": "success",
        "query": body.query,
        "directory": str(directory),
        "recursive": body.recursive,
        "scanned_entries": scanned_entries,
        "total_results": len(results),
        "results_limit_reached": reached_limit,
        "results": results,
    }
