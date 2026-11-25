import atexit
import collections
import ctypes
import difflib
import io
import json
import os
import queue
import re
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
import numpy as np
import sounddevice as sd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yollar

SES_AD = yollar.SES_AD
WINDOWS = yollar.WINDOWS
CONFIG_DIR = yollar.CONFIG_DIR
DATA_DIR = yollar.DATA_DIR
RUN_DIR = yollar.RUN_DIR
CONFIG_FILE = yollar.CONFIG_FILE
SESLER_DIR = yollar.SESLER_DIR
PORT_FILE = yollar.PORT_FILE
PID_FILE = yollar.PID_FILE
OTURUM_FILE = yollar.OTURUM_FILE
LOG_FILE = yollar.LOG_FILE
PLUGIN_ROOT = yollar.PLUGIN_ROOT
DILLER_FILE = yollar.DILLER_FILE
WHISPER_DIR = DATA_DIR / "whisper"
DIZIN = RUN_DIR

RUN_DIR.mkdir(parents=True, exist_ok=True)

SR = 16000
BLOK_SURESI = 0.030
BLOK = int(SR * BLOK_SURESI)
ON_TAMPON_BOYUT = int(0.6 / BLOK_SURESI)
SESSILIK_LIMIT = int(0.7 / BLOK_SURESI)
MAX_BLOK = int(15.0 / BLOK_SURESI)
MIN_ORNEK = int(SR * 0.4)

HALUSINASYON_RE = re.compile(
    r"altyaz|abone ol|izlediğiniz için|thanks for watching|subscribe|subtitles|^[.♪ -]+$",
    re.IGNORECASE,
)

konusuyor = False
cikis_istegi = threading.Event()
tts_kuyruk = queue.Queue()
mic_kuyruk = queue.Queue()
test_kuyruk = queue.Queue()


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_uint16),
        ("wScan", ctypes.c_uint16),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_int32),
        ("dy", ctypes.c_int32),
        ("mouseData", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_uint32),
        ("wParamL", ctypes.c_uint16),
        ("wParamH", ctypes.c_uint16),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("u", INPUT_UNION),
    ]


def ses_cihazi_al():
    if not WINDOWS:
        try:
            sd.check_input_settings(device="pulse", channels=1, dtype="float32", samplerate=SR)
            sd.check_output_settings(device="pulse")
            return "pulse"
        except Exception:
            try:
                sd.query_devices("pulse")
                return "pulse"
            except Exception:
                return None
    return None


SES_CIHAZI = ses_cihazi_al()


def giris_akisi_ac(callback):
    try:
        return sd.InputStream(
            samplerate=SR,
            channels=1,
            dtype="float32",
            device=SES_CIHAZI,
            blocksize=BLOK,
            callback=callback,
        )
    except Exception:
        return sd.InputStream(
            samplerate=SR,
            channels=1,
            dtype="float32",
            device=None,
            blocksize=BLOK,
            callback=callback,
        )


def ayar_oku():
    varsayilan = {
        "dil": "tr",
        "motor": "piper",
        "piper_ses": "",
        "referans_wav": "",
        "asistan_adi": "",
        "uyandirma": [],
        "kullanici_adi": "",
        "ses_seviyesi": 1.0,
        "hiz": 1.0,
        "sessiz": False,
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                varsayilan.update(d)
        except Exception:
            pass
    return varsayilan


def ayar_yaz(yeni_ayarlar):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    mevcut = ayar_oku()
    mevcut.update(yeni_ayarlar)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(mevcut, f, ensure_ascii=False, indent=2)
    return mevcut


def dil_verisi_al(dil_kodu):
    try:
        with open(DILLER_FILE, "r", encoding="utf-8") as f:
            diller = json.load(f)
            return diller.get(dil_kodu, diller.get("tr", {}))
    except Exception:
        return {}


def log_yaz(mesaj):
    try:
        zaman = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        satir = f"[{zaman}] {mesaj}\n"
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(satir)
        print(satir, end="", flush=True)
    except Exception:
        pass


def temizle():
    for dosya in (PORT_FILE, PID_FILE):
        try:
            if dosya.exists():
                dosya.unlink()
        except Exception:
            pass


def bol_metin(metin):
    ham = re.split(r"(?<=[.!?])\s+|\r?\n+", metin)
    parcalar = []
    for h in ham:
        h = h.strip()
        if not h:
            continue
        if len(h) <= 250:
            parcalar.append(h)
        else:
            virgullu = re.split(r"(?<=,)\s+", h)
            tampon = ""
            for v in virgullu:
                v = v.strip()
                if not v:
                    continue
                if not tampon:
                    tampon = v
                elif len(tampon) + len(v) + 1 <= 250:
                    tampon += " " + v
                else:
                    parcalar.append(tampon)
                    tampon = v
            if tampon:
                parcalar.append(tampon)
    sonuc = []
    for p in parcalar:
        if len(p) <= 250:
            sonuc.append(p)
        else:
            kelimeler = p.split()
            tampon = ""
            for k in kelimeler:
                if not tampon:
                    tampon = k
                elif len(tampon) + len(k) + 1 <= 250:
                    tampon += " " + k
                else:
                    sonuc.append(tampon)
                    tampon = k
            if tampon:
                sonuc.append(tampon)
    return [s for s in sonuc if s.strip()]


def normalize(ses):
    tepe = np.abs(ses).max() if len(ses) else 0
    return ses * (0.9 / tepe) if tepe > 1e-4 else ses


class PiperTTS:
    def __init__(self, onnx_yolu, ornekleme_hizi=22050):
        from piper.voice import PiperVoice

        yol = str(onnx_yolu)
        if yol.endswith(".json"):
            yol = yol[:-5]
        cfg_yolu = yol + ".json"
        self.voice = PiperVoice.load(yol, config_path=cfg_yolu if os.path.exists(cfg_yolu) else None)
        self.sr = getattr(getattr(self.voice, "config", None), "sample_rate", ornekleme_hizi)

    def generate(self, metin, hiz=1.0):
        from piper.config import SynthesisConfig

        parcalar = []
        for chunk in self.voice.synthesize(metin, syn_config=SynthesisConfig(length_scale=1.0 / max(hiz, 0.1))):
            self.sr = getattr(chunk, "sample_rate", self.sr)
            if hasattr(chunk, "audio_float_array"):
                parcalar.append(np.asarray(chunk.audio_float_array, dtype=np.float32))
            elif hasattr(chunk, "audio_int16_bytes"):
                parcalar.append(np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16).astype(np.float32) / 32768.0)
        if not parcalar:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(parcalar)


class ChatterboxTTS:
    def __init__(self, referans_wav=None, dil="tr"):
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        self.tts = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
        self.dil = dil
        self.sr = getattr(self.tts, "sr", 24000)
        if referans_wav and os.path.exists(referans_wav):
            self.tts.prepare_conditionals(str(referans_wav), exaggeration=0.5)

    def generate(self, metin, hiz=1.0):
        wav = self.tts.generate(metin, language_id=self.dil, exaggeration=0.5, cfg_weight=0.4)
        if wav is None:
            return np.zeros(0, dtype=np.float32)
        if hasattr(wav, "squeeze"):
            wav = wav.squeeze()
        if hasattr(wav, "cpu"):
            return wav.cpu().numpy()
        return np.asarray(wav, dtype=np.float32)


def tts_olustur(ayarlar):
    motor = ayarlar.get("motor", "piper")
    dil = ayarlar.get("dil", "tr")
    if motor == "chatterbox":
        return ChatterboxTTS(referans_wav=ayarlar.get("referans_wav"), dil=dil)
    piper_yol = ayarlar.get("piper_ses", "")
    if not piper_yol or not os.path.exists(piper_yol):
        varsayilan_dizin = SESLER_DIR
        if varsayilan_dizin.exists():
            bulunanlar = list(varsayilan_dizin.glob("*.onnx"))
            if bulunanlar:
                piper_yol = str(bulunanlar[0])
    return PiperTTS(piper_yol)


class TTSYonetici:
    def __init__(self, ayarlar):
        self.ayarlar = ayarlar
        self.motor = tts_olustur(ayarlar)
        self.sr = self.motor.sr
        self.mtime = CONFIG_FILE.stat().st_mtime if CONFIG_FILE.exists() else 0.0

    def tazele(self):
        try:
            m = CONFIG_FILE.stat().st_mtime if CONFIG_FILE.exists() else 0.0
        except OSError:
            return
        if m == self.mtime:
            return
        self.mtime = m
        yeni = ayar_oku()
        degisti = yeni.get("piper_ses") != self.ayarlar.get("piper_ses") or yeni.get("motor") != self.ayarlar.get("motor")
        self.ayarlar = yeni
        if degisti:
            try:
                self.motor = tts_olustur(yeni)
                log_yaz(f"Ses degisti: {Path(str(yeni.get('piper_ses', ''))).stem}")
            except Exception as e:
                log_yaz(f"Ses yukleme hatasi: {e}")

    def generate(self, metin):
        self.tazele()
        if self.ayarlar.get("sessiz"):
            return np.zeros(0, dtype=np.float32)
        ses = self.motor.generate(metin, hiz=float(self.ayarlar.get("hiz", 1.0)))
        self.sr = self.motor.sr
        seviye = float(self.ayarlar.get("ses_seviyesi", 1.0))
        return np.clip(np.asarray(ses, dtype=np.float32) * seviye, -1.0, 1.0)


def ses_seviyesi_degistir(fark):
    d = ayar_oku()
    d["ses_seviyesi"] = round(min(max(float(d.get("ses_seviyesi", 1.0)) + fark, 0.1), 1.5), 2)
    ayar_yaz({"ses_seviyesi": d["ses_seviyesi"]})
    log_yaz(f"Ses seviyesi: {d['ses_seviyesi']}")


def cuda_kutuphaneleri_yukle():
    import glob
    import site
    kokler = [Path(p) / "nvidia" for p in site.getsitepackages() if (Path(p) / "nvidia").is_dir()]
    for kok in kokler:
        if WINDOWS:
            for d in glob.glob(str(kok / "*" / "bin")):
                try:
                    os.add_dll_directory(d)
                except Exception:
                    pass
            continue
        for desen in ("cublas/lib/libcublasLt.so*", "cublas/lib/libcublas.so*", "cudnn/lib/libcudnn*.so*"):
            for f in sorted(glob.glob(str(kok / desen))):
                try:
                    ctypes.CDLL(f, mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    pass


class GuvenliSTT:
    def __init__(self, model, gpu):
        self.model = model
        self.gpu = gpu

    def transcribe(self, ses, **kw):
        try:
            segments, info = self.model.transcribe(ses, **kw)
            return list(segments), info
        except Exception as e:
            hata = str(e).lower()
            if not (self.gpu and ("cuda" in hata or "memory" in hata)):
                raise
            from faster_whisper import WhisperModel
            log_yaz(f"GPU hatasi, islemciye geciliyor: {e}")
            self.model = WhisperModel("small", device="cpu", compute_type="int8")
            self.gpu = False
            segments, info = self.model.transcribe(ses, **kw)
            return list(segments), info


def stt_olustur(dil, asistan_adi):
    import ctranslate2
    from faster_whisper import WhisperModel

    try:
        if ctranslate2.get_cuda_device_count() > 0:
            cuda_kutuphaneleri_yukle()
            model = WhisperModel("large-v3-turbo", device="cuda", compute_type="int8_float16")
            list(model.transcribe(np.zeros(16000, dtype=np.float32), language=dil)[0])
            return GuvenliSTT(model, True)
    except Exception as e:
        log_yaz(f"GPU kullanilamadi, islemciye geciliyor: {e}")
    return GuvenliSTT(WhisperModel("small", device="cpu", compute_type="int8"), False)


def ses_oynat(ses_veri, sr):
    if os.environ.get("SES_SESSIZ") == "1":
        return
    if ses_veri is not None and ses_veri.size > 0:
        try:
            sd.play(ses_veri, sr, device=SES_CIHAZI)
            sd.wait()
        except Exception:
            sd.play(ses_veri, sr, device=None)
            sd.wait()


def tts_thread_fonk(tts):
    global konusuyor
    while not cikis_istegi.is_set():
        try:
            metin = tts_kuyruk.get(timeout=0.1)
        except queue.Empty:
            continue
        if metin is None:
            break
        konusuyor = True
        parcalar = bol_metin(metin)
        for parca in parcalar:
            if cikis_istegi.is_set():
                break
            try:
                ses_veri = tts.generate(parca)
                ses_oynat(ses_veri, tts.sr)
            except Exception as e:
                log_yaz(f"TTS uretim hatasi: {e}")
        time.sleep(0.5)
        if tts_kuyruk.empty():
            konusuyor = False


def senkron_soyle(metin, tts):
    global konusuyor
    konusuyor = True
    try:
        parcalar = bol_metin(metin)
        for parca in parcalar:
            if cikis_istegi.is_set():
                break
            ses_veri = tts.generate(parca)
            ses_oynat(ses_veri, tts.sr)
    except Exception as e:
        log_yaz(f"TTS senkron uretim hatasi: {e}")
    finally:
        time.sleep(0.3)
        konusuyor = False


def socket_sunucu_fonk():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(5)
        server.settimeout(0.5)
        port = server.getsockname()[1]
        PORT_FILE.write_text(str(port), encoding="utf-8")
        while not cikis_istegi.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                with conn:
                    tampon = b""
                    while True:
                        veri = conn.recv(1024)
                        if not veri:
                            break
                        tampon += veri
                        if b"\n" in veri:
                            break
                    satir = tampon.decode("utf-8", errors="ignore").strip()
                    if satir:
                        try:
                            komut = json.loads(satir)
                            if "say" in komut:
                                tts_kuyruk.put(komut["say"])
                            elif komut.get("quit"):
                                log_yaz("Socket quit sinyali alindi.")
                                cikis_istegi.set()
                                break
                        except Exception as e:
                            log_yaz(f"Socket JSON ayristirma hatasi: {e}")
            except Exception as e:
                log_yaz(f"Socket baglanti hatasi: {e}")
    finally:
        try:
            server.close()
        except Exception:
            pass
        try:
            if PORT_FILE.exists():
                PORT_FILE.unlink()
        except OSError:
            pass


def komut_gonder(metin):
    log_yaz(f"Gonderilen komut: {metin}")
    if WINDOWS:
        try:
            hwnd = 0
            if "SES_HWND" in os.environ:
                try:
                    hwnd = int(os.environ["SES_HWND"])
                except Exception:
                    hwnd = 0
            if hwnd:
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, 9)
                fg_hwnd = user32.GetForegroundWindow()
                cur_tid = kernel32.GetCurrentThreadId()
                fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
                if cur_tid != fg_tid and fg_tid != 0:
                    user32.AttachThreadInput(cur_tid, fg_tid, True)
                    user32.SetForegroundWindow(hwnd)
                    user32.AttachThreadInput(cur_tid, fg_tid, False)
                else:
                    user32.SetForegroundWindow(hwnd)
            time.sleep(0.15)
            inputs = []
            raw = metin.encode("utf-16-le")
            for cu in struct.unpack(f"<{len(raw)//2}H", raw):
                inputs.append(INPUT(type=1, ki=KEYBDINPUT(0, cu, 0x0004, 0, 0)))
                inputs.append(INPUT(type=1, ki=KEYBDINPUT(0, cu, 0x0004 | 0x0002, 0, 0)))
            inputs.append(INPUT(type=1, ki=KEYBDINPUT(0x0D, 0, 0, 0, 0)))
            inputs.append(INPUT(type=1, ki=KEYBDINPUT(0x0D, 0, 0x0002, 0, 0)))
            inp_array = (INPUT * len(inputs))(*inputs)
            ctypes.windll.user32.SendInput(len(inputs), inp_array, ctypes.sizeof(INPUT))
        except Exception as e:
            log_yaz(f"Windows SendInput hatasi: {e}")
        return

    kitty_listen = os.environ.get("KITTY_LISTEN_ON")
    kitty_win = os.environ.get("KITTY_WINDOW_ID")
    if kitty_listen and kitty_win:
        try:
            subprocess.run(
                ["kitty", "@", "--to", kitty_listen, "send-text", "--match", f"id:{kitty_win}", metin + "\r"],
                check=True,
            )
            return
        except Exception as e:
            log_yaz(f"Kitty send-text hatasi: {e}")

    tmux = os.environ.get("TMUX")
    tmux_pane = os.environ.get("TMUX_PANE")
    if tmux and tmux_pane:
        try:
            subprocess.run(["tmux", "send-keys", "-t", tmux_pane, metin, "Enter"], check=True)
            return
        except Exception as e:
            log_yaz(f"Tmux send-keys hatasi: {e}")

    kitty_pid = os.environ.get("KITTY_PID")
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        try:
            if kitty_pid:
                subprocess.run(["hyprctl", "dispatch", "focuswindow", f"pid:{kitty_pid}"], check=False)
                time.sleep(0.15)
            subprocess.run(["wtype", "--", metin], check=True)
            subprocess.run(["wtype", "-k", "Return"], check=True)
            return
        except Exception as e:
            log_yaz(f"wtype hatasi: {e}")

    try:
        subprocess.run(["xdotool", "type", "--", metin], check=True)
        subprocess.run(["xdotool", "key", "Return"], check=True)
    except Exception as e:
        log_yaz(f"xdotool hatasi: {e}")


def komut_isle(komut_metni, tts, kapat_kelimeleri, gule_metni):
    kapat_kontrol = re.sub(r"[^\w\s]", "", komut_metni.lower()).strip()
    kapatma_listesi = [re.sub(r"[^\w\s]", "", k.lower()).strip() for k in kapat_kelimeleri]
    dv = dil_verisi_al(ayar_oku().get("dil", "tr"))
    for anahtar, fark in (("ses_kis", -0.2), ("ses_ac", 0.2)):
        if kapat_kontrol in [re.sub(r"[^\w\s]", "", k.lower()).strip() for k in dv.get(anahtar, [])]:
            ses_seviyesi_degistir(fark)
            tts_kuyruk.put(dv.get("tamam", "OK"))
            return
    if kapat_kontrol in kapatma_listesi:
        log_yaz(f"Kapatma komutu alindi: {komut_metni}")
        tts_kuyruk.put(gule_metni)
        time.sleep(0.2)
        bitis = time.time() + 10.0
        while (not tts_kuyruk.empty() or konusuyor) and time.time() < bitis:
            time.sleep(0.05)
        cikis_istegi.set()
        return
    komut_gonder(komut_metni)


def uyandirma_derle(uyandirma_listesi, asistan_adi):
    tum = set()
    if asistan_adi:
        tum.add(asistan_adi.strip().lower())
    for u in uyandirma_listesi:
        if u and u.strip():
            tum.add(u.strip().lower())
    kokler = sorted(tum, key=lambda x: len(x), reverse=True)
    parcalar = [re.escape(k) for k in kokler]
    pattern = r"^(hey\s+)?(" + "|".join(parcalar) + r")\w*\b[\s,.!?:-]*(.*)$" if parcalar else r"^(hey\s+)?()\b[\s,.!?:-]*(.*)$"
    uyandirma_re = re.compile(pattern, re.IGNORECASE | re.DOTALL)
    wake_kokler = tuple(re.sub(r"[^\wçğıöşü]", "", k) for k in kokler if len(k) >= 3)
    return uyandirma_re, wake_kokler


def uyandirma_bul(metin, uyandirma_re, wake_kokler):
    m = uyandirma_re.match(metin)
    if m:
        return m.group(3).strip()
    kelimeler = metin.split()
    for i, k in enumerate(kelimeler[:3]):
        sade = re.sub(r"[^\wçğıöşü]", "", k.lower())
        if len(sade) >= 4 and any(difflib.SequenceMatcher(None, sade, w).ratio() >= 0.8 for w in wake_kokler):
            return re.sub(r"^[\s,.!?:-]+", "", " ".join(kelimeler[i + 1:])).strip()
    return None


def mik_geri_cagri(indata, frames, time_info, status):
    if not konusuyor:
        mic_kuyruk.put(indata[:, 0].copy())


def tek_cumle_kaydet(stt, dil, asistan_adi, timeout=20.0):
    taban = 0.001
    kaydediyor = False
    kayit_bloklari = []
    on_tampon = collections.deque(maxlen=ON_TAMPON_BOYUT)
    sessiz_sayisi = 0
    baslangic = time.time()

    with giris_akisi_ac(mik_geri_cagri):
        while not cikis_istegi.is_set() and (time.time() - baslangic < timeout):
            try:
                blok = mic_kuyruk.get(timeout=0.1)
            except queue.Empty:
                continue

            rms = float(np.sqrt(np.mean(blok ** 2)))
            esik = max(taban * 4.0, 0.004)

            if not kaydediyor:
                if rms > esik:
                    kaydediyor = True
                    kayit_bloklari = list(on_tampon)
                    kayit_bloklari.append(blok)
                    sessiz_sayisi = 0
                else:
                    on_tampon.append(blok)
                    taban = taban * 0.95 + rms * 0.05
            else:
                kayit_bloklari.append(blok)
                if rms > esik:
                    sessiz_sayisi = 0
                else:
                    sessiz_sayisi += 1

                if sessiz_sayisi >= SESSILIK_LIMIT or len(kayit_bloklari) >= MAX_BLOK:
                    ses = np.concatenate(kayit_bloklari) if kayit_bloklari else np.zeros(0, dtype=np.float32)
                    if len(ses) < MIN_ORNEK:
                        kaydediyor = False
                        kayit_bloklari = []
                        sessiz_sayisi = 0
                        on_tampon.clear()
                        continue
                    ses = normalize(ses)
                    try:
                        segments, _ = stt.transcribe(
                            ses,
                            language=dil,
                            beam_size=1,
                            vad_filter=True,
                            initial_prompt=f"{asistan_adi}, ",
                        )
                        return " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.6 and s.avg_logprob > -1.0).strip()
                    except Exception as e:
                        log_yaz(f"Transkripsiyon hatasi: {e}")
                        return ""
    return ""


def cevap_al(stt, dil, asistan_adi):
    if not test_kuyruk.empty():
        time.sleep(1.0)
        return test_kuyruk.get()
    if "SES_TEST_GIRDI" in os.environ:
        return ""
    return tek_cumle_kaydet(stt, dil, asistan_adi)


def kurulum_yap(stt, tts, ayarlar, dil_verisi):
    soru_ad = dil_verisi.get("soru_ad", "Bana ne diye seslenmek istersin?")
    soru_tekrar = dil_verisi.get("soru_tekrar", "Bir kez daha söyler misin?")
    zor_isim = dil_verisi.get("zor_isim", "Bu isim zor anlaşılıyor, başka bir isim söyle.")
    soru_kullanici = dil_verisi.get("soru_kullanici", "Sana ne diye hitap edeyim?")
    hazir_sablon = dil_verisi.get("hazir", "Hazırım {kullanici}. Bana {ad} diye seslen.")
    dil = ayarlar.get("dil", "tr")

    asistan_adi = ""
    uyandirma = []

    while not cikis_istegi.is_set():
        senkron_soyle(soru_ad, tts)
        c1 = cevap_al(stt, dil, asistan_adi)
        k1 = re.sub(r"[^\wçğıöşü]", "", c1.split()[0].lower()) if c1.split() else ""

        senkron_soyle(soru_tekrar, tts)
        c2 = cevap_al(stt, dil, asistan_adi)
        k2 = re.sub(r"[^\wçğıöşü]", "", c2.split()[0].lower()) if c2.split() else ""

        senkron_soyle(soru_tekrar, tts)
        c3 = cevap_al(stt, dil, asistan_adi)
        k3 = re.sub(r"[^\wçğıöşü]", "", c3.split()[0].lower()) if c3.split() else ""

        if not k1 or not k2 or not k3:
            senkron_soyle(zor_isim, tts)
            continue

        r12 = difflib.SequenceMatcher(None, k1, k2).ratio()
        r13 = difflib.SequenceMatcher(None, k1, k3).ratio()
        r23 = difflib.SequenceMatcher(None, k2, k3).ratio()

        if min(r12, r13, r23) < 0.6:
            senkron_soyle(zor_isim, tts)
            continue

        asistan_adi = k1.capitalize()
        uyandirma = list(dict.fromkeys([k1, k2, k3]))
        break

    senkron_soyle(soru_kullanici, tts)
    ck = cevap_al(stt, dil, asistan_adi)
    kullanici_adi = ck.strip().title() if ck.strip() else ayarlar.get("kullanici_adi", "")

    guncel = {
        "asistan_adi": asistan_adi,
        "uyandirma": uyandirma,
        "kullanici_adi": kullanici_adi,
    }
    ayar_yaz(guncel)
    hazir_metin = hazir_sablon.format(kullanici=kullanici_adi, ad=asistan_adi)
    senkron_soyle(hazir_metin, tts)


def test_thread_fonk(tts, uyandirma_re, wake_kokler, kapat_kelimeleri, gule_metni):
    hazir_son_zaman = 0.0
    while not cikis_istegi.is_set():
        while konusuyor and not cikis_istegi.is_set():
            time.sleep(0.05)
        time.sleep(1.0)
        if test_kuyruk.empty():
            time.sleep(3.0)
            cikis_istegi.set()
            break
        try:
            metin = test_kuyruk.get_nowait()
        except queue.Empty:
            continue

        if HALUSINASYON_RE.search(metin):
            continue

        temiz_metin = re.sub(r"^[\s,.!?:-]+", "", metin)
        kalan = uyandirma_bul(temiz_metin, uyandirma_re, wake_kokler)
        if kalan is not None:
            if not kalan:
                log_yaz("Uyandirildi, 8 sn dinliyor")
                hazir_son_zaman = time.time() + 8.0
            else:
                hazir_son_zaman = 0.0
                komut_isle(kalan, tts, kapat_kelimeleri, gule_metni)
        else:
            if time.time() < hazir_son_zaman:
                hazir_son_zaman = 0.0
                komut_isle(metin.strip(), tts, kapat_kelimeleri, gule_metni)


def mikrofon_thread_fonk(stt, tts, dil, asistan_adi, uyandirma_re, wake_kokler, kapat_kelimeleri, gule_metni):
    global konusuyor
    taban = 0.001
    kaydediyor = False
    kayit_bloklari = []
    on_tampon = collections.deque(maxlen=ON_TAMPON_BOYUT)
    sessiz_sayisi = 0
    hazir_son_zaman = 0.0

    with giris_akisi_ac(mik_geri_cagri):
        while not cikis_istegi.is_set():
            if konusuyor:
                while not mic_kuyruk.empty():
                    try:
                        mic_kuyruk.get_nowait()
                    except queue.Empty:
                        break
                kaydediyor = False
                kayit_bloklari.clear()
                on_tampon.clear()
                sessiz_sayisi = 0
                time.sleep(0.01)
                continue

            try:
                blok = mic_kuyruk.get(timeout=0.1)
            except queue.Empty:
                continue

            rms = float(np.sqrt(np.mean(blok ** 2)))
            esik = max(taban * 4.0, 0.004)

            if not kaydediyor:
                if rms > esik:
                    kaydediyor = True
                    kayit_bloklari = list(on_tampon)
                    kayit_bloklari.append(blok)
                    sessiz_sayisi = 0
                else:
                    on_tampon.append(blok)
                    taban = taban * 0.95 + rms * 0.05
            else:
                kayit_bloklari.append(blok)
                if rms > esik:
                    sessiz_sayisi = 0
                else:
                    sessiz_sayisi += 1

                bitir = False
                if sessiz_sayisi >= SESSILIK_LIMIT:
                    bitir = True
                elif len(kayit_bloklari) >= MAX_BLOK:
                    bitir = True

                if bitir:
                    kaydediyor = False
                    ses = np.concatenate(kayit_bloklari) if kayit_bloklari else np.zeros(0, dtype=np.float32)
                    kayit_bloklari = []
                    sessiz_sayisi = 0
                    on_tampon.clear()

                    if len(ses) < MIN_ORNEK:
                        continue

                    ses = normalize(ses)
                    try:
                        segments, _ = stt.transcribe(
                            ses,
                            language=dil,
                            beam_size=1,
                            vad_filter=True,
                            initial_prompt=f"{asistan_adi}, ",
                        )
                        metin = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.6 and s.avg_logprob > -1.0).strip()
                    except Exception as e:
                        log_yaz(f"Transkripsiyon hatasi: {e}")
                        continue

                    if not metin:
                        continue

                    if HALUSINASYON_RE.search(metin):
                        continue

                    temiz_metin = re.sub(r"^[\s,.!?:-]+", "", metin)
                    kalan = uyandirma_bul(temiz_metin, uyandirma_re, wake_kokler)

                    if kalan is not None:
                        if not kalan:
                            log_yaz("Uyandirildi, 8 sn dinliyor")
                            hazir_son_zaman = time.time() + 8.0
                            continue
                        else:
                            hazir_son_zaman = 0.0
                            komut_isle(kalan, tts, kapat_kelimeleri, gule_metni)
                    else:
                        if time.time() < hazir_son_zaman:
                            hazir_son_zaman = 0.0
                            komut_isle(metin.strip(), tts, kapat_kelimeleri, gule_metni)


def main():
    kurulum_modu = "--kurulum" in sys.argv
    ayarlar = ayar_oku()
    dil = ayarlar.get("dil", "tr")
    dil_verisi = dil_verisi_al(dil)

    if "SES_TEST_GIRDI" in os.environ:
        for p in os.environ["SES_TEST_GIRDI"].split("|"):
            p = p.strip()
            if p:
                test_kuyruk.put(p)

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

    atexit.register(temizle)
    try:
        signal.signal(signal.SIGTERM, lambda s, f: cikis_istegi.set())
    except Exception:
        pass
    try:
        signal.signal(signal.SIGINT, lambda s, f: cikis_istegi.set())
    except Exception:
        pass

    log_yaz("Baslatiliyor, modeller yukleniyor...")
    tts = TTSYonetici(ayarlar)
    stt = stt_olustur(dil, ayarlar.get("asistan_adi", "Nova"))

    log_yaz("Modeller hazir.")

    if kurulum_modu:
        kurulum_yap(stt, tts, ayarlar, dil_verisi)
        ayarlar = ayar_oku()
        dil_verisi = dil_verisi_al(ayarlar.get("dil", "tr"))

    asistan_adi = ayarlar.get("asistan_adi", "Nova")
    uyandirma_listesi = ayarlar.get("uyandirma", ["nova"])
    kapat_kelimeleri = dil_verisi.get("kapat_kelimeleri", ["kapat"])
    selam_metni = dil_verisi.get("selam", "Efendim")
    gule_metni = dil_verisi.get("gule", "Görüşürüz")

    uyandirma_re, wake_kokler = uyandirma_derle(uyandirma_listesi, asistan_adi)

    t_tts = threading.Thread(target=tts_thread_fonk, args=(tts,), daemon=True)
    t_tts.start()

    tts_kuyruk.put(selam_metni)

    t_sock = threading.Thread(target=socket_sunucu_fonk, daemon=True)
    t_sock.start()

    if "SES_TEST_GIRDI" in os.environ:
        t_dinle = threading.Thread(
            target=test_thread_fonk,
            args=(tts, uyandirma_re, wake_kokler, kapat_kelimeleri, gule_metni),
            daemon=True,
        )
    else:
        t_dinle = threading.Thread(
            target=mikrofon_thread_fonk,
            args=(stt, tts, dil, asistan_adi, uyandirma_re, wake_kokler, kapat_kelimeleri, gule_metni),
            daemon=True,
        )
    t_dinle.start()

    try:
        cikis_istegi.wait()
    except KeyboardInterrupt:
        pass
    finally:
        temizle()
        try:
            if OTURUM_FILE.exists():
                OTURUM_FILE.unlink()
        except Exception:
            pass
        log_yaz("Kapandi.")
        os._exit(0)


if __name__ == "__main__":
    main()
