const form=document.getElementById("form");
const out=document.getElementById("out");
const workspace=document.getElementById("workspace");
const viewer=document.getElementById("pdfViewer");
const viewerEmpty=document.getElementById("viewerEmpty");
const viewerTitle=document.getElementById("viewerTitle");
const viewerPage=document.getElementById("viewerPage");

let currentAnalysisId=null;
let currentAnalysis=null;

function esc(value){
  return String(value==null?"":value)
    .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
    .replaceAll('"',"&quot;").replaceAll("'","&#039;");
}
function statusLabel(status){
  return {
    located:"Localizado",
    not_found:"Não localizado",
    not_applicable:"Não aplicável",
    inconclusive:"Inconclusivo"
  }[status]||status;
}
function statusClass(status){
  if(status==="located")return "ok";
  if(status==="not_found")return "warn";
  return "neutral";
}
function typeLabel(type){
  const labels={
    movimentacao_1doc:"Movimentação 1Doc",
    pedido_reequilibrio:"Pedido de reequilíbrio",
    ata_registro_precos:"Ata de Registro de Preços",
    pregao:"Pregão",
    edital:"Edital",
    termo_referencia:"Termo de Referência",
    contrato:"Contrato",
    empenho:"Nota de Empenho",
    ordem_fornecimento:"Ordem de Fornecimento",
    oficio:"Ofício",
    relatorio_tecnico:"Relatório técnico",
    relatorio_conclusivo:"Relatório conclusivo",
    notificacao:"Notificação",
    intimacao:"Intimação",
    defesa:"Defesa",
    parecer_juridico:"Parecer jurídico",
    parecer_tecnico:"Parecer técnico",
    recurso:"Recurso",
    decisao:"Decisão / despacho",
    unclassified:"Não classificado"
  };
  return labels[type]||type;
}
function profileValue(v){return v?esc(v):"Não identificado com segurança";}
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
    }).join("")+
  '</div>';
}
function profileCard(p,label,key,value){
  return '<div class="profile-card '+(((p.conflicts||{})[key]||[]).length?'has-conflict':'')+'"><small>'+esc(label)+'</small><b>'+profileValue(value)+'</b>'+profileSourceHtml(p,key)+profileConflictHtml(p,key)+'</div>';
}

function formatIsoDate(value){
  if(!value)return "Data não identificada";
  const m=String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m?m[3]+"/"+m[2]+"/"+m[1]:value;
}
function pendingKindLabel(kind){
  return {missing:"Pendência",review:"Conferência",next_step:"Próximo passo"}[kind]||kind;
}
function evidenceCategoryLabel(category){
  return {fact:"Fato",procedural:"Processual",defense:"Defesa",legal:"Jurídico",decision:"Decisão"}[category]||"Evidência";
}

async function openDocument(documentId,page){
  if(!currentAnalysisId)return;
  try{
    const r=await fetch("/api/v8/document/"+encodeURIComponent(currentAnalysisId)+"/"+encodeURIComponent(documentId));
    const d=await r.json();
    if(!r.ok)throw new Error(d.detail||"Documento indisponível");
    const doc=d.document;
    const targetPage=page||doc.page_start;
    const base=(d.viewer_url||"").split("#")[0];
    if(!base)throw new Error("PDF original não disponível");
    viewer.src=base+"#page="+encodeURIComponent(targetPage)+"&zoom=page-width";
    viewer.classList.remove("hidden");
    viewerEmpty.classList.add("hidden");
    viewerTitle.textContent=doc.title||documentId;
    viewerPage.textContent="DOC "+doc.id+" · p. "+targetPage;
  }catch(err){
    viewer.classList.add("hidden");
    viewerEmpty.classList.remove("hidden");
    viewerEmpty.textContent=err.message;
  }
}


async function loadCompatibleDraft(){
  if(!currentAnalysisId)return;
  let target=document.getElementById("stageDraft");
  if(!target){
    target=document.createElement("div");
    target.id="stageDraft";
    const stage=document.querySelector(".stage-card");
    if(stage)stage.insertAdjacentElement("afterend",target);
  }
  target.innerHTML='<div class="draft-panel"><div class="loading">Gerando minuta compatível com o estágio…</div></div>';
  try{
    const r=await fetch("/api/v8/draft/"+encodeURIComponent(currentAnalysisId));
    const d=await r.json();
    if(!r.ok)throw new Error(d.detail||"Minuta indisponível");
    const sources=(d.source_document_ids||[]).map(function(id){
      return '<button class="draft-source" onclick="openDocument(\''+esc(id)+'\')">'+esc(id)+'</button>';
    }).join("");
    const warnings=(d.warnings||[]).map(function(w){return '<div class="draft-warning">• '+esc(w)+'</div>';}).join("");
    target.innerHTML=
      '<div class="draft-panel">'+
        '<div class="draft-head"><div><small>Minuta compatível com a fase atual</small><strong>'+esc(d.title)+'</strong></div>'+
        '<div class="draft-tools"><button class="secondary-btn" onclick="copyDraft()">Copiar</button><button class="secondary-btn" onclick="downloadDraft()">Baixar .txt</button></div></div>'+
        '<pre id="draftText" class="draft-text">'+esc(d.text)+'</pre>'+
        '<div class="draft-foot"><b>Fontes utilizadas como referência</b><div class="draft-sources">'+(sources||'<span class="neutral">Sem fonte destacada</span>')+'</div>'+warnings+'</div>'+
      '</div>';
  }catch(err){
    target.innerHTML='<div class="error">'+esc(err.message)+'</div>';
  }
}
async function copyDraft(){
  const el=document.getElementById("draftText");
  if(!el)return;
  const text=el.textContent||"";
  try{await navigator.clipboard.writeText(text)}
  catch(e){
    const ta=document.createElement("textarea");
    ta.value=text;document.body.appendChild(ta);ta.select();document.execCommand("copy");ta.remove();
  }
}
function downloadDraft(){
  const el=document.getElementById("draftText");
  if(!el)return;
  const blob=new Blob([el.textContent||""],{type:"text/plain;charset=utf-8"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download="fiscaliza-v8-minuta.txt";
  a.click();
  URL.revokeObjectURL(a.href);
}

function renderAnalysis(a,meta){
  currentAnalysis=a;
  const p=a.profile||{};
  const docs=a.documents||[];
  const evidence=a.evidence||[];
  const checks=a.checklist||[];
  const timeline=a.timeline||[];
  const pending=a.pending_items||[];
  const stage=a.stage||{};

  const docsHtml=docs.map(function(d){
    return '<div class="doc-row" tabindex="0" role="button" onclick="openDocument(\''+esc(d.id)+'\','+Number(d.page_start)+')" onkeydown="if(event.key===\'Enter\')this.click()">'+
      '<span class="doc-id">'+esc(d.id)+'</span>'+
      '<div class="doc-main"><b>'+esc(d.title||typeLabel(d.type))+'</b><span>p. '+esc(d.page_start)+(d.page_end!==d.page_start?"–"+esc(d.page_end):"")+' · confiança '+Math.round((d.confidence||0)*100)+'%</span></div>'+
      '<span class="doc-type">'+esc(typeLabel(d.type))+'</span>'+
    '</div>';
  }).join("");

  const evidenceHtml=evidence.length?evidence.map(function(e,i){
    return '<div class="evidence-row" tabindex="0" role="button" onclick="openDocument(\''+esc(e.document_id)+'\','+Number(e.page)+')" onkeydown="if(event.key===\'Enter\')this.click()">'+
      '<span class="evidence-num">'+(i+1)+'</span>'+
      '<div><span class="evidence-kind">'+esc(evidenceCategoryLabel(e.category))+'</span><b>'+esc(e.fact)+'</b><p>'+esc(e.excerpt)+'</p></div>'+
      '<div class="evidence-meta"><span class="evidence-source">'+esc(e.document_id)+' · p. '+esc(e.page)+'</span><span>'+Math.round((e.confidence||0)*100)+'%</span></div>'+
    '</div>';
  }).join(""):'<div class="check-card"><small>Evidências</small><b class="neutral">Nenhuma evidência prioritária extraída nesta versão.</b></div>';

  const checksHtml=checks.map(function(x){
    return '<div class="check-card"><small>'+esc(x.label)+'</small><b class="'+statusClass(x.status)+'">'+esc(statusLabel(x.status))+'</b><p>'+esc(x.reason)+'</p></div>';
  }).join("");

  const pendingHtml=pending.length?pending.map(function(x){
    const cls=x.kind==="missing"?"warn":(x.kind==="next_step"?"ok":"neutral");
    return '<div class="pending-row"><div><small>'+esc(pendingKindLabel(x.kind))+' · '+esc(x.severity)+'</small><b class="'+cls+'">'+esc(x.label)+'</b><p>'+esc(x.reason)+'</p></div></div>';
  }).join(""):'<div class="check-card"><small>Pendências</small><b class="ok">Nenhuma pendência atual identificada.</b></div>';

  const timelineHtml=timeline.length?timeline.map(function(t){
    const dateLabel=formatIsoDate(t.date);
    const sourceLabel=t.date_source==="envelope"?"data do envelope":(t.date_source==="document"?"data do documento":"sem data");
    return '<button class="timeline-event" onclick="openDocument(\''+esc(t.document_id)+'\','+Number(t.page)+')">'+
      '<span class="timeline-dot"></span>'+
      '<div><small>'+esc(dateLabel)+' · '+esc(sourceLabel)+'</small><b>'+esc(t.label)+'</b><span>'+esc(t.document_id)+' · p. '+esc(t.page)+'</span></div>'+
    '</button>';
  }).join(""):'<div class="check-card"><small>Cronologia</small><b class="neutral">Nenhum marco cronológico consolidado.</b></div>';

  out.innerHTML=
    '<div class="summary-head"><div><small>Análise V8</small><h2>'+profileValue(p.process_number||p.origin_process)+'</h2>'+
    '<div class="process-meta"><span class="chip">'+esc(meta.pages||0)+' páginas</span><span class="chip">'+esc(docs.length)+' peças segmentadas</span><span class="chip">'+esc(meta.ocr_pages||0)+' OCR</span></div></div>'+
    '<span class="stage-badge">'+esc(stage.label||"Estágio não definido")+'</span></div>'+
    '<div class="stage-card"><small>Leitura processual</small><strong>'+esc(stage.rationale||"")+'</strong><p>'+esc(stage.next_action||"")+'</p>'+
    '<div class="next-grid"><div class="next-box"><b>Próximo ato</b><span>'+esc(stage.next_action||"—")+'</span></div><div class="next-box"><b>Minuta compatível</b><span>'+esc(stage.suggested_draft||"—")+'</span></div></div>'+
    '<div class="stage-actions"><button onclick="loadCompatibleDraft()">Gerar minuta compatível</button></div></div>'+
    '<div id="stageDraft"></div>'+
    '<div class="section-title"><h3>Pendências e próximo passo</h3><span>Ausência ≠ não aplicabilidade</span></div><div class="pending-list">'+pendingHtml+'</div>'+
    '<div class="section-title"><h3>Cronologia essencial</h3><span>Clique para abrir a fonte</span></div><div class="timeline-list">'+timelineHtml+'</div>'+
    '<div class="section-title"><h3>Identificação e contratação</h3><span>Cada dado aponta para DOC-ID + página</span></div>'+
    '<div class="profile-grid">'+
      profileCard(p,"Processo de penalização","process_number",p.process_number)+
      profileCard(p,"Processo / protocolo de origem","origin_process",p.origin_process)+
      profileCard(p,"Pregão","pregao",p.pregao)+
      profileCard(p,"Ata de Registro de Preços","ata",p.ata)+
      profileCard(p,"Contrato","contrato",p.contrato)+
      profileCard(p,"Nota(s) de Empenho","empenhos",(p.empenhos||[]).join(", "))+ 
      profileCard(p,"Empresa / interessada","company",p.company)+
      profileCard(p,"CNPJ","cnpj",p.cnpj)+
      profileCard(p,"Objeto","object_description",p.object_description)+
      profileCard(p,"Quantidade","quantity",p.quantity)+
    '</div>'+
    '<div class="section-title"><h3>Documentos autônomos</h3><span>Clique para abrir a fonte</span></div><div class="doc-list">'+docsHtml+'</div>'+
    '<div class="section-title"><h3>Evidências prioritárias</h3><span>DOC-ID + página exata</span></div><div class="evidence-list">'+evidenceHtml+'</div>'+
    '<div class="section-title"><h3>Checklist de aplicabilidade</h3><span>4 estados, sem confundir ausência com não aplicabilidade</span></div><div class="check-grid">'+checksHtml+'</div>';
}

form.addEventListener("submit",async function(e){
  e.preventDefault();
  const input=document.getElementById("files");
  if(!input.files.length)return;

  const fd=new FormData();
  Array.from(input.files).forEach(function(f){fd.append("files",f)});
  workspace.classList.remove("hidden");
  out.innerHTML='<div class="loading">Analisando e segmentando documentos…</div>';
  viewer.classList.add("hidden");
  viewerEmpty.classList.remove("hidden");
  viewerEmpty.textContent="Aguardando a segmentação documental.";

  try{
    const r=await fetch("/api/v8/analyze?module=penalizacao",{method:"POST",body:fd});
    const d=await r.json();
    if(!r.ok)throw new Error(d.detail||"Falha");
    currentAnalysisId=d.analysis_id;
    renderAnalysis(d.analysis,d);
  }catch(err){
    out.innerHTML='<div class="error">'+esc(err.message)+'</div>';
  }
});
