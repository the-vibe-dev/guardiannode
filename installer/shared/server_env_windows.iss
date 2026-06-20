; Shared GuardianNode backend environment writer for Windows installers.

procedure WriteGuardianNodeServerEnv(
  const DataDir: String;
  const Tier: String;
  const TextModel: String;
  const VisionModel: String;
  const OllamaUrl: String
);
var
  EnvPath: String;
  EnvFile: TArrayOfString;
begin
  EnvPath := AddBackslash(DataDir) + 'server.env';
  SetArrayLength(EnvFile, 17);
  EnvFile[0] := 'GUARDIANNODE_BIND_HOST=127.0.0.1';
  EnvFile[1] := 'GUARDIANNODE_BIND_PORT=8787';
  EnvFile[2] := 'GUARDIANNODE_DATA_DIR=' + DataDir;
  EnvFile[3] := 'GUARDIANNODE_MDNS_ENABLED=false';
  EnvFile[4] := 'GUARDIANNODE_CLASSIFIER_TIER=' + Tier;
  EnvFile[5] := 'GUARDIANNODE_TEXT_MODEL=' + TextModel;
  EnvFile[6] := 'GUARDIANNODE_VISION_MODEL=' + VisionModel;
  EnvFile[7] := 'GUARDIANNODE_OLLAMA_URL=' + OllamaUrl;
  EnvFile[8] := 'GUARDIANNODE_TEXT_OLLAMA_URL=' + OllamaUrl;
  EnvFile[9] := 'GUARDIANNODE_VISION_OLLAMA_URL=' + OllamaUrl;
  EnvFile[10] := 'GUARDIANNODE_CLASSIFIER_TIMEOUT_SECONDS=120';
  EnvFile[11] := 'GUARDIANNODE_VISION_NUM_CTX=8192';
  EnvFile[12] := 'GUARDIANNODE_VISION_MAX_IMAGE_EDGE=2560';
  EnvFile[13] := 'GUARDIANNODE_LOG_LEVEL=INFO';
  EnvFile[14] := 'GUARDIANNODE_ALLOWED_HOSTS=127.0.0.1,localhost';
  EnvFile[15] := 'GUARDIANNODE_HTTPS_ONLY_COOKIES=false';
  EnvFile[16] := 'GUARDIANNODE_RETENTION_CLEANUP_ENABLED=true';
  SaveStringsToFile(EnvPath, EnvFile, False);
end;
