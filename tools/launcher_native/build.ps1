param([string]$Qt='C:\Qt\6.11.2\msvc2022_64')
$ErrorActionPreference='Stop'
$here=$PSScriptRoot
$obj=Join-Path $env:TEMP 'echoes_launcher_native_build'
New-Item -ItemType Directory -Path $obj -Force | Out-Null
$vswhere="${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs=& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(-not $vs){throw 'MSVC Build Tools not found'}
$env:PATH=(Split-Path -Parent $vswhere)+';'+$env:PATH
cmd /c "`"$vs\VC\Auxiliary\Build\vcvars64.bat`" >nul 2>nul && set" | ForEach-Object {
    if($_ -match '^([^=]+)=(.*)$'){Set-Item -Path "env:$($matches[1])" -Value $matches[2]}
}
$out=Join-Path $here 'echoes_launcher.dll'
$inc=@("/I$Qt\include","/I$Qt\include\QtCore","/I$Qt\include\QtGui","/I$Qt\include\QtWidgets")
$libs=@("$Qt\lib\Qt6Core.lib","$Qt\lib\Qt6Gui.lib","$Qt\lib\Qt6Widgets.lib")
& cl.exe /nologo /std:c++17 /permissive- /Zc:__cplusplus /EHsc /O2 /MD /utf-8 /W3 /DNDEBUG /DQT_NO_DEBUG /DUNICODE /D_UNICODE /DNOMINMAX $inc (Join-Path $here 'launcher.cpp') /Fo"$obj\\" /LD /Fe"$out" /link /NOLOGO "/IMPLIB:$obj\echoes_launcher.lib" $libs
if($LASTEXITCODE -ne 0){throw 'Native launcher build failed'}

$root = Split-Path -Parent (Split-Path -Parent $here)
$player = Join-Path $root 'setup/Echoes.exe'
$resources = Join-Path $obj 'player.res'
& rc.exe /nologo /i (Join-Path $root 'app') /fo $resources (Join-Path $here 'player.rc')
if($LASTEXITCODE -ne 0){throw 'Player resources build failed'}
& cl.exe /nologo /std:c++17 /EHsc /O2 /MT /W3 /DUNICODE /D_UNICODE /DNOMINMAX (Join-Path $here 'player.cpp') $resources /Fo"$obj\\" /Fe"$player" /link /NOLOGO /SUBSYSTEM:WINDOWS user32.lib
if($LASTEXITCODE -ne 0){throw 'Native player build failed'}
Get-Item -LiteralPath $out, $player | Select-Object Name,Length
