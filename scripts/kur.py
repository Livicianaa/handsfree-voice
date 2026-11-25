import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

DAEMON_DIR = Path(__file__).resolve().parent.parent / "daemon"
sys.path.insert(0, str(DAEMON_DIR))
import yollar


class ArgParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write(f"error: {message}\n")
        sys.exit(1)


def main():
    parser = ArgParser(description="Voice mode setup")
    parser.add_argument("--lang", "--dil", dest="lang", default="tr")
    parser.add_argument("--engine", "--motor", dest="engine", default="piper", choices=["piper", "chatterbox"])
    parser.add_argument("--reference", "--referans", dest="reference", default="")
    parser.add_argument("--name", "--ad", dest="name", default="")
    args = parser.parse_args()

    if shutil.which("nvidia-smi"):
        print("GPU:")
        try:
            subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                check=False,
            )
        except Exception:
            pass

    yollar.DATA_DIR.mkdir(parents=True, exist_ok=True)
    yollar.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    yollar.SESLER_DIR.mkdir(parents=True, exist_ok=True)

    venv_dir = yollar.DATA_DIR / "venv"
    if not yollar.VENV_PY.exists():
        if shutil.which("uv"):
            res = subprocess.run(["uv", "venv", str(venv_dir)])
        else:
            res = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)])
        if res.returncode != 0 or not yollar.VENV_PY.exists():
            sys.stderr.write("Failed to create virtual environment.\n")
            sys.exit(1)

    pkgs = ["faster-whisper", "sounddevice", "numpy", "piper-tts"]
    if args.engine == "chatterbox":
        pkgs.append("chatterbox-tts")
    if shutil.which("nvidia-smi"):
        pkgs.extend(["nvidia-cublas-cu12", "nvidia-cudnn-cu12"])

    if shutil.which("uv"):
        cmd_pip = ["uv", "pip", "install", "--python", str(yollar.VENV_PY)] + pkgs
    else:
        cmd_pip = [str(yollar.VENV_PY), "-m", "pip", "install"] + pkgs

    res = subprocess.run(cmd_pip)
    if res.returncode != 0:
        sys.stderr.write("Failed to install packages.\n")
        sys.exit(1)

    if not yollar.DILLER_FILE.exists():
        sys.stderr.write(f"Language definitions file not found: {yollar.DILLER_FILE}\n")
        sys.exit(1)

    try:
        with open(yollar.DILLER_FILE, "r", encoding="utf-8") as f:
            diller_veri = json.load(f)
    except Exception as e:
        sys.stderr.write(f"Failed to read {yollar.DILLER_FILE}: {e}\n")
        sys.exit(1)

    info = diller_veri.get(args.lang, diller_veri.get("tr", {}))
    voice_name = info.get("voice", "")
    voice_url = info.get("voice_url", "")
    json_url = info.get("json_url", "")

    onnx_target = yollar.SESLER_DIR / f"{voice_name}.onnx" if voice_name else None
    json_target = yollar.SESLER_DIR / f"{voice_name}.onnx.json" if voice_name else None

    def indir(url, hedef):
        if not url or not hedef or hedef.exists():
            return
        tmp = hedef.with_name(hedef.name + ".tmp")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp, open(tmp, "wb") as out:
                shutil.copyfileobj(resp, out)
            tmp.replace(hedef)
        except Exception as e:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            sys.stderr.write(f"Failed to download {url}: {e}\n")
            sys.exit(1)

    if voice_url and onnx_target:
        indir(voice_url, onnx_target)
    if json_url and json_target:
        indir(json_url, json_target)

    piper_ses = str(onnx_target) if onnx_target and (onnx_target.exists() or voice_url) else ""
    mevcut = {
        "dil": args.lang,
        "motor": args.engine,
        "piper_ses": piper_ses,
        "referans_wav": args.reference,
        "asistan_adi": args.name,
        "uyandirma": [args.name.lower()] if args.name else [],
        "kullanici_adi": "",
    }

    if yollar.CONFIG_FILE.exists():
        try:
            with open(yollar.CONFIG_FILE, "r", encoding="utf-8") as f:
                eski = json.load(f)
                eski.update({k: v for k, v in mevcut.items() if v or k not in eski})
                mevcut = eski
        except Exception:
            pass

    try:
        with open(yollar.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(mevcut, f, ensure_ascii=False, indent=2)
    except Exception as e:
        sys.stderr.write(f"Failed to write configuration: {e}\n")
        sys.exit(1)

    whisper_code = (
        "import shutil\n"
        "from faster_whisper.utils import download_model\n"
        "download_model('small')\n"
        "if shutil.which('nvidia-smi'):\n"
        "    download_model('large-v3-turbo')\n"
    )
    res = subprocess.run([str(yollar.VENV_PY), "-c", whisper_code])
    if res.returncode != 0:
        sys.stderr.write("Failed to download Whisper model.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
