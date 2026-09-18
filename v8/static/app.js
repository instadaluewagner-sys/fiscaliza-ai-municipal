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
      '<div><b>'+esc(e.fact)+'</b><p>'+esc(e.excerpt)+'</p></div>'+
      '<span class="evidence-source">'+esc(e.document_id)+' · p. '+esc(e.page)+'</span>'+
    '</div>';
  }).join(""):'<div class="check-card"><small>Evidências</small><b class="neutral">Nenhuma evidência prioritária extraída nesta versão.</b></div>';

  const checksHtml=checks.map(function(x){
    return '<div class="check-card"><small>'+esc(x.label)+'</small><b class="'+statusClass(x.status)+'">'+esc(statusLabel(x.status))+'</b><p>'+esc(x.reason)+'</p></div>';
  }).join("");

  out.innerHTML=
    '<div class="summary-head"><div><small>Análise V8</small><h2>'+profileValue(p.process_number||p.origin_process)+'</h2>'+
    '<div class="process-meta"><span class="chip">'+esc(meta.pages||0)+' páginas</span><span class="chip">'+esc(docs.length)+' peças segmentadas</span><span class="chip">'+esc(meta.ocr_pages||0)+' OCR</span></div></div>'+
    '<span class="stage-badge">'+esc(stage.label||"Estágio não definido")+'</span></div>'+
    '<div class="stage-card"><small>Leitura processual</small><strong>'+esc(stage.rationale||"")+'</strong><p>'+esc(stage.next_action||"")+'</p>'+
    '<div class="next-grid"><div class="next-box"><b>Próximo ato</b><span>'+esc(stage.next_action||"—")+'</span></div><div class="next-box"><b>Minuta compatível</b><span>'+esc(stage.suggested_draft||"—")+'</span></div></div>'+
    '<div class="stage-actions"><button onclick="loadCompatibleDraft()">Gerar minuta compatível</button></div></div>'+
    '<div id="stageDraft"></div>'+
    '<div class="section-title"><h3>Perfil extraído</h3><span>Somente quando há suporte documental</span></div>'+
    '<div class="check-grid">'+
      '<div class="check-card"><small>Empresa</small><b class="neutral">'+profileValue(p.company)+'</b></div>'+
      '<div class="check-card"><small>CNPJ</small><b class="neutral">'+profileValue(p.cnpj)+'</b></div>'+
      '<div class="check-card"><small>Objeto</small><b class="neutral">'+profileValue(p.object_description)+'</b></div>'+
      '<div class="check-card"><small>Quantidade</small><b class="neutral">'+profileValue(p.quantity)+'</b></div>'+
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
