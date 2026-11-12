# BANANA FILM 5070 STUDIO - clone/update only this public experimental branch.
# Portable: can run from extracted launcher package or the repository's tools folder.
param(
 [string]$InstallRoot='F:\BANANA_FILM_5070_STUDIO',
 [string]$ComfyUrl='http://127.0.0.1:8000',
 [string]$ComfyBase='',
 [string]$ComfySource='',
 [string]$ComfyInputDir='',
 [string]$PythonPath='',
 [int]$Port=8195,
 [switch]$NoAutoComfy,
 [switch]$NoBrowser
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
 & git -C $repo diff --quiet
 if($LASTEXITCODE -ne 0){throw 'Tracked local edits detected. Commit/stash before auto-update; no files were overwritten.'}
 & git -C $repo diff --cached --quiet
 if($LASTEXITCODE -ne 0){throw 'Staged local edits detected. Commit/stash before auto-update.'}
 Write-Host 'Updating only current RTX5070 branch (fast-forward, no reset)...'
 & git -C $repo pull --ff-only origin $branch
 if($LASTEXITCODE -ne 0){throw 'Fast-forward update failed. Existing local files remain intact.'}
}
$head=(& git -C $repo log -1 --format=%h)
Write-Host "BANANA FILM 5070 STUDIO revision: $head"
$service=Join-Path $repo 'tools\start_film_v2_5070.ps1'
if(-not (Test-Path -LiteralPath $service -PathType Leaf)){throw '5070 service launcher missing from checked-out branch.'}

# Persist double-click launcher on F: and create a durable desktop shortcut.
New-Item -ItemType Directory -Path $launcher -Force | Out-Null
$bootstrapSource=$MyInvocation.MyCommand.Path
$sourceDirectory=Split-Path -Parent $bootstrapSource
$cmdSource=Join-Path $sourceDirectory 'Start_BANANA_FILM_5070.cmd'
if(-not (Test-Path -LiteralPath $cmdSource)){
 $cmdSource=Join-Path (Split-Path -Parent $sourceDirectory) 'Start_BANANA_FILM_5070.cmd'
}
if(-not (Test-Path -LiteralPath $cmdSource)){throw 'Start_BANANA_FILM_5070.cmd missing from extracted launcher package.'}
$cmdTarget=Join-Path $launcher 'Start_BANANA_FILM_5070.cmd'
$bootstrapTarget=Join-Path $launcher 'Bootstrap_BANANA_FILM_5070.ps1'
if($cmdSource -ine $cmdTarget){Copy-Item -LiteralPath $cmdSource -Destination $cmdTarget -Force}
if($bootstrapSource -ine $bootstrapTarget){Copy-Item -LiteralPath $bootstrapSource -Destination $bootstrapTarget -Force}
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

# Explicit named parameters: do not modify global Windows settings or ComfyUI models.
$args=@{DataRoot=$media;ComfyUrl=$ComfyUrl;Port=$Port}
if($ComfyBase){$args.ComfyBase=$ComfyBase}
if($ComfySource){$args.ComfySource=$ComfySource}
if($ComfyInputDir){$args.ComfyInputDir=$ComfyInputDir}
if($PythonPath){$args.PythonPath=$PythonPath}
if($NoAutoComfy){$args.NoAutoComfy=$true}
if($NoBrowser){$args.NoBrowser=$true}
& $service @args
if(-not $?){throw 'BANANA FILM V2 local launcher did not complete. Review its error message.'}
