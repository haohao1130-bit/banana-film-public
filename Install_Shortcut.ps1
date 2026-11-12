$ErrorActionPreference='Stop'
$root='F:\BANANA_FILM_5070_STUDIO'
$install=Join-Path $root 'Launcher'
if(-not (Test-Path -LiteralPath 'F:\' -PathType Container)){throw 'F: drive is missing; install aborted. No second C: data folder will be created.'}
$desktop=[Environment]::GetFolderPath('Desktop')
$windowsPowerShell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
New-Item -ItemType Directory -Path $install -Force | Out-Null
foreach($name in @('Bootstrap_BANANA_FILM_5070.ps1','Start_BANANA_FILM_5070.cmd')){
 $source=Join-Path $PSScriptRoot $name
 if(-not (Test-Path -LiteralPath $source -PathType Leaf) -and $name -eq 'Bootstrap_BANANA_FILM_5070.ps1'){
  $source=Join-Path $PSScriptRoot 'tools\bootstrap_film_v2_5070.ps1'
 }
 if(-not (Test-Path -LiteralPath $source -PathType Leaf)){throw "Installer file missing: $source"}
 $target=Join-Path $install $name
 if([System.IO.Path]::GetFullPath($source) -ine [System.IO.Path]::GetFullPath($target)){
  Copy-Item -LiteralPath $source -Destination $target -Force
 }
}
$script=Join-Path $install 'Bootstrap_BANANA_FILM_5070.ps1'
$shell=New-Object -ComObject WScript.Shell
$lnk=$shell.CreateShortcut((Join-Path $desktop 'BANANA FILM 5070 STUDIO.lnk'))
$lnk.TargetPath=$windowsPowerShell
$lnk.Arguments='-NoProfile -NoExit -ExecutionPolicy Bypass -File "'+$script+'"'
$lnk.WorkingDirectory=$install
$lnk.Description='BANANA FILM RTX5070; V4-style Git updates; reuse existing CU130 ComfyUI; F: uploads and movies'
$lnk.Save()
Write-Host ''
Write-Host 'BANANA FILM 5070 STUDIO - desktop shortcut installed.'
Write-Host "Shortcut: $(Join-Path $desktop 'BANANA FILM 5070 STUDIO.lnk')"
Write-Host "Launcher: $script"
Write-Host "App checkout on first launch: $(Join-Path $root 'App')"
Write-Host "Projects and exports: $(Join-Path $root 'Media')"
Write-Host 'Double-click the desktop shortcut to check updates and start the Studio.'
Write-Host 'Original BANANAMV, ComfyUI models, CUDA/Torch, projects and media were not modified.'
