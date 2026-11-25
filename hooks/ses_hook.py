import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "daemon"))
import yollar

SES_AD = yollar.SES_AD
RUN_DIR = yollar.RUN_DIR
CONFIG_DIR = yollar.CONFIG_DIR
CONFIG_FILE = yollar.CONFIG_FILE
DILLER_FILE = yollar.DILLER_FILE
OTURUM_FILE = yollar.OTURUM_FILE
PLUGIN_ROOT = yollar.PLUGIN_ROOT
SES_PY = str(PLUGIN_ROOT / "scripts" / "ses.py")


def ayar_oku():
    varsayilan = {
        "dil": "tr",
        "asistan_adi": "Nova",
        "kullanici_adi": "",
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                varsayilan.update(d)
        except Exception:
            pass
    return varsayilan


def dil_verisi_al(dil_kodu):
    try:
        with open(DILLER_FILE, "r", encoding="utf-8") as f:
            diller = json.load(f)
            return diller.get(dil_kodu, diller.get("tr", {}))
    except Exception:
        return {}


def temizle(metin):
    metin = re.sub(r"```.*?```", " ", metin, flags=re.S)
    metin = re.sub(r"\[(Kesin|Muhtemel|Tahmin)\]", "", metin)
    metin = re.sub(r"https?://\S+|`[^`]*`", "", metin)
    metin = re.sub(r"[*_#>|]+", "", metin)
    return re.sub(r"\s+", " ", metin).strip()[:400]


def main():
    d = json.load(sys.stdin)
    olay = d.get("hook_event_name")
    oturum = d.get("session_id", "")
    oturum_dosya = OTURUM_FILE
    aktif = yollar.calisiyor_mu()
    sahip = oturum_dosya.read_text(encoding="utf-8").strip() if oturum_dosya.exists() else ""
    if aktif and sahip == "?" and oturum:
        oturum_dosya.write_text(oturum, encoding="utf-8")
        sahip = oturum
    bizim = aktif and sahip == oturum

    ayarlar = ayar_oku()
    dil_verisi = dil_verisi_al(ayarlar.get("dil", "tr"))
    asistan_adi = ayarlar.get("asistan_adi", "Nova")
    kullanici_adi = ayarlar.get("kullanici_adi", "")

    if olay == "UserPromptSubmit":
        prompt = d.get("prompt", "").strip()
        if prompt.rstrip("/").replace("handsfree-voice:", "") in ("/ses", "/handsfree") or "CLAUDE_SES_TOGGLE" in prompt:
            if bizim:
                subprocess.run([sys.executable, SES_PY, "off"])
                bilgi = dil_verisi.get("bilgi_kapandi", "Ses modu kapatıldı.")
                print(json.dumps({"decision": "block", "reason": bilgi}))
            else:
                RUN_DIR.mkdir(parents=True, exist_ok=True)
                oturum_dosya.write_text(oturum, encoding="utf-8")
                subprocess.run([sys.executable, SES_PY, "on"])
                bilgi_sablon = dil_verisi.get("bilgi_acildi", "Ses modu açılıyor (~20 sn). '{ad} ...' diye başla.")
                bilgi = bilgi_sablon.format(ad=asistan_adi, kullanici=kullanici_adi)
                print(json.dumps({"decision": "block", "reason": bilgi}))
        elif bizim:
            baglam_sablon = dil_verisi.get(
                "baglam",
                "VOICE MODE ON: user speaks Turkish. Work and answer in the terminal normally and fully. The LAST line of your reply must start with \"Sesli: \" (keep this exact prefix) and contain 1-2 short natural sentences in Turkish, no markdown/code/paths. Your name in voice mode is {ad}; address the user as {kullanici}."
            )
            if not kullanici_adi and ";" in baglam_sablon:
                baglam_sablon = baglam_sablon[:baglam_sablon.rfind(";")] + "."
            baglam = baglam_sablon.format(ad=asistan_adi, kullanici=kullanici_adi)
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": baglam}}))

    elif olay == "Stop" and bizim:
        son = ""
        try:
            transcript_yolu = d.get("transcript_path", "")
            if transcript_yolu and os.path.exists(transcript_yolu):
                with open(transcript_yolu, "r", encoding="utf-8") as f:
                    for satir in f:
                        e = json.loads(satir)
                        if e.get("type") != "assistant":
                            continue
                        icerik = e.get("message", {}).get("content", [])
                        yazi = " ".join(c.get("text", "") for c in icerik if isinstance(c, dict) and c.get("type") == "text")
                        if yazi.strip():
                            son = yazi
        except Exception:
            pass

        sesli = re.findall(r"^\s*\**Sesli:\**\s*(.+)$", son, flags=re.M)
        son = temizle(sesli[-1] if sesli else re.split(r"(?<=[.!?])\s", temizle(son))[0])
        if son:
            yollar.gonder({"say": son})


if __name__ == "__main__":
    main()
