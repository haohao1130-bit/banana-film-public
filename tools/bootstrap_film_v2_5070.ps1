# BANANA FILM 5070 STUDIO - clone/update only this public experimental branch.
# Portable: can run from extracted launcher package or the repository's tools folder.
param(
 [string]$InstallRoot='F:\BANANA_FILM_5070_STUDIO',
 [string]$ComfyUrl='http://127.0.0.1:8000',
 [string]$ComfyBase='',
 [string]$ComfySource='',
 [string]$ComfyInputDir='',
 [string]$PythonPath='',
 [int]$Port=8193,
 [switch]$NoAutoComfy,
 [switch]$NoBrowser,
 [switch]$FromCheckout
)
$ErrorActionPreference='Stop'
$repoUrl='https://github.com/haohao1130-bit/banana-film-public.git'
$branch='film-v2-rtx5070-fdrive'
if(-not (Test-Path -LiteralPath 'F:\' -PathType Container)){throw 'F: drive missing; mount F: before starting.'}
if(-not $InstallRoot.StartsWith('F:\',[StringComparison]::OrdinalIgnoreCase)){
 throw 'InstallRoot must be on F:; this launcher is an F-drive edition.'
}
if(-not (Get-Command git -ErrorAction SilentlyContinue)){throw 'Git for Windows is required: https://git-scm.com/download/win'}
$repo=Join-Path $InstallRoot 'App'
$launcher=Join-Path $InstallRoot 'Launcher'
$media=Join-Path $InstallRoot 'Media'
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
if(-not (Test-Path -LiteralPath $repo)){
 Write-Host 'Cloning BANANA FILM V2 RTX5070 branch from PUBLIC GitHub...'
 & git -c credential.helper= clone --depth 1 --single-branch --branch $branch $repoUrl $repo
 if($LASTEXITCODE -ne 0){throw 'Git clone failed. Check network and Git for Windows.'}
}else{
 if(-not (Test-Path -LiteralPath (Join-Path $repo '.git'))){throw "Install path $repo exists but is not a Git repository. Cannot overwrite it."}
 $remote=(& git -C $repo remote get-url origin)
 if($LASTEXITCODE -ne 0 -or $remote -notmatch '^https://github\.com/haohao1130-bit/banana-film-public(\.git)?$'){
  throw "Unknown repository at $repo. Refusing to change it."
 }
 $actual=(& git -C $repo branch --show-current)
 if($actual -ne $branch){throw "Different branch in $repo ($actual). Refusing checkout or reset."}
 if(-not $FromCheckout){
  & git -C $repo diff --quiet
  $trackedDirty=($LASTEXITCODE -ne 0)
  & git -C $repo diff --cached --quiet
  $stagedDirty=($LASTEXITCODE -ne 0)
  if($trackedDirty -or $stagedDirty){
   Write-Warning 'Tracked local edits exist. Skipping update; running unchanged local version.'
  }else{
   $before=(& git -C $repo rev-parse --short=9 HEAD)
   Write-Host 'Checking GitHub updates (fast-forward only, no reset)...'
   # PowerShell 5.1 may promote native stderr to an exception under Stop.
   # A network/update failure should never make the existing working build unusable.
   $pullOK=$false
   try{
    & git -C $repo pull --ff-only origin $branch
    $pullOK=($LASTEXITCODE -eq 0)
   }catch{
    Write-Warning ('Git update command failed: ' + $_.Exception.Message)
   }
   if(-not $pullOK){
    Write-Warning 'GitHub update unavailable or non-fast-forward. Keeping existing local version.'
   }else{
    $after=(& git -C $repo rev-parse --short=9 HEAD)
    if($before -ne $after){Write-Host "Updated: $before -> $after"}
    else{Write-Host "Already up to date: $after"}
   }
  }
 }
}
$head=(& git -C $repo log -1 --format=%h)
Write-Host "BANANA FILM 5070 STUDIO revision: $head"
$service=Join-Path $repo 'tools\start_film_v2_5070.ps1'
if(-not (Test-Path -LiteralPath $service -PathType Leaf)){throw '5070 service launcher missing from checked-out branch.'}
$canonicalBootstrap=Join-Path $repo 'tools\bootstrap_film_v2_5070.ps1'
if(-not (Test-Path -LiteralPath $canonicalBootstrap -PathType Leaf)){throw 'Current-branch bootstrap script missing.'}
# V4-style: the desktop launcher pulls first, then runs the freshly checked-out
# bootstrap rather than continuing with potentially stale launcher code.
if(-not $FromCheckout -and
   ([System.IO.Path]::GetFullPath($MyInvocation.MyCommand.Path) -ine
    [System.IO.Path]::GetFullPath($canonicalBootstrap))){
 $freshParams=@{}
 foreach($pair in $PSBoundParameters.GetEnumerator()){
  if($pair.Key -ne 'FromCheckout'){$freshParams[$pair.Key]=$pair.Value}
 }
 $freshParams.FromCheckout=$true
 Write-Host 'Handing off to the updated F-drive launcher from Git checkout...'
 & $canonicalBootstrap @freshParams
 if(-not $?){throw 'Newly checked-out launcher failed.'}
 return
}

# Persist double-click launcher on F: and create a durable desktop shortcut.
New-Item -ItemType Directory -Path $launcher -Force | Out-Null
$cmdSource=Join-Path $repo 'Start_BANANA_FILM_5070.cmd'
if(-not (Test-Path -LiteralPath $cmdSource -PathType Leaf)){throw 'Current branch CMD launcher missing.'}
$cmdTarget=Join-Path $launcher 'Start_BANANA_FILM_5070.cmd'
$bootstrapTarget=Join-Path $launcher 'Bootstrap_BANANA_FILM_5070.ps1'
if([System.IO.Path]::GetFullPath($cmdSource) -ine [System.IO.Path]::GetFullPath($cmdTarget)){
 Copy-Item -LiteralPath $cmdSource -Destination $cmdTarget -Force
}
if([System.IO.Path]::GetFullPath($canonicalBootstrap) -ine [System.IO.Path]::GetFullPath($bootstrapTarget)){
 Copy-Item -LiteralPath $canonicalBootstrap -Destination $bootstrapTarget -Force
}
try{
 $shell=New-Object -ComObject WScript.Shell
 $desktop=[Environment]::GetFolderPath('Desktop')
 $shortcut=$shell.CreateShortcut((Join-Path $desktop 'BANANA FILM 5070 STUDIO.lnk'))
 $shortcut.TargetPath=$cmdTarget
 $shortcut.WorkingDirectory=$launcher
 $shortcut.Description='BANANA FILM V2 RTX5070 CU130 - F: uploads, clips, movies'
 $shortcut.Save()
 Write-Host 'Desktop shortcut: BANANA FILM 5070 STUDIO'
}catch{
 Write-Warning 'Could not create desktop shortcut; use F:\BANANA_FILM_5070_STUDIO\Launcher\Start_BANANA_FILM_5070.cmd instead.'
}

# Persist overrides on F: so future desktop clicks reuse relocated ComfyUI/Python paths.
$settingsPath=Join-Path $launcher 'settings.json'
if(Test-Path -LiteralPath $settingsPath -PathType Leaf){
 $saved=Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
 foreach($name in @('ComfyUrl','ComfyBase','ComfySource','ComfyInputDir','PythonPath','Port')){
  if(-not $PSBoundParameters.ContainsKey($name)){
   $value=$saved.$name
   if($name -eq 'Port' -and $value -eq 8195){continue}
   if($null -ne $value -and [string]$value -ne ''){ Set-Variable -Name $name -Value $value }
  }
 }
}
$settings=[ordered]@{ComfyUrl=$ComfyUrl;ComfyBase=$ComfyBase;ComfySource=$ComfySource;ComfyInputDir=$ComfyInputDir;PythonPath=$PythonPath;Port=$Port}
[System.IO.File]::WriteAllText($settingsPath,($settings | ConvertTo-Json -Depth 8),(New-Object System.Text.UTF8Encoding($false)))
Write-Host "Local runtime settings: $settingsPath"

# Explicit named parameters: do not modify global Windows settings or ComfyUI models.
$launchParams=@{DataRoot=$media;ComfyUrl=$ComfyUrl;Port=$Port}
if($ComfyBase){$launchParams.ComfyBase=$ComfyBase}
if($ComfySource){$launchParams.ComfySource=$ComfySource}
if($ComfyInputDir){$launchParams.ComfyInputDir=$ComfyInputDir}
if($PythonPath){$launchParams.PythonPath=$PythonPath}
if($NoAutoComfy){$launchParams.NoAutoComfy=$true}
if($NoBrowser){$launchParams.NoBrowser=$true}
& $service @launchParams
if(-not $?){throw 'BANANA FILM V2 local launcher did not complete. Review its error message.'}
