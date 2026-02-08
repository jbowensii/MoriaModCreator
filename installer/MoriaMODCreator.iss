; Moria MOD Creator Installer Script
; Created with Inno Setup 6.7

#define MyAppName "Moria MOD Creator"
#define MyAppVersion "0.6"
#define MyAppPublisher "John B Owens II"
#define MyAppURL "https://github.com/jbowensii/MoriaModCreator"
#define MyAppExeName "MoriaMODCreator.exe"

[Setup]
; Application info
AppId={{7A9C3E2B-4D5F-6A8B-9C0D-1E2F3A4B5C6D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\release
OutputBaseFilename=MoriaMODCreator_Setup_v{#MyAppVersion}
SetupIconFile=..\assets\icons\application icons\app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Signing (uncomment after testing)
; SignTool=ssl /d $q{#MyAppName}$q /du $q{#MyAppURL}$q $f

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main executable
Source: "..\release\MoriaMODCreator.exe"; DestDir: "{app}"; Flags: ignoreversion

; Data files - extracted to %APPDATA%\MoriaMODCreator
Source: "..\release\Definitions.zip"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall
Source: "..\release\mymodfiles.zip"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall
Source: "..\release\NewObjects.zip"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall
Source: "..\release\utilities.zip"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall
Source: "..\release\Constructions.zip"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall skipifsourcedoesntexist

[Dirs]
; Create AppData directory structure
Name: "{userappdata}\MoriaMODCreator"
Name: "{userappdata}\MoriaMODCreator\Constructions"
Name: "{userappdata}\MoriaMODCreator\Definitions"
Name: "{userappdata}\MoriaMODCreator\mymodfiles"
Name: "{userappdata}\MoriaMODCreator\output"
Name: "{userappdata}\MoriaMODCreator\output\jsondata"
Name: "{userappdata}\MoriaMODCreator\output\retoc"
Name: "{userappdata}\MoriaMODCreator\utilities"
Name: "{userappdata}\MoriaMODCreator\New Objects"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Extract zip files to AppData (runs before launching app)
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path '{tmp}\Definitions.zip' -DestinationPath '{userappdata}\MoriaMODCreator\Definitions' -Force"""; Flags: runhidden waituntilterminated; StatusMsg: "Extracting definitions..."
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path '{tmp}\mymodfiles.zip' -DestinationPath '{userappdata}\MoriaMODCreator\mymodfiles' -Force"""; Flags: runhidden waituntilterminated; StatusMsg: "Extracting mod templates..."
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path '{tmp}\NewObjects.zip' -DestinationPath '{userappdata}\MoriaMODCreator\New Objects' -Force"""; Flags: runhidden waituntilterminated; StatusMsg: "Extracting new objects..."
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path '{tmp}\utilities.zip' -DestinationPath '{userappdata}\MoriaMODCreator\utilities' -Force"""; Flags: runhidden waituntilterminated; StatusMsg: "Extracting utilities..."
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""if (Test-Path '{tmp}\Constructions.zip') {{ Expand-Archive -Path '{tmp}\Constructions.zip' -DestinationPath '{userappdata}\MoriaMODCreator\Constructions' -Force }}"""; Flags: runhidden waituntilterminated; StatusMsg: "Extracting constructions..."
; Launch application
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Optional: Check for Moria game installation
function InitializeSetup(): Boolean;
begin
  Result := True;
  // Could add check for game installation here if needed
end;
