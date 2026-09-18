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
