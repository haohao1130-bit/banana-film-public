// Keep video nodes and playback intact across status polls.
const clipView={job:null,rows:new Map(),jobData:null,locked:false,handled:null};
function clipIdle(){return !clipView.locked&&['done','error','cancelled','interrupted'].includes(clipView.jobData?.status);}
function updateClipActions(){
  let count=0;
  for(const row of clipView.rows.values()){
    row.check.disabled=clipView.locked;
    if(row.check.checked)count++;
    row.use.disabled=!clipIdle()||row.select.value===(row.segment.pending_take||row.segment.selected_take);
    row.correction.disabled=clipView.locked||['retaking','assembling','refining_faces'].includes(clipView.jobData?.status);
  }
  const pending=Object.keys(clipView.jobData?.pending_takes||{}).length;
  $('clips-condense').disabled=!clipIdle()||!pending||clipView.jobData?.segments?.some(s=>s.status!=='done');
  $('clips-condense').textContent=pending?`確認合成（${pending} 段待採用）`:'確認合成';
  $('clips-all').disabled=clipView.locked||!clipView.rows.size;
  $('clips-clear').disabled=clipView.locked||!count;
  $('clips-retake').disabled=!clipIdle()||!count;
  const film=clipView.jobData?.request?.production==='film';
  $('clips-retake').textContent=film?(count?`此菜未熟，送回去重炒（${count} 段）`:'此菜未熟，送回去重炒'):
    count?`重新炒菜（${count} 段）`:'重新炒菜';
}
function showClipVersion(row){
  const take=row.segment.takes.find(t=>t.id===row.select.value&&t.status==='ready');
  if(take&&row.url!==take.preview){row.url=take.preview;row.video.src=take.preview;}
  row.note.textContent=take?`V${take.version||1} · ${take.filename||''} · Seed：${take.seed}`+(take.correction?` · 局部修改：${take.correction}`:''):'';
  if(clipView.jobData?.request?.production==='film'&&take&&row.editTake!==take.id){
    const source=take.prompt||(take.id===row.segment.selected_take?row.segment.prompt:'')||'';
    const storage='banana_film_clip_prompts:'+clipView.job;
    let drafts={};
    try{drafts=JSON.parse(localStorage.getItem(storage)||'{}');}catch{}
    row.sourcePrompt=source;
    row.correction.value=Object.prototype.hasOwnProperty.call(drafts,row.index+':'+take.id)?
      drafts[row.index+':'+take.id]:source;
    row.editTake=take.id;
  }
  updateClipActions();
}
function renderClipPreviews(job){
  if(clipView.job!==job.id){clipView.job=job.id;clipView.rows.clear();clipView.handled=null;$('clip-list').replaceChildren();}
  clipView.jobData=job;
  $('clip-chain-note').hidden=!['chain','chain5'].includes(job.request?.mode);
  for(let i=0;i<(job.segments||[]).length;i++){
    const segment=job.segments[i];if(!segment.preview)continue;
    let row=clipView.rows.get(i);
    if(!row){
      const card=document.createElement('article');card.className='dan-card';
      const label=document.createElement('label'),check=document.createElement('input'),title=document.createElement('span');
      check.type='checkbox';label.append(check,title);
      const video=document.createElement('video');video.controls=true;video.muted=false;video.preload='none';video.playsInline=true;
      const version=document.createElement('div');version.className='dan-version';
      const select=document.createElement('select');select.setAttribute('aria-label',`第 ${i+1} 段鏡頭的版本`);
      const use=document.createElement('button');use.type='button';use.className='secondary';use.textContent='選用此版';
      const note=document.createElement('p');note.className='muted';version.append(select,use);card.append(label,video,version,note);$('clip-list').append(card);
      const film=job.request?.production==='film';
      const fixLabel=document.createElement('label');fixLabel.textContent=film?'本版實際 H3 攝影提示詞（可直接編輯）':'局部修改建議（選填）';
      const correction=document.createElement('textarea');correction.rows=film?12:3;correction.maxLength=film?30000:3000;
      correction.setAttribute('aria-label',`第 ${i+1} 段鏡頭的`+(film?'完整攝影提示詞':'局部修改建議'));
      correction.placeholder=film?'此版本攝影咒載入中；修改完整原稿後勾選重炒。原稿不變則只換 Seed。':'例如：表情更憤怒；增加手部操作特寫；保留事件，只改這段拍法。';
      const help=document.createElement('p');help.className='muted';help.textContent=film?
        '直接修改選中版本的完整攝影咒 → H3 拍攝，不經 9B；完全不改則只換 Seed。歷史版本不覆蓋，選用後再確認合成。':
        '以已選用的待採用版修改；未選則用目前成片版。留空只換 Seed。想改哪裡就在這裡交代，勾選此段後，9B 只修這道。';
      if(!film){try{correction.value=JSON.parse(localStorage.getItem('banana_film_clip_fixes:'+job.id)||'{}')[i]||'';}catch{}}
      correction.oninput=()=>{try{
        const key=film?'banana_film_clip_prompts:'+job.id:'banana_film_clip_fixes:'+job.id;
        const saved=JSON.parse(localStorage.getItem(key)||'{}');
        saved[film?(i+':'+(row?.editTake||'original')):i]=correction.value;
        localStorage.setItem(key,JSON.stringify(saved));
      }catch{}};
      fixLabel.append(correction);card.append(fixLabel,help);
      row={card,check,title,video,select,use,note,correction,segment,index:i};clipView.rows.set(i,row);
      check.onchange=updateClipActions;select.onchange=()=>showClipVersion(row);
      use.onclick=()=>adoptClip(row.index,row.select.value);
    }
    const desired=segment.pending_take||segment.selected_take;const changed=(row.segment.pending_take||row.segment.selected_take)!==desired;row.segment=segment;
    row.title.textContent=`${i===0?'第一道菜上桌':`第 ${i+1} 段`} · ${segment.start.toFixed(2)}–${(segment.start+segment.seconds).toFixed(2)} 秒｜可預覽、重拍或選版`;
    const ready=segment.takes.filter(t=>t.status==='ready');
    const signature=ready.map(t=>t.id+':'+(t.id===segment.selected_take)+':'+(t.id===desired)).join('|');
    if(row.signature!==signature){
      const previous=row.select.value;row.select.replaceChildren();
      for(const [n,take] of ready.entries()){
        const option=document.createElement('option');option.value=take.id;
        option.textContent=`V${take.version||(n+1)}${take.id==='original'?' · 初煉':take.kind==='face_refine'?' · 修臉':' · 重拍'}`+(take.id===segment.selected_take?' · 目前成片':'')+(take.id===desired&&desired!==segment.selected_take?' · 待合成':'');row.select.append(option);
      }
      row.select.value=changed||!ready.some(t=>t.id===previous)?desired:previous;row.signature=signature;
    }
    showClipVersion(row);
  }
  $('clip-review').hidden=!clipView.rows.size;
  const batch=job.retake,stamp=batch&&JSON.stringify([job.resumed,batch.takes,batch.indices,batch.status]);
  if(batch?.status==='done'&&clipView.handled!==stamp){for(const i of batch.indices||[])if(clipView.rows.has(i))clipView.rows.get(i).check.checked=false;clipView.handled=stamp;}
  if(batch?.status==='error'&&clipView.handled!==stamp){
    for(const [i,id] of Object.entries(batch.takes||{})){const row=clipView.rows.get(Number(i));if(row?.segment.takes.some(t=>t.id===id&&t.status==='ready'))row.check.checked=false;}
    clipView.handled=stamp;
  }
  $('clip-review-status').textContent=batch?.status==='error'?`重拍未完成：${batch.error} 原版保留；已完成新版可在版本選單預覽、選用；確認合成才更新成片。`:
    batch?.status==='done'?(batch.operation==='condense'?'合成完成，已另存完整新版。':'重拍完成，請逐顆預覽、選用，再確認合成。'):job.status==='retaking'?`重拍中：已完成 ${batch?.completed||0}／${batch?.indices?.length||0} 顆；完成後只存候選，不自動合成。`:
    job.status==='assembling'?'正在重新合成所選片段…':clipIdle()?'勾選需要重煉的片段，或選擇版本預覽與選用，再確認合成。':'可先預覽；請待這爐完成或停止後再重拍。';
  updateClipActions();
}
async function runClipAction(path,body){
  clipView.locked=true;updateClipActions();busy(true);
  try{
    const job=await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:active,...body})});
    renderClipPreviews(job);clearTimeout(timer);await poll();
  }catch(error){$('clip-review-status').textContent=error.message;busy(false);}
  finally{clipView.locked=false;updateClipActions();}
}
async function adoptClip(index,take){return runClipAction('api/mv/select-take',{index,take});}
$('clips-condense').onclick=()=>{if(clipIdle())return runClipAction('api/mv/condense',{revision:clipView.jobData.selection_revision});};
$('clips-all').onclick=()=>{if(clipView.locked)return;for(const row of clipView.rows.values())row.check.checked=true;updateClipActions();};
$('clips-clear').onclick=()=>{if(clipView.locked)return;for(const row of clipView.rows.values())row.check.checked=false;updateClipActions();};
$('clips-retake').onclick=()=>{
  if(!clipIdle())return;
  const indices=[...clipView.rows].filter(([,row])=>row.check.checked).map(([i])=>i);
  const film=clipView.jobData?.request?.production==='film';
  if(!film){
    const instructions=Object.fromEntries(indices.map(i=>[String(i),clipView.rows.get(i).correction.value.trim()]).filter(([,text])=>text));
    if(indices.length)return runClipAction('api/mv/retake',{indices,...(Object.keys(instructions).length?{instructions}:{})});
    return;
  }
  const bases=Object.fromEntries(indices.map(i=>[String(i),clipView.rows.get(i).select.value]));
  const prompts={};
  for(const i of indices){
    const row=clipView.rows.get(i),value=row.correction.value.trim(),source=(row.sourcePrompt||'').trim();
    if(value!==source){
      if(!value){$('clip-review-status').textContent=`第 ${i+1} 段攝影咒不能清空；只換 Seed 請保留原稿。`;return;}
      prompts[String(i)]=value;
    }
  }
  if(indices.length)return runClipAction('api/mv/retake',{indices,bases,...(Object.keys(prompts).length?{prompts}:{})});
};
if(active){busy(true);poll();}
