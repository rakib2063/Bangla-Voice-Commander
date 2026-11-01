<#  Local build on Windows 10/11 (needs Python 3.11 x64 and Inno Setup 6; internet only for this build step).
    .\build_windows.ps1                 # whisper 'small'
    .\build_windows.ps1 -Whisper medium
    Output: release\BanglaVoiceCommander_Setup.exe  and  release\BanglaVoiceCommander_Portable.zip          #>
param([string]$Whisper = "small", [string]$Version = "1.0.0")
$ErrorActionPreference = "Stop"
python -m venv .venv-build
& .\.venv-build\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-build.txt
python -m unittest discover -s tests
python tools\make_icon.py
python tools\fetch_models.py --whisper $Whisper
pyinstaller BanglaVoiceCommander.spec --noconfirm --clean
Copy-Item -Recurse -Force models dist\BanglaVoiceCommander\models
# offline self-test of the frozen app
$report = "$PWD\release\selftest.json"; New-Item -ItemType Directory -Force release | Out-Null
$p = Start-Process dist\BanglaVoiceCommander\BanglaVoiceCommander.exe -ArgumentList "--selftest","--report",$report -Wait -PassThru
Get-Content $report
if ($p.ExitCode -ne 0) { throw "self-test failed" }
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
& $iscc "/DAppVersion=$Version" installer\BanglaVoiceCommander.iss
# portable zip
$port = "release\portable\BanglaVoiceCommander"; Remove-Item -Recurse -Force release\portable -ErrorAction SilentlyContinue
Copy-Item -Recurse dist\BanglaVoiceCommander $port; New-Item "$port\portable.flag" -ItemType File | Out-Null
Compress-Archive -Path $port -DestinationPath release\BanglaVoiceCommander_Portable.zip -Force
Get-FileHash release\*.exe, release\*.zip -Algorithm SHA256 | Format-Table
