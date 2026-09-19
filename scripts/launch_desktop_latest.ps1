param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$releaseDir = Join-Path $repoRoot 'src-tauri\target\release'
$desktopExe = Join-Path $releaseDir 'arkali-desktop.exe'
$builtHeadFile = Join-Path $releaseDir '.arkali-built-head'
$buildLockFile = Join-Path $releaseDir '.arkali-build.lock'
$tauriCli = Join-Path $repoRoot 'frontend\node_modules\.bin\tauri.cmd'

function Read-CurrentHead {
    $value = (& git -C $repoRoot rev-parse HEAD 2>$null | Select-Object -First 1)
    if ($LASTEXITCODE -ne 0 -or -not $value) { throw 'Git HEAD okunamadı; sürüm doğrulanamadı.' }
    return $value.Trim()
}

function Test-BuildInputsClean {
    $paths = @(
        'frontend/src', 'frontend/index.html', 'frontend/package.json',
        'frontend/package-lock.json', 'backend/arkali', 'src-tauri/src',
        'src-tauri/tauri.conf.json', 'src-tauri/Cargo.toml',
        'scripts/build_desktop_backend.py'
    )
    $changes = & git -C $repoRoot status --porcelain --untracked-files=normal -- $paths
    if ($LASTEXITCODE -ne 0) { throw 'Kaynak durumu doğrulanamadı.' }
    return -not [bool]$changes
}

try {
    $head = Read-CurrentHead
    $inputsClean = Test-BuildInputsClean
    $builtHead = if (Test-Path -LiteralPath $builtHeadFile) {
        (Get-Content -LiteralPath $builtHeadFile -Raw).Trim()
    } else { '' }
    $stale = -not (Test-Path -LiteralPath $desktopExe) -or $builtHead -ne $head

    if ($CheckOnly) {
        [pscustomobject]@{
            Head = $head
            BuiltHead = $builtHead
            BuildInputsClean = $inputsClean
            NeedsBuild = $stale
            ExecutableExists = Test-Path -LiteralPath $desktopExe
        } | ConvertTo-Json -Compress
        exit 0
    }

    if (-not $inputsClean) {
        throw 'Masaüstü kaynaklarında commit edilmemiş değişiklik var. Güncel sürüm güvenle doğrulanamadı.'
    }

    if ($stale) {
        $running = Get-Process -Name 'arkali-desktop' -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -eq $desktopExe }
        if ($running) {
            throw 'ARKALI zaten açık. Kaydedilmemiş çalışmalarınızı korumak için önce açık pencereyi kapatın, sonra simgeye yeniden tıklayın.'
        }
        if (-not (Test-Path -LiteralPath $tauriCli)) {
            throw 'Tauri derleme aracı bulunamadı. frontend bağımlılıkları kurulmalı.'
        }
        New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
        $lock = [System.IO.File]::Open($buildLockFile, 'OpenOrCreate', 'ReadWrite', 'None')
        try {
            Write-Host 'ARKALI güncelleniyor. İlk açılış birkaç dakika sürebilir...'
            Push-Location (Join-Path $repoRoot 'frontend')
            try {
                & $tauriCli build --no-bundle
                if ($LASTEXITCODE -ne 0) { throw 'Masaüstü derlemesi başarısız oldu; eski sürüm açılmadı.' }
            } finally { Pop-Location }
            if ((Read-CurrentHead) -ne $head -or -not (Test-BuildInputsClean)) {
                throw 'Derleme sırasında kaynak değişti; sonuç güncel olarak işaretlenmedi.'
            }
            if (-not (Test-Path -LiteralPath $desktopExe)) {
                throw 'Derleme tamamlandı ancak masaüstü çalıştırılabilir dosyası bulunamadı.'
            }
            Set-Content -LiteralPath $builtHeadFile -Value $head -NoNewline
        } finally { $lock.Dispose() }
    }

    Start-Process -FilePath $desktopExe -WorkingDirectory $releaseDir
} catch {
    $ErrorActionPreference = 'Continue'
    Write-Error $_.Exception.Message
    if (-not $CheckOnly) { Read-Host 'Pencereyi kapatmak için Enter tuşuna basın' | Out-Null }
    exit 1
}
