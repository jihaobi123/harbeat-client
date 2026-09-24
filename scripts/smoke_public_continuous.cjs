const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const url=process.env.HARBEAT_PUBLIC_URL||'https://8.136.120.255/listen/';
const out=path.resolve(process.env.HARBEAT_QA_OUT||'work/public-listen-smoke');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{})});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
  const errors=[],failed=[],requests=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400&&!r.url().endsWith('favicon.ico'))failed.push({url:r.url(),status:r.status()});if(r.url().includes('/media/'))requests.push(r.url())});
  await page.goto(url,{waitUntil:'networkidle'});
  const inventory=await page.evaluate(()=>fetch('./library.json').then(r=>r.json()));assert.equal(inventory.tracks.length,157);assert.equal(inventory.coverage.playable,157);
  assert.equal(await page.evaluate(()=>isSecureContext),true);
  console.log('CHECK inventory, HTTPS and responsive layout');await page.screenshot({path:path.join(out,'desktop.png')});
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.screenshot({path:path.join(out,'mobile.png')});
  await page.setViewportSize({width:1440,height:1000});await page.getByRole('checkbox',{name:'自动续播'}).uncheck();
  const search=page.getByRole('searchbox');await search.fill('The Spectre');const started=Date.now();await page.locator('.song-row button').first().click();
  await page.waitForFunction(()=>document.querySelector('.live-dot')?.textContent==='LIVE',null,{timeout:120000});const startupMs=Date.now()-started;
  await page.getByRole('button',{name:'Ⅱ 暂停',exact:true}).click();const progress=page.getByRole('slider',{name:'播放进度',exact:true});
  const paused=Number(await progress.inputValue());await page.waitForTimeout(450);assert(Math.abs(Number(await progress.inputValue())-paused)<.01);
  async function jump(seconds){await progress.fill(String(seconds));await progress.press('ArrowRight');await page.getByRole('button',{name:'▶ 继续播放',exact:true}).waitFor({timeout:90000});await page.getByRole('button',{name:'▶ 继续播放',exact:true}).click()}
  await jump(28);await page.waitForFunction(()=>Number(document.querySelector('input[aria-label="播放进度"]').value)>31,null,{timeout:45000});
  await page.getByRole('button',{name:'Ⅱ 暂停',exact:true}).click();await jump(148);await page.waitForFunction(()=>Number(document.querySelector('input[aria-label="播放进度"]').value)>152,null,{timeout:45000});
  await page.getByRole('slider',{name:'音量',exact:true}).fill('0.45');await page.getByRole('button',{name:'停止',exact:true}).click();
  console.log('CHECK pause and segment boundary seek');await search.fill('After LIKE');await page.locator('.song-row button').first().click();await page.waitForFunction(()=>document.querySelector('.live-dot')?.textContent==='LIVE',null,{timeout:120000});await page.waitForTimeout(600);await page.getByRole('button',{name:'停止',exact:true}).click();
  await search.fill('24K Magic');await page.locator('.song-row button').first().click();await page.waitForFunction(()=>document.querySelector('.live-dot')?.textContent==='LIVE',null,{timeout:120000});
  await page.getByRole('button',{name:'Ⅱ 暂停',exact:true}).click();await progress.fill('60');await progress.press('ArrowRight');
  await search.fill('Clap Clap');await page.locator('.song-row button').first().click();await page.waitForFunction(()=>document.querySelector('.prep-status')?.textContent.includes('素材已准备'),null,{timeout:120000});
  await page.getByRole('button',{name:'▶ 继续播放',exact:true}).click();await page.getByRole('button',{name:'现在接歌'}).click();await page.getByText('正在渐进交接',{exact:true}).waitFor({timeout:30000});
  console.log('CHECK live progressive handoff');await search.fill('FREE BRO');await page.locator('.song-row button').first().click();await page.getByText('当前交接完成后，会准备这首歌。',{exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('.now h2')?.textContent.includes('Clap Clap'),null,{timeout:30000});
  await page.waitForFunction(()=>document.querySelector('.prep-status')?.textContent.includes('素材已准备'),null,{timeout:120000});
  await page.getByRole('button',{name:'Ⅱ 暂停',exact:true}).click();await page.waitForTimeout(800);
  const sessions=await page.evaluate(()=>new Promise((resolve,reject)=>{const r=indexedDB.open('harbeat-mix-audit',1);r.onerror=()=>reject(r.error);r.onsuccess=()=>{const db=r.result,q=db.transaction('sessions').objectStore('sessions').getAll();q.onsuccess=()=>{resolve(q.result);db.close()};q.onerror=()=>reject(q.error)}}));
  const logs=sessions.flatMap(s=>s.logs);assert(logs.some(l=>l.kind==='plan_scheduled'&&l.plan.vocalOverlap&&l.plan.v30Eq));assert(logs.some(l=>l.kind==='handoff_state_commit'));
  assert(requests.length>5);assert(requests.every(u=>u.startsWith(new URL('media/',url).href)));assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);
  await page.screenshot({path:path.join(out,'playing-desktop.png')});await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.screenshot({path:path.join(out,'playing-mobile.png')});
  const proof={url:page.url(),inventory:inventory.coverage,secureContext:true,startupMs,cloudMediaRequests:requests.length,pausedSeek:true,segmentBoundaries:[30,150],handoff:true,thirdSongQueued:true,thirdSongPrepared:true,errors,failed,events:logs.filter(l=>['track_start','handoff_state_commit','native_segment_scheduled'].includes(l.kind))};
  fs.writeFileSync(path.join(out,'proof.json'),JSON.stringify(proof,null,2));console.log('PUBLIC_BROWSER_PASS',JSON.stringify({...proof,events:proof.events.length}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
