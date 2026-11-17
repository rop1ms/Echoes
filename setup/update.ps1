#Requires -Version 5.1
<#
    ECHOES — обновление уже установленного плеера.
    Находит, куда ECHOES был установлен (даже если в другую папку),
    закрывает его, заменяет файлы программы на новые и обновляет
    загрузчик yt-dlp. Плейлисты, библиотека и настройки не трогаются.
    -Auto — запуск из самого ECHOES (кнопка «Обновить», версия с GitHub): без вопросов,
    в конце ECHOES открывается сам.
#>
param([switch]$Auto, [switch]$NoLaunch, [string]$InstallDir = "")
$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try { $Host.UI.RawUI.WindowTitle = 'ECHOES — обновление' } catch {}
try { $Host.UI.RawUI.BackgroundColor = 'Black'; $Host.UI.RawUI.ForegroundColor = 'Gray' } catch {}
Clear-Host

$SRC_ROOT = Split-Path -Parent $PSScriptRoot
$SRC_APP = Join-Path $SRC_ROOT 'app'
. (Join-Path $PSScriptRoot 'launcher.ps1')
. (Join-Path $PSScriptRoot 'player.ps1')

function Ok([string]$t)   { Write-Host "      √ $t" -ForegroundColor Green }
function Info([string]$t) { Write-Host "      · $t" -ForegroundColor DarkGray }
function Warn([string]$t) { Write-Host "      ! $t" -ForegroundColor Yellow }
function Step([int]$n, [string]$t) { Write-Host ""; Write-Host "  [$n/5] $t" -ForegroundColor White }
function Done([int]$code) {
    Write-Host ''
    if ($Auto) { exit $code }
    Read-Host '  Нажмите Enter, чтобы закрыть' | Out-Null
    exit $code
}
function Fail([string]$msg) {
    Write-Host ''
    Write-Host "  × $msg" -ForegroundColor Red
    Done 1
}

Write-Host ''
Write-Host '   ███████╗ ██████╗██╗  ██╗ ██████╗ ███████╗███████╗' -ForegroundColor Yellow
Write-Host '   ██╔════╝██╔════╝██║  ██║██╔═══██╗██╔════╝██╔════╝' -ForegroundColor Yellow
Write-Host '   █████╗  ██║     ███████║██║   ██║█████╗  ███████╗' -ForegroundColor DarkYellow
Write-Host '   ███████╗╚██████╗██║  ██║╚██████╔╝███████╗███████║' -ForegroundColor DarkYellow
Write-Host '   ╚══════╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝' -ForegroundColor DarkGray
Write-Host '                     обновление' -ForegroundColor Gray

if (-not (Test-Path (Join-Path $SRC_APP 'main.py'))) {
    Fail 'Рядом нет папки app с новой версией. Распакуйте архив ЦЕЛИКОМ и запустите файл из распакованной папки.'
}

# ── 1. где установлен ECHOES ─────────────────────────────────────────────
Step 1 'Ищу установленный ECHOES'
if ($InstallDir) {
    $cands = @($InstallDir)
} else {
    $cands = New-Object System.Collections.Generic.List[string]
    try {
        $loc = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ECHOES' -ErrorAction Stop).InstallLocation
        if ($loc) { $cands.Add($loc) }
    } catch {}
    try {
        $ws = New-Object -ComObject WScript.Shell
        foreach ($lnk in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'ECHOES.lnk'),
                           (Join-Path ([Environment]::GetFolderPath('Programs')) 'ECHOES\ECHOES.lnk'))) {
            if (Test-Path $lnk) {
                $t = $ws.CreateShortcut($lnk).TargetPath            # ...\ECHOES\python\Echoes.exe (or legacy pythonw.exe)
                if ($t) { $cands.Add((Split-Path -Parent (Split-Path -Parent $t))) }
            }
        }
    } catch {}
    $cands.Add((Join-Path $env:LOCALAPPDATA 'Programs\ECHOES'))
}
$InstallDir = $null
foreach ($c in $cands) {
    if ($c -and (Test-Path (Join-Path $c 'app\main.py')) -and (Test-Path (Join-Path $c 'python\python.exe'))) {
        $InstallDir = $c; break
    }
}
if (-not $InstallDir) {
    Fail 'ECHOES не найден на этом компьютере. Сначала установите его: «УСТАНОВИТЬ ECHOES.bat».'
}
$APP = Join-Path $InstallDir 'app'
$PY  = Join-Path $InstallDir 'python\python.exe'
Ok "найден: $InstallDir"
$launcherSource = Get-EchoesLauncher $SRC_ROOT

$verFile = Join-Path $APP 'version.txt'
$oldVer = if (Test-Path $verFile) { (Get-Content $verFile -Raw).Trim() } else { 'старая' }
$newVerFile = Join-Path $SRC_APP 'version.txt'
$newVer = if (Test-Path $newVerFile) { (Get-Content $newVerFile -Raw).Trim() } else { 'новая' }
Info "версия: $oldVer  →  $newVer"

# ── 2. закрыть плеер ─────────────────────────────────────────────────────
Step 2 'Закрываю ECHOES, если он открыт'
if ($Auto -and -not $NoLaunch) { Start-Sleep -Seconds 3 }                    # ECHOES сам закрывается и сохраняет всё
$killed = Stop-EchoesRuntime $InstallDir -IncludeExternal
if ($killed) { Ok 'закрыт' } else { Ok 'не был запущен' }
$player = Install-EchoesPlayer $InstallDir

# ── 3. заменить файлы ────────────────────────────────────────────────────
Step 3 'Обновляю файлы программы'
# прошлая версия — в app.prev: если новая дважды не запустится, ECHOES сам вернёт её (app/boot_guard.py)
$curVer = ''; $newVer = ''
try { $curVer = (Get-Content -LiteralPath (Join-Path $APP 'version.txt') -Raw -ErrorAction Stop).Trim() } catch {}
try { $newVer = (Get-Content -LiteralPath (Join-Path $SRC_APP 'version.txt') -Raw -ErrorAction Stop).Trim() } catch {}
if ($curVer -and $curVer -ne $newVer -and (Test-Path -LiteralPath (Join-Path $APP 'main.py'))) {
    $prev = Join-Path $InstallDir 'app.prev'
    $null = & robocopy $APP $prev /MIR /XD __pycache__ /XF '*.old*' /R:1 /W:1 /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -lt 8) { Info "прошлая версия $curVer сохранена для отката" } else { Warn 'копия для отката не сохранилась' }
}
Get-ChildItem -Path $APP -Filter '*.dll.old*' -File -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }
$changed = 0; $same = 0; $failed = @()
Get-ChildItem -Path $SRC_APP -File | ForEach-Object {
    $dst = Join-Path $APP $_.Name
    $need = $true
    if (Test-Path $dst) {
        try {
            $need = (Get-FileHash $_.FullName -Algorithm MD5).Hash -ne (Get-FileHash $dst -Algorithm MD5).Hash
        } catch { $need = $true }
    }
    if ($need) {
        $ok = $false
        for ($i = 0; $i -lt 5 -and -not $ok; $i++) {
            try { Copy-Item $_.FullName -Destination $dst -Force; $ok = $true }
            catch { Start-Sleep -Milliseconds 600 }
        }
        if (-not $ok -and $_.Extension -eq '.dll' -and (Test-Path $dst)) {
            # занятую DLL (C++-ядро эффектов) Windows не даёт перезаписать, но даёт переименовать:
            # старая уходит в сторону и удаляется при следующем обновлении
            try {
                Rename-Item $dst ($_.Name + '.old' + (Get-Random)) -Force
                Copy-Item $_.FullName -Destination $dst -Force
                $ok = $true
            } catch {}
        }
        if ($ok) { $changed++; Info "обновлён $($_.Name)" } else { $failed += $_.Name }
    } else { $same++ }
}
foreach ($assetFolder in @('assets', 'discord_assets', 'dsl_themes', 'montage_native', 'sounds')) {
    $assetSource = Join-Path $SRC_APP $assetFolder
    if (Test-Path -LiteralPath $assetSource) {
        $assetTarget = Join-Path $APP $assetFolder
        New-Item -ItemType Directory -Path $assetTarget -Force | Out-Null
        Get-ChildItem -LiteralPath $assetSource | Copy-Item -Destination $assetTarget -Recurse -Force
    }
}
Get-ChildItem -Path $APP -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
Remove-Item (Join-Path $APP '__pycache__') -Recurse -Force -ErrorAction SilentlyContinue
$un = Join-Path $PSScriptRoot 'uninstall.ps1'
if (Test-Path $un) { Copy-Item $un -Destination $InstallDir -Force -ErrorAction SilentlyContinue }
if ($failed.Count) {
    Fail "Не удалось заменить: $($failed -join ', '). Закройте ECHOES вручную (и в трее) и запустите обновление ещё раз."
}
Ok "обновлено файлов: $changed, без изменений: $same"

# ── 4. загрузчик и библиотеки ────────────────────────────────────────────
Step 4 'Обновляю загрузчик yt-dlp и поиск YouTube Music (1-2 минуты)'
$old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
$constraints = Join-Path $PSScriptRoot 'constraints.txt'           # проверенные версии библиотек
$cArgs = if (Test-Path -LiteralPath $constraints) { @('-c', $constraints) } else { @() }
& $PY -m pip install --upgrade --prefer-binary --no-compile --no-warn-script-location --disable-pip-version-check @cArgs `
      --timeout 60 --retries 3 yt-dlp ytmusicapi syncedlyrics requests mutagen Pillow sounddevice pycryptodomex websockets av `
      winrt-runtime winrt-Windows.Foundation winrt-Windows.Foundation.Collections winrt-Windows.Media `
      winrt-Windows.Media.Playback winrt-Windows.Storage winrt-Windows.Storage.Streams 2>&1 | ForEach-Object {
    $l = "$_"
    if ($l -match '^Successfully installed (.+)') { Info "обновлено: $($Matches[1])" }
}
$pipCode = $LASTEXITCODE
$ErrorActionPreference = $old

# C++-модуль интерфейса (echoes_ui.dll) собран под Qt 6.11.2 и на более старом Qt не загружается — тогда
# молча выключаются все ускорения интерфейса (низкий FPS, «тугие» кнопки). Раньше обновление PyQt6 не трогало.
$needQt = '6.11.2'
$old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
$qt = (& $PY -c "from PyQt6.QtCore import qVersion; print(qVersion())" 2>$null | Select-Object -Last 1)
$ErrorActionPreference = $old
$qtOld = $true
try { $qtOld = ([version]("$qt".Trim()) -lt [version]$needQt) } catch { $qtOld = $true }
if ($qtOld) {
    Info "Обновляю Qt интерфейса ($qt → $needQt+), это нужно для плавности (1-3 минуты)"
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $PY -m pip install --upgrade --prefer-binary --no-compile --no-warn-script-location --disable-pip-version-check @cArgs `
          --timeout 120 --retries 3 PyQt6 "PyQt6-Qt6>=$needQt" 2>&1 | ForEach-Object {
        $l = "$_"
        if ($l -match '^Successfully installed (.+)') { Info "обновлено: $($Matches[1])" }
    }
    $ErrorActionPreference = $old
}
if ($pipCode -eq 0) { Ok 'готово' } else { Warn 'часть библиотек не обновилась (нет интернета?) — плеер всё равно обновлён' }

Step 5 'Завершаю обновление'
if ($launcherSource) { Install-EchoesLauncher $launcherSource $InstallDir }
try { Update-EchoesWindowsShortcuts $InstallDir }
catch { Warn "Не удалось обновить ярлыки: $($_.Exception.Message)" }

# ── готово ───────────────────────────────────────────────────────────────
try {
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ECHOES'
    if ((Test-Path $key) -and (Get-ItemProperty -Path $key).InstallLocation -eq $InstallDir) {
        Set-ItemProperty -Path $key -Name DisplayVersion -Value $newVer -ErrorAction SilentlyContinue
        Set-ItemProperty -Path $key -Name DisplayIcon -Value "$player,0" -ErrorAction SilentlyContinue
    }
} catch {}
Write-Host ''
Write-Host '  ╔══════════════════════════════════════════════╗' -ForegroundColor Green
Write-Host "  ║   ECHOES ОБНОВЛЁН  ·  версия $($newVer.PadRight(16))║" -ForegroundColor Green
Write-Host '  ╚══════════════════════════════════════════════╝' -ForegroundColor Green
Write-Host ''
$go = if ($NoLaunch) { 'n' } elseif ($Auto) { '' } else { Read-Host '   Запустить ECHOES? [Enter — да / n — нет]' }
if ($go -notmatch '^(n|н|no|нет)$') {
    Start-Process -FilePath $player -ArgumentList "`"$(Join-Path $APP 'main.py')`"" -WorkingDirectory $APP
}
exit 0
