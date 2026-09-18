
# --- Fiscaliza.AI v3.2: separa peça autônoma de mera menção e melhora Q&A ---
STRONG_RULES={
"contrato":[r"\\bcontratante\\b",r"\\bcontratada\\b"],
"notificacao":[r"\\bnotificacao extrajudicial\\b",r"\\bnotificacao administrativa\\b"],
"intimacao":[r"\\bintimacao\\b",r"\\bfica intimad[ao]\\b"],
"defesa":[r"\\bdefesa administrativa\\b",r"\\brazoes de defesa\\b",r"\\bapresenta(?:r)? (?:a |sua )?defesa\\b"],
"parecer_juridico":[r"\\bparecer juridico\\b",r"\\bprocuradoria juridica\\b"],
"parecer_tecnico":[r"\\bparecer tecnico\\b",r"\\brelatorio tecnico\\b",r"\\bmanifestacao tecnica\\b"],
"decisao":[r"\\bdecisao administrativa\\b",r"\\bdecido\\b",r"\\b(resolvo|determino|autorizo)\\b.*\\b(rescis|extin|instaur|processo administrativo sancionador)\\b"],
"termo_recebimento":[r"^\\s*termo de recebimento\\b"],
"nota_fiscal":[r"\\bdanfe\\b",r"^\\s*nota fiscal(?: eletronica)?\\b"],
"empenho":[r"^\\s*nota de empenho\\b",r"^\\s*empenho\\s*(?:n|numero)\\b"],
"ordem_fornecimento":[r"^\\s*(?:ordem|autorizacao) de fornecimento\\b"]
}

def _strong_type(p,typ):
    raw=c(p["text"]); top=n(raw[:1400]); short=n(raw[:420])
    if typ=="contrato":
        return ("contrato" in top and "contratante" in top and "contratada" in top)
    if typ=="termo_recebimento":
        return bool(re.search(r"^\\s*termo de recebimento\\b",short))
    if typ=="nota_fiscal":
        return bool(re.search(r"\\bdanfe\\b",top) or re.search(r"^\\s*nota fiscal(?: eletronica)?\\b",short))
    if typ=="empenho":
        return bool(re.search(r"^\\s*nota de empenho\\b",short) or re.search(r"^\\s*empenho\\s*(?:n|numero)",short))
    if typ=="ordem_fornecimento":
        return bool(re.search(r"^\\s*(?:ordem|autorizacao) de fornecimento\\b",short))
    return any(re.search(pat,top) for pat in STRONG_RULES[typ])

def classify(ps):
    found=[]
    for p in ps:
        for typ in LABEL:
            if _strong_type(p,typ):
                found.append({**p,"type":typ})
    # inclui uma página imediatamente posterior quando ela continua a mesma peça
    # e contém vocabulário da própria classe, sem novo cabeçalho forte conflitante.
    extra=[]
    byfile={}
    for p in ps: byfile.setdefault(p["file"],{})[p["page"]]=p
    keys={(x["file"],x["page"],x["type"]) for x in found}
    anchors={(x["file"],x["page"]):x["type"] for x in found}
    for x in list(found):
        np=byfile.get(x["file"],{}).get(x["page"]+1)
        if not np or (np["file"],np["page"]) in anchors: continue
        z=n(np["text"])
        if any(term in z for term in RULES.get(x["type"],[])):
            k=(np["file"],np["page"],x["type"])
            if k not in keys:
                extra.append({**np,"type":x["type"]});keys.add(k)
    return found+extra

def group(found):
    out=[]
    for typ in LABEL:
        xs=[x for x in found if x["type"]==typ]
        if not xs: continue
        by={}
        for x in xs: by.setdefault(x["file"],[]).append(x["page"])
        for f,pg in by.items():
            out.append({"type":typ,"label":LABEL[typ],"file":f,"pages":sorted(set(pg))})
    return out

def mention_groups(ps,found):
    strong={(x["file"],x["page"],x["type"]) for x in found}
    out=[]
    for typ,pats in RULES.items():
        by={}
        for p in ps:
            if (p["file"],p["page"],typ) in strong: continue
            z=n(p["text"])
            if any(x in z for x in pats):
                by.setdefault(p["file"],[]).append(p["page"])
        for f,pg in by.items():
            out.append({"type":typ,"label":LABEL[typ],"file":f,"pages":sorted(set(pg))})
    return out

def analyze(ps):
    f=classify(ps); pcs=group(f); mns=mention_groups(ps,f)
    has={k:any(x["type"]==k for x in pcs) for k in LABEL}
    nd=snippets(ps,[r"nenhuma entrega",r"nao houve entrega",r"nao realizou (?:a )?entrega",r"inexecucao total"],5)
    defense=snippets(ps,[r"reequilibr",r"aumento.*custo",r"frete",r"impossibil",r"forca maior",r"inviabil"],5)
    contra=snippets(ps,[r"nenhuma entrega",r"nao houve entrega",r"descumpr",r"inexecucao",r"rescisao unilateral",r"extincao unilateral"],6)
    sanc=snippets(ps,[r"abertura.*processo administrativo sancionador",r"instauracao.*processo administrativo sancionador"],3)
    delivered=snippets(ps,[r"foi entregue",r"entrega realizada",r"recebido.*objeto"],2)
    pend=[]
    if delivered and not has["termo_recebimento"]:
        pend.append("Há indício de entrega, mas não foi localizado termo de recebimento como peça autônoma.")
    if not has["defesa"]:
        pend.append("Não foi localizada defesa administrativa como peça autônoma com segurança.")
    if not(has["notificacao"] or has["intimacao"]):
        pend.append("Não foi localizada notificação/intimação como peça autônoma com segurança.")
    if sanc:
        pend.append("Os autos indicam abertura/instauração de processo sancionador posterior; não presuma sanção final a partir deste PDF.")
    if sanc:
        concl="Os autos registram abertura/instauração de processo administrativo sancionador posterior. Isso não equivale a sanção já aplicada."
    elif has["decisao"] and has["defesa"] and (has["notificacao"] or has["intimacao"]):
        concl="Foram localizadas peças relevantes de contraditório e decisão. A ferramenta organiza a evidência; a decisão permanece humana."
    else:
        concl="Nem todas as peças esperadas foram identificadas como documentos autônomos com segurança. Menções no corpo dos autos não são tratadas como peças."
    return {"pieces":pcs,"mentions":mns,"has":has,"defense":defense,"contra":contra,"pending":pend,"quantity":quantity(ps),"conclusion":concl,"no_delivery":nd}

def _piece_pages(a,typ):
    return sorted({p for x in a.get("pieces",[]) if x["type"]==typ for p in x["pages"]})

def _fmt_pages(pgs):
    if not pgs:return ""
    runs=[];s=e=pgs[0]
    for p in pgs[1:]:
        if p==e+1:e=p
        else:runs.append((s,e));s=e=p
    runs.append((s,e))
    return ", ".join(str(a) if a==b else f"{a}–{b}" for a,b in runs)

def _arg_categories(ps,pageset):
    cats=[
      ("reequilíbrio econômico-financeiro",[r"reequilibr"]),
      ("aumento de custos/frete",[r"aumento.*custo",r"frete"]),
      ("impossibilidade ou inviabilidade de execução",[r"impossibil",r"inviabil"]),
      ("pedido de rescisão/encerramento",[r"rescis",r"encerramento"]),
      ("caso fortuito/força maior",[r"caso fortuito",r"forca maior"])
    ]
    out=[]
    for label,pats in cats:
        pgs=[]
        for p in ps:
            if p["page"] not in pageset:continue
            z=n(p["text"])
            if any(re.search(x,z) for x in pats):pgs.append(p["page"])
        if pgs:out.append((label,sorted(set(pgs))))
    return out

def ask(q,a,ps):
    z=n(q)
    if "defesa" in z:
        pgs=_piece_pages(a,"defesa")
        if not pgs:
            return {"answer":"Não localizei defesa administrativa como peça autônoma com segurança.","sources":[]}
        cats=_arg_categories(ps,set(pgs))
        args="; ".join(f"{lab} (p. {_fmt_pages(pg)})" for lab,pg in cats[:4]) or "conteúdo a conferir nas páginas indicadas"
        first=min(pgs);prior=[]
        for p in ps:
            if p["page"]>=first:continue
            zz=n(p["text"])
            if ("reequilibr" in zz or "rescisao amigavel" in zz or "pedido de emissao" in zz) and not _strong_type(p,"defesa"):
                prior.append(p["page"])
        prior=sorted(set(prior))[:8]
        extra=f" Há manifestações anteriores da contratada nas páginas {_fmt_pages(prior)}, separadas da defesa formal." if prior else ""
        return {"answer":f"Sim. A defesa administrativa foi localizada como peça própria nas páginas {_fmt_pages(pgs)}. Principais argumentos identificados: {args}.{extra}",
                "sources":[f"Defesa administrativa · p. {_fmt_pages(pgs)}"]}
    if "notifica" in z or "intim" in z:
        pgs=sorted(set(_piece_pages(a,"notificacao")+_piece_pages(a,"intimacao")))
        return {"answer":f"Sim. Foi localizada notificação/intimação como peça própria nas páginas {_fmt_pages(pgs)}." if pgs else "Não localizei notificação/intimação como peça própria com segurança.",
                "sources":[f"Notificação/intimação · p. {_fmt_pages(pgs)}"] if pgs else []}
    if "quantidade" in z:
        s=a["quantity"].get("source")
        return {"answer":"Quantidade total: "+a["quantity"]["value"],"sources":[f'{s["file"]} · p.{s["page"]}'] if s else []}
    if "entrega" in z and a["no_delivery"]:
        s=a["no_delivery"][0]
        return {"answer":"Há registro textual indicando ausência de entrega.","sources":[f'{s["file"]} · p.{s["page"]} — {s["text"]}']}
    if "decis" in z or "rescis" in z:
        pgs=_piece_pages(a,"decisao")
        return {"answer":a["conclusion"]+(f" Decisão localizada nas páginas {_fmt_pages(pgs)}." if pgs else ""),"sources":[f"Decisão · p. {_fmt_pages(pgs)}"] if pgs else []}
    words=[w for w in re.findall(r"[a-z0-9çãõáéíóúâêô]{4,}",q.lower()) if w not in {"qual","quais","como","para","sobre","processo","informe","paginas","páginas"}]
    sc=[]
    for p in ps:
        for s in re.split(r"(?<=[.!?;])\\s+",p["text"]):
            k=sum(1 for w in words if n(w) in n(s))
            if k:sc.append((k,p,s))
    sc.sort(key=lambda x:(-x[0],x[1]["page"]))
    if not sc:return {"answer":"Não encontrei evidência textual suficiente.","sources":[]}
    return {"answer":"Encontrei evidências relacionadas. Revise os trechos e páginas antes de concluir.",
            "sources":[f'{p["file"]} · p.{p["page"]} — {c(s)[:320]}' for _,p,s in sc[:4]]}

try:
    HTML=HTML.replace("VERSÃO 3.1 · LEITURA POR PEÇAS","VERSÃO 3.2 · PEÇA ≠ MENÇÃO")
    HTML=HTML.replace("A análise agora é feita por página.","A análise agora separa peça autônoma de simples menção no corpo dos autos.")
except Exception:
    pass
