# Bangla Voice Commander — বাংলা ভয়েস কমান্ডার

Hands-free Windows control by speaking Bangla (and English). **Everything runs locally**: speech recognition
(faster-whisper), command understanding (deterministic parser), automation and Bangla voice feedback
(sherpa-onnx). No cloud, no API key, no subscription.

> **Honest status — please read [docs/STATUS.md](docs/STATUS.md).** The source is complete and its logic is
> unit-tested, but the Windows installer has to be built on Windows (GitHub Actions workflow included), and the
> audio/Windows/UI parts have not yet been run by me on real hardware.

## 1. Get the installer

### Option A — GitHub Actions (no tools needed on your PC)
1. Create a GitHub repository and upload this folder (or `git push` it).
2. **Actions → "Build Windows installer" → Run workflow** (choose Whisper size; `small` is the default).
3. After ~20–40 min download the artifact **BanglaVoiceCommander-Windows**: it contains
   `BanglaVoiceCommander_Setup.exe`, `BanglaVoiceCommander_Portable.zip`, `SHA256.txt` and the self-test reports.

The workflow fails (no artifact) if any of these fail: unit tests, offline self-test **with outbound network
blocked by a firewall rule**, silent install → self-test of the installed app → silent uninstall.

### Option B — build locally on Windows 10/11
Install Python 3.11 (x64) and [Inno Setup 6](https://jrsoftware.org/isinfo.php), then in PowerShell:
```powershell
.\build_windows.ps1            # or:  .\build_windows.ps1 -Whisper medium
```
Output in `release\`. Internet is needed **only for this build step** (downloading the models).

## 2. Install and use
1. Run `BanglaVoiceCommander_Setup.exe` (desktop + Start-menu shortcuts, uninstaller included).
   Windows SmartScreen may warn because the installer is not code-signed → *More info → Run anyway*.
2. Allow microphone access: Windows **Settings → Privacy & security → Microphone**.
3. Launch from the desktop, press **🎤 শোনা শুরু করো**. The first start loads the model (a few seconds).
4. Try: “ফেসবুক খোলো”, “নিচে স্ক্রল করো”, “স্ক্রল বন্ধ করো”, “নতুন ট্যাব খোলো”, “থামো”.
   Full list: **সাহায্য** page inside the app. Type-to-test box on the dashboard works without a microphone.

**Portable:** unzip `BanglaVoiceCommander_Portable.zip` anywhere (USB works). The file `portable.flag` keeps all
settings/history inside the folder. Delete `portable.flag` to use `%APPDATA%` instead.

**Emergency stop:** say *থামো / বন্ধ করো / Stop*, click ⛔, press **Ctrl+Alt+Q**, or slam the mouse into a screen corner.
It stops scrolling, releases drags, silences speech, cancels pending confirmations and **aborts a scheduled shutdown**.

## 3. Safety rules (built in)
Shutdown, restart, delete and send **always** ask “হ্যাঁ/না” first (15 s timeout, voice or button). Shutdown has an extra
15-second window you can cancel with “শাটডাউন বাতিল করো”. Duplicate clicks are suppressed. Failures are spoken and shown,
never reported as success. Custom commands cannot run sensitive actions. Audio is never saved; history stores text only
and can be disabled/cleared (Settings → Privacy).

## 4. Offline details → [docs/OFFLINE_MODELS.md](docs/OFFLINE_MODELS.md)
## 5. What is tested / unsupported → [docs/STATUS.md](docs/STATUS.md)

## 6. Custom commands
**কাস্টম কমান্ড** page: name + trigger phrases + steps (open app, open site, hotkey, type, wait, say, run another voice
command). A sample “আমার কাজ শুরু করো” (Chrome → Facebook → YouTube) is created on first run.

## 7. Developer notes
```
bvc/nlp        normaliser, intents, lexicon, parser (deterministic, no AI executes anything)
bvc/actions    mouse, keyboard, browser, facebook, system, uia (UI Automation)
bvc/speech     mic + VAD (webrtcvad / energy), offline Whisper recogniser
bvc/tts.py     offline Bangla TTS (sherpa-onnx MMS) with Windows SAPI fallback
bvc/engine.py  dispatch, confirmation, emergency stop, custom commands     bvc/ui   PySide6 UI
python -m bvc.cli --dry "নিচে স্ক্রল করো"     # test any command without a mic or Windows
python -m unittest discover -s tests
```
