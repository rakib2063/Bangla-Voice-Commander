; Inno Setup 6 script -> BanglaVoiceCommander_Setup.exe
#define AppName "Bangla Voice Commander"
#define AppExe  "BanglaVoiceCommander.exe"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{B3A1C2D4-7E55-4F0A-9A53-BD0C0DEC0DE1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Bangla Voice Commander
DefaultDirName={autopf}\BanglaVoiceCommander
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=BanglaVoiceCommander_Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
Compression=lzma2/fast
SolidCompression=no
WizardStyle=modern
LicenseFile=..\models\MODEL_LICENSES.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "..\dist\BanglaVoiceCommander\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; Verify offline recognition engine, models, TTS and microphone right after installing (no internet needed).
Filename: "{app}\{#AppExe}"; Parameters: "--selftest"; StatusMsg: "Verifying offline speech engine..."; Flags: runhidden waituntilterminated
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if MsgBox('Also delete your settings, custom commands and history?', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{userappdata}\BanglaVoiceCommander'), True, True, True);
end;
