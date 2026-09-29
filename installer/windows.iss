#ifndef AppVersion
  #define AppVersion "0.1.1"
#endif
[Setup]
AppId={{7AD3A261-755D-4B4C-A52A-9E66DDE31447}
AppName=Ameblo Studio
AppVersion={#AppVersion}
AppPublisher=Ameblo Studio contributors
DefaultDirName={localappdata}\Programs\AmebloStudio
DefaultGroupName=Ameblo Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=AmebloStudio-Setup-{#AppVersion}-Windows-x64
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AmebloStudio.exe
CloseApplications=yes
RestartApplications=no
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\AmebloStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\Ameblo Studio"; Filename: "{app}\AmebloStudio.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\Ameblo Studio"; Filename: "{app}\AmebloStudio.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\AmebloStudio.exe"; Description: "Launch Ameblo Studio"; Flags: nowait postinstall skipifsilent
