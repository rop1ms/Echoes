$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$icon = Join-Path $root 'app/icon.ico'
$assets = Join-Path $root 'app/assets'
& (Join-Path $PSScriptRoot 'launcher_native/build.ps1')
if($LASTEXITCODE -ne 0){throw 'Native launcher compilation failed'}
$pythonExecutable = (& py -c 'import sys; print(sys.executable)').Trim()
$savedBuildPath = $env:PATH
try {
    # Avoid bundling incompatible ICU/UCRT DLLs from unrelated tools on PATH.
    $env:PATH = "$(Split-Path $pythonExecutable);$env:SystemRoot\System32;$env:SystemRoot"
    & $pythonExecutable -m PyInstaller --noconfirm --clean --onefile --windowed --name 'ECHOES Launcher' --icon $icon --version-file "$PSScriptRoot/launcher_native/launcher_version.txt" --add-data "$icon;." --add-data "$assets/logo/echoes_mark.png;logo" --add-data "$assets/fonts/nick/UnifrakturMaguntia-Book*;fonts/nick" --add-data "$assets/fonts/inter/Inter-latin.ttf;fonts/inter" --add-data "$assets/fonts/inter/Inter-cyrillic.ttf;fonts/inter" --add-data "$assets/licenses/Inter-OFL.txt;fonts/inter" --add-binary "$root/tools/launcher_native/echoes_launcher.dll;." --paths launcher --paths app --hidden-import core --hidden-import release_sign --hidden-import Cryptodome.Signature.eddsa --hidden-import psutil --distpath . --workpath tools/launcher-build --specpath tools tools/launcher_native/host.py
    if ($LASTEXITCODE -ne 0) { throw 'Launcher build failed' }
    $hash = (Get-FileHash -LiteralPath (Join-Path $root 'ECHOES Launcher.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath (Join-Path $root 'setup/launcher.sha256') -Value $hash -Encoding ASCII
} finally { $env:PATH = $savedBuildPath }
