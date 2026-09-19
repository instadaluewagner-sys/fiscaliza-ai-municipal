const form=document.getElementById("form");
const startState=document.getElementById("startState");
const processWorkspace=document.getElementById("processWorkspace");
const viewer=document.getElementById("pdfViewer");
const viewerEmpty=document.getElementById("viewerEmpty");
const viewerTitle=document.getElementById("viewerTitle");
const viewerPage=document.getElementById("viewerPage");

let currentAnalysisId=null;
let currentAnalysis=null;
let currentMeta=null;
let currentDraft=null;

function esc(value){
  return String(value==null?"":value)
    .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
    .replaceAll('"',"&quot;").replaceAll("'","&#039;");
}
function statusLabel(status){
  return {located:"Localizado",not_found:"Não localizado",not_applicable:"Não aplicável",inconclusive:"Inconclusivo"}[status]||status;
}
function statusClass(status){
  if(status==="located")return "ok";
  if(status==="not_found")return "warn";
  return "neutral";
}
function typeLabel(type){
  const labels={
    movimentacao_1doc:"Movimentação 1Doc",pedido_reequilibrio:"Pedido de reequilíbrio",
    ata_registro_precos:"Ata de Registro de Preços",pregao:"Pregão",edital:"Edital",
    termo_referencia:"Termo de Referência",contrato:"Contrato",empenho:"Nota de Empenho",
    ordem_fornecimento:"Ordem de Fornecimento",oficio:"Ofício",relatorio_tecnico:"Relatório técnico",
    relatorio_conclusivo:"Relatório conclusivo",notificacao:"Notificação",intimacao:"Intimação",
    defesa:"Defesa",parecer_juridico:"Parecer jurídico",parecer_tecnico:"Parecer técnico",
    recurso:"Recurso",decisao:"Decisão / despacho",unclassified:"Não classificado"
  };
  return labels[type]||type;
}
function evidenceCategoryLabel(category){
  return {fact:"Fato",procedural:"Processual",defense:"Defesa",legal:"Jurídico",decision:"Decisão"}[category]||"Evidência";
}
function pendingKindLabel(kind){
  return {missing:"Pendência",review:"Conferência",next_step:"Próximo passo"}[kind]||kind;
}
function formatIsoDate(value){
  if(!value)return "Data não identificada";
  const m=String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m?m[3]+"/"+m[2]+"/"+m[1]:value;
}
function profileValue(v){
  if(Array.isArray(v))return v.length?esc(v.join(", ")):"Não identificado com segurança";
  return v?esc(v):"Não identificado com segurança";
}
function profileSourceHtml(p,key){
  const src=(p.sources||{})[key];
  if(!src||!src.document_id)return '<span class="profile-source missing">Sem fonte segura</span>';
  return '<button class="profile-source" onclick="openDocument(\''+esc(src.document_id)+'\','+Number(src.page)+')">'+esc(src.document_id)+' · p. '+esc(src.page)+'</button>';
}
function profileConflictHtml(p,key){
  const values=(p.conflicts||{})[key]||[];
  const refs=(p.conflict_sources||{})[key]||[];
  if(!values.length)return "";
  return '<div class="profile-conflict"><strong>Divergência nos autos</strong>'+
    values.map(function(value,i){
      const src=refs[i];
      const source=src&&src.document_id
        ? '<button onclick="openDocument(\''+esc(src.document_id)+'\','+Number(src.page)+')">'+esc(src.document_id)+' · p. '+esc(src.page)+'</button>'
        : '';
      return '<span>'+esc(value)+source+'</span>';
    }).join("")+'</div>';
}
function profileCard(p,label,key,value){
  const conflict=((p.conflicts||{})[key]||[]).length;
  return '<div class="profile-card '+(conflict?'has-conflict':'')+'"><small>'+esc(label)+'</small><b>'+profileValue(value)+'</b>'+profileSourceHtml(p,key)+profileConflictHtml(p,key)+'</div>';
}
function docSourceButton(documentId,page,label){
  if(!documentId)return '<span class="neutral">Sem fonte</span>';
  return '<button class="profile-source" onclick="openDocument(\''+esc(documentId)+'\','+Number(page||1)+')">'+esc(label||documentId+' · p. '+page)+'</button>';
}
function stageSourcesHtml(stage){
  const sources=(stage&&stage.sources)||[];
  if(!sources.length)return '<span class="neutral">Base documental ainda não consolidada.</span>';
  return sources.map(function(src){
    return docSourceButton(src.document_id,src.page,src.document_id+' · p. '+src.page);
  }).join("");
}
function countByStatus(checks,status){
  return (checks||[]).filter(function(x){return x.status===status}).length;
}
function meaningfulPending(pending){
  return (pending||[]).filter(function(x){return x.kind==="missing"||x.kind==="review"});
}

function showTab(tab){
  if(!currentAnalysis)return;
  document.querySelectorAll(".tab-panel").forEach(function(el){el.classList.toggle("active",el.id==="tab-"+tab)});
  document.querySelectorAll(".process-tab,.side-item").forEach(function(el){el.classList.toggle("active",el.dataset.tab===tab)});
  if(tab==="drafts"&&!currentDraft)loadCompatibleDraft(false);
  window.scrollTo({top:64,behavior:"smooth"});
}

async function deleteCurrentAnalysis(resetUi=true){
  const id=currentAnalysisId;
  currentAnalysisId=null;currentAnalysis=null;currentMeta=null;currentDraft=null;
  if(id){
    try{await fetch("/api/v8/analysis/"+encodeURIComponent(id),{method:"DELETE"});}catch(e){}
  }
  if(resetUi){
    form.reset();
    processWorkspace.classList.add("hidden");
    startState.classList.remove("hidden");
    viewer.src="about:blank";
    viewer.classList.add("hidden");
    viewerEmpty.classList.remove("hidden");
    viewerEmpty.innerHTML='<div class="viewer-placeholder"><strong>PDF original</strong><span>Clique em um DOC-ID, evidência, evento ou fonte para abrir exatamente na página citada.</span></div>';
    viewerTitle.textContent="Selecione um documento";
    viewerPage.textContent="—";
    document.querySelectorAll(".process-tab,.side-item").forEach(function(el){el.classList.toggle("active",el.dataset.tab==="overview")});
  }
}
function downloadAuditReport(format){
  if(!currentAnalysisId)return;
  const ext=format==="json"?"json":"pdf";
  const a=document.createElement("a");
  a.href="/api/v8/report/"+encodeURIComponent(currentAnalysisId)+"."+ext;
  document.body.appendChild(a);a.click();a.remove();
}
async function openDocument(documentId,page){
  if(!currentAnalysisId||!documentId)return;
  try{
    const r=await fetch("/api/v8/document/"+encodeURIComponent(currentAnalysisId)+"/"+encodeURIComponent(documentId));
    const d=await r.json();
    if(!r.ok)throw new Error(d.detail||"Documento indisponível");
    const doc=d.document;
    const targetPage=Number(page||doc.page_start);
    const base=(d.viewer_url||"").split("#")[0];
    if(!base)throw new Error("PDF original não disponível");
    viewer.src=base+"#page="+encodeURIComponent(targetPage)+"&zoom=page-width";
    viewer.classList.remove("hidden");viewerEmpty.classList.add("hidden");
    viewerTitle.textContent=doc.title||documentId;
    viewerPage.textContent=doc.id+" · p. "+targetPage;
  }catch(err){
    viewer.classList.add("hidden");viewerEmpty.classList.remove("hidden");
    viewerEmpty.innerHTML='<div class="viewer-placeholder"><strong>Não foi possível abrir a fonte</strong><span>'+esc(err.message)+'</span></div>';
  }
}

function renderProcessHeader(a,meta){
  const p=a.profile||{},stage=a.stage||{};
  const number=p.process_number||p.origin_process||"Processo sem número identificado";
  const subtitle=[
    p.company||"Interessado não identificado",
    p.contrato?("Contrato "+p.contrato):null
  ].filter(Boolean).join(" · ");
  document.getElementById("processNumber").textContent=number;
  document.getElementById("processSubtitle").textContent=subtitle;
  document.getElementById("stageBadge").textContent=stage.label||"Estágio não definido";
  document.getElementById("processMeta").innerHTML=[
    (meta.pages||0)+" páginas",
    (a.documents||[]).length+" peças segmentadas",
    (a.evidence||[]).length+" evidências",
    (meta.ocr_pages||0)+" páginas OCR"
  ].map(function(x){return '<span>'+esc(x)+'</span>';}).join("");
}

function renderQuality(a){
  const warnings=a.warnings||[];
  const el=document.getElementById("qualityAlert");
  el.innerHTML=warnings.length
    ? '<div class="quality-alert"><b>Conferência de integridade necessária</b>'+warnings.map(function(w){return '<span>• '+esc(w)+'</span>';}).join("")+'</div>'
    : '';
}

function renderOverview(a,meta){
  const p=a.profile||{},stage=a.stage||{},checks=a.checklist||[],evidence=a.evidence||[],pending=a.pending_items||[],timeline=a.timeline||[];
  const realPending=meaningfulPending(pending);
  const located=countByStatus(checks,"located");
  const applicable=checks.filter(function(x){return x.status!=="not_applicable"}).length;
  const completeness=applicable?Math.round(located*100/applicable):0;

  const priorityEvidence=evidence.slice(0,3).map(function(e,i){
    return '<div class="overview-row" onclick="openDocument(\''+esc(e.document_id)+'\','+Number(e.page)+')" role="button" tabindex="0"><i>'+(i+1)+'</i><div><b>'+esc(e.fact)+'</b><span>'+esc(evidenceCategoryLabel(e.category))+' · '+esc(e.document_id)+' · p. '+esc(e.page)+'</span></div><em>'+Math.round((e.confidence||0)*100)+'%</em></div>';
  }).join("")||'<div class="empty-box">Nenhuma evidência prioritária consolidada.</div>';

  const priorityPending=realPending.slice(0,3).map(function(x){
    return '<div class="overview-row warn"><i>!</i><div><b>'+esc(x.label)+'</b><span>'+esc(x.reason)+'</span></div><em>'+esc(pendingKindLabel(x.kind))+'</em></div>';
  }).join("")||'<div class="overview-row"><i>✓</i><div><b>Sem pendência crítica automática</b><span>Conferir os autos antes do próximo ato.</span></div><em>Revisão humana</em></div>';

  const recentTimeline=timeline.slice(-4).map(function(t){
    return '<div class="overview-row" onclick="openDocument(\''+esc(t.document_id)+'\','+Number(t.page)+')" role="button"><i>•</i><div><b>'+esc(t.label)+'</b><span>'+esc(formatIsoDate(t.date))+' · '+esc(t.document_id)+' · p. '+esc(t.page)+'</span></div></div>';
  }).join("")||'<div class="empty-box">Cronologia ainda não consolidada.</div>';

  const identity=[
    ["Empresa",p.company||"Não identificada"],
    ["Pregão",p.pregao||"Não identificado"],
    ["Ata",p.ata||"Não identificada / conferir aplicabilidade"],
    ["Contrato",p.contrato||"Não identificado"],
    ["Quantidade",p.quantity||"Não identificada com segurança"]
  ].map(function(x){return '<div class="overview-row"><i>•</i><div><b>'+esc(x[0])+'</b><span>'+esc(x[1])+'</span></div></div>';}).join("");

  document.getElementById("overviewContent").innerHTML=
    '<div class="overview-stack">'+
      '<div class="overview-hero">'+
        '<div class="summary-card"><small>Situação processual</small><strong>'+esc(stage.label||"Estágio não definido")+'</strong><p>'+esc(stage.rationale||"")+'</p><div class="overview-actions">'+stageSourcesHtml(stage)+'</div></div>'+
        '<div class="next-action-card"><small>Próxima providência</small><strong>'+esc(stage.next_action||"Revisar os autos")+'</strong><p>Minuta sugerida: '+esc(stage.suggested_draft||"—")+'</p><div class="overview-actions"><button class="small-btn primary" onclick="showTab(\'drafts\')">Abrir minuta</button><button class="small-btn" onclick="showTab(\'pending\')">Ver pendências</button></div></div>'+
      '</div>'+
      '<div class="overview-kpis">'+
        '<div class="kpi"><small>Peças</small><strong>'+esc((a.documents||[]).length)+'</strong></div>'+
        '<div class="kpi"><small>Evidências</small><strong>'+esc(evidence.length)+'</strong></div>'+
        '<div class="kpi"><small>Pendências / revisão</small><strong>'+esc(realPending.length)+'</strong></div>'+
        '<div class="kpi"><small>Dossiê aplicável</small><strong>'+esc(completeness)+'%</strong></div>'+
      '</div>'+
      '<div class="overview-two">'+
        '<div class="overview-card"><small>Contratação</small><h3>Identificação essencial</h3><div class="overview-list">'+identity+'</div><div class="overview-actions"><button class="small-btn" onclick="showTab(\'documents\')">Ver dossiê completo</button></div></div>'+
        '<div class="overview-card"><small>Controle</small><h3>Pontos que pedem atenção</h3><div class="overview-list">'+priorityPending+'</div></div>'+
      '</div>'+
      '<div class="overview-two">'+
        '<div class="overview-card"><small>Base probatória</small><h3>Evidências prioritárias</h3><div class="overview-list">'+priorityEvidence+'</div><div class="overview-actions"><button class="small-btn" onclick="showTab(\'evidence\')">Abrir evidências</button></div></div>'+
        '<div class="overview-card"><small>Cronologia</small><h3>Últimos marcos relevantes</h3><div class="overview-list">'+recentTimeline+'</div><div class="overview-actions"><button class="small-btn" onclick="showTab(\'timeline\')">Ver cronologia</button></div></div>'+
      '</div>'+
      '<div class="overview-card"><small>Minuta assistida</small><h3 id="overviewDraftTitle">Documento compatível com a fase atual</h3><p id="overviewDraftPreview">Carregando uma prévia segura da minuta sugerida...</p><div class="overview-actions"><button class="small-btn primary" onclick="showTab(\'drafts\')">Abrir minuta completa</button></div></div>'+
    '</div>';

  loadOverviewDraftPreview();
}

function renderDocuments(a){
  const p=a.profile||{},docs=a.documents||[];
  document.getElementById("documentCount").textContent=docs.length;
  const profile=
    '<div class="section-head compact-head"><div><span class="eyebrow">Identificação da contratação</span><h2>Dados estruturados</h2><p>Cada valor só é exibido com sua fonte documental ou indicação explícita de ausência.</p></div></div>'+
    '<div class="profile-grid">'+
      profileCard(p,"Processo de penalização","process_number",p.process_number)+
      profileCard(p,"Processo / protocolo de origem","origin_process",p.origin_process)+
      profileCard(p,"Pregão","pregao",p.pregao)+
      profileCard(p,"Ata de Registro de Preços","ata",p.ata)+
      profileCard(p,"Contrato","contrato",p.contrato)+
      profileCard(p,"Nota(s) de Empenho","empenhos",p.empenhos||[])+
      profileCard(p,"Empresa / interessada","company",p.company)+
      profileCard(p,"CNPJ","cnpj",p.cnpj)+
      profileCard(p,"Objeto","object_description",p.object_description)+
      profileCard(p,"Quantidade","quantity",p.quantity)+
    '</div>';

  const list=docs.map(function(d){
    return '<div class="doc-row" tabindex="0" role="button" onclick="openDocument(\''+esc(d.id)+'\','+Number(d.page_start)+')" onkeydown="if(event.key===\'Enter\')this.click()">'+
      '<span class="doc-id">'+esc(d.id)+'</span>'+
      '<div class="doc-main"><b>'+esc(d.title||typeLabel(d.type))+'</b><span>p. '+esc(d.page_start)+(d.page_end!==d.page_start?"–"+esc(d.page_end):"")+' · confiança '+Math.round((d.confidence||0)*100)+'%</span></div>'+
      '<span class="doc-type">'+esc(typeLabel(d.type))+'</span></div>';
  }).join("")||'<div class="empty-box">Nenhuma peça segmentada.</div>';
  document.getElementById("documentsContent").innerHTML=profile+'<div class="section-head compact-head second"><div><span class="eyebrow">Peças dos autos</span><h2>Documentos segmentados</h2></div></div><div class="doc-list">'+list+'</div>';
}

function renderEvidence(a){
  const evidence=a.evidence||[],checks=a.checklist||[];
  document.getElementById("evidenceCount").textContent=evidence.length;
  const evidenceHtml=evidence.length?evidence.map(function(e,i){
    return '<div class="evidence-row" tabindex="0" role="button" onclick="openDocument(\''+esc(e.document_id)+'\','+Number(e.page)+')" onkeydown="if(event.key===\'Enter\')this.click()">'+
      '<span class="evidence-num">'+(i+1)+'</span><div><span class="evidence-kind">'+esc(evidenceCategoryLabel(e.category))+'</span><b>'+esc(e.fact)+'</b><p>'+esc(e.excerpt)+'</p></div>'+
      '<div class="evidence-meta"><span class="evidence-source">'+esc(e.document_id)+' · p. '+esc(e.page)+'</span><span>'+Math.round((e.confidence||0)*100)+'%</span></div></div>';
  }).join(""):'<div class="empty-box">Nenhuma evidência prioritária consolidada.</div>';
  const checksHtml=checks.map(function(x){
    return '<div class="check-card"><small>'+esc(x.label)+'</small><b class="'+statusClass(x.status)+'">'+esc(statusLabel(x.status))+'</b><p>'+esc(x.reason)+'</p></div>';
  }).join("");
  document.getElementById("evidenceContent").innerHTML=
    '<div class="evidence-list">'+evidenceHtml+'</div>'+
    '<div class="section-head compact-head second"><div><span class="eyebrow">Aplicabilidade</span><h2>Checklist processual</h2><p>Localizado, ausente, não aplicável e inconclusivo não são tratados como sinônimos.</p></div></div>'+
    '<div class="check-grid">'+checksHtml+'</div>';
}

function renderTimeline(a){
  const timeline=a.timeline||[];
  const html=timeline.length?timeline.map(function(t){
    const source=t.date_source==="envelope"?"data do envelope":(t.date_source==="document"?"data do documento":"sem data confirmada");
    return '<button class="timeline-event" onclick="openDocument(\''+esc(t.document_id)+'\','+Number(t.page)+')">'+
      '<span class="timeline-dot"></span><div><small>'+esc(formatIsoDate(t.date))+' · '+esc(source)+'</small><b>'+esc(t.label)+'</b><span>'+esc(t.document_id)+' · p. '+esc(t.page)+'</span></div></button>';
  }).join(""):'<div class="empty-box">Nenhum marco cronológico consolidado.</div>';
  document.getElementById("timelineContent").innerHTML='<div class="timeline-list">'+html+'</div>';
}

function renderPending(a){
  const pending=a.pending_items||[];
  document.getElementById("pendingCount").textContent=meaningfulPending(pending).length;
  const html=pending.length?pending.map(function(x){
    const cls=x.kind==="missing"?"warn":(x.kind==="next_step"?"ok":"neutral");
    return '<div class="pending-row"><small>'+esc(pendingKindLabel(x.kind))+' · '+esc(x.severity)+'</small><b class="'+cls+'">'+esc(x.label)+'</b><p>'+esc(x.reason)+'</p></div>';
  }).join(""):'<div class="empty-box">Nenhuma pendência atual identificada.</div>';
  document.getElementById("pendingContent").innerHTML='<div class="pending-list">'+html+'</div>';
}

function renderDraftPlaceholder(a){
  const stage=a.stage||{};
  document.getElementById("draftContent").innerHTML=
    '<div class="draft-empty"><strong>'+esc(stage.suggested_draft||"Minuta compatível")+'</strong><span>O documento será gerado somente para a fase identificada. Dados ausentes permanecem como campos para conferência, sem serem inventados.</span><button class="primary-btn" style="width:auto" onclick="loadCompatibleDraft(true)">Gerar minuta</button></div>';
}

function renderReport(a,meta){
  const p=a.profile||{};
  document.getElementById("reportContent").innerHTML=
    '<div class="report-options">'+
      '<div class="report-card"><small>Documento de trabalho</small><strong>Relatório auditável em PDF</strong><p>Inclui fontes digitais, estágio, identificação, pendências, evidências, cronologia e checklist.</p><button class="primary-btn" style="width:auto" onclick="downloadAuditReport(\'pdf\')">Baixar PDF</button></div>'+
      '<div class="report-card"><small>Dados estruturados</small><strong>Exportação JSON</strong><p>Preserva o resultado completo da análise para auditoria técnica ou integração futura.</p><button class="primary-btn" style="width:auto" onclick="downloadAuditReport(\'json\')">Baixar JSON</button></div>'+
    '</div>'+
    '<div class="overview-card" style="margin-top:8px"><small>Resumo da análise</small><h3>'+esc(p.process_number||p.origin_process||"Processo sem número")+'</h3><p>'+esc((a.stage||{}).label||"")+' · '+esc(meta.pages||0)+' páginas · '+esc((a.documents||[]).length)+' peças segmentadas · '+esc((a.evidence||[]).length)+' evidências prioritárias.</p></div>';
}

async function fetchCompatibleDraft(){
  if(currentDraft)return currentDraft;
  if(!currentAnalysisId)throw new Error("Análise indisponível.");
  const r=await fetch("/api/v8/draft/"+encodeURIComponent(currentAnalysisId));
  const d=await r.json();
  if(!r.ok)throw new Error(d.detail||"Minuta indisponível");
  currentDraft=d;
  return d;
}
async function loadOverviewDraftPreview(){
  const title=document.getElementById("overviewDraftTitle");
  const preview=document.getElementById("overviewDraftPreview");
  if(!title||!preview)return;
  try{
    const d=await fetchCompatibleDraft();
    title.textContent=d.title||"Minuta compatível";
    const compact=String(d.text||"").replace(/\s+/g," ").trim();
    preview.textContent=compact.length>620?compact.slice(0,620)+"…":compact;
  }catch(err){
    preview.textContent="A minuta não pôde ser gerada automaticamente: "+err.message;
  }
}
async function loadCompatibleDraft(focusTab=true){
  if(focusTab)showTab("drafts");
  const target=document.getElementById("draftContent");
  target.innerHTML='<div class="loading">Gerando minuta compatível com o estágio…</div>';
  try{
    const d=await fetchCompatibleDraft();
    const sourceRefs=d.source_refs||[];
    const sources=sourceRefs.length
      ? sourceRefs.map(function(src){return '<button class="draft-source" onclick="openDocument(\''+esc(src.document_id)+'\','+Number(src.page)+')">'+esc(src.document_id)+' · p. '+esc(src.page)+'</button>';}).join("")
      : (d.source_document_ids||[]).map(function(id){return '<button class="draft-source" onclick="openDocument(\''+esc(id)+'\')">'+esc(id)+'</button>';}).join("");
    const warnings=(d.warnings||[]).map(function(w){return '<div class="draft-warning">• '+esc(w)+'</div>';}).join("");
    target.innerHTML='<div class="draft-panel"><div class="draft-head"><div><small>Minuta compatível com a fase atual</small><strong>'+esc(d.title)+'</strong></div><div class="draft-tools"><button class="ghost-btn" onclick="copyDraft()">Copiar</button><button class="ghost-btn" onclick="downloadDraft()">Baixar .txt</button></div></div>'+
      '<pre id="draftText" class="draft-text">'+esc(d.text)+'</pre><div class="draft-foot"><b>Fontes utilizadas como referência</b><div class="draft-sources">'+(sources||'<span class="neutral">Sem fonte destacada</span>')+'</div>'+warnings+'</div></div>';
  }catch(err){target.innerHTML='<div class="error">'+esc(err.message)+'</div>';}
}
async function copyDraft(){
  const el=document.getElementById("draftText");if(!el)return;
  try{await navigator.clipboard.writeText(el.textContent||"");}
  catch(e){const ta=document.createElement("textarea");ta.value=el.textContent||"";document.body.appendChild(ta);ta.select();document.execCommand("copy");ta.remove();}
}
function downloadDraft(){
  const el=document.getElementById("draftText");if(!el)return;
  const blob=new Blob([el.textContent||""],{type:"text/plain;charset=utf-8"});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="fiscaliza-v8-minuta.txt";a.click();URL.revokeObjectURL(a.href);
}

function renderAnalysis(a,meta){
  currentAnalysis=a;currentMeta=meta;currentDraft=null;
  renderProcessHeader(a,meta);
  renderQuality(a);
  renderOverview(a,meta);
  renderDocuments(a);
  renderEvidence(a);
  renderTimeline(a);
  renderPending(a);
  renderDraftPlaceholder(a);
  renderReport(a,meta);
  showTab("overview");
}

async function runAnalysis(files){
  if(!files||!files.length)return;
  if(currentAnalysisId)await deleteCurrentAnalysis(false);

  const fd=new FormData();
  Array.from(files).forEach(function(file){fd.append("files",file)});
  startState.classList.add("hidden");
  processWorkspace.classList.remove("hidden");
  document.getElementById("overviewContent").innerHTML='<div class="loading">Analisando os autos, segmentando documentos e consolidando a fase processual…</div>';
  document.querySelectorAll(".tab-panel").forEach(function(el){el.classList.toggle("active",el.id==="tab-overview")});
  viewer.classList.add("hidden");viewerEmpty.classList.remove("hidden");
  viewerEmpty.innerHTML='<div class="viewer-placeholder"><strong>Análise em andamento</strong><span>O documento original será liberado para consulta assim que a segmentação terminar.</span></div>';

  try{
    const r=await fetch("/api/v8/analyze?module=penalizacao",{method:"POST",body:fd});
    const d=await r.json();
    if(!r.ok)throw new Error(d.detail||"Falha na análise");
    currentAnalysisId=d.analysis_id;
    renderAnalysis(d.analysis,d);
    viewerEmpty.innerHTML='<div class="viewer-placeholder"><strong>PDF original</strong><span>Clique em uma fonte para abrir o documento exatamente na página citada.</span></div>';
  }catch(err){
    startState.classList.remove("hidden");processWorkspace.classList.add("hidden");
    alert("Não foi possível analisar o processo: "+err.message);
  }
}

async function analyzeDemoProcess(){
  const button=document.querySelector(".demo-btn");
  const previous=button?button.textContent:"";
  if(button){button.disabled=true;button.textContent="Preparando processo modelo…";}
  try{
    const r=await fetch("/api/v8/demo.pdf");
    if(!r.ok)throw new Error("Não foi possível carregar o processo modelo.");
    const blob=await r.blob();
    const file=new File([blob],"fiscaliza-v8-processo-modelo.pdf",{type:"application/pdf"});
    await runAnalysis([file]);
  }catch(err){
    alert(err.message);
  }finally{
    if(button){button.disabled=false;button.textContent=previous||"Usar processo modelo";}
  }
}

form.addEventListener("submit",async function(e){
  e.preventDefault();
  const input=document.getElementById("files");
  if(!input.files.length)return;
  await runAnalysis(input.files);
});
