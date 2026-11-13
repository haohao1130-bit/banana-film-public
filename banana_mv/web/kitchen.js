/* BANANA FILM V2 kitchen show: existing mascot SVG traced from banana_mv/web/film.html. */
(function () {
'use strict';
const DISHES=[["🍗","宮保雞丁"],["🥘","三杯雞"],["🍤","鳳梨蝦球"],["🐟","清蒸石斑"],["🥟","水晶蝦餃"],["🍚","櫻花蝦炒飯"],["🦀","避風塘炒蟹"],["🍖","糖醋排骨"],["🍜","紅燒牛肉麵"],["🥬","開陽白菜"],["🍲","佛跳牆"],["🦑","三杯中卷"],["🥩","黑椒牛柳"],["🍳","蟹黃豆腐"],["🫕","麻辣鴨血"],["🦐","蒜蓉粉絲蝦"],["🧆","獅子頭"],["🍱","蒲燒鰻魚"],["🥗","涼拌海蜇"],["🌽","金沙玉米"],["🥠","椒鹽杏鮑菇"],["🍛","咖哩牛腩"],["🥒","醬爆黃瓜"],["🦆","脆皮烤鴨"],["🥦","蠔油雙菇"],["🦪","蒜蒸扇貝"],["🫔","荷葉糯米雞"],["🍢","孜然羊肉串"],["🦞","上湯焗龍蝦"],["🥚","茶香滷蛋"],["🍠","拔絲地瓜"],["🍄","香菇扒菜心"],["🍣","花壽司"],["🐙","醬燒章魚"],["🥔","椒香土豆絲"],["🫛","臘味炒四季豆"],["🥕","紅燒獅子頭"],["🍝","XO醬炒麵"],["🍥","蟹肉蒸蛋"],["🥮","八寶甜芋泥"],["🍨","桂花杏仁豆腐"],["🍮","焦糖布丁"],["🍰","芋泥千層"],["🍡","芝麻湯圓"],["🥯","芝麻燒餅"],["🧁","桂花糕"],["🍓","草莓奶凍"],["🍌","香蕉宗門甜點"]];
const ART="<svg viewBox=\"0 0 620 310\" role=\"img\" aria-labelledby=\"kitchen-svg-title\" xmlns=\"http://www.w3.org/2000/svg\">\n<title id=\"kitchen-svg-title\">蕉彌投入食材，蕉大師拿鍋鏟爆炒，每完成一段短片就有一道菜上桌</title>\n<defs><linearGradient id=\"kitchen-wood\" x1=\"0\" y1=\"0\" x2=\"0\" y2=\"1\"><stop stop-color=\"#8d5d37\"/><stop offset=\"1\" stop-color=\"#493123\"/></linearGradient><linearGradient id=\"kitchen-pan\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\"><stop stop-color=\"#bac6bf\"/><stop offset=\".56\" stop-color=\"#303d38\"/><stop offset=\"1\" stop-color=\"#161e1c\"/></linearGradient><radialGradient id=\"kitchen-glow\"><stop stop-color=\"#efbd72\" stop-opacity=\".45\"/><stop offset=\"1\" stop-color=\"#efbd72\" stop-opacity=\"0\"/></radialGradient></defs>\n<rect x=\"0\" y=\"0\" width=\"620\" height=\"310\" rx=\"17\" fill=\"#18221b\"/>\n<circle cx=\"312\" cy=\"158\" r=\"162\" fill=\"url(#kitchen-glow)\"/>\n<g fill=\"none\" stroke=\"#cdb285\" opacity=\".22\"><path d=\"M24 47h571M24 89h571M24 47v236m571-236v236\"/><path d=\"M263 34v48m104-48v48\"/><path d=\"M38 285h544\"/></g>\n<g class=\"kitchen-shelf\"><path d=\"M212 72h196\" stroke=\"#b18c5c\" stroke-width=\"7\" stroke-linecap=\"round\"/><rect x=\"241\" y=\"39\" width=\"22\" height=\"32\" rx=\"4\" fill=\"#c68b51\"/><rect x=\"276\" y=\"47\" width=\"16\" height=\"24\" rx=\"4\" fill=\"#6e9570\"/><path d=\"M325 51h18l-3 20h-12Z\" fill=\"#d8ac7a\"/><path d=\"M366 43q16-8 31 0v28h-31Z\" fill=\"#a4c1a8\"/></g>\n<path d=\"M18 276h585\" stroke=\"#8d6849\" stroke-width=\"15\" stroke-linecap=\"round\"/>\n<g class=\"kitchen-stove\"><rect x=\"242\" y=\"222\" width=\"142\" height=\"55\" rx=\"11\" fill=\"#4d5a53\" stroke=\"#a2a98c\" stroke-width=\"3\"/><path d=\"M256 254h116\" stroke=\"#1b2724\" stroke-width=\"5\"/><circle cx=\"274\" cy=\"261\" r=\"5\" fill=\"#d1b775\"/><circle cx=\"297\" cy=\"261\" r=\"5\" fill=\"#d1b775\"/><circle cx=\"320\" cy=\"261\" r=\"5\" fill=\"#d1b775\"/>\n<g class=\"kitchen-flames\"><path d=\"M274 227q-15-21 0-35-3 20 12 14 12-14 6-30 27 25 3 51Z\" fill=\"#f19b41\"/><path d=\"M310 227q-16-19 0-37-2 18 12 12 11-16 5-25 25 27 2 50Z\" fill=\"#ffd978\"/><path d=\"M347 227q-19-15 1-31-6 18 14 12 16-10 9-23 18 23-1 42Z\" fill=\"#e46e2b\"/></g>\n<ellipse cx=\"320\" cy=\"224\" rx=\"115\" ry=\"19\" fill=\"#202a27\" stroke=\"#acb9ad\" stroke-width=\"5\"/><path d=\"M211 221q9 50 109 50 101 0 113-50\" fill=\"url(#kitchen-pan)\" stroke=\"#829b90\" stroke-width=\"3\"/><path d=\"M215 221Q320 260 428 221\" stroke=\"#d1d4c1\" stroke-width=\"2\" fill=\"none\"/><path d=\"M431 225l45-8\" stroke=\"#697a70\" stroke-width=\"9\" stroke-linecap=\"round\"/><ellipse cx=\"319\" cy=\"211\" rx=\"80\" ry=\"11\" fill=\"#b58946\" opacity=\".7\"/></g>\n<g class=\"kitchen-ingredients\"><circle cx=\"185\" cy=\"139\" r=\"9\" fill=\"#76ad55\"/><path d=\"m174 134 11-9 9 8\" fill=\"none\" stroke=\"#d1df82\" stroke-width=\"4\"/><ellipse cx=\"171\" cy=\"140\" rx=\"7\" ry=\"5\" fill=\"#df9860\"/><ellipse cx=\"202\" cy=\"150\" rx=\"7\" ry=\"5\" fill=\"#9dbd68\"/></g>\n<g class=\"kitchen-steam\" fill=\"none\" stroke=\"#e1efcf\" stroke-width=\"6\" stroke-linecap=\"round\" opacity=\".58\"><path d=\"M292 188q-14-13 3-26t-1-23\"/><path d=\"M325 182q-13-10 4-25t0-22\"/><path d=\"M355 191q-15-13 1-25t1-22\"/></g>\n<g transform=\"translate(103 103)\" class=\"banana-helper\" aria-hidden=\"true\">\n  <ellipse cx=\"5\" cy=\"157\" rx=\"48\" ry=\"8\" fill=\"#080c09\" opacity=\".65\"/>\n  <path d=\"M33 117q49 18 43-17\" fill=\"none\" stroke=\"#d6b75d\" stroke-width=\"13\" stroke-linecap=\"round\"/>\n  <path d=\"M65 102q-12-21 7-26 21 4 11 24z\" fill=\"#63754b\" stroke=\"#acaa65\" stroke-width=\"1.5\"/>\n  <g class=\"banana-bob\">\n    <ellipse cx=\"-15\" cy=\"150\" rx=\"16\" ry=\"7\" fill=\"#6e5034\"/><ellipse cx=\"20\" cy=\"150\" rx=\"16\" ry=\"7\" fill=\"#6e5034\"/>\n    <path d=\"M-31 73Q-44 38-9 4q8-17 11-31l25 5q-3 33 12 65c20 38 13 72 4 93q-34 25-65 0Z\" fill=\"#e5c76e\" stroke=\"#ac8848\" stroke-width=\"2\"/>\n    <path d=\"M1-27l26 5 1 9q-13 3-28-5Z\" fill=\"#805438\"/>\n    <ellipse cx=\"2\" cy=\"106\" rx=\"31\" ry=\"34\" fill=\"#efe0b1\"/>\n    <path d=\"M-25 39Q-60 34-51 77q13 17 25-13M31 39q34-5 26 38-13 17-26-13\" fill=\"#e5c76e\" stroke=\"#ac8848\" stroke-width=\"1.5\"/>\n    <path d=\"M-34 46q-21 3-10 28M39 46q18 3 9 28\" fill=\"none\" stroke=\"#d69a8e\" stroke-width=\"9\" stroke-linecap=\"round\"/>\n    <ellipse cx=\"3\" cy=\"56\" rx=\"32\" ry=\"31\" fill=\"#f5e9ce\"/>\n    <path d=\"M-16 53q6-7 12 0m14 0q6-7 12 0\" fill=\"none\" stroke=\"#5c4331\" stroke-width=\"3\" stroke-linecap=\"round\"/>\n    <path d=\"M-1 61q4-4 8 0l-4 4Z\" fill=\"#bd8270\"/><path d=\"M3 65q-8 10-15 2m15-2q8 10 15 2\" fill=\"none\" stroke=\"#79533b\" stroke-width=\"1.5\"/>\n    <path d=\"M3 42c-13-1-11-16 0-16 12 0 10 12 3 12-5 0-5-6-1-6m-2-6v-7\" fill=\"none\" stroke=\"#c39137\" stroke-width=\"3\" stroke-linecap=\"round\"/>\n    <path d=\"M-26 92q-13 15-1 26l15-2\" fill=\"none\" stroke=\"#cfb35d\" stroke-width=\"13\" stroke-linecap=\"round\"/>\n    <g class=\"banana-throw-arm\"><path d=\"M29 92q22 0 37-15\" fill=\"none\" stroke=\"#e5c76e\" stroke-width=\"15\" stroke-linecap=\"round\"/><g class=\"ingredient-pouch\"><path d=\"M59 57q9-9 23 1l-2 24q-11 11-22-2Z\" fill=\"#648e4e\" stroke=\"#e1d29c\" stroke-width=\"2\"/><path d=\"M62 62q11 5 17 0M68 67q7 4 10 0\" fill=\"none\" stroke=\"#f2d78e\" stroke-width=\"2\"/></g></g>\n  </g>\n\n</g>\n<g transform=\"translate(512 101)\" class=\"master-helper\" aria-hidden=\"true\">\n    <ellipse cx=\"0\" cy=\"164\" rx=\"51\" ry=\"8\" fill=\"#080c09\" opacity=\".65\"/>\n  <path d=\"M-20 134l-3 25m41-25 3 25\" stroke=\"#727775\" stroke-width=\"14\" stroke-linecap=\"round\"/>\n  <path d=\"M-42 160h27m34 0h27\" stroke=\"#383f3c\" stroke-width=\"9\" stroke-linecap=\"round\"/>\n  <g class=\"master-flow\">\n    <path d=\"M-24 51q24-13 49 0l17 88q-42 17-83 0Z\" fill=\"#8c918d\" stroke=\"#b1afa0\" stroke-width=\"1.5\"/>\n    <path d=\"M10 46 30 60l15 79q-26 12-62 8l5-59Z\" fill=\"#b76e36\" stroke=\"#d4a066\" stroke-width=\"1.5\"/>\n    <path d=\"M10 46-16 82M-20 126q27-1 56-9M-11 93q22 3 41-5\" fill=\"none\" stroke=\"#e0b279\" stroke-opacity=\".5\" stroke-width=\"2\"/>\n    <g class=\"master-left-arm\"><path d=\"M-23 64Q-45 80-56 60\" fill=\"none\" stroke=\"#8c918d\" stroke-width=\"19\" stroke-linecap=\"round\"/><path d=\"M-56 60l-5-11m5 11 6-12\" stroke=\"#d6ad88\" stroke-width=\"6\" stroke-linecap=\"round\"/></g>\n    <g class=\"master-right-arm\"><path d=\"M24 65q27 11 15-25\" fill=\"none\" stroke=\"#b76e36\" stroke-width=\"17\" stroke-linecap=\"round\"/><path d=\"M39 40 51 -19\" stroke=\"#b88a55\" stroke-width=\"8\" stroke-linecap=\"round\"/><ellipse cx=\"53\" cy=\"-20\" rx=\"12\" ry=\"18\" transform=\"rotate(23 53 -20)\" fill=\"#bcc7be\" stroke=\"#71837e\" stroke-width=\"3\"/><path d=\"M49-32v24m7-24v24\" stroke=\"#71837e\" stroke-width=\"2\"/></g>\n    <path d=\"M-20 49q-8 34 21 39 28-7 18-39\" fill=\"none\" stroke=\"#d9b656\" stroke-width=\"6\" stroke-dasharray=\"1 7\" stroke-linecap=\"round\"/>\n    <circle cx=\"1\" cy=\"91\" r=\"7\" fill=\"#d9b656\"/><text x=\"1\" y=\"95\" text-anchor=\"middle\" fill=\"#79502e\" font-size=\"9\" font-weight=\"bold\">G</text>\n    <path d=\"M-8 43v12q8 7 16 0V43\" fill=\"#c69775\"/>\n    <ellipse cx=\"0\" cy=\"24\" rx=\"26\" ry=\"30\" fill=\"#d8b18b\" stroke=\"#aa805d\" stroke-width=\"1.5\"/>\n    <g class=\"chef-hat\" transform=\"translate(0 4)\"><path d=\"M-28 0q-12-10-1-24-1-15 15-19 7-17 20-13 17-4 24 13 16 7 12 20 8 10-5 23Z\" fill=\"#f1eee2\" stroke=\"#bfc6bb\" stroke-width=\"2\"/><rect x=\"-28\" y=\"-5\" width=\"60\" height=\"12\" rx=\"4\" fill=\"#f9f3e4\" stroke=\"#c6c8ba\" stroke-width=\"2\"/></g>\n    <ellipse cx=\"-26\" cy=\"27\" rx=\"4\" ry=\"7\" fill=\"#cfa37e\"/><ellipse cx=\"26\" cy=\"27\" rx=\"4\" ry=\"7\" fill=\"#cfa37e\"/>\n    <path d=\"M-18 16q7-5 12-1m12 0q7-4 12 1\" stroke=\"#5c4937\" stroke-width=\"2.5\" fill=\"none\" stroke-linecap=\"round\"/>\n    <path d=\"M-16 23q6 5 11 0m10 0q6 5 11 0\" stroke=\"#6f513b\" stroke-width=\"2\" fill=\"none\" stroke-linecap=\"round\"/>\n    <path d=\"M0 25l-2 9m-3 0q5 6 12 0\" stroke=\"#9b7152\" stroke-width=\"1.5\" fill=\"none\" stroke-linecap=\"round\"/>\n  </g>\n</g>\n<g class=\"kitchen-completion-stars\" fill=\"#f1d48d\"><path d=\"M310 49l7 16 18 3-14 12 4 17-15-8-15 8 4-17-14-12 18-3Z\"/><circle cx=\"244\" cy=\"113\" r=\"5\"/><circle cx=\"405\" cy=\"104\" r=\"6\"/></g>\n<text x=\"102\" y=\"300\" font-size=\"15\" text-anchor=\"middle\" fill=\"#e9ca7e\">蕉彌 · 下料</text><text x=\"510\" y=\"300\" font-size=\"15\" text-anchor=\"middle\" fill=\"#e9ca7e\">蕉大師 · 爆炒</text>\n</svg>";

const projector = document.getElementById('projector');
const hero = projector && projector.closest('.hero');
if (!projector || !hero) return;
projector.setAttribute('aria-label','蕉彌下料、蕉大師爆炒短片的製作狀態');
projector.innerHTML = ART;
const board = document.createElement('section');
board.id = 'banana-kitchen-board';
board.className = 'banana-kitchen-board';
board.setAttribute('aria-label', 'BANANA FILM 出菜進度');
board.innerHTML = '<div class="kitchen-board-head"><div><strong id="kitchen-title">蕉彌備料，蕉大師等開鍋</strong><p id="kitchen-message">故事下單後，每完成一段便出一道新菜。</p></div><span id="kitchen-count">0 / 0 道已出鍋</span></div><ol id="kitchen-dishes" class="kitchen-dishes" aria-label="已完成影片片段對應的菜色"></ol><div id="kitchen-banquet" class="kitchen-banquet" hidden><span aria-hidden="true">🍱 🥘 🦞 🍗 🥟 🍲 🦀</span><strong>滿漢全席上桌！</strong><small>全片完成，請享用本次佳餚</small></div>';
hero.after(board);
const title = document.getElementById('kitchen-title');
const message = document.getElementById('kitchen-message');
const count = document.getElementById('kitchen-count');
const banquet = document.getElementById('kitchen-banquet');
const plates = document.getElementById('kitchen-dishes');
const style = document.createElement('style');
style.id = 'banana-kitchen-style';
style.textContent = "\n.projector:after{display:none}\n.projector .kitchen-flames{opacity:.28}\n.projector[data-kitchen-state=\"preparing\"] .banana-throw-arm,\n.projector[data-kitchen-state=\"cooking\"] .banana-throw-arm,\n.projector[data-kitchen-state=\"retaking\"] .banana-throw-arm{\n  transform-box:fill-box;transform-origin:65% 15%;animation:kitchen-drop 2.4s ease-in-out infinite}\n.projector[data-kitchen-state=\"preparing\"] .ingredient-pouch,\n.projector[data-kitchen-state=\"cooking\"] .ingredient-pouch,\n.projector[data-kitchen-state=\"retaking\"] .ingredient-pouch{\n  transform-box:fill-box;transform-origin:center;animation:kitchen-pouch-drop 2.4s ease-in-out infinite}\n.projector[data-kitchen-state=\"cooking\"] .master-right-arm,\n.projector[data-kitchen-state=\"retaking\"] .master-right-arm{\n  transform-box:fill-box;transform-origin:20% 75%;animation:kitchen-stir .82s ease-in-out infinite alternate}\n.projector[data-kitchen-state=\"cooking\"] .kitchen-flames,\n.projector[data-kitchen-state=\"retaking\"] .kitchen-flames{\n  transform-box:fill-box;transform-origin:center bottom;animation:kitchen-flare .85s ease-in-out infinite alternate}\n.projector[data-kitchen-state=\"cooking\"] .kitchen-ingredients,\n.projector[data-kitchen-state=\"retaking\"] .kitchen-ingredients{\n  animation:kitchen-flip 1.7s ease-in-out infinite}\n.projector[data-kitchen-state=\"banquet\"] .kitchen-completion-stars{\n  animation:kitchen-sparkle 1.7s ease-in-out infinite}\n.banana-kitchen-board{border:1px solid #6c6543;border-radius:14px;background:linear-gradient(130deg,#28312b,#1c2423);padding:16px 20px;margin:0 0 24px}\n.kitchen-board-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}\n.kitchen-board-head strong{color:#f4d28d;font-size:16px}.kitchen-board-head p{color:#b8c1b9;margin:3px 0 0;font-size:12px}\n#kitchen-count{font:12px/1.5 ui-monospace,Consolas,monospace;color:#e8d6ac;white-space:nowrap}\n.kitchen-dishes{list-style:none;display:flex;flex-wrap:wrap;gap:9px;margin:13px 0 0;padding:0}.kitchen-dishes:empty{display:none}\n.kitchen-plate{display:flex;align-items:center;gap:8px;border:1px dashed #64746b;border-radius:12px;padding:7px 10px;background:#222e2b;min-width:124px;opacity:.72}\n.kitchen-plate-ready{opacity:1;border:1px solid #d0ad61;background:#3a3325}\n.kitchen-plate-cooking{border-color:#e3ae6c;box-shadow:0 0 0 2px #e3ae6c25}\n.plate-emoji{display:grid;place-items:center;border:2px solid #ab9170;background:#fbebc9;width:43px;height:43px;flex:none;border-radius:50%;font-size:23px;color:#31261a;box-shadow:inset 0 1px 3px #947c604a}\n.plate-desc{display:flex;flex-direction:column;gap:1px}.plate-desc small{font-size:10px;color:#b5beb3}.plate-desc strong{font-size:12px;color:#f1dba9}\n.kitchen-plate-new{animation:kitchen-plate-serve .7s cubic-bezier(.2,1.6,.35,1)}\n.kitchen-banquet{border-top:1px solid #826a46;margin:14px 0 0;padding:12px 8px 3px;display:flex;flex-direction:column;align-items:center;gap:4px;color:#f9d88d;text-align:center}\n.kitchen-banquet>span{font-size:24px;letter-spacing:5px}.kitchen-banquet>strong{font-size:clamp(20px,3vw,29px)}.kitchen-banquet>small{color:#cbd1bd}\n.kitchen-banquet.new{animation:kitchen-plate-serve .75s ease-out}\n@keyframes kitchen-drop{0%,14%,100%{transform:rotate(0)}37%,56%{transform:rotate(-18deg)}}\n@keyframes kitchen-pouch-drop{0%,16%,100%{transform:translate(0,0) rotate(0);opacity:1}34%,50%{transform:translate(21px,-14px) rotate(35deg);opacity:1}61%,82%{transform:translate(50px,24px) rotate(70deg);opacity:0}}\n@keyframes kitchen-stir{from{transform:rotate(-11deg) translateY(0)}to{transform:rotate(12deg) translateY(-5px)}}\n@keyframes kitchen-flare{from{transform:scaleY(.68);opacity:.68}to{transform:scaleY(1.14);opacity:1}}\n@keyframes kitchen-flip{0%,100%{transform:translateY(0)}50%{transform:translate(0,-21px)}}\n@keyframes kitchen-sparkle{0%,100%{opacity:.6;transform:scale(.8)}50%{opacity:1;transform:scale(1.12)}}\n@keyframes kitchen-plate-serve{0%{opacity:0;transform:translateY(-25px) scale(.6)}65%{opacity:1}100%{opacity:1;transform:translateY(0) scale(1)}}\n@media(max-width:520px){.banana-kitchen-board{padding:12px}.kitchen-plate{min-width:calc(50% - 5px)}.kitchen-banquet>span{font-size:19px;letter-spacing:2px}}\n@media(prefers-reduced-motion:reduce){.projector [class],.kitchen-plate-new,.kitchen-banquet.new{animation:none!important}}\n";
document.head.append(style);
let previousJobId = '';
let oldDone = new Set();
let previousBanquet = false;
let lastSignature = '';
function dishAt(index) {
  if (index < DISHES.length) return DISHES[index];
  return ['🍽️', '宗門特製第 ' + (index + 1) + ' 道'];
}
function render(job) {
  const segments = Array.isArray(job?.segments) ? job.segments : [];
  const finished = segments.filter(s=>s.status === 'done');
  const status = job?.status || 'idle';
  const current = Number.isInteger(job?.current) ? job.current : 0;
  let stage='idle',heading='蕉彌備料，蕉大師等開鍋',detail='故事下單後，每完成一段便出一道新菜。';
  if (status === 'planning_story' || status === 'revising_story') {
    stage='preparing';heading='蕉彌正在下料配菜';detail='9B 導演準備劇本，事件與鏡頭正逐道入鍋。';
  } else if (status === 'script_ready') {
    stage='review';heading='菜單備妥，等你確認';detail='導演劇本可修改；確認後才正式爆炒。';
  } else if (status === 'running') {
    stage='cooking';heading='蕉大師爆炒中';
    detail=current ? '第 ' + current + ' 道：H3 正在翻鍋製作短片。' : '整備鍋爐，開始逐段拍攝。';
  } else if (status === 'retaking') {
    stage='retaking';heading='蕉大師回鍋重炒';
    detail='重拍同一道菜，不會增加盤數；其他已完成菜色照留。';
  } else if (status === 'assembling') {
    stage='plating';heading='滿漢全席擺盤中';detail='每段已出鍋，正在剪接與合成原生影音。';
  } else if (status === 'done' && segments.length && finished.length === segments.length && (job?.video || job?.final_video)) {
    stage='banquet';heading='滿漢全席上桌！';detail='蕉彌與蕉大師完成全部 ' + finished.length + ' 道菜，整部影片可享用！';
  } else if (status === 'error') {
    stage='error';heading='這道火候出了狀況';detail='已完成的片段保留，可檢查錯誤後續跑。';
  } else if (status === 'interrupted' || status === 'cancelled') {
    stage='paused';heading='廚房暫停營業';detail='完成的盤數不重算，下次從剩餘片段接著炒。';
  } else if (status === 'done') {
    stage='plating';heading='正在確認宴席';detail='影片已結束，等待完整成片驗收。';
  }
  projector.dataset.kitchenState=stage;
  title.textContent=heading;message.textContent=detail;
  count.textContent=finished.length + ' / ' + segments.length + ' 道已出鍋';
  banquet.hidden = stage !== 'banquet';
  const id=String(job?.id||'');
  if (id !== previousJobId) {
    previousJobId=id;
    oldDone=new Set(finished.map(s=>Number(s.index)));
    previousBanquet=stage==='banquet';
  }
  const signature=JSON.stringify([id,status,current,segments.map(s=>[s.index,s.status,s.selected_take,s.take]),stage]);
  if (signature === lastSignature) return;
  lastSignature=signature;
  const newDone=new Set(finished.map(s=>Number(s.index)));
  plates.replaceChildren();
  for (const seg of segments) {
    const index = Number.isInteger(seg.index)?seg.index:segments.indexOf(seg);
    const [emoji,name]=dishAt(index);
    const ready=seg.status==='done';
    const item=document.createElement('li');
    item.className='kitchen-plate'+(ready?' kitchen-plate-ready':'');
    if (ready && !oldDone.has(index)) item.classList.add('kitchen-plate-new');
    if (!ready && current===index+1 && status==='running') item.classList.add('kitchen-plate-cooking');
    const icon=document.createElement('span');
    icon.className='plate-emoji';icon.setAttribute('aria-hidden','true');icon.textContent=ready?emoji:'🍽️';
    const desc=document.createElement('span');desc.className='plate-desc';
    const number=document.createElement('small');
    number.textContent='第 '+(index+1)+' 段'+(status==='retaking' && ready?' · 回鍋中':'');
    const nameText=document.createElement('strong');
    nameText.textContent=ready?name:(status==='running' && current===index+1?'爆炒中…':'待出鍋');
    desc.append(number,nameText);item.append(icon,desc);plates.append(item);
  }
  oldDone=newDone;
  if (stage==='banquet' && !previousBanquet) banquet.classList.add('new');
  else banquet.classList.remove('new');
  previousBanquet=stage==='banquet';
}
window.BananaKitchen=Object.freeze({render,dishCount:DISHES.length});
render(null);
})();