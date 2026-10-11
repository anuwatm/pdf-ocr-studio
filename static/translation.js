"use strict";
window.createTranslationWorkspace = ({state, activateMainTab, loadEpubExportStatus}) => {
  const byId = id => document.getElementById(id);
  let capabilities = null, result = null, glossaryRevision = null, pollTimer = null, loadedJob = null, configDirty = false, consentProvider = null;
  const draftsByJob = new Map();
  const activeStates = new Set(["queued","running","cancelling"]);

  function config() {
    return {source_variant:byId("translation-source").value,source_language:byId("translation-source-language").value,
      target_language:byId("translation-target-language").value,style:byId("translation-style").value,
      provider:byId("translation-provider").value,translate_toc:byId("translation-toc").checked,
      cloud_consent:byId("translation-cloud-consent").checked,
      manual_strategy:byId("translation-manual-strategy").value,preserve_manual_final:byId("translation-manual-strategy").value!=="reset"};
  }
  async function api(path, options={}) {
    const response=await fetch(path,{cache:"no-store",...options});
    const data=await response.json().catch(()=>({}));
    if(!response.ok) throw new Error(data.detail||`HTTP ${response.status}`); return data;
  }
  function parseGlossary() {
    return byId("translation-glossary-editor").value.split(/\r?\n/).map(line=>line.trim()).filter(Boolean).map(line=>{
      if(line.startsWith("!")) return {source:line.slice(1).trim(),target:"",case_sensitive:true,do_not_translate:true,mode:"preserved"};
      const transliterate=line.startsWith("~"),normalized=transliterate?line.slice(1):line;
      const parts=normalized.split("=>"); if(parts.length!==2) throw new Error(`Glossary ไม่ถูกต้อง: ${line}`);
      return {source:parts[0].trim(),target:parts[1].trim(),case_sensitive:false,do_not_translate:false,mode:transliterate?"transliterated":"translated"};
    });
  }
  function renderGlossary(model) {
    glossaryRevision=model.revision;
    byId("translation-glossary-editor").value=(model.entries||[]).map(e=>e.do_not_translate?`!${e.source}`:`${e.mode==="transliterated"?"~":""}${e.source} => ${e.target}`).join("\n");
    byId("translation-glossary-status").textContent=`revision ${model.revision}`;
  }
  async function loadGlossary(){if(state.currentJobId) renderGlossary(await api(`/api/jobs/${state.currentJobId}/translation/glossary`));}
  async function saveGlossary(){
    const model=await api(`/api/jobs/${state.currentJobId}/translation/glossary`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({entries:parseGlossary(),base_revision:glossaryRevision,source_language:byId("translation-source-language").value||null,target_language:byId("translation-target-language").value||null})}); renderGlossary(model);
  }
  function providerChanged(){
    const name=byId("translation-provider").value, provider=capabilities?.providers?.find(p=>p.provider===name);
    const cloud=Boolean(provider?.cloud); byId("translation-consent-wrap").classList.toggle("hidden",!cloud);
    if(cloud){
      if(consentProvider!==name)byId("translation-cloud-consent").checked=false;
      consentProvider=name;
      byId("translation-consent-text").textContent=`ยินยอมส่งข้อความ segment ไป Cloud AI ผ่าน ${provider?.label||"Provider"}`;
    }else{consentProvider=null;byId("translation-cloud-consent").checked=false;}
    byId("translation-provider-badge").textContent=`${cloud?"Cloud":"Offline"} · ${provider?.available?"พร้อม":"ไม่พร้อม"}`;
    byId("translation-provider-badge").className=`badge ${provider?.available?"badge-success":"badge-warning"}`;
    const old=byId("translation-target-language").value;
    byId("translation-target-language").replaceChildren(new Option("เลือกภาษา",""));
    for(const lang of provider?.languages||[]) byId("translation-target-language").add(new Option(`${lang.name} (${lang.code})`,lang.code));
    const values=[...byId("translation-target-language").options].map(option=>option.value);
    byId("translation-target-language").value=values.includes(old)&&old?old:(values.includes("th")?"th":"");
  }
  async function loadCapabilities(){
    capabilities=await api("/api/translation/capabilities");
    const providerSelect=byId("translation-provider"),oldProvider=providerSelect.value;
    providerSelect.replaceChildren();
    for(const provider of capabilities.providers||[]){
      const suffix=provider.available?"":" — ไม่พร้อม";
      providerSelect.add(new Option(`${provider.label||provider.provider}${suffix}`,provider.provider));
    }
    providerSelect.value=[...providerSelect.options].some(option=>option.value===oldProvider)?oldProvider:"local_api";
    const source=byId("translation-source-language");
    for(const lang of capabilities.providers?.[0]?.languages||[]) source.add(new Option(`${lang.name} (${lang.code})`,lang.code));
    providerChanged();
  }
  async function estimate(){
    const data=await api(`/api/jobs/${state.currentJobId}/translation/estimate`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(config())});
    byId("translation-estimate").textContent=`${data.characters.toLocaleString()} อักขระ · ${data.batch_count} batch${data.cloud?` · ประมาณ ${data.estimated_cost} ${data.currency}`:" · ไม่ส่งออกนอกเครื่อง"}`; return data;
  }
  function setStatus(progress){
    const status=progress.status||"idle", total=progress.batch_count||0, done=progress.completed_batches||0;
    byId("translation-status-badge").textContent=status; byId("translation-status-badge").className=`badge ${status==="completed"?"badge-success":activeStates.has(status)?"badge-code":status==="partial"?"badge-warning":"badge-neutral"}`;
    byId("translation-progress-fill").style.width=`${total?Math.round(done/total*100):0}%`;
    byId("translation-progress-text").textContent=`${done}/${total} batch · ${progress.completed_segments||0}/${progress.total_segments||0} segment · ${(progress.elapsed_seconds||0).toFixed(1)}s${progress.error?` · ${progress.error}`:""}`;
    byId("btn-cancel-translation").disabled=!activeStates.has(status);
    byId("btn-retry-translation").classList.toggle("hidden",!["failed","partial","cancelled"].includes(status));
  }
  function markConfigDirty(){
    if(!result)return;configDirty=true;
    byId("translation-language-status").textContent="config เปลี่ยนแล้ว ผลเดิมเป็น stale จนกว่าจะแปลใหม่";
    for(const id of ["btn-download-translation-text","btn-download-translation-html","btn-open-translated-epub"])byId(id).classList.add("hidden");
  }
  async function poll(){
    if(!state.currentJobId)return; const progress=await api(`/api/jobs/${state.currentJobId}/translation/progress`); setStatus(progress);
    if(activeStates.has(progress.status)){clearTimeout(pollTimer);pollTimer=setTimeout(()=>poll().catch(console.error),1000);} else {clearTimeout(pollTimer);await loadResult();}
  }
  async function start(resume=false){
    if(!byId("translation-target-language").value) throw new Error("กรุณาเลือกภาษาปลายทาง");
    const provider=capabilities?.providers?.find(item=>item.provider===byId("translation-provider").value);
    if(provider?.cloud&&!byId("translation-cloud-consent").checked){
      byId("translation-cloud-consent").focus();
      throw new Error(`กรุณาติ๊กยินยอมก่อนส่งข้อความไป ${provider.label||"Cloud provider"}`);
    }
    captureDrafts();
    if(!resume&&result?.segments?.some(s=>s.manual_edited)){
      const labels={preserve:"เก็บคำแก้มือ",rebase:"เก็บคำแก้มือและตรวจ rebase",reset:"ล้างคำแก้มือและเริ่มใหม่"};
      if(!window.confirm(`พบคำแก้มือเดิม\nการแปลซ้ำจะ: ${labels[byId("translation-manual-strategy").value]}`))return;
    }
    await estimate(); const path=resume?"retry":"start";
    const payload={...config(),...(resume?{}:{resume:false})};
    const progress=await api(`/api/jobs/${state.currentJobId}/translation/${path}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}); setStatus(progress); poll();
  }
  function segmentText(segment,mode){return mode==="source"?segment.source_text:mode==="google"?(segment.baseline_text||segment.source_text):mode==="ai"?(segment.translated_text||segment.source_text):(segment.final_text||segment.translated_text||segment.source_text);}
  function draftMap(){if(!draftsByJob.has(state.currentJobId))draftsByJob.set(state.currentJobId,new Map());return draftsByJob.get(state.currentJobId);}
  function captureDrafts(){if(!state.currentJobId)return;const map=draftMap();for(const row of document.querySelectorAll(".translation-segment")){const editor=row.querySelector("[data-final]");if(editor)map.set(row.dataset.segmentId,editor.value);}}
  function combinedText(){
    const drafts=draftMap();
    return (result?.segments||[])
      .filter(s=>!(s.translation_unit_id && s.translation_unit_member_index > 0 && s.translation_unit_enabled !== false && !drafts.has(s.id) && !s.manual_edited && (s.translated_text === "" || s.final_text === "")))
      .map(segment=>drafts.get(segment.id)??segmentText(segment,"final"))
      .join("\n\n");
  }
  function renderCombined(){
    const segments=result?.segments||[],text=segments.length?combinedText():"",area=byId("translation-combined-text");area.value=text;
    byId("translation-combined-summary").textContent=segments.length?`${segments.length.toLocaleString()} segment · ${text.length.toLocaleString()} อักขระ`:"ยังไม่มีผลแปล";
    byId("btn-copy-translation-combined").disabled=!text; if(!text)byId("translation-combined-copy-status").textContent="";
  }
  async function copyCombined(){
    const area=byId("translation-combined-text"),text=area.value;if(!text)return;
    try{if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(text);else{area.focus();area.select();document.execCommand("copy");area.setSelectionRange(0,0);}byId("translation-combined-copy-status").textContent="คัดลอกแล้ว";}
    catch(error){byId("translation-combined-copy-status").textContent="คัดลอกไม่สำเร็จ กรุณาเลือกข้อความแล้วคัดลอกเอง";}
  }
  function applyVisible(action){for(const row of document.querySelectorAll(".translation-segment")){const segment=(result?.segments||[]).find(s=>s.id===row.dataset.segmentId);if(segment)row.querySelector("[data-final]").value=action==="accept"?segmentText(segment,"ai"):segment.source_text;}captureDrafts();renderCombined();}
  function renderSegments(){
    captureDrafts();const container=byId("translation-segments"), page=byId("translation-page-filter").value,mode=byId("translation-review-mode").value; container.replaceChildren();
    const segments=(result?.segments||[]).filter(s=>page==="all"||String(s.page||"")===page);
    for(const segment of segments){
      const isContinuation = Boolean(segment.translation_unit_id && segment.translation_unit_member_index > 0 && segment.translation_unit_enabled !== false);
      const unit = result?.translation_units?.find(u=>u.id===segment.translation_unit_id);
      const row=document.createElement("article");
      row.className=`translation-segment ${segment.warnings?.length?"translation-segment-warning":""} ${isContinuation?"translation-segment-continuation":""}`;
      row.dataset.segmentId=segment.id;
      const head=document.createElement("div");head.className="translation-segment-head";
      let headBadge = `${segment.id} · ${segment.type} · ${segment.status}`;
      if(isContinuation){
        headBadge += ` · ↳ ต่อเนื่องในย่อหน้า (${segment.translation_unit_id})`;
      } else if(segment.translation_unit_id && segment.translation_unit_member_index === 0) {
        headBadge += ` · [หน่วยแปล ${segment.translation_unit_id}]`;
        if(unit?.transformations?.length){
          headBadge += ` · de-hyphenated (${unit.transformations.length})`;
        }
      }
      head.textContent=headBadge;
      const source=document.createElement("pre");source.textContent=`Source\n${segment.source_text}`;
      const comparison=document.createElement("pre");comparison.textContent=`${{source:"Source",google:"Google baseline",ai:"AI result",final:"Final"}[mode]}\n${segmentText(segment,mode)}`;
      const final=document.createElement("textarea");final.value=draftMap().get(segment.id)??segmentText(segment,"final");final.rows=3;final.dataset.final="true";final.setAttribute("aria-label",`Final ${segment.id}`);final.oninput=()=>{draftMap().set(segment.id,final.value);renderCombined();};
      const warning=document.createElement("p");warning.className="text-xs text-warning";warning.textContent=(segment.warnings||[]).join(" · ");
      const actions=document.createElement("div");actions.className="html-action-buttons";
      const accept=document.createElement("button");accept.type="button";accept.className="btn btn-outline btn-xs";accept.textContent="ใช้ผลแปล";accept.onclick=()=>{final.value=segmentText(segment,"ai");draftMap().set(segment.id,final.value);renderCombined();};
      const revert=document.createElement("button");revert.type="button";revert.className="btn btn-outline btn-xs";revert.textContent="คืนต้นฉบับ";revert.onclick=()=>{final.value=segment.source_text;draftMap().set(segment.id,final.value);renderCombined();};
      const addTerm=document.createElement("button");addTerm.type="button";addTerm.className="btn btn-outline btn-xs";addTerm.textContent="เพิ่มศัพท์";addTerm.onclick=()=>{const sourceTerm=window.prompt("คำต้นทาง");if(!sourceTerm)return;const target=window.prompt("คำปลายทาง (เว้นว่าง = do not translate)","");const line=target?`${sourceTerm} => ${target}`:`!${sourceTerm}`;const editor=byId("translation-glossary-editor");editor.value+=(editor.value?"\n":"")+line;};
      actions.append(accept,revert,addTerm);row.append(head,source,comparison,final,warning,actions);container.append(row);
    }
    for(const id of ["btn-save-translation-final","btn-accept-translation-page","btn-revert-translation-page"])byId(id).disabled=!result;renderCombined();
  }
  function fillPages(){
    const select=byId("translation-page-filter"),old=select.value,pages=[...new Set((result?.segments||[]).map(s=>s.page).filter(Boolean))];select.replaceChildren(new Option("ทุกหน้า","all"));for(const page of pages)select.add(new Option(`หน้า ${page}`,String(page)));select.value=[...select.options].some(o=>o.value===old)?old:"all";
  }
  async function loadResult(){
    try{captureDrafts();result=await api(`/api/jobs/${state.currentJobId}/translation/result`);fillPages();renderSegments();
      const active=config(),saved=result.config||{};configDirty=Boolean(result.config)&&["source_variant","source_language","target_language","style","provider","translate_toc"].some(key=>saved[key]!==active[key]);
      const ready=result.status==="completed"&&!result.stale&&!configDirty;
      byId("translation-language-status").textContent=`ตรวจพบภาษา ${result.detected_language||"und"} · confidence ${Math.round((result.language_confidence||0)*100)}%${result.warnings?.length?` · ${result.warnings.join(" · ")}`:""}${result.stale?` · stale: ${result.stale_reasons.join(", ")}`:""}`;
      if(configDirty)byId("translation-language-status").textContent+=" · config เปลี่ยนแล้ว";
      for(const id of ["btn-download-translation-text","btn-download-translation-html","btn-open-translated-epub"])byId(id).classList.toggle("hidden",!ready);
      if(ready){byId("btn-download-translation-text").href=`/api/jobs/${state.currentJobId}/translation/export/text`;byId("btn-download-translation-html").href=`/api/jobs/${state.currentJobId}/translation/export/html`;byId("translation-preview-frame").src=`/api/jobs/${state.currentJobId}/translation/preview?revision=${result.translation_revision}`;byId("translation-preview-frame").classList.remove("hidden");}
    }catch(error){if(!error.message.includes("not found"))console.error(error);}
  }
  async function saveFinal(){
    captureDrafts();const edits=[...draftMap()].map(([id,text])=>({id,text}));
    result=await api(`/api/jobs/${state.currentJobId}/translation/final`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({edits,base_revision:result.translation_revision})});fillPages();renderSegments();await loadResult();
  }
  async function refresh(){
    if(loadedJob!==state.currentJobId){loadedJob=state.currentJobId;result=null;clearTimeout(pollTimer);byId("translation-segments").innerHTML='<p class="text-muted">ยังไม่มีผลแปล</p>';renderCombined();}
    if(!capabilities)await loadCapabilities();
    if(!state.currentJobId)return;await Promise.allSettled([loadGlossary(),poll()]);
  }
  function init(){
    byId("translation-provider").addEventListener("change",providerChanged);byId("btn-load-translation-glossary").onclick=()=>loadGlossary().catch(e=>alert(e.message));byId("btn-save-translation-glossary").onclick=()=>saveGlossary().catch(e=>alert(e.message));
    for(const id of ["translation-source","translation-source-language","translation-target-language","translation-style","translation-provider","translation-toc"])byId(id).addEventListener("change",markConfigDirty);
    byId("btn-estimate-translation").onclick=()=>estimate().catch(e=>alert(e.message));byId("btn-start-translation").onclick=()=>start(false).catch(e=>alert(e.message));byId("btn-retry-translation").onclick=()=>start(true).catch(e=>alert(e.message));
    byId("btn-cancel-translation").onclick=()=>api(`/api/jobs/${state.currentJobId}/translation/cancel`,{method:"POST"}).then(setStatus).catch(e=>alert(e.message));byId("translation-page-filter").onchange=renderSegments;byId("translation-review-mode").onchange=renderSegments;byId("btn-accept-translation-page").onclick=()=>applyVisible("accept");byId("btn-revert-translation-page").onclick=()=>applyVisible("revert");byId("btn-save-translation-final").onclick=()=>saveFinal().catch(e=>alert(e.message));
    byId("btn-copy-translation-combined").onclick=()=>copyCombined();
    byId("btn-view-translation-source").onclick=()=>{
      if(!state.currentJobId)return alert("กรุณาเปิดงานก่อน");
      const variant=encodeURIComponent(byId("translation-source").value);
      window.open(`/api/jobs/${state.currentJobId}/translation/source/preview?source_variant=${variant}`,"_blank","noopener");
    };
    byId("btn-open-translated-epub").onclick=()=>{byId("epub-source-variant").value="translated";activateMainTab("epub");loadEpubExportStatus();};
  }
  return {init,refresh,loadResult};
};
