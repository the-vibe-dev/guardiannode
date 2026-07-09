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

function GNCreatePreUpgradeBackup(DataDir: String): Boolean;
var
  BackupDir, KeysSource, KeysDest: String;
  ResultCode: Integer;
begin
  Result := True;
  if not FileExists(AddBackslash(DataDir) + 'guardiannode.db') then
    Exit;

  BackupDir := AddBackslash(DataDir) + 'backups\installer-' +
    GetDateTimeString('yyyymmdd-hhnnss', '-', ':');
  if not ForceDirectories(BackupDir) then begin
    Result := False;
    Exit;
  end;

  Result :=
    GNCopyIfPresent(AddBackslash(DataDir) + 'guardiannode.db', AddBackslash(BackupDir) + 'guardiannode.db') and
    GNCopyIfPresent(AddBackslash(DataDir) + 'guardiannode.db-wal', AddBackslash(BackupDir) + 'guardiannode.db-wal') and
    GNCopyIfPresent(AddBackslash(DataDir) + 'guardiannode.db-shm', AddBackslash(BackupDir) + 'guardiannode.db-shm') and
    GNCopyIfPresent(AddBackslash(DataDir) + 'server.env', AddBackslash(BackupDir) + 'server.env') and
    GNCopyIfPresent(AddBackslash(DataDir) + 'agent.yaml', AddBackslash(BackupDir) + 'agent.yaml');
  if not Result then
    Exit;

  KeysSource := AddBackslash(DataDir) + 'keys';
  if DirExists(KeysSource) then begin
    KeysDest := AddBackslash(BackupDir) + 'keys';
    ForceDirectories(KeysDest);
    Exec(ExpandConstant('{sys}\robocopy.exe'),
      '"' + KeysSource + '" "' + KeysDest + '" /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Result := ResultCode <= 7;
  end;
end;
