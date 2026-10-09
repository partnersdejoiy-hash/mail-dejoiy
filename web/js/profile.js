/* ============ Dejoiy Mail — profile.js : profile photos, avatars and signature images ============ */
(function(){
"use strict";

const hue = text => [...String(text||"?")].reduce((n,c)=>n+c.charCodeAt(0),0)%360;
const readFile = file => new Promise((resolve,reject)=>{
  const reader=new FileReader(); reader.onload=()=>resolve(reader.result);
  reader.onerror=()=>reject(new Error("Could not read that file. Choose it again.")); reader.readAsDataURL(file);
});
const loadImage = src => new Promise((resolve,reject)=>{
  const img=new Image(); img.onload=()=>resolve(img);
  img.onerror=()=>reject(new Error("That file is not an image Dmail can use.")); img.src=src;
});

const Profile = {
  /* Photo address for a mailbox, or "" when it has none (initials are shown instead). Signed-in
     mailboxes see their colleagues' photos; the demo only knows your own. */
  photo(email){
    const key=String(email||"").toLowerCase(); if(!key) return "";
    if(window.Live?.enabled){ const v=Live.avatars?.[key]; return v ? `/api/avatar?email=${encodeURIComponent(key)}&v=${v}` : ""; }
    return key===String(Store.state.user.email||"").toLowerCase() ? (Store.state.prefs.avatar||"") : "";
  },
  avatar(email, name, cls){
    const url=this.photo(email);
    return url ? `<span class="${cls} has-photo" aria-hidden="true"><img src="${esc(url)}" alt="" loading="lazy"></span>`
      : `<span class="${cls}" aria-hidden="true" style="--h:${hue(email||name)}"><span class="av-initials">${esc(initials(name||email||"?"))}</span></span>`;
  },

  /* Profile photos are cropped to a centred square and kept small, so lists stay fast. */
  async setPhoto(file){
    const image = file ? await this.square(file, 256) : "";
    if(window.Live?.enabled){
      const result=await Live.request("avatar",{image}), key=Store.state.user.email.toLowerCase();
      Live.avatars={...(Live.avatars||{})};
      if(result.version) Live.avatars[key]=result.version; else delete Live.avatars[key];
    } else { Store.state.prefs.avatar=image; Store.save(); }
    App.refreshNav();
  },
  async square(file, size){
    if(!/^image\//.test(file.type)) throw new Error("Choose a photo (JPG, PNG or WebP).");
    const img=await loadImage(await readFile(file)), side=Math.min(img.naturalWidth,img.naturalHeight);
    const canvas=document.createElement("canvas"); canvas.width=canvas.height=size;
    const ctx=canvas.getContext("2d"); ctx.fillStyle="#fff"; ctx.fillRect(0,0,size,size);
    ctx.drawImage(img,(img.naturalWidth-side)/2,(img.naturalHeight-side)/2,side,side,0,0,size,size);
    return canvas.toDataURL("image/jpeg",.88);
  },

  /* Signature images are scaled down and hosted on the mail server, because Gmail and most
     mail apps do not show images embedded inside a message. */
  async signatureImage(file){
    if(!/^image\/(png|jpeg|gif)$/.test(file.type)) throw new Error("Use a PNG, JPG or GIF image for your signature.");
    let image=await readFile(file); const img=await loadImage(image), max=600;
    if(img.naturalWidth>max && file.type!=="image/gif"){
      const canvas=document.createElement("canvas"); canvas.width=max; canvas.height=Math.round(img.naturalHeight*max/img.naturalWidth);
      canvas.getContext("2d").drawImage(img,0,0,canvas.width,canvas.height);
      image=canvas.toDataURL(file.type==="image/png"?"image/png":"image/jpeg",.9);
    }
    const url = window.Live?.enabled ? (await Live.request("signature-image",{image})).url : image;
    return {url, width:Math.min(img.naturalWidth,300)};
  },
  /* The formatted signature when there is one, else the plain-text one as HTML. */
  signatureHtml(){
    const u=Store.state.user;
    return u.signatureHtml || (u.signature ? esc(u.signature).replace(/\n/g,"<br>") : "");
  }
};

window.Profile = Profile;
})();
