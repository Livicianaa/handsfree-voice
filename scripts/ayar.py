import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

DAEMON_DIR = Path(__file__).resolve().parent.parent / "daemon"
sys.path.insert(0, str(DAEMON_DIR))
from yollar import CONFIG_FILE, DATA_DIR, SESLER_DIR

VOICES_JSON = DATA_DIR / "voices.json"
SESLER = SESLER_DIR
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
VARSAYILAN = {"ses_seviyesi": 1.0, "hiz": 1.0, "sessiz": False}


def oku():
    veri = dict(VARSAYILAN)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                veri.update(json.load(f))
        except Exception:
            pass
    return veri


def yaz(d):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_dosya = CONFIG_FILE.parent / f"{CONFIG_FILE.name}.tmp"
    with open(tmp_dosya, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    tmp_dosya.replace(CONFIG_FILE)


def sesler(dil):
    if not VOICES_JSON.exists():
        VOICES_JSON.parent.mkdir(parents=True, exist_ok=True)
        tmp_voices = VOICES_JSON.parent / f"{VOICES_JSON.name}.tmp"
        req = urllib.request.Request(HF + "voices.json", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(tmp_voices, "wb") as f:
            shutil.copyfileobj(resp, f)
        tmp_voices.replace(VOICES_JSON)
    with open(VOICES_JSON, "r", encoding="utf-8") as f:
        veri = json.load(f)
    degerler = [v for v in veri.values() if isinstance(v, dict) and v.get("language", {}).get("family") == dil]
    kalite_sira = {"x_low": 0, "low": 1, "medium": 2, "high": 3}
    degerler.sort(
        key=lambda v: (
            v.get("language", {}).get("code", ""),
            v.get("name", ""),
            kalite_sira.get(v.get("quality", ""), 99)
        )
    )
    return degerler


def durum_komutu():
    ayar = oku()
    motor = ayar.get("motor", "piper")
    dil = ayar.get("dil", "tr")
    piper_ses = ayar.get("piper_ses", "")
    if motor == "piper":
        aktif_stem = Path(piper_ses).stem if piper_ses else ""
        ses_listesi = [
            {
                "anahtar": v["key"],
                "konusmaci": v["name"],
                "bolge": v.get("language", {}).get("code", ""),
                "kalite": v.get("quality", ""),
                "aktif": v["key"] == aktif_stem,
            }
            for v in sesler(dil)
        ]
    else:
        ses_listesi = []
    cikti = {
        "motor": motor,
        "dil": dil,
        "ses_seviyesi": ayar.get("ses_seviyesi", 1.0),
        "hiz": ayar.get("hiz", 1.0),
        "sessiz": ayar.get("sessiz", False),
        "sesler": ses_listesi,
    }
    print(json.dumps(cikti, ensure_ascii=False, indent=2))


def ayarla_komutu(argumanlar):
    ayar = oku()
    for arg in argumanlar:
        if "=" not in arg:
            sys.exit(f"Invalid argument: {arg}")
        k, v = arg.split("=", 1)
        if k == "ses_seviyesi":
            try:
                val = float(v)
            except ValueError:
                sys.exit(f"Invalid ses_seviyesi value: {v}")
            val = max(0.1, min(1.5, val))
            ayar["ses_seviyesi"] = round(val, 2)
        elif k == "hiz":
            try:
                val = float(v)
            except ValueError:
                sys.exit(f"Invalid hiz value: {v}")
            val = max(0.6, min(1.8, val))
            ayar["hiz"] = round(val, 2)
        elif k == "sessiz":
            ayar["sessiz"] = v.lower() in ("1", "true", "evet", "yes", "on")
        else:
            sys.exit(f"Unknown setting: {k}")
    yaz(ayar)
    sonuc = {
        "ses_seviyesi": ayar["ses_seviyesi"],
        "hiz": ayar["hiz"],
        "sessiz": ayar["sessiz"],
    }
    print(json.dumps(sonuc, ensure_ascii=False, indent=2))


def ses_komutu(argumanlar):
    if not argumanlar:
        sys.exit("usage: ayar.py voice <key>")
    anahtar = argumanlar[0]
    ayar = oku()
    dil = ayar.get("dil", "tr")
    bulunan = None
    for s in sesler(dil):
        if s.get("key") == anahtar:
            bulunan = s
            break
    if not bulunan:
        sys.exit(f"Voice not found: {anahtar}")
    onnx_rel = None
    for dosya in bulunan.get("files", {}):
        if dosya.endswith(".onnx"):
            onnx_rel = dosya
            break
    if not onnx_rel:
        sys.exit(f"ONNX file not found: {anahtar}")
    json_rel = onnx_rel + ".json"
    SESLER_DIR.mkdir(parents=True, exist_ok=True)
    target_onnx = SESLER_DIR / f"{anahtar}.onnx"
    target_json = SESLER_DIR / f"{anahtar}.onnx.json"
    if not target_onnx.exists():
        tmp_onnx = target_onnx.with_suffix(".tmp")
        req = urllib.request.Request(HF + onnx_rel, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(tmp_onnx, "wb") as f:
            shutil.copyfileobj(resp, f)
        tmp_onnx.replace(target_onnx)
    if not target_json.exists():
        tmp_json = target_json.with_suffix(".tmp")
        req = urllib.request.Request(HF + json_rel, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(tmp_json, "wb") as f:
            shutil.copyfileobj(resp, f)
        tmp_json.replace(target_json)
    ayar["piper_ses"] = str(target_onnx)
    yaz(ayar)
    print(json.dumps({"anahtar": anahtar, "piper_ses": str(target_onnx)}, ensure_ascii=False, indent=2))


def main():
    if len(sys.argv) <= 1 or sys.argv[1] in ("durum", "status"):
        durum_komutu()
    elif sys.argv[1] in ("ayarla", "set"):
        ayarla_komutu(sys.argv[2:])
    elif sys.argv[1] in ("ses", "voice"):
        ses_komutu(sys.argv[2:])
    else:
        sys.exit("usage: ayar.py [status | set ses_seviyesi=0.8 hiz=1.2 sessiz=false | voice <key>]")


if __name__ == "__main__":
    main()
