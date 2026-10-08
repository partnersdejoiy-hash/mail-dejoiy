const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
function setup(prefs){
 const bg={classList:{add(){},remove(){}},style:{setProperty(){},removeProperty(){}}};
 const context={document:{documentElement:{dataset:{}},getElementById(){return bg}},localStorage:{getItem(){return prefs?JSON.stringify({version:1,prefs}):null},setItem(){}},App:{route:'mail',toast(){}},Date,console};
 context.window=context;vm.createContext(context);
 for(const name of ['data','store','themes'])vm.runInContext(fs.readFileSync(path.join(__dirname,`../web/js/${name}.js`),'utf8'),context);
 return context;
}
test('first visit uses the light Pearl appearance',()=>{
 const c=setup();c.Themes.apply();assert.equal(c.document.documentElement.dataset.theme,'pearl');assert.equal(c.document.documentElement.dataset.brightness,'light');
});
test('old default migrates once; a later deliberate theme choice is retained',()=>{
 const c=setup({theme:'aol',brightness:'dark',customBg:''});assert.equal(c.Store.state.prefs.theme,'pearl');assert.equal(c.Store.state.prefs.brightness,'light');
 const later=setup({theme:'aol',brightness:'dark',customBg:'',designVersion:3});assert.equal(later.Store.state.prefs.theme,'aol');assert.equal(later.Store.state.prefs.brightness,'dark');
});
test('existing scenic and custom themes survive appearance migration',()=>{
 for(const prefs of [{theme:'galaxy',brightness:'dark',customBg:''},{theme:'aol',brightness:'medium',customBg:'data:image/png;base64,abc'}]){
 const c=setup(prefs);c.Themes.apply();assert.equal(c.Store.state.prefs.theme,prefs.theme);assert.equal(c.Store.state.prefs.brightness,prefs.brightness);assert.equal(c.document.documentElement.dataset.scenic,'true');}
});
test('light, medium and dark changes target the element used by the stylesheet',()=>{
 const c=setup();const css=fs.readFileSync(path.join(__dirname,'../web/css/themes.css'),'utf8');
 for(const mode of ['light','medium','dark']){c.Themes.setBrightness(mode);assert.equal(c.document.documentElement.dataset.brightness,mode);assert.ok(css.includes(`html[data-brightness="${mode}"] body{`));}
});
test('forest uses a photo for both wallpaper and theme preview',()=>{
 const c=setup();c.Themes.set('forest');const theme=c.Themes.ALL.find(t=>t.id==='forest');assert.equal(theme.kind,'photo');assert.match(theme.image,/^https:\/\/images\.unsplash\.com\//);assert.match(c.Themes.preview('forest'),/^url\(/);assert.equal(c.document.documentElement.dataset.photoTheme,'true');
});
