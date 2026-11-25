import json
import os
import socket
import sys
from pathlib import Path

SES_AD = os.environ.get("SES_AD", "handsfree-voice")
WINDOWS = sys.platform == "win32"
if WINDOWS:
    CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / SES_AD
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / SES_AD
    RUN_DIR = DATA_DIR / "run"
    VENV_PY = DATA_DIR / "venv" / "Scripts" / "python.exe"
    VENV_PYW = DATA_DIR / "venv" / "Scripts" / "pythonw.exe"
else:
    CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / SES_AD
    DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / SES_AD
    _run = os.environ.get("XDG_RUNTIME_DIR")
    RUN_DIR = Path(_run) / SES_AD if _run else DATA_DIR / "run"
    VENV_PY = VENV_PYW = DATA_DIR / "venv" / "bin" / "python"
CONFIG_FILE = CONFIG_DIR / "ayar.json"
SESLER_DIR = DATA_DIR / "sesler"
PORT_FILE = RUN_DIR / "port"
PID_FILE = RUN_DIR / "pid"
OTURUM_FILE = RUN_DIR / "oturum"
LOG_FILE = RUN_DIR / "log"
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DILLER_FILE = PLUGIN_ROOT / "daemon" / "diller.json"


def gonder(veri, zaman_asimi=2.0):
    try:
        port = int(PORT_FILE.read_text().strip())
        with socket.create_connection(("127.0.0.1", port), timeout=zaman_asimi) as s:
            s.sendall((json.dumps(veri, ensure_ascii=False) + "\n").encode("utf-8"))
        return True
    except Exception:
        return False


def calisiyor_mu():
    try:
        pid = int(PID_FILE.read_text().strip())
    except Exception:
        return False
    if not WINDOWS:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    kod = ctypes.c_ulong()
    k32.GetExitCodeProcess(h, ctypes.byref(kod))
    k32.CloseHandle(h)
    return kod.value == 259
