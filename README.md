# handsfree-voice

Hands-free voice mode for [Claude Code](https://claude.com/claude-code). Not affiliated with Anthropic. Different from Claude Code's built-in `/voice` (hold-to-talk dictation): this one listens for a wake word, needs no key press, and speaks the reply back. Give your assistant a name, say it, and keep talking: the sentence goes to Claude as a normal prompt, and the reply is read back to you. Everything still shows up in the terminal as usual.

Runs locally. Speech recognition is [faster-whisper](https://github.com/SYSTRAN/faster-whisper), speech is [Piper](https://github.com/rhasspy/piper) (light, CPU) or [Chatterbox](https://github.com/resemble-ai/chatterbox) (higher quality, voice cloning, NVIDIA GPU).

## How it works

- `/handsfree` (or `/ses` in Turkish) turns voice mode on. The assistant greets you.
- `<Name>, check the tests` sends "check the tests" to Claude with Enter.
- Saying only `<Name>` makes it wait 8 seconds; the next sentence is sent.
- Anything that does not start with the name is ignored.
- Claude answers fully in the terminal. Only the last line, `Sesli: ...` (1-2 short sentences), is spoken.

## Requirements

- Python 3.10+ ([uv](https://github.com/astral-sh/uv) is used if present), a microphone and speakers
- Optional: NVIDIA GPU. Recognition then uses `large-v3-turbo`; Chatterbox needs it. If the GPU is missing, busy or out of memory, recognition falls back to the CPU (`small` model) automatically.

**Linux:** PipeWire or PulseAudio, and one way to type into the terminal: kitty remote control, tmux, `wtype` (Wayland) or `xdotool` (X11). Runs as a systemd user service when available.

**Windows (beta):** Python from python.org on PATH. The terminal window that is in front when you type `/handsfree` is remembered; recognized sentences are typed into it with the Windows keyboard API (it is brought to the front first). Uses the default audio devices. Not yet tested on real Windows machines, reports welcome.

macOS is not supported yet.

For kitty, add this to `kitty.conf` and restart kitty:

```
allow_remote_control socket-only
listen_on unix:@kitty-{kitty_pid}
```

## Install

In Claude Code:

```
/plugin install handsfree-voice --marketplace Livicianaa/handsfree-voice
```

On older versions:

```
/plugin marketplace add Livicianaa/handsfree-voice
/plugin install handsfree-voice@handsfree-voice
```

For local development: `claude --plugin-dir /path/to/handsfree-voice`. Then run:

```
/handsfree setup
```

(`/ses kurulum` in Turkish.)

Claude asks for your language (tr, en, es, fr, de, pt, ru, ar, hi) and, if you have a GPU, which voice engine to use. It downloads the models, then the assistant asks out loud:

1. What do you want to call me? Say the name three times; the spellings Whisper produces are saved as wake words. If the name is hard to recognize, you are asked for another one.
2. What should I call you?

Settings are stored in `~/.config/handsfree-voice/ayar.json` (Windows: `%APPDATA%\handsfree-voice`), models and the virtual environment in `~/.local/share/handsfree-voice/` (Windows: `%LOCALAPPDATA%\handsfree-voice`).

## Voice controls

`/handsfree settings` (or `/ses kontrol`) opens a picker (like choosing a model):

- **Volume:** 50% / 75% / 100% / 130%
- **Speed:** slow / normal / fast / very fast
- **Voice:** every Piper voice for your language, with speaker and quality (x_low, low, medium, high). Missing voices are downloaded on selection.
- **Reading:** on, or silent (still listens, does not read replies)

Changes apply from the next sentence, no restart. By voice: `<Name>, volume down` / `<Name>, volume up` (Turkish: `sesi kıs` / `sesi aç`) changes volume by 20%. Settings can also be changed with `scripts/ayar.py set ...`.

Commands and arguments work in English and Turkish: `/handsfree` = `/ses`, `setup` = `kurulum`, `settings` = `kontrol`. Speech recognition uses the language picked at setup; to switch languages run setup again.

## Turning it off

- Say `<Name>, kapat` (or the close words for your language, e.g. `<Name>, turn off`)
- Type `/handsfree` again
- Or run `python3 scripts/ses.py off`

## Privacy

- Audio never leaves your machine. Only sentences that start with the wake word are typed into Claude Code.
- Heard speech is not stored. The log (`$XDG_RUNTIME_DIR/handsfree-voice/log` on Linux, `%LOCALAPPDATA%\handsfree-voice\run\log` on Windows) keeps only sent commands and errors.

## Voice cloning

Chatterbox can clone a voice from a short reference recording (`--referans file.wav`). Use only your own voice or a voice you have explicit permission to use.

## Türkçe

Claude Code için eller serbest sesli mod. Asistana bir isim ver, o isimle başlayan cümlen Claude'a normal mesaj olarak gider, cevabın son "Sesli:" satırı sesli okunur. Terminalde her şey her zamanki gibi görünür.

- Yükleme: Claude Code içinde `/plugin install handsfree-voice --marketplace Livicianaa/handsfree-voice`.
- Kurulum: `/ses kurulum`. Dil ve ses motoru seçilir, modeller indirilir, sonra asistan sesli olarak "Bana ne diye seslenmek istersin?" ve "Sana ne diye hitap edeyim?" diye sorar.
- Aç/kapat: `/ses`, ya da sesle "<İsim> kapat".
- Ses ayarları: `/ses kontrol` (ses seviyesi, hız, konuşmacı/kalite, sessiz okuma). Sesle: "<İsim> sesi kıs" / "<İsim> sesi aç".
- Duyulan konuşmalar kaydedilmez; sadece isimle başlayan cümleler gönderilir.
- Ses klonlamada sadece kendi sesini ya da izinli bir sesi kullan.

---

Created by Liviciana · [Codemisk](https://codemisk.com.tr/) · [GitHub](https://github.com/Livicianaa)
