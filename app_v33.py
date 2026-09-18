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
