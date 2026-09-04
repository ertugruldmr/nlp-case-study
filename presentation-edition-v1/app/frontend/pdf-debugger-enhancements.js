/* Progressive interaction layer kept separate so the view-model remains easy to audit. */
(function () {
  const q = (s) => document.querySelector(s);
  const css = document.createElement('style');
  css.textContent = `
    .paper-wrap.zoomed{transform-origin:top center}.ov.table{border:3px solid #7654b5;background:#7654b50b}.dot.table{background:#7654b5}
    .mono.nowrap{white-space:pre;overflow-wrap:normal}.scope-note{border-left:4px solid #0b3b82}.muted{color:#66738f}
    .layout.panel-wide{grid-template-columns:minmax(360px,.72fr) minmax(680px,1.28fr)}
    .panel.panel-full{position:fixed;inset:12px;z-index:30;border:1px solid #b9c8df;border-radius:12px;box-shadow:0 24px 80px #00133088}
    .data-tools{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}.data-table{width:100%;border-collapse:collapse;font-size:11px}.data-table th{position:sticky;top:0;background:#edf3fb;text-align:left;z-index:1}.data-table th,.data-table td{padding:6px;border-bottom:1px solid #e1e7f0;vertical-align:top}.data-table tr:hover{background:#effaff}.data-table button{padding:3px 6px;font-size:10px}
    .cell-grid{display:grid;grid-template-columns:minmax(180px,1.5fr) repeat(var(--cols,2),minmax(120px,1fr));overflow:auto}.cell-grid>div{padding:7px;border-bottom:1px solid #e1e7f0}.cell-grid .head{position:sticky;top:0;background:#edf3fb;font-weight:700;z-index:1}
    .workbench{max-width:920px}.workbench-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.workbench input,.workbench select{width:100%;padding:7px;border:1px solid #d9e1ef;border-radius:7px}.workbench .actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}.run-progress{padding:9px;border-radius:8px;background:#edf7ff;margin-top:9px}
    .tour{position:fixed;right:24px;bottom:24px;width:min(390px,calc(100% - 32px));z-index:10}.tour h3{margin:0 0 4px}.tour-actions{display:flex;gap:6px;margin-top:9px;justify-content:flex-end}
    .run-progress.error{background:#fff0f2;color:#9d1f38}.run-progress.success{background:#eaf8f1;color:#126847}.top .status.running{border-color:#d6a63e;color:#ffe19a}.top .status.error{border-color:#d55d71;color:#ffb8c4}
    .scope-flow{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;gap:8px;align-items:center}.scope-flow .card{height:100%}.scope-flow .arrow{font-size:20px;color:#4973a9}.truth-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
    .proof-hash{word-break:break-all;font:10px/1.4 ui-monospace,SFMono-Regular,monospace}.proof-ok{border-left:4px solid #147d5a}.proof-bad{border-left:4px solid #b72d45}.file-profile{margin-top:9px;background:#f2f8ff}
    @media(max-width:900px){.workbench-grid{grid-template-columns:1fr}.layout.panel-wide{grid-template-columns:1fr}.scope-flow{grid-template-columns:1fr}.scope-flow .arrow{transform:rotate(90deg);text-align:center}.truth-list{grid-template-columns:1fr}}
    #backBtn{margin-left:10px;padding:3px 9px;font-size:11px}#backBtn:disabled{opacity:.35;cursor:default}
    @keyframes ftlink-spin{to{transform:rotate(360deg)}}
    .spinner{display:inline-block;width:11px;height:11px;border:2px solid #9dbde3;border-top-color:#0b3b82;border-radius:50%;animation:ftlink-spin .7s linear infinite;vertical-align:-1px;margin-right:6px}
    .run-progress.running{background:#edf7ff}
    .progress-track{height:5px;border-radius:3px;background:#d9e6f7;overflow:hidden;margin-top:7px}
    .progress-fill{height:100%;width:38%;border-radius:3px;background:linear-gradient(90deg,#0b3b82,#20c4d8);animation:ftlink-indeterminate 1.3s ease-in-out infinite}
    @keyframes ftlink-indeterminate{0%{margin-left:-38%}100%{margin-left:100%}}
    .top .status.running .spinner{border-color:#7c6a2c;border-top-color:#ffe19a}
    .footnote-steps{margin-top:6px;font-size:11px;color:#4973a9;display:flex;gap:6px;flex-wrap:wrap}
    .footnote-steps .step{padding:2px 7px;border-radius:999px;border:1px solid #c7d8ef;background:#f2f8ff}
    .footnote-steps .step.done{background:#eaf8f1;border-color:#bfe3cf;color:#126847}
    .footnote-steps .step.active{background:#fff7e0;border-color:#e7cf8e;color:#7c6a2c}
    .footnote-steps .step.failed{background:#fff0f2;border-color:#f0c3cd;color:#9d1f38}
  `;
  document.head.appendChild(css);

  const config = q('#config');
  if (config) { config.textContent='Configure / upload / run'; config.onclick = () => window.openWorkbench(); }

  // A heavy bounded/full-document run executes CPU-bound work in a background thread, but
  // Python's GIL means it can still starve this same process's ability to answer OTHER
  // concurrent requests promptly (Run proof, switching runs, etc.), surfacing to the browser
  // as a bare "Failed to fetch" rather than a slow-but-successful response. This retries a
  // transient failure with backoff instead of leaving the click looking dead.
  async function fetchWithRetry(url, options, attempts = 3, delayMs = 2000) {
    let lastError;
    for (let i = 0; i < attempts; i++) {
      try { return await fetch(url, options); }
      catch (e) { lastError = e; if (i < attempts - 1) await new Promise(r => setTimeout(r, delayMs * (i + 1))); }
    }
    throw new Error(`${lastError?.message || 'network error'} (gave up after ${attempts} attempts -- a long-running bounded/full-document run elsewhere on this server can delay other requests; wait for it to finish and retry)`);
  }

  window.updateBackButtonState = function () {
    const btn = q('#backBtn');
    if (!btn) return;
    const depth = (typeof state !== 'undefined' && state.history) ? state.history.length : 0;
    btn.disabled = depth === 0;
    btn.title = depth ? `Return to your previous selection (${depth} step${depth === 1 ? '' : 's'} back)` : 'Return to your previous selection';
  };

  const toolbar = document.querySelector('.toolbar');
  const reviewMode = document.querySelector('[data-mode="review"]');
  const guideMode = document.createElement('button');
  guideMode.className = 'mode'; guideMode.dataset.mode = 'guide'; guideMode.textContent = 'Case guide';
  reviewMode?.before(guideMode);
  const jsonMode = document.querySelector('[data-mode="json"]');
  const proofMode = document.createElement('button');
  proofMode.className = 'mode'; proofMode.dataset.mode = 'proof'; proofMode.textContent = 'Run proof';
  jsonMode?.before(proofMode);
  const extractedMode = document.createElement('button');
  extractedMode.className = 'mode'; extractedMode.dataset.mode = 'extracted'; extractedMode.textContent = 'Extracted';
  jsonMode?.before(extractedMode);
  const tourButton = document.createElement('button'); tourButton.textContent = 'Guided tour'; tourButton.id = 'tour'; toolbar?.appendChild(tourButton);
  const annotationButton = document.createElement('button'); annotationButton.textContent = 'Export annotations'; annotationButton.id = 'exportAnnotations'; toolbar?.appendChild(annotationButton);
  const importButton = document.createElement('button'); importButton.textContent = 'Import annotations'; importButton.id = 'importAnnotations'; toolbar?.appendChild(importButton);
  const zoomLabel = q('#zoom'); let zoom = 1;
  function setZoom(next) { zoom = next; const p = q('.paper-wrap'); if (p) { p.classList.toggle('zoomed', next !== 1); p.style.width = next === 1 ? 'min(100%,650px)' : `min(${650 * next}px, ${100 * next}%)`; } zoomLabel.textContent = next === 1 ? 'Fit width' : `${Math.round(next * 100)}%`; }
  if (q('#fit')) q('#fit').onclick = () => setZoom(1);
  if (zoomLabel) zoomLabel.onclick = () => setZoom(zoom >= 1.5 ? 1 : 1.5);
  const rotateButton=document.createElement('button'); rotateButton.id='rotatePage'; rotateButton.textContent='Rotate 90°'; zoomLabel?.after(rotateButton);
  const compareViewButton=document.createElement('button'); compareViewButton.id='compareView'; compareViewButton.textContent='⊞ Compare side-by-side'; compareViewButton.title='Open two or more runs next to each other, each a full independent debugger';
  compareViewButton.onclick=()=>{const cur=state.run?.run_id||'baseline';const ids=cur==='baseline'?[cur]:[cur,'baseline'];location.href=`/pdf-debugger-compare.html?runs=${encodeURIComponent(ids.join(','))}`;};
  q('#export')?.after(compareViewButton);

  state.pageCount = state.pageCount || 95;
  state.wrapJson = true;
  state.pageJsonOnly = false;
  state.viewRotations = {};
  state.proof = null;
  state.pendingPdfProfile = null;

  function rotatedBox(b,width,height,rotation) {
    if(rotation===90) return {bbox:[height-b[3],b[0],height-b[1],b[2]],width:height,height:width};
    if(rotation===180) return {bbox:[width-b[2],height-b[3],width-b[0],height-b[1]],width,height};
    if(rotation===270) return {bbox:[b[1],width-b[2],b[3],width-b[0]],width:height,height:width};
    return {bbox:b,width,height};
  }

  function validBbox(x) {
    const b = x?.provenance?.bbox;
    return Array.isArray(b) && b.length === 4 && b.every(Number.isFinite) && b[2] > b[0] && b[3] > b[1];
  }

  function bboxFor(x) {
    if (validBbox(x)) return x.provenance.bbox;
    if (!x?.row_id || !state.run) return null;
    const cells=state.run.result.cells.filter(c=>c.row_id===x.row_id && validBbox(c));
    if (!cells.length) return null;
    const table=ix.tables.get(x.table_id), tb=validBbox(table)?table.provenance.bbox:null;
    return [tb?.[0] ?? Math.min(...cells.map(c=>c.provenance.bbox[0])),
            Math.min(...cells.map(c=>c.provenance.bbox[1])),
            tb?.[2] ?? Math.max(...cells.map(c=>c.provenance.bbox[2])),
            Math.max(...cells.map(c=>c.provenance.bbox[3]))];
  }

  pageFor = function (id) {
    const relation = ix?.rels?.get(id);
    if (relation) return pageFor(relation.summary_row_id);
    const x = ix?.cells?.get(id) || ix?.rows?.get(id) || ix?.tables?.get(id);
    return x?.provenance?.page || x?.page || state.page || 1;
  };

  select = function (kind, id, explicitPage) {
    const exists = ix && (ix.cells.has(id) || ix.rows.has(id) || ix.rels.has(id) || ix.tables.has(id));
    if (!exists) return;
    state.history = state.history || [];
    state.history.push({page: state.page, selected: state.selected});
    if (state.history.length > 25) state.history.shift();
    state.selected = {kind, id};
    state.page = explicitPage || pageFor(id);
    render();
    window.updateBackButtonState && window.updateBackButtonState();
  };

  currentOverlays = function () {
    const r = state.run.result, out = [];
    r.tables.forEach(t => { const box=bboxFor(t); if(t.page===state.page&&box)out.push({id:t.table_id,kind:'table',object:t,bbox:box}); });
    r.rows.forEach(x => { const box=bboxFor(x); if(x.provenance?.page===state.page&&box)out.push({id:x.row_id,kind:'row',object:x,bbox:box}); });
    r.cells.forEach(x => { const box=bboxFor(x); if(x.provenance?.page===state.page&&box)out.push({id:x.cell_id,kind:'cell',object:x,bbox:box}); });
    r.relations.forEach(rel => [rel.summary_row_id, rel.footnote_row_id].forEach(id => {
      const x=ix.rows.get(id), box=bboxFor(x);
      if(x?.provenance?.page===state.page&&box)out.push({id:rel.relation_id,kind:'relation',object:x,rel,bbox:box});
    }));
    return out;
  };

  renderPage = function () {
    const img=q('#pageImg'), runId=encodeURIComponent(state.run?.run_id || 'baseline'), requestedPage=state.page;
    const viewRotation=state.viewRotations[requestedPage]||0;
    img.src=`/api/debugger/page/${requestedPage}?run_id=${runId}&view_rotation=${viewRotation}`;
    img.onload=()=>{
      if(requestedPage!==state.page || viewRotation!==(state.viewRotations[requestedPage]||0)) return;
      const root=q('#overlays'), space=state.run.coordinate_spaces?.[String(state.page)] || {width:img.naturalWidth,height:img.naturalHeight}; root.innerHTML='';
      currentOverlays().forEach(o=>{
        const warning=o.object.confidence<=.5 || o.rel?.low_confidence;
        if (!state.layer[o.kind] || (warning && !state.layer.warn)) return;
        const transformed=rotatedBox(o.bbox,space.width,space.height,viewRotation), b=transformed.bbox, d=document.createElement('button');
        d.className='ov '+o.kind+(warning?' warn':'')+(state.selected?.id===o.id?' selected':'');
        d.title=`${o.kind} · ${o.object.label_raw||o.object.title||o.object.value?.raw||o.id}`;
        d.style.left=(b[0]/transformed.width*100)+'%'; d.style.top=(b[1]/transformed.height*100)+'%';
        d.style.width=((b[2]-b[0])/transformed.width*100)+'%'; d.style.height=((b[3]-b[1])/transformed.height*100)+'%';
        d.onclick=()=>select(o.kind,o.id,state.page); root.appendChild(d);
      });
    };
    img.onerror=()=>{if(requestedPage===state.page){q('#overlays').innerHTML='';q('#selectionText').textContent=`Page ${requestedPage} could not be rendered. Check the PDF and run status.`;}};
    q('#pageLabel').textContent=`Page ${state.page} / ${state.pageCount}`;
    rotateButton.textContent=`Rotate 90° · view ${viewRotation}°`;
  };

  rotateButton.onclick=()=>{state.viewRotations[state.page]=((state.viewRotations[state.page]||0)+90)%360;renderPage();};

  function pageData() {
    const r=state.run.result;
    const tables=r.tables.filter(x=>x.page===state.page);
    const tableIds=new Set(tables.map(x=>x.table_id));
    const rows=r.rows.filter(x=>x.provenance?.page===state.page || tableIds.has(x.table_id));
    const rowIds=new Set(rows.map(x=>x.row_id));
    const cells=r.cells.filter(x=>x.provenance?.page===state.page || rowIds.has(x.row_id));
    const relations=r.relations.filter(x=>rowIds.has(x.summary_row_id)||rowIds.has(x.footnote_row_id));
    const checks=r.checks.filter(x=>tables.some(t=>x.scope?.includes(t.table_id))||rows.some(v=>x.scope?.includes(v.row_id)));
    return {page:state.page,tables,rows,cells,relations,checks};
  }

  function scopeText() {
    const c=state.run.result.run?.config_echo?.document || {}, range=c.summary_pages || [];
    if (range.length===2 && state.page>=range[0] && state.page<=range[1]) return 'Configured summary extraction page';
    const controls=state.run.result.run?.config_echo?.confidence?.extra_control_pages || [];
    if (controls.includes(state.page)) return 'Calibration-control page. Control intermediates are not persisted in canonical result.json.';
    if (state.run.result.tables.some(t=>t.page===state.page)) return 'Automatically located footnote/table page';
    return 'Outside canonical extraction scope. No overlay is expected.';
  }

  function contractName() {
    const c=state.run.result.run?.config_echo?.document||{}, range=c.summary_pages||[];
    if(range[0]===5&&range[1]===7&&c.footnote_no===11) return state.run?.run_id==='baseline'?'Authoritative case baseline':'Case-compatible configuration';
    if(range[0]===5&&range[1]===10&&c.footnote_no===11) return 'Extended statement experiment';
    if(range[0]===1&&range[1]===state.pageCount) return 'Legacy full-range configuration (visual review recommended)';
    return 'Custom configuration';
  }

  function runContext() {
    const result=state.run.result, documentConfig=result.run?.config_echo?.document||{};
    const range=Array.isArray(documentConfig.summary_pages)?documentConfig.summary_pages:[];
    const summaryStart=Number.isInteger(range[0])?range[0]:1;
    const summaryEnd=Number.isInteger(range[1])?range[1]:summaryStart;
    const footnoteNo=documentConfig.footnote_no??'not configured';
    const footnotePages=[...new Set(result.tables
      .filter(t=>!(t.page>=summaryStart&&t.page<=summaryEnd))
      .map(t=>t.page).filter(Number.isInteger))].sort((a,b)=>a-b);
    const firstRelation=result.relations[0]||null;
    return {
      result, documentConfig, range, summaryStart, summaryEnd, footnoteNo, footnotePages,
      firstRelation, isBaseline:state.run.run_id==='baseline',
      firstTable:result.tables[0]||null, firstCell:result.cells[0]||null,
      relationSourcePage:firstRelation?pageFor(firstRelation.summary_row_id):null,
      relationTargetPage:firstRelation?pageFor(firstRelation.footnote_row_id):null,
    };
  }

  window.jumpDebuggerPage = function (page,mode='review') { state.page=page;state.selected=null;state.mode=mode;render(); };
  window.copyText = function (value) { navigator.clipboard?.writeText(value); };

  function guide() {
    const ctx=runContext(), pages=`${ctx.summaryStart}–${ctx.summaryEnd}`;
    const located=ctx.footnotePages.length?`PDF page${ctx.footnotePages.length===1?'':'s'} ${ctx.footnotePages.join(', ')}`:'no footnote-table page persisted';
    const relationReview=ctx.firstRelation
      ? `<p><b>Summary source</b> is on page ${ctx.relationSourcePage}; <b>Note target</b> is on page ${ctx.relationTargetPage}. One summary row may have several supporting targets.</p><button onclick="jumpDebuggerPage(${ctx.relationSourcePage},'review')">Open first emitted relation</button>`
      : `<p><b>No relation was emitted for this run.</b> Review the configured summary rows, note references and REL_COVERAGE/locator checks before interpreting that as a valid negative.</p><button onclick="jumpDebuggerPage(${ctx.summaryStart},'extracted')">Inspect configured summary data</button>`;
    const groundTruth=ctx.isBaseline
      ? `<section class="card"><h3>Baseline-only ground truth</h3><p>Yapı Kredi supplied no answer key. The hand reference attached to the baseline covers 201 logical cell positions and seven expected row-pair relations. It does not prove production accuracy, complete hierarchy correctness or universal calibration.</p>${ctx.footnotePages.length?`<button onclick="jumpDebuggerPage(${ctx.footnotePages[0]},'extracted')">Inspect baseline Note ${esc(ctx.footnoteNo)} evidence</button>`:''}</section>`
      : `<section class="card scope-note"><h3>No ground truth attached to this run</h3><p>The 201-cell / seven-relation hand reference belongs to the <b>baseline assignment run only</b>. This ${esc(state.run.run_id)} view shows emitted evidence and checks, but makes no accuracy, precision or recall claim without a separately authored reference for this exact PDF and configuration.</p><button onclick="document.querySelector('[data-mode=proof]').click()">Inspect run-bound proof</button></section>`;
    q('#content').innerHTML=`<div class="hero"><div class="eyebrow">${ctx.isBaseline?'Case contract':'Run-specific guide'} · reviewer orientation</div><h1>${ctx.isBaseline?'What this solution is required to prove':'What this configured run actually attempted'}</h1><p><b>${esc(contractName())}</b> · run ${esc(state.run.run_id)}. Configuration changes the evaluated scope, so evidence and ground truth must never leak between runs.</p><div class="data-tools"><button onclick="openWorkbench()">Choose configuration / PDF</button><button onclick="jumpDebuggerPage(${ctx.summaryStart},'extracted')">Start at configured page ${ctx.summaryStart}</button></div></div>
      <div class="scope-flow"><div class="card"><b>1 · Summary statements</b><p>Extract configured PDF pages ${pages}, including emitted hierarchy, columns, references and numeric states.</p></div><div class="arrow">→</div><div class="card"><b>2 · Locate Note ${esc(ctx.footnoteNo)}</b><p>Search the full PDF for the configured note. This run contains ${located}.</p></div><div class="arrow">→</div><div class="card"><b>3 · Evidence edges</b><p>${ctx.result.relations.length} relation edge${ctx.result.relations.length===1?'':'s'} persisted for this run, with confidence and checks.</p></div></div>
      <section class="card"><h3>Configuration meanings</h3><table class="data-table"><thead><tr><th>Mode</th><th>Pages</th><th>Claim</th><th>Action</th></tr></thead><tbody><tr><td><b>Current run</b></td><td>${pages} + Note ${esc(ctx.footnoteNo)}</td><td>${esc(contractName())}; claims are limited to its persisted output.</td><td><button onclick="jumpDebuggerPage(${ctx.summaryStart},'extracted')">Inspect</button></td></tr><tr><td>Case contract</td><td>5–7 + Note 11</td><td>Authoritative assignment acceptance scope; baseline ground truth is scoped here only.</td><td><button onclick="openWorkbench()">Configure</button></td></tr><tr><td>Full-document visual</td><td>1–${state.pageCount}</td><td>Browse and annotate; makes no full-document extraction claim.</td><td><button onclick="jumpDebuggerPage(1,'review')">Browse</button></td></tr><tr><td>Bounded extraction</td><td>Document-specific range</td><td>Choose statement pages and leave later pages available for note discovery. A 1–end extraction is rejected.</td><td><button onclick="openWorkbench()">Configure</button></td></tr></tbody></table></section>
      <div class="truth-list"><section class="card"><h3>How to review relations</h3>${relationReview}</section>${groundTruth}</div>
      <section class="card issue"><h3>Claims we must not make</h3><p>Do not transfer baseline accuracy to this run. Do not interpret zero emitted relations as correctness without checking coverage. Do not treat omitted cells as correct or OCR-engine agreement as independent ground truth.</p></section>`;
  }

  debug = function () {
    const ctx=runContext(), r=ctx.result, cfg=r.run?.config_echo||{}, ocr=cfg.ocr||{};
    const stages=['S0 config','S1 primary OCR','S1b numeric verifier','S2 page checks','S3 structure & hierarchy','S4 numeric grammar','S5 footnote locator','S6 candidate generation / RRF','S7 link decision','S8 confidence','S9 validation','S10 output'];
    const configText=`Config echo: summary pages ${ctx.summaryStart}–${ctx.summaryEnd}, footnote ${ctx.footnoteNo}, OCR ${ocr.dpi??'n/a'} dpi / PSM ${ocr.psm??'n/a'}.`;
    const linkText=r.relations.length
      ? `Accepted relations: ${r.relations.length}; approaches and evidence are available per emitted relation.`
      : 'Accepted relations: 0. No relation detail exists; inspect reference-bearing rows and coverage/locator checks.';
    q('#content').innerHTML=`<div class="hero"><div class="eyebrow">Technical debugger · ${esc(state.run.run_id)}</div><h1>Evidence trace</h1><p><b>${esc(contractName())}</b>. Only fields persisted by this exact run are shown; baseline facts are not substituted.</p></div>`+stages.map((s,i)=>`<div class="card stage"><b>${esc(s.split(' ')[0])}</b><div><h3>${esc(s.slice(3))}</h3><p>${i===0?esc(configText):i===3?'Checks: '+r.checks.filter(x=>x.group==='structural').length+' structural.':i===8?esc(linkText):i===9?'Calibration and interval fields are shown only where this run persisted them.':'Stored tables, rows, cells, relations or checks only; additional intermediate evidence is not persisted.'}</p></div></div>`).join('');
  };

  extracted = function () {
    const p=pageData(), rowById=new Map(state.run.result.rows.map(x=>[x.row_id,x]));
    const tableSections=p.tables.map(t=>{
      const rows=p.rows.filter(r=>r.table_id===t.table_id), periods=t.periods||[];
      const cellByKey=new Map(p.cells.filter(c=>rows.some(r=>r.row_id===c.row_id)).map(c=>[`${c.row_id}|${c.period_id}`,c]));
      const columns=periods.map(col=>`<tr><td>${esc(col.period_id)}</td><td>${esc(col.label)}</td><td>${esc(col.kind)}</td></tr>`).join('');
      const matrixRows=rows.map(r=>{
        const parent=rowById.get(r.parent_row_id);
        const label=`<button onclick="focusObject('row','${r.row_id}',${state.page})">${esc(r.label_raw||'(unlabelled total)')}</button><div class="small">${esc(r.role)} · indent ${r.indent_level} · parent ${esc(parent?.label_raw||'none')} · refs ${esc((r.dipnot_refs||[]).join(',')||'none')} · conf ${r.confidence.toFixed(2)}</div>`;
        const values=periods.map(col=>{const c=cellByKey.get(`${r.row_id}|${col.period_id}`);return `<div>${c?`<button onclick="focusObject('cell','${c.cell_id}',${state.page})"><b>${esc(c.value.raw??c.value.state)}</b></button><div class="small">${esc(c.value.value??c.value.state)} · ${c.confidence.toFixed(2)}${c.value.repaired?' · repaired':''}</div>`:'<span class="small">not emitted</span>'}</div>`;}).join('');
        return `<div>${label}</div>${values}`;
      }).join('');
      return `<section class="card"><div class="eyebrow">Table ${esc(t.table_id)}</div><h3><button onclick="focusObject('table','${t.table_id}',${state.page})">${esc(t.title)}</button></h3><p>${esc(t.statement_hint||'table')} · confidence ${t.confidence.toFixed(2)}</p><details><summary>Column contract (${periods.length})</summary><table class="data-table"><thead><tr><th>ID</th><th>Header</th><th>Kind</th></tr></thead><tbody>${columns}</tbody></table></details><h3>Bound row × column values</h3><div class="cell-grid" style="--cols:${periods.length}"><div class="head">Row / hierarchy / references</div>${periods.map(x=>`<div class="head">${esc(x.label)}<br><span class="small">${esc(x.period_id)} · ${esc(x.kind)}</span></div>`).join('')}${matrixRows}</div></section>`;
    }).join('');
    const relations=p.relations.map(rel=>`<button class="relbtn" onclick="focusObject('relation','${rel.relation_id}',${state.page})"><b>${esc(rowById.get(rel.summary_row_id)?.label_raw)}</b> → ${esc(rowById.get(rel.footnote_row_id)?.label_raw)} <span class="chip">${esc(rel.period_scope)}</span><br><span class="small">${esc(rel.relation_type)} · ${esc(rel.agreement)} · confidence ${rel.confidence.toFixed(2)} · ${esc(rel.evidence)}</span></button>`).join('');
    const checks=p.checks.map(x=>`<tr><td>${esc(x.check_id)}</td><td>${esc(x.group)}</td><td>${esc(x.status)}</td><td>${esc(x.scope)}</td><td>${esc(x.detail)}</td></tr>`).join('');
    q('#content').innerHTML=`<div class="hero"><div class="eyebrow">Page-local extraction</div><h1>Page ${state.page}</h1><p>${esc(scopeText())}</p><div class="data-tools"><button onclick="togglePanelWide()">Widen / reset split</button><button onclick="togglePanelFull()">Full-screen data</button><button onclick="openWorkbench()">Configure or run</button></div></div><div class="metrics"><div class="metric"><b>${p.tables.length}</b><span>tables</span></div><div class="metric"><b>${p.rows.length}</b><span>rows</span></div><div class="metric"><b>${p.cells.length}</b><span>cells</span></div><div class="metric"><b>${p.relations.length}</b><span>relation edges</span></div></div>${tableSections||`<div class="card scope-note"><h3>No canonical extraction on this page</h3><p>${esc(scopeText())}</p><button onclick="openWorkbench()">Change configuration</button></div>`}${relations?`<div class="tabs"><b>Relations touching this page</b></div>${relations}`:''}${checks?`<details class="card"><summary>Validation checks touching this page (${p.checks.length})</summary><div style="overflow:auto"><table class="data-table"><thead><tr><th>Check</th><th>Group</th><th>Status</th><th>Scope</th><th>Detail</th></tr></thead><tbody>${checks}</tbody></table></div></details>`:''}`;
  };

  window.focusObject = function (kind,id,page) {
    q('.panel')?.classList.remove('panel-full');
    select(kind,id,page);
  };
  window.togglePanelWide = function () { q('.layout')?.classList.toggle('panel-wide'); };
  window.togglePanelFull = function () { q('.panel')?.classList.toggle('panel-full'); };

  function ensureWorkbench() {
    let dialog=q('#workbenchDialog'); if(dialog) return dialog;
    dialog=document.createElement('dialog'); dialog.id='workbenchDialog'; dialog.className='workbench';
    dialog.innerHTML=`<form method="dialog"><div class="eyebrow">Debugger-native workbench</div><h2>Inspect the exact PDF, configure it, then run the real pipeline</h2><div class="workbench-grid"><section><label>Configuration preset<select id="wbPreset"><option value="case">Case contract: summary 5-7, Note 11</option><option value="extended">Extended statements: pages 5-10, Note 11</option><option value="visual">Full document (browse current run; RUNS a new file bounded 1..end-1)</option><option value="custom">Custom bounded pipeline configuration</option></select></label><label>Summary page start<input id="wbStart" type="number" min="1"></label><label>Summary page end<input id="wbEnd" type="number" min="1"></label><div class="small" id="wbEndHint" style="margin:-6px 0 6px"></div><label>Target footnote(s)<input id="wbFootnote" placeholder="11 or 11,12,13"></label><div class="small" style="margin:-6px 0 6px">One number runs once. Several, comma-separated, run one after another on the same PDF and configuration -- useful when more than one note is worth covering, not just the note the case names.</div><label>Extra calibration-control pages<input id="wbControls" placeholder="9,10"></label><label>Display label (run selector only)<input id="wbLabel" maxlength="120"></label><label>Company legal name<input id="wbCompany" maxlength="240"></label><label>Reporting period end<input id="wbPeriod" type="date"></label><label>Currency code<input id="wbCurrency" maxlength="8" placeholder="TL"></label><label>OCR language<input id="wbOcrLang" maxlength="24" placeholder="tur"></label></section><section><label>Optional new PDF<input id="wbFile" type="file" accept="application/pdf,.pdf"></label><div id="wbFileProfile" class="card file-profile" hidden></div><div class="card scope-note"><b>Scope contract</b><p id="wbScopeHelp"></p></div><div class="card"><b>Current run</b><p id="wbCurrent"></p><div class="actions"><button type="button" id="wbReport">Report</button><button type="button" id="wbWalk">Pipeline stages</button><button type="button" id="wbTriage">Review queue</button><button type="button" id="wbCompare">Compare baseline</button><button type="button" id="wbProof">Run proof</button></div></div></section></div><div id="wbStatus" class="run-progress" hidden></div><div class="actions"><button value="cancel">Close</button><button type="button" id="wbVisual">Review all pages now</button><button type="button" id="wbRun">Create configuration and run</button></div></form>`;
    document.body.appendChild(dialog);
    q('#wbPreset').onchange=applyWorkbenchPreset;
    q('#wbFile').onchange=inspectWorkbenchFile;
    q('#wbVisual').onclick=()=>{
      if(q('#wbFile').files?.[0]) {
        // "Visual review" itself never runs the pipeline -- it just pages through
        // whatever a completed run already rendered. A freshly selected file has no
        // completed run yet, so there is nothing to page through. What the user
        // almost always actually wants here is the widest bounded RUN the sealed
        // pipeline can do (1..page_count-1; the locator needs one later page free),
        // after which every page -- including ones outside the extraction window --
        // is still individually browsable from Review/Extracted. Offer that directly
        // instead of a dead-end error.
        const pc=state.pendingPdfProfile?.page_count;
        if(!pc){q('#wbStatus').hidden=false;q('#wbStatus').className='run-progress error';q('#wbStatus').textContent='Wait for the selected PDF inspection to finish successfully, then try again.';return;}
        q('#wbPreset').value='custom';
        q('#wbStart').value=1;q('#wbEnd').value=Math.max(1,pc-1);
        if(!q('#wbFootnote').value.trim())q('#wbFootnote').value='11';
        applyWorkbenchPreset();
        q('#wbStatus').hidden=false;q('#wbStatus').className='run-progress';
        q('#wbStatus').textContent=`No pipeline run exists yet for this new file, so there is nothing to page through. Running the widest bound this ${pc}-page document allows instead: pages 1-${Math.max(1,pc-1)}, note(s) ${q('#wbFootnote').value}. Every page, including ones outside this range, stays individually browsable afterward via Review/Extracted page navigation. WARNING: a range this wide has measured anywhere from ~2.5 to ~68 minutes depending on the document -- do not start this live without saying so out loud first; use a bounded custom range instead if time is short.`;
        startWorkbenchRun();
        return;
      }
      state.page=1;state.selected=null;dialog.close();render();
    };
    q('#wbRun').onclick=startWorkbenchRun;
    q('#wbReport').onclick=()=>window.open(`/api/runs/${encodeURIComponent(state.run.run_id)}/report`,'_blank','noopener');
    q('#wbWalk').onclick=()=>showRunArtifact('walkthrough');
    q('#wbTriage').onclick=()=>showRunArtifact('triage');
    q('#wbCompare').onclick=()=>showRunArtifact('compare');
    q('#wbProof').onclick=()=>{dialog.close();state.mode='proof';render();};
    return dialog;
  }

  function applyWorkbenchPreset() {
    const preset=q('#wbPreset').value, end=state.pendingPdfProfile?.page_count||state.pageCount;
    const values={case:[5,Math.min(7,end),11,'9,10'],extended:[5,Math.min(10,end),11,''],visual:[1,end,11,''],custom:[null,null,null,null]}[preset];
    if(values[0]!==null){q('#wbStart').value=values[0];q('#wbEnd').value=values[1];q('#wbFootnote').value=values[2];q('#wbControls').value=values[3];}
    const help={case:'Authoritative assignment scope. Extract PDF pages 5-7 and automatically locate Note 11.',extended:'Measured research extension: include balance, income, equity and cash-flow statement pages 5-10 while retaining Note 11.',visual:'On the current run: browse every rendered page with no pipeline rerun (narrative/cover inspection). On a newly selected file, which has no run yet: instead RUNS it bounded to the widest range this pipeline allows (page 1 to the second-to-last page, note 11 unless you set another) -- there is nothing to "just browse" before something has actually run. Measured 2.5 to 68 minutes depending on the document; not a quick live-demo action.',custom:'Choose the document-specific bounded statement range, one target footnote and optional calibration pages. The end page must leave room for note discovery.'};
    q('#wbScopeHelp').textContent=help[preset];
    const disable=preset==='visual'; ['#wbStart','#wbEnd','#wbControls'].forEach(s=>q(s).disabled=disable);
    // Start/end are auto-computed (1..end-1) in visual mode and stay locked, but the
    // footnote still matters once a file is present, since picking this preset then
    // RUNS the pipeline (see #wbVisual's onclick) -- leave it editable in that case
    // so the note number can be corrected for a document that isn't the case's own.
    q('#wbFootnote').disabled=disable&&!q('#wbFile').files?.[0];
  }

  window.openWorkbench = function () {
    const dialog=ensureWorkbench(), c=state.run.result.run?.config_echo?.document||{}, ocr=state.run.result.run?.config_echo?.ocr||{}, controls=state.run.result.run?.config_echo?.confidence?.extra_control_pages||[];
    const range=c.summary_pages||[]; q('#wbPreset').value=range[0]===5&&range[1]===7?'case':range[0]===5&&range[1]===10?'extended':range[0]===1&&range[1]===state.pageCount?'visual':'custom'; q('#wbStart').value=range[0]||1;q('#wbEnd').value=range[1]||state.pageCount;q('#wbFootnote').value=c.footnote_no||11;q('#wbControls').value=controls.join(',');q('#wbLabel').value=`${state.run.run_id} configured review`;q('#wbCompany').value=c.company||state.run.result.document?.company||'';q('#wbPeriod').value=c.period_end||state.run.result.document?.period_end||'';q('#wbCurrency').value=c.currency||state.run.result.document?.currency||'TL';q('#wbOcrLang').value=ocr.lang||'tur';
    q('#wbCurrent').textContent=`${state.run.run_id} · ${state.pageCount} pages · summary ${c.summary_pages?.join('-')||'n/a'} · Note ${c.footnote_no||'n/a'}`;
    q('#wbStart').max=state.pageCount;q('#wbEnd').max=Math.max(1,state.pageCount-1);
    q('#wbEndHint').textContent=`Max ${Math.max(1,state.pageCount-1)} of ${state.pageCount} pages -- the locator needs at least one later page to find the target note(s). Use "Full-document visual review" (no pipeline run) to browse every page instead.`;
    q('#wbCompare').disabled=state.run.run_id==='baseline'; q('#wbStatus').hidden=true; applyWorkbenchPreset(); dialog.showModal();
  };

  async function inspectWorkbenchFile() {
    const file=q('#wbFile').files?.[0], box=q('#wbFileProfile'), status=q('#wbStatus');
    state.pendingPdfProfile=null;
    if(!file){box.hidden=true;q('#wbStart').max=state.pageCount;q('#wbEnd').max=Math.max(1,state.pageCount-1);q('#wbEndHint').textContent=`Max ${Math.max(1,state.pageCount-1)} of ${state.pageCount} pages -- the locator needs at least one later page to find the target note(s).`;q('#wbVisual').disabled=false;q('#wbVisual').textContent='Review all pages now';applyWorkbenchPreset();return;}
    q('#wbVisual').disabled=true;q('#wbVisual').textContent='Review all pages now';
    box.hidden=false;box.innerHTML='<b>Read-only PDF inspection</b><p>Hashing and checking page structure… nothing is stored yet.</p>';
    status.hidden=true;
    try {
      const fd=new FormData();fd.append('file',file);const r=await fetch('/api/debugger/inspect-pdf',{method:'POST',body:fd});if(!r.ok)throw new Error(await responseError(r));
      const profile=await r.json();if(q('#wbFile').files?.[0]!==file)return;state.pendingPdfProfile=profile;
      q('#wbVisual').disabled=false;q('#wbVisual').textContent='Run bounded 1..end-1 now';
      q('#wbStart').max=profile.page_count;q('#wbEnd').max=Math.max(1,profile.page_count-1);
      q('#wbEndHint').textContent=`Max ${Math.max(1,profile.page_count-1)} of ${profile.page_count} pages -- the locator needs at least one later page to find the target note(s).`;
      box.className='card file-profile proof-ok';box.innerHTML=`<b>Exact input inspected · not persisted</b><p>${esc(file.name)} · ${profile.page_count} pages · ${esc(profile.source_kind)} · ${(profile.size_bytes/1048576).toFixed(2)} MB</p><div class="proof-hash">SHA-256 ${esc(profile.sha256)}</div><p>${profile.native_text_page_count} native-text pages · ${profile.image_page_count} image pages · landscape ${esc(profile.landscape_pages.join(', ')||'none')} · metadata rotation ${esc(profile.metadata_rotated_pages.join(', ')||'none')}</p><p><b>Next:</b> choose the exact summary range and note. Inspection proves which bytes will be uploaded; it does not assume the case layout.</p>`;
      q('#wbPreset').value='custom';q('#wbScopeHelp').textContent=`New ${profile.page_count}-page PDF inspected. Choose its real summary-table pages and target note; do not reuse the case page numbers unless they genuinely apply.`;
    } catch(e) {box.className='card file-profile proof-bad';box.innerHTML=`<b>PDF inspection failed</b><p>${esc(e.message)}</p>`;}
  }

  // Forecast text based on real measurements taken against this app (03-04.09.2026), not a
  // guess: bounded 3-10 page ranges were consistently fast; anything wider than ~30 pages was
  // measured to vary by more than an order of magnitude between two similarly-sized documents
  // (155s vs ~4065s for two ~90-page ranges), so a single-number ETA there would be dishonest.
  // Widening this table only when a new range width is actually measured and recorded keeps it
  // trustworthy instead of decorative.
  function forecastForWidth(width) {
    if (!Number.isFinite(width) || width < 1) return '';
    if (width <= 3) return 'measured 15-30s for ranges this narrow';
    if (width <= 10) return 'measured 17-46s for ranges this size (3-6 pages) tonight';
    if (width <= 30) return 'no direct measurement at this width; extrapolating from smaller/larger ranges, expect roughly 1-5 minutes';
    return `wide range (${width} pages): highly variable, measured 155s to ~68 minutes for similarly wide ranges on different documents tonight -- no reliable ETA, budget for over an hour`;
  }

  // Ticking elapsed-time + spinner, independent of whether the workbench dialog stays
  // open -- addresses "no action, no progress bar" during a multi-minute OCR/model run.
  // rangeWidth (optional, in pages) drives the forecast line; omit it where the range
  // isn't known yet (e.g. before submitting the first request).
  function startProgressTicker(status, initialLabel, rangeWidth) {
    const badge = q('.top .status');
    const startedAt = Date.now();
    let label = initialLabel;
    let stepsHtml = '';
    const forecast = forecastForWidth(rangeWidth);
    const spinner = '<span class="spinner"></span>';
    const paint = () => {
      const elapsed = Math.round((Date.now() - startedAt) / 1000);
      const forecastLine = forecast ? `<div class="small" style="margin-top:4px">Forecast: ${esc(forecast)}</div>` : '';
      status.innerHTML = `${spinner}${esc(label)} &middot; ${elapsed}s elapsed<div class="progress-track"><div class="progress-fill"></div></div>${forecastLine}${stepsHtml}`;
      badge.innerHTML = `${spinner}RUNNING &middot; ${elapsed}s`;
      badge.title = forecast ? `Forecast: ${forecast}` : '';
    };
    paint();
    const timer = setInterval(paint, 1000);
    return {
      setLabel(text) { label = text; paint(); },
      setSteps(html) { stepsHtml = html; paint(); },
      stop() { clearInterval(timer); },
    };
  }

  function renderFootnoteSteps(footnotes, activeIndex, failedIndex) {
    if (footnotes.length < 2) return '';
    const chips = footnotes.map((f, i) => {
      const cls = failedIndex === i ? 'failed' : i < activeIndex ? 'done' : i === activeIndex ? 'active' : '';
      return `<span class="step ${cls}">Note ${esc(f)}${i < activeIndex ? ' ✓' : ''}</span>`;
    }).join('');
    return `<div class="footnote-steps">${chips}</div>`;
  }

  // Polls one run to completion/failure. Resolves with the final document view on
  // success; throws with the server's own error message on failure or timeout.
  async function waitForRun(docId, runId, ticker) {
    for (let attempt = 0; attempt < 900; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      const r = await fetch(`/api/documents/${encodeURIComponent(docId)}`);
      if (!r.ok) throw new Error(await responseError(r));
      const d = await r.json(), s = d.status?.state || 'unknown';
      if (ticker) ticker.setLabel(`${runId}: ${s}${d.status?.duration_s ? ` (${d.status.duration_s}s)` : ''}`);
      if (s === 'done') return d;
      if (s === 'error') throw new Error(d.status?.error || 'run failed');
    }
    throw new Error('still running after 30 minutes of polling; it remains visible in the run selector once it finishes');
  }

  async function startWorkbenchRun() {
    const preset=q('#wbPreset').value;
    if(preset==='visual'){q('#wbVisual').click();return;}
    const controlTokens=q('#wbControls').value.split(',').map(x=>x.trim()).filter(Boolean);
    const controls=controlTokens.map(Number);
    const footnoteTokens=q('#wbFootnote').value.split(',').map(x=>x.trim()).filter(Boolean);
    const footnotes=footnoteTokens.map(Number);
    const start=Number(q('#wbStart').value), end=Number(q('#wbEnd').value), label=q('#wbLabel').value, company=q('#wbCompany').value.trim(), periodEnd=q('#wbPeriod').value, currency=q('#wbCurrency').value.trim().toUpperCase(), ocrLang=q('#wbOcrLang').value.trim().toLowerCase();
    const status=q('#wbStatus'); status.hidden=false; status.className='run-progress'; status.textContent='Validating configuration…';
    let currentStepIndex=-1;
    try {
      const file=q('#wbFile').files?.[0], configuredPageCount=state.pendingPdfProfile?.page_count||state.pageCount;
      if(file&&!state.pendingPdfProfile) throw new Error('Wait for the selected PDF inspection to finish successfully.');
      if(!Number.isInteger(start)||!Number.isInteger(end)||start<1||end<start) throw new Error('Summary pages must be whole numbers with start ≤ end.');
      if(!footnotes.length||footnotes.some(x=>!Number.isInteger(x)||x<1)) throw new Error('Target footnote(s) must be one or more comma-separated positive whole numbers.');
      if(!currency) throw new Error('Currency is required; use a code such as TL, TRY or USD.');
      if(!ocrLang) throw new Error('OCR language is required; use a Tesseract code such as tur or eng.');
      if(controls.some(x=>!Number.isInteger(x)||x<1)) throw new Error('Control pages must be comma-separated positive whole numbers.');
      if(controls.some(x=>x>=start&&x<=end)) throw new Error('Calibration-control pages must be outside the summary-page range.');
      if(end>configuredPageCount||controls.some(x=>x>configuredPageCount)) throw new Error(`Configured pages must be within this ${configuredPageCount}-page PDF.`);

      q('.top .status').className='status running';
      const ticker=startProgressTicker(status, `Note ${footnotes[0]}: submitting`, end-start+1);
      let value, lastGood;
      try {
        for (let i=0;i<footnotes.length;i++) {
          currentStepIndex=i;
          const footnote=footnotes[i];
          ticker.setSteps(renderFootnoteSteps(footnotes, i, -1));
          if (i===0 && file) {
            const fd=new FormData();fd.append('file',file);fd.append('summary_pages_start',start);fd.append('summary_pages_end',end);fd.append('footnote_no',footnote);fd.append('extra_control_pages',[...new Set(controls)].join(','));fd.append('label',label||file.name);fd.append('company',company);fd.append('period_end',periodEnd);fd.append('currency',currency);fd.append('ocr_lang',ocrLang);
            let r=await fetch('/api/documents',{method:'POST',body:fd});if(!r.ok)throw new Error(await responseError(r));
            value=await r.json();if(value.sha256!==state.pendingPdfProfile.sha256)throw new Error('Uploaded bytes do not match the inspected fingerprint.');
            r=await fetch(`/api/documents/${encodeURIComponent(value.doc_id)}/run`,{method:'POST'});if(!r.ok)throw new Error(await responseError(r));
          } else {
            const sourceRunId = i===0 ? state.run.run_id : lastGood.run_id;
            const r=await fetch('/api/debugger/configured-run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_run_id:sourceRunId,summary_pages_start:start,summary_pages_end:end,footnote_no:footnote,extra_control_pages:[...new Set(controls)],label:footnotes.length>1?`${label||sourceRunId} (note ${footnote})`:label,company,period_end:periodEnd,currency,ocr_lang:ocrLang})});
            if(!r.ok)throw new Error(await responseError(r));
            value=await r.json();
          }
          ticker.setLabel(footnotes.length>1?`Note ${footnote} (${i+1}/${footnotes.length}): running`:`${value.run_id}: running`);
          const doc=await waitForRun(value.doc_id, value.run_id, ticker);
          lastGood={doc_id:value.doc_id, run_id:value.run_id, doc};
        }
      } finally { ticker.stop(); }

      status.className='run-progress success';
      q('.top .status').textContent='● COMPLETED';q('.top .status').className='status';
      status.innerHTML=(footnotes.length>1?`All ${footnotes.length} footnote runs completed. Opening the last one (Note ${footnotes[footnotes.length-1]}); the earlier ones stay in the run selector above.${renderFootnoteSteps(footnotes,footnotes.length,-1)}`:'Completed.');
      const finalPage=lastGood.doc.summary_pages ? lastGood.doc.summary_pages[0] : start;
      setTimeout(()=>{location.href=`/pdf-debugger.html?run=${encodeURIComponent(lastGood.run_id)}#extracted&page=${finalPage}`;}, footnotes.length>1?900:0);
    } catch(e) {
      q('.top .status').textContent='● ERROR';q('.top .status').className='status error';
      status.className='run-progress error';
      const stepNote=footnotes.length>1&&currentStepIndex>=0?` (failed on note ${footnotes[currentStepIndex]}, step ${currentStepIndex+1}/${footnotes.length}${currentStepIndex>0?'; earlier notes in this batch already completed and stay in the run selector':''})`:'';
      status.innerHTML=`Run not started: ${esc(e.message)}${esc(stepNote)}${renderFootnoteSteps(footnotes,currentStepIndex,currentStepIndex)}`;
    }
  }

  async function responseError(response) {
    try { const body=await response.json(); return body.detail||body.message||`${response.status} ${response.statusText}`; }
    catch (_) { return `${response.status} ${response.statusText}`; }
  }

  async function showRunArtifact(kind) {
    const dialog=ensureWorkbench(); let url;
    if(kind==='compare')url=`/api/compare?a=baseline&b=${encodeURIComponent(state.run.run_id)}`;
    else url=`/api/runs/${encodeURIComponent(state.run.run_id)}/${kind}`;
    try{const r=await fetchWithRetry(url);if(!r.ok)throw new Error(await r.text());const value=await r.json();dialog.close();state.mode='json';state.pageJsonOnly=false;q('#content').innerHTML=`<div class="hero"><div class="eyebrow">${esc(kind)} · ${esc(state.run.run_id)}</div><h1>Run workbench artifact</h1><p>This view is derived from the stored run and does not modify canonical output.</p><button onclick="render()">Back to debugger</button></div><pre class="mono">${esc(JSON.stringify(value,null,2))}</pre>`;}catch(e){q('#wbStatus').hidden=false;q('#wbStatus').textContent=e.message;}
  }

  async function proof() {
    q('#content').innerHTML='<div class="card">Loading run-bound evidence…</div>';
    try {
      if(!state.proof){const r=await fetchWithRetry(`/api/debugger/proof?run_id=${encodeURIComponent(state.run.run_id)}`);if(!r.ok)throw new Error(await responseError(r));state.proof=await r.json();}
      const p=state.proof, input=p.input, cfg=p.configuration.echo||{}, exec=p.execution, out=p.output, uploaded=p.uploaded_document;
      q('#content').innerHTML=`<div class="hero"><div class="eyebrow">Run proof · ${esc(p.run_id)}</div><h1>This output is bound to real input bytes and configuration</h1><p>Use this view when asked whether the demo is static. Hashes are computed from the loaded PDF, stored result and pipeline source—not typed into the UI.</p><div class="data-tools"><button onclick="copyText('${esc(input.actual_sha256)}')">Copy input hash</button><button onclick="copyText('${esc(out.result_sha256)}')">Copy output hash</button><button onclick="document.querySelector('[data-mode=json]').click()">Inspect canonical JSON</button></div></div>
        <section class="card ${input.sha256_match?'proof-ok':'proof-bad'}"><h3>1 · Exact input fingerprint ${input.sha256_match?'matches result claim':'MISMATCH'}</h3><p>${esc(input.filename)} · ${input.size_bytes} bytes</p><div class="proof-hash">actual ${esc(input.actual_sha256)}<br>result ${esc(input.result_claimed_sha256)}</div>${uploaded?`<p>Uploaded ${esc(uploaded.uploaded_at)} · document ID ${esc(uploaded.doc_id)} · ${esc(uploaded.profile?.source_kind||'unknown source kind')} · ${uploaded.profile?.page_count||state.pageCount} pages</p>`:''}</section>
        <section class="card proof-ok"><h3>2 · Configuration echo</h3><p>Summary pages <b>${esc(cfg.document?.summary_pages?.join('–'))}</b> · target Note <b>${esc(cfg.document?.footnote_no)}</b> · OCR ${esc(cfg.ocr?.dpi)} DPI / PSM ${esc(cfg.ocr?.psm)} · candidate top-k ${esc(cfg.candidates?.top_k)} · link threshold ${esc(cfg.linking?.accept_threshold)}</p><div class="proof-hash">configuration SHA-256 ${esc(p.configuration.sha256)}</div><details><summary>Full persisted configuration</summary><pre class="mono">${esc(JSON.stringify(cfg,null,2))}</pre></details></section>
        <section class="card proof-ok"><h3>3 · Real execution and model evidence</h3><p>Started ${esc(exec.result_started_at||'stored legacy run')} · state ${esc(exec.state)} · duration ${esc(exec.duration_s??'not recorded')}s · cross-encoder loaded ${esc(exec.models_loaded?.cross_encoder)}</p><div class="proof-hash">pipeline source SHA-256 ${esc(exec.pipeline_code_sha256)}</div><p class="small">Changing source code, configuration or input bytes changes its corresponding fingerprint.</p></section>
        <section class="card proof-ok"><h3>4 · Generated output fingerprint</h3><div class="metrics"><div class="metric"><b>${out.counts.tables}</b><span>tables</span></div><div class="metric"><b>${out.counts.rows}</b><span>rows</span></div><div class="metric"><b>${out.counts.cells}</b><span>cells</span></div><div class="metric"><b>${out.counts.relations}</b><span>relations</span></div></div><p>${out.non_pass_checks} non-pass checks remain visible; a fresh run is allowed to fail rather than being replaced by baseline data.</p><div class="proof-hash">result SHA-256 ${esc(out.result_sha256)} · ${out.size_bytes} bytes</div></section>
        <section class="card issue"><h3>Honest boundary</h3><p>Cryptographic binding proves which bytes, config and code produced the stored artifact. It does not prove correctness on every PDF; correctness still requires validation and independently authored ground truth.</p></section>`;
    } catch(e) {q('#content').innerHTML=`<div class="card issue"><b>Run proof unavailable</b><p>${esc(e.message)}</p></div>`;}
  }

  relationCard = function (rel) {
    const s=ix.rows.get(rel.summary_row_id), f=ix.rows.get(rel.footnote_row_id), sp=pageFor(rel.summary_row_id), fp=pageFor(rel.footnote_row_id);
    return `<button class="relbtn ${state.selected?.id===rel.relation_id?'selected':''}" onclick="select('relation','${rel.relation_id}',${sp})"><b>${esc(s?.label_raw)}</b> → ${esc(f?.label_raw)} <span class="chip">${esc(rel.period_scope)}</span><span class="chip ${rel.low_confidence?'bad':'good'}">${rel.confidence.toFixed(2)} ${rel.low_confidence?'review':''}</span><br><span class="small">summary p${sp} · Note target p${fp} · ${esc(rel.evidence)}</span></button>`;
  };

  review = function () {
    const r=state.run.result, rel=r.relations, issues=r.checks.filter(x=>x.status!=='pass'), obj=selectedObject();
    const c=r.run?.config_echo?.document||{}, summary=c.summary_pages?.join('–')||'n/a', footnote=c.footnote_no||'n/a';
    let html=`<div class="hero"><div class="eyebrow">Review desk · ${esc(state.run.run_id)}</div><h1>Trace every result to its PDF evidence</h1><p><b>${esc(contractName())}</b> · configured summary pages ${summary} · footnote ${footnote}. Current page: ${esc(scopeText())}</p><div class="data-tools"><button onclick="openWorkbench()">Change scope / PDF</button><button onclick="document.querySelector('[data-mode=extracted]').click()">Inspect page data</button></div></div><div class="metrics"><div class="metric"><b>${r.tables.length}</b><span>tables</span></div><div class="metric"><b>${r.rows.length}</b><span>rows</span></div><div class="metric"><b>${r.relations.length}</b><span>relation edges</span></div><div class="metric"><b class="bad">${issues.length}</b><span>non-pass checks</span></div></div>`;
    if (obj?.relation_id) {
      const s=ix.rows.get(obj.summary_row_id), f=ix.rows.get(obj.footnote_row_id), sp=pageFor(obj.summary_row_id), fp=pageFor(obj.footnote_row_id);
      html+=`<div class="card"><div class="eyebrow">Selected relation ${esc(obj.relation_id)}</div><h3>${esc(s?.label_raw)} → ${esc(f?.label_raw)}</h3><p>${esc(obj.evidence)}</p><span class="chip">${esc(obj.relation_type)}</span><span class="chip">confidence ${obj.confidence.toFixed(2)}</span><p><button onclick="select('row','${obj.summary_row_id}',${sp})">Summary source · page ${sp}</button> <button onclick="select('row','${obj.footnote_row_id}',${fp})">Note target · page ${fp}</button></p></div>`;
    } else if (obj?.value) {
      html+=`<div class="card"><div class="eyebrow">Selected cell ${esc(obj.cell_id)}</div><h3>${esc(ix.rows.get(obj.row_id)?.label_raw)} · ${esc(obj.period_id)}</h3><p>Raw <b>${esc(obj.value.raw||'empty')}</b> → parsed <b>${esc(obj.value.value??obj.value.state)}</b></p><span class="chip ${obj.confidence<=.5?'bad':'good'}">confidence ${obj.confidence.toFixed(2)}</span></div>`;
    } else if (obj) {
      html+=`<div class="card"><div class="eyebrow">Selected ${esc(state.selected.kind)}</div><h3>${esc(obj.label_raw||obj.title||obj.table_id)}</h3><p>page ${pageFor(state.selected.id)} · confidence ${obj.confidence?.toFixed?.(2)??'n/a'}</p></div>`;
    }
    const relationList=rel.length?rel.map(relationCard).join(''):`<div class="card scope-note"><b>No relations emitted</b><p>This run has no relation endpoint to navigate. Inspect configured summary rows, note references, located tables and coverage checks; zero is not automatically a correct negative.</p></div>`;
    html+=`<div class="tabs"><b>Relations</b><span class="small">summary source → footnote target</span></div>${relationList}<div class="card issue"><b>Issue queue · persisted evidence</b><p>${issues.length?issues.slice(0,5).map(x=>esc(x.check_id)+': '+esc(x.detail)).join('<br>'):'No non-pass check persisted for this run.'}</p><span class="small">Fail and not-evaluable are shown separately in canonical data; neither is an automatic correctness judgment.</span></div>`;
    q('#content').innerHTML=html;
  };

  json = function () {
    const value=state.pageJsonOnly?pageData():state.run.result;
    q('#content').innerHTML=`<div class="hero"><div class="eyebrow">${state.pageJsonOnly?'Page-local':'Canonical'} JSON</div><h1>${state.pageJsonOnly?'Page '+state.page:'Loaded result.json'}</h1><p>Canonical download remains byte-preserving. Page-local JSON is a debugger view.</p><input class="search" id="search" placeholder="Filter visible lines"><div class="tabs"><button id="toggleWrap">${state.wrapJson?'Disable':'Enable'} wrap</button><button id="toggleJsonScope">Show ${state.pageJsonOnly?'full result':'current page only'}</button><button onclick="navigator.clipboard?.writeText(JSON.stringify(${state.pageJsonOnly?'pageData()':'state.run.result'},null,2))">Copy object</button></div></div><pre class="mono ${state.wrapJson?'':'nowrap'}">${esc(JSON.stringify(value,null,2))}</pre>`;
    q('#toggleWrap').onclick=()=>{state.wrapJson=!state.wrapJson;json();};
    q('#toggleJsonScope').onclick=()=>{state.pageJsonOnly=!state.pageJsonOnly;json();};
  };

  render = function () {
    renderPage();
    q('#selectionText').textContent=state.selected?`${state.selected.kind} · ${state.selected.id}`:scopeText();
    state.mode==='guide'?guide():state.mode==='review'?review():state.mode==='debug'?debug():state.mode==='extracted'?extracted():state.mode==='proof'?proof():json();
    document.querySelectorAll('.mode').forEach(x=>x.classList.toggle('active',x.dataset.mode===state.mode));
    const hp=new URLSearchParams({page:String(state.page)}); if(state.selected) hp.set('object',state.selected.id);
    history.replaceState(null,'',`?run=${encodeURIComponent(state.run.run_id)}#${state.mode}&${hp}`);
  };

  extractedMode.onclick=()=>{state.mode='extracted';render();};
  guideMode.onclick=()=>{state.mode='guide';render();};
  proofMode.onclick=()=>{state.mode='proof';render();};
  document.querySelectorAll('.mode').forEach(x=>x.onclick=()=>{state.mode=x.dataset.mode;render();});
  document.querySelector('[data-layer="row"]')?.closest('label')?.insertAdjacentHTML('beforebegin','<label><input type="checkbox" data-layer="table" checked> tables</label>');
  document.querySelector('[data-layer="warn"]')?.closest('label')?.insertAdjacentHTML('beforebegin','<label><input type="checkbox" data-layer="relation" checked> relations</label>');
  document.querySelector('.legend')?.insertAdjacentHTML('afterbegin','<span><i class="dot table"></i>table</span>');
  document.querySelectorAll('[data-layer]').forEach(x=>{state.layer[x.dataset.layer]=x.checked;x.onchange=()=>{state.layer[x.dataset.layer]=x.checked;renderPage();};});

  function annotationBody() { return localStorage.getItem('ftlink-debugger-annotations') || ''; }
  function exportAnnotations() {
    if (location.pathname.includes('pdf-debugger')) { location.href='/api/debugger/annotations/export?format=jsonl'; return; }
    const body = annotationBody();
    const blob = new Blob([body], {type: 'application/x-ndjson'}), a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'ftlink-debugger-annotations.jsonl'; a.click(); URL.revokeObjectURL(a.href);
  }
  annotationButton.onclick = exportAnnotations;

  async function postAnnotation(value) {
    try { const r=await fetch('/api/debugger/annotations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)}); if (!r.ok) throw new Error('server rejected annotation'); return true; }
    catch (_) { const old=annotationBody(); localStorage.setItem('ftlink-debugger-annotations',old+JSON.stringify(value)+'\n'); return false; }
  }
  const issueForm = q('#saveIssue');
  if (issueForm) issueForm.onclick = async (event) => {
    event.preventDefault();
    const value={schema_version:'debugger.annotation.v1',decision:q('#decision').value,issue_family:q('#family').value,note:q('#note').value,severity:q('#severity').value,object_ids:state.selected?[state.selected.id]:[],document_sha256:state.run.result.document.source_sha256,run_id:state.run.run_id,timestamp:new Date().toISOString()};
    const serverSaved=await postAnnotation(value); q('#issue')?.close(); alert(serverSaved?'Saved to the local debugger annotation store.':'Saved to browser-local JSONL fallback.');
  };
  importButton.onclick = () => { const input=document.createElement('input'); input.type='file'; input.accept='.jsonl,.ndjson,.json'; input.onchange=async()=>{ try { const text=await input.files[0].text(); const values=text.trim().startsWith('[')?JSON.parse(text):text.trim().split(/\n+/).map(JSON.parse); if(!Array.isArray(values)||!values.length) throw new Error('empty bundle'); values.forEach(v=>{if(v.schema_version!=='debugger.annotation.v1'||v.run_id!==state.run.run_id||!Array.isArray(v.object_ids)) throw new Error('schema/run mismatch');}); if(!confirm(`Import ${values.length} annotation(s)? They remain separate from pipeline output.`)) return; for(const v of values) await postAnnotation(v); alert('Validated and imported.'); } catch(e) { alert('Import rejected: '+e.message); } }; input.click(); };

  function showTour(step) {
    const ctx=runContext(), baselineErrors=ctx.isBaseline&&ix.cells.has('p05.t00.r007.c00')&&ix.cells.has('p05.t00.r010.c00');
    const steps = baselineErrors ? [
      {title:'1 · Baseline digit substitution', text:'This is baseline-only evidence: Stoklar is read as 77.943.097. Engine disagreement and a parent-sum inconsistency remain visible.', action:()=>select('cell','p05.t00.r007.c00')},
      {title:'2 · Baseline separator corruption', text:'This is baseline-only evidence: Financial Investments is raw 4,224 but parsed as 4.224. Financial validation catches what engine agreement misses.', action:()=>select('cell','p05.t00.r010.c00')},
      ctx.firstRelation
        ? {title:'3 · Why linked?', text:'Inspect the first emitted relation and compare its value/role, semantic and lexical evidence. No single mechanism is implied.', action:()=>select('relation',ctx.firstRelation.relation_id,ctx.relationSourcePage)}
        : {title:'3 · No emitted relation', text:'This run emitted zero relations. Inspect coverage and locator checks; absence is not automatically a correct negative.', action:()=>{state.page=ctx.summaryStart;state.mode='review';state.selected=null;render();}},
      {title:'4 · Complaint to improvement', text:'Create a separate annotation and explain that adjudication, benchmarking and release are proposed—not automatic learning.', action:()=>q('#annotate')?.click()}
    ] : [
      {title:'1 · Run-specific scope', text:`This tour is bound to ${state.run.run_id}: summary pages ${ctx.summaryStart}–${ctx.summaryEnd}, Note ${ctx.footnoteNo}. Baseline errors and gold metrics are intentionally not reused.`, action:()=>{state.page=ctx.summaryStart;state.mode='guide';state.selected=null;render();}},
      ctx.firstCell
        ? {title:'2 · Inspect emitted evidence', text:'Focus an emitted cell and compare its raw value, parsed state, confidence and PDF provenance.', action:()=>select('cell',ctx.firstCell.cell_id,pageFor(ctx.firstCell.cell_id))}
        : {title:'2 · No emitted cell', text:'This run emitted no cells. Inspect extraction and structural checks rather than showing baseline cell evidence.', action:()=>{state.page=ctx.summaryStart;state.mode='extracted';state.selected=null;render();}},
      ctx.firstRelation
        ? {title:'3 · Inspect an emitted relation', text:'Follow this run’s summary source and note target. The relation is evidence for this configuration only.', action:()=>select('relation',ctx.firstRelation.relation_id,ctx.relationSourcePage)}
        : {title:'3 · No emitted relation', text:'This run emitted zero relations. Check whether that is explained by zero reference-bearing rows, failed location, or failed relation coverage.', action:()=>{state.page=ctx.summaryStart;state.mode='review';state.selected=null;render();}},
      {title:'4 · Preserve review evidence', text:'Create a separate annotation or export the run proof. Neither action modifies canonical output or creates ground truth.', action:()=>q('#annotate')?.click()}
    ];
    let box = q('.tour'); if (!box) { box=document.createElement('div'); box.className='tour card'; document.body.appendChild(box); }
    const item=steps[step]; item.action(); box.innerHTML=`<h3>${item.title}</h3><p>${item.text}</p><div class="tour-actions"><button id="tourExit">Exit</button>${step?'<button id="tourBack">Back</button>':''}${step<steps.length-1?'<button id="tourNext">Next</button>':'<button id="tourDone">Done</button>'}</div>`;
    q('#tourExit').onclick=()=>box.remove(); q('#tourBack')?.addEventListener('click',()=>showTour(step-1)); q('#tourNext')?.addEventListener('click',()=>showTour(step+1)); q('#tourDone')?.addEventListener('click',()=>box.remove());
  }
  tourButton.onclick=()=>showTour(0);

  document.addEventListener('input', (event) => { if (event.target.id !== 'search') return; const query=event.target.value.toLowerCase(); const pre=document.querySelector('.mono'); if (!pre || !state.run) return; const raw=JSON.stringify(state.pageJsonOnly?pageData():state.run.result,null,2); pre.textContent=query ? raw.split('\n').filter(line=>line.toLowerCase().includes(query)).join('\n') || 'No matching persisted field.' : raw; });

  const help = q('#helpDialog');
  if (help) { const p=document.createElement('div'); p.className='muted'; p.innerHTML='<p><b>Review:</b> select a relation, then use its explicit summary-source and note-target buttons.</p><p><b>Extracted:</b> inspect all emitted columns and values; click any object to focus the PDF box. Widen or maximize the panel when comparing dense tables.</p><p><b>Configure / upload / run:</b> choose the assignment contract, an experiment or a custom PDF configuration. Full-document visual review does not claim full-document extraction accuracy.</p><p><b>Keyboard:</b> ←/→ changes page; Escape closes dialogs. Rotate 90° changes only the review view and never canonical coordinates.</p>'; help.querySelector('button')?.before(p); }
  document.addEventListener('keydown', (e) => { if (e.key==='ArrowLeft') q('#prev')?.click(); if (e.key==='ArrowRight') q('#next')?.click(); if (e.key==='Escape') document.querySelectorAll('dialog[open]').forEach(d=>d.close()); });

  q('#prev').onclick=()=>{state.page=Math.max(1,state.page-1);state.selected=null;render();};
  q('#next').onclick=()=>{state.page=Math.min(state.pageCount,state.page+1);state.selected=null;render();};
  q('#export').onclick=()=>{location.href=`/api/debugger/canonical?run_id=${encodeURIComponent(state.run.run_id)}`;};
  downloadView = function () { const value={schema_version:'debugger.view.v1',run_id:state.run.run_id,page:state.page,selection:state.selected,created_at:new Date().toISOString()}; const b=new Blob([JSON.stringify(value,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=`${state.run.run_id}-debugger-view.json`;a.click();URL.revokeObjectURL(a.href); };

  async function loadDebuggerRun(runId) {
    const response=await fetchWithRetry(`/api/debugger/run?run_id=${encodeURIComponent(runId)}`);
    if(!response.ok) throw new Error(await response.text());
    state.run=await response.json(); state.pageCount=state.run.page_count; state.viewRotations={}; state.proof=null; state.pendingPdfProfile=null; ix=indexes(state.run.result);
    q('.top .status').textContent='● COMPLETED';q('.top .status').className='status';
    guideMode.textContent=state.run.run_id==='baseline'?'Case guide':'Run guide';
    const hash=location.hash.slice(1), mode=hash.split('&')[0];
    if(['guide','review','debug','extracted','proof','json'].includes(mode)) state.mode=mode;
    const hp=new URLSearchParams(hash.includes('&')?hash.slice(hash.indexOf('&')+1):'');
    const requestedPage=Number(hp.get('page'));
    const range=state.run.result.run?.config_echo?.document?.summary_pages;
    state.page=Number.isInteger(requestedPage)&&requestedPage>=1&&requestedPage<=state.pageCount?requestedPage:(range?.[0]||1);
    const id=hp.get('object'); state.selected=null;
    if(id && (ix.cells.has(id)||ix.rows.has(id)||ix.rels.has(id)||ix.tables.has(id))) state.selected={kind:ix.cells.has(id)?'cell':ix.rows.has(id)?'row':ix.rels.has(id)?'relation':'table',id};
    const baselineShortcuts=state.run.run_id==='baseline';
    q('#stok').disabled=!baselineShortcuts||!ix.cells.has('p05.t00.r007.c00'); q('#fin').disabled=!baselineShortcuts||!ix.cells.has('p05.t00.r010.c00');
    const knownErrorCard=q('#stok')?.closest('.card'); if(knownErrorCard) knownErrorCard.hidden=!baselineShortcuts;
    render();
  }

  async function initRuns() {
    const requested=new URLSearchParams(location.search).get('run')||'baseline', selectRun=q('#run');
    const response=await fetch('/api/debugger/runs'); const runs=await response.json();
    selectRun.innerHTML=runs.map(x=>`<option value="${esc(x.run_id)}">${esc(x.label)}${x.group?` · ${esc(x.group)}`:''} · completed</option>`).join('');
    selectRun.value=runs.some(x=>x.run_id===requested)?requested:'baseline';
    selectRun.onchange=()=>{location.href=`/pdf-debugger.html?run=${encodeURIComponent(selectRun.value)}#review`;};
    await loadDebuggerRun(selectRun.value);
  }
  initRuns().catch(e=>{q('#content').innerHTML=`<div class="card issue">Unable to load debugger run: ${esc(e.message)}</div>`;});
})();
