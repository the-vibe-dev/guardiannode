// Shared fail-safe helpers for Windows upgrade and repair installs.

function GNServiceExists(Name: String): Boolean;
begin
  Result := RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\' + Name);
end;

function GNCopyIfPresent(SourcePath, DestPath: String): Boolean;
begin
  Result := True;
  if FileExists(SourcePath) then
    Result := FileCopy(SourcePath, DestPath, False);
end;

function GNCopyDirectoryIfPresent(SourcePath, DestPath: String): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if not DirExists(SourcePath) then
    Exit;
  if not ForceDirectories(DestPath) then begin
    Result := False;
    Exit;
  end;
  Exec(ExpandConstant('{sys}\robocopy.exe'),
    '"' + SourcePath + '" "' + DestPath + '" /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := ResultCode <= 7;
end;

function GNMirrorDirectory(SourcePath, DestPath: String): Boolean;
var
  ResultCode: Integer;
begin
  Result := DirExists(SourcePath) and ForceDirectories(DestPath);
  if not Result then
    Exit;
  Exec(ExpandConstant('{sys}\robocopy.exe'),
    '"' + SourcePath + '" "' + DestPath + '" /MIR /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := ResultCode <= 7;
end;

function GNMirrorDirectoryIfPresent(SourcePath, DestPath: String): Boolean;
begin
  if DirExists(SourcePath) then
    Result := GNMirrorDirectory(SourcePath, DestPath)
  else
    Result := True;
end;

function GNCreatePreUpgradeBackup(DataDir, AppDir: String; var BackupDir: String): Boolean;
var
  DataBackupDir: String;
begin
  BackupDir := AddBackslash(DataDir) + 'backups\installer-' +
    GetDateTimeString('yyyymmdd-hhnnss', '-', ':');
  DataBackupDir := AddBackslash(BackupDir) + 'programdata';
  if not ForceDirectories(DataBackupDir) then begin
    Result := False;
    Exit;
  end;

  Result :=
    GNCopyIfPresent(AddBackslash(DataDir) + 'guardiannode.db', AddBackslash(DataBackupDir) + 'guardiannode.db') and
    GNCopyIfPresent(AddBackslash(DataDir) + 'guardiannode.db-wal', AddBackslash(DataBackupDir) + 'guardiannode.db-wal') and
    GNCopyIfPresent(AddBackslash(DataDir) + 'guardiannode.db-shm', AddBackslash(DataBackupDir) + 'guardiannode.db-shm') and
    GNCopyIfPresent(AddBackslash(DataDir) + 'server.env', AddBackslash(DataBackupDir) + 'server.env') and
    GNCopyIfPresent(AddBackslash(DataDir) + 'agent.yaml', AddBackslash(DataBackupDir) + 'agent.yaml') and
    GNCopyDirectoryIfPresent(AddBackslash(DataDir) + 'keys', AddBackslash(DataBackupDir) + 'keys') and
    GNCopyDirectoryIfPresent(AddBackslash(DataDir) + 'Secure', AddBackslash(DataBackupDir) + 'Secure') and
    GNCopyDirectoryIfPresent(AddBackslash(DataDir) + 'AgentSecure', AddBackslash(DataBackupDir) + 'AgentSecure') and
    GNCopyDirectoryIfPresent(AppDir, AddBackslash(BackupDir) + 'application');
end;

function GNRestorePreUpgradeBackup(BackupDir, DataDir, AppDir: String): Boolean;
var
  DataBackupDir: String;
begin
  DataBackupDir := AddBackslash(BackupDir) + 'programdata';
  { Remove sidecars created by the failed candidate before restoring the exact
    pre-upgrade SQLite snapshot. }
  DeleteFile(AddBackslash(DataDir) + 'guardiannode.db-wal');
  DeleteFile(AddBackslash(DataDir) + 'guardiannode.db-shm');
  Result :=
    GNMirrorDirectory(AddBackslash(BackupDir) + 'application', AppDir) and
    GNCopyIfPresent(AddBackslash(DataBackupDir) + 'guardiannode.db', AddBackslash(DataDir) + 'guardiannode.db') and
    GNCopyIfPresent(AddBackslash(DataBackupDir) + 'guardiannode.db-wal', AddBackslash(DataDir) + 'guardiannode.db-wal') and
    GNCopyIfPresent(AddBackslash(DataBackupDir) + 'guardiannode.db-shm', AddBackslash(DataDir) + 'guardiannode.db-shm') and
    GNCopyIfPresent(AddBackslash(DataBackupDir) + 'server.env', AddBackslash(DataDir) + 'server.env') and
    GNCopyIfPresent(AddBackslash(DataBackupDir) + 'agent.yaml', AddBackslash(DataDir) + 'agent.yaml') and
    GNMirrorDirectoryIfPresent(AddBackslash(DataBackupDir) + 'keys', AddBackslash(DataDir) + 'keys') and
    GNMirrorDirectoryIfPresent(AddBackslash(DataBackupDir) + 'Secure', AddBackslash(DataDir) + 'Secure') and
    GNMirrorDirectoryIfPresent(AddBackslash(DataBackupDir) + 'AgentSecure', AddBackslash(DataDir) + 'AgentSecure');
end;
