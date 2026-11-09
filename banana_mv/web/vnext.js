"use strict";
const $ = id => document.getElementById(id);
let current = localStorage.getItem("banana_vnext_project") || "";
let currentInfo = null, currentPlan = null, timer = null, busy = false, allPrompts = false;
let projectRequestSerial=0;
const selected = Array(9).fill(null);
const previewURLs = Array(9).fill(null);
const activeStatuses = new Set(["preparing", "rendering"]);
const mention={range:null,items:[],index:0,composing:false};
function closeMentions(){
  mention.range=null;mention.items=[];$("image-mentions").hidden=true;
  $("story").setAttribute("aria-expanded","false");
  $("story").removeAttribute("aria-activedescendant");
}
function insertReference(number,range){
  const input=$("story"),start=range?.start??input.selectionStart,end=range?.end??input.selectionEnd;
  const trailing=input.value[end],label="@圖片"+number+(trailing&&/\\s/.test(trailing)?"":" ");
  input.setRangeText(label,start,end,"end");closeMentions();input.focus({preventScroll:true});
  input.dispatchEvent(new Event("input",{bubbles:true}));
}
function highlightMention(){
  const buttons=$("image-mentions").querySelectorAll("button");
  buttons.forEach((button,i)=>button.setAttribute("aria-selected",String(i===mention.index)));
  if(buttons[mention.index]){
    $("story").setAttribute("aria-activedescendant",buttons[mention.index].id);
  }
}
function selectMention(index){
  const match=mention.items[index];
  if(match&&mention.range)insertReference(match.number,mention.range);
}
function updateMentions(event){
  text("char-count",[...$("story").value].length+" / 30000 字");
  const input=$("story"),menu=$("image-mentions");
  if(mention.composing||event?.isComposing||input.selectionStart!==input.selectionEnd){closeMentions();return;}
  const before=input.value.slice(0,input.selectionStart);
  const found= /@(?:圖片?|图片?|image)?[1-9]?$/i.exec(before);
  if(!found||(found.index>0&&/[a-z0-9_.]/i.test(before[found.index-1]))){closeMentions();return;}
  const number=found[0].match(/[1-9]$/)?.[0];
  mention.items=selected.flatMap((file,i)=>file&&(!number||Number(number)===i+1)?[{number:i+1,name:file.name,url:previewURLs[i]}]:[]);
  mention.index=0;mention.range={start:found.index,end:input.selectionStart};
  menu.replaceChildren();
  if(!mention.items.length) menu.append(h("p","muted","請先在上方選擇參考圖片。"));
  mention.items.forEach((item,i)=>{
    const button=h("button","mention-option");
    button.type="button";button.id="vnext-mention-"+item.number;button.setAttribute("role","option");
    button.setAttribute("aria-label","@圖片"+item.number+"："+item.name);
    const img=document.createElement("img");img.src=item.url;img.alt="";
    const caption=h("span","","@圖片"+item.number+" · "+item.name);
    button.append(img,caption);button.onpointerdown=e=>e.preventDefault();
    button.addEventListener("click",()=>selectMention(i));menu.append(button);
  });
  menu.hidden=false;input.setAttribute("aria-expanded","true");highlightMention();
}
function setupMentions(){
  const input=$("story");
  input.addEventListener("input",updateMentions);
  input.addEventListener("click",updateMentions);
  input.addEventListener("compositionstart",()=>{mention.composing=true;closeMentions();});
  input.addEventListener("compositionend",()=>{mention.composing=false;updateMentions();});
  input.addEventListener("blur",closeMentions);
  input.addEventListener("keydown",e=>{
    if(e.isComposing||mention.composing||e.keyCode===229||$("image-mentions").hidden)return;
    if(e.key==="Escape"){e.preventDefault();closeMentions();return;}
    if(!mention.items.length)return;
    if(e.key==="ArrowDown"||e.key==="ArrowUp"){
      e.preventDefault();mention.index=(mention.index+(e.key==="ArrowDown"?1:-1)+mention.items.length)%mention.items.length;highlightMention();
    }else if(e.key==="Enter"){e.preventDefault();selectMention(mention.index);}
    else if(e.key==="Tab")closeMentions();
  });
}


async function request(path, options) {
  const response = await fetch(path, {cache:"no-store", ...options});
  const raw = await response.text();
  let data;
  try { data = JSON.parse(raw); } catch (_) { throw new Error("伺服器回傳非 JSON，請確認 Colab 服務仍在。"); }
  if (!response.ok || data.error) throw new Error(data.error || "請求失敗");
  return data;
}
function post(path, body) {
  return request(path, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
}
function statusLabel(s) {
  return ({draft:"等待備稿",preparing:"9B 全片備稿中",ready:"已備稿待確認",rendering:"H3 拍攝中",
           done:"完成",interrupted:"中斷可續拍",error:"出錯可檢查"})[s] || "待命";
}
function text(id, value) { $(id).textContent = String(value); }
function show(id, visible) { $(id).hidden = !visible; }
function setBusy(value) { busy=value; $("prepare").disabled=value; $("refresh").disabled=value; $("new-project").disabled=value; $("projector").classList.toggle("working",value || activeStatuses.has(currentInfo?.status)); document.querySelectorAll("#references input, #references button").forEach(el=>el.disabled=value); }
function error(message) {
  show("error-panel", true);
  text("error-text", message);
  $("error-panel").scrollIntoView({behavior:"smooth",block:"nearest"});
}
function clearError() { show("error-panel", false); show("diagnostic-content",false); text("error-text",""); }
function setCurrent(id) {
  if(current!==id){projectRequestSerial++; currentPlan=null; currentInfo=null; clearTimeout(timer);timer=null; $("confirm-render").checked=false;}
  current=id; if (id) localStorage.setItem("banana_vnext_project",id);
  else localStorage.removeItem("banana_vnext_project");
  $("reload-project").disabled=!id;
}
async function loadProjects() {
  const data = await request("/api/projects");
  const container = $("projects");
  container.replaceChildren();
  if (!data.projects.length) {
    const p=document.createElement("p");p.className="muted";p.textContent="還沒有作品。";container.append(p);
  }
  for (const item of data.projects) {
    const button=document.createElement("button");
    button.className="project-item"+(item.id===current?" active":"");
    const title=document.createElement("strong"),meta=document.createElement("small");
    title.textContent=item.name;meta.textContent=statusLabel(item.status)+" · "+item.id;
    button.append(title,meta);
    button.addEventListener("click",()=>{setCurrent(item.id); loadProject(item.id,true).catch(e=>error(e.message));});
    container.append(button);
  }
}
function renderRefs() {
  const root=$("references");
  root.replaceChildren();
  for (let i=0;i<9;i++) {
    const card=document.createElement("label");
    card.className="ref-slot"+(selected[i]?" has-image":"");
    card.setAttribute("aria-label","參考圖片 "+(i+1));
    card.title="選擇 @圖片"+(i+1);
    const file=document.createElement("input");
    file.type="file";file.accept="image/png,image/jpeg,image/webp";file.disabled=busy;
    const container=document.createElement("div");container.className="slot-body";
    const label=document.createElement("span"),name=document.createElement("div");
    name.className="slot-name";label.textContent="📷 圖片 "+(i+1);
    name.textContent=selected[i]?.name || "點此上傳";
    if (selected[i]) {
      const img=document.createElement("img"); img.src=previewURLs[i];img.alt="第 "+(i+1)+" 張預覽";card.append(img);
      const remove=h("button","remove-ref","移除");remove.type="button";remove.disabled=busy;
      remove.setAttribute("aria-label","移除第 "+(i+1)+" 張參考圖");
      remove.addEventListener("click",e=>{e.preventDefault();e.stopPropagation();
        if(busy)return; if(previewURLs[i])URL.revokeObjectURL(previewURLs[i]);
        selected[i]=null;previewURLs[i]=null;renderRefs();updateMentions();
      });card.append(remove);
    }
    container.append(label,name);
    file.addEventListener("change",()=>{
      if(previewURLs[i]) URL.revokeObjectURL(previewURLs[i]);
      const chosen=file.files[0]||null;
      if(chosen&&!["image/png","image/jpeg","image/webp"].includes(chosen.type)){
        error("參考圖片僅接受 PNG、JPG、WEBP。"); selected[i]=null;previewURLs[i]=null;
      } else if(chosen&&chosen.size>12*1024*1024){
        error("單張參考圖片不得超過 12 MiB。");selected[i]=null;previewURLs[i]=null;
      } else {selected[i]=chosen;previewURLs[i]=chosen?URL.createObjectURL(chosen):null;clearError();}
      renderRefs();updateMentions();
    });
    card.append(container,file);root.append(card);
  }
}
function requestBody() {
  const story=$("story").value.trim();
  if (!story||[...story].length>30000) throw Error("請輸入 1–30000 字的全片劇情。");
  const indexes=selected.map((f,i)=>f?i:null).filter(i=>i!==null);
  if (!indexes.length) throw Error("目前 H3 Ref2VA 模式至少需要一張參考圖，請先上傳圖片 1。");
  if (indexes.some((index,i)=>index!==i)) throw Error("圖片必須從 1 號開始連續選取，不可跳格。");
  return {name:$("project-name").value.trim()||"未命名電影",story,
          genre:$("genre").value.trim(),max_seconds:Number($("max-seconds").value),
          width:$("aspect").value==="portrait"?720:1280,
          height:$("aspect").value==="portrait"?1280:720,
          chain5:$("chain5").checked,seed:Number($("seed").value)};
}
async function startPreproduction() {
  if (busy) return;
  clearError();
  let body;
  try { body=requestBody(); } catch(e) { error(e.message);return; }
  setBusy(true);
  text("current-step","建立新專案與上傳參考圖片");
  try {
    const created=await post("/api/create",body);
    setCurrent(created.id);
    let confirmed=[];
    for(let i=0;i<9;i++) {
      if(!selected[i]) continue;
      text("upload-status","⬆️ 正在傳送圖片 "+(i+1)+" / "+selected.filter(Boolean).length+"…");
      const response=await request("/api/upload?id="+encodeURIComponent(created.id)+"&slot="+(i+1), {
        method:"POST",headers:{"Content-Type":"application/octet-stream"},body:selected[i]
      });
      if(response.slot!==i+1)throw Error("伺服器圖片回覆格號不符："+(i+1));
      confirmed.push(i+1);
      text("upload-status","✅ 已成功傳送到 Colab："+confirmed.map(n=>"圖片"+n).join("、"));
    }
    const receipt=await request("/api/project?id="+encodeURIComponent(created.id));
    const persisted=JSON.stringify(receipt.picture_slots||[]);
    if(persisted!==JSON.stringify(confirmed)){
      throw Error("伺服器確認的圖片格號與上傳不一致：預期 "+JSON.stringify(confirmed)+"；實際 "+persisted+"。已停止備稿。");
    }
    await post("/api/prepare?id="+encodeURIComponent(created.id),{});
    await loadProject(created.id,false);
    await loadProjects();
    $("review-panel").scrollIntoView({behavior:"smooth"});
  } catch(e){text("upload-status","⚠️ 上傳或建立失敗，請看右側錯誤訊息。");error(e.message);} finally{setBusy(false);}
}
function h(tag,css,content) { const n=document.createElement(tag);if(css)n.className=css;if(content!==undefined)n.textContent=content;return n; }
function buildReview(data) {
  currentPlan={...data,id:current};
  const ready=data.ready, script=data.screenplay;
  const summary=$("plan-summary");summary.replaceChildren();
  [["片名",ready.title],["總時間",(ready.duration_ms/1000).toFixed(2)+" 秒"],["H3 段落",ready.clip_count+" 段"]].forEach(([label,value])=>{
    const div=h("div","summary-item");div.append(h("strong","",value),h("small","",label));summary.append(div);
  });
  show("camera-notice",Boolean(ready.camera_fallback));
  const root=$("shot-list");root.replaceChildren();
  for(let i=0;i<script.clips.length;i++){
    const clip=script.clips[i], details=h("details","shot");
    const heading=h("summary","",`第 ${i+1} 段｜${(clip.duration_ms/1000).toFixed(2)} 秒｜${clip.beats.length} 個事件`);
    const body=h("div","shot-body");
    body.append(h("p","opening","起始狀態："+clip.opening_state));
    clip.beats.forEach(beat=>{
      const row=h("div","beat");
      row.append(h("small","",`+${(beat.at_ms/1000).toFixed(2)}s｜事件 ${beat.id}`));
      row.append(h("p","",beat.action));
      if(beat.dialogue)row.append(h("p","",`角色 ${beat.speaker}：「${beat.dialogue}」`));
      body.append(row);
    });
    body.append(h("p","opening","結束狀態："+clip.outgoing_state));
    const pre=h("pre","h3-prompt",data.prompts[i]);
    pre.hidden=!allPrompts;
    const toggle=h("button","secondary small","檢視本段 H3 提示詞");
    toggle.addEventListener("click",()=>{pre.hidden=!pre.hidden;});
    body.append(toggle,pre);
    details.append(heading,body);root.append(details);
  }
  show("review-panel",true);
  $("render").disabled=!$("confirm-render").checked;
  show("output-panel", data.has_film || (data.completed_clips||[]).length>0);
}
function renderOutput(data) {
  const list=$("clip-list");list.replaceChildren();
  const clips=data.completed_clips || [];
  for(const index of clips) {
    const box=h("div","clip-card");
    box.append(h("h4","",`已完成片段 ${index+1}`));
    const player=document.createElement("video");
    player.controls=true;player.playsInline=true;player.preload="none";
    player.src="/api/clip?id="+encodeURIComponent(data.id)+"&index="+index;
    box.append(player);list.append(box);
  }
  show("film-view",Boolean(data.has_film));
  if(data.has_film) {
    const link="/api/film?id="+encodeURIComponent(data.id);
    if($("film-player").dataset.src!==link){$("film-player").src=link;$("film-player").dataset.src=link;}
    $("film-download").href=link;
    $("film-download").download="BananaFilmVNext_"+data.id+".mp4";
  }
  show("output-panel",Boolean(data.has_film||clips.length));
}
async function loadProject(pid, withPlan=true) {
  if(!pid)return;
  const serial=projectRequestSerial;
  const data=await request("/api/project?id="+encodeURIComponent(pid));
  if(current!==pid||serial!==projectRequestSerial)return;
  currentInfo=data;setCurrent(pid);
  text("current-project",data.name);
  text("current-step",data.step||statusLabel(data.status));
  text("status-chip",statusLabel(data.status));
  show("error-panel",data.status==="error"||Boolean(data.integrity_error));
  text("error-text",data.error||data.integrity_error||"");
  show("diagnostics",Boolean(data.has_raw_screenplay&&(data.status==="error")));
  show("progress-wrap",data.status==="rendering"||data.status==="preparing");
  const total=data.ready?.clip_count||0, done=(data.completed_clips||[]).length;
  $("progress").value=total?Math.round(done/total*100):0;
  text("progress-label",data.status==="preparing"?"9B 正在完成全片備稿；H3 尚未啟動。":
       `已完成 ${done}/${total} 段；每段拍完後自動保存。`);
  if(data.ready && (withPlan || !currentPlan || currentPlan.id!==pid)){
    try{const plan=await request("/api/plan?id="+encodeURIComponent(pid));
      if(current!==pid||serial!==projectRequestSerial)return;
      buildReview(plan);}
    catch(e){error(e.message);}
  }
  if(!data.ready){show("review-panel",false);currentPlan=null;}
  if(data.ready) {
    $("render").textContent = data.status==="done"?"↻ 重新合成／確認已完成影片":
        done>0?"🎥 從已完成片段繼續拍攝":"🎥 確認劇本，開始 H3 正式拍攝";
    $("render").disabled=!$("confirm-render").checked || activeStatuses.has(data.status);
  }
  renderOutput(data);
  $("projector").classList.toggle("working",activeStatuses.has(data.status)||busy);
  const canCreate=!activeStatuses.has(data.status);
  $("prepare").disabled=busy; // New projects remain possible; GPU lock serializes jobs.
  if(activeStatuses.has(data.status)) schedulePoll();
  else {clearTimeout(timer);timer=null;}
}
function schedulePoll() {
  clearTimeout(timer);
  const id=current;
  timer=setTimeout(()=>loadProject(id,true).then(()=>{if(current===id)return loadProjects();}).catch(e=>{if(current===id)error(e.message);}),3500);
}
async function renderFilm() {
  if(!current||!$("confirm-render").checked) return;
  clearError();
  $("render").disabled=true;
  try {await post("/api/render?id="+encodeURIComponent(current),{});await loadProject(current,false);}
  catch(e){error(e.message);$("render").disabled=false;}
}
async function diagnostics() {
  try{
    const data=await request("/api/diagnostic?id="+encodeURIComponent(current));
    const pre=$("diagnostic-content");
    pre.textContent=data.text||"(空白回覆)";
    show("diagnostic-content",true);
  }catch(e){error(e.message);}
}
function resetForm() {
  setCurrent("");currentInfo=null;currentPlan=null;
  text("current-project","尚未建立");text("current-step","輸入故事與角色");
  text("status-chip","待命");
  show("review-panel",false);show("output-panel",false);show("progress-wrap",false);
  $("confirm-render").checked=false;
  clearError();loadProjects().catch(e=>error(e.message));
  $("start-panel").scrollIntoView({behavior:"smooth"});
}
setupMentions();
$("prepare").addEventListener("click",startPreproduction);
$("render").addEventListener("click",renderFilm);
$("confirm-render").addEventListener("change",()=>{$("render").disabled=!$("confirm-render").checked||activeStatuses.has(currentInfo?.status);});
$("reload-project").addEventListener("click",()=>loadProject(current,true).catch(e=>error(e.message)));
$("refresh").addEventListener("click",()=>loadProjects().then(()=>current?loadProject(current,true):null).catch(e=>error(e.message)));
$("new-project").addEventListener("click",resetForm);
$("diagnostics").addEventListener("click",diagnostics);
$("show-all-prompts").addEventListener("click",()=>{
  allPrompts=!allPrompts;
  document.querySelectorAll(".h3-prompt").forEach(pre=>pre.hidden=!allPrompts);
});
$("copy-plan").addEventListener("click",async()=>{
  if(!currentPlan)return;
  const source=currentPlan.screenplay.clips.map((clip,i)=>
    `# ${i+1}｜${(clip.duration_ms/1000).toFixed(2)}s\n${clip.beats.map(b=>b.action+(b.dialogue?"「"+b.dialogue+"」":"")).join("\n")}\n結尾：${clip.outgoing_state}`).join("\n\n");
  try {await navigator.clipboard.writeText(source);text("current-step","全片劇本大綱已複製");}
  catch(_) {error("瀏覽器不允許複製。請展開各段檢視。");}
});
renderRefs();
request("/api/health").then(v=>{
  if(v.service!=="banana-film-vnext")throw Error("不是 VNext 伺服器");
  text("connection","服務已連線");$("connection").classList.add("ok");
  return loadProjects();
}).then(()=>current?loadProject(current,true):null).catch(e=>{
  text("connection","服務未連線");error(e.message);
});
