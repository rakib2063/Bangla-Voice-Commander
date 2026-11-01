# PyInstaller spec - one-folder build (fast start-up; models are copied next to the exe afterwards).
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [("assets", "assets")], [], []
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "tokenizers", "av", "sherpa_onnx", "webrtcvad",
            "_sounddevice_data", "sounddevice", "uiautomation", "pycaw", "comtypes", "pyttsx3", "pyautogui",
            "pyscreeze", "pytweening", "pymsgbox", "pyperclip", "screen_brightness_control", "keyboard"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:                       # optional package missing -> skip, app degrades gracefully
        print("spec: skipping", pkg, e)
hiddenimports += ["pyttsx3.drivers", "pyttsx3.drivers.sapi5", "win32com.client"]

a = Analysis(["main.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=["matplotlib", "scipy", "torch", "IPython", "pytest", "PyQt5", "PyQt6", "PySide2"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="BanglaVoiceCommander", console=False,
          icon="assets/icon.ico", uac_admin=False)
coll = COLLECT(exe, a.binaries, a.datas, name="BanglaVoiceCommander", upx=False)
