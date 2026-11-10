import platform
import sys
from pathlib import Path

import psutil
from fastapi import APIRouter, Depends

from app.core.security import verify_token

router = APIRouter(dependencies=[Depends(verify_token)])


@router.get("/windows/system-info")
def system_info() -> dict:
    disk_root = Path.home().anchor or "/"
    disk = psutil.disk_usage(disk_root)
    mem = psutil.virtual_memory()
    battery = None
    if hasattr(psutil, "sensors_battery"):
        b = psutil.sensors_battery()
        if b is not None:
            battery = {"percent": b.percent, "plugged_in": b.power_plugged}
    return {
        "status": "ok",
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram": {"percent": mem.percent, "used_gb": round(mem.used / 1e9, 2),
                "total_gb": round(mem.total / 1e9, 2)},
        "disk": {"percent": disk.percent, "used_gb": round(disk.used / 1e9, 1),
                 "total_gb": round(disk.total / 1e9, 1)},
        "battery": battery,
        "os": platform.platform(),
        "python": sys.version.split()[0],
    }
