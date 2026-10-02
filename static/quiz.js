/* 共用刷題元件：drill / reading / listening / placement / wrongs / marks 都用這個
   功能：逐字中文翻譯、標記題目、答題後即時向 AI 發問 */
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

/* 中文預設藏起來：整句用按鈕顯示，單字可以個別點開 */
function zhOn() { return localStorage.getItem('showZh') === '1'; }

function glossHTML(tokens, show) {
  if (!tokens || !tokens.length) return '';
  return tokens.map(t => {
    if (t.sp) return ' ';
    const w = esc(t.w).replace(/_{2,}/, '<b style="color:var(--accent)">______</b>');
    if (!t.zh) return '<span class="gl"><b>' + w + '</b></span>';
    return '<span class="gl has-zh" data-zh="' + esc(t.zh) + '"><b>' + w + '</b>' +
      '<i' + (show ? '' : ' hidden') + '>' + esc(t.zh) + '</i></span>';
  }).join('');
}

/* 讓容器裡的單字可以點一下看中文，再點一下收起來 */
function wireWordTap(el) {
  if (!el) return;
  el.addEventListener('click', e => {
    const g = e.target.closest('.gl.has-zh');
    if (!g || !el.contains(g)) return;
    const i = g.querySelector('i');
    if (i) i.hidden = !i.hidden;
  });
}

/* 給整頁用的「顯示全部中文」按鈕 */
function toggleAllZh(scope, btn) {
  const on = !zhOn();
  localStorage.setItem('showZh', on ? '1' : '0');
  (scope || document).querySelectorAll('.gl.has-zh i').forEach(i => { i.hidden = !on; });
  if (btn) btn.textContent = on ? '隱藏中文' : '顯示中文';
  return on;
}

function Quiz(opts) {
  const box = document.getElementById(opts.mount);
  let items = [], idx = 0, t0 = 0, results = [], answered = false, chosenIdx = null;
  let showZh = zhOn();

  async function load() {
    box.innerHTML = '<p class="muted"><span class="spin"></span>出題中…</p>';
    try {
      const r = await fetch(opts.url);
      const d = await r.json();
      if (d.error) { box.innerHTML = '<div class="err">' + esc(d.error) + '</div>'; return; }
      items = Array.isArray(d) ? d : d.items;
      if (!items || !items.length) {
        box.innerHTML = '<div class="err">題庫裡還沒有符合條件的題目。</div>'; return;
      }
      if (opts.onload) opts.onload(d);
      idx = 0; results = [];
      render();
    } catch (e) {
      box.innerHTML = '<div class="err">載入失敗：' + esc(e.message) + '</div>';
    }
  }

  function render() {
    if (idx >= items.length) return finish();
    const it = items[idx];
    answered = false; chosenIdx = null; t0 = Date.now();
    box.innerHTML = `
      <div class="row" style="margin-bottom:6px">
        <span class="muted">第 ${idx + 1} / ${items.length} 題</span>
        <span class="spacer"></span>
        <span class="tag">${esc(it.skill_zh)}</span>
        <span class="tag">${esc(it.tag_zh)}</span>
        <span class="tag">${esc(it.level_zh)}</span>
        <button class="btn sm ghost" id="zhbtn" title="鍵盤 Z">${showZh ? '隱藏中文' : '顯示中文'}</button>
        <button class="btn sm ghost" id="mkbtn">${it.marked ? '★ 已標記' : '☆ 標記'}</button>
      </div>
      <div class="bar" style="margin-bottom:14px"><i style="width:${idx / items.length * 100}%"></i></div>
      ${it.skill === 'cloze' && it.passage ? '<div class="passage gw" id="psg"></div>' : ''}
      <div class="stem gw" id="stem"></div>
      <div id="opts"></div>
      <div class="row" id="dkrow">
        <button class="btn ghost" id="dkbtn" title="鍵盤 0">🤷 我不會，直接看答案</button>
        <span class="muted">不用猜，按了不算你答錯，但這題會排進複習</span>
      </div>
      <div id="fb"></div>`;

    const psg = document.getElementById('psg');
    if (psg) {
      psg.innerHTML = (it.passage_g && it.passage_g.length)
        ? glossHTML(it.passage_g, showZh) : esc(it.passage);
      wireWordTap(psg);
    }
    const stemEl = document.getElementById('stem');
    stemEl.innerHTML =
      (it.stem_g && it.stem_g.length) ? glossHTML(it.stem_g, showZh)
        : esc(it.stem).replace(/____/g, '<b style="color:var(--accent)">______</b>');
    wireWordTap(stemEl);

    const wrap = box.querySelector('#opts');
    it.options.forEach((o, i) => {
      const b = document.createElement('button');
      b.className = 'opt gw';
      const g = it.opts_g && it.opts_g[i];
      b.innerHTML = '<b style="color:var(--dim);margin-right:8px">' + 'ABCD'[i] + '</b>' +
        ((g && g.length) ? glossHTML(g, showZh) : esc(o));
      b.onclick = () => choose(i);
      wrap.appendChild(b);
    });

    box.querySelector('#zhbtn').onclick = e => {
      showZh = toggleAllZh(box, e.currentTarget);
    };
    box.querySelector('#mkbtn').onclick = () => toggleMark(it);
    box.querySelector('#dkbtn').onclick = () => choose(-1);
  }

  async function toggleMark(it) {
    const b = box.querySelector('#mkbtn');
    b.disabled = true;
    try {
      const r = await fetch('/api/mark', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: it.id })
      });
      const d = await r.json();
      it.marked = d.marked;
      b.textContent = d.marked ? '★ 已標記' : '☆ 標記';
    } catch (e) { alert('標記失敗：' + e.message); }
    b.disabled = false;
  }

  async function choose(i) {
    if (answered) return;
    answered = true; chosenIdx = i;
    const dk = (i === -1);
    const it = items[idx];
    const secs = (Date.now() - t0) / 1000;
    const btns = [...box.querySelectorAll('.opt')];
    btns.forEach(b => b.disabled = true);
    let d;
    try {
      const r = await fetch('/api/answer', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: it.id, chosen: i, seconds: secs, mode: opts.mode || 'drill' })
      });
      d = await r.json();
    } catch (e) { d = { correct: false, answer: 0, explain_zh: '（無法連線）' }; }

    btns[d.answer] && btns[d.answer].classList.add('ok');
    if (!d.correct && !dk && btns[i]) btns[i].classList.add('bad');
    const dkrow = box.querySelector('#dkrow');
    if (dkrow) dkrow.remove();
    results.push({ id: it.id, correct: d.correct, dk: dk, tag_zh: it.tag_zh });

    const v = (d.vocab || []).map(w =>
      `<span class="tag">${esc(w.w)} ${esc(w.pos || '')} ${esc(w.zh)}</span>`).join('');
    const fu = d.followup_zh
      ? '<div style="margin-top:9px;color:var(--warn)">💡 ' + esc(d.followup_zh) + '</div>' : '';

    box.querySelector('#fb').innerHTML = `
      <div class="explain">
        <div style="font-weight:700;color:${d.correct ? 'var(--ok)' : dk ? 'var(--warn)' : 'var(--bad)'};margin-bottom:6px">
          ${d.correct ? '✓ 答對了'
        : dk ? '🤷 這題你按了「我不會」，正解是 ' + 'ABCD'[d.answer] + '，先看懂解析，之後會再出一次'
          : '✗ 答錯了，正解是 ' + 'ABCD'[d.answer]}
        </div>
        <div>${esc(d.explain_zh)}</div>
        ${v ? '<div style="margin-top:9px">' + v + '</div>' : ''}${fu}
      </div>

      <div class="card" style="margin:12px 0;background:#141c2c">
        <div class="row">
          <b>還是不懂？直接問</b>
          <span class="muted" style="font-size:13px">會叫 AI 來回答，約 20 秒</span>
        </div>
        <div class="row" style="margin-top:8px">
          <input id="qin" placeholder="例如：為什麼不能選 B？這裡的 since 是什麼用法？"
                 style="flex:1;min-width:200px">
          <button class="btn sm" id="qbtn">問</button>
        </div>
        <div class="row" style="margin-top:8px">
          <button class="btn sm ghost qq">為什麼我選的不對？</button>
          <button class="btn sm ghost qq">這個考點的規則是什麼？</button>
          <button class="btn sm ghost qq">再給我兩個例句</button>
        </div>
        <div id="qout"></div>
      </div>

      <div class="row" style="margin-top:6px">
        <button class="btn" id="nx">${idx + 1 >= items.length ? '看成績' : '下一題 →'}</button>
        <span class="muted">按 Enter 也可以</span>
      </div>`;

    const qin = box.querySelector('#qin');
    box.querySelector('#qbtn').onclick = () => askAI(it, qin.value);
    qin.onkeydown = e => { if (e.key === 'Enter') { e.stopPropagation(); askAI(it, qin.value); } };
    box.querySelectorAll('.qq').forEach(b =>
      b.onclick = () => { qin.value = b.textContent; askAI(it, b.textContent); });

    const nx = box.querySelector('#nx');
    nx.focus();
    nx.onclick = () => { idx++; render(); };
  }

  async function askAI(it, q) {
    q = (q || '').trim();
    if (q.length < 2) { alert('先打出你的問題'); return; }
    const out = box.querySelector('#qout');
    const btn = box.querySelector('#qbtn');
    btn.disabled = true;
    out.innerHTML = '<p class="muted"><span class="spin"></span>老師想一下…</p>';
    try {
      const r = await fetch('/api/ask', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: it.id, question: q, chosen: chosenIdx })
      });
      const d = await r.json();
      if (d.error) { out.innerHTML = '<div class="err">' + esc(d.error) + '</div>'; }
      else {
        const ex = (d.examples || []).map(e =>
          `<li><b>${esc(e.en)}</b><br><span class="muted">${esc(e.zh)}</span></li>`).join('');
        out.innerHTML = `
          <div class="explain" style="margin-top:10px">
            <div style="white-space:pre-wrap">${esc(d.answer_zh)}</div>
            <div style="margin-top:10px"><b>規則</b><br>${esc(d.rule_zh)}</div>
            ${ex ? '<div style="margin-top:10px"><b>例句</b><ul class="clean">' + ex + '</ul></div>' : ''}
            <div style="margin-top:10px;color:var(--ok)">🔑 ${esc(d.remember_zh)}</div>
          </div>`;
      }
    } catch (e) { out.innerHTML = '<div class="err">連線失敗：' + esc(e.message) + '</div>'; }
    btn.disabled = false;
  }

  function finish() {
    const ok = results.filter(r => r.correct).length;
    const dkN = results.filter(r => r.dk).length;
    const wrongN = results.length - ok - dkN;
    const pct = Math.round(ok / results.length * 100);
    const bad = {};
    results.filter(r => !r.correct).forEach(r => bad[r.tag_zh] = (bad[r.tag_zh] || 0) + 1);
    const list = Object.entries(bad).sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `<span class="tag bad">${esc(k)} 錯 ${v} 題</span>`).join('');
    box.innerHTML = `
      <div style="text-align:center;padding:24px 0">
        <div class="big" style="color:${pct >= 80 ? 'var(--ok)' : pct >= 60 ? 'var(--warn)' : 'var(--bad)'}">${pct}%</div>
        <p class="muted">答對 ${ok} 題　·　答錯 ${wrongN} 題　·　不會 ${dkN} 題　（共 ${results.length} 題）</p>
        ${list ? '<div style="margin:16px 0">這次的弱點：<br>' + list + '</div>'
        : '<p style="color:var(--ok)">全對！這批標籤你已經穩了 👍</p>'}
        <div class="row" style="justify-content:center;margin-top:18px">
          <button class="btn" onclick="location.reload()">再來一輪</button>
          <a class="btn ghost" href="/">回首頁</a>
        </div>
      </div>`;
    if (opts.onfinish) opts.onfinish(results);
  }

  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    const nx = document.getElementById('nx');
    if (e.key === 'Enter' && nx) { e.preventDefault(); nx.click(); return; }
    if (e.key === 'z' || e.key === 'Z') {
      const zb = document.getElementById('zhbtn'); if (zb) zb.click(); return;
    }
    if (e.key === 'm' || e.key === 'M') {
      const mk = document.getElementById('mkbtn'); if (mk) mk.click(); return;
    }
    if (!answered && e.key === '0') {
      const db = document.getElementById('dkbtn'); if (db) db.click(); return;
    }
    if (!answered && /^[1-4a-dA-D]$/.test(e.key)) {
      const i = '1234'.indexOf(e.key) >= 0 ? '1234'.indexOf(e.key)
        : 'abcd'.indexOf(e.key.toLowerCase());
      const b = box.querySelectorAll('.opt')[i];
      if (b) b.click();
    }
  });

  load();
  return { reload: load };
}
