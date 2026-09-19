import re
import app_v33 as core

app = core.app


# RC1: correcoes finais da Penalizacao observadas no preview real.
# Mantem a aplicacao principal intacta e aplica apenas ajustes de acabamento/consistencia.


def _best_company_and_cnpj_rc1(pages):
    joined = "\n".join(p.get("text") or "" for p in pages)
    company_candidates = []
    patterns = [
        r"(?:CONTRATADA|Empresa)\s*[:\-]?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 .,&\-]{3,140}?\b(?:LTDA|EIRELI|EPP|ME|S\.?A\.?)\b)",
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 .,&\-]{4,140}?\b(?:LTDA|EIRELI|EPP|ME|S\.?A\.?)\b)\s*,?\s*(?:inscrita|inscrito)?\s*(?:no\s+)?CNPJ",
    ]
    for pat in patterns:
        for m in re.finditer(pat, joined, flags=re.I):
            name = re.sub(r"\s+", " ", m.group(1)).strip(" ,;:-")
            # Evita falsos positivos como "EMPRESA" por causa de "S.A." dentro da palavra.
            if len(name.split()) >= 2:
                company_candidates.append((m.start(), name))

    company = company_candidates[0][1] if company_candidates else "[NÃO IDENTIFICADO AUTOMATICAMENTE]"

    cnpjs = [(m.start(), m.group(0)) for m in re.finditer(
        r"\b\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}\b", joined
    )]
    if company_candidates and cnpjs:
        pos = company_candidates[0][0]
        cnpj = min(cnpjs, key=lambda x: abs(x[0] - pos))[1]
    else:
        cnpj = cnpjs[0][1] if cnpjs else "[NÃO IDENTIFICADO AUTOMATICAMENTE]"
    return company, cnpj


def _extract_origin_process_rc1(pages):
    joined = "\n".join(p.get("text") or "" for p in pages)
    return core._first_match(joined, [
        r"Protocolo(?:\s+de\s+origem)?\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)",
        r"Processo(?:\s+Administrativo)?(?:\s+de\s+origem)?\s*(?:n[ºo.]?|número)?\s*[:\-]?\s*([0-9][0-9.\-\/]+)",
    ])


core._best_company_and_cnpj = _best_company_and_cnpj_rc1
core._extract_origin_process = _extract_origin_process_rc1


_old_process_profile = core._derive_process_profile


def _derive_unit_from_pages(pages):
    joined = "\n".join(p.get("text") or "" for p in pages[:12])
    patterns = [
        r"Interessad[oa]\s*:\s*([^\.\n]{3,140})",
        r"Unidade\s+(?:demandante|requisitante|solicitante)\s*:\s*([^\.\n]{3,140})",
        r"((?:Secretaria|Fundo|Departamento|Autarquia|Coordena[cç][aã]o|Ger[eê]ncia)\s+(?:Municipal\s+)?[^\.\n]{3,100})",
    ]
    for pat in patterns:
        m = re.search(pat, joined, flags=re.I)
        if not m:
            continue
        value = re.sub(r"\s+", " ", m.group(1)).strip(" ,;:-")
        if re.search(r"Secretaria|Fundo|Departamento|Autarquia|Coordena[cç][aã]o|Ger[eê]ncia|Unidade", value, flags=re.I):
            return value[:160]
    return ""


def _derive_process_profile_rc1(pages, module, process_number="", interested="", unit=""):
    profile = _old_process_profile(pages, module, process_number, interested, unit)
    if not unit and profile.get("unit") == "Unidade não informada":
        derived = _derive_unit_from_pages(pages)
        if derived:
            profile["unit"] = derived
    return profile


core._derive_process_profile = _derive_process_profile_rc1


_old_next_action = core._next_action


def _next_action_rc1(pages, a):
    if a.get("final_sanction"):
        return {
            "stage": "Pós-decisão",
            "action": "Conferir a ciência da empresa sobre a decisão e verificar eventual recurso, publicação e registro cabíveis.",
            "why": "Há decisão final com sanção expressa nos autos; a providência seguinte é de ciência e encerramento/seguimento do fluxo."
        }
    return _old_next_action(pages, a)


core._next_action = _next_action_rc1


_old_generic_document_draft = core._generic_document_draft


def _generic_document_draft_rc1(item, kind):
    kind = (kind or "").lower()
    if kind != "comunicacao_decisao":
        return _old_generic_document_draft(item, kind)

    pages = item["pages"]
    md = core._validated_metadata(pages)
    lines = core._draft_header(md, "MINUTA — CIÊNCIA DA DECISÃO ADMINISTRATIVA")
    lines += [
        "Fica a empresa " + md["empresa"] + " CIENTIFICADA da decisão administrativa proferida no Processo Administrativo de Penalização nº " + md["penalizacao"] + ".",
        "",
        "A íntegra da decisão deverá acompanhar esta comunicação, assegurando à interessada conhecimento dos fundamentos, da conclusão e das providências determinadas pela autoridade competente.",
        "",
        "Eventual recurso, pedido de reconsideração ou outra medida cabível deverá observar o prazo, a forma e o canal previstos na legislação e regulamentação aplicáveis, os quais deverão ser conferidos antes da expedição desta comunicação.",
        "",
        "Após a comprovação da ciência, deverão ser adotadas, conforme o caso, as providências de registro, publicação, cumprimento da decisão e encerramento ou continuidade da fase recursal.",
        "",
        "[LOCAL], [DATA].",
        "",
        "[RESPONSÁVEL / AUTORIDADE COMPETENTE]",
        "",
        "MINUTA ASSISTIDA — REVISÃO HUMANA OBRIGATÓRIA."
    ]
    return {
        "draft": "\n".join(lines),
        "sources": ["Decisão administrativa e documentos do processo analisado"]
    }


core._generic_document_draft = _generic_document_draft_rc1


_rc1_css = r"""
<style id="rc1-final-fixes">
/* Uma unica navegacao: menu lateral. */
#processTabs,
.process-tabs.visible{display:none!important}

/* Evita paineis esticados e elimina o vazio observado no preview. */
.ov-grid{align-items:start}
.ov-grid:last-child{grid-template-columns:1fr!important}
.ov-grid:last-child .ov-panel{min-height:0!important}

/* Minuta precisa ser lida como documento, nao como coluna estreita. */
.ov-grid:last-child .ov-draft-paper{
  width:100%;
  max-height:520px;
  font-size:11.5px;
  line-height:1.72;
  padding:22px 28px;
}
.ov-grid:last-child .ov-draft-actions{margin-top:10px}

/* Legibilidade do painel executivo. */
.ov-summary{font-size:11px;line-height:1.65}
.ov-evidence-item p{font-size:10px;line-height:1.5}
.ov-evidence-item span{font-size:8.3px}
.ov-time{min-width:145px}
.ov-time b{font-size:9.6px}
.ov-time small{font-size:7.8px}

@media(max-width:700px){
  .ov-grid:last-child .ov-draft-paper{padding:16px;font-size:10.8px}
}
</style>
"""

_rc1_js = r"""
<script id="rc1-final-fixes-js">
// Corrige a classificacao da aba Documentos apos o titulo ter sido refinado na v7.4.
var _grupoSecaoRC1=grupoSecao;
grupoSecao=function(titulo){
  var t=String(titulo||"").toLowerCase();
  if(
    t.indexOf("documentos e elementos da instrução")>=0 ||
    t.indexOf("documentos e elementos da instrucao")>=0 ||
    t.indexOf("dossiê processual")>=0 ||
    t.indexOf("dossie processual")>=0
  )return "documentos";
  return _grupoSecaoRC1(titulo);
};

function ovDefaultDraftKind(a){
  var m=a.module_key||selectedModule;
  if(m==="penalizacao"){
    if(a.final_sanction && a.final_sanction.length)return "comunicacao_decisao";
    if(a.has && a.has.decisao)return "comunicacao_decisao";
    return "notificacao";
  }
  if(m==="sindicancia"||m==="disciplinar"||m==="fiscalizacao")return "relatorio";
  if(m==="reequilibrio"||m==="rescisao")return "decisao";
  return "relatorio";
}
function ovDraftLabel(kind){
  return {
    notificacao:"Notificação de instauração",
    relatorio:"Relatório conclusivo",
    decisao:"Minuta de decisão",
    diligencia:"Despacho de diligência",
    despacho:"Despacho",
    intimacao:"Intimação",
    comunicacao_decisao:"Ciência da decisão administrativa"
  }[kind]||"Minuta assistida";
}
</script>
"""

core.HTML = core.HTML.replace("</head>", _rc1_css + "</head>", 1)
core.HTML = core.HTML.replace("</body>", _rc1_js + "</body>", 1)


# --- Fiscalizacao de contratos: refinamento observado no preview real ---

def _fisc_marker_pages(pages, patterns):
    regs=[re.compile(p,re.I) for p in patterns]
    hits=[]
    for p in pages:
        marker=core.norm(p.get("source_document_id") or "")
        head=core.norm((p.get("text") or "")[:260])
        if any(rx.search(marker) for rx in regs) or (not marker and any(rx.search(head) for rx in regs)):
            hits.append(p.get("page"))
    return sorted(set(x for x in hits if x))

def _fisc_page(pages, page_no):
    for p in pages:
        if p.get("page")==page_no:return p
    return None

def _fisc_body(pages, page_no, limit=360):
    p=_fisc_page(pages,page_no)
    if not p:return ""
    raw=p.get("text") or ""
    lines=[re.sub(r"\s+"," ",x).strip() for x in raw.splitlines() if x.strip()]
    marker=re.sub(r"\s+"," ",p.get("source_document_id") or "").strip()
    clean=[]
    for i,line in enumerate(lines):
        if i==0 and marker and core.norm(line)==core.norm(marker):
            continue
        if "FISCALIZA.AI" in line.upper() and "PROCESSO MODELO" in line.upper():
            continue
        if re.fullmatch(r"P[aá]gina\s+\d+\s+de\s+\d+",line,flags=re.I):
            continue
        clean.append(line)
    text=" ".join(clean)
    text=re.sub(r"\bCASO FICT[IÍ]CIO\.?\s*","",text,flags=re.I)
    return core.clip(re.sub(r"\s+"," ",text).strip(),limit)

_old_module_overlay_fiscal_rc1=core._module_overlay
def _module_overlay_fiscal_rc1(pages,a,module):
    a=_old_module_overlay_fiscal_rc1(pages,a,module)
    if module!="fiscalizacao":
        return a

    contract=_fisc_marker_pages(pages,[r"^contrato administrativo\b",r"^contrato\b"])
    designation=_fisc_marker_pages(pages,[r"portaria.{0,50}designa[cç][aã]o.{0,40}fiscal",r"designa[cç][aã]o de fiscal"])
    execution=_fisc_marker_pages(pages,[r"relat[oó]rio de execu[cç][aã]o",r"relat[oó]rio final de fiscaliza[cç][aã]o"])
    receipt=_fisc_marker_pages(pages,[r"termo de recebimento",r"\bmedi[cç][aã]o\b",r"\batesto\b"])
    occurrence=_fisc_marker_pages(pages,[r"notifica[cç][aã]o de ocorr[eê]ncia",r"comunica[cç][aã]o de ocorr[eê]ncia"])
    manifestation=_fisc_marker_pages(pages,[r"manifesta[cç][aã]o da contratada",r"resposta da contratada"])
    final_report=_fisc_marker_pages(pages,[r"relat[oó]rio final de fiscaliza[cç][aã]o"])
    service_order=_fisc_marker_pages(pages,[r"ordem de servi[cç]o"])

    regularization=sorted(set(manifestation+final_report))
    specs=[
        ("Há instrumento contratual?","instrumento contratual",contract),
        ("Há designação de fiscal ou gestor?","designação de fiscal ou gestor",designation),
        ("Há relatório de execução/fiscalização?","relatório de execução/fiscalização",execution),
        ("Há entrega, medição ou recebimento?","entrega, medição ou recebimento",receipt),
        ("Há ocorrência ou comunicação à contratada?","ocorrência ou comunicação à contratada",occurrence),
        ("Há providência ou regularização registrada?","providência ou regularização registrada",regularization),
    ]
    matrix=[]
    for question,label,pgs in specs:
        ex=_fisc_body(pages,pgs[0]) if pgs else ""
        matrix.append({
            "question":question,
            "answer":"Localizado" if pgs else "Não identificado",
            "ok":bool(pgs),
            "pages":pgs[:8],
            "label":label,
            "excerpt":ex
        })

    timeline=[]
    timeline_specs=[
        ("Contrato",contract),
        ("Designação do fiscal",designation),
        ("Ordem de serviço",service_order),
        ("Relatório de execução",_fisc_marker_pages(pages,[r"relat[oó]rio de execu[cç][aã]o"])),
        ("Medição / recebimento",receipt),
        ("Notificação de ocorrência",occurrence),
        ("Manifestação da contratada",manifestation),
        ("Relatório final de fiscalização",final_report),
    ]
    for label,pgs in timeline_specs:
        if pgs:timeline.append({"label":label,"pages":pgs[:4]})
    timeline.sort(key=lambda x:(x["pages"][0] if x.get("pages") else 999999))

    evidence=[]
    evidence_specs=[
        ("Designação e responsabilidade do fiscal",designation),
        ("Execução verificada",_fisc_marker_pages(pages,[r"relat[oó]rio de execu[cç][aã]o"])),
        ("Medição / recebimento",receipt),
        ("Ocorrência comunicada à contratada",occurrence),
        ("Manifestação e plano de correção",manifestation),
        ("Resultado do acompanhamento",final_report),
    ]
    for label,pgs in evidence_specs:
        if pgs:
            evidence.append({"label":label,"page":pgs[0],"text":_fisc_body(pages,pgs[0])})

    missing=[x for x in matrix if not x["ok"]]
    a["module_matrix"]=matrix
    a["module_timeline"]=timeline
    a["module_evidence"]=evidence
    a["process_checklist"]=[{"label":x["label"],"ok":x["ok"],"pages":x["pages"]} for x in matrix]
    a["module_summary"]=[
        {"label":x["label"],"ok":x["ok"],"value":"Localizado" if x["ok"] else "Conferir"}
        for x in matrix[:4]
    ]
    a["review_flags"]=[
        {"level":"media","text":"Não identificado com segurança: "+x["label"]+"."}
        for x in missing
    ][:5]
    # Remove cautelas herdadas da lógica sancionadora; neste módulo valem os controles próprios.
    a["pending"]=[]
    a["contradictions"]=[]

    if missing:
        a["next_action"]={
            "stage":"Fiscalização em instrução",
            "action":"Conferir ou localizar: "+missing[0]["label"]+".",
            "why":"Foram localizados "+str(len(matrix)-len(missing))+" de "+str(len(matrix))+" controles essenciais de fiscalização."
        }
    elif final_report:
        a["next_action"]={
            "stage":"Acompanhamento regular",
            "action":"Conferir o relatório final, registrar as correções verificadas e manter o acompanhamento do contrato conforme o cronograma.",
            "why":"Os controles essenciais foram localizados e há relatório final de fiscalização nos autos."
        }
    else:
        a["next_action"]={
            "stage":"Acompanhamento contratual",
            "action":"Manter o registro da execução, das ocorrências, das comunicações e das providências adotadas até o encerramento do período fiscalizado.",
            "why":"Os controles essenciais de fiscalização foram localizados."
        }

    if final_report:
        a["conclusion"]="A fiscalização possui instrumento contratual, fiscal designado, registro de execução, medição/recebimento, comunicação de ocorrência e providências de regularização. O relatório final localizado deve ser conferido antes do encerramento do acompanhamento."
    else:
        a["conclusion"]="Os autos contêm os principais controles de fiscalização contratual identificados na leitura automática. A conferência humana permanece necessária antes de qualquer encaminhamento."

    a["traceability"]=[
        {
            "claim":x["label"],
            "status":"Evidência localizada" if x["ok"] else "Conferir",
            "source":(_fisc_page(pages,x["pages"][0]) or {}).get("file","Processo") if x["pages"] else "Processo",
            "pages":x["pages"][:4]
        }
        for x in matrix
    ]
    doc_ids=set(p.get("document_id") for p in pages if p.get("document_id"))
    a.setdefault("metrics",{})
    a["metrics"]["pieces"]=len(doc_ids)
    a["metrics"]["evidence_points"]=len(evidence)
    a["metrics"]["checklist_ok"]=sum(1 for x in matrix if x["ok"])
    a["metrics"]["checklist_total"]=len(matrix)
    return a

core._module_overlay=_module_overlay_fiscal_rc1


_old_generic_document_draft_fiscal_rc1=core._generic_document_draft
def _generic_document_draft_fiscal_rc1(item,kind):
    if item.get("module")!="fiscalizacao":
        return _old_generic_document_draft_fiscal_rc1(item,kind)

    pages=item["pages"]
    profile=item.get("profile") or {}
    process_no=core._module_process_number(pages,"fiscalizacao")
    contract_no=core._first_match("\n".join(p.get("text") or "" for p in pages),[
        r"Contrato(?: Administrativo)?\s*(?:n[ºo.]?)?\s*[:\-]?\s*([0-9.\-\/]+)"
    ],default="[CONTRATO — CONFERIR]")
    company=profile.get("interested") or core._derive_interested(pages,"fiscalizacao") or "[CONTRATADA — CONFERIR]"

    exec_p=_fisc_marker_pages(pages,[r"relat[oó]rio de execu[cç][aã]o"])
    rec_p=_fisc_marker_pages(pages,[r"termo de recebimento",r"\bmedi[cç][aã]o\b"])
    occ_p=_fisc_marker_pages(pages,[r"notifica[cç][aã]o de ocorr[eê]ncia"])
    man_p=_fisc_marker_pages(pages,[r"manifesta[cç][aã]o da contratada"])
    fin_p=_fisc_marker_pages(pages,[r"relat[oó]rio final de fiscaliza[cç][aã]o"])

    execution=_fisc_body(pages,exec_p[0],520) if exec_p else "[EXECUÇÃO VERIFICADA — CONFERIR AUTOS]"
    receipt=_fisc_body(pages,rec_p[0],420) if rec_p else "[MEDIÇÃO/RECEBIMENTO — CONFERIR AUTOS]"
    occurrence=_fisc_body(pages,occ_p[0],420) if occ_p else "[OCORRÊNCIA — CONFERIR AUTOS]"
    manifestation=_fisc_body(pages,man_p[0],420) if man_p else "[MANIFESTAÇÃO DA CONTRATADA — CONFERIR AUTOS]"
    final=_fisc_body(pages,fin_p[0],520) if fin_p else "[RESULTADO DO ACOMPANHAMENTO — CONFERIR AUTOS]"

    header=[
        "Processo de Fiscalização Contratual: nº "+process_no,
        "Contrato: nº "+contract_no,
        "Contratada: "+company,
        ""
    ]

    if kind in ("relatorio","relatorio_fiscalizacao"):
        lines=["MINUTA — RELATÓRIO DE FISCALIZAÇÃO CONTRATUAL",""]+header+[
            "I — EXECUÇÃO ACOMPANHADA","",execution,"",
            "II — MEDIÇÃO / RECEBIMENTO","",receipt,"",
            "III — OCORRÊNCIAS REGISTRADAS","",occurrence,"",
            "IV — MANIFESTAÇÃO E PROVIDÊNCIAS DA CONTRATADA","",manifestation,"",
            "V — RESULTADO DO ACOMPANHAMENTO","",final,"",
            "VI — ENCAMINHAMENTO",
            "[REGISTRAR, APÓS CONFERÊNCIA DOS AUTOS, AS PROVIDÊNCIAS DE ACOMPANHAMENTO, GLOSA, ACEITE, CORREÇÃO OU OUTRO ENCAMINHAMENTO CABÍVEL.]"
        ]
    elif kind in ("notificacao","notificacao_ocorrencia"):
        lines=["MINUTA — NOTIFICAÇÃO DE OCORRÊNCIA CONTRATUAL",""]+header+[
            "Fica a contratada NOTIFICADA acerca das ocorrências registradas durante a fiscalização do contrato.","",
            "Ocorrência identificada para conferência: "+(execution if exec_p else occurrence),"",
            "A contratada deverá adotar as providências necessárias à regularização e apresentar manifestação/documentos comprobatórios no prazo e pelo canal oficial indicados abaixo.","",
            "Prazo: [CONFERIR PRAZO APLICÁVEL].",
            "Canal oficial: [INFORMAR CANAL]."
        ]
    elif kind in ("diligencia","despacho_regularizacao"):
        lines=["MINUTA — DESPACHO DE PROVIDÊNCIAS DE FISCALIZAÇÃO",""]+header+[
            "Considerando os registros da fiscalização e a necessidade de acompanhamento da execução contratual, DETERMINO:","",
            "1. conferir a execução e a medição registradas nos autos;",
            "2. acompanhar o cumprimento das providências comunicadas à contratada;",
            "3. registrar documentalmente eventual regularização, glosa, pendência remanescente ou necessidade de nova comunicação;",
            "4. encaminhar o processo à unidade competente caso os fatos exijam providência além da fiscalização ordinária.","",
            "Elementos localizados para conferência: "+occurrence+" "+manifestation
        ]
    elif kind=="registro_ocorrencia":
        lines=["MINUTA — REGISTRO DE OCORRÊNCIA DA FISCALIZAÇÃO",""]+header+[
            "Durante o acompanhamento da execução contratual, foi registrada a seguinte ocorrência:","",
            occurrence if occ_p else execution,"",
            "Providência adotada ou proposta: [DESCREVER PROVIDÊNCIA].",
            "Prazo para regularização, se aplicável: [CONFERIR].",
            "Documentos comprobatórios: [INDICAR]."
        ]
    else:
        return _old_generic_document_draft_fiscal_rc1(item,kind)

    lines += ["","[LOCAL], [DATA].","","[FISCAL/GESTOR OU RESPONSÁVEL]","",
              "MINUTA ASSISTIDA — REVISÃO HUMANA OBRIGATÓRIA."]
    src=[]
    for label,pgs in [
        ("Execução",exec_p),("Medição/recebimento",rec_p),("Ocorrência",occ_p),
        ("Manifestação",man_p),("Relatório final",fin_p)
    ]:
        if pgs:src.append(label+" · p. "+", ".join(str(x) for x in pgs))
    return {"draft":"\n".join(lines),"sources":src}

core._generic_document_draft=_generic_document_draft_fiscal_rc1


_fiscal_ui_js = r"""
<script id="fiscalizacao-final-fixes-js">
var _grupoSecaoFiscal=grupoSecao;
grupoSecao=function(titulo){
  var t=String(titulo||"").toLowerCase();
  if(t.indexOf("checklist da fiscalização")>=0 || t.indexOf("checklist da fiscalizacao")>=0)return "pendencias";
  return _grupoSecaoFiscal(titulo);
};

var _ovStagesFiscal=ovStages;
ovStages=function(a){
  if(a&&a.module_key==="fiscalizacao"){
    var rows=a.module_matrix||[];
    function ok(term){return rows.some(function(r){return String(r.label||"").toLowerCase().indexOf(term)>=0 && r.ok})}
    return [
      {label:"Contrato",done:ok("instrumento contratual")},
      {label:"Fiscal designado",done:ok("designação")},
      {label:"Execução",done:ok("relatório de execução")},
      {label:"Ocorrências",done:ok("ocorrência")},
      {label:"Regularização",done:ok("regularização")}
    ];
  }
  return _ovStagesFiscal(a);
};

var _ovDefaultDraftKindFiscal=ovDefaultDraftKind;
ovDefaultDraftKind=function(a){
  if(a&&a.module_key==="fiscalizacao")return "relatorio_fiscalizacao";
  return _ovDefaultDraftKindFiscal(a);
};

var _ovDraftLabelFiscal=ovDraftLabel;
ovDraftLabel=function(kind){
  if(kind==="relatorio_fiscalizacao")return "Relatório de fiscalização";
  return _ovDraftLabelFiscal(kind);
};

var _renderOverviewHubFiscal=renderOverviewHub;
renderOverviewHub=function(a){
  _renderOverviewHubFiscal(a);
  if(!a||a.module_key!=="fiscalizacao")return;
  var hs=document.querySelectorAll("#overviewHub .ov-evidence-block h4");
  if(hs[0])hs[0].textContent="Execução e acompanhamento";
  if(hs[1])hs[1].textContent="Ocorrências e providências";
};

var _ajustarResultadoModuloFiscal=ajustarResultadoModulo;
ajustarResultadoModulo=function(a){
  _ajustarResultadoModuloFiscal(a);
  if(!a||a.module_key!=="fiscalizacao")return;

  var map=acharSectionPorTitulo("Mapa de pendências");
  if(map){
    var h=map.querySelector("h2");if(h)h.textContent="Checklist da fiscalização";
    var k=map.querySelector(".kicker");if(k)k.textContent="Controle da execução";
  }

  var genericPending=acharSectionPorTitulo("Pendências e limites");
  if(genericPending)genericPending.style.display="none";
};

function customizarMinutasFiscalizacao(){
  var notification=document.getElementById("notificationPanel");
  if(notification){notification.style.display="none";notification.classList.remove("tab-visible")}

  var panel=document.getElementById("docsPanel");
  if(!panel)return;
  panel.style.display="block";panel.classList.add("tab-visible");

  var kicker=panel.querySelector(".kicker");if(kicker)kicker.textContent="Fluxo documental · Fiscalização contratual";
  var title=panel.querySelector(".title");if(title)title.textContent="Gerar documento de fiscalização";
  var desc=panel.querySelector(".desc");if(desc)desc.textContent="Minutas próprias do acompanhamento contratual, preenchidas somente com informações localizadas nos autos.";
  var chain=panel.querySelector(".doc-chain");
  if(chain){
    chain.innerHTML=
      '<button class="btn btn-blue" onclick="gerarDocumento(\'registro_ocorrencia\')">Registro de ocorrência</button>'+
      '<button class="btn btn-blue" onclick="gerarDocumento(\'notificacao_ocorrencia\')">Notificação de ocorrência</button>'+
      '<button class="btn btn-blue" onclick="gerarDocumento(\'despacho_regularizacao\')">Despacho de providências</button>'+
      '<button class="btn btn-primary" onclick="gerarDocumento(\'relatorio_fiscalizacao\')">Relatório de fiscalização</button>';
  }
}

var _mostrarAbaProcessoFiscal=mostrarAbaProcesso;
mostrarAbaProcesso=function(tab,btn){
  _mostrarAbaProcessoFiscal(tab,btn);
  if(selectedModule==="fiscalizacao"){
    if(tab==="perguntar"){
      var q=document.getElementById("q");
      if(q)q.placeholder="Ex.: Quais ocorrências foram registradas pela fiscalização e quais providências a contratada apresentou?";
    }
    if(tab==="minutas")customizarMinutasFiscalizacao();
  }
};
</script>
"""

core.HTML=core.HTML.replace("</body>",_fiscal_ui_js+"</body>",1)


# --- Legibilidade global do sistema v7.6 ---
_readability_css = r"""
<style id="fiscaliza-readability-v76">
/* Base de leitura */
body{font-size:14px!important}
button,input,textarea,select{font-size:13px!important}

/* Cabeçalho e contexto do processo */
.brandtext strong{font-size:18px!important}
.brandtext span{font-size:11px!important}
.workspace-title small{font-size:10px!important}
.workspace-title strong{font-size:20px!important}
.workspace-title span{font-size:12px!important;line-height:1.45!important}
.process-context span{font-size:10px!important}
.process-status{font-size:11px!important}

/* Menu lateral */
.side-brand small{font-size:9.5px!important}
.side-brand strong{font-size:15px!important}
.side-item{font-size:12px!important;padding:11px 10px!important}
.side-ico{font-size:10px!important}
.side-footer{font-size:9.5px!important;line-height:1.6!important}

/* KPIs e cartões */
.dash-metric small{font-size:9.5px!important}
.dash-metric strong{font-size:20px!important}
.dash-metric strong.text{font-size:12px!important;line-height:1.35!important}
.dash-metric .mini{font-size:9.5px!important}

/* Títulos, rótulos e descrições */
.kicker,.panel-kicker,.ov-eyebrow{font-size:10px!important}
.title,.panel-title{font-size:20px!important}
.desc,.panel-desc{font-size:12.5px!important;line-height:1.55!important}
#result.system-result .title,#result.system-result h2{font-size:17px!important}
.section h2,.ov-panel-head h3{font-size:16px!important}

/* Visão geral */
.ov-title{font-size:21px!important}
.ov-sub{font-size:12.5px!important;line-height:1.6!important}
.ov-chip{font-size:10px!important}
.ov-next small{font-size:9.5px!important}
.ov-next strong{font-size:14px!important}
.ov-next p{font-size:11.5px!important;line-height:1.55!important}
.ov-progress-head b{font-size:13px!important}
.ov-progress-head span{font-size:10px!important}
.ov-stage{font-size:10.5px!important}
.ov-summary{font-size:12.5px!important;line-height:1.65!important}
.ov-evidence-item p{font-size:11.5px!important;line-height:1.55!important}
.ov-evidence-item span{font-size:9.5px!important}
.ov-time b{font-size:10.5px!important}
.ov-time small{font-size:9px!important}

/* Documentos e evidências */
.piece-name{font-size:13px!important}
.source,.file-name{font-size:10.5px!important}
.page-chip{font-size:9.5px!important}
.matrix th{font-size:10.5px!important}
.matrix td{font-size:11.5px!important;line-height:1.5!important}
.finding-text{font-size:12px!important;line-height:1.55!important}
.source-card{font-size:9.5px!important}
.dossier-label{font-size:11.5px!important}
.dossier-source{font-size:10px!important}
.dossier-status{font-size:9.5px!important}
.dossier-group-title{font-size:9.5px!important}
.process-fact small{font-size:9px!important}
.process-fact strong{font-size:12px!important}

/* Cronologia */
.timeline-step b{font-size:11.5px!important;line-height:1.4!important}
.timeline-step .tp{font-size:9.5px!important}
.ov-time{font-size:10.5px!important}

/* Pendências e alertas */
.check-row{font-size:11.5px!important;line-height:1.5!important}
.review-flag{font-size:11.5px!important;line-height:1.5!important}
.warning,.warn{font-size:11.5px!important;line-height:1.55!important}
.empty,.result-empty{font-size:11.5px!important}

/* Perguntas */
.qa input,.qa-input{font-size:13px!important}
.answer-text,#answer{font-size:12.5px!important;line-height:1.6!important}

/* Minutas */
.draft-text,.ov-draft-paper{font-size:12.5px!important;line-height:1.7!important}
.draft-toolbar strong{font-size:12px!important}
.draft-toolbar span,.draft-sources{font-size:10px!important}
.doc-chain .btn{font-size:11px!important}

/* Relatório e privacidade */
.privacy-box p,.footnote,.footer-note{font-size:11.5px!important;line-height:1.55!important}

/* Botões */
.btn{font-size:12px!important}
.workspace-back,.recent-open,.config-btn{font-size:10.5px!important}

/* Mantém densidade sem voltar a ficar minúsculo em notebooks */
@media(max-width:1100px){
  body{font-size:13.5px!important}
  .side-item{font-size:11.5px!important}
  .matrix td{font-size:11px!important}
}
</style>
"""

core.HTML = core.HTML.replace("</head>", _readability_css + "</head>", 1)


# --- Padrão tipográfico definitivo: Calibri 12 ---
_calibri12_css = r"""
<style id="fiscaliza-calibri12">
:root{--font-ui:Calibri,"Segoe UI",Arial,sans-serif}

/* Fonte padrão do produto */
body,button,input,textarea,select{font-family:var(--font-ui)!important}

/* Piso de leitura: 12pt para todo texto operacional */
body,
.side-item,
.side-footer,
.workspace-title span,
.process-context span,
.process-status,
.dash-metric small,
.dash-metric strong.text,
.dash-metric .mini,
.desc,.panel-desc,
.ov-sub,.ov-chip,.ov-next p,
.ov-progress-head span,.ov-stage,
.ov-summary,.ov-evidence-item p,.ov-evidence-item span,
.ov-time,.ov-time b,.ov-time small,
.piece-name,.source,.file-name,.page-chip,
.matrix th,.matrix td,.finding-text,.source-card,
.dossier-label,.dossier-source,.dossier-status,.dossier-group-title,
.process-fact small,.process-fact strong,
.timeline-step b,.timeline-step .tp,
.check-row,.review-flag,.warning,.warn,.empty,.result-empty,
.qa input,.qa-input,.answer-text,#answer,
.draft-text,.ov-draft-paper,.draft-toolbar strong,.draft-toolbar span,.draft-sources,
.privacy-box p,.footnote,.footer-note,
.btn,.workspace-back,.recent-open,.config-btn{
  font-size:12pt!important;
  line-height:1.45!important
}

/* Hierarquia */
.kicker,.panel-kicker,.ov-eyebrow,.workspace-title small,
.side-brand small{font-size:12pt!important}
.side-brand strong{font-size:14pt!important}
.brandtext strong{font-size:16pt!important}
.brandtext span{font-size:12pt!important}
.workspace-title strong{font-size:16pt!important}
.title,.panel-title,#result.system-result .title,#result.system-result h2,
.section h2,.ov-panel-head h3{font-size:15pt!important;line-height:1.25!important}
.ov-title{font-size:17pt!important;line-height:1.2!important}
h1{font-size:20pt!important}
h2{font-size:16pt!important}
h3{font-size:14pt!important}

/* Ajustes de espaço para a nova escala tipográfica */
.system-layout{grid-template-columns:250px minmax(0,1fr)!important}
.side-item{padding:12px 11px!important}
.dash-metric{min-height:76px!important}
.matrix th,.matrix td{padding:10px 11px!important}
.ov-panel,.section{overflow-wrap:anywhere}
.timeline-step{min-width:170px!important}

@media(max-width:980px){
  .system-layout{grid-template-columns:1fr!important}
}
</style>
"""
core.HTML = core.HTML.replace("</head>", _calibri12_css + "</head>", 1)


# --- Legibilidade forte: Calibri 12 real em toda a interface v7.7 ---
_calibri12_strict_css = r"""
<style id="fiscaliza-calibri12-strict">
:root{--font-ui:Calibri,"Segoe UI",Arial,sans-serif}

/* 12pt no navegador equivale aproximadamente a 16px. */
body{font-family:var(--font-ui)!important;font-size:16px!important}

/* HOME / seleção de módulos */
.module-panel.home-only .kicker,
.module-toolbar-copy .kicker{font-size:16px!important}
.module-toolbar-copy h2{font-size:24px!important;line-height:1.25!important}
.module-toolbar-copy p{font-size:16px!important;line-height:1.55!important}

.screen-home .module-card{
  min-height:150px!important;
  padding:18px!important;
}
.screen-home .module-card.active{padding:18px!important}
.screen-home .module-icon{
  width:42px!important;height:42px!important;
  font-size:16px!important;
  margin-bottom:12px!important
}
.screen-home .module-name{
  font-size:18px!important;
  line-height:1.35!important
}
.screen-home .module-desc{
  font-size:16px!important;
  line-height:1.5!important;
  margin-top:7px!important;
  padding-right:8px!important
}
.module-category{
  font-size:14px!important;
  padding:5px 8px!important;
  top:14px!important;right:14px!important
}
.screen-home .module-card:after{
  font-size:14px!important;
  bottom:13px!important;
  right:14px!important
}

/* Processos recentes */
.recent-head .kicker{font-size:16px!important}
.recent-head h3{font-size:22px!important}
.recent-head p{font-size:16px!important;line-height:1.5!important}
.recent-row{
  min-height:78px!important;
  grid-template-columns:minmax(220px,1.2fr) minmax(180px,1fr) minmax(170px,.8fr) minmax(150px,.7fr) auto!important;
  gap:16px!important;
  padding:14px 16px!important
}
.recent-main b{font-size:17px!important}
.recent-main span,
.recent-cell,
.recent-status{font-size:16px!important;line-height:1.45!important}
.recent-open{
  font-size:16px!important;
  padding:10px 14px!important
}
.recent-empty{font-size:16px!important}

/* Topo */
.brandtext strong{font-size:20px!important}
.brandtext span{font-size:16px!important}
.config-btn{font-size:16px!important}
.live,.topmeta{font-size:16px!important}

/* Workspace */
.workspace-back{font-size:16px!important}
.workspace-title small{font-size:16px!important}
.workspace-title strong{font-size:22px!important}
.workspace-title span{font-size:16px!important;line-height:1.5!important}
.process-context span{font-size:16px!important;padding:5px 9px!important}
.process-status{font-size:16px!important}

/* Menu lateral */
.side-brand small{font-size:16px!important}
.side-brand strong{font-size:19px!important}
.side-item{
  font-size:17px!important;
  line-height:1.35!important;
  padding:13px 12px!important
}
.side-ico{
  width:28px!important;height:28px!important;
  font-size:14px!important
}
.side-footer{font-size:15px!important;line-height:1.55!important}

/* Estado vazio */
.system-empty{min-height:230px!important;padding:34px!important}
.empty-launch h3{font-size:22px!important}
.empty-launch p{font-size:16px!important;line-height:1.55!important;max-width:760px!important}
.empty-launch .btn{font-size:16px!important;padding:12px 18px!important}

/* KPIs */
.dash-metric{min-height:88px!important;padding:12px 14px!important}
.dash-metric small{font-size:15px!important}
.dash-metric strong{font-size:24px!important}
.dash-metric strong.text{font-size:16px!important;line-height:1.4!important}
.dash-metric .mini{font-size:15px!important}

/* Conteúdo interno */
.kicker,.panel-kicker,.ov-eyebrow{font-size:16px!important}
.title,.panel-title,
#result.system-result .title,
#result.system-result h2,
.section h2,
.ov-panel-head h3{font-size:21px!important;line-height:1.3!important}

.desc,.panel-desc,
.ov-sub,.ov-summary,
.ov-next p,
.ov-evidence-item p,
.finding-text,
.warning,.warn,
.empty,.result-empty,
.check-row,.review-flag,
.privacy-box p,.footnote,.footer-note{
  font-size:16px!important;
  line-height:1.6!important
}

.ov-title{font-size:24px!important}
.ov-chip,.ov-stage,.ov-progress-head span,
.ov-next small,.ov-evidence-item span,
.ov-time,.ov-time b,.ov-time small{
  font-size:15px!important;
  line-height:1.45!important
}
.ov-next strong{font-size:18px!important}

/* Documentos / evidências / cronologia */
.piece-name,
.dossier-label,
.process-fact strong,
.timeline-step b{
  font-size:16px!important;
  line-height:1.5!important
}
.source,.file-name,.page-chip,
.dossier-source,.dossier-status,.dossier-group-title,
.process-fact small,.timeline-step .tp,
.source-card{
  font-size:15px!important;
  line-height:1.5!important
}
.matrix th{font-size:15px!important}
.matrix td{font-size:16px!important;line-height:1.55!important}
.matrix th,.matrix td{padding:12px 13px!important}

/* Perguntar / minutas / botões */
.qa input,.qa-input,
.answer-text,#answer,
.draft-text,.ov-draft-paper{
  font-family:var(--font-ui)!important;
  font-size:16px!important;
  line-height:1.65!important
}
.draft-toolbar strong,
.draft-toolbar span,
.draft-sources{font-size:16px!important}
.btn,.doc-chain .btn{
  font-family:var(--font-ui)!important;
  font-size:16px!important;
  padding:11px 16px!important
}

/* Garante que elementos auxiliares específicos não voltem abaixo do piso */
.module-selected,
.home-badge,
.home-benefits span,
.home-side-card p,
.home-stat span,
.settings-head p,
.settings-note,
.np-field label,
.np-field input,
.demo-note,
.bank-step b,
.bank-step span{
  font-size:16px!important;
  line-height:1.5!important
}

/* Mais espaço horizontal para textos maiores */
.system-layout{grid-template-columns:270px minmax(0,1fr)!important}
.system-sidebar{padding:14px!important}
.piece-grid{gap:14px!important}
.summary-grid{gap:12px!important}

@media(max-width:1150px){
  .recent-row{grid-template-columns:1fr auto!important}
  .recent-cell.hide-mobile{display:none!important}
}
@media(max-width:980px){
  .system-layout{grid-template-columns:1fr!important}
  .side-nav{grid-template-columns:repeat(2,1fr)!important}
}
</style>
"""

core.HTML = core.HTML.replace("</head>", _calibri12_strict_css + "</head>", 1)


# --- Fiscalização: leitura executiva em cards e hierarquia visual v7.8 ---
_fiscal_exec_css = r"""
<style id="fiscalizacao-executiva-v78">
/* Títulos e subtítulos realmente legíveis */
#overviewHub .ov-panel-head h3{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:22px!important;
  line-height:1.25!important;
  margin:0!important
}
#overviewHub .ov-panel-head p{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;
  line-height:1.5!important;
  margin:5px 0 0!important;
  color:#65788b!important
}
#overviewHub .ov-link{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;
  line-height:1.35!important
}

/* Resumo executivo: curto e com respiro */
#overviewHub .ov-summary{
  font-size:17px!important;
  line-height:1.65!important;
  margin:0 0 16px!important;
  color:#29445a!important;
  max-width:980px
}

/* Grade visual da Fiscalização */
.fisc-exec-grid{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:12px;
  margin-top:8px
}
.fisc-exec-card{
  border:1px solid #dbe5ec;
  border-left:5px solid #7da7c4;
  border-radius:12px;
  padding:15px 16px;
  min-height:150px;
  background:#f7fbfe
}
.fisc-exec-card.execution{
  background:#f2f8fc;
  border-left-color:#5f95b8
}
.fisc-exec-card.measurement{
  background:#f2faf7;
  border-left-color:#55a58c
}
.fisc-exec-card.occurrence{
  background:#fff9ed;
  border-left-color:#d39a3b
}
.fisc-exec-card.action{
  background:#f5f7fb;
  border-left-color:#778fa8
}
.fisc-exec-head{
  display:flex;
  align-items:center;
  gap:9px;
  margin-bottom:9px
}
.fisc-exec-icon{
  width:30px;height:30px;
  border-radius:8px;
  display:grid;
  place-items:center;
  font-size:16px;
  font-weight:800;
  background:rgba(255,255,255,.78);
  border:1px solid rgba(17,49,73,.08)
}
.fisc-exec-card h4{
  margin:0!important;
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:18px!important;
  line-height:1.3!important;
  color:#17364e!important;
  text-transform:none!important;
  letter-spacing:0!important
}
.fisc-exec-card p{
  margin:0!important;
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;
  line-height:1.55!important;
  color:#354e63!important
}
.fisc-exec-source{
  display:inline-flex;
  margin-top:11px;
  padding:5px 8px;
  border-radius:999px;
  background:rgba(255,255,255,.82);
  border:1px solid #d8e2e9;
  color:#61798c;
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:14px!important;
  line-height:1.25!important
}

/* Dossiê ao lado: títulos e dados sem mini-fontes */
#overviewHub .ov-dossier-num{
  font-size:15px!important
}
#overviewHub .ov-dossier-group b{
  font-size:16px!important;
  line-height:1.4!important
}
#overviewHub .ov-dossier-group span{
  font-size:15px!important;
  line-height:1.4!important
}
#overviewHub .ov-dossier-group{
  padding:12px!important
}

/* Em notebook, mantém leitura sem comprimir os cards */
@media(max-width:1180px){
  #overviewHub .ov-grid{grid-template-columns:1fr!important}
}
@media(max-width:760px){
  .fisc-exec-grid{grid-template-columns:1fr}
}
</style>
"""
core.HTML = core.HTML.replace("</head>", _fiscal_exec_css + "</head>", 1)

_fiscal_exec_js = r"""
<script id="fiscalizacao-executiva-v78-js">
function fiscShortText(txt,max){
  txt=String(txt||"").replace(/\s+/g," ").trim();
  max=max||210;
  if(txt.length<=max)return txt;
  var cut=txt.slice(0,max);
  var end=Math.max(cut.lastIndexOf(". "),cut.lastIndexOf("; "));
  if(end>110)cut=cut.slice(0,end+1);
  else cut=cut.replace(/\s+\S*$/,"")+"…";
  return cut;
}
function fiscFindEvidence(a,terms){
  var ev=a.module_evidence||[];
  terms=terms||[];
  for(var i=0;i<ev.length;i++){
    var lab=String(ev[i].label||"").toLowerCase();
    if(terms.some(function(t){return lab.indexOf(t)>=0}))return ev[i];
  }
  return null;
}
function fiscExecCard(cls,icon,title,item,fallback){
  var text=item&&item.text?fiscShortText(item.text,220):fallback;
  var src=item?ovPageSource(item):"";
  return '<article class="fisc-exec-card '+cls+'">'+
    '<div class="fisc-exec-head"><span class="fisc-exec-icon">'+icon+'</span><h4>'+ovEsc(title)+'</h4></div>'+
    '<p>'+ovEsc(text||"Nenhum registro prioritário localizado automaticamente.")+'</p>'+
    (src?'<span class="fisc-exec-source">'+ovEsc(src)+'</span>':'')+
  '</article>';
}
function refinarLeituraExecutivaFiscalizacao(a){
  if(!a||a.module_key!=="fiscalizacao")return;
  var hub=document.getElementById("overviewHub");if(!hub)return;
  var panels=hub.querySelectorAll(".ov-panel");
  var panel=null;
  for(var i=0;i<panels.length;i++){
    var h=panels[i].querySelector(".ov-panel-head h3");
    if(h&&h.textContent.trim()==="Leitura executiva"){panel=panels[i];break}
  }
  if(!panel)return;

  var subtitle=panel.querySelector(".ov-panel-head p");
  if(subtitle)subtitle.textContent="Síntese dos fatos essenciais da execução contratual.";

  var summary=panel.querySelector(".ov-summary");
  if(summary){
    summary.textContent="Os autos apresentam os controles essenciais da fiscalização. Abaixo estão os quatro pontos que merecem leitura imediata antes de abrir os documentos detalhados.";
  }

  var execution=fiscFindEvidence(a,["execução verificada","responsabilidade do fiscal"]);
  var measurement=fiscFindEvidence(a,["medição","recebimento"]);
  var occurrence=fiscFindEvidence(a,["ocorrência"]);
  var action=fiscFindEvidence(a,["manifestação","plano de correção","resultado do acompanhamento"]);

  var old=panel.querySelector(".ov-evidence-columns");
  if(old){
    old.outerHTML='<div class="fisc-exec-grid">'+
      fiscExecCard("execution","↗","Execução",execution,"A execução contratual foi acompanhada e registrada pela fiscalização.")+
      fiscExecCard("measurement","✓","Medição / recebimento",measurement,"Conferir medição, recebimento e eventual glosa dos itens não executados.")+
      fiscExecCard("occurrence","!","Ocorrências",occurrence,"Conferir as ocorrências registradas e as comunicações encaminhadas à contratada.")+
      fiscExecCard("action","→","Providências / regularização",action,"Conferir as providências adotadas e o resultado da regularização.")+
    '</div>';
  }
}

var _renderOverviewHubExecV78=renderOverviewHub;
renderOverviewHub=function(a){
  _renderOverviewHubExecV78(a);
  if(a&&a.module_key==="fiscalizacao")refinarLeituraExecutivaFiscalizacao(a);
};
</script>
"""
core.HTML = core.HTML.replace("</body>", _fiscal_exec_js + "</body>", 1)


# --- Piso tipográfico absoluto nas telas internas v7.9 ---
_internal_text_floor_css = r"""
<style id="fiscaliza-internal-text-floor-v79">
/*
  Regra definitiva:
  todo texto informativo nas telas internas >= 16px (~12pt).
  Ícones decorativos ficam fora dessa regra.
*/

/* Visão geral: inclusive alertas/pontos de atenção */
#overviewHub p,
#overviewHub small,
#overviewHub b,
#overviewHub strong,
#overviewHub span:not(.ov-row-icon):not(.fisc-exec-icon),
#overviewHub button,
#overviewHub a{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;
  line-height:1.5!important
}

/* Ponto de atenção que ainda aparecia minúsculo */
#overviewHub .ov-row b{
  font-size:17px!important;
  line-height:1.4!important
}
#overviewHub .ov-row p{
  font-size:16px!important;
  line-height:1.55!important;
  margin-top:4px!important
}
#overviewHub .ov-row .ov-source{
  font-size:16px!important;
  line-height:1.4!important;
  white-space:normal!important
}
#overviewHub .ov-note,
#overviewHub .ov-draft-loading{
  font-size:16px!important;
  line-height:1.5!important
}

/* Telas detalhadas: Documentos, Evidências, Cronologia e Pendências */
#result.system-result p,
#result.system-result small,
#result.system-result label,
#result.system-result span:not(.piece-icon):not(.flag-dot),
#result.system-result b,
#result.system-result strong,
#result.system-result td,
#result.system-result th,
#result.system-result button,
#result.system-result a,
#result.system-result summary{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;
  line-height:1.5!important
}

/* Checklist de fiscalização */
#result.system-result .check-row,
#result.system-result .check-row span,
#result.system-result .check-ok,
#result.system-result .check-miss{
  font-size:16px!important;
  line-height:1.5!important
}
#result.system-result .check-row{
  padding:12px 0!important;
  gap:18px!important
}

/* Revisão/pontos antes da conclusão */
#result.system-result .review-flag,
#result.system-result .review-flag span{
  font-size:16px!important;
  line-height:1.55!important
}

/* Referências e rastreabilidade também devem ser lidas sem esforço */
#result.system-result .trace-row,
#result.system-result .trace-row b,
#result.system-result .trace-row span,
#result.system-result .source,
#result.system-result .source-card,
#result.system-result .page-chip,
#result.system-result .finding-foot{
  font-size:16px!important;
  line-height:1.5!important
}

/* Títulos preservam hierarquia maior */
#overviewHub h2,
#result.system-result h2{
  font-size:22px!important;
  line-height:1.3!important
}
#overviewHub h3,
#result.system-result h3{
  font-size:20px!important;
  line-height:1.3!important
}
#overviewHub h4,
#result.system-result h4{
  font-size:18px!important;
  line-height:1.35!important
}

/* Rótulos superiores permanecem legíveis, mas discretos */
#overviewHub .ov-eyebrow,
#result.system-result .kicker{
  font-size:16px!important;
  line-height:1.4!important;
  letter-spacing:.06em!important
}
</style>
"""

core.HTML = core.HTML.replace("</head>", _internal_text_floor_css + "</head>", 1)


# --- Home aprovada: visual premium institucional v8.0 ---
_home_v80_css = r"""
<style id="fiscaliza-home-approved-v80">
/* Página inicial aprovada: institucional, moderna e legível */
.screen-home{padding-bottom:20px!important}
.screen-home .home-welcome{margin-bottom:18px!important}

.home-commercial-hero.home-approved-v80{
  display:grid!important;
  grid-template-columns:minmax(0,1.35fr) minmax(220px,.52fr) minmax(330px,.63fr)!important;
  gap:22px!important;
  align-items:center!important;
  min-height:330px!important;
  padding:30px 32px!important;
  border-radius:20px!important;
  background:
    radial-gradient(circle at 74% 20%,rgba(24,199,189,.20),transparent 28%),
    radial-gradient(circle at 95% 80%,rgba(15,164,157,.16),transparent 30%),
    linear-gradient(118deg,#0d3150 0%,#104366 55%,#087b7e 100%)!important;
  box-shadow:0 18px 44px rgba(12,47,74,.16)!important;
  overflow:hidden!important;
  position:relative!important
}
.home-commercial-hero.home-approved-v80:before{
  content:"";position:absolute;inset:auto -90px -150px auto;width:420px;height:420px;border-radius:50%;
  border:70px solid rgba(255,255,255,.035);pointer-events:none
}
.home-commercial-hero.home-approved-v80:after{
  content:"";position:absolute;left:42%;top:-120px;width:380px;height:380px;
  background:linear-gradient(140deg,rgba(255,255,255,.05),rgba(255,255,255,0));
  transform:rotate(18deg);border-radius:90px;pointer-events:none
}
.home-approved-v80 .home-copy{z-index:2}
.home-approved-v80 .home-badge{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;
  font-weight:700!important;
  letter-spacing:.08em!important;
  padding:8px 12px!important;
  border:1px solid rgba(255,255,255,.18)!important;
  background:rgba(255,255,255,.09)!important;
  color:#dff7f4!important
}
.home-approved-v80 h1{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  margin:15px 0 0!important;
  font-size:38px!important;
  line-height:1.08!important;
  letter-spacing:-.7px!important;
  color:#fff!important;
  max-width:760px!important
}
.home-approved-v80 h1 .hero-accent{color:#55d8d2!important}
.home-approved-v80 .home-copy>p{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  margin:14px 0 0!important;
  font-size:17px!important;
  line-height:1.6!important;
  color:#e2edf3!important;
  max-width:760px!important
}
.home-approved-v80 .home-benefits{
  display:flex!important;gap:9px!important;flex-wrap:wrap!important;margin-top:20px!important
}
.home-approved-v80 .home-benefits span{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;
  line-height:1.25!important;
  padding:9px 12px!important;
  border-radius:999px!important;
  border:1px solid rgba(255,255,255,.18)!important;
  background:rgba(255,255,255,.08)!important;
  color:#f4fbfd!important
}
.home-approved-v80 .home-benefits span:before{
  content:"✓"!important;color:#65e3d6!important;font-weight:900!important;margin-right:3px
}

/* Ilustração vetorial sem dependência externa */
.home-visual{
  position:relative;z-index:2;min-height:230px;display:flex;align-items:center;justify-content:center
}
.home-visual-card{
  width:190px;height:190px;border-radius:28px;
  background:linear-gradient(145deg,rgba(255,255,255,.18),rgba(255,255,255,.05));
  border:1px solid rgba(255,255,255,.16);
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 24px 54px rgba(4,34,54,.20);
  transform:rotate(-3deg)
}
.home-visual-card svg{width:138px;height:138px;display:block}
.home-visual-note{
  position:absolute;right:-4px;bottom:5px;
  width:150px;color:#ecffff;font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px;line-height:1.35;font-weight:700
}

/* Card de fluxo */
.home-approved-v80 .home-side-card{
  z-index:3!important;
  background:rgba(255,255,255,.98)!important;
  border:1px solid rgba(255,255,255,.46)!important;
  border-radius:17px!important;
  padding:20px!important;
  box-shadow:0 16px 36px rgba(2,35,55,.14)!important;
  min-height:270px!important
}
.home-approved-v80 .home-side-card small{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;color:#087f77!important;font-weight:800!important;
  text-transform:uppercase!important;letter-spacing:.06em!important
}
.home-approved-v80 .home-side-card strong{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:22px!important;line-height:1.2!important;color:#102f49!important;margin-top:7px!important
}
.home-approved-v80 .home-side-card p{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;line-height:1.55!important;color:#5e7488!important;margin:10px 0 0!important
}
.home-approved-v80 .home-stats{
  display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:8px!important;margin-top:16px!important
}
.home-approved-v80 .home-stat{
  padding:10px!important;border:1px solid #dbe5ec!important;border-radius:11px!important;background:#f8fbfd!important
}
.home-approved-v80 .home-stat b{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:18px!important;color:#0f3150!important
}
.home-approved-v80 .home-stat span{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;line-height:1.35!important;color:#6b8092!important
}
.home-flow-foot{
  margin-top:14px;padding-top:12px;border-top:1px solid #e1e8ee;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;font-size:16px;line-height:1.35;
  color:#147c77;text-transform:uppercase;letter-spacing:.05em;font-weight:700
}

/* Módulos */
.screen-home .module-panel.home-only{
  background:#fff!important;border:1px solid #dfe8ee!important;
  box-shadow:0 10px 28px rgba(13,48,74,.06)!important;
  padding:22px 24px 24px!important;border-radius:18px!important
}
.screen-home .module-toolbar{margin-bottom:18px!important}
.screen-home .module-toolbar-copy h2{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:25px!important;line-height:1.2!important;color:#102f49!important
}
.screen-home .module-toolbar-copy p{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;line-height:1.55!important;color:#657a8d!important
}
.screen-home .module-grid{
  display:grid!important;
  grid-template-columns:repeat(3,minmax(0,1fr))!important;
  gap:12px!important
}
.screen-home .module-card{
  min-height:150px!important;
  padding:16px 18px 18px!important;
  border-radius:14px!important;
  border:1px solid #d7e2ea!important;
  background:#fff!important;
  box-shadow:0 3px 10px rgba(15,47,73,.025)!important;
  overflow:hidden!important
}
.screen-home .module-card:hover{
  transform:translateY(-2px)!important;
  box-shadow:0 12px 26px rgba(15,47,73,.09)!important
}
.screen-home .module-icon{
  width:44px!important;height:44px!important;border-radius:11px!important;
  display:grid!important;place-items:center!important;margin-bottom:12px!important
}
.screen-home .module-icon svg{width:24px;height:24px;display:block}
.screen-home .module-name{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:18px!important;line-height:1.3!important;font-weight:700!important;color:#102f49!important
}
.screen-home .module-desc{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;line-height:1.45!important;color:#667c8f!important;margin-top:6px!important;padding-right:70px!important
}
.screen-home .module-category{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:15px!important;line-height:1.2!important;
  padding:5px 9px!important;border-radius:999px!important;
  background:#eef4f7!important;color:#5f7487!important;
  top:14px!important;right:14px!important
}
.screen-home .module-card:after{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;line-height:1.2!important;
  right:15px!important;bottom:16px!important;font-weight:700!important
}

/* Cores por fluxo */
.screen-home .module-card[data-module="penalizacao"] .module-icon{background:#e9f2ff!important;color:#1767c7!important}
.screen-home .module-card[data-module="penalizacao"]:after{color:#1767c7!important}
.screen-home .module-card[data-module="fiscalizacao"] .module-icon{background:#e6f6f1!important;color:#087d72!important}
.screen-home .module-card[data-module="fiscalizacao"]:after{color:#087d72!important}
.screen-home .module-card[data-module="reequilibrio"] .module-icon{background:#fff0df!important;color:#c46818!important}
.screen-home .module-card[data-module="reequilibrio"]:after{color:#c46818!important}
.screen-home .module-card[data-module="rescisao"] .module-icon{background:#fdecee!important;color:#b62939!important}
.screen-home .module-card[data-module="rescisao"]:after{color:#b62939!important}
.screen-home .module-card[data-module="disciplinar"] .module-icon{background:#f0edff!important;color:#6246c7!important}
.screen-home .module-card[data-module="disciplinar"]:after{color:#6246c7!important}
.screen-home .module-card[data-module="sindicancia"] .module-icon{background:#e5f6f4!important;color:#087a74!important}
.screen-home .module-card[data-module="sindicancia"]:after{color:#087a74!important}

/* Processos recentes: cards executivos */
.recent-panel.home-approved-recent{
  margin-top:14px!important;
  padding:20px 22px!important;
  border:1px solid #dfe8ee!important;border-radius:17px!important;
  background:#fff!important;
  box-shadow:0 9px 24px rgba(13,48,74,.05)!important
}
.home-approved-recent .recent-head{margin-bottom:14px!important;align-items:flex-end!important}
.home-approved-recent .recent-head h3{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:24px!important;color:#102f49!important
}
.home-approved-recent .recent-head p{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;line-height:1.5!important;color:#657a8d!important
}
.recent-session-label{
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px;color:#1768b7;font-weight:700;white-space:nowrap
}
.home-approved-recent .recent-list{
  display:grid!important;
  grid-template-columns:repeat(3,minmax(0,1fr))!important;
  gap:12px!important
}
.home-approved-recent .recent-row{
  display:grid!important;
  grid-template-columns:52px minmax(0,1fr)!important;
  grid-template-areas:
    "icon main"
    "icon status"
    "icon action"!important;
  gap:7px 12px!important;
  min-height:132px!important;
  padding:14px!important;
  border:1px solid #dce6ed!important;border-radius:13px!important;background:#fbfdfe!important
}
.recent-icon{
  grid-area:icon;width:48px;height:48px;border-radius:11px;
  display:grid;place-items:center;background:#eaf2f8;color:#1767c7
}
.recent-icon svg{width:25px;height:25px}
.home-approved-recent .recent-main{grid-area:main}
.home-approved-recent .recent-main b{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:17px!important;color:#102f49!important
}
.home-approved-recent .recent-main span{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;line-height:1.4!important;color:#667c8f!important
}
.recent-meta{
  margin-top:4px;font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px;line-height:1.4;color:#7a8d9d
}
.recent-status-wrap{grid-area:status;display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.home-approved-recent .recent-status{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:15px!important;line-height:1.25!important;
  display:inline-flex!important;padding:5px 9px!important;border-radius:999px!important;
  background:#e8f5f2!important;color:#08776e!important
}
.home-approved-recent .recent-status:before{width:7px!important;height:7px!important}
.home-approved-recent .recent-open{
  grid-area:action;justify-self:end;
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;padding:8px 12px!important;border-radius:9px!important;
  background:#edf4f8!important;color:#10314e!important
}
.home-approved-recent .recent-empty{
  grid-column:1/-1;font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;line-height:1.5!important
}

/* Rodapé */
.fiscaliza-home-footer{
  margin-top:14px;padding:14px 4px 4px;
  display:flex;justify-content:space-between;gap:20px;align-items:center;
  border-top:1px solid #dce5eb;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;font-size:16px;line-height:1.4;color:#718597
}
.fiscaliza-home-footer strong{color:#14334d}

@media(max-width:1180px){
  .home-commercial-hero.home-approved-v80{
    grid-template-columns:minmax(0,1.25fr) minmax(180px,.45fr)!important
  }
  .home-approved-v80 .home-side-card{grid-column:1/-1!important;min-height:auto!important}
  .home-visual-note{display:none}
}
@media(max-width:980px){
  .home-commercial-hero.home-approved-v80{grid-template-columns:1fr!important}
  .home-visual{display:none!important}
  .screen-home .module-grid,
  .home-approved-recent .recent-list{grid-template-columns:repeat(2,minmax(0,1fr))!important}
}
@media(max-width:660px){
  .home-approved-v80 h1{font-size:31px!important}
  .screen-home .module-grid,
  .home-approved-recent .recent-list{grid-template-columns:1fr!important}
  .fiscaliza-home-footer{flex-direction:column;align-items:flex-start}
}
</style>
"""

core.HTML = core.HTML.replace("</head>", _home_v80_css + "</head>", 1)

_home_v80_js = r"""
<script id="fiscaliza-home-approved-v80-js">
function homeIconSvg(key){
  var base='fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
  var map={
    penalizacao:'<svg viewBox="0 0 24 24"><path '+base+' d="M14 4l6 6M12 6l6 6M5 19l7-7M4 20l3-3M15 3l6 6-3 3-6-6z"/></svg>',
    fiscalizacao:'<svg viewBox="0 0 24 24"><path '+base+' d="M6 3h9l3 3v15H6z"/><path '+base+' d="M15 3v4h4M9 11h6M9 15h6"/></svg>',
    reequilibrio:'<svg viewBox="0 0 24 24"><path '+base+' d="M5 20V11M10 20V5M15 20v-7M20 20V8"/></svg>',
    rescisao:'<svg viewBox="0 0 24 24"><path '+base+' d="M6 6l12 12M18 6L6 18"/></svg>',
    disciplinar:'<svg viewBox="0 0 24 24"><circle '+base+' cx="9" cy="8" r="3"/><circle '+base+' cx="17" cy="8" r="2.5"/><path '+base+' d="M3 19c.8-3.2 3-5 6-5s5.2 1.8 6 5M14 14c3.2 0 5.3 1.8 6 5"/></svg>',
    sindicancia:'<svg viewBox="0 0 24 24"><circle '+base+' cx="10" cy="10" r="6"/><path '+base+' d="M14.5 14.5L20 20"/></svg>'
  };
  return map[key]||'<svg viewBox="0 0 24 24"><circle '+base+' cx="12" cy="12" r="8"/></svg>';
}
function homeShieldSvg(){
  return '<svg viewBox="0 0 160 160" aria-hidden="true">'+
    '<rect x="27" y="18" width="76" height="105" rx="10" fill="#d8edf7" opacity=".82" transform="rotate(-8 65 70)"/>'+
    '<rect x="47" y="24" width="78" height="108" rx="10" fill="#b9ddec" opacity=".9" transform="rotate(5 86 78)"/>'+
    '<path d="M98 53l30 12v25c0 23-15 37-30 45-15-8-30-22-30-45V65z" fill="#0d5875" stroke="#79e0d8" stroke-width="4"/>'+
    '<path d="M84 91l9 9 18-22" fill="none" stroke="#7af1e3" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>'+
    '<path d="M43 47h39M40 62h36M38 77h25" stroke="#6fa9c3" stroke-width="5" stroke-linecap="round"/>'+
  '</svg>';
}
function moduloCategoriaCor(key){
  return {
    penalizacao:"#1767c7",fiscalizacao:"#087d72",reequilibrio:"#c46818",
    rescisao:"#b62939",disciplinar:"#6246c7",sindicancia:"#087a74"
  }[key]||"#1767c7";
}
function aplicarHomeAprovadaV80(){
  var hero=document.querySelector(".home-commercial-hero");
  if(hero){
    hero.classList.add("home-approved-v80");
    var copy=hero.querySelector(".home-copy");
    if(copy){
      var badge=copy.querySelector(".home-badge");
      if(badge)badge.textContent="Inteligência processual para gestão pública";
      var h=copy.querySelector("h1");
      if(h)h.innerHTML='Inteligência processual com <span class="hero-accent">evidência rastreável.</span>';
      var p=copy.querySelector("p");
      if(p)p.textContent="Organize autos, acompanhe pendências e produza documentos assistidos em fluxos especializados para gestão contratual e responsabilização administrativa.";
    }
    if(!hero.querySelector(".home-visual")){
      var visual=document.createElement("div");
      visual.className="home-visual";
      visual.innerHTML='<div class="home-visual-card">'+homeShieldSvg()+'</div><div class="home-visual-note">Mais transparência para uma gestão mais eficiente.</div>';
      var side=hero.querySelector(".home-side-card");
      if(side)hero.insertBefore(visual,side);else hero.appendChild(visual);
    }
    var side=hero.querySelector(".home-side-card");
    if(side){
      side.innerHTML=
        '<div><small>Fluxo de trabalho</small><strong>Do documento à decisão humana</strong>'+
        '<p>Um ambiente único para organizar gestão contratual e responsabilização administrativa com rastreabilidade e padrão de trabalho.</p></div>'+
        '<div class="home-stats">'+
          '<div class="home-stat"><b>6</b><span>fluxos</span></div>'+
          '<div class="home-stat"><b>ID + p.</b><span>rastreabilidade</span></div>'+
          '<div class="home-stat"><b>Humana</b><span>decisão final</span></div>'+
        '</div>'+
        '<div class="home-flow-foot">Tecnologia a serviço do interesse público</div>';
    }
  }

  document.querySelectorAll(".module-card").forEach(function(card){
    var key=card.getAttribute("data-module");
    if(!commercialModuleMeta[key])return;
    var icon=card.querySelector(".module-icon");
    if(icon)icon.innerHTML=homeIconSvg(key);
    var tag=card.querySelector(".module-category");
    if(tag){
      tag.style.border="1px solid "+moduloCategoriaCor(key)+"22";
      tag.style.color=moduloCategoriaCor(key);
    }
  });

  var recent=document.getElementById("recentPanel");
  if(recent)recent.classList.add("home-approved-recent");

  if(!document.getElementById("fiscalizaHomeFooter")){
    var home=document.getElementById("screenHome");
    if(home){
      var footer=document.createElement("footer");
      footer.id="fiscalizaHomeFooter";
      footer.className="fiscaliza-home-footer";
      footer.innerHTML='<div><strong>Fiscaliza.AI Municipal</strong> &nbsp;|&nbsp; Prefeitura Municipal · Unidade Administrativa</div><div>Gestão pública mais eficiente, transparente e responsável.</div>';
      home.appendChild(footer);
    }
  }
}

var _deixarHomeMaisProdutoV80=deixarHomeMaisProduto;
deixarHomeMaisProduto=function(){
  _deixarHomeMaisProdutoV80();
  setTimeout(aplicarHomeAprovadaV80,0);
};

renderProcessosRecentes=function(){
  var listEl=document.getElementById("recentList");if(!listEl)return;
  var panel=document.getElementById("recentPanel");
  if(panel){
    panel.classList.add("home-approved-recent");
    var head=panel.querySelector(".recent-head");
    if(head)head.innerHTML='<div><div class="kicker">Continuidade do trabalho</div><h3>Processos recentes</h3><p>Seus últimos acessos desta sessão. Retome de onde parou.</p></div><div class="recent-session-label">Sessão atual</div>';
  }
  var list=recentStore();
  if(!list.length){
    listEl.innerHTML='<div class="recent-empty">Quando você analisar um processo, ele aparecerá aqui para acesso rápido durante esta sessão.</div>';
    return;
  }
  listEl.innerHTML=list.slice(0,3).map(function(x){
    var dt=new Date(x.updated);
    var when=isNaN(dt)?"":dt.toLocaleString("pt-BR",{day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"});
    var key=x.module||"geral";
    return '<article class="recent-row">'+
      '<div class="recent-icon" style="color:'+moduloCategoriaCor(key)+'">'+homeIconSvg(key)+'</div>'+
      '<div class="recent-main"><b>'+esc(x.number)+'</b><span>'+esc(x.module_label||"Processo")+'</span><div class="recent-meta">'+esc(x.interested||"Interessado não informado")+(when?' · último acesso em '+esc(when):'')+'</div></div>'+
      '<div class="recent-status-wrap"><span class="recent-status">'+esc(x.stage||"Analisado")+'</span></div>'+
      '<button class="recent-open" onclick="abrirProcessoRecente(\''+esc(x.id)+'\')">Abrir ↗</button>'+
    '</article>';
  }).join("");
};

var _prepararHomeComercialV80=prepararHomeComercial;
prepararHomeComercial=function(){
  _prepararHomeComercialV80();
  setTimeout(function(){aplicarHomeAprovadaV80();renderProcessosRecentes()},0);
};

document.addEventListener("DOMContentLoaded",function(){
  setTimeout(function(){aplicarHomeAprovadaV80();renderProcessosRecentes()},220);
});
</script>
"""
core.HTML = core.HTML.replace("</body>", _home_v80_js + "</body>", 1)


# --- Refino de densidade e leitura: Home + módulos internos v8.1 ---
_layout_readability_v81_css = r"""
<style id="fiscaliza-layout-readability-v81">

/* =========================================================
   HOME: mantém o visual aprovado, mas traz os serviços para cima
   ========================================================= */
.home-commercial-hero.home-approved-v80{
  min-height:245px!important;
  padding:22px 26px!important;
  grid-template-columns:minmax(0,1.45fr) minmax(150px,.38fr) minmax(300px,.62fr)!important;
  gap:18px!important
}
.home-approved-v80 h1{
  font-size:34px!important;
  margin-top:10px!important
}
.home-approved-v80 .home-copy>p{
  margin-top:9px!important;
  font-size:16px!important;
  line-height:1.5!important
}
.home-approved-v80 .home-benefits{
  margin-top:13px!important;
  gap:7px!important
}
.home-approved-v80 .home-benefits span{
  padding:7px 10px!important
}
.home-visual{
  min-height:170px!important
}
.home-visual-card{
  width:145px!important;
  height:145px!important;
  border-radius:22px!important
}
.home-visual-card svg{
  width:108px!important;
  height:108px!important
}
.home-visual-note{
  display:none!important
}
.home-approved-v80 .home-side-card{
  min-height:205px!important;
  padding:16px!important
}
.home-approved-v80 .home-side-card strong{
  font-size:20px!important
}
.home-approved-v80 .home-side-card p{
  margin-top:6px!important;
  line-height:1.45!important
}
.home-approved-v80 .home-stats{
  margin-top:10px!important
}
.home-approved-v80 .home-stat{
  padding:8px!important
}
.home-flow-foot{
  margin-top:9px!important;
  padding-top:8px!important;
  font-size:14px!important
}

.screen-home .module-panel.home-only{
  padding:18px 20px 20px!important
}
.screen-home .module-toolbar{
  margin-bottom:12px!important
}
.screen-home .module-toolbar-copy h2{
  font-size:23px!important
}
.screen-home .module-toolbar-copy p{
  margin-top:3px!important
}
.screen-home .module-card{
  min-height:142px!important
}

/* =========================================================
   ÁREA OPERACIONAL: mais largura útil para informação densa
   ========================================================= */
.system-layout{
  grid-template-columns:250px minmax(0,1fr)!important;
  gap:16px!important
}
.system-main{
  min-width:0!important;
  width:100%!important
}
#result.system-result{
  min-width:0!important;
  width:100%!important
}

/* Quando um container misto mostra só um bloco, não o deixa preso
   à primeira coluna da antiga grade. */
#result.system-result > .cols[data-group="mixed"],
#result.system-result > .control-grid[data-group="mixed"]{
  grid-template-columns:minmax(0,1fr)!important
}
#result.system-result > .cols[data-group="mixed"] > .section,
#result.system-result > .control-grid[data-group="mixed"] > .section{
  width:100%!important;
  min-width:0!important
}

/* =========================================================
   EVIDÊNCIAS: tabela com distribuição de largura previsível
   ========================================================= */
#result.system-result table.matrix{
  width:100%!important;
  table-layout:fixed!important;
  border-collapse:collapse!important
}
#result.system-result table.matrix th,
#result.system-result table.matrix td{
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;
  line-height:1.5!important;
  padding:14px 14px!important;
  vertical-align:top!important;
  overflow-wrap:anywhere!important
}
#result.system-result table.matrix th:nth-child(1),
#result.system-result table.matrix td:nth-child(1){
  width:24%!important
}
#result.system-result table.matrix th:nth-child(2),
#result.system-result table.matrix td:nth-child(2){
  width:12%!important
}
#result.system-result table.matrix th:nth-child(3),
#result.system-result table.matrix td:nth-child(3){
  width:49%!important
}
#result.system-result table.matrix th:nth-child(4),
#result.system-result table.matrix td:nth-child(4){
  width:15%!important;
  white-space:nowrap!important;
  text-align:right!important
}
#result.system-result .matrix-ok,
#result.system-result .matrix-limit{
  white-space:nowrap!important;
  word-break:normal!important;
  overflow-wrap:normal!important;
  font-weight:700!important
}
#result.system-result .ref-stack{
  gap:7px!important;
  align-items:center!important
}
#result.system-result .doc-id-chip,
#result.system-result .doc-origin,
#result.system-result .page-chip{
  font-size:16px!important;
  line-height:1.35!important
}

/* =========================================================
   PONTOS A CONFRONTAR / ACHADOS: uma coluna larga
   ========================================================= */
#result.system-result [data-group="evidencias"] .finding,
#result.system-result .finding{
  display:grid!important;
  grid-template-columns:42px minmax(0,1fr)!important;
  gap:13px!important;
  width:100%!important;
  padding:15px!important;
  margin:0 0 12px!important;
  border:1px solid #dce5eb!important;
  border-radius:13px!important;
  background:#fbfdfe!important
}
#result.system-result .finding-num{
  width:32px!important;
  height:32px!important;
  border-radius:9px!important;
  display:grid!important;
  place-items:center!important;
  font-size:16px!important;
  line-height:1!important
}
#result.system-result .finding-text{
  font-size:16px!important;
  line-height:1.55!important
}
#result.system-result .finding-foot{
  display:flex!important;
  align-items:center!important;
  flex-wrap:wrap!important;
  gap:7px!important;
  margin-top:9px!important;
  font-size:16px!important;
  line-height:1.45!important
}

/* Força containers de confrontação/evidência a ocupar a largura disponível. */
#result.system-result .cols{
  gap:14px!important
}
#result.system-result .cols > .section[data-group="evidencias"]{
  width:100%!important;
  min-width:0!important
}

/* =========================================================
   CRONOLOGIA: cards largos em trilho horizontal legível
   ========================================================= */
#result.system-result .timeline{
  display:flex!important;
  gap:12px!important;
  width:100%!important;
  overflow-x:auto!important;
  overflow-y:hidden!important;
  padding:8px 2px 14px!important;
  scroll-snap-type:x proximity!important
}
#result.system-result .timeline-step{
  flex:0 0 250px!important;
  min-width:250px!important;
  max-width:250px!important;
  min-height:155px!important;
  padding:14px!important;
  border:1px solid #dce5eb!important;
  border-top:4px solid #0b8f82!important;
  border-radius:12px!important;
  background:#fff!important;
  scroll-snap-align:start!important;
  overflow:hidden!important
}
#result.system-result .timeline-step .tp{
  font-size:16px!important;
  line-height:1.45!important;
  margin-bottom:9px!important
}
#result.system-result .timeline-step b{
  display:block!important;
  font-size:16px!important;
  line-height:1.45!important;
  overflow-wrap:anywhere!important
}
#result.system-result .timeline::-webkit-scrollbar{
  height:10px
}
#result.system-result .timeline::-webkit-scrollbar-thumb{
  background:#a8b8c5;
  border-radius:999px
}
#result.system-result .timeline::-webkit-scrollbar-track{
  background:#edf2f5;
  border-radius:999px
}

/* =========================================================
   PENDÊNCIAS: sem cartão estreito e sem status quebrado
   ========================================================= */
#result.system-result .control-grid{
  grid-template-columns:minmax(0,1fr)!important;
  gap:14px!important
}
#result.system-result .control-card{
  width:100%!important;
  max-width:none!important;
  padding:16px 18px!important
}
#result.system-result .check-row{
  display:grid!important;
  grid-template-columns:minmax(0,1fr) 165px!important;
  align-items:center!important;
  gap:18px!important;
  padding:13px 0!important;
  font-size:16px!important;
  line-height:1.5!important
}
#result.system-result .check-row > :last-child,
#result.system-result .check-ok,
#result.system-result .check-miss{
  justify-self:end!important;
  text-align:right!important;
  white-space:nowrap!important;
  word-break:normal!important;
  overflow-wrap:normal!important;
  font-size:16px!important;
  line-height:1.35!important
}
#result.system-result [data-group="pendencias"]{
  width:100%!important;
  max-width:none!important
}

/* KPI de topo também sem microtexto */
.dashboard-metrics .dash-metric small,
.dashboard-metrics .dash-metric .mini{
  font-size:16px!important;
  line-height:1.35!important
}
.dashboard-metrics .dash-metric strong.text{
  font-size:17px!important;
  line-height:1.4!important
}

/* Responsividade sem voltar a comprimir */
@media(max-width:1100px){
  .home-commercial-hero.home-approved-v80{
    grid-template-columns:minmax(0,1fr) minmax(285px,.48fr)!important
  }
  .home-visual{display:none!important}
  .system-layout{
    grid-template-columns:235px minmax(0,1fr)!important
  }
}
@media(max-width:900px){
  .system-layout{
    grid-template-columns:1fr!important
  }
  #result.system-result table.matrix{
    min-width:820px!important
  }
  #result.system-result [data-group="evidencias"]{
    overflow-x:auto!important
  }
}
@media(max-width:700px){
  #result.system-result .check-row{
    grid-template-columns:1fr!important
  }
  #result.system-result .check-row > :last-child,
  #result.system-result .check-ok,
  #result.system-result .check-miss{
    justify-self:start!important;
    text-align:left!important
  }
}
</style>
"""

core.HTML = core.HTML.replace("</head>", _layout_readability_v81_css + "</head>", 1)


# --- Ajuste visual final v1: hierarquia de leitura v8.2 ---
_visual_final_v82_css = r"""
<style id="fiscaliza-visual-final-v82">

/* =========================================================
   VISÃO GERAL — separação visual e leitura por prioridade
   ========================================================= */
#overviewHub .ov-hero{
  grid-template-columns:minmax(0,1.55fr) minmax(300px,.45fr)!important;
  gap:16px!important;
  padding:18px!important;
  background:#fff!important
}
#overviewHub .ov-next{
  border-left:0!important;
  padding:16px!important;
  border:1px solid #cfe3e0!important;
  border-radius:13px!important;
  background:linear-gradient(180deg,#f3fbf9 0%,#edf8f6 100%)!important
}
#overviewHub .ov-next small{
  font-size:16px!important;
  text-transform:none!important;
  letter-spacing:0!important;
  color:#5e7587!important
}
#overviewHub .ov-next strong{
  font-size:19px!important;
  line-height:1.3!important;
  margin-top:5px!important
}
#overviewHub .ov-next p{
  font-size:16px!important;
  line-height:1.55!important
}

/* Quatro fatos-chave viram cartões independentes */
#overviewHub .ov-status-grid{
  grid-template-columns:repeat(4,minmax(0,1fr))!important;
  gap:9px!important;
  margin-top:14px!important
}
#overviewHub .ov-status{
  border:1px solid #dbe5ec!important;
  border-top-width:3px!important;
  border-radius:11px!important;
  padding:12px 13px!important;
  min-height:88px!important;
  background:#f8fbfd!important
}
#overviewHub .ov-status:nth-child(1){
  background:#f0f7ff!important;
  border-color:#cbdff3!important;
  border-top-color:#5c95c5!important
}
#overviewHub .ov-status:nth-child(2){
  background:#f7f4fd!important;
  border-color:#e1d9f2!important;
  border-top-color:#8a71bd!important
}
#overviewHub .ov-status:nth-child(3){
  background:#f0faf6!important;
  border-color:#cce7db!important;
  border-top-color:#4f9b7e!important
}
#overviewHub .ov-status:nth-child(4){
  background:#fff8ed!important;
  border-color:#eedfca!important;
  border-top-color:#c88d43!important
}
#overviewHub .ov-status small{
  display:block!important;
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;
  line-height:1.35!important;
  text-transform:none!important;
  letter-spacing:0!important;
  font-weight:700!important;
  color:#60768a!important
}
#overviewHub .ov-status b{
  display:block!important;
  margin-top:7px!important;
  font-size:17px!important;
  line-height:1.4!important;
  color:#17354d!important
}

/* Leitura executiva: dois blocos visualmente separados */
#overviewHub .ov-evidence-columns{
  grid-template-columns:repeat(2,minmax(0,1fr))!important;
  gap:12px!important;
  margin-top:12px!important
}
#overviewHub .ov-evidence-block{
  border:1px solid #dce6ed!important;
  border-radius:12px!important;
  padding:14px 15px!important;
  background:#f8fbfd!important
}
#overviewHub .ov-evidence-block:first-child{
  background:#f3faf7!important;
  border-color:#d5e9e0!important
}
#overviewHub .ov-evidence-block:last-child{
  background:#fff9ef!important;
  border-color:#eee1cb!important
}
#overviewHub .ov-evidence-block h4{
  margin:0 0 9px!important;
  font-size:18px!important;
  line-height:1.3!important;
  text-transform:none!important;
  letter-spacing:0!important;
  color:#193750!important
}
#overviewHub .ov-evidence-item{
  border-top:1px solid rgba(98,119,136,.16)!important;
  padding:10px 0!important
}
#overviewHub .ov-evidence-item:first-of-type{border-top:0!important;padding-top:0!important}
#overviewHub .ov-evidence-item p{
  font-size:16px!important;
  line-height:1.55!important;
  color:#344f64!important
}
#overviewHub .ov-evidence-item span{
  font-size:16px!important;
  line-height:1.4!important;
  color:#72899b!important;
  margin-top:5px!important
}

/* Dossiê: ligeiramente diferenciado da leitura principal */
#overviewHub .ov-grid > .ov-panel:nth-child(2){
  background:#fcfdfe!important
}

/* =========================================================
   CRONOLOGIA DA VISÃO GERAL — documento primeiro, ID depois
   ========================================================= */
#overviewHub .ov-timeline{
  gap:10px!important;
  padding:4px 0 9px!important
}
#overviewHub .ov-time.timeline-v82{
  flex:0 0 205px!important;
  min-width:205px!important;
  border-left:0!important;
  border:1px solid #dce6ed!important;
  border-top:4px solid #5f9cbd!important;
  border-radius:11px!important;
  padding:12px!important;
  background:#fbfdfe!important
}
#overviewHub .ov-time.timeline-v82:nth-child(4n+2){border-top-color:#7c72b7!important}
#overviewHub .ov-time.timeline-v82:nth-child(4n+3){border-top-color:#4e9a7e!important}
#overviewHub .ov-time.timeline-v82:nth-child(4n+4){border-top-color:#c48a43!important}
.timeline-v82-title{
  font-size:16px!important;
  line-height:1.45!important;
  font-weight:700!important;
  color:#17354d!important;
  text-transform:none!important;
  letter-spacing:0!important
}
.timeline-v82-type{
  display:inline-flex!important;
  margin-top:9px!important;
  padding:5px 8px!important;
  border-radius:999px!important;
  background:#eef4f8!important;
  color:#526c80!important;
  font-size:15px!important;
  line-height:1.25!important;
  font-weight:700!important;
  text-transform:none!important
}
.timeline-v82-meta{
  display:flex!important;
  flex-wrap:wrap!important;
  gap:6px!important;
  margin-top:9px!important
}
.timeline-v82-page,
.timeline-v82-id{
  display:inline-flex!important;
  align-items:center!important;
  padding:5px 8px!important;
  border-radius:999px!important;
  border:1px solid #dbe5ec!important;
  background:#fff!important;
  color:#71879a!important;
  font-size:15px!important;
  line-height:1.25!important;
  font-weight:500!important;
  text-transform:none!important
}

/* =========================================================
   CRONOLOGIA DETALHADA — cartão editorial, sem caixa alta
   ========================================================= */
#result.system-result .timeline-step.timeline-v82{
  flex:0 0 260px!important;
  min-width:260px!important;
  max-width:260px!important;
  min-height:190px!important;
  padding:16px!important;
  border:1px solid #d9e4eb!important;
  border-top:4px solid #5f9cbd!important;
  border-radius:13px!important;
  background:#fff!important
}
#result.system-result .timeline-step.timeline-v82:nth-child(4n+2){border-top-color:#7c72b7!important}
#result.system-result .timeline-step.timeline-v82:nth-child(4n+3){border-top-color:#4e9a7e!important}
#result.system-result .timeline-step.timeline-v82:nth-child(4n+4){border-top-color:#c48a43!important}
#result.system-result .timeline-step.timeline-v82 h4{
  margin:0!important;
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:18px!important;
  line-height:1.45!important;
  color:#17354d!important;
  text-transform:none!important;
  letter-spacing:0!important;
  font-weight:700!important;
  overflow-wrap:anywhere!important
}
#result.system-result .timeline-step.timeline-v82 .timeline-v82-type{
  margin-top:11px!important
}
#result.system-result .timeline-step.timeline-v82 .timeline-v82-meta{
  margin-top:12px!important
}

/* =========================================================
   EVIDÊNCIAS E PENDÊNCIAS — status em chips, sem quebras
   ========================================================= */
.status-chip-v82{
  display:inline-flex!important;
  align-items:center!important;
  justify-content:center!important;
  gap:6px!important;
  min-width:112px!important;
  padding:6px 10px!important;
  border-radius:999px!important;
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;
  line-height:1.25!important;
  font-weight:700!important;
  white-space:nowrap!important
}
.status-chip-v82.ok{
  background:#e9f7f2!important;
  color:#08786e!important;
  border:1px solid #c6e5dc!important
}
.status-chip-v82.warn{
  background:#fff5e6!important;
  color:#9a6500!important;
  border:1px solid #ecd8b3!important
}
#result.system-result td.matrix-ok,
#result.system-result td.matrix-limit{
  vertical-align:middle!important
}
#result.system-result .check-row{
  border-radius:0!important
}
#result.system-result .check-row:nth-child(even){
  background:#fbfdfe!important
}

/* Pontos a confrontar: reforço sutil por posição */
#result.system-result .finding:nth-of-type(3n+1){border-left:5px solid #5f9cbd!important}
#result.system-result .finding:nth-of-type(3n+2){border-left:5px solid #c48a43!important}
#result.system-result .finding:nth-of-type(3n+3){border-left:5px solid #4e9a7e!important}

/* =========================================================
   CAIXA ALTA: apenas micro-rótulos institucionais
   ========================================================= */
#result.system-result .timeline-step h4,
#overviewHub .ov-evidence-block h4,
#overviewHub .ov-status small,
#result.system-result .piece-name,
#result.system-result .finding-text{
  text-transform:none!important;
  letter-spacing:normal!important
}

@media(max-width:1050px){
  #overviewHub .ov-status-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}
}
@media(max-width:720px){
  #overviewHub .ov-status-grid,
  #overviewHub .ov-evidence-columns{grid-template-columns:1fr!important}
}
</style>
"""

core.HTML = core.HTML.replace("</head>", _visual_final_v82_css + "</head>", 1)

_visual_final_v82_js = r"""
<script id="fiscaliza-visual-final-v82-js">
function readableDocumentTitleV82(value){
  var s=String(value||"").replace(/\s+/g," ").trim();
  if(!s)return "Documento";
  var letters=s.replace(/[^A-Za-zÀ-ÖØ-öø-ÿ]/g,"");
  if(letters && letters===letters.toUpperCase()){
    s=s.toLocaleLowerCase("pt-BR");
    s=s.charAt(0).toLocaleUpperCase("pt-BR")+s.slice(1);
    s=s.replace(/\bnº\b/gi,"nº");
  }
  return s;
}
function timelineItemsV82(a){
  var out=[];
  if(!a)return out;

  if(a.module_key==="penalizacao"){
    (a.pieces||[]).forEach(function(piece){
      var docs=piece.documents||[],pages=piece.pages||[];
      if(docs.length){
        docs.forEach(function(d,idx){
          out.push({
            title:readableDocumentTitleV82(d.source_document_id||piece.label),
            type:piece.label||"Documento",
            page:d.page||pages[idx]||pages[0]||null,
            id:d.document_id||"",
            order:d.page||pages[idx]||pages[0]||999999
          });
        });
      }else{
        out.push({
          title:readableDocumentTitleV82(piece.label),
          type:"Documento",
          page:pages[0]||null,
          id:"",
          order:pages[0]||999999
        });
      }
    });
  }else{
    (a.module_timeline||[]).forEach(function(item){
      var docs=item.documents||[],pages=item.pages||[];
      if(docs.length){
        docs.forEach(function(d,idx){
          out.push({
            title:readableDocumentTitleV82(d.source_document_id||item.label),
            type:item.label||"Documento",
            page:d.page||pages[idx]||pages[0]||null,
            id:d.document_id||"",
            order:d.page||pages[idx]||pages[0]||999999
          });
        });
      }else{
        out.push({
          title:readableDocumentTitleV82(item.label),
          type:item.label||"Documento",
          page:pages[0]||null,
          id:"",
          order:pages[0]||999999
        });
      }
    });
  }
  out.sort(function(x,y){return (x.order||999999)-(y.order||999999)});
  return out;
}
function timelineCardV82(item,compact){
  var title=ovEsc(item.title||"Documento");
  var type=ovEsc(readableDocumentTitleV82(item.type||"Documento"));
  var page=item.page?'<span class="timeline-v82-page">p. '+ovEsc(item.page)+'</span>':"";
  var id=item.id?'<span class="timeline-v82-id">ID '+ovEsc(item.id)+'</span>':"";
  if(compact){
    return '<article class="ov-time timeline-v82">'+
      '<div class="timeline-v82-title">'+title+'</div>'+
      '<span class="timeline-v82-type">'+type+'</span>'+
      '<div class="timeline-v82-meta">'+page+id+'</div>'+
    '</article>';
  }
  return '<article class="timeline-step timeline-v82">'+
    '<h4>'+title+'</h4>'+
    '<span class="timeline-v82-type">'+type+'</span>'+
    '<div class="timeline-v82-meta">'+page+id+'</div>'+
  '</article>';
}
function refinarVisaoGeralV82(a){
  var hub=document.getElementById("overviewHub");
  if(!hub||!a)return;

  /* Remove caixa alta pesada nos dois cabeçalhos da leitura executiva. */
  var evheads=hub.querySelectorAll(".ov-evidence-block h4");
  if(evheads[0])evheads[0].textContent="Elementos favoráveis / manifestações";
  if(evheads[1])evheads[1].textContent="Pontos a confrontar";

  /* Documento é a informação principal; ID fica por último. */
  var line=hub.querySelector(".ov-timeline");
  if(line){
    var items=timelineItemsV82(a).slice(0,7);
    line.innerHTML=items.length
      ?items.map(function(x){return timelineCardV82(x,true)}).join("")
      :'<article class="ov-time timeline-v82"><div class="timeline-v82-title">Cronologia ainda não consolidada</div></article>';
  }
}
function refinarCronologiaDetalhadaV82(a){
  var timeline=acharSectionPorTitulo("Linha do tempo do processo");
  if(!timeline||!a)return;
  var items=timelineItemsV82(a);
  var html='<div class="kicker">Cronologia dos autos · '+ovEsc(a.module_label||"Processo")+'</div>'+
    '<h2>Linha do tempo do processo</h2>';
  if(!items.length){
    html+='<div class="empty">Nenhum marco específico foi localizado com segurança.</div>';
  }else{
    html+='<div class="timeline">'+items.map(function(x){return timelineCardV82(x,false)}).join("")+'</div>';
  }
  timeline.innerHTML=html;
}
function statusChipsV82(){
  document.querySelectorAll("#result.system-result td.matrix-ok,#result.system-result td.matrix-limit").forEach(function(td){
    if(td.querySelector(".status-chip-v82"))return;
    var ok=td.classList.contains("matrix-ok");
    td.innerHTML='<span class="status-chip-v82 '+(ok?"ok":"warn")+'">'+(ok?"✓ Confirmado":"! Conferir")+'</span>';
  });

  document.querySelectorAll("#result.system-result .check-ok,#result.system-result .check-miss").forEach(function(el){
    if(el.querySelector(".status-chip-v82"))return;
    var ok=el.classList.contains("check-ok");
    el.innerHTML='<span class="status-chip-v82 '+(ok?"ok":"warn")+'">'+(ok?"✓ Confirmado":"! Conferir")+'</span>';
  });
}

var _renderOverviewHubV82=renderOverviewHub;
renderOverviewHub=function(a){
  _renderOverviewHubV82(a);
  setTimeout(function(){refinarVisaoGeralV82(a)},0);
};

var _ajustarResultadoModuloV82=ajustarResultadoModulo;
ajustarResultadoModulo=function(a){
  _ajustarResultadoModuloV82(a);
  setTimeout(function(){
    refinarCronologiaDetalhadaV82(a);
    statusChipsV82();
  },0);
};
</script>
"""
core.HTML = core.HTML.replace("</body>", _visual_final_v82_js + "</body>", 1)


# --- Cronologia em grade e evidências mais limpas v8.3 ---
_timeline_grid_v83_css = r"""
<style id="fiscaliza-timeline-grid-v83">

/* =========================================================
   CRONOLOGIA DA VISÃO GERAL — sem rolagem horizontal
   ========================================================= */
#overviewHub .ov-timeline{
  display:grid!important;
  grid-template-columns:repeat(4,minmax(0,1fr))!important;
  gap:12px!important;
  overflow:visible!important;
  padding:4px 0 0!important
}
#overviewHub .ov-time.timeline-v82{
  min-width:0!important;
  width:100%!important;
  max-width:none!important;
  min-height:150px!important;
  margin:0!important
}

/* =========================================================
   CRONOLOGIA DETALHADA — quebra automática de linha
   ========================================================= */
#result.system-result .timeline{
  display:grid!important;
  grid-template-columns:repeat(4,minmax(0,1fr))!important;
  gap:14px!important;
  width:100%!important;
  overflow:visible!important;
  padding:10px 0 2px!important;
  scroll-snap-type:none!important
}
#result.system-result .timeline-step.timeline-v82{
  min-width:0!important;
  max-width:none!important;
  width:100%!important;
  min-height:190px!important;
  flex:none!important;
  scroll-snap-align:none!important
}

/* Remove qualquer aparência residual de scrollbar */
#result.system-result .timeline::-webkit-scrollbar,
#overviewHub .ov-timeline::-webkit-scrollbar{
  display:none!important
}

/* Cards da cronologia mais editoriais */
#result.system-result .timeline-step.timeline-v82 h4,
#overviewHub .timeline-v82-title{
  color:#17354d!important;
  font-weight:700!important;
  text-transform:none!important;
  letter-spacing:0!important;
  overflow-wrap:anywhere!important;
  word-break:normal!important
}
#result.system-result .timeline-step.timeline-v82 .timeline-v82-type,
#overviewHub .timeline-v82-type{
  max-width:100%!important;
  white-space:normal!important;
  text-align:left!important
}
.timeline-v82-meta{
  align-items:center!important
}
.timeline-v82-page,
.timeline-v82-id{
  font-size:15px!important;
  font-weight:500!important;
  color:#73889a!important;
  background:#fbfcfd!important;
  border-color:#dce5eb!important
}
.timeline-v82-id{
  opacity:.82
}

/* =========================================================
   EVIDÊNCIAS — nome do documento antes do ID
   ========================================================= */
#result.system-result table.matrix td:nth-child(3) .ref-stack{
  display:flex!important;
  flex-wrap:wrap!important;
  align-items:center!important;
  gap:7px!important
}

/* O nome/origem do documento ganha prioridade visual */
#result.system-result table.matrix td:nth-child(3) .doc-origin{
  order:-2!important;
  flex-basis:100%!important;
  display:block!important;
  margin:0 0 4px!important;
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;
  line-height:1.45!important;
  font-weight:600!important;
  color:#405b70!important;
  text-transform:none!important;
  letter-spacing:0!important
}

/* ID e página passam a ser metadados */
#result.system-result table.matrix td:nth-child(3) .doc-id-chip{
  order:1!important;
  background:#f3f7fa!important;
  border:1px solid #dce5eb!important;
  color:#698095!important;
  font-size:15px!important;
  font-weight:600!important;
  padding:5px 8px!important
}
#result.system-result table.matrix td:nth-child(3) .page-chip{
  order:2!important;
  background:#f7f9fb!important;
  border:1px solid #dce5eb!important;
  color:#667e92!important;
  font-size:15px!important;
  font-weight:600!important;
  padding:5px 8px!important
}

/* Mais respiro entre linhas da matriz */
#result.system-result table.matrix tbody tr{
  border-top:1px solid #e2e9ee!important
}
#result.system-result table.matrix tbody tr:first-child{
  border-top:0!important
}
#result.system-result table.matrix td{
  padding-top:15px!important;
  padding-bottom:15px!important
}

/* Status continua compacto, mas sem dominar a tela */
#result.system-result .status-chip-v82{
  min-width:118px!important;
  box-shadow:none!important
}

/* =========================================================
   Responsividade
   ========================================================= */
@media(max-width:1180px){
  #overviewHub .ov-timeline,
  #result.system-result .timeline{
    grid-template-columns:repeat(3,minmax(0,1fr))!important
  }
}
@media(max-width:900px){
  #overviewHub .ov-timeline,
  #result.system-result .timeline{
    grid-template-columns:repeat(2,minmax(0,1fr))!important
  }
}
@media(max-width:620px){
  #overviewHub .ov-timeline,
  #result.system-result .timeline{
    grid-template-columns:1fr!important
  }
}
</style>
"""

core.HTML = core.HTML.replace("</head>", _timeline_grid_v83_css + "</head>", 1)


# --- Refino de clareza: Evidências v2 v8.4 ---
_evidence_clarity_v84_css = r"""
<style id="fiscaliza-evidence-clarity-v84">

/* Cabeçalhos de seção: menos técnicos, mais claros */
#result.system-result [data-group="evidencias"] > .kicker,
#result.system-result [data-group="evidencias"] .kicker{
  font-size:16px!important;
  line-height:1.4!important;
  letter-spacing:.055em!important
}
#result.system-result [data-group="evidencias"] h2{
  margin-top:5px!important;
  margin-bottom:16px!important
}

/* =========================================================
   CONFRONTO DOCUMENTAL — estrutura fixa de leitura
   ========================================================= */
.confront-v84-list{
  display:grid;
  grid-template-columns:1fr;
  gap:12px
}
.confront-v84-card{
  display:grid;
  grid-template-columns:44px minmax(0,1fr);
  gap:14px;
  width:100%;
  padding:16px 18px;
  border:1px solid #dce6ed;
  border-left:5px solid #5f9cbd;
  border-radius:13px;
  background:#fbfdfe
}
.confront-v84-card:nth-child(3n+2){border-left-color:#c48a43;background:#fffdf9}
.confront-v84-card:nth-child(3n+3){border-left-color:#4e9a7e;background:#f9fdfb}
.confront-v84-num{
  width:34px;height:34px;border-radius:9px;
  display:grid;place-items:center;
  background:#103a59;color:#fff;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px;font-weight:800
}
.confront-v84-label{
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:15px!important;
  line-height:1.3!important;
  font-weight:700!important;
  color:#71879a!important;
  margin-bottom:5px!important
}
.confront-v84-text{
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:17px!important;
  line-height:1.55!important;
  color:#203d54!important;
  margin:0!important
}
.confront-v84-source{
  margin-top:12px;
  padding-top:11px;
  border-top:1px solid #e2e9ee
}
.confront-v84-source-title{
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:15px!important;
  line-height:1.3!important;
  font-weight:700!important;
  color:#71879a!important
}
.confront-v84-doc{
  margin-top:4px;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px!important;
  line-height:1.45!important;
  font-weight:700!important;
  color:#304f66!important;
  text-transform:none!important
}
.confront-v84-meta{
  display:flex;flex-wrap:wrap;gap:7px;
  margin-top:8px
}
.confront-v84-chip{
  display:inline-flex;align-items:center;
  padding:5px 8px;border-radius:999px;
  border:1px solid #dce5eb;background:#fff;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:15px!important;line-height:1.25!important;
  color:#6b8295!important
}
.confront-v84-origin{
  margin-top:8px;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:15px!important;
  line-height:1.4!important;
  color:#8293a1!important
}

/* =========================================================
   CONTRADIÇÕES E DIVERGÊNCIAS — mensagem compreensível
   ========================================================= */
.contradictions-v84-empty{
  display:flex;gap:12px;align-items:flex-start;
  padding:15px 16px;border:1px solid #d6e7e2;
  border-radius:12px;background:#f4fbf8
}
.contradictions-v84-icon{
  width:30px;height:30px;border-radius:9px;
  display:grid;place-items:center;flex:0 0 auto;
  background:#e2f4ee;color:#08786e;
  font-size:16px;font-weight:800
}
.contradictions-v84-empty b,
.contradiction-v84-card b{
  display:block;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:17px!important;
  line-height:1.4!important;
  color:#18374f!important
}
.contradictions-v84-empty p,
.contradiction-v84-card p{
  margin:4px 0 0!important;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px!important;
  line-height:1.55!important;
  color:#60778a!important
}
.contradiction-v84-card{
  padding:15px 16px;
  margin-top:10px;
  border:1px solid #eadbbc;
  border-left:5px solid #c48a43;
  border-radius:12px;background:#fffaf1
}
.contradiction-v84-card.high{
  border-color:#e9c9c5;
  border-left-color:#ba4c40;
  background:#fff7f6
}

/* =========================================================
   RASTREABILIDADE — grade de quatro campos legíveis
   ========================================================= */
.trace-v84{
  border:1px solid #dce5eb;
  border-radius:13px;
  overflow:hidden;
  background:#fff
}
.trace-v84-head,
.trace-v84-row{
  display:grid;
  grid-template-columns:minmax(150px,.8fr) minmax(155px,.7fr) minmax(260px,1.35fr) minmax(190px,.8fr);
  gap:14px;
  align-items:start
}
.trace-v84-head{
  padding:11px 14px;
  background:#f3f6f8;
  border-bottom:1px solid #dce5eb
}
.trace-v84-head span{
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:15px!important;
  line-height:1.3!important;
  font-weight:700!important;
  color:#667d90!important;
  text-transform:none!important;
  letter-spacing:0!important
}
.trace-v84-row{
  padding:14px;
  border-top:1px solid #e6ecf0
}
.trace-v84-row:first-of-type{border-top:0}
.trace-v84-row:nth-child(even){background:#fbfdfe}
.trace-v84-topic{
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px!important;
  line-height:1.45!important;
  font-weight:700!important;
  color:#17354d!important
}
.trace-v84-status{
  display:inline-flex;align-items:center;
  width:max-content;max-width:100%;
  padding:5px 9px;border-radius:999px;
  background:#eaf7f3;border:1px solid #c8e5dd;
  color:#08786e;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:15px!important;line-height:1.25!important;
  font-weight:700!important;
  white-space:normal!important
}
.trace-v84-doc{
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px!important;
  line-height:1.5!important;
  color:#405d72!important;
  font-weight:600!important;
  text-transform:none!important
}
.trace-v84-meta{
  display:flex;flex-wrap:wrap;gap:6px
}
.trace-v84-chip{
  display:inline-flex;
  padding:5px 8px;border-radius:999px;
  border:1px solid #dce5eb;background:#f8fafb;
  color:#6a8296;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:15px!important;line-height:1.25!important
}

/* =========================================================
   MATRIZ DE EVIDÊNCIAS — hierarquia editorial
   ========================================================= */
#result.system-result table.matrix thead th{
  background:#f3f6f8!important;
  color:#62798c!important;
  text-transform:none!important;
  letter-spacing:0!important;
  font-size:16px!important;
  font-weight:700!important
}
#result.system-result table.matrix td:first-child{
  font-weight:600!important;
  color:#203d54!important
}
#result.system-result table.matrix td:nth-child(2){
  color:#50697c!important
}
#result.system-result table.matrix td:nth-child(3) .doc-origin{
  color:#304f66!important;
  font-weight:700!important;
  text-transform:none!important
}
#result.system-result table.matrix tbody tr:nth-child(even){
  background:#fbfdfe!important
}
#result.system-result table.matrix tbody tr:hover{
  background:#f5fafc!important
}

/* Responsividade */
@media(max-width:980px){
  .trace-v84-head{display:none!important}
  .trace-v84-row{
    grid-template-columns:1fr!important;
    gap:8px!important
  }
}
@media(max-width:620px){
  .confront-v84-card{
    grid-template-columns:1fr!important
  }
}
</style>
"""
core.HTML = core.HTML.replace("</head>", _evidence_clarity_v84_css + "</head>", 1)

_evidence_clarity_v84_js = r"""
<script id="fiscaliza-evidence-clarity-v84-js">
function sourceNameV84(x){
  var s=(x&&x.source_document_id)||"";
  if(s)return readableDocumentTitleV82(s);
  return "Documento do processo";
}
function originNameV84(x){
  return (x&&x.file)?String(x.file):"";
}
function renderConfrontoV84(a){
  if(!a||a.module_key!=="penalizacao")return;
  var sec=acharSectionPorTitulo("Pontos a confrontar");
  if(!sec)return;
  var items=a.contra||[];
  var html='<div class="kicker">Confronto documental</div><h2>Pontos a confrontar</h2>';
  if(!items.length){
    html+='<div class="empty">Nenhum ponto de confronto foi localizado automaticamente.</div>';
    sec.innerHTML=html;return;
  }
  html+='<div class="confront-v84-list">';
  items.forEach(function(x,i){
    var doc=sourceNameV84(x);
    var origin=originNameV84(x);
    html+='<article class="confront-v84-card">'+
      '<div class="confront-v84-num">'+(i+1)+'</div>'+
      '<div>'+
        '<div class="confront-v84-label">Fato ou questão a verificar</div>'+
        '<p class="confront-v84-text">'+ovEsc(x.text||"Ponto identificado para conferência.")+'</p>'+
        '<div class="confront-v84-source">'+
          '<div class="confront-v84-source-title">Fonte principal</div>'+
          '<div class="confront-v84-doc">'+ovEsc(doc)+'</div>'+
          '<div class="confront-v84-meta">'+
            (x.page?'<span class="confront-v84-chip">Página '+ovEsc(x.page)+'</span>':'')+
            (x.document_id?'<span class="confront-v84-chip">ID '+ovEsc(x.document_id)+'</span>':'')+
          '</div>'+
          (origin?'<div class="confront-v84-origin">Arquivo de origem: '+ovEsc(origin)+'</div>':'')+
        '</div>'+
      '</div>'+
    '</article>';
  });
  html+='</div>';
  sec.innerHTML=html;
}
function renderContradictionsV84(a){
  var sec=acharSectionPorTitulo("Contradições e divergências");
  if(!sec||!a)return;
  var items=a.contradictions||[];
  var html='<div class="kicker">Confronto inteligente</div><h2>Contradições e divergências</h2>';
  if(!items.length){
    html+='<div class="contradictions-v84-empty">'+
      '<span class="contradictions-v84-icon">✓</span>'+
      '<div><b>Nenhuma divergência objetiva detectada automaticamente</b>'+
      '<p>Os documentos analisados não apresentaram, nesta leitura, conflito objetivo que exigisse alerta automático. A conferência humana dos autos continua necessária.</p></div>'+
    '</div>';
  }else{
    items.forEach(function(x){
      html+='<article class="contradiction-v84-card '+(x.severity==="alta"?"high":"")+'">'+
        '<b>'+ovEsc(x.title||"Divergência localizada")+'</b>'+
        '<p>'+ovEsc(x.detail||"Conferir os documentos relacionados antes da conclusão.")+'</p>'+
      '</article>';
    });
  }
  sec.innerHTML=html;
}
function renderTraceV84(a){
  var sec=acharSectionPorTitulo("Rastreabilidade da conclusão");
  if(!sec||!a)return;
  var rows=a.traceability||[];
  var html='<div class="kicker">Como chegou aqui</div><h2>Rastreabilidade da conclusão</h2>';
  if(!rows.length){
    html+='<div class="empty">Nenhuma referência de rastreabilidade foi consolidada.</div>';
    sec.innerHTML=html;return;
  }
  html+='<div class="trace-v84">'+
    '<div class="trace-v84-head"><span>Tema</span><span>Situação</span><span>Documento</span><span>Página / ID</span></div>';
  rows.forEach(function(r){
    var docs=r.documents||[];
    var d=docs.length?docs[0]:null;
    var docName=d&&d.source_document_id?readableDocumentTitleV82(d.source_document_id):(r.source||"Documento do processo");
    var pages=r.pages||[];
    var ids=[];
    docs.forEach(function(x){if(x.document_id&&ids.indexOf(x.document_id)<0)ids.push(x.document_id)});
    var meta='';
    pages.slice(0,4).forEach(function(p){if(p)meta+='<span class="trace-v84-chip">p. '+ovEsc(p)+'</span>'});
    ids.slice(0,3).forEach(function(id){meta+='<span class="trace-v84-chip">ID '+ovEsc(id)+'</span>'});
    html+='<div class="trace-v84-row">'+
      '<div class="trace-v84-topic">'+ovEsc(r.claim||"Evidência")+'</div>'+
      '<div><span class="trace-v84-status">'+ovEsc(r.status||"Localizado")+'</span></div>'+
      '<div class="trace-v84-doc">'+ovEsc(readableDocumentTitleV82(docName))+'</div>'+
      '<div class="trace-v84-meta">'+meta+'</div>'+
    '</div>';
  });
  html+='</div>';
  sec.innerHTML=html;
}
function refineMatrixHeadersV84(){
  var matrix=document.querySelector("#result.system-result table.matrix");
  if(!matrix)return;
  var th=matrix.querySelectorAll("thead th");
  if(th[0])th[0].textContent="Questão analisada";
  if(th[1])th[1].textContent="Resultado";
  if(th[2])th[2].textContent="Documento / página";
  if(th[3])th[3].textContent="Situação";
}
function aplicarEvidenciasV84(a){
  renderConfrontoV84(a);
  renderContradictionsV84(a);
  renderTraceV84(a);
  refineMatrixHeadersV84();
  statusChipsV82();
}

var _ajustarResultadoModuloV84=ajustarResultadoModulo;
ajustarResultadoModulo=function(a){
  _ajustarResultadoModuloV84(a);
  setTimeout(function(){aplicarEvidenciasV84(a)},0);
};
</script>
"""
core.HTML = core.HTML.replace("</body>", _evidence_clarity_v84_js + "</body>", 1)


# --- Home executiva aprovada v8.5 ---
_home_exec_v85_css = r"""
<style id="fiscaliza-home-executive-v85">
/* =========================================================
   HOME EXECUTIVA — módulos primeiro, sem hero de landing page
   ========================================================= */
.screen-home{
  padding-top:12px!important;
  padding-bottom:18px!important;
  gap:0!important
}
.screen-home .home-welcome{
  margin:0 0 10px!important;
  padding:0!important
}

/* Intro compacta */
.home-commercial-hero.home-executive-v85{
  display:grid!important;
  grid-template-columns:minmax(0,1.3fr) minmax(520px,.7fr)!important;
  align-items:center!important;
  gap:22px!important;
  min-height:0!important;
  padding:17px 20px!important;
  border:1px solid #dce7ed!important;
  border-radius:16px!important;
  background:
    radial-gradient(circle at 92% 16%,rgba(20,168,157,.10),transparent 30%),
    linear-gradient(110deg,#ffffff 0%,#f7fbfc 70%,#eef9f7 100%)!important;
  box-shadow:0 5px 18px rgba(15,47,73,.045)!important;
  color:#17354d!important;
  overflow:hidden!important
}
.home-commercial-hero.home-executive-v85:before,
.home-commercial-hero.home-executive-v85:after{
  content:none!important;
  display:none!important
}
.home-exec-copy-v85{
  min-width:0
}
.home-exec-kicker-v85{
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:15px!important;
  line-height:1.3!important;
  font-weight:700!important;
  letter-spacing:.06em!important;
  color:#07877d!important;
  margin:0 0 5px!important
}
.home-exec-title-v85{
  margin:0!important;
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:30px!important;
  line-height:1.12!important;
  letter-spacing:-.45px!important;
  color:#102f49!important
}
.home-exec-desc-v85{
  margin:6px 0 0!important;
  max-width:740px!important;
  font-family:Calibri,"Segoe UI",Arial,sans-serif!important;
  font-size:16px!important;
  line-height:1.45!important;
  color:#63798d!important
}
.home-exec-kpis-v85{
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:9px
}
.home-exec-kpi-v85{
  display:grid;
  grid-template-columns:42px minmax(0,1fr);
  gap:10px;
  align-items:center;
  min-height:76px;
  padding:10px 11px;
  border:1px solid #dce6ec;
  border-radius:12px;
  background:rgba(255,255,255,.9)
}
.home-exec-kpi-icon-v85{
  width:42px;height:42px;border-radius:10px;
  display:grid;place-items:center;
  background:#e6f6f2;color:#07877d
}
.home-exec-kpi-icon-v85 svg{
  width:23px;height:23px
}
.home-exec-kpi-v85 b{
  display:block;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:17px!important;
  line-height:1.15!important;
  color:#102f49!important
}
.home-exec-kpi-v85 span{
  display:block;
  margin-top:3px;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:15px!important;
  line-height:1.3!important;
  color:#6a8093!important
}

/* Busca global no topo */
.home-top-search-v85{
  flex:1 1 410px;
  max-width:520px;
  min-width:260px;
  height:42px;
  display:flex;
  align-items:center;
  gap:9px;
  margin-left:auto;
  padding:0 11px;
  border:1px solid rgba(255,255,255,.18);
  border-radius:10px;
  background:#fff;
  box-shadow:0 4px 12px rgba(2,31,51,.08)
}
.home-top-search-v85.hidden{
  display:none!important
}
.home-top-search-v85 svg{
  width:19px;height:19px;
  flex:0 0 auto;
  color:#567189
}
.home-top-search-v85 input{
  width:100%;
  min-width:0;
  border:0;
  outline:0;
  background:transparent;
  color:#1f3d54;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px!important
}
.home-top-search-v85 input::placeholder{
  color:#8495a5
}
.home-search-key-v85{
  flex:0 0 auto;
  padding:4px 7px;
  border:1px solid #dbe4eb;
  border-radius:7px;
  background:#f7fafc;
  color:#73889a;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:13px!important
}

/* Painel de módulos vira área de trabalho limpa */
.screen-home .module-panel.home-only{
  margin:0!important;
  padding:0!important;
  border:0!important;
  border-radius:0!important;
  background:transparent!important;
  box-shadow:none!important
}
.screen-home .module-toolbar{
  display:none!important
}

/* Navegação rápida */
.home-tabs-v85{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
  margin:0 0 9px;
  padding:0 4px
}
.home-tabs-left-v85{
  display:flex;
  align-items:center;
  gap:5px
}
.home-tab-v85{
  border:0;
  background:transparent;
  color:#60778a;
  border-radius:9px;
  padding:9px 12px;
  display:inline-flex;
  align-items:center;
  gap:7px;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px!important;
  line-height:1.2!important;
  font-weight:700;
  cursor:pointer
}
.home-tab-v85:hover{
  background:#f1f6f8;
  color:#15364f
}
.home-tab-v85.active{
  background:#eaf4fb;
  color:#155fae;
  box-shadow:inset 0 -2px 0 #1876d2
}
.home-tab-v85 svg{
  width:19px;height:19px
}
.home-tabs-hint-v85{
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:15px!important;
  color:#768a9b
}
.home-tabs-hint-v85 strong{
  color:#155fae
}

/* Cards dos módulos como no mockup aprovado */
.screen-home .module-grid{
  display:grid!important;
  grid-template-columns:repeat(3,minmax(0,1fr))!important;
  gap:10px!important;
  margin:0!important
}
.screen-home .module-card{
  display:grid!important;
  grid-template-columns:66px minmax(0,1fr)!important;
  grid-template-rows:auto auto 1fr!important;
  column-gap:14px!important;
  row-gap:4px!important;
  align-content:center!important;
  min-height:132px!important;
  padding:14px 16px!important;
  border:1px solid #d9e4eb!important;
  border-radius:13px!important;
  background:#fff!important;
  box-shadow:0 3px 10px rgba(15,47,73,.025)!important;
  position:relative!important;
  overflow:hidden!important
}
.screen-home .module-card:hover{
  transform:translateY(-2px)!important;
  border-color:#b9cbd7!important;
  box-shadow:0 10px 24px rgba(15,47,73,.08)!important
}
.screen-home .module-icon{
  grid-column:1!important;
  grid-row:1 / 4!important;
  align-self:center!important;
  width:58px!important;
  height:58px!important;
  margin:0!important;
  border-radius:12px!important
}
.screen-home .module-icon svg{
  width:29px!important;
  height:29px!important
}
.screen-home .module-category{
  grid-column:2!important;
  grid-row:1!important;
  position:static!important;
  justify-self:start!important;
  width:max-content!important;
  max-width:calc(100% - 72px)!important;
  margin:0 0 1px!important;
  padding:5px 9px!important;
  font-size:14px!important;
  line-height:1.15!important;
  border-radius:999px!important;
  white-space:nowrap!important;
  overflow:hidden!important;
  text-overflow:ellipsis!important
}
.screen-home .module-name{
  grid-column:2!important;
  grid-row:2!important;
  padding-right:72px!important;
  font-size:18px!important;
  line-height:1.28!important;
  color:#102f49!important;
  font-weight:700!important
}
.screen-home .module-desc{
  grid-column:2!important;
  grid-row:3!important;
  margin:1px 0 0!important;
  padding:0 76px 0 0!important;
  font-size:16px!important;
  line-height:1.38!important;
  color:#667d90!important
}
.screen-home .module-card:after{
  right:15px!important;
  bottom:15px!important;
  font-size:16px!important;
  line-height:1.2!important;
  font-weight:700!important
}
.screen-home.home-model-mode-v85 .module-card:after{
  content:"Abrir modelo →"!important;
  font-size:15px!important
}

/* Barra de resultados de busca */
.home-search-result-v85{
  display:none;
  margin:0 4px 9px;
  padding:8px 11px;
  border:1px solid #dce6ed;
  border-radius:9px;
  background:#f8fbfd;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:15px!important;
  color:#61788b
}
.home-search-result-v85.visible{
  display:block
}

/* Bloco inferior: recentes + inteligência */
.home-bottom-v85{
  display:grid;
  grid-template-columns:minmax(0,1.8fr) minmax(290px,.72fr);
  gap:11px;
  margin-top:11px
}
.recent-panel.home-approved-recent.home-recent-v85{
  margin:0!important;
  padding:15px 16px!important;
  border-radius:14px!important;
  box-shadow:0 4px 14px rgba(15,47,73,.04)!important
}
.home-recent-v85 .recent-head{
  margin-bottom:10px!important
}
.home-recent-v85 .recent-head h3{
  font-size:21px!important
}
.home-recent-v85 .recent-head p{
  font-size:15px!important;
  margin-top:2px!important
}
.home-recent-v85 .recent-session-label{
  font-size:14px!important
}
.home-recent-v85 .recent-list{
  grid-template-columns:repeat(3,minmax(0,1fr))!important;
  gap:8px!important
}
.home-recent-v85 .recent-row{
  grid-template-columns:1fr!important;
  grid-template-areas:
    "main"
    "status"
    "action"!important;
  min-height:126px!important;
  gap:6px!important;
  padding:11px 12px!important
}
.home-recent-v85 .recent-icon{
  display:none!important
}
.home-recent-v85 .recent-main b{
  font-size:16px!important
}
.home-recent-v85 .recent-main span,
.home-recent-v85 .recent-meta{
  font-size:15px!important;
  line-height:1.35!important
}
.home-recent-v85 .recent-status{
  font-size:14px!important;
  padding:4px 8px!important
}
.home-recent-v85 .recent-open{
  font-size:15px!important;
  padding:7px 10px!important
}

/* Card institucional inferior */
.home-intel-card-v85{
  position:relative;
  overflow:hidden;
  min-height:100%;
  padding:18px;
  border:1px solid #d5e8e5;
  border-radius:14px;
  background:
    radial-gradient(circle at 90% 25%,rgba(15,164,157,.14),transparent 34%),
    linear-gradient(135deg,#f5fcfa 0%,#e5f6f3 100%);
  color:#17354d
}
.home-intel-card-v85:after{
  content:"";
  position:absolute;
  right:-55px;bottom:-70px;
  width:210px;height:210px;
  border:35px solid rgba(15,143,130,.06);
  border-radius:50%
}
.home-intel-overline-v85{
  position:relative;z-index:1;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:14px!important;
  line-height:1.35!important;
  color:#087d73;
  font-weight:700;
  letter-spacing:.07em
}
.home-intel-card-v85 h3{
  position:relative;z-index:1;
  margin:8px 0 0;
  max-width:250px;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:23px!important;
  line-height:1.2!important;
  color:#102f49
}
.home-intel-card-v85 p{
  position:relative;z-index:1;
  margin:9px 0 0;
  max-width:290px;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px!important;
  line-height:1.48!important;
  color:#5f778a
}
.home-intel-graphic-v85{
  position:absolute;
  z-index:1;
  right:18px;
  top:45px;
  width:100px;height:100px;
  display:grid;place-items:center;
  color:#087d73
}
.home-intel-graphic-v85 svg{
  width:90px;height:90px
}
.home-intel-button-v85{
  position:absolute;
  z-index:2;
  right:16px;
  bottom:15px;
  border:0;
  border-radius:9px;
  padding:8px 11px;
  background:#d5f0eb;
  color:#12675f;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:15px!important;
  line-height:1.2!important;
  font-weight:700;
  cursor:pointer
}

/* Footer mais discreto */
.fiscaliza-home-footer{
  margin-top:10px!important;
  padding-top:10px!important;
  font-size:14px!important
}

/* Mantém os seis módulos na primeira dobra em notebooks comuns */
@media(max-height:820px) and (min-width:1000px){
  .home-commercial-hero.home-executive-v85{
    padding:13px 18px!important
  }
  .home-exec-title-v85{font-size:27px!important}
  .home-exec-kpi-v85{min-height:68px;padding:8px 10px}
  .screen-home .module-card{
    min-height:118px!important;
    padding-top:11px!important;
    padding-bottom:11px!important
  }
  .screen-home .module-icon{
    width:52px!important;height:52px!important
  }
  .home-bottom-v85{
    margin-top:9px
  }
}

@media(max-width:1180px){
  .home-commercial-hero.home-executive-v85{
    grid-template-columns:1fr!important
  }
  .home-exec-kpis-v85{
    max-width:none
  }
  .home-top-search-v85{
    max-width:420px
  }
  .home-bottom-v85{
    grid-template-columns:1fr!important
  }
  .home-intel-card-v85{
    min-height:190px
  }
}
@media(max-width:930px){
  .screen-home .module-grid{
    grid-template-columns:repeat(2,minmax(0,1fr))!important
  }
  .home-top-search-v85{
    display:none!important
  }
  .home-recent-v85 .recent-list{
    grid-template-columns:1fr!important
  }
}
@media(max-width:650px){
  .home-exec-kpis-v85{
    grid-template-columns:1fr!important
  }
  .home-tabs-v85{
    align-items:flex-start;
    flex-direction:column
  }
  .home-tabs-left-v85{
    width:100%;
    overflow-x:auto
  }
  .screen-home .module-grid{
    grid-template-columns:1fr!important
  }
  .screen-home .module-card{
    grid-template-columns:56px minmax(0,1fr)!important
  }
  .screen-home .module-icon{
    width:50px!important;height:50px!important
  }
  .home-exec-title-v85{
    font-size:25px!important
  }
}
</style>
"""
core.HTML = core.HTML.replace("</head>", _home_exec_v85_css + "</head>", 1)

_home_exec_v85_js = r"""
<script id="fiscaliza-home-executive-v85-js">
var homeV85ModelMode=false;

function homeKpiIconV85(kind){
  var common='fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
  if(kind==="layers")return '<svg viewBox="0 0 24 24"><path '+common+' d="M12 3l8 4-8 4-8-4 8-4zM4 12l8 4 8-4M4 17l8 4 8-4"/></svg>';
  if(kind==="doc")return '<svg viewBox="0 0 24 24"><path '+common+' d="M6 3h9l3 3v15H6zM15 3v4h4M9 12h6M9 16h6"/></svg>';
  return '<svg viewBox="0 0 24 24"><circle '+common+' cx="9" cy="8" r="3"/><circle '+common+' cx="17" cy="8" r="2.5"/><path '+common+' d="M3 19c.8-3.2 3-5 6-5s5.2 1.8 6 5M14 14c3.2 0 5.3 1.8 6 5"/></svg>';
}
function searchIconV85(){
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/></svg>';
}
function tabsIconV85(kind){
  if(kind==="grid")return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="6" height="6"/><rect x="14" y="4" width="6" height="6"/><rect x="4" y="14" width="6" height="6"/><rect x="14" y="14" width="6" height="6"/></svg>';
  if(kind==="clock")return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>';
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 3h9l3 3v15H6zM15 3v4h4M9 12h6M9 16h6"/></svg>';
}
function intelGraphicV85(){
  return '<svg viewBox="0 0 100 100" fill="none">'+
    '<rect x="17" y="14" width="49" height="64" rx="7" fill="#fff" opacity=".88" transform="rotate(-6 17 14)"/>'+
    '<path d="M30 33h24M29 43h27M28 53h20" stroke="#7bb9c7" stroke-width="4" stroke-linecap="round"/>'+
    '<path d="M68 43l21 8v17c0 16-10 25-21 31-11-6-21-15-21-31V51z" fill="#0b6275"/>'+
    '<path d="M58 68l7 7 13-17" stroke="#70e2d3" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'+
  '</svg>';
}

function instalarBuscaTopoV85(){
  if(document.getElementById("homeTopSearchV85"))return;
  var inner=document.querySelector(".topbar-inner");
  if(!inner)return;
  var actions=inner.querySelector(".top-actions");
  var search=document.createElement("label");
  search.id="homeTopSearchV85";
  search.className="home-top-search-v85";
  search.innerHTML=searchIconV85()+
    '<input id="homeSearchInputV85" type="search" autocomplete="off" placeholder="Buscar módulos ou processos..." oninput="buscarHomeV85(this.value)">'+
    '<span class="home-search-key-v85">Ctrl + K</span>';
  if(actions)inner.insertBefore(search,actions);
  else inner.appendChild(search);

  if(!window._homeV85KeyInstalled){
    window._homeV85KeyInstalled=true;
    document.addEventListener("keydown",function(e){
      if((e.ctrlKey||e.metaKey)&&String(e.key).toLowerCase()==="k"){
        var home=document.getElementById("screenHome");
        if(home&&home.classList.contains("active")){
          e.preventDefault();
          var input=document.getElementById("homeSearchInputV85");
          if(input){input.focus();input.select()}
        }
      }
    });
  }
}

function buscarHomeV85(q){
  var raw=String(q||"").trim();
  var key=raw.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"");
  var moduleHits=0,recentHits=0;

  document.querySelectorAll("#screenHome .module-card").forEach(function(card){
    if(card.style.display==="none"&&["penalizacao","fiscalizacao","reequilibrio","rescisao","disciplinar","sindicancia"].indexOf(card.dataset.module)<0)return;
    var text=(card.textContent||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"");
    var show=!key||text.indexOf(key)>=0;
    card.style.display=show?"grid":"none";
    if(show)moduleHits++;
  });

  document.querySelectorAll("#recentList .recent-row").forEach(function(row){
    var text=(row.textContent||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"");
    var show=!key||text.indexOf(key)>=0;
    row.style.display=show?"grid":"none";
    if(show)recentHits++;
  });

  var note=document.getElementById("homeSearchResultV85");
  if(note){
    if(key){
      note.classList.add("visible");
      note.textContent=moduleHits+" módulo(s) e "+recentHits+" processo(s) recente(s) encontrados para “"+raw+"”.";
    }else{
      note.classList.remove("visible");
      note.textContent="";
    }
  }
}

function homeTabV85(tab){
  var home=document.getElementById("screenHome");if(!home)return;
  document.querySelectorAll(".home-tab-v85").forEach(function(b){
    b.classList.toggle("active",b.dataset.homeTab===tab);
  });

  if(tab==="recent"){
    homeV85ModelMode=false;
    home.classList.remove("home-model-mode-v85");
    restaurarCardsModuloV85();
    var recent=document.getElementById("recentPanel");
    if(recent)recent.scrollIntoView({behavior:"smooth",block:"start"});
    return;
  }

  if(tab==="models"){
    homeV85ModelMode=true;
    home.classList.add("home-model-mode-v85");
    ativarCardsModeloV85();
    var title=home.querySelector(".home-exec-title-v85");
    var desc=home.querySelector(".home-exec-desc-v85");
    if(title)title.textContent="Escolha um processo modelo";
    if(desc)desc.textContent="Selecione um módulo para abrir a área de trabalho e carregar automaticamente o processo fictício correspondente.";
    var grid=home.querySelector(".module-grid");
    if(grid)grid.scrollIntoView({behavior:"smooth",block:"nearest"});
    return;
  }

  homeV85ModelMode=false;
  home.classList.remove("home-model-mode-v85");
  restaurarCardsModuloV85();
  var title=home.querySelector(".home-exec-title-v85");
  var desc=home.querySelector(".home-exec-desc-v85");
  if(title)title.textContent="Escolha um fluxo especializado";
  if(desc)desc.textContent="Organize seus processos com rastreabilidade, evidências e revisão humana.";
  var grid=home.querySelector(".module-grid");
  if(grid)grid.scrollIntoView({behavior:"smooth",block:"nearest"});
}

function ativarCardsModeloV85(){
  document.querySelectorAll("#screenHome .module-card").forEach(function(card){
    var key=card.getAttribute("data-module");
    if(["penalizacao","fiscalizacao","reequilibrio","rescisao","disciplinar","sindicancia"].indexOf(key)<0)return;
    card.setAttribute("onclick","abrirModeloModuloV85('"+key+"')");
  });
}
function restaurarCardsModuloV85(){
  document.querySelectorAll("#screenHome .module-card").forEach(function(card){
    var key=card.getAttribute("data-module");
    if(["penalizacao","fiscalizacao","reequilibrio","rescisao","disciplinar","sindicancia"].indexOf(key)<0)return;
    card.setAttribute("onclick","abrirModulo('"+key+"')");
  });
}
function abrirModeloModuloV85(key){
  homeV85ModelMode=false;
  var home=document.getElementById("screenHome");
  if(home)home.classList.remove("home-model-mode-v85");
  abrirTelaModulo(key,null,true);
  setTimeout(function(){
    if(typeof testarDemo==="function")testarDemo();
  },220);
}

function instalarTabsHomeV85(){
  var panel=document.querySelector("#screenHome .module-panel.home-only");
  var grid=panel&&panel.querySelector(".module-grid");
  if(!panel||!grid)return;
  var tabs=document.getElementById("homeTabsV85");
  if(!tabs){
    tabs=document.createElement("div");
    tabs.id="homeTabsV85";
    tabs.className="home-tabs-v85";
    tabs.innerHTML=
      '<div class="home-tabs-left-v85">'+
        '<button class="home-tab-v85 active" data-home-tab="modules" onclick="homeTabV85(\'modules\')">'+tabsIconV85("grid")+'<span>Módulos</span></button>'+
        '<button class="home-tab-v85" data-home-tab="recent" onclick="homeTabV85(\'recent\')">'+tabsIconV85("clock")+'<span>Recentes</span></button>'+
        '<button class="home-tab-v85" data-home-tab="models" onclick="homeTabV85(\'models\')">'+tabsIconV85("doc")+'<span>Modelos</span></button>'+
      '</div>'+
      '<div class="home-tabs-hint-v85"><strong>6 fluxos</strong> prontos para uso</div>';
    panel.insertBefore(tabs,grid);
  }
  if(!document.getElementById("homeSearchResultV85")){
    var res=document.createElement("div");
    res.id="homeSearchResultV85";
    res.className="home-search-result-v85";
    panel.insertBefore(res,grid);
  }
}

function instalarBlocoInferiorV85(){
  var home=document.getElementById("screenHome");
  var recent=document.getElementById("recentPanel");
  if(!home||!recent)return;
  recent.classList.add("home-recent-v85");

  var bottom=document.getElementById("homeBottomV85");
  if(!bottom){
    bottom=document.createElement("div");
    bottom.id="homeBottomV85";
    bottom.className="home-bottom-v85";
    recent.parentNode.insertBefore(bottom,recent);
    bottom.appendChild(recent);

    var intel=document.createElement("aside");
    intel.className="home-intel-card-v85";
    intel.innerHTML=
      '<div class="home-intel-overline-v85">Inteligência a serviço do interesse público</div>'+
      '<h3>Do documento à decisão humana</h3>'+
      '<p>Organize autos, acompanhe pendências e produza documentos assistidos, com rastreabilidade e padrão de trabalho.</p>'+
      '<div class="home-intel-graphic-v85">'+intelGraphicV85()+'</div>'+
      '<button class="home-intel-button-v85" onclick="homeTabV85(\'modules\')">Ver módulos →</button>';
    bottom.appendChild(intel);
  }
}

function aplicarHomeExecutivaV85(){
  var home=document.getElementById("screenHome");
  var hero=document.querySelector("#screenHome .home-commercial-hero");
  if(!home||!hero)return;

  instalarBuscaTopoV85();

  hero.classList.add("home-executive-v85");
  if(!hero.dataset.executiveV85){
    hero.dataset.executiveV85="1";
    hero.innerHTML=
      '<div class="home-exec-copy-v85">'+
        '<div class="home-exec-kicker-v85">Gestão contratual e responsabilização</div>'+
        '<h1 class="home-exec-title-v85">Escolha um fluxo especializado</h1>'+
        '<p class="home-exec-desc-v85">Organize seus processos com rastreabilidade, evidências e revisão humana.</p>'+
      '</div>'+
      '<div class="home-exec-kpis-v85">'+
        '<div class="home-exec-kpi-v85"><span class="home-exec-kpi-icon-v85">'+homeKpiIconV85("layers")+'</span><div><b>6 módulos</b><span>fluxos especializados</span></div></div>'+
        '<div class="home-exec-kpi-v85"><span class="home-exec-kpi-icon-v85">'+homeKpiIconV85("doc")+'</span><div><b>ID + página</b><span>rastreabilidade em todos os fluxos</span></div></div>'+
        '<div class="home-exec-kpi-v85"><span class="home-exec-kpi-icon-v85">'+homeKpiIconV85("human")+'</span><div><b>Revisão humana</b><span>decisão final com segurança</span></div></div>'+
      '</div>';
  }

  instalarTabsHomeV85();
  instalarBlocoInferiorV85();

  /* Garante os ícones e as categorias já aprovados no mockup. */
  document.querySelectorAll("#screenHome .module-card").forEach(function(card){
    var key=card.getAttribute("data-module");
    if(["penalizacao","fiscalizacao","reequilibrio","rescisao","disciplinar","sindicancia"].indexOf(key)<0){
      card.style.display="none";
      return;
    }
    card.style.display="grid";
    var icon=card.querySelector(".module-icon");
    if(icon&&typeof homeIconSvg==="function")icon.innerHTML=homeIconSvg(key);
    var meta=commercialModuleMeta[key];
    var tag=card.querySelector(".module-category");
    if(!tag&&meta){
      tag=document.createElement("span");
      tag.className="module-category";
      tag.textContent=meta.category;
      card.appendChild(tag);
    }
  });

  var input=document.getElementById("homeSearchInputV85");
  if(input&&input.value)buscarHomeV85(input.value);
}

function atualizarBuscaTopoV85(){
  var search=document.getElementById("homeTopSearchV85");
  var home=document.getElementById("screenHome");
  if(!search||!home)return;
  search.classList.toggle("hidden",!home.classList.contains("active"));
}

/* Mantém a Home nova após todos os fluxos antigos que também mexem na tela. */
var _deixarHomeMaisProdutoV85=deixarHomeMaisProduto;
deixarHomeMaisProduto=function(){
  _deixarHomeMaisProdutoV85();
  setTimeout(function(){
    aplicarHomeExecutivaV85();
    atualizarBuscaTopoV85();
  },0);
};

var _prepararHomeComercialV85=prepararHomeComercial;
prepararHomeComercial=function(){
  _prepararHomeComercialV85();
  setTimeout(function(){
    aplicarHomeExecutivaV85();
    atualizarBuscaTopoV85();
  },0);
};

var _abrirTelaModuloV85=abrirTelaModulo;
abrirTelaModulo=function(key,el,push){
  _abrirTelaModuloV85(key,el,push);
  setTimeout(atualizarBuscaTopoV85,0);
};
window.abrirModulo=abrirTelaModulo;

var _voltarAosModulosV85=voltarAosModulos;
voltarAosModulos=function(push){
  _voltarAosModulosV85(push);
  setTimeout(function(){
    aplicarHomeExecutivaV85();
    atualizarBuscaTopoV85();
  },0);
};

document.addEventListener("DOMContentLoaded",function(){
  setTimeout(function(){
    aplicarHomeExecutivaV85();
    atualizarBuscaTopoV85();
  },320);
});
</script>
"""
core.HTML = core.HTML.replace("</body>", _home_exec_v85_js + "</body>", 1)


# --- Home executiva isolada v8.6: corrige heranças e exibe somente 6 módulos ---
_home_v86_css = r"""
<style id="fiscaliza-home-v86">
/* Oculta integralmente a Home antiga. A v8.6 não depende dos componentes herdados. */
#screenHome > .home-welcome,
#screenHome > .home-commercial-hero,
#screenHome > .module-panel.home-only,
#screenHome > .home-bottom-v85,
#screenHome > .fiscaliza-home-footer{
  display:none!important
}

#screenHome{
  padding:14px 22px 22px!important;
  min-height:calc(100vh - 72px)!important;
  background:#f3f6f8!important
}

/* Container novo e isolado */
.home-v86{
  width:100%;
  max-width:1500px;
  margin:0 auto;
  font-family:Calibri,"Segoe UI",Arial,sans-serif
}

/* Faixa executiva — curta de propósito */
.home-v86-summary{
  display:grid;
  grid-template-columns:minmax(0,1.2fr) auto;
  gap:18px;
  align-items:center;
  min-height:104px;
  padding:16px 18px;
  border:1px solid #d8e4ea;
  border-radius:15px;
  background:
    radial-gradient(circle at 96% 18%,rgba(18,154,145,.09),transparent 28%),
    linear-gradient(110deg,#fff 0%,#f8fbfc 72%,#edf8f6 100%);
  box-shadow:0 4px 14px rgba(14,45,68,.04)
}
.home-v86-summary h1{
  margin:0;
  font-size:27px!important;
  line-height:1.15!important;
  letter-spacing:-.3px;
  color:#12334d!important
}
.home-v86-summary p{
  margin:6px 0 0;
  max-width:720px;
  font-size:16px!important;
  line-height:1.45!important;
  color:#647b8d!important
}
.home-v86-kpis{
  display:flex;
  align-items:stretch;
  gap:8px
}
.home-v86-kpi{
  min-width:150px;
  padding:10px 12px;
  border:1px solid #d9e4ea;
  border-radius:11px;
  background:#fff
}
.home-v86-kpi b{
  display:block;
  font-size:17px!important;
  line-height:1.2!important;
  color:#12334d!important
}
.home-v86-kpi span{
  display:block;
  margin-top:3px;
  font-size:16px!important;
  line-height:1.3!important;
  color:#708598!important
}

/* Cabeçalho da grade */
.home-v86-modules-head{
  display:flex;
  justify-content:space-between;
  align-items:end;
  gap:18px;
  margin:14px 2px 9px
}
.home-v86-modules-head h2{
  margin:0;
  font-size:22px!important;
  line-height:1.2!important;
  color:#12334d!important
}
.home-v86-modules-head p{
  margin:3px 0 0;
  font-size:16px!important;
  line-height:1.4!important;
  color:#6c8193!important
}
.home-v86-count{
  flex:0 0 auto;
  display:inline-flex;
  align-items:center;
  gap:7px;
  padding:7px 10px;
  border:1px solid #cfe3df;
  border-radius:999px;
  background:#eef8f5;
  color:#08786e;
  font-size:16px!important;
  font-weight:700
}
.home-v86-count:before{
  content:"";
  width:8px;height:8px;border-radius:50%;
  background:#12a58f
}

/* Exatamente seis cards */
.home-v86-grid{
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:11px
}
.home-v86-card{
  position:relative;
  display:grid;
  grid-template-columns:58px minmax(0,1fr);
  gap:13px;
  min-height:142px;
  padding:15px 16px;
  border:1px solid #d7e2e9;
  border-radius:13px;
  background:#fff;
  box-shadow:0 3px 9px rgba(12,42,65,.025);
  transition:transform .15s ease,border-color .15s ease,box-shadow .15s ease
}
.home-v86-card:hover{
  transform:translateY(-2px);
  border-color:#b9cbd6;
  box-shadow:0 10px 22px rgba(12,42,65,.08)
}
.home-v86-icon{
  width:54px;height:54px;
  border-radius:12px;
  display:grid;
  place-items:center;
  align-self:start;
  margin-top:2px
}
.home-v86-icon svg{
  width:28px;height:28px
}
.home-v86-card[data-module="penalizacao"] .home-v86-icon{background:#e9f2ff;color:#1767c7}
.home-v86-card[data-module="fiscalizacao"] .home-v86-icon{background:#e6f6f1;color:#087d72}
.home-v86-card[data-module="reequilibrio"] .home-v86-icon{background:#fff0df;color:#c46818}
.home-v86-card[data-module="rescisao"] .home-v86-icon{background:#fdecee;color:#b62939}
.home-v86-card[data-module="disciplinar"] .home-v86-icon{background:#f0edff;color:#6246c7}
.home-v86-card[data-module="sindicancia"] .home-v86-icon{background:#e5f6f4;color:#087a74}

.home-v86-category{
  display:inline-flex;
  width:max-content;
  max-width:100%;
  padding:4px 8px;
  border:1px solid #d8e3e9;
  border-radius:999px;
  background:#f6f9fb;
  color:#6a8092;
  font-size:16px!important;
  line-height:1.2!important;
  font-weight:700
}
.home-v86-card h3{
  margin:7px 0 0;
  font-size:19px!important;
  line-height:1.25!important;
  color:#102f49!important
}
.home-v86-card p{
  margin:5px 0 0;
  padding-right:2px;
  font-size:16px!important;
  line-height:1.4!important;
  color:#667d90!important
}
.home-v86-actions{
  display:flex;
  align-items:center;
  gap:8px;
  margin-top:11px
}
.home-v86-open,
.home-v86-model{
  border-radius:8px;
  padding:7px 10px;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px!important;
  line-height:1.2!important;
  font-weight:700;
  cursor:pointer
}
.home-v86-open{
  border:0;
  background:#123a59;
  color:#fff
}
.home-v86-open:hover{background:#0d2f49}
.home-v86-model{
  border:1px solid #d7e3ea;
  background:#f7fafc;
  color:#526c80
}
.home-v86-model:hover{background:#eef4f7}

/* Recentes só abaixo dos módulos — não interfere na primeira decisão */
.home-v86-recent{
  margin-top:13px;
  padding:15px 16px;
  border:1px solid #d9e4ea;
  border-radius:14px;
  background:#fff
}
.home-v86-recent-head{
  display:flex;
  justify-content:space-between;
  align-items:end;
  gap:12px;
  margin-bottom:9px
}
.home-v86-recent h2{
  margin:0;
  font-size:20px!important;
  line-height:1.2!important;
  color:#12334d!important
}
.home-v86-recent p{
  margin:3px 0 0;
  font-size:16px!important;
  line-height:1.4!important;
  color:#6d8193!important
}
.home-v86-recent-link{
  border:0;
  background:transparent;
  color:#087d73;
  font-size:16px!important;
  font-weight:700;
  cursor:pointer
}
.home-v86-recent-list{
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:8px
}
.home-v86-recent-item{
  min-width:0;
  padding:10px 11px;
  border:1px solid #e0e8ed;
  border-radius:10px;
  background:#fbfdfe
}
.home-v86-recent-item b{
  display:block;
  font-size:16px!important;
  color:#16364e!important
}
.home-v86-recent-item span{
  display:block;
  margin-top:3px;
  font-size:16px!important;
  line-height:1.35!important;
  color:#708598!important
}
.home-v86-recent-item button{
  margin-top:7px;
  border:0;
  background:transparent;
  padding:0;
  color:#1767c7;
  font-size:16px!important;
  font-weight:700;
  cursor:pointer
}
.home-v86-empty{
  grid-column:1/-1;
  padding:10px;
  border:1px dashed #d7e3ea;
  border-radius:9px;
  color:#718699;
  font-size:16px!important
}

/* A busca do topo continua, mas o campo novo é limpo e funcional */
#homeTopSearchV85{
  max-width:495px!important
}

/* Em 1366x768 os seis módulos devem aparecer sem rolar para encontrá-los */
@media(max-height:800px) and (min-width:1000px){
  #screenHome{padding-top:10px!important}
  .home-v86-summary{
    min-height:88px;
    padding:12px 16px
  }
  .home-v86-summary h1{font-size:25px!important}
  .home-v86-kpi{padding:8px 10px;min-width:140px}
  .home-v86-modules-head{margin-top:10px;margin-bottom:7px}
  .home-v86-card{
    min-height:128px;
    padding:12px 14px
  }
  .home-v86-icon{
    width:49px;height:49px
  }
  .home-v86-card h3{margin-top:5px}
  .home-v86-actions{margin-top:7px}
}

@media(max-width:1100px){
  .home-v86-summary{
    grid-template-columns:1fr
  }
  .home-v86-kpis{
    display:grid;
    grid-template-columns:repeat(3,1fr)
  }
  .home-v86-kpi{min-width:0}
}
@media(max-width:900px){
  .home-v86-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .home-v86-recent-list{grid-template-columns:1fr}
}
@media(max-width:620px){
  #screenHome{padding:10px 12px 18px!important}
  .home-v86-kpis{grid-template-columns:1fr}
  .home-v86-grid{grid-template-columns:1fr}
  .home-v86-modules-head{align-items:flex-start;flex-direction:column}
}
</style>
"""
core.HTML = core.HTML.replace("</head>", _home_v86_css + "</head>", 1)

_home_v86_js = r"""
<script id="fiscaliza-home-v86-js">
function homeV86Meta(){
  return {
    penalizacao:{
      category:"Responsabilização",
      title:"Penalização contratual",
      desc:"Responsabilização, defesa, sanção e decisão."
    },
    fiscalizacao:{
      category:"Gestão contratual",
      title:"Fiscalização de contratos",
      desc:"Execução, entregas, ocorrências e fiscalização."
    },
    reequilibrio:{
      category:"Gestão contratual",
      title:"Reequilíbrio econômico-financeiro",
      desc:"Pedido, custos, justificativas, pareceres e decisão."
    },
    rescisao:{
      category:"Gestão contratual",
      title:"Rescisão / extinção",
      desc:"Motivação, contraditório, parecer e decisão."
    },
    disciplinar:{
      category:"Responsabilização interna",
      title:"Processo disciplinar",
      desc:"Instauração, citação, defesa, relatório e julgamento."
    },
    sindicancia:{
      category:"Apuração interna",
      title:"Sindicância",
      desc:"Fato, diligências, provas e relatório conclusivo."
    }
  };
}
function homeV86Card(key,meta){
  var icon=(typeof homeIconSvg==="function")?homeIconSvg(key):"";
  return '<article class="home-v86-card" data-module="'+key+'">'+
    '<div class="home-v86-icon">'+icon+'</div>'+
    '<div>'+
      '<span class="home-v86-category">'+ovEsc(meta.category)+'</span>'+
      '<h3>'+ovEsc(meta.title)+'</h3>'+
      '<p>'+ovEsc(meta.desc)+'</p>'+
      '<div class="home-v86-actions">'+
        '<button class="home-v86-open" onclick="abrirModulo(\''+key+'\')">Abrir módulo →</button>'+
        '<button class="home-v86-model" onclick="abrirModeloModuloV85(\''+key+'\')">Processo modelo</button>'+
      '</div>'+
    '</div>'+
  '</article>';
}
function homeV86Recent(){
  var list=(typeof recentStore==="function")?recentStore():[];
  if(!list.length){
    return '<div class="home-v86-empty">Os processos analisados nesta sessão aparecerão aqui para acesso rápido.</div>';
  }
  return list.slice(0,3).map(function(x){
    return '<article class="home-v86-recent-item">'+
      '<b>'+ovEsc(x.number||"Processo")+'</b>'+
      '<span>'+ovEsc(x.module_label||"Processo administrativo")+'</span>'+
      '<span>'+ovEsc(x.interested||"Interessado não informado")+'</span>'+
      '<button onclick="abrirProcessoRecente(\''+ovEsc(x.id)+'\')">Abrir processo →</button>'+
    '</article>';
  }).join("");
}
function construirHomeV86(){
  var home=document.getElementById("screenHome");
  if(!home)return;
  var root=document.getElementById("homeV86");
  if(!root){
    root=document.createElement("section");
    root.id="homeV86";
    root.className="home-v86";
    home.insertBefore(root,home.firstChild);
  }
  var meta=homeV86Meta();
  var keys=["penalizacao","fiscalizacao","reequilibrio","rescisao","disciplinar","sindicancia"];

  root.innerHTML=
    '<section class="home-v86-summary">'+
      '<div>'+
        '<h1>Escolha o fluxo que você deseja analisar</h1>'+
        '<p>Seis módulos especializados, com evidências rastreáveis por documento e página e revisão humana preservada.</p>'+
      '</div>'+
      '<div class="home-v86-kpis">'+
        '<div class="home-v86-kpi"><b>6 módulos</b><span>fluxos especializados</span></div>'+
        '<div class="home-v86-kpi"><b>ID + página</b><span>rastreabilidade</span></div>'+
        '<div class="home-v86-kpi"><b>Revisão humana</b><span>decisão final</span></div>'+
      '</div>'+
    '</section>'+
    '<div class="home-v86-modules-head">'+
      '<div><h2>Módulos especializados</h2><p>Acesse diretamente o fluxo desejado ou abra um processo modelo para demonstração.</p></div>'+
      '<span class="home-v86-count">6 fluxos disponíveis</span>'+
    '</div>'+
    '<section class="home-v86-grid">'+keys.map(function(k){return homeV86Card(k,meta[k])}).join("")+'</section>'+
    '<section class="home-v86-recent" id="homeV86Recent">'+
      '<div class="home-v86-recent-head">'+
        '<div><h2>Processos recentes</h2><p>Retome os últimos processos usados nesta sessão.</p></div>'+
      '</div>'+
      '<div class="home-v86-recent-list">'+homeV86Recent()+'</div>'+
    '</section>';
}
function atualizarHomeV86Recent(){
  var box=document.querySelector("#homeV86Recent .home-v86-recent-list");
  if(box)box.innerHTML=homeV86Recent();
}

/* A busca passa a atuar somente na Home nova e nos recentes novos. */
buscarHomeV85=function(q){
  var raw=String(q||"").trim();
  var key=raw.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"");
  var count=0;
  document.querySelectorAll("#homeV86 .home-v86-card").forEach(function(card){
    var txt=(card.textContent||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"");
    var show=!key||txt.indexOf(key)>=0;
    card.style.display=show?"grid":"none";
    if(show)count++;
  });
  document.querySelectorAll("#homeV86 .home-v86-recent-item").forEach(function(row){
    var txt=(row.textContent||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"");
    row.style.display=(!key||txt.indexOf(key)>=0)?"block":"none";
  });
};

var _prepararHomeComercialV86=prepararHomeComercial;
prepararHomeComercial=function(){
  _prepararHomeComercialV86();
  setTimeout(function(){
    construirHomeV86();
    atualizarBuscaTopoV85();
  },0);
};

var _deixarHomeMaisProdutoV86=deixarHomeMaisProduto;
deixarHomeMaisProduto=function(){
  _deixarHomeMaisProdutoV86();
  setTimeout(function(){
    construirHomeV86();
    atualizarBuscaTopoV85();
  },0);
};

var _voltarAosModulosV86=voltarAosModulos;
voltarAosModulos=function(push){
  _voltarAosModulosV86(push);
  setTimeout(function(){
    construirHomeV86();
    atualizarBuscaTopoV85();
  },0);
};

document.addEventListener("DOMContentLoaded",function(){
  setTimeout(function(){
    construirHomeV86();
    atualizarBuscaTopoV85();
  },420);
});
</script>
"""
core.HTML = core.HTML.replace("</body>", _home_v86_js + "</body>", 1)


# --- Home final congelada v8.7: compactação para 1366x768 ---
_home_v87_css = r"""
<style id="fiscaliza-home-v87">
/* Ajuste final: manter os 6 módulos e ações totalmente visíveis na primeira dobra */

#screenHome{
  padding-top:8px!important;
  padding-bottom:14px!important
}

.home-v86-summary{
  min-height:80px!important;
  padding:11px 14px!important;
  gap:14px!important
}
.home-v86-summary h1{
  font-size:24px!important;
  line-height:1.12!important
}
.home-v86-summary p{
  margin-top:4px!important;
  font-size:16px!important;
  line-height:1.35!important
}
.home-v86-kpis{
  gap:7px!important
}
.home-v86-kpi{
  min-width:136px!important;
  padding:7px 9px!important
}
.home-v86-kpi b{
  font-size:16px!important
}
.home-v86-kpi span{
  margin-top:2px!important;
  font-size:15px!important;
  line-height:1.2!important
}

/* Aproxima os módulos da faixa superior */
.home-v86-modules-head{
  margin:8px 2px 6px!important
}
.home-v86-modules-head h2{
  font-size:20px!important
}
.home-v86-modules-head p{
  margin-top:2px!important;
  font-size:15px!important;
  line-height:1.3!important
}

/* Chip redundante removido: o topo já informa os 6 módulos */
.home-v86-count{
  display:none!important
}

/* Cards ligeiramente mais baixos sem reduzir legibilidade */
.home-v86-grid{
  gap:9px!important
}
.home-v86-card{
  min-height:118px!important;
  padding:10px 13px!important;
  grid-template-columns:52px minmax(0,1fr)!important;
  gap:11px!important
}
.home-v86-icon{
  width:48px!important;
  height:48px!important;
  border-radius:10px!important;
  margin-top:1px!important
}
.home-v86-icon svg{
  width:25px!important;
  height:25px!important
}
.home-v86-category{
  padding:3px 7px!important;
  font-size:15px!important
}
.home-v86-card h3{
  margin-top:4px!important;
  font-size:18px!important;
  line-height:1.2!important
}
.home-v86-card p{
  margin-top:3px!important;
  font-size:16px!important;
  line-height:1.3!important
}
.home-v86-actions{
  margin-top:7px!important;
  gap:7px!important
}
.home-v86-open,
.home-v86-model{
  padding:6px 9px!important;
  font-size:15px!important
}

/* Recentes continua abaixo e não compete com a seleção inicial */
.home-v86-recent{
  margin-top:10px!important
}

/* Notebook / 1366x768: alvo principal */
@media(max-height:800px) and (min-width:1000px){
  #screenHome{
    padding-top:6px!important
  }
  .home-v86-summary{
    min-height:74px!important;
    padding:9px 13px!important
  }
  .home-v86-summary h1{
    font-size:23px!important
  }
  .home-v86-kpi{
    padding:6px 8px!important
  }
  .home-v86-modules-head{
    margin-top:6px!important;
    margin-bottom:5px!important
  }
  .home-v86-card{
    min-height:112px!important;
    padding-top:9px!important;
    padding-bottom:9px!important
  }
  .home-v86-actions{
    margin-top:5px!important
  }
}
</style>
"""
core.HTML = core.HTML.replace("</head>", _home_v87_css + "</head>", 1)


# --- Arquitetura do ciclo completo da contratação v8.8 ---
# O produto deixa de misturar contratos com apuração funcional e passa a cobrir
# o ciclo da contratação pública: planejamento -> formalização -> execução ->
# alterações -> responsabilização -> encerramento.

core.MODULES = {
    "planejamento":{
        "label":"Planejamento da contratação",
        "short":"Planejamento",
        "desc":"DFD, ETP, termo de referência, preços, riscos e aprovações."
    },
    "formalizacao":{
        "label":"Formalização da contratação",
        "short":"Formalização",
        "desc":"Seleção, proposta, adjudicação/homologação, contrato, garantias e designações."
    },
    "fiscalizacao":{
        "label":"Fiscalização e execução",
        "short":"Fiscalização",
        "desc":"Execução, entregas, ocorrências, medições, recebimento e providências."
    },
    "alteracoes":{
        "label":"Alterações contratuais",
        "short":"Alterações",
        "desc":"Aditivos, prorrogações, reajuste, repactuação e reequilíbrio econômico-financeiro."
    },
    "penalizacao":{
        "label":"Penalização contratual",
        "short":"Penalização",
        "desc":"Instauração, notificação, defesa, instrução, decisão e sanção."
    },
    "encerramento":{
        "label":"Extinção / encerramento",
        "short":"Encerramento",
        "desc":"Extinção, obrigações finais, recebimento definitivo e registros de encerramento."
    }
}

core.MODULE_RULES = {
    "planejamento":[
        ("Documento de formalização da demanda",["formalizacao da demanda"]),
        ("Estudo técnico preliminar",["estudo tecnico preliminar"]),
        ("Termo de referência / projeto básico",["termo de referencia"]),
        ("Pesquisa de preços / orçamento estimado",["pesquisa de precos"]),
        ("Mapa ou matriz de riscos",["riscos"]),
        ("Autorização / aprovação do planejamento",["autorizacao"])
    ],
    "formalizacao":[
        ("Edital / instrumento de seleção",["edital"]),
        ("Proposta vencedora",["proposta vencedora"]),
        ("Adjudicação / homologação",["homologacao"]),
        ("Ata / registro do resultado",["ata"]),
        ("Contrato ou instrumento equivalente",["contrato"]),
        ("Designação de fiscal ou gestor",["designacao"])
    ],
    "fiscalizacao":[
        ("Instrumento contratual",["contrato"]),
        ("Designação de fiscal ou gestor",["fiscal"]),
        ("Relatório de execução / fiscalização",["relatorio","execucao"]),
        ("Entrega, medição ou recebimento",["recebimento"]),
        ("Ocorrência ou comunicação à contratada",["notificacao"]),
        ("Providência ou regularização registrada",["providencia"])
    ],
    "alteracoes":[
        ("Pedido / justificativa da alteração",["alteracao contratual"]),
        ("Contrato vigente",["contrato"]),
        ("Memória de cálculo / planilha / preços",["planilha"]),
        ("Disponibilidade orçamentária",["dotacao"]),
        ("Parecer técnico ou jurídico",["parecer"]),
        ("Termo aditivo / apostilamento / decisão",["termo aditivo"])
    ],
    "encerramento":[
        ("Contrato ou instrumento equivalente",["contrato"]),
        ("Motivação da extinção / encerramento",["extincao"]),
        ("Comunicação ou notificação da contratada",["notificacao"]),
        ("Manifestação / contraditório quando cabível",["manifestacao"]),
        ("Parecer / análise final",["parecer"]),
        ("Decisão e registro de encerramento",["encerramento"])
    ]
}

# Processos-modelo específicos dos novos fluxos.
core.MODEL_CASES.update({
    "planejamento":{
        "title":"Planejamento da contratação",
        "pages":[
            (
                "PROCESSO DE PLANEJAMENTO DA CONTRATAÇÃO Nº 3101/2026",
                "CASO FICTÍCIO. Aquisição de notebooks para modernização de unidades administrativas municipais."
            ),
            (
                "DOCUMENTO DE FORMALIZAÇÃO DA DEMANDA — DFD",
                "A unidade requisitante registra a necessidade de aquisição, problema a ser resolvido, quantitativo preliminar de 60 notebooks e resultados esperados. Documento de formalização da demanda aprovado pela chefia da unidade."
            ),
            (
                "ESTUDO TÉCNICO PRELIMINAR — ETP",
                "O estudo técnico preliminar descreve a necessidade, alternativas disponíveis, requisitos mínimos, estimativa de quantitativos e justificativa da solução escolhida."
            ),
            (
                "MAPA DE RISCOS DA CONTRATAÇÃO",
                "O mapa de riscos identifica riscos de especificação inadequada, atraso no fornecimento, variação de preços e recebimento de equipamentos em desacordo, com medidas preventivas e responsáveis."
            ),
            (
                "PESQUISA DE PREÇOS E ORÇAMENTO ESTIMADO",
                "A pesquisa de preços reúne fontes de mercado e consolida orçamento estimado para 60 unidades, com memória da metodologia utilizada e tratamento dos valores coletados."
            ),
            (
                "TERMO DE REFERÊNCIA",
                "O termo de referência define objeto, 60 notebooks, requisitos técnicos, prazo de entrega, critérios de aceitação, obrigações, fiscalização, forma de pagamento e condições de recebimento."
            ),
            (
                "AUTORIZAÇÃO DO PLANEJAMENTO",
                "A autoridade competente registra autorização para prosseguimento da contratação após conferência do documento de formalização da demanda, estudo técnico preliminar, pesquisa de preços, riscos e termo de referência."
            )
        ]
    },
    "formalizacao":{
        "title":"Formalização da contratação",
        "pages":[
            (
                "PROCESSO DE FORMALIZAÇÃO DA CONTRATAÇÃO Nº 3202/2026",
                "CASO FICTÍCIO. Contratação decorrente de processo competitivo para aquisição de notebooks destinados a unidades municipais."
            ),
            (
                "EDITAL DO PREGÃO ELETRÔNICO Nº 41/2026",
                "O edital estabelece objeto, critérios de julgamento, condições de participação, requisitos de habilitação, prazo e regras do procedimento de seleção."
            ),
            (
                "PROPOSTA VENCEDORA",
                "A empresa Tecnologia Modelo Ltda. apresenta proposta vencedora para fornecimento de 60 notebooks, com preço unitário e condições compatíveis com o edital."
            ),
            (
                "ATA DA SESSÃO E RESULTADO",
                "A ata registra propostas, lances, classificação, habilitação e resultado final da sessão pública."
            ),
            (
                "ADJUDICAÇÃO E HOMOLOGAÇÃO",
                "A autoridade adjudica o objeto à proposta vencedora e registra a homologação do resultado do procedimento."
            ),
            (
                "CONTRATO ADMINISTRATIVO Nº 188/2026",
                "CONTRATANTE: Município Demonstração. CONTRATADA: Tecnologia Modelo Ltda. Objeto: fornecimento de 60 notebooks. O contrato estabelece prazo, obrigações, recebimento, pagamento, fiscalização e demais condições."
            ),
            (
                "PORTARIA DE DESIGNAÇÃO DE FISCAL E GESTOR",
                "Ficam designados fiscal e gestor para acompanhar o Contrato Administrativo nº 188/2026 e registrar ocorrências e providências."
            ),
            (
                "PUBLICAÇÃO E REGISTRO DA CONTRATAÇÃO",
                "A unidade registra a publicação e os dados essenciais da contratação, concluindo a etapa de formalização."
            )
        ]
    },
    "alteracoes":{
        "title":"Alterações contratuais",
        "pages":[
            (
                "PROCESSO DE ALTERAÇÃO CONTRATUAL Nº 3404/2026",
                "CASO FICTÍCIO. Contrato nº 260/2026. Análise de prorrogação de prazo e reequilíbrio econômico-financeiro requerido pela contratada."
            ),
            (
                "CONTRATO ADMINISTRATIVO Nº 260/2026",
                "Objeto: fornecimento continuado de gêneros alimentícios. O contrato define prazo, preços, condições de reajuste e hipóteses de alteração."
            ),
            (
                "PEDIDO E JUSTIFICATIVA DE ALTERAÇÃO CONTRATUAL",
                "A unidade apresenta justificativa para prorrogação da vigência e a contratada formula pedido de alteração contratual com reequilíbrio econômico-financeiro em razão de aumento extraordinário de custos."
            ),
            (
                "PLANILHA, MEMÓRIA DE CÁLCULO E PESQUISA DE PREÇOS",
                "A instrução contém planilha comparativa, memória de cálculo e pesquisa de preços para demonstrar a variação dos custos e avaliar a vantajosidade da alteração."
            ),
            (
                "DECLARAÇÃO DE DOTAÇÃO E DISPONIBILIDADE ORÇAMENTÁRIA",
                "A unidade orçamentária registra dotação e disponibilidade para suportar a despesa decorrente da alteração contratual proposta."
            ),
            (
                "NOTA TÉCNICA DA UNIDADE GESTORA",
                "A área técnica examina necessidade, interesse público, vantajosidade, execução do contrato e documentação do pedido de alteração."
            ),
            (
                "PARECER JURÍDICO Nº 61/2026",
                "O parecer jurídico analisa os requisitos da prorrogação e do reequilíbrio econômico-financeiro, recomendando decisão motivada e formalização adequada."
            ),
            (
                "TERMO ADITIVO Nº 02/2026",
                "O termo aditivo formaliza a prorrogação da vigência e os efeitos financeiros aprovados, conforme decisão constante dos autos."
            )
        ]
    },
    "encerramento":{
        "title":"Extinção / encerramento",
        "pages":[
            (
                "PROCESSO DE EXTINÇÃO E ENCERRAMENTO Nº 3606/2026",
                "CASO FICTÍCIO. Contrato nº 411/2026. Avaliação de extinção e providências necessárias ao encerramento do vínculo contratual."
            ),
            (
                "CONTRATO ADMINISTRATIVO Nº 411/2026",
                "Objeto: serviços continuados de transporte. O contrato estabelece obrigações, prazo, hipóteses de extinção, recebimento e responsabilidades finais."
            ),
            (
                "RELATÓRIO DE MOTIVAÇÃO DA EXTINÇÃO",
                "A fiscalização registra descumprimentos reiterados e apresenta motivação técnica para avaliação da extinção contratual."
            ),
            (
                "NOTIFICAÇÃO À CONTRATADA",
                "A contratada fica notificada acerca da proposta de extinção e das ocorrências registradas, com possibilidade de manifestação."
            ),
            (
                "MANIFESTAÇÃO DA CONTRATADA",
                "A empresa apresenta manifestação, contesta parte das ocorrências e requer consideração das providências adotadas."
            ),
            (
                "PARECER JURÍDICO Nº 72/2026",
                "O parecer examina a motivação, o contraditório, os efeitos da extinção e as providências necessárias ao encerramento."
            ),
            (
                "DECISÃO DE EXTINÇÃO CONTRATUAL",
                "Após análise dos autos, a autoridade decide pela extinção do Contrato nº 411/2026 e determina as providências finais."
            ),
            (
                "TERMO DE ENCERRAMENTO E REGISTROS FINAIS",
                "O termo de encerramento registra recebimento definitivo do que foi executado, acertos finais, garantias, saldo contratual e baixa dos controles administrativos."
            )
        ]
    }
})

# O modelo de Fiscalização existente permanece válido e passa a ser apresentado
# como Fiscalização e execução.
if "fiscalizacao" in core.MODEL_CASES:
    core.MODEL_CASES["fiscalizacao"]["title"] = "Fiscalização e execução"

core.app.version = "8.8"


_home_cycle_v88_css = r"""
<style id="fiscaliza-home-cycle-v88">
/* Paleta dos seis fluxos do ciclo da contratação */
.home-v86-card[data-module="planejamento"] .home-v86-icon{background:#e9f2ff!important;color:#1767c7!important}
.home-v86-card[data-module="formalizacao"] .home-v86-icon{background:#edf0ff!important;color:#4f60bd!important}
.home-v86-card[data-module="fiscalizacao"] .home-v86-icon{background:#e6f6f1!important;color:#087d72!important}
.home-v86-card[data-module="alteracoes"] .home-v86-icon{background:#fff0df!important;color:#c46818!important}
.home-v86-card[data-module="penalizacao"] .home-v86-icon{background:#fdecee!important;color:#b62939!important}
.home-v86-card[data-module="encerramento"] .home-v86-icon{background:#eef2f5!important;color:#405d72!important}

/* A Home passa a comunicar explicitamente o ciclo contratual */
.home-v86-cycle{
  display:flex;
  align-items:center;
  gap:5px;
  flex-wrap:wrap;
  margin-top:7px
}
.home-v86-cycle span{
  display:inline-flex;
  align-items:center;
  gap:5px;
  color:#718699;
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:14px!important;
  line-height:1.2!important
}
.home-v86-cycle span:not(:last-child):after{
  content:"→";
  color:#9aabb8;
  margin-left:2px
}
</style>
"""
core.HTML = core.HTML.replace("</head>", _home_cycle_v88_css + "</head>", 1)

_home_cycle_v88_js = r"""
<script id="fiscaliza-home-cycle-v88-js">
/* Catálogo oficial do produto — somente os seis fluxos do ciclo contratual. */
moduleLabels={
  planejamento:"Planejamento da contratação",
  formalizacao:"Formalização da contratação",
  fiscalizacao:"Fiscalização e execução",
  alteracoes:"Alterações contratuais",
  penalizacao:"Penalização contratual",
  encerramento:"Extinção / encerramento"
};

function homeV86Meta(){
  return {
    planejamento:{
      category:"Fase preparatória",
      title:"Planejamento da contratação",
      desc:"DFD, ETP, termo de referência, preços, riscos e aprovações."
    },
    formalizacao:{
      category:"Contratação",
      title:"Formalização da contratação",
      desc:"Seleção, proposta, adjudicação/homologação, contrato e designações."
    },
    fiscalizacao:{
      category:"Execução contratual",
      title:"Fiscalização e execução",
      desc:"Entregas, ocorrências, medições, recebimento e providências."
    },
    alteracoes:{
      category:"Gestão contratual",
      title:"Alterações contratuais",
      desc:"Aditivos, prorrogações, reajuste, repactuação e reequilíbrio."
    },
    penalizacao:{
      category:"Responsabilização",
      title:"Penalização contratual",
      desc:"Instauração, notificação, defesa, instrução, decisão e sanção."
    },
    encerramento:{
      category:"Encerramento",
      title:"Extinção / encerramento",
      desc:"Extinção, obrigações finais, recebimento definitivo e registros."
    }
  };
}

function homeIconSvg(key){
  var base='fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
  var map={
    planejamento:'<svg viewBox="0 0 24 24"><path '+base+' d="M5 4h14v16H5zM8 8h8M8 12h5M8 16h7"/><path '+base+' d="M9 2h6v4H9z"/></svg>',
    formalizacao:'<svg viewBox="0 0 24 24"><path '+base+' d="M6 3h9l3 3v15H6zM15 3v4h4M9 12h6"/><path '+base+' d="M9 16l2 2 4-5"/></svg>',
    fiscalizacao:'<svg viewBox="0 0 24 24"><circle '+base+' cx="10" cy="10" r="6"/><path '+base+' d="M14.5 14.5L20 20M8 10l1.5 1.5L13 8"/></svg>',
    alteracoes:'<svg viewBox="0 0 24 24"><path '+base+' d="M4 7h12M13 4l3 3-3 3M20 17H8M11 14l-3 3 3 3"/></svg>',
    penalizacao:'<svg viewBox="0 0 24 24"><path '+base+' d="M14 4l6 6M12 6l6 6M5 19l7-7M4 20l3-3M15 3l6 6-3 3-6-6z"/></svg>',
    encerramento:'<svg viewBox="0 0 24 24"><path '+base+' d="M6 3h12v18H6zM9 8h6M9 12h6"/><path '+base+' d="M9 16l2 2 4-5"/></svg>'
  };
  return map[key]||'';
}

function moduloCategoriaCor(key){
  return {
    planejamento:"#1767c7",
    formalizacao:"#4f60bd",
    fiscalizacao:"#087d72",
    alteracoes:"#c46818",
    penalizacao:"#b62939",
    encerramento:"#405d72"
  }[key]||"#1767c7";
}

/* Contexto específico da área de trabalho de cada novo módulo. */
var _aplicarContextoDoModuloV88=aplicarContextoDoModulo;
aplicarContextoDoModulo=function(key){
  _aplicarContextoDoModuloV88(key);
  var meta=homeV86Meta()[key];
  if(!meta)return;
  var t=document.getElementById("workspaceModuleTitle");
  var d=document.getElementById("workspaceModuleDesc");
  if(t)t.textContent=meta.title;
  if(d)d.textContent=meta.desc;
  document.title="Fiscaliza.AI · "+meta.title;
};

/* Reconstrói a Home com a nova arquitetura e somente estes seis fluxos. */
function construirHomeV86(){
  var home=document.getElementById("screenHome");
  if(!home)return;
  var root=document.getElementById("homeV86");
  if(!root){
    root=document.createElement("section");
    root.id="homeV86";
    root.className="home-v86";
    home.insertBefore(root,home.firstChild);
  }

  var meta=homeV86Meta();
  var keys=["planejamento","formalizacao","fiscalizacao","alteracoes","penalizacao","encerramento"];

  root.innerHTML=
    '<section class="home-v86-summary">'+
      '<div>'+
        '<h1>Inteligência processual para o ciclo da contratação pública</h1>'+
        '<p>Da necessidade administrativa ao encerramento do contrato, organize documentos, evidências, pendências e decisões com rastreabilidade por documento e página.</p>'+
        '<div class="home-v86-cycle">'+
          '<span>Planejamento</span><span>Formalização</span><span>Execução</span><span>Alterações</span><span>Penalização</span><span>Encerramento</span>'+
        '</div>'+
      '</div>'+
      '<div class="home-v86-kpis">'+
        '<div class="home-v86-kpi"><b>6 módulos</b><span>ciclo contratual</span></div>'+
        '<div class="home-v86-kpi"><b>ID + página</b><span>rastreabilidade</span></div>'+
        '<div class="home-v86-kpi"><b>Revisão humana</b><span>decisão final</span></div>'+
      '</div>'+
    '</section>'+
    '<div class="home-v86-modules-head">'+
      '<div><h2>Módulos especializados</h2><p>Escolha a etapa do ciclo contratual ou abra um processo modelo para demonstração.</p></div>'+
    '</div>'+
    '<section class="home-v86-grid">'+keys.map(function(k){return homeV86Card(k,meta[k])}).join("")+'</section>'+
    '<section class="home-v86-recent" id="homeV86Recent">'+
      '<div class="home-v86-recent-head"><div><h2>Processos recentes</h2><p>Retome os últimos processos usados nesta sessão.</p></div></div>'+
      '<div class="home-v86-recent-list">'+homeV86Recent()+'</div>'+
    '</section>';
}

/* Processo modelo funciona para os seis novos módulos. */
function ativarCardsModeloV85(){
  var keys=["planejamento","formalizacao","fiscalizacao","alteracoes","penalizacao","encerramento"];
  document.querySelectorAll("#homeV86 .home-v86-card").forEach(function(card){
    var key=card.getAttribute("data-module");
    if(keys.indexOf(key)<0)return;
    var open=card.querySelector(".home-v86-open");
    if(open){
      open.textContent="Abrir processo modelo →";
      open.setAttribute("onclick","abrirModeloModuloV85('"+key+"')");
    }
  });
}
function restaurarCardsModuloV85(){
  var keys=["planejamento","formalizacao","fiscalizacao","alteracoes","penalizacao","encerramento"];
  document.querySelectorAll("#homeV86 .home-v86-card").forEach(function(card){
    var key=card.getAttribute("data-module");
    if(keys.indexOf(key)<0)return;
    var open=card.querySelector(".home-v86-open");
    if(open){
      open.textContent="Abrir módulo →";
      open.setAttribute("onclick","abrirModulo('"+key+"')");
    }
  });
}

document.addEventListener("DOMContentLoaded",function(){
  setTimeout(function(){
    construirHomeV86();
    if(typeof atualizarBuscaTopoV85==="function")atualizarBuscaTopoV85();
  },520);
});
</script>
"""
core.HTML = core.HTML.replace("</body>", _home_cycle_v88_js + "</body>", 1)


# --- Processo modelo: carregamento automático robusto v8.9 ---
_model_autoload_v89_js = r"""
<script id="fiscaliza-model-autoload-v89-js">
var modelLoadV89Busy=false;

/* 
   O botão Processo modelo da Home precisa fazer duas coisas na mesma ação:
   1) abrir o módulo correto;
   2) carregar e analisar o PDF fictício daquele módulo.
   Não depende mais de timeout.
*/
async function abrirModeloModuloV85(key){
  if(modelLoadV89Busy)return;
  if(!moduleLabels[key])return;

  modelLoadV89Busy=true;
  try{
    selectedModule=key;
    abrirTelaModulo(key,null,true);

    /* Garante que o contexto do módulo já esteja aplicado antes do download. */
    selectedModule=key;

    var status=document.getElementById("status");
    if(status){
      status.innerHTML='<span class="loading"><span class="spinner"></span> Carregando processo modelo de '+esc(moduleLabels[key])+'…</span>';
    }

    await testarDemo();
  }catch(e){
    var status=document.getElementById("status");
    if(status)status.textContent="Não foi possível carregar o processo modelo deste módulo.";
    console.error("Falha ao abrir processo modelo",e);
  }finally{
    modelLoadV89Busy=false;
  }
}

/* Botão interno usa sempre o módulo exibido na área de trabalho. */
async function usarProcessoModeloV89(){
  if(modelLoadV89Busy)return;
  modelLoadV89Busy=true;
  try{
    var q=new URLSearchParams(window.location.search).get("module");
    if(q&&moduleLabels[q])selectedModule=q;
    await testarDemo();
  }finally{
    modelLoadV89Busy=false;
  }
}

/* Substitui, na barra do módulo, a chamada genérica pelo carregamento protegido. */
function corrigirBotoesModeloV89(){
  document.querySelectorAll("#screenWorkspace .workspace-actions button").forEach(function(btn){
    var txt=(btn.textContent||"").toLowerCase();
    if(txt.indexOf("processo modelo")>=0){
      btn.setAttribute("onclick","usarProcessoModeloV89()");
    }
  });
}

/* Se o módulo foi aberto por URL, mantém selectedModule sincronizado. */
function sincronizarModuloV89(){
  var q=new URLSearchParams(window.location.search).get("module");
  if(q&&moduleLabels[q])selectedModule=q;
  corrigirBotoesModeloV89();
}

document.addEventListener("DOMContentLoaded",function(){
  setTimeout(sincronizarModuloV89,650);
});

var _abrirTelaModuloV89=abrirTelaModulo;
abrirTelaModulo=function(key,el,push){
  _abrirTelaModuloV89(key,el,push);
  selectedModule=key;
  setTimeout(corrigirBotoesModeloV89,0);
};
window.abrirModulo=abrirTelaModulo;
</script>
"""
core.HTML = core.HTML.replace("</body>", _model_autoload_v89_js + "</body>", 1)




# --- Correção estrutural do catálogo v9.1 ---
# O backend legado mantém "geral" como fallback interno. A Home continua exibindo
# somente os seis módulos do ciclo contratual, mas o fallback precisa existir
# para perfil, minutas e rotinas genéricas do analisador.
core.MODULES.setdefault("geral",{
    "label":"Análise geral",
    "short":"Geral",
    "desc":"Análise documental genérica com cronologia, evidências e revisão humana."
})
core.MODULE_RULES.setdefault("geral",[
    ("Identificação do processo",["processo"]),
    ("Documento de origem",["protocolo"]),
    ("Manifestação do interessado",["manifestacao"]),
    ("Parecer / análise",["parecer"]),
    ("Decisão / encaminhamento",["decisao"])
])
core.app.version="9.1"

# --- Carregador central de processo modelo v9.0 ---
_model_loader_v90_css = r"""
<style id="fiscaliza-model-loader-v90">
.model-loader-v90{
  width:100%;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  gap:10px;
  min-height:190px;
  text-align:center
}
.model-loader-v90 .spinner-v90{
  width:34px;height:34px;
  border:3px solid #d8e6ec;
  border-top-color:#0b8f82;
  border-radius:50%;
  animation:modelSpinV90 .8s linear infinite
}
.model-loader-v90 strong{
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:18px!important;
  color:#12334d
}
.model-loader-v90 span{
  font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px!important;
  color:#6d8193
}
.model-loader-v90.error .spinner-v90{display:none}
.model-loader-v90.error strong{color:#a8333f}
@keyframes modelSpinV90{to{transform:rotate(360deg)}}
</style>
"""
core.HTML = core.HTML.replace("</head>", _model_loader_v90_css + "</head>", 1)

_model_loader_v90_js = r"""
<script id="fiscaliza-model-loader-v90-js">
var modelLoaderV90Busy=false;

function modelLoaderV90State(mode,key,msg){
  var empty=document.getElementById("systemEmpty");
  if(!empty)return;
  if(mode==="loading"){
    empty.style.display="flex";
    empty.innerHTML=
      '<div class="model-loader-v90">'+
        '<div class="spinner-v90"></div>'+
        '<strong>Carregando processo modelo</strong>'+
        '<span>'+esc(moduleLabels[key]||key)+' · preparando e analisando os documentos fictícios…</span>'+
      '</div>';
  }else if(mode==="error"){
    empty.style.display="flex";
    empty.innerHTML=
      '<div class="model-loader-v90 error">'+
        '<strong>Não foi possível carregar o processo modelo</strong>'+
        '<span>'+esc(msg||"Tente novamente. Se o problema persistir, confira o deploy mais recente.")+'</span>'+
      '</div>';
  }
}

/* Reimplementação completa: não depende da versão antiga de testarDemo. */
testarDemo=async function(){
  if(modelLoaderV90Busy)return;

  var queryModule=new URLSearchParams(window.location.search).get("module");
  var key=(queryModule&&moduleLabels[queryModule])?queryModule:selectedModule;
  if(!key||!moduleLabels[key]){
    key="penalizacao";
  }

  modelLoaderV90Busy=true;
  selectedModule=key;
  demoMode=true;
  modelLoaderV90State("loading",key);

  try{
    var r=await fetch("/api/demo-pdf?module="+encodeURIComponent(key),{
      method:"GET",
      cache:"no-store"
    });
    if(!r.ok){
      var detail="";
      try{detail=await r.text()}catch(_e){}
      throw new Error("PDF modelo indisponível ("+r.status+")"+(detail?": "+detail.slice(0,140):""));
    }

    var blob=await r.blob();
    if(!blob||blob.size<100){
      throw new Error("O arquivo do processo modelo veio vazio.");
    }

    var input=document.getElementById("files");
    if(!input){
      throw new Error("Campo de documentos não encontrado na área de trabalho.");
    }

    var file=new File(
      [blob],
      "Processo-Modelo-"+key+"-FiscalizaAI.pdf",
      {type:"application/pdf"}
    );

    var dt=new DataTransfer();
    dt.items.add(file);
    input.files=dt.files;

    /* Mantém o módulo escolhido mesmo que versões antigas tenham defaults internos. */
    selectedModule=key;

    await analisar();

    /* Confere se a análise realmente foi ativada. */
    if(!lastAnalysisData){
      await new Promise(function(resolve){setTimeout(resolve,120)});
    }
    if(!lastAnalysisData){
      throw new Error("O PDF foi carregado, mas a análise não foi concluída.");
    }

  }catch(e){
    console.error("Fiscaliza.AI · erro no processo modelo:",e);
    modelLoaderV90State(
      "error",
      key,
      e&&e.message?e.message:"Falha inesperada ao preparar o processo modelo."
    );
  }finally{
    demoMode=false;
    modelLoaderV90Busy=false;
  }
};

/* Home: abre a área, deixa o reset interno terminar e só então carrega o modelo. */
abrirModeloModuloV85=async function(key){
  if(modelLoaderV90Busy)return;
  if(!moduleLabels[key])return;

  selectedModule=key;
  abrirTelaModulo(key,null,true);

  /* A versão de interface agenda prepararInicioModulo em setTimeout(0).
     Esperamos esse ciclo terminar para não apagar a análise recém-carregada. */
  await new Promise(function(resolve){setTimeout(resolve,90)});

  selectedModule=key;
  await testarDemo();
};

/* Botão dentro do módulo usa o mesmo carregador central. */
usarProcessoModeloV89=async function(){
  await testarDemo();
};

function corrigirBotoesModeloV90(){
  document.querySelectorAll("#screenWorkspace button").forEach(function(btn){
    var txt=(btn.textContent||"").toLowerCase();
    if(txt.indexOf("usar processo modelo")>=0){
      btn.setAttribute("onclick","testarDemo()");
    }
  });
}

document.addEventListener("DOMContentLoaded",function(){
  setTimeout(corrigirBotoesModeloV90,760);
});

var _abrirTelaModuloV90=abrirTelaModulo;
abrirTelaModulo=function(key,el,push){
  _abrirTelaModuloV90(key,el,push);
  selectedModule=key;
  setTimeout(corrigirBotoesModeloV90,20);
};
window.abrirModulo=abrirTelaModulo;
</script>
"""
core.HTML = core.HTML.replace("</body>", _model_loader_v90_js + "</body>", 1)


# --- Separação definitiva: Abrir módulo x Processo modelo v9.2 ---
_model_flow_v92_js = r"""
<script id="fiscaliza-model-flow-v92-js">
/*
  Regra definitiva:
  - Abrir módulo = área vazia, nunca carrega demonstração.
  - Processo modelo = abre o módulo e carrega somente o modelo daquele módulo.
  - Uma demonstração antiga não pode terminar dentro de outro módulo.
*/
var modelFlowV92Token=0;

function cancelarModeloPendenteV92(){
  modelFlowV92Token++;
  modelLoaderV90Busy=false;
  modelLoadV89Busy=false;
  demoMode=false;
}

function limparWorkspaceParaModuloV92(){
  if(typeof prepararInicioModulo==="function"){
    prepararInicioModulo();
  }else{
    lastAnalysisData=null;
    var result=document.getElementById("result");
    if(result){result.innerHTML="";result.style.display="none"}
    var empty=document.getElementById("systemEmpty");
    if(empty)empty.style.display="flex";
  }
}

/* Ação exclusiva do botão "Abrir módulo". */
function abrirModuloV92(key){
  if(!moduleLabels[key])return;

  cancelarModeloPendenteV92();
  selectedModule=key;

  /* Usa a navegação existente, mas força estado vazio depois dos wrappers legados. */
  abrirTelaModulo(key,null,true);
  selectedModule=key;
  limparWorkspaceParaModuloV92();

  setTimeout(function(){
    if(selectedModule===key){
      limparWorkspaceParaModuloV92();
      corrigirBotoesModeloV92();
    }
  },30);
}

/* Carrega um modelo com chave explícita; nunca deduz pelo módulo anterior. */
async function carregarProcessoModeloV92(key){
  if(!moduleLabels[key])return;

  var myToken=++modelFlowV92Token;
  modelLoaderV90Busy=true;
  modelLoadV89Busy=true;
  demoMode=true;
  selectedModule=key;

  modelLoaderV90State("loading",key);

  try{
    var pdfResponse=await fetch("/api/demo-pdf?module="+encodeURIComponent(key),{
      method:"GET",
      cache:"no-store"
    });
    if(!pdfResponse.ok){
      var pdfDetail="";
      try{pdfDetail=await pdfResponse.text()}catch(_e){}
      throw new Error("PDF modelo indisponível ("+pdfResponse.status+")"+(pdfDetail?": "+pdfDetail.slice(0,140):""));
    }

    if(myToken!==modelFlowV92Token || selectedModule!==key)return;

    var blob=await pdfResponse.blob();
    if(!blob||blob.size<100)throw new Error("O arquivo do processo modelo veio vazio.");

    var input=document.getElementById("files");
    if(!input)throw new Error("Campo de documentos não encontrado.");

    var dt=new DataTransfer();
    dt.items.add(new File(
      [blob],
      "Processo-Modelo-"+key+"-FiscalizaAI.pdf",
      {type:"application/pdf"}
    ));
    input.files=dt.files;

    if(myToken!==modelFlowV92Token || selectedModule!==key)return;

    selectedModule=key;
    await analisar();

    /* Se o usuário trocou de módulo durante a análise, descarta visualmente o resultado antigo. */
    if(myToken!==modelFlowV92Token || selectedModule!==key){
      limparWorkspaceParaModuloV92();
      return;
    }

    /* Defesa adicional contra resposta de módulo incorreto. */
    var analyzedModule=(lastAnalysisData&&(
      lastAnalysisData.module_key ||
      (lastAnalysisData.process_profile&&lastAnalysisData.process_profile.module)
    ))||key;

    if(analyzedModule!==key){
      limparWorkspaceParaModuloV92();
      throw new Error("A análise retornou um módulo diferente do selecionado.");
    }

  }catch(e){
    if(myToken===modelFlowV92Token && selectedModule===key){
      console.error("Fiscaliza.AI · processo modelo:",e);
      modelLoaderV90State("error",key,e&&e.message?e.message:"Falha ao carregar o processo modelo.");
    }
  }finally{
    if(myToken===modelFlowV92Token){
      demoMode=false;
      modelLoaderV90Busy=false;
      modelLoadV89Busy=false;
    }
  }
}

/* Ação exclusiva do botão "Processo modelo" da Home. */
async function abrirModeloModuloV85(key){
  if(!moduleLabels[key])return;

  cancelarModeloPendenteV92();
  selectedModule=key;
  abrirTelaModulo(key,null,true);

  /* Espera os resets legados do abrirTelaModulo finalizarem. */
  await new Promise(function(resolve){setTimeout(resolve,80)});
  if(selectedModule!==key)return;

  limparWorkspaceParaModuloV92();
  selectedModule=key;
  await carregarProcessoModeloV92(key);
}

/* Botão interno: usa exatamente o módulo que está aberto. */
async function usarProcessoModeloV92(){
  var key=selectedModule;
  var q=new URLSearchParams(window.location.search).get("module");
  if(q&&moduleLabels[q])key=q;
  if(!key||!moduleLabels[key])return;

  cancelarModeloPendenteV92();
  selectedModule=key;
  limparWorkspaceParaModuloV92();
  await carregarProcessoModeloV92(key);
}

function corrigirBotoesModeloV92(){
  document.querySelectorAll("#screenWorkspace button").forEach(function(btn){
    var txt=(btn.textContent||"").trim().toLowerCase();
    if(txt.indexOf("usar processo modelo")>=0){
      btn.setAttribute("onclick","usarProcessoModeloV92()");
    }
  });
}

/* Home final: ações independentes e explícitas. */
homeV86Card=function(key,meta){
  var icon=(typeof homeIconSvg==="function")?homeIconSvg(key):"";
  return '<article class="home-v86-card" data-module="'+key+'">'+
    '<div class="home-v86-icon">'+icon+'</div>'+
    '<div>'+
      '<span class="home-v86-category">'+ovEsc(meta.category)+'</span>'+
      '<h3>'+ovEsc(meta.title)+'</h3>'+
      '<p>'+ovEsc(meta.desc)+'</p>'+
      '<div class="home-v86-actions">'+
        '<button class="home-v86-open" onclick="abrirModuloV92(\''+key+'\')">Abrir módulo →</button>'+
        '<button class="home-v86-model" onclick="abrirModeloModuloV85(\''+key+'\')">Processo modelo</button>'+
      '</div>'+
    '</div>'+
  '</article>';
};

/* Impede wrappers antigos de converter o botão Abrir módulo em modelo. */
ativarCardsModeloV85=function(){};
restaurarCardsModuloV85=function(){};

document.addEventListener("DOMContentLoaded",function(){
  setTimeout(function(){
    if(typeof construirHomeV86==="function")construirHomeV86();
    corrigirBotoesModeloV92();
  },900);
});
</script>
"""
core.HTML = core.HTML.replace("</body>", _model_flow_v92_js + "</body>", 1)
core.app.version="9.2"


# --- Especialização real dos novos módulos v9.3 ---
# Corrige fallback genérico, identificação do processo e segmentação documental.

core.MODULE_AUDIT.update({
    "planejamento":[
        ("Há Documento de Formalização da Demanda (DFD)?",[
            r"\bdocumento de formalizacao da demanda\b",r"\bdfd\b"
        ]),
        ("Há Estudo Técnico Preliminar (ETP)?",[
            r"\bestudo tecnico preliminar\b",r"\betp\b"
        ]),
        ("Há Termo de Referência ou Projeto Básico?",[
            r"\btermo de referencia\b",r"\bprojeto basico\b"
        ]),
        ("Há pesquisa de preços ou orçamento estimado?",[
            r"\bpesquisa de precos\b",r"\borcamento estimado\b"
        ]),
        ("Há mapa ou matriz de riscos?",[
            r"\bmapa de riscos\b",r"\bmatriz de riscos\b"
        ]),
        ("Há autorização ou aprovação do planejamento?",[
            r"\bautorizacao do planejamento\b",r"\baprovacao do planejamento\b",
            r"\bautoriza.{0,80}prosseguimento\b"
        ])
    ],
    "formalizacao":[
        ("Há edital ou instrumento de seleção?",[
            r"\bedital\b",r"\binstrumento de selecao\b"
        ]),
        ("Há proposta vencedora?",[
            r"\bproposta vencedora\b",r"\bempresa vencedora\b"
        ]),
        ("Há ata da sessão ou registro do resultado?",[
            r"\bata da sessao\b",r"\bregistro do resultado\b"
        ]),
        ("Há adjudicação e homologação?",[
            r"\badjudic",r"\bhomolog"
        ]),
        ("Há contrato ou instrumento equivalente?",[
            r"\bcontrato administrativo\b",r"\binstrumento equivalente\b"
        ]),
        ("Há designação de fiscal e/ou gestor?",[
            r"\bdesignacao de fiscal\b",r"\bfiscal e gestor\b",r"\bgestor do contrato\b"
        ])
    ],
    "alteracoes":[
        ("Há pedido ou justificativa da alteração contratual?",[
            r"\bpedido.{0,100}alteracao contratual\b",
            r"\bjustificativa.{0,100}alteracao contratual\b",
            r"\bpedido.{0,100}reequilibrio\b",
            r"\bprorrogacao\b"
        ]),
        ("Há contrato vigente vinculado?",[
            r"\bcontrato administrativo\b",r"\bcontrato vigente\b"
        ]),
        ("Há planilha, memória de cálculo ou pesquisa de preços?",[
            r"\bplanilha\b",r"\bmemoria de calculo\b",r"\bpesquisa de precos\b"
        ]),
        ("Há disponibilidade orçamentária?",[
            r"\bdotacao\b",r"\bdisponibilidade orcamentaria\b"
        ]),
        ("Há análise técnica ou parecer jurídico?",[
            r"\bnota tecnica\b",r"\bparecer juridico\b",r"\banalise tecnica\b"
        ]),
        ("Há termo aditivo, apostilamento ou decisão?",[
            r"\btermo aditivo\b",r"\bapostilamento\b",r"\bdecisao administrativa\b"
        ])
    ],
    "encerramento":[
        ("Há contrato ou instrumento a encerrar?",[
            r"\bcontrato administrativo\b",r"\binstrumento contratual\b"
        ]),
        ("Há motivação da extinção ou encerramento?",[
            r"\bmotivacao.{0,100}(?:extincao|encerramento)\b",
            r"\brelatorio de motivacao da extincao\b"
        ]),
        ("Houve notificação ou ciência da contratada?",[
            r"\bnotificacao\b",r"\bciencia da contratada\b"
        ]),
        ("Há manifestação ou contraditório quando cabível?",[
            r"\bmanifestacao da contratada\b",r"\bcontraditorio\b"
        ]),
        ("Há parecer ou análise final?",[
            r"\bparecer juridico\b",r"\banalise final\b"
        ]),
        ("Há decisão e registro de encerramento?",[
            r"\bdecisao de extincao contratual\b",
            r"\btermo de encerramento\b",
            r"\bregistros finais\b"
        ])
    ]
})

# Número de processo específico por novo fluxo.
_old_module_process_number_v93 = core._module_process_number
def _module_process_number_v93(pages,module):
    joined="\n".join(p.get("text") or "" for p in pages)
    pats={
        "planejamento":[
            r"Processo de Planejamento da Contrata[cç][aã]o\s*n[ºo.]?\s*([0-9.\-\/]+)"
        ],
        "formalizacao":[
            r"Processo de Formaliza[cç][aã]o da Contrata[cç][aã]o\s*n[ºo.]?\s*([0-9.\-\/]+)"
        ],
        "alteracoes":[
            r"Processo de Altera[cç][aã]o Contratual\s*n[ºo.]?\s*([0-9.\-\/]+)"
        ],
        "encerramento":[
            r"Processo de Extin[cç][aã]o e Encerramento\s*n[ºo.]?\s*([0-9.\-\/]+)",
            r"Processo de Encerramento Contratual\s*n[ºo.]?\s*([0-9.\-\/]+)"
        ]
    }
    if module in pats:
        for pat in pats[module]:
            m=re.search(pat,joined,flags=re.I)
            if m:
                return m.group(1).strip()
    return _old_module_process_number_v93(pages,module)

core._module_process_number = _module_process_number_v93

# O gerador de ID documental reconhece as peças próprias do novo ciclo.
_old_document_marker_v93 = core._document_marker
def _document_marker_v93(text):
    raw=text or ""
    lines=[re.sub(r"\s+"," ",x).strip() for x in raw.splitlines() if x.strip()]
    new_heads=[
        "DOCUMENTO DE FORMALIZAÇÃO DA DEMANDA",
        "DOCUMENTO DE FORMALIZACAO DA DEMANDA",
        "ESTUDO TÉCNICO PRELIMINAR",
        "ESTUDO TECNICO PRELIMINAR",
        "TERMO DE REFERÊNCIA",
        "TERMO DE REFERENCIA",
        "PROJETO BÁSICO",
        "PROJETO BASICO",
        "PESQUISA DE PREÇOS",
        "PESQUISA DE PRECOS",
        "ORÇAMENTO ESTIMADO",
        "ORCAMENTO ESTIMADO",
        "MAPA DE RISCOS",
        "MATRIZ DE RISCOS",
        "AUTORIZAÇÃO DO PLANEJAMENTO",
        "AUTORIZACAO DO PLANEJAMENTO",
        "EDITAL DO PREGÃO",
        "EDITAL DO PREGAO",
        "PROPOSTA VENCEDORA",
        "ATA DA SESSÃO",
        "ATA DA SESSAO",
        "ADJUDICAÇÃO E HOMOLOGAÇÃO",
        "ADJUDICACAO E HOMOLOGACAO",
        "PUBLICAÇÃO E REGISTRO DA CONTRATAÇÃO",
        "PUBLICACAO E REGISTRO DA CONTRATACAO",
        "PEDIDO E JUSTIFICATIVA DE ALTERAÇÃO CONTRATUAL",
        "PEDIDO E JUSTIFICATIVA DE ALTERACAO CONTRATUAL",
        "PLANILHA, MEMÓRIA DE CÁLCULO E PESQUISA DE PREÇOS",
        "PLANILHA, MEMORIA DE CALCULO E PESQUISA DE PRECOS",
        "DECLARAÇÃO DE DOTAÇÃO E DISPONIBILIDADE ORÇAMENTÁRIA",
        "DECLARACAO DE DOTACAO E DISPONIBILIDADE ORCAMENTARIA",
        "NOTA TÉCNICA DA UNIDADE GESTORA",
        "NOTA TECNICA DA UNIDADE GESTORA",
        "TERMO ADITIVO",
        "RELATÓRIO DE MOTIVAÇÃO DA EXTINÇÃO",
        "RELATORIO DE MOTIVACAO DA EXTINCAO",
        "MANIFESTAÇÃO DA CONTRATADA",
        "MANIFESTACAO DA CONTRATADA",
        "DECISÃO DE EXTINÇÃO CONTRATUAL",
        "DECISAO DE EXTINCAO CONTRATUAL",
        "TERMO DE ENCERRAMENTO E REGISTROS FINAIS"
    ]
    for line in lines[:10]:
        up=line.upper()
        if any(h in up for h in new_heads) and len(line)<=170:
            return line
    return _old_document_marker_v93(text)

core._document_marker = _document_marker_v93

# Rótulos de cronologia mais legíveis para Planejamento.
core.app.version="9.3"


# --- Análise blindada por módulo v9.4 ---
# O backend não depende apenas do estado JS para identificar um processo modelo.
# Se o arquivo é um dos modelos internos, o módulo é inferido do próprio nome do
# arquivo e prevalece sobre qualquer estado antigo do navegador.

from typing import List as _ListV94
from fastapi import UploadFile as _UploadFileV94, File as _FileV94, HTTPException as _HTTPExceptionV94

_V94_MODULE_KEYS = {
    "planejamento","formalizacao","fiscalizacao",
    "alteracoes","penalizacao","encerramento"
}

def _demo_module_from_filename_v94(filename):
    name=str(filename or "").lower()
    for key in _V94_MODULE_KEYS:
        if (
            ("processo-modelo-"+key) in name
            or ("processo_modelo_"+key) in name
            or ("modelo-"+key) in name
        ):
            return key
    return None

async def _analyze_v94(
    files:_ListV94[_UploadFileV94]=_FileV94(...),
    module:str="penalizacao",
    process_number:str="",
    interested:str="",
    unit:str=""
):
    pages=[];ocr=0;names=[]
    detected_module=None

    for f in files:
        filename=f.filename or ""
        if not filename.lower().endswith(".pdf"):
            continue
        if not detected_module:
            detected_module=_demo_module_from_filename_v94(filename)
        pp,oo=core.extract_pdf(await f.read(),filename)
        pages.extend(pp);ocr+=oo;names.append(filename)

    if not pages:
        raise _HTTPExceptionV94(400,"Envie pelo menos um PDF.")

    # Para processo modelo, o próprio arquivo é a fonte de verdade do módulo.
    if detected_module:
        module=detected_module

    if module not in core.MODULES:
        module="geral"

    core._assign_document_ids(pages)
    a=core.analyze_pages(pages)
    a=core._module_overlay(pages,a,module)
    a=core._enrich_doc_refs(a,pages)
    profile=core._derive_process_profile(pages,module,process_number,interested,unit)
    a["process_profile"]=profile
    a["source_mode"]="modelo" if detected_module else "upload"

    aid=core.uuid.uuid4().hex
    core.ANALYSES[aid]={
        "pages":pages,
        "analysis":a,
        "created":core.datetime.utcnow().isoformat(),
        "module":module,
        "profile":profile,
        "files":names
    }
    return {
        "analysis_id":aid,
        "files":names,
        "pages":len(pages),
        "ocr_pages":ocr,
        "module":module,
        "profile":profile,
        "analysis":a
    }

core.app.router.routes=[
    r for r in core.app.router.routes
    if not (getattr(r,"path",None)=="/api/analyze" and "POST" in getattr(r,"methods",set()))
]
core.app.add_api_route("/api/analyze",_analyze_v94,methods=["POST"])
core.app.version="9.4"


# Frontend: durante a demonstração, a URL do módulo também é fonte de verdade.
_model_context_v94_js = r"""
<script id="fiscaliza-model-context-v94-js">
function moduloAbertoV94(fallback){
  var q=new URLSearchParams(window.location.search).get("module");
  if(q&&moduleLabels[q])return q;
  return (fallback&&moduleLabels[fallback])?fallback:selectedModule;
}

var _carregarProcessoModeloV92Base=carregarProcessoModeloV92;
carregarProcessoModeloV92=async function(key){
  key=moduloAbertoV94(key);
  selectedModule=key;
  return await _carregarProcessoModeloV92Base(key);
};

var _modelLoaderV90StateBase=modelLoaderV90State;
modelLoaderV90State=function(mode,key,msg){
  key=moduloAbertoV94(key);
  return _modelLoaderV90StateBase(mode,key,msg);
};
</script>
"""
core.HTML = core.HTML.replace("</body>", _model_context_v94_js + "</body>", 1)


# --- Coerência executiva dos seis módulos v9.5 ---
_overview_semantics_v95_js = r"""
<script id="fiscaliza-overview-semantics-v95-js">
/* Contagem no painel = documentos rastreáveis reais, não quantidade de controles. */
var _ativarProcessoNoSistemaV95=ativarProcessoNoSistema;
ativarProcessoNoSistema=function(a){
  _ativarProcessoNoSistemaV95(a);
  var docs=(a&&a.process_profile&&a.process_profile.documents);
  var dash=document.getElementById("dashDocs");
  if(dash&&docs!=null)dash.textContent=String(docs);

  var footer=document.querySelector(".side-footer");
  if(footer)footer.innerHTML="Rastreabilidade por documento e página<br>VERSÃO 9.5 · CICLO CONTRATUAL";
};

/* Etapas próprias por fluxo: elimina a régua genérica onde ela não faz sentido. */
var _ovStagesV95=ovStages;
ovStages=function(a){
  var m=a&&a.module_key;
  var rows=(a&&a.module_matrix)||[];
  var ok=function(i){return !!(rows[i]&&rows[i].ok)};
  if(m==="planejamento"){
    return [
      {label:"Demanda",done:ok(0)},
      {label:"Estudos",done:ok(1)},
      {label:"Especificação",done:ok(2)},
      {label:"Preços e riscos",done:ok(3)&&ok(4)},
      {label:"Aprovação",done:ok(5)}
    ];
  }
  if(m==="formalizacao"){
    return [
      {label:"Seleção",done:ok(0)},
      {label:"Proposta",done:ok(1)},
      {label:"Resultado",done:ok(2)&&ok(3)},
      {label:"Contrato",done:ok(4)},
      {label:"Designação",done:ok(5)}
    ];
  }
  if(m==="fiscalizacao"){
    return [
      {label:"Contrato",done:ok(0)},
      {label:"Fiscal designado",done:ok(1)},
      {label:"Execução",done:ok(2)},
      {label:"Medição / recebimento",done:ok(3)},
      {label:"Providências",done:ok(4)&&ok(5)}
    ];
  }
  if(m==="alteracoes"){
    return [
      {label:"Pedido / justificativa",done:ok(0)},
      {label:"Contrato vigente",done:ok(1)},
      {label:"Cálculos e orçamento",done:ok(2)&&ok(3)},
      {label:"Análise",done:ok(4)},
      {label:"Formalização",done:ok(5)}
    ];
  }
  if(m==="encerramento"){
    return [
      {label:"Contrato",done:ok(0)},
      {label:"Motivação",done:ok(1)},
      {label:"Ciência / manifestação",done:ok(2)&&ok(3)},
      {label:"Análise final",done:ok(4)},
      {label:"Encerramento",done:ok(5)}
    ];
  }
  return _ovStagesV95(a);
};

function titulosEvidenciaV95(moduleKey){
  var map={
    planejamento:["Documentos estruturantes","Controles complementares"],
    formalizacao:["Seleção e resultado","Contrato e designações"],
    fiscalizacao:["Execução e acompanhamento","Ocorrências e providências"],
    alteracoes:["Fundamentos da alteração","Análises e formalização"],
    encerramento:["Motivação e contraditório","Decisão e encerramento"]
  };
  return map[moduleKey]||["Elementos localizados","Pontos para revisão"];
}

/* Pós-processa somente textos de interface; Penalização preserva o desenho já validado. */
var _renderOverviewHubV95=renderOverviewHub;
renderOverviewHub=function(a){
  _renderOverviewHubV95(a);
  if(!a||a.module_key==="penalizacao")return;

  var hub=document.getElementById("overviewHub");
  if(!hub)return;

  var panelHeads=hub.querySelectorAll(".ov-panel-head");
  panelHeads.forEach(function(head){
    var h=head.querySelector("h3");
    if(h&&h.textContent.trim()==="Leitura executiva"){
      var p=head.querySelector("p");
      if(p)p.textContent="Síntese dos documentos, controles localizados e pontos para revisão.";
    }
  });

  var titles=titulosEvidenciaV95(a.module_key);
  var blocks=hub.querySelectorAll(".ov-evidence-block h4");
  if(blocks[0])blocks[0].textContent=titles[0];
  if(blocks[1])blocks[1].textContent=titles[1];
};

/* Minutas coerentes com os novos nomes de módulo. */
var _ovDefaultDraftKindV95=ovDefaultDraftKind;
ovDefaultDraftKind=function(a){
  var m=(a&&a.module_key)||selectedModule;
  if(m==="alteracoes"||m==="encerramento")return "decisao";
  if(m==="planejamento"||m==="formalizacao"||m==="fiscalizacao")return "relatorio";
  return _ovDefaultDraftKindV95(a);
};
</script>
"""
core.HTML = core.HTML.replace("</body>", _overview_semantics_v95_js + "</body>", 1)
core.app.version="9.5"


# --- Normalização final do overview v9.6 ---
_overview_normalize_v96_js = r"""
<script id="fiscaliza-overview-normalize-v96-js">
function overviewEtapasV96(a){
  var rows=(a&&a.module_matrix)||[];
  var ok=function(i){return !!(rows[i]&&rows[i].ok)};
  var m=a&&a.module_key;
  if(m==="planejamento")return [
    ["Demanda",ok(0)],["Estudos",ok(1)],["Especificação",ok(2)],
    ["Preços e riscos",ok(3)&&ok(4)],["Aprovação",ok(5)]
  ];
  if(m==="formalizacao")return [
    ["Seleção",ok(0)],["Proposta",ok(1)],["Resultado",ok(2)&&ok(3)],
    ["Contrato",ok(4)],["Designação",ok(5)]
  ];
  if(m==="fiscalizacao")return [
    ["Contrato",ok(0)],["Fiscal designado",ok(1)],["Execução",ok(2)],
    ["Medição / recebimento",ok(3)],["Providências",ok(4)&&ok(5)]
  ];
  if(m==="alteracoes")return [
    ["Pedido / justificativa",ok(0)],["Contrato vigente",ok(1)],
    ["Cálculos e orçamento",ok(2)&&ok(3)],["Análise",ok(4)],["Formalização",ok(5)]
  ];
  if(m==="encerramento")return [
    ["Contrato",ok(0)],["Motivação",ok(1)],["Ciência / manifestação",ok(2)&&ok(3)],
    ["Análise final",ok(4)],["Encerramento",ok(5)]
  ];
  return null;
}

function normalizarOverviewV96(a){
  if(!a)return;

  var docs=a.process_profile&&a.process_profile.documents;
  var dash=document.getElementById("dashDocs");
  if(dash&&docs!=null)dash.textContent=String(docs);

  var footer=document.querySelector(".side-footer");
  if(footer)footer.innerHTML="Rastreabilidade por documento e página<br>VERSÃO 9.6 · CICLO CONTRATUAL";

  if(a.module_key==="penalizacao")return;

  var hub=document.getElementById("overviewHub");
  if(!hub)return;

  var head=Array.from(hub.querySelectorAll(".ov-panel-head")).find(function(x){
    var h=x.querySelector("h3");return h&&h.textContent.trim()==="Leitura executiva";
  });
  if(head){
    var sub=head.querySelector("p");
    if(sub)sub.textContent="Síntese dos documentos, controles localizados e pontos para revisão.";
  }

  var titles=titulosEvidenciaV95(a.module_key);
  var blocks=hub.querySelectorAll(".ov-evidence-block h4");
  if(blocks[0])blocks[0].textContent=titles[0];
  if(blocks[1])blocks[1].textContent=titles[1];

  var stages=overviewEtapasV96(a);
  if(stages){
    var nodes=hub.querySelectorAll(".ov-stage");
    stages.forEach(function(row,i){
      if(!nodes[i])return;
      nodes[i].textContent=row[0];
      nodes[i].classList.toggle("done",!!row[1]);
    });
  }
}

var _ativarProcessoNoSistemaV96=ativarProcessoNoSistema;
ativarProcessoNoSistema=function(a){
  _ativarProcessoNoSistemaV96(a);
  normalizarOverviewV96(a);
  setTimeout(function(){normalizarOverviewV96(a)},0);
};
</script>
"""
core.HTML = core.HTML.replace("</body>", _overview_normalize_v96_js + "</body>", 1)
core.app.version="9.6"


# --- Isolamento de estado e pendências por módulo v9.7 ---
_old_module_overlay_v97 = core._module_overlay
def _module_overlay_v97(pages,a,module):
    out=_old_module_overlay_v97(pages,a,module)
    if module!="penalizacao":
        # Pendências herdadas do analisador sancionador não pertencem aos demais fluxos.
        flags=out.get("review_flags") or []
        out["pending"]=[x.get("text","") for x in flags if x.get("text")]

        # A cronologia deve apontar o primeiro documento que materializa cada marco,
        # não todas as páginas que apenas voltam a mencioná-lo.
        for item in out.get("module_timeline") or []:
            pgs=item.get("pages") or []
            if pgs:
                item["pages"]=[pgs[0]]
    return out

core._module_overlay=_module_overlay_v97
core.app.version="9.7"


_workspace_reset_v97_js = r"""
<script id="fiscaliza-workspace-reset-v97-js">
function emptyWorkspaceHtmlV97(){
  return '<div style="display:flex;gap:14px;align-items:flex-start">'+
    '<div class="empty-icon">+</div>'+
    '<div><h3>Nenhum processo aberto</h3>'+
    '<p>Inicie um novo processo para carregar os autos ou use um caso fictício pronto para conhecer este fluxo.</p>'+
    '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:16px">'+
      '<button class="btn btn-primary" onclick="novoProcessoModulo()">+ Novo processo</button>'+
      '<button class="btn btn-blue" onclick="usarProcessoModeloV92()">Usar processo modelo</button>'+
    '</div></div></div>';
}

var _prepararInicioModuloV97=prepararInicioModulo;
prepararInicioModulo=function(){
  _prepararInicioModuloV97();

  /* Nunca reaproveitar visão geral ou loading de outro módulo. */
  var hub=document.getElementById("overviewHub");
  if(hub){
    hub.classList.remove("visible");
    hub.innerHTML="";
    hub.style.display="none";
  }

  var empty=document.getElementById("systemEmpty");
  if(empty){
    empty.innerHTML=emptyWorkspaceHtmlV97();
    empty.style.display="flex";
  }

  var result=document.getElementById("result");
  if(result){
    result.innerHTML="";
    result.style.display="none";
  }

  var dash=document.getElementById("dashDocs");
  if(dash)dash.textContent="0";
};

var _ativarProcessoNoSistemaV97=ativarProcessoNoSistema;
ativarProcessoNoSistema=function(a){
  var hub=document.getElementById("overviewHub");
  if(hub)hub.style.display="";
  _ativarProcessoNoSistemaV97(a);
  normalizarOverviewV96(a);
};

/* Para os demais módulos, pendência = controle específico ausente. */
var _ovPendingV97=ovPending;
ovPending=function(a){
  if(a&&a.module_key!=="penalizacao"){
    return (a.review_flags||[]).map(function(x){return x.text}).filter(Boolean).slice(0,5);
  }
  return _ovPendingV97(a);
};
</script>
"""
core.HTML = core.HTML.replace("</body>", _workspace_reset_v97_js + "</body>", 1)


# --- Modelo somente por ação explícita v9.8 ---
_model_intent_v98_js = r"""
<script id="fiscaliza-model-intent-v98-js">
/*
  Regra operacional:
  - entrar em um módulo SEMPRE abre workspace vazio;
  - processo modelo só pode nascer de clique explícito em "Processo modelo"
    ou "Usar processo modelo";
  - resultado de um modelo cancelado nunca pode reaparecer depois.
*/
var modelIntentV98=false;
var modelRenderAuthorizedV98=false;
var modelRequestSeqV98=0;
var modelFetchControllerV98=null;

function cancelarModeloV98(){
  modelIntentV98=false;
  modelRenderAuthorizedV98=false;
  modelRequestSeqV98++;
  if(modelFetchControllerV98){
    try{modelFetchControllerV98.abort()}catch(_e){}
  }
  modelFetchControllerV98=null;
  if(typeof cancelarModeloPendenteV92==="function")cancelarModeloPendenteV92();
}

function workspaceVazioV98(key){
  cancelarModeloV98();
  selectedModule=key;

  /* um módulo aberto não herda análise/modelo anterior */
  analysisId=null;
  try{localStorage.removeItem("fiscaliza_analysis_id")}catch(_e){}
  var fi=document.getElementById("files");
  if(fi)fi.value="";

  abrirTelaModulo(key,null,true);
  selectedModule=key;

  if(typeof prepararInicioModulo==="function")prepararInicioModulo();
  if(typeof restaurarCabecalhoModulo==="function")restaurarCabecalhoModulo();

  var empty=document.getElementById("systemEmpty");
  if(empty){
    empty.innerHTML=emptyWorkspaceHtmlV97();
    empty.style.display="flex";
  }
  var hub=document.getElementById("overviewHub");
  if(hub){hub.innerHTML="";hub.classList.remove("visible");hub.style.display="none"}

  setTimeout(function(){
    if(selectedModule!==key)return;
    if(typeof prepararInicioModulo==="function")prepararInicioModulo();
    var e=document.getElementById("systemEmpty");
    if(e){e.innerHTML=emptyWorkspaceHtmlV97();e.style.display="flex"}
    var h=document.getElementById("overviewHub");
    if(h){h.innerHTML="";h.classList.remove("visible");h.style.display="none"}
  },60);
}

/* Esta é a única ação do botão "Abrir módulo". */
abrirModuloV92=function(key){
  if(!moduleLabels[key])return;
  workspaceVazioV98(key);
};
window.abrirModulo=abrirModuloV92;

/* Carregador exclusivo de modelo, com autorização e cancelamento próprios. */
async function carregarModeloExplicitoV98(key){
  if(!moduleLabels[key])return;
  cancelarModeloV98();

  var seq=++modelRequestSeqV98;
  modelIntentV98=true;
  modelRenderAuthorizedV98=true;
  selectedModule=key;
  demoMode=true;

  modelFetchControllerV98=new AbortController();
  modelLoaderV90State("loading",key);

  try{
    var r=await fetch("/api/demo-pdf?module="+encodeURIComponent(key),{
      method:"GET",
      cache:"no-store",
      signal:modelFetchControllerV98.signal
    });
    if(!r.ok)throw new Error("PDF modelo indisponível ("+r.status+").");
    if(seq!==modelRequestSeqV98 || !modelIntentV98)return;

    var blob=await r.blob();
    if(!blob||blob.size<100)throw new Error("O arquivo do processo modelo veio vazio.");
    if(seq!==modelRequestSeqV98 || !modelIntentV98)return;

    var input=document.getElementById("files");
    if(!input)throw new Error("Campo de documentos não encontrado.");

    var dt=new DataTransfer();
    dt.items.add(new File(
      [blob],
      "Processo-Modelo-"+key+"-FiscalizaAI.pdf",
      {type:"application/pdf"}
    ));
    input.files=dt.files;

    selectedModule=key;
    await analisar();

    if(seq!==modelRequestSeqV98 || !modelIntentV98){
      if(typeof prepararInicioModulo==="function")prepararInicioModulo();
      return;
    }
  }catch(e){
    if(e&&e.name==="AbortError")return;
    if(seq===modelRequestSeqV98 && modelIntentV98){
      modelLoaderV90State("error",key,e&&e.message?e.message:"Falha ao carregar o processo modelo.");
    }
  }finally{
    if(seq===modelRequestSeqV98){
      demoMode=false;
      modelIntentV98=false;
      modelRenderAuthorizedV98=false;
      modelFetchControllerV98=null;
    }
  }
}

/* Botão Processo modelo da Home. */
abrirModeloModuloV85=async function(key){
  if(!moduleLabels[key])return;

  cancelarModeloV98();
  var launchSeq=modelRequestSeqV98;
  selectedModule=key;
  abrirTelaModulo(key,null,true);

  await new Promise(function(resolve){setTimeout(resolve,90)});

  /* Se o usuário escolheu "Abrir módulo" durante esta espera, mesmo no
     MESMO módulo, a intenção de demonstração foi cancelada. */
  if(selectedModule!==key || launchSeq!==modelRequestSeqV98)return;

  if(typeof prepararInicioModulo==="function")prepararInicioModulo();
  selectedModule=key;
  await carregarModeloExplicitoV98(key);
};

/* Botão Usar processo modelo dentro do módulo. */
usarProcessoModeloV92=async function(){
  var q=new URLSearchParams(window.location.search).get("module");
  var key=(q&&moduleLabels[q])?q:selectedModule;
  if(!key||!moduleLabels[key])return;
  if(typeof prepararInicioModulo==="function")prepararInicioModulo();
  selectedModule=key;
  await carregarModeloExplicitoV98(key);
};

/* Bloqueia chamadas legadas a testarDemo: nenhum código antigo pode iniciar
   demonstração ao simples ato de abrir um módulo. */
testarDemo=async function(){
  return false;
};

/* Se uma resposta antiga de processo modelo chegar depois de o usuário ter
   aberto o módulo limpo, ela é descartada antes de tocar a interface. */
var _ajustarResultadoModuloV98=ajustarResultadoModulo;
ajustarResultadoModulo=function(a){
  if(a&&a.source_mode==="modelo"&&!modelRenderAuthorizedV98){
    return;
  }
  return _ajustarResultadoModuloV98(a);
};

/* Garante handlers finais, mesmo com scripts legados presentes na página. */
function corrigirAcoesModeloV98(){
  document.querySelectorAll("#homeV86 .home-v86-card").forEach(function(card){
    var key=card.getAttribute("data-module");
    var open=card.querySelector(".home-v86-open");
    var model=card.querySelector(".home-v86-model");
    if(open){
      open.setAttribute("onclick","event.stopPropagation();abrirModuloV92('"+key+"')");
      open.textContent="Abrir módulo →";
    }
    if(model){
      model.setAttribute("onclick","event.stopPropagation();abrirModeloModuloV85('"+key+"')");
      model.textContent="Processo modelo";
    }

    /* Clique no corpo do card = abrir módulo vazio. */
    card.onclick=function(ev){
      if(ev.target.closest("button"))return;
      abrirModuloV92(key);
    };
  });

  document.querySelectorAll("#screenWorkspace button").forEach(function(btn){
    var txt=(btn.textContent||"").trim().toLowerCase();
    if(txt.indexOf("usar processo modelo")>=0){
      btn.setAttribute("onclick","usarProcessoModeloV92()");
    }
  });
}

document.addEventListener("DOMContentLoaded",function(){
  setTimeout(corrigirAcoesModeloV98,1100);
});
</script>
"""
core.HTML = core.HTML.replace("</body>", _model_intent_v98_js + "</body>", 1)
core.app.version="9.9"


# --- Perfil normativo Pimenta Bueno v10.0 ---
from profile_pimenta_bueno import (
    PROFILE as PB_PROFILE,
    PROCEDURES as PB_PROCEDURES,
    PLANEJAMENTO_CONTROLS as PB_PLANEJAMENTO_CONTROLS,
    classify_planning_procedure as pb_classify_planning_procedure,
)

# No perfil Pimenta Bueno, o rótulo principal é DOD; DFD continua aceito como sinônimo.
core.MODULE_AUDIT["planejamento"] = [
    ("Há DOD — Documento Oficial de Demanda?",[
        r"\bdocumento oficial de demanda\b",r"\bdod\b",
        r"\bdocumento de formalizacao da demanda\b",r"\bdfd\b"
    ]),
    ("Há Estudo Técnico Preliminar (ETP)?",[
        r"\bestudo tecnico preliminar\b",r"\betp\b"
    ]),
    ("Há Termo de Referência ou Projeto Básico?",[
        r"\btermo de referencia\b",r"\bprojeto basico\b"
    ]),
    ("Há pesquisa de preços ou orçamento estimado?",[
        r"\bpesquisa de precos\b",r"\borcamento estimado\b"
    ]),
    ("Há análise, mapa ou matriz de riscos?",[
        r"\banalise de riscos\b",r"\bmapa de riscos\b",r"\bmatriz de riscos\b"
    ]),
    ("Há autorização ou aprovação do planejamento?",[
        r"\bautorizacao do planejamento\b",r"\baprovacao do planejamento\b",
        r"\bautoriza.{0,80}prosseguimento\b"
    ])
]

# Atualiza o caso fictício de Planejamento para a terminologia municipal e informa
# o procedimento pretendido, permitindo ao classificador selecionar a matriz correta.
if "planejamento" in core.MODEL_CASES:
    core.MODEL_CASES["planejamento"]["pages"] = [
        (
            "PROCESSO DE PLANEJAMENTO DA CONTRATAÇÃO Nº 3101/2026",
            "CASO FICTÍCIO. Procedimento pretendido: Pregão eletrônico para aquisição de bens. Aquisição de notebooks para modernização de unidades administrativas municipais."
        ),
        (
            "DOCUMENTO OFICIAL DE DEMANDA — DOD",
            "A Secretaria de Origem registra a necessidade de aquisição, problema a ser resolvido, quantitativo preliminar de 60 notebooks e resultados esperados. Documento Oficial de Demanda aprovado pela chefia da unidade."
        ),
        (
            "ESTUDO TÉCNICO PRELIMINAR — ETP",
            "O Estudo Técnico Preliminar descreve a necessidade, alternativas disponíveis, requisitos mínimos, estimativa de quantitativos e justificativa da solução escolhida."
        ),
        (
            "ANÁLISE DE RISCOS",
            "A análise de riscos identifica riscos de especificação inadequada, atraso no fornecimento, variação de preços e recebimento de equipamentos em desacordo, com medidas preventivas e responsáveis."
        ),
        (
            "PESQUISA DE PREÇOS E ORÇAMENTO ESTIMADO",
            "A pesquisa de preços reúne fontes de mercado e consolida orçamento estimado para 60 unidades, com memória da metodologia utilizada e tratamento dos valores coletados."
        ),
        (
            "TERMO DE REFERÊNCIA",
            "O Termo de Referência define objeto, 60 notebooks, requisitos técnicos, prazo de entrega, critérios de aceitação, obrigações, fiscalização, forma de pagamento e condições de recebimento."
        ),
        (
            "AUTORIZAÇÃO DO PLANEJAMENTO",
            "A autoridade competente registra autorização para prosseguimento da contratação após conferência do DOD, Estudo Técnico Preliminar, pesquisa de preços, análise de riscos e Termo de Referência."
        )
    ]

_old_module_overlay_v100 = core._module_overlay
def _module_overlay_v100(pages,a,module):
    out=_old_module_overlay_v100(pages,a,module)
    if module!="planejamento":
        return out

    joined=core.norm("\n".join(p.get("text") or "" for p in pages))
    procedure=pb_classify_planning_procedure(joined)
    proc_label=PB_PROCEDURES.get(procedure,PB_PROCEDURES["outro"])

    out["normative_profile"]={
        "id":PB_PROFILE["id"],
        "label":PB_PROFILE["label"],
        "version":PB_PROFILE["version"],
        "review_notice":PB_PROFILE["review_notice"],
    }
    out["procedure"]={"key":procedure,"label":proc_label}

    matrix=out.get("module_matrix") or []
    legal=[]
    for i,control in enumerate(PB_PLANEJAMENTO_CONTROLS):
        base=matrix[i] if i<len(matrix) else {}
        applicable=(procedure=="outro" or procedure in control["applies_to"])
        found=bool(base.get("ok"))
        if not applicable:
            state="Condicional"
        elif found:
            state="Localizado"
        else:
            state="Não localizado"

        legal.append({
            "control_id":control["id"],
            "label":control["label"],
            "aliases":control.get("aliases") or [],
            "responsible":control["responsible"],
            "nature":control["nature"],
            "criticality":control["criticality"],
            "foundation":control["foundation"],
            "absence_action":control["absence_action"],
            "applicable":applicable,
            "status":state,
            "ok":found,
            "pages":(base.get("pages") or [])[:8],
            "excerpt":base.get("excerpt") or "",
        })

        if i<len(matrix):
            matrix[i]["legal_control_id"]=control["id"]
            matrix[i]["responsible"]=control["responsible"]
            matrix[i]["nature"]=control["nature"]
            matrix[i]["criticality"]=control["criticality"]
            matrix[i]["foundation"]=control["foundation"]
            matrix[i]["applicable"]=applicable
            matrix[i]["legal_status"]=state

    out["legal_matrix"]=legal

    missing=[x for x in legal if x["applicable"] and not x["ok"]]
    out["review_flags"]=[
        {
            "level":"alta" if x["criticality"]=="alta" else "media",
            "text":x["label"]+" não localizado. "+x["absence_action"]
        }
        for x in missing[:5]
    ]
    if missing:
        out["next_action"]={
            "stage":"Planejamento · Perfil Pimenta Bueno",
            "action":"Conferir ou localizar: "+missing[0]["label"]+".",
            "why":"O controle é esperado no fluxo classificado como "+proc_label+"; a ausência deve ser conferida por revisão humana."
        }
    else:
        out["next_action"]={
            "stage":"Planejamento · controles localizados",
            "action":"Confrontar a coerência entre DOD, ETP, Termo de Referência, quantitativos, pesquisa de preços e riscos antes do prosseguimento.",
            "why":"Os controles parametrizados aplicáveis ao fluxo "+proc_label+" foram localizados automaticamente."
        }

    out["conclusion"]=(
        "Perfil "+PB_PROFILE["label"]+" · "+proc_label+": o sistema localizou "
        +str(sum(1 for x in legal if x["applicable"] and x["ok"]))+" de "
        +str(sum(1 for x in legal if x["applicable"]))+
        " controles normativos/documentais aplicáveis. A classificação e a incidência permanecem sujeitas à revisão humana."
    )
    return out

core._module_overlay=_module_overlay_v100

_old_enrich_doc_refs_v100=core._enrich_doc_refs
def _enrich_doc_refs_v100(a,pages):
    out=_old_enrich_doc_refs_v100(a,pages)
    for x in out.get("legal_matrix",[]) or []:
        x["documents"]=core._page_doc_refs(pages,None,x.get("pages",[]))
    return out
core._enrich_doc_refs=_enrich_doc_refs_v100


_profile_v100_css = r"""
<style id="fiscaliza-profile-v100">
.pb-profile-chip{
  display:inline-flex;align-items:center;gap:6px;padding:5px 8px;
  border:1px solid #bddbd6;border-radius:999px;background:#eef9f7;
  color:#087b70;font-family:Calibri,"Segoe UI",Arial,sans-serif;
  font-size:16px!important;font-weight:700
}
.pb-legal-panel{margin-top:11px!important}
.pb-legal-panel .ov-panel-head h3{font-size:18px!important}
.pb-legal-panel .ov-panel-head p{font-size:16px!important;line-height:1.4!important}
.pb-legal-table-wrap{overflow-x:auto}
.pb-legal-table{
  width:100%;border-collapse:collapse;min-width:980px;
  font-family:Calibri,"Segoe UI",Arial,sans-serif
}
.pb-legal-table th{
  text-align:left;padding:9px 10px;border-bottom:2px solid #dbe5eb;
  color:#5d7183;font-size:15px!important;font-weight:700
}
.pb-legal-table td{
  vertical-align:top;padding:10px;border-bottom:1px solid #e8eef2;
  color:#304b61;font-size:16px!important;line-height:1.35!important
}
.pb-legal-table td:first-child{font-weight:700;color:#17364f}
.pb-legal-status{
  display:inline-flex;padding:4px 7px;border-radius:999px;font-size:15px!important;font-weight:700;white-space:nowrap
}
.pb-legal-status.ok{background:#eaf7f4;color:#087b70}
.pb-legal-status.warn{background:#fff2df;color:#966100}
.pb-legal-status.conditional{background:#eef2f5;color:#5c7081}
.pb-legal-source{margin-top:4px;color:#718698;font-size:14px!important}
.pb-legal-note{
  margin-top:10px;padding:9px 11px;border:1px solid #dce7ed;border-radius:9px;
  background:#f8fafb;color:#647b8d;font-size:15px!important;line-height:1.4!important
}
</style>
"""
core.HTML=core.HTML.replace("</head>",_profile_v100_css+"</head>",1)

_profile_v100_js = r"""
<script id="fiscaliza-profile-v100-js">
function legalStatusClassV100(status){
  if(status==="Localizado")return "ok";
  if(status==="Condicional")return "conditional";
  return "warn";
}
function renderPerfilNormativoV100(a){
  if(!a||a.module_key!=="planejamento"||!a.normative_profile)return;
  var hub=document.getElementById("overviewHub");
  if(!hub)return;

  var meta=hub.querySelector(".ov-meta");
  if(meta&&!meta.querySelector(".pb-profile-chip")){
    var chip=document.createElement("span");
    chip.className="pb-profile-chip";
    chip.textContent="Perfil normativo: "+a.normative_profile.label+" · "+a.normative_profile.version;
    meta.appendChild(chip);

    var proc=document.createElement("span");
    proc.className="pb-profile-chip";
    proc.textContent="Procedimento: "+((a.procedure&&a.procedure.label)||"Não classificado");
    meta.appendChild(proc);
  }

  var old=document.getElementById("legalMatrixPanelV100");
  if(old)old.remove();

  var panel=document.createElement("section");
  panel.id="legalMatrixPanelV100";
  panel.className="ov-panel pb-legal-panel";
  var rows=(a.legal_matrix||[]).map(function(r){
    var source=(r.documents&&r.documents.length)
      ? documentRefHtml(r.documents,r.pages||[])
      : '<span class="pb-legal-source">Sem evidência documental rastreável</span>';
    return '<tr>'+
      '<td>'+ovEsc(r.label)+'</td>'+
      '<td><span class="pb-legal-status '+legalStatusClassV100(r.status)+'">'+ovEsc(r.status)+'</span></td>'+
      '<td>'+ovEsc(r.responsible)+'</td>'+
      '<td>'+ovEsc(r.foundation)+'<div class="pb-legal-source">'+ovEsc(r.nature)+'</div></td>'+
      '<td>'+source+'</td>'+
    '</tr>';
  }).join("");

  panel.innerHTML=
    '<div class="ov-panel-head"><div>'+
      '<h3>Matriz normativa · Perfil Pimenta Bueno</h3>'+
      '<p>Controle esperado, responsável, fundamento parametrizado e evidência localizada nos autos.</p>'+
    '</div></div>'+
    '<div class="pb-legal-table-wrap"><table class="pb-legal-table">'+
      '<thead><tr><th>Controle</th><th>Status</th><th>Responsável</th><th>Fundamento / natureza</th><th>Evidência</th></tr></thead>'+
      '<tbody>'+rows+'</tbody></table></div>'+
    '<div class="pb-legal-note">'+ovEsc(a.normative_profile.review_notice)+'</div>';

  var grids=hub.querySelectorAll(".ov-grid");
  if(grids.length)grids[0].insertAdjacentElement("afterend",panel);
  else hub.appendChild(panel);
}

var _normalizarOverviewV100=normalizarOverviewV96;
normalizarOverviewV96=function(a){
  _normalizarOverviewV100(a);
  renderPerfilNormativoV100(a);
};
</script>
"""
core.HTML=core.HTML.replace("</body>",_profile_v100_js+"</body>",1)
core.app.version="10.0"


# --- IDs documentais do Planejamento Pimenta Bueno v10.1 ---
_old_document_marker_v101=core._document_marker
def _document_marker_v101(text):
    raw=text or ""
    lines=[re.sub(r"\s+"," ",x).strip() for x in raw.splitlines() if x.strip()]
    heads=[
        "PROCESSO DE PLANEJAMENTO DA CONTRATAÇÃO",
        "PROCESSO DE PLANEJAMENTO DA CONTRATACAO",
        "DOCUMENTO OFICIAL DE DEMANDA",
        "DOD —",
        "DOD -",
        "ANÁLISE DE RISCOS",
        "ANALISE DE RISCOS",
    ]
    for line in lines[:10]:
        up=line.upper()
        if any(h in up for h in heads) and len(line)<=180:
            return line
    return _old_document_marker_v101(text)

core._document_marker=_document_marker_v101
core.app.version="10.1"


# --- Formalização parametrizada · Pimenta Bueno v11.0 ---
from profile_pimenta_bueno import FORMALIZACAO_CONTROLS as PB_FORMALIZACAO_CONTROLS

core.MODULE_AUDIT["formalizacao"] = [
    ("Há conferência da fase preparatória ou atesto de conformidade?",[
        r"\bconferencia da fase preparatoria\b",r"\bdeclaracao de conformidade\b",
        r"\batesto de conformidade\b"
    ]),
    ("Há edital ou instrumento convocatório?",[
        r"\bedital\b",r"\binstrumento convocatorio\b"
    ]),
    ("Há controle prévio de legalidade ou parecer jurídico?",[
        r"\bcontrole previo de legalidade\b",r"\bparecer juridico\b",
        r"\bprocuradoria geral do municipio\b",r"\bpgm\b"
    ]),
    ("Há autorização de abertura ou prosseguimento?",[
        r"\bautorizacao de abertura\b",r"\bautorizacao para prosseguimento\b",
        r"\bautoriza.{0,80}(?:abertura|prosseguimento)\b"
    ]),
    ("Há registros da fase externa, proposta, julgamento e habilitação?",[
        r"\bproposta vencedora\b",r"\bata da sessao\b",r"\bjulgamento\b",
        r"\bhabilitacao\b",r"\bresultado da sessao\b"
    ]),
    ("Há manifestação da CGM anterior à homologação?",[
        r"\bmanifestacao da cgm\b",r"\bcontroladoria geral do municipio\b",
        r"\bcontrole interno\b"
    ]),
    ("Há adjudicação e homologação?",[
        r"\badjudicacao\b",r"\bhomologacao\b"
    ]),
    ("Há pedido de empenho ou Nota de Empenho?",[
        r"\bpedido de empenho\b",r"\bnota de empenho\b"
    ]),
    ("Há contrato ou instrumento equivalente?",[
        r"\bcontrato administrativo\b",r"\binstrumento equivalente\b"
    ]),
    ("Há designação de fiscal e gestor?",[
        r"\bdesignacao de fiscal\b",r"\bdesignacao de gestor\b",
        r"\bfiscal e gestor\b",r"\bportaria de designacao\b"
    ]),
    ("Há publicação ou registro da contratação?",[
        r"\bpublicacao do contrato\b",r"\bpublicacao e registro\b",
        r"\bextrato do contrato\b",r"\bregistro da contratacao\b"
    ]),
]

core.MODEL_CASES["formalizacao"]={
    "title":"Formalização da contratação",
    "pages":[
        (
            "PROCESSO DE FORMALIZAÇÃO DA CONTRATAÇÃO Nº 3202/2026",
            "CASO FICTÍCIO PARA DEMONSTRAÇÃO. Procedimento: Pregão eletrônico para aquisição de bens. Objeto: aquisição de 60 notebooks para unidades administrativas."
        ),
        (
            "DECLARAÇÃO DE CONFORMIDADE DA FASE PREPARATÓRIA — SUPEL",
            "A SUPEL registra a conferência dos documentos da fase preparatória e declara a instrução apta ao prosseguimento do Pregão Eletrônico para aquisição de bens."
        ),
        (
            "EDITAL DO PREGÃO ELETRÔNICO Nº 41/2026",
            "A SUPEL elabora o edital contendo objeto, critérios de julgamento, condições de participação, requisitos de habilitação, prazos e regras do procedimento."
        ),
        (
            "PARECER JURÍDICO — PGM",
            "A Procuradoria-Geral do Município realiza controle prévio de legalidade da minuta do edital e dos documentos da contratação, registrando conclusão para prosseguimento."
        ),
        (
            "AUTORIZAÇÃO PARA ABERTURA E PROSSEGUIMENTO",
            "A autoridade competente autoriza a abertura e o prosseguimento da fase externa após a análise jurídica e a conferência da instrução."
        ),
        (
            "PROPOSTA VENCEDORA",
            "A EMPRESA MODELO LTDA. apresenta proposta vencedora para fornecimento de 60 notebooks, com preço unitário e condições compatíveis com o edital."
        ),
        (
            "ATA DA SESSÃO, JULGAMENTO E HABILITAÇÃO",
            "A ata registra propostas, lances, classificação, julgamento, habilitação e resultado da sessão pública, indicando a empresa vencedora."
        ),
        (
            "MANIFESTAÇÃO DA CGM — CONTROLE INTERNO",
            "A Controladoria-Geral do Município registra manifestação favorável quanto à regularidade da fase externa antes da homologação."
        ),
        (
            "ADJUDICAÇÃO E HOMOLOGAÇÃO",
            "A autoridade competente adjudica o objeto e homologa o resultado após a manifestação do controle interno."
        ),
        (
            "NOTA DE EMPENHO Nº 2026NE000188",
            "É emitida Nota de Empenho referente à aquisição de 60 notebooks, vinculada ao procedimento e à proposta vencedora."
        ),
        (
            "CONTRATO ADMINISTRATIVO Nº 188/2026",
            "CONTRATANTE: MUNICÍPIO — CASO FICTÍCIO. CONTRATADA: EMPRESA MODELO LTDA. Objeto: fornecimento de 60 notebooks. O contrato estabelece prazo, obrigações, recebimento, pagamento e fiscalização."
        ),
        (
            "PORTARIA DE DESIGNAÇÃO DE FISCAL E GESTOR",
            "A autoridade competente designa fiscal e gestor para acompanhar o Contrato Administrativo nº 188/2026 e registrar ocorrências e providências."
        ),
        (
            "PUBLICAÇÃO E REGISTRO DA CONTRATAÇÃO",
            "A unidade competente registra a publicação do contrato e os dados necessários à publicidade e ao acompanhamento da contratação."
        ),
    ]
}

_old_module_overlay_v110=core._module_overlay
def _module_overlay_v110(pages,a,module):
    out=_old_module_overlay_v110(pages,a,module)
    if module!="formalizacao":
        return out

    joined=core.norm("\n".join(p.get("text") or "" for p in pages))
    procedure=pb_classify_planning_procedure(joined)
    proc_label=PB_PROCEDURES.get(procedure,PB_PROCEDURES["outro"])

    out["normative_profile"]={
        "id":PB_PROFILE["id"],
        "label":PB_PROFILE["label"],
        "version":PB_PROFILE["version"],
        "review_notice":PB_PROFILE["review_notice"],
    }
    out["procedure"]={"key":procedure,"label":proc_label}

    matrix=out.get("module_matrix") or []
    legal=[]
    for i,control in enumerate(PB_FORMALIZACAO_CONTROLS):
        base=matrix[i] if i<len(matrix) else {}
        applicable=(procedure=="outro" or procedure in control["applies_to"])
        found=bool(base.get("ok"))
        if not applicable:
            state="Condicional"
        elif found:
            state="Localizado"
        else:
            state="Não localizado"

        row={
            "control_id":control["id"],
            "label":control["label"],
            "aliases":control.get("aliases") or [],
            "responsible":control["responsible"],
            "nature":control["nature"],
            "criticality":control["criticality"],
            "foundation":control["foundation"],
            "absence_action":control["absence_action"],
            "applicable":applicable,
            "status":state,
            "ok":found,
            "pages":(base.get("pages") or [])[:8],
            "excerpt":base.get("excerpt") or "",
        }
        legal.append(row)

        if i<len(matrix):
            matrix[i]["legal_control_id"]=control["id"]
            matrix[i]["responsible"]=control["responsible"]
            matrix[i]["nature"]=control["nature"]
            matrix[i]["criticality"]=control["criticality"]
            matrix[i]["foundation"]=control["foundation"]
            matrix[i]["applicable"]=applicable
            matrix[i]["legal_status"]=state

    out["legal_matrix"]=legal
    missing=[x for x in legal if x["applicable"] and not x["ok"]]
    out["review_flags"]=[
        {
            "level":"alta" if x["criticality"]=="alta" else "media",
            "text":x["label"]+" não localizado. "+x["absence_action"]
        }
        for x in missing[:5]
    ]

    if missing:
        out["next_action"]={
            "stage":"Formalização · Perfil Pimenta Bueno",
            "action":"Conferir ou localizar: "+missing[0]["label"]+".",
            "why":"O controle é esperado no fluxo classificado como "+proc_label+"; a ausência exige conferência humana."
        }
    else:
        out["next_action"]={
            "stage":"Formalização · controles localizados",
            "action":"Conferir a sequência SUPEL → PGM → autorização → fase externa → CGM → homologação → empenho → contrato → designação → publicação.",
            "why":"Os controles normativos/documentais parametrizados para "+proc_label+" foram localizados."
        }

    out["conclusion"]=(
        "Perfil "+PB_PROFILE["label"]+" · "+proc_label+": o sistema localizou "
        +str(sum(1 for x in legal if x["applicable"] and x["ok"]))+" de "
        +str(sum(1 for x in legal if x["applicable"]))+
        " controles de formalização aplicáveis. A ordem, competência e incidência permanecem sujeitas à revisão humana."
    )
    return out

core._module_overlay=_module_overlay_v110


_old_document_marker_v110=core._document_marker
def _document_marker_v110(text):
    raw=text or ""
    lines=[re.sub(r"\s+"," ",x).strip() for x in raw.splitlines() if x.strip()]
    heads=[
        "PROCESSO DE FORMALIZAÇÃO DA CONTRATAÇÃO",
        "PROCESSO DE FORMALIZACAO DA CONTRATACAO",
        "DECLARAÇÃO DE CONFORMIDADE DA FASE PREPARATÓRIA",
        "DECLARACAO DE CONFORMIDADE DA FASE PREPARATORIA",
        "PARECER JURÍDICO",
        "PARECER JURIDICO",
        "AUTORIZAÇÃO PARA ABERTURA",
        "AUTORIZACAO PARA ABERTURA",
        "ATA DA SESSÃO, JULGAMENTO E HABILITAÇÃO",
        "ATA DA SESSAO, JULGAMENTO E HABILITACAO",
        "MANIFESTAÇÃO DA CGM",
        "MANIFESTACAO DA CGM",
        "NOTA DE EMPENHO",
        "PORTARIA DE DESIGNAÇÃO DE FISCAL E GESTOR",
        "PORTARIA DE DESIGNACAO DE FISCAL E GESTOR",
        "PUBLICAÇÃO E REGISTRO DA CONTRATAÇÃO",
        "PUBLICACAO E REGISTRO DA CONTRATACAO",
    ]
    for line in lines[:10]:
        up=line.upper()
        if any(h in up for h in heads) and len(line)<=190:
            return line
    return _old_document_marker_v110(text)

core._document_marker=_document_marker_v110


_formalizacao_v110_js=r"""
<script id="fiscaliza-formalizacao-v110-js">
/* Etapas executivas aderentes ao fluxo municipal parametrizado. */
var _overviewEtapasV110=overviewEtapasV96;
overviewEtapasV96=function(a){
  if(a&&a.module_key==="formalizacao"){
    var rows=(a.legal_matrix||[]);
    var ok=function(id){
      var r=rows.find(function(x){return x.control_id===id});
      return !!(r&&r.ok);
    };
    return [
      ["SUPEL / edital",ok("conferencia_fase_preparatoria")&&ok("edital")],
      ["PGM / autorização",ok("parecer_pgm")&&ok("autorizacao_abertura")],
      ["Fase externa",ok("fase_externa")],
      ["CGM / homologação",ok("manifestacao_cgm")&&ok("adjudicacao_homologacao")],
      ["Contrato / gestão",ok("empenho")&&ok("contrato")&&ok("designacao_fiscal_gestor")&&ok("publicacao_registro")]
    ];
  }
  return _overviewEtapasV110(a);
};

/* A matriz normativa passa a servir tanto Planejamento quanto Formalização. */
renderPerfilNormativoV100=function(a){
  if(!a||["planejamento","formalizacao"].indexOf(a.module_key)<0||!a.normative_profile)return;
  var hub=document.getElementById("overviewHub");
  if(!hub)return;

  var meta=hub.querySelector(".ov-meta");
  if(meta&&!meta.querySelector(".pb-profile-chip")){
    var chip=document.createElement("span");
    chip.className="pb-profile-chip";
    chip.textContent="Perfil normativo: "+a.normative_profile.label+" · "+a.normative_profile.version;
    meta.appendChild(chip);

    var proc=document.createElement("span");
    proc.className="pb-profile-chip";
    proc.textContent="Procedimento: "+((a.procedure&&a.procedure.label)||"Não classificado");
    meta.appendChild(proc);
  }

  var old=document.getElementById("legalMatrixPanelV100");
  if(old)old.remove();

  var panel=document.createElement("section");
  panel.id="legalMatrixPanelV100";
  panel.className="ov-panel pb-legal-panel";
  var rows=(a.legal_matrix||[]).map(function(r){
    var source=(r.documents&&r.documents.length)
      ? documentRefHtml(r.documents,r.pages||[])
      : '<span class="pb-legal-source">Sem evidência documental rastreável</span>';
    return '<tr>'+
      '<td>'+ovEsc(r.label)+'</td>'+
      '<td><span class="pb-legal-status '+legalStatusClassV100(r.status)+'">'+ovEsc(r.status)+'</span></td>'+
      '<td>'+ovEsc(r.responsible)+'</td>'+
      '<td>'+ovEsc(r.foundation)+'<div class="pb-legal-source">'+ovEsc(r.nature)+'</div></td>'+
      '<td>'+source+'</td>'+
    '</tr>';
  }).join("");

  panel.innerHTML=
    '<div class="ov-panel-head"><div>'+
      '<h3>Matriz normativa · Perfil Pimenta Bueno</h3>'+
      '<p>'+(
        a.module_key==="formalizacao"
          ?"Sequência da formalização, competência, fundamento parametrizado e evidência localizada."
          :"Controle esperado, responsável, fundamento parametrizado e evidência localizada nos autos."
      )+'</p>'+
    '</div></div>'+
    '<div class="pb-legal-table-wrap"><table class="pb-legal-table">'+
      '<thead><tr><th>Controle</th><th>Status</th><th>Responsável</th><th>Fundamento / natureza</th><th>Evidência</th></tr></thead>'+
      '<tbody>'+rows+'</tbody></table></div>'+
    '<div class="pb-legal-note">'+ovEsc(a.normative_profile.review_notice)+'</div>';

  var grids=hub.querySelectorAll(".ov-grid");
  if(grids.length)grids[0].insertAdjacentElement("afterend",panel);
  else hub.appendChild(panel);
};
</script>
"""
core.HTML=core.HTML.replace("</body>",_formalizacao_v110_js+"</body>",1)
core.app.version="11.0"


# --- Fiscalização e execução parametrizadas · Pimenta Bueno v12.0 ---
from profile_pimenta_bueno import FISCALIZACAO_CONTROLS as PB_FISCALIZACAO_CONTROLS

core.MODULE_AUDIT["fiscalizacao"] = [
    ("Há contrato ou instrumento vigente?",[
        r"\bcontrato administrativo\b",r"\bata de registro de precos\b",r"\binstrumento contratual\b"
    ]),
    ("Há designação formal de fiscal e gestor?",[
        r"\bdesignacao de fiscal\b",r"\bdesignacao de gestor\b",r"\bfiscal e gestor\b",
        r"\bportaria de designacao\b"
    ]),
    ("Há ordem de serviço/fornecimento ou autorização de execução?",[
        r"\bordem de servico\b",r"\bordem de fornecimento\b",r"\bautorizacao de execucao\b"
    ]),
    ("Há registro de acompanhamento ou relatório de fiscalização?",[
        r"\brelatorio de execucao\b",r"\brelatorio de fiscalizacao\b",
        r"\bacompanhamento da execucao\b"
    ]),
    ("Há medição ou atesto da execução?",[
        r"\bmedicao\b",r"\batesto\b",r"\bboletim de medicao\b"
    ]),
    ("Há recebimento provisório/definitivo ou aceite?",[
        r"\btermo de recebimento\b",r"\brecebimento provisori\b",
        r"\brecebimento definitiv\b",r"\baceite\b"
    ]),
    ("Há registro de ocorrência ou não conformidade?",[
        r"\bregistro de ocorrencia\b",r"\bnao conformidade\b",
        r"\bocorrencia contratual\b",r"\bpendencias? de execucao\b"
    ]),
    ("Há notificação ou comunicação à contratada?",[
        r"\bnotificacao de ocorrencia\b",r"\bnotificacao a contratada\b",
        r"\bcomunicacao a contratada\b"
    ]),
    ("Há providência, manifestação ou regularização registrada?",[
        r"\bmanifestacao da contratada\b",r"\bplano de correcao\b",
        r"\bregularizacao\b",r"\bprovidencia adotada\b"
    ]),
    ("Há encaminhamento para providência superior ou penalização quando necessário?",[
        r"\bencaminhamento para penalizacao\b",r"\bremessa a comissao de penalizacao\b",
        r"\bprovidencia superior\b"
    ]),
]

core.MODEL_CASES["fiscalizacao"]={
    "title":"Fiscalização e execução",
    "pages":[
        (
            "PROCESSO DE FISCALIZAÇÃO CONTRATUAL Nº 1001/2026",
            "CASO FICTÍCIO PARA DEMONSTRAÇÃO. Execução do Contrato nº 210/2026. Objeto: manutenção preventiva de aparelhos de ar-condicionado em unidades administrativas."
        ),
        (
            "CONTRATO ADMINISTRATIVO Nº 210/2026",
            "CONTRATANTE: MUNICÍPIO — CASO FICTÍCIO. CONTRATADA: EMPRESA MODELO LTDA. Objeto: manutenção preventiva mensal. Prazo: 12 meses. O contrato estabelece obrigações, cronograma, fiscalização, medição e recebimento."
        ),
        (
            "PORTARIA DE DESIGNAÇÃO DE FISCAL E GESTOR Nº 55/2026",
            "A autoridade competente designa FISCAL DO CONTRATO e GESTOR DO CONTRATO para acompanhar a execução do Contrato nº 210/2026, registrar ocorrências e adotar ou encaminhar providências."
        ),
        (
            "ORDEM DE SERVIÇO Nº 03/2026",
            "A unidade gestora autoriza a execução dos serviços referentes ao mês de junho de 2026, conforme cronograma e condições do Contrato nº 210/2026."
        ),
        (
            "RELATÓRIO DE FISCALIZAÇÃO E EXECUÇÃO Nº 06/2026",
            "O fiscal registra os serviços executados no período. Duas unidades apresentaram pendências de execução e três equipamentos exigiram correção antes do aceite."
        ),
        (
            "BOLETIM DE MEDIÇÃO E ATESTO Nº 06/2026",
            "A fiscalização mede e atesta apenas os serviços efetivamente executados, registrando glosa temporária dos itens ainda pendentes."
        ),
        (
            "TERMO DE RECEBIMENTO PROVISÓRIO Nº 06/2026",
            "A unidade registra recebimento provisório da parcela executada, condicionado à correção das pendências identificadas pela fiscalização."
        ),
        (
            "REGISTRO DE OCORRÊNCIA CONTRATUAL Nº 02/2026",
            "O fiscal formaliza ocorrência contratual referente às pendências de execução, identifica os itens afetados, as datas e as providências necessárias."
        ),
        (
            "NOTIFICAÇÃO À CONTRATADA Nº 02/2026",
            "A contratada é formalmente notificada sobre a ocorrência e recebe prazo para regularizar as pendências e apresentar manifestação."
        ),
        (
            "MANIFESTAÇÃO E PLANO DE CORREÇÃO DA CONTRATADA",
            "A EMPRESA MODELO LTDA. reconhece as pendências, apresenta plano de correção, reforça a equipe e informa cronograma de regularização."
        ),
        (
            "RELATÓRIO FINAL DE FISCALIZAÇÃO E REGULARIZAÇÃO",
            "A fiscalização verifica a regularização integral das pendências, registra o cumprimento das correções e recomenda o prosseguimento regular do contrato. Não há, neste momento, necessidade de encaminhamento para penalização."
        ),
    ]
}

_old_module_overlay_v120=core._module_overlay
def _module_overlay_v120(pages,a,module):
    out=_old_module_overlay_v120(pages,a,module)
    if module!="fiscalizacao":
        return out

    out["normative_profile"]={
        "id":PB_PROFILE["id"],
        "label":PB_PROFILE["label"],
        "version":PB_PROFILE["version"],
        "review_notice":PB_PROFILE["review_notice"],
    }
    out["procedure"]={"key":"execucao_contratual","label":PB_PROCEDURES["execucao_contratual"]}

    matrix=out.get("module_matrix") or []
    joined=core.norm("\n".join(p.get("text") or "" for p in pages))
    occurrence_found=bool(matrix[6].get("ok")) if len(matrix)>6 else False
    notification_found=bool(matrix[7].get("ok")) if len(matrix)>7 else False
    regularization_found=bool(matrix[8].get("ok")) if len(matrix)>8 else False
    unresolved_terms=[
        "nao regularizou","nao solucionou","descumprimento persistente",
        "permanece inadimplente","falha nao solucionada","inexecucao persistente"
    ]
    unresolved=any(t in joined for t in unresolved_terms)

    legal=[]
    for i,control in enumerate(PB_FISCALIZACAO_CONTROLS):
        base=matrix[i] if i<len(matrix) else {}
        found=bool(base.get("ok"))
        cid=control["id"]

        if cid=="ordem_execucao":
            applicable=found
            state="Localizado" if found else "Condicional"
        elif cid=="ocorrencia":
            applicable=occurrence_found
            state="Localizado" if found else "Condicional"
        elif cid=="notificacao":
            applicable=occurrence_found
            state="Localizado" if found else ("Não localizado" if applicable else "Condicional")
        elif cid=="providencia":
            applicable=occurrence_found
            state="Localizado" if found else ("Não localizado" if applicable else "Condicional")
        elif cid=="encaminhamento_penalizacao":
            applicable=bool(occurrence_found and unresolved and not regularization_found)
            state="Localizado" if found else ("Não localizado" if applicable else "Condicional")
        else:
            applicable=True
            state="Localizado" if found else "Não localizado"

        legal.append({
            "control_id":cid,
            "label":control["label"],
            "aliases":control.get("aliases") or [],
            "responsible":control["responsible"],
            "nature":control["nature"],
            "criticality":control["criticality"],
            "foundation":control["foundation"],
            "absence_action":control["absence_action"],
            "applicable":applicable,
            "status":state,
            "ok":found,
            "pages":(base.get("pages") or [])[:8],
            "excerpt":base.get("excerpt") or "",
        })

        if i<len(matrix):
            matrix[i]["legal_control_id"]=cid
            matrix[i]["responsible"]=control["responsible"]
            matrix[i]["nature"]=control["nature"]
            matrix[i]["criticality"]=control["criticality"]
            matrix[i]["foundation"]=control["foundation"]
            matrix[i]["applicable"]=applicable
            matrix[i]["legal_status"]=state

    out["legal_matrix"]=legal

    applicable_rows=[x for x in legal if x["applicable"]]
    present=[x for x in applicable_rows if x["ok"]]
    missing=[x for x in applicable_rows if not x["ok"]]
    out["metrics"]["checklist_ok"]=len(present)
    out["metrics"]["checklist_total"]=len(applicable_rows)
    out["review_flags"]=[
        {
            "level":"alta" if x["criticality"]=="alta" else "media",
            "text":x["label"]+" não localizado. "+x["absence_action"]
        }
        for x in missing[:5]
    ]

    if missing:
        out["next_action"]={
            "stage":"Fiscalização · Perfil Pimenta Bueno",
            "action":"Conferir ou localizar: "+missing[0]["label"]+".",
            "why":"O controle é aplicável à execução identificada e exige conferência humana antes da conclusão."
        }
    elif occurrence_found and regularization_found:
        out["next_action"]={
            "stage":"Execução acompanhada · ocorrência regularizada",
            "action":"Conferir o resultado da regularização, o recebimento e os reflexos na medição antes de prosseguir.",
            "why":"A ocorrência foi registrada, a contratada foi cientificada e há providência/regularização documentada; o encaminhamento sancionador permanece condicional."
        }
    else:
        out["next_action"]={
            "stage":"Execução acompanhada",
            "action":"Manter o registro periódico da execução, medições, recebimentos e ocorrências relevantes.",
            "why":"Os controles aplicáveis da fiscalização foram localizados e não há pendência automática que determine encaminhamento."
        }

    out["conclusion"]=(
        "Perfil "+PB_PROFILE["label"]+" · Execução contratual: foram localizados "
        +str(len(present))+" de "+str(len(applicable_rows))+
        " controles aplicáveis. Controles condicionais são ativados apenas quando os autos indicam a situação correspondente."
    )
    return out

core._module_overlay=_module_overlay_v120


_old_document_marker_v120=core._document_marker
def _document_marker_v120(text):
    raw=text or ""
    lines=[re.sub(r"\s+"," ",x).strip() for x in raw.splitlines() if x.strip()]
    heads=[
        "PROCESSO DE FISCALIZAÇÃO CONTRATUAL",
        "PROCESSO DE FISCALIZACAO CONTRATUAL",
        "PORTARIA DE DESIGNAÇÃO DE FISCAL E GESTOR",
        "PORTARIA DE DESIGNACAO DE FISCAL E GESTOR",
        "RELATÓRIO DE FISCALIZAÇÃO E EXECUÇÃO",
        "RELATORIO DE FISCALIZACAO E EXECUCAO",
        "BOLETIM DE MEDIÇÃO E ATESTO",
        "BOLETIM DE MEDICAO E ATESTO",
        "REGISTRO DE OCORRÊNCIA CONTRATUAL",
        "REGISTRO DE OCORRENCIA CONTRATUAL",
        "MANIFESTAÇÃO E PLANO DE CORREÇÃO DA CONTRATADA",
        "MANIFESTACAO E PLANO DE CORRECAO DA CONTRATADA",
        "RELATÓRIO FINAL DE FISCALIZAÇÃO E REGULARIZAÇÃO",
        "RELATORIO FINAL DE FISCALIZACAO E REGULARIZACAO",
    ]
    for line in lines[:10]:
        up=line.upper()
        if any(h in up for h in heads) and len(line)<=195:
            return line
    return _old_document_marker_v120(text)

core._document_marker=_document_marker_v120


_fiscalizacao_v120_js=r"""
<script id="fiscaliza-fiscalizacao-v120-js">
var _overviewEtapasV120=overviewEtapasV96;
overviewEtapasV96=function(a){
  if(a&&a.module_key==="fiscalizacao"){
    var rows=(a.legal_matrix||[]);
    var state=function(id){
      return rows.find(function(x){return x.control_id===id});
    };
    var ok=function(id){
      var r=state(id);return !!(r&&(r.ok||!r.applicable));
    };
    return [
      ["Contrato / responsáveis",ok("contrato_vigente")&&ok("designacao")],
      ["Início / execução",ok("ordem_execucao")&&ok("acompanhamento")],
      ["Medição / recebimento",ok("medicao_atesto")&&ok("recebimento")],
      ["Ocorrências / ciência",ok("ocorrencia")&&ok("notificacao")],
      ["Providências",ok("providencia")&&ok("encaminhamento_penalizacao")]
    ];
  }
  return _overviewEtapasV120(a);
};

var _renderPerfilNormativoV120=renderPerfilNormativoV100;
renderPerfilNormativoV100=function(a){
  if(!a||["planejamento","formalizacao","fiscalizacao"].indexOf(a.module_key)<0||!a.normative_profile)return;
  return _renderPerfilNormativoV120(a);
};

/* A função anterior limita os módulos aceitos; replica a renderização para Fiscalização. */
function renderFiscalizacaoNormativaV120(a){
  if(!a||a.module_key!=="fiscalizacao"||!a.normative_profile)return;
  var hub=document.getElementById("overviewHub");
  if(!hub)return;

  var meta=hub.querySelector(".ov-meta");
  if(meta&&!meta.querySelector(".pb-profile-chip")){
    var chip=document.createElement("span");
    chip.className="pb-profile-chip";
    chip.textContent="Perfil normativo: "+a.normative_profile.label+" · "+a.normative_profile.version;
    meta.appendChild(chip);
    var proc=document.createElement("span");
    proc.className="pb-profile-chip";
    proc.textContent="Procedimento: "+((a.procedure&&a.procedure.label)||"Execução contratual");
    meta.appendChild(proc);
  }

  var old=document.getElementById("legalMatrixPanelV100");
  if(old)old.remove();

  var panel=document.createElement("section");
  panel.id="legalMatrixPanelV100";
  panel.className="ov-panel pb-legal-panel";
  var rows=(a.legal_matrix||[]).map(function(r){
    var source=(r.documents&&r.documents.length)
      ? documentRefHtml(r.documents,r.pages||[])
      : '<span class="pb-legal-source">Sem evidência documental rastreável</span>';
    return '<tr>'+
      '<td>'+ovEsc(r.label)+'</td>'+
      '<td><span class="pb-legal-status '+legalStatusClassV100(r.status)+'">'+ovEsc(r.status)+'</span></td>'+
      '<td>'+ovEsc(r.responsible)+'</td>'+
      '<td>'+ovEsc(r.foundation)+'<div class="pb-legal-source">'+ovEsc(r.nature)+'</div></td>'+
      '<td>'+source+'</td>'+
    '</tr>';
  }).join("");

  panel.innerHTML=
    '<div class="ov-panel-head"><div>'+
      '<h3>Matriz normativa · Perfil Pimenta Bueno</h3>'+
      '<p>Execução, fiscalização, recebimento, ocorrências e providências com incidência condicional quando cabível.</p>'+
    '</div></div>'+
    '<div class="pb-legal-table-wrap"><table class="pb-legal-table">'+
      '<thead><tr><th>Controle</th><th>Status</th><th>Responsável</th><th>Fundamento / natureza</th><th>Evidência</th></tr></thead>'+
      '<tbody>'+rows+'</tbody></table></div>'+
    '<div class="pb-legal-note">'+ovEsc(a.normative_profile.review_notice)+'</div>';

  var grids=hub.querySelectorAll(".ov-grid");
  if(grids.length)grids[0].insertAdjacentElement("afterend",panel);
  else hub.appendChild(panel);
}

var _normalizarOverviewV120=normalizarOverviewV96;
normalizarOverviewV96=function(a){
  _normalizarOverviewV120(a);
  if(a&&a.module_key==="fiscalizacao")renderFiscalizacaoNormativaV120(a);
};
</script>
"""
core.HTML=core.HTML.replace("</body>",_fiscalizacao_v120_js+"</body>",1)
core.app.version="12.0"


# --- Fiscalização: substituição efetiva da matriz legada v12.1 ---
_old_module_overlay_v121=core._module_overlay
def _module_overlay_v121(pages,a,module):
    out=_old_module_overlay_v121(pages,a,module)
    if module!="fiscalizacao":
        return out

    contract=_fisc_marker_pages(pages,[r"^contrato administrativo\b",r"^ata de registro de precos\b"])
    designation=_fisc_marker_pages(pages,[r"portaria.{0,70}designa[cç][aã]o.{0,50}(?:fiscal|gestor)",r"designa[cç][aã]o de fiscal"])
    service_order=_fisc_marker_pages(pages,[r"^ordem de servi[cç]o\b",r"^ordem de fornecimento\b",r"autoriza[cç][aã]o de execu[cç][aã]o"])
    execution=_fisc_marker_pages(pages,[r"relat[oó]rio de fiscaliza[cç][aã]o e execu[cç][aã]o",r"relat[oó]rio de execu[cç][aã]o"])
    measurement=_fisc_marker_pages(pages,[r"boletim de medi[cç][aã]o",r"\batesto\b"])
    receipt=_fisc_marker_pages(pages,[r"termo de recebimento",r"recebimento provis[oó]rio",r"recebimento definitivo"])
    occurrence=_fisc_marker_pages(pages,[r"registro de ocorr[eê]ncia contratual",r"registro de ocorr[eê]ncia",r"n[aã]o conformidade"])
    notification=_fisc_marker_pages(pages,[r"notifica[cç][aã]o [àa] contratada",r"notifica[cç][aã]o de ocorr[eê]ncia",r"comunica[cç][aã]o [àa] contratada"])
    manifestation=_fisc_marker_pages(pages,[r"manifesta[cç][aã]o e plano de corre[cç][aã]o",r"manifesta[cç][aã]o da contratada",r"plano de corre[cç][aã]o"])
    final_report=_fisc_marker_pages(pages,[r"relat[oó]rio final de fiscaliza[cç][aã]o"])
    penalty=_fisc_marker_pages(pages,[r"encaminhamento para penaliza[cç][aã]o",r"remessa [àa] comiss[aã]o de penaliza[cç][aã]o"])

    regularization=sorted(set(manifestation+final_report))
    specs=[
        ("Há contrato ou instrumento vigente?","Contrato / instrumento vigente",contract),
        ("Há designação formal de fiscal e gestor?","Designação formal de fiscal e gestor",designation),
        ("Há ordem de serviço/fornecimento ou autorização de execução?","Ordem de serviço / fornecimento ou autorização de execução",service_order),
        ("Há registro de acompanhamento ou relatório de fiscalização?","Registro de acompanhamento / relatório de fiscalização",execution),
        ("Há medição ou atesto da execução?","Medição / atesto da execução",measurement),
        ("Há recebimento provisório/definitivo ou aceite?","Recebimento provisório/definitivo ou aceite",receipt),
        ("Há registro de ocorrência ou não conformidade?","Registro de ocorrência / não conformidade",occurrence),
        ("Há notificação ou comunicação à contratada?","Notificação / comunicação à contratada",notification),
        ("Há providência, manifestação ou regularização registrada?","Providência, manifestação ou regularização registrada",regularization),
        ("Há encaminhamento para providência superior ou penalização quando necessário?","Encaminhamento para providência superior / penalização",penalty),
    ]

    matrix=[]
    for question,label,pgs in specs:
        matrix.append({
            "question":question,
            "answer":"Localizado" if pgs else "Não identificado",
            "ok":bool(pgs),
            "pages":pgs[:8],
            "label":label,
            "excerpt":_fisc_body(pages,pgs[0]) if pgs else "",
        })

    out["module_matrix"]=matrix
    out["process_checklist"]=[{"label":x["label"],"ok":x["ok"],"pages":x["pages"]} for x in matrix]
    out["module_summary"]=[
        {"label":x["label"],"ok":x["ok"],"value":"Localizado" if x["ok"] else "Conferir"}
        for x in matrix[:4]
    ]

    timeline_specs=[
        ("Contrato",contract),
        ("Designação do fiscal e gestor",designation),
        ("Ordem de serviço",service_order),
        ("Acompanhamento da execução",execution),
        ("Medição / atesto",measurement),
        ("Recebimento",receipt),
        ("Registro de ocorrência",occurrence),
        ("Notificação à contratada",notification),
        ("Manifestação / regularização",manifestation),
        ("Relatório final",final_report),
        ("Encaminhamento para penalização",penalty),
    ]
    out["module_timeline"]=[
        {"label":label,"pages":pgs[:4]}
        for label,pgs in timeline_specs if pgs
    ]

    evidence_specs=[
        ("Responsáveis pela fiscalização",designation),
        ("Execução registrada",execution),
        ("Medição e atesto",measurement),
        ("Recebimento",receipt),
        ("Ocorrência formalizada",occurrence),
        ("Ciência da contratada",notification),
        ("Providência / regularização",regularization),
    ]
    out["module_evidence"]=[
        {"label":label,"page":pgs[0],"text":_fisc_body(pages,pgs[0])}
        for label,pgs in evidence_specs if pgs
    ]

    # Reaplica a camada normativa sobre a matriz efetivamente usada.
    out["normative_profile"]={
        "id":PB_PROFILE["id"],
        "label":PB_PROFILE["label"],
        "version":PB_PROFILE["version"],
        "review_notice":PB_PROFILE["review_notice"],
    }
    out["procedure"]={"key":"execucao_contratual","label":PB_PROCEDURES["execucao_contratual"]}

    joined=core.norm("\n".join(p.get("text") or "" for p in pages))
    occurrence_found=bool(occurrence)
    regularization_found=bool(regularization)
    unresolved_terms=[
        "nao regularizou","nao solucionou","descumprimento persistente",
        "permanece inadimplente","falha nao solucionada","inexecucao persistente"
    ]
    unresolved=any(t in joined for t in unresolved_terms)

    legal=[]
    for i,control in enumerate(PB_FISCALIZACAO_CONTROLS):
        base=matrix[i]
        found=bool(base["ok"])
        cid=control["id"]

        if cid=="ordem_execucao":
            applicable=found
            state="Localizado" if found else "Condicional"
        elif cid=="ocorrencia":
            applicable=occurrence_found
            state="Localizado" if found else "Condicional"
        elif cid in ("notificacao","providencia"):
            applicable=occurrence_found
            state="Localizado" if found else ("Não localizado" if applicable else "Condicional")
        elif cid=="encaminhamento_penalizacao":
            applicable=bool(occurrence_found and unresolved and not regularization_found)
            state="Localizado" if found else ("Não localizado" if applicable else "Condicional")
        else:
            applicable=True
            state="Localizado" if found else "Não localizado"

        row={
            "control_id":cid,
            "label":control["label"],
            "aliases":control.get("aliases") or [],
            "responsible":control["responsible"],
            "nature":control["nature"],
            "criticality":control["criticality"],
            "foundation":control["foundation"],
            "absence_action":control["absence_action"],
            "applicable":applicable,
            "status":state,
            "ok":found,
            "pages":base["pages"],
            "excerpt":base["excerpt"],
        }
        legal.append(row)
        base.update({
            "legal_control_id":cid,
            "responsible":control["responsible"],
            "nature":control["nature"],
            "criticality":control["criticality"],
            "foundation":control["foundation"],
            "applicable":applicable,
            "legal_status":state,
        })

    out["legal_matrix"]=legal
    applicable_rows=[x for x in legal if x["applicable"]]
    present=[x for x in applicable_rows if x["ok"]]
    missing=[x for x in applicable_rows if not x["ok"]]
    out["review_flags"]=[
        {
            "level":"alta" if x["criticality"]=="alta" else "media",
            "text":x["label"]+" não localizado. "+x["absence_action"]
        }
        for x in missing[:5]
    ]
    out["pending"]=[x["text"] for x in out["review_flags"]]
    out["metrics"]["checklist_ok"]=len(present)
    out["metrics"]["checklist_total"]=len(applicable_rows)
    out["metrics"]["evidence_points"]=len(out["module_evidence"])

    if missing:
        out["next_action"]={
            "stage":"Fiscalização · Perfil Pimenta Bueno",
            "action":"Conferir ou localizar: "+missing[0]["label"]+".",
            "why":"O controle é aplicável à execução identificada e exige conferência humana."
        }
    elif occurrence_found and regularization_found:
        out["next_action"]={
            "stage":"Execução acompanhada · ocorrência regularizada",
            "action":"Conferir o resultado da regularização, o recebimento e os reflexos na medição antes de prosseguir.",
            "why":"A ocorrência foi formalizada, houve ciência da contratada e há providência/regularização documentada. O encaminhamento para penalização permanece condicional."
        }
    else:
        out["next_action"]={
            "stage":"Execução acompanhada",
            "action":"Manter registros periódicos da execução, medições, recebimentos e ocorrências relevantes.",
            "why":"Os controles aplicáveis foram localizados sem pendência automática de encaminhamento."
        }

    out["conclusion"]=(
        "Perfil "+PB_PROFILE["label"]+" · Execução contratual: foram localizados "
        +str(len(present))+" de "+str(len(applicable_rows))+
        " controles aplicáveis. Os controles condicionais somente são exigidos quando os autos demonstram a situação correspondente."
    )
    return out

core._module_overlay=_module_overlay_v121
core.app.version="12.1"


# --- Alterações contratuais parametrizadas · Pimenta Bueno v13.0 ---
from profile_pimenta_bueno import (
    ALTERATION_TYPES as PB_ALTERATION_TYPES,
    ALTERACOES_CONTROLS as PB_ALTERACOES_CONTROLS,
    classify_alteration_type as pb_classify_alteration_type,
)

core.MODEL_CASES["alteracoes"]={
    "title":"Alterações contratuais",
    "pages":[
        (
            "PROCESSO DE ALTERAÇÃO CONTRATUAL Nº 3404/2026",
            "CASO FICTÍCIO PARA DEMONSTRAÇÃO. Pedido de restabelecimento do equilíbrio econômico-financeiro relacionado ao Contrato nº 260/2026."
        ),
        (
            "CONTRATO ADMINISTRATIVO Nº 260/2026",
            "Objeto: fornecimento continuado de gêneros alimentícios. O contrato registra preços, vigência, condições de alteração e matriz de riscos da contratação."
        ),
        (
            "PEDIDO DE REEQUILÍBRIO ECONÔMICO-FINANCEIRO",
            "A EMPRESA MODELO LTDA. requer restabelecimento do equilíbrio econômico-financeiro, descreve aumento extraordinário e superveniente do custo de insumo essencial e apresenta documentação comprobatória."
        ),
        (
            "RELATÓRIO DA FISCALIZAÇÃO SOBRE A EXECUÇÃO",
            "A fiscalização informa que o contrato permanece em execução regular, registra o histórico de fornecimento e relata os efeitos do evento alegado sobre a execução."
        ),
        (
            "NOTA DE INTERESSE PÚBLICO E VANTAJOSIDADE",
            "A unidade gestora examina a continuidade do fornecimento, a necessidade administrativa e a vantajosidade de manter a contratação caso o pedido seja comprovado."
        ),
        (
            "PLANILHA E MEMÓRIA DE CÁLCULO DO REEQUILÍBRIO",
            "A requerente apresenta memória de cálculo com preços originários, custos atuais, documentos fiscais e impacto econômico. A unidade técnica realiza conferência dos cálculos."
        ),
        (
            "NOTA TÉCNICA — FATO SUPERVENIENTE E NEXO ECONÔMICO",
            "A área técnica examina o fato superveniente alegado, a documentação temporal, a variação extraordinária e o nexo entre o evento e o aumento dos encargos contratuais."
        ),
        (
            "MATRIZ DE RISCOS — CONFERÊNCIA DA ALOCAÇÃO",
            "A unidade confronta o evento alegado com a matriz de riscos do contrato e registra que o evento analisado não foi alocado à contratada nas condições descritas no pedido."
        ),
        (
            "DECLARAÇÃO DE DOTAÇÃO E DISPONIBILIDADE ORÇAMENTÁRIA",
            "A unidade orçamentária registra disponibilidade suficiente para suportar eventual impacto financeiro decorrente do pedido, caso deferido."
        ),
        (
            "PARECER TÉCNICO CONCLUSIVO",
            "A unidade gestora consolida a análise técnica, a memória de cálculo, a prova do fato superveniente, o nexo econômico e a vantajosidade, recomendando decisão motivada."
        ),
        (
            "PARECER JURÍDICO Nº 61/2026",
            "A PGM examina a hipótese de restabelecimento do equilíbrio econômico-financeiro à luz da Lei nº 14.133/2021, da documentação produzida e da matriz de riscos."
        ),
        (
            "DECISÃO ADMINISTRATIVA SOBRE O REEQUILÍBRIO",
            "A autoridade competente decide motivadamente sobre o pedido após examinar o contrato, as provas, os cálculos, as manifestações técnica e jurídica e a disponibilidade orçamentária."
        ),
        (
            "TERMO ADITIVO Nº 02/2026",
            "O termo aditivo formaliza o resultado econômico aprovado, identifica o fundamento do restabelecimento e registra os efeitos financeiros conforme a decisão administrativa."
        ),
    ]
}

def _alt_marker_pages_v130(pages,patterns):
    regs=[re.compile(p,re.I) for p in patterns]
    hits=[]
    for p in pages:
        marker=core.norm(p.get("source_document_id") or "")
        head=core.norm((p.get("text") or "")[:500])
        full=core.norm(p.get("text") or "")
        if any(rx.search(marker) or rx.search(head) or rx.search(full) for rx in regs):
            hits.append(p.get("page"))
    return sorted(set(x for x in hits if x))

def _alt_excerpt_v130(pages,page_no,limit=360):
    for p in pages:
        if p.get("page")==page_no:
            raw=p.get("text") or ""
            lines=[re.sub(r"\s+"," ",x).strip() for x in raw.splitlines() if x.strip()]
            marker=core.norm(p.get("source_document_id") or "")
            clean=[]
            for i,line in enumerate(lines):
                if i==0 and marker and core.norm(line)==marker:
                    continue
                if "FISCALIZA.AI" in line.upper() and "PROCESSO MODELO" in line.upper():
                    continue
                clean.append(line)
            return core.clip(" ".join(clean),limit)
    return ""

_ALT_PATTERNS_V130 = {
    "contrato_vigente":[r"^contrato administrativo\b",r"\bcontrato vigente\b"],
    "pedido_justificativa":[r"pedido de reequilibrio",r"pedido e justificativa",r"requer.{0,80}reequilibrio",r"requer.{0,80}alteracao"],
    "relatorio_execucao":[r"relatorio da fiscalizacao",r"relatorio de execucao"],
    "vantajosidade":[r"vantajosidade",r"interesse publico"],
    "memoria_calculo":[r"memoria de calculo",r"planilha.{0,60}reequilibrio",r"comprovacao economica"],
    "indice_data_base":[r"indice.{0,60}data-base",r"data-base.{0,60}reajuste",r"interregno"],
    "repactuacao_custos":[r"planilha de custos",r"convencao coletiva",r"acordo coletivo",r"sentenca normativa"],
    "fato_superveniente_nexo":[r"fato superveniente",r"nexo economico",r"evento superveniente"],
    "matriz_riscos":[r"matriz de riscos",r"alocacao de riscos"],
    "limites_quantitativos":[r"limite.{0,40}25",r"acrescimo.{0,60}supressao",r"alteracao quantitativa"],
    "dotacao":[r"dotacao",r"disponibilidade orcamentaria"],
    "analise_tecnica":[r"parecer tecnico",r"nota tecnica",r"analise tecnica"],
    "parecer_juridico":[r"parecer juridico",r"\bpgm\b",r"procuradoria geral do municipio"],
    "decisao":[r"decisao administrativa",r"decide.{0,100}(?:pedido|alteracao|reequilibrio|reajuste|repactuacao|prorrogacao)"],
    "formalizacao":[r"termo aditivo",r"\bapostila\b",r"\bapostilamento\b"],
}

_old_module_overlay_v130=core._module_overlay
def _module_overlay_v130(pages,a,module):
    out=_old_module_overlay_v130(pages,a,module)
    if module!="alteracoes":
        return out

    joined=core.norm("\n".join(p.get("text") or "" for p in pages))
    alteration_type=pb_classify_alteration_type(joined)
    type_label=PB_ALTERATION_TYPES.get(alteration_type,PB_ALTERATION_TYPES["outra"])

    rows=[]
    legal=[]
    for control in PB_ALTERACOES_CONTROLS:
        cid=control["id"]
        pgs=_alt_marker_pages_v130(pages,_ALT_PATTERNS_V130.get(cid,[]))
        found=bool(pgs)
        applicable=alteration_type in control["applies_to"]

        # Matriz de riscos é juridicamente relevante quando existir/alocar o evento,
        # mas sua ausência não deve ser convertida automaticamente em irregularidade.
        if cid=="matriz_riscos" and alteration_type=="reequilibrio" and not found:
            applicable=False

        state=("Localizado" if found else ("Não localizado" if applicable else "Condicional"))
        ex=_alt_excerpt_v130(pages,pgs[0]) if pgs else ""

        row={
            "question":"Há "+control["label"].lower()+"?",
            "answer":state,
            "ok":found,
            "pages":pgs[:8],
            "label":control["label"],
            "excerpt":ex,
            "legal_control_id":cid,
            "responsible":control["responsible"],
            "nature":control["nature"],
            "criticality":control["criticality"],
            "foundation":control["foundation"],
            "applicable":applicable,
            "legal_status":state,
        }
        rows.append(row)

        legal.append({
            "control_id":cid,
            "label":control["label"],
            "responsible":control["responsible"],
            "nature":control["nature"],
            "criticality":control["criticality"],
            "foundation":control["foundation"],
            "absence_action":control["absence_action"],
            "applicable":applicable,
            "status":state,
            "ok":found,
            "pages":pgs[:8],
            "excerpt":ex,
        })

    out["module_matrix"]=rows
    out["legal_matrix"]=legal
    out["process_checklist"]=[{
        "label":x["label"],"ok":x["ok"],"pages":x["pages"]
    } for x in rows if x["applicable"]]
    out["module_summary"]=[
        {
            "label":x["label"],
            "ok":x["ok"] if x["applicable"] else True,
            "value":x["legal_status"]
        }
        for x in rows if x["applicable"]
    ][:4]

    out["normative_profile"]={
        "id":PB_PROFILE["id"],
        "label":PB_PROFILE["label"],
        "version":PB_PROFILE["version"],
        "review_notice":PB_PROFILE["review_notice"],
    }
    out["procedure"]={"key":alteration_type,"label":type_label}

    # Cronologia somente das peças pertinentes ao tipo classificado.
    out["module_timeline"]=[
        {"label":x["label"],"pages":x["pages"][:4]}
        for x in rows if x["applicable"] and x["ok"]
    ]
    out["module_timeline"].sort(key=lambda x:(x["pages"][0] if x.get("pages") else 999999))

    out["module_evidence"]=[
        {
            "label":x["label"],
            "page":x["pages"][0],
            "text":x["excerpt"]
        }
        for x in rows if x["applicable"] and x["ok"] and x["pages"]
    ]

    applicable_rows=[x for x in legal if x["applicable"]]
    present=[x for x in applicable_rows if x["ok"]]
    missing=[x for x in applicable_rows if not x["ok"]]
    out["review_flags"]=[
        {
            "level":"alta" if x["criticality"]=="alta" else "media",
            "text":x["label"]+" não localizado. "+x["absence_action"]
        }
        for x in missing[:5]
    ]
    out["pending"]=[x["text"] for x in out["review_flags"]]
    out["metrics"]["checklist_ok"]=len(present)
    out["metrics"]["checklist_total"]=len(applicable_rows)
    out["metrics"]["evidence_points"]=len(out["module_evidence"])

    if missing:
        out["next_action"]={
            "stage":"Alterações · "+type_label,
            "action":"Conferir ou localizar: "+missing[0]["label"]+".",
            "why":"O controle é aplicável ao tipo de alteração identificado; a ausência requer revisão humana antes da conclusão."
        }
    else:
        out["next_action"]={
            "stage":"Alterações · "+type_label+" instruído",
            "action":"Revisar a coerência entre fundamento, provas, cálculos, manifestações e instrumento de formalização antes da assinatura.",
            "why":"Todos os controles parametrizados aplicáveis ao tipo "+type_label+" foram localizados."
        }

    out["conclusion"]=(
        "Perfil "+PB_PROFILE["label"]+" · "+type_label+": foram localizados "
        +str(len(present))+" de "+str(len(applicable_rows))+
        " controles aplicáveis. Controles de outros tipos de alteração permanecem condicionais e não geram pendência automática."
    )
    return out

core._module_overlay=_module_overlay_v130


_old_document_marker_v130=core._document_marker
def _document_marker_v130(text):
    raw=text or ""
    lines=[re.sub(r"\s+"," ",x).strip() for x in raw.splitlines() if x.strip()]
    heads=[
        "PROCESSO DE ALTERAÇÃO CONTRATUAL",
        "PROCESSO DE ALTERACAO CONTRATUAL",
        "PEDIDO DE REEQUILÍBRIO ECONÔMICO-FINANCEIRO",
        "PEDIDO DE REEQUILIBRIO ECONOMICO-FINANCEIRO",
        "RELATÓRIO DA FISCALIZAÇÃO SOBRE A EXECUÇÃO",
        "RELATORIO DA FISCALIZACAO SOBRE A EXECUCAO",
        "NOTA DE INTERESSE PÚBLICO E VANTAJOSIDADE",
        "NOTA DE INTERESSE PUBLICO E VANTAJOSIDADE",
        "PLANILHA E MEMÓRIA DE CÁLCULO DO REEQUILÍBRIO",
        "PLANILHA E MEMORIA DE CALCULO DO REEQUILIBRIO",
        "NOTA TÉCNICA — FATO SUPERVENIENTE E NEXO ECONÔMICO",
        "NOTA TECNICA - FATO SUPERVENIENTE E NEXO ECONOMICO",
        "MATRIZ DE RISCOS — CONFERÊNCIA DA ALOCAÇÃO",
        "MATRIZ DE RISCOS - CONFERENCIA DA ALOCACAO",
        "DECLARAÇÃO DE DOTAÇÃO E DISPONIBILIDADE ORÇAMENTÁRIA",
        "DECLARACAO DE DOTACAO E DISPONIBILIDADE ORCAMENTARIA",
        "PARECER TÉCNICO CONCLUSIVO",
        "PARECER TECNICO CONCLUSIVO",
        "DECISÃO ADMINISTRATIVA SOBRE O REEQUILÍBRIO",
        "DECISAO ADMINISTRATIVA SOBRE O REEQUILIBRIO",
    ]
    for line in lines[:10]:
        up=line.upper()
        if any(h in up for h in heads) and len(line)<=200:
            return line
    return _old_document_marker_v130(text)

core._document_marker=_document_marker_v130


_alteracoes_v130_js=r"""
<script id="fiscaliza-alteracoes-v130-js">
var _overviewEtapasV130=overviewEtapasV96;
overviewEtapasV96=function(a){
  if(a&&a.module_key==="alteracoes"){
    var rows=(a.legal_matrix||[]);
    var good=function(id){
      var r=rows.find(function(x){return x.control_id===id});
      return !!(r&&(!r.applicable||r.ok));
    };
    var type=(a.procedure&&a.procedure.key)||"outra";
    if(type==="reequilibrio"){
      return [
        ["Contrato / pedido",good("contrato_vigente")&&good("pedido_justificativa")],
        ["Execução / interesse",good("relatorio_execucao")&&good("vantajosidade")],
        ["Prova / cálculos",good("memoria_calculo")&&good("fato_superveniente_nexo")&&good("matriz_riscos")],
        ["Análises / orçamento",good("dotacao")&&good("analise_tecnica")&&good("parecer_juridico")],
        ["Decisão / aditivo",good("decisao")&&good("formalizacao")]
      ];
    }
    return [
      ["Contrato / pedido",good("contrato_vigente")&&good("pedido_justificativa")],
      ["Fundamento",true],
      ["Cálculos / suporte",good("memoria_calculo")],
      ["Análises",good("analise_tecnica")&&good("parecer_juridico")],
      ["Decisão / formalização",good("decisao")&&good("formalizacao")]
    ];
  }
  return _overviewEtapasV130(a);
};

function renderAlteracoesNormativaV130(a){
  if(!a||a.module_key!=="alteracoes"||!a.normative_profile)return;
  var hub=document.getElementById("overviewHub");
  if(!hub)return;

  var meta=hub.querySelector(".ov-meta");
  if(meta&&!meta.querySelector(".pb-profile-chip")){
    var chip=document.createElement("span");
    chip.className="pb-profile-chip";
    chip.textContent="Perfil normativo: "+a.normative_profile.label+" · "+a.normative_profile.version;
    meta.appendChild(chip);

    var proc=document.createElement("span");
    proc.className="pb-profile-chip";
    proc.textContent="Tipo de alteração: "+((a.procedure&&a.procedure.label)||"Não classificado");
    meta.appendChild(proc);
  }

  var old=document.getElementById("legalMatrixPanelV100");
  if(old)old.remove();

  var panel=document.createElement("section");
  panel.id="legalMatrixPanelV100";
  panel.className="ov-panel pb-legal-panel";

  var rows=(a.legal_matrix||[]).filter(function(r){return r.applicable}).map(function(r){
    var source=(r.documents&&r.documents.length)
      ? documentRefHtml(r.documents,r.pages||[])
      : '<span class="pb-legal-source">Sem evidência documental rastreável</span>';
    return '<tr>'+
      '<td>'+ovEsc(r.label)+'</td>'+
      '<td><span class="pb-legal-status '+legalStatusClassV100(r.status)+'">'+ovEsc(r.status)+'</span></td>'+
      '<td>'+ovEsc(r.responsible)+'</td>'+
      '<td>'+ovEsc(r.foundation)+'<div class="pb-legal-source">'+ovEsc(r.nature)+'</div></td>'+
      '<td>'+source+'</td>'+
    '</tr>';
  }).join("");

  panel.innerHTML=
    '<div class="ov-panel-head"><div>'+
      '<h3>Matriz normativa · Alterações contratuais</h3>'+
      '<p>O sistema classifica primeiro o tipo da alteração e só então ativa os controles correspondentes.</p>'+
    '</div></div>'+
    '<div class="pb-legal-table-wrap"><table class="pb-legal-table">'+
      '<thead><tr><th>Controle</th><th>Status</th><th>Responsável</th><th>Fundamento / natureza</th><th>Evidência</th></tr></thead>'+
      '<tbody>'+rows+'</tbody></table></div>'+
    '<div class="pb-legal-note">'+ovEsc(a.normative_profile.review_notice)+'</div>';

  var grids=hub.querySelectorAll(".ov-grid");
  if(grids.length)grids[0].insertAdjacentElement("afterend",panel);
  else hub.appendChild(panel);
}

var _normalizarOverviewV130=normalizarOverviewV96;
normalizarOverviewV96=function(a){
  _normalizarOverviewV130(a);
  if(a&&a.module_key==="alteracoes")renderAlteracoesNormativaV130(a);
};
</script>
"""
core.HTML=core.HTML.replace("</body>",_alteracoes_v130_js+"</body>",1)
core.app.version="13.0"
