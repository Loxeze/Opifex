import re, ast, subprocess
P="app/"
ok=0
def c(cond,msg):
    global ok
    print(("OK   " if cond else "FAIL ")+msg); ok+= (not cond)
d=open(P+"static/dettatura.js").read(); css=open(P+"static/stile.css").read()
idx=open(P+"static/index.html").read(); ch=open(P+"static/chat.js").read(); v=open(P+"static/voce.js").read()
t=open(P+"trascrizione.py").read(); ast.parse(t)
c("dettatura.js" in idx and idx.index("voce.js")<idx.index("dettatura.js"),"dettatura.js caricato dopo voce.js")
c(subprocess.run(["node","--check",P+"static/dettatura.js"]).returncode==0,"dettatura.js sintassi")
c("password" in d and "one-time-code" in d,"esclude password/OTP")
c(".mic-campo" in css and "min-height:104px" in css,"CSS mic e textarea mobile")
c("crescita" in ch,"auto-grow chat")
c("def vocabolario" in t and "whisper-1" in t and "MODELLI" in t,"trascrizione: vocabolario+fallback")
c("SILENZIO_MS" in v,"voce.js soglia silenzio")
import sys
c(bool(re.search(r"MODELLI\s*=\s*[\(\[]",t)),"MODELLI definito")
print("FALLITI:",ok); sys.exit(1 if ok else 0)
