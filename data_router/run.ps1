# Local dev runner. Reads the project root .env (single source of truth
# for the docker-compose stack), applies the same name aliases that
# docker-compose.yml uses for data_router, and runs `go run`.
#
# Why we re-implement compose's mapping here: when iterating outside
# docker we still want to honor the canonical env names that the rest
# of the stack agrees on. Adding a local .env at services/data_router/
# would split the source of truth and is rejected on purpose.

param(
    [string]$EnvFile = "..\..\..env"   # placeholder; real path computed below
)

$ErrorActionPreference = 'Stop'

$rootEnv = Resolve-Path (Join-Path $PSScriptRoot "..\..\.env") -ErrorAction SilentlyContinue
if (-not $rootEnv) {
    Write-Error "root .env not found at $(Join-Path $PSScriptRoot '..\..\.env')"
    exit 1
}

# 1. Load root .env. Same parsing rules docker-compose uses:
#    - skip blank lines and lines starting with '#'
#    - inline comments only after at least one whitespace char before '#'
#    - strip surrounding double-quotes if present
Get-Content $rootEnv | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith('#')) { return }
    $idx = $line.IndexOf('=')
    if ($idx -lt 1) { return }
    $name  = $line.Substring(0, $idx).Trim()
    $value = $line.Substring($idx + 1)
    # strip inline comment ' #...' or '\t#...' (whitespace+# only)
    $m = [regex]::Match($value, '\s#.*$')
    if ($m.Success) { $value = $value.Substring(0, $m.Index) }
    $value = $value.Trim()
    # strip surrounding quotes
    if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    if ([string]::IsNullOrEmpty([System.Environment]::GetEnvironmentVariable($name))) {
        [System.Environment]::SetEnvironmentVariable($name, $value)
    }
}

# 2. docker-compose-style aliases (compose maps these for data_router):
#    ORACLE_SERVICE       -> ORACLE_SERVICE_ALIAS
#    OCI_NAMESPACE        -> OS_NAMESPACE
#    OCI_BUCKET_NAME      -> OS_BUCKET
function alias-env([string]$src, [string]$dst) {
    if ([string]::IsNullOrEmpty([System.Environment]::GetEnvironmentVariable($dst))) {
        $v = [System.Environment]::GetEnvironmentVariable($src)
        if (-not [string]::IsNullOrEmpty($v)) {
            [System.Environment]::SetEnvironmentVariable($dst, $v)
        }
    }
}
alias-env 'ORACLE_SERVICE'   'ORACLE_SERVICE_ALIAS'
alias-env 'OCI_NAMESPACE'    'OS_NAMESPACE'
alias-env 'OCI_BUCKET_NAME'  'OS_BUCKET'

# 3. Local-dev storage handling.
#    Root .env defaults OS_AUTH_MODE=instance_principal (OCI VM only).
#    Outside the VM we must switch to config_file mode if ~/.oci/config
#    exists, or disable storage entirely. The compose stack uses its own
#    settings so it's unaffected.
if ([string]::IsNullOrEmpty([System.Environment]::GetEnvironmentVariable('OS_ENABLED'))) {
    if (Test-Path "$env:USERPROFILE\.oci\config") {
        [System.Environment]::SetEnvironmentVariable('OS_ENABLED', '1')
        [System.Environment]::SetEnvironmentVariable('OS_AUTH_MODE', 'config_file')
    } else {
        [System.Environment]::SetEnvironmentVariable('STORAGE_ENABLED', '0')
    }
}

# Wallet path is relative — root .env doesn't carry it (compose mounts at
# /app/wallet). Default to ./wallet_v2 from repo root.
if ([string]::IsNullOrEmpty([System.Environment]::GetEnvironmentVariable('ORACLE_WALLET_DIR'))) {
    [System.Environment]::SetEnvironmentVariable('ORACLE_WALLET_DIR', '..\..\wallet_v2')
}

$go = "C:\Program Files\Go\bin\go.exe"
if (-not (Test-Path $go)) { $go = "go" }

Set-Location $PSScriptRoot
& $go run ./cmd/data_router
