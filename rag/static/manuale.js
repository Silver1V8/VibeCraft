const voci=[...document.querySelectorAll('nav a')];
const titoli=[...document.querySelectorAll('main h1,main h2')];
const campo=document.getElementById('cerca');
const vuoto=document.getElementById('vuoto');

campo.addEventListener('input',()=>{
  const q=campo.value.trim().toLowerCase();
  let visibili=0;
  for(const a of voci){
    const ok=!q||a.textContent.toLowerCase().includes(q);
    a.parentElement.classList.toggle('nascosto',!ok);
    if(ok)visibili++;
  }
  vuoto.hidden=visibili>0;
});
campo.addEventListener('keydown',e=>{
  if(e.key==='Escape'){campo.value='';campo.dispatchEvent(new Event('input'));}
});

// Evidenzia nell'indice la sezione che si sta leggendo.
const perSlug=new Map(voci.map(a=>[a.getAttribute('href').slice(1),a]));
const osservatore=new IntersectionObserver(entries=>{
  for(const e of entries){
    if(!e.isIntersecting)continue;
    for(const a of voci)a.classList.remove('attivo');
    perSlug.get(e.target.id)?.classList.add('attivo');
    break;
  }
},{rootMargin:'0px 0px -75% 0px',threshold:0});
titoli.forEach(t=>osservatore.observe(t));

// "/" porta il fuoco alla ricerca.
document.addEventListener('keydown',e=>{
  if(e.key==='/'&&document.activeElement!==campo){e.preventDefault();campo.focus();}
});
