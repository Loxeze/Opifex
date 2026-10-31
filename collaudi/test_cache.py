import os, sys
os.environ["DATABASE_URL"] = "postgresql://postgres@127.0.0.1:54329/agenti_test"
os.environ["SECRET_KEY"] = "chiave-di-prova-lunga-e-casuale-0123456789abcdef"
os.environ["CHIAVE_ANTHROPIC"] = "finta"
sys.path.insert(0, os.getcwd())
from app import fornitori
ris = []
def ok(n, c, d=""):
    ris.append(bool(c)); print(("OK    " if c else "FALLITO") + " | " + n + (f"  [{d}]" if d and not c else ""))
orig = {"model": "m", "system": "istruzioni lunghe", "tools": [{"name": "a"}], "messages": [{"role": "user", "content": "ciao"}]}
c = fornitori._con_cache(orig)
ok("system diventa blocco con cache", c["system"][0]["cache_control"] == {"type": "ephemeral"} and c["system"][0]["text"] == "istruzioni lunghe")
ok("ultimo messaggio marcato", c["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"})
ok("l'originale non viene modificato", orig["system"] == "istruzioni lunghe" and orig["messages"][0]["content"] == "ciao")
m = [{"role": "user", "content": "q"}, {"role": "assistant", "content": [{"type": "tool_use", "id": "1", "name": "a", "input": {}}]},
     {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": "ok"}]}]
c2 = fornitori._con_cache({"system": "s", "messages": m})
ok("tool_result in coda marcato, i precedenti no", "cache_control" in c2["messages"][-1]["content"][-1] and "cache_control" not in str(c2["messages"][:-1]))
ok("system vuoto e messaggi vuoti non si rompono", fornitori._con_cache({"system": "", "messages": []}) == {"system": "", "messages": []})
ok("costo equivalente: letti al 10%, scritti al 125%", fornitori.token_ingresso({"input_tokens": 100, "cache_read_input_tokens": 10000, "cache_creation_input_tokens": 800}) == 100 + 1000 + 1000)
ok("senza campi cache invariato", fornitori.token_ingresso({"input_tokens": 77}) == 77)
# invia: cache attiva solo per Anthropic e conteggio dei token riletti
visti = []
class R:
    status_code = 200; headers = {}; text = ""
    def json(s): return {"usage": {"input_tokens": 5, "output_tokens": 1, "cache_read_input_tokens": 4000}}
def post(url, headers=None, json=None, timeout=0):
    visti.append((url, json)); return R()
fornitori.httpx.post = post
fornitori.CACHE_LETTA.set(0)
fornitori.invia("https://api.anthropic.com/v1/messages", {}, {"system": "s", "messages": [{"role": "user", "content": "x"}]})
fornitori.invia("https://api.openai.com/v1/chat/completions", {}, {"messages": [{"role": "user", "content": "x"}]})
ok("Anthropic riceve la cache", visti[0][1]["system"][0]["cache_control"])
ok("altri fornitori invariati", visti[1][1] == {"messages": [{"role": "user", "content": "x"}]})
ok("token riletti contati una volta sola", fornitori.CACHE_LETTA.get() == 4000, str(fornitori.CACHE_LETTA.get()))
print("TOTALE", sum(ris), "/", len(ris))
