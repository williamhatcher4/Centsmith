; Inno Setup script for Credit Tracker
; Build with: iscc packaging\installer.iss
; Produces:  packaging\dist\CreditTracker-Setup-<version>.exe
;
; Expects the Tauri release build to already exist at:
;   desktop\src-tauri\target\release\credit-tracker.exe
;   desktop\src-tauri\target\release\resources\backend\
; (packaging\build.ps1 produces this.)

#define AppName        "Credit Tracker"
#define AppExeName     "credit-tracker.exe"
#define AppVersion     "0.1.0"
#define AppPublisher   "William Hatcher"
#define AppId          "{{B2E58F1F-2C61-4D7E-A4DB-9B6F0C1D8E54}"
#define ReleaseDir     "..\desktop\src-tauri\target\release"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=CreditTracker-Setup-{#AppVersion}
SetupIconFile=..\desktop\src-tauri\icons\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Tauri shell executable
Source: "{#ReleaseDir}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Backend sidecar bundle (PyInstaller one-folder output).
; Installed directly under {app}\backend\ because Tauri's resource_dir() on
; Windows resolves to the exe's parent directory (not a resources\ subdir).
Source: "{#ReleaseDir}\resources\backend\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Preserve %APPDATA%\CreditTracker\ by default — user data lives there.
; If you want a "remove data" prompt, add a [Code] section using
; MsgBox + DelTree on {userappdata}\CreditTracker.
Type: filesandordirs; Name: "{app}"
