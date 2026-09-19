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
