/* ============ Dejoiy Mail — data.js : demo mailbox content (replace with real backend) ============
   Everything here is clearly-marked DEMO data so every button has something real to do.
   When the real mail backend lands (see docs/ROADMAP.md), this file is replaced by API calls. */
(function(){
"use strict";
const H = 3600e3, D = 24*H, now = Date.now();
const ME = { name:"Roopa", email:"roopa@dejoiy.com" };

const emails = [
 {id:"m1", from:{name:"Deepanshu", email:"deepanshu@dejoiy.com"}, to:[ME.email],
  subject:"D-mail launch plan — this week", folder:"inbox", read:false, starred:true, important:true,
  date: now-2*H, labels:["work"], hasAttachment:false,
  body:"<p>Hi!</p><p>Let's lock the launch checklist for Dejoiy Mail this week:</p><ul><li>Finish the theme picker (24 themes)</li><li>Test on phone + tablet layouts</li><li>Write the welcome email for first companies</li></ul><p>We can do this. 💪</p>"},
 {id:"m2", from:{name:"Dejoiy Billing", email:"billing@dejoiy.com"}, to:[ME.email],
  subject:"Your receipt — dejoiy.com renewal", folder:"inbox", read:false, starred:false,
  date: now-5*H, labels:[], hasAttachment:true, attachments:[{name:"receipt-dejoiy-2026.pdf", size:"82 KB"}],
  body:"<p>Thanks for your payment.</p><p><b>Domain:</b> dejoiy.com<br><b>Amount:</b> ₹1,199<br><b>Valid till:</b> 12 Aug 2027</p><p>Receipt is attached.</p>"},
 {id:"m3", from:{name:"Priya Nair", email:"priya@craftkart.in"}, to:[ME.email],
  subject:"Interested in Dejoiy Mail for our 30-member team", folder:"inbox", read:false, starred:false,
  date: now-9*H, labels:["work"], hasAttachment:false,
  body:"<p>Hello Roopa,</p><p>We are a 30-member team and currently overpaying for email. Your per-user pricing sounds perfect.</p><p>Can we get a demo of the admin panel — especially user management and custom domain setup?</p><p>Thanks,<br>Priya</p>"},
 {id:"m4", from:{name:"Aarav Mehta", email:"aarav@pixelstudio.co"}, to:[ME.email],
  subject:"Re: Logo concepts v3", folder:"inbox", read:true, starred:false,
  date: now-1*D-3*H, labels:["design"], hasAttachment:true, attachments:[{name:"logo-v3.zip", size:"4.1 MB"}],
  body:"<p>Sharing v3 of the logo concepts — zipped and attached.</p><p>My favourite is the envelope-mark. Let me know what you think!</p>"},
 {id:"m5", from:{name:"Dejoiy Updates", email:"updates@dejoiy.com"}, to:[ME.email],
  subject:"✨ 5 new themes added to Dejoiy Mail", folder:"inbox", read:true, starred:false,
  date: now-2*D, labels:[], hasAttachment:false,
  body:"<p>We've added <b>Sunset Aussie</b>, <b>Galaxy</b>, <b>Roadtrip</b>, <b>Lighthouse</b> and <b>Western</b> to the theme gallery.</p><p>Open <b>Themes</b> from the top bar to try them — they apply instantly.</p>"},
 {id:"m6", from:{name:"Rahul Verma", email:"rahul.v@gmail.com"}, to:[ME.email],
  subject:"Sunday brunch?", folder:"inbox", read:true, starred:false,
  date: now-3*D, labels:["personal"], hasAttachment:false,
  body:"<p>Hey! Long time — brunch this Sunday at that new place in Indiranagar? Say 11?</p>"},
 {id:"m7", from:{name:"Bank Alerts", email:"alerts@hdfcbank.example"}, to:[ME.email],
  subject:"UPI payment of ₹2,499 successful", folder:"inbox", read:true, starred:false,
  date: now-4*D, labels:["finance"], hasAttachment:false,
  body:"<p>Your UPI payment of <b>₹2,499</b> to CLOUD HOSTING was successful. UTR 611823774501.</p>"},
 {id:"m8", from:{name:"Lucky Draw Winner", email:"winner@prize-lotto.xyz"}, to:[ME.email],
  subject:"CONGRATULATIONS!! You won $5,000,000", folder:"spam", read:false, starred:false,
  date: now-1*D, labels:[], hasAttachment:false,
  body:"<p>Dear winner, you have won $5,000,000 in our lottery. Send your bank details to claim!!!</p>"},
 {id:"m9", from:{name:"Cheap Meds", email:"deals@rx-cheap.xyz"}, to:[ME.email],
  subject:"90% OFF pharmacy — today only", folder:"spam", read:false, starred:false,
  date: now-2*D, labels:[], hasAttachment:false,
  body:"<p>Buy now, limited stock, click here!!!</p>"},
 {id:"m10", from:ME, to:["priya@craftkart.in"],
  subject:"Re: Interested in Dejoiy Mail for our 30-member team", folder:"sent", read:true, starred:false,
  date: now-8*H, labels:["work"], hasAttachment:false,
  body:"<p>Hi Priya,</p><p>Thanks for reaching out! I'd love to show you the admin panel — user management and custom domains take about five minutes to set up.</p><p>Would Thursday work for a 20-minute demo?</p><p>Best,<br>Roopa</p>"},
 {id:"m11", from:ME, to:["deepanshu@dejoiy.com"],
  subject:"Theme list — final 24", folder:"sent", read:true, starred:false,
  date: now-1*D, labels:["work"], hasAttachment:false,
  body:"<p>Final theme list locked: 13 colour themes + 11 scenic. Brightness stays independent. Custom upload works too.</p>"},
 {id:"m12", from:{name:"Old Newsletter", email:"news@oldsite.example"}, to:[ME.email],
  subject:"Weekly digest — unsubscribe below", folder:"trash", read:true, starred:false,
  date: now-9*D, labels:[], hasAttachment:false,
  body:"<p>Old stuff.</p>"},
 {id:"m13", from:{name:"Kavya Rao", email:"kavya@dejoiy.com"}, to:[ME.email],
  subject:"Draft: investor update Q3", folder:"drafts", read:true, starred:false,
  date: now-6*H, labels:["work"], hasAttachment:false,
  body:"<p>Team,</p><p>Quick Q3 update: prototype is live, first demo scheduled…</p>"},
 {id:"m14", from:{name:"System", email:"system@dejoiy.com"}, to:[ME.email],
  subject:"Welcome to Dejoiy Mail 🎉", folder:"archive", read:true, starred:true,
  date: now-12*D, labels:[], hasAttachment:false,
  body:"<p>Welcome aboard! This is your new company mailbox.</p><p>Try the <b>Themes</b> button up top, press <b>?</b> for keyboard shortcuts, and hit <b>c</b> to compose.</p>"}
];

/* pool of "incoming" mail for the Check-mail simulation */
const incomingPool = [
 {from:{name:"Sneha Kulkarni", email:"sneha@brightleaf.in"}, subject:"Demo request: Dejoiy Mail for 12 users",
  labels:["work"], body:"<p>Hi Roopa,</p><p>We'd like a demo for our 12-member team next week. Do you support data migration from our old provider?</p>"},
 {from:{name:"GitHub", email:"noreply@github.com"}, subject:"[mail-dejoiy] New commit pushed to main",
  labels:["work"], body:"<p>A new commit was pushed to <b>mail-dejoiy</b>.</p>"},
 {from:{name:"Mom", email:"mom@family.example"}, subject:"Beta, khana khaya?",
  labels:["personal"], body:"<p>Call when free. ❤️</p>"},
 {from:{name:"Dejoiy Status", email:"status@dejoiy.com"}, subject:"All systems operational",
  labels:[], body:"<p>All mail systems are running normally. Uptime this month: 99.99%.</p>"},
 {from:{name:"Arjun Patel", email:"arjun@finlytics.io"}, subject:"Invoice #INV-2091 — design retainer",
  labels:["finance"], hasAttachment:true, attachments:[{name:"INV-2091.pdf", size:"140 KB"}],
  body:"<p>Hi, attaching this month's invoice. Please confirm receipt.</p>"},
 {from:{name:"BookMyShow", email:"alerts@bookmyshow.example"}, subject:"Your tickets: Saturday 7 PM show",
  labels:["personal"], body:"<p>Your booking is confirmed. Enjoy the show! 🎬</p>"}
];

const contacts = [
 {id:"c1", name:"Deepanshu", email:"deepanshu@dejoiy.com", phone:"+91 98XXX XXXXX", org:"Dejoiy", presence:"online"},
 {id:"c2", name:"Priya Nair", email:"priya@craftkart.in", phone:"+91 97XXX XXXXX", org:"CraftKart", presence:"online"},
 {id:"c3", name:"Aarav Mehta", email:"aarav@pixelstudio.co", phone:"", org:"Pixel Studio", presence:"away"},
 {id:"c4", name:"Kavya Rao", email:"kavya@dejoiy.com", phone:"+91 99XXX XXXXX", org:"Dejoiy", presence:"online"},
 {id:"c5", name:"Rahul Verma", email:"rahul.v@gmail.com", phone:"", org:"", presence:"off"},
 {id:"c6", name:"Sneha Kulkarni", email:"sneha@brightleaf.in", phone:"", org:"Brightleaf", presence:"away"},
 {id:"c7", name:"Arjun Patel", email:"arjun@finlytics.io", phone:"", org:"Finlytics", presence:"off"},
 {id:"c8", name:"Mom", email:"mom@family.example", phone:"+91 98XXX XXXXX", org:"Family", presence:"online"}
];

const events = [
 {id:"e1", title:"D-mail theme review", date: ymd(0), time:"10:00", notes:"Final 24 themes"},
 {id:"e2", title:"Demo — CraftKart (Priya)", date: ymd(3), time:"15:00", notes:"Admin panel walkthrough"},
 {id:"e3", title:"Dentist", date: ymd(5), time:"11:30", notes:""},
 {id:"e4", title:"Investor update call", date: ymd(8), time:"17:00", notes:"Q3 numbers"}
];
function ymd(offset){ const d=new Date(Date.now()+offset*D); return d.toISOString().slice(0,10); }

const todos = [
 {id:"t1", text:"Publish theme picker build", done:true},
 {id:"t2", text:"Test D-mail on tablet layout", done:true},
 {id:"t3", text:"Write welcome email for first companies", done:false},
 {id:"t4", text:"Fix SPF record for dejoiy.com", done:false}
];

const news = [
 {src:"Dejoiy Blog", ico:"🚀", title:"Dejoiy Mail: our 24-theme gallery is complete",
  sum:"Every theme now applies instantly across the whole app — plus independent light/medium/dark brightness.", ts: now-3*H},
 {src:"Tech Daily", ico:"📧", title:"Small teams are ditching pricey per-seat email",
  sum:"Bootstrapped companies are moving to simpler, flat-priced business email with custom domains.", ts: now-7*H},
 {src:"Design Weekly", ico:"🎨", title:"Dark mode done right: brightness ≠ theme",
  sum:"Why separating colour themes from brightness levels makes for calmer, more usable interfaces.", ts: now-1*D},
 {src:"Founder Notes", ico:"💡", title:"Build the boring parts first: deliverability",
  sum:"SPF, DKIM and DMARC matter more than any UI polish when you run real email infrastructure.", ts: now-2*D},
 {src:"Product Hunt", ico:"⭐", title:"Keyboard-first email clients are back",
  sum:"Power users are returning to shortcut-driven workflows — j/k navigation, single-key actions.", ts: now-3*D}
];

const cannedReplies = [
 "Haha, nice one! 😄", "Sounds good — let's do it.", "Give me 10 minutes, checking now.",
 "Perfect, thanks for sending this over!", "Can we discuss this on call later?", "Done! ✅"
];

const defaultFilters = [
 {id:"f1", name:"Star newsletters from Dejoiy", on:true,
  criteria:{from:"updates@dejoiy.com", to:"", subject:"", hasWords:"", noWords:"", larger:"", smaller:"", after:"", before:"", hasAttachment:false},
  actions:{archive:false, markRead:false, star:true, label:"", forwardTo:"", delete:false, neverSpam:true, important:false, category:""}},
 {id:"f2", name:"Archive bank alerts (keep unread)", on:true,
  criteria:{from:"alerts@", to:"", subject:"", hasWords:"", noWords:"", larger:"", smaller:"", after:"", before:"", hasAttachment:false},
  actions:{archive:true, markRead:false, star:false, label:"finance", forwardTo:"", delete:false, neverSpam:false, important:false, category:""}}
];

window.DemoData = { ME, emails, incomingPool, contacts, events, todos, news, cannedReplies, defaultFilters };
})();
