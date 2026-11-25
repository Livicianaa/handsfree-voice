import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

DAEMON_DIR = Path(__file__).resolve().parent.parent / "daemon"
sys.path.insert(0, str(DAEMON_DIR))
import yollar


def baslat(kurulum):
    if yollar.calisiyor_mu():
        return
    yollar.RUN_DIR.mkdir(parents=True, exist_ok=True)
    if not yollar.OTURUM_FILE.is_file() or (time.time() - yollar.OTURUM_FILE.stat().st_mtime) > 5:
        yollar.OTURUM_FILE.write_text("?\n", encoding="utf-8")
    daemon_py = str(yollar.PLUGIN_ROOT / "daemon" / "sesli.py")
    daemon_dir = str(yollar.PLUGIN_ROOT / "daemon")
    if not yollar.WINDOWS and shutil.which("systemd-run"):
        subprocess.run(["systemctl", "--user", "reset-failed", yollar.SES_AD], capture_output=True)
        cmd = ["systemd-run", "--user", f"--unit={yollar.SES_AD}", "--collect", "-q"]
        env_vars = [
            "KITTY_WINDOW_ID",
            "KITTY_PID",
            "KITTY_LISTEN_ON",
            "TMUX",
            "TMUX_PANE",
            "WAYLAND_DISPLAY",
            "HYPRLAND_INSTANCE_SIGNATURE",
            "DISPLAY",
            "PULSE_SOURCE",
            "SES_AD",
            "XDG_RUNTIME_DIR",
        ]
        for v in env_vars:
            val = os.environ.get(v)
            if val:
                cmd.append(f"--setenv={v}={val}")
        cmd.append(f"--working-directory={daemon_dir}")
        cmd.extend([str(yollar.VENV_PY), "-u", daemon_py])
        if kurulum:
            cmd.append("--kurulum")
        subprocess.run(cmd)
    elif yollar.WINDOWS:
        env = os.environ.copy()
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            env["SES_HWND"] = str(hwnd)
        except Exception:
            pass
        flags = 0x00000008 | 0x00000200 | 0x08000000
        cmd = [str(yollar.VENV_PYW), daemon_py]
        if kurulum:
            cmd.append("--kurulum")
        subprocess.Popen(
            cmd,
            cwd=daemon_dir,
            env=env,
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    else:
        cmd = [str(yollar.VENV_PY), "-u", daemon_py]
        if kurulum:
            cmd.append("--kurulum")
        subprocess.Popen(
            cmd,
            cwd=daemon_dir,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def durdur():
    yollar.gonder({"quit": True})
    bitis = time.time() + 5.0
    while time.time() < bitis:
        if not yollar.calisiyor_mu():
            break
        time.sleep(0.2)
    if yollar.calisiyor_mu():
        if not yollar.WINDOWS and shutil.which("systemctl"):
            subprocess.run(["systemctl", "--user", "stop", yollar.SES_AD], capture_output=True)
        elif yollar.WINDOWS:
            try:
                pid = int(yollar.PID_FILE.read_text().strip())
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
            except Exception:
                pass
        else:
            try:
                pid = int(yollar.PID_FILE.read_text().strip())
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    try:
        yollar.OTURUM_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def durum():
    print("active" if yollar.calisiyor_mu() else "inactive")
    if yollar.LOG_FILE.is_file():
        try:
            satirlar = yollar.LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
            for satir in satirlar[-5:]:
                print(satir)
        except Exception:
            pass


def soyle(metin):
    if not metin or not yollar.gonder({"say": metin}):
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: ses.py on|off|say TEXT|status|setup\n")
        sys.exit(1)
    komut = sys.argv[1].lower()
    if komut in ("on", "ac"):
        baslat(False)
    elif komut in ("setup", "kurulum"):
        baslat(True)
    elif komut in ("off", "kapat"):
        durdur()
    elif komut in ("say", "soyle"):
        if len(sys.argv) < 3:
            sys.stderr.write("usage: ses.py say <text>\n")
            sys.exit(1)
        soyle(" ".join(sys.argv[2:]))
    elif komut in ("status", "durum"):
        durum()
    else:
        sys.stderr.write("usage: ses.py on|off|say TEXT|status|setup\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
