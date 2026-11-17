# The release manifest covers the native player executable under setup/.
function Install-EchoesPlayer([string]$InstallDir) {
    $source = Join-Path $PSScriptRoot 'Echoes.exe'
    $target = Join-Path $InstallDir 'python\Echoes.exe'
    if (-not (Test-Path -LiteralPath $target -PathType Leaf) -or
        (Get-FileHash -LiteralPath $source).Hash -ne (Get-FileHash -LiteralPath $target).Hash) {
        Copy-EchoesExecutable $source $target
    }
    return $target
}

function Stop-EchoesRuntime([string]$InstallDir, [switch]$IncludeExternal) {
    $runtime = Join-Path ([IO.Path]::GetFullPath($InstallDir)) 'python'
    $targets = @('Echoes.exe', 'pythonw.exe', 'python.exe') | ForEach-Object { Join-Path $runtime $_ }
    $processes = @(Get-Process -Name Echoes, pythonw, python -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -in $targets })
    if ($IncludeExternal) {
        $main = Join-Path ([IO.Path]::GetFullPath($InstallDir)) 'app\main.py'
        $quotedMain = [regex]::Escape($main)
        $external = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.ExecutablePath -notin $targets -and $_.CommandLine -match "(?:^|[\s""])$quotedMain(?:[\s""]|$)" }
        $processes += @($external | ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
    }
    $processes | Stop-Process -Force -ErrorAction SilentlyContinue
    $processes | Wait-Process -Timeout 3 -ErrorAction SilentlyContinue
    return $processes.Count
}

function Update-EchoesShortcutDirectory($Shell, [string]$Folder, [string]$InstallDir, [switch]$AddLauncher) {
    $player = Join-Path $InstallDir 'python\Echoes.exe'
    $legacy = @((Join-Path $InstallDir 'python\pythonw.exe'), (Join-Path $InstallDir 'python\python.exe'))
    $launcher = Join-Path $InstallDir 'ECHOES Launcher.exe'
    $main = [regex]::Escape((Join-Path $InstallDir 'app\main.py'))
    $uninstall = [regex]::Escape((Join-Path $InstallDir 'uninstall.ps1'))
    $hasPlayer = $false
    foreach ($link in (Get-ChildItem -LiteralPath $Folder -Filter '*.lnk' -File -ErrorAction SilentlyContinue)) {
        $shortcut = $Shell.CreateShortcut($link.FullName)
        $legacyPlayerLink = $shortcut.TargetPath -in $legacy -and (
            $shortcut.Arguments -match "(?:^|[\s""])$main(?:[\s""]|$)" -or
            ($link.BaseName -eq 'ECHOES' -and -not $shortcut.Arguments))
        if ($shortcut.TargetPath -eq $player -or $legacyPlayerLink) {
            $shortcut.TargetPath = $player
            $shortcut.IconLocation = "$player,0"
            $hasPlayer = $true
        } elseif ($shortcut.TargetPath -eq $launcher) {
            $shortcut.IconLocation = "$launcher,0"
        } elseif ($shortcut.TargetPath -and
            (Split-Path -Leaf $shortcut.TargetPath) -in 'powershell.exe', 'pwsh.exe' -and
            $shortcut.Arguments -match "(?:^|[\s""])$uninstall(?:[\s""]|$)") {
            $shortcut.IconLocation = "$player,0"
        } else {
            continue
        }
        $shortcut.Save()
    }
    $launcherLink = Join-Path $Folder 'ECHOES Launcher.lnk'
    if ($AddLauncher -and $hasPlayer -and (Test-Path -LiteralPath $launcher) -and
        -not (Test-Path -LiteralPath $launcherLink)) {
        $shortcut = $Shell.CreateShortcut($launcherLink)
        $shortcut.TargetPath = $launcher
        $shortcut.WorkingDirectory = $InstallDir
        $shortcut.IconLocation = "$launcher,0"
        $shortcut.Description = 'Echoes Launcher'
        $shortcut.Save()
    }
}

function Update-EchoesWindowsShortcuts([string]$InstallDir) {
    $shell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath('Desktop')
    $programs = Join-Path ([Environment]::GetFolderPath('Programs')) 'ECHOES'
    $startup = [Environment]::GetFolderPath('Startup')
    $pinned = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'
    Update-EchoesShortcutDirectory $shell $desktop $InstallDir -AddLauncher
    Update-EchoesShortcutDirectory $shell $programs $InstallDir -AddLauncher
    Update-EchoesShortcutDirectory $shell $startup $InstallDir
    Update-EchoesShortcutDirectory $shell $pinned $InstallDir

    # Older versions also exposed autostart through an app-generated script.
    $vbs = Join-Path $startup 'NeonPlayer.vbs'
    if (Test-Path -LiteralPath $vbs -PathType Leaf) {
        $legacyPlayer = Join-Path $InstallDir 'python\pythonw.exe'
        $main = Join-Path $InstallDir 'app\main.py'
        $text = [IO.File]::ReadAllText($vbs)
        if ($text -match [regex]::Escape($main) -and $text -match [regex]::Escape($legacyPlayer)) {
            $text = $text.Replace($legacyPlayer, (Join-Path $InstallDir 'python\Echoes.exe'))
            [IO.File]::WriteAllText($vbs, $text, [Text.Encoding]::Unicode)
        }
    }
}
