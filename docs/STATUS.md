# Verification status (be sceptical of anything marked ✔ only if you did not see the evidence)

## ✔ Verified by automated tests (in a Linux sandbox, dry-run mode, 24 tests)
* Bangla/English/Banglish command parsing, spelling variants, numbers, parameters (search, type, click-by-name/number, volume).
* Engine: confirmation flow (shutdown/restart/delete/send), emergency stop cancels continuous scroll + scheduled shutdown,
  sleep mode, wake word, duplicate-click suppression, numbered-label flow, custom macros (incl. refusing sensitive steps),
  history on/off, honest failure reporting.
* Source contains no online speech/AI/TTS client code; Whisper is loaded local-only; defaults are offline.

## ✘ NOT yet verified (needs Windows + hardware — the CI workflow checks the first four automatically)
1. Frozen-app start-up, PyInstaller hidden-import completeness (may need small `spec` tweaks on first CI run).
2. Offline Whisper load + **Bangla recognition accuracy** (CI runs a synthetic TTS→STT→command round-trip, but real
   human speech with your microphone/accent is the real test).
3. Offline Bangla TTS: the source repo `csukuangfj/vits-mms-ben` was **not directly confirmed by me** (my tools could not open it); the pattern is confirmed from sherpa-onnx's own code. `fetch_models.py` now fails the build if the repo/files are wrong or the model lacks Bangla tokens, and tries a real synthesis. Audio quality is untested.
4. Silent install / uninstall, shortcuts.
5. Microphone capture + VAD, real latency on your CPU.
6. Mouse/keyboard/scroll, browser shortcuts, UI Automation click-by-name/numbered labels, volume (pycaw), brightness,
   Facebook J/K/L shortcuts and button lookup, global hotkey, overlay alignment on multi-monitor / mixed-DPI setups.
7. The PySide6 UI (written but never rendered).
8. Disconnected-internet test on a real PC: the CI blocks the app's network access and checks it still loads and
   transcribes, but you should repeat this yourself by turning Wi-Fi off.

## Known limitations / unsupported
* Stock Whisper-small Bangla accuracy is modest; short commands are helped by prompt biasing + fuzzy matching but
  misrecognitions will happen. Use `medium` or a Bangla fine-tuned model for better results.
* Facebook changes its page often. Like/comment/video use accessible names (English + Bangla guesses; overridable in
  the `facebook_labels` setting) then Facebook's own shortcuts; shortcut fallbacks cannot confirm the result, and the app says
  when it used a fallback. Un-like never guesses.
* Chrome/Edge expose page controls to UI Automation only when accessibility is on (app launches them with
  `--force-renderer-accessibility` when you pick a browser in Settings; otherwise enable it at `chrome://accessibility`).
* Click-by-name/number works on the foreground window only; keyboard/mouse input into elevated (admin) windows is blocked by Windows.
* Brightness works only on laptop panels/monitors that support it. "Bangla voice" for SAPI requires a Bangla voice installed in Windows.
* No code signing → SmartScreen warning; some antivirus tools flag global-hotkey/automation programs.
* Installer ≈ 0.7 GB (models dominate). Portable build is a folder/zip, not a single .exe (a one-file exe would unpack 600 MB on every launch).
* 64-bit Windows 10/11 only.
