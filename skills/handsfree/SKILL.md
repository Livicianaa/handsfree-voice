---
name: handsfree
description: Hands-free voice mode for Claude Code (wake word + spoken replies, 9 languages). Use for "/handsfree", "/handsfree setup", "/handsfree settings", "turn voice mode on/off", "voice settings", "volume", or when voice mode is not set up yet.
---

Paths: `${CLAUDE_PLUGIN_ROOT}/scripts/`. Run commands with Bash. On Windows use `python` instead of `python3`. Reply in the user's language.

Pick the branch from the argument. Arguments work in English or Turkish:

| Argument | Branch |
|---|---|
| `setup`, `install`, `kurulum` | Setup |
| `settings`, `control`, `kontrol`, `ayar` | Settings |
| none, `on`, `off`, `ac`, `kapat` | Toggle |

If `~/.config/${SES_AD:-handsfree-voice}/ayar.json` does not exist, run Setup whatever the argument is.

## Setup

1. Ask with AskUserQuestion which language the user will speak: Turkish (tr), English (en), Spanish (es), French (fr), German (de), Portuguese (pt), Russian (ru), Arabic (ar), Hindi (hi). AskUserQuestion shows 4 options at a time; offer the 3 most likely plus "Other" and accept the rest by name.
2. Run `nvidia-smi`. If an NVIDIA GPU is present, ask for the engine:
   - Piper: light, runs on CPU, fixed voices per language
   - Chatterbox: higher quality and voice cloning, needs about 4.5 GB of GPU memory
   If Chatterbox, ask for a reference WAV path (10-30 s of clean speech). Say it must be the user's own voice or one they have permission to use. Without a GPU use Piper.
3. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kur.py" --lang <code> --engine <piper|chatterbox> [--reference <wav>]`. It takes a few minutes the first time.
4. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ses.py" setup`.
5. Tell the user in one sentence: the assistant will now ask out loud what to call it (say the name 3 times) and how to address them.

## Settings

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ayar.py" status` (JSON: ses_seviyesi, hiz, sessiz, sesler).
2. Ask with AskUserQuestion in one call, marking the current value with "(current)":
   - Volume: 50% (0.5), 75% (0.75), 100% (1.0), 130% (1.3)
   - Speed: slow (0.85), normal (1.0), fast (1.2), very fast (1.4)
   - Voice: up to 4 entries from `sesler`, label "speaker · quality". Skip if there is only one or the engine is chatterbox.
   - Reading: on, or silent (keeps listening, does not read replies)
3. Apply: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ayar.py" set ses_seviyesi=<x> hiz=<y> sessiz=<true|false>`. If the voice changed: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ayar.py" voice <key>` (downloads it if needed).
4. Confirm in one sentence. No restart needed; it applies from the next sentence. By voice: "<name>, volume up / volume down" changes volume by 20%.

## Toggle

Typing exactly `/handsfree` or `/ses` is handled by the hook before this skill runs. When asked in words:

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ses.py" status`.
2. If active: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ses.py" off`. Otherwise: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ses.py" on`.
3. Confirm in one sentence. When turning on, say models take about 20 seconds to load and sentences must start with the assistant's name.
