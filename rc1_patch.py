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
