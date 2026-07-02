; Inno Setup script — wraps the PyInstaller onedir bundle (dist\Flumen) into a
; single per-user installer (no admin rights needed).
;
; Build the bundle first, then compile this:
;   python build.py                 (produces dist\Flumen + VERSION)
;   ISCC /DAppVersion=0.1.0 packaging\flumen.iss
; or in one step on Windows:
;   python build.py --installer
;
; Output: dist\Flumen-Setup-<version>.exe

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Flumen Workspace"
#define AppPublisher "Flumen Pipeline"
#define SourceDir "..\dist\Flumen"

[Setup]
; AppId must stay constant across versions so upgrades replace cleanly.
AppId={{8F3A2C10-9B4E-4D7A-AE21-2C5E9F0A77B1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
; Per-user install — no administrator prompt.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\Flumen
DefaultGroupName=Flumen
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Flumen-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Installer's own icon (relative to this .iss). Shortcuts inherit the icon
; embedded in Flumen-Workspace.exe by PyInstaller.
SetupIconFile=flumen.ico
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\Flumen-Workspace.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"

[InstallDelete]
; The app was renamed (Legami -> Flumen). Same AppId, so this upgrades an
; existing install in place — drop the old-name exes and shortcuts so nothing
; stale is left to launch.
Type: files; Name: "{app}\Legami-Workspace.exe"
Type: files; Name: "{app}\animpipe.exe"
Type: files; Name: "{userdesktop}\Legami Workspace.lnk"
Type: filesandordirs; Name: "{userprograms}\Legami"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; \
    Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{userprograms}\Flumen\Flumen Workspace"; Filename: "{app}\Flumen-Workspace.exe"
Name: "{userprograms}\Flumen\Uninstall Flumen"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Flumen Workspace"; Filename: "{app}\Flumen-Workspace.exe"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\Flumen-Workspace.exe"; Description: "Launch Flumen Workspace now"; \
    Flags: nowait postinstall skipifsilent
