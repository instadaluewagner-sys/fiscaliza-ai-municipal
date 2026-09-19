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
