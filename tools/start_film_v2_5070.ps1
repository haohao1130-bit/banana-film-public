# BANANA FILM 5070 STUDIO - Windows 10/11 PowerShell 5.1, no model installations.
param(
 [string]$DataRoot='F:\AI\BANANA_FILM_5070_STUDIO\Media',
 [string]$ComfyUrl='http://127.0.0.1:8000',
 [string]$ComfyBase='',
 [string]$ComfySource='',
 [string]$ComfyInputDir='',
 [string]$PythonPath='',
 [int]$Port=8193,
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
# Match the proven MV V4 pattern: the front-end/backend may use the existing
# ComfyUI venv; GPU inference belongs to ComfyUI at port 8000.
$probe=Join-Path $project 'tools\check_film_cuda13.py'
if(-not (Test-Path -LiteralPath $probe -PathType Leaf)){throw "Missing environment probe: $probe"}
$cuPython=Join-Path $env:LOCALAPPDATA 'Banana9B-cu130\Scripts\python.exe'
$venvPython=Join-Path $ComfyBase '.venv\Scripts\python.exe'
$backendCandidates=@($PythonPath,$venvPython,$cuPython) | Where-Object {$_ -and (Test-Path -LiteralPath $_ -PathType Leaf)}
$python=$null
foreach($candidate in $backendCandidates){
 try{
  & $candidate $probe --role backend 2>$null
  if($LASTEXITCODE -eq 0){$python=$candidate;break}
 }catch{
  Write-Warning "Backend Python candidate rejected: $candidate"
 }
}
if(-not $python){throw 'No existing backend Python with Pillow + NumPy. Use -PythonPath for the working MV Python environment.'}
Write-Host "Film backend Python: $python (CUDA version is NOT a frontend gate)"
foreach($bin in @('ffmpeg','ffprobe')){
 if(-not (Get-Command $bin -ErrorAction SilentlyContinue)){ throw "$bin not found in PATH." }
}
foreach($name in @('','library','films','_runtime\logs','_runtime\comfy_input','_runtime\comfy_output','_runtime\comfy_temp')){
 New-Item -ItemType Directory -Force -Path (Join-Path $DataRoot $name) | Out-Null
}
function Read-JsonUrl([string]$url){
 try{ return Invoke-RestMethod -Uri $url -TimeoutSec 5 -ErrorAction Stop }catch{ return $null }
}
$nodes=Read-JsonUrl "$ComfyUrl/object_info"
# MV V4 pattern: an already-running ComfyUI owns its own CUDA/venv.
# Only probe the dedicated CU130 Python if we must start a new ComfyUI.
$comfyPython=$null
if(-not $nodes -and -not $NoAutoComfy){
 foreach($candidate in @($cuPython,$venvPython) | Select-Object -Unique){
  if(-not (Test-Path -LiteralPath $candidate -PathType Leaf)){continue}
  try{
   & $candidate $probe --role comfy 2>$null
   if($LASTEXITCODE -eq 0){$comfyPython=$candidate;break}
  }catch{Write-Warning "Comfy CUDA13 Python candidate rejected: $candidate"}
 }
}
$comfyLaunched=$false
if(-not $nodes){
 if($NoAutoComfy){throw 'ComfyUI is not running. Start your existing CUDA13 ComfyUI first.'}
 $main=Join-Path $ComfySource 'main.py'
 if(-not (Test-Path -LiteralPath $main -PathType Leaf)){throw "ComfyUI source missing: $main. Set -ComfySource or start port 8000 manually."}
 if($ComfyUrl -ne 'http://127.0.0.1:8000'){throw 'Auto-launch only supports default local ComfyUI port 8000.'}
 $input=Join-Path $DataRoot '_runtime\comfy_input'
 $output=Join-Path $DataRoot '_runtime\comfy_output'
 $temp=Join-Path $DataRoot '_runtime\comfy_temp'
 $comfyArgs=@('-u',('"' + $main + '"'),'--base-directory',('"' + $ComfyBase + '"'),'--input-directory',('"' + $input + '"'),'--output-directory',('"' + $output + '"'),'--temp-directory',('"' + $temp + '"'),'--listen','127.0.0.1','--port','8000','--lowvram','--preview-method','none')
 Write-Host 'Starting existing CUDA13 ComfyUI with F: cache / --lowvram.'
 if(-not $comfyPython){throw 'No working CUDA13 ComfyUI Python found. Start ComfyUI with the existing MV V4 launcher, or repair your CU130 environment; no Torch was modified.'}
 Write-Host "Starting ComfyUI with CUDA13 Python: $comfyPython"
 $comfy=Start-Process -FilePath $comfyPython -ArgumentList $comfyArgs -WorkingDirectory $ComfySource -PassThru -RedirectStandardOutput (Join-Path $DataRoot '_runtime\logs\comfy.stdout.log') -RedirectStandardError (Join-Path $DataRoot '_runtime\logs\comfy.stderr.log')
 $comfyLaunched=$true
 $deadline=(Get-Date).AddMinutes(3)
 while(-not $nodes -and (Get-Date) -lt $deadline){
  Start-Sleep -Seconds 3
  $nodes=Read-JsonUrl "$ComfyUrl/object_info"
  if($comfy.HasExited){throw 'ComfyUI startup exited; inspect F:\AI\BANANA_FILM_5070_STUDIO\Media\_runtime\logs\comfy.stderr.log.'}
 }
 if(-not $nodes){throw 'ComfyUI did not become ready; inspect Media\_runtime\logs\comfy.stderr.log.'}
}
if(-not $ComfyInputDir){
 if($comfyLaunched){$ComfyInputDir=Join-Path $DataRoot '_runtime\comfy_input'}
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
$receiptPath=Join-Path $DataRoot '_runtime\logs\server_process.json'
$expectedRoot=[System.IO.Path]::GetFullPath($DataRoot).TrimEnd('\')
$expectedCommit=(& git -C $project rev-parse --short=9 HEAD)
if($LASTEXITCODE -ne 0 -or -not $expectedCommit){throw 'Cannot read current Git commit; verify the F-drive checkout.'}
$health=Read-JsonUrl $healthUrl
if($health){
 if($health.variant -ne 'rtx5070-fdrive' -or
    $health.engine -notin @('colab_film','python_owned_film_v2')){
  throw "Port $Port is used by a different application. Refusing to stop it."
 }
 $reportedRoot=[string]$health.data_root
 if($reportedRoot.TrimEnd('\') -ine $expectedRoot){
  throw "Port $Port is already bound to another data root: $reportedRoot"
 }
 $runningCommit=[string]$health.version.commit
 # Old Python-Owned V2 process must also be upgraded to the actual Colab Film UI.
 if($runningCommit -ne $expectedCommit -or $health.engine -ne 'colab_film'){
  Write-Host "Colab Film parity: switching port $Port backend from $($health.engine) / $runningCommit to colab_film / $expectedCommit."
  if($null -eq $health.busy){
   throw 'Existing Film backend is too old to report GPU activity. Close ONLY the old BANANA FILM backend once, then double-click again. ComfyUI can stay on.'
  }
  if($health.busy){
   throw 'BANANA FILM is rendering a job. Update downloaded; automatic service restart deferred. Relaunch when it finishes.'
  }
  # Stop ONLY the verified Film server, never port 8000 / shared ComfyUI.
  $ownerPid=$null
  if(Test-Path -LiteralPath $receiptPath){
   try{
    $receipt=Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if($receipt.instance -eq $health.instance -and $receipt.data_root -ieq $expectedRoot){
     $ownerPid=[int]$receipt.pid
    }
   }catch{Write-Warning 'Could not read prior server receipt; checking TCP port owner.'}
  }
  if(-not $ownerPid){
   $sockets=@(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
              Where-Object {$_.LocalAddress -eq '127.0.0.1'})
   $owners=@($sockets | Select-Object -ExpandProperty OwningProcess -Unique)
   if($owners.Count -eq 1){$ownerPid=[int]$owners[0]}
  }
  if(-not $ownerPid){
   throw 'Cannot determine the verified Film backend PID. Stop ONLY the Film server manually; ComfyUI must remain running.'
  }
  $processInfo=Get-CimInstance Win32_Process -Filter "ProcessId=$ownerPid" -ErrorAction SilentlyContinue
  if(-not $processInfo -or
     [string]$processInfo.CommandLine -notmatch '(?i)(?:^|\s)-m\s+film_v2\.(?:server|local_classic_server)(?:\s|$)'){
   throw "PID $ownerPid is not a verified local Film backend process. Refusing to kill it."
  }
  Write-Host "Safely restarting outdated Film-only process PID $ownerPid ..."
  Stop-Process -Id $ownerPid -ErrorAction Stop
  $deadline=(Get-Date).AddSeconds(20)
  while((Read-JsonUrl $healthUrl) -and (Get-Date) -lt $deadline){Start-Sleep -Milliseconds 500}
  if(Read-JsonUrl $healthUrl){throw 'Old Film server has not released its port; refusing second server.'}
  Remove-Item -LiteralPath $receiptPath -Force -ErrorAction SilentlyContinue
  $health=$null
 }
}
if(-not $health){
 $proc=Start-Process -FilePath $python -ArgumentList @('-u','-m','film_v2.local_classic_server') -WorkingDirectory $project -PassThru -RedirectStandardOutput (Join-Path $DataRoot '_runtime\logs\server.stdout.log') -RedirectStandardError (Join-Path $DataRoot '_runtime\logs\server.stderr.log')
 $deadline=(Get-Date).AddSeconds(80)
 while(-not $health -and (Get-Date) -lt $deadline){
  Start-Sleep -Seconds 2
  $health=Read-JsonUrl $healthUrl
  if($proc.HasExited){throw 'V2 service failed; check F:\AI\BANANA_FILM_5070_STUDIO\Media\_runtime\logs\server.stderr.log.'}
 }
}
if(-not $health -or $health.engine -ne 'colab_film' -or $health.variant -ne 'rtx5070-fdrive'){
 throw 'Wrong/missing full Colab Film Studio backend at requested port.'
}
if(([string]$health.data_root).TrimEnd('\') -ine $expectedRoot){
 throw "Data root mismatch: $($health.data_root); expected $expectedRoot"
}
if($health.version.commit -ne $expectedCommit){
 throw "Running backend is NOT updated: $($health.version.commit); checkout: $expectedCommit"
}
if($proc -and -not $proc.HasExited){
 $receipt=[ordered]@{pid=$proc.Id;instance=$health.instance;commit=$expectedCommit;data_root=$expectedRoot}
 [System.IO.File]::WriteAllText($receiptPath,($receipt | ConvertTo-Json -Depth 4),(New-Object System.Text.UTF8Encoding($false)))
}
Write-Host "Running backend version: $($health.version.branch) | $($health.version.commit)"
Write-Host ''
Write-Host 'BANANA FILM 5070 STUDIO - FULL COLAB UI + FUNCTION PARITY READY'
Write-Host "UI: http://127.0.0.1:$Port"
Write-Host "Uploaded originals: $(Join-Path $DataRoot 'library')"
Write-Host "Finished videos: $(Join-Path (Split-Path -Parent $DataRoot) 'videos')"
Write-Host "Colab-compatible Film projects: $(Join-Path $DataRoot 'films')"
Write-Host "Original Python-Owned V2 projects preserved: $(Join-Path $DataRoot 'films_v2')"
Write-Host "ComfyUI: $ComfyUrl; input: $ComfyInputDir"
Write-Host 'No Torch/CUDA/model changes. Do NOT generate from MV concurrently.'
if(-not $NoBrowser){Start-Process "http://127.0.0.1:$Port/" | Out-Null}
