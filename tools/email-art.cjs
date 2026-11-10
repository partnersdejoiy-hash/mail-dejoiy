/* Builds the art used in outgoing mail: an animated :D banner per label colour and the footer logo.
   Mail apps run no scripts or CSS animation, so the motion is baked into GIFs.
   Run: node tools/email-art.cjs  (needs Playwright + Chromium), then python3 tools/email-gif.py */
const {chromium} = require("playwright");
const path = require("path"), fs = require("fs");
const web = path.join(__dirname, "..", "web"), out = path.join(__dirname, "..", ".email-frames");
const font = "file://" + path.join(web, "assets/fonts/bricolage-grotesque-latin-wght-normal.woff2");
const TONES = {important:["#FF4FA3","Important"], urgent:["#FF5A5F","Urgent"], money:["#FF8A3D","Money"], work:["#FFD23F","Work"],
  personal:["#3DDC84","Personal"], ideas:["#B892FF","Ideas"], updates:["#4DA3FF","Updates"], mail:["#FF4FA3","New mail"]};
const FRAMES = 20, LOOP = 1600; // ms

const page = (bg, word) => `<!doctype html><html><head><style>
@font-face{font-family:B;src:url(${font}) format("woff2");font-weight:200 800}
*{margin:0;box-sizing:border-box}html,body{width:1200px;height:300px;overflow:hidden;background:${bg}}
body{font-family:B,sans-serif;position:relative;color:#121212}
.d{position:absolute;left:70px;top:46px;width:208px;height:208px;animation:bob ${LOOP}ms cubic-bezier(.45,0,.55,1) infinite}
.d svg{width:100%;height:100%;overflow:visible;filter:drop-shadow(8px 8px 0 #121212)}
.eye{transform-box:fill-box;transform-origin:center;animation:wink ${LOOP}ms infinite}
.word{position:absolute;left:330px;top:58px;font-size:132px;font-weight:800;letter-spacing:-.05em;line-height:1;white-space:nowrap}
.via{position:absolute;left:336px;top:210px;font-size:30px;font-weight:700;letter-spacing:-.01em;background:#121212;color:#fff;padding:8px 18px;border-radius:999px}
.s{position:absolute;background:#fff;border:6px solid #121212;border-radius:50%;animation:pop ${LOOP}ms infinite}
.star{position:absolute;width:64px;height:64px;animation:spin ${LOOP}ms linear infinite}
@keyframes bob{0%,100%{transform:translateY(0) rotate(-6deg)}50%{transform:translateY(-14px) rotate(5deg)}}
@keyframes wink{0%,62%,78%,100%{transform:scaleY(1)}70%{transform:scaleY(.1)}}
@keyframes tilt{0%,100%{transform:rotate(-1.5deg)}50%{transform:rotate(1.5deg) translateX(6px)}}
@keyframes pop{0%,100%{transform:scale(.7)}50%{transform:scale(1.15)}}
@keyframes spin{to{transform:rotate(90deg)}}
</style></head><body>
<div class="d"><svg viewBox="0 -25 150 150"><path d="M18 -20H80A70 70 0 0 1 80 120H18A18 18 0 0 1 0 102V-2A18 18 0 0 1 18 -20Z" fill="#FFFFFF" stroke="#121212" stroke-width="7"/>
<g transform="translate(22 17) scale(.66)"><circle class="eye" cx="13" cy="28" r="12" fill="#FF4FA3" stroke="#121212" stroke-width="6"/><circle cx="13" cy="72" r="12" fill="#121212"/>
<path fill-rule="evenodd" d="M38 0H88A50 50 0 0 1 88 100H38Z M62 26H86A24 24 0 0 1 86 74H62Z" fill="#121212"/></g></svg></div>
<div class="word">${word}</div><div class="via">via Dejoiy Mail</div>
<i class="s" style="right:96px;top:40px;width:54px;height:54px"></i><i class="s" style="right:190px;bottom:36px;width:34px;height:34px;animation-delay:-${LOOP/2}ms"></i>
<svg class="star" style="right:58px;bottom:62px" viewBox="0 0 64 64"><path d="M32 2 38 26 62 32 38 38 32 62 26 38 2 32 26 26Z" fill="#121212"/></svg>
</body></html>`;

(async () => {
  fs.mkdirSync(out, {recursive:true});
  const b = await chromium.launch(), p = await b.newPage({viewport:{width:1200,height:300}});
  for(const [key,[bg,word]] of Object.entries(TONES)){
    await p.setContent(page(bg, word)); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(200);
    for(let i=0;i<FRAMES;i++){
      await p.evaluate(t => document.getAnimations().forEach(a => { a.pause(); a.currentTime = t; }), i*LOOP/FRAMES);
      await p.screenshot({path:path.join(out, `${key}_${String(i).padStart(2,"0")}.png`)});
    }
  }
  // Footer logo on its own white sticker, so it reads on light and dark mail apps alike.
  const mark = fs.readFileSync(path.join(web, "assets/brand/dejoiy-mail.svg"), "utf8");
  await p.setViewportSize({width:420,height:110});
  await p.setContent(`<body style="margin:0;background:transparent"><div style="display:inline-flex;align-items:center;padding:16px 26px;background:#fff;border:5px solid #121212;border-radius:999px;box-shadow:6px 6px 0 #121212;margin:4px 12px 12px 4px">
    <div style="width:310px;height:61px">${mark.replace("<svg ", '<svg width="310" height="61" ')}</div></div></body>`);
  await p.locator("body > div").screenshot({path:path.join(web, "assets/mail/footer-logo.png"), omitBackground:true});
  await b.close(); console.log(Object.keys(TONES).join(" "));
})();
