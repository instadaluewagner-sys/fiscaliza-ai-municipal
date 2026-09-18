const form=document.getElementById("form");
const out=document.getElementById("out");

form.addEventListener("submit",async function(e){
  e.preventDefault();
  const input=document.getElementById("files");
  if(!input.files.length)return;
  const fd=new FormData();
  Array.from(input.files).forEach(function(f){fd.append("files",f)});
  out.classList.remove("hidden");
  out.innerHTML="<p>Analisando...</p>";
  try{
    const r=await fetch("/api/v8/analyze?module=penalizacao",{method:"POST",body:fd});
    const d=await r.json();
    if(!r.ok)throw new Error(d.detail||"Falha");
    const a=d.analysis;
    let cards="";
    (a.checklist||[]).forEach(function(x){
      const cls=x.status==="located"?"ok":"warn";
      cards+='<div class="card"><small>'+x.label+'</small><b class="'+cls+'">'+x.status+'</b><small>'+x.reason+'</small></div>';
    });
    out.innerHTML="<h2>"+(a.profile.process_number||"Processo sem número identificado")+"</h2>"+
      "<p><b>Estágio:</b> "+a.stage.label+"</p>"+
      "<p><b>Próximo ato:</b> "+a.stage.next_action+"</p>"+
      "<p><b>Minuta sugerida:</b> "+a.stage.suggested_draft+"</p>"+
      '<div class="grid">'+cards+"</div>";
  }catch(err){
    out.innerHTML='<p class="warn">'+err.message+"</p>";
  }
});
