// Browser smoke test for VNext (no real 9B/H3 needed).
const assert=require('node:assert/strict');
const fs=require('node:fs'),http=require('node:http'),path=require('node:path');
const {chromium}=require('playwright');
const web=path.resolve('banana_mv/web');
const calls=[];
const server=http.createServer(async(req,res)=>{
 const pathname=new URL(req.url,'http://localhost').pathname;
 const answer=(code,payload)=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(payload));};
 if(pathname.startsWith('/api/')){
   calls.push([req.method,pathname]);
   if(pathname==='/api/health')return answer(200,{service:'banana-film-vnext'});
   if(pathname==='/api/projects')return answer(200,{projects:[]});
   if(pathname==='/api/create')return answer(201,{id:'0123456789ab',name:'測試電影',status:'draft'});
   if(pathname==='/api/upload')return answer(201,{slot:1,bytes:67});
   if(pathname==='/api/prepare')return answer(202,{id:'0123456789ab',status:'preparing'});
   if(pathname==='/api/project')return answer(200,{id:'0123456789ab',name:'測試電影',status:'preparing',step:'9B 正在備稿',completed_clips:[],picture_slots:[],has_film:false});
   return answer(404,{error:'not found'});
 }
 const file=path.join(web,pathname==='/'?'vnext.html':pathname);
 if(!file.startsWith(web+path.sep)||!fs.existsSync(file)){res.writeHead(404);return res.end('missing');}
 res.writeHead(200,{'Content-Type':file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'});
 res.end(fs.readFileSync(file));
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({executablePath:process.env.CHROME_BIN||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 try{
   const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
   page.on('pageerror',err=>errors.push(String(err)));
   await page.goto('http://127.0.0.1:'+server.address().port);
   await page.locator('#connection.ok').waitFor();
   assert.equal(await page.locator('#references input[type=file]').count(),9);
   assert.equal(await page.locator('#review-panel').isVisible(),false);
   const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF1cAAAAASUVORK5CYII=','base64');
   await page.locator('#references input[type=file]').first().setInputFiles({name:'role.png',mimeType:'image/png',buffer:png});
   await page.locator('#project-name').fill('測試電影');
   await page.locator('#story').fill('小語與蕉大師在日本庭院中練習詠春，動作因果連續，真正結局才停戰。');
   await page.locator('#prepare').click();
   await page.getByText('9B 全片備稿中').first().waitFor();
   assert(calls.some(([m,p])=>m==='POST'&&p==='/api/create'));
   assert(calls.some(([m,p])=>m==='POST'&&p==='/api/prepare'));
   assert.equal(await page.locator('#render').isVisible(),false);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   assert.deepEqual(errors,[]);
   console.log('VNext Chromium passed: mobile layout, 9-slot references, prompt editor, create/prepare APIs, safe H3 gating.');
 } finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>server.close());
