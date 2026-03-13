; Moria MOD Creator Installer Script
; Created with Inno Setup 6.7

#define MyAppName "Moria MOD Creator"
#define MyAppVersion "2.1.0"
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

; Signing (configure SignTool in Inno Setup IDE Tools > Configure Sign Tools)
; Add a sign tool named "ssl" with your certificate details
; Then uncomment the line below to enable automatic signing
; SignTool=ssl /d $q{#MyAppName}$q /du $q{#MyAppURL}$q $f

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main executable
Source: "..\release\MoriaMODCreator.exe"; DestDir: "{app}"; Flags: ignoreversion

; Data files - extracted to %APPDATA%\MoriaMODCreator during install
Source: "Definitions.zip"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall
Source: "prebuilt_modfiles.zip"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall
Source: "SecretsSource.zip"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall
Source: "NewObjects.zip"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall
Source: "changeconstructions.zip"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall
Source: "changesecrets.zip"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall
Source: "utilities.zip"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall

[Dirs]
; Create AppData directory structure
Name: "{userappdata}\MoriaMODCreator"
Name: "{userappdata}\MoriaMODCreator\cache"
Name: "{userappdata}\MoriaMODCreator\cache\constructions"
Name: "{userappdata}\MoriaMODCreator\cache\game"
Name: "{userappdata}\MoriaMODCreator\cache\secrets"
Name: "{userappdata}\MoriaMODCreator\changeconstructions"
Name: "{userappdata}\MoriaMODCreator\changesecrets"
Name: "{userappdata}\MoriaMODCreator\Definitions"
Name: "{userappdata}\MoriaMODCreator\mymodfiles"
Name: "{userappdata}\MoriaMODCreator\New Objects"
Name: "{userappdata}\MoriaMODCreator\prebuilt modfiles"
Name: "{userappdata}\MoriaMODCreator\output"
Name: "{userappdata}\MoriaMODCreator\output\jsondata"
Name: "{userappdata}\MoriaMODCreator\output\retoc"
Name: "{userappdata}\MoriaMODCreator\Secrets Source"
Name: "{userappdata}\MoriaMODCreator\utilities"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Extract zip files to AppData (runs before launching app)
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path '{tmp}\Definitions.zip' -DestinationPath '{userappdata}\MoriaMODCreator\Definitions' -Force"""; Flags: runhidden waituntilterminated; StatusMsg: "Extracting definitions..."
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path '{tmp}\prebuilt_modfiles.zip' -DestinationPath '{userappdata}\MoriaMODCreator\prebuilt modfiles' -Force"""; Flags: runhidden waituntilterminated; StatusMsg: "Extracting prebuilt mods..."
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path '{tmp}\SecretsSource.zip' -DestinationPath '{userappdata}\MoriaMODCreator\Secrets Source' -Force"""; Flags: runhidden waituntilterminated; StatusMsg: "Extracting secrets source..."
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path '{tmp}\NewObjects.zip' -DestinationPath '{userappdata}\MoriaMODCreator\New Objects' -Force"""; Flags: runhidden waituntilterminated; StatusMsg: "Extracting new objects..."
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path '{tmp}\changeconstructions.zip' -DestinationPath '{userappdata}\MoriaMODCreator\changeconstructions' -Force"""; Flags: runhidden waituntilterminated; StatusMsg: "Extracting constructions data..."
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path '{tmp}\changesecrets.zip' -DestinationPath '{userappdata}\MoriaMODCreator\changesecrets' -Force"""; Flags: runhidden waituntilterminated; StatusMsg: "Extracting secrets data..."
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Expand-Archive -Path '{tmp}\utilities.zip' -DestinationPath '{userappdata}\MoriaMODCreator\utilities' -Force"""; Flags: runhidden waituntilterminated; StatusMsg: "Extracting utilities..."
; Launch application
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Optional: Check for Moria game installation
function InitializeSetup(): Boolean;
begin
  Result := True;
  // Could add check for game installation here if needed
end;
