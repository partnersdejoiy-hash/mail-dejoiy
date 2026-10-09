/* ============ Dejoiy Mail — live-themes.js : animated canvas backgrounds ============
   Every scene is original procedural art drawn as a pure function of time, so a frame can be
   rendered for a picker thumbnail exactly as it looks live. Runs at 30fps with a capped pixel
   ratio, pauses while the tab is hidden and shows one still frame under reduced motion. */
(function(){
"use strict";

const TAU=Math.PI*2;
function rng(seed){return function(){seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}
const wrap=(v,m)=>((v%m)+m)%m;
const range=(r,a,b)=>a+r()*(b-a);
const many=(n,make)=>Array.from({length:n},(_,i)=>make(i));

/* ---------- drawing helpers ---------- */
function sky(c,w,h,stops){const g=c.createLinearGradient(0,0,0,h);stops.forEach((s,i)=>g.addColorStop(i/(stops.length-1),s));c.fillStyle=g;c.fillRect(0,0,w,h);}
function glow(c,x,y,r,color){const g=c.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,color);g.addColorStop(1,"rgba(0,0,0,0)");c.fillStyle=g;c.beginPath();c.arc(x,y,r,0,TAU);c.fill();}
function hills(c,w,h,base,amp,freq,phase,color){c.fillStyle=color;c.beginPath();c.moveTo(0,h);for(let x=0;x<=w+8;x+=8)c.lineTo(x,base+Math.sin(x*freq+phase)*amp+Math.sin(x*freq*2.3+phase*1.7)*amp*.35);c.lineTo(w,h);c.closePath();c.fill();}
function cloud(c,x,y,s,color){c.fillStyle=color;c.beginPath();c.arc(x,y,20*s,0,TAU);c.arc(x+22*s,y-10*s,24*s,0,TAU);c.arc(x+48*s,y,20*s,0,TAU);c.arc(x+24*s,y+6*s,22*s,0,TAU);c.fill();}
function bird(c,x,y,s,flap,color){const f=Math.sin(flap)*6*s;c.strokeStyle=color;c.lineWidth=Math.max(1,1.6*s);c.lineCap="round";c.beginPath();c.moveTo(x-10*s,y-f);c.quadraticCurveTo(x-4*s,y-2*s,x,y);c.quadraticCurveTo(x+4*s,y-2*s,x+10*s,y-f);c.stroke();}
function oval(c,x,y,rx,ry,rot,color){c.save();c.translate(x,y);c.rotate(rot);c.fillStyle=color;c.beginPath();c.ellipse(0,0,rx,ry,0,0,TAU);c.fill();c.restore();}
function pine(c,x,base,hgt,color,sway){c.fillStyle=color;c.beginPath();for(let i=0;i<3;i++){const top=base-hgt+i*hgt*.25,wid=hgt*(.3+i*.1),lean=(sway||0)*(3-i);c.moveTo(x+lean,top);c.lineTo(x-wid/2,top+hgt*.45);c.lineTo(x+wid/2,top+hgt*.45);}c.fill();c.fillRect(x-hgt*.03,base-hgt*.13,hgt*.06,hgt*.13);}
function roundTree(c,x,base,s,trunk,leaves,sway){c.fillStyle=trunk;c.fillRect(x-4*s,base-40*s,8*s,40*s);c.fillStyle=leaves;c.beginPath();const o=sway*s;c.arc(x+o,base-52*s,22*s,0,TAU);c.arc(x-16*s+o,base-42*s,16*s,0,TAU);c.arc(x+16*s+o,base-42*s,16*s,0,TAU);c.fill();}
function acacia(c,x,base,s,color){c.strokeStyle=color;c.lineWidth=5*s;c.lineCap="round";c.beginPath();c.moveTo(x,base);c.lineTo(x+4*s,base-50*s);c.lineTo(x-18*s,base-74*s);c.moveTo(x+4*s,base-50*s);c.lineTo(x+24*s,base-78*s);c.stroke();oval(c,x+3*s,base-82*s,52*s,10*s,0,color);}
function ground(c,w,h,y,color){c.fillStyle=color;c.fillRect(0,y,w,h-y);}

/* Animals face right and stand on (x,y); p is the walk phase. */
function giraffe(c,x,y,k,p,body,spot){
  c.save();c.translate(x,y);c.scale(k,k);c.strokeStyle=body;c.lineCap="round";c.lineWidth=5;
  for(const [lx,o] of [[-22,0],[-14,Math.PI],[14,Math.PI],[22,0]]){const a=Math.sin(p+o)*.32;c.beginPath();c.moveTo(lx,-62);c.lineTo(lx+Math.sin(a)*62,-62+Math.cos(a)*62);c.stroke();}
  c.fillStyle=body;c.beginPath();c.ellipse(0,-70,34,17,-.08,0,TAU);c.fill();
  c.beginPath();c.moveTo(16,-82);c.lineTo(40,-150);c.lineTo(52,-147);c.lineTo(34,-72);c.closePath();c.fill();
  const nod=Math.sin(p*2)*.06;c.beginPath();c.ellipse(53,-152,13,7,.3+nod,0,TAU);c.fill();
  c.lineWidth=2.5;c.beginPath();c.moveTo(45,-158);c.lineTo(43,-168);c.moveTo(50,-160);c.lineTo(49,-170);c.stroke();
  c.lineWidth=2;c.beginPath();c.moveTo(-33,-73);c.quadraticCurveTo(-42,-60+Math.sin(p*2)*4,-40,-46);c.stroke();
  if(spot){c.fillStyle=spot;for(const [sx,sy,r] of [[-15,-74,6],[0,-66,5],[14,-76,5],[-4,-80,4],[22,-68,4],[33,-105,4],[39,-128,3.5],[28,-90,4],[-24,-66,4]]){c.beginPath();c.arc(sx,sy,r,0,TAU);c.fill();}}
  c.restore();
}
function elephant(c,x,y,k,p,body,ear){
  c.save();c.translate(x,y);c.scale(k,k);c.fillStyle=body;
  for(const [lx,o] of [[-30,0],[-14,Math.PI],[12,Math.PI],[28,0]]){const sw=Math.sin(p+o)*4;c.fillRect(lx-7+sw,-42,14,42);}
  c.beginPath();c.ellipse(0,-56,46,30,0,0,TAU);c.fill();
  c.beginPath();c.arc(44,-64,20,0,TAU);c.fill();
  c.strokeStyle=body;c.lineWidth=9;c.lineCap="round";c.beginPath();c.moveTo(58,-58);c.quadraticCurveTo(70+Math.sin(p)*4,-32,62+Math.sin(p*1.3)*6,-10);c.stroke();
  oval(c,34,-60,13,19,-.2+Math.sin(p*1.5)*.08,ear||body);
  c.lineWidth=3;c.beginPath();c.moveTo(-45,-62);c.lineTo(-52+Math.sin(p*2)*3,-40);c.stroke();
  if(ear){c.fillStyle="#1d1d1d";c.beginPath();c.arc(50,-70,2.2,0,TAU);c.fill();}
  c.restore();
}
function butterfly(c,x,y,s,flap,color){const o=Math.abs(Math.sin(flap));c.save();c.translate(x,y);c.scale(s,s);c.fillStyle=color;oval(c,-5*o,0,6*o+1,8,-.5,color);oval(c,5*o,0,6*o+1,8,.5,color);c.fillStyle="#2b2b2b";c.fillRect(-.8,-6,1.6,12);c.restore();}
function fish(c,x,y,s,dir,color,p){c.save();c.translate(x,y);c.scale(dir*s,s);c.fillStyle=color;c.beginPath();c.ellipse(0,0,18,9,0,0,TAU);c.fill();const wag=Math.sin(p)*4;c.beginPath();c.moveTo(-14,0);c.lineTo(-28,-9+wag);c.lineTo(-28,9+wag);c.closePath();c.fill();c.fillStyle="#fff";c.beginPath();c.arc(9,-2,3,0,TAU);c.fill();c.fillStyle="#123";c.beginPath();c.arc(10,-2,1.5,0,TAU);c.fill();c.restore();}

/* ---------- scenes: name, accent, init(w,h,r) → state, draw(c,w,h,t,s) ---------- */
const SCENES={
  zoo:{name:"Zoo Parade",accent:"#2f8f4e",
    init:(w,h,r)=>({clouds:many(5,()=>({x:r()*w,y:range(r,.06,.3)*h,s:range(r,.7,1.5),v:range(r,6,14)})),
      trees:many(7,i=>({x:(i+r()*.6)/7*w,s:range(r,.8,1.3)})),
      animals:[{kind:"giraffe",x:r()*w,v:22,k:.9},{kind:"elephant",x:r()*w,v:16,k:.85},{kind:"giraffe",x:r()*w,v:18,k:.65},{kind:"elephant",x:r()*w,v:13,k:.55}],
      flies:many(6,()=>({x:r()*w,y:range(r,.45,.8)*h,c:["#ff7aa2","#ffd23f","#7ad3ff","#c38bff"][Math.floor(r()*4)],p:r()*TAU})),
      birds:many(4,()=>({x:r()*w,y:range(r,.1,.3)*h,v:range(r,30,50),p:r()*TAU}))}),
    draw(c,w,h,t,s){
      sky(c,w,h,["#6ec3f4","#bfe6fb","#f4f9e9"]);glow(c,w*.84,h*.16,h*.22,"rgba(255,236,150,.85)");c.fillStyle="#ffe46b";c.beginPath();c.arc(w*.84,h*.16,h*.055,0,TAU);c.fill();
      for(const k of s.clouds)cloud(c,wrap(k.x+t*k.v,w+160)-80,k.y,k.s,"rgba(255,255,255,.92)");
      for(const b of s.birds)bird(c,wrap(b.x+t*b.v,w+60)-30,b.y+Math.sin(t+b.p)*8,1,t*8+b.p,"#35506b");
      hills(c,w,h,h*.62,h*.03,.006,1,"#9fd17a");hills(c,w,h,h*.7,h*.025,.009,3,"#7cbf5c");
      for(const tr of s.trees)roundTree(c,tr.x,h*.74,tr.s*h/700,"#7a5233","#4f9e45",Math.sin(t*.8+tr.x)*2);
      ground(c,w,h,h*.8,"#8cc760");
      const animals=[...s.animals].sort((a,b)=>a.k-b.k);
      for(const a of animals){const x=wrap(a.x+t*a.v,w+320)-160,base=h*(.78+(a.k-.5)*.2),k=a.k*h/650,p=t*a.v*.09;
        if(a.kind==="giraffe")giraffe(c,x,base,k,p,"#e7b24a","#9a5b22");else elephant(c,x,base,k,p,"#8e959e","#7b828b");}
      for(const f of s.flies)butterfly(c,f.x+Math.sin(t*.6+f.p)*60,f.y+Math.sin(t*1.3+f.p)*24,1.1,t*14+f.p,f.c);
    }},
  safari:{name:"Safari Sunset",accent:"#d9653b",
    init:(w,h,r)=>({trees:many(4,()=>({x:r()*w,s:range(r,.8,1.4)})),herd:many(5,i=>({kind:i%2?"elephant":"giraffe",x:r()*w,v:range(r,10,20),k:range(r,.5,.9)})),birds:many(7,()=>({x:r()*w,y:range(r,.15,.4)*h,v:range(r,20,40),p:r()*TAU}))}),
    draw(c,w,h,t,s){
      sky(c,w,h,["#2b1055","#7b2a6b","#e2574c","#f7a541","#fbd07c"]);const sy=h*.66;glow(c,w*.5,sy,h*.5,"rgba(255,190,90,.55)");c.fillStyle="#ffd36e";c.beginPath();c.arc(w*.5,sy,h*.12+Math.sin(t*.5)*2,0,TAU);c.fill();
      for(const b of s.birds)bird(c,wrap(b.x+t*b.v,w+60)-30,b.y+Math.sin(t*.8+b.p)*10,1.2,t*7+b.p,"#2a0f2a");
      hills(c,w,h,h*.76,h*.015,.005,2,"#3a1430");
      for(const tr of s.trees)acacia(c,tr.x,h*.8,tr.s*h/650,"#1b0b1e");
      ground(c,w,h,h*.8,"#1b0b1e");
      for(const a of [...s.herd].sort((a,b)=>a.k-b.k)){const x=wrap(a.x+t*a.v,w+320)-160,k=a.k*h/650,p=t*a.v*.09;
        if(a.kind==="giraffe")giraffe(c,x,h*.81,k,p,"#1b0b1e");else elephant(c,x,h*.81,k,p,"#1b0b1e");}
    }},
  liveforest:{name:"Enchanted Forest",accent:"#3f8f5f",
    init:(w,h,r)=>({layers:[0,1,2].map(l=>many(Math.ceil(w/(70-l*14))+2,i=>({x:i*(70-l*14)+r()*30,h:range(r,.22,.36)*h*(1+l*.35)}))),
      flies:many(40,()=>({x:r()*w,y:range(r,.35,.95)*h,p:r()*TAU,q:range(r,.3,.9)})),leaves:many(18,()=>({x:r()*w,y:r()*h,v:range(r,18,40),p:r()*TAU}))}),
    draw(c,w,h,t,s){
      sky(c,w,h,["#0d2a1f","#1d4a35","#3d7a52"]);
      c.save();c.globalAlpha=.12;c.fillStyle="#f6ffcf";for(let i=0;i<5;i++){const x=w*(.15+i*.18)+Math.sin(t*.2+i)*30;c.beginPath();c.moveTo(x,0);c.lineTo(x+60,0);c.lineTo(x+260,h);c.lineTo(x+120,h);c.closePath();c.fill();}c.restore();
      const cols=["#1a3d2c","#123224","#0a2018"];
      s.layers.forEach((trees,l)=>{const base=h*(.78+l*.1);for(const tr of trees)pine(c,tr.x,base,tr.h,cols[l],Math.sin(t*.7+tr.x*.01)*(1+l));ground(c,w,h,base-2,cols[l]);});
      for(const f of s.flies){const x=f.x+Math.sin(t*f.q+f.p)*40,y=f.y+Math.cos(t*f.q*1.3+f.p)*25,a=.4+.6*Math.abs(Math.sin(t*2*f.q+f.p));c.globalAlpha=a;glow(c,x,y,10,"rgba(246,255,140,.9)");c.globalAlpha=1;}
      for(const l of s.leaves)oval(c,wrap(l.x+Math.sin(t+l.p)*40,w),wrap(l.y+t*l.v,h+20)-10,6,3,t*2+l.p,"rgba(196,170,80,.8)");
    }},
  ocean:{name:"Ocean Waves",accent:"#1f7fb8",
    init:(w,h,r)=>({clouds:many(4,()=>({x:r()*w,y:range(r,.08,.28)*h,s:range(r,.8,1.6),v:range(r,5,12)})),gulls:many(5,()=>({x:r()*w,y:range(r,.12,.35)*h,v:range(r,25,45),p:r()*TAU}))}),
    draw(c,w,h,t,s){
      sky(c,w,h,["#3f9ee8","#9fd4ff","#ffe7c4"]);glow(c,w*.22,h*.3,h*.3,"rgba(255,240,190,.8)");c.fillStyle="#fff2b8";c.beginPath();c.arc(w*.22,h*.3,h*.06,0,TAU);c.fill();
      for(const k of s.clouds)cloud(c,wrap(k.x+t*k.v,w+160)-80,k.y,k.s,"rgba(255,255,255,.85)");
      for(const g of s.gulls)bird(c,wrap(g.x+t*g.v,w+60)-30,g.y+Math.sin(t+g.p)*6,1.2,t*6+g.p,"#355");
      const waves=[["#3a8fc7",.56,10,.012,.6],["#2a77b0",.64,14,.009,-.8],["#1c5f94",.74,18,.007,1],["#134a78",.86,22,.005,-1.2]];
      waves.forEach(([col,b,amp,f,sp],i)=>{hills(c,w,h,h*b,amp,f,t*sp+i,col);if(i===1){const bx=wrap(w*.3+t*12,w+120)-60,by=h*b+Math.sin(bx*f+t*sp+i)*amp-4;c.save();c.translate(bx,by);c.rotate(Math.cos(bx*f+t*sp+i)*amp*f);c.fillStyle="#5b3a26";c.beginPath();c.moveTo(-26,0);c.lineTo(26,0);c.lineTo(18,10);c.lineTo(-18,10);c.closePath();c.fill();c.fillStyle="#fffaf0";c.beginPath();c.moveTo(0,-2);c.lineTo(0,-46);c.lineTo(22,-6);c.closePath();c.fill();c.fillStyle="#ff6b5b";c.beginPath();c.moveTo(-2,-2);c.lineTo(-2,-38);c.lineTo(-18,-6);c.closePath();c.fill();c.restore();}});
      c.fillStyle="rgba(255,255,255,.35)";for(let i=0;i<30;i++){const x=wrap(i*97+t*20,w),y=h*(.6+(i%7)*.05);c.fillRect(x,y+Math.sin(t*2+i)*2,14,2);}
    }},
  aquarium:{name:"Aquarium",accent:"#0f8fb3",
    init:(w,h,r)=>({fish:many(12,()=>({y:range(r,.15,.8)*h,x:r()*w,v:range(r,25,60),dir:r()<.5?1:-1,s:range(r,.7,1.5),c:["#ff8c42","#ffd23f","#ff5d8f","#7ae582","#9b8cff","#4cc9f0"][Math.floor(r()*6)],p:r()*TAU})),
      weeds:many(Math.ceil(w/60),i=>({x:i*60+r()*40,h:range(r,.15,.35)*h,p:r()*TAU,c:r()<.5?"#2f8f5b":"#3fae6a"})),bubbles:many(40,()=>({x:r()*w,y:r()*h,v:range(r,20,60),s:range(r,2,6)}))}),
    draw(c,w,h,t,s){
      sky(c,w,h,["#1aa6c9","#0c6e9e","#0a3d62"]);
      c.save();c.globalAlpha=.1;c.fillStyle="#fff";for(let i=0;i<6;i++){const x=w*(i/6)+Math.sin(t*.3+i)*60;c.beginPath();c.moveTo(x,0);c.lineTo(x+40,0);c.lineTo(x+140,h);c.lineTo(x+60,h);c.closePath();c.fill();}c.restore();
      hills(c,w,h,h*.9,h*.015,.01,0,"#e9d39b");
      for(const g of s.weeds){c.strokeStyle=g.c;c.lineWidth=6;c.lineCap="round";c.beginPath();const b=h*.92;c.moveTo(g.x,b);c.bezierCurveTo(g.x+Math.sin(t+g.p)*20,b-g.h*.4,g.x-Math.sin(t*1.2+g.p)*25,b-g.h*.7,g.x+Math.sin(t*.9+g.p)*18,b-g.h);c.stroke();}
      for(const f of s.fish){const x=f.dir>0?wrap(f.x+t*f.v,w+120)-60:w-wrap(f.x+t*f.v,w+120)+60;fish(c,x,f.y+Math.sin(t*.8+f.p)*14,f.s,f.dir,f.c,t*8+f.p);}
      c.strokeStyle="rgba(255,255,255,.6)";c.lineWidth=1.2;for(const b of s.bubbles){c.beginPath();c.arc(b.x+Math.sin(t*2+b.y)*4,h-wrap(h-b.y+t*b.v,h+20),b.s,0,TAU);c.stroke();}
    }},
  snowfall:{name:"Snowy Night",accent:"#5b7fb5",
    init:(w,h,r)=>({flakes:many(160,()=>({x:r()*w,y:r()*h,v:range(r,15,55),s:range(r,1,3.2),p:r()*TAU})),pines:many(Math.ceil(w/45),i=>({x:i*45+r()*30,h:range(r,.12,.22)*h}))}),
    draw(c,w,h,t,s){
      sky(c,w,h,["#0b1d3a","#22416e","#6d8fb8"]);glow(c,w*.78,h*.18,h*.2,"rgba(220,235,255,.5)");c.fillStyle="#f2f6ff";c.beginPath();c.arc(w*.78,h*.18,h*.05,0,TAU);c.fill();
      c.fillStyle="#c9d8ee";c.beginPath();c.moveTo(0,h*.7);[[.12,.38],[.25,.6],[.4,.32],[.58,.62],[.75,.4],[.9,.58],[1,.5]].forEach(([x,y])=>c.lineTo(w*x,h*y));c.lineTo(w,h*.7);c.closePath();c.fill();
      hills(c,w,h,h*.74,h*.02,.006,0,"#e8f0fb");
      for(const p of s.pines)pine(c,p.x,h*.8,p.h,"#1d3557",Math.sin(t*.6+p.x)*.8);
      ground(c,w,h,h*.8,"#f4f8ff");
      c.fillStyle="#fff";for(const f of s.flakes){c.globalAlpha=.85;c.beginPath();c.arc(wrap(f.x+Math.sin(t*.8+f.p)*20,w),wrap(f.y+t*f.v,h+10)-5,f.s,0,TAU);c.fill();}c.globalAlpha=1;
    }},
  starfield:{name:"Starfield",accent:"#8b6cf0",
    init:(w,h,r)=>({stars:many(260,()=>({x:r()*w,y:r()*h,s:range(r,.4,1.8),p:r()*TAU,q:range(r,.5,2.5)})),neb:many(3,i=>({x:range(r,.2,.8)*w,y:range(r,.2,.8)*h,r:range(r,.25,.45)*Math.max(w,h),c:["rgba(155,89,255,.35)","rgba(56,140,255,.3)","rgba(255,80,170,.25)"][i]}))}),
    draw(c,w,h,t,s){
      sky(c,w,h,["#05010f","#120a2e","#1c0f3f"]);
      for(const n of s.neb)glow(c,n.x+Math.sin(t*.05+n.r)*40,n.y+Math.cos(t*.04+n.r)*30,n.r,n.c);
      c.fillStyle="#fff";for(const st of s.stars){c.globalAlpha=.35+.65*Math.abs(Math.sin(t*st.q+st.p));c.beginPath();c.arc(st.x,st.y,st.s,0,TAU);c.fill();}c.globalAlpha=1;
      const k=Math.floor(t/6),ph=(t%6)/1.1;if(ph<1){const r=rng(k*7919+3),sx=r()*w*.7+w*.1,sy=r()*h*.4,x=sx+ph*w*.3,y=sy+ph*h*.15,g=c.createLinearGradient(x-120,y-60,x,y);g.addColorStop(0,"rgba(255,255,255,0)");g.addColorStop(1,"rgba(255,255,255,.9)");c.strokeStyle=g;c.lineWidth=2;c.beginPath();c.moveTo(x-120,y-60);c.lineTo(x,y);c.stroke();}
    }},
  aurora:{name:"Northern Lights",accent:"#2bb38c",
    init:(w,h,r)=>({stars:many(140,()=>({x:r()*w,y:r()*h*.6,s:range(r,.4,1.4),p:r()*TAU}))}),
    draw(c,w,h,t,s){
      sky(c,w,h,["#020814","#04162b","#0a2a3d"]);
      c.fillStyle="#fff";for(const st of s.stars){c.globalAlpha=.4+.6*Math.abs(Math.sin(t*.8+st.p));c.fillRect(st.x,st.y,st.s,st.s);}c.globalAlpha=1;
      c.save();c.globalCompositeOperation="lighter";
      [["rgba(60,255,170,.0)","rgba(60,255,170,.45)",.32,0],["rgba(80,200,255,.0)","rgba(80,200,255,.3)",.26,2],["rgba(180,90,255,.0)","rgba(180,90,255,.25)",.38,4]].forEach(([c0,c1,b,o])=>{
        const base=h*b,band=h*.22,g=c.createLinearGradient(0,base-band,0,base+40);g.addColorStop(0,c0);g.addColorStop(.75,c1);g.addColorStop(1,c0);c.fillStyle=g;c.beginPath();
        const y=x=>base+Math.sin(x*.004+t*.35+o)*h*.06+Math.sin(x*.011-t*.5+o)*h*.02;
        c.moveTo(0,y(0)-band);for(let x=0;x<=w+12;x+=12)c.lineTo(x,y(x)-band-Math.sin(x*.02+t+o)*12);for(let x=w+12;x>=0;x-=12)c.lineTo(x,y(x)+30);c.closePath();c.fill();});
      c.restore();
      c.fillStyle="#06121f";c.beginPath();c.moveTo(0,h);[[0,.72],[.1,.6],[.22,.7],[.35,.55],[.5,.7],[.62,.58],[.78,.72],[.9,.62],[1,.7]].forEach(([x,y])=>c.lineTo(w*x,h*y));c.lineTo(w,h);c.closePath();c.fill();
      ground(c,w,h,h*.84,"#0b1f30");
    }},
  rainycity:{name:"Rainy City",accent:"#4f7cac",
    init:(w,h,r)=>{let x=0;const blds=[];while(x<w){const bw=range(r,40,110),bh=range(r,.2,.55)*h;blds.push({x,w:bw,h:bh,win:many(Math.floor(bw/14)*Math.floor(bh/18),()=>({on:r()<.45,p:r()*60}))});x+=bw+range(r,2,8);}
      return {blds,drops:many(220,()=>({x:r()*w,y:r()*h,v:range(r,500,800),l:range(r,10,22)}))};},
    draw(c,w,h,t,s){
      sky(c,w,h,["#0d1117","#1b2433","#2d3b52"]);
      const flash=Math.max(0,1-(t%9)*3)*(Math.floor(t/9)%2?1:0);if(flash>0){c.fillStyle=`rgba(200,215,255,${flash*.35})`;c.fillRect(0,0,w,h);}
      for(const b of s.blds){const top=h*.92-b.h;c.fillStyle="#141b26";c.fillRect(b.x,top,b.w,b.h);const cols=Math.floor(b.w/14);b.win.forEach((wi,i)=>{const on=wi.on!==((t+wi.p)%40<1.5);if(!on)return;c.fillStyle="rgba(255,214,120,.75)";c.fillRect(b.x+4+(i%cols)*14,top+8+Math.floor(i/cols)*18,7,9);});}
      ground(c,w,h,h*.92,"#0e131b");
      c.strokeStyle="rgba(170,190,220,.35)";c.lineWidth=1;c.beginPath();for(const d of s.drops){const x=wrap(d.x+t*60,w),y=wrap(d.y+t*d.v,h+30)-15;c.moveTo(x,y);c.lineTo(x-2,y+d.l);}c.stroke();
    }},
  sakura:{name:"Cherry Blossom",accent:"#d9578e",
    init:(w,h,r)=>({petals:many(60,()=>({x:r()*w,y:r()*h,v:range(r,20,45),p:r()*TAU,s:range(r,.8,1.6)})),blooms:many(40,()=>({a:r(),o:range(r,-40,40),s:range(r,8,18)}))}),
    draw(c,w,h,t,s){
      sky(c,w,h,["#ffd6e8","#ffeef5","#fff8e7"]);glow(c,w*.7,h*.35,h*.3,"rgba(255,255,255,.8)");
      hills(c,w,h,h*.78,h*.03,.005,1,"#f5bcd3");hills(c,w,h,h*.86,h*.02,.008,4,"#eaa0c0");
      const sway=Math.sin(t*.6)*6;c.strokeStyle="#5a3a3a";c.lineCap="round";c.lineWidth=14;c.beginPath();c.moveTo(-10,h*.08);c.quadraticCurveTo(w*.18,h*.12+sway,w*.38,h*.04+sway);c.stroke();c.lineWidth=6;c.beginPath();c.moveTo(w*.15,h*.11+sway*.5);c.quadraticCurveTo(w*.22,h*.22+sway,w*.3,h*.26+sway);c.stroke();
      for(const b of s.blooms){const x=b.a*w*.38,y=h*.08+Math.sin(b.a*3)*h*.05+b.o+sway*b.a;c.fillStyle=b.a>.5?"#ffb7d0":"#ffc8dc";c.beginPath();c.arc(x,y,b.s,0,TAU);c.fill();}
      for(const p of s.petals)oval(c,wrap(p.x+t*25+Math.sin(t+p.p)*30,w+20)-10,wrap(p.y+t*p.v,h+20)-10,6*p.s,3.5*p.s,t*1.5+p.p,"rgba(255,160,195,.9)");
    }},
  autumn:{name:"Autumn Breeze",accent:"#c2571a",
    init:(w,h,r)=>({trees:many(6,i=>({x:(i+r()*.7)/6*w,s:range(r,.9,1.5),c:["#d9622b","#e8a33d","#b8401f"][Math.floor(r()*3)]})),leaves:many(45,()=>({x:r()*w,y:r()*h,v:range(r,25,55),p:r()*TAU,c:["#d9622b","#e8a33d","#b8401f","#f2c14e"][Math.floor(r()*4)]}))}),
    draw(c,w,h,t,s){
      sky(c,w,h,["#f6c87a","#f8dfb0","#fdf1d6"]);
      hills(c,w,h,h*.66,h*.03,.006,2,"#d79b5b");hills(c,w,h,h*.74,h*.025,.009,5,"#b97a3e");
      for(const tr of s.trees)roundTree(c,tr.x,h*.8,tr.s*h/650,"#5b3a1e",tr.c,Math.sin(t*.9+tr.x)*3);
      ground(c,w,h,h*.8,"#a3652c");
      for(const l of s.leaves)oval(c,wrap(l.x+t*35+Math.sin(t*1.3+l.p)*40,w+20)-10,wrap(l.y+t*l.v,h+20)-10,7,3.5,t*2.5+l.p,l.c);
    }},
  balloons:{name:"Balloon Festival",accent:"#e0563f",
    init:(w,h,r)=>({clouds:many(5,()=>({x:r()*w,y:range(r,.1,.6)*h,s:range(r,.7,1.6),v:range(r,4,10)})),balloons:many(6,()=>({x:r()*w,y:r()*h,v:range(r,8,18),s:range(r,.5,1.1),p:r()*TAU,c:[["#e0563f","#ffd166"],["#118ab2","#ffffff"],["#06d6a0","#ef476f"],["#8338ec","#ffbe0b"]][Math.floor(r()*4)]}))}),
    draw(c,w,h,t,s){
      sky(c,w,h,["#7cc6f0","#bfe6ff","#fff1d6"]);glow(c,w*.15,h*.85,h*.35,"rgba(255,220,150,.7)");
      for(const k of s.clouds)cloud(c,wrap(k.x+t*k.v,w+160)-80,k.y,k.s,"rgba(255,255,255,.9)");
      hills(c,w,h,h*.88,h*.02,.006,0,"#8fc77a");
      for(const b of [...s.balloons].sort((a,b)=>a.s-b.s)){const k=b.s*h/600,x=b.x+Math.sin(t*.3+b.p)*30,y=wrap(b.y-t*b.v,h+260*k)-60*k+40;
        c.save();c.translate(x,y);c.scale(k,k);c.beginPath();c.ellipse(0,0,40,48,0,0,TAU);c.save();c.clip();for(let i=-4;i<4;i++){c.fillStyle=b.c[(i+8)%2];c.fillRect(i*12,-50,12,100);}c.restore();
        c.strokeStyle="rgba(60,40,30,.7)";c.lineWidth=1.2;c.beginPath();c.moveTo(-28,34);c.lineTo(-9,68);c.moveTo(28,34);c.lineTo(9,68);c.stroke();c.fillStyle="#8a5a33";c.fillRect(-10,66,20,14);c.restore();}
    }}
};

let run=null;
const reduced=()=>!!(window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches);
const thumbs={};

const LiveThemes={
  list(){return Object.entries(SCENES).map(([id,sc])=>({id,name:sc.name,accent:sc.accent}));},
  has(id){return Object.prototype.hasOwnProperty.call(SCENES,id);},
  start(id,host){
    if(run&&run.id===id&&run.host===host)return;
    this.stop();
    const scene=SCENES[id];if(!scene||!host||!host.appendChild)return;
    const cv=document.createElement("canvas");cv.className="live-canvas";cv.setAttribute("aria-hidden","true");host.appendChild(cv);
    const c=cv.getContext("2d");if(!c){cv.remove();return;}
    const state={id,host,cv,raf:0,last:0,t0:performance.now()};
    const size=()=>{const dpr=Math.min(window.devicePixelRatio||1,1.5);state.w=window.innerWidth;state.h=window.innerHeight;cv.width=Math.round(state.w*dpr);cv.height=Math.round(state.h*dpr);c.setTransform(dpr,0,0,dpr,0,0);state.s=scene.init(state.w,state.h,rng(id.length*977+13));};
    const frame=t=>{c.clearRect(0,0,state.w,state.h);scene.draw(c,state.w,state.h,t,state.s);};
    const loop=now=>{state.raf=requestAnimationFrame(loop);if(now-state.last<33)return;state.last=now;frame((now-state.t0)/1000);};
    state.onResize=()=>{size();if(reduced())frame(8);};
    size();window.addEventListener("resize",state.onResize);
    if(reduced())frame(8);else state.raf=requestAnimationFrame(loop);
    run=state;
  },
  stop(){if(!run)return;cancelAnimationFrame(run.raf);window.removeEventListener("resize",run.onResize);run.cv.remove();run=null;},
  /* A still frame of the scene for theme pickers, cached as a data URL. */
  thumb(id){
    if(thumbs[id])return thumbs[id];
    const scene=SCENES[id];if(!scene||typeof document==="undefined"||!document.createElement)return "";
    const cv=document.createElement("canvas"),w=320,h=190;cv.width=w;cv.height=h;const c=cv.getContext&&cv.getContext("2d");if(!c)return "";
    scene.draw(c,w,h,8,scene.init(w,h,rng(id.length*977+13)));
    return thumbs[id]=cv.toDataURL("image/jpeg",.82);
  }
};

window.LiveThemes=LiveThemes;
})();
