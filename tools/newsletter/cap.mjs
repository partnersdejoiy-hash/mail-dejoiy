import {chromium} from '/home/claude/.npm-global/lib/node_modules/playwright/index.mjs';
const [,,page_,sel,n,out,scale]=process.argv;
const b=await chromium.launch({args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const p=await b.newPage({deviceScaleFactor:Number(scale||1),viewport:{width:700,height:900}});
p.on('console',m=>console.log('console:',m.text()));p.on('pageerror',e=>console.log('err:',e.message));
await p.goto('http://127.0.0.1:8765/'+page_);await p.waitForFunction('window.ready===true',null,{timeout:30000});
const el=await p.$(sel);
for(let i=0;i<+n;i++){await p.evaluate(t=>window.renderAt(t),i/+n);await el.screenshot({path:`${out}_${String(i).padStart(3,'0')}.png`});}
await b.close();
