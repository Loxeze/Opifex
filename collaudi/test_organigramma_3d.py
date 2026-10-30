import json, subprocess, os
SORG = os.path.join(os.getcwd(), "app/static/organizzazione.js")
f = 0
def ok(c, m):
    global f
    print(("OK    | " if c else "FALLITO | ") + m)
    f += 0 if c else 1
JS = r'''
const fs=require('fs'); const src=fs.readFileSync(process.argv[1],'utf8');
const L=new Function(src.slice(src.indexOf('function calcolaLayout'), src.indexOf('function vistaOrganigramma'))+'; return calcolaLayout;')();
function dati(nRep, perRep, nSent){
  const aziende=[1,2,3].map(i=>({id:i,nome:'A'+i,attiva:true,colore:'#fff'}));
  const agenti=[]; let id=1;
  for(let r=0;r<nRep;r++){ const az=[[1],[2],[3],[1,2],[1,2,3],[]][r%6]; const m={id:id++,nome:'M'+r,categoria:'normale',superiore_id:null,aziende:az,livello:'manager'}; agenti.push(m);
    for(let i=0;i<perRep;i++) agenti.push({id:id++,nome:'o'+r+'_'+i,categoria:'normale',superiore_id:m.id,aziende:az,livello:'operativo'}); }
  for(let i=0;i<nSent;i++) agenti.push({id:id++,nome:'S'+i,categoria:'sentinella',superiore_id:null,aziende:[]});
  return {agenti,aziende};
}
function misura(d){
  const l=L(d), n=l.nodi; let min=1e9, vicine=0;
  for(let a=0;a<n.length;a++)for(let b=a+1;b<n.length;b++){const x=Math.hypot(n[a].x-n[b].x,n[a].y-n[b].y,n[a].z-n[b].z); min=Math.min(min,x); if(x<0.45) vicine++;}
  const fuori=n.filter(p=>!p.centro&&Math.hypot(p.x,p.y,p.z)>l.estensione+1e-9).length;
  const nan=n.filter(p=>![p.x,p.y,p.z].every(Number.isFinite)).length;
  const raggi=l.raggi; const crescenti=raggi.every((r,i)=>i===0||r>raggi[i-1]);
  return {nodi:n.length,min,vicine,fuori,nan,crescenti,k:l.k,estensione:l.estensione};
}
console.log(JSON.stringify({piccolo:misura(dati(4,3,3)), medio:misura(dati(6,10,6)), grande:misura(dati(9,22,8)), vuoto:misura({agenti:[],aziende:[]})}));
'''
out = subprocess.run(["node", "-e", JS, SORG], capture_output=True, text=True, timeout=60)
ok(out.returncode == 0, "il calcolo del layout gira senza errori " + out.stderr[:200])
r = json.loads(out.stdout) if out.returncode == 0 else {}
for nome in ("piccolo", "medio", "grande"):
    m = r.get(nome, {})
    ok(m.get("min", 0) >= 0.45 and m.get("vicine") == 0, f"{nome} ({m.get('nodi')} soggetti): nessuna coppia troppo vicina (minima {m.get('min', 0):.2f})")
    ok(m.get("nan") == 0 and m.get("fuori") == 0, f"{nome}: tutti i punti dentro la scena e con coordinate valide")
    ok(m.get("crescenti") is True, f"{nome}: gli anelli crescono verso l'esterno")
ok(r["grande"]["k"] < 1 <= r["piccolo"]["k"] + 1e-9 and r["piccolo"]["k"] == 1, "la scena si rimpicciolisce da sola solo quando la struttura cresce")
ok(r["vuoto"]["nodi"] == 1, "senza agenti resta solo Lorenzo al centro")
src = open(SORG).read()
ok("ARCO_MIN" in src and "daEtichettare" in src, "distribuzione a anelli omogenei e nomi senza sovrapposizioni")
JS2 = r'''
const fs=require('fs'); const src=fs.readFileSync(process.argv[1],'utf8');
const L=new Function(src.slice(src.indexOf('function calcolaLayout'), src.indexOf('function vistaOrganigramma'))+'; return calcolaLayout;')();
function dati(nRep, perRep, nSent){
  const aziende=[1,2,3].map(i=>({id:i,nome:'A'+i,attiva:true,colore:'#fff'})); const divisioni=[]; const agenti=[]; let id=1;
  for(let r=0;r<nRep;r++){ divisioni.push({id:100+r,nome:'Rep'+r}); const m={id:id++,nome:'M'+r,categoria:'normale',superiore_id:null,aziende:[1],livello:'manager',divisione_id:100+r}; agenti.push(m);
    for(let i=0;i<perRep;i++) agenti.push({id:id++,nome:'o'+r+'_'+i,categoria:'normale',superiore_id:m.id,aziende:[1],livello:'operativo',divisione_id:100+r}); }
  for(let i=0;i<nSent;i++) agenti.push({id:id++,nome:'S'+i,categoria:'sentinella',superiore_id:null,aziende:[]});
  agenti.push({id:id++,nome:'libero',categoria:'normale',superiore_id:null,aziende:[],livello:'operativo'});
  return {agenti,aziende,divisioni};
}
const out={};
for (const [nome,d] of [['medio',dati(6,10,6)],['grande',dati(9,22,8)]]) {
  const l=L(d), n=l.nodi, r={gruppi:l.gruppi.length, senza:n.filter(p=>!p.centro&&p.gruppo===undefined).length};
  for (const m of ['sfera','cost','anelli']) {
    let min=1e9, nan=0; for(const p of n){ const q=p.pos[m]; if(![q.x,q.y,q.z].every(Number.isFinite)) nan++; }
    for(let a=0;a<n.length;a++)for(let b=a+1;b<n.length;b++){const A=n[a].pos[m],B=n[b].pos[m]; min=Math.min(min,Math.hypot(A.x-B.x,A.y-B.y,A.z-B.z));}
    r[m]={min,nan,ext:l.ext[m]};
  }
  r.centro=n[0].pos.cost.x===0&&n[0].pos.anelli.x===0; out[nome]=r;
}
console.log(JSON.stringify(out));
'''
o2 = subprocess.run(["node", "-e", JS2, SORG], capture_output=True, text=True, timeout=60)
ok(o2.returncode == 0, "i modelli alternativi si calcolano senza errori " + o2.stderr[:200])
r2 = json.loads(o2.stdout) if o2.returncode == 0 else {}
for nome in ("medio", "grande"):
    m = r2.get(nome, {})
    ok(m.get("senza") == 0 and m.get("gruppi", 0) >= 7, f"{nome}: ogni soggetto appartiene a un reparto ({m.get('gruppi')} gruppi, con sentinelle e senza reparto)")
    for mod in ("cost", "anelli"):
        q = m.get(mod, {})
        ok(q.get("nan") == 0 and q.get("min", 0) >= 0.12, f"{nome}/{mod}: coordinate valide e nessuna sovrapposizione (minima {q.get('min', 0):.2f})")
    ok(m.get("centro"), f"{nome}: Lorenzo resta al centro in tutti i modelli")
ok("SOLE" in src and "schede-reparti" in src and "org_modello" in src, "sole giallo, vista a schede e scelta del modello ricordata")
print("FALLITI", f)
