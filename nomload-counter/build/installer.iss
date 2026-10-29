; Inno Setup script for NomLoad Counter  (Inno Setup 6: https://jrsoftware.org/isinfo.php)
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build\installer.iss
#define MyAppName "NomLoad Counter"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Devnom"
#define MyAppExeName "NomLoad.exe"

[Setup]
AppId={{6E0C7A52-3B7E-4D47-9A55-4E0A1D2C9B11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Devnom\NomLoad Counter
DefaultGroupName=Devnom\NomLoad Counter
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=NomLoadCounter_Setup_{#MyAppVersion}
SetupIconFile=..\nomload\assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Start NomLoad when Windows starts (recommended for the gate PC)"; GroupDescription: "Startup:"; Flags: unchecked

[Dirs]
; shared data folder (database, evidence, models) writable by every Windows user of this PC
Name: "{commonappdata}\Devnom\NomLoad"; Permissions: users-modify; Flags: uninsneveruninstall

[Files]
Source: "..\dist\NomLoad\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\NomLoad data folder"; Filename: "{commonappdata}\Devnom\NomLoad"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; the data folder (database + evidence) is intentionally kept on uninstall
Type: filesandordirs; Name: "{app}\__pycache__"
