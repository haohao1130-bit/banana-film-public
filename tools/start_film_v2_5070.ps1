# BANANA FILM 5070 STUDIO - Windows 10/11 PowerShell 5.1, no model installations.
param(
 [string]$DataRoot='F:\BANANA_FILM_5070_STUDIO\Media',
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
$project=Split-Path -Parent $PSScriptRoot
$branch='film-v2-rtx5070-fdrive'
if(-not (Test-Path -LiteralPath 'F:\' -PathType Container)){ throw 'F: drive missing. No files were moved.' }
if(-not $DataRoot.StartsWith('F:\',[StringComparison]::OrdinalIgnoreCase)){ throw 'DataRoot must be under F:\.' }
if(-not (Test-Path -LiteralPath (Join-Path $project 'film_v2\server.py'))){ throw 'FILM V2 source not found.' }
if(Get-Command git -ErrorAction SilentlyContinue){
 $current=(& git -C $project branch --show-current 2>$null)
 if($LASTEXITCODE -eq 0 -and $current -ne $branch){ throw "Wrong git branch: $current; expected $branch." }
}
if(-not $ComfyBase){$ComfyBase=Join-Path $env:USERPROFILE 'Documents\ComfyUI'}
if(-not $ComfySource){$ComfySource=Join-Path $env:LOCALAPPDATA 'Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI'}
$candidates=@($PythonPath,(Join-Path $ComfyBase '.venv\Scripts\python.exe'),(Join-Path $env:LOCALAPPDATA 'Banana9B-cu130\Scripts\python.exe'))
$python=@($candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1)
if(-not $python){ throw 'Working CU130 Python not found. Supply -PythonPath with your existing 5070 interpreter.' }
$python=$python[0]
Write-Host "Using Python: $python"
& $python -c 'import torch,PIL,numpy; print("GPU:",torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none","CUDA:",torch.version.cuda); assert torch.cuda.is_available(); assert torch.version.cuda and torch.version.cuda.startswith("13")'
if($LASTEXITCODE -ne 0){ throw 'CUDA 13 or Pillow/numpy check failed. This launcher never upgrades Torch.' }
foreach($bin in @('ffmpeg','ffprobe')){
 if(-not (Get-Command $bin -ErrorAction SilentlyContinue)){ throw "$bin not found in PATH." }
}
foreach($name in @('','library','videos','films_v2','logs','comfy_input','comfy_output','comfy_temp')){
 New-Item -ItemType Directory -Force -Path (Join-Path $DataRoot $name) | Out-Null
}
function Read-JsonUrl([string]$url){
 try{ return Invoke-RestMethod -Uri $url -TimeoutSec 5 -ErrorAction Stop }catch{ return $null }
}
$nodes=Read-JsonUrl "$ComfyUrl/object_info"
$comfyLaunched=$false
if(-not $nodes){
 if($NoAutoComfy){throw 'ComfyUI is not running. Start your existing CUDA13 ComfyUI first.'}
 $main=Join-Path $ComfySource 'main.py'
 if(-not (Test-Path -LiteralPath $main -PathType Leaf)){throw "ComfyUI source missing: $main. Set -ComfySource or start port 8000 manually."}
 if($ComfyUrl -ne 'http://127.0.0.1:8000'){throw 'Auto-launch only supports default local ComfyUI port 8000.'}
 $input=Join-Path $DataRoot 'comfy_input'
 $output=Join-Path $DataRoot 'comfy_output'
 $temp=Join-Path $DataRoot 'comfy_temp'
 $args=@('-u',('"' + $main + '"'),'--base-directory',('"' + $ComfyBase + '"'),'--input-directory',('"' + $input + '"'),'--output-directory',('"' + $output + '"'),'--temp-directory',('"' + $temp + '"'),'--listen','127.0.0.1','--port','8000','--lowvram','--preview-method','none')
 Write-Host 'Starting existing CUDA13 ComfyUI with F: cache / --lowvram.'
 $comfy=Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $ComfySource -PassThru -RedirectStandardOutput (Join-Path $DataRoot 'logs\comfy.stdout.log') -RedirectStandardError (Join-Path $DataRoot 'logs\comfy.stderr.log')
 $comfyLaunched=$true
 $deadline=(Get-Date).AddMinutes(3)
 while(-not $nodes -and (Get-Date) -lt $deadline){
  Start-Sleep -Seconds 3
  $nodes=Read-JsonUrl "$ComfyUrl/object_info"
  if($comfy.HasExited){throw 'ComfyUI startup exited; inspect F:\BANANA_FILM_5070_STUDIO\Media\logs\comfy.stderr.log.'}
 }
 if(-not $nodes){throw 'ComfyUI did not become ready; inspect Media\logs\comfy.stderr.log.'}
}
if(-not $ComfyInputDir){
 if($comfyLaunched){$ComfyInputDir=Join-Path $DataRoot 'comfy_input'}
 else{$ComfyInputDir=Join-Path $ComfyBase 'input'}
}
if(-not (Test-Path -LiteralPath $ComfyInputDir -PathType Container)){
 throw "ComfyUI input path missing: $ComfyInputDir. Supply -ComfyInputDir matching your running ComfyUI."
}
$missing=@()
foreach($node in @('TextGenerate','MiniMaxH3ReferenceToVideo','VAEDecodeAudio')){
 if(-not $nodes.PSObject.Properties[$node]){$missing+=$node}
}
if($missing.Count){throw "Required node missing: $($missing -join ', '). Use your working CUDA13 H3/9B installation."}
if(-not $nodes.PSObject.Properties['MiniMaxH3AddGuide']){Write-Warning 'Chain5 node missing; use independent until MiniMaxH3AddGuide is installed.'}
$guide=Join-Path $project 'guides\VIDEO_PROMPT_WRITING_GUIDE_ref_en.md'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $guide) | Out-Null
if(-not (Test-Path -LiteralPath $guide)){
 foreach($candidate in @((Join-Path $env:LOCALAPPDATA 'BananaMVVNext\guides\VIDEO_PROMPT_WRITING_GUIDE_ref_en.md'),(Join-Path $env:USERPROFILE 'banana-mv-5070\guides\VIDEO_PROMPT_WRITING_GUIDE_ref_en.md'))){
  if(Test-Path -LiteralPath $candidate){Copy-Item -LiteralPath $candidate -Destination $guide;break}
 }
 if(-not (Test-Path -LiteralPath $guide)){
  Write-Host 'Downloading only the small official prompt guide (no model weights).'
  Invoke-WebRequest -UseBasicParsing -Uri 'https://huggingface.co/MiniMaxAI/MiniMax-H3/resolve/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md' -OutFile $guide
 }
}
$configPath=Join-Path $DataRoot 'config.json'
$config=[pscustomobject]@{}
if(Test-Path -LiteralPath $configPath){$config=Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json}
$config | Add-Member -NotePropertyName 'comfy_url' -NotePropertyValue $ComfyUrl -Force
$config | Add-Member -NotePropertyName 'comfy_input_dir' -NotePropertyValue $ComfyInputDir -Force
[System.IO.File]::WriteAllText($configPath,($config | ConvertTo-Json -Depth 20),(New-Object System.Text.UTF8Encoding($false)))
$env:BANANA_DATA=$DataRoot
$env:BANANA_PORT=[string]$Port
$healthUrl="http://127.0.0.1:$Port/api/health"
$health=Read-JsonUrl $healthUrl
if($health -and $health.engine -ne 'python_owned_film_v2'){throw "Port $Port is occupied by another service."}
if(-not $health){
 $proc=Start-Process -FilePath $python -ArgumentList @('-u','-m','film_v2.server') -WorkingDirectory $project -PassThru -RedirectStandardOutput (Join-Path $DataRoot 'logs\server.stdout.log') -RedirectStandardError (Join-Path $DataRoot 'logs\server.stderr.log')
 $deadline=(Get-Date).AddSeconds(80)
 while(-not $health -and (Get-Date) -lt $deadline){
  Start-Sleep -Seconds 2
  $health=Read-JsonUrl $healthUrl
  if($proc.HasExited){throw 'V2 service failed; inspect F:\BANANA_FILM_5070_STUDIO\Media\logs\server.stderr.log.'}
 }
}
if(-not $health -or $health.engine -ne 'python_owned_film_v2'){throw 'Wrong/missing V2 service at requested port.'}
if($health.variant -ne 'rtx5070-fdrive'){throw 'Different V2 edition is already running on the requested port. Stop it before launching the F-drive studio.'}
$expectedRoot=[System.IO.Path]::GetFullPath($DataRoot).TrimEnd('\')
$reportedRoot=[string]$health.data_root
if($reportedRoot.TrimEnd('\') -ine $expectedRoot){throw "Port $Port belongs to a V2 server with another data root: $reportedRoot. Stop it to protect F: files."}
Write-Host ''
Write-Host 'BANANA FILM 5070 STUDIO - READY'
Write-Host "UI: http://127.0.0.1:$Port"
Write-Host "Uploaded originals: $(Join-Path $DataRoot 'library')"
Write-Host "Finished videos: $(Join-Path $DataRoot 'videos')"
Write-Host "Saved clips/projects: $(Join-Path $DataRoot 'films_v2')"
Write-Host "ComfyUI: $ComfyUrl; input: $ComfyInputDir"
Write-Host 'No Torch/CUDA/model changes. Do NOT generate from MV concurrently.'
if(-not $NoBrowser){Start-Process "http://127.0.0.1:$Port/" | Out-Null}
