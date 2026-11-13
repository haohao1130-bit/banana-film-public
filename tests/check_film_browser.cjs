// Real Chromium input, mention selection and responsive layout; no GPU or rendering.
const assert=require('node:assert/strict'),fs=require('node:fs'),http=require('node:http'),path=require('node:path');
const {chromium}=require('playwright');
const web=path.resolve('banana_mv/web');
const server=http.createServer((req,res)=>{
 const name=req.url.split('?')[0];
 if(name.startsWith('/api/')){res.setHeader('Content-Type','application/json');res.end('[]');return;}
 const file=path.join(web,name==='/'?'film.html':name);
 if(!file.startsWith(web+path.sep)||!fs.existsSync(file)){res.writeHead(404);res.end();return;}
 res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':'text/html');res.end(fs.readFileSync(file));
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('http://127.0.0.1:'+server.address().port);
  // Real Chromium: chefs and serving board must respond only to real clip statuses.
  assert.equal(await page.locator('#banana-kitchen-board').count(),1);
  assert.equal(await page.locator('.projector .banana-helper').count(),1);
  assert.equal(await page.locator('.projector .master-helper').count(),1);
  const cooked={id:'kitchen-fixture',current:2,
    segments:[{index:0,status:'done'},{index:1,status:'rendering'}]};
  await page.evaluate(job=>window.BananaKitchen.render(job),{...cooked,status:'running'});
  assert.equal(await page.locator('#kitchen-dishes li').count(),2);
  assert((await page.locator('#kitchen-dishes li').first().textContent()).includes('宮保雞丁'));
  assert((await page.locator('#kitchen-dishes li').last().textContent()).includes('爆炒中'));
  assert.equal(await page.locator('#projector').getAttribute('data-kitchen-state'),'cooking');
  await page.evaluate(job=>window.BananaKitchen.render(job),{...cooked,status:'retaking'});
  assert.equal(await page.locator('#kitchen-dishes li').count(),2);
  await page.evaluate(job=>window.BananaKitchen.render(job),{
    ...cooked,status:'assembling',segments:[{index:0,status:'done'},{index:1,status:'done'}]});
  const plateNames=await page.locator('#kitchen-dishes li strong').allTextContents();
  assert.deepEqual(plateNames,['宮保雞丁','三杯雞']);
  await page.evaluate(job=>window.BananaKitchen.render(job),{
    ...cooked,status:'done',video:'/api/mv/file?id=kitchen-fixture',
    segments:[{index:0,status:'done'},{index:1,status:'done'}]});
  assert(await page.locator('#kitchen-banquet').isVisible());
  assert((await page.locator('#kitchen-title').textContent()).includes('滿漢全席'));
  const prompt=page.locator('#prompt');
  assert.equal(await page.locator('#mode').evaluate(e=>e.closest('details')),null);
  await page.evaluate(()=>{active='fixture';renderJob({id:'fixture',status:'running',duration:0,seed:0,segments:[],request:{max_seconds:180}});});
  assert(await page.locator('#stop').isVisible());
  assert.equal(await page.locator('#stop').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(181, 41, 50)');
  assert((await page.locator('#stop-hint').textContent()).includes('本段完成後停止'));
  await page.evaluate(()=>renderJob({id:'fixture',status:'done',duration:0,seed:0,segments:[]}));
  assert(await page.locator('#references').evaluate(e=>!!(e.compareDocumentPosition(document.getElementById('prompt'))&Node.DOCUMENT_POSITION_FOLLOWING)));
  await prompt.fill('x'.repeat(25000));await prompt.press('End');await prompt.press('a');
  assert.equal((await prompt.inputValue()).length,25001);
  assert.equal(await prompt.evaluate(e=>e.maxLength),-1);
  assert.equal(await prompt.evaluate(e=>e.checkValidity()),true);
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF1cAAAAASUVORK5CYII=','base64');
  await page.locator('#image-3').setInputFiles({name:'jpg',mimeType:'image/png',buffer:png});
  await prompt.fill('@');await prompt.press('End');
  await page.getByRole('option',{name:'@圖片3：jpg',exact:true}).waitFor();
  await prompt.press('Enter');assert.equal(await prompt.inputValue(),'@圖片3 ');
  await prompt.press('a');await prompt.press('Enter');assert((await prompt.inputValue()).endsWith('a\n'));
  await prompt.fill('@');await prompt.evaluate(e=>e.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true})));
  assert.equal(await page.locator('#image-mentions').isVisible(),false);
  assert.equal(await prompt.evaluate(e=>e.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',isComposing:true,bubbles:true,cancelable:true}))),true);
  await prompt.evaluate(e=>e.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true})));
  await page.getByRole('option',{name:'@圖片3：jpg',exact:true}).click();assert.equal(await prompt.inputValue(),'@圖片3 ');
  await prompt.fill('x'.repeat(30001));await prompt.press('a');assert.equal((await prompt.inputValue()).length,30002);
  assert.equal(await prompt.evaluate(e=>e.checkValidity()),false);
  assert((await page.locator('#prompt-count').textContent()).includes('超過上限'));
  // Product contract: AUTO remains default. OFF disables genre interference;
  // an authored H3 prompt is visibly treated as direct, not rewritten prose.
  assert.equal(await page.locator('#auto-director').isChecked(),true);
  assert.equal(await page.locator('#sound-mode').inputValue(),'auto');
  await page.locator('#auto-director').uncheck();
  assert(await page.locator('#genre-comedy').isDisabled());
  assert(await page.locator('#manual-h3-help').isVisible());
  await page.locator('#max-seconds').selectOption('custom');
  assert(await page.locator('#custom-seconds').isVisible());
  await page.locator('#custom-seconds').fill('35');
  await prompt.fill('=== CLIP 1 (12s) ===\nsubject_definitions:\n<Subject 1>...');
  assert((await page.locator('#generate').textContent()).includes('驗證完整 H3 全咒'));
  await page.locator('#auto-director').check();
  assert(await page.locator('#genre-comedy').isEnabled());
  assert(await page.locator('#manual-h3-help').isHidden());
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);
  console.log('Chromium checks passed: 25K typing, no truncation, fixed-slot mentions, normal Enter, composition guard, 30K validation and mobile layout.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>server.close());
