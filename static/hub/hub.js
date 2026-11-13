/* CNAP Member Hub homepage (MW 2026-11-13). Behaviour only: every date, name, and number on the page comes from the server. */

(function(){
  function words(h){var t=h.textContent;h.textContent='';t.split(' ').forEach(function(w,i){var s=document.createElement('span');s.className='w';s.style.setProperty('--i',i);s.textContent=w;h.appendChild(s);if(i<t.split(' ').length-1)h.appendChild(document.createTextNode(' '));});}
  document.querySelectorAll('.greet h1').forEach(words);
  var g=document.querySelector('.greet'),fs=g.querySelector('.fibers'),mb=g.querySelector('.motion');
  var still=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(still&&fs.pauseAnimations)fs.pauseAnimations();
  mb.addEventListener('click',function(){var p=mb.getAttribute('aria-pressed')!=='true';mb.setAttribute('aria-pressed',p);g.classList.toggle('paused',p);if(p)fs.pauseAnimations();else fs.unpauseAnimations();mb.querySelector('span').textContent=p?'Play motion':'Pause motion';mb.querySelector('svg').innerHTML=p?'<path d="M4 2l8 5-8 5z"/>':'<rect x="3" y="2" width="3" height="10" rx="1"/><rect x="8" y="2" width="3" height="10" rx="1"/>';});
  try{var lol=document.querySelector('.lineup ol'),arr=document.querySelectorAll('.lineup .arrow'),lst=document.getElementById('lu-status');
  function lupd(){var max=lol.scrollWidth-lol.clientWidth;arr[0].setAttribute('aria-disabled',lol.scrollLeft<=2);arr[1].setAttribute('aria-disabled',lol.scrollLeft>=max-2);
    var items=lol.querySelectorAll('li'),r=lol.getBoundingClientRect(),vis=[];items.forEach(function(l,i){var b=l.getBoundingClientRect();if(b.left>=r.left-2&&b.right<=r.right+2)vis.push(i+1);});if(vis.length)lst.textContent='Showing speakers '+vis[0]+' to '+vis[vis.length-1]+' of '+items.length;}
  arr.forEach(function(b){b.addEventListener('click',function(){if(b.getAttribute('aria-disabled')==='true')return;var li=lol.querySelector('li');var step=li.getBoundingClientRect().width+parseFloat(getComputedStyle(lol).columnGap||0);lol.scrollBy({left:step*+b.dataset.dir,behavior:still?'auto':'smooth'});});});
  lol.addEventListener('scroll',function(){clearTimeout(lol._t);lol._t=setTimeout(lupd,80);},{passive:true});addEventListener('resize',lupd);lupd();
  }catch(e){}
  var lud=document.querySelector('.lu-d');if(lud)lud.addEventListener('toggle',function(){if(lud.open)lupd();});
  var cx=document.querySelectorAll('.core-x');cx.forEach(function(d){d.addEventListener('toggle',function(){cx.forEach(function(o){if(o!==d&&o.open!==d.open)o.open=d.open;});});});


  /* corner rules: draw in once their section is on screen */
  try{if('IntersectionObserver' in window){document.documentElement.classList.add('js-draw');var dio=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('drawn');dio.unobserve(e.target);}});},{rootMargin:'0px 0px -25% 0px'});document.querySelectorAll('.ns-band,.cx').forEach(function(el){dio.observe(el);});}}catch(e){}
  /* calendar: dates come from the Hub (reporting sessions, NeuroSync talks, funding deadlines, and research events) */
  if(document.getElementById('hub-cal'))try{
  var KIND={ns:'NeuroSync',ctr:'Center event',due:'Deadline',you:'Your meeting · only you see this',cam:'K-State'};
  var SHAPE={ns:'<circle cx="5" cy="5" r="4"/>',ctr:'<path d="M5 .5L9.5 5 5 9.5 .5 5z"/>',due:'<rect x="1" y="1" width="8" height="8" rx="1"/>',you:'<circle cx="5" cy="5" r="3.4" fill="none" stroke-width="2"/>',cam:'<path d="M5 .8L9.4 9H.6z"/>'};
  var CAL=JSON.parse(document.getElementById('hub-cal').textContent),EV=CAL.events,BRK=CAL.breaks||[];
  var MON=['January','February','March','April','May','June','July','August','September','October','November','December'],WD=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  var TODAY=CAL.today,sel=TODAY,ym=[+TODAY.slice(0,4),+TODAY.slice(5,7)-1],on={ns:1,ctr:1,due:1,you:1,cam:1};
  function iso(y,m,d){return y+'-'+String(m+1).padStart(2,'0')+'-'+String(d).padStart(2,'0');}
  function dt(s){var a=s.split('-');return new Date(+a[0],a[1]-1,+a[2]);}
  function evOn(d){return EV.filter(function(e){return on[e[2]]&&(e[0]===d||(e[4]&&e[0]<=d&&d<=e[4]));});}
  function brk(d){return BRK.some(function(b){return b[0]<=d&&d<=b[1];});}
  function mk(k){return '<svg viewBox="0 0 10 10" class="k-'+k+'" aria-hidden="true">'+SHAPE[k]+'</svg>';}
  var body=document.getElementById('cm-body'),cmh=document.getElementById('cm-h'),clb=document.getElementById('cl-body'),clh=document.getElementById('cl-h'),tb=document.querySelector('.cl-today');
  function month(focus){var y=ym[0],m=ym[1],first=new Date(y,m,1).getDay(),days=new Date(y,m+1,0).getDate(),h='',c=0;cmh.textContent=MON[m]+' '+y;
    for(var i=0;i<first;i++){if(c%7===0)h+='<tr>';h+='<td></td>';c++;}
    for(var d=1;d<=days;d++){if(c%7===0)h+='<tr>';var s=iso(y,m,d),es=evOn(s),cls='dbtn'+(s<TODAY?' past':'')+(s===TODAY?' today':'')+(brk(s)?' brk':''),ks=[];es.forEach(function(e){if(ks.indexOf(e[2])<0)ks.push(e[2]);});
      var lab='';
      h+='<td><button type="button" class="'+cls+'" data-d="'+s+'" tabindex="'+(s===sel?0:-1)+'" aria-pressed="'+(s===sel)+'"'+(s===TODAY?' aria-current="date"':'')+' aria-label="'+WD[new Date(y,m,d).getDay()]+', '+MON[m]+' '+d+(es.length?', '+es.length+(es.length>1?' items':' item'):', nothing scheduled')+'"><span class="dn">'+d+'</span>'+lab+'<span class="ces">'+es.filter(function(e){return !(e[4]&&/break/.test(e[3])&&e[0]!==s&&new Date(y,m,d).getDay()!==0);}).slice(0,3).map(function(e){var short=e[1]==='All day'||e[1]==='All week'?'':e[1].replace(' p.m.','').replace(' a.m.',' a.m.');return '<span class="ce k-'+e[2]+'"><span class="ci"><span class="lead">'+mk(e[2])+(short?'<span class="tm">'+short+'</span>':'')+'</span>'+(short?'':'')+'<span class="ct">'+e[3]+'</span></span></span>';}).join('')+(es.length>3?'<span class="ce-more">'+(es.length-3)+' more</span>':'')+'</span><span class="mks">'+ks.map(mk).join('')+'</span></button></td>';c++;if(c%7===0)h+='</tr>';}
    while(c%7){h+='<td></td>';c++;if(c%7===0)h+='</tr>';}
    body.innerHTML=h;
    if(focus){var f=body.querySelector('[tabindex="0"]')||body.querySelector('.dbtn');if(f){f.tabIndex=0;f.focus();}}}
  function list(){var D=dt(sel),es=evOn(sel);
    clh.textContent=(sel===TODAY?'Today, ':'')+WD[D.getDay()]+', '+MON[D.getMonth()]+' '+D.getDate();tb.hidden=sel===TODAY;
    clb.innerHTML=es.length?es.map(function(e){return '<a class="cd-ev" href="'+(e[5]||'#cal-h')+'"><span class="t">'+e[1]+'</span><span class="kind k-'+e[2]+'">'+mk(e[2])+' '+KIND[e[2]]+'</span><b>'+e[3]+'</b></a>';}).join(''):'<p class="cd-empty">Nothing is scheduled. Choose another day, or turn on more types above.</p>';}
  function pick(d,focus){sel=d;var D=dt(d);ym=[D.getFullYear(),D.getMonth()];render(focus);}
  body.addEventListener('click',function(e){var b=e.target.closest('.dbtn');if(b)pick(b.dataset.d,true);});
  body.addEventListener('keydown',function(e){var b=e.target.closest('.dbtn');if(!b)return;var mv={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7}[e.key];if(!mv)return;e.preventDefault();var D=dt(b.dataset.d);D.setDate(D.getDate()+mv);if(D<MIN||D>MAX)return;var d=iso(D.getFullYear(),D.getMonth(),D.getDate());
    if(D.getMonth()!==ym[1]){ym=[D.getFullYear(),D.getMonth()];month(false);updNav();}body.querySelectorAll('.dbtn').forEach(function(x){x.tabIndex=x.dataset.d===d?0:-1;});var t=body.querySelector('[data-d="'+d+'"]');if(t)t.focus();});

  var view='week',tbl=document.querySelector('.cm-grid'),cv=document.getElementById('cv'),cday=document.querySelector('.cm-day'),MIN=dt(CAL.min),MAX=dt(CAL.max);
  function chip(e){var t=e[1]==='All day'||e[1]==='All week'?'':e[1];return '<span class="ce k-'+e[2]+'"><span class="ci"><span class="lead">'+mk(e[2])+(t?'<span class="tm">'+t+'</span>':'')+'</span><span class="ct">'+e[3]+'</span></span></span>';}
  function week(){var D=dt(sel);D.setDate(D.getDate()-D.getDay());var a=new Date(D),h='<div class="wk">';
    for(var i=0;i<7;i++){var s=iso(D.getFullYear(),D.getMonth(),D.getDate()),es=evOn(s);
      h+='<div class="wk-d'+(brk(s)?' brk':'')+(s===TODAY?' today':'')+(s===sel?' sel':'')+'"><button type="button" class="wk-h" data-d="'+s+'" aria-pressed="'+(s===sel)+'"'+(s===TODAY?' aria-current="date"':'')+'><span class="wk-wd">'+WD[D.getDay()]+'</span><span class="dn num">'+D.getDate()+'</span></button><div class="wk-evs">'+(es.length?es.map(chip).join(''):'<span class="wk-none">Nothing scheduled</span>')+'</div></div>';D.setDate(D.getDate()+1);}
    var b=new Date(D);b.setDate(b.getDate()-1);cmh.textContent=MON[a.getMonth()]+' '+a.getDate()+' to '+(a.getMonth()!==b.getMonth()?MON[b.getMonth()]+' ':'')+b.getDate()+', '+b.getFullYear();cv.innerHTML=h+'</div>';}
  function agenda(){var out=[];EV.forEach(function(e,i){if(!on[e[2]])return;var end=e[4]||e[0];if(end<sel)return;out.push([e[0]<sel?sel:e[0],e,i]);});
    out.sort(function(a,b){return a[0]<b[0]?-1:a[0]>b[0]?1:a[2]-b[2];});var S=dt(sel);cmh.textContent='Coming up from '+MON[S.getMonth()]+' '+S.getDate();
    if(!out.length){cv.innerHTML='<p class="cl-empty">Nothing else is on the calendar with these filters.</p>';return;}
    var h='',cur='';out.forEach(function(o){var d=o[0],e=o[1],D=dt(d);if(d!==cur){if(cur)h+='</div></div>';cur=d;h+='<div class="cl-day"><div class="cl-date"><span class="d-num num">'+D.getDate()+'</span><span class="d-wd">'+WD[D.getDay()]+'<br>'+MON[D.getMonth()]+'</span></div><div>';}
      h+='<a class="cl-ev" href="'+(e[5]||'#cal-h')+'"><span class="t">'+e[1]+'</span><span class="kind k-'+e[2]+'">'+mk(e[2])+' '+KIND[e[2]]+'</span><b>'+e[3]+(e[4]?' <span class="meta">through '+MON[dt(e[4]).getMonth()]+' '+dt(e[4]).getDate()+'</span>':'')+'</b></a>';});
    cv.innerHTML='<div class="ag">'+h+'</div></div></div>';}
  function year(){var Y0=MIN.getFullYear(),M0=MIN.getMonth();cmh.textContent='Academic year '+Y0+' to '+(Y0+1);var h='<div class="yr">';
    for(var k=0;k<12;k++){var y=Y0+Math.floor((M0+k)/12),m=(M0+k)%12,first=new Date(y,m,1).getDay(),days=new Date(y,m+1,0).getDate();
      h+='<div class="ym"><h4>'+MON[m]+' '+y+'</h4><div class="ym-g">';['S','M','T','W','T','F','S'].forEach(function(x){h+='<span class="ym-w" aria-hidden="true">'+x+'</span>';});
      for(var i=0;i<first;i++)h+='<span></span>';
      for(var d=1;d<=days;d++){var s=iso(y,m,d),es=evOn(s);h+='<button type="button" class="ym-d'+(es.length?' has':'')+(brk(s)?' brk':'')+(s===TODAY?' today':'')+'" data-d="'+s+'" tabindex="'+(es.length||s===TODAY?0:-1)+'" aria-label="'+WD[new Date(y,m,d).getDay()]+', '+MON[m]+' '+d+(es.length?', '+es.length+(es.length>1?' items':' item'):'')+'">'+d+'</button>';}
      h+='</div></div>';}
    cv.innerHTML=h+'</div>';}
  function updNav(){var a=document.querySelectorAll('.cm-nav .arrow'),nav=document.querySelector('.cm-nav');nav.hidden=(view==='list'||view==='year');var lo,hi;
    if(view==='month'){lo=ym[0]*12+ym[1]<=MIN.getFullYear()*12+MIN.getMonth();hi=ym[0]*12+ym[1]>=MAX.getFullYear()*12+MAX.getMonth();}else{var D=dt(sel);lo=D-MIN<7*864e5;hi=MAX-D<7*864e5;}
    a[0].setAttribute('aria-disabled',lo);a[1].setAttribute('aria-disabled',hi);a[0].setAttribute('aria-label',view==='week'?'Previous week':'Previous month');a[1].setAttribute('aria-label',view==='week'?'Next week':'Next month');}
  function render(focus){tbl.hidden=view!=='month';cv.hidden=view==='month';cday.hidden=view!=='month';cv.className='cv cv-'+view;
    if(view==='month'){month(focus);list();}else if(view==='week')week();else if(view==='list')agenda();else year();
    updNav();document.querySelectorAll('.cm-views button').forEach(function(b){b.setAttribute('aria-pressed',b.dataset.v===view);});}
  document.querySelectorAll('.cm-views button').forEach(function(b){b.addEventListener('click',function(){view=b.dataset.v;render(false);});});
  document.querySelectorAll('.cm-nav .arrow').forEach(function(b){b.addEventListener('click',function(){if(b.getAttribute('aria-disabled')==='true')return;var dir=+b.dataset.m;
    if(view==='month'){var D=new Date(ym[0],ym[1]+dir,1);ym=[D.getFullYear(),D.getMonth()];render(false);var x=body.querySelector('[data-d="'+sel+'"]')||body.querySelector('.dbtn');body.querySelectorAll('.dbtn').forEach(function(y){y.tabIndex=-1;});if(x)x.tabIndex=0;}
    else{var W=dt(sel);W.setDate(W.getDate()+7*dir);sel=iso(W.getFullYear(),W.getMonth(),W.getDate());ym=[W.getFullYear(),W.getMonth()];render(false);}});});
  cv.addEventListener('click',function(e){var b=e.target.closest('[data-d]');if(!b)return;sel=b.dataset.d;var D=dt(sel);ym=[D.getFullYear(),D.getMonth()];if(view==='year')view='month';render(view==='month');});
  tb.addEventListener('click',function(){pick(TODAY,false);});
  document.querySelectorAll('.cf').forEach(function(b){b.addEventListener('click',function(){var v=b.getAttribute('aria-pressed')!=='true';b.setAttribute('aria-pressed',v);on[b.dataset.k]=v?1:0;render(false);});});
  render(false);
  }catch(e){}

  try{var otp=document.querySelector('.otp'),links=[].slice.call(otp.querySelectorAll('ol a'));
    
    var tr=otp.querySelector('.otp-track'),olx=otp.querySelector('ol');
    function spy(){var cur=links[0],ci=0;links.forEach(function(a,i){var h=document.getElementById(a.dataset.t);if(h&&h.getBoundingClientRect().top<innerHeight*0.35){cur=a;ci=i;}});links.forEach(function(a,i){a.setAttribute('aria-current',a===cur);a.classList.toggle('seen',i<ci);});
      try{var o=otp.getBoundingClientRect(),f=links[0].getBoundingClientRect(),l=links[links.length-1].getBoundingClientRect(),c=cur.getBoundingClientRect();var top=f.top-o.top+16,end=l.top-o.top+16;tr.style.setProperty('--tt',top+'px');tr.style.setProperty('--th',(end-top)+'px');tr.style.setProperty('--tf',(c.top-o.top+16-top)+'px');}catch(e){}}
    var gr=document.querySelector('.greet');function place(){otp.style.top=Math.max(124,Math.round(gr.getBoundingClientRect().bottom+48))+'px';}
    addEventListener('scroll',function(){place();clearTimeout(otp._t);otp._t=setTimeout(spy,60);},{passive:true});addEventListener('resize',place);place();spy();
    var ob=document.querySelector('.otp-btn');if(ob){function setOpen(v){otp.classList.toggle('open',v);ob.setAttribute('aria-expanded',v);if(v){spy();}}
      ob.addEventListener('click',function(e){e.stopPropagation();setOpen(!otp.classList.contains('open'));});
      otp.addEventListener('click',function(e){if(e.target.closest('a'))setOpen(false);});
      document.addEventListener('click',function(e){if(otp.classList.contains('open')&&!otp.contains(e.target))setOpen(false);});
      document.addEventListener('keydown',function(e){if(e.key==='Escape'&&otp.classList.contains('open')){setOpen(false);ob.focus();}});}
    otp.addEventListener('mouseenter',function(){setTimeout(spy,260);});otp.addEventListener('mouseleave',function(){setTimeout(spy,260);});otp.addEventListener('focusin',function(){setTimeout(spy,260);});}catch(e){}

  try{if(!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)){var fd=document.querySelector('.fund');fd.classList.add('grow-wait');var gt;new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){clearTimeout(gt);gt=setTimeout(function(){fd.classList.add('grown');},900);}else clearTimeout(gt);});},{threshold:.35}).observe(fd);}}catch(e){}


  try{var ml=document.querySelector('.mp-list'),ma=document.querySelectorAll('.mp-arrow');function mupd(){var mx=ml.scrollWidth-ml.clientWidth;ma[0].setAttribute('aria-disabled',ml.scrollLeft<=2);ma[1].setAttribute('aria-disabled',ml.scrollLeft>=mx-2);}
    ma.forEach(function(b){b.addEventListener('click',function(){if(b.getAttribute('aria-disabled')==='true')return;ml.scrollBy({left:ml.clientWidth*0.8*+b.dataset.dir,behavior:still?'auto':'smooth'});});});
    ml.addEventListener('scroll',function(){clearTimeout(ml._t);ml._t=setTimeout(mupd,80);},{passive:true});addEventListener('resize',mupd);mupd();}catch(e){}

  try{var web=document.querySelector('.cm-web');if(!still){web.classList.add('wait');new IntersectionObserver(function(es,o){if(es[0].isIntersecting){setTimeout(function(){web.classList.add('go');},150);o.disconnect();}},{threshold:.4}).observe(web);}}catch(e){}
  (function(){
    var vis=[].slice.call(document.querySelectorAll('.brief .bi'));vis.forEach(function(e,i){e.classList.toggle('lastvis',i===vis.length-1);});
    var n=0;vis.forEach(function(e){e.style.setProperty('--n',n++);var k=e.querySelector('.kind');if(k)e.style.setProperty('--k',getComputedStyle(k).color);});
    var first=true;document.querySelectorAll('.brief .bi:not(.intro)').forEach(function(e){if(first){first=false;e.classList.add('firstvis');}else{e.classList.add('compact');}});
  })();
  /* the avatar menu */
  try{var am=document.querySelector('.acct'),ab=am.querySelector('.avatar');function amOpen(v){am.classList.toggle('open',v);ab.setAttribute('aria-expanded',v);}
    ab.addEventListener('click',function(e){e.stopPropagation();amOpen(!am.classList.contains('open'));});
    document.addEventListener('click',function(e){if(!am.contains(e.target))amOpen(false);});
    document.addEventListener('keydown',function(e){if(e.key==='Escape'&&am.classList.contains('open')){amOpen(false);ab.focus();}});}catch(e){}
})();
