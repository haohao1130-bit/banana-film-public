const $=id=>document.getElementById(id);
let active=null,timer,selected=Array(9).fill(null),imageURLs=[],currentJob=null,stopRequested=null;
const terminal=['done','error','cancelled','interrupted','script_ready'];
async function api(path,options){const response=await fetch(path,options);const data=await response.json();if(!response.ok||data.error&&!data.id)throw Object.assign(Error(data.error||'請求失敗'),{code:data.code});return data;}
function busy(value){$('mode').disabled=value;$('generate').disabled=value;$('direct-render').disabled=value;for(let i=1;i<=9;i++){ $('image-'+i).disabled=value;$('remove-'+i).disabled=value;}$('open-project').disabled=value;$('refresh-projects').disabled=value;$('stop').hidden=!value;$('stop-hint').hidden=!value;$('stop').disabled=stopRequested===active;$('stop').textContent=stopRequested===active?'已要求停爐・等待本段完成':'🚨 緊急停爐';$('projector').classList.toggle('working',value);}
function refs(){closeImageMentions();for(const url of imageURLs)URL.revokeObjectURL(url);imageURLs=[];selected.forEach((file,i)=>{const img=$('preview-'+(i+1));img.hidden=!file;if(file){img.src=URL.createObjectURL(file);imageURLs.push(img.src);}else img.removeAttribute('src');$('name-'+(i+1)).textContent=file?file.name:'尚未選圖';});}
for(let i=1;i<=9;i++){
 $('image-'+i).onchange=()=>{selected[i-1]=$('image-'+i).files[0]||null;refs();};
 $('remove-'+i).onclick=()=>{selected[i-1]=null;$('image-'+i).value='';refs();};
 $('insert-'+i).onclick=()=>insertReference(i);
}

const STORY_LIMIT=30000;
const imageMention={range:null,items:[],index:0,composing:false};
function storyLength(text){return Array.from(text).length;}
function promptCount(){const input=$('prompt'),length=storyLength(input.value),over=length>STORY_LIMIT;input.setCustomValidity?.(over?'故事最多 30000 字，請刪減後再送出。':'');input.setAttribute('aria-invalid',String(over));$('prompt-count').textContent=`${length} / ${STORY_LIMIT} 字`+(over?'・已超過上限，請刪減後再開拍':'');}
function closeImageMentions(){imageMention.range=null;imageMention.items=[];$('image-mentions').hidden=true;$('prompt').setAttribute('aria-expanded','false');$('prompt').removeAttribute('aria-activedescendant');}
function insertReference(number,range){const input=$('prompt'),start=range?.start??input.selectionStart,end=range?.end??input.selectionEnd,next=input.value[end],text='@圖片'+number+(next&&/\s/.test(next)?'':' ');if(storyLength(input.value.slice(0,start)+text+input.value.slice(end))>STORY_LIMIT){ $('status').textContent='故事已達字數上限，請先刪減後再插入圖片標記。';return;}const scroll=input.scrollTop;input.setRangeText(text,start,end,'end');closeImageMentions();promptCount();input.focus({preventScroll:true});input.scrollTop=scroll;}
function updateImageMentions(event){promptCount();updateFilmControls();const input=$('prompt'),menu=$('image-mentions');if(imageMention.composing||event?.isComposing||input.selectionStart!==input.selectionEnd){closeImageMentions();return;}const before=input.value.slice(0,input.selectionStart),match=/@(?:圖片?|图片?|image)?[1-9]?$/i.exec(before);if(!match||(match.index>0&&/[a-z0-9_.]/i.test(before[match.index-1]))){closeImageMentions();return;}const number=match[0].match(/[1-9]$/)?.[0],limit=$('mode').value==='chain'?8:9;imageMention.items=[];for(let i=0;i<limit;i++){const file=selected[i];if(file&&(!number||Number(number)===i+1))imageMention.items.push({number:i+1,name:file.name,url:$('preview-'+(i+1)).src});}imageMention.range={start:match.index,end:input.selectionStart};imageMention.index=0;menu.replaceChildren();if(!imageMention.items.length){const empty=document.createElement('p');empty.className='mention-empty';empty.textContent='請先在上方選擇參考圖片。';menu.append(empty);}imageMention.items.forEach((item,index)=>{const button=document.createElement('button');button.type='button';button.id='image-mention-'+item.number;button.className='mention-option';button.setAttribute('role','option');button.setAttribute('aria-label',`@圖片${item.number}：${item.name}`);const img=document.createElement('img');img.src=item.url;img.alt='';const label=document.createElement('span');label.textContent='@圖片'+item.number;const name=document.createElement('small');name.textContent=item.name;label.append(name);button.append(img,label);button.onpointerdown=e=>e.preventDefault();button.onclick=()=>chooseImageMention(index);menu.append(button);});menu.hidden=false;input.setAttribute('aria-expanded','true');highlightImageMention();}
function highlightImageMention(){const menu=$('image-mentions');imageMention.items.forEach((item,i)=>menu.children[i].setAttribute('aria-selected',String(i===imageMention.index)));const item=menu.children[imageMention.index];if(imageMention.items.length){$('prompt').setAttribute('aria-activedescendant',item.id);item.scrollIntoView?.({block:'nearest'});}else $('prompt').removeAttribute('aria-activedescendant');}
function chooseImageMention(index){const item=imageMention.items[index],range=imageMention.range;if(item&&range)insertReference(item.number,range);}
$('prompt').addEventListener('input',updateImageMentions);
$('prompt').addEventListener('click',updateImageMentions);
$('prompt').addEventListener('compositionstart',()=>{imageMention.composing=true;closeImageMentions();});
$('prompt').addEventListener('compositionend',()=>{imageMention.composing=false;updateImageMentions();});
$('prompt').addEventListener('blur',closeImageMentions);
$('prompt').addEventListener('keydown',e=>{if(e.isComposing||imageMention.composing||e.keyCode===229||$('image-mentions').hidden)return;if(e.key==='Escape'){e.preventDefault();closeImageMentions();return;}if(!imageMention.items.length)return;if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();imageMention.index=(imageMention.index+(e.key==='ArrowDown'?1:-1)+imageMention.items.length)%imageMention.items.length;highlightImageMention();}else if(e.key==='Enter'){e.preventDefault();chooseImageMention(imageMention.index);}else if(e.key==='Tab')closeImageMentions();});
$('prompt').addEventListener('keyup',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key))updateImageMentions(e);});
$('mode').addEventListener('change',closeImageMentions);
async function upload(file){return api('api/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(file.name)},body:file});}
function renderPrompt(){const index=Number($('prompt-segment').value);$('rewritten-prompt').value=currentJob?.segments?.[index]?.prompt||'';}
$('prompt-segment').onchange=renderPrompt;
$('copy-prompt').onclick=async()=>{try{await navigator.clipboard.writeText($('rewritten-prompt').value);$('copy-feedback').textContent='已複製';}catch{$('rewritten-prompt').select();$('copy-feedback').textContent='請長按選取文字複製。';}};
function faceRefineActivity(job) {
 const progress = job.face_refine_progress;
 if (progress?.stage === 'clip') return `正在修臉第 ${progress.index + 1}／${progress.total} 段${progress.reference ? ` · @圖片${progress.reference}` : ''}…`;
 if (progress?.stage === 'assembling') return '正在合成並另存修臉版…';
 return '正在準備修臉…';
}

function renderFinalPreviews(job, relative = false) {
 const current = (job.final_versions || []).find(version => version.version === job.current_master);
 const refined = (job.final_versions || []).findLast(version =>
  version.reason === 'face_refine' && version.source_master === job.current_master);
 const url = value => relative ? value.replace(/^\//, '') : value;
 function show(videoId, linkId, source) {
  const video = $(videoId), link = $(linkId);
  video.hidden = link.hidden = !source;
  link.style.display = source ? 'block' : 'none';
  if (source) {
   const src = url(source);
   if (video.getAttribute('src') !== src) video.setAttribute('src', src);
   link.href = src;
  } else if (video.getAttribute('src')) {
   video.removeAttribute('src');
   video.load?.();
   link.removeAttribute('href');
  }
 }
 const master = current?.download || job.video;
 $('final-previews').hidden = !master;
 show('video', 'download', master);
 show('refined-video', 'refined-download', refined?.download);
 const upscale = (job.final_versions || []).findLast(version =>
  version.reason === 'upscale_1080p' && version.source_master === job.current_master);
 $('upscale-preview').hidden = !(upscale || job.request?.upscale_1080p);
 show('upscale-video', 'upscale-download', upscale?.download);
 $('upscale-status').textContent = job.status === 'upscaling_1080p' ? '正在使用 NVIDIA RTX 放大…' :
  upscale?.export_error || upscale?.output_video || job.upscale_error || (upscale ? '' : '等待成片。');
 const output = $('refined-output');
 output.textContent = refined?.output_video ? '修臉版成品：' + refined.output_video : refined?.export_error || '';
 output.hidden = !output.textContent;
 const status = $('refined-status');
 const segments = job.segments || [];
 const failed = segments.flatMap((segment, index) => segment.face_refine_error
  ? [`第 ${index + 1} 段：${segment.face_refine_error.split('\n')[0].slice(0, 220)}`] : []);
 const refining = job.status === 'refining_faces';
 status.hidden = !refining && !failed.length && Boolean(refined && refined.refined_clips === segments.length);
 if (refining) {
  status.textContent = faceRefineActivity(job);
 } else if (refined) {
  status.textContent = [`${refined.refined_clips}／${segments.length} 段有修臉輸出。`, ...failed].join(' ');
 } else if (job.face_refine_error || failed.length) {
  status.textContent = ['修臉版未輸出。', job.face_refine_error, ...failed].filter(Boolean).join(' ');
 } else if (job.request?.face_refine === false) {
  status.textContent = '本次未啟用修臉。';
 } else {
  status.textContent = '這版母片尚無完整修臉版。';
 }
}

function renderJob(j){
 currentJob=j;globalThis.BananaKitchen?.render(j);$('projector').dataset.state=j.status;renderScript(j);const segments=j.segments||[],done=segments.filter(s=>s.status==='done').length,working=!terminal.includes(j.status);
 busy(working);$('resume-project').hidden=!['error','cancelled','interrupted'].includes(j.status);
 $('activity').textContent=({script_ready:'編劇桌｜劇本完成，等待你的確認',planning_story:'編劇桌｜導演正在安排故事與分場',running:'攝影棚｜正在製作片段',retaking:'補拍現場｜正在重拍指定片段',assembling:'剪接室｜正在合成原生影音',refining_faces:'剪接室｜正在生成修臉版',upscaling_1080p:'剪接室｜正在使用 NVIDIA RTX 放大',done:'放映室｜作品完成',error:'製作暫停｜請查看錯誤',cancelled:'已停機｜完成片段保留',interrupted:'執行階段中斷｜可繼續製作'})[j.status]||'正在備料';
 if(j.status==='refining_faces')$('activity').textContent=faceRefineActivity(j);
 if(j.status==='running'&&j.current){const s=segments[j.current-1];$('activity').textContent=`第 ${j.current} 段｜${s?.status==='rewriting'?'攝影導演寫稿':'H3 原生影音生成中'}`;}
 $('progress').max=segments.length||1;$('progress').value=done;$('progress-label').textContent=segments.length?`${j.status==='refining_faces'?'母片 ':''}${done} / ${segments.length} 段完成 · 全片 ${j.duration.toFixed(2)} 秒`:'依故事決定實際長度';
 $('status').textContent=j.error?`${j.error_stage||''}：${j.error}`:j.status==='refining_faces'?'母片已完成，可以先播放或下載。':j.status==='done'?'作品已合成。可以放映，或挑選片段補拍。':j.status==='script_ready'?'劇本已完成，可細修；尚未送入 H3。':j.status==='planning_story'?`全片上限 ${j.request?.max_seconds||0} 秒；${j.request?.duration_policy==='target'?'自動導演依目標展開故事。':'依提供內容安排自然長度。'}`:'原始資料與完成片段會保留，請勿重複提交。';
 const continuityLabels={independent:'各段獨立',chain:'單張末幀參考',chain5:'末五幀動作接續'};$('project-summary').textContent=`${j.title||j.id} · ${j.id} · 接續：${continuityLabels[j.request?.mode]||j.request?.mode||'未記錄'}`;$('job-seed').textContent='Seed：'+j.seed;
 renderFinalPreviews(j, true);
 $('output-location').textContent=[j.final_video?'目前完整作品：'+j.final_video:'',j.output_video?'母片成品：'+j.output_video:'',j.export_error||''].filter(Boolean).join('\n');
 $('master-review').hidden=!j.final_versions?.length;const signature=JSON.stringify([j.current_master,j.final_versions]);if($('master-list').dataset.signature!==signature){$('master-list').replaceChildren();for(const v of j.final_versions||[]){const a=document.createElement('a');a.className='secondary';a.href=v.download.replace(/^\//,'');a.download=`banana-film-v${v.version}.mp4`;a.textContent=(v.reason==='face_refine'?'修臉版 · ':v.reason==='upscale_1080p'?'1080P · ':'')+`第 ${v.version} 版`+(v.version===j.current_master?' · 目前採用':'');$('master-list').append(a);}$('master-list').dataset.signature=signature;}
 $('plan-panel').hidden=!segments.length;const plan=JSON.stringify(segments.map(s=>s.director_plan));if($('scene-list').dataset.signature!==plan){$('scene-list').replaceChildren();for(const s of segments){const d=document.createElement('details');d.className='scene';const title=document.createElement('summary');title.textContent=`${s.index+1} / ${s.start.toFixed(2)}–${(s.start+s.seconds).toFixed(2)} 秒`;const text=document.createElement('pre');text.textContent=s.director_plan?.event||'';d.append(title,text);$('scene-list').append(d);}$('scene-list').dataset.signature=plan;}
 const written=segments.filter(s=>s.prompt);$('prompt-panel').hidden=!written.length;const prior=$('prompt-segment').value;$('prompt-segment').replaceChildren();for(const s of written){const o=document.createElement('option');o.value=s.index;o.textContent='第 '+(s.index+1)+' 段';$('prompt-segment').append(o);}if(written.some(s=>String(s.index)===prior))$('prompt-segment').value=prior;renderPrompt();renderClipPreviews(j);
}
async function poll(restoring=false){if(!active)return;const requested=active;clearTimeout(timer);try{const j=await api('api/mv/status?id='+encodeURIComponent(active));if(active!==requested)return;if(restoring&&j.status==='done'){active=null;localStorage.removeItem('banana_film_job');busy(false);$('status').textContent='上次作品已完成。可選圖建立新短片。';return;}renderJob(j);if(!terminal.includes(j.status))timer=setTimeout(poll,2500);}catch(error){if(active!==requested)return;if(error.code==='film_state_missing'){active=null;currentJob=null;localStorage.removeItem('banana_film_job');busy(false);$('status').textContent='找不到上次開啟的作品。可重新選圖建立短片，或從作品清單開啟其他作品。';return;}$('status').textContent='連線暫時中斷：'+error.message+'；會重新查詢，不會重送生成。';timer=setTimeout(()=>poll(restoring),5000);}}
async function projects(){const list=await api('api/mv/projects');$('projects').replaceChildren();for(const row of list){const o=document.createElement('option');o.value=row.id;o.textContent=`${row.title} · ${row.completed}/${row.total} · ${row.status}`;$('projects').append(o);}return list;}
$('refresh-projects').onclick=()=>projects().catch(e=>$('status').textContent=e.message);
$('open-project').onclick=async()=>{if(!$('projects').value)return;clearTimeout(timer);active=$('projects').value;localStorage.setItem('banana_film_job',active);await poll();};
$('resume-project').onclick=async()=>{try{busy(true);await api('api/mv/resume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:active})});await poll();}catch(e){busy(false);$('status').textContent=e.message;}};
$('stop').onclick=async()=>{if(!active||stopRequested===active)return;stopRequested=active;$('stop').disabled=true;$('stop').textContent='正在送出停爐要求…';try{await api('api/mv/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:active})});$('stop').disabled=true;$('stop').textContent='已要求停爐・等待本段完成';}catch(e){stopRequested=null;$('stop').disabled=false;$('stop').textContent='🚨 緊急停爐';$('status').textContent=e.message;}};
$('form').onsubmit=async event=>{event.preventDefault();const direct=event.submitter?.id==='direct-render';try{if(storyLength($('prompt').value)>STORY_LIMIT)throw Error('故事最多 30000 字，請刪減後再送出。');const modeAtSubmit=$('mode').value;const limit=modeAtSubmit==='chain'?8:9;if(selected.filter(Boolean).length>limit)throw Error(`最多 ${limit} 張參考圖。`);busy(true);clearTimeout(timer);$('activity').textContent='場記備料｜正在上傳參考圖片';$('status').textContent='正在建立新作品…';const slots=[];for(const file of selected)slots.push(file?(await upload(file)).id:null);const widths={'720p':{'16:9':1280,'9:16':720,'4:5':720,'1:1':720},'480p':{'16:9':854,'9:16':480,'4:5':480,'1:1':480}};const chosenDuration=$('max-seconds').value;
const customDuration=chosenDuration==='custom'?Number($('custom-seconds').value):null;
if(chosenDuration==='custom'&&(!Number.isFinite(customDuration)||customDuration<6||customDuration>300))throw Error('自訂全片秒數需介於 6–300 秒。');
const body={face_refine:$('face_refine').checked,upscale_1080p:$('upscale_1080p').checked,face_refine_reference:Number($('face_refine_reference').value),face_refine_reference_2:$('face_refine_reference_2').value ? Number($('face_refine_reference_2').value) : null,script_review:!direct,project_name:$('project-name').value,prompt:$('prompt').value,image_slots:slots,
auto_director:$('auto-director').checked,genres:$('auto-director').checked?genreKeys.filter(k=>$('genre-'+k).checked):[],
duration_preference:chosenDuration==='prompt'?'prompt':chosenDuration==='custom'?'custom':'selector',
max_seconds:chosenDuration==='prompt'?300:chosenDuration==='custom'?customDuration:Number(chosenDuration),segment_seconds:$('segment').value==='auto'?'auto':Number($('segment').value),visual_style:$('visual-style').value,sound_mode:$('sound-mode').value,mode:modeAtSubmit,aspect:$('aspect').value,width:widths[$('resolution').value][$('aspect').value],intensity:$('intensity').value,seed:$('seed').value,kitchen_attention:$('kitchen').checked,sparse_attention:$('sparse').checked,motion_lora:$('motion').checked,rewrite_retries:2};const job=await api(direct?'api/film/start':'api/film/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});active=job.id;localStorage.setItem('banana_film_job',active);renderJob(job);if(job.request?.mode!==modeAtSubmit)throw Error(`已建立作品 ${job.id}，但接續模式不一致：送出 ${modeAtSubmit}，後端回傳 ${job.request?.mode||'未提供'}。請勿直接開拍，先檢查設定。`);await poll();}catch(error){busy(false);$('status').textContent=error.message;}};

const genreKeys=['comedy','cinematic','drama','action','romance','bl','sports','scifi','horror'];
let scriptKey='',scriptRows=[];
function addScriptRow(row={seconds:6,mode:'story',brief:''}){
 const card=document.createElement('div');card.className='script-scene';
 const label=document.createElement('label');label.textContent='段落秒數 / 拍攝模式';
 const seconds=document.createElement('input');seconds.type='number';seconds.min=124/24;seconds.max=currentJob?.request?.segment_seconds||15;seconds.step='any';seconds.value=row.seconds;seconds.oninput=scriptDuration;
 const mode=document.createElement('select');for(const [value,text] of [['story','劇情'],['action','動作']]){const o=document.createElement('option');o.value=value;o.textContent=text;mode.append(o);}mode.value=row.mode;
 const brief=document.createElement('textarea');brief.value=row.brief;brief.maxLength=currentJob?.request?.manual_h3?30000:5000;brief.setAttribute('aria-label','段落劇本');
 const remove=document.createElement('button');remove.type='button';remove.className='secondary';remove.textContent='刪除此段';
 const item={card,seconds,mode,brief};remove.onclick=()=>{scriptRows=scriptRows.filter(x=>x!==item);card.remove();scriptDuration();};
 card.append(label,seconds,mode,brief,remove);scriptRows.push(item);$('script-scenes').append(card);scriptDuration();
}
function scriptDuration(){const total=scriptRows.reduce((v,r)=>v+Number(r.seconds.value),0);$('script-duration').textContent=`草稿 ${total.toFixed(2)} 秒 / 上限 ${currentJob?.request?.max_seconds||0} 秒（送出時對齊 H3 幀數）`;}
function loadScript(draft){$('script-title').value=draft.title;$('script-scenes').replaceChildren();scriptRows=[];for(const row of draft.segments)addScriptRow(row);}
function collectScript(){return {title:$('script-title').value,segments:scriptRows.map(r=>({seconds:Number(r.seconds.value),mode:r.mode.value,brief:r.brief.value}))};}
function renderScript(j){$('script-review').hidden=j.status!=='script_ready';if(j.status!=='script_ready')return;
$('script-revise').hidden=!!j.request?.manual_h3;
$('script-instruction').hidden=!!j.request?.manual_h3;const key=j.id+':'+j.script_revision;if(scriptKey===key)return;scriptKey=key;loadScript(j.script_draft);$('script-history').replaceChildren();for(const [i,v] of (j.script_history||[]).entries()){const o=document.createElement('option');o.value=i;o.textContent=`第 ${i+1} 次修改前 · ${v.note||'原稿'}`;$('script-history').append(o);}}
$('script-add').onclick=()=>addScriptRow();
$('script-restore').onclick=()=>{const old=currentJob?.script_history?.[Number($('script-history').value)];if(old){loadScript(old.script);$('script-feedback').textContent='已載入舊版草稿；儲存或確認開拍才會採用。';}};
async function scriptAction(kind){const buttons=['generate','direct-render','open-project','refresh-projects','script-save','script-render','script-revise','script-add','script-restore'];try{for(const id of buttons)$(id).disabled=true;$('script-feedback').textContent=kind==='revise'?'導演正在細修目前這版…':'正在處理劇本…';const body={id:active,revision:currentJob.script_revision,script:collectScript(),instruction:$('script-instruction').value};const j=await api('api/film/'+kind,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});renderJob(j);$('script-feedback').textContent=kind==='render'?'已確認，開始開拍。':kind==='revise'?'細修完成，請檢視新版。':'已儲存劇本。';if(kind==='render')await poll();}catch(e){$('script-feedback').textContent=e.message;}finally{for(const id of buttons)$(id).disabled=false;const running=currentJob&&!terminal.includes(currentJob.status);for(const id of ['generate','direct-render','open-project','refresh-projects'])$(id).disabled=!!running;}}
$('script-save').onclick=()=>scriptAction('script');$('script-render').onclick=()=>scriptAction('render');$('script-revise').onclick=()=>scriptAction('revise');

function updateFilmControls(){
 const auto=$('auto-director').checked;
 $('manual-h3-help').hidden=auto;
 for(const genre of genreKeys)$('genre-'+genre).disabled=!auto;
 const custom=$('max-seconds').value==='custom';
 $('custom-seconds').hidden=!custom;
 $('custom-seconds-label').hidden=!custom;
 $('custom-seconds').required=custom;
 $('generate').textContent=!auto&&/^(?:\s*subject_definitions\s*:|\s*===\s*CLIP\s)/i.test($('prompt').value)
   ?'驗證完整 H3 全咒 →':'生成劇本 →';
}
$('auto-director').addEventListener('change',updateFilmControls);
$('max-seconds').addEventListener('change',updateFilmControls);
updateFilmControls();

// The 5070 backend exposes a new instance ID on every real furnace restart.
// Browser localStorage survives process restarts, so reattach an old job only
// while the same backend instance is alive. Stored movies/jobs are not deleted.
function clearFilmWorkspaceCache(){
 clearTimeout(timer);
 active=null;currentJob=null;stopRequested=null;scriptKey='';
 localStorage.removeItem('banana_film_job');
 if(typeof localStorage.key==='function'){
  const obsolete=[];
  for(let i=0;i<localStorage.length;i++){
   const key=localStorage.key(i);
   if(key&&key.startsWith('banana_film_clip_prompts:'))obsolete.push(key);
  }
  for(const key of obsolete)localStorage.removeItem(key);
 }
 $('form').reset?.();
 selected=Array(9).fill(null);
 for(let i=1;i<=9;i++)$('image-'+i).value='';
 $('prompt').value='';
 refs();
 promptCount();
 updateFilmControls();
 $('script-review').hidden=true;
 $('plan-panel').hidden=true;
 $('prompt-panel').hidden=true;
 renderFinalPreviews({});
 $('status').textContent='新丹爐已啟動。介面已清空；歷史作品仍可從作品清單開啟。';
 busy(false);
}

async function restoreFilmWorkspace(){
 const saved=localStorage.getItem('banana_film_job');
 let instance=null;
 try{
  const health=await api('api/health',{cache:'no-store'});
  instance=typeof health.instance==='string'&&health.instance?health.instance:null;
 }catch{}
 if(!instance){
  // Compatibility with the shared Colab frontend, which may lack a boot ID.
  if(saved){active=saved;busy(true);void poll(true);}
  return;
 }
 const key='banana_film_backend_instance';
 const prior=sessionStorage.getItem(key);
 sessionStorage.setItem(key,instance);
 if(prior===instance && saved){
  active=saved;busy(true);void poll(true);
 }else if(prior!==instance){
  clearFilmWorkspaceCache();
 }
}
void restoreFilmWorkspace();
