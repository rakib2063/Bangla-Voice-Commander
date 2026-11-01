# Offline models & dependencies

| Component | What | Where in the installed app | Licence | Size |
|---|---|---|---|---|
| Speech recognition | faster-whisper (CTranslate2, int8 on CPU), Systran conversion of OpenAI Whisper `small` | `models\whisper\small\` | MIT | ~460 MB |
| Voice activity | webrtcvad (or built-in energy VAD) + Silero VAD inside faster-whisper | in the program | BSD / MIT | tiny |
| Bangla TTS | sherpa-onnx runtime + Meta **MMS-TTS Bangla** (`vits-mms-ben`) | `models\tts\vits-mms-ben\` | **CC-BY-NC 4.0 (non-commercial)** | ~110 MB |
| Fallback TTS | Windows SAPI via pyttsx3 — only if you installed a Bangla voice in Windows | Windows | Windows | — |
| Command understanding | local deterministic parser | `bvc\nlp` | own code | — |

* The app **never downloads anything at run time**: Whisper is opened with `local_files_only=True`; there is no
  online STT/TTS/LLM code path (enforced by `tests/test_offline.py`). Models are fetched once by
  `tools/fetch_models.py` when *building* the installer.
* Other Whisper sizes: build with `-Whisper base|medium`, or copy any CTranslate2 Whisper folder to
  `models\whisper\<name>` (or `%APPDATA%\BanglaVoiceCommander\models\whisper\<name>`) and select it in Settings.
  A Bangla-fine-tuned model converted with `ct2-transformers-converter` can be used the same way and will likely
  recognise Bangla better than stock Whisper.
* `small` on a typical dual/quad-core laptop CPU: expect roughly 1–3 s from end of speech to action. `base` is
  faster but less accurate; `medium` is more accurate but needs ~2–4× longer on CPU.
* **Limits that remain online by nature:** opening Facebook/YouTube/Google or running a web search needs the
  internet for the *website itself* (the app only opens the browser). Voice recognition and control do not.
* **TTS licence:** MMS-TTS is non-commercial. For commercial redistribution swap in another sherpa-onnx VITS model.
