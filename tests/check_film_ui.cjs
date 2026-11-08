// Real film frontend scripts, mocked DOM/HTTP. GPU and browser layout are not tested.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('banana_mv/web/film.html','utf8');
class Element{
 constructor(){this.children=[];this.value='';this.files=[];this.dataset={};this.style={};this.events={};this.checked=false;this.classList={toggle(){}};}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=[...items];}
 removeAttribute(k){delete this[k];}remove(){}setAttribute(k,v){this[k]=v;}getAttribute(k){return this[k]||null;}
 addEventListener(k,v){this.events[k]=v;}focus(){}select(){this.selected=true;}
 setRangeText(text,a,b){this.value=this.value.slice(0,a)+text+this.value.slice(b);}
}
const els=Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],new Element()]));
const values={'mode':'independent','aspect':'16:9','resolution':'720p','segment':'10','max-seconds':'60','visual-style':'動畫','sound-mode':'dialogue','intensity':'extreme','prompt':'<script>not executable</script>故事','seed':'0','project-name':'短片'};
for(const [id,v]of Object.entries(values))els[id].value=v;
const posts=[],uploads=[],copied=[],store=new Map(),creationRoutes=[];
let status={id:'film123',title:'短片',status:'planning_story',seed:0,duration:0,segments:[],request:{production:'film',max_seconds:60,mode:'independent'}};
const context=vm.createContext({document:{getElementById:id=>{assert(els[id],id);return els[id];},createElement:()=>new Element()},console,
 URL:{createObjectURL:f=>'blob:'+f.name,revokeObjectURL(){}},setTimeout:()=>0,clearTimeout(){},navigator:{clipboard:{writeText:async t=>copied.push(t)}},
 localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},
 fetch:async(url,options)=>({ok:true,json:async()=>{
  if(url==='api/upload'){uploads.push(options.body);return {id:'ref'+uploads.length};}
  if(['api/film/plan','api/film/start'].includes(url)){creationRoutes.push(url);const body=JSON.parse(options.body);posts.push(body);status={...status,status:'planning_story',request:{...status.request,...body}};return status;}
  if(['api/film/script','api/film/revise','api/film/render'].includes(url)){posts.push(JSON.parse(options.body));status={...status,script_revision:'rev2',status:url.endsWith('/render')?'running':'script_ready',script_draft:JSON.parse(options.body).script};return status;}
  if(url.startsWith('api/mv/status'))return status;
  if(url==='api/mv/projects')return [{id:'film123',title:'短片',completed:1,total:1,status:'done'}];
  if(url==='api/mv/retake'){posts.push(JSON.parse(options.body));return {...status,status:'retaking'};}
  return {};
 }})});
vm.runInContext(fs.readFileSync('banana_mv/web/film.js','utf8'),context);
vm.runInContext(fs.readFileSync('banana_mv/web/film_review.js','utf8'),context);
(async()=>{
 assert(!els.song);assert(!els.lyrics);assert(html.includes('放映機'));assert(html.includes('無對白'));assert(html.includes('max-seconds'));
 els['image-1'].files=[{name:'one.jpg'}];els['image-1'].onchange();els['image-3'].files=[{name:'three.jpg'}];els['image-3'].onchange();assert.equal(els['name-1'].textContent,'one.jpg');assert.equal(els['name-3'].textContent,'three.jpg');els['remove-1'].onclick();assert.equal(els['name-3'].textContent,'three.jpg');els['auto-director'].checked=true;els['genre-comedy'].checked=true;
 await els.form.onsubmit({preventDefault(){}});assert.equal(posts.length,1);assert.equal(posts[0].script_review,true);assert.equal(creationRoutes[0],'api/film/plan');assert.deepEqual(posts[0].image_slots,[null,null,'ref1',null,null,null,null,null,null]);assert.equal(posts[0].auto_director,true);assert.deepEqual(posts[0].genres,['comedy']);assert.equal(posts[0].seed,'0');assert.equal(posts[0].max_seconds,60);assert.equal(posts[0].visual_style,'動畫');assert.equal(posts[0].sound_mode,'dialogue');assert(!('song_id'in posts[0]));assert.equal(store.get('banana_film_job'),'film123');
 status={...status,status:'script_ready',script_revision:'rev1',script_history:[],script_draft:{title:'初稿',segments:[{seconds:6,mode:'story',brief:'@圖片3 遞出信件，隨後停下等待對方回答。'}]}};await vm.runInContext('poll()',context);assert.equal(els['script-review'].hidden,false);vm.runInContext("scriptRows[0].brief.value='目前手動編輯的劇本';",context);await vm.runInContext('poll()',context);assert.equal(vm.runInContext('collectScript().segments[0].brief',context),'目前手動編輯的劇本');els['script-instruction'].value='結尾保留，開頭更快';await els['script-revise'].onclick();assert.equal(posts.at(-1).script.segments[0].brief,'目前手動編輯的劇本');assert.equal(status.status,'script_ready');assert.equal(els['script-render'].disabled,false);await els['script-render'].onclick();assert.equal(status.status,'running');
 status={...status,status:'done',duration:6,video:'/api/mv/file?id=film123',current_master:2,final_video:'/film/films/film123/final.mp4',
  final_versions:[{version:1,download:'/api/mv/file?id=film123&version=1'},{version:2,download:'/api/mv/file?id=film123&version=2'}],
  segments:[{index:0,start:0,seconds:6,status:'done',director_plan:{event:'Only local event'},prompt:'native filming prompt',preview:'/api/mv/clip?id=film123&index=0',selected_take:'original',takes:[{id:'original',status:'ready',seed:0,preview:'/api/mv/clip?id=film123&index=0'}]}]};
 await vm.runInContext('poll()',context);assert.equal(els.progress.value,1);assert.equal(els['master-list'].children.length,2);assert(els['output-location'].textContent.includes('final.mp4'));assert.equal(els.video.hidden,false);
 const row=vm.runInContext('clipView.rows.get(0)',context);assert.equal(row.video.muted,false);row.correction.value='只改燈光';row.correction.oninput();await vm.runInContext('poll()',context);assert.equal(vm.runInContext('clipView.rows.get(0).video',context),row.video);assert.equal(row.correction.value,'只改燈光');
 await els['copy-prompt'].onclick();assert.equal(copied[0],'native filming prompt');row.check.checked=true;await els['clips-retake'].onclick();assert.deepEqual(posts.at(-1).instructions,{'0':'只改燈光'});
 status={...status,status:'done'};await vm.runInContext('poll()',context);
 await els.form.onsubmit({preventDefault(){},submitter:{id:'direct-render'}});
 assert.equal(posts.at(-1).script_review,false);assert.equal(creationRoutes.at(-1),'api/film/start');assert.equal(els['direct-render'].disabled,true);assert.equal(els.generate.disabled,true);
 status={...status,status:'done'};await vm.runInContext('poll()',context);assert.equal(els['direct-render'].disabled,false);
 assert(html.indexOf('id="references"')<html.indexOf('id="prompt"'));
 assert(!html.match(/<textarea[^>]*id="prompt"[^>]*maxlength=/));
 els.prompt.selectionStart=1;els.prompt.selectionEnd=1;els.prompt.value='@';els.prompt.events.input({});
 assert.equal(els['image-mentions'].hidden,false);assert.equal(els['image-mentions'].children.length,1);
 assert.equal(els['image-mentions'].children[0].getAttribute('aria-label'),'@圖片3：three.jpg');
 let prevented=false;els.prompt.events.keydown({key:'x',preventDefault(){prevented=true;}});assert.equal(prevented,false);
 els.prompt.events.compositionstart();els.prompt.events.keydown({key:'Enter',isComposing:true,preventDefault(){prevented=true;}});assert.equal(prevented,false);assert.equal(els['image-mentions'].hidden,true);
 els.prompt.value='@';els.prompt.selectionStart=1;els.prompt.selectionEnd=1;els.prompt.events.compositionend();
 els.prompt.events.keydown({key:'Enter',preventDefault(){prevented=true;}});assert.equal(els.prompt.value,'@圖片3 ');
 els.prompt.value='a'.repeat(25000);els.prompt.selectionStart=25000;els.prompt.selectionEnd=25000;els.prompt.events.input({});assert(els['prompt-count'].textContent.includes('25000 / 30000'));assert.equal(els.prompt.getAttribute('aria-invalid'),'false');
 const requests=posts.length,uploaded=uploads.length;els.prompt.value='a'.repeat(30001);els.prompt.events.input({});await els.form.onsubmit({preventDefault(){}});assert.equal(posts.length,requests);assert.equal(uploads.length,uploaded);assert(els.status.textContent.includes('30000'));assert.equal(els.prompt.getAttribute('aria-invalid'),'true');
 assert(html.includes('value="auto" selected'));
 els.prompt.value='Dynamic story';els.segment.value='auto';
 status={...status,status:'done'};await vm.runInContext('poll()',context);await els.form.onsubmit({preventDefault(){}});assert.equal(posts.at(-1).segment_seconds,'auto');
 assert(html.includes('value="chain5"'));
 els.prompt.value='New motion scene';els.mode.value='chain5';
 status={...status,status:'done'};await vm.runInContext('poll()',context);await els.form.onsubmit({preventDefault(){}});assert.equal(posts.at(-1).mode,'chain5');
 assert(!html.match(/<button[^>]*id="stop"[^>]*class="secondary"/));
 status={...status,status:'running'};await vm.runInContext('poll()',context);assert.equal(els.stop.hidden,false);
 await els.stop.onclick();assert.equal(els.stop.disabled,true);await vm.runInContext('poll()',context);assert.equal(els.stop.disabled,true);assert(els.stop.textContent.includes('已要求停爐'));
 status={...status,status:'cancelled'};await vm.runInContext('poll()',context);assert.equal(els.stop.hidden,true);assert.equal(els['resume-project'].hidden,false);
 console.log('Film UI checks passed: story-only request, fixed image slots, zero seed, planning, native audio previews, stable correction drafts, versions and selective retakes.');
})().catch(e=>{console.error(e);process.exitCode=1;});
