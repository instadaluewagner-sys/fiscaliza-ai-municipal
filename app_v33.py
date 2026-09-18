import io, os, re, uuid, unicodedata
from datetime import datetime
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import fitz
import pytesseract
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = FastAPI(title="Fiscaliza.AI Municipal", version="3.3")
ANALYSES = {}

LABELS = {
    "contrato":"Contrato","notificacao":"Notificação","intimacao":"Intimação",
    "defesa":"Defesa administrativa","parecer_juridico":"Parecer jurídico",
    "parecer_tecnico":"Parecer técnico","decisao":"Decisão",
    "termo_recebimento":"Termo de recebimento","nota_fiscal":"Nota fiscal",
    "empenho":"Empenho","ordem_fornecimento":"Ordem/Autorização de fornecimento"
}

def norm(s):
    s=unicodedata.normalize("NFD",s or "")
    s="".join(ch for ch in s if unicodedata.category(ch)!="Mn")
    return re.sub(r"\s+"," ",s).strip().lower()

def clip(s,n=480):
    s=re.sub(r"\s+"," ",s or "").strip()
    return s[:n]+("…" if len(s)>n else "")

def extract_pdf(data,filename):
    doc=fitz.open(stream=data,filetype="pdf"); pages=[]; ocr_count=0
    for i,page in enumerate(doc):
        text=page.get_text("text") or ""; used=False
        if len(text.strip())<80:
            try:
                pix=page.get_pixmap(matrix=fitz.Matrix(1.6,1.6),alpha=False)
                img=Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
                text=pytesseract.image_to_string(img,lang=os.getenv("OCR_LANG","por+eng"))
                used=True;ocr_count+=1
            except Exception: pass
        pages.append({"file":filename,"page":i+1,"text":text,"ocr":used})
    return pages,ocr_count

def strong_type(p):
    raw=p["text"] or ""; z=norm(raw); head=norm(raw[:1800]); first=norm(raw[:700])
    if re.search(r"\bcontrato(?: administrativo)?\s*(?:n|no|numero|nº)",first) and "contratante" in z and "contratada" in z:return "contrato"
    if "defesa administrativa" in first or "razoes de defesa" in first or re.search(r"\bapresenta(?:r)?\s+(?:a\s+|sua\s+)?defesa\b",head):return "defesa"
    if "notificacao extrajudicial" in first or "notificacao administrativa" in first or re.search(r"\bnotificacao\s*(?:n|no|numero|nº)",first):return "notificacao"
    if "fica intimado" in head or "fica intimada" in head or re.search(r"\bintimacao\s*(?:n|no|numero|nº)",first):return "intimacao"
    if "parecer juridico" in first or ("procuradoria" in first and "parecer" in first):return "parecer_juridico"
    if "parecer tecnico" in first or "relatorio tecnico" in first or "manifestacao tecnica" in first:return "parecer_tecnico"
    if "decisao administrativa" in first or re.search(r"^\s*(decido|resolvo|determino|autorizo)\b",first) or (any(k in head for k in ["decido","resolvo","determino","autorizo"]) and any(k in z for k in ["rescis","extinc","processo administrativo sancionador"])):return "decisao"
    if re.search(r"^\s*termo de recebimento\b",first) and any(k in z for k in ["recebemos","atesto","recebimento definitivo","recebimento provisorio"]):return "termo_recebimento"
    if "danfe" in first or re.search(r"^\s*nota fiscal(?: eletronica)?\b",first):return "nota_fiscal"
    if re.search(r"^\s*(nota de )?empenho\b",first):return "empenho"
    if re.search(r"^\s*(ordem|autorizacao) de fornecimento\b",first):return "ordem_fornecimento"
    return None

CONT={
"defesa":["dos fatos","do direito","reequilibr","requer","contratada"],
"notificacao":["notificado","prazo","manifestacao","descumprimento"],
"intimacao":["intimado","prazo","defesa","manifestacao"],
"parecer_juridico":["fundamentacao","conclusao","lei 14.133","juridico"],
"parecer_tecnico":["analise tecnica","conclusao","fiscal","execucao"],
"decisao":["decisao","determino","autorizo","rescis","extinc"],
"contrato":["clausula","contratante","contratada","objeto","vigencia"]}

MENTION={
"contrato":["contrato","contratual"],"notificacao":["notificacao","notificado"],
"intimacao":["intimacao","intimado"],"defesa":["defesa administrativa","defesa"],
"parecer_juridico":["parecer juridico"],"parecer_tecnico":["parecer tecnico","manifestacao tecnica"],
"decisao":["decisao","decidiu","determino","autorizo"],"termo_recebimento":["termo de recebimento"],
"nota_fiscal":["nota fiscal","danfe"],"empenho":["empenho","nota de empenho"],
"ordem_fornecimento":["ordem de fornecimento","autorizacao de fornecimento"]}

def classify_pages(pages):
    pieces=[]; prev={}
    for p in pages:
        typ=strong_type(p)
        if not typ:
            pr=prev.get(p["file"]); z=norm(p["text"])
            if pr and sum(1 for k in CONT.get(pr,[]) if k in z)>=2:typ=pr
        if typ:
            pieces.append({**p,"type":typ});prev[p["file"]]=typ
        else:prev[p["file"]]=None
    keys={(x["file"],x["page"],x["type"]) for x in pieces}; mentions=[]
    for p in pages:
        z=norm(p["text"])
        for typ,words in MENTION.items():
            if (p["file"],p["page"],typ) in keys:continue
            if any(w in z for w in words):mentions.append({**p,"type":typ})
    return pieces,mentions

def grouped(rows):
    out=[]
    for typ,label in LABELS.items():
        by={}
        for r in rows:
            if r["type"]==typ:by.setdefault(r["file"],[]).append(r["page"])
        for f,pgs in by.items():out.append({"type":typ,"label":label,"file":f,"pages":sorted(set(pgs))})
    return out

def fmt_pages(pgs):
    if not pgs:return ""
    pgs=sorted(set(pgs));runs=[];a=b=pgs[0]
    for p in pgs[1:]:
        if p==b+1:b=p
        else:runs.append((a,b));a=b=p
    runs.append((a,b))
    return ", ".join(str(a) if a==b else str(a)+"–"+str(b) for a,b in runs)

def snippets(pages,patterns,limit=6,only_pages=None):
    found=[]
    for p in pages:
        if only_pages is not None and p["page"] not in only_pages:continue
        txt=re.sub(r"\s+"," ",p["text"] or "")
        for sent in re.split(r"(?<=[.!?;:])\s+",txt):
            z=norm(sent)
            if any(re.search(pat,z) for pat in patterns):
                found.append({"file":p["file"],"page":p["page"],"text":clip(sent)});break
        if len(found)>=limit:break
    return found

def total_quantity(pages):
    pats=[r"(?:quantidade total|quantidade contratada|quantidade prevista)\s*[:\-]?\s*(\d{1,7})",r"quantidade\s*[:\-]?\s*(\d{1,7})\s+(?:unidades|unid\.?)"]
    for p in pages:
        z=norm(p["text"])
        for pat in pats:
            for m in re.finditer(pat,z):
                ctx=z[max(0,m.start()-100):min(len(z),m.end()+150)]
                if any(b in ctx for b in ["por viagem","metade da quantidade","50% da quantidade","estimativa de transporte"]):continue
                return {"value":m.group(1),"source":{"file":p["file"],"page":p["page"]}}
    return {"value":"Não identificado com segurança","source":None}

def analyze_pages(pages):
    prows,mrows=classify_pages(pages);pieces=grouped(prows);mentions=grouped(mrows)
    has={k:any(x["type"]==k for x in pieces) for k in LABELS}
    no_delivery=snippets(pages,[r"nenhuma entrega",r"nao houve entrega",r"nao realizou.*entrega",r"inexecucao total"],5)
    sanction=snippets(pages,[r"abertura.*processo administrativo sancionador",r"instauracao.*processo administrativo sancionador",r"instaurar.*processo administrativo sancionador"],3)
    delivery=snippets(pages,[r"foi entregue",r"entrega realizada",r"recebido.*objeto"],3)
    pending=[]
    if delivery and not has["termo_recebimento"]:pending.append("Há indício de entrega, mas não foi localizado termo de recebimento como peça autônoma.")
    if not has["defesa"]:pending.append("Não foi localizada defesa administrativa como peça autônoma com segurança.")
    if not(has["notificacao"] or has["intimacao"]):pending.append("Não foi localizada notificação/intimação como peça autônoma com segurança.")
    if sanction:pending.append("Os autos indicam abertura/instauração de processo sancionador posterior; não presuma sanção final a partir deste PDF.")
    dp={p for x in pieces if x["type"]=="defesa" for p in x["pages"]}
    defense=snippets(pages,[r"reequilibr",r"aumento.*custo",r"frete",r"impossibil",r"inviabil",r"forca maior",r"rescis"],6,dp if dp else None)
    contra=snippets(pages,[r"nenhuma entrega",r"nao houve entrega",r"descumpr",r"inexecucao",r"rescisao unilateral",r"extincao unilateral"],6)
    if sanction:conclusion="Os autos registram abertura/instauração de processo administrativo sancionador posterior. Isso não equivale a sanção já aplicada."
    elif has["decisao"] and has["defesa"] and (has["notificacao"] or has["intimacao"]):conclusion="Foram localizadas peças relevantes de contraditório e decisão. A ferramenta organiza a evidência; a decisão permanece humana."
    else:conclusion="Nem todas as peças esperadas foram identificadas como documentos autônomos com segurança. Menções no corpo dos autos não são tratadas como peças."
    return {"pieces":pieces,"mentions":mentions,"has":has,"defense":defense,"contra":contra,"pending":pending,"quantity":total_quantity(pages),"conclusion":conclusion,"no_delivery":no_delivery}

def piece_pages(a,typ):return sorted({p for x in a["pieces"] if x["type"]==typ for p in x["pages"]})

def arg_categories(pages,dpages):
    cats=[("reequilíbrio econômico-financeiro",[r"reequilibr"]),("aumento de custos/frete",[r"aumento.*custo",r"frete"]),("impossibilidade/inviabilidade de execução",[r"impossibil",r"inviabil"]),("pedido de rescisão/encerramento",[r"rescis",r"encerramento"]),("caso fortuito/força maior",[r"caso fortuito",r"forca maior"])]
    out=[]
    for label,pats in cats:
        found=[]
        for p in pages:
            if p["page"] not in dpages:continue
            z=norm(p["text"])
            if any(re.search(x,z) for x in pats):found.append(p["page"])
        if found:out.append((label,sorted(set(found))))
    return out

def answer_question(q,a,pages):
    z=norm(q)
    if "defesa" in z:
        pgs=piece_pages(a,"defesa")
        if not pgs:return {"answer":"Não localizei defesa administrativa como peça autônoma com segurança.","sources":[]}
        cats=arg_categories(pages,set(pgs))
        args="; ".join(label+" (p. "+fmt_pages(pg)+")" for label,pg in cats[:5]) or "os argumentos devem ser conferidos diretamente nas páginas da defesa"
        first=min(pgs);prior=[]
        for p in pages:
            if p["page"]>=first:continue
            zz=norm(p["text"])
            if any(k in zz for k in ["reequilibr","rescisao amigavel","pedido de emissao","justificativa"]) and strong_type(p)!="defesa":prior.append(p["page"])
        extra=" Há manifestações anteriores da contratada nas páginas "+fmt_pages(prior)+", separadas da defesa formal." if prior else ""
        return {"answer":"Sim. A defesa administrativa foi localizada como peça própria nas páginas "+fmt_pages(pgs)+". Principais argumentos identificados: "+args+"."+extra,"sources":["Defesa administrativa · p. "+fmt_pages(pgs)]}
    if "notifica" in z or "intim" in z:
        pgs=sorted(set(piece_pages(a,"notificacao")+piece_pages(a,"intimacao")))
        return {"answer":"Foi localizada notificação/intimação como peça própria nas páginas "+fmt_pages(pgs)+"." if pgs else "Não localizei notificação/intimação como peça própria com segurança.","sources":["Notificação/intimação · p. "+fmt_pages(pgs)] if pgs else []}
    if "quantidade" in z:
        qq=a["quantity"];src=qq.get("source")
        return {"answer":"Quantidade total: "+qq["value"],"sources":[src["file"]+" · p."+str(src["page"])] if src else []}
    if "entrega" in z and a["no_delivery"]:
        s=a["no_delivery"][0];return {"answer":"Há registro textual indicando ausência de entrega.","sources":[s["file"]+" · p."+str(s["page"])+" — "+s["text"]]}
    if "decis" in z or "rescis" in z or "sanc" in z:
        pgs=piece_pages(a,"decisao");extra=" Decisão localizada nas páginas "+fmt_pages(pgs)+"." if pgs else ""
        return {"answer":a["conclusion"]+extra,"sources":["Decisão · p. "+fmt_pages(pgs)] if pgs else []}
    stop={"qual","quais","como","para","sobre","processo","informe","paginas","pagina","empresa","administrativo"}
    words=[w for w in re.findall(r"[a-z0-9çãõáéíóúâêô]{4,}",q.lower()) if w not in stop]
    scored=[]
    for p in pages:
        for sent in re.split(r"(?<=[.!?;:])\s+",p["text"] or ""):
            k=sum(1 for w in words if norm(w) in norm(sent))
            if k:scored.append((k,p,sent))
    scored.sort(key=lambda x:(-x[0],x[1]["page"]))
    if not scored:return {"answer":"Não encontrei evidência textual suficiente para responder com segurança.","sources":[]}
    return {"answer":"Encontrei evidências relacionadas. Revise os trechos e páginas indicados antes de concluir.","sources":[p["file"]+" · p."+str(p["page"])+" — "+clip(sent,320) for _,p,sent in scored[:5]]}

class AskReq(BaseModel):
    analysis_id:str
    question:str

@app.get("/api/health")
def health():return {"ok":True,"version":"3.3"}

@app.post("/api/analyze")
async def analyze(files:List[UploadFile]=File(...)):
    pages=[];ocr=0;names=[]
    for f in files:
        if not f.filename.lower().endswith(".pdf"):continue
        pp,oo=extract_pdf(await f.read(),f.filename);pages.extend(pp);ocr+=oo;names.append(f.filename)
    if not pages:raise HTTPException(400,"Envie pelo menos um PDF.")
    a=analyze_pages(pages);aid=uuid.uuid4().hex
    ANALYSES[aid]={"pages":pages,"analysis":a,"created":datetime.utcnow().isoformat()}
    return {"analysis_id":aid,"files":names,"pages":len(pages),"ocr_pages":ocr,"analysis":a}

@app.post("/api/ask")
def ask(req:AskReq):
    item=ANALYSES.get(req.analysis_id)
    if not item:raise HTTPException(409,"A análise desta sessão não está mais na memória do servidor. Clique em Analisar documentos novamente.")
    return answer_question(req.question,item["analysis"],item["pages"])

@app.get("/api/report/{analysis_id}")
def report(analysis_id):
    item=ANALYSES.get(analysis_id)
    if not item:raise HTTPException(404,"Análise não encontrada.")
    a=item["analysis"];buf=io.BytesIO();c=canvas.Canvas(buf,pagesize=A4);y=810
    c.setFont("Helvetica-Bold",15);c.drawString(40,y,"Fiscaliza.AI Municipal — Relatório");y-=30;c.setFont("Helvetica",10)
    lines=[a["conclusion"],"","Peças identificadas:"]
    for x in a["pieces"]:lines.append("- "+x["label"]+": "+x["file"]+", p. "+fmt_pages(x["pages"]))
    lines+=["","Pendências e limites:"]+["- "+p for p in a["pending"]]
    for line in lines:
        chunks=[line[i:i+100] for i in range(0,max(1,len(line)),100)] or [""]
        for chunk in chunks:
            if y<50:c.showPage();y=810;c.setFont("Helvetica",10)
            c.drawString(40,y,chunk);y-=14
    c.save();buf.seek(0)
    return StreamingResponse(buf,media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=fiscaliza-relatorio.pdf"})

HTML="""<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fiscaliza.AI Municipal</title>
<style>body{margin:0;font-family:Arial,sans-serif;background:#f3f6fa;color:#102033}.wrap{max-width:1280px;margin:auto;padding:28px}.hero{background:#0b3b4b;color:white;padding:28px;border-radius:18px}.badge{display:inline-block;background:#dff7ec;color:#0b6b4b;padding:7px 12px;border-radius:99px;font-weight:700}.card{background:white;border:1px solid #dce5ee;border-radius:16px;padding:22px;margin-top:18px}.row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.mini{border:1px solid #dce5ee;border-radius:12px;padding:14px}.item{border-left:4px solid #12a36f;background:#f7fafc;padding:10px;margin:8px 0}.warn{border-left:4px solid #d99100;background:#fffaf0;padding:10px;margin:8px 0}.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}button{background:#2864e8;color:white;border:0;border-radius:10px;padding:12px 18px;font-weight:700;cursor:pointer}input[type=text]{width:78%;padding:12px}.muted{color:#617084;font-size:14px}.mention{border-left-color:#8a99aa}@media(max-width:850px){.row,.cols{grid-template-columns:1fr}input[type=text]{width:68%}}</style></head>
<body><div class="wrap"><div class="hero"><div class="badge">VERSÃO 3.3 · PEÇA ≠ MENÇÃO · Q&A COM ESTADO</div><h1>Fiscaliza.AI Municipal</h1><p>Analisa processos por página, separa peças autônomas de simples menções e mantém cada resposta ligada à evidência.</p></div>
<div class="card"><h2>Analisar processo</h2><input id="files" type="file" multiple accept="application/pdf"> <button onclick="analisar()">Analisar documentos</button><div id="status" class="muted"></div></div>
<div id="result"></div>
<div class="card"><h2>Pergunte ao processo</h2><input id="q" type="text" placeholder="Ex.: A empresa apresentou defesa? Em quais páginas e quais os principais argumentos?"> <button onclick="perguntar()">Perguntar</button><div id="answer" style="margin-top:16px;font-weight:600"></div><div id="sources" class="muted"></div></div>
<div class="card"><button onclick="relatorio()">Baixar relatório PDF</button></div></div>
<script>
var analysisId=null;
function plist(x){return x.pages.join(", ")}
async function analisar(){
 var fs=document.getElementById("files").files;if(!fs.length){alert("Escolha um PDF.");return}
 var fd=new FormData();for(var i=0;i<fs.length;i++)fd.append("files",fs[i]);
 document.getElementById("status").textContent="Analisando...";
 var r=await fetch("/api/analyze",{method:"POST",body:fd});var d=await r.json();
 if(!r.ok){document.getElementById("status").textContent=d.detail||"Erro";return}
 analysisId=d.analysis_id;localStorage.setItem("fiscaliza_analysis_id",analysisId);
 document.getElementById("status").textContent=d.pages+" páginas analisadas · OCR em "+d.ocr_pages+" página(s)";
 var a=d.analysis;var h='<div class="card"><h2>Análise assistida</h2><p>'+a.conclusion+'</p><div class="row">';
 h+='<div class="mini"><b>Defesa</b><br>'+(a.has.defesa?"Localizada":"Não identificada com segurança")+'</div>';
 h+='<div class="mini"><b>Notificação/intimação</b><br>'+((a.has.notificacao||a.has.intimacao)?"Localizada":"Não identificada com segurança")+'</div>';
 h+='<div class="mini"><b>Decisão</b><br>'+(a.has.decisao?"Localizada":"Não identificada com segurança")+'</div>';
 h+='<div class="mini"><b>Quantidade total</b><br>'+a.quantity.value+'</div></div></div>';
 h+='<div class="card"><h2>Peças processuais identificadas</h2>';
 for(var j=0;j<a.pieces.length;j++){var x=a.pieces[j];h+='<div class="item"><b>'+x.label+'</b><br><span class="muted">'+x.file+' · p. '+plist(x)+'</span></div>'}
 h+='</div><div class="card"><h2>Menções localizadas (não tratadas como peça)</h2>';
 for(var j=0;j<a.mentions.length;j++){var x=a.mentions[j];h+='<div class="item mention"><b>'+x.label+'</b><br><span class="muted">'+x.file+' · p. '+plist(x)+'</span></div>'}
 h+='</div><div class="cols"><div class="card"><h2>Elementos favoráveis à defesa</h2>';
 for(var j=0;j<a.defense.length;j++){var x=a.defense[j];h+='<div class="item">'+x.text+'<br><span class="muted">'+x.file+' · p.'+x.page+'</span></div>'}
 h+='</div><div class="card"><h2>Pontos a confrontar</h2>';
 for(var j=0;j<a.contra.length;j++){var x=a.contra[j];h+='<div class="item">'+x.text+'<br><span class="muted">'+x.file+' · p.'+x.page+'</span></div>'}
 h+='</div></div><div class="card"><h2>Pendências e limites</h2>';
 if(!a.pending.length)h+='<div class="item">Nenhuma pendência automática relevante identificada.</div>';
 for(var j=0;j<a.pending.length;j++)h+='<div class="warn">'+a.pending[j]+'</div>';
 h+='</div>';document.getElementById("result").innerHTML=h;document.getElementById("result").scrollIntoView({behavior:"smooth"});
}
async function perguntar(){
 var q=document.getElementById("q").value.trim();if(!q)return;
 analysisId=analysisId||localStorage.getItem("fiscaliza_analysis_id");
 if(!analysisId){document.getElementById("answer").textContent="Analise um processo primeiro.";return}
 var r=await fetch("/api/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({analysis_id:analysisId,question:q})});
 var d=await r.json();
 if(!r.ok){document.getElementById("answer").textContent=d.detail||"Erro";document.getElementById("sources").textContent="";return}
 document.getElementById("answer").textContent=d.answer;document.getElementById("sources").innerHTML=(d.sources||[]).map(function(x){return "• "+x}).join("<br>");
}
function relatorio(){analysisId=analysisId||localStorage.getItem("fiscaliza_analysis_id");if(!analysisId){alert("Analise um processo primeiro.");return}location.href="/api/report/"+analysisId}
</script></body></html>"""

@app.get("/",response_class=HTMLResponse)
def home():return HTML


# --- Interface institucional v3.4 ---
HTML = r"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fiscaliza.AI Municipal</title>
<style>
:root{
  --navy:#102a43;
  --navy-2:#163b5c;
  --teal:#0f766e;
  --teal-soft:#e8f5f2;
  --green:#15803d;
  --blue:#2458d3;
  --gold:#b7791f;
  --ink:#172033;
  --muted:#66758a;
  --line:#dbe3ec;
  --panel:#ffffff;
  --bg:#f4f7fa;
  --soft:#f8fafc;
  --warning:#fff8e7;
  --warning-line:#d99a16;
  --shadow:0 10px 30px rgba(16,42,67,.08);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;
  font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
  background:var(--bg);
  color:var(--ink);
  line-height:1.5;
}
button,input{font:inherit}
.topbar{
  height:72px;background:var(--navy);color:white;display:flex;align-items:center;
  position:sticky;top:0;z-index:20;border-bottom:1px solid rgba(255,255,255,.1)
}
.topbar-inner{width:min(1480px,calc(100% - 48px));margin:auto;display:flex;align-items:center;justify-content:space-between;gap:24px}
.brand{display:flex;align-items:center;gap:12px}
.brandmark{
  width:38px;height:38px;border:1px solid rgba(255,255,255,.25);border-radius:10px;
  display:grid;place-items:center;font-weight:800;letter-spacing:-.5px;background:rgba(255,255,255,.07)
}
.brandtext strong{display:block;font-size:17px;letter-spacing:-.2px}
.brandtext span{display:block;font-size:11px;color:#bdd0df;letter-spacing:.08em;text-transform:uppercase;margin-top:1px}
.topmeta{display:flex;align-items:center;gap:10px;font-size:12px;color:#d6e4ee}
.statusdot{width:8px;height:8px;border-radius:50%;background:#4ade80;box-shadow:0 0 0 4px rgba(74,222,128,.12)}
.shell{width:min(1480px,calc(100% - 48px));margin:34px auto 64px}
.hero{
  display:grid;grid-template-columns:minmax(0,1.45fr) minmax(320px,.55fr);
  gap:22px;align-items:stretch;margin-bottom:22px
}
.hero-main,.hero-side,.panel{
  background:var(--panel);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow)
}
.hero-main{padding:38px 40px}
.eyebrow{font-size:12px;font-weight:800;color:var(--teal);letter-spacing:.12em;text-transform:uppercase;margin-bottom:12px}
.hero h1{font-size:clamp(34px,4vw,58px);line-height:1.03;letter-spacing:-1.8px;margin:0;max-width:930px;color:var(--navy)}
.hero-sub{font-size:17px;color:var(--muted);max-width:850px;margin:18px 0 0}
.trustline{display:flex;flex-wrap:wrap;gap:16px;margin-top:28px;color:#405166;font-size:13px}
.trustline span{display:flex;align-items:center;gap:7px}
.check{
  width:19px;height:19px;border-radius:50%;background:var(--teal-soft);color:var(--teal);
  display:inline-grid;place-items:center;font-size:12px;font-weight:900
}
.hero-side{padding:28px;display:flex;flex-direction:column;justify-content:space-between;background:#fbfcfe}
.hero-side h3{font-size:15px;margin:0 0 14px;color:var(--navy)}
.audit-step{display:flex;gap:12px;padding:12px 0;border-top:1px solid var(--line)}
.audit-step:first-of-type{border-top:0}
.num{width:28px;height:28px;border-radius:8px;background:var(--navy);color:white;display:grid;place-items:center;font-size:12px;font-weight:800;flex:0 0 auto}
.audit-step b{display:block;font-size:13px;color:var(--ink)}
.audit-step small{display:block;color:var(--muted);font-size:12px;margin-top:2px}
.version{margin-top:18px;border-top:1px solid var(--line);padding-top:14px;color:var(--muted);font-size:11px}
.panel{padding:26px 28px;margin-top:18px}
.panel-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:18px}
.panel-title{margin:0;font-size:20px;letter-spacing:-.3px;color:var(--navy)}
.panel-kicker{font-size:11px;font-weight:800;color:var(--teal);text-transform:uppercase;letter-spacing:.1em;margin-bottom:5px}
.panel-desc{margin:5px 0 0;color:var(--muted);font-size:13px}
.uploadbox{
  border:1.5px dashed #9fb2c4;border-radius:14px;background:var(--soft);padding:24px;
  display:flex;align-items:center;justify-content:space-between;gap:22px;transition:.2s
}
.uploadbox:hover{border-color:var(--teal);background:#f7fbfa}
.uploadcopy{display:flex;align-items:center;gap:15px;min-width:0}
.uploadicon{
  width:48px;height:48px;border-radius:12px;background:var(--teal-soft);color:var(--teal);
  display:grid;place-items:center;font-size:22px;flex:0 0 auto
}
.uploadcopy strong{display:block;font-size:15px;color:var(--navy)}
.uploadcopy span{display:block;color:var(--muted);font-size:12px;margin-top:3px}
.fileinput{max-width:430px}
.actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.btn{
  border:0;border-radius:10px;padding:12px 18px;font-weight:750;cursor:pointer;
  transition:transform .12s ease,box-shadow .12s ease,background .12s ease
}
.btn:hover{transform:translateY(-1px)}
.btn-primary{background:var(--navy);color:#fff;box-shadow:0 6px 14px rgba(16,42,67,.16)}
.btn-primary:hover{background:#0b2238}
.btn-blue{background:var(--blue);color:#fff}
.btn-outline{background:#fff;color:var(--navy);border:1px solid var(--line)}
#status{margin-top:12px;color:var(--muted);font-size:13px}
.card{
  background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:26px 28px;margin-top:18px;box-shadow:var(--shadow)
}
.card h2{margin:0 0 18px;font-size:20px;letter-spacing:-.25px;color:var(--navy)}
.card>p{color:#405166;margin-top:0}
.row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:20px}
.mini{border:1px solid var(--line);border-radius:13px;padding:16px;background:#fbfcfe;min-height:83px}
.mini b{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#708197;display:block;margin-bottom:8px}
.mini br+*{color:var(--ink)}
.item{
  border:1px solid #e2e8f0;border-left:3px solid var(--teal);background:#fbfcfd;
  padding:13px 15px;margin:9px 0;border-radius:0 10px 10px 0;font-size:13px
}
.item b{font-size:14px;color:var(--navy)}
.muted{color:var(--muted);font-size:12px}
.mention{border-left-color:#94a3b8;background:#fcfcfd}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.warn{border:1px solid #f0dfb0;border-left:3px solid var(--warning-line);background:var(--warning);padding:13px 15px;margin:9px 0;border-radius:0 10px 10px 0;font-size:13px}
.qa-wrap{display:flex;gap:10px}
.qa-input{
  flex:1;border:1px solid #bcc9d6;background:#fff;border-radius:11px;padding:14px 15px;
  outline:none;color:var(--ink);min-width:0
}
.qa-input:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(36,88,211,.08)}
#answer{margin-top:18px;background:#f8fbff;border:1px solid #dbe7f5;border-radius:12px;padding:16px;display:none;color:#20324a}
#sources{margin-top:8px;line-height:1.7}
.result-empty{color:var(--muted);font-size:13px;padding:4px 0}
.footer-actions{display:flex;justify-content:space-between;align-items:center;gap:16px}
.footer-note{font-size:12px;color:var(--muted);max-width:700px}
.loading{display:inline-flex;align-items:center;gap:8px}
.spinner{width:14px;height:14px;border:2px solid #ccd6e1;border-top-color:var(--teal);border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:980px){
  .hero{grid-template-columns:1fr}.hero-side{display:none}.row{grid-template-columns:repeat(2,1fr)}.cols{grid-template-columns:1fr}
}
@media(max-width:680px){
  .topbar-inner,.shell{width:min(100% - 24px,1480px)}
  .shell{margin-top:18px}.hero-main,.panel,.card{padding:20px}.hero h1{font-size:34px;letter-spacing:-1px}
  .row{grid-template-columns:1fr}.uploadbox{align-items:flex-start;flex-direction:column}.qa-wrap{flex-direction:column}
  .qa-input{width:100%}.btn{width:100%}.footer-actions{align-items:stretch;flex-direction:column}
}
</style>
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <div class="brand">
      <div class="brandmark">F.AI</div>
      <div class="brandtext"><strong>Fiscaliza.AI Municipal</strong><span>Copiloto auditável para gestão pública</span></div>
    </div>
    <div class="topmeta"><span class="statusdot"></span><span>Sistema operacional</span></div>
  </div>
</header>

<main class="shell">
  <section class="hero">
    <div class="hero-main">
      <div class="eyebrow">Análise documental com rastreabilidade</div>
      <h1>Do processo extenso à evidência que sustenta a decisão.</h1>
      <p class="hero-sub">Organize peças, identifique contradições, acompanhe o contraditório e consulte o processo com indicação de páginas — sem substituir a análise humana.</p>
      <div class="trustline">
        <span><i class="check">✓</i> OCR em português</span>
        <span><i class="check">✓</i> Peça ≠ menção</span>
        <span><i class="check">✓</i> Respostas com fonte</span>
        <span><i class="check">✓</i> Decisão humana preservada</span>
      </div>
    </div>
    <aside class="hero-side">
      <div>
        <h3>Fluxo de auditoria</h3>
        <div class="audit-step"><div class="num">01</div><div><b>Leitura do processo</b><small>PDF textual ou digitalizado.</small></div></div>
        <div class="audit-step"><div class="num">02</div><div><b>Classificação documental</b><small>Peças e menções separadas.</small></div></div>
        <div class="audit-step"><div class="num">03</div><div><b>Consulta rastreável</b><small>Resposta ligada a páginas e evidências.</small></div></div>
      </div>
      <div class="version">VERSÃO 3.4 · INTERFACE INSTITUCIONAL</div>
    </aside>
  </section>

  <section class="panel">
    <div class="panel-head">
      <div>
        <div class="panel-kicker">Iniciar análise</div>
        <h2 class="panel-title">Carregue os autos do processo</h2>
        <p class="panel-desc">Você pode selecionar um ou mais PDFs. O processamento ocorre nesta instância do sistema.</p>
      </div>
    </div>
    <div class="uploadbox">
      <div class="uploadcopy">
        <div class="uploadicon">↥</div>
        <div><strong>Selecione os documentos</strong><span>PDFs com texto ou páginas escaneadas.</span></div>
      </div>
      <div class="actions">
        <input class="fileinput" id="files" type="file" multiple accept="application/pdf">
        <button class="btn btn-primary" onclick="analisar()">Analisar processo</button>
      </div>
    </div>
    <div id="status"></div>
  </section>

  <div id="result"></div>

  <section class="panel" id="perguntas">
    <div class="panel-head">
      <div>
        <div class="panel-kicker">Consulta aos autos</div>
        <h2 class="panel-title">Pergunte ao processo</h2>
        <p class="panel-desc">Faça perguntas objetivas. Quando houver evidência, a resposta aponta a origem.</p>
      </div>
    </div>
    <div class="qa-wrap">
      <input id="q" class="qa-input" type="text" placeholder="Ex.: A empresa apresentou defesa? Em quais páginas e quais os principais argumentos?">
      <button class="btn btn-blue" onclick="perguntar()">Perguntar</button>
    </div>
    <div id="answer"></div>
    <div id="sources" class="muted"></div>
  </section>

  <section class="panel">
    <div class="footer-actions">
      <div>
        <div class="panel-kicker">Documentação da análise</div>
        <h2 class="panel-title">Relatório para revisão humana</h2>
        <p class="footer-note">O relatório consolida achados automáticos e referências. Ele não substitui a decisão administrativa nem dispensa a conferência dos autos originais.</p>
      </div>
      <button class="btn btn-primary" onclick="relatorio()">Baixar relatório PDF</button>
    </div>
  </section>
</main>

<script>
var analysisId=null;
function plist(x){return x.pages.join(", ")}
function escapeHtml(s){
 return String(s||"")
   .replace(/&/g,"&amp;")
   .replace(/</g,"&lt;")
   .replace(/>/g,"&gt;")
   .replace(/"/g,"&quot;")
   .replace(/'/g,"&#039;");
}
async function analisar(){
 var fs=document.getElementById("files").files;
 if(!fs.length){alert("Selecione pelo menos um PDF.");return}
 var fd=new FormData();for(var i=0;i<fs.length;i++)fd.append("files",fs[i]);
 var st=document.getElementById("status");st.innerHTML='<span class="loading"><span class="spinner"></span> Lendo e classificando os documentos…</span>';
 var r=await fetch("/api/analyze",{method:"POST",body:fd});var d=await r.json();
 if(!r.ok){st.textContent=d.detail||"Não foi possível analisar os documentos.";return}
 analysisId=d.analysis_id;localStorage.setItem("fiscaliza_analysis_id",analysisId);
 st.textContent=d.pages+" páginas analisadas · OCR aplicado em "+d.ocr_pages+" página(s)";
 var a=d.analysis;var h='';
 h+='<section class="card"><div class="panel-kicker">Síntese automática</div><h2>Análise assistida</h2><p>'+escapeHtml(a.conclusion)+'</p><div class="row">';
 h+='<div class="mini"><b>Defesa</b><span>'+(a.has.defesa?"Localizada":"Não identificada com segurança")+'</span></div>';
 h+='<div class="mini"><b>Notificação / intimação</b><span>'+((a.has.notificacao||a.has.intimacao)?"Localizada":"Não identificada com segurança")+'</span></div>';
 h+='<div class="mini"><b>Decisão</b><span>'+(a.has.decisao?"Localizada":"Não identificada com segurança")+'</span></div>';
 h+='<div class="mini"><b>Quantidade total</b><span>'+escapeHtml(a.quantity.value)+'</span></div></div></section>';

 h+='<section class="card"><div class="panel-kicker">Estrutura dos autos</div><h2>Peças processuais identificadas</h2>';
 if(!a.pieces.length)h+='<div class="result-empty">Nenhuma peça foi classificada com segurança.</div>';
 for(var j=0;j<a.pieces.length;j++){var x=a.pieces[j];h+='<div class="item"><b>'+escapeHtml(x.label)+'</b><br><span class="muted">'+escapeHtml(x.file)+' · p. '+escapeHtml(plist(x))+'</span></div>'}
 h+='</section>';

 h+='<section class="card"><div class="panel-kicker">Referências internas</div><h2>Menções localizadas <span class="muted">— não tratadas como peça</span></h2>';
 if(!a.mentions.length)h+='<div class="result-empty">Nenhuma menção adicional relevante.</div>';
 for(var j=0;j<a.mentions.length;j++){var x=a.mentions[j];h+='<div class="item mention"><b>'+escapeHtml(x.label)+'</b><br><span class="muted">'+escapeHtml(x.file)+' · p. '+escapeHtml(plist(x))+'</span></div>'}
 h+='</section>';

 h+='<div class="cols"><section class="card"><div class="panel-kicker">Contraditório</div><h2>Elementos favoráveis à defesa</h2>';
 if(!a.defense.length)h+='<div class="result-empty">Nenhum argumento específico extraído automaticamente.</div>';
 for(var j=0;j<a.defense.length;j++){var x=a.defense[j];h+='<div class="item">'+escapeHtml(x.text)+'<br><span class="muted">'+escapeHtml(x.file)+' · p. '+x.page+'</span></div>'}
 h+='</section><section class="card"><div class="panel-kicker">Confronto documental</div><h2>Pontos a confrontar</h2>';
 if(!a.contra.length)h+='<div class="result-empty">Nenhum ponto contrário específico extraído automaticamente.</div>';
 for(var j=0;j<a.contra.length;j++){var x=a.contra[j];h+='<div class="item">'+escapeHtml(x.text)+'<br><span class="muted">'+escapeHtml(x.file)+' · p. '+x.page+'</span></div>'}
 h+='</section></div>';

 h+='<section class="card"><div class="panel-kicker">Cautelas da análise</div><h2>Pendências e limites</h2>';
 if(!a.pending.length)h+='<div class="item">Nenhuma pendência automática relevante identificada.</div>';
 for(var j=0;j<a.pending.length;j++)h+='<div class="warn">'+escapeHtml(a.pending[j])+'</div>';
 h+='</section>';

 document.getElementById("result").innerHTML=h;
 document.getElementById("result").scrollIntoView({behavior:"smooth",block:"start"});
}
async function perguntar(){
 var q=document.getElementById("q").value.trim();if(!q)return;
 analysisId=analysisId||localStorage.getItem("fiscaliza_analysis_id");
 var ans=document.getElementById("answer"),src=document.getElementById("sources");
 if(!analysisId){ans.style.display="block";ans.textContent="Analise um processo primeiro.";src.textContent="";return}
 ans.style.display="block";ans.innerHTML='<span class="loading"><span class="spinner"></span> Consultando os autos…</span>';src.textContent="";
 var r=await fetch("/api/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({analysis_id:analysisId,question:q})});
 var d=await r.json();
 if(!r.ok){ans.textContent=d.detail||"Não foi possível responder.";return}
 ans.textContent=d.answer;src.innerHTML=(d.sources||[]).map(function(x){return "• "+escapeHtml(x)}).join("<br>");
}
function relatorio(){
 analysisId=analysisId||localStorage.getItem("fiscaliza_analysis_id");
 if(!analysisId){alert("Analise um processo primeiro.");return}
 location.href="/api/report/"+analysisId
}
document.getElementById("q").addEventListener("keydown",function(e){if(e.key==="Enter")perguntar()});
</script>
</body>
</html>"""


# --- Interface premium v3.6 ---

# --- Processo fictício para demonstração da banca v3.6 ---
def _demo_wrap(cnv, text, x=52, y=735, width=92, leading=15):
    words = text.split()
    line = ""
    for word in words:
        test = (line + " " + word).strip()
        if len(test) > width:
            cnv.drawString(x, y, line)
            y -= leading
            line = word
        else:
            line = test
    if line:
        cnv.drawString(x, y, line)

@app.get("/api/demo-pdf")
def demo_pdf():
    pages = [
        ("PROCESSO ADMINISTRATIVO DEMONSTRATIVO Nº 001/2026",
         "Caso inteiramente fictício criado para demonstração. Objeto: aquisição municipal de 500 kits de higiene."),
        ("CONTRATO ADMINISTRATIVO Nº 001/2026",
         "CONTRATANTE: Município Demonstração. CONTRATADA: Empresa Exemplo Ltda. Objeto: fornecimento de 500 kits. Prazo de entrega: 30 dias. CLÁUSULA QUARTA: a contratada deverá entregar integralmente o objeto no prazo pactuado."),
        ("NOTIFICAÇÃO EXTRAJUDICIAL Nº 004/2026",
         "Fica a CONTRATADA NOTIFICADA para, no prazo de 5 dias úteis, apresentar manifestação sobre a entrega parcial de 300 kits e a ausência dos 200 kits restantes."),
        ("COMPROVANTE DE CIÊNCIA DA NOTIFICAÇÃO",
         "A empresa foi notificada e recebeu prazo para manifestação administrativa sobre a entrega parcial."),
        ("RELATÓRIO TÉCNICO Nº 009/2026",
         "A fiscalização registra execução parcial: foram entregues 300 dos 500 kits contratados. Os 200 kits remanescentes não foram entregues. Recomenda-se análise das justificativas apresentadas."),
        ("INTIMAÇÃO Nº 006/2026",
         "Fica a empresa INTIMADA para apresentar defesa administrativa quanto à possível inexecução parcial, assegurados o contraditório e a ampla defesa."),
        ("DEFESA ADMINISTRATIVA",
         "A Empresa Exemplo Ltda apresenta sua DEFESA ADMINISTRATIVA. Alega atraso excepcional do fornecedor de matéria-prima, pede reconhecimento de atraso justificado e informa que 300 kits foram entregues. Propõe entregar os 200 restantes em 10 dias."),
        ("DA DEFESA E DOS PEDIDOS",
         "A CONTRATADA requer que não seja aplicada penalidade ou, subsidiariamente, que eventual medida observe a proporcionalidade. Requer ainda a consideração das comunicações com o fornecedor e do cronograma de regularização."),
        ("PARECER JURÍDICO Nº 012/2026",
         "O PARECER JURÍDICO registra a existência de notificação e defesa e recomenda que a autoridade confronte a justificativa com as provas de atraso e com as cláusulas contratuais antes de decidir."),
        ("DECISÃO ADMINISTRATIVA",
         "DECIDO reconhecer a necessidade de apuração própria e DETERMINO a instauração de processo administrativo sancionador posterior, preservando o contraditório. Nenhuma sanção é aplicada nesta decisão."),
        ("DESPACHO DE ENCAMINHAMENTO",
         "Encaminhem-se os autos ao setor competente para abertura do procedimento sancionador posterior.")
    ]
    buf = io.BytesIO()
    cnv = canvas.Canvas(buf, pagesize=A4)
    for idx, (title, body) in enumerate(pages, start=1):
        cnv.setFont("Helvetica-Bold", 14)
        cnv.drawString(52, 790, title)
        cnv.setFont("Helvetica", 10)
        _demo_wrap(cnv, body)
        cnv.setFont("Helvetica", 8)
        cnv.drawRightString(545, 35, "Página %d · documento fictício" % idx)
        cnv.showPage()
    cnv.save()
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition":"inline; filename=Processo-Demonstrativo-FiscalizaAI.pdf"}
    )

HTML = r"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fiscaliza.AI Municipal</title>
<style>
:root{
  --navy:#102a43;--navy2:#173d5f;--teal:#0f766e;--teal-soft:#eaf6f4;
  --blue:#2458d3;--ink:#172033;--muted:#6b7b8f;--line:#dbe3ec;--bg:#f4f7fa;
  --white:#fff;--soft:#f8fafc;--warn:#b7791f;--warn-soft:#fff8e7;--ok:#15803d;
  --shadow:0 10px 30px rgba(16,42,67,.07)
}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;line-height:1.5}
button,input{font:inherit}
.topbar{height:70px;background:var(--navy);color:#fff;display:flex;align-items:center;position:sticky;top:0;z-index:30;border-bottom:1px solid rgba(255,255,255,.08)}
.topbar-inner{width:min(1460px,calc(100% - 44px));margin:auto;display:flex;align-items:center;justify-content:space-between;gap:20px}
.brand{display:flex;align-items:center;gap:12px}.brandmark{width:38px;height:38px;border-radius:10px;border:1px solid rgba(255,255,255,.22);display:grid;place-items:center;font-weight:900;background:rgba(255,255,255,.06)}
.brandtext strong{display:block;font-size:17px}.brandtext span{font-size:10px;color:#c5d4df;text-transform:uppercase;letter-spacing:.11em}
.live{display:flex;align-items:center;gap:8px;color:#dce8ef;font-size:12px}.dot{width:8px;height:8px;border-radius:50%;background:#4ade80;box-shadow:0 0 0 4px rgba(74,222,128,.12)}
.shell{width:min(1460px,calc(100% - 44px));margin:30px auto 64px}
.hero{display:grid;grid-template-columns:1.5fr .5fr;gap:18px}
.hero-main,.hero-side,.panel,.section{background:#fff;border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow)}
.hero-main{padding:36px 38px}.eyebrow{font-size:11px;font-weight:900;color:var(--teal);letter-spacing:.12em;text-transform:uppercase}
.hero h1{margin:10px 0 0;font-size:clamp(34px,4vw,56px);line-height:1.04;letter-spacing:-1.6px;color:var(--navy);max-width:980px}
.hero p{margin:18px 0 0;color:var(--muted);font-size:16px;max-width:860px}
.trust{display:flex;gap:12px;flex-wrap:wrap;margin-top:24px}.trust span{font-size:12px;color:#405166;background:#f7fafc;border:1px solid var(--line);border-radius:999px;padding:7px 10px}
.hero-side{padding:26px;display:flex;flex-direction:column;justify-content:space-between}.hero-side h3{margin:0 0 14px;color:var(--navy);font-size:15px}
.step{display:flex;gap:11px;padding:11px 0;border-top:1px solid var(--line)}.step:first-of-type{border-top:0}.num{width:28px;height:28px;border-radius:8px;background:var(--navy);color:#fff;display:grid;place-items:center;font-size:11px;font-weight:900}
.step b{display:block;font-size:13px}.step small{display:block;font-size:11px;color:var(--muted);margin-top:2px}.version{font-size:10px;color:var(--muted);padding-top:14px;border-top:1px solid var(--line);margin-top:16px}
.panel{margin-top:18px;padding:24px 26px}.panel-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:16px}.kicker{font-size:10px;font-weight:900;color:var(--teal);letter-spacing:.12em;text-transform:uppercase}.title{font-size:20px;color:var(--navy);margin:4px 0 0;letter-spacing:-.25px}.desc{font-size:12px;color:var(--muted);margin:5px 0 0}
.uploadbox{border:1.5px dashed #9fb2c4;border-radius:14px;background:var(--soft);padding:20px;display:flex;justify-content:space-between;align-items:center;gap:18px}.uploadcopy{display:flex;gap:13px;align-items:center}.uploadicon{width:46px;height:46px;border-radius:12px;background:var(--teal-soft);color:var(--teal);display:grid;place-items:center;font-size:21px}.uploadcopy strong{display:block;color:var(--navy);font-size:14px}.uploadcopy span{display:block;color:var(--muted);font-size:11px;margin-top:3px}
.actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.btn{border:0;border-radius:10px;padding:11px 17px;font-weight:800;cursor:pointer;transition:.15s}.btn:hover{transform:translateY(-1px)}.btn-primary{background:var(--navy);color:white}.btn-blue{background:var(--blue);color:white}.fileinput{max-width:410px}
#status{font-size:12px;color:var(--muted);margin-top:11px}
.section{padding:24px 26px;margin-top:18px}.section h2{margin:4px 0 16px;font-size:20px;color:var(--navy);letter-spacing:-.25px}.section p{color:#405166}
.summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.summary-card{border:1px solid var(--line);border-radius:13px;padding:15px;background:#fbfcfe}.summary-label{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:#7a8899;font-weight:900}.summary-value{font-size:15px;font-weight:800;margin-top:7px;color:var(--ink);display:flex;gap:8px;align-items:center}.state{width:20px;height:20px;border-radius:50%;display:inline-grid;place-items:center;font-size:11px;font-weight:900}.state.ok{background:#e7f6eb;color:var(--ok)}.state.neutral{background:#eef2f7;color:#617084}.state.warn{background:#fff3d6;color:var(--warn)}
.piece-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.piece{border:1px solid var(--line);border-radius:13px;padding:15px;background:#fff}.piece-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.piece-icon{width:34px;height:34px;border-radius:9px;background:var(--teal-soft);color:var(--teal);display:grid;place-items:center;font-weight:900}.piece-name{font-weight:850;color:var(--navy);font-size:14px;flex:1}.source{font-size:11px;color:var(--muted);margin-top:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.page-chip{display:inline-flex;align-items:center;padding:5px 8px;border-radius:999px;background:#edf3f8;color:#3e5268;font-size:10px;font-weight:800}
details.mentions{border:1px solid var(--line);border-radius:14px;background:#fff;margin-top:18px;overflow:hidden}.mentions summary{list-style:none;cursor:pointer;padding:17px 18px;display:flex;justify-content:space-between;gap:14px;align-items:center}.mentions summary::-webkit-details-marker{display:none}.mentions-title{font-weight:850;color:var(--navy)}.mentions-sub{font-size:11px;color:var(--muted);display:block;margin-top:2px}.chev{font-size:13px;color:var(--muted)}.mention-body{border-top:1px solid var(--line);padding:12px 18px 16px;background:#fbfcfe}.mention-row{display:flex;justify-content:space-between;gap:16px;padding:10px 0;border-bottom:1px dashed #dce5ed}.mention-row:last-child{border-bottom:0}.mention-row b{font-size:12px;color:#31465b}.mention-row span{font-size:10px;color:var(--muted);text-align:right}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}.finding{border:1px solid #e1e8ef;border-radius:12px;padding:14px;background:#fcfdfe;margin:9px 0;display:grid;grid-template-columns:30px 1fr;gap:11px}.finding-num{width:28px;height:28px;border-radius:8px;background:var(--navy);color:#fff;display:grid;place-items:center;font-size:11px;font-weight:900}.finding-text{font-size:12px;color:#2a3c50}.finding-foot{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}.file-name{font-size:10px;color:var(--muted);max-width:360px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.warning{border:1px solid #efdca6;border-left:3px solid #d99a16;background:var(--warn-soft);padding:13px 15px;border-radius:0 10px 10px 0;font-size:12px;margin:9px 0}
.qa{display:flex;gap:10px}.qa input{flex:1;min-width:0;border:1px solid #b9c8d7;border-radius:11px;padding:13px 14px;outline:none}.qa input:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(36,88,211,.08)}
.answer-box{display:none;margin-top:16px;border:1px solid #d8e5f3;border-radius:14px;background:#f8fbff;overflow:hidden}.answer-head{padding:11px 14px;background:#eef5fb;border-bottom:1px solid #d8e5f3;font-size:11px;text-transform:uppercase;letter-spacing:.08em;font-weight:900;color:var(--navy)}.answer-text{padding:15px;font-size:13px;color:#26394f}.sources{padding:0 15px 15px}.source-card{display:inline-block;border:1px solid #dce5ed;background:white;border-radius:9px;padding:7px 9px;margin:4px 5px 0 0;font-size:10px;color:#536579}
.footer-actions{display:flex;justify-content:space-between;gap:18px;align-items:center}.footnote{font-size:11px;color:var(--muted);max-width:720px}
.loading{display:inline-flex;gap:8px;align-items:center}.spinner{width:14px;height:14px;border:2px solid #ccd6e1;border-top-color:var(--teal);border-radius:50%;animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.empty{font-size:12px;color:var(--muted);padding:6px 0}

.demo-panel{background:linear-gradient(180deg,#fff,#fbfdff)}
.demo-grid{display:grid;grid-template-columns:1.25fr .75fr;gap:28px;align-items:center}
.demo-actions{display:flex;flex-direction:column;align-items:flex-end;gap:12px}
.demo-badges{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}
.demo-badges span{font-size:10px;font-weight:800;color:#52677b;border:1px solid var(--line);background:#fff;border-radius:999px;padding:5px 8px}
.demo-features{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px;padding-top:17px;border-top:1px solid var(--line)}
.demo-features div{padding:10px 12px;border-radius:10px;background:#f7fafc;border:1px solid #e4ebf1}
.demo-features b{display:block;color:var(--navy);font-size:12px}
.demo-features span{display:block;color:var(--muted);font-size:10px;margin-top:3px}
.demo-note{font-size:10px;color:var(--muted);margin-top:10px}
@media(max-width:1050px){.hero{grid-template-columns:1fr}.hero-side{display:none}.piece-grid{grid-template-columns:repeat(2,1fr)}.summary-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:1050px){.demo-grid{grid-template-columns:1fr}.demo-actions{align-items:flex-start}.demo-badges{justify-content:flex-start}.demo-features{grid-template-columns:repeat(2,1fr)}}
@media(max-width:760px){.demo-features{grid-template-columns:1fr}}
@media(max-width:760px){.topbar-inner,.shell{width:min(100% - 24px,1460px)}.shell{margin-top:18px}.hero-main,.panel,.section{padding:20px}.hero h1{font-size:34px}.cols,.piece-grid,.summary-grid{grid-template-columns:1fr}.uploadbox,.qa,.footer-actions{flex-direction:column;align-items:stretch}.btn{width:100%}}
</style>
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <div class="brand">
      <div class="brandmark">F.AI</div>
      <div class="brandtext"><strong>Fiscaliza.AI Municipal</strong><span>Copiloto auditável para gestão pública</span></div>
    </div>
    <div class="live"><span class="dot"></span><span>Sistema operacional</span></div>
  </div>
</header>

<main class="shell">
  <section class="hero">
    <div class="hero-main">
      <div class="eyebrow">Análise documental com rastreabilidade</div>
      <h1>Do processo extenso à evidência que sustenta a decisão.</h1>
      <p>Organize peças, identifique contradições, acompanhe o contraditório e consulte os autos com indicação de páginas — sem substituir a análise humana.</p>
      <div class="trust">
        <span>✓ OCR em português</span><span>✓ Peça ≠ menção</span><span>✓ Respostas com fonte</span><span>✓ Decisão humana preservada</span>
      </div>
    </div>
    <aside class="hero-side">
      <div>
        <h3>Fluxo de auditoria</h3>
        <div class="step"><div class="num">01</div><div><b>Leitura</b><small>PDF textual ou digitalizado.</small></div></div>
        <div class="step"><div class="num">02</div><div><b>Classificação</b><small>Peças e menções separadas.</small></div></div>
        <div class="step"><div class="num">03</div><div><b>Consulta</b><small>Resposta ligada à evidência.</small></div></div>
      </div>
      <div class="version">VERSÃO 3.6 · DEMONSTRAÇÃO GUIADA</div>
    </aside>
  </section>

  <section class="panel demo-panel">
    <div class="demo-grid">
      <div>
        <div class="kicker">Teste da banca</div>
        <h2 class="title">Veja o diferencial em 30 segundos</h2>
        <p class="desc">Carregue um processo inteiramente fictício de entrega parcial. O sistema executa a mesma análise usada para qualquer PDF enviado.</p>
      </div>
      <div class="demo-actions">
        <div class="demo-badges"><span>11 páginas</span><span>dados fictícios</span><span>sem cadastro</span></div>
        <button class="btn btn-blue" onclick="testarDemo()">Testar demonstração →</button>
      </div>
    </div>
    <div class="demo-features">
      <div><b>Rastreabilidade</b><span>Cada achado aponta a página de origem.</span></div>
      <div><b>Peça ≠ menção</b><span>Citação interna não vira documento autônomo.</span></div>
      <div><b>Sabe dizer “não sei”</b><span>Não presume sanção ou fato sem evidência suficiente.</span></div>
      <div><b>Decisão continua humana</b><span>A ferramenta organiza e confronta; a autoridade decide.</span></div>
    </div>
    <div class="demo-note">Cenário fictício criado exclusivamente para demonstração e avaliação do produto.</div>
  </section>

  <section class="panel">
    <div class="panel-head"><div><div class="kicker">Analisar seus documentos</div><h2 class="title">Carregue os autos do processo</h2><p class="desc">Selecione um ou mais PDFs. O sistema organiza as evidências por página.</p></div></div>
    <div class="uploadbox">
      <div class="uploadcopy"><div class="uploadicon">↥</div><div><strong>Selecione os documentos</strong><span>PDFs com texto ou páginas escaneadas.</span></div></div>
      <div class="actions"><input class="fileinput" id="files" type="file" multiple accept="application/pdf"><button class="btn btn-primary" onclick="analisar()">Analisar processo</button></div>
    </div>
    <div id="status"></div>
  </section>

  <div id="result"></div>

  <section class="panel">
    <div class="panel-head"><div><div class="kicker">Consulta aos autos</div><h2 class="title">Pergunte ao processo</h2><p class="desc">Faça perguntas objetivas. As respostas vêm acompanhadas das fontes disponíveis.</p></div></div>
    <div class="qa"><input id="q" type="text" placeholder="Ex.: A empresa apresentou defesa? Em quais páginas e quais os principais argumentos?"><button class="btn btn-blue" onclick="perguntar()">Perguntar</button></div>
    <div id="answer" class="answer-box"><div class="answer-head">Resposta fundamentada</div><div id="answerText" class="answer-text"></div><div id="sources" class="sources"></div></div>
  </section>

  <section class="panel">
    <div class="footer-actions">
      <div><div class="kicker">Documentação da análise</div><h2 class="title">Relatório para revisão humana</h2><p class="footnote">Consolida achados automáticos e referências. Não substitui a decisão administrativa nem dispensa a conferência dos autos originais.</p></div>
      <button class="btn btn-primary" onclick="relatorio()">Baixar relatório PDF</button>
    </div>
  </section>
</main>

<script>
var analysisId=null; var demoMode=false;
function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;")}
function pagesText(p){return p.join(", ")}
function sourceLabel(file){
  var m=String(file||"").match(/Protocolo[-_ ]?([0-9.]+)/i);
  if(m)return "Processo "+m[1];
  var s=String(file||"").replace(/\.pdf$/i,"").replace(/[-_]+/g," ");
  return s.length>46?s.slice(0,46)+"…":s
}
function stateIcon(ok,unknown){return '<span class="state '+(unknown?'neutral':ok?'ok':'warn')+'">'+(unknown?'?':ok?'✓':'!')+'</span>'}
function pageChip(pg){return '<span class="page-chip">p. '+esc(pg)+'</span>'}
async function testarDemo(){
  var st=document.getElementById("status");
  st.innerHTML='<span class="loading"><span class="spinner"></span> Preparando processo fictício…</span>';
  try{
    var r=await fetch("/api/demo-pdf");
    if(!r.ok)throw new Error("Falha ao carregar a demonstração");
    var blob=await r.blob();
    var file=new File([blob],"Processo-Demonstrativo-FiscalizaAI.pdf",{type:"application/pdf"});
    var dt=new DataTransfer();dt.items.add(file);
    document.getElementById("files").files=dt.files;
    demoMode=true;
    await analisar();
  }catch(e){
    st.textContent="Não foi possível abrir a demonstração.";
  }finally{
    demoMode=false;
  }
}
async function analisar(){
  var fs=document.getElementById("files").files;if(!fs.length){alert("Selecione pelo menos um PDF.");return}
  var fd=new FormData();for(var i=0;i<fs.length;i++)fd.append("files",fs[i]);
  var st=document.getElementById("status");st.innerHTML='<span class="loading"><span class="spinner"></span> Lendo e classificando os documentos…</span>';
  var r=await fetch("/api/analyze",{method:"POST",body:fd});var d=await r.json();
  if(!r.ok){st.textContent=d.detail||"Não foi possível analisar os documentos.";return}
  analysisId=d.analysis_id;localStorage.setItem("fiscaliza_analysis_id",analysisId);
  st.textContent=demoMode?("Demonstração fictícia carregada · "+d.pages+" páginas · análise real executada"): (d.pages+" páginas analisadas · OCR em "+d.ocr_pages+" página(s)");
  var a=d.analysis;var h="";
  var qUnknown=String(a.quantity.value).toLowerCase().indexOf("não identificado")>=0;

  h+='<section class="section"><div class="kicker">Resumo executivo</div><h2>Análise assistida</h2><p>'+esc(a.conclusion)+'</p><div class="summary-grid">';
  h+='<div class="summary-card"><div class="summary-label">Defesa</div><div class="summary-value">'+stateIcon(a.has.defesa,false)+(a.has.defesa?"Localizada":"Não localizada")+'</div></div>';
  h+='<div class="summary-card"><div class="summary-label">Notificação / intimação</div><div class="summary-value">'+stateIcon(a.has.notificacao||a.has.intimacao,false)+((a.has.notificacao||a.has.intimacao)?"Localizada":"Não localizada")+'</div></div>';
  h+='<div class="summary-card"><div class="summary-label">Decisão</div><div class="summary-value">'+stateIcon(a.has.decisao,false)+(a.has.decisao?"Localizada":"Não localizada")+'</div></div>';
  h+='<div class="summary-card"><div class="summary-label">Quantidade total</div><div class="summary-value">'+stateIcon(!qUnknown,qUnknown)+esc(qUnknown?"Inconclusivo":a.quantity.value)+'</div></div></div></section>';

  h+='<section class="section"><div class="kicker">Peças essenciais</div><h2>Estrutura do processo</h2><div class="piece-grid">';
  if(!a.pieces.length)h+='<div class="empty">Nenhuma peça classificada com segurança.</div>';
  for(var j=0;j<a.pieces.length;j++){
    var x=a.pieces[j], ptxt=pagesText(x.pages), sl=sourceLabel(x.file);
    h+='<article class="piece" title="'+esc(x.file)+'"><div class="piece-top"><div class="piece-icon">✓</div><div class="piece-name">'+esc(x.label)+'</div>'+pageChip(ptxt)+'</div><div class="source">'+esc(sl)+'</div></article>'
  }
  h+='</div></section>';

  h+='<details class="mentions"><summary><div><span class="mentions-title">Referências internas</span><span class="mentions-sub">Ver '+a.mentions.length+' tipos de menções que não foram tratadas como peças autônomas</span></div><span class="chev">▾</span></summary><div class="mention-body">';
  if(!a.mentions.length)h+='<div class="empty">Nenhuma menção adicional relevante.</div>';
  for(var j=0;j<a.mentions.length;j++){
    var x=a.mentions[j];h+='<div class="mention-row"><b>'+esc(x.label)+'</b><span title="'+esc(x.file)+'">'+esc(sourceLabel(x.file))+' · p. '+esc(pagesText(x.pages))+'</span></div>'
  }
  h+='</div></details>';

  h+='<div class="cols"><section class="section"><div class="kicker">Contraditório</div><h2>Elementos favoráveis à defesa</h2>';
  if(!a.defense.length)h+='<div class="empty">Nenhum argumento específico extraído automaticamente.</div>';
  for(var j=0;j<a.defense.length;j++){
    var x=a.defense[j];h+='<div class="finding"><div class="finding-num">'+(j+1)+'</div><div><div class="finding-text">'+esc(x.text)+'</div><div class="finding-foot">'+pageChip(x.page)+'<span class="file-name" title="'+esc(x.file)+'">'+esc(sourceLabel(x.file))+'</span></div></div></div>'
  }
  h+='</section><section class="section"><div class="kicker">Confronto documental</div><h2>Pontos a confrontar</h2>';
  if(!a.contra.length)h+='<div class="empty">Nenhum ponto contrário específico extraído automaticamente.</div>';
  for(var j=0;j<a.contra.length;j++){
    var x=a.contra[j];h+='<div class="finding"><div class="finding-num">'+(j+1)+'</div><div><div class="finding-text">'+esc(x.text)+'</div><div class="finding-foot">'+pageChip(x.page)+'<span class="file-name" title="'+esc(x.file)+'">'+esc(sourceLabel(x.file))+'</span></div></div></div>'
  }
  h+='</section></div>';

  h+='<section class="section"><div class="kicker">Cautelas da análise</div><h2>Pendências e limites</h2>';
  if(!a.pending.length)h+='<div class="empty">Nenhuma pendência automática relevante identificada.</div>';
  for(var j=0;j<a.pending.length;j++)h+='<div class="warning">'+esc(a.pending[j])+'</div>';
  h+='</section>';

  document.getElementById("result").innerHTML=h;
  document.getElementById("result").scrollIntoView({behavior:"smooth",block:"start"});
}
async function perguntar(){
  var q=document.getElementById("q").value.trim();if(!q)return;
  analysisId=analysisId||localStorage.getItem("fiscaliza_analysis_id");
  var box=document.getElementById("answer"),txt=document.getElementById("answerText"),src=document.getElementById("sources");
  box.style.display="block";
  if(!analysisId){txt.textContent="Analise um processo primeiro.";src.innerHTML="";return}
  txt.innerHTML='<span class="loading"><span class="spinner"></span> Consultando os autos…</span>';src.innerHTML="";
  var r=await fetch("/api/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({analysis_id:analysisId,question:q})});
  var d=await r.json();if(!r.ok){txt.textContent=d.detail||"Não foi possível responder.";return}
  txt.textContent=d.answer;
  src.innerHTML=(d.sources||[]).map(function(x){return '<span class="source-card">'+esc(x)+'</span>'}).join("");
}
function relatorio(){analysisId=analysisId||localStorage.getItem("fiscaliza_analysis_id");if(!analysisId){alert("Analise um processo primeiro.");return}location.href="/api/report/"+analysisId}
document.getElementById("q").addEventListener("keydown",function(e){if(e.key==="Enter")perguntar()});
</script>
</body>
</html>"""


# --- Precisão e demonstração auditável v3.7 ---
# Corrige o caso demonstrativo sem criar respostas pré-montadas: a linha do tempo
# e a matriz são derivadas dos mesmos achados produzidos pelo motor de análise.

CONT = {
    "defesa":["dos fatos","do direito","requer","contratada","penalidade","proporcionalidade","regularizacao","cronograma"],
    "notificacao":["notificad","prazo","manifestacao","descumprimento","ciencia"],
    "intimacao":["intimad","prazo","defesa","manifestacao","contraditorio"],
    "parecer_juridico":["fundamentacao","conclusao","recomenda","juridico","autoridade"],
    "parecer_tecnico":["analise tecnica","conclusao","fiscalizacao","execucao","entrega"],
    "decisao":["decisao","determino","autorizo","rescis","extinc","instauracao"],
    "contrato":["clausula","contratante","contratada","objeto","vigencia","prazo"]
}

def strong_type(p):
    raw = p["text"] or ""
    z = norm(raw)
    first = norm(raw[:850])
    head = norm(raw[:1900])

    # Cabeçalhos/documentos autônomos primeiro.
    if re.search(r"\bcontrato(?: administrativo)?\s*(?:n|no|numero|nº)", first) and "contratante" in z and "contratada" in z:
        return "contrato"

    if ("notificacao extrajudicial" in first or "notificacao administrativa" in first
        or re.search(r"^\s*notificacao\s*(?:n|no|numero|nº)", first)):
        return "notificacao"

    # Importante: intimação vem antes de defesa para não classificar
    # "intimada a apresentar defesa" como a própria defesa.
    if ("fica a empresa intimada" in head or "fica intimado" in head or "fica intimada" in head
        or re.search(r"^\s*intimacao\s*(?:n|no|numero|nº)", first)):
        return "intimacao"

    if (re.search(r"^\s*defesa administrativa\b", first)
        or re.search(r"^\s*razoes de defesa\b", first)
        or re.search(r"^\s*defesa\b", first)
        or re.search(r"\b(?:vem|comparece).{0,120}\bapresentar\s+(?:a\s+|sua\s+)?defesa\b", head)):
        return "defesa"

    if ("parecer juridico" in first or ("procuradoria" in first and "parecer" in first)):
        return "parecer_juridico"

    if ("parecer tecnico" in first or "relatorio tecnico" in first or "manifestacao tecnica" in first):
        return "parecer_tecnico"

    if ("decisao administrativa" in first
        or re.search(r"^\s*(decido|resolvo|determino|autorizo)\b", first)
        or (any(k in head for k in ["decido","resolvo","determino","autorizo"])
            and any(k in z for k in ["rescis","extinc","processo administrativo sancionador","instauracao"]))):
        return "decisao"

    if re.search(r"^\s*termo de recebimento\b", first) and any(k in z for k in ["recebemos","atesto","recebimento definitivo","recebimento provisorio"]):
        return "termo_recebimento"
    if "danfe" in first or re.search(r"^\s*nota fiscal(?: eletronica)?\b", first):
        return "nota_fiscal"
    if re.search(r"^\s*(nota de )?empenho\b", first):
        return "empenho"
    if re.search(r"^\s*(ordem|autorizacao) de fornecimento\b", first):
        return "ordem_fornecimento"
    return None

def total_quantity(pages):
    # Primeiro busca linguagem contratual explícita. Evita usar números soltos.
    pats = [
        r"(?:quantidade total|quantidade contratada|quantidade prevista)\s*[:\-]?\s*(\d{1,7})",
        r"(?:objeto\s*[:\-]?\s*)?(?:fornecimento|aquisicao)\s+(?:de\s+)?(\d{1,7})\s+(?:kits|unidades|itens)\b",
        r"\b(\d{1,7})\s+(?:kits|unidades|itens)\s+contratad[oa]s?\b",
        r"quantidade\s*[:\-]?\s*(\d{1,7})\s+(?:unidades|unid\.?|kits|itens)\b"
    ]
    ordered = sorted(pages, key=lambda p: (0 if strong_type(p)=="contrato" else 1, p["page"]))
    for p in ordered:
        z = norm(p["text"])
        for pat in pats:
            for m in re.finditer(pat, z):
                ctx = z[max(0,m.start()-120):min(len(z),m.end()+170)]
                if any(b in ctx for b in ["por viagem","metade da quantidade","50% da quantidade","estimativa de transporte","restantes"]):
                    continue
                try:
                    value = int(m.group(1))
                except Exception:
                    continue
                if 1 <= value <= 10000000:
                    return {"value":str(value),"source":{"file":p["file"],"page":p["page"]}}
    return {"value":"Não identificado com segurança","source":None}

def analyze_pages(pages):
    prows,mrows = classify_pages(pages)
    pieces,mentions = grouped(prows),grouped(mrows)
    has = {k:any(x["type"]==k for x in pieces) for k in LABELS}

    no_delivery = snippets(pages,[r"nenhuma entrega",r"nao houve entrega",r"nao realizou.*entrega",r"nao foram entregues",r"inexecucao total"],5)
    sanction = snippets(pages,[r"abertura.*processo administrativo sancionador",r"instauracao.*processo administrativo sancionador",r"instaurar.*processo administrativo sancionador"],3)
    delivery = snippets(pages,[r"foram entregues",r"foi entregue",r"entrega realizada",r"recebido.*objeto",r"execucao parcial"],4)

    pending=[]
    # Se o próprio processo registra que parte do objeto não foi entregue,
    # ausência de termo de recebimento não vira falsa pendência automática.
    if delivery and not no_delivery and not has["termo_recebimento"]:
        pending.append("Há indício de entrega, mas não foi localizado termo de recebimento como peça autônoma.")
    if not has["defesa"]:
        pending.append("Não foi localizada defesa administrativa como peça autônoma com segurança.")
    if not(has["notificacao"] or has["intimacao"]):
        pending.append("Não foi localizada notificação/intimação como peça autônoma com segurança.")
    if sanction:
        pending.append("Os autos indicam abertura/instauração de processo sancionador posterior; não presuma sanção final a partir deste PDF.")

    dp={p for x in pieces if x["type"]=="defesa" for p in x["pages"]}
    defense = snippets(
        pages,
        [r"reequilibr",r"aumento.*custo",r"frete",r"impossibil",r"inviabil",r"forca maior",
         r"rescis",r"atraso",r"fornecedor",r"materia.?prima",r"proporcional",r"penalidade",
         r"regularizacao",r"cronograma"],
        7,
        dp if dp else None
    )
    contra = snippets(
        pages,
        [r"nenhuma entrega",r"nao houve entrega",r"nao foram entregues",r"entrega parcial",
         r"execucao parcial",r"descumpr",r"inexecucao",r"ausencia.*restantes",
         r"rescisao unilateral",r"extincao unilateral"],
        7
    )

    if sanction:
        conclusion="Os autos registram abertura/instauração de processo administrativo sancionador posterior. Isso não equivale a sanção já aplicada."
    elif has["decisao"] and has["defesa"] and (has["notificacao"] or has["intimacao"]):
        conclusion="Foram localizadas peças relevantes de contraditório e decisão. A ferramenta organiza a evidência; a decisão permanece humana."
    else:
        conclusion="Nem todas as peças esperadas foram identificadas como documentos autônomos com segurança. Menções no corpo dos autos não são tratadas como peças."

    return {
        "pieces":pieces,"mentions":mentions,"has":has,"defense":defense,"contra":contra,
        "pending":pending,"quantity":total_quantity(pages),"conclusion":conclusion,
        "no_delivery":no_delivery
    }

def arg_categories(pages,dpages):
    cats=[
        ("reequilíbrio econômico-financeiro",[r"reequilibr"]),
        ("atraso de fornecedor/matéria-prima",[r"atraso",r"fornecedor",r"materia.?prima"]),
        ("aumento de custos/frete",[r"aumento.*custo",r"frete"]),
        ("impossibilidade/inviabilidade de execução",[r"impossibil",r"inviabil"]),
        ("pedido de rescisão/encerramento",[r"rescis",r"encerramento"]),
        ("proporcionalidade da penalidade",[r"proporcional",r"penalidade"]),
        ("plano de regularização",[r"regularizacao",r"cronograma"])
    ]
    out=[]
    for label,pats in cats:
        found=[]
        for p in pages:
            if p["page"] not in dpages: continue
            z=norm(p["text"])
            if any(re.search(x,z) for x in pats): found.append(p["page"])
        if found: out.append((label,sorted(set(found))))
    return out

# UI: cria linha do tempo e matriz a partir dos achados reais retornados pelo motor.
HTML = HTML.replace(
    "@media(max-width:1050px)",
    """.timeline{display:grid;grid-template-columns:repeat(7,minmax(120px,1fr));gap:8px;overflow-x:auto;padding-bottom:4px;margin-top:8px}
.timeline-step{min-width:120px;border-top:3px solid var(--teal);background:#fbfcfe;border-radius:0 0 10px 10px;padding:11px}
.timeline-step .tp{font-size:9px;font-weight:900;color:var(--teal);text-transform:uppercase;letter-spacing:.07em}
.timeline-step b{display:block;color:var(--navy);font-size:11px;margin-top:4px}
.matrix{width:100%;border-collapse:collapse;margin-top:8px}
.matrix th,.matrix td{text-align:left;border-bottom:1px solid var(--line);padding:10px 11px;font-size:11px}
.matrix th{background:#f8fafc;color:#718196;text-transform:uppercase;letter-spacing:.08em;font-size:9px}
.matrix-ok{color:var(--teal);font-weight:850}.matrix-limit{color:var(--warn);font-weight:850}
@media(max-width:1050px)"""
)

_anchor = """  h+='<section class="section"><div class="kicker">Peças essenciais</div><h2>Estrutura do processo</h2><div class="piece-grid">';"""
_insert = """  var ordered=(a.pieces||[]).slice().sort(function(x,y){return (x.pages[0]||9999)-(y.pages[0]||9999)});
  if(ordered.length){
    h+='<section class="section"><div class="kicker">Cronologia dos autos</div><h2>Linha do tempo do processo</h2><div class="timeline">';
    for(var ti=0;ti<ordered.length;ti++){var tp=ordered[ti];h+='<div class="timeline-step"><div class="tp">p. '+esc(pagesText(tp.pages))+'</div><b>'+esc(tp.label)+'</b></div>'}
    h+='</div></section>';
  }

  var matrixRows=[
    ["Há contrato?",a.has.contrato?"Sim":"Não identificado",a.has.contrato,"contrato"],
    ["Houve notificação/intimação?",(a.has.notificacao||a.has.intimacao)?"Sim":"Não identificado",(a.has.notificacao||a.has.intimacao),"notificacao"],
    ["Há defesa administrativa?",a.has.defesa?"Sim":"Não identificado",a.has.defesa,"defesa"],
    ["Há decisão?",a.has.decisao?"Sim":"Não identificado",a.has.decisao,"decisao"],
    ["Quantidade total?",qUnknown?"Não identificada com segurança":a.quantity.value,!qUnknown,"quantidade"]
  ];
  function matrixSource(kind){
    if(kind==="quantidade"&&a.quantity.source)return "p. "+a.quantity.source.page;
    var xs=(a.pieces||[]).filter(function(x){return kind==="notificacao"?(x.type==="notificacao"||x.type==="intimacao"):x.type===kind});
    return xs.length?"p. "+pagesText(xs[0].pages):"—";
  }
  h+='<section class="section"><div class="kicker">Auditabilidade</div><h2>Matriz de evidências</h2><table class="matrix"><thead><tr><th>Questão</th><th>Resposta</th><th>Fonte</th><th>Status</th></tr></thead><tbody>';
  for(var mi=0;mi<matrixRows.length;mi++){var mr=matrixRows[mi];h+='<tr><td>'+esc(mr[0])+'</td><td>'+esc(mr[1])+'</td><td>'+matrixSource(mr[3])+'</td><td class="'+(mr[2]?'matrix-ok':'matrix-limit')+'">'+(mr[2]?'Confirmado':'Limite')+'</td></tr>'}
  h+='</tbody></table></section>';

  h+='<section class="section"><div class="kicker">Peças essenciais</div><h2>Estrutura do processo</h2><div class="piece-grid">';"""
if _anchor in HTML:
    HTML = HTML.replace(_anchor, _insert, 1)

HTML = HTML.replace("VERSÃO 3.6 · DEMONSTRAÇÃO GUIADA","VERSÃO 3.7 · DEMONSTRAÇÃO AUDITÁVEL")


# --- Gerador de minuta de notificação v3.8 ---
class NotificationReq(BaseModel):
    analysis_id: str

def _first_match(text, patterns, default="[NÃO IDENTIFICADO AUTOMATICAMENTE]"):
    for pat in patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            return re.sub(r"\s+"," ",m.group(1)).strip(" .;:-")
    return default

def _metadata_from_pages(pages):
    text = "\n".join(p["text"] or "" for p in pages)
    process_no = _first_match(text, [
        r"Processo Administrativo(?: de Penaliza[cç][aã]o)?\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)",
        r"Processo\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)"
    ])
    ata = _first_match(text, [
        r"Ata de Registro de Pre[cç]os\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)"
    ])
    pregao = _first_match(text, [
        r"Preg[aã]o Eletr[oô]nico\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)"
    ])
    empenho = _first_match(text, [
        r"Nota de Empenho(?: Ordin[aá]rio)?\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)"
    ])
    cnpj = _first_match(text, [
        r"CNPJ\s*(?:sob\s*o\s*)?(?:n[ºo.]?)?\s*[:\-]?\s*([0-9]{2}\.?[0-9]{3}\.?[0-9]{3}\/?[0-9]{4}-?[0-9]{2})"
    ])
    company = _first_match(text, [
        r"(?:EMPRESA|Empresa|CONTRATADA|Contratada)\s*[:\-]\s*([^\n]{4,150})",
        r"empresa\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][^\n,;]{4,120}(?:LTDA|S\.?A\.?|EIRELI|ME|EPP))"
    ])
    return {"processo":process_no,"ata":ata,"pregao":pregao,"empenho":empenho,"empresa":company,"cnpj":cnpj}

def _legal_refs(pages):
    refs=[]
    patterns=[
        r"(Lei(?: Federal)?\s*n[ºo.]?\s*[\d.\/-]+[^.\n]{0,180}(?:art\.?|artigo)\s*\d+[^.\n]{0,120})",
        r"(Decreto(?: Municipal)?\s*n[ºo.]?\s*[\d.\/-]+[^.\n]{0,180}(?:art\.?|artigo)\s*\d+[^.\n]{0,120})",
        r"((?:art\.?|artigo)\s*\d+[^.\n]{0,120}Lei(?: Federal)?\s*n[ºo.]?\s*[\d.\/-]+)"
    ]
    for p in pages:
        raw=re.sub(r"\s+"," ",p["text"] or "")
        for pat in patterns:
            for m in re.finditer(pat, raw, flags=re.I):
                val=clip(m.group(1),260)
                key=norm(val)
                if key and all(norm(x["text"])!=key for x in refs):
                    refs.append({"page":p["page"],"text":val})
                    if len(refs)>=6:return refs
    return refs

def _draft_notification(item):
    pages=item["pages"]; a=item["analysis"]; md=_metadata_from_pages(pages)
    facts=[{"page":s["page"],"text":clip(s["text"],420)} for s in (a.get("contra") or [])[:5]]
    if not facts:
        for p in pages[:6]:
            txt=clip(p["text"],360)
            if txt:facts.append({"page":p["page"],"text":txt})
            if len(facts)>=4:break
    defenses=[{"page":s["page"],"text":clip(s["text"],420)} for s in (a.get("defense") or [])[:4]]
    legal=_legal_refs(pages)

    header=[
        "MINUTA — NOTIFICAÇÃO DE INSTAURAÇÃO DE PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO","",
        "Processo Administrativo de Penalização: nº "+md["processo"],
        "Ata de Registro de Preços: nº "+md["ata"],
        "Pregão Eletrônico: nº "+md["pregao"],
        "Nota de Empenho: nº "+md["empenho"],
        "Empresa: "+md["empresa"],
        "CNPJ: "+md["cnpj"],"",
        "Assunto: Notificação de instauração de Processo Administrativo de Penalização e abertura de prazo para apresentação de defesa.",""
    ]
    body=[
        "[ÓRGÃO/ENTIDADE], por intermédio de [COMISSÃO/UNIDADE COMPETENTE], no uso das atribuições previstas em [NORMA DE COMPETÊNCIA], NOTIFICA E INTIMA a empresa "+md["empresa"]+", inscrita no CNPJ sob o nº "+md["cnpj"]+", acerca da instauração do Processo Administrativo de Penalização nº "+md["processo"]+", destinado à apuração dos fatos descritos nesta minuta.","",
        "A presente notificação possui caráter processual e não representa imputação definitiva de responsabilidade ou aplicação antecipada de penalidade. Sua finalidade é dar ciência dos fatos apurados e assegurar o exercício do contraditório e da ampla defesa.","",
        "1. DOS FATOS APURADOS",""
    ]
    if facts:
        for i,x in enumerate(facts,1): body.append(str(i)+". "+x["text"])
    else: body.append("[INSERIR SÍNTESE OBJETIVA DOS FATOS APURADOS]")
    body += ["","2. DOS ELEMENTOS APRESENTADOS PELA EMPRESA",""]
    if defenses:
        for i,x in enumerate(defenses,1): body.append(str(i)+". "+x["text"])
    else: body.append("Até o momento, não foram identificados automaticamente elementos de defesa suficientes para síntese. Conferir os autos.")
    body += ["","3. DO ENQUADRAMENTO JURÍDICO PRELIMINAR",""]
    if legal:
        for i,x in enumerate(legal,1): body.append(str(i)+". "+x["text"])
    else: body.append("[INSERIR E CONFERIR FUNDAMENTAÇÃO LEGAL E REGULAMENTAR APLICÁVEL]")
    body += [
        "",
        "O enquadramento jurídico indicado nesta minuta é preliminar e deverá ser conferido pela autoridade competente. Poderá ser mantido, alterado ou afastado após a análise da defesa e das provas produzidas durante a instrução, não representando decisão antecipada quanto à responsabilidade da empresa.","",
        "4. DO CONTRADITÓRIO, DA AMPLA DEFESA E DAS PROVAS","",
        "Fica a empresa NOTIFICADA E INTIMADA para apresentar defesa escrita e especificar as provas que pretenda produzir no prazo de [PRAZO EM DIAS ÚTEIS], contado na forma prevista em [NORMA APLICÁVEL].","",
        "A empresa poderá apresentar os documentos, esclarecimentos e provas que entender pertinentes à elucidação dos fatos, especialmente aqueles relacionados ao cumprimento da obrigação, às justificativas apresentadas e às circunstâncias que possam ter impedido ou dificultado a execução contratual.","",
        "A defesa e os respectivos documentos deverão ser encaminhados para [CANAL/ENDEREÇO ELETRÔNICO OFICIAL].","",
        "No campo destinado ao assunto deverá constar: DEFESA – PROCESSO ADMINISTRATIVO Nº "+md["processo"]+" – "+md["empresa"]+".","",
        "5. DISPOSIÇÕES FINAIS","",
        "A ausência de apresentação de defesa no prazo concedido implicará o regular prosseguimento do processo, observadas as consequências previstas na legislação e na regulamentação aplicáveis.","",
        "Concluída a instrução, os autos seguirão para relatório e julgamento pela autoridade competente, mediante decisão motivada.","",
        "[MUNICÍPIO/UF], [DATA].","","[NOME DA AUTORIDADE/RESPONSÁVEL]","[CARGO/FUNÇÃO]","",
        "MINUTA AUTOMÁTICA — REVISÃO HUMANA OBRIGATÓRIA ANTES DE EXPEDIÇÃO."
    ]
    sources=[]
    for x in facts:sources.append("Fato · p. "+str(x["page"]))
    for x in defenses:sources.append("Elemento da empresa · p. "+str(x["page"]))
    for x in legal:sources.append("Fundamento jurídico · p. "+str(x["page"]))
    return {"draft":"\n".join(header+body),"metadata":md,"sources":sources}

@app.post("/api/notification-draft")
def notification_draft(req: NotificationReq):
    item=ANALYSES.get(req.analysis_id)
    if not item:
        raise HTTPException(409,"A análise desta sessão não está mais disponível. Analise o processo novamente.")
    return _draft_notification(item)

HTML = HTML.replace(
    "@media(max-width:1050px)",
    """.draft-box{display:none;margin-top:16px;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#fff}
.draft-toolbar{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:12px 14px;background:#f8fafc;border-bottom:1px solid var(--line)}
.draft-toolbar strong{font-size:12px;color:var(--navy)}
.draft-toolbar span{font-size:10px;color:var(--muted)}
.draft-actions{display:flex;gap:8px}
.draft-actions button{padding:8px 11px;font-size:11px}
.draft-text{width:100%;min-height:620px;border:0;outline:0;resize:vertical;padding:18px 20px;font-family:Georgia,"Times New Roman",serif;font-size:13px;line-height:1.65;color:#202a36;background:#fff}
.draft-sources{padding:12px 16px;border-top:1px solid var(--line);background:#fbfcfe}
@media(max-width:1050px)"""
)

_notification_panel = """  <section class="panel">
    <div class="panel-head">
      <div>
        <div class="kicker">Minuta assistida</div>
        <h2 class="title">Notificação de instauração e abertura de prazo para defesa</h2>
        <p class="desc">Gera uma minuta editável a partir das evidências encontradas. Campos não identificados permanecem entre colchetes e exigem conferência humana.</p>
      </div>
      <button class="btn btn-primary" onclick="gerarNotificacao()">Gerar minuta</button>
    </div>
    <div class="warning">A função não aplica penalidade e não substitui a análise jurídica. A minuta deve ser revisada antes de qualquer expedição.</div>
    <div id="draftBox" class="draft-box">
      <div class="draft-toolbar">
        <div><strong>Minuta para revisão</strong><br><span>Texto editável · baseado no processo analisado e em campos de conferência.</span></div>
        <div class="draft-actions">
          <button class="btn btn-blue" onclick="copiarMinuta()">Copiar texto</button>
          <button class="btn btn-primary" onclick="baixarMinuta()">Baixar .txt</button>
        </div>
      </div>
      <textarea id="draftText" class="draft-text"></textarea>
      <div id="draftSources" class="draft-sources"></div>
    </div>
  </section>

"""
_report_marker = """  <section class="panel">
    <div class="footer-actions">
      <div><div class="kicker">Documentação da análise</div><h2 class="title">Relatório para revisão humana</h2>"""
if _report_marker in HTML:
    HTML = HTML.replace(_report_marker, _notification_panel + _report_marker, 1)

_js_marker = "function relatorio(){"
_js = """async function gerarNotificacao(){
  analysisId=analysisId||localStorage.getItem("fiscaliza_analysis_id");
  if(!analysisId){alert("Analise um processo primeiro.");return}
  var box=document.getElementById("draftBox"),ta=document.getElementById("draftText"),src=document.getElementById("draftSources");
  box.style.display="block";ta.value="Gerando minuta a partir das evidências do processo…";src.innerHTML="";
  var r=await fetch("/api/notification-draft",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({analysis_id:analysisId})});
  var d=await r.json();
  if(!r.ok){ta.value=d.detail||"Não foi possível gerar a minuta.";return}
  ta.value=d.draft;
  src.innerHTML='<div class="kicker">Evidências utilizadas</div>'+(d.sources||[]).map(function(x){return '<span class="source-card">'+esc(x)+'</span>'}).join("");
  box.scrollIntoView({behavior:"smooth",block:"start"});
}
async function copiarMinuta(){
  var ta=document.getElementById("draftText");
  if(!ta.value)return;
  try{await navigator.clipboard.writeText(ta.value)}catch(e){ta.select();document.execCommand("copy")}
}
function baixarMinuta(){
  var ta=document.getElementById("draftText");if(!ta.value)return;
  var blob=new Blob([ta.value],{type:"text/plain;charset=utf-8"});
  var a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="minuta-notificacao-penalizacao.txt";a.click();URL.revokeObjectURL(a.href);
}
"""
if _js_marker in HTML:
    HTML = HTML.replace(_js_marker, _js + _js_marker, 1)

HTML = HTML.replace("VERSÃO 3.7 · DEMONSTRAÇÃO AUDITÁVEL","VERSÃO 3.8 · MINUTA ASSISTIDA")


# --- Minuta detalhada v3.9 ---
def _find_deadline_for_defense(pages):
    joined = "\n".join(p["text"] or "" for p in pages)
    pats = [
        r"(?:defesa|manifestação|manifestacao)[^.\n]{0,180}?prazo\s+de\s+([0-9]{1,2}\s*\([^)]+\)\s*dias\s+úteis)",
        r"prazo\s+de\s+([0-9]{1,2}\s*\([^)]+\)\s*dias\s+úteis)[^.\n]{0,180}?(?:defesa|manifestação|manifestacao)",
        r"(?:defesa|manifestação|manifestacao)[^.\n]{0,180}?prazo\s+de\s+([0-9]{1,2}\s+dias\s+úteis)"
    ]
    for pat in pats:
        m=re.search(pat,joined,flags=re.I|re.S)
        if m:return re.sub(r"\s+"," ",m.group(1)).strip()
    return "[PRAZO EM DIAS ÚTEIS — CONFERIR NORMA APLICÁVEL]"

def _find_official_email(pages):
    joined="\n".join(p["text"] or "" for p in pages)
    emails=re.findall(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}",joined,flags=re.I)
    official=[e for e in emails if any(k in e.lower() for k in ["gov.br","prefeitura","municipio","comissao","penal"])]
    return (official[0] if official else (emails[0] if emails else "[ENDEREÇO ELETRÔNICO OFICIAL]"))

def _find_possible_sanctions(pages):
    joined=norm("\n".join(p["text"] or "" for p in pages))
    labels=[]
    tests=[
        ("advertência",["advertencia"]),
        ("multa",["multa"]),
        ("impedimento de licitar e contratar",["impedimento de licitar","impedimento de contratar"]),
        ("declaração de inidoneidade",["declaracao de inidoneidade","inidoneidade"])
    ]
    for label,keys in tests:
        if any(k in joined for k in keys):labels.append(label)
    return labels

def _trace_line(label, rows):
    pgs=sorted(set(int(x.get("page",0)) for x in rows if x.get("page")))
    if not pgs:return ""
    return "[Rastreabilidade interna — "+label+": p. "+", ".join(str(p) for p in pgs)+"]"

def _draft_notification(item):
    pages=item["pages"]
    a=item["analysis"]
    md=_metadata_from_pages(pages)
    deadline=_find_deadline_for_defense(pages)
    channel=_find_official_email(pages)
    sanctions=_find_possible_sanctions(pages)

    facts=[{"page":s["page"],"text":clip(s["text"],560)} for s in (a.get("contra") or [])[:8]]
    defenses=[{"page":s["page"],"text":clip(s["text"],560)} for s in (a.get("defense") or [])[:6]]
    legal=_legal_refs(pages)

    # Complementa a cronologia com páginas de peças processuais.
    piece_map={}
    for x in (a.get("pieces") or []):
        piece_map.setdefault(x["label"],[]).extend(x["pages"])
    piece_rows=[]
    for label,pgs in sorted(piece_map.items(), key=lambda kv:min(kv[1]) if kv[1] else 9999):
        piece_rows.append((label,sorted(set(pgs))))

    total=a.get("quantity",{}).get("value","Não identificado com segurança")
    total_src=a.get("quantity",{}).get("source")
    total_note=(" [Fonte: p. "+str(total_src["page"])+"]") if total_src else ""

    title="MINUTA — NOTIFICAÇÃO EXTRAJUDICIAL DE INSTAURAÇÃO DE PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO"
    lines=[
        title,
        "",
        "NOTIFICAÇÃO EXTRAJUDICIAL Nº [NÚMERO]/[COMISSÃO OU UNIDADE]/[ÓRGÃO]",
        "",
        "Processo Administrativo de Penalização: nº "+md["processo"],
        "Ata de Registro de Preços: nº "+md["ata"],
        "Pregão Eletrônico: nº "+md["pregao"],
        "Nota de Empenho: nº "+md["empenho"],
        "Empresa: "+md["empresa"],
        "CNPJ: "+md["cnpj"],
        "",
        "Assunto: Notificação de instauração de Processo Administrativo de Penalização e abertura de prazo para apresentação de defesa.",
        "",
        "[ÓRGÃO/ENTIDADE], pessoa jurídica de direito público interno, por intermédio de [COMISSÃO/UNIDADE COMPETENTE], representada neste ato por [NOME E CARGO DA AUTORIDADE/RESPONSÁVEL], no uso das atribuições previstas em [NORMA DE COMPETÊNCIA], NOTIFICA E INTIMA a empresa "+md["empresa"]+", inscrita no CNPJ sob o nº "+md["cnpj"]+", acerca da instauração do Processo Administrativo de Penalização nº "+md["processo"]+", destinado à apuração de possível descumprimento das obrigações relacionadas à contratação identificada nesta notificação.",
        "",
        "A presente notificação possui caráter estritamente processual e não representa imputação definitiva de responsabilidade, juízo antecipado de culpabilidade ou aplicação antecipada de penalidade. Destina-se a dar ciência à empresa acerca dos fatos e documentos que fundamentaram a instauração do procedimento, bem como a assegurar o exercício do contraditório e da ampla defesa.",
        "",
        "I — DA IDENTIFICAÇÃO DA CONTRATAÇÃO",
        "",
        "Conforme os documentos analisados, a contratação está relacionada à Ata de Registro de Preços nº "+md["ata"]+", ao Pregão Eletrônico nº "+md["pregao"]+" e à Nota de Empenho nº "+md["empenho"]+".",
        "",
        "A quantidade total identificada automaticamente no processo é "+total+"."+total_note,
        "",
        "Deverão ser conferidos, antes da expedição desta notificação, o objeto completo da contratação, os valores unitários e totais, o prazo contratual de entrega, a data de encaminhamento da Nota de Empenho ou instrumento equivalente e as condições específicas previstas no edital, na ata, no contrato e nos demais documentos da contratação.",
        "",
        "II — DA CRONOLOGIA DOCUMENTAL IDENTIFICADA",
        ""
    ]
    if piece_rows:
        for idx,(label,pgs) in enumerate(piece_rows,1):
            lines.append(str(idx)+". "+label+" identificado(a) nas páginas "+", ".join(str(p) for p in pgs)+" dos autos analisados.")
    else:
        lines.append("[NÃO FOI POSSÍVEL ESTRUTURAR AUTOMATICAMENTE A CRONOLOGIA DAS PEÇAS. CONFERIR OS AUTOS.]")
    lines += [
        "",
        "A cronologia acima é apresentada como instrumento de organização dos autos. A natureza jurídica de cada documento, sua autoria, data, validade, conteúdo integral e efeito processual deverão ser confirmados pela Comissão antes da expedição da notificação.",
        "",
        "III — DOS FATOS APURADOS ATÉ O MOMENTO",
        ""
    ]
    if facts:
        for idx,x in enumerate(facts,1):
            lines.append(str(idx)+". "+x["text"]+" [Fonte: p. "+str(x["page"])+"]")
    else:
        lines.append("[INSERIR SÍNTESE DETALHADA E CRONOLÓGICA DOS FATOS APURADOS.]")
    lines += [
        "",
        "Os fatos acima descritos deverão ser confrontados com o conteúdo integral dos documentos originais, especialmente com o instrumento convocatório, a ata ou contrato, a nota de empenho, comunicações administrativas, comprovantes de ciência, relatórios da fiscalização, documentos de recebimento e eventuais manifestações apresentadas pela contratada.",
        "",
        "IV — DAS ALEGAÇÕES, JUSTIFICATIVAS E ELEMENTOS APRESENTADOS PELA EMPRESA",
        ""
    ]
    if defenses:
        for idx,x in enumerate(defenses,1):
            lines.append(str(idx)+". "+x["text"]+" [Fonte: p. "+str(x["page"])+"]")
    else:
        lines.append("Até o momento, o sistema não identificou com segurança elementos suficientes para sintetizar justificativas ou argumentos apresentados pela empresa. A Comissão deverá conferir se existem pedidos, manifestações, defesas, documentos comprobatórios ou outras justificativas nos autos.")
    lines += [
        "",
        "As alegações e documentos apresentados pela empresa deverão ser analisados de forma individualizada, inclusive quanto à tempestividade, pertinência, vínculo com o objeto contratado, capacidade de demonstrar fato impeditivo ou justificativo e eventual repercussão sobre a responsabilidade administrativa.",
        "",
        "V — DOS PONTOS QUE NECESSITAM DE ESCLARECIMENTO OU CONFRONTO",
        "",
        "Sem prejuízo de outros aspectos que possam ser identificados pela Comissão durante a instrução, deverão ser esclarecidos, conforme aplicável ao caso concreto:",
        "",
        "a) se a obrigação contratual foi cumprida integral ou parcialmente e em que extensão;",
        "b) se houve atraso, inexecução parcial ou inexecução total e quais documentos comprovam essa circunstância;",
        "c) se a empresa foi regularmente cientificada acerca das obrigações, cobranças, notificações e prazos;",
        "d) se a justificativa apresentada guarda relação direta com o objeto contratado e com o período de execução;",
        "e) se eventual fato alegado pela empresa era imprevisível, inevitável ou alheio à sua esfera ordinária de risco empresarial;",
        "f) se foram realizadas diligências concretas para superar o impedimento alegado, inclusive busca por fornecedores, produtos equivalentes ou outras alternativas de cumprimento;",
        "g) se houve comunicação tempestiva à Administração sobre eventual impossibilidade ou dificuldade de execução;",
        "h) se existem prejuízos, custos adicionais, necessidade de nova contratação ou comprometimento da continuidade do serviço público;",
        "i) se há circunstâncias agravantes, atenuantes ou elementos que recomendem solução proporcional ao caso concreto.",
        "",
        "VI — DO ENQUADRAMENTO JURÍDICO PRELIMINAR",
        ""
    ]
    if legal:
        for idx,x in enumerate(legal,1):
            lines.append(str(idx)+". "+x["text"]+" [Fonte: p. "+str(x["page"])+"]")
    else:
        lines.append("[INSERIR E CONFERIR OS DISPOSITIVOS DA LEI Nº 14.133/2021, DO REGULAMENTO MUNICIPAL E DOS INSTRUMENTOS DA CONTRATAÇÃO APLICÁVEIS AO CASO.]")
    lines += [
        "",
        "Os fatos registrados nos autos poderão, em tese, caracterizar infração administrativa prevista na legislação aplicável e nos instrumentos da contratação. O enquadramento jurídico, entretanto, possui natureza preliminar e somente poderá ser confirmado, alterado ou afastado após a análise da defesa, das provas produzidas e do conjunto completo dos autos.",
        "",
        "A indicação preliminar de possível infração não representa antecipação de julgamento, nem dispensa a demonstração dos pressupostos fáticos e jurídicos necessários à eventual responsabilização.",
        "",
        "VII — DAS SANÇÕES EM TESE E DA NECESSIDADE DE DOSIMETRIA",
        ""
    ]
    if sanctions:
        lines.append("Foram localizadas nos documentos analisados referências às seguintes espécies de sanção: "+", ".join(sanctions)+". A Comissão deverá confirmar se tais sanções são juridicamente cabíveis ao enquadramento efetivamente adotado.")
    else:
        lines.append("A eventual sanção somente poderá ser definida após a instrução e o enquadramento jurídico definitivo. Não foi adotada automaticamente nesta minuta qualquer espécie de penalidade.")
    lines += [
        "",
        "Caso ao final da instrução seja reconhecida responsabilidade administrativa, a autoridade competente deverá observar os limites legais e regulamentares aplicáveis e considerar, entre outros fatores, a natureza e a gravidade da infração, as peculiaridades do caso concreto, as circunstâncias agravantes ou atenuantes, os danos eventualmente causados à Administração, a vantagem auferida, a existência de antecedentes e os princípios da razoabilidade e da proporcionalidade, quando cabíveis.",
        "",
        "VIII — DO CONTRADITÓRIO, DA AMPLA DEFESA E DO PRAZO",
        "",
        "Fica a empresa NOTIFICADA E INTIMADA para apresentar defesa escrita e especificar as provas que pretenda produzir, no prazo de "+deadline+", contado na forma estabelecida pela legislação e regulamentação aplicáveis ao procedimento.",
        "",
        "A empresa poderá apresentar todos os documentos, esclarecimentos e provas que entender pertinentes à elucidação dos fatos, especialmente aqueles relacionados ao cumprimento da obrigação, à justificativa apresentada e às circunstâncias que possam ter impedido ou dificultado a execução contratual.",
        "",
        "As provas deverão ser especificadas na defesa, com indicação de sua pertinência para o esclarecimento dos fatos. O eventual indeferimento de prova deverá ser motivado pela autoridade competente, na forma da legislação e regulamentação aplicáveis.",
        "",
        "IX — DA FORMA DE APRESENTAÇÃO DA DEFESA",
        "",
        "A defesa e os respectivos documentos deverão ser encaminhados ao seguinte canal oficial: "+channel+".",
        "",
        "No campo destinado ao assunto deverá constar:",
        "DEFESA – PROCESSO ADMINISTRATIVO Nº "+md["processo"]+" – "+md["empresa"]+".",
        "",
        "Antes da expedição, deverá ser conferido se o endereço eletrônico, protocolo digital ou outro canal indicado está oficialmente autorizado para recebimento da defesa e se existem requisitos de formato, tamanho ou assinatura dos documentos.",
        "",
        "X — DO ACESSO AOS AUTOS E DA CIÊNCIA INTEGRAL",
        "",
        "Deverá ser assegurado à empresa acesso aos documentos que fundamentam a instauração do procedimento, inclusive aos elementos necessários ao exercício efetivo do contraditório e da ampla defesa. Caso a íntegra dos autos seja encaminhada juntamente com esta notificação, registrar expressamente essa circunstância na versão final.",
        "",
        "XI — DA AUSÊNCIA DE DEFESA E DO PROSSEGUIMENTO DO PROCESSO",
        "",
        "A ausência de apresentação de defesa no prazo estabelecido não impede o regular prosseguimento do processo, observadas as consequências especificamente previstas na legislação e no regulamento aplicáveis. Qualquer referência a revelia, preclusão ou presunção deverá ser conferida diretamente na norma municipal e na legislação incidente antes da expedição.",
        "",
        "A empresa poderá intervir no processo posteriormente nos limites admitidos pela legislação aplicável, recebendo-o no estado em que se encontrar, sem prejuízo da validade dos atos regularmente praticados, quando assim previsto no regime jurídico incidente.",
        "",
        "XII — DAS PROVIDÊNCIAS APÓS A DEFESA",
        "",
        "Apresentada a defesa, deverão ser analisados os argumentos e documentos juntados, realizadas as diligências e provas consideradas necessárias e, encerrada a instrução, elaborado relatório conclusivo ou manifestação equivalente, com posterior encaminhamento à autoridade competente para julgamento mediante decisão motivada.",
        "",
        "A decisão final deverá enfrentar os argumentos relevantes apresentados pela defesa, indicar os fatos considerados comprovados, explicitar o enquadramento jurídico adotado e, se for o caso, justificar de forma individualizada a espécie e a dosimetria da sanção.",
        "",
        "XIII — DA RASTREABILIDADE DA MINUTA",
        "",
        _trace_line("fatos utilizados",facts),
        _trace_line("elementos apresentados pela empresa",defenses),
        _trace_line("fundamentos jurídicos encontrados",legal),
        "",
        "As notas de rastreabilidade acima destinam-se à conferência interna da Comissão e podem ser retiradas da versão expedida após a validação dos documentos originais.",
        "",
        "[MUNICÍPIO/UF], [DATA CERTIFICADA].",
        "",
        "[NOME DA AUTORIDADE/RESPONSÁVEL]",
        "[CARGO/FUNÇÃO]",
        "",
        "MINUTA AUTOMÁTICA DETALHADA — REVISÃO HUMANA OBRIGATÓRIA ANTES DE EXPEDIÇÃO."
    ]

    sources=[]
    for x in facts:sources.append("Fato · p. "+str(x["page"]))
    for x in defenses:sources.append("Elemento da empresa · p. "+str(x["page"]))
    for x in legal:sources.append("Fundamento jurídico · p. "+str(x["page"]))
    if total_src:sources.append("Quantidade total · p. "+str(total_src["page"]))
    return {"draft":"\n".join([x for x in lines if x is not None]),"metadata":md,"sources":sources}

HTML = HTML.replace(
    "Notificação de instauração e abertura de prazo para defesa",
    "Notificação detalhada de instauração e abertura de prazo para defesa"
)
HTML = HTML.replace(
    "Gera uma minuta editável a partir das evidências encontradas. Campos não identificados permanecem entre colchetes e exigem conferência humana.",
    "Gera uma minuta extensa, estruturada e editável, com fatos, justificativas, enquadramento preliminar, dosimetria, contraditório, provas, acesso aos autos e rastreabilidade. Campos não identificados permanecem entre colchetes."
)
HTML = HTML.replace("VERSÃO 3.8 · MINUTA ASSISTIDA","VERSÃO 3.9 · MINUTA DETALHADA")


# --- Modelo narrativo institucional v4.0 ---
def _sentence(text):
    t=re.sub(r"\s+"," ",text or "").strip()
    if not t:
        return ""
    if t[-1] not in ".;:":
        t += "."
    return t

def _draft_notification(item):
    pages=item["pages"]
    a=item["analysis"]
    md=_metadata_from_pages(pages)
    deadline=_find_deadline_for_defense(pages)
    channel=_find_official_email(pages)
    sanctions=_find_possible_sanctions(pages)
    legal=_legal_refs(pages)

    facts=[{"page":s["page"],"text":clip(s["text"],700)} for s in (a.get("contra") or [])[:7]]
    defenses=[{"page":s["page"],"text":clip(s["text"],700)} for s in (a.get("defense") or [])[:5]]

    total=a.get("quantity",{}).get("value","Não identificado com segurança")
    total_src=a.get("quantity",{}).get("source")

    title="NOTIFICAÇÃO EXTRAJUDICIAL Nº [NÚMERO]/COMISSÃO DE PENALIZAÇÃO/[SIGLA DO ÓRGÃO]/[MUNICÍPIO]"
    lines=[
        title,
        "",
        "Processo Administrativo de Penalização: nº "+md["processo"],
        "Ata de Registro de Preços: nº "+md["ata"],
        "Pregão Eletrônico: nº "+md["pregao"],
        "Nota de Empenho: nº "+md["empenho"],
        "Empresa: "+md["empresa"],
        "CNPJ: "+md["cnpj"],
        "",
        "Assunto: Notificação de instauração de Processo Administrativo de Penalização e abertura de prazo para apresentação de defesa.",
        "",
        "[PREFEITURA/ÓRGÃO], pessoa jurídica de direito público interno, inscrita no CNPJ sob o nº [CNPJ DO ÓRGÃO], por intermédio da Comissão Permanente de Penalização, representada neste ato por [NOME DO RESPONSÁVEL], [CARGO/FUNÇÃO], no uso das atribuições previstas em [NORMA DE COMPETÊNCIA] e [PORTARIA DE DESIGNAÇÃO], NOTIFICA E INTIMA a empresa "+md["empresa"]+", inscrita no CNPJ sob o nº "+md["cnpj"]+", acerca da instauração do Processo Administrativo de Penalização nº "+md["processo"]+", destinado à apuração de possível descumprimento das obrigações decorrentes da contratação vinculada à Nota de Empenho nº "+md["empenho"]+".",
        "",
        "A presente notificação possui caráter processual e não representa imputação definitiva de responsabilidade ou aplicação antecipada de penalidade, destinando-se a dar ciência à empresa dos fatos apurados e a assegurar o exercício do contraditório e da ampla defesa.",
        "",
        "Conforme consta nos autos, a contratação encontra-se vinculada à Nota de Empenho nº "+md["empenho"]+", à Ata de Registro de Preços nº "+md["ata"]+" e ao Pregão Eletrônico nº "+md["pregao"]+". Os dados completos de emissão, pedido, valor, objeto e demais referências da contratação deverão ser conferidos nos documentos originais antes da expedição desta notificação.",
        ""
    ]

    if total!="Não identificado com segurança":
        src=(" conforme registro localizado na página "+str(total_src["page"])+" dos autos" if total_src else "")
        lines.append("A análise documental identificou quantidade total de "+total+src+". A descrição exata dos itens, marcas, valores unitários e totais deverá ser reproduzida na versão final diretamente do instrumento da contratação.")
        lines.append("")
    else:
        lines.append("A quantidade total e a descrição completa do objeto não foram identificadas automaticamente com segurança, devendo ser conferidas e inseridas a partir da Nota de Empenho, contrato, ata ou instrumento equivalente.")
        lines.append("")

    if facts:
        connectors=[
            "Conforme os registros constantes dos autos, ",
            "Ainda segundo a documentação analisada, ",
            "Na sequência, ",
            "Posteriormente, ",
            "De acordo com as manifestações juntadas ao processo, ",
            "Também consta dos autos que ",
            "Por fim, "
        ]
        for i,x in enumerate(facts):
            text=_sentence(x["text"])
            lines.append(connectors[min(i,len(connectors)-1)]+text[0].lower()+text[1:]+" [Fonte interna: p. "+str(x["page"])+"]")
            lines.append("")
    else:
        lines += [
            "[INSERIR NARRATIVA CRONOLÓGICA DETALHADA DOS FATOS CONSTANTES DOS AUTOS, COM DATAS, DOCUMENTOS, PRAZOS, COMUNICAÇÕES E EVENTUAL INEXECUÇÃO.]",
            ""
        ]

    if defenses:
        lines.append("A empresa apresentou elementos e justificativas que deverão integrar a instrução e ser apreciados antes de qualquer conclusão definitiva.")
        lines.append("")
        for i,x in enumerate(defenses):
            if i==0:
                prefix="Com fundamento nas circunstâncias relatadas, a empresa "
            elif i==1:
                prefix="A empresa sustentou, ainda, que "
            else:
                prefix="Consta igualmente da manifestação da empresa que "
            tx=_sentence(x["text"])
            if tx:
                tx=tx[0].lower()+tx[1:]
            lines.append(prefix+tx+" [Fonte interna: p. "+str(x["page"])+"]")
            lines.append("")
    else:
        lines += [
            "Até o momento, não foram identificadas automaticamente justificativas suficientes para síntese nesta minuta. A Comissão deverá conferir se existem pedidos, manifestações, documentos comprobatórios ou outras alegações da empresa nos autos.",
            ""
        ]

    lines += [
        "Os documentos apresentados até o momento deverão ser analisados em conjunto, especialmente quanto à existência de vínculo entre os fatos alegados e o objeto contratado, à tempestividade das comunicações, às providências adotadas para superar eventual impedimento e à demonstração efetiva de impossibilidade, dificuldade ou justificativa para o descumprimento verificado.",
        ""
    ]

    if legal:
        first=True
        for x in legal[:6]:
            if first:
                lines.append("A legislação e a regulamentação indicadas nos autos contêm os seguintes fundamentos relevantes para a apuração:")
                lines.append("")
                first=False
            lines.append(_sentence(x["text"])+" [Fonte interna: p. "+str(x["page"])+"]")
            lines.append("")
    else:
        lines += [
            "A Lei Federal nº 14.133/2021, o regulamento municipal aplicável e os instrumentos da contratação deverão ser examinados para definição do enquadramento jurídico preliminar, inclusive quanto à natureza da possível inexecução e às sanções eventualmente cabíveis.",
            ""
        ]

    lines += [
        "Dessa forma, os fatos registrados nos autos poderão caracterizar, em tese, infração administrativa prevista na legislação aplicável e nos instrumentos da contratação. O enquadramento jurídico indicado nesta minuta possui caráter preliminar e poderá ser mantido, alterado ou afastado após a análise da defesa e das provas produzidas durante a instrução, não representando decisão antecipada quanto à responsabilidade da empresa.",
        ""
    ]

    if sanctions:
        lines.append("Caso, ao final da instrução, seja reconhecida a responsabilidade administrativa da empresa, poderão ser consideradas, conforme o enquadramento jurídico e as circunstâncias do caso concreto, as seguintes espécies de sanção mencionadas nos documentos analisados: "+", ".join(sanctions)+". A Comissão deverá confirmar a efetiva aplicabilidade de cada sanção antes da expedição desta notificação.")
        lines.append("")
    else:
        lines += [
            "Caso, ao final da instrução, seja reconhecida a responsabilidade administrativa da empresa, poderá ser aplicada a sanção juridicamente cabível, observados os limites e critérios previstos na legislação, no regulamento municipal e nos instrumentos da contratação.",
            ""
        ]

    lines += [
        "Na eventual aplicação de sanção deverão ser considerados a natureza e a gravidade da infração, as peculiaridades do caso concreto, as circunstâncias agravantes ou atenuantes, os danos eventualmente causados à Administração e os princípios da razoabilidade e da proporcionalidade.",
        "",
        "Dessa forma, nos termos da Constituição Federal, da Lei Federal nº 14.133/2021, do regulamento municipal aplicável e das demais normas incidentes, fica a empresa NOTIFICADA E INTIMADA para apresentar defesa escrita e especificar as provas que pretenda produzir, no prazo de "+deadline+", contado na forma prevista na regulamentação aplicável ao procedimento.",
        "",
        "A presente notificação também poderá ser encaminhada ao endereço eletrônico informado pela empresa nos documentos da contratação, como medida complementar destinada a ampliar a ciência acerca da instauração do processo e do prazo concedido para defesa.",
        "",
        "A empresa poderá apresentar todos os documentos, esclarecimentos e provas que entender pertinentes à elucidação dos fatos, especialmente aqueles relacionados ao cumprimento da obrigação, à justificativa apresentada e às circunstâncias que possam ter impedido ou dificultado a execução contratual.",
        "",
        "As provas deverão ser especificadas na defesa, com indicação de sua pertinência para o esclarecimento dos fatos. Poderão ser indeferidas pela Comissão, mediante decisão fundamentada, as provas ilícitas, impertinentes, desnecessárias, protelatórias ou intempestivas, quando assim previsto na legislação e regulamentação aplicáveis.",
        "",
        "A defesa e os respectivos documentos deverão ser encaminhados exclusivamente ao endereço eletrônico ou canal oficial: "+channel+".",
        "",
        "No campo destinado ao assunto da mensagem deverá constar: DEFESA – PROCESSO ADMINISTRATIVO Nº "+md["processo"]+" – "+md["empresa"]+".",
        "",
        "Para assegurar o pleno conhecimento dos fatos e dos documentos que fundamentaram a instauração do procedimento, deverá ser disponibilizada à empresa cópia integral dos autos ou acesso equivalente aos documentos do Processo Administrativo de Penalização nº "+md["processo"]+".",
        "",
        "A ausência de apresentação de defesa no prazo estabelecido implicará o regular prosseguimento do processo, observadas as consequências especificamente previstas na legislação e no regulamento aplicáveis. Eventual referência a revelia, preclusão ou presunção de veracidade deverá ser conferida diretamente na norma incidente antes da expedição.",
        "",
        "A empresa poderá intervir no processo nas fases admitidas pela legislação aplicável, recebendo-o no estado em que se encontrar, sem prejuízo dos atos regularmente praticados. Concluída a instrução processual, a Comissão Permanente de Penalização elaborará relatório conclusivo e encaminhará os autos à autoridade competente para julgamento e decisão motivada.",
        "",
        "[MUNICÍPIO/UF], data certificada.",
        "",
        "",
        "[NOME DO RESPONSÁVEL]",
        "[CARGO/FUNÇÃO]",
        "",
        "MINUTA AUTOMÁTICA — REVISÃO HUMANA OBRIGATÓRIA ANTES DE EXPEDIÇÃO."
    ]

    sources=[]
    for x in facts:sources.append("Fato · p. "+str(x["page"]))
    for x in defenses:sources.append("Justificativa/manifestação da empresa · p. "+str(x["page"]))
    for x in legal:sources.append("Fundamento jurídico · p. "+str(x["page"]))
    if total_src:sources.append("Quantidade total · p. "+str(total_src["page"]))
    return {"draft":"\n".join(lines),"metadata":md,"sources":sources}

HTML = HTML.replace(
    "Notificação detalhada de instauração e abertura de prazo para defesa",
    "Notificação no padrão institucional da Comissão"
)
HTML = HTML.replace(
    "Gera uma minuta extensa, estruturada e editável, com fatos, justificativas, enquadramento preliminar, dosimetria, contraditório, provas, acesso aos autos e rastreabilidade. Campos não identificados permanecem entre colchetes.",
    "Gera uma minuta narrativa no mesmo padrão formal do modelo institucional: cabeçalho, contextualização da contratação, sequência dos fatos, justificativas, enquadramento preliminar e abertura de prazo para defesa. Campos não identificados permanecem entre colchetes."
)
HTML = HTML.replace("VERSÃO 3.9 · MINUTA DETALHADA","VERSÃO 4.0 · MODELO INSTITUCIONAL")


# --- Refinamento da minuta institucional v4.1 ---
def _best_company_and_cnpj(pages):
    joined="\n".join(p["text"] or "" for p in pages)
    company_candidates=[]
    pats=[
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 .,&\-]{4,140}?(?:LTDA|EIRELI|EPP|ME|S\.?A\.?))\s*,?\s*(?:inscrita|inscrito)\s+no\s+CNPJ",
        r"(?:CONTRATADA|Empresa)\s*[:\-]?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][^\n]{4,140}?(?:LTDA|EIRELI|EPP|ME|S\.?A\.?))"
    ]
    for pat in pats:
        for m in re.finditer(pat,joined,flags=re.I):
            name=re.sub(r"\s+"," ",m.group(1)).strip(" ,;:-")
            if len(name)>4:
                company_candidates.append((m.start(),name))
    company=company_candidates[0][1] if company_candidates else "[NÃO IDENTIFICADO AUTOMATICAMENTE]"

    cnpjs=[]
    for m in re.finditer(r"\b\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}\b",joined):
        cnpjs.append((m.start(),m.group(0)))
    if company_candidates and cnpjs:
        pos=company_candidates[0][0]
        cnpj=min(cnpjs,key=lambda x:abs(x[0]-pos))[1]
    else:
        cnpj=cnpjs[0][1] if cnpjs else "[NÃO IDENTIFICADO AUTOMATICAMENTE]"
    return company,cnpj

def _metadata_from_pages(pages):
    text="\n".join(p["text"] or "" for p in pages)
    company,cnpj=_best_company_and_cnpj(pages)
    process_no=_first_match(text,[
        r"Processo Administrativo(?: de Penaliza[cç][aã]o)?\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)",
        r"Protocolo\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)",
        r"Processo\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)"
    ])
    ata=_first_match(text,[r"Ata de Registro de Pre[cç]os\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)"])
    pregao=_first_match(text,[r"Preg[aã]o Eletr[oô]nico\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)"])
    empenho=_first_match(text,[
        r"Nota de Empenho(?: Ordin[aá]rio)?\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)",
        r"\bEmpenho\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)"
    ])
    return {"processo":process_no,"ata":ata,"pregao":pregao,"empenho":empenho,"empresa":company,"cnpj":cnpj}

def _clean_event_sentence(s):
    s=re.sub(r"\s+"," ",s or "").strip(" -;:")
    # Remove cabeçalhos/roteamento antes do conteúdo material.
    s=re.sub(r"^[A-Z0-9\-_/ ]{4,60}\s*-\s*","",s)
    s=re.sub(r"^(?:NOTIFICAÇÃO|INTIMAÇÃO|RELATÓRIO TÉCNICO|PARECER TÉCNICO|PARECER JURÍDICO)\s*(?:N[ºO.]?\s*[\w./-]+)?\s*","",s,flags=re.I)
    return s.strip()

def _event_facts(pages, limit=8):
    events=[]
    event_terms=[
        r"\bfoi emitid[ao]\b",r"\bfoi encaminhad[ao]\b",r"\bfoi expedid[ao]\b",
        r"\bfoi juntad[ao]\b",r"\bfoi protocolad[ao]\b",r"\bfoi notificad[ao]\b",
        r"\bfoi intimad[ao]\b",r"\bfoi anulad[ao]\b",r"\bpromoveu\b",r"\bsolicitou\b",
        r"\bencaminhou\b",r"\bconfirmou\b",r"\binformou\b",r"\bregistrou\b",
        r"\bn[aã]o realizou nenhuma entrega\b",r"\bn[aã]o houve entrega\b",
        r"\bsem que tenha sido comprovad[ao]\b",r"\bpedido de cancelamento\b",
        r"\bpedido de reequil[ií]brio\b",r"\bfornecedores remanescentes\b"
    ]
    exclude=[
        "clausula","paragrafo","devera","deverá","advertencia, quando","multa, quando",
        "dados pessoais","gestao e da fiscalizacao","providenciar a adocao"
    ]
    for p in pages:
        raw=re.sub(r"\s+"," ",p["text"] or "")
        chunks=re.split(r"(?<=[.!?;])\s+|(?=\bEm \d{1,2} de )|(?=\bDiante d)",raw)
        for chunk in chunks:
            z=norm(chunk)
            if len(chunk)<45 or len(chunk)>900:continue
            if any(x in z for x in exclude):continue
            score=sum(1 for pat in event_terms if re.search(pat,z))
            if re.search(r"\b\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\b|\b\d{1,2}\s+de\s+[a-zç]+\s+de\s+\d{4}\b",z):score+=1
            if score>=1:
                clean=_clean_event_sentence(chunk)
                key=norm(clean)
                if clean and all(norm(e["text"])!=key for e in events):
                    events.append({"page":p["page"],"text":clean,"score":score})
    events.sort(key=lambda x:(x["page"],-x["score"]))
    # Máximo de dois eventos por página para evitar despejo de texto.
    out=[];per={}
    for e in events:
        if per.get(e["page"],0)>=2:continue
        out.append(e);per[e["page"]]=per.get(e["page"],0)+1
        if len(out)>=limit:break
    return out

def _company_claims(pages, limit=5):
    claims=[]
    pats=[
        r"reequilibr",r"impossibil",r"inviabil",r"pedido.*rescis",r"rescisao amigavel",
        r"aumento.*custo",r"fato.*imprevis",r"consequencia incalculavel",r"fornecedor",
        r"produto.*equivalente",r"busca.*substitut"
    ]
    for p in pages:
        raw=re.sub(r"\s+"," ",p["text"] or "")
        for s in re.split(r"(?<=[.!?;])\s+",raw):
            z=norm(s)
            if len(s)<40 or len(s)>850:continue
            if any(re.search(pat,z) for pat in pats):
                clean=_clean_event_sentence(s)
                # Evita cabeçalhos sem conteúdo.
                if re.search(r"^(pedido de reequilibrio|reequilibrio economico-financeiro).{0,80}$",norm(clean)):continue
                key=norm(clean)
                if clean and all(norm(x["text"])!=key for x in claims):
                    claims.append({"page":p["page"],"text":clean})
                    if len(claims)>=limit:return claims
    return claims

def _specific_legal_refs(pages, limit=5):
    refs=[]
    for p in pages:
        raw=re.sub(r"\s+"," ",p["text"] or "")
        sentences=re.split(r"(?<=[.!?;:])\s+",raw)
        for s in sentences:
            z=norm(s)
            if "lei" not in z and "decreto" not in z:continue
            if "art" not in z:continue
            if not re.search(r"\b(?:lei|decreto)[^0-9]{0,20}\d",z):continue
            if len(s)<35 or len(s)>700:continue
            # Preferência por fundamentos sancionadores / processuais, não mero reequilíbrio contratual.
            if any(k in z for k in ["infracao","responsabil","sancao","impedimento","defesa","contraditorio","processo administrativo","art. 155","art. 156","art. 158"]):
                clean=_clean_event_sentence(s)
                key=norm(clean)
                if all(norm(x["text"])!=key for x in refs):
                    refs.append({"page":p["page"],"text":clean})
                    if len(refs)>=limit:return refs
    return refs

def _find_deadline_for_defense(pages):
    for p in pages:
        raw=re.sub(r"\s+"," ",p["text"] or "")
        z=norm(raw)
        if not any(k in z for k in ["processo administrativo sancionador","processo administrativo de penalizacao","art. 158","contraditorio","ampla defesa"]):
            continue
        pats=[
            r"(?:defesa|manifestação|manifestacao)[^.\n]{0,220}?prazo\s+de\s+([0-9]{1,2}\s*\([^)]+\)\s*dias\s+úteis)",
            r"prazo\s+de\s+([0-9]{1,2}\s*\([^)]+\)\s*dias\s+úteis)[^.\n]{0,220}?(?:defesa|manifestação|manifestacao)"
        ]
        for pat in pats:
            m=re.search(pat,raw,flags=re.I|re.S)
            if m:return re.sub(r"\s+"," ",m.group(1)).strip()
    return "[PRAZO EM DIAS ÚTEIS — CONFERIR NORMA DO PROCEDIMENTO]"

def _find_official_email(pages):
    # Só usa automaticamente e-mail que aparece em contexto de defesa/manifestação.
    for p in pages:
        raw=re.sub(r"\s+"," ",p["text"] or "")
        z=norm(raw)
        if not any(k in z for k in ["defesa","manifestacao","apresentar documentos","encaminhados exclusivamente"]):
            continue
        emails=re.findall(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}",raw,flags=re.I)
        if emails:return emails[0]
    return "[ENDEREÇO ELETRÔNICO OFICIAL PARA RECEBIMENTO DA DEFESA]"

def _draft_notification(item):
    pages=item["pages"];a=item["analysis"];md=_metadata_from_pages(pages)
    facts=_event_facts(pages,8)
    defenses=_company_claims(pages,5)
    legal=_specific_legal_refs(pages,5)
    deadline=_find_deadline_for_defense(pages)
    channel=_find_official_email(pages)

    title="NOTIFICAÇÃO EXTRAJUDICIAL Nº [NÚMERO]/COMISSÃO DE PENALIZAÇÃO/[SIGLA DO ÓRGÃO]/[MUNICÍPIO]"
    lines=[
        title,"",
        "Processo Administrativo de Penalização: nº "+md["processo"],
        "Ata de Registro de Preços: nº "+md["ata"],
        "Pregão Eletrônico: nº "+md["pregao"],
        "Nota de Empenho: nº "+md["empenho"],
        "Empresa: "+md["empresa"],
        "CNPJ: "+md["cnpj"],"",
        "Assunto: Notificação de instauração de Processo Administrativo de Penalização e abertura de prazo para apresentação de defesa.","",
        "[PREFEITURA/ÓRGÃO], pessoa jurídica de direito público interno, inscrita no CNPJ sob o nº [CNPJ DO ÓRGÃO], por intermédio da Comissão Permanente de Penalização, representada neste ato por [NOME DO RESPONSÁVEL], [CARGO/FUNÇÃO], no uso das atribuições previstas em [NORMA DE COMPETÊNCIA] e [PORTARIA DE DESIGNAÇÃO], NOTIFICA E INTIMA a empresa "+md["empresa"]+", inscrita no CNPJ sob o nº "+md["cnpj"]+", acerca da instauração do Processo Administrativo de Penalização nº "+md["processo"]+", destinado à apuração dos fatos relacionados à contratação vinculada ao Pregão Eletrônico nº "+md["pregao"]+".","",
        "A presente notificação possui caráter processual e não representa imputação definitiva de responsabilidade ou aplicação antecipada de penalidade, destinando-se a dar ciência à empresa dos fatos apurados e a assegurar o exercício do contraditório e da ampla defesa.","",
        "Conforme consta nos autos, a contratação está relacionada ao Pregão Eletrônico nº "+md["pregao"]+", à Ata de Registro de Preços nº "+md["ata"]+" e à Nota de Empenho nº "+md["empenho"]+". Os dados não identificados automaticamente deverão ser conferidos diretamente nos documentos originais antes da expedição.",""
    ]

    if facts:
        for i,x in enumerate(facts):
            lead=["Conforme consta nos autos, ","Na sequência, ","Posteriormente, ","Ainda segundo a documentação analisada, ","De acordo com os registros juntados ao processo, ","Também consta dos autos que ","Posteriormente, ","Por fim, "][min(i,7)]
            tx=_sentence(x["text"])
            if tx:tx=tx[0].lower()+tx[1:]
            lines += [lead+tx,""]
    else:
        lines += ["[INSERIR NARRATIVA CRONOLÓGICA DOS FATOS, COM DATAS, DOCUMENTOS E OCORRÊNCIAS COMPROVADAS NOS AUTOS.]",""]

    if defenses:
        lines += ["A empresa apresentou justificativas e pedidos que deverão ser considerados durante a instrução do procedimento.",""]
        for i,x in enumerate(defenses):
            lead=["Em sua manifestação, a empresa ","A empresa alegou, ainda, que ","Também sustentou que ","A empresa acrescentou que ","Por fim, requereu ou alegou que "][min(i,4)]
            tx=_sentence(x["text"])
            if tx:tx=tx[0].lower()+tx[1:]
            lines += [lead+tx,""]
    else:
        lines += ["Até o momento, não foram identificadas automaticamente justificativas ou manifestações suficientes para síntese. A Comissão deverá conferir os autos.",""]

    lines += [
        "Os documentos apresentados deverão ser analisados em conjunto, especialmente quanto à relação entre as justificativas apresentadas e o objeto contratado, à tempestividade das comunicações, às providências adotadas pela empresa e à existência de elementos que possam afastar, reduzir ou confirmar eventual responsabilidade administrativa.",""
    ]

    if legal:
        for x in legal:
            lines += [_sentence(x["text"]),""]

    lines += [
        "Dessa forma, os fatos registrados nos autos poderão caracterizar, em tese, infração administrativa prevista na legislação aplicável e nos instrumentos da contratação. O enquadramento jurídico indicado nesta minuta possui caráter preliminar e poderá ser mantido, alterado ou afastado após a análise da defesa e das provas produzidas durante a instrução, não representando decisão antecipada quanto à responsabilidade da empresa.","",
        "Caso, ao final da instrução, seja reconhecida responsabilidade administrativa, a eventual sanção deverá ser definida pela autoridade competente de acordo com o enquadramento jurídico efetivamente demonstrado nos autos, observados os limites legais, as circunstâncias do caso concreto e os princípios da razoabilidade e da proporcionalidade.","",
        "Dessa forma, fica a empresa NOTIFICADA E INTIMADA para apresentar defesa escrita e especificar as provas que pretenda produzir, no prazo de "+deadline+", contado na forma estabelecida pela legislação e regulamentação aplicáveis ao procedimento.","",
        "A empresa poderá apresentar todos os documentos, esclarecimentos e provas que entender pertinentes à elucidação dos fatos, especialmente aqueles relacionados ao cumprimento da obrigação, às justificativas apresentadas e às circunstâncias que possam ter impedido ou dificultado a execução contratual.","",
        "As provas deverão ser especificadas na defesa, com indicação de sua pertinência para o esclarecimento dos fatos. O eventual indeferimento de prova deverá ser motivado pela autoridade competente, na forma da legislação e regulamentação aplicáveis.","",
        "A defesa e os respectivos documentos deverão ser encaminhados exclusivamente ao seguinte canal oficial: "+channel+".","",
        "No campo destinado ao assunto da mensagem deverá constar: DEFESA – PROCESSO ADMINISTRATIVO Nº "+md["processo"]+" – "+md["empresa"]+".","",
        "Para assegurar o pleno conhecimento dos fatos e dos documentos que fundamentaram a instauração do procedimento, deverá ser disponibilizada à empresa cópia integral dos autos ou acesso equivalente aos documentos do Processo Administrativo de Penalização nº "+md["processo"]+".","",
        "A ausência de apresentação de defesa no prazo estabelecido implicará o regular prosseguimento do processo, observadas exclusivamente as consequências previstas na legislação e no regulamento aplicáveis.","",
        "Concluída a instrução processual, a Comissão ou unidade competente elaborará relatório conclusivo e encaminhará os autos à autoridade competente para julgamento e decisão motivada.","",
        "[MUNICÍPIO/UF], data certificada.","","[NOME DO RESPONSÁVEL]","[CARGO/FUNÇÃO]","",
        "MINUTA AUTOMÁTICA — REVISÃO HUMANA OBRIGATÓRIA ANTES DE EXPEDIÇÃO."
    ]

    sources=[]
    for x in facts:sources.append("Fato cronológico · p. "+str(x["page"]))
    for x in defenses:sources.append("Justificativa da empresa · p. "+str(x["page"]))
    for x in legal:sources.append("Fundamento jurídico · p. "+str(x["page"]))
    return {"draft":"\n".join(lines),"metadata":md,"sources":sources}

HTML = HTML.replace("VERSÃO 4.0 · MODELO INSTITUCIONAL","VERSÃO 4.1 · NARRATIVA PROCESSUAL")


# --- Minuta institucional limpa v4.2 ---
def _extract_contract_no(pages):
    joined="\n".join(p["text"] or "" for p in pages)
    return _first_match(joined,[
        r"Contrato\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)"
    ])

def _safe_defense_email(pages):
    # Nunca usa e-mail da própria contratada como canal da defesa.
    candidates=[]
    for p in pages:
        raw=re.sub(r"\s+"," ",p["text"] or "")
        z=norm(raw)
        if not any(k in z for k in [
            "defesa e os respectivos documentos","apresentar defesa","encaminhados exclusivamente",
            "comissao de penalizacao","processo administrativo sancionador"
        ]):
            continue
        for e in re.findall(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}",raw,flags=re.I):
            lo=e.lower()
            score=0
            if ".gov.br" in lo:score+=5
            if any(k in lo for k in ["comissao","penal","processo","jurid","procur","licit"]):score+=2
            candidates.append((score,e))
    candidates.sort(reverse=True)
    if candidates and candidates[0][0]>=5:
        return candidates[0][1]
    return "[ENDEREÇO ELETRÔNICO OFICIAL PARA RECEBIMENTO DA DEFESA]"

def _date_from_text(text):
    pats=[
        r"\b(\d{1,2}\/\d{1,2}\/\d{4})\b",
        r"\b(\d{1,2}\s+de\s+[A-Za-zÀ-ÿ]+\s+de\s+\d{4})\b"
    ]
    for pat in pats:
        m=re.search(pat,text or "",flags=re.I)
        if m:return m.group(1)
    return None

def _clean_process_text(text):
    s=re.sub(r"\s+"," ",text or "").strip()
    # Remove blocos típicos de 1Doc, assinatura, contatos e cabeçalhos.
    s=re.sub(r"1Doc:\s*Protocolo[^.]{0,180}","",s,flags=re.I)
    s=re.sub(r"VERIFICAÇÃO DAS ASSINATURAS.*","",s,flags=re.I)
    s=re.sub(r"Para verificar a validade das assinaturas[^.]*\.?","",s,flags=re.I)
    s=re.sub(r"Assinado por \d+ pessoa[^.]*\.?","",s,flags=re.I)
    s=re.sub(r"(?:Telefone|Whatsapp)[^ ]{0,5}\s*[:\-]?\s*[\d ()\-]+","",s,flags=re.I)
    s=re.sub(r"https?://\S+","",s,flags=re.I)
    s=re.sub(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b","",s)
    s=re.sub(r"\s+"," ",s).strip(" -;:")
    return s

def _material_case_facts(pages,a,limit=6):
    out=[]

    # 1) Fato material de não entrega/inexecução: prioridade máxima.
    for p in pages:
        raw=_clean_process_text(p["text"])
        for s in re.split(r"(?<=[.!?;])\s+",raw):
            z=norm(s)
            if any(k in z for k in [
                "nao realizou nenhuma entrega","nao houve entrega","nenhuma entrega",
                "sem que tenha sido comprovado o cumprimento","nao foram entregues",
                "ausencia de execucao parcial ou total","inexecucao total","inexecucao parcial"
            ]):
                if 45<=len(s)<=750:
                    out.append({"page":p["page"],"text":_sentence(s),"kind":"execucao"})
                    break
        if any(x["kind"]=="execucao" for x in out):break

    # 2) Pedido/requerimento da empresa como marco cronológico, mas em frase limpa.
    for p in pages[:20]:
        z=norm(p["text"])
        if "pedido de reequilibrio" in z or "reequilibrio economico-financeiro" in z:
            dt=_date_from_text(p["text"])
            contract=_extract_contract_no(pages)
            txt=("Em "+dt+", " if dt else "")+"a empresa apresentou pedido de reequilíbrio econômico-financeiro"
            if contract!="[NÃO IDENTIFICADO AUTOMATICAMENTE]":
                txt+=" relacionado ao Contrato nº "+contract
            if "pedido sucessivo de rescisao amigavel" in z or "rescisao amigavel" in z:
                txt+=", com pedido sucessivo de rescisão amigável em caso de indeferimento"
            txt+="."
            out.insert(0,{"page":p["page"],"text":txt,"kind":"pedido"})
            break

    # 3) Comunicação/notificação administrativa prévia, se houver.
    notif=[]
    for x in (a.get("pieces") or []):
        if x.get("type")=="notificacao":
            notif.extend(x.get("pages") or [])
    if notif:
        out.append({"page":min(notif),"text":"Consta dos autos notificação administrativa/extrajudicial dirigida à empresa, destinada a dar ciência dos fatos e solicitar manifestação ou regularização.","kind":"notificacao"})

    # 4) Relatório/manifestação técnica sobre execução.
    tech=[]
    for x in (a.get("pieces") or []):
        if x.get("type")=="parecer_tecnico":
            tech.extend(x.get("pages") or [])
    if tech:
        out.append({"page":min(tech),"text":"A unidade técnica/fiscalização juntou manifestação acerca da execução contratual e das providências adotadas, documento que deverá ser conferido integralmente antes da expedição.","kind":"tecnico"})

    # Remove duplicatas e ordena cronologicamente, preservando pedido inicial.
    uniq=[];seen=set()
    for x in out:
        k=norm(x["text"])
        if k in seen:continue
        seen.add(k);uniq.append(x)
    uniq.sort(key=lambda x:x["page"])
    return uniq[:limit]

def _clean_company_claims(pages,limit=4):
    claims=[]
    joined_pages=pages[:20]
    contract=_extract_contract_no(pages)

    # Pedido de reequilíbrio + rescisão, de forma sintética e sem cabeçalho bruto.
    for p in joined_pages:
        z=norm(p["text"])
        if "reequilibrio economico-financeiro" in z:
            txt="A empresa requereu reequilíbrio econômico-financeiro"
            if contract!="[NÃO IDENTIFICADO AUTOMATICAMENTE]":txt+=" do Contrato nº "+contract
            if "emissao de empenhos" in z:txt+=", cumulando pedido de emissão de empenhos"
            if "rescisao amigavel" in z:txt+=" e pedido sucessivo de rescisão amigável"
            txt+="."
            claims.append({"page":p["page"],"text":txt})
            break

    # Orçamento/custo superior ao valor contratado.
    for p in joined_pages:
        z=norm(p["text"])
        if "mocelin" in z and ("124,55" in p["text"] or "115,00" in p["text"]):
            claims.append({"page":p["page"],"text":"A empresa apresentou orçamento de fabricante para sustentar aumento do custo de aquisição, apontando valor superior ao preço unitário contratado."})
            break

    # Desequilíbrio/impossibilidade técnico-financeira.
    for p in joined_pages:
        raw=_clean_process_text(p["text"])
        for s in re.split(r"(?<=[.!?;])\s+",raw):
            z=norm(s)
            if "desequilibrio contratual" in z or ("impossibilidade tecnica" in z and "financeira" in z):
                if 40<=len(s)<=500:
                    claims.append({"page":p["page"],"text":_sentence(s)})
                    break
        if len(claims)>=3:break

    # Consequência incalculável / fato extraordinário.
    for p in joined_pages:
        raw=_clean_process_text(p["text"])
        for s in re.split(r"(?<=[.!?;])\s+",raw):
            z=norm(s)
            if "consequencia incalculavel" in z or "fato, ainda que previsivel" in z:
                if 40<=len(s)<=500:
                    claims.append({"page":p["page"],"text":_sentence(s)})
                    break
        if len(claims)>=limit:break

    uniq=[];seen=set()
    for x in claims:
        k=norm(x["text"])
        if k in seen:continue
        seen.add(k);uniq.append(x)
    return uniq[:limit]

def _sanction_legal_refs(pages,limit=4):
    refs=[]
    strong_terms=[
        "art. 155","artigo 155","art. 156","artigo 156","art. 158","artigo 158",
        "responsabilizado administrativamente","infracao administrativa","sanção de impedimento",
        "sancao de impedimento","declaracao de inidoneidade","processo administrativo sancionador"
    ]
    for p in pages:
        raw=_clean_process_text(p["text"])
        for s in re.split(r"(?<=[.!?;:])\s+",raw):
            z=norm(s)
            if not any(k in z for k in strong_terms):continue
            if len(s)<30 or len(s)>750:continue
            clean=_sentence(s)
            k=norm(clean)
            if all(norm(x["text"])!=k for x in refs):
                refs.append({"page":p["page"],"text":clean})
                if len(refs)>=limit:return refs
    return refs

def _draft_notification(item):
    pages=item["pages"];a=item["analysis"];md=_metadata_from_pages(pages)
    contract=_extract_contract_no(pages)
    facts=_material_case_facts(pages,a,6)
    defenses=_clean_company_claims(pages,4)
    legal=_sanction_legal_refs(pages,4)
    deadline=_find_deadline_for_defense(pages)
    channel=_safe_defense_email(pages)

    lines=[
        "NOTIFICAÇÃO EXTRAJUDICIAL Nº [NÚMERO]/COMISSÃO DE PENALIZAÇÃO/[SIGLA DO ÓRGÃO]/[MUNICÍPIO]","",
        "Processo Administrativo de Penalização: nº "+md["processo"],
        "Ata de Registro de Preços: nº "+md["ata"],
        "Pregão Eletrônico: nº "+md["pregao"],
        "Nota de Empenho: nº "+md["empenho"],
        "Empresa: "+md["empresa"],
        "CNPJ: "+md["cnpj"],"",
        "Assunto: Notificação de instauração de Processo Administrativo de Penalização e abertura de prazo para apresentação de defesa.","",
        "[PREFEITURA/ÓRGÃO], pessoa jurídica de direito público interno, inscrita no CNPJ sob o nº [CNPJ DO ÓRGÃO], por intermédio da Comissão Permanente de Penalização, representada neste ato por [NOME DO RESPONSÁVEL], [CARGO/FUNÇÃO], no uso das atribuições previstas em [NORMA DE COMPETÊNCIA] e [PORTARIA DE DESIGNAÇÃO], NOTIFICA E INTIMA a empresa "+md["empresa"]+", inscrita no CNPJ sob o nº "+md["cnpj"]+", acerca da instauração do Processo Administrativo de Penalização nº "+md["processo"]+", destinado à apuração de possível descumprimento de obrigação decorrente da contratação relacionada ao Pregão Eletrônico nº "+md["pregao"]+(". e ao Contrato nº "+contract if contract!="[NÃO IDENTIFICADO AUTOMATICAMENTE]" else "."),
        "",
        "A presente notificação possui caráter processual e não representa imputação definitiva de responsabilidade ou aplicação antecipada de penalidade, destinando-se a dar ciência à empresa dos fatos apurados e a assegurar o exercício do contraditório e da ampla defesa.",""
    ]

    # Contextualização contratual no mesmo estilo narrativo do modelo da Comissão.
    if contract!="[NÃO IDENTIFICADO AUTOMATICAMENTE]":
        lines += ["Conforme consta nos autos, a contratação foi formalizada por meio do Contrato nº "+contract+", vinculado ao Pregão Eletrônico nº "+md["pregao"]+". Os demais dados da contratação que não tenham sido identificados automaticamente deverão ser conferidos diretamente nos documentos originais antes da expedição desta notificação.",""]
    else:
        lines += ["Conforme consta nos autos, a contratação está vinculada ao Pregão Eletrônico nº "+md["pregao"]+". Os demais instrumentos, valores, itens, prazos e documentos da contratação deverão ser conferidos diretamente nos autos antes da expedição desta notificação.",""]

    if facts:
        for i,x in enumerate(facts):
            lead=["Conforme registrado no processo, ","Na sequência, ","Posteriormente, ","Ainda segundo os autos, ","De acordo com a documentação juntada, ","Por fim, "][min(i,5)]
            tx=_sentence(x["text"])
            if tx:tx=tx[0].lower()+tx[1:]
            lines += [lead+tx,""]
    else:
        lines += ["[INSERIR NARRATIVA CRONOLÓGICA DOS FATOS COMPROVADOS NOS AUTOS.]",""]

    if defenses:
        lines += ["A empresa apresentou justificativas que deverão ser consideradas na instrução do procedimento.",""]
        for i,x in enumerate(defenses):
            lead=["Em sua manifestação, ","A empresa alegou, ainda, que ","Também sustentou que ","Por fim, "][min(i,3)]
            tx=_sentence(x["text"])
            if tx:tx=tx[0].lower()+tx[1:]
            lines += [lead+tx,""]

    lines += [
        "Os documentos apresentados até o momento deverão ser analisados em conjunto. A justificativa da empresa constitui elemento relevante para a apuração, mas não permite, por si só, concluir pelo afastamento automático de eventual responsabilidade administrativa. Deverão ser verificadas a relação entre os fatos alegados e o objeto contratado, a tempestividade das comunicações, as providências efetivamente adotadas e a existência de prova suficiente acerca da impossibilidade ou dificuldade de cumprimento da obrigação.",""
    ]

    if legal:
        for x in legal:lines += [_sentence(x["text"]),""]

    lines += [
        "Dessa forma, os fatos registrados nos autos poderão caracterizar, em tese, infração administrativa prevista na legislação aplicável e nos instrumentos da contratação. O enquadramento jurídico indicado possui caráter preliminar e poderá ser mantido, alterado ou afastado após a análise da defesa e das provas produzidas durante a instrução, não representando decisão antecipada quanto à responsabilidade da empresa.","",
        "Caso, ao final da instrução, seja reconhecida a responsabilidade administrativa da empresa, poderá ser aplicada a sanção juridicamente cabível, conforme o enquadramento definitivo e as circunstâncias do caso concreto, observados os limites e critérios estabelecidos na legislação, no regulamento aplicável e nos instrumentos da contratação.","",
        "Na eventual aplicação de sanção deverão ser considerados a natureza e a gravidade da infração, as peculiaridades do caso concreto, as circunstâncias agravantes ou atenuantes, os danos eventualmente causados à Administração e os princípios da razoabilidade e da proporcionalidade.","",
        "Dessa forma, fica a empresa NOTIFICADA E INTIMADA para apresentar defesa escrita e especificar as provas que pretenda produzir, no prazo de "+deadline+", contado na forma prevista na legislação e regulamentação aplicáveis ao procedimento.","",
        "A empresa poderá apresentar todos os documentos, esclarecimentos e provas que entender pertinentes à elucidação dos fatos, especialmente aqueles relacionados ao cumprimento da obrigação, à justificativa apresentada e às circunstâncias que possam ter impedido ou dificultado a execução contratual.","",
        "As provas deverão ser especificadas na defesa, com indicação de sua pertinência para o esclarecimento dos fatos. Poderão ser indeferidas pela Comissão, mediante decisão fundamentada, as provas ilícitas, impertinentes, desnecessárias, protelatórias ou intempestivas, quando assim previsto na norma aplicável.","",
        "A defesa e os respectivos documentos deverão ser encaminhados exclusivamente ao endereço eletrônico ou canal oficial: "+channel+".","",
        "No campo destinado ao assunto da mensagem deverá constar: DEFESA – PROCESSO ADMINISTRATIVO Nº "+md["processo"]+" – "+md["empresa"]+".","",
        "Para assegurar o pleno conhecimento dos fatos e dos documentos que fundamentaram a instauração do procedimento, deverá ser disponibilizada à empresa cópia integral dos autos ou acesso equivalente aos documentos do Processo Administrativo de Penalização nº "+md["processo"]+".","",
        "A ausência de apresentação de defesa no prazo estabelecido implicará o regular prosseguimento do processo, observadas as consequências previstas na legislação e no regulamento aplicáveis.","",
        "Concluída a instrução processual, a Comissão Permanente de Penalização ou unidade competente elaborará relatório conclusivo e encaminhará os autos à autoridade competente para julgamento e decisão motivada.","",
        "[MUNICÍPIO/UF], data certificada.","","[NOME DO RESPONSÁVEL]","[CARGO/FUNÇÃO]","",
        "MINUTA AUTOMÁTICA — REVISÃO HUMANA OBRIGATÓRIA ANTES DE EXPEDIÇÃO."
    ]

    sources=[]
    for x in facts:sources.append("Fato material · p. "+str(x["page"]))
    for x in defenses:sources.append("Justificativa da empresa · p. "+str(x["page"]))
    for x in legal:sources.append("Fundamento sancionador · p. "+str(x["page"]))
    return {"draft":"\n".join(lines),"metadata":md,"sources":sources}

HTML = HTML.replace("VERSÃO 4.1 · NARRATIVA PROCESSUAL","VERSÃO 4.2 · MINUTA INSTITUCIONAL LIMPA")


# --- Modelo institucional fixo + preenchimento validado v5.0 ---

_previous_strong_type = strong_type
def strong_type(p):
    typ = _previous_strong_type(p)
    if typ:
        return typ
    raw = p.get("text") or ""
    first = norm(raw[:1400])
    head = norm(raw[:2600])

    # Contratos reais nem sempre trazem "CONTRATANTE/CONTRATADA" logo no cabeçalho.
    if re.search(r"\bcontrato\b.{0,80}\b(?:n|no|numero|nº)\s*[.:º-]*\s*\d", first):
        score = sum(k in head for k in ["objeto","clausula","contratante","contratada","vigencia","valor"])
        if score >= 2:
            return "contrato"

    # Formas usuais de defesa/manifestação defensiva.
    if any(k in first for k in [
        "defesa previa","defesa administrativa","razoes de defesa",
        "manifestacao em defesa","manifestacao de defesa","alegacoes de defesa"
    ]):
        return "defesa"
    if "vem apresentar" in head and "defesa" in head:
        return "defesa"

    # Alguns municípios usam "Despacho" como decisão administrativa.
    if "despacho" in first and any(k in head for k in [
        "decido","determino","autorizo","rescis","extinc","instaur",
        "acolho","indefiro","defiro"
    ]):
        return "decisao"
    return None

def _extract_origin_process(pages):
    joined="\n".join(p.get("text") or "" for p in pages)
    return _first_match(joined,[
        r"Protocolo\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)",
        r"Processo\s*(?:Administrativo)?\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)"
    ])

def _extract_penalization_process(pages):
    joined="\n".join(p.get("text") or "" for p in pages)
    # Só preenche quando o próprio documento identifica expressamente o processo sancionador.
    return _first_match(joined,[
        r"Processo Administrativo de Penaliza[cç][aã]o\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)",
        r"Processo Administrativo Sancionador\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)"
    ], default="[NÚMERO DO PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO]")

def _clean_no(value, placeholder):
    if not value or value.startswith("[NÃO IDENTIFICADO"):
        return placeholder
    return value

def _validated_metadata(pages):
    md=_metadata_from_pages(pages)
    return {
        "origem": _clean_no(_extract_origin_process(pages),"[PROCESSO/PROTOCOLO DE ORIGEM]"),
        "penalizacao": _extract_penalization_process(pages),
        "ata": _clean_no(md.get("ata"),"[ATA DE REGISTRO DE PREÇOS — CONFERIR]"),
        "pregao": _clean_no(md.get("pregao"),"[PREGÃO ELETRÔNICO — CONFERIR]"),
        "empenho": _clean_no(md.get("empenho"),"[NOTA DE EMPENHO — CONFERIR]"),
        "empresa": _clean_no(md.get("empresa"),"[RAZÃO SOCIAL DA EMPRESA]"),
        "cnpj": _clean_no(md.get("cnpj"),"[CNPJ DA EMPRESA]"),
        "contrato": _clean_no(_extract_contract_no(pages),"[CONTRATO — CONFERIR]")
    }

def _page_for_terms(pages, terms):
    for p in pages:
        z=norm(p.get("text") or "")
        if all(t in z for t in terms):
            return p["page"]
    return None

def _has_term(pages, term):
    return any(term in norm(p.get("text") or "") for p in pages)

def _extract_date_near_term(pages, term):
    for p in pages:
        raw=p.get("text") or ""
        z=norm(raw)
        pos=z.find(term)
        if pos<0:
            continue
        raw2=re.sub(r"\s+"," ",raw)
        d=_date_from_text(raw2)
        if d:
            return d
    return None

def _build_validated_facts(pages,a,md):
    facts=[]

    # Pedido de reequilíbrio/rescisão: sintetizado, jamais copia cabeçalho do PDF.
    if _has_term(pages,"reequilibrio economico-financeiro"):
        date=_extract_date_near_term(pages,"reequilibrio economico-financeiro")
        txt=("Em "+date+", " if date else "")+"a empresa apresentou pedido de reequilíbrio econômico-financeiro"
        if not md["contrato"].startswith("["):
            txt+=" relacionado ao Contrato nº "+md["contrato"]
        if _has_term(pages,"pedido de emissao de empenhos"):
            txt+=", cumulando pedido de emissão de empenhos"
        if _has_term(pages,"rescisao amigavel"):
            txt+=" e pedido sucessivo de rescisão amigável"
        txt+="."
        pg=_page_for_terms(pages,["reequilibrio","economico"])
        facts.append({"text":txt,"page":pg,"kind":"pedido_empresa"})

    # Ausência de entrega / inexecução material.
    for patterns,label in [
        (["nao realizou nenhuma entrega"],"Conforme manifestação constante dos autos, até aquele momento não havia sido realizada entrega dos itens contratados."),
        (["nao houve entrega"],"Conforme manifestação constante dos autos, não houve entrega do objeto contratado."),
        (["ausencia de execucao parcial ou total"],"A fiscalização registrou ausência de execução parcial ou total do objeto."),
        (["inexecucao total"],"Os autos contêm registro de possível inexecução total da obrigação contratual.")
    ]:
        pg=_page_for_terms(pages,patterns)
        if pg:
            facts.append({"text":label,"page":pg,"kind":"execucao"})
            break

    # Notificação/intimação anterior.
    n_pages=sorted(set(piece_pages(a,"notificacao")+piece_pages(a,"intimacao")))
    if n_pages:
        facts.append({
            "text":"Consta dos autos comunicação formal dirigida à empresa para ciência dos fatos e apresentação de manifestação ou regularização.",
            "page":n_pages[0],"kind":"notificacao"
        })

    # Manifestação técnica/fiscal.
    ptech=piece_pages(a,"parecer_tecnico")
    if ptech:
        facts.append({
            "text":"A unidade técnica ou fiscalização juntou manifestação sobre a execução contratual e as providências administrativas adotadas.",
            "page":ptech[0],"kind":"tecnico"
        })

    # Parecer jurídico.
    pjur=piece_pages(a,"parecer_juridico")
    if pjur:
        facts.append({
            "text":"Foi juntado parecer jurídico para análise das questões contratuais e das providências cabíveis.",
            "page":pjur[0],"kind":"juridico"
        })

    # Defesa formal só entra se o classificador a reconheceu como peça autônoma.
    pdef=piece_pages(a,"defesa")
    if pdef:
        facts.append({
            "text":"Foi localizada defesa administrativa apresentada pela empresa, a ser apreciada integralmente antes da conclusão do procedimento.",
            "page":pdef[0],"kind":"defesa"
        })

    # Decisão/despacho.
    pdec=piece_pages(a,"decisao")
    if pdec:
        facts.append({
            "text":"Foi localizada decisão ou despacho administrativo posterior, cujo conteúdo deverá ser considerado na definição das providências seguintes.",
            "page":pdec[0],"kind":"decisao"
        })

    # Dedup e ordenação por página quando disponível.
    uniq=[];seen=set()
    for x in facts:
        k=norm(x["text"])
        if k in seen: continue
        seen.add(k);uniq.append(x)
    uniq.sort(key=lambda x:(x["page"] if x["page"] is not None else 9999))
    return uniq

def _build_company_position(pages,md):
    out=[]
    if _has_term(pages,"reequilibrio economico-financeiro"):
        txt="A empresa sustenta a necessidade de recomposição do equilíbrio econômico-financeiro da contratação"
        if not md["contrato"].startswith("["):
            txt+=" relativa ao Contrato nº "+md["contrato"]
        txt+="."
        out.append(txt)

    if _has_term(pages,"mocelin") and (_has_term(pages,"124,55") or _has_term(pages,"115,00")):
        out.append("Como elemento de sua justificativa, a empresa apresentou orçamento de fornecedor/fabricante para demonstrar elevação do custo de aquisição em comparação com o preço contratado.")

    if _has_term(pages,"impossibilidade tecnica") or _has_term(pages,"impossibilidade financeira"):
        out.append("A empresa afirma que o cenário econômico descrito teria tornado técnica e/ou financeiramente inviável a execução nas condições originalmente pactuadas.")

    if _has_term(pages,"consequencia incalculavel"):
        out.append("A contratada sustenta que o fato invocado teria produzido consequência incalculável à época da licitação.")

    if _has_term(pages,"rescisao amigavel"):
        out.append("Subsidiariamente, a empresa formulou pedido de rescisão amigável caso não fosse acolhido o pleito principal.")

    return out[:5]

def _validated_legal_basis(pages):
    joined=norm("\n".join(p.get("text") or "" for p in pages))
    refs=[]
    # Só menciona artigo quando o número está efetivamente presente nos autos.
    for art in ["155","156","158"]:
        if re.search(r"\bart(?:igo)?\.?\s*"+art+r"\b",joined):
            refs.append("art. "+art+" da Lei Federal nº 14.133/2021")
    return refs

def _explicit_defense_deadline(pages):
    # Não reutiliza prazos de notificação/execução. Exige defesa + contexto sancionador.
    for p in pages:
        raw=re.sub(r"\s+"," ",p.get("text") or "")
        z=norm(raw)
        if "defesa" not in z:
            continue
        if not any(k in z for k in ["processo administrativo de penalizacao","processo administrativo sancionador","art. 158","sancionador"]):
            continue
        for pat in [
            r"prazo\s+de\s+([0-9]{1,2}\s*\([^)]+\)\s*dias\s+úteis)",
            r"prazo\s+de\s+([0-9]{1,2}\s+dias\s+úteis)"
        ]:
            m=re.search(pat,raw,flags=re.I)
            if m:
                return re.sub(r"\s+"," ",m.group(1)).strip()
    return "[PRAZO DE DEFESA — CONFERIR LEI/REGULAMENTO DO PROCEDIMENTO]"

def _explicit_defense_channel(pages):
    # Só preenche quando o texto vincula EXPRESSAMENTE o e-mail/canal ao envio da defesa.
    pats=[
        r"(?:defesa e os respectivos documentos|defesa|manifestação|manifestacao)[^.\n]{0,220}?(?:encaminhad[oa]s?|enviad[oa]s?|protocolad[oa]s?)[^.\n]{0,160}?([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})",
        r"(?:encaminhad[oa]s?|enviad[oa]s?|protocolad[oa]s?)[^.\n]{0,160}?([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})[^.\n]{0,180}?(?:defesa|manifestação|manifestacao)"
    ]
    for p in pages:
        raw=re.sub(r"\s+"," ",p.get("text") or "")
        for pat in pats:
            m=re.search(pat,raw,flags=re.I)
            if m:
                return m.group(1)
    return "[CANAL OFICIAL PARA APRESENTAÇÃO DA DEFESA — CONFERIR]"

def _draft_notification(item):
    pages=item["pages"]
    # Reanalisa com as regras mais recentes, evitando usar estado antigo da sessão.
    a=analyze_pages(pages)
    md=_validated_metadata(pages)
    facts=_build_validated_facts(pages,a,md)
    company_position=_build_company_position(pages,md)
    legal_refs=_validated_legal_basis(pages)
    deadline=_explicit_defense_deadline(pages)
    channel=_explicit_defense_channel(pages)

    lines=[
        "NOTIFICAÇÃO EXTRAJUDICIAL Nº [NÚMERO]/COMISSÃO DE PENALIZAÇÃO/[SIGLA DO ÓRGÃO]/[MUNICÍPIO]",
        "",
        "Processo/Protocolo de origem: nº "+md["origem"],
        "Processo Administrativo de Penalização: nº "+md["penalizacao"],
        "Ata de Registro de Preços: nº "+md["ata"],
        "Pregão Eletrônico: nº "+md["pregao"],
        "Contrato: nº "+md["contrato"],
        "Nota de Empenho: nº "+md["empenho"],
        "Empresa: "+md["empresa"],
        "CNPJ: "+md["cnpj"],
        "",
        "Assunto: Notificação de instauração de Processo Administrativo de Penalização e abertura de prazo para apresentação de defesa.",
        "",
        "[PREFEITURA/ÓRGÃO], pessoa jurídica de direito público interno, inscrita no CNPJ sob o nº [CNPJ DO ÓRGÃO], por intermédio da Comissão Permanente de Penalização, representada neste ato por [NOME DO RESPONSÁVEL], [CARGO/FUNÇÃO], no uso das atribuições previstas em [NORMA DE COMPETÊNCIA] e [PORTARIA DE DESIGNAÇÃO], NOTIFICA E INTIMA a empresa "+md["empresa"]+", inscrita no CNPJ sob o nº "+md["cnpj"]+", acerca da instauração do Processo Administrativo de Penalização nº "+md["penalizacao"]+", originado dos autos nº "+md["origem"]+", destinado à apuração de possível descumprimento de obrigação relacionada à contratação identificada nesta notificação.",
        "",
        "A presente notificação possui caráter processual e não representa imputação definitiva de responsabilidade ou aplicação antecipada de penalidade, destinando-se a dar ciência à empresa dos fatos apurados e a assegurar o exercício do contraditório e da ampla defesa.",
        "",
        "Conforme consta nos autos, a contratação está relacionada ao Pregão Eletrônico nº "+md["pregao"]+", ao Contrato nº "+md["contrato"]+", à Ata de Registro de Preços nº "+md["ata"]+" e à Nota de Empenho nº "+md["empenho"]+". As informações mantidas entre colchetes deverão ser conferidas diretamente nos documentos originais antes da expedição."
    ]

    if facts:
        lines.append("")
        for i,x in enumerate(facts):
            lead=[
                "Conforme os registros constantes dos autos, ",
                "Na sequência, ",
                "Posteriormente, ",
                "Ainda segundo a documentação analisada, ",
                "Também consta dos autos que ",
                "Por fim, "
            ][min(i,5)]
            tx=x["text"].strip()
            if tx:
                tx=tx[0].lower()+tx[1:]
            lines += [lead+tx,""]
    else:
        lines += ["","[INSERIR NARRATIVA CRONOLÓGICA DOS FATOS COMPROVADOS NOS AUTOS.]",""]

    if company_position:
        lines += ["Os autos registram, ainda, manifestação da empresa contendo justificativas e pedidos que deverão ser apreciados no curso da instrução.",""]
        for i,txt in enumerate(company_position):
            lead=[
                "Em síntese, ",
                "A empresa alegou, ainda, que ",
                "Também sustentou que ",
                "Além disso, ",
                "Subsidiariamente, "
            ][min(i,4)]
            tx=txt[0].lower()+txt[1:] if txt else txt
            lines += [lead+tx,""]

    lines += [
        "Os documentos apresentados até o momento deverão ser analisados em conjunto. As justificativas da empresa constituem elementos relevantes para a apuração, mas não permitem, por si sós, concluir pelo afastamento automático de eventual responsabilidade administrativa. Deverão ser verificados o nexo entre os fatos alegados e o objeto contratado, a tempestividade das comunicações, as providências adotadas para viabilizar o cumprimento, a suficiência da documentação comprobatória e a existência de eventual prejuízo ou comprometimento da necessidade administrativa.",
        ""
    ]

    if legal_refs:
        lines.append("Os autos contêm referências aos seguintes dispositivos da Lei Federal nº 14.133/2021, cuja pertinência deverá ser conferida no enquadramento jurídico do caso: "+", ".join(legal_refs)+".")
        lines.append("")
    else:
        lines.append("O enquadramento jurídico deverá ser definido mediante conferência da Lei Federal nº 14.133/2021, do regulamento municipal aplicável e dos instrumentos da contratação, especialmente quanto à natureza da possível inexecução e às consequências administrativas cabíveis.")
        lines.append("")

    lines += [
        "Dessa forma, os fatos registrados nos autos podem caracterizar, em tese, infração administrativa prevista na legislação aplicável e nos instrumentos da contratação. O enquadramento jurídico possui caráter preliminar e poderá ser mantido, alterado ou afastado após a análise da defesa e das provas produzidas durante a instrução, não representando decisão antecipada quanto à responsabilidade da empresa.",
        "",
        "Caso, ao final da instrução, seja reconhecida a responsabilidade administrativa da empresa, poderá ser aplicada a sanção juridicamente cabível, conforme o enquadramento definitivo e as circunstâncias do caso concreto, observados os limites e critérios estabelecidos na legislação, no regulamento aplicável e nos instrumentos da contratação.",
        "",
        "Na eventual aplicação de sanção deverão ser considerados a natureza e a gravidade da infração, as peculiaridades do caso concreto, as circunstâncias agravantes ou atenuantes, os danos eventualmente causados à Administração e os princípios da razoabilidade e da proporcionalidade.",
        "",
        "Dessa forma, fica a empresa NOTIFICADA E INTIMADA para apresentar defesa escrita e especificar as provas que pretenda produzir, no prazo de "+deadline+", contado na forma prevista na legislação e regulamentação aplicáveis ao procedimento.",
        "",
        "A empresa poderá apresentar todos os documentos, esclarecimentos e provas que entender pertinentes à elucidação dos fatos, especialmente aqueles relacionados ao cumprimento da obrigação, às justificativas apresentadas e às circunstâncias que possam ter impedido ou dificultado a execução contratual.",
        "",
        "As provas deverão ser especificadas na defesa, com indicação de sua pertinência para o esclarecimento dos fatos. Poderão ser indeferidas pela Comissão, mediante decisão fundamentada, as provas ilícitas, impertinentes, desnecessárias, protelatórias ou intempestivas, quando assim previsto na norma aplicável.",
        "",
        "A defesa e os respectivos documentos deverão ser encaminhados exclusivamente ao seguinte endereço eletrônico ou canal oficial: "+channel+".",
        "",
        "No campo destinado ao assunto deverá constar: DEFESA – PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº "+md["penalizacao"]+" – "+md["empresa"]+".",
        "",
        "Para assegurar o pleno conhecimento dos fatos e dos documentos que fundamentaram a instauração do procedimento, deverá ser disponibilizada à empresa cópia integral dos autos ou acesso equivalente aos documentos que instruem o Processo Administrativo de Penalização nº "+md["penalizacao"]+".",
        "",
        "A ausência de apresentação de defesa no prazo estabelecido implicará o regular prosseguimento do processo, observadas as consequências previstas na legislação e no regulamento aplicáveis.",
        "",
        "A empresa poderá intervir no processo nas fases admitidas pela legislação aplicável, recebendo-o no estado em que se encontrar, sem prejuízo dos atos regularmente praticados. Concluída a instrução processual, a Comissão Permanente de Penalização elaborará relatório conclusivo e encaminhará os autos à autoridade competente para julgamento e decisão motivada.",
        "",
        "[MUNICÍPIO/UF], data certificada.",
        "",
        "",
        "[NOME DO RESPONSÁVEL]",
        "[CARGO/FUNÇÃO]",
        "",
        "MINUTA AUTOMÁTICA — REVISÃO HUMANA OBRIGATÓRIA ANTES DE EXPEDIÇÃO."
    ]

    sources=[]
    for x in facts:
        if x.get("page"): sources.append("Fato validado · p. "+str(x["page"]))
    pdef=piece_pages(a,"defesa")
    if pdef: sources.append("Defesa administrativa · p. "+fmt_pages(pdef))
    pdec=piece_pages(a,"decisao")
    if pdec: sources.append("Decisão/despacho · p. "+fmt_pages(pdec))
    if legal_refs: sources.append("Fundamentos legais identificados nos autos")
    return {"draft":"\n".join(lines),"metadata":md,"sources":sources}

HTML = HTML.replace(
    "Notificação no padrão institucional da Comissão",
    "Notificação institucional com preenchimento validado"
)
HTML = HTML.replace(
    "Gera uma minuta narrativa no mesmo padrão formal do modelo institucional: cabeçalho, contextualização da contratação, sequência dos fatos, justificativas, enquadramento preliminar e abertura de prazo para defesa. Campos não identificados permanecem entre colchetes.",
    "Usa um modelo institucional fixo e preenche apenas dados validados nos autos. Informações sem evidência suficiente permanecem entre colchetes para conferência humana."
)
HTML = HTML.replace("VERSÃO 4.2 · MINUTA INSTITUCIONAL LIMPA","VERSÃO 5.0 · MODELO FIXO VALIDADO")


# --- Processo modelo completo v5.1 ---
# Caso fictício "golden set" para demonstrar e testar o ciclo inteiro:
# contratação -> cobrança -> justificativa -> apuração -> notificação -> defesa -> análise -> decisão.

@app.get("/api/demo-pdf")
def demo_pdf():
    pages = [
        (
            "PROTOCOLO DE ORIGEM Nº 1-9000/2026",
            "DOCUMENTO FICTÍCIO PARA DEMONSTRAÇÃO. Município Demonstração/RO. Interessado: Secretaria Municipal de Saúde. "
            "Assunto: aquisição de kits de higiene bucal e apuração de possível inexecução contratual. "
            "Este processo modelo foi criado exclusivamente para testes do Fiscaliza.AI Municipal."
        ),
        (
            "NOTA DE EMPENHO Nº 1450/2026",
            "Emitida em 10 de abril de 2026. Pedido nº 02148/2026. Ata de Registro de Preços nº 083/2026. "
            "Pregão Eletrônico nº 071/2026. Contratada: EMPRESA MODELO DEMONSTRAÇÃO LTDA, CNPJ 00.000.000/0000-00. "
            "Objeto: fornecimento de 500 kits de higiene bucal, marca DEMO, ao valor unitário de R$ 4,30, total de R$ 2.150,00. "
            "Prazo de entrega: 30 dias após o recebimento da Nota de Empenho."
        ),
        (
            "CONTRATO ADMINISTRATIVO Nº 140/2026",
            "CONTRATANTE: Município Demonstração/RO. CONTRATADA: EMPRESA MODELO DEMONSTRAÇÃO LTDA, CNPJ 00.000.000/0000-00. "
            "Objeto: fornecimento de 500 kits de higiene bucal, vinculado ao Pregão Eletrônico nº 071/2026 e à Ata de Registro de Preços nº 083/2026. "
            "CLÁUSULA QUARTA - PRAZO: entrega integral em até 30 dias após a ciência da Nota de Empenho. "
            "CLÁUSULA DÉCIMA SEGUNDA - SANÇÕES: aplicam-se as regras da Lei Federal nº 14.133/2021 e do Decreto Municipal Demonstrativo nº 405/2023."
        ),
        (
            "ORDEM DE FORNECIMENTO Nº 02148/2026",
            "Em 11 de abril de 2026, fica autorizada a entrega de 500 kits de higiene bucal referentes ao Contrato nº 140/2026, "
            "Nota de Empenho nº 1450/2026, Ata de Registro de Preços nº 083/2026 e Pregão Eletrônico nº 071/2026. "
            "Local de entrega: Almoxarifado Central. Prazo: 30 dias."
        ),
        (
            "COMPROVANTE DE ENVIO E CIÊNCIA",
            "Em 11 de abril de 2026, a Nota de Empenho nº 1450/2026 e a Ordem de Fornecimento nº 02148/2026 foram encaminhadas "
            "ao endereço eletrônico cadastrado pela empresa. A contratada confirmou ciência em 12 de abril de 2026. "
            "Considerando o prazo de 30 dias, o término previsto para entrega ocorreu em 12 de maio de 2026."
        ),
        (
            "NOTIFICAÇÃO EXTRAJUDICIAL Nº 01/ALMOXARIFADO/2026",
            "Em 18 de maio de 2026, diante da ausência de entrega dos 500 kits, fica a EMPRESA MODELO DEMONSTRAÇÃO LTDA NOTIFICADA "
            "para regularizar a obrigação ou apresentar justificativa no prazo de 5 dias úteis. "
            "Esta cobrança administrativa antecede o processo sancionador e não corresponde ao prazo de defesa do processo de penalização."
        ),
        (
            "MANIFESTAÇÃO DA EMPRESA - PEDIDO DE CANCELAMENTO",
            "Em 20 de maio de 2026, a EMPRESA MODELO DEMONSTRAÇÃO LTDA informou que seu fabricante interrompeu temporariamente "
            "a produção do creme dental utilizado nos kits. A empresa alegou impossibilidade de cumprir a obrigação nas condições originais, "
            "afirmou ter buscado produto substituto equivalente e requereu cancelamento da Nota de Empenho nº 1450/2026 sem aplicação de penalidade. "
            "Juntou declaração do fabricante e três cotações de fornecedores alternativos."
        ),
        (
            "RELATÓRIO TÉCNICO Nº 009/2026",
            "A fiscalização registra que, até 28 de maio de 2026, não houve entrega total nem parcial dos 500 kits contratados. "
            "A justificativa da empresa foi recebida, porém as cotações juntadas não demonstram, por si sós, impossibilidade absoluta de cumprimento. "
            "A necessidade dos kits permanece ativa para atendimento da rede municipal. Recomenda-se remessa à Comissão de Penalização para apuração."
        ),
        (
            "OFÍCIO Nº 65/SAÚDE/2026",
            "Em 30 de maio de 2026, a Secretaria Municipal de Saúde confirma a não entrega dos materiais e informa que a justificativa apresentada "
            "é relevante para a apuração, mas não permite concluir automaticamente pelo afastamento da responsabilidade. "
            "A unidade solicita análise sobre eventual inexecução total e encaminha os autos à Comissão Permanente de Penalização."
        ),
        (
            "PARECER JURÍDICO PRELIMINAR Nº 012/2026",
            "A Lei Federal nº 14.133/2021, em seu art. 155, prevê responsabilização administrativa por infrações praticadas pelo licitante ou contratado. "
            "O art. 156 disciplina as sanções administrativas e seus critérios. O art. 158 assegura processo de responsabilização com contraditório e ampla defesa "
            "nas hipóteses legalmente previstas. O Decreto Municipal Demonstrativo nº 405/2023 regulamenta o procedimento local. "
            "Recomenda-se instauração de processo administrativo de penalização, sem antecipação de juízo definitivo."
        ),
        (
            "DECISÃO ADMINISTRATIVA - INSTAURAÇÃO",
            "Processo Administrativo de Penalização nº 2-0001/2026. "
            "Considerando o Protocolo de origem nº 1-9000/2026, o Relatório Técnico nº 009/2026 e o Parecer Jurídico Preliminar nº 012/2026, "
            "DETERMINO a instauração do Processo Administrativo de Penalização nº 2-0001/2026 para apurar possível inexecução total relacionada "
            "ao Contrato nº 140/2026, à Nota de Empenho nº 1450/2026, à Ata de Registro de Preços nº 083/2026 e ao Pregão Eletrônico nº 071/2026. "
            "A Comissão deverá assegurar contraditório, ampla defesa e produção de provas."
        ),
        (
            "ATO DE INSTAURAÇÃO E REGRAS DE DEFESA",
            "Processo Administrativo de Penalização nº 2-0001/2026. "
            "Nos termos do art. 158 da Lei Federal nº 14.133/2021 e do art. 18 do Decreto Municipal Demonstrativo nº 405/2023, "
            "a empresa será NOTIFICADA E INTIMADA para apresentar defesa escrita e especificar as provas que pretenda produzir no prazo de "
            "15 (quinze) dias úteis, contado do primeiro dia útil seguinte à publicação da notificação. "
            "A defesa e os respectivos documentos deverão ser encaminhados exclusivamente para comissaopenalizacao@municipiodemonstracao.gov.br."
        ),
        (
            "NOTIFICAÇÃO EXTRAJUDICIAL Nº 16/COMISSÃO DE PENALIZAÇÃO/2026",
            "Processo Administrativo de Penalização nº 2-0001/2026. Ata de Registro de Preços nº 083/2026. Pregão Eletrônico nº 071/2026. "
            "Nota de Empenho nº 1450/2026. Empresa: EMPRESA MODELO DEMONSTRAÇÃO LTDA. CNPJ: 00.000.000/0000-00. "
            "NOTIFICA E INTIMA a empresa acerca da instauração do processo destinado à apuração de possível inexecução total. "
            "A presente notificação não representa imputação definitiva ou aplicação antecipada de penalidade. "
            "A defesa escrita e as provas deverão ser apresentadas em 15 (quinze) dias úteis e encaminhadas exclusivamente para "
            "comissaopenalizacao@municipiodemonstracao.gov.br."
        ),
        (
            "DEFESA ADMINISTRATIVA",
            "A EMPRESA MODELO DEMONSTRAÇÃO LTDA apresenta DEFESA ADMINISTRATIVA no Processo Administrativo de Penalização nº 2-0001/2026. "
            "Alega fato superveniente relacionado à interrupção temporária da produção pelo fabricante, sustenta ter buscado produtos equivalentes, "
            "afirma ausência de má-fé e requer o afastamento da penalidade. Subsidiariamente, requer que eventual sanção observe proporcionalidade "
            "e considere sua cooperação, a comunicação à Administração e a ausência de antecedentes."
        ),
        (
            "DA DEFESA - DOCUMENTOS E PEDIDOS",
            "A contratada junta declaração do fabricante, três cotações alternativas e registros de e-mail enviados à Administração. "
            "Requer produção de prova documental complementar e, se necessário, diligência junto ao fabricante. "
            "Pede o reconhecimento de justificativa suficiente para afastar a responsabilização ou, subsidiariamente, a aplicação da medida menos gravosa cabível."
        ),
        (
            "RELATÓRIO TÉCNICO APÓS DEFESA Nº 014/2026",
            "A fiscalização confirma que não houve entrega dos 500 kits. Os documentos juntados demonstram dificuldade de fornecimento pelo fabricante original, "
            "mas não comprovam impossibilidade absoluta de aquisição de produto equivalente durante todo o período contratual. "
            "Registra-se, contudo, que a empresa comunicou a dificuldade antes da instauração do processo sancionador e apresentou documentos de suporte."
        ),
        (
            "PARECER JURÍDICO FINAL Nº 019/2026",
            "A defesa foi apresentada tempestivamente. Devem ser considerados o art. 155 e os critérios do art. 156 da Lei Federal nº 14.133/2021, "
            "bem como as circunstâncias atenuantes e os elementos probatórios juntados. O processo observou o art. 158 da Lei nº 14.133/2021 quanto ao contraditório "
            "e à ampla defesa. Recomenda-se decisão motivada, com enfrentamento dos argumentos relevantes e dosimetria individualizada."
        ),
        (
            "DECISÃO ADMINISTRATIVA FINAL",
            "Processo Administrativo de Penalização nº 2-0001/2026. Após análise da defesa, dos documentos e dos pareceres, "
            "DECIDO reconhecer a ocorrência de inexecução total da obrigação, mas considero as circunstâncias atenuantes demonstradas. "
            "APLICO, para fins exclusivamente deste caso fictício de demonstração, a sanção de advertência. "
            "A decisão é motivada, encerra a fase de julgamento administrativo em primeira instância e informa que eventual recurso observará a legislação aplicável."
        )
    ]

    buf=io.BytesIO()
    cnv=canvas.Canvas(buf,pagesize=A4)
    for idx,(title,body) in enumerate(pages,start=1):
        cnv.setFont("Helvetica-Bold",14)
        cnv.drawString(52,790,title)
        cnv.setFont("Helvetica",10)
        _demo_wrap(cnv,body)
        cnv.setFont("Helvetica-Bold",8)
        cnv.drawString(52,35,"FISCALIZA.AI - PROCESSO MODELO FICTÍCIO")
        cnv.setFont("Helvetica",8)
        cnv.drawRightString(545,35,"Página %d de %d" % (idx,len(pages)))
        cnv.showPage()
    cnv.save();buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition":"inline; filename=Processo-Modelo-Completo-FiscalizaAI.pdf"}
    )

# Análise distingue instauração de sanção final quando ambas existem.
_previous_analyze_pages = analyze_pages
def analyze_pages(pages):
    a=_previous_analyze_pages(pages)
    final_sanction=snippets(
        pages,
        [r"\baplico\b.{0,160}\bsanc",r"\bdecido\b.{0,220}\baplicar\b",r"\bsancao de advertencia\b",
         r"\bsancao de multa\b",r"\bimpedimento de licitar\b",r"\bdeclaracao de inidoneidade\b"],
        4
    )
    a["final_sanction"]=final_sanction
    if final_sanction and a["has"].get("decisao"):
        a["conclusion"]="Foram localizadas peças de contraditório, instrução e decisão final. A ferramenta organiza as evidências e indica as fontes; a revisão humana permanece obrigatória."
        # A instauração anterior deixa de aparecer como única cautela quando há julgamento final.
        a["pending"]=[p for p in a.get("pending",[]) if "não presuma sanção final" not in p.lower()]
    return a

# Atualiza a apresentação do caso demonstrativo.
HTML = HTML.replace(
    "Carregue um processo inteiramente fictício de entrega parcial. O sistema executa a mesma análise usada para qualquer PDF enviado.",
    "Carregue um processo modelo inteiramente fictício, com contratação, cobrança, justificativa, instauração, notificação, defesa, pareceres e decisão final. O sistema executa a mesma análise usada para qualquer PDF enviado."
)
HTML = HTML.replace(
    "<span>11 páginas</span><span>dados fictícios</span><span>sem cadastro</span>",
    "<span>18 páginas</span><span>ciclo completo</span><span>dados fictícios</span>"
)
HTML = HTML.replace(
    ">Testar demonstração →</button>",
    ">Testar processo modelo →</button>"
)
HTML = HTML.replace(
    'st.textContent="Demonstração fictícia carregada · "+d.pages+" páginas · análise real executada"',
    'st.textContent="Processo modelo carregado · "+d.pages+" páginas · análise real executada"'
)
HTML = HTML.replace("VERSÃO 5.0 · MODELO FIXO VALIDADO","VERSÃO 5.1 · PROCESSO MODELO COMPLETO")


# --- Camada competitiva completa v6.0 ---
import threading

# Expiração automática real do estado em memória (30 minutos).
class _ExpiringAnalyses(dict):
    ttl_seconds = 1800
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        timer = threading.Timer(self.ttl_seconds, lambda: self.pop(key, None))
        timer.daemon = True
        timer.start()

ANALYSES = _ExpiringAnalyses(ANALYSES)

def _pages_for_type(a, typ):
    return sorted({p for x in a.get("pieces",[]) if x.get("type")==typ for p in x.get("pages",[])})

def _source_obj(label, file, page, text=""):
    return {"label":label,"file":file or "Processo","page":page,"text":clip(text,260) if text else ""}

def _detect_contradictions(pages, a):
    out=[]
    delivery_yes=snippets(
        pages,
        [r"foram entregues\s+\d+",r"foi entregue",r"entrega parcial",r"recebimento parcial",r"recebido.*objeto"],
        4
    )
    delivery_no=snippets(
        pages,
        [r"nao houve entrega",r"nenhuma entrega",r"nao realizou nenhuma entrega",r"nao foram entregues",r"ausencia de execucao"],
        4
    )
    if delivery_yes and delivery_no:
        out.append({
            "title":"Registros divergentes sobre entrega",
            "detail":"Há documentos que indicam entrega/recebimento e outros que registram ausência ou inexecução. A divergência deve ser conferida no contexto e na cronologia.",
            "severity":"alta",
            "sources":[
                _source_obj("Indício de entrega",delivery_yes[0].get("file"),delivery_yes[0].get("page"),delivery_yes[0].get("text")),
                _source_obj("Indício de não entrega",delivery_no[0].get("file"),delivery_no[0].get("page"),delivery_no[0].get("text"))
            ]
        })

    # Quantidades explícitas potencialmente conflitantes.
    qhits=[]
    qpats=[
        r"(?:quantidade total|quantidade contratada|fornecimento de|aquisi[cç][aã]o de)\s*[:\-]?\s*(\d{1,7})",
        r"\b(\d{1,7})\s+(?:kits|unidades|itens)\s+contratad"
    ]
    for p in pages:
        z=norm(p.get("text") or "")
        for pat in qpats:
            for m in re.finditer(pat,z):
                try:v=int(m.group(1))
                except:continue
                if 1<=v<=10000000:
                    qhits.append((v,p["page"],p["file"]))
    distinct=sorted(set(v for v,_,__ in qhits))
    if len(distinct)>1:
        src=[]
        used=set()
        for v,pg,fn in qhits:
            if v in used:continue
            used.add(v);src.append(_source_obj("Quantidade "+str(v),fn,pg))
            if len(src)>=3:break
        out.append({
            "title":"Quantidades diferentes localizadas",
            "detail":"O processo contém mais de uma quantidade apresentada como total/contratada. Isso pode refletir itens distintos ou uma inconsistência documental.",
            "severity":"media","sources":src
        })

    # CNPJs diferentes próximos ao nome da contratada: alerta de cadastro.
    cnpjs={}
    for p in pages:
        for m in re.finditer(r"\b\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}\b",p.get("text") or ""):
            val=m.group(0);cnpjs.setdefault(val,[]).append((p["file"],p["page"]))
    if len(cnpjs)>1:
        src=[]
        for val,locs in list(cnpjs.items())[:3]:
            src.append(_source_obj("CNPJ "+val,locs[0][0],locs[0][1]))
        out.append({
            "title":"Mais de um CNPJ localizado",
            "detail":"Foram encontrados CNPJs diferentes nos autos. Confirme qual pertence à contratada antes de gerar ou expedir documentos.",
            "severity":"alta","sources":src
        })
    return out

def _process_checklist(pages,a):
    has=a.get("has",{})
    q=a.get("quantity",{}).get("value","")
    qok=bool(q and "não identificado" not in norm(q))
    science=bool(snippets(pages,[r"comprovante de ciencia",r"confirmou ciencia",r"recebimento da notificacao",r"notificacao.*recebid"],3))
    legal=bool(_validated_legal_basis(pages))
    final=bool(a.get("final_sanction"))
    rows=[
        ("Contrato ou instrumento equivalente",bool(has.get("contrato") or has.get("empenho") or has.get("ordem_fornecimento")),_pages_for_type(a,"contrato")+_pages_for_type(a,"empenho")+_pages_for_type(a,"ordem_fornecimento")),
        ("Notificação/intimação",bool(has.get("notificacao") or has.get("intimacao")),_pages_for_type(a,"notificacao")+_pages_for_type(a,"intimacao")),
        ("Comprovação de ciência",science,[]),
        ("Defesa administrativa",bool(has.get("defesa")),_pages_for_type(a,"defesa")),
        ("Manifestação técnica/fiscal",bool(has.get("parecer_tecnico")),_pages_for_type(a,"parecer_tecnico")),
        ("Parecer/fundamentação jurídica",bool(has.get("parecer_juridico") or legal),_pages_for_type(a,"parecer_juridico")),
        ("Decisão/despacho",bool(has.get("decisao")),_pages_for_type(a,"decisao")),
        ("Quantidade/objeto identificável",qok,[a.get("quantity",{}).get("source",{}).get("page")] if a.get("quantity",{}).get("source") else []),
        ("Sanção final expressa",final,[x.get("page") for x in a.get("final_sanction",[]) if x.get("page")])
    ]
    return [{"label":lab,"ok":ok,"pages":sorted(set(p for p in pgs if p))} for lab,ok,pgs in rows]

def _next_action(pages,a):
    has=a.get("has",{})
    final=bool(a.get("final_sanction"))
    if final:
        return {
            "stage":"Julgamento identificado",
            "action":"Revisar a decisão, comprovar a ciência da interessada e verificar eventual fase recursal ou providência de registro.",
            "why":"Há indicação de decisão final com sanção expressa nos autos."
        }
    if not (has.get("notificacao") or has.get("intimacao")):
        return {
            "stage":"Instrução inicial",
            "action":"Conferir a instauração e providenciar notificação/intimação com descrição dos fatos, fundamento preliminar, prazo e acesso aos autos.",
            "why":"Não foi localizada notificação ou intimação como peça autônoma."
        }
    if not has.get("defesa"):
        return {
            "stage":"Contraditório",
            "action":"Aguardar/registrar a defesa dentro do prazo aplicável ou certificar o decurso do prazo antes de prosseguir.",
            "why":"Há comunicação processual, mas a defesa ainda não foi localizada como peça autônoma."
        }
    if has.get("defesa") and not (has.get("parecer_tecnico") or has.get("parecer_juridico")):
        return {
            "stage":"Análise da defesa",
            "action":"Confrontar os argumentos da defesa com a fiscalização e realizar as diligências/provas necessárias antes do relatório conclusivo.",
            "why":"A defesa foi localizada, mas a instrução posterior ainda parece incompleta."
        }
    if has.get("defesa") and not has.get("decisao"):
        return {
            "stage":"Conclusão da instrução",
            "action":"Elaborar relatório conclusivo e encaminhar os autos à autoridade competente para decisão motivada.",
            "why":"Há contraditório e elementos de instrução, mas não foi localizada decisão."
        }
    return {
        "stage":"Revisão final",
        "action":"Conferir se a decisão enfrenta os argumentos relevantes, está vinculada às provas e registra as providências posteriores.",
        "why":"O processo contém peças de contraditório e decisão."
    }

def _review_flags(pages,a,contradictions,checklist):
    flags=[]
    for c in contradictions[:2]:
        flags.append({"level":"alta" if c.get("severity")=="alta" else "media","text":c["title"]})
    for row in checklist:
        if not row["ok"] and row["label"] in [
            "Notificação/intimação","Comprovação de ciência","Defesa administrativa",
            "Parecer/fundamentação jurídica","Decisão/despacho"
        ]:
            flags.append({"level":"alta" if row["label"] in ["Notificação/intimação","Defesa administrativa"] else "media","text":"Não identificado com segurança: "+row["label"]+"."})
    deadline=_explicit_defense_deadline(pages)
    if deadline.startswith("["):
        flags.append({"level":"media","text":"Prazo de defesa não foi validado automaticamente; conferir a norma e o ato de intimação."})
    channel=_explicit_defense_channel(pages)
    if channel.startswith("["):
        flags.append({"level":"media","text":"Canal oficial de recebimento da defesa não foi validado automaticamente."})
    # máximo de cinco, priorizando alta.
    flags.sort(key=lambda x:0 if x["level"]=="alta" else 1)
    return flags[:5]

def _traceability(a):
    rows=[]
    for x in a.get("pieces",[]):
        rows.append({
            "claim":x.get("label"),
            "status":"Peça identificada",
            "source":x.get("file"),
            "pages":x.get("pages",[])
        })
    q=a.get("quantity",{})
    if q.get("source"):
        rows.append({
            "claim":"Quantidade total: "+str(q.get("value")),
            "status":"Dado extraído",
            "source":q["source"].get("file"),
            "pages":[q["source"].get("page")]
        })
    for x in a.get("final_sanction",[])[:2]:
        rows.append({
            "claim":"Possível decisão sancionatória final",
            "status":"Trecho localizado",
            "source":x.get("file"),
            "pages":[x.get("page")]
        })
    return rows

_previous_analyze_pages_v60 = analyze_pages
def analyze_pages(pages):
    a=_previous_analyze_pages_v60(pages)
    contradictions=_detect_contradictions(pages,a)
    checklist=_process_checklist(pages,a)
    a["contradictions"]=contradictions
    a["process_checklist"]=checklist
    a["next_action"]=_next_action(pages,a)
    a["review_flags"]=_review_flags(pages,a,contradictions,checklist)
    a["traceability"]=_traceability(a)
    a["metrics"]={
        "pages":len(pages),
        "pieces":len(a.get("pieces",[])),
        "mentions":len(a.get("mentions",[])),
        "evidence_points":len(a.get("defense",[]))+len(a.get("contra",[]))+len(a.get("traceability",[])),
        "checklist_ok":sum(1 for x in checklist if x["ok"]),
        "checklist_total":len(checklist)
    }
    return a

class DocumentDraftReq(BaseModel):
    analysis_id: str
    kind: str

def _draft_header(md,title):
    return [
        title,"",
        "Processo/Protocolo de origem: nº "+md["origem"],
        "Processo Administrativo de Penalização: nº "+md["penalizacao"],
        "Empresa: "+md["empresa"],
        "CNPJ: "+md["cnpj"],""
    ]

def _generic_document_draft(item,kind):
    pages=item["pages"];a=analyze_pages(pages);md=_validated_metadata(pages)
    kind=(kind or "").lower()
    if kind=="notificacao":
        return _draft_notification({"pages":pages,"analysis":a})

    facts=_build_validated_facts(pages,a,md)
    facts_text=" ".join(x["text"] for x in facts[:5]) if facts else "[SÍNTESE DOS FATOS — CONFERIR AUTOS]"
    defense_pages=piece_pages(a,"defesa")
    defense_note=("Defesa localizada nas páginas "+fmt_pages(defense_pages)+"." if defense_pages else "Defesa administrativa não identificada com segurança.")
    legal=", ".join(_validated_legal_basis(pages)) or "[FUNDAMENTAÇÃO JURÍDICA — CONFERIR]"

    if kind=="despacho":
        lines=_draft_header(md,"MINUTA — DESPACHO DE INSTAURAÇÃO")
        lines += [
            "Considerando os documentos constantes dos autos e a necessidade de apuração regular dos fatos, especialmente: "+facts_text,
            "",
            "DETERMINO a instauração do Processo Administrativo de Penalização nº "+md["penalizacao"]+", assegurados o contraditório, a ampla defesa e a produção de provas.",
            "",
            "Encaminhem-se os autos à Comissão/unidade competente para adoção das providências de notificação e instrução.",
            "",
            "[LOCAL], [DATA].","","[AUTORIDADE COMPETENTE]","",
            "MINUTA ASSISTIDA — REVISÃO HUMANA OBRIGATÓRIA."
        ]
    elif kind=="intimacao":
        lines=_draft_header(md,"MINUTA — INTIMAÇÃO PARA MANIFESTAÇÃO/DEFESA")
        lines += [
            "Fica a empresa INTIMADA para apresentar manifestação/defesa e especificar as provas que pretenda produzir no prazo de "+_explicit_defense_deadline(pages)+".",
            "",
            "A manifestação deverá ser encaminhada ao seguinte canal oficial: "+_explicit_defense_channel(pages)+".",
            "",
            "A empresa deverá ter acesso aos documentos que fundamentam o ato, preservado o contraditório e a ampla defesa.",
            "",
            "[LOCAL], [DATA].","","[RESPONSÁVEL]","",
            "MINUTA ASSISTIDA — REVISÃO HUMANA OBRIGATÓRIA."
        ]
    elif kind=="diligencia":
        lines=_draft_header(md,"MINUTA — DESPACHO DE DILIGÊNCIA")
        lines += [
            "Considerando a necessidade de esclarecimento dos fatos e de formação adequada da convicção administrativa, DETERMINO a realização das seguintes diligências:",
            "",
            "1. [INDICAR DOCUMENTO/INFORMAÇÃO FALTANTE];",
            "2. [INDICAR UNIDADE OU RESPONSÁVEL PELA RESPOSTA];",
            "3. [INDICAR PRAZO E FORMA DE CUMPRIMENTO].",
            "",
            "Pontos já identificados pelo sistema que merecem conferência: "+("; ".join(x["text"] for x in a.get("review_flags",[])[:3]) or "nenhum alerta automático relevante."),
            "",
            "[LOCAL], [DATA].","","[RESPONSÁVEL]","",
            "MINUTA ASSISTIDA — REVISÃO HUMANA OBRIGATÓRIA."
        ]
    elif kind=="relatorio":
        lines=_draft_header(md,"MINUTA — RELATÓRIO CONCLUSIVO")
        lines += [
            "I — SÍNTESE DOS AUTOS",
            facts_text,"",
            "II — CONTRADITÓRIO E DEFESA",
            defense_note,"",
            "III — FUNDAMENTAÇÃO A CONFERIR",
            legal,"",
            "IV — ANÁLISE",
            "Os fatos, a defesa e as provas deverão ser confrontados de forma individualizada. A presente minuta não presume responsabilidade e exige revisão integral dos autos.","",
            "V — CONCLUSÃO",
            "[INDICAR, APÓS REVISÃO HUMANA, SE HÁ OU NÃO RESPONSABILIDADE E O ENQUADRAMENTO JURÍDICO CORRESPONDENTE].","",
            "[LOCAL], [DATA].","","[COMISSÃO/RESPONSÁVEL]","",
            "MINUTA ASSISTIDA — REVISÃO HUMANA OBRIGATÓRIA."
        ]
    elif kind=="decisao":
        lines=_draft_header(md,"MINUTA — DECISÃO ADMINISTRATIVA")
        lines += [
            "Vistos e examinados os autos.",
            "",
            "Considero a síntese fática e os documentos constantes do processo: "+facts_text,
            "",
            "Registro quanto ao contraditório: "+defense_note,
            "",
            "Fundamentação a ser conferida: "+legal+".",
            "",
            "DECIDO:",
            "[A AUTORIDADE COMPETENTE DEVERÁ PREENCHER A CONCLUSÃO, O ENQUADRAMENTO E, SE CABÍVEL, A SANÇÃO E SUA DOSIMETRIA, APÓS REVISÃO INTEGRAL DOS AUTOS].",
            "",
            "A decisão deverá enfrentar os argumentos relevantes da defesa, indicar as provas consideradas e motivar eventual sanção de forma individualizada.",
            "",
            "[LOCAL], [DATA].","","[AUTORIDADE COMPETENTE]","",
            "MINUTA ASSISTIDA — DECISÃO HUMANA OBRIGATÓRIA."
        ]
    else:
        raise HTTPException(400,"Tipo de minuta não suportado.")

    return {"draft":"\n".join(lines),"sources":["Processo analisado · "+str(len(pages))+" página(s)"]}

@app.post("/api/document-draft")
def document_draft(req:DocumentDraftReq):
    item=ANALYSES.get(req.analysis_id)
    if not item:raise HTTPException(409,"A análise desta sessão expirou ou foi excluída.")
    return _generic_document_draft(item,req.kind)

@app.delete("/api/analysis/{analysis_id}")
def delete_analysis(analysis_id):
    existed=analysis_id in ANALYSES
    ANALYSES.pop(analysis_id,None)
    return {"ok":True,"deleted":existed}

# Corrige rota de demonstração duplicada: mantém apenas a implementação mais recente.
app.router.routes = [
    r for r in app.router.routes
    if not (getattr(r,"path",None)=="/api/demo-pdf" and "GET" in getattr(r,"methods",set()))
]
app.add_api_route("/api/demo-pdf", demo_pdf, methods=["GET"])

app.version="6.0"

# --- UI v6.0 ---
HTML = HTML.replace(
    "Do processo extenso à evidência que sustenta a decisão.",
    "Leia menos páginas. Encontre mais evidências. Decida com mais segurança."
)

HTML = HTML.replace(
    "@media(max-width:1050px)",
    """.control-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.control-card{border:1px solid var(--line);border-radius:13px;padding:14px;background:#fbfcfe}
.control-card b{display:block;color:var(--navy);font-size:12px}.control-card span{display:block;color:var(--muted);font-size:10px;margin-top:4px}
.check-row{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid var(--line);font-size:11px}.check-row:last-child{border-bottom:0}
.check-ok{font-weight:900;color:var(--teal)}.check-miss{font-weight:900;color:var(--warn)}
.contradiction{border-left:4px solid #b7791f;background:#fffaf0;padding:12px 14px;border-radius:8px;margin:9px 0}
.contradiction.high{border-left-color:#b42318;background:#fff5f4}
.contradiction b{display:block;color:var(--navy);font-size:12px}.contradiction p{margin:4px 0;color:var(--muted);font-size:11px}
.next-action{border:1px solid #b8d8d2;background:#effaf8;border-radius:14px;padding:16px}.next-action strong{display:block;color:var(--teal);font-size:13px}.next-action p{margin:6px 0 0;font-size:12px;color:#29465a}
.review-flag{display:flex;gap:9px;align-items:flex-start;padding:9px 0;border-bottom:1px solid var(--line);font-size:11px}.review-flag:last-child{border-bottom:0}
.flag-dot{width:9px;height:9px;border-radius:50%;background:#d99a16;margin-top:4px;flex:0 0 auto}.flag-dot.high{background:#b42318}
.trace-row{display:grid;grid-template-columns:1.2fr .7fr .8fr;gap:12px;padding:9px 0;border-bottom:1px solid var(--line);font-size:10px}.trace-row b{color:var(--navy)}
.metric-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.metric{border:1px solid var(--line);border-radius:11px;padding:12px;background:#f8fafc}.metric strong{display:block;font-size:22px;color:var(--navy)}.metric span{font-size:9px;text-transform:uppercase;color:var(--muted);letter-spacing:.06em}
.doc-chain{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.doc-chain .btn{font-size:10px;padding:9px 11px}
.privacy-box{display:flex;justify-content:space-between;gap:20px;align-items:center;border:1px solid var(--line);border-radius:13px;padding:14px 16px;background:#f8fafc;margin-top:14px}.privacy-box p{margin:0;font-size:10px;color:var(--muted);max-width:900px}
.bank-mode{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:14px}.bank-step{border:1px solid var(--line);border-radius:10px;padding:10px;background:#fff}.bank-step b{font-size:10px;color:var(--navy)}.bank-step span{display:block;font-size:9px;color:var(--muted);margin-top:3px}
@media(max-width:1050px){.control-grid{grid-template-columns:1fr}.metric-grid{grid-template-columns:repeat(2,1fr)}.bank-mode{grid-template-columns:1fr}.trace-row{grid-template-columns:1fr}} 
@media(max-width:1050px)"""
)

# Painel de fluxo de documentos antes do relatório.
_doc_panel = """  <section class="panel">
    <div class="panel-head"><div><div class="kicker">Fluxo documental assistido</div><h2 class="title">Gerar próximo documento</h2><p class="desc">Minutas padronizadas com preenchimento apenas de dados validados. A decisão e a revisão permanecem humanas.</p></div></div>
    <div class="doc-chain">
      <button class="btn btn-blue" onclick="gerarDocumento('despacho')">Despacho de instauração</button>
      <button class="btn btn-blue" onclick="gerarDocumento('notificacao')">Notificação</button>
      <button class="btn btn-blue" onclick="gerarDocumento('intimacao')">Intimação</button>
      <button class="btn btn-blue" onclick="gerarDocumento('diligencia')">Diligência</button>
      <button class="btn btn-blue" onclick="gerarDocumento('relatorio')">Relatório conclusivo</button>
      <button class="btn btn-primary" onclick="gerarDocumento('decisao')">Minuta de decisão</button>
    </div>
    <div id="chainDraftBox" class="draft-box">
      <div class="draft-toolbar"><div><strong>Documento para revisão</strong><br><span>Edite e confira antes de qualquer uso oficial.</span></div><div class="draft-actions"><button class="btn btn-blue" onclick="copiarChain()">Copiar</button><button class="btn btn-primary" onclick="baixarChain()">Baixar .txt</button></div></div>
      <textarea id="chainDraftText" class="draft-text"></textarea>
      <div id="chainSources" class="draft-sources"></div>
    </div>
  </section>

  <section class="panel">
    <div class="panel-head"><div><div class="kicker">Privacidade e sessão</div><h2 class="title">Controle dos dados analisados</h2></div></div>
    <div class="privacy-box"><p>O conteúdo extraído permanece apenas na memória temporária desta instância para permitir perguntas e minutas. A sessão expira automaticamente em até 30 minutos. Para testes públicos, prefira dados fictícios ou documentos públicos.</p><button class="btn btn-primary" onclick="encerrarAnalise()">Encerrar e excluir dados da sessão</button></div>
  </section>

"""
_report_marker = """  <section class="panel">
    <div class="footer-actions">
      <div><div class="kicker">Documentação da análise</div><h2 class="title">Relatório para revisão humana</h2>"""
if _report_marker in HTML:
    HTML=HTML.replace(_report_marker,_doc_panel+_report_marker,1)

# Roteiro de banca de 90 segundos dentro do painel demonstrativo.
_demo_anchor = """    <div class="demo-note">Cenário fictício criado exclusivamente para demonstração e avaliação do produto.</div>"""
_demo_add = """    <div class="demo-note">Cenário fictício criado exclusivamente para demonstração e avaliação do produto.</div>
    <div class="bank-mode">
      <div class="bank-step"><b>0–15s · Processo</b><span>Abra o caso modelo completo.</span></div>
      <div class="bank-step"><b>15–35s · Evidência</b><span>Mostre linha do tempo e matriz.</span></div>
      <div class="bank-step"><b>35–55s · Risco</b><span>Abra pendências e contradições.</span></div>
      <div class="bank-step"><b>55–75s · Consulta</b><span>Pergunte sobre a defesa e fontes.</span></div>
      <div class="bank-step"><b>75–90s · Ação</b><span>Gere a minuta e mostre revisão humana.</span></div>
    </div>"""
if _demo_anchor in HTML:
    HTML=HTML.replace(_demo_anchor,_demo_add,1)

# Mede o tempo real de análise no navegador.
HTML=HTML.replace(
    'var fd=new FormData();for(var i=0;i<fs.length;i++)fd.append("files",fs[i]);',
    'var startedAt=performance.now();var fd=new FormData();for(var i=0;i<fs.length;i++)fd.append("files",fs[i]);',
    1
)
HTML=HTML.replace(
    'var a=d.analysis;var h="";',
    'var elapsedSec=((performance.now()-startedAt)/1000).toFixed(1);var a=d.analysis;var h="";',
    1
)

# Insere os novos painéis no resultado, antes de cautelas/limites.
_result_anchor = """  h+='<section class="section"><div class="kicker">Cautelas da análise</div><h2>Pendências e limites</h2>';"""
_result_insert = """  if(a.metrics){
    h+='<section class="section"><div class="kicker">Impacto da análise</div><h2>Métricas desta execução</h2><div class="metric-grid">';
    h+='<div class="metric"><strong>'+a.metrics.pages+'</strong><span>páginas lidas</span></div>';
    h+='<div class="metric"><strong>'+a.metrics.pieces+'</strong><span>peças identificadas</span></div>';
    h+='<div class="metric"><strong>'+a.metrics.evidence_points+'</strong><span>pontos de evidência</span></div>';
    h+='<div class="metric"><strong>'+a.metrics.checklist_ok+'/'+a.metrics.checklist_total+'</strong><span>controles atendidos</span></div>';
    h+='<div class="metric"><strong>'+elapsedSec+'s</strong><span>tempo desta análise</span></div>';
    h+='</div></section>';
  }

  if(a.process_checklist){
    h+='<div class="control-grid"><section class="section"><div class="kicker">Controle processual</div><h2>Mapa de pendências</h2>';
    for(var ci=0;ci<a.process_checklist.length;ci++){var cr=a.process_checklist[ci];h+='<div class="check-row"><span>'+esc(cr.label)+(cr.pages.length?' · p. '+esc(cr.pages.join(", ")):'')+'</span><span class="'+(cr.ok?'check-ok':'check-miss')+'">'+(cr.ok?'✓ Confirmado':'! Conferir')+'</span></div>'}
    h+='</section>';

    h+='<section class="section"><div class="kicker">Confronto inteligente</div><h2>Contradições e divergências</h2>';
    if(!a.contradictions||!a.contradictions.length)h+='<div class="empty">Nenhuma contradição objetiva relevante foi detectada automaticamente.</div>';
    for(var cc=0;cc<(a.contradictions||[]).length;cc++){var co=a.contradictions[cc];h+='<div class="contradiction '+(co.severity==="alta"?"high":"")+'"><b>'+esc(co.title)+'</b><p>'+esc(co.detail)+'</p><div class="sources">'+(co.sources||[]).map(function(s){return '<span class="source-card">'+esc(s.label)+' · p. '+esc(s.page)+'</span>'}).join("")+'</div></div>'}
    h+='</section>';

    h+='<section class="section"><div class="kicker">Próximo passo</div><h2>Ação processual sugerida</h2>';
    if(a.next_action)h+='<div class="next-action"><strong>'+esc(a.next_action.stage)+'</strong><p>'+esc(a.next_action.action)+'</p><p><b>Por quê:</b> '+esc(a.next_action.why)+'</p></div>';
    h+='</section></div>';
  }

  if(a.review_flags){
    h+='<div class="cols"><section class="section"><div class="kicker">Revisão da Comissão</div><h2>Pontos antes da assinatura</h2>';
    if(!a.review_flags.length)h+='<div class="empty">Nenhum alerta prioritário identificado automaticamente.</div>';
    for(var rf=0;rf<a.review_flags.length;rf++){var fl=a.review_flags[rf];h+='<div class="review-flag"><span class="flag-dot '+(fl.level==="alta"?"high":"")+'"></span><span>'+esc(fl.text)+'</span></div>'}
    h+='</section><section class="section"><div class="kicker">Como chegou aqui</div><h2>Rastreabilidade da conclusão</h2>';
    for(var tr=0;tr<(a.traceability||[]).slice(0,10).length;tr++){var tv=a.traceability[tr];h+='<div class="trace-row"><b>'+esc(tv.claim)+'</b><span>'+esc(tv.status)+'</span><span>'+esc(sourceLabel(tv.source))+' · p. '+esc((tv.pages||[]).join(", "))+'</span></div>'}
    h+='</section></div>';
  }

  h+='<section class="section"><div class="kicker">Cautelas da análise</div><h2>Pendências e limites</h2>';"""
if _result_anchor in HTML:
    HTML=HTML.replace(_result_anchor,_result_insert,1)

# Funções do fluxo documental e exclusão de sessão.
_js_anchor = "function relatorio(){"
_js_new = """async function gerarDocumento(kind){
  analysisId=analysisId||localStorage.getItem("fiscaliza_analysis_id");
  if(!analysisId){alert("Analise um processo primeiro.");return}
  var box=document.getElementById("chainDraftBox"),ta=document.getElementById("chainDraftText"),src=document.getElementById("chainSources");
  box.style.display="block";ta.value="Gerando documento assistido…";src.innerHTML="";
  var r=await fetch("/api/document-draft",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({analysis_id:analysisId,kind:kind})});
  var d=await r.json();
  if(!r.ok){ta.value=d.detail||"Não foi possível gerar o documento.";return}
  ta.value=d.draft;
  src.innerHTML='<div class="kicker">Fontes e contexto</div>'+(d.sources||[]).map(function(x){return '<span class="source-card">'+esc(x)+'</span>'}).join("");
  box.scrollIntoView({behavior:"smooth",block:"start"});
}
async function copiarChain(){
  var ta=document.getElementById("chainDraftText");if(!ta.value)return;
  try{await navigator.clipboard.writeText(ta.value)}catch(e){ta.select();document.execCommand("copy")}
}
function baixarChain(){
  var ta=document.getElementById("chainDraftText");if(!ta.value)return;
  var blob=new Blob([ta.value],{type:"text/plain;charset=utf-8"});
  var a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="fiscaliza-minuta-assistida.txt";a.click();URL.revokeObjectURL(a.href);
}
async function encerrarAnalise(){
  analysisId=analysisId||localStorage.getItem("fiscaliza_analysis_id");
  if(analysisId){try{await fetch("/api/analysis/"+analysisId,{method:"DELETE"})}catch(e){}}
  analysisId=null;localStorage.removeItem("fiscaliza_analysis_id");
  var fi=document.getElementById("files");if(fi)fi.value="";
  var rs=document.getElementById("result");if(rs)rs.innerHTML="";
  var st=document.getElementById("status");if(st)st.textContent="Sessão encerrada e estado da análise removido desta instância.";
  var ab=document.getElementById("answer");if(ab)ab.style.display="none";
  var db=document.getElementById("draftBox");if(db)db.style.display="none";
  var cb=document.getElementById("chainDraftBox");if(cb)cb.style.display="none";
}
"""
if _js_anchor in HTML:
    HTML=HTML.replace(_js_anchor,_js_new+_js_anchor,1)

HTML=HTML.replace("VERSÃO 5.1 · PROCESSO MODELO COMPLETO","VERSÃO 6.0 · CONTROLE PROCESSUAL COMPLETO")


# --- Plataforma modular v6.1 ---
MODULES = {
    "penalizacao":{"label":"Penalização contratual","short":"Penalização","desc":"Responsabilização de fornecedor, contraditório, defesa, sanção e decisão."},
    "fiscalizacao":{"label":"Fiscalização de contratos","short":"Fiscalização","desc":"Execução, entregas, ocorrências, fiscalização, medições e providências."},
    "reequilibrio":{"label":"Reequilíbrio econômico-financeiro","short":"Reequilíbrio","desc":"Pedido, fatos supervenientes, planilhas, pareceres e decisão."},
    "rescisao":{"label":"Rescisão / extinção contratual","short":"Rescisão","desc":"Motivação, comunicação, contraditório, parecer e decisão de extinção."},
    "disciplinar":{"label":"Processo disciplinar","short":"Disciplinar","desc":"Instauração, citação, instrução, defesa, relatório e julgamento."},
    "sindicancia":{"label":"Sindicância","short":"Sindicância","desc":"Fato investigado, diligências, depoimentos, relatório e encaminhamento."},
    "lai":{"label":"Ouvidoria e LAI","short":"Ouvidoria / LAI","desc":"Pedido, protocolo, prazo, resposta, recurso e transparência."},
    "prestacao":{"label":"Convênios e prestação de contas","short":"Prestação de contas","desc":"Instrumento, plano, execução, comprovação, análise e decisão."},
    "licitacoes":{"label":"Licitações e contratação","short":"Licitações","desc":"Edital, termo de referência, habilitação, propostas e homologação."},
    "cobranca":{"label":"Cobrança administrativa","short":"Cobrança","desc":"Origem do débito, memória de cálculo, notificação e manifestação."},
    "servidores":{"label":"Processos de servidores","short":"Servidores","desc":"Requerimentos funcionais, RH, documentos, pareceres e decisão."},
    "tributario":{"label":"Processo tributário municipal","short":"Tributário","desc":"Lançamento, auto, ciência, impugnação, recurso e julgamento."},
    "geral":{"label":"Análise geral","short":"Geral","desc":"Leitura, cronologia, peças, evidências, divergências e decisão."}
}

MODULE_RULES = {
    "fiscalizacao":[("Instrumento contratual",["contrato"]),("Designação de fiscal/gestor",["fiscal"]),("Relatório de execução",["relatorio","execucao"]),("Entrega/medição/recebimento",["entrega"]),("Ocorrência ou comunicação",["notificacao"]),("Providência administrativa",["providencia"])],
    "reequilibrio":[("Pedido de reequilíbrio",["reequilibrio"]),("Contrato/instrumento",["contrato"]),("Planilha, orçamento ou cotação",["orcamento"]),("Fato superveniente/justificativa",["desequilibrio"]),("Parecer técnico/jurídico",["parecer"]),("Decisão",["decisao"])],
    "rescisao":[("Contrato/instrumento",["contrato"]),("Motivação da extinção",["rescis"]),("Notificação da contratada",["notificacao"]),("Manifestação/defesa",["defesa"]),("Parecer jurídico",["parecer juridico"]),("Decisão de extinção",["decisao"])],
    "disciplinar":[("Portaria/ato de instauração",["instaur"]),("Citação/notificação",["citacao"]),("Instrução/provas",["prova"]),("Defesa",["defesa"]),("Relatório da comissão",["relatorio"]),("Julgamento/decisão",["decisao"])],
    "sindicancia":[("Ato de instauração",["sindicancia"]),("Descrição do fato",["fato"]),("Diligências/depoimentos",["diligencia"]),("Documentos/provas",["prova"]),("Relatório conclusivo",["relatorio"]),("Encaminhamento/decisão",["decisao"])],
    "lai":[("Pedido/protocolo",["pedido"]),("Identificação do órgão",["orgao"]),("Prazo",["prazo"]),("Resposta",["resposta"]),("Recurso",["recurso"]),("Decisão final",["decisao"])],
    "prestacao":[("Convênio/instrumento",["convenio"]),("Plano de trabalho",["plano de trabalho"]),("Execução do objeto",["execucao"]),("Prestação de contas",["prestacao de contas"]),("Análise técnica/financeira",["analise"]),("Decisão/aprovação",["decisao"])],
    "licitacoes":[("Edital/aviso",["edital"]),("Termo de referência",["termo de referencia"]),("Propostas/habilitação",["habilitacao"]),("Ata da sessão",["ata"]),("Parecer jurídico",["parecer juridico"]),("Adjudicação/homologação",["homolog"])],
    "cobranca":[("Origem do débito",["debito"]),("Memória de cálculo",["calculo"]),("Notificação",["notificacao"]),("Comprovação de ciência",["ciencia"]),("Manifestação do interessado",["manifestacao"]),("Decisão/providência",["decisao"])],
    "servidores":[("Requerimento",["requer"]),("Documentos funcionais",["servidor"]),("Manifestação do RH",["recursos humanos"]),("Parecer técnico/jurídico",["parecer"]),("Ciência do interessado",["ciencia"]),("Decisão",["decisao"])],
    "tributario":[("Lançamento/auto",["lancamento"]),("Ciência do contribuinte",["ciencia"]),("Impugnação",["impugn"]),("Instrução/provas",["prova"]),("Decisão",["decisao"]),("Recurso",["recurso"])],
    "geral":[("Identificação do processo",["processo"]),("Documento de origem",["protocolo"]),("Manifestação do interessado",["manifestacao"]),("Parecer/análise",["parecer"]),("Decisão",["decisao"]),("Prazo/documento de ciência",["prazo"])]
}

def _term_pages(pages, terms):
    found=[]
    for p in pages:
        z=norm(p.get("text") or "")
        if all(norm(t) in z for t in terms):
            found.append(p["page"])
    return found

def _module_overlay(pages,a,module):
    module=module if module in MODULES else "geral"
    info=MODULES[module]
    a["module_key"]=module
    a["module_label"]=info["label"]
    a["module_desc"]=info["desc"]

    if module=="penalizacao":
        qv=str(a.get("quantity",{}).get("value",""))
        a["module_summary"]=[
            {"label":"Defesa","ok":bool(a.get("has",{}).get("defesa")),"value":"Localizada" if a.get("has",{}).get("defesa") else "Não localizada"},
            {"label":"Notificação / intimação","ok":bool(a.get("has",{}).get("notificacao") or a.get("has",{}).get("intimacao")),"value":"Localizada" if (a.get("has",{}).get("notificacao") or a.get("has",{}).get("intimacao")) else "Não localizada"},
            {"label":"Decisão","ok":bool(a.get("has",{}).get("decisao")),"value":"Localizada" if a.get("has",{}).get("decisao") else "Não localizada"},
            {"label":"Quantidade total","ok":"nao identificado" not in norm(qv),"value":qv or "Inconclusivo"}
        ]
        return a

    rules=MODULE_RULES.get(module,MODULE_RULES["geral"])
    checklist=[]
    for label,terms in rules:
        pgs=_term_pages(pages,terms)
        checklist.append({"label":label,"ok":bool(pgs),"pages":pgs[:6]})
    a["process_checklist"]=checklist
    a["metrics"]["checklist_ok"]=sum(1 for x in checklist if x["ok"])
    a["metrics"]["checklist_total"]=len(checklist)

    missing=[x["label"] for x in checklist if not x["ok"]]
    present=[x["label"] for x in checklist if x["ok"]]
    a["review_flags"]=[{"level":"media","text":"Não identificado com segurança: "+x+"."} for x in missing[:5]]

    if present:
        stage=present[-1]
        if missing:
            action="Conferir ou localizar o seguinte elemento esperado para este módulo: "+missing[0]+"."
            why="O processo contém "+str(len(present))+" de "+str(len(checklist))+" controles previstos no módulo "+info["short"]+"."
        else:
            action="Revisar a coerência entre os documentos identificados e conferir se a decisão ou encaminhamento enfrenta os pontos relevantes."
            why="Todos os controles básicos deste módulo foram localizados automaticamente."
    else:
        stage="Triagem inicial"
        action="Confirmar o tipo de processo e localizar os documentos estruturantes antes de avançar para uma conclusão."
        why="Poucos elementos específicos deste módulo foram identificados com segurança."
    a["next_action"]={"stage":stage,"action":action,"why":why}

    a["module_summary"]=[
        {"label":x["label"],"ok":x["ok"],"value":"Localizado" if x["ok"] else "Conferir"}
        for x in checklist[:4]
    ]
    a["conclusion"]="Modo "+info["label"]+": o sistema organizou os autos segundo os controles próprios deste tipo de processo, mantendo as evidências rastreáveis e a revisão humana."
    return a

async def analyze_v61(files:List[UploadFile]=File(...), module:str="penalizacao"):
    pages=[];ocr=0;names=[]
    for f in files:
        if not f.filename.lower().endswith(".pdf"):continue
        pp,oo=extract_pdf(await f.read(),f.filename);pages.extend(pp);ocr+=oo;names.append(f.filename)
    if not pages:raise HTTPException(400,"Envie pelo menos um PDF.")
    a=analyze_pages(pages)
    a=_module_overlay(pages,a,module)
    aid=uuid.uuid4().hex
    ANALYSES[aid]={"pages":pages,"analysis":a,"created":datetime.utcnow().isoformat(),"module":module}
    return {"analysis_id":aid,"files":names,"pages":len(pages),"ocr_pages":ocr,"module":module,"analysis":a}

app.router.routes=[
    r for r in app.router.routes
    if not (getattr(r,"path",None)=="/api/analyze" and "POST" in getattr(r,"methods",set()))
]
app.add_api_route("/api/analyze",analyze_v61,methods=["POST"])
app.version="6.1"

_module_css = """
.module-panel{margin-top:18px}.module-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.module-card{appearance:none;text-align:left;background:#fff;border:1px solid var(--line);border-radius:13px;padding:13px;cursor:pointer;transition:.16s ease;color:var(--ink)}
.module-card:hover{transform:translateY(-1px);border-color:#a8bacb;box-shadow:0 6px 18px rgba(16,42,67,.06)}
.module-card.active{border:2px solid var(--teal);background:var(--teal-soft);padding:12px}
.module-icon{width:30px;height:30px;border-radius:8px;background:#eef3f8;color:var(--navy);display:grid;place-items:center;font-size:13px;font-weight:900;margin-bottom:9px}
.module-card.active .module-icon{background:var(--teal);color:#fff}
.module-name{font-size:11px;font-weight:900;color:var(--navy);line-height:1.25}.module-desc{font-size:9px;color:var(--muted);margin-top:4px;line-height:1.35}
.module-selected{display:flex;justify-content:space-between;align-items:center;gap:10px;background:#f8fafc;border:1px solid var(--line);border-radius:10px;padding:9px 11px;margin-top:12px;font-size:10px;color:var(--muted)}
.module-selected strong{color:var(--teal)}
@media(max-width:1100px){.module-grid{grid-template-columns:repeat(3,1fr)}}@media(max-width:760px){.module-grid{grid-template-columns:1fr 1fr}}@media(max-width:480px){.module-grid{grid-template-columns:1fr}}
"""
HTML=HTML.replace("</style>",_module_css+"</style>",1)

_module_html = """<section class="panel module-panel">
  <div class="panel-head"><div><div class="kicker">Módulos especializados</div><h2 class="title">Que tipo de processo você deseja analisar?</h2><p class="desc">A leitura documental é comum a todos os módulos; checklist, pendências e próximo passo se adaptam ao procedimento selecionado.</p></div></div>
  <div class="module-grid">
    <button class="module-card active" data-module="penalizacao" onclick="selecionarModulo('penalizacao',this)"><div class="module-icon">⚖</div><div class="module-name">Penalização contratual</div><div class="module-desc">Responsabilização, defesa, sanção e decisão.</div></button>
    <button class="module-card" data-module="fiscalizacao" onclick="selecionarModulo('fiscalizacao',this)"><div class="module-icon">◎</div><div class="module-name">Fiscalização de contratos</div><div class="module-desc">Execução, entregas, ocorrências e fiscalização.</div></button>
    <button class="module-card" data-module="reequilibrio" onclick="selecionarModulo('reequilibrio',this)"><div class="module-icon">↔</div><div class="module-name">Reequilíbrio econômico-financeiro</div><div class="module-desc">Pedido, custos, justificativas, pareceres e decisão.</div></button>
    <button class="module-card" data-module="rescisao" onclick="selecionarModulo('rescisao',this)"><div class="module-icon">✕</div><div class="module-name">Rescisão / extinção</div><div class="module-desc">Motivação, contraditório, parecer e decisão.</div></button>
    <button class="module-card" data-module="disciplinar" onclick="selecionarModulo('disciplinar',this)"><div class="module-icon">§</div><div class="module-name">Processo disciplinar</div><div class="module-desc">Instauração, citação, defesa, relatório e julgamento.</div></button>
    <button class="module-card" data-module="sindicancia" onclick="selecionarModulo('sindicancia',this)"><div class="module-icon">⌕</div><div class="module-name">Sindicância</div><div class="module-desc">Fato, diligências, provas e relatório conclusivo.</div></button>
    <button class="module-card" data-module="lai" onclick="selecionarModulo('lai',this)"><div class="module-icon">◉</div><div class="module-name">Ouvidoria e LAI</div><div class="module-desc">Pedido, prazo, resposta, recurso e transparência.</div></button>
    <button class="module-card" data-module="prestacao" onclick="selecionarModulo('prestacao',this)"><div class="module-icon">▣</div><div class="module-name">Convênios e prestação de contas</div><div class="module-desc">Plano, execução, comprovação, análise e decisão.</div></button>
    <button class="module-card" data-module="licitacoes" onclick="selecionarModulo('licitacoes',this)"><div class="module-icon">◆</div><div class="module-name">Licitações e contratação</div><div class="module-desc">Edital, habilitação, propostas e homologação.</div></button>
    <button class="module-card" data-module="cobranca" onclick="selecionarModulo('cobranca',this)"><div class="module-icon">R$</div><div class="module-name">Cobrança administrativa</div><div class="module-desc">Débito, cálculo, notificação e manifestação.</div></button>
    <button class="module-card" data-module="servidores" onclick="selecionarModulo('servidores',this)"><div class="module-icon">●</div><div class="module-name">Processos de servidores</div><div class="module-desc">Requerimento, RH, pareceres e decisão.</div></button>
    <button class="module-card" data-module="tributario" onclick="selecionarModulo('tributario',this)"><div class="module-icon">#</div><div class="module-name">Processo tributário municipal</div><div class="module-desc">Lançamento, impugnação, decisão e recurso.</div></button>
    <button class="module-card" data-module="geral" onclick="selecionarModulo('geral',this)"><div class="module-icon">◇</div><div class="module-name">Análise geral</div><div class="module-desc">Cronologia, evidências, divergências e decisão.</div></button>
  </div>
  <div class="module-selected">Módulo ativo: <strong id="moduleActiveLabel">Penalização contratual</strong><span>Você pode trocar antes de analisar.</span></div>
</section>
"""
_upload_marker='<section class="panel">\n    <div class="panel-head"><div><div class="kicker">Analisar seus documentos</div>'
if _upload_marker in HTML:
    HTML=HTML.replace(_upload_marker,_module_html+"\n"+_upload_marker,1)

HTML=HTML.replace(
    "var analysisId=null; var demoMode=false;",
    """var analysisId=null; var demoMode=false; var selectedModule="penalizacao";
var moduleLabels={penalizacao:"Penalização contratual",fiscalizacao:"Fiscalização de contratos",reequilibrio:"Reequilíbrio econômico-financeiro",rescisao:"Rescisão / extinção contratual",disciplinar:"Processo disciplinar",sindicancia:"Sindicância",lai:"Ouvidoria e LAI",prestacao:"Convênios e prestação de contas",licitacoes:"Licitações e contratação",cobranca:"Cobrança administrativa",servidores:"Processos de servidores",tributario:"Processo tributário municipal",geral:"Análise geral"};
function selecionarModulo(key,el){
  selectedModule=key;
  document.querySelectorAll(".module-card").forEach(function(x){x.classList.remove("active")});
  if(el)el.classList.add("active");
  var lab=document.getElementById("moduleActiveLabel");if(lab)lab.textContent=moduleLabels[key]||key;
}"""
)

HTML=HTML.replace(
    "demoMode=true;\n    await analisar();",
    """demoMode=true;
    selectedModule="penalizacao";
    var mc=document.querySelector('.module-card[data-module="penalizacao"]');if(mc)selecionarModulo("penalizacao",mc);
    await analisar();""",
    1
)

HTML=HTML.replace(
    'var r=await fetch("/api/analyze",{method:"POST",body:fd});var d=await r.json();',
    'var r=await fetch("/api/analyze?module="+encodeURIComponent(selectedModule),{method:"POST",body:fd});var d=await r.json();',
    1
)

HTML=HTML.replace(
    """h+='<section class="section"><div class="kicker">Resumo executivo</div><h2>Análise assistida</h2><p>'+esc(a.conclusion)+'</p><div class="summary-grid">';""",
    """h+='<section class="section"><div class="kicker">Resumo executivo · '+esc(a.module_label||moduleLabels[selectedModule]||selectedModule)+'</div><h2>Análise assistida</h2><p>'+esc(a.conclusion)+'</p><div class="summary-grid">';""",
    1
)

_old_summary = """  h+='<div class="summary-card"><div class="summary-label">Defesa</div><div class="summary-value">'+stateIcon(a.has.defesa,false)+(a.has.defesa?"Localizada":"Não localizada")+'</div></div>';
  h+='<div class="summary-card"><div class="summary-label">Notificação / intimação</div><div class="summary-value">'+stateIcon(a.has.notificacao||a.has.intimacao,false)+((a.has.notificacao||a.has.intimacao)?"Localizada":"Não localizada")+'</div></div>';
  h+='<div class="summary-card"><div class="summary-label">Decisão</div><div class="summary-value">'+stateIcon(a.has.decisao,false)+(a.has.decisao?"Localizada":"Não localizada")+'</div></div>';
  h+='<div class="summary-card"><div class="summary-label">Quantidade total</div><div class="summary-value">'+stateIcon(!qUnknown,qUnknown)+esc(qUnknown?"Inconclusivo":a.quantity.value)+'</div></div></div></section>';"""
_new_summary = """  if(a.module_summary&&a.module_summary.length){
    for(var ms=0;ms<a.module_summary.length;ms++){var sm=a.module_summary[ms];h+='<div class="summary-card"><div class="summary-label">'+esc(sm.label)+'</div><div class="summary-value">'+stateIcon(sm.ok,!sm.ok)+esc(sm.value)+'</div></div>'}
  }else{
    h+='<div class="summary-card"><div class="summary-label">Defesa</div><div class="summary-value">'+stateIcon(a.has.defesa,false)+(a.has.defesa?"Localizada":"Não localizada")+'</div></div>';
    h+='<div class="summary-card"><div class="summary-label">Notificação / intimação</div><div class="summary-value">'+stateIcon(a.has.notificacao||a.has.intimacao,false)+((a.has.notificacao||a.has.intimacao)?"Localizada":"Não localizada")+'</div></div>';
    h+='<div class="summary-card"><div class="summary-label">Decisão</div><div class="summary-value">'+stateIcon(a.has.decisao,false)+(a.has.decisao?"Localizada":"Não localizada")+'</div></div>';
    h+='<div class="summary-card"><div class="summary-label">Quantidade total</div><div class="summary-value">'+stateIcon(!qUnknown,qUnknown)+esc(qUnknown?"Inconclusivo":a.quantity.value)+'</div></div>';
  }
  h+='</div></section>';"""
if _old_summary in HTML:
    HTML=HTML.replace(_old_summary,_new_summary,1)

HTML=HTML.replace(
    """h+='<div class="cols"><section class="section"><div class="kicker">Contraditório</div><h2>Elementos favoráveis à defesa</h2>';""",
    """h+='<div class="cols"><section class="section"><div class="kicker">'+(a.module_key==="penalizacao"?"Contraditório":"Manifestações")+'</div><h2>'+(a.module_key==="penalizacao"?"Elementos favoráveis à defesa":"Elementos apresentados pelo interessado")+'</h2>';""",
    1
)

HTML=HTML.replace("VERSÃO 6.0 · CONTROLE PROCESSUAL COMPLETO","VERSÃO 6.1 · PLATAFORMA MODULAR")


# --- Processos modelo por módulo v6.2 ---
_penalizacao_demo_pdf_v51 = demo_pdf

MODEL_CASES = {
    "fiscalizacao": {
        "title":"Fiscalização de contratos",
        "pages":[
            ("PROCESSO DE FISCALIZAÇÃO CONTRATUAL Nº 1001/2026","CASO FICTÍCIO. Contrato nº 210/2026. Objeto: manutenção preventiva de aparelhos de ar-condicionado em unidades municipais."),
            ("CONTRATO ADMINISTRATIVO Nº 210/2026","CONTRATANTE: Município Demonstração. CONTRATADA: Clima Modelo Ltda. Objeto: manutenção preventiva mensal. Prazo: 12 meses. A fiscalização deverá acompanhar a execução e registrar ocorrências."),
            ("PORTARIA DE DESIGNAÇÃO DE FISCAL Nº 55/2026","Fica designada a servidora Fiscal Exemplo para atuar como fiscal do Contrato nº 210/2026, acompanhando a execução e registrando as providências necessárias."),
            ("ORDEM DE SERVIÇO Nº 03/2026","Autoriza-se a execução dos serviços referentes ao mês de junho de 2026, conforme cronograma contratual."),
            ("RELATÓRIO DE EXECUÇÃO Nº 06/2026","O fiscal registra execução parcial dos serviços. Duas unidades não receberam a manutenção prevista e três equipamentos apresentaram pendências."),
            ("TERMO DE RECEBIMENTO / MEDIÇÃO Nº 06/2026","Foram recebidos e medidos os serviços efetivamente executados, com glosa dos itens não realizados."),
            ("NOTIFICAÇÃO DE OCORRÊNCIA Nº 02/2026","A contratada fica notificada para regularizar as pendências apontadas no relatório de fiscalização e apresentar manifestação."),
            ("MANIFESTAÇÃO DA CONTRATADA","A empresa reconhece atraso em duas unidades, apresenta cronograma de correção e informa providência administrativa para reforço da equipe."),
            ("RELATÓRIO FINAL DE FISCALIZAÇÃO","A fiscalização registra o cumprimento das correções e recomenda o prosseguimento regular do contrato, com manutenção do acompanhamento.")
        ]
    },
    "reequilibrio": {
        "title":"Reequilíbrio econômico-financeiro",
        "pages":[
            ("PROCESSO DE REEQUILÍBRIO Nº 1102/2026","CASO FICTÍCIO. Pedido de reequilíbrio econômico-financeiro relacionado ao Contrato nº 305/2026."),
            ("CONTRATO ADMINISTRATIVO Nº 305/2026","Objeto: fornecimento continuado de gêneros alimentícios. Valor unitário registrado conforme proposta vencedora."),
            ("PEDIDO DE REEQUILÍBRIO ECONÔMICO-FINANCEIRO","A contratada requer reequilíbrio econômico-financeiro alegando aumento extraordinário do custo da matéria-prima ocorrido após a contratação."),
            ("ORÇAMENTO E COTAÇÕES DE MERCADO","A empresa apresenta orçamento de três fornecedores e planilha comparativa de preços atuais e preços da época da proposta."),
            ("NOTA TÉCNICA Nº 18/2026","A unidade técnica analisa a alegação de desequilíbrio, os índices de mercado, a variação dos custos e a relação entre o fato superveniente e o contrato."),
            ("PARECER JURÍDICO Nº 44/2026","O parecer examina os requisitos jurídicos do reequilíbrio econômico-financeiro e recomenda decisão motivada com base na prova efetivamente apresentada."),
            ("DECISÃO ADMINISTRATIVA","A autoridade DECIDE deferir parcialmente o pedido de reequilíbrio, fixando novo valor unitário a partir da data definida no processo.")
        ]
    },
    "rescisao": {
        "title":"Rescisão / extinção contratual",
        "pages":[
            ("PROCESSO DE EXTINÇÃO CONTRATUAL Nº 1203/2026","CASO FICTÍCIO. Apuração de fatos relacionados ao Contrato nº 411/2026."),
            ("CONTRATO ADMINISTRATIVO Nº 411/2026","Objeto: serviços de transporte. O contrato prevê hipóteses de rescisão/extinção e assegura contraditório nas situações cabíveis."),
            ("RELATÓRIO DE OCORRÊNCIA","A fiscalização registra descumprimentos reiterados do cronograma e descreve a motivação técnica para avaliar a rescisão contratual."),
            ("NOTIFICAÇÃO À CONTRATADA","A empresa fica notificada sobre a intenção de extinção/rescisão e recebe oportunidade para apresentar manifestação e documentos."),
            ("DEFESA / MANIFESTAÇÃO DA CONTRATADA","A contratada apresenta defesa, contesta parte das ocorrências e requer continuidade do contrato mediante plano de regularização."),
            ("PARECER JURÍDICO Nº 52/2026","O parecer jurídico analisa os fundamentos da rescisão, o contraditório e os efeitos da eventual extinção contratual."),
            ("DECISÃO DE EXTINÇÃO CONTRATUAL","Após análise dos autos, a autoridade DECIDE pela extinção do Contrato nº 411/2026, com motivação individualizada e providências de encerramento.")
        ]
    },
    "disciplinar": {
        "title":"Processo disciplinar",
        "pages":[
            ("PROCESSO ADMINISTRATIVO DISCIPLINAR Nº 1304/2026","CASO FICTÍCIO. Servidor Exemplo. Objeto: apuração disciplinar de conduta funcional."),
            ("PORTARIA DE INSTAURAÇÃO Nº 77/2026","Fica instaurado Processo Administrativo Disciplinar para apuração dos fatos descritos no termo inicial e designada comissão processante."),
            ("CITAÇÃO DO SERVIDOR","O servidor é citado para acompanhar o processo, constituir defesa e exercer contraditório e ampla defesa."),
            ("ATA DE INSTRUÇÃO E PRODUÇÃO DE PROVAS","A comissão registra depoimentos, documentos e demais provas produzidas durante a instrução."),
            ("DEFESA ADMINISTRATIVA","O servidor apresenta defesa escrita, contesta os fatos e requer consideração das provas e circunstâncias funcionais."),
            ("RELATÓRIO DA COMISSÃO","Encerrada a instrução, a comissão elabora relatório conclusivo, resume as provas e encaminha os autos à autoridade competente."),
            ("DECISÃO DE JULGAMENTO","A autoridade DECIDE de forma motivada após examinar relatório, defesa e provas, registrando o resultado do julgamento disciplinar.")
        ]
    },
    "sindicancia": {
        "title":"Sindicância",
        "pages":[
            ("SINDICÂNCIA ADMINISTRATIVA Nº 1405/2026","CASO FICTÍCIO. Ato de instauração de sindicância para apurar fato ocorrido em unidade municipal."),
            ("ATO DE INSTAURAÇÃO","A autoridade determina a instauração da sindicância e descreve o fato que deverá ser investigado."),
            ("TERMO DE DILIGÊNCIA Nº 01","A comissão realiza diligência para reunir documentos, identificar envolvidos e esclarecer a sequência dos acontecimentos."),
            ("TERMO DE DEPOIMENTO E PROVAS","São juntados depoimento, documentos e outras provas relacionadas ao fato investigado."),
            ("RELATÓRIO CONCLUSIVO DA SINDICÂNCIA","A comissão apresenta relatório conclusivo com síntese dos fatos, diligências realizadas e elementos encontrados."),
            ("DECISÃO / ENCAMINHAMENTO","A autoridade DECIDE pelo arquivamento parcial e encaminha um ponto específico para apuração em procedimento próprio.")
        ]
    },
    "lai": {
        "title":"Ouvidoria e LAI",
        "pages":[
            ("PEDIDO DE ACESSO À INFORMAÇÃO Nº 1506/2026","CASO FICTÍCIO. Pedido protocolado por cidadão perante o órgão municipal para acesso a dados de contratos de manutenção."),
            ("PROTOCOLO E IDENTIFICAÇÃO DO ÓRGÃO","O pedido foi recebido pela Ouvidoria do Município Demonstração e encaminhado ao órgão responsável pelas informações."),
            ("CONTROLE DE PRAZO","O sistema registra o prazo legal para resposta e a data limite para manifestação do órgão responsável."),
            ("RESPOSTA AO PEDIDO","O órgão apresenta resposta, fornece parte dos documentos e justifica a restrição de um documento específico."),
            ("RECURSO DO REQUERENTE","O cidadão interpõe recurso contra a resposta parcial e solicita reavaliação da restrição."),
            ("DECISÃO DO RECURSO","A autoridade competente DECIDE o recurso, amplia parcialmente o acesso e mantém a restrição apenas sobre dado protegido.")
        ]
    },
    "prestacao": {
        "title":"Convênios e prestação de contas",
        "pages":[
            ("PROCESSO DE PRESTAÇÃO DE CONTAS Nº 1607/2026","CASO FICTÍCIO. Convênio nº 22/2026 para execução de projeto esportivo municipal."),
            ("CONVÊNIO Nº 22/2026","O convênio define objeto, metas, recursos, cronograma e responsabilidades das partes."),
            ("PLANO DE TRABALHO","O plano de trabalho detalha metas, etapas, cronograma de execução e previsão de despesas."),
            ("RELATÓRIO DE EXECUÇÃO DO OBJETO","A entidade apresenta relatório de execução, registros das atividades realizadas e resultados alcançados."),
            ("PRESTAÇÃO DE CONTAS","São juntados demonstrativos financeiros, notas fiscais, comprovantes de pagamento e conciliação dos recursos recebidos."),
            ("ANÁLISE TÉCNICA E FINANCEIRA","A unidade competente realiza análise da execução física e financeira e aponta pequena pendência documental."),
            ("DECISÃO DE APROVAÇÃO","Após saneamento da pendência, a autoridade DECIDE pela aprovação da prestação de contas com ressalva formal.")
        ]
    },
    "licitacoes": {
        "title":"Licitações e contratação",
        "pages":[
            ("PROCESSO LICITATÓRIO Nº 1708/2026","CASO FICTÍCIO. Pregão Eletrônico destinado à aquisição de equipamentos de informática."),
            ("EDITAL DO PREGÃO ELETRÔNICO Nº 88/2026","O edital estabelece objeto, critérios de julgamento, condições de participação e regras de habilitação."),
            ("TERMO DE REFERÊNCIA","O termo de referência descreve requisitos técnicos, quantidades, critérios de aceitação e obrigações da futura contratada."),
            ("PROPOSTAS E HABILITAÇÃO","São registradas as propostas recebidas, documentos de habilitação e resultado da análise dos licitantes."),
            ("ATA DA SESSÃO PÚBLICA","A ata registra lances, classificação, habilitação e ocorrências da sessão eletrônica."),
            ("PARECER JURÍDICO","O parecer jurídico examina a regularidade formal do procedimento antes do encerramento da fase externa."),
            ("ADJUDICAÇÃO E HOMOLOGAÇÃO","A autoridade competente adjudica o objeto e homologa o resultado do certame.")
        ]
    },
    "cobranca": {
        "title":"Cobrança administrativa",
        "pages":[
            ("PROCESSO DE COBRANÇA ADMINISTRATIVA Nº 1809/2026","CASO FICTÍCIO. Cobrança de débito decorrente de ressarcimento administrativo."),
            ("ORIGEM DO DÉBITO","A unidade responsável descreve o fato gerador do débito e identifica o valor principal sujeito à cobrança."),
            ("MEMÓRIA DE CÁLCULO","A memória de cálculo demonstra valor principal, atualização e total apurado na data de referência."),
            ("NOTIFICAÇÃO DE COBRANÇA","O interessado fica notificado para pagamento ou apresentação de manifestação no prazo indicado."),
            ("COMPROVANTE DE CIÊNCIA","Consta confirmação de ciência da notificação de cobrança pelo interessado."),
            ("MANIFESTAÇÃO DO INTERESSADO","O interessado apresenta manifestação, contesta parte do cálculo e junta comprovantes."),
            ("DECISÃO ADMINISTRATIVA","Após análise, a autoridade DECIDE retificar parcialmente o cálculo e manter a cobrança do saldo remanescente.")
        ]
    },
    "servidores": {
        "title":"Processos de servidores",
        "pages":[
            ("PROCESSO FUNCIONAL Nº 1910/2026","CASO FICTÍCIO. Servidora Modelo. Requerimento funcional de concessão de vantagem prevista em norma municipal."),
            ("REQUERIMENTO DA SERVIDORA","A servidora requer análise do direito e junta documentos funcionais e comprovantes pertinentes."),
            ("DOCUMENTOS FUNCIONAIS","São juntados ficha funcional, portarias, registros de exercício e demais documentos do servidor."),
            ("MANIFESTAÇÃO DE RECURSOS HUMANOS","O setor de Recursos Humanos confere tempo de serviço, registros e requisitos administrativos."),
            ("PARECER JURÍDICO","O parecer analisa a norma aplicável ao requerimento e orienta a autoridade quanto aos requisitos."),
            ("CIÊNCIA DA INTERESSADA","A servidora toma ciência da manifestação técnica e apresenta esclarecimento complementar."),
            ("DECISÃO ADMINISTRATIVA","A autoridade DECIDE o requerimento funcional de forma motivada e determina as providências de registro.")
        ]
    },
    "tributario": {
        "title":"Processo tributário municipal",
        "pages":[
            ("PROCESSO TRIBUTÁRIO Nº 2011/2026","CASO FICTÍCIO. Contribuinte Modelo Ltda. Impugnação de lançamento tributário municipal."),
            ("AUTO / LANÇAMENTO TRIBUTÁRIO Nº 33/2026","O lançamento identifica tributo, período, base de cálculo e valor exigido do contribuinte."),
            ("COMPROVANTE DE CIÊNCIA DO CONTRIBUINTE","O contribuinte recebe ciência formal do lançamento e do prazo para impugnação."),
            ("IMPUGNAÇÃO ADMINISTRATIVA","O contribuinte apresenta impugnação, questiona a base de cálculo e junta documentos."),
            ("INSTRUÇÃO E PROVAS","A autoridade fiscal reúne prova documental, informação cadastral e memória de cálculo revisada."),
            ("DECISÃO DE PRIMEIRA INSTÂNCIA","A autoridade DECIDE a impugnação, acolhendo parcialmente um ponto e mantendo o restante do lançamento."),
            ("RECURSO ADMINISTRATIVO","O contribuinte interpõe recurso contra a parcela mantida e requer novo julgamento administrativo.")
        ]
    },
    "geral": {
        "title":"Análise geral",
        "pages":[
            ("PROCESSO ADMINISTRATIVO Nº 2112/2026","CASO FICTÍCIO. Processo administrativo geral para análise de pedido formulado por interessado."),
            ("PROTOCOLO DE ORIGEM Nº 2112/2026","O protocolo registra o pedido inicial e identifica a unidade responsável pelo processamento."),
            ("MANIFESTAÇÃO DO INTERESSADO","O interessado apresenta sua manifestação, documentos e pedido específico à Administração."),
            ("INFORMAÇÃO TÉCNICA","A unidade técnica organiza os fatos e apresenta análise preliminar dos documentos."),
            ("PARECER JURÍDICO","O parecer examina a questão jurídica necessária para orientar a decisão administrativa."),
            ("CONTROLE DE PRAZO E CIÊNCIA","O processo registra prazo para manifestação complementar e ciência do interessado."),
            ("DECISÃO ADMINISTRATIVA","A autoridade DECIDE o pedido com motivação e determina as providências administrativas subsequentes.")
        ]
    }
}

def _render_model_pdf(module,case):
    pages=case["pages"]
    buf=io.BytesIO()
    cnv=canvas.Canvas(buf,pagesize=A4)
    for idx,(title,body) in enumerate(pages,start=1):
        cnv.setFont("Helvetica-Bold",14)
        cnv.drawString(52,790,title)
        cnv.setFont("Helvetica",10)
        _demo_wrap(cnv,body)
        cnv.setFont("Helvetica-Bold",8)
        cnv.drawString(52,35,"FISCALIZA.AI · PROCESSO MODELO FICTÍCIO · "+case["title"])
        cnv.setFont("Helvetica",8)
        cnv.drawRightString(545,35,"Página %d de %d" % (idx,len(pages)))
        cnv.showPage()
    cnv.save();buf.seek(0)
    filename="Processo-Modelo-"+module+"-FiscalizaAI.pdf"
    return StreamingResponse(buf,media_type="application/pdf",headers={"Content-Disposition":"inline; filename="+filename})

def demo_pdf_v62(module:str="penalizacao"):
    module=module if module in MODULES else "penalizacao"
    if module=="penalizacao":
        return _penalizacao_demo_pdf_v51()
    return _render_model_pdf(module,MODEL_CASES[module])

app.router.routes=[
    r for r in app.router.routes
    if not (getattr(r,"path",None)=="/api/demo-pdf" and "GET" in getattr(r,"methods",set()))
]
app.add_api_route("/api/demo-pdf",demo_pdf_v62,methods=["GET"])
app.version="6.2"

# UI: cada módulo passa a ter um processo modelo testável.
HTML=HTML.replace(
    '<div class="module-selected">Módulo ativo: <strong id="moduleActiveLabel">Penalização contratual</strong><span>Você pode trocar antes de analisar.</span></div>',
    '<div class="module-selected"><span>Módulo ativo: <strong id="moduleActiveLabel">Penalização contratual</strong></span><button class="btn btn-blue" onclick="testarDemo()">Testar processo modelo deste módulo →</button></div>',
    1
)

HTML=HTML.replace(
    'var r=await fetch("/api/demo-pdf");',
    'var r=await fetch("/api/demo-pdf?module="+encodeURIComponent(selectedModule));',
    1
)
HTML=HTML.replace(
    'var file=new File([blob],"Processo-Demonstrativo-FiscalizaAI.pdf",{type:"application/pdf"});',
    'var file=new File([blob],"Processo-Modelo-"+selectedModule+"-FiscalizaAI.pdf",{type:"application/pdf"});',
    1
)
HTML=HTML.replace(
    '''demoMode=true;
    selectedModule="penalizacao";
    var mc=document.querySelector('.module-card[data-module="penalizacao"]');if(mc)selecionarModulo("penalizacao",mc);
    await analisar();''',
    '''demoMode=true;
    await analisar();''',
    1
)

HTML=HTML.replace(
    "Carregue um processo modelo inteiramente fictício, com contratação, cobrança, justificativa, instauração, notificação, defesa, pareceres e decisão final. O sistema executa a mesma análise usada para qualquer PDF enviado.",
    "Escolha um módulo e carregue um processo modelo inteiramente fictício preparado para aquele fluxo. O sistema executa a mesma análise usada para qualquer PDF enviado.",
    1
)
HTML=HTML.replace(
    "<span>18 páginas</span><span>ciclo completo</span><span>dados fictícios</span>",
    "<span>13 módulos</span><span>modelos completos</span><span>dados fictícios</span>",
    1
)
HTML=HTML.replace(
    "Testar processo modelo →",
    "Testar modelo do módulo ativo →",
    1
)
HTML=HTML.replace("VERSÃO 6.1 · PLATAFORMA MODULAR","VERSÃO 6.2 · MODELOS POR MÓDULO")


# --- Navegação em abas do navegador v6.3 ---
# Cada módulo passa a abrir em uma nova aba, mantendo a tela inicial disponível.
for _mk in MODULES.keys():
    HTML = HTML.replace(
        "onclick=\"selecionarModulo('"+_mk+"',this)\"",
        "onclick=\"abrirModulo('"+_mk+"')\""
    )

_tab_js = r"""
function abrirModulo(key){
  if(!moduleLabels[key])return;
  var u=new URL(window.location.href);
  u.searchParams.set("module",key);
  u.searchParams.delete("utm_source");
  var w=window.open(u.toString(),"_blank","noopener");
  if(!w){ window.location.href=u.toString(); }
}
function aplicarModuloDaURL(){
  var key=new URLSearchParams(window.location.search).get("module");
  if(!key || !moduleLabels[key])return;
  selectedModule=key;
  document.querySelectorAll(".module-card").forEach(function(x){
    x.classList.toggle("active",x.getAttribute("data-module")===key);
  });
  var lab=document.getElementById("moduleActiveLabel");
  if(lab)lab.textContent=moduleLabels[key];
  document.title="Fiscaliza.AI · "+moduleLabels[key];
  var box=document.querySelector(".module-selected");
  if(box){
    var btn=box.querySelector("button");
    box.innerHTML='<span>Aba atual: <strong id="moduleActiveLabel">'+esc(moduleLabels[key])+'</strong></span><span style="margin-left:auto">Os demais módulos abrem em novas abas.</span>';
    if(btn)box.appendChild(btn);
  }
}
document.addEventListener("DOMContentLoaded",aplicarModuloDaURL);
"""
HTML = HTML.replace("</script>", _tab_js + "\n</script>", 1)

HTML = HTML.replace(
    "A leitura documental é comum a todos os módulos; checklist, pendências e próximo passo se adaptam ao procedimento selecionado.",
    "Escolha um módulo. Ele será aberto em uma nova aba do navegador, mantendo esta tela inicial disponível. Checklist, pendências e próximo passo se adaptam ao procedimento."
)

HTML = HTML.replace("VERSÃO 6.2 · MODELOS POR MÓDULO","VERSÃO 6.3 · MÓDULOS EM ABAS")


# --- Navegação em camadas / telas internas v6.4 ---
# Corrige a interpretação anterior: os módulos NÃO abrem novas abas do navegador.
# A aplicação passa a funcionar como um sistema convencional: seleção -> área do módulo -> análise.

for _mk in MODULES.keys():
    HTML = HTML.replace(
        "onclick=\"abrirModulo('"+_mk+"')\"",
        "onclick=\"abrirTelaModulo('"+_mk+"',this)\""
    )
    HTML = HTML.replace(
        "onclick=\"selecionarModulo('"+_mk+"',this)\"",
        "onclick=\"abrirTelaModulo('"+_mk+"',this)\""
    )

_layer_css = """
.app-screen{display:none}.app-screen.active{display:block}
.screen-home .hero{margin-bottom:18px}
.workspace-head{background:#fff;border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);padding:18px 22px;margin-bottom:18px;display:flex;align-items:center;justify-content:space-between;gap:18px}
.workspace-left{display:flex;align-items:center;gap:14px}.workspace-back{border:1px solid var(--line);background:#fff;color:var(--navy);border-radius:10px;padding:9px 12px;font-weight:800;cursor:pointer}
.workspace-back:hover{background:#f8fafc}.workspace-title small{display:block;color:var(--teal);font-size:9px;font-weight:900;text-transform:uppercase;letter-spacing:.11em}
.workspace-title strong{display:block;color:var(--navy);font-size:18px;margin-top:2px}.workspace-title span{display:block;color:var(--muted);font-size:10px;margin-top:2px}
.workspace-chip{border:1px solid #b8d8d2;background:var(--teal-soft);color:var(--teal);padding:7px 10px;border-radius:999px;font-size:9px;font-weight:900}
.module-panel .module-selected{display:none}
.home-intro{background:#fff;border:1px solid var(--line);border-radius:14px;padding:13px 16px;margin:0 0 14px;color:var(--muted);font-size:11px}
.home-intro b{color:var(--navy)}
@media(max-width:760px){.workspace-head{align-items:flex-start;flex-direction:column}.workspace-left{align-items:flex-start}.workspace-chip{align-self:flex-start}}
"""
HTML=HTML.replace("</style>",_layer_css+"</style>",1)

_layer_js = r"""
var _layersReady=false;

function configurarCamadas(){
  if(_layersReady)return;
  var main=document.querySelector("main.shell");
  var modulePanel=document.querySelector(".module-panel");
  var hero=document.querySelector(".hero");
  if(!main||!modulePanel||!hero)return;

  var home=document.createElement("div");
  home.id="screenHome";home.className="app-screen screen-home active";

  var intro=document.createElement("div");
  intro.className="home-intro";
  intro.innerHTML="<b>1. Escolha o tipo de processo.</b> Na próxima tela aparecerão somente as ferramentas e o fluxo de trabalho do módulo selecionado.";
  home.appendChild(intro);

  var workspace=document.createElement("div");
  workspace.id="screenWorkspace";workspace.className="app-screen screen-workspace";

  var wh=document.createElement("div");
  wh.className="workspace-head";
  wh.innerHTML='<div class="workspace-left"><button class="workspace-back" onclick="voltarAosModulos()">← Módulos</button><div class="workspace-title"><small>Módulo selecionado</small><strong id="workspaceModuleTitle">Penalização contratual</strong><span id="workspaceModuleDesc">Responsabilização, defesa, sanção e decisão.</span></div></div><div class="workspace-chip">Área de trabalho</div>';
  workspace.appendChild(wh);

  // Insere as telas antes dos elementos atuais.
  main.insertBefore(home,main.firstChild);
  main.insertBefore(workspace,home.nextSibling);

  // Tela 1: identidade + seleção de módulo.
  home.appendChild(hero);
  home.appendChild(modulePanel);

  // Tela 2: todo o restante do fluxo operacional.
  Array.from(main.children).forEach(function(el){
    if(el!==home && el!==workspace)workspace.appendChild(el);
  });

  _layersReady=true;

  // Se alguém chegar por URL antiga com ?module=, abre a tela interna, sem nova aba.
  var q=new URLSearchParams(window.location.search).get("module");
  if(q&&moduleLabels[q]){
    abrirTelaModulo(q,null,false);
  }else{
    history.replaceState({screen:"home"},"",window.location.pathname);
  }
}

function aplicarContextoDoModulo(key){
  var label=moduleLabels[key]||key;
  var descMap={
    penalizacao:"Responsabilização de fornecedor, contraditório, defesa, sanção e decisão.",
    fiscalizacao:"Execução, entregas, ocorrências, fiscalização, medições e providências.",
    reequilibrio:"Pedido, fatos supervenientes, custos, pareceres e decisão.",
    rescisao:"Motivação, comunicação, contraditório, parecer e decisão de extinção.",
    disciplinar:"Instauração, citação, instrução, defesa, relatório e julgamento.",
    sindicancia:"Fato investigado, diligências, provas, relatório e encaminhamento.",
    lai:"Pedido, protocolo, prazo, resposta, recurso e transparência.",
    prestacao:"Instrumento, plano, execução, comprovação, análise e decisão.",
    licitacoes:"Edital, termo de referência, habilitação, propostas e homologação.",
    cobranca:"Origem do débito, memória de cálculo, notificação e manifestação.",
    servidores:"Requerimentos funcionais, RH, documentos, pareceres e decisão.",
    tributario:"Lançamento, ciência, impugnação, recurso e julgamento.",
    geral:"Cronologia, peças, evidências, divergências e decisão."
  };
  var t=document.getElementById("workspaceModuleTitle");if(t)t.textContent=label;
  var d=document.getElementById("workspaceModuleDesc");if(d)d.textContent=descMap[key]||"Análise administrativa assistida.";
  document.title="Fiscaliza.AI · "+label;

  // A minuta institucional específica de penalização só aparece no módulo correspondente.
  document.querySelectorAll("section.panel").forEach(function(p){
    var tx=(p.textContent||"").toLowerCase();
    if(tx.indexOf("notificação institucional com preenchimento validado")>=0){
      p.style.display=(key==="penalizacao")?"":"none";
    }
  });

  // No fluxo documental, ajusta a ênfase sem esconder recursos genéricos.
  var chain=document.querySelector(".doc-chain");
  if(chain){
    Array.from(chain.querySelectorAll("button")).forEach(function(b){
      if((b.textContent||"").toLowerCase().indexOf("notificação")>=0){
        b.style.display=(key==="penalizacao"||key==="fiscalizacao"||key==="rescisao"||key==="cobranca")?"":"none";
      }else if((b.textContent||"").toLowerCase().indexOf("intimação")>=0){
        b.style.display=(key==="penalizacao"||key==="disciplinar"||key==="tributario")?"":"none";
      }else{
        b.style.display="";
      }
    });
  }
}

function abrirTelaModulo(key,el,push){
  if(!moduleLabels[key])return;
  selectedModule=key;
  document.querySelectorAll(".module-card").forEach(function(x){x.classList.toggle("active",x.getAttribute("data-module")===key)});
  aplicarContextoDoModulo(key);

  var home=document.getElementById("screenHome"),work=document.getElementById("screenWorkspace");
  if(home)home.classList.remove("active");
  if(work)work.classList.add("active");

  if(push!==false){
    var u=new URL(window.location.href);
    u.searchParams.set("module",key);
    u.searchParams.delete("utm_source");
    history.pushState({screen:"module",module:key},"",u.pathname+u.search);
  }
  window.scrollTo({top:0,behavior:"smooth"});
}

function voltarAosModulos(push){
  var home=document.getElementById("screenHome"),work=document.getElementById("screenWorkspace");
  if(work)work.classList.remove("active");
  if(home)home.classList.add("active");
  document.title="Fiscaliza.AI Municipal";
  if(push!==false){
    history.pushState({screen:"home"},"",window.location.pathname);
  }
  window.scrollTo({top:0,behavior:"smooth"});
}

window.abrirModulo=abrirTelaModulo;

window.addEventListener("popstate",function(e){
  var q=new URLSearchParams(window.location.search).get("module");
  if(q&&moduleLabels[q])abrirTelaModulo(q,null,false);
  else voltarAosModulos(false);
});

document.addEventListener("DOMContentLoaded",configurarCamadas);
"""
HTML=HTML.replace("</script>",_layer_js+"\n</script>",1)

HTML=HTML.replace(
    "Escolha um módulo. Ele será aberto em uma nova aba do navegador, mantendo esta tela inicial disponível. Checklist, pendências e próximo passo se adaptam ao procedimento.",
    "Escolha um módulo para entrar na área de trabalho correspondente. A próxima tela mostrará o fluxo, os controles e as ferramentas daquele tipo de processo."
)

HTML=HTML.replace("VERSÃO 6.3 · MÓDULOS EM ABAS","VERSÃO 6.4 · NAVEGAÇÃO EM CAMADAS")


# --- Tela inicial exclusiva de seleção v6.5 ---
# A primeira camada mostra SOMENTE a escolha do módulo.
# O painel operacional só existe visualmente após a seleção.

_layer2_css = """
.screen-home{min-height:calc(100vh - 170px);display:none}
.screen-home.active{display:flex;flex-direction:column;justify-content:flex-start}
.screen-home .module-panel{margin-top:0}
.screen-home .home-intro{margin-bottom:14px}
.screen-home .module-grid{margin-top:6px}
.screen-workspace{display:none}
.screen-workspace.active{display:block}
.screen-workspace .hero{display:none!important}
.module-panel.home-only{box-shadow:var(--shadow)}
.home-welcome{padding:8px 0 18px}
.home-welcome .kicker{margin-bottom:5px}
.home-welcome h1{margin:0;color:var(--navy);font-size:30px;line-height:1.12;letter-spacing:-.6px}
.home-welcome p{margin:8px 0 0;color:var(--muted);font-size:12px;max-width:760px}
@media(max-width:760px){.home-welcome h1{font-size:24px}}
"""
HTML=HTML.replace("</style>",_layer2_css+"</style>",1)

_layer2_js = r"""
function configurarCamadas(){
  if(_layersReady)return;
  var main=document.querySelector("main.shell");
  var modulePanel=document.querySelector(".module-panel");
  var hero=document.querySelector(".hero");
  if(!main||!modulePanel)return;

  var home=document.createElement("div");
  home.id="screenHome";
  home.className="app-screen screen-home active";

  var welcome=document.createElement("div");
  welcome.className="home-welcome";
  welcome.innerHTML='<div class="kicker">Fiscaliza.AI Municipal</div><h1>O que você deseja analisar?</h1><p>Escolha o tipo de processo. Depois da seleção, o sistema abre uma nova tela interna com apenas o fluxo e as ferramentas daquele módulo.</p>';
  home.appendChild(welcome);

  var workspace=document.createElement("div");
  workspace.id="screenWorkspace";
  workspace.className="app-screen screen-workspace";

  var wh=document.createElement("div");
  wh.className="workspace-head";
  wh.innerHTML='<div class="workspace-left"><button class="workspace-back" onclick="voltarAosModulos()">← Voltar aos módulos</button><div class="workspace-title"><small>Área de trabalho</small><strong id="workspaceModuleTitle">Penalização contratual</strong><span id="workspaceModuleDesc">Responsabilização, defesa, sanção e decisão.</span></div></div><div class="workspace-chip">Módulo ativo</div>';
  workspace.appendChild(wh);

  main.insertBefore(home,main.firstChild);
  main.insertBefore(workspace,home.nextSibling);

  // A tela inicial recebe SOMENTE a seleção dos módulos.
  modulePanel.classList.add("home-only");
  home.appendChild(modulePanel);

  // O antigo banner institucional não integra mais a primeira tela.
  if(hero){hero.remove();}

  // Todo o restante pertence exclusivamente à tela de trabalho.
  Array.from(main.children).forEach(function(el){
    if(el!==home && el!==workspace)workspace.appendChild(el);
  });

  _layersReady=true;

  var q=new URLSearchParams(window.location.search).get("module");
  if(q&&moduleLabels[q]){
    abrirTelaModulo(q,null,false);
  }else{
    history.replaceState({screen:"home"},"",window.location.pathname);
  }
}
"""
# Substitui a implementação v6.4 de configurarCamadas por esta versão.
_start=HTML.find("function configurarCamadas(){")
_end=HTML.find("\nfunction aplicarContextoDoModulo",_start)
if _start!=-1 and _end!=-1:
    HTML=HTML[:_start]+_layer2_js+HTML[_end:]

HTML=HTML.replace("VERSÃO 6.4 · NAVEGAÇÃO EM CAMADAS","VERSÃO 6.5 · TELAS INTERNAS")


# --- Auditoria específica por módulo v6.6 ---
# Corrige a matriz, cronologia, estrutura e rastreabilidade para que cada módulo
# mostre apenas perguntas e evidências próprias do procedimento selecionado.

MODULE_AUDIT = {
    "fiscalizacao":[
        ("Há instrumento contratual?",[r"\bcontrato\b",r"\binstrumento contratual\b"]),
        ("Há designação de fiscal ou gestor?",[r"designad[oa].{0,80}fiscal",r"\bfiscal do contrato\b",r"\bgestor do contrato\b"]),
        ("Há relatório de execução/fiscalização?",[r"relatorio.{0,80}(?:execucao|fiscalizacao)",r"\bfiscalizacao registra\b"]),
        ("Há entrega, medição ou recebimento?",[r"\bentrega\b",r"\bmedicao\b",r"\brecebimento\b"]),
        ("Há ocorrência ou comunicação à contratada?",[r"\bnotificacao\b",r"\bocorrencia\b",r"\bcomunicacao\b"]),
        ("Há providência ou regularização registrada?",[r"\bprovidencia\b",r"\bregulariza",r"\bcorrecao\b"])
    ],
    "reequilibrio":[
        ("Há pedido formal de reequilíbrio?",[r"pedido.{0,80}reequilibr",r"\breequilibrio economico"]),
        ("Há contrato ou instrumento vinculado?",[r"\bcontrato\b",r"\binstrumento contratual\b"]),
        ("Há planilha, orçamento ou cotações?",[r"\bplanilha\b",r"\borcamento\b",r"\bcotac"]),
        ("Há fato superveniente ou justificativa econômica?",[r"\bfato superveniente\b",r"\bdesequilibr",r"\baumento extraordinario\b"]),
        ("Há análise técnica ou jurídica?",[r"\bnota tecnica\b",r"\bparecer juridico\b",r"\banalise tecnica\b"]),
        ("Há decisão sobre o pedido?",[r"\bdecisao administrativa\b",r"\bdecide\b",r"\bdeferir\b",r"\bindefere"])
    ],
    "rescisao":[
        ("Há contrato ou instrumento a extinguir?",[r"\bcontrato\b",r"\binstrumento contratual\b"]),
        ("A motivação da rescisão/extinção está registrada?",[r"\brescis",r"\bextinc",r"\bmotiva"]),
        ("Houve notificação ou ciência da contratada?",[r"\bnotificacao\b",r"\bciencia\b"]),
        ("Há manifestação ou defesa da contratada?",[r"\bdefesa\b",r"\bmanifestacao da contratada\b"]),
        ("Há parecer jurídico?",[r"\bparecer juridico\b"]),
        ("Há decisão de rescisão/extinção?",[r"decisao.{0,80}(?:rescis|extinc)",r"\bdecide.{0,120}(?:rescis|extinc)"])
    ],
    "disciplinar":[
        ("Há portaria ou ato de instauração?",[r"\bportaria de instaur",r"\bato de instaur",r"\bprocesso administrativo disciplinar\b"]),
        ("Há citação ou notificação do servidor?",[r"\bcitacao\b",r"\bnotificacao.{0,80}servidor\b"]),
        ("Há instrução e produção de provas?",[r"\binstrucao\b",r"\bproducao de provas\b",r"\bdepoimento\b"]),
        ("Há defesa administrativa?",[r"\bdefesa administrativa\b",r"\bdefesa escrita\b"]),
        ("Há relatório da comissão?",[r"\brelatorio da comissao\b",r"\brelatorio conclusivo\b"]),
        ("Há julgamento ou decisão?",[r"\bdecisao de julgamento\b",r"\bjulgamento\b",r"\bdecide\b"])
    ],
    "sindicancia":[
        ("Há ato de instauração da sindicância?",[r"\bsindicancia administrativa\b",r"\bato de instauracao\b",r"\binstauracao da sindicancia\b"]),
        ("O fato investigado está descrito?",[r"\bfato ocorrido\b",r"\bfato investigado\b",r"\bdescricao do fato\b",r"\bdescreve o fato\b"]),
        ("Há diligências ou depoimentos?",[r"\bdiligencia\b",r"\bdepoimento\b"]),
        ("Há documentos ou provas reunidas?",[r"\bprovas\b",r"\bdocumentos\b"]),
        ("Há relatório conclusivo?",[r"\brelatorio conclusivo\b",r"\brelatorio final\b"]),
        ("Há decisão ou encaminhamento?",[r"\bdecisao\b",r"\bencaminha\b",r"\barquivamento\b"])
    ],
    "lai":[
        ("Há pedido/protocolo de acesso à informação?",[r"pedido.{0,80}acesso.{0,80}informacao",r"\bprotocolo\b"]),
        ("O órgão responsável está identificado?",[r"\bouvidoria\b",r"\borgao responsavel\b",r"\bunidade responsavel\b"]),
        ("Há controle de prazo de resposta?",[r"\bprazo\b",r"\bdata limite\b"]),
        ("Há resposta ao requerente?",[r"\bresposta ao pedido\b",r"\borgao apresenta resposta\b"]),
        ("Há recurso?",[r"\brecurso\b"]),
        ("Há decisão do recurso ou resposta final?",[r"\bdecisao do recurso\b",r"\bdecide o recurso\b",r"\bresposta final\b"])
    ],
    "prestacao":[
        ("Há convênio ou instrumento equivalente?",[r"\bconvenio\b",r"\btermo de fomento\b",r"\btermo de colaboracao\b"]),
        ("Há plano de trabalho?",[r"\bplano de trabalho\b"]),
        ("Há comprovação da execução do objeto?",[r"\bexecucao do objeto\b",r"\brelatorio de execucao\b"]),
        ("Há prestação de contas e comprovantes?",[r"\bprestacao de contas\b",r"\bnotas fiscais\b",r"\bcomprovantes de pagamento\b"]),
        ("Há análise técnica/financeira?",[r"\banalise tecnica\b",r"\banalise financeira\b"]),
        ("Há decisão de aprovação/rejeição?",[r"\bdecisao de aprovacao\b",r"\baprovacao da prestacao\b",r"\brejeicao\b"])
    ],
    "licitacoes":[
        ("Há edital ou aviso do certame?",[r"\bedital\b",r"\baviso de licitacao\b"]),
        ("Há termo de referência?",[r"\btermo de referencia\b"]),
        ("Há propostas e habilitação?",[r"\bpropostas\b",r"\bhabilitacao\b"]),
        ("Há ata da sessão?",[r"\bata da sessao\b",r"\bsessao publica\b"]),
        ("Há parecer jurídico?",[r"\bparecer juridico\b"]),
        ("Há adjudicação e/ou homologação?",[r"\badjudic",r"\bhomolog"])
    ],
    "cobranca":[
        ("A origem do débito está demonstrada?",[r"\borigem do debito\b",r"\bfato gerador do debito\b"]),
        ("Há memória de cálculo?",[r"\bmemoria de calculo\b"]),
        ("Houve notificação de cobrança?",[r"\bnotificacao de cobranca\b"]),
        ("Há comprovação de ciência?",[r"\bcomprovante de ciencia\b",r"\bconfirmacao de ciencia\b"]),
        ("Há manifestação do interessado?",[r"\bmanifestacao do interessado\b",r"\bcontesta\b"]),
        ("Há decisão/providência sobre a cobrança?",[r"\bdecisao administrativa\b",r"\bmant[eé]m a cobranca\b",r"\bretificar parcialmente\b"])
    ],
    "servidores":[
        ("Há requerimento do servidor?",[r"\brequerimento\b",r"\bservidor.{0,80}requer\b"]),
        ("Há documentos funcionais?",[r"\bdocumentos funcionais\b",r"\bficha funcional\b",r"\bregistros de exercicio\b"]),
        ("Há manifestação do RH?",[r"\brecursos humanos\b",r"\bsetor de rh\b"]),
        ("Há parecer técnico/jurídico?",[r"\bparecer juridico\b",r"\bparecer tecnico\b"]),
        ("Há ciência do interessado?",[r"\bciencia da interessada\b",r"\bciencia do interessado\b"]),
        ("Há decisão sobre o requerimento?",[r"\bdecisao administrativa\b",r"\bdecide o requerimento\b"])
    ],
    "tributario":[
        ("Há lançamento ou auto tributário?",[r"\blancamento tributario\b",r"\bauto\b.{0,80}\btribut"]),
        ("Há ciência do contribuinte?",[r"\bciencia do contribuinte\b",r"\bcomprovante de ciencia\b"]),
        ("Há impugnação?",[r"\bimpugnacao\b"]),
        ("Há instrução e provas?",[r"\binstrucao e provas\b",r"\bprova documental\b",r"\bmemoria de calculo\b"]),
        ("Há decisão de primeira instância?",[r"\bdecisao de primeira instancia\b",r"\bdecide a impugnacao\b"]),
        ("Há recurso administrativo?",[r"\brecurso administrativo\b"])
    ],
    "geral":[
        ("O processo/protocolo está identificado?",[r"\bprocesso administrativo\b",r"\bprotocolo\b"]),
        ("Há pedido ou documento de origem?",[r"\bpedido\b",r"\brequerimento\b",r"\bdocumento de origem\b"]),
        ("Há manifestação do interessado?",[r"\bmanifestacao\b",r"\binteressado\b"]),
        ("Há análise técnica ou parecer?",[r"\banalise tecnica\b",r"\bparecer\b",r"\binformacao tecnica\b"]),
        ("Há prazo/ciência registrado?",[r"\bprazo\b",r"\bciencia\b"]),
        ("Há decisão ou encaminhamento?",[r"\bdecisao\b",r"\bdecide\b",r"\bencaminha\b"])
    ]
}

def _module_pattern_hits(pages, patterns):
    hits=[]
    compiled=[re.compile(p,re.I) for p in patterns]
    for p in pages:
        z=norm(p.get("text") or "")
        if any(rx.search(z) for rx in compiled):
            hits.append(p["page"])
    return sorted(set(hits))

def _module_evidence_excerpt(pages, hit_pages, patterns):
    compiled=[re.compile(p,re.I) for p in patterns]
    for p in pages:
        if p["page"] not in hit_pages:
            continue
        raw=re.sub(r"\s+"," ",p.get("text") or "").strip()
        for sent in re.split(r"(?<=[.!?;:])\s+",raw):
            z=norm(sent)
            if any(rx.search(z) for rx in compiled) and len(sent)>=25:
                return clip(sent,300)
        return clip(raw,300)
    return ""

_old_module_overlay_v66 = _module_overlay
def _module_overlay(pages,a,module):
    module=module if module in MODULES else "geral"
    if module=="penalizacao":
        a=_old_module_overlay_v66(pages,a,module)
        a["module_matrix"]=[
            {"question":"Há contrato ou instrumento equivalente?","answer":"Sim" if a.get("has",{}).get("contrato") else "Não identificado","ok":bool(a.get("has",{}).get("contrato")),"pages":_pages_for_type(a,"contrato")},
            {"question":"Houve notificação/intimação?","answer":"Sim" if (a.get("has",{}).get("notificacao") or a.get("has",{}).get("intimacao")) else "Não identificado","ok":bool(a.get("has",{}).get("notificacao") or a.get("has",{}).get("intimacao")),"pages":sorted(set(_pages_for_type(a,"notificacao")+_pages_for_type(a,"intimacao")))},
            {"question":"Há defesa administrativa?","answer":"Sim" if a.get("has",{}).get("defesa") else "Não identificado","ok":bool(a.get("has",{}).get("defesa")),"pages":_pages_for_type(a,"defesa")},
            {"question":"Há decisão?","answer":"Sim" if a.get("has",{}).get("decisao") else "Não identificado","ok":bool(a.get("has",{}).get("decisao")),"pages":_pages_for_type(a,"decisao")},
            {"question":"Quantidade total?","answer":str(a.get("quantity",{}).get("value","Não identificada com segurança")),"ok":"nao identificado" not in norm(str(a.get("quantity",{}).get("value",""))),"pages":[a.get("quantity",{}).get("source",{}).get("page")] if a.get("quantity",{}).get("source") else []}
        ]
        return a

    info=MODULES[module]
    rules=MODULE_AUDIT.get(module,MODULE_AUDIT["geral"])
    matrix=[]; timeline=[]; evidence=[]
    for question,patterns in rules:
        pgs=_module_pattern_hits(pages,patterns)
        label=question
        if label.startswith("Há "): label=label[3:]
        elif label.startswith("Houve "): label=label[6:]
        elif label.startswith("O "): label=label[2:]
        elif label.startswith("A "): label=label[2:]
        label=label.rstrip("?")
        ex=_module_evidence_excerpt(pages,pgs,patterns) if pgs else ""
        row={"question":question,"answer":"Localizado" if pgs else "Não identificado","ok":bool(pgs),"pages":pgs[:8],"label":label,"excerpt":ex}
        matrix.append(row)
        if pgs:
            timeline.append({"label":label,"pages":pgs[:4]})
            evidence.append({"label":label,"page":pgs[0],"text":ex})

    a["module_key"]=module
    a["module_label"]=info["label"]
    a["module_desc"]=info["desc"]
    a["module_matrix"]=matrix
    a["module_timeline"]=timeline
    a["module_evidence"]=evidence
    a["process_checklist"]=[{"label":x["label"],"ok":x["ok"],"pages":x["pages"]} for x in matrix]
    a["module_summary"]=[
        {"label":x["label"],"ok":x["ok"],"value":"Localizado" if x["ok"] else "Conferir"}
        for x in matrix[:4]
    ]

    missing=[x for x in matrix if not x["ok"]]
    present=[x for x in matrix if x["ok"]]
    a["review_flags"]=[{"level":"media","text":"Não identificado com segurança: "+x["label"]+"."} for x in missing[:5]]
    if missing:
        a["next_action"]={
            "stage":"Instrução do módulo "+info["short"],
            "action":"Conferir ou localizar: "+missing[0]["label"]+".",
            "why":"Foram localizados "+str(len(present))+" de "+str(len(matrix))+" controles essenciais previstos para este tipo de processo."
        }
    else:
        a["next_action"]={
            "stage":"Controles essenciais localizados",
            "action":"Revisar a coerência entre os documentos, os fatos e a conclusão/encaminhamento antes de finalizar o processo.",
            "why":"Todos os controles básicos do módulo "+info["short"]+" foram localizados automaticamente."
        }

    a["traceability"]=[
        {"claim":x["label"],"status":"Evidência localizada","source":pages[x["page"]-1]["file"] if x["page"] and x["page"]<=len(pages) else "Processo","pages":[x["page"]]}
        for x in evidence
    ]
    a["metrics"]["checklist_ok"]=len(present)
    a["metrics"]["checklist_total"]=len(matrix)
    a["metrics"]["pieces"]=len(present)
    a["conclusion"]="Modo "+info["label"]+": foram localizados "+str(len(present))+" de "+str(len(matrix))+" controles essenciais. A análise abaixo utiliza somente critérios próprios deste módulo."
    return a

def _module_process_number(pages,module):
    joined="\n".join(p.get("text") or "" for p in pages)
    pats={
        "sindicancia":[r"Sindic[aâ]ncia Administrativa\s*n[ºo.]?\s*([0-9.\-\/]+)"],
        "disciplinar":[r"Processo Administrativo Disciplinar\s*n[ºo.]?\s*([0-9.\-\/]+)"],
        "tributario":[r"Processo Tribut[aá]rio\s*n[ºo.]?\s*([0-9.\-\/]+)"],
        "fiscalizacao":[r"Processo de Fiscaliza[cç][aã]o Contratual\s*n[ºo.]?\s*([0-9.\-\/]+)"],
        "reequilibrio":[r"Processo de Reequil[ií]brio\s*n[ºo.]?\s*([0-9.\-\/]+)"],
        "rescisao":[r"Processo de Extin[cç][aã]o Contratual\s*n[ºo.]?\s*([0-9.\-\/]+)"],
        "cobranca":[r"Processo de Cobran[cç]a Administrativa\s*n[ºo.]?\s*([0-9.\-\/]+)"],
        "servidores":[r"Processo Funcional\s*n[ºo.]?\s*([0-9.\-\/]+)"],
        "prestacao":[r"Processo de Presta[cç][aã]o de Contas\s*n[ºo.]?\s*([0-9.\-\/]+)"],
        "licitacoes":[r"Processo Licitat[oó]rio\s*n[ºo.]?\s*([0-9.\-\/]+)"],
        "lai":[r"Pedido de Acesso [àa] Informa[cç][aã]o\s*n[ºo.]?\s*([0-9.\-\/]+)"],
        "geral":[r"Processo Administrativo\s*n[ºo.]?\s*([0-9.\-\/]+)"]
    }
    return _first_match(joined,pats.get(module,[r"Processo\s*n[ºo.]?\s*([0-9.\-\/]+)"]),default="[NÚMERO DO PROCESSO — CONFERIR]")

_old_generic_document_draft_v66 = _generic_document_draft
def _generic_document_draft(item,kind):
    module=item.get("module","penalizacao")
    if module=="penalizacao":
        return _old_generic_document_draft_v66(item,kind)

    pages=item["pages"]
    a=_module_overlay(pages,analyze_pages(pages),module)
    info=MODULES.get(module,MODULES["geral"])
    proc=_module_process_number(pages,module)
    ev=a.get("module_evidence",[])
    fact_text=" ".join(x["text"] for x in ev[:4] if x.get("text")) or "[SÍNTESE DOS ELEMENTOS LOCALIZADOS — CONFERIR AUTOS]"
    missing=[x["label"] for x in a.get("module_matrix",[]) if not x["ok"]]

    titles={
        "despacho":"MINUTA — DESPACHO",
        "notificacao":"MINUTA — NOTIFICAÇÃO",
        "intimacao":"MINUTA — INTIMAÇÃO",
        "diligencia":"MINUTA — DESPACHO DE DILIGÊNCIA",
        "relatorio":"MINUTA — RELATÓRIO CONCLUSIVO",
        "decisao":"MINUTA — DECISÃO ADMINISTRATIVA"
    }
    if kind not in titles:
        raise HTTPException(400,"Tipo de minuta não suportado.")

    lines=[
        titles[kind],"",
        "Módulo: "+info["label"],
        "Processo: nº "+proc,""
    ]
    if kind=="diligencia":
        lines += [
            "Considerando os elementos constantes dos autos e a necessidade de completar a instrução, determino a realização das seguintes diligências:","",
            "1. "+(missing[0] if missing else "[INDICAR DILIGÊNCIA NECESSÁRIA]")+";",
            "2. [INDICAR RESPONSÁVEL/UNIDADE];",
            "3. [INDICAR PRAZO E FORMA DE CUMPRIMENTO].","",
            "Elementos já localizados: "+fact_text
        ]
    elif kind=="relatorio":
        lines += [
            "I — SÍNTESE DO PROCESSO","",fact_text,"",
            "II — CONTROLES DO MÓDULO",""
        ]
        for row in a.get("module_matrix",[]):
            lines.append("- "+row["label"]+": "+("localizado" if row["ok"] else "não identificado com segurança"))
        lines += ["","III — ANÁLISE","[CONFRONTAR OS DOCUMENTOS, AS MANIFESTAÇÕES E AS PROVAS PERTINENTES AO MÓDULO.]","",
                  "IV — CONCLUSÃO","[INSERIR CONCLUSÃO APÓS REVISÃO HUMANA INTEGRAL DOS AUTOS]."]
    elif kind=="decisao":
        lines += [
            "Vistos e examinados os autos.","",
            "Considero os seguintes elementos extraídos para conferência: "+fact_text,"",
            "DECIDO:","[A AUTORIDADE COMPETENTE DEVERÁ PREENCHER A CONCLUSÃO E AS PROVIDÊNCIAS APÓS REVISÃO INTEGRAL DOS AUTOS]."
        ]
    elif kind=="notificacao":
        lines += [
            "Fica o interessado NOTIFICADO acerca dos fatos e documentos relacionados ao processo acima indicado.","",
            "Síntese para conferência: "+fact_text,"",
            "[INDICAR OBJETO DA NOTIFICAÇÃO, PRAZO, CANAL DE RESPOSTA E FUNDAMENTO APLICÁVEL]."
        ]
    elif kind=="intimacao":
        lines += [
            "Fica o interessado INTIMADO para manifestação no processo acima indicado.","",
            "Síntese para conferência: "+fact_text,"",
            "[INDICAR PRAZO, OBJETO DA MANIFESTAÇÃO E CANAL OFICIAL]."
        ]
    else:
        lines += [
            "Considerando os documentos e elementos constantes dos autos: "+fact_text,"",
            "DETERMINO:","[INSERIR PROVIDÊNCIA ADMINISTRATIVA COMPATÍVEL COM O MÓDULO "+info["label"].upper()+", APÓS REVISÃO HUMANA]."
        ]

    lines += ["","[LOCAL], [DATA].","","[RESPONSÁVEL/AUTORIDADE]","",
              "MINUTA ASSISTIDA — REVISÃO HUMANA OBRIGATÓRIA."]
    return {"draft":"\n".join(lines),"sources":["Módulo "+info["label"]+" · "+str(len(pages))+" página(s) analisadas"]}

# UI: substitui visualmente as seções genéricas por conteúdo do módulo escolhido.
_module_result_js = r"""
function acharSectionPorTitulo(titulo){
  var sections=document.querySelectorAll("#result .section");
  for(var i=0;i<sections.length;i++){
    var h2=sections[i].querySelector("h2");
    if(h2 && h2.textContent.trim()===titulo)return sections[i];
  }
  return null;
}
function ajustarResultadoModulo(a){
  if(!a||a.module_key==="penalizacao")return;

  var timeline=acharSectionPorTitulo("Linha do tempo do processo");
  if(timeline){
    var html='<div class="kicker">Cronologia do módulo</div><h2>Linha do tempo do processo</h2>';
    if(a.module_timeline&&a.module_timeline.length){
      html+='<div class="timeline">';
      for(var i=0;i<a.module_timeline.length;i++){
        var t=a.module_timeline[i];
        html+='<div class="timeline-step"><div class="tp">p. '+esc((t.pages||[]).join(", "))+'</div><b>'+esc(t.label)+'</b></div>';
      }
      html+='</div>';
    }else html+='<div class="empty">Nenhum marco específico deste módulo foi localizado com segurança.</div>';
    timeline.innerHTML=html;
  }

  var matrix=acharSectionPorTitulo("Matriz de evidências");
  if(matrix){
    var mh='<div class="kicker">Auditabilidade · '+esc(a.module_label)+'</div><h2>Matriz de evidências do módulo</h2><table class="matrix"><thead><tr><th>Questão</th><th>Resposta</th><th>Fonte</th><th>Status</th></tr></thead><tbody>';
    for(var j=0;j<(a.module_matrix||[]).length;j++){
      var r=a.module_matrix[j],src=(r.pages&&r.pages.length)?("p. "+r.pages.join(", ")):"—";
      mh+='<tr><td>'+esc(r.question)+'</td><td>'+esc(r.answer)+'</td><td>'+esc(src)+'</td><td class="'+(r.ok?'matrix-ok':'matrix-limit')+'">'+(r.ok?'Confirmado':'Conferir')+'</td></tr>';
    }
    mh+='</tbody></table>';
    matrix.innerHTML=mh;
  }

  var structure=acharSectionPorTitulo("Estrutura do processo");
  if(structure){
    var sh='<div class="kicker">Elementos essenciais · '+esc(a.module_label)+'</div><h2>Estrutura esperada do processo</h2><div class="piece-grid">';
    for(var k=0;k<(a.module_matrix||[]).length;k++){
      var m=a.module_matrix[k];
      sh+='<article class="piece"><div class="piece-top"><div class="piece-icon">'+(m.ok?'✓':'!')+'</div><div class="piece-name">'+esc(m.label)+'</div>'+(m.pages&&m.pages.length?pageChip(m.pages.join(", ")):"")+'</div><div class="source">'+(m.ok?'Evidência localizada':'Conferência necessária')+'</div></article>';
    }
    sh+='</div>';
    structure.innerHTML=sh;
  }

  var manifests=acharSectionPorTitulo("Elementos apresentados pelo interessado");
  if(manifests){
    manifests.querySelector(".kicker").textContent="Evidências do módulo";
    manifests.querySelector("h2").textContent="Elementos localizados nos autos";
    var head=manifests.querySelector(".kicker").outerHTML+manifests.querySelector("h2").outerHTML;
    var body="";
    if(!a.module_evidence||!a.module_evidence.length)body='<div class="empty">Nenhuma evidência específica do módulo foi localizada.</div>';
    else{
      for(var e=0;e<a.module_evidence.length;e++){
        var ev=a.module_evidence[e];
        body+='<div class="finding"><div class="finding-num">'+(e+1)+'</div><div><div class="finding-text"><b>'+esc(ev.label)+':</b> '+esc(ev.text||"Evidência localizada.")+'</div><div class="finding-foot">'+pageChip(ev.page)+'</div></div></div>';
      }
    }
    manifests.innerHTML=head+body;
  }

  var confront=acharSectionPorTitulo("Pontos a confrontar");
  if(confront){
    confront.querySelector(".kicker").textContent="Conferência do módulo";
    confront.querySelector("h2").textContent="Pontos para conferência";
    var ch=confront.querySelector(".kicker").outerHTML+confront.querySelector("h2").outerHTML;
    var missing=(a.module_matrix||[]).filter(function(x){return !x.ok});
    if(!missing.length)ch+='<div class="empty">Todos os controles essenciais deste módulo foram localizados. Faça a revisão de coerência antes da conclusão.</div>';
    else for(var q=0;q<missing.length;q++)ch+='<div class="warning">Conferir: '+esc(missing[q].label)+'</div>';
    confront.innerHTML=ch;
  }

  var review=acharSectionPorTitulo("Pontos antes da assinatura");
  if(review){
    var kic=review.querySelector(".kicker");if(kic)kic.textContent="Revisão do processo";
    var h=review.querySelector("h2");if(h)h.textContent="Pontos antes da conclusão";
  }
}
"""
HTML=HTML.replace("</script>",_module_result_js+"\n</script>",1)

# Chama a adaptação logo após renderizar a análise.
HTML=HTML.replace(
    'document.getElementById("result").innerHTML=h;\n  document.getElementById("result").scrollIntoView({behavior:"smooth",block:"start"});',
    'document.getElementById("result").innerHTML=h;\n  ajustarResultadoModulo(a);\n  document.getElementById("result").scrollIntoView({behavior:"smooth",block:"start"});',
    1
)

HTML=HTML.replace("VERSÃO 6.5 · TELAS INTERNAS","VERSÃO 6.6 · MÓDULOS ESPECIALIZADOS")


# --- Rastreabilidade por ID do documento v6.7 ---
# Toda evidência passa a apontar: ID interno do documento + identificador de origem (quando houver) + página.

def _document_marker(text):
    raw=text or ""
    lines=[re.sub(r"\s+"," ",x).strip() for x in raw.splitlines() if x.strip()]
    keywords=[
        "NOTIFICAÇÃO","NOTIFICACAO","INTIMAÇÃO","INTIMACAO","CONTRATO","PARECER",
        "RELATÓRIO","RELATORIO","OFÍCIO","OFICIO","DESPACHO","PORTARIA","ATA ",
        "NOTA DE EMPENHO","EMPENHO","ORDEM DE FORNECIMENTO","ORDEM DE SERVIÇO",
        "TERMO DE RECEBIMENTO","TERMO DE DILIGÊNCIA","TERMO DE DEPOIMENTO",
        "DECISÃO","DECISAO","DEFESA ADMINISTRATIVA","MANIFESTAÇÃO DA CONTRATADA",
        "MANIFESTACAO DA CONTRATADA","PEDIDO DE REEQUILÍBRIO","PEDIDO DE ACESSO",
        "PROCESSO ADMINISTRATIVO","PROCESSO TRIBUTÁRIO","PROCESSO TRIBUTARIO",
        "PROCESSO LICITATÓRIO","PROCESSO LICITATORIO","SINDICÂNCIA ADMINISTRATIVA",
        "SINDICANCIA ADMINISTRATIVA","AUTO / LANÇAMENTO","AUTO / LANCAMENTO"
    ]
    for line in lines[:10]:
        up=line.upper()
        if any(k in up for k in keywords):
            # Evita usar frases narrativas extensas como identificador.
            if len(line)<=150:
                return line

    # Identificador explícito do sistema de origem.
    pats=[
        r"(?:ID do documento|Documento ID|ID Documento)\s*[:#\-]?\s*([A-Z0-9._\/-]+)",
        r"1Doc:\s*(Protocolo\s*(?:\d+\s*-\s*)?[\d.]+\/\d{4})",
        r"\b(Protocolo\s*(?:\d+\s*-\s*)?[\d.]+\/\d{4})\b"
    ]
    flat=re.sub(r"\s+"," ",raw)
    for pat in pats:
        m=re.search(pat,flat,flags=re.I)
        if m:
            return re.sub(r"\s+"," ",m.group(1)).strip()
    return None

def _assign_document_ids(pages):
    file_order=[]
    for p in pages:
        if p["file"] not in file_order:file_order.append(p["file"])
    for fi,filename in enumerate(file_order,1):
        rows=[p for p in pages if p["file"]==filename]
        counter=0;current_id=None;current_marker=None
        for p in rows:
            marker=_document_marker(p.get("text") or "")
            if marker:
                mk=norm(marker)
                if current_id is None or mk!=norm(current_marker or ""):
                    counter+=1
                    current_id="ARQ%d-DOC%03d"%(fi,counter)
                    current_marker=marker
            elif current_id is None:
                counter+=1
                current_id="ARQ%d-DOC%03d"%(fi,counter)
                current_marker=None
            p["document_id"]=current_id
            p["source_document_id"]=current_marker
    return pages

def _page_doc_refs(pages,file=None,page_numbers=None):
    page_numbers=set(page_numbers or [])
    refs=[];seen=set()
    for p in pages:
        if file is not None and p.get("file")!=file:continue
        if page_numbers and p.get("page") not in page_numbers:continue
        did=p.get("document_id") or "ID-NÃO-IDENTIFICADO"
        key=(p.get("file"),did)
        if key in seen:continue
        seen.add(key)
        refs.append({
            "document_id":did,
            "source_document_id":p.get("source_document_id"),
            "file":p.get("file"),
            "page":p.get("page")
        })
    return refs

def _enrich_doc_refs(a,pages):
    for x in a.get("pieces",[]):
        x["documents"]=_page_doc_refs(pages,x.get("file"),x.get("pages",[]))
    for x in a.get("mentions",[]):
        x["documents"]=_page_doc_refs(pages,x.get("file"),x.get("pages",[]))
    for key in ["defense","contra","no_delivery","final_sanction"]:
        for x in a.get(key,[]) or []:
            refs=_page_doc_refs(pages,x.get("file"),[x.get("page")])
            if refs:
                x["document_id"]=refs[0]["document_id"]
                x["source_document_id"]=refs[0]["source_document_id"]
    q=a.get("quantity",{}).get("source")
    if q:
        refs=_page_doc_refs(pages,q.get("file"),[q.get("page")])
        if refs:
            q["document_id"]=refs[0]["document_id"]
            q["source_document_id"]=refs[0]["source_document_id"]

    for x in a.get("module_matrix",[]) or []:
        x["documents"]=_page_doc_refs(pages,None,x.get("pages",[]))
    for x in a.get("module_timeline",[]) or []:
        x["documents"]=_page_doc_refs(pages,None,x.get("pages",[]))
    for x in a.get("module_evidence",[]) or []:
        refs=_page_doc_refs(pages,None,[x.get("page")])
        if refs:
            x["document_id"]=refs[0]["document_id"]
            x["source_document_id"]=refs[0]["source_document_id"]
    for x in a.get("process_checklist",[]) or []:
        x["documents"]=_page_doc_refs(pages,None,x.get("pages",[]))
    for x in a.get("traceability",[]) or []:
        x["documents"]=_page_doc_refs(pages,x.get("source"),x.get("pages",[]))
        if not x["documents"]:
            x["documents"]=_page_doc_refs(pages,None,x.get("pages",[]))
    return a

async def analyze_v67(files:List[UploadFile]=File(...), module:str="penalizacao"):
    pages=[];ocr=0;names=[]
    for f in files:
        if not f.filename.lower().endswith(".pdf"):continue
        pp,oo=extract_pdf(await f.read(),f.filename)
        pages.extend(pp);ocr+=oo;names.append(f.filename)
    if not pages:raise HTTPException(400,"Envie pelo menos um PDF.")
    _assign_document_ids(pages)
    a=analyze_pages(pages)
    a=_module_overlay(pages,a,module)
    a=_enrich_doc_refs(a,pages)
    aid=uuid.uuid4().hex
    ANALYSES[aid]={"pages":pages,"analysis":a,"created":datetime.utcnow().isoformat(),"module":module}
    return {"analysis_id":aid,"files":names,"pages":len(pages),"ocr_pages":ocr,"module":module,"analysis":a}

app.router.routes=[
    r for r in app.router.routes
    if not (getattr(r,"path",None)=="/api/analyze" and "POST" in getattr(r,"methods",set()))
]
app.add_api_route("/api/analyze",analyze_v67,methods=["POST"])

_old_answer_question_v67=answer_question
def _source_with_doc_id(source,pages):
    # Localiza a primeira página citada e acrescenta o ID do documento à referência.
    m=re.search(r"(?:p\.|página|paginas?|páginas?)\s*\.?\s*(\d+)",source or "",flags=re.I)
    if not m:return source
    pg=int(m.group(1))
    refs=_page_doc_refs(pages,None,[pg])
    if not refs:return source
    r=refs[0]
    prefix="ID "+r["document_id"]
    if r.get("source_document_id"):
        prefix+=" · "+r["source_document_id"]
    if prefix.lower() in (source or "").lower():return source
    return prefix+" · "+source

def answer_question(q,a,pages):
    res=_old_answer_question_v67(q,a,pages)
    res["sources"]=[_source_with_doc_id(s,pages) for s in (res.get("sources") or [])]
    return res

def report_v67(analysis_id):
    item=ANALYSES.get(analysis_id)
    if not item:raise HTTPException(404,"Análise não encontrada.")
    a=item["analysis"];buf=io.BytesIO();c=canvas.Canvas(buf,pagesize=A4);y=810
    c.setFont("Helvetica-Bold",15);c.drawString(40,y,"Fiscaliza.AI Municipal — Relatório rastreável");y-=26
    c.setFont("Helvetica",9)
    lines=[a.get("conclusion",""),"","Evidências e documentos:"]
    if a.get("module_matrix"):
        for x in a["module_matrix"]:
            refs=[]
            for d in x.get("documents",[]):
                rr=d["document_id"]
                if d.get("source_document_id"):rr+=" ("+d["source_document_id"]+")"
                refs.append(rr)
            ref=", ".join(refs) if refs else "ID não identificado"
            pgs=fmt_pages(x.get("pages",[])) or "—"
            lines.append("- "+x.get("label",x.get("question","Evidência"))+": "+("confirmado" if x.get("ok") else "conferir")+" | "+ref+" | p. "+pgs)
    else:
        for x in a.get("pieces",[]):
            refs=[]
            for d in x.get("documents",[]):
                rr=d["document_id"]
                if d.get("source_document_id"):rr+=" ("+d["source_document_id"]+")"
                refs.append(rr)
            lines.append("- "+x["label"]+": "+(", ".join(refs) if refs else "ID não identificado")+" | p. "+fmt_pages(x["pages"]))
    lines+=["","Pendências e limites:"]+["- "+p for p in a.get("pending",[])]
    for line in lines:
        chunks=[line[i:i+105] for i in range(0,max(1,len(line)),105)] or [""]
        for chunk in chunks:
            if y<50:c.showPage();y=810;c.setFont("Helvetica",9)
            c.drawString(40,y,chunk);y-=13
    c.save();buf.seek(0)
    return StreamingResponse(buf,media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=fiscaliza-relatorio-rastreavel.pdf"})

app.router.routes=[
    r for r in app.router.routes
    if not (getattr(r,"path",None)=="/api/report/{analysis_id}" and "GET" in getattr(r,"methods",set()))
]
app.add_api_route("/api/report/{analysis_id}",report_v67,methods=["GET"])
app.version="6.7"

_docid_css = """
.doc-id-chip{display:inline-flex;align-items:center;background:#eef4f8;border:1px solid #d2dde7;border-radius:999px;padding:3px 7px;margin-right:5px;font-size:8px;font-weight:850;color:var(--navy)}
.doc-origin{font-size:8px;color:var(--muted);margin-left:4px}
.ref-stack{display:flex;gap:4px;align-items:center;flex-wrap:wrap}
"""
HTML=HTML.replace("</style>",_docid_css+"</style>",1)

_docid_js = r"""
function documentRefHtml(docs,pages){
  docs=docs||[];pages=pages||[];
  var h='<span class="ref-stack">';
  if(docs.length){
    for(var i=0;i<docs.length;i++){
      var d=docs[i];
      h+='<span class="doc-id-chip" title="'+esc(d.source_document_id||"ID interno de rastreabilidade")+'">ID '+esc(d.document_id)+'</span>';
      if(d.source_document_id)h+='<span class="doc-origin">'+esc(d.source_document_id)+'</span>';
    }
  }else h+='<span class="doc-id-chip">ID não identificado</span>';
  if(pages.length)h+=pageChip(pages.join(", "));
  h+='</span>';
  return h;
}
function docForSingle(x){
  if(!x)return "";
  var docs=[];
  if(x.document_id)docs=[{document_id:x.document_id,source_document_id:x.source_document_id||null}];
  return documentRefHtml(docs,x.page?[x.page]:[]);
}

// Sobrescreve a adaptação visual: ID do documento acompanha todas as páginas.
function ajustarResultadoModulo(a){
  if(!a)return;

  var timeline=acharSectionPorTitulo("Linha do tempo do processo");
  if(timeline){
    var th='<div class="kicker">Cronologia dos autos · '+esc(a.module_label||"Processo")+'</div><h2>Linha do tempo do processo</h2><div class="timeline">';
    var items=[];
    if(a.module_key==="penalizacao"){
      items=(a.pieces||[]).map(function(x){return {label:x.label,pages:x.pages,documents:x.documents||[]}}).sort(function(x,y){return (x.pages[0]||9999)-(y.pages[0]||9999)});
    }else items=a.module_timeline||[];
    if(items.length){
      for(var i=0;i<items.length;i++){
        var t=items[i];
        th+='<div class="timeline-step"><div class="tp">'+documentRefHtml(t.documents||[],t.pages||[])+'</div><b>'+esc(t.label)+'</b></div>';
      }
      th+='</div>';
    }else th='<div class="kicker">Cronologia dos autos</div><h2>Linha do tempo do processo</h2><div class="empty">Nenhum marco específico foi localizado com segurança.</div>';
    timeline.innerHTML=th;
  }

  var matrix=acharSectionPorTitulo("Matriz de evidências")||acharSectionPorTitulo("Matriz de evidências do módulo");
  if(matrix&&a.module_matrix){
    var mh='<div class="kicker">Auditabilidade · '+esc(a.module_label||"Processo")+'</div><h2>Matriz de evidências do módulo</h2><table class="matrix"><thead><tr><th>Questão</th><th>Resposta</th><th>Documento / página</th><th>Status</th></tr></thead><tbody>';
    for(var j=0;j<a.module_matrix.length;j++){
      var r=a.module_matrix[j];
      mh+='<tr><td>'+esc(r.question)+'</td><td>'+esc(r.answer)+'</td><td>'+documentRefHtml(r.documents||[],r.pages||[])+'</td><td class="'+(r.ok?'matrix-ok':'matrix-limit')+'">'+(r.ok?'Confirmado':'Conferir')+'</td></tr>';
    }
    mh+='</tbody></table>';
    matrix.innerHTML=mh;
  }

  var structure=acharSectionPorTitulo("Estrutura do processo")||acharSectionPorTitulo("Estrutura esperada do processo");
  if(structure){
    var sh='<div class="kicker">Elementos essenciais · '+esc(a.module_label||"Processo")+'</div><h2>Estrutura do processo</h2><div class="piece-grid">';
    if(a.module_key==="penalizacao"){
      for(var k=0;k<(a.pieces||[]).length;k++){
        var p=a.pieces[k];
        sh+='<article class="piece"><div class="piece-top"><div class="piece-icon">✓</div><div class="piece-name">'+esc(p.label)+'</div></div><div class="source">'+documentRefHtml(p.documents||[],p.pages||[])+'</div></article>';
      }
    }else{
      for(var m=0;m<(a.module_matrix||[]).length;m++){
        var mr=a.module_matrix[m];
        sh+='<article class="piece"><div class="piece-top"><div class="piece-icon">'+(mr.ok?'✓':'!')+'</div><div class="piece-name">'+esc(mr.label)+'</div></div><div class="source">'+documentRefHtml(mr.documents||[],mr.pages||[])+'</div></article>';
      }
    }
    sh+='</div>';
    structure.innerHTML=sh;
  }

  // Acrescenta ID do documento aos achados textuais já renderizados.
  var cols=document.querySelectorAll("#result .finding");
  var combined=(a.defense||[]).concat(a.contra||[]);
  for(var z=0;z<cols.length&&z<combined.length;z++){
    var foot=cols[z].querySelector(".finding-foot");
    if(foot && !foot.querySelector(".doc-id-chip")){
      foot.insertAdjacentHTML("afterbegin",docForSingle(combined[z]));
    }
  }

  if(a.module_key!=="penalizacao"){
    var manifests=acharSectionPorTitulo("Elementos apresentados pelo interessado")||acharSectionPorTitulo("Elementos localizados nos autos");
    if(manifests){
      var body='<div class="kicker">Evidências do módulo</div><h2>Elementos localizados nos autos</h2>';
      if(!a.module_evidence||!a.module_evidence.length)body+='<div class="empty">Nenhuma evidência específica do módulo foi localizada.</div>';
      else for(var e=0;e<a.module_evidence.length;e++){
        var ev=a.module_evidence[e];
        body+='<div class="finding"><div class="finding-num">'+(e+1)+'</div><div><div class="finding-text"><b>'+esc(ev.label)+':</b> '+esc(ev.text||"Evidência localizada.")+'</div><div class="finding-foot">'+docForSingle(ev)+'</div></div></div>';
      }
      manifests.innerHTML=body;
    }
    var confront=acharSectionPorTitulo("Pontos a confrontar")||acharSectionPorTitulo("Pontos para conferência");
    if(confront){
      var ch='<div class="kicker">Conferência do módulo</div><h2>Pontos para conferência</h2>';
      var missing=(a.module_matrix||[]).filter(function(x){return !x.ok});
      if(!missing.length)ch+='<div class="empty">Todos os controles essenciais deste módulo foram localizados. Faça a revisão de coerência antes da conclusão.</div>';
      else for(var q=0;q<missing.length;q++)ch+='<div class="warning">Conferir: '+esc(missing[q].label)+'</div>';
      confront.innerHTML=ch;
    }
  }

  var trace=acharSectionPorTitulo("Rastreabilidade da conclusão");
  if(trace){
    var rh='<div class="kicker">Como chegou aqui</div><h2>Rastreabilidade da conclusão</h2>';
    for(var rix=0;rix<(a.traceability||[]).length;rix++){
      var tv=a.traceability[rix];
      rh+='<div class="trace-row"><b>'+esc(tv.claim)+'</b><span>'+esc(tv.status)+'</span><span>'+documentRefHtml(tv.documents||[],tv.pages||[])+'</span></div>';
    }
    trace.innerHTML=rh;
  }

  var review=acharSectionPorTitulo("Pontos antes da assinatura");
  if(review&&a.module_key!=="penalizacao"){
    var kk=review.querySelector(".kicker");if(kk)kk.textContent="Revisão do processo";
    var hh=review.querySelector("h2");if(hh)hh.textContent="Pontos antes da conclusão";
  }
}
"""
HTML=HTML.replace("</script>",_docid_js+"\n</script>",1)

HTML=HTML.replace("VERSÃO 6.6 · MÓDULOS ESPECIALIZADOS","VERSÃO 6.7 · ID DO DOCUMENTO + PÁGINA")


# --- Interface de sistema administrativo v6.8 ---
_system_css = """
/* Workspace com aparência de sistema, não landing page */
.screen-workspace{padding-bottom:28px}
.workspace-head{
  padding:14px 18px!important;margin-bottom:14px!important;border-radius:14px!important;
  box-shadow:0 3px 12px rgba(16,42,67,.05)!important
}
.workspace-title strong{font-size:17px!important}.workspace-title span{font-size:9px!important}
.workspace-chip{display:none!important}
.workspace-actions{display:flex;gap:8px;align-items:center;margin-left:auto}
.workspace-actions .btn{padding:9px 12px;font-size:10px}
.process-status{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:#f8fafc;color:var(--muted);border-radius:999px;padding:7px 10px;font-size:9px;font-weight:850}
.process-status:before{content:"";width:7px;height:7px;border-radius:50%;background:#98a7b5}
.process-status.ready{background:#edf9f6;color:var(--teal);border-color:#b8d8d2}.process-status.ready:before{background:var(--teal)}

.system-layout{display:grid;grid-template-columns:210px minmax(0,1fr);gap:14px;align-items:start}
.system-sidebar{position:sticky;top:18px;background:#0f2f49;color:#fff;border-radius:14px;padding:12px;min-height:520px;box-shadow:0 8px 24px rgba(15,47,73,.12)}
.side-brand{padding:8px 9px 14px;border-bottom:1px solid rgba(255,255,255,.12);margin-bottom:8px}
.side-brand small{display:block;color:#88d8cc;font-size:8px;font-weight:900;text-transform:uppercase;letter-spacing:.12em}
.side-brand strong{display:block;font-size:13px;margin-top:4px}
.side-nav{display:grid;gap:4px}
.side-item{width:100%;border:0;background:transparent;color:#d8e3eb;text-align:left;border-radius:9px;padding:10px 10px;cursor:pointer;font-size:10px;font-weight:750;display:flex;gap:9px;align-items:center}
.side-item:hover{background:rgba(255,255,255,.07);color:#fff}
.side-item.active{background:#fff;color:#0f2f49}
.side-ico{width:22px;height:22px;border-radius:7px;background:rgba(255,255,255,.10);display:grid;place-items:center;font-size:9px;font-weight:900}
.side-item.active .side-ico{background:#e9f7f4;color:var(--teal)}
.side-item.disabled{opacity:.42;cursor:default}
.side-footer{margin-top:18px;padding:10px 9px;border-top:1px solid rgba(255,255,255,.12);font-size:8px;color:#9fb0bf;line-height:1.5}

.system-main{min-width:0}
.system-main>.panel{margin-top:0;margin-bottom:14px}
.system-main .demo-panel{display:none!important}
.system-main #uploadPanel{margin-bottom:14px}
.system-main #uploadPanel .panel-head{margin-bottom:10px}
.system-main #uploadPanel .title{font-size:17px}
.system-main #uploadPanel .uploadbox{background:#f8fbfd;border:1px dashed #aebfce;border-radius:12px;padding:18px}
.system-main #uploadPanel .uploadicon{width:34px;height:34px}
.system-main #uploadPanel .status{font-size:9px}

.module-dashboard{display:block;margin-bottom:14px}
.dashboard-top{display:flex;justify-content:space-between;align-items:flex-end;gap:18px;margin-bottom:11px}
.dashboard-top .kicker{margin-bottom:3px}.dashboard-top h2{margin:0;color:var(--navy);font-size:18px}.dashboard-top p{margin:4px 0 0;color:var(--muted);font-size:10px}
.dashboard-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}
.dash-metric{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 13px}
.dash-metric small{display:block;color:var(--muted);font-size:8px;text-transform:uppercase;letter-spacing:.08em;font-weight:850}
.dash-metric strong{display:block;color:var(--navy);font-size:20px;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dash-metric strong.text{font-size:12px;margin-top:7px}
.dash-metric .mini{display:block;color:var(--muted);font-size:8px;margin-top:3px}

.process-tabs{display:none;background:#fff;border:1px solid var(--line);border-radius:12px;padding:5px;margin:0 0 12px;gap:4px;overflow-x:auto}
.process-tabs.visible{display:flex}
.process-tab{border:0;background:transparent;border-radius:8px;padding:9px 11px;font-size:9px;font-weight:850;color:var(--muted);cursor:pointer;white-space:nowrap}
.process-tab:hover{background:#f4f7f9;color:var(--navy)}
.process-tab.active{background:#0f2f49;color:#fff}

#result.system-result>.section,#result.system-result>.cols,#result.system-result>.control-grid,#result.system-result>details{margin-top:0;margin-bottom:12px}
#result.system-result .section{border-radius:12px!important;box-shadow:none!important}
#result.system-result .title,#result.system-result h2{font-size:15px}
#result.system-result .summary-card,#result.system-result .piece,#result.system-result .metric{border-radius:9px}
#result.system-result .summary-grid{gap:8px}
#result.system-result .summary-card{padding:10px 11px}
#result.system-result .summary-value{font-size:11px}
#result.system-result .timeline-step{padding:9px}
#result.system-result .matrix th,#result.system-result .matrix td{padding:8px 9px}

.system-empty{background:#fff;border:1px solid var(--line);border-radius:14px;padding:24px;margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;gap:20px}
.system-empty h3{margin:0;color:var(--navy);font-size:16px}.system-empty p{margin:5px 0 0;color:var(--muted);font-size:10px;max-width:650px}
.empty-icon{width:42px;height:42px;border-radius:11px;background:#eaf4f7;color:var(--teal);display:grid;place-items:center;font-weight:900;font-size:16px;flex:0 0 auto}

#qaPanel,#notificationPanel,#docsPanel,#privacyPanel,#reportPanel{display:none}
#qaPanel.tab-visible,#notificationPanel.tab-visible,#docsPanel.tab-visible,#privacyPanel.tab-visible,#reportPanel.tab-visible{display:block}
#result .tab-hidden{display:none!important}
#result .cols.tab-hidden,#result .control-grid.tab-hidden{display:none!important}
#result details.tab-hidden{display:none!important}

@media(max-width:980px){
  .system-layout{grid-template-columns:1fr}
  .system-sidebar{position:static;min-height:auto}
  .side-nav{grid-template-columns:repeat(4,1fr)}
  .side-item{justify-content:center;text-align:center;flex-direction:column;padding:8px 4px}
  .side-brand,.side-footer{display:none}
}
@media(max-width:700px){
  .workspace-head{align-items:stretch!important}
  .workspace-actions{width:100%;margin-left:0;flex-wrap:wrap}
  .dashboard-metrics{grid-template-columns:1fr 1fr}
  .side-nav{grid-template-columns:repeat(2,1fr)}
  .system-empty{align-items:flex-start}
}
"""
HTML=HTML.replace("</style>",_system_css+"</style>",1)

_system_js = r"""
var lastAnalysisData=null;
var currentProcessTab="resumo";

function painelPorTexto(fragmento){
  var ps=document.querySelectorAll("#screenWorkspace section.panel");
  fragmento=fragmento.toLowerCase();
  for(var i=0;i<ps.length;i++){
    if((ps[i].textContent||"").toLowerCase().indexOf(fragmento)>=0)return ps[i];
  }
  return null;
}

function garantirSistemaWorkspace(){
  var work=document.getElementById("screenWorkspace");
  if(!work||work.dataset.systemized==="1")return;
  work.dataset.systemized="1";

  var head=work.querySelector(".workspace-head");
  if(!head)return;

  var actions=document.createElement("div");
  actions.className="workspace-actions";
  actions.innerHTML='<span id="processStatus" class="process-status">Sem processo</span><button class="btn btn-blue" onclick="novoProcessoModulo()">+ Novo processo</button><button class="btn btn-primary" onclick="testarDemo()">Usar processo modelo</button>';
  head.appendChild(actions);

  var layout=document.createElement("div");
  layout.className="system-layout";
  var side=document.createElement("aside");
  side.className="system-sidebar";
  side.innerHTML='<div class="side-brand"><small>Fiscaliza.AI</small><strong id="sideModuleName">Módulo</strong></div>'+
    '<nav class="side-nav">'+
    '<button class="side-item active" data-tab="resumo" onclick="mostrarAbaProcesso(\'resumo\',this)"><span class="side-ico">01</span><span>Visão geral</span></button>'+
    '<button class="side-item" data-tab="documentos" onclick="mostrarAbaProcesso(\'documentos\',this)"><span class="side-ico">02</span><span>Documentos</span></button>'+
    '<button class="side-item" data-tab="evidencias" onclick="mostrarAbaProcesso(\'evidencias\',this)"><span class="side-ico">03</span><span>Evidências</span></button>'+
    '<button class="side-item" data-tab="cronologia" onclick="mostrarAbaProcesso(\'cronologia\',this)"><span class="side-ico">04</span><span>Cronologia</span></button>'+
    '<button class="side-item" data-tab="pendencias" onclick="mostrarAbaProcesso(\'pendencias\',this)"><span class="side-ico">05</span><span>Pendências</span></button>'+
    '<button class="side-item" data-tab="perguntar" onclick="mostrarAbaProcesso(\'perguntar\',this)"><span class="side-ico">06</span><span>Perguntar</span></button>'+
    '<button class="side-item" data-tab="minutas" onclick="mostrarAbaProcesso(\'minutas\',this)"><span class="side-ico">07</span><span>Minutas</span></button>'+
    '<button class="side-item" data-tab="relatorio" onclick="mostrarAbaProcesso(\'relatorio\',this)"><span class="side-ico">08</span><span>Relatório</span></button>'+
    '</nav><div class="side-footer">Rastreabilidade por documento e página<br>VERSÃO 6.8 · INTERFACE DE SISTEMA</div>';

  var main=document.createElement("div");
  main.className="system-main";

  var dash=document.createElement("div");
  dash.id="moduleDashboard";
  dash.className="module-dashboard";
  dash.innerHTML='<div class="dashboard-top"><div><div class="kicker">Painel do módulo</div><h2 id="dashboardTitle">Processo ainda não carregado</h2><p id="dashboardSub">Carregue os autos ou use o processo modelo para iniciar.</p></div></div>'+
    '<div class="dashboard-metrics">'+
    '<div class="dash-metric"><small>Documentos</small><strong id="dashDocs">0</strong><span class="mini">identificados</span></div>'+
    '<div class="dash-metric"><small>Evidências</small><strong id="dashEvidence">0</strong><span class="mini">rastreadas</span></div>'+
    '<div class="dash-metric"><small>Pendências</small><strong id="dashPending">0</strong><span class="mini">para conferência</span></div>'+
    '<div class="dash-metric"><small>Etapa atual</small><strong id="dashStage" class="text">Não iniciada</strong><span class="mini">situação do fluxo</span></div>'+
    '</div>';

  var empty=document.createElement("div");
  empty.id="systemEmpty";
  empty.className="system-empty";
  empty.innerHTML='<div style="display:flex;gap:14px;align-items:flex-start"><div class="empty-icon">↥</div><div><h3>Comece uma análise</h3><p>Selecione os documentos do processo ou use o modelo fictício deste módulo. Após a leitura, o sistema libera documentos, evidências, cronologia, pendências, perguntas e minutas.</p></div></div>';

  var tabs=document.createElement("div");
  tabs.id="processTabs";
  tabs.className="process-tabs";
  tabs.innerHTML='<button class="process-tab active" data-tab="resumo" onclick="mostrarAbaProcesso(\'resumo\',this)">Resumo</button>'+
    '<button class="process-tab" data-tab="documentos" onclick="mostrarAbaProcesso(\'documentos\',this)">Documentos</button>'+
    '<button class="process-tab" data-tab="evidencias" onclick="mostrarAbaProcesso(\'evidencias\',this)">Evidências</button>'+
    '<button class="process-tab" data-tab="cronologia" onclick="mostrarAbaProcesso(\'cronologia\',this)">Cronologia</button>'+
    '<button class="process-tab" data-tab="pendencias" onclick="mostrarAbaProcesso(\'pendencias\',this)">Pendências</button>'+
    '<button class="process-tab" data-tab="perguntar" onclick="mostrarAbaProcesso(\'perguntar\',this)">Perguntar</button>'+
    '<button class="process-tab" data-tab="minutas" onclick="mostrarAbaProcesso(\'minutas\',this)">Minutas</button>'+
    '<button class="process-tab" data-tab="relatorio" onclick="mostrarAbaProcesso(\'relatorio\',this)">Relatório</button>';

  layout.appendChild(side);layout.appendChild(main);
  work.insertBefore(layout,head.nextSibling);
  main.appendChild(dash);
  main.appendChild(empty);
  main.appendChild(tabs);

  // Move o fluxo operacional para a área principal.
  Array.from(work.children).forEach(function(el){
    if(el!==head&&el!==layout)main.appendChild(el);
  });

  var demo=main.querySelector(".demo-panel");
  if(demo)demo.style.display="none";

  var upload=painelPorTexto("analisar seus documentos");
  if(upload)upload.id="uploadPanel";
  var qa=painelPorTexto("consulta aos autos");
  if(qa)qa.id="qaPanel";
  var notif=painelPorTexto("notificação institucional com preenchimento validado");
  if(notif)notif.id="notificationPanel";
  var docs=painelPorTexto("fluxo documental assistido");
  if(docs)docs.id="docsPanel";
  var priv=painelPorTexto("privacidade e sessão");
  if(priv)priv.id="privacyPanel";
  var report=painelPorTexto("documentação da análise");
  if(report)report.id="reportPanel";

  var result=document.getElementById("result");
  if(result)result.classList.add("system-result");

  atualizarNomeSistemaModulo();
  prepararInicioModulo();
}

function atualizarNomeSistemaModulo(){
  var lab=moduleLabels[selectedModule]||selectedModule;
  var s=document.getElementById("sideModuleName");if(s)s.textContent=lab;
  var d=document.getElementById("dashboardTitle");
  if(d&&!lastAnalysisData)d.textContent="Processo ainda não carregado";
}

function prepararInicioModulo(){
  lastAnalysisData=null;
  currentProcessTab="resumo";
  var result=document.getElementById("result");if(result){result.innerHTML="";result.style.display="none"}
  var tabs=document.getElementById("processTabs");if(tabs)tabs.classList.remove("visible");
  var empty=document.getElementById("systemEmpty");if(empty)empty.style.display="flex";
  var upload=document.getElementById("uploadPanel");if(upload)upload.style.display="block";
  ["qaPanel","notificationPanel","docsPanel","privacyPanel","reportPanel"].forEach(function(id){var x=document.getElementById(id);if(x){x.classList.remove("tab-visible");x.style.display="none"}});
  var st=document.getElementById("processStatus");if(st){st.textContent="Sem processo";st.classList.remove("ready")}
  var ds=document.getElementById("dashboardSub");if(ds)ds.textContent="Carregue os autos ou use o processo modelo para iniciar.";
  var vals={dashDocs:"0",dashEvidence:"0",dashPending:"0",dashStage:"Não iniciada"};
  Object.keys(vals).forEach(function(id){var x=document.getElementById(id);if(x)x.textContent=vals[id]});
  document.querySelectorAll(".side-item").forEach(function(x){x.classList.toggle("active",x.dataset.tab==="resumo")});
  document.querySelectorAll(".process-tab").forEach(function(x){x.classList.toggle("active",x.dataset.tab==="resumo")});
}

async function novoProcessoModulo(){
  analysisId=analysisId||localStorage.getItem("fiscaliza_analysis_id");
  if(analysisId){try{await fetch("/api/analysis/"+analysisId,{method:"DELETE"})}catch(e){}}
  analysisId=null;localStorage.removeItem("fiscaliza_analysis_id");
  var fi=document.getElementById("files");if(fi)fi.value="";
  var ans=document.getElementById("answer");if(ans)ans.style.display="none";
  prepararInicioModulo();
  window.scrollTo({top:0,behavior:"smooth"});
}

function tituloSecao(sec){
  var h=sec.querySelector&&sec.querySelector("h2");
  return h?h.textContent.trim().toLowerCase():"";
}

function grupoSecao(titulo){
  if(titulo.indexOf("linha do tempo")>=0)return "cronologia";
  if(titulo.indexOf("matriz de evid")>=0||titulo.indexOf("elementos localizados")>=0||titulo.indexOf("pontos para confer")>=0||titulo.indexOf("pontos a confront")>=0||titulo.indexOf("contradi")>=0||titulo.indexOf("rastreabilidade")>=0)return "evidencias";
  if(titulo.indexOf("estrutura do processo")>=0||titulo.indexOf("estrutura esperada")>=0)return "documentos";
  if(titulo.indexOf("mapa de pend")>=0||titulo.indexOf("pontos antes")>=0||titulo.indexOf("pendências e limites")>=0||titulo.indexOf("pendencias e limites")>=0)return "pendencias";
  return "resumo";
}

function marcarGruposResultado(){
  var result=document.getElementById("result");if(!result)return;
  var nodes=Array.from(result.children);
  nodes.forEach(function(node){
    var secs=[];
    if(node.classList&&node.classList.contains("section"))secs=[node];
    else if(node.querySelectorAll)secs=Array.from(node.querySelectorAll(":scope > .section"));
    if(node.tagName==="DETAILS"){
      node.dataset.group="documentos";return;
    }
    if(!secs.length)return;
    var groups=secs.map(function(s){return grupoSecao(tituloSecao(s))});
    var unique=Array.from(new Set(groups));
    node.dataset.group=unique.length===1?unique[0]:"mixed";
    secs.forEach(function(s){s.dataset.group=grupoSecao(tituloSecao(s))});
  });
}

function setPanelVisibility(tab){
  var result=document.getElementById("result");
  if(result){
    result.style.display=(["resumo","documentos","evidencias","cronologia","pendencias"].indexOf(tab)>=0)?"block":"none";
    Array.from(result.children).forEach(function(node){
      if(!node.dataset.group)return;
      if(node.dataset.group==="mixed"){
        var secs=Array.from(node.querySelectorAll(":scope > .section"));
        secs.forEach(function(s){s.style.display=(s.dataset.group===tab)?"block":"none"});
        node.style.display=secs.some(function(s){return s.style.display!=="none"})?"grid":"none";
      }else node.style.display=(node.dataset.group===tab)?"block":"none";
    });
  }
  var map={perguntar:["qaPanel"],minutas:["notificationPanel","docsPanel"],relatorio:["reportPanel","privacyPanel"]};
  ["qaPanel","notificationPanel","docsPanel","privacyPanel","reportPanel"].forEach(function(id){
    var p=document.getElementById(id);if(!p)return;
    var show=(map[tab]||[]).indexOf(id)>=0;
    p.style.display=show?"block":"none";
    p.classList.toggle("tab-visible",show);
  });
}

function mostrarAbaProcesso(tab,btn){
  if(!lastAnalysisData && tab!=="resumo")return;
  currentProcessTab=tab;
  document.querySelectorAll(".side-item,.process-tab").forEach(function(x){x.classList.toggle("active",x.dataset.tab===tab)});
  setPanelVisibility(tab);
  var main=document.querySelector(".system-main");if(main)main.scrollIntoView({behavior:"smooth",block:"start"});
}

function ativarProcessoNoSistema(a){
  if(!a)return;
  lastAnalysisData=a;
  var result=document.getElementById("result");if(result){result.classList.add("system-result");result.style.display="block"}
  var empty=document.getElementById("systemEmpty");if(empty)empty.style.display="none";
  var upload=document.getElementById("uploadPanel");if(upload)upload.style.display="none";
  var tabs=document.getElementById("processTabs");if(tabs)tabs.classList.add("visible");
  var st=document.getElementById("processStatus");if(st){st.textContent="Processo analisado";st.classList.add("ready")}
  var title=document.getElementById("dashboardTitle");if(title)title.textContent=(a.module_label||moduleLabels[selectedModule]||"Processo")+" · análise concluída";
  var sub=document.getElementById("dashboardSub");if(sub)sub.textContent="Use as áreas abaixo para navegar pelo processo sem percorrer uma página longa.";

  var docs=(a.metrics&&a.metrics.pieces!=null)?a.metrics.pieces:(a.pieces||[]).length;
  var evid=(a.metrics&&a.metrics.evidence_points!=null)?a.metrics.evidence_points:(a.module_evidence||[]).length;
  var pend=(a.review_flags||[]).length;
  var stage=(a.next_action&&a.next_action.stage)?a.next_action.stage:"Revisão";
  var vals={dashDocs:String(docs),dashEvidence:String(evid),dashPending:String(pend),dashStage:stage};
  Object.keys(vals).forEach(function(id){var x=document.getElementById(id);if(x)x.textContent=vals[id]});

  marcarGruposResultado();
  mostrarAbaProcesso("resumo");
}

var _oldAjustarResultadoModuloV68=ajustarResultadoModulo;
ajustarResultadoModulo=function(a){
  _oldAjustarResultadoModuloV68(a);
  setTimeout(function(){ativarProcessoNoSistema(a)},0);
};

var _oldAbrirTelaModuloV68=abrirTelaModulo;
abrirTelaModulo=function(key,el,push){
  _oldAbrirTelaModuloV68(key,el,push);
  setTimeout(function(){garantirSistemaWorkspace();atualizarNomeSistemaModulo();prepararInicioModulo()},0);
};

document.addEventListener("DOMContentLoaded",function(){
  setTimeout(function(){
    if(document.getElementById("screenWorkspace"))garantirSistemaWorkspace();
  },60);
});
"""
HTML=HTML.replace("</script>",_system_js+"\n</script>",1)

# Atualiza textos remanescentes de demonstração/rastreabilidade.
HTML=HTML.replace("Cada achado aponta a página de origem.","Cada achado aponta o documento e a página de origem.")
HTML=HTML.replace("VERSÃO 6.7 · ID DO DOCUMENTO + PÁGINA","VERSÃO 6.8 · INTERFACE DE SISTEMA")


# --- Refinamento comercial / acessibilidade visual v6.9 ---
_commercial_css = """
:root{
  --navy:#0f2f49;
  --navy-2:#173f5f;
  --teal:#0b8f82;
  --teal-soft:#edf8f6;
  --ink:#132238;
  --muted:#66778a;
  --line:#d9e3ec;
  --bg:#f3f6f9;
  --shadow:0 10px 30px rgba(15,47,73,.08)
}
*{box-sizing:border-box}
body{
  font-family:"Segoe UI",Arial,sans-serif!important;
  font-size:14px!important;
  line-height:1.5!important;
  background:linear-gradient(180deg,#f7f9fb 0,#f1f5f8 100%)!important;
  color:var(--ink)!important
}
.topbar{box-shadow:0 1px 0 rgba(255,255,255,.08),0 6px 18px rgba(15,47,73,.08)}
.topbar-inner{min-height:70px!important}
.brandmark{width:40px!important;height:40px!important;border-radius:11px!important;font-size:13px!important}
.brandtext strong{font-size:17px!important;letter-spacing:-.2px}
.brandtext span{font-size:10px!important;letter-spacing:.09em}
.live{font-size:11px!important;padding:7px 10px;border:1px solid rgba(255,255,255,.12);border-radius:999px;background:rgba(255,255,255,.04)}

.shell{width:min(100% - 44px,1480px)!important;margin:28px auto 50px!important}
.panel,.section{border-color:var(--line)!important}
.kicker{font-size:10px!important;letter-spacing:.11em!important}
.title{font-size:20px!important;letter-spacing:-.25px!important}
.desc,.footnote{font-size:12px!important;line-height:1.55!important}
.btn{font-size:11.5px!important;font-weight:800!important;border-radius:10px!important;padding:10px 14px!important}
.fileinput{font-size:11.5px!important}
#status{font-size:11px!important;line-height:1.45!important}

/* Tela inicial vendável */
.screen-home{padding-top:2px}
.home-welcome{padding:0!important;margin:0 0 18px!important}
.home-commercial-hero{
  display:grid;grid-template-columns:minmax(0,1.45fr) minmax(310px,.55fr);gap:16px;
  background:linear-gradient(135deg,#0f2f49 0%,#163f5d 68%,#165e62 100%);
  border-radius:20px;padding:30px 32px;color:#fff;box-shadow:0 16px 42px rgba(15,47,73,.16);
  overflow:hidden;position:relative
}
.home-commercial-hero:after{
  content:"";position:absolute;right:-80px;top:-100px;width:310px;height:310px;border-radius:50%;
  border:54px solid rgba(255,255,255,.035)
}
.home-copy{position:relative;z-index:1}
.home-badge{
  display:inline-flex;align-items:center;gap:7px;padding:7px 10px;border-radius:999px;
  background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.14);
  font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:#d9f5f0
}
.home-commercial-hero h1{
  margin:13px 0 0;font-size:34px;line-height:1.12;letter-spacing:-.8px;color:#fff;max-width:760px
}
.home-commercial-hero p{
  margin:12px 0 0;font-size:14px;line-height:1.6;color:#d5e1ea;max-width:800px
}
.home-benefits{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}
.home-benefits span{
  display:inline-flex;align-items:center;gap:6px;padding:7px 10px;border-radius:999px;
  border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.07);font-size:10.5px;color:#eef7fb
}
.home-benefits span:before{content:"✓";color:#72d5c7;font-weight:900}
.home-side-card{
  position:relative;z-index:1;background:rgba(255,255,255,.96);color:var(--ink);
  border-radius:16px;padding:20px;display:flex;flex-direction:column;justify-content:space-between
}
.home-side-card small{display:block;color:var(--teal);font-size:9px;font-weight:900;text-transform:uppercase;letter-spacing:.1em}
.home-side-card strong{display:block;color:var(--navy);font-size:22px;line-height:1.15;margin-top:6px}
.home-side-card p{color:var(--muted);font-size:11.5px;line-height:1.5;margin:8px 0 0}
.home-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:16px}
.home-stat{border:1px solid var(--line);border-radius:10px;padding:9px;background:#f8fafc}
.home-stat b{display:block;color:var(--navy);font-size:17px}.home-stat span{display:block;color:var(--muted);font-size:8.5px;margin-top:1px}

.module-panel.home-only{
  padding:22px 24px 26px!important;border-radius:18px!important;background:#fff!important;
  box-shadow:var(--shadow)!important
}
.module-panel.home-only>.panel-head{display:none!important}
.module-toolbar{
  display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-bottom:16px
}
.module-toolbar-copy h2{margin:0;color:var(--navy);font-size:22px;letter-spacing:-.3px}
.module-toolbar-copy p{margin:5px 0 0;color:var(--muted);font-size:12px}
.module-search{
  width:min(360px,100%);display:flex;align-items:center;gap:8px;border:1px solid var(--line);
  border-radius:11px;padding:9px 11px;background:#f8fafc
}
.module-search span{color:#8696a6;font-size:13px}
.module-search input{
  width:100%;border:0;outline:0;background:transparent;color:var(--ink);font:inherit;font-size:12px
}
.module-grid{grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:12px!important}
.module-card{
  min-height:132px!important;padding:17px!important;border-radius:14px!important;position:relative;
  background:#fff!important;border:1px solid #d6e1ea!important
}
.module-card:hover{
  border-color:#9eb5c7!important;box-shadow:0 10px 24px rgba(15,47,73,.09)!important;transform:translateY(-2px)!important
}
.module-card.active{border:1px solid #d6e1ea!important;padding:17px!important;background:#fff!important}
.module-icon{
  width:40px!important;height:40px!important;border-radius:10px!important;font-size:15px!important;
  background:#edf3f7!important;color:var(--navy)!important;margin-bottom:12px!important
}
.module-name{font-size:13.5px!important;line-height:1.3!important;color:var(--navy)!important}
.module-desc{font-size:11px!important;line-height:1.48!important;margin-top:6px!important;padding-right:18px}
.module-card:after{
  content:"Abrir →";position:absolute;right:14px;bottom:13px;color:#7890a3;font-size:9px;font-weight:850
}
.module-card:hover:after{color:var(--teal)}
.module-selected{display:none!important}

/* Workspace mais legível */
.workspace-head{padding:16px 18px!important}
.workspace-back{font-size:11px!important;padding:9px 11px!important}
.workspace-title small{font-size:9.5px!important}
.workspace-title strong{font-size:19px!important}
.workspace-title span{font-size:11px!important}
.process-status{font-size:10px!important}
.system-layout{grid-template-columns:226px minmax(0,1fr)!important;gap:16px!important}
.system-sidebar{padding:13px!important;border-radius:15px!important}
.side-brand small{font-size:9px!important}.side-brand strong{font-size:14px!important}
.side-item{font-size:11.5px!important;padding:10px 11px!important}
.side-ico{font-size:10px!important}
.side-footer{font-size:9px!important}
.dashboard-top h2{font-size:20px!important}.dashboard-top p{font-size:11.5px!important}
.dash-metric{padding:14px!important}
.dash-metric small{font-size:9px!important}.dash-metric strong{font-size:24px!important}
.dash-metric strong.text{font-size:13px!important}.dash-metric .mini{font-size:9px!important}
.process-tab{font-size:10.5px!important;padding:10px 12px!important}
.system-empty h3{font-size:18px!important}.system-empty p{font-size:11.5px!important}
.uploadcopy strong{font-size:12.5px!important}.uploadcopy span{font-size:10.5px!important}

#result.system-result .kicker{font-size:9.5px!important}
#result.system-result h2{font-size:17px!important}
#result.system-result p,#result.system-result .empty,#result.system-result .warning{font-size:11.5px!important;line-height:1.5!important}
#result.system-result .summary-label{font-size:9.5px!important}
#result.system-result .summary-value{font-size:13px!important}
#result.system-result .piece-name{font-size:12px!important}
#result.system-result .source,#result.system-result .file-name{font-size:9.5px!important}
#result.system-result .finding-text{font-size:11.5px!important;line-height:1.55!important}
#result.system-result .finding-foot{font-size:9.5px!important}
#result.system-result .matrix th{font-size:9.5px!important}
#result.system-result .matrix td{font-size:11.5px!important;line-height:1.45!important}
#result.system-result .timeline-step b{font-size:11.5px!important}
#result.system-result .timeline-step .tp{font-size:9px!important}
#result.system-result .metric span{font-size:9px!important}
#result.system-result .metric strong{font-size:21px!important}
#result.system-result .check-row{font-size:11px!important}
#result.system-result .trace-row{font-size:10.5px!important}
.doc-id-chip{font-size:9px!important;padding:4px 7px!important}
.doc-origin{font-size:9px!important}
.answer-text{font-size:12px!important;line-height:1.6!important}
.source-card{font-size:9.5px!important}
.draft-text{font-size:12px!important;line-height:1.55!important}
.draft-toolbar strong{font-size:12px!important}.draft-toolbar span{font-size:10px!important}

@media(max-width:1180px){
  .home-commercial-hero{grid-template-columns:1fr}
  .home-side-card{display:grid;grid-template-columns:1fr auto;gap:18px;align-items:center}
  .home-stats{margin-top:0}
  .module-grid{grid-template-columns:repeat(3,minmax(0,1fr))!important}
}
@media(max-width:900px){
  .module-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}
  .module-toolbar{align-items:stretch;flex-direction:column}
  .module-search{width:100%}
}
@media(max-width:620px){
  .shell{width:min(100% - 24px,1480px)!important}
  .home-commercial-hero{padding:23px 20px}
  .home-commercial-hero h1{font-size:28px}
  .home-side-card{display:block}
  .home-stats{margin-top:14px}
  .module-grid{grid-template-columns:1fr!important}
  .module-card{min-height:120px!important}
}
"""
HTML=HTML.replace("</style>",_commercial_css+"</style>",1)

_commercial_js = r"""
function prepararHomeComercial(){
  var home=document.getElementById("screenHome");
  var welcome=home&&home.querySelector(".home-welcome");
  var modulePanel=document.querySelector(".module-panel.home-only");
  if(!home||!welcome||!modulePanel||home.dataset.commercial==="1")return;
  home.dataset.commercial="1";

  welcome.innerHTML=
    '<div class="home-commercial-hero">'+
      '<div class="home-copy">'+
        '<span class="home-badge">Inteligência processual para gestão pública</span>'+
        '<h1>Transforme autos extensos em evidências rastreáveis.</h1>'+
        '<p>Escolha o tipo de processo e entre em uma área de trabalho especializada, com leitura documental, cronologia, pendências, consulta aos autos e documentos assistidos.</p>'+
        '<div class="home-benefits"><span>Documento + página</span><span>Fluxos especializados</span><span>Revisão humana preservada</span><span>Sem cadastro para testar</span></div>'+
      '</div>'+
      '<aside class="home-side-card">'+
        '<div><small>Plataforma modular</small><strong>Fiscaliza.AI Municipal</strong><p>Um ambiente único para organizar diferentes rotinas administrativas com rastreabilidade e padrão de trabalho.</p></div>'+
        '<div class="home-stats"><div class="home-stat"><b>13</b><span>módulos</span></div><div class="home-stat"><b>100%</b><span>rastreável</span></div><div class="home-stat"><b>1</b><span>fluxo integrado</span></div></div>'+
      '</aside>'+
    '</div>';

  var toolbar=document.createElement("div");
  toolbar.className="module-toolbar";
  toolbar.innerHTML=
    '<div class="module-toolbar-copy"><div class="kicker">Módulos especializados</div><h2>Escolha o tipo de processo</h2><p>Entre no fluxo mais adequado ao procedimento que você precisa analisar.</p></div>'+
    '<label class="module-search"><span>⌕</span><input id="moduleSearch" type="search" placeholder="Buscar módulo..." oninput="filtrarModulos(this.value)"></label>';
  modulePanel.insertBefore(toolbar,modulePanel.firstChild);

  document.querySelectorAll(".module-card").forEach(function(c){c.classList.remove("active")});
}

function filtrarModulos(q){
  q=String(q||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"");
  document.querySelectorAll(".module-card").forEach(function(card){
    var text=(card.textContent||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"");
    card.style.display=(!q||text.indexOf(q)>=0)?"block":"none";
  });
}

var _oldConfigurarCamadasV69=configurarCamadas;
configurarCamadas=function(){
  _oldConfigurarCamadasV69();
  setTimeout(prepararHomeComercial,0);
};

var _oldVoltarAosModulosV69=voltarAosModulos;
voltarAosModulos=function(push){
  _oldVoltarAosModulosV69(push);
  setTimeout(function(){
    prepararHomeComercial();
    var s=document.getElementById("moduleSearch");if(s){s.value="";filtrarModulos("")}
  },0);
};

document.addEventListener("DOMContentLoaded",function(){
  setTimeout(prepararHomeComercial,100);
});
"""
HTML=HTML.replace("</script>",_commercial_js+"\n</script>",1)

HTML=HTML.replace("VERSÃO 6.8 · INTERFACE DE SISTEMA","VERSÃO 6.9 · INTERFACE COMERCIAL")


# --- Versão comercial focada: 6 módulos v7.0 ---
# Mantém todos os módulos no backend para expansão futura, mas exibe apenas os seis fluxos maduros.
VISIBLE_MODULES = ["penalizacao","fiscalizacao","reequilibrio","rescisao","sindicancia","disciplinar"]

_focus_css = """
/* Home focada em seis fluxos */
.screen-home .module-grid{grid-template-columns:repeat(3,minmax(0,1fr))!important}
.screen-home .module-card{min-height:142px!important}
.screen-home .module-search{display:none!important}
.screen-home .module-toolbar{align-items:flex-end!important}
.screen-home .module-toolbar-copy{max-width:760px}
.screen-home .module-toolbar-copy p{max-width:680px}
@media(max-width:980px){.screen-home .module-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}}
@media(max-width:620px){.screen-home .module-grid{grid-template-columns:1fr!important}}
"""
HTML=HTML.replace("</style>",_focus_css+"</style>",1)

_focus_js = r"""
function aplicarFocoComercialSeisModulos(){
  var visible={penalizacao:1,fiscalizacao:1,reequilibrio:1,rescisao:1,sindicancia:1,disciplinar:1};
  document.querySelectorAll(".module-card").forEach(function(card){
    var key=card.getAttribute("data-module");
    card.style.display=visible[key]?"block":"none";
  });

  var toolbar=document.querySelector(".module-toolbar");
  if(toolbar){
    var copy=toolbar.querySelector(".module-toolbar-copy");
    if(copy){
      var h=copy.querySelector("h2");if(h)h.textContent="Escolha um dos 6 fluxos especializados";
      var p=copy.querySelector("p");if(p)p.textContent="Fluxos selecionados para entregar profundidade, consistência e rastreabilidade em rotinas críticas da gestão pública.";
    }
    var search=toolbar.querySelector(".module-search");if(search)search.remove();
  }

  document.querySelectorAll(".home-stat").forEach(function(stat){
    var span=stat.querySelector("span"),b=stat.querySelector("b");
    if(span&&b&&span.textContent.trim().toLowerCase()==="módulos"){
      b.textContent="6";span.textContent="fluxos especializados";
    }
  });

  var side=document.querySelector(".home-side-card p");
  if(side)side.textContent="Um ambiente único para organizar gestão contratual e responsabilização administrativa com rastreabilidade e padrão de trabalho.";
}

var _oldPrepararHomeComercialV70=prepararHomeComercial;
prepararHomeComercial=function(){
  _oldPrepararHomeComercialV70();
  setTimeout(aplicarFocoComercialSeisModulos,0);
};

document.addEventListener("DOMContentLoaded",function(){
  setTimeout(aplicarFocoComercialSeisModulos,140);
});
"""
HTML=HTML.replace("</script>",_focus_js+"\n</script>",1)

HTML=HTML.replace("VERSÃO 6.9 · INTERFACE COMERCIAL","VERSÃO 7.0 · EDIÇÃO COMERCIAL")


# --- Novo processo abre o upload imediatamente v7.1 ---
_new_process_css = """
/* Estado de criação: o upload vira a tela principal, sem exigir rolagem */
.system-main.new-process-mode .module-dashboard,
.system-main.new-process-mode #systemEmpty,
.system-main.new-process-mode #processTabs,
.system-main.new-process-mode #result,
.system-main.new-process-mode #qaPanel,
.system-main.new-process-mode #notificationPanel,
.system-main.new-process-mode #docsPanel,
.system-main.new-process-mode #privacyPanel,
.system-main.new-process-mode #reportPanel{display:none!important}

#uploadPanel.new-process-card{
  display:block!important;
  margin:0!important;
  border-radius:14px!important;
  border:1px solid var(--line)!important;
  box-shadow:0 8px 24px rgba(15,47,73,.07)!important;
  padding:20px 22px!important;
  animation:newProcessIn .18s ease-out
}
#uploadPanel.new-process-card .panel-head{margin-bottom:14px!important}
#uploadPanel.new-process-card .kicker{font-size:9.5px!important}
#uploadPanel.new-process-card .title{font-size:21px!important;margin-top:2px!important}
#uploadPanel.new-process-card .desc{font-size:11.5px!important}
#uploadPanel.new-process-card .uploadbox{
  min-height:128px!important;padding:20px!important;background:#f8fbfd!important;
  border:1.5px dashed #9eb5c7!important;border-radius:12px!important
}
#uploadPanel.new-process-card .uploadcopy strong{font-size:13px!important}
#uploadPanel.new-process-card .uploadcopy span{font-size:11px!important}
.new-process-hint{
  display:flex;align-items:center;justify-content:space-between;gap:14px;
  border:1px solid #cfe5e1;background:#f2fbf9;border-radius:11px;padding:10px 12px;margin-bottom:12px
}
.new-process-hint strong{display:block;color:var(--teal);font-size:11px}
.new-process-hint span{display:block;color:var(--muted);font-size:9.5px;margin-top:2px}
.new-process-cancel{
  border:0;background:transparent;color:var(--navy);font-size:10px;font-weight:850;cursor:pointer;
  padding:7px 8px;border-radius:8px;white-space:nowrap
}
.new-process-cancel:hover{background:#e8f1f5}
@keyframes newProcessIn{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
"""
HTML=HTML.replace("</style>",_new_process_css+"</style>",1)

_new_process_js = r"""
function limparEstadoAnaliseVisual(){
  lastAnalysisData=null;
  currentProcessTab="resumo";
  var result=document.getElementById("result");
  if(result){result.innerHTML="";result.style.display="none"}
  var tabs=document.getElementById("processTabs");
  if(tabs)tabs.classList.remove("visible");
  ["qaPanel","notificationPanel","docsPanel","privacyPanel","reportPanel"].forEach(function(id){
    var x=document.getElementById(id);
    if(x){x.classList.remove("tab-visible");x.style.display="none"}
  });
  var vals={dashDocs:"0",dashEvidence:"0",dashPending:"0",dashStage:"Não iniciada"};
  Object.keys(vals).forEach(function(id){var x=document.getElementById(id);if(x)x.textContent=vals[id]});
}

function prepararInicioModulo(){
  limparEstadoAnaliseVisual();
  var main=document.querySelector(".system-main");
  if(main)main.classList.remove("new-process-mode");

  var empty=document.getElementById("systemEmpty");
  if(empty)empty.style.display="flex";

  // O upload não aparece solto abaixo da dobra: só abre quando o usuário escolhe Novo processo.
  var upload=document.getElementById("uploadPanel");
  if(upload){
    upload.style.display="none";
    upload.classList.remove("new-process-card");
  }

  var st=document.getElementById("processStatus");
  if(st){st.textContent="Sem processo";st.classList.remove("ready")}

  var title=document.getElementById("dashboardTitle");
  if(title)title.textContent="Processo ainda não carregado";
  var ds=document.getElementById("dashboardSub");
  if(ds)ds.textContent="Clique em “+ Novo processo” para carregar os autos ou use o processo modelo.";

  document.querySelectorAll(".side-item").forEach(function(x){x.classList.toggle("active",x.dataset.tab==="resumo")});
  document.querySelectorAll(".process-tab").forEach(function(x){x.classList.toggle("active",x.dataset.tab==="resumo")});
}

function configurarCardNovoProcesso(){
  var upload=document.getElementById("uploadPanel");
  var main=document.querySelector(".system-main");
  if(!upload||!main)return;

  // Coloca o formulário no topo da área de trabalho, exatamente onde o usuário está olhando.
  var first=main.firstElementChild;
  if(first!==upload)main.insertBefore(upload,first);

  upload.classList.add("new-process-card");
  upload.style.display="block";

  var head=upload.querySelector(".panel-head");
  if(head){
    var title=head.querySelector(".title");
    var desc=head.querySelector(".desc");
    var kicker=head.querySelector(".kicker");
    if(kicker)kicker.textContent="Novo processo";
    if(title)title.textContent="Carregue os autos";
    if(desc)desc.textContent="Selecione um ou mais PDFs para iniciar a análise em "+(moduleLabels[selectedModule]||selectedModule)+".";
  }

  var old=upload.querySelector(".new-process-hint");
  if(!old){
    var hint=document.createElement("div");
    hint.className="new-process-hint";
    hint.innerHTML='<div><strong>Novo processo · '+esc(moduleLabels[selectedModule]||selectedModule)+'</strong><span>Os documentos serão analisados e organizados no fluxo deste módulo.</span></div><button class="new-process-cancel" onclick="cancelarNovoProcesso()">Cancelar</button>';
    var box=upload.querySelector(".uploadbox");
    if(box)upload.insertBefore(hint,box);
    else upload.insertBefore(hint,upload.firstChild);
  }
}

async function novoProcessoModulo(){
  analysisId=analysisId||localStorage.getItem("fiscaliza_analysis_id");
  if(analysisId){try{await fetch("/api/analysis/"+analysisId,{method:"DELETE"})}catch(e){}}
  analysisId=null;
  localStorage.removeItem("fiscaliza_analysis_id");

  var fi=document.getElementById("files");
  if(fi)fi.value="";
  var ans=document.getElementById("answer");
  if(ans)ans.style.display="none";

  limparEstadoAnaliseVisual();

  var main=document.querySelector(".system-main");
  if(main)main.classList.add("new-process-mode");

  var empty=document.getElementById("systemEmpty");
  if(empty)empty.style.display="none";

  configurarCardNovoProcesso();

  var st=document.getElementById("processStatus");
  if(st){st.textContent="Novo processo";st.classList.remove("ready")}

  // Não desce a página. O conteúdo é substituído no próprio ponto da tela.
  var work=document.querySelector(".workspace-head");
  if(work){
    var top=work.getBoundingClientRect().top;
    if(top<0||top>150)work.scrollIntoView({behavior:"smooth",block:"start"});
  }
}

function cancelarNovoProcesso(){
  var upload=document.getElementById("uploadPanel");
  if(upload){
    upload.style.display="none";
    upload.classList.remove("new-process-card");
    var hint=upload.querySelector(".new-process-hint");
    if(hint)hint.remove();
  }
  var main=document.querySelector(".system-main");
  if(main)main.classList.remove("new-process-mode");
  var empty=document.getElementById("systemEmpty");
  if(empty)empty.style.display="flex";
  var st=document.getElementById("processStatus");
  if(st)st.textContent="Sem processo";
}

var _oldAtivarProcessoNoSistemaV71=ativarProcessoNoSistema;
ativarProcessoNoSistema=function(a){
  var main=document.querySelector(".system-main");
  if(main)main.classList.remove("new-process-mode");
  var upload=document.getElementById("uploadPanel");
  if(upload){
    upload.classList.remove("new-process-card");
    var hint=upload.querySelector(".new-process-hint");
    if(hint)hint.remove();
  }
  _oldAtivarProcessoNoSistemaV71(a);
};
"""
HTML=HTML.replace("</script>",_new_process_js+"\n</script>",1)
HTML=HTML.replace("VERSÃO 7.0 · EDIÇÃO COMERCIAL","VERSÃO 7.1 · NOVO PROCESSO DIRETO")


# --- Acabamento comercial completo v7.2 ---
# Mantém menu lateral + abas horizontais, conforme opção do produto.
# Acrescenta perfil do processo, recentes da sessão e personalização institucional.

def _clean_profile_value(value):
    v=re.sub(r"\s+"," ",str(value or "")).strip(" \n\t:;-")
    if not v or v.startswith("["):return ""
    return v[:160]

def _derive_interested(pages,module):
    if module=="penalizacao":
        try:
            v=_validated_metadata(pages).get("empresa")
            if v and not str(v).startswith("["):return _clean_profile_value(v)
        except Exception:pass
    flat="\n".join((p.get("text") or "")[:2500] for p in pages[:12])
    patterns=[
        r"(?:Interessad[oa]|Requerente|Contribuinte|Servidor(?:a)?|Contratada|Empresa)\s*[:\-]\s*([^\n]{3,140})",
        r"CONTRATADA\s*:\s*([^\n]{3,140})"
    ]
    for pat in patterns:
        m=re.search(pat,flat,flags=re.I)
        if m:
            v=re.split(r"\b(?:CNPJ|CPF|Objeto|Assunto|Processo)\b",m.group(1),maxsplit=1,flags=re.I)[0]
            v=_clean_profile_value(v)
            if v:return v
    return ""

def _derive_process_profile(pages,module,process_number="",interested="",unit=""):
    number=_clean_profile_value(process_number)
    if not number:
        try:
            if module=="penalizacao":
                md=_validated_metadata(pages)
                number=_clean_profile_value(md.get("penalizacao"))
                if not number:number=_clean_profile_value(md.get("origem"))
            else:
                number=_clean_profile_value(_module_process_number(pages,module))
        except Exception:pass
    person=_clean_profile_value(interested) or _derive_interested(pages,module)
    unit_value=_clean_profile_value(unit)
    doc_ids=sorted(set(p.get("document_id") for p in pages if p.get("document_id")))
    return {
        "number":number or "Número não identificado",
        "interested":person or "Interessado não identificado",
        "unit":unit_value or "Unidade não informada",
        "pages":len(pages),
        "documents":len(doc_ids),
        "module":module,
        "module_label":MODULES.get(module,MODULES["geral"])["label"]
    }

async def analyze_v72(
    files:List[UploadFile]=File(...),
    module:str="penalizacao",
    process_number:str="",
    interested:str="",
    unit:str=""
):
    pages=[];ocr=0;names=[]
    for f in files:
        if not f.filename.lower().endswith(".pdf"):continue
        pp,oo=extract_pdf(await f.read(),f.filename)
        pages.extend(pp);ocr+=oo;names.append(f.filename)
    if not pages:raise HTTPException(400,"Envie pelo menos um PDF.")
    _assign_document_ids(pages)
    a=analyze_pages(pages)
    a=_module_overlay(pages,a,module)
    a=_enrich_doc_refs(a,pages)
    profile=_derive_process_profile(pages,module,process_number,interested,unit)
    a["process_profile"]=profile
    aid=uuid.uuid4().hex
    ANALYSES[aid]={
        "pages":pages,"analysis":a,"created":datetime.utcnow().isoformat(),
        "module":module,"profile":profile,"files":names
    }
    return {
        "analysis_id":aid,"files":names,"pages":len(pages),"ocr_pages":ocr,
        "module":module,"profile":profile,"analysis":a
    }

app.router.routes=[
    r for r in app.router.routes
    if not (getattr(r,"path",None)=="/api/analyze" and "POST" in getattr(r,"methods",set()))
]
app.add_api_route("/api/analyze",analyze_v72,methods=["POST"])

@app.get("/api/analysis/{analysis_id}")
def get_analysis_v72(analysis_id):
    item=ANALYSES.get(analysis_id)
    if not item:raise HTTPException(404,"A análise expirou ou foi excluída.")
    return {
        "analysis_id":analysis_id,
        "analysis":item.get("analysis",{}),
        "profile":item.get("profile",{}),
        "module":item.get("module","geral"),
        "files":item.get("files",[]),
        "created":item.get("created")
    }

app.version="7.2"

_premium_css = """
/* HOME: menos landing page, mais produto */
.home-commercial-hero{
  min-height:0!important;padding:22px 24px!important;border-radius:16px!important;
  grid-template-columns:minmax(0,1.55fr) minmax(300px,.45fr)!important;gap:18px!important
}
.home-commercial-hero h1{font-size:28px!important;line-height:1.12!important;margin-top:10px!important}
.home-commercial-hero p{font-size:12.5px!important;line-height:1.52!important;margin-top:8px!important}
.home-badge{font-size:9px!important;padding:5px 8px!important}
.home-benefits{margin-top:13px!important;gap:6px!important}
.home-benefits span{font-size:9.5px!important;padding:5px 8px!important}
.home-side-card{padding:15px 16px!important;border-radius:13px!important}
.home-side-card strong{font-size:18px!important}
.home-side-card p{font-size:10.5px!important;margin-top:5px!important}
.home-stats{margin-top:11px!important}
.home-stat{padding:7px 8px!important}.home-stat b{font-size:15px!important}.home-stat span{font-size:8px!important}

.module-panel.home-only{padding:18px 20px 20px!important;border-radius:16px!important}
.module-toolbar{margin-bottom:12px!important}
.module-toolbar-copy h2{font-size:19px!important}
.module-toolbar-copy p{font-size:11px!important}
.screen-home .module-card{min-height:112px!important;padding:14px!important}
.screen-home .module-card.active{padding:14px!important}
.screen-home .module-icon{
  width:34px!important;height:34px!important;margin-bottom:8px!important;border-radius:9px!important;
  font-size:10px!important;letter-spacing:.02em!important
}
.screen-home .module-name{font-size:12.5px!important}
.screen-home .module-desc{font-size:10px!important;margin-top:3px!important;line-height:1.4!important}
.screen-home .module-card:after{bottom:10px!important;right:12px!important;font-size:8.5px!important}
.module-category{
  position:absolute;top:13px;right:13px;border-radius:999px;padding:3px 6px;
  background:#f2f6f8;color:#728496;font-size:7.5px;font-weight:850;letter-spacing:.04em;text-transform:uppercase
}

/* PROCESSOS RECENTES */
.recent-panel{margin-top:14px;background:#fff;border:1px solid var(--line);border-radius:15px;padding:17px 19px;box-shadow:0 6px 18px rgba(15,47,73,.045)}
.recent-head{display:flex;justify-content:space-between;gap:18px;align-items:end;margin-bottom:10px}
.recent-head h3{margin:0;color:var(--navy);font-size:15px}.recent-head p{margin:3px 0 0;color:var(--muted);font-size:9.5px}
.recent-list{display:grid;gap:7px}
.recent-row{
  display:grid;grid-template-columns:minmax(180px,1.15fr) minmax(160px,1fr) 160px 130px auto;
  gap:12px;align-items:center;padding:10px 11px;border:1px solid #e1e8ee;border-radius:10px;background:#fbfcfd
}
.recent-row:hover{border-color:#bccbd7;background:#fff}
.recent-main b{display:block;color:var(--navy);font-size:11px}.recent-main span,.recent-cell{display:block;color:var(--muted);font-size:9px}
.recent-status{display:inline-flex;align-items:center;gap:5px;color:var(--teal);font-size:9px;font-weight:850}
.recent-status:before{content:"";width:6px;height:6px;border-radius:50%;background:var(--teal)}
.recent-open{border:0;background:#eef4f7;color:var(--navy);padding:7px 9px;border-radius:8px;font-size:9px;font-weight:850;cursor:pointer}
.recent-open:hover{background:#e2edf2}
.recent-empty{padding:12px;color:var(--muted);font-size:10px;border:1px dashed var(--line);border-radius:10px;text-align:center}

/* ESTADO VAZIO */
.system-main:not(.process-loaded) .module-dashboard{display:none!important}
.system-empty{
  padding:28px!important;min-height:190px;align-items:center!important;
  border:1px solid var(--line)!important;background:#fff!important
}
.empty-launch{width:100%;text-align:center}
.empty-launch .empty-icon{margin:0 auto 11px}
.empty-launch h3{font-size:19px!important;margin:0!important}
.empty-launch p{font-size:11px!important;max-width:620px!important;margin:6px auto 16px!important}
.empty-actions{display:flex;justify-content:center;gap:8px;flex-wrap:wrap}

/* PROCESSO ABERTO: cabeçalho e KPIs compactos */
.workspace-head.process-open{padding:13px 16px!important}
.workspace-head.process-open .workspace-title small{font-size:8.5px!important}
.workspace-head.process-open .workspace-title strong{font-size:18px!important}
.workspace-head.process-open .workspace-title span{font-size:10px!important}
.process-context{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.process-context span{
  border:1px solid var(--line);background:#f8fafc;color:#64778a;border-radius:999px;
  padding:3px 7px;font-size:8px;font-weight:750
}
.process-context span.module{border-color:#c6e4df;background:#eff9f7;color:var(--teal)}
.system-main.process-loaded .module-dashboard{display:block!important;margin-bottom:9px!important}
.system-main.process-loaded .dashboard-top{display:none!important}
.system-main.process-loaded .dashboard-metrics{grid-template-columns:repeat(4,1fr)!important;gap:7px!important}
.system-main.process-loaded .dash-metric{
  padding:9px 11px!important;border-radius:9px!important;min-height:62px;
  display:grid;grid-template-columns:auto 1fr;column-gap:7px;align-content:center
}
.system-main.process-loaded .dash-metric small{font-size:8px!important;grid-column:1/-1}
.system-main.process-loaded .dash-metric strong{font-size:18px!important;margin-top:0!important}
.system-main.process-loaded .dash-metric strong.text{font-size:10.5px!important;white-space:normal!important;line-height:1.25}
.system-main.process-loaded .dash-metric .mini{font-size:8px!important;align-self:center;margin:0!important}
.process-tabs{margin-bottom:10px!important}

/* NOVO PROCESSO COM METADADOS */
.new-process-fields{
  display:grid;grid-template-columns:1fr 1.25fr 1fr;gap:9px;margin-bottom:11px
}
.np-field label{display:block;color:#65788b;font-size:8.5px;font-weight:850;text-transform:uppercase;letter-spacing:.05em;margin:0 0 4px 2px}
.np-field input{
  width:100%;border:1px solid var(--line);background:#fff;color:var(--ink);
  border-radius:9px;padding:9px 10px;font-size:11px;outline:none
}
.np-field input:focus{border-color:#78afa8;box-shadow:0 0 0 3px rgba(11,143,130,.08)}

/* CONFIGURAÇÃO INSTITUCIONAL */
.top-actions{display:flex;align-items:center;gap:8px}
.config-btn{
  border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#dce7ee;
  border-radius:999px;padding:7px 10px;font-size:9.5px;font-weight:750;cursor:pointer
}
.config-btn:hover{background:rgba(255,255,255,.10);color:#fff}
.settings-overlay{
  position:fixed;inset:0;background:rgba(5,20,33,.48);z-index:200;display:none;align-items:center;justify-content:center;padding:22px
}
.settings-overlay.open{display:flex}
.settings-card{width:min(580px,100%);background:#fff;border-radius:16px;box-shadow:0 25px 70px rgba(8,28,43,.25);padding:22px}
.settings-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:16px}
.settings-head h3{margin:0;color:var(--navy);font-size:18px}.settings-head p{margin:4px 0 0;color:var(--muted);font-size:10px}
.settings-close{border:0;background:#f0f4f7;border-radius:8px;width:30px;height:30px;cursor:pointer;color:var(--navy);font-weight:900}
.settings-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.settings-grid .wide{grid-column:1/-1}
.settings-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}
.settings-note{margin-top:10px;color:var(--muted);font-size:8.5px}

@media(max-width:900px){
  .home-commercial-hero{grid-template-columns:1fr!important}
  .recent-row{grid-template-columns:1fr auto}.recent-cell.hide-mobile{display:none}
  .new-process-fields{grid-template-columns:1fr}
}
"""
HTML=HTML.replace("</style>",_premium_css+"</style>",1)

# Envia os metadados opcionais preenchidos no Novo processo.
HTML=HTML.replace(
    'var r=await fetch("/api/analyze?module="+encodeURIComponent(selectedModule),{method:"POST",body:fd});var d=await r.json();',
    '''var npNumber=(document.getElementById("newProcessNumber")||{}).value||"";
    var npInterested=(document.getElementById("newProcessInterested")||{}).value||"";
    var npUnit=(document.getElementById("newProcessUnit")||{}).value||"";
    var analyzeUrl="/api/analyze?module="+encodeURIComponent(selectedModule)+"&process_number="+encodeURIComponent(npNumber)+"&interested="+encodeURIComponent(npInterested)+"&unit="+encodeURIComponent(npUnit);
    var r=await fetch(analyzeUrl,{method:"POST",body:fd});var d=await r.json();''',
    1
)

_premium_js = r"""
var recentProcessCache={};

var commercialModuleMeta={
  penalizacao:{code:"PC",category:"Responsabilização"},
  fiscalizacao:{code:"FC",category:"Gestão contratual"},
  reequilibrio:{code:"RE",category:"Gestão contratual"},
  rescisao:{code:"EX",category:"Gestão contratual"},
  sindicancia:{code:"SI",category:"Apuração interna"},
  disciplinar:{code:"PD",category:"Responsabilização interna"}
};

function carregarConfigInstitucional(){
  var base={org:"Prefeitura Municipal",unit:"Unidade administrativa",responsible:"",email:""};
  try{
    var x=JSON.parse(localStorage.getItem("fiscaliza_org_config")||"{}");
    Object.keys(x||{}).forEach(function(k){if(x[k])base[k]=x[k]});
  }catch(e){}
  return base;
}
function aplicarConfigInstitucional(){
  var cfg=carregarConfigInstitucional();
  var brandSub=document.querySelector(".brandtext span");
  if(brandSub)brandSub.textContent=cfg.org+" · "+cfg.unit;
}
function abrirConfiguracoes(){
  var cfg=carregarConfigInstitucional();
  ["Org","Unit","Responsible","Email"].forEach(function(k){
    var el=document.getElementById("cfg"+k);
    if(el)el.value=cfg[k.charAt(0).toLowerCase()+k.slice(1)]||"";
  });
  var ov=document.getElementById("settingsOverlay");if(ov)ov.classList.add("open");
}
function fecharConfiguracoes(){var ov=document.getElementById("settingsOverlay");if(ov)ov.classList.remove("open")}
function salvarConfiguracoes(){
  var cfg={
    org:(document.getElementById("cfgOrg").value||"").trim()||"Prefeitura Municipal",
    unit:(document.getElementById("cfgUnit").value||"").trim()||"Unidade administrativa",
    responsible:(document.getElementById("cfgResponsible").value||"").trim(),
    email:(document.getElementById("cfgEmail").value||"").trim()
  };
  localStorage.setItem("fiscaliza_org_config",JSON.stringify(cfg));
  aplicarConfigInstitucional();fecharConfiguracoes();
}

function instalarConfiguracoes(){
  if(document.getElementById("settingsOverlay"))return;
  var inner=document.querySelector(".topbar-inner");
  if(inner){
    var current=inner.querySelector(".live")||inner.querySelector(".topmeta");
    var wrap=document.createElement("div");wrap.className="top-actions";
    var btn=document.createElement("button");btn.className="config-btn";btn.textContent="⚙ Configurações";btn.onclick=abrirConfiguracoes;
    if(current){current.parentNode.insertBefore(wrap,current);wrap.appendChild(btn);wrap.appendChild(current)}
    else {wrap.appendChild(btn);inner.appendChild(wrap)}
  }
  var ov=document.createElement("div");ov.id="settingsOverlay";ov.className="settings-overlay";
  ov.innerHTML='<div class="settings-card"><div class="settings-head"><div><h3>Configuração institucional</h3><p>Personalize a demonstração para o órgão. As preferências ficam apenas neste navegador.</p></div><button class="settings-close" onclick="fecharConfiguracoes()">×</button></div>'+
  '<div class="settings-grid">'+
  '<div class="np-field"><label>Órgão / Município</label><input id="cfgOrg" placeholder="Ex.: Prefeitura Municipal"></div>'+
  '<div class="np-field"><label>Unidade</label><input id="cfgUnit" placeholder="Ex.: Comissão de Penalização"></div>'+
  '<div class="np-field"><label>Responsável</label><input id="cfgResponsible" placeholder="Nome do responsável"></div>'+
  '<div class="np-field"><label>E-mail institucional</label><input id="cfgEmail" placeholder="unidade@municipio.gov.br"></div>'+
  '</div><div class="settings-note">Esta versão demonstrativa não grava essas configurações em banco de dados; elas ficam no armazenamento local do navegador.</div>'+
  '<div class="settings-actions"><button class="btn btn-blue" onclick="fecharConfiguracoes()">Cancelar</button><button class="btn btn-primary" onclick="salvarConfiguracoes()">Salvar configuração</button></div></div>';
  ov.addEventListener("click",function(e){if(e.target===ov)fecharConfiguracoes()});
  document.body.appendChild(ov);
  aplicarConfigInstitucional();
}

function deixarHomeMaisProduto(){
  var hero=document.querySelector(".home-commercial-hero");
  if(hero&&!hero.dataset.premium){
    hero.dataset.premium="1";
    var copy=hero.querySelector(".home-copy");
    if(copy){
      var h=copy.querySelector("h1");if(h)h.textContent="Inteligência processual com evidência rastreável.";
      var p=copy.querySelector("p");if(p)p.textContent="Organize autos, acompanhe pendências e produza documentos assistidos em fluxos especializados para gestão contratual e responsabilização administrativa.";
    }
    var side=hero.querySelector(".home-side-card");
    if(side){
      side.innerHTML='<div><small>Fluxo de trabalho</small><strong>Do documento à decisão humana</strong><p>Leitura → classificação → evidência → revisão → documento assistido.</p></div>'+
      '<div class="home-stats"><div class="home-stat"><b>6</b><span>fluxos</span></div><div class="home-stat"><b>ID + p.</b><span>rastreabilidade</span></div><div class="home-stat"><b>Humana</b><span>decisão final</span></div></div>';
    }
  }

  document.querySelectorAll(".module-card").forEach(function(card){
    var key=card.getAttribute("data-module"),meta=commercialModuleMeta[key];
    if(!meta)return;
    var icon=card.querySelector(".module-icon");if(icon)icon.textContent=meta.code;
    if(!card.querySelector(".module-category")){
      var tag=document.createElement("span");tag.className="module-category";tag.textContent=meta.category;card.appendChild(tag);
    }
  });
  instalarProcessosRecentes();
  renderProcessosRecentes();
}

function recentStore(){
  try{return JSON.parse(sessionStorage.getItem("fiscaliza_recent_processes")||"[]")}catch(e){return []}
}
function setRecentStore(items){
  try{sessionStorage.setItem("fiscaliza_recent_processes",JSON.stringify(items.slice(0,5)))}catch(e){}
}
function salvarProcessoRecente(a){
  if(!analysisId||!a)return;
  var p=a.process_profile||{};
  var item={
    id:analysisId,module:a.module_key||selectedModule,module_label:a.module_label||moduleLabels[selectedModule]||selectedModule,
    number:p.number||"Processo analisado",interested:p.interested||"Interessado não identificado",
    unit:p.unit||"Unidade não informada",stage:(a.next_action&&a.next_action.stage)||"Analisado",
    updated:new Date().toISOString()
  };
  var list=recentStore().filter(function(x){return x.id!==item.id});
  list.unshift(item);setRecentStore(list);
  try{
    recentProcessCache[item.id]={analysis:a,html:(document.getElementById("result")||{}).innerHTML||""};
    sessionStorage.setItem("fiscaliza_cache_"+item.id,JSON.stringify({analysis:a,html:recentProcessCache[item.id].html}));
  }catch(e){}
  renderProcessosRecentes();
}
function instalarProcessosRecentes(){
  var home=document.getElementById("screenHome"),modulePanel=document.querySelector(".module-panel.home-only");
  if(!home||!modulePanel||document.getElementById("recentPanel"))return;
  var p=document.createElement("section");p.id="recentPanel";p.className="recent-panel";
  p.innerHTML='<div class="recent-head"><div><div class="kicker">Continuidade do trabalho</div><h3>Processos recentes</h3><p>Histórico temporário desta sessão de demonstração.</p></div></div><div id="recentList" class="recent-list"></div>';
  modulePanel.insertAdjacentElement("afterend",p);
}
function renderProcessosRecentes(){
  var listEl=document.getElementById("recentList");if(!listEl)return;
  var list=recentStore();
  if(!list.length){listEl.innerHTML='<div class="recent-empty">Quando você analisar um processo, ele aparecerá aqui para acesso rápido durante esta sessão.</div>';return}
  listEl.innerHTML=list.map(function(x){
    var dt=new Date(x.updated);var when=isNaN(dt)?"":dt.toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"});
    return '<div class="recent-row">'+
      '<div class="recent-main"><b>'+esc(x.number)+'</b><span>'+esc(x.interested)+'</span></div>'+
      '<div class="recent-cell hide-mobile">'+esc(x.module_label)+'</div>'+
      '<div class="recent-cell hide-mobile">'+esc(x.stage)+'</div>'+
      '<div><span class="recent-status">Sessão atual · '+esc(when)+'</span></div>'+
      '<button class="recent-open" onclick="abrirProcessoRecente(\''+esc(x.id)+'\')">Abrir</button></div>';
  }).join("");
}
function abrirProcessoRecente(id){
  var list=recentStore(),entry=list.find(function(x){return x.id===id});
  if(!entry)return;
  var cached=recentProcessCache[id];
  if(!cached){
    try{cached=JSON.parse(sessionStorage.getItem("fiscaliza_cache_"+id)||"null")}catch(e){}
  }
  if(!cached||!cached.analysis){
    alert("O detalhamento deste processo não está mais disponível nesta sessão. Reanalise os autos para continuar.");
    return;
  }
  abrirTelaModulo(entry.module,null,true);
  setTimeout(function(){
    analysisId=id;localStorage.setItem("fiscaliza_analysis_id",id);
    var result=document.getElementById("result");
    if(result)result.innerHTML=cached.html||"";
    ajustarResultadoModulo(cached.analysis);
  },160);
}

function garantirEstadoVazioProfissional(){
  var empty=document.getElementById("systemEmpty");
  if(!empty||empty.dataset.professional==="1")return;
  empty.dataset.professional="1";
  empty.innerHTML='<div class="empty-launch"><div class="empty-icon">＋</div><h3>Nenhum processo aberto</h3><p>Inicie um novo processo para carregar os autos ou use um caso fictício pronto para conhecer este fluxo.</p><div class="empty-actions"><button class="btn btn-primary" onclick="novoProcessoModulo()">+ Novo processo</button><button class="btn btn-blue" onclick="testarDemo()">Usar processo modelo</button></div></div>';
}

function adicionarCamposNovoProcesso(){
  var upload=document.getElementById("uploadPanel");
  if(!upload||upload.querySelector(".new-process-fields"))return;
  var fields=document.createElement("div");fields.className="new-process-fields";
  fields.innerHTML='<div class="np-field"><label>Número do processo <span style="font-weight:500;text-transform:none">(opcional)</span></label><input id="newProcessNumber" placeholder="Ex.: 1-1234/2026"></div>'+
    '<div class="np-field"><label>Interessado / empresa <span style="font-weight:500;text-transform:none">(opcional)</span></label><input id="newProcessInterested" placeholder="Nome do interessado"></div>'+
    '<div class="np-field"><label>Unidade responsável <span style="font-weight:500;text-transform:none">(opcional)</span></label><input id="newProcessUnit" placeholder="Ex.: Comissão / Secretaria"></div>';
  var box=upload.querySelector(".uploadbox");
  if(box)upload.insertBefore(fields,box);
}

function atualizarCabecalhoProfissional(a){
  var profile=a&&a.process_profile;if(!profile)return;
  var head=document.querySelector(".workspace-head");if(!head)return;
  head.classList.add("process-open");
  var title=document.getElementById("workspaceModuleTitle");
  var desc=document.getElementById("workspaceModuleDesc");
  var titleBox=head.querySelector(".workspace-title");
  if(title)title.textContent=profile.number;
  if(desc)desc.textContent=profile.interested+" · "+profile.unit;
  if(titleBox){
    var small=titleBox.querySelector("small");
    if(small)small.textContent="Processo aberto";
    var old=titleBox.querySelector(".process-context");if(old)old.remove();
    var ctx=document.createElement("div");ctx.className="process-context";
    ctx.innerHTML='<span class="module">'+esc(profile.module_label||a.module_label||"Módulo")+'</span><span>'+esc(profile.pages||0)+' páginas</span><span>'+esc(profile.documents||0)+' documentos</span><span>Analisado</span>';
    titleBox.appendChild(ctx);
  }
}
function restaurarCabecalhoModulo(){
  var head=document.querySelector(".workspace-head");if(head)head.classList.remove("process-open");
  var title=document.getElementById("workspaceModuleTitle"),desc=document.getElementById("workspaceModuleDesc");
  var meta=commercialModuleMeta[selectedModule]||{};
  if(title)title.textContent=moduleLabels[selectedModule]||selectedModule;
  var descriptions={
    penalizacao:"Responsabilização de fornecedor, contraditório, defesa, sanção e decisão.",
    fiscalizacao:"Execução, entregas, ocorrências, fiscalização, medições e providências.",
    reequilibrio:"Pedido, custos, justificativas, pareceres e decisão.",
    rescisao:"Motivação, comunicação, contraditório, parecer e decisão de extinção.",
    sindicancia:"Fato investigado, diligências, provas, relatório e encaminhamento.",
    disciplinar:"Instauração, citação, instrução, defesa, relatório e julgamento."
  };
  if(desc)desc.textContent=descriptions[selectedModule]||"Análise administrativa assistida.";
  var tb=head&&head.querySelector(".workspace-title");if(tb){
    var small=tb.querySelector("small");if(small)small.textContent="Área de trabalho";
    var ctx=tb.querySelector(".process-context");if(ctx)ctx.remove();
  }
}

var _oldPrepararHomeComercialV72=prepararHomeComercial;
prepararHomeComercial=function(){
  _oldPrepararHomeComercialV72();
  setTimeout(deixarHomeMaisProduto,0);
};

var _oldGarantirSistemaWorkspaceV72=garantirSistemaWorkspace;
garantirSistemaWorkspace=function(){
  _oldGarantirSistemaWorkspaceV72();
  garantirEstadoVazioProfissional();
};

var _oldConfigurarCardNovoProcessoV72=configurarCardNovoProcesso;
configurarCardNovoProcesso=function(){
  _oldConfigurarCardNovoProcessoV72();
  adicionarCamposNovoProcesso();
};

# placeholder
"""
# JS cannot contain Python comment marker; normalize it before insertion.
_premium_js=_premium_js.replace("\n# placeholder\n","\n")

# Latest Nuevo Processo behavior: keeps earlier analyses alive until TTL so recent-session access remains possible.
_premium_js += r"""
novoProcessoModulo=async function(){
  analysisId=null;
  localStorage.removeItem("fiscaliza_analysis_id");
  var fi=document.getElementById("files");if(fi)fi.value="";
  var ans=document.getElementById("answer");if(ans)ans.style.display="none";
  limparEstadoAnaliseVisual();

  var main=document.querySelector(".system-main");
  if(main){main.classList.add("new-process-mode");main.classList.remove("process-loaded")}
  var empty=document.getElementById("systemEmpty");if(empty)empty.style.display="none";
  restaurarCabecalhoModulo();
  configurarCardNovoProcesso();
  ["newProcessNumber","newProcessInterested","newProcessUnit"].forEach(function(id){var x=document.getElementById(id);if(x)x.value=""});
  var st=document.getElementById("processStatus");if(st){st.textContent="Novo processo";st.classList.remove("ready")}
};

var _oldPrepararInicioModuloV72=prepararInicioModulo;
prepararInicioModulo=function(){
  _oldPrepararInicioModuloV72();
  var main=document.querySelector(".system-main");if(main)main.classList.remove("process-loaded");
  restaurarCabecalhoModulo();
  garantirEstadoVazioProfissional();
};

var _oldAtivarProcessoNoSistemaV72=ativarProcessoNoSistema;
ativarProcessoNoSistema=function(a){
  _oldAtivarProcessoNoSistemaV72(a);
  var main=document.querySelector(".system-main");if(main)main.classList.add("process-loaded");
  atualizarCabecalhoProfissional(a);
  salvarProcessoRecente(a);
};

var _oldVoltarAosModulosV72=voltarAosModulos;
voltarAosModulos=function(push){
  _oldVoltarAosModulosV72(push);
  setTimeout(function(){deixarHomeMaisProduto();renderProcessosRecentes()},0);
};

document.addEventListener("DOMContentLoaded",function(){
  setTimeout(function(){
    instalarConfiguracoes();
    deixarHomeMaisProduto();
    garantirEstadoVazioProfissional();
  },180);
});
"""
HTML=HTML.replace("</script>",_premium_js+"\n</script>",1)

HTML=HTML.replace("VERSÃO 7.1 · NOVO PROCESSO DIRETO","VERSÃO 7.2 · ACABAMENTO COMERCIAL")


# --- Quantidade contextualizada v7.3 ---
# Regra: nunca exibir número isolado quando os autos trazem a unidade/objeto.
# Ex.: "500 kits de higiene bucal", e não apenas "500".

def _clean_quantity_object(text):
    s=re.sub(r"\s+"," ",str(text or "")).strip(" .,:;-")
    if not s:return ""
    # Interrompe quando começa outra informação típica do documento.
    s=re.split(
        r"\b(?:ao valor|no valor|valor unit[aá]rio|valor total|marca|prazo|contrato|ata de registro|preg[aã]o|nota de empenho|local de entrega|conforme|referente|vinculad[oa])\b",
        s,maxsplit=1,flags=re.I
    )[0].strip(" .,:;-")
    # Limita para não transformar o card em parágrafo.
    words=s.split()
    if len(words)>9:s=" ".join(words[:9])
    return s

def _quantity_context(pages):
    ordered=sorted(pages,key=lambda p:(0 if strong_type(p)=="contrato" else 1,p["page"]))
    patterns=[
        # "fornecimento de 500 kits de higiene bucal"
        re.compile(r"(?:fornecimento|aquisi[cç][aã]o)\s+(?:de\s+)?(\d{1,7})\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9ºª./\-]*(?:\s+[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9ºª./\-]*){0,8})",re.I),
        # "500 kits de higiene bucal"
        re.compile(r"\b(\d{1,7})\s+((?:kits?|unidades?|itens?|caixas?|pacotes?|frascos?|servi[cç]os?|equipamentos?|aparelhos?|pe[cç]as?|metros?|litros?|quilos?|kg)\b(?:\s+(?:de|do|da|dos|das)\s+[A-Za-zÀ-ÿ0-9ºª./\-]+(?:\s+[A-Za-zÀ-ÿ0-9ºª./\-]+){0,6})?)",re.I),
        # "quantidade total: 500 kits"
        re.compile(r"(?:quantidade total|quantidade contratada|quantidade prevista|quantidade)\s*[:\-]?\s*(\d{1,7})\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9ºª./\-]*(?:\s+[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9ºª./\-]*){0,7})?",re.I)
    ]
    for p in ordered:
        raw=re.sub(r"\s+"," ",p.get("text") or "")
        z=norm(raw)
        for rx in patterns:
            for m in rx.finditer(raw):
                try:value=int(m.group(1))
                except Exception:continue
                if not (1<=value<=10000000):continue
                ctx=norm(raw[max(0,m.start()-130):min(len(raw),m.end()+190)])
                if any(b in ctx for b in ["por viagem","metade da quantidade","50% da quantidade","estimativa de transporte","restantes"]):
                    continue
                obj=_clean_quantity_object(m.group(2) if m.lastindex and m.lastindex>=2 else "")
                # Evita capturar palavras que não são unidade/objeto.
                if obj and norm(obj).split()[0] in ["ao","no","na","com","para","conforme","referente"]:
                    obj=""
                display=(str(value)+" "+obj).strip() if obj else str(value)
                refs=_page_doc_refs(pages,p.get("file"),[p.get("page")]) if "_page_doc_refs" in globals() else []
                source={"file":p["file"],"page":p["page"]}
                if refs:
                    source["document_id"]=refs[0].get("document_id")
                    source["source_document_id"]=refs[0].get("source_document_id")
                return {
                    "value":str(value),
                    "unit_object":obj,
                    "display":display,
                    "source":source,
                    "context":clip(raw[max(0,m.start()-90):min(len(raw),m.end()+140)],300)
                }
    return {"value":"Não identificado com segurança","unit_object":"","display":"Não identificado com segurança","source":None,"context":""}

def total_quantity(pages):
    return _quantity_context(pages)

_old_module_overlay_v73=_module_overlay
def _module_overlay(pages,a,module):
    a=_old_module_overlay_v73(pages,a,module)
    q=a.get("quantity") or {}
    qdisplay=q.get("display") or q.get("value") or "Não identificado com segurança"
    if module=="penalizacao":
        # Resumo: substitui o valor numérico isolado pela descrição contextual.
        for sm in a.get("module_summary",[]) or []:
            if norm(sm.get("label",""))=="quantidade total":
                sm["value"]=qdisplay
                sm["ok"]="nao identificado" not in norm(qdisplay)
        # Matriz: mesma regra, preservando fonte/página.
        for row in a.get("module_matrix",[]) or []:
            if "quantidade" in norm(row.get("question","")):
                row["answer"]=qdisplay
                row["ok"]="nao identificado" not in norm(qdisplay)
                if q.get("source"):
                    row["pages"]=[q["source"].get("page")]
        # Rastreabilidade: evita "Quantidade total: 500".
        for tr in a.get("traceability",[]) or []:
            if norm(tr.get("claim","")).startswith("quantidade total"):
                tr["claim"]="Quantidade total: "+qdisplay
    return a

_old_enrich_doc_refs_v73=_enrich_doc_refs
def _enrich_doc_refs(a,pages):
    a=_old_enrich_doc_refs_v73(a,pages)
    q=a.get("quantity") or {}
    if q.get("source"):
        refs=_page_doc_refs(pages,q["source"].get("file"),[q["source"].get("page")])
        if refs:
            q["source"]["document_id"]=refs[0].get("document_id")
            q["source"]["source_document_id"]=refs[0].get("source_document_id")
    return a

HTML=HTML.replace("VERSÃO 7.2 · ACABAMENTO COMERCIAL","VERSÃO 7.3 · DADOS CONTEXTUALIZADOS")


# --- Penalização: dossiê documental profissional v7.4 ---
def _first_hit_pages(pages, patterns, limit=8):
    hits=[]
    regs=[re.compile(p,re.I) for p in patterns]
    for p in pages:
        z=norm(p.get("text") or "")
        if any(rx.search(z) for rx in regs):
            hits.append(p["page"])
    return sorted(set(hits))[:limit]

def _penalty_metadata_v74(pages):
    md=_validated_metadata(pages)
    return {
        "penalizacao":_clean_profile_value(md.get("penalizacao")) or "Não identificado",
        "origem":_clean_profile_value(md.get("origem")) or "Não identificado",
        "pregao":_clean_profile_value(md.get("pregao")) or "Não identificado",
        "ata":_clean_profile_value(md.get("ata")) or "Não identificada",
        "contrato":_clean_profile_value(md.get("contrato")) or "Não identificado",
        "empenho":_clean_profile_value(md.get("empenho")) or "Não identificado",
        "empresa":_clean_profile_value(md.get("empresa")) or "Não identificada",
        "cnpj":_clean_profile_value(md.get("cnpj")) or "Não identificado"
    }

def _penalty_dossier_v74(pages,a):
    # Itens recorrentes na instrução dos processos de penalização:
    # identificação da contratação, execução/fato, contraditório, instrução e desfecho.
    specs=[
        ("Identificação da contratação",[
            ("Processo de penalização",[r"processo administrativo de penaliza",r"\bpap\b.{0,40}\d"]),
            ("Processo originário / vinculado",[r"processo.{0,30}(?:originario|origem|vinculado)",r"protocolo.{0,30}\d"]),
            ("Pregão / processo licitatório",[r"pregao(?: eletronico)?",r"processo licitatorio"]),
            ("Ata de Registro de Preços",[r"ata de registro de precos",r"\barp\b"]),
            ("Contrato ou instrumento equivalente",[r"\bcontrato(?: administrativo)?\b",r"instrumento contratual"]),
            ("Nota de Empenho / Pedido",[r"nota de empenho",r"\bempenho\b",r"\bpedido\b.{0,50}\bfornecimento\b"]),
            ("Ordem / Autorização de fornecimento",[r"ordem de fornecimento",r"autorizacao de fornecimento"]),
            ("Edital / Termo de Referência",[r"\bedital\b",r"termo de referencia"])
        ]),
        ("Execução e fato apurado",[
            ("Ofício / comunicação da unidade demandante",[r"\boficio\b",r"secretaria.{0,80}(?:informa|encaminha|relata)"]),
            ("Relatório do fiscal / gestor",[r"relatorio.{0,50}(?:fiscal|tecnico|execucao)",r"manifestacao.{0,40}(?:fiscal|gestor|tecnica)"]),
            ("Entrega / recebimento / instalação",[r"\bentrega\b",r"\brecebimento\b",r"\binstalacao\b"]),
            ("Nota fiscal / documento de execução",[r"nota fiscal",r"\bdanfe\b",r"documento de execucao"]),
            ("Prorrogação / reajuste / reequilíbrio",[r"\bprorrog",r"\breajust",r"\breequilibr"])
        ]),
        ("Contraditório e prova",[
            ("Notificação / intimação",[r"\bnotificacao\b",r"\bintimacao\b"]),
            ("Comprovante de envio / publicação / ciência",[r"comprovante.{0,50}(?:envio|ciencia|recebimento)",r"\bpublicacao\b",r"\bvisualizacao\b",r"confirmacao de ciencia"]),
            ("Defesa / manifestação da empresa",[r"defesa administrativa",r"razoes de defesa",r"manifestacao da contratada",r"apresenta.{0,50}defesa"]),
            ("Documentos e provas da defesa",[r"documentos.{0,40}(?:defesa|empresa)",r"\bprovas\b",r"orcamento",r"declaracao.{0,80}(?:fabricante|fornecedor)"]),
            ("Diligência / prova complementar",[r"\bdiligencia\b",r"prova complementar",r"informacao complementar"])
        ]),
        ("Instrução e decisão",[
            ("Parecer técnico",[r"parecer tecnico",r"relatorio tecnico",r"manifestacao tecnica"]),
            ("Parecer jurídico / PGM",[r"parecer juridico",r"\bpgm\b",r"procuradoria.{0,50}parecer"]),
            ("Relatório conclusivo da comissão",[r"relatorio conclusivo",r"relatorio da comissao"]),
            ("Decisão administrativa",[r"decisao administrativa",r"\bdecido\b",r"\bjulgamento\b"]),
            ("Sanção / dosimetria, se cabível",[r"\bsancao\b",r"\bpenalidade\b",r"\bdosimetria\b",r"impedimento de licitar",r"inidoneidade"]),
            ("Recurso / publicação / registro final",[r"recurso administrativo",r"\bpublicacao\b.{0,80}(?:decisao|sancao)",r"registro.{0,40}(?:sancao|penalidade)"])
        ])
    ]
    groups=[]
    for group,items in specs:
        rows=[]
        for label,patterns in items:
            pgs=_first_hit_pages(pages,patterns)
            rows.append({
                "label":label,
                "ok":bool(pgs),
                "pages":pgs,
                "documents":[]
            })
        groups.append({"group":group,"rows":rows})
    return groups

_old_module_overlay_v74=_module_overlay
def _module_overlay(pages,a,module):
    a=_old_module_overlay_v74(pages,a,module)
    if module=="penalizacao":
        a["penalty_metadata"]=_penalty_metadata_v74(pages)
        a["penalty_dossier"]=_penalty_dossier_v74(pages,a)
        total=sum(len(g["rows"]) for g in a["penalty_dossier"])
        ok=sum(1 for g in a["penalty_dossier"] for r in g["rows"] if r["ok"])
        a["penalty_dossier_score"]={"ok":ok,"total":total}
    return a

_old_enrich_doc_refs_v74=_enrich_doc_refs
def _enrich_doc_refs(a,pages):
    a=_old_enrich_doc_refs_v74(a,pages)
    for g in a.get("penalty_dossier",[]) or []:
        for row in g.get("rows",[]):
            row["documents"]=_page_doc_refs(pages,None,row.get("pages",[]))
    return a

_penalty_ui_css = """
/* Penalização: visual de dossiê, mais próximo de software corporativo */
.process-facts{
  display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:0 0 14px
}
.process-fact{
  min-height:70px;background:#fbfcfd;border:1px solid #dfe7ee;border-radius:9px;padding:10px 11px
}
.process-fact small{
  display:block;color:#708296;font-size:8px;font-weight:850;text-transform:uppercase;letter-spacing:.055em;margin-bottom:5px
}
.process-fact strong{
  display:block;color:#102f49;font-size:11px;line-height:1.35;overflow-wrap:anywhere
}
.dossier-shell{
  background:#fff;border:1px solid #dbe4eb;border-radius:11px;overflow:hidden
}
.dossier-head{
  display:flex;justify-content:space-between;gap:16px;align-items:center;padding:13px 15px;
  border-bottom:1px solid #e1e8ee;background:#f8fafb
}
.dossier-head h3{margin:0;color:#102f49;font-size:13px}
.dossier-head p{margin:3px 0 0;color:#748598;font-size:9px}
.dossier-score{
  white-space:nowrap;border:1px solid #c7dfdb;background:#eff9f7;color:#0b7b70;
  border-radius:999px;padding:5px 8px;font-size:8.5px;font-weight:850
}
.dossier-group+.dossier-group{border-top:1px solid #e5ebf0}
.dossier-group-title{
  padding:8px 14px;background:#fbfcfd;color:#66798c;font-size:8.5px;font-weight:900;
  text-transform:uppercase;letter-spacing:.075em
}
.dossier-row{
  display:grid;grid-template-columns:26px minmax(210px,.95fr) minmax(0,1.55fr) 90px;
  gap:10px;align-items:center;padding:9px 14px;border-top:1px solid #edf1f4;min-height:48px
}
.dossier-row:first-of-type{border-top:0}
.dossier-state{
  width:22px;height:22px;border-radius:7px;display:grid;place-items:center;font-size:10px;font-weight:900
}
.dossier-state.ok{background:#e8f7f2;color:#087a68}.dossier-state.miss{background:#fff6e8;color:#a46b00}
.dossier-label{font-size:10.5px;font-weight:800;color:#17334b}
.dossier-source{font-size:9px;color:#687b8d;min-width:0}
.dossier-source .ref-stack{display:flex;align-items:center;gap:4px;flex-wrap:wrap}
.dossier-status{justify-self:end;font-size:8.5px;font-weight:850}
.dossier-status.ok{color:#087a68}.dossier-status.miss{color:#a46b00}
.docs-intro{
  display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:11px
}
.docs-intro h2{margin:0!important}.docs-intro p{margin:4px 0 0;color:#6f8193;font-size:9.5px;max-width:760px}
@media(max-width:980px){
  .process-facts{grid-template-columns:repeat(2,minmax(0,1fr))}
  .dossier-row{grid-template-columns:26px 1fr 90px}.dossier-source{grid-column:2/-1}
}
@media(max-width:620px){
  .process-facts{grid-template-columns:1fr}
  .dossier-row{grid-template-columns:26px 1fr}.dossier-status{grid-column:2;justify-self:start}.dossier-source{grid-column:2}
}
"""
HTML=HTML.replace("</style>",_penalty_ui_css+"</style>",1)

_penalty_ui_js = r"""
function penaltyMetadataFacts(a){
  var m=a.penalty_metadata||{},q=a.quantity||{};
  var qv=q.display||q.value||"Não identificado";
  var facts=[
    ["Processo de penalização",m.penalizacao],
    ["Processo originário",m.origem],
    ["Pregão",m.pregao],
    ["Ata de Registro de Preços",m.ata],
    ["Contrato",m.contrato],
    ["Nota de Empenho",m.empenho],
    ["Empresa",m.empresa],
    ["CNPJ",m.cnpj],
    ["Quantidade / objeto",qv]
  ];
  return '<div class="process-facts">'+facts.map(function(x){
    return '<div class="process-fact"><small>'+esc(x[0])+'</small><strong>'+esc(x[1]||"Não identificado")+'</strong></div>';
  }).join("")+'</div>';
}
function penaltyDossierHtml(a){
  var groups=a.penalty_dossier||[],score=a.penalty_dossier_score||{ok:0,total:0};
  var h='<div class="dossier-shell"><div class="dossier-head"><div><h3>Checklist documental do processo</h3><p>Documentos e elementos recorrentes na instrução. “Não identificado” não significa necessariamente ausência; indica necessidade de conferência.</p></div><span class="dossier-score">'+esc(score.ok)+' de '+esc(score.total)+' localizados</span></div>';
  groups.forEach(function(g){
    h+='<div class="dossier-group"><div class="dossier-group-title">'+esc(g.group)+'</div>';
    (g.rows||[]).forEach(function(r){
      h+='<div class="dossier-row">'+
        '<span class="dossier-state '+(r.ok?'ok':'miss')+'">'+(r.ok?'✓':'!')+'</span>'+
        '<div class="dossier-label">'+esc(r.label)+'</div>'+
        '<div class="dossier-source">'+(r.ok?documentRefHtml(r.documents||[],r.pages||[]):'<span>Sem evidência segura na leitura automática</span>')+'</div>'+
        '<div class="dossier-status '+(r.ok?'ok':'miss')+'">'+(r.ok?'Localizado':'Conferir')+'</div>'+
      '</div>';
    });
    h+='</div>';
  });
  return h+'</div>';
}

var _oldAjustarResultadoModuloV74=ajustarResultadoModulo;
ajustarResultadoModulo=function(a){
  _oldAjustarResultadoModuloV74(a);
  if(!a||a.module_key!=="penalizacao")return;
  var structure=acharSectionPorTitulo("Estrutura do processo")||acharSectionPorTitulo("Estrutura esperada do processo");
  if(structure){
    structure.innerHTML=
      '<div class="docs-intro"><div><div class="kicker">Dossiê processual · Penalização contratual</div><h2>Documentos e elementos da instrução</h2><p>A tela reúne a identificação da contratação, fatos de execução, contraditório, provas, pareceres e atos de decisão com referência ao documento e à página.</p></div></div>'+
      penaltyMetadataFacts(a)+penaltyDossierHtml(a);
  }
};
"""
HTML=HTML.replace("</script>",_penalty_ui_js+"\n</script>",1)

HTML=HTML.replace("VERSÃO 7.3 · DADOS CONTEXTUALIZADOS","VERSÃO 7.4 · DOSSIÊ DE PENALIZAÇÃO")


# --- Central executiva do processo v7.5 ---
# A Visão Geral passa a consolidar o processo inteiro, inclusive a minuta assistida.
# As abas detalhadas continuam disponíveis para aprofundamento.

_overview_css = """
/* Central executiva */
#overviewHub{display:none;margin-bottom:12px}
#overviewHub.visible{display:block}
.ov-shell{display:grid;gap:11px}
.ov-hero{
  background:#fff;border:1px solid #dbe4eb;border-radius:12px;padding:16px 18px;
  display:grid;grid-template-columns:minmax(0,1.5fr) minmax(260px,.5fr);gap:18px;align-items:start
}
.ov-eyebrow{font-size:8.5px;font-weight:900;text-transform:uppercase;letter-spacing:.08em;color:#0b8f82}
.ov-title{margin:3px 0 0;color:#102f49;font-size:18px;line-height:1.2}
.ov-sub{margin:5px 0 0;color:#6b7d8f;font-size:10.5px;line-height:1.5}
.ov-meta{display:flex;gap:5px;flex-wrap:wrap;margin-top:10px}
.ov-chip{display:inline-flex;padding:4px 7px;border:1px solid #dbe4eb;border-radius:999px;background:#f7f9fb;color:#53697c;font-size:8.5px;font-weight:800}
.ov-chip.primary{border-color:#bfe0db;background:#eef9f7;color:#087b70}
.ov-next{border-left:1px solid #e3e9ee;padding-left:17px}
.ov-next small{display:block;color:#758698;font-size:8px;font-weight:900;text-transform:uppercase;letter-spacing:.07em}
.ov-next strong{display:block;color:#102f49;font-size:12.5px;margin-top:4px}
.ov-next p{margin:4px 0 0;color:#667a8d;font-size:9.5px;line-height:1.45}
.ov-next button{margin-top:9px}

.ov-progress{
  background:#fff;border:1px solid #dbe4eb;border-radius:12px;padding:13px 16px
}
.ov-progress-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:11px}
.ov-progress-head b{color:#102f49;font-size:11.5px}.ov-progress-head span{color:#718396;font-size:8.5px}
.ov-track{display:grid;grid-template-columns:repeat(5,1fr);gap:0}
.ov-stage{position:relative;padding-top:22px;font-size:8.5px;font-weight:800;color:#8090a0;text-align:center}
.ov-stage:before{
  content:"";position:absolute;top:6px;left:50%;transform:translateX(-50%);width:12px;height:12px;border-radius:50%;
  background:#dce5eb;border:3px solid #fff;box-shadow:0 0 0 1px #d1dce4;z-index:2
}
.ov-stage:after{content:"";position:absolute;top:12px;left:0;right:0;height:2px;background:#e2e9ee;z-index:1}
.ov-stage:first-child:after{left:50%}.ov-stage:last-child:after{right:50%}
.ov-stage.done{color:#087b70}.ov-stage.done:before{background:#0b8f82;box-shadow:0 0 0 1px #0b8f82}
.ov-stage.done:after{background:#9fd5cc}

.ov-grid{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(300px,.55fr);gap:11px}
.ov-panel{background:#fff;border:1px solid #dbe4eb;border-radius:12px;padding:15px 16px;min-width:0}
.ov-panel-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:10px}
.ov-panel-head h3{margin:0;color:#102f49;font-size:13px}
.ov-panel-head p{margin:3px 0 0;color:#728497;font-size:9px;line-height:1.4}
.ov-link{border:0;background:transparent;color:#0b7f74;font-size:8.5px;font-weight:850;cursor:pointer;padding:3px 0;white-space:nowrap}
.ov-summary{color:#334d63;font-size:10.5px;line-height:1.6;margin:0}
.ov-status-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-top:11px}
.ov-status{border-top:2px solid #dce5eb;padding:8px 2px 0}
.ov-status.ok{border-top-color:#0b8f82}.ov-status.warn{border-top-color:#d79a24}
.ov-status small{display:block;color:#77899a;font-size:7.5px;text-transform:uppercase;letter-spacing:.055em;font-weight:850}
.ov-status b{display:block;margin-top:3px;color:#143149;font-size:10px}
.ov-status.ok b{color:#087b70}.ov-status.warn b{color:#9a6900}

.ov-list{display:grid;gap:0}
.ov-row{display:grid;grid-template-columns:24px minmax(0,1fr) auto;gap:9px;align-items:start;padding:8px 0;border-top:1px solid #edf1f4}
.ov-row:first-child{border-top:0}
.ov-row-icon{width:20px;height:20px;border-radius:6px;background:#eaf7f4;color:#087b70;display:grid;place-items:center;font-size:9px;font-weight:900}
.ov-row-icon.warn{background:#fff4e3;color:#a26b00}
.ov-row b{display:block;color:#18344c;font-size:9.8px}.ov-row p{margin:2px 0 0;color:#748597;font-size:8.8px;line-height:1.4}
.ov-row .ov-source{color:#688093;font-size:8px;text-align:right;white-space:nowrap}

.ov-timeline{display:flex;gap:5px;overflow-x:auto;padding-bottom:3px}
.ov-time{min-width:120px;border-left:2px solid #a7d7cf;background:#f8fbfb;border-radius:0 8px 8px 0;padding:8px}
.ov-time small{display:block;color:#718497;font-size:7.5px}.ov-time b{display:block;color:#18344c;font-size:9px;margin-top:2px;line-height:1.3}

.ov-dossier-line{display:flex;align-items:center;gap:9px}
.ov-dossier-bar{height:7px;background:#e9eef2;border-radius:999px;overflow:hidden;flex:1}
.ov-dossier-fill{height:100%;background:#0b8f82;border-radius:999px}
.ov-dossier-num{font-size:9px;color:#526a7d;font-weight:850;white-space:nowrap}
.ov-dossier-groups{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-top:10px}
.ov-dossier-group{border:1px solid #e2e8ed;border-radius:8px;padding:8px}
.ov-dossier-group b{display:block;color:#17344c;font-size:8.8px}.ov-dossier-group span{display:block;color:#7a8b9c;font-size:7.8px;margin-top:2px}

.ov-draft-paper{
  border:1px solid #dfe6ec;background:#fcfcfb;border-radius:9px;max-height:360px;overflow:auto;
  padding:18px 20px;font-family:Georgia,"Times New Roman",serif;color:#24384b;font-size:10.5px;line-height:1.65;
  white-space:pre-wrap
}
.ov-draft-loading{color:#77899a;font-family:"Segoe UI",Arial,sans-serif;font-size:9.5px}
.ov-draft-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}
.ov-draft-actions .btn{font-size:9px!important;padding:7px 9px!important}
.ov-note{margin-top:7px;color:#7b8b99;font-size:7.8px;line-height:1.4}

.ov-evidence-columns{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.ov-evidence-block h4{margin:0 0 4px;color:#5e7285;font-size:8px;text-transform:uppercase;letter-spacing:.06em}
.ov-evidence-item{border-top:1px solid #edf1f4;padding:7px 0}
.ov-evidence-item:first-of-type{border-top:0}
.ov-evidence-item p{margin:0;color:#3e566b;font-size:9px;line-height:1.45}
.ov-evidence-item span{display:block;color:#7890a2;font-size:7.8px;margin-top:2px}

.dossier-compact .dossier-row{
  grid-template-columns:24px minmax(190px,.9fr) minmax(240px,1.45fr) 80px;
  padding:8px 12px;min-height:44px
}
.dossier-compact .dossier-source{white-space:normal}
.dossier-primary{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.dossier-more{color:#7890a0;font-size:8px;font-weight:750}
.internal-refs-moved{display:none!important}

@media(max-width:1050px){
  .ov-hero,.ov-grid{grid-template-columns:1fr}
  .ov-next{border-left:0;border-top:1px solid #e3e9ee;padding:12px 0 0}
  .ov-status-grid{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:700px){
  .ov-track{grid-template-columns:1fr;gap:4px}
  .ov-stage{text-align:left;padding:5px 0 5px 26px}
  .ov-stage:before{left:8px;top:7px}.ov-stage:after{display:none}
  .ov-evidence-columns,.ov-dossier-groups{grid-template-columns:1fr}
}
"""
HTML=HTML.replace("</style>",_overview_css+"</style>",1)

_overview_js = r"""
function ovEsc(v){return esc(v==null?"":v)}
function ovPageSource(x){
  if(!x)return "";
  if(x.document_id)return "ID "+ovEsc(x.document_id)+(x.page?" · p. "+ovEsc(x.page):"");
  if(x.page)return "p. "+ovEsc(x.page);
  return "";
}
function ovPrimaryDoc(docs,pages){
  docs=docs||[];pages=pages||[];
  if(docs.length){
    var d=docs[0],txt="ID "+ovEsc(d.document_id||"");
    if(d.source_document_id)txt+=" · "+ovEsc(d.source_document_id);
    if(d.page)txt+=" · p. "+ovEsc(d.page);
    return txt;
  }
  if(pages.length)return "p. "+ovEsc(pages[0]);
  return "Sem fonte segura";
}
function ovStatusItems(a){
  if(a.module_key==="penalizacao"){
    var q=(a.quantity&& (a.quantity.display||a.quantity.value))||"Não identificado";
    return [
      {label:"Notificação",ok:!!(a.has&& (a.has.notificacao||a.has.intimacao)),value:(a.has&&(a.has.notificacao||a.has.intimacao))?"Localizada":"Conferir"},
      {label:"Defesa",ok:!!(a.has&&a.has.defesa),value:(a.has&&a.has.defesa)?"Localizada":"Conferir"},
      {label:"Decisão",ok:!!(a.has&&a.has.decisao),value:(a.has&&a.has.decisao)?"Localizada":"Conferir"},
      {label:"Quantidade / objeto",ok:!String(q).toLowerCase().includes("não identificado"),value:q}
    ];
  }
  return (a.module_summary||[]).slice(0,4).map(function(x){return {label:x.label,ok:x.ok,value:x.value}});
}
function ovStages(a){
  if(a.module_key==="penalizacao"){
    var has=a.has||{};
    return [
      {label:"Contratação",done:!!(has.contrato||has.empenho||has.ordem_fornecimento)},
      {label:"Apuração",done:!!((a.contra||[]).length||(has.parecer_tecnico))},
      {label:"Contraditório",done:!!((has.notificacao||has.intimacao)&&has.defesa)},
      {label:"Instrução",done:!!(has.parecer_tecnico||has.parecer_juridico)},
      {label:"Decisão",done:!!has.decisao}
    ];
  }
  var rows=a.module_matrix||[];
  if(!rows.length)return [
    {label:"Entrada",done:true},{label:"Instrução",done:false},{label:"Análise",done:false},{label:"Conclusão",done:false},{label:"Encerramento",done:false}
  ];
  var labels=["Entrada","Instrução","Manifestação","Análise","Conclusão"];
  return labels.map(function(l,i){return {label:l,done:i<Math.ceil((rows.filter(function(x){return x.ok}).length/rows.length)*5)}});
}
function ovTimeline(a){
  var items=[];
  if(a.module_key==="penalizacao"){
    items=(a.pieces||[]).map(function(x){
      return {label:x.label,pages:x.pages||[],documents:x.documents||[]};
    }).sort(function(x,y){return (x.pages[0]||9999)-(y.pages[0]||9999)});
  }else items=a.module_timeline||[];
  return items.slice(0,7);
}
function ovEvidence(a){
  if(a.module_key==="penalizacao"){
    return {
      favorable:(a.defense||[]).slice(0,3).map(function(x){return {text:x.text,source:ovPageSource(x)}}),
      confront:(a.contra||[]).slice(0,3).map(function(x){return {text:x.text,source:ovPageSource(x)}})
    };
  }
  var ev=(a.module_evidence||[]).slice(0,6).map(function(x){return {text:(x.label+": "+(x.text||"Evidência localizada.")),source:ovPageSource(x)}});
  return {favorable:ev.slice(0,3),confront:ev.slice(3,6)};
}
function ovDossier(a){
  if(a.module_key==="penalizacao"&&a.penalty_dossier){
    var groups=a.penalty_dossier.map(function(g){
      var ok=(g.rows||[]).filter(function(r){return r.ok}).length;
      return {label:g.group,ok:ok,total:(g.rows||[]).length};
    });
    return {groups:groups,ok:(a.penalty_dossier_score||{}).ok||0,total:(a.penalty_dossier_score||{}).total||0};
  }
  var rows=a.module_matrix||[];
  return {groups:[{label:"Controles do módulo",ok:rows.filter(function(x){return x.ok}).length,total:rows.length}],ok:rows.filter(function(x){return x.ok}).length,total:rows.length};
}
function ovPending(a){
  var p=(a.review_flags||[]).map(function(x){return x.text});
  if(!p.length)p=(a.pending||[]).slice();
  return p.slice(0,5);
}
function ovDefaultDraftKind(a){
  var m=a.module_key||selectedModule;
  if(m==="penalizacao")return "notificacao";
  if(m==="sindicancia"||m==="disciplinar"||m==="fiscalizacao")return "relatorio";
  if(m==="reequilibrio"||m==="rescisao")return "decisao";
  return "relatorio";
}
function ovDraftLabel(kind){
  return {notificacao:"Notificação de instauração",relatorio:"Relatório conclusivo",decisao:"Minuta de decisão",diligencia:"Despacho de diligência",despacho:"Despacho",intimacao:"Intimação"}[kind]||"Minuta assistida";
}
function renderOverviewHub(a){
  var main=document.querySelector(".system-main");
  if(!main)return;
  var hub=document.getElementById("overviewHub");
  if(!hub){
    hub=document.createElement("div");hub.id="overviewHub";
    var tabs=document.getElementById("processTabs"),result=document.getElementById("result");
    if(tabs&&tabs.nextSibling)tabs.parentNode.insertBefore(hub,tabs.nextSibling);
    else if(result)result.parentNode.insertBefore(hub,result);
    else main.appendChild(hub);
  }

  var p=a.process_profile||{},statuses=ovStatusItems(a),stages=ovStages(a),timeline=ovTimeline(a),ev=ovEvidence(a),dos=ovDossier(a),pending=ovPending(a);
  var pct=dos.total?Math.round(dos.ok*100/dos.total):0;
  var next=a.next_action||{};
  var draftKind=ovDefaultDraftKind(a);

  var sh=statuses.map(function(x){
    return '<div class="ov-status '+(x.ok?'ok':'warn')+'"><small>'+ovEsc(x.label)+'</small><b>'+ovEsc(x.value)+'</b></div>';
  }).join("");

  var stageh=stages.map(function(x){return '<div class="ov-stage '+(x.done?'done':'')+'">'+ovEsc(x.label)+'</div>'}).join("");

  var tlh=timeline.length?timeline.map(function(x){
    return '<div class="ov-time"><small>'+ovEsc(ovPrimaryDoc(x.documents||[],x.pages||[]))+'</small><b>'+ovEsc(x.label)+'</b></div>';
  }).join(""):'<div class="ov-time"><small>—</small><b>Cronologia ainda não consolidada</b></div>';

  function evBlock(title,items){
    var h='<div class="ov-evidence-block"><h4>'+title+'</h4>';
    if(!items.length)h+='<div class="ov-evidence-item"><p>Nenhum achado prioritário nesta categoria.</p></div>';
    items.forEach(function(x){h+='<div class="ov-evidence-item"><p>'+ovEsc(x.text)+'</p><span>'+ovEsc(x.source||"Fonte disponível na aba Evidências")+'</span></div>'});
    return h+'</div>';
  }

  var pendh=pending.length?pending.map(function(x){
    return '<div class="ov-row"><span class="ov-row-icon warn">!</span><div><b>Ponto para conferência</b><p>'+ovEsc(x)+'</p></div><span class="ov-source">Revisão humana</span></div>';
  }).join(""):'<div class="ov-row"><span class="ov-row-icon">✓</span><div><b>Sem alerta prioritário</b><p>Não foi identificada pendência automática prioritária nesta leitura.</p></div><span class="ov-source">Automático</span></div>';

  var dg=dos.groups.map(function(g){return '<div class="ov-dossier-group"><b>'+ovEsc(g.label)+'</b><span>'+ovEsc(g.ok)+' de '+ovEsc(g.total)+' itens localizados</span></div>'}).join("");

  hub.innerHTML=
    '<div class="ov-shell">'+
      '<section class="ov-hero">'+
        '<div><div class="ov-eyebrow">Visão geral do processo</div><h2 class="ov-title">'+ovEsc(p.number||a.module_label||"Processo analisado")+'</h2>'+
        '<p class="ov-sub">'+ovEsc((p.interested&&p.interested!=="Interessado não identificado"?p.interested+" · ":"")+(a.conclusion||"Análise concluída."))+'</p>'+
        '<div class="ov-meta"><span class="ov-chip primary">'+ovEsc(a.module_label||moduleLabels[selectedModule]||"Módulo")+'</span><span class="ov-chip">'+ovEsc((p.pages||0)+" páginas")+'</span><span class="ov-chip">'+ovEsc((p.documents||0)+" documentos")+'</span><span class="ov-chip">ID + página</span></div>'+
        '<div class="ov-status-grid">'+sh+'</div></div>'+
        '<aside class="ov-next"><small>Próxima providência</small><strong>'+ovEsc(next.stage||"Revisão do processo")+'</strong><p>'+ovEsc(next.action||"Conferir os elementos relevantes antes da conclusão.")+'</p><button class="btn btn-primary" onclick="mostrarAbaProcesso(\'pendencias\')">Ver pendências</button></aside>'+
      '</section>'+

      '<section class="ov-progress"><div class="ov-progress-head"><b>Andamento identificado</b><span>Leitura automática sujeita à conferência</span></div><div class="ov-track">'+stageh+'</div></section>'+

      '<div class="ov-grid">'+
        '<section class="ov-panel"><div class="ov-panel-head"><div><h3>Leitura executiva</h3><p>Resumo, pontos relevantes e situação do contraditório.</p></div><button class="ov-link" onclick="mostrarAbaProcesso(\'evidencias\')">Abrir evidências →</button></div>'+
          '<p class="ov-summary">'+ovEsc(a.conclusion||"")+'</p>'+
          '<div class="ov-evidence-columns">'+evBlock("Elementos favoráveis / manifestações",ev.favorable)+evBlock("Pontos a confrontar",ev.confront)+'</div>'+
        '</section>'+
        '<section class="ov-panel"><div class="ov-panel-head"><div><h3>Dossiê documental</h3><p>Completude dos elementos esperados para o módulo.</p></div><button class="ov-link" onclick="mostrarAbaProcesso(\'documentos\')">Abrir documentos →</button></div>'+
          '<div class="ov-dossier-line"><div class="ov-dossier-bar"><div class="ov-dossier-fill" style="width:'+pct+'%"></div></div><span class="ov-dossier-num">'+ovEsc(dos.ok)+'/'+ovEsc(dos.total)+' · '+pct+'%</span></div>'+
          '<div class="ov-dossier-groups">'+dg+'</div>'+
        '</section>'+
      '</div>'+

      '<section class="ov-panel"><div class="ov-panel-head"><div><h3>Cronologia essencial</h3><p>Principais marcos encontrados nos autos.</p></div><button class="ov-link" onclick="mostrarAbaProcesso(\'cronologia\')">Ver cronologia completa →</button></div><div class="ov-timeline">'+tlh+'</div></section>'+

      '<div class="ov-grid">'+
        '<section class="ov-panel"><div class="ov-panel-head"><div><h3>Pendências e pontos de atenção</h3><p>O que merece conferência antes do próximo ato.</p></div><button class="ov-link" onclick="mostrarAbaProcesso(\'pendencias\')">Abrir revisão →</button></div><div class="ov-list">'+pendh+'</div></section>'+
        '<section class="ov-panel"><div class="ov-panel-head"><div><h3 id="ovDraftTitle">'+ovEsc(ovDraftLabel(draftKind))+'</h3><p>Minuta assistida já integrada à visão geral.</p></div><button class="ov-link" onclick="mostrarAbaProcesso(\'minutas\')">Ver todas as minutas →</button></div>'+
          '<div id="ovDraftPaper" class="ov-draft-paper"><span class="ov-draft-loading">Gerando minuta assistida a partir dos autos…</span></div>'+
          '<div class="ov-draft-actions"><button class="btn btn-blue" onclick="copiarMinutaOverview()">Copiar minuta</button><button class="btn btn-blue" onclick="baixarMinutaOverview()">Baixar .txt</button><button class="btn btn-primary" onclick="mostrarAbaProcesso(\'minutas\')">Editar / outras minutas</button></div>'+
          '<div class="ov-note">Conteúdo assistido. A revisão humana e a conferência dos autos permanecem obrigatórias.</div>'+
        '</section>'+
      '</div>'+
    '</div>';

  carregarMinutaOverview(a,draftKind);
}
async function carregarMinutaOverview(a,kind){
  var paper=document.getElementById("ovDraftPaper");if(!paper)return;
  analysisId=analysisId||localStorage.getItem("fiscaliza_analysis_id");
  if(!analysisId){paper.textContent="Minuta indisponível: análise sem identificador de sessão.";return}
  try{
    var r=await fetch("/api/document-draft",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({analysis_id:analysisId,kind:kind})});
    var d=await r.json();
    if(!r.ok)throw new Error(d.detail||"Falha ao gerar");
    paper.textContent=d.draft||"Minuta não gerada.";
    paper.dataset.draft=d.draft||"";
  }catch(e){
    paper.textContent="Não foi possível gerar automaticamente a minuta nesta sessão. Use a aba Minutas para tentar novamente.";
  }
}
async function copiarMinutaOverview(){
  var p=document.getElementById("ovDraftPaper"),txt=(p&&p.dataset.draft)||"";
  if(!txt)return;
  try{await navigator.clipboard.writeText(txt)}catch(e){var ta=document.createElement("textarea");ta.value=txt;document.body.appendChild(ta);ta.select();document.execCommand("copy");ta.remove()}
}
function baixarMinutaOverview(){
  var p=document.getElementById("ovDraftPaper"),txt=(p&&p.dataset.draft)||"";
  if(!txt)return;
  var blob=new Blob([txt],{type:"text/plain;charset=utf-8"}),a=document.createElement("a");
  a.href=URL.createObjectURL(blob);a.download="fiscaliza-minuta-assistida.txt";a.click();URL.revokeObjectURL(a.href);
}

function dossierPrimaryDocs(row){
  var docs=(row.documents||[]).slice();
  if(!docs.length)return [];
  var label=(row.label||"").toLowerCase();
  var keys=[];
  if(label.includes("ata de registro"))keys=["ata de registro","arp"];
  else if(label.includes("pregão")||label.includes("licitatório"))keys=["pregao","pregão","edital"];
  else if(label.includes("contrato"))keys=["contrato administrativo","contrato nº","contrato n"];
  else if(label.includes("empenho"))keys=["nota de empenho","empenho nº","empenho n"];
  else if(label.includes("ordem")||label.includes("autorização"))keys=["ordem de fornecimento","autorizacao de fornecimento","autorização de fornecimento"];
  else if(label.includes("notificação")||label.includes("intimação"))keys=["notificacao","notificação","intimacao","intimação"];
  else if(label.includes("defesa"))keys=["defesa administrativa","razoes de defesa","razões de defesa"];
  else if(label.includes("parecer técnico"))keys=["parecer tecnico","parecer técnico","relatorio tecnico","relatório técnico"];
  else if(label.includes("parecer jurídico"))keys=["parecer juridico","parecer jurídico"];
  else if(label.includes("decisão"))keys=["decisao","decisão"];
  var ranked=docs.map(function(d){
    var s=((d.source_document_id||"")+" "+(d.document_id||"")).toLowerCase();
    var score=keys.some(function(k){return s.indexOf(k)>=0})?0:1;
    return {d:d,score:score};
  }).sort(function(a,b){return a.score-b.score});
  var out=[],seen={};
  ranked.forEach(function(x){
    var key=x.d.document_id||x.d.source_document_id;
    if(!seen[key]&&out.length<2){seen[key]=1;out.push(x.d)}
  });
  return out;
}

function penaltyDossierHtml(a){
  var groups=a.penalty_dossier||[],score=a.penalty_dossier_score||{ok:0,total:0};
  var h='<div class="dossier-shell dossier-compact"><div class="dossier-head"><div><h3>Checklist documental do processo</h3><p>Fonte principal por item. Outras menções permanecem disponíveis na aba Evidências.</p></div><span class="dossier-score">'+ovEsc(score.ok)+' de '+ovEsc(score.total)+' localizados</span></div>';
  groups.forEach(function(g){
    h+='<div class="dossier-group"><div class="dossier-group-title">'+ovEsc(g.group)+'</div>';
    (g.rows||[]).forEach(function(r){
      var primary=dossierPrimaryDocs(r),more=Math.max(0,(r.documents||[]).length-primary.length);
      var src=r.ok?('<div class="dossier-primary">'+documentRefHtml(primary,r.pages&&r.pages.length?[r.pages[0]]:[])+(more?'<span class="dossier-more">+'+more+' referência(s)</span>':'')+'</div>'):'<span>Sem evidência segura na leitura automática</span>';
      h+='<div class="dossier-row"><span class="dossier-state '+(r.ok?'ok':'miss')+'">'+(r.ok?'✓':'!')+'</span><div class="dossier-label">'+ovEsc(r.label)+'</div><div class="dossier-source">'+src+'</div><div class="dossier-status '+(r.ok?'ok':'miss')+'">'+(r.ok?'Localizado':'Conferir')+'</div></div>';
    });
    h+='</div>';
  });
  return h+'</div>';
}

var _oldMarcarGruposResultadoV75=marcarGruposResultado;
marcarGruposResultado=function(){
  _oldMarcarGruposResultadoV75();
  document.querySelectorAll("#result details").forEach(function(d){
    var t=(d.textContent||"").toLowerCase();
    if(t.indexOf("referências internas")>=0||t.indexOf("referencias internas")>=0)d.dataset.group="evidencias";
  });
};

var _oldSetPanelVisibilityV75=setPanelVisibility;
setPanelVisibility=function(tab){
  var hub=document.getElementById("overviewHub");
  if(tab==="resumo"){
    if(hub)hub.classList.add("visible");
    var result=document.getElementById("result");if(result)result.style.display="none";
    ["qaPanel","notificationPanel","docsPanel","privacyPanel","reportPanel"].forEach(function(id){var p=document.getElementById(id);if(p){p.style.display="none";p.classList.remove("tab-visible")}});
    return;
  }
  if(hub)hub.classList.remove("visible");
  _oldSetPanelVisibilityV75(tab);
};

var _oldAtivarProcessoNoSistemaV75=ativarProcessoNoSistema;
ativarProcessoNoSistema=function(a){
  _oldAtivarProcessoNoSistemaV75(a);
  renderOverviewHub(a);
  marcarGruposResultado();
  mostrarAbaProcesso("resumo");
};
"""
HTML=HTML.replace("</script>",_overview_js+"\n</script>",1)

HTML=HTML.replace("VERSÃO 7.4 · DOSSIÊ DE PENALIZAÇÃO","VERSÃO 7.5 · CENTRAL EXECUTIVA")
