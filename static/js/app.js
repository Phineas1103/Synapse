/* 
   Synapse — 
    */

const API = 'http://127.0.0.1:18090';

//   
let state = {
  currentPage: 'home',
  currentProject: null,
  currentChapter: 0,
  presets: null,
  projectChats: {},
};

// 
//  
// 

function navigateTo(page) {
  const currentPage = document.querySelector('.page.active');
  const target = document.getElementById(`page-${page}`);

  // Update menu items
  document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('active'));
  const menuItem = document.querySelector(`.menu-item[data-page="${page}"]`);
  if (menuItem) menuItem.classList.add('active');

  state.currentPage = page;

  if (currentPage && currentPage !== target && typeof gsap !== 'undefined') {
    // Animated transition
    gsap.to(currentPage, {
      opacity: 0, y: -20, duration: 0.2, ease: 'power2.in',
      onComplete: () => {
        currentPage.classList.remove('active');
        currentPage.style.cssText = '';
        if (target) {
          target.classList.add('active');
          gsap.fromTo(target,
            { opacity: 0, y: 30 },
            { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' }
          );
        }
      }
    });
  } else {
    // Instant fallback
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    if (target) target.classList.add('active');
  }

  if (page === 'projects') loadProjects();
  if (page === 'settings') loadSettings();
}

function openApiRelay() {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.open_external_window('https://toapis.com/login?aff=PSJx');
  } else {
    window.open('https://toapis.com/login?aff=PSJx', '_blank');
  }
}

// 
//  
// 


// 
//  API 
// 

async function api(url, method = 'GET', body = null, timeoutMs = 30000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const opts = { method, signal: controller.signal };
  if (body instanceof FormData) {
    opts.body = body;
  } else {
    opts.headers = { 'Content-Type': 'application/json' };
    if (body) opts.body = JSON.stringify(body);
  }
  try {
    const resp = await fetch(API + url, opts);
    clearTimeout(timer);
    if (!resp.ok) {
      let err;
      try { err = await resp.json(); } catch(e) { err = { detail: resp.statusText }; }
      let msg = err.detail || err.message || resp.statusText;
      if (typeof msg === 'object') msg = JSON.stringify(msg);
      throw new Error(msg);
    }
    return resp.json();
  } catch(e) {
    clearTimeout(timer);
    if (e.name === 'AbortError') throw new Error('请求超时');
    throw e;
  }
}

function esc(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function showNotification(msg, type = 'success') {
  let container = document.getElementById('notification-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'notification-container';
    container.style.cssText = 'position:fixed;top:20px;right:20px;z-index:10000;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(container);
  }
  const n = document.createElement('div');
  n.className = 'notification glass-card';
  n.style.cssText = 'padding:12px 24px;border-radius:12px;font-size:14px;animation:slideIn 0.3s ease;color:var(--text-primary);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.1);';
  if (type === 'error') {
    n.style.background = 'rgba(239,68,68,0.2)';
    n.style.borderColor = 'rgba(239,68,68,0.3)';
  } else {
    n.style.background = 'rgba(34,197,94,0.2)';
    n.style.borderColor = 'rgba(34,197,94,0.3)';
  }
  n.textContent = msg;
  container.appendChild(n);
  setTimeout(() => { n.style.opacity = '0'; setTimeout(() => n.remove(), 300); }, 3000);
}

function showLoading(text = '...') {
  const overlay = document.getElementById('loading-overlay');
  const loadingText = document.getElementById('loading-text');
  if (overlay) { overlay.classList.add('show'); }
  if (loadingText) { loadingText.textContent = text; }
}

function hideLoading() {
  const overlay = document.getElementById('loading-overlay');
  if (overlay) { overlay.classList.remove('show'); }
}


// ═══ Liquid Glass Loading Manager ═══
let _synapseProgressInterval = null;
let _synapsePhaseInterval = null;

const _outlinePhaseTexts = [
  "正在架构宏观剧本世界观与多线因果律...",
  "正在雕刻核心人物冲突，注入反同质化协议锚点...",
  "正在淬炼前3秒黄金冷开场钩子...",
  "正在编排30集剧烈情节剧情钩子(Cliffhangers)...",
  "正在对30集大纲执行结构化约束审查...",
  "正在过滤大模型惰性废话，全量数据收包中..."
];

function toggleSynapseLoading(show, title, initialText) {
  const overlay = document.getElementById('synapse-loading-overlay');
  if (!overlay) return;
  if (!show) {
    clearInterval(_synapseProgressInterval);
    clearInterval(_synapsePhaseInterval);
    _synapseProgressInterval = null;
    _synapsePhaseInterval = null;
    const bar = document.getElementById('synapse-progress-bar');
    const pct = document.getElementById('synapse-progress-percent');
    if (bar) bar.style.width = '100%';
    if (pct) pct.innerText = '100%';
    setTimeout(() => { overlay.style.display = 'none'; }, 600);
    return;
  }
  overlay.style.display = 'flex';
  const t = document.getElementById('loading-engine-title');
  const p = document.getElementById('loading-phase-text');
  const bar = document.getElementById('synapse-progress-bar');
  const pct = document.getElementById('synapse-progress-percent');
  const sub = document.getElementById('synapse-loading-subtext');
  if (t) t.innerText = title || 'SYNAPSE Engine';
  if (p) p.innerText = initialText || '正在初始化...';
  if (bar) bar.style.width = '0%';
  if (pct) pct.innerText = '0%';
  if (sub) sub.innerText = '';
}

function _startOutlinePseudoProgress() {
  let prog = 0, textIdx = 0;
  _synapseProgressInterval = setInterval(() => {
    if (prog < 50) prog += Math.random() * 3 + 1;
    else if (prog < 85) prog += Math.random() * 0.8 + 0.2;
    else if (prog < 96) prog += Math.random() * 0.08 + 0.01;
    const bar = document.getElementById('synapse-progress-bar');
    const pct = document.getElementById('synapse-progress-percent');
    if (bar) bar.style.width = Math.min(prog, 96).toFixed(1) + '%';
    if (pct) pct.innerText = Math.min(prog, 96).toFixed(0) + '%';
  }, 400);
  _synapsePhaseInterval = setInterval(() => {
    if (textIdx < _outlinePhaseTexts.length - 1) {
      textIdx++;
      const p = document.getElementById('loading-phase-text');
      if (p) {
        p.style.opacity = '0';
        setTimeout(() => { p.innerText = _outlinePhaseTexts[textIdx]; p.style.opacity = '0.9'; }, 300);
      }
    }
  }, 9000);
}

async function stepGenerateNovel(chapterIndices, total) {
  toggleSynapseLoading(true, 'SYNAPSE 核心流水线：雕刻正文', '正在调度单集短连接执行矩阵...');
  const MAX_RETRIES = 2;

  async function generateOneChapter(idx, attempt) {
    const response = await fetch(`${API}/api/projects/${state.currentProject.id}/novel/${idx}/stream`);
    if (!response.ok) throw new Error('请求失败 ' + response.status);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let novelText = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));
          if (event.type === 'done') {
            novelText = event.novel_text;
          } else if (event.type === 'error') {
            throw new Error(event.message);
          } else if (event.type === 'chunk' && event.content) {
            const charCount = (novelText + event.content).length;
            const sub = document.getElementById('synapse-loading-subtext');
            if (sub) sub.innerText = '第 ' + (idx + 1) + ' 集' + (attempt > 0 ? '(重试' + attempt + ')' : '') + ' · 已生成 ' + charCount + ' 字';
          }
        } catch (e) {
          if (e.message && !e.message.includes('JSON')) throw e;
        }
      }
    }
    return novelText;
  }

  let remaining = [...chapterIndices];
  for (let round = 0; round <= MAX_RETRIES; round++) {
    if (remaining.length === 0) break;
    if (round > 0) {
      showNotification('第' + remaining.map(i=>i+1).join(',') + '集重试中(' + round + '/' + MAX_RETRIES + ')...');
      await new Promise(r => setTimeout(r, 2000));
    }
    const nextRemaining = [];
    for (let i = 0; i < remaining.length; i++) {
      const idx = remaining[i];
      const bar = document.getElementById('synapse-progress-bar');
      const pct = document.getElementById('synapse-progress-percent');
      const phase = document.getElementById('loading-phase-text');
      const sub = document.getElementById('synapse-loading-subtext');
      const realPct = Math.round(((chapterIndices.length - remaining.length + i) / chapterIndices.length) * 100);
      if (bar) bar.style.width = realPct + '%';
      if (pct) pct.innerText = realPct + '%';
      if (phase) phase.innerText = '正在精雕细琢第 ' + (idx + 1) + ' 集小说正文...' + (round > 0 ? '(重试' + round + ')' : '');
      if (sub) sub.innerText = '总进度：' + (chapterIndices.length - remaining.length + i + 1) + ' / ' + chapterIndices.length + ' 集';
      try {
        const novelText = await generateOneChapter(idx, round);
        if (novelText) {
          if (!state.currentProject.chapters) state.currentProject.chapters = {};
          state.currentProject.chapters[String(idx)] = { novel_text: novelText };
        } else {
          nextRemaining.push(idx);
        }
      } catch (e) {
        console.error('第' + (idx+1) + '集生成失败(轮次' + round + '):', e);
        nextRemaining.push(idx);
      }
    }
    remaining = nextRemaining;
  }

  toggleSynapseLoading(false);
  if (remaining.length > 0) {
    showNotification('第' + remaining.map(i=>i+1).join(',') + '集生成失败(已重试' + MAX_RETRIES + '次)', 'error');
  } else {
    showNotification('全部小说生成完成');
  }
  loadChapter(state.currentChapter);
  checkNovelComplete();
}



// ══════════════════════════════════════════
//  AI Polish — selection floating toolbar
// ══════════════════════════════════════════
(function initAiPolishToolbar() {
  const toolbar = document.createElement('div');
  toolbar.id = 'ai-polish-toolbar';
  toolbar.className = 'ai-polish-toolbar';
  toolbar.innerHTML = '<button class="ai-polish-btn" id="ai-polish-btn"><span class="spinner"></span>\u2728 AI\u6da6\u8272</button>';
  document.body.appendChild(toolbar);
  document.getElementById('ai-polish-btn').addEventListener('click', handleAiPolish);
})();

function showPolishToolbar(x, y) {
  const tb = document.getElementById('ai-polish-toolbar');
  if (!tb) return;
  tb.style.left = x + 'px';
  tb.style.top = (y - 44) + 'px';
  tb.classList.add('show');
}

function hidePolishToolbar() {
  const tb = document.getElementById('ai-polish-toolbar');
  if (tb) tb.classList.remove('show');
}

document.addEventListener('mouseup', function(e) {
  const display = document.getElementById('novel-display');
  if (!display || !display.contains(e.target)) {
    if (!e.target.closest('#ai-polish-toolbar')) hidePolishToolbar();
    return;
  }
  const sel = window.getSelection();
  const text = sel ? sel.toString().trim() : '';
  if (text.length >= 5) {
    const range = sel.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    showPolishToolbar(rect.left + rect.width / 2 - 50, rect.top + window.scrollY);
  } else {
    if (!e.target.closest('#ai-polish-toolbar')) hidePolishToolbar();
  }
});

document.addEventListener('mousedown', function(e) {
  if (!e.target.closest('#ai-polish-toolbar')) hidePolishToolbar();
});

async function handleAiPolish() {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return;
  const selectedText = sel.toString().trim();
  if (selectedText.length < 5) { showNotification('\u8bf7\u5148\u9009\u4e2d\u81f3\u5c115\u4e2a\u5b57', 'error'); return; }

  const btn = document.getElementById('ai-polish-btn');
  btn.classList.add('loading');

  try {
    const novelText = state.currentProject?.chapters?.[String(state.currentChapter)]?.novel_text || '';
    const idx = novelText.indexOf(selectedText);
    const ctxRadius = 200;
    let contextBefore = '', contextAfter = '';
    if (idx >= 0) {
      contextBefore = novelText.substring(Math.max(0, idx - ctxRadius), idx);
      contextAfter = novelText.substring(idx + selectedText.length, idx + selectedText.length + ctxRadius);
    }
    const instruction = '\u8bf7\u5bf9\u4ee5\u4e0b\u9009\u4e2d\u6bb5\u843d\u8fdb\u884c\u6da6\u8272\uff0c\u4fdd\u6301\u539f\u6587\u98ce\u683c\u548c\u60c5\u8282\u4e0d\u53d8\uff0c\u63d0\u5347\u6587\u5b57\u8d28\u91cf\u3002\u53ea\u8f93\u51fa\u6da6\u8272\u540e\u7684\u6587\u672c\uff0c\u4e0d\u8981\u52a0\u4efb\u4f55\u89e3\u91ca\u3002\n\n\u4e0a\u4e0b\u6587\uff1a\n\u201c' + contextBefore + '\u201d\n\u3010\u5f85\u6da6\u8272\u6587\u672c\u3011\n\u201c' + selectedText + '\u201d\n\u3010\u5f85\u6da6\u8272\u6587\u672c\u7ed3\u675f\u3011\n\u201c' + contextAfter + '\u201d';
    const result = await api('/api/projects/' + state.currentProject.id + '/novel/' + state.currentChapter + '/modify', 'POST', { instruction }, 300000);
    const newText = (result.novel_text || '').trim();

    if (newText && newText !== selectedText) {
      const fullText = state.currentProject.chapters[String(state.currentChapter)].novel_text;
      state.currentProject.chapters[String(state.currentChapter)].novel_text = fullText.replace(selectedText, newText);
      loadChapter(state.currentChapter);
      showNotification('AI\u6da6\u8272\u5b8c\u6210');
    } else {
      showNotification('AI\u672a\u4ea7\u751f\u4fee\u6539', 'error');
    }
  } catch (e) {
    showNotification('AI\u6da6\u8272\u5931\u8d25: ' + e.message, 'error');
  } finally {
    btn.classList.remove('loading');
    hidePolishToolbar();
  }
}


// ══════════════════════════════════════════
//  Emotion Curve Visualization
// ══════════════════════════════════════════
function getEmotionData(chapterIndex) {
  const outline = state.currentProject?.outline;
  if (!outline) return [];
  const chapters = outline.chapters || outline.episodes || [];
  const ch = chapters[chapterIndex];
  if (!ch) return [];

  // Try to extract emotion data from various possible fields
  // 1) Check for explicit emotion_arc / emotion_trend / emotional_curve field
  const arc = ch.emotion_arc || ch.emotion_trend || ch.emotional_curve || ch['\u60c5\u7eea\u8d70\u5411'] || null;
  if (arc && typeof arc === 'string') {
    return parseEmotionString(arc);
  }
  if (Array.isArray(arc)) {
    return arc.map((v, i) => ({ label: '\u70b9' + (i+1), value: typeof v === 'number' ? v : mapMoodToValue(v) }));
  }

  // 2) Try to extract from scenes[].mood
  const scenes = ch.scenes || [];
  if (scenes.length > 0) {
    return scenes.map((s, i) => ({
      label: '\u573a\u666f' + (i+1),
      value: mapMoodToValue(s.mood || s.emotion || ''),
      mood: s.mood || s.emotion || ''
    }));
  }

  // 3) Try to parse from summary text (look for mood keywords)
  return [];
}

function parseEmotionString(str) {
  // Parse comma-separated mood descriptions like "平静,紧张,高潮,释然"
  const parts = str.split(/[,，、\-\->\uff1a:]/).map(s => s.trim()).filter(Boolean);
  return parts.map((p, i) => ({ label: '\u70b9' + (i+1), value: mapMoodToValue(p), mood: p }));
}

function mapMoodToValue(mood) {
  if (!mood || typeof mood !== 'string') return 5;
  const m = mood.toLowerCase();
  // Map mood keywords to 1-10 scale
  const highEnergy = ['\u9ad8\u6f6e', '\u6fc0\u70c8', '\u7d27\u5f20', '\u51b2\u7a81', '\u6fc0\u6218', '\u9ad8\u6f6e', '\u7206\u53d1', '\u60ca\u8bb6', '\u9707\u64bc', '\u5cf0',
    'climax', 'intense', 'explosive', 'shock', 'peak', 'epic', 'dramatic', 'fierce'];
  const midHigh = ['\u5371\u673a', '\u60ac\u7591', '\u7d27\u8feb', '\u611f\u52a8', '\u6fc0\u52a8', '\u6ce2\u52a8', '\u5bf9\u6297', '\u60b2\u4f24', '\u6124\u6012',
    'suspense', 'crisis', 'tension', 'exciting'];
  const neutral = ['\u5e73\u9759', '\u65e5\u5e38', '\u6e29\u99a8', '\u5e73\u7a33', '\u81ea\u7136', '\u53d9\u8ff0', '\u5e73\u6de1',
    'calm', 'peaceful', 'neutral', 'normal'];
  const lowEnergy = ['\u4f4e\u8c37', '\u60ac\u5ff5', '\u6c89\u9ed8', '\u5b64\u72ec', '\u60b2\u4f24', '\u5931\u843d', '\u7edd\u671b', '\u843d\u5bde',
    'melancholy', 'sad', 'despair', 'lonely', 'gloomy'];
  const rising = ['\u5e0c\u671b', '\u6e29\u6696', '\u5145\u5b9e', '\u89c9\u9192', '\u8f6c\u673a', '\u559c\u60a6', '\u5e78\u798f',
    'hope', 'warm', 'joy', 'happy', 'rising'];

  for (const kw of highEnergy) { if (m.includes(kw)) return 9; }
  for (const kw of midHigh) { if (m.includes(kw)) return 7; }
  for (const kw of rising) { if (m.includes(kw)) return 8; }
  for (const kw of lowEnergy) { if (m.includes(kw)) return 3; }
  for (const kw of neutral) { if (m.includes(kw)) return 5; }
  return 5;
}

function renderEmotionCurve(chapterIndex) {
  const panel = document.getElementById('emotion-curve-panel');
  if (!panel) return;

  const data = getEmotionData(chapterIndex);
  if (data.length < 2) {
    panel.innerHTML = '<h4>\u2728 \u60c5\u7eea\u66f2\u7ebf</h4><div class="emotion-curve-legend">\u6682\u65e0\u60c5\u7eea\u6570\u636e<br>\u751f\u6210\u5927\u7eb2\u540e\u81ea\u52a8\u663e\u793a</div>';
    return;
  }

  const W = 188, H = 140, padX = 20, padY = 20;
  const plotW = W - padX * 2, plotH = H - padY * 2;
  const minV = 0, maxV = 10;

  const points = data.map((d, i) => {
    const x = padX + (i / (data.length - 1)) * plotW;
    const y = padY + plotH - ((d.value - minV) / (maxV - minV)) * plotH;
    return { x, y, ...d };
  });

  const pathD = points.map((p, i) => (i === 0 ? 'M' : 'L') + p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' ');

  // Gradient area fill
  const areaD = pathD + ' L' + points[points.length-1].x.toFixed(1) + ',' + (H - padY) + ' L' + points[0].x.toFixed(1) + ',' + (H - padY) + ' Z';

  // Color based on average value
  const avg = data.reduce((s, d) => s + d.value, 0) / data.length;
  const color = avg > 7 ? '#ef4444' : avg > 5 ? '#a855f7' : avg > 3 ? '#3b82f6' : '#6b7280';

  let svg = '<svg class="emotion-curve-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet">';
  // Grid lines
  for (let v = 0; v <= 10; v += 2) {
    const y = padY + plotH - (v / 10) * plotH;
    svg += '<line x1="' + padX + '" y1="' + y.toFixed(1) + '" x2="' + (W - padX) + '" y2="' + y.toFixed(1) + '" stroke="rgba(255,255,255,0.06)" stroke-width="0.5"/>';
    if (v === 0 || v === 5 || v === 10) {
      const labels = { 0: '\u4f4e', 5: '\u4e2d', 10: '\u9ad8' };
      svg += '<text x="' + (padX - 4) + '" y="' + (y + 3).toFixed(1) + '" text-anchor="end" fill="rgba(255,255,255,0.25)" font-size="8">' + labels[v] + '</text>';
    }
  }
  // Area fill
  svg += '<defs><linearGradient id="emotionGrad" x1="0" y1="0" x2="0" y2="1">';
  svg += '<stop offset="0%" stop-color="' + color + '" stop-opacity="0.3"/>';
  svg += '<stop offset="100%" stop-color="' + color + '" stop-opacity="0.02"/>';
  svg += '</linearGradient></defs>';
  svg += '<path d="' + areaD + '" fill="url(#emotionGrad)"/>';
  // Line
  svg += '<path d="' + pathD + '" fill="none" stroke="' + color + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>';
  // Points and labels
  points.forEach((p, i) => {
    svg += '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="3.5" fill="' + color + '" stroke="rgba(0,0,0,0.4)" stroke-width="1"/>';
    const lbl = p.label || ('' + (i+1));
    if (data.length <= 8 || i % 2 === 0) {
      svg += '<text x="' + p.x.toFixed(1) + '" y="' + (H - padY + 14) + '" text-anchor="middle" class="emotion-point-label">' + esc(lbl) + '</text>';
    }
  });
  svg += '</svg>';

  // Mood descriptions below
  let moodHtml = '';
  data.forEach((d, i) => {
    if (d.mood) {
      moodHtml += '<div style="font-size:10px;color:var(--text-secondary);margin-top:2px;"><span style="color:var(--accent-light);">' + esc(d.label || ('S'+(i+1))) + ':</span> ' + esc(d.mood) + '</div>';
    }
  });

  panel.innerHTML = '<h4>\u2728 \u60c5\u7eea\u66f2\u7ebf</h4>' + svg + '<div class="emotion-curve-legend">' + (moodHtml || '\u60c5\u7eea\u8d70\u5411\u56fe') + '</div>';
}


function initSpotlight() {
  document.querySelectorAll('.spotlight').forEach(card => {
    card.addEventListener('mousemove', e => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      card.style.setProperty('--mouse-x', x + 'px');
      card.style.setProperty('--mouse-y', y + 'px');
    });
  });
}

function showPromptModal(title, onConfirm) {
  document.getElementById('modal-prompt-title').textContent = title;
  document.getElementById('modal-prompt-input').value = '';
  document.getElementById('modal-prompt-confirm').onclick = () => {
    const val = document.getElementById('modal-prompt-input').value.trim();
    if (val) { closeModal('modal-prompt'); onConfirm(val); }
  };
  document.getElementById('modal-prompt').classList.add('show');
}


async function loadSettings() {
  try {
    const cfg = await api('/api/config');
    for (const type of ['llm', 'image', 'video']) {
      const p = cfg[type];
      document.getElementById(`${type}-base-url`).value = p.base_url || '';
      const keyInput = document.getElementById(`${type}-api-key`);
      if (p.api_key_masked) {
        keyInput.value = p.api_key_masked;
        keyInput.setAttribute('data-saved', 'true');
        keyInput.style.borderColor = 'rgba(34,197,94,0.4)';
      } else {
        keyInput.value = '';
        keyInput.removeAttribute('data-saved');
        keyInput.style.borderColor = '';
      }
      keyInput.placeholder = ' API Key';
      document.getElementById(`${type}-model`).value = p.model || '';
    }
  } catch (e) {
    console.error('Load settings error:', e);
  }
}

function toggleKeyVisibility(inputId) {
  const inp = document.getElementById(inputId);
  const btn = inp.parentElement.querySelector('.toggle-visibility');
  if (inp.type === 'password') {
    inp.type = 'text';
    btn.textContent = '隐藏';
  } else {
    inp.type = 'password';
    btn.textContent = '显示';
  }
}

async function testConnection(type) {
  const resultEl = document.getElementById(`${type}-test-result`);
  const btn = document.querySelector(`[onclick="testConnection('${type}')"]`);
  const origText = btn.textContent;
  btn.textContent = '测试中...';
  btn.disabled = true;
  btn.style.opacity = '0.6';
  resultEl.textContent = '';
  resultEl.className = 'test-result';

  const base_url = document.getElementById(`${type}-base-url`).value;
  const api_key = document.getElementById(`${type}-api-key`).value || '';
  const model = document.getElementById(`${type}-model`).value;

  // 15s timeout
  const timeout = new Promise((_, reject) =>
    setTimeout(() => reject(new Error('连接超时(15s)')), 15000)
  );

  try {
    const result = await Promise.race([
      api('/api/config/test', 'POST', { type, base_url, api_key, model }),
      timeout,
    ]);
    if (result.success) {
      resultEl.textContent = '连接成功';
      resultEl.className = 'test-result success';
    } else {
      resultEl.textContent = '连接失败: ' + result.message;
      resultEl.className = 'test-result error';
    }
  } catch (e) {
    resultEl.textContent = '连接失败: ' + e.message;
    resultEl.className = 'test-result error';
  } finally {
    btn.textContent = origText;
    btn.disabled = false;
    btn.style.opacity = '1';
  }
}

async function saveSettings() {
  const data = {};
  for (const type of ['llm', 'image', 'video']) {
    data[type] = {
      base_url: document.getElementById(`${type}-base-url`).value,
      api_key: (() => { const v = document.getElementById(`${type}-api-key`).value; return (!v || v.includes('****')) ? '__UNCHANGED__' : v; })(),
      model: document.getElementById(`${type}-model`).value,
    };
  }
  try {
    await api('/api/config', 'POST', data);
    showNotification('设置已保存');
  } catch (e) {
    showNotification('确认失败: ' + e.message, 'error');
  }
}

// 
//  
// 

async function loadProjects() {
  try {
    const projects = await api('/api/projects');
    const grid = document.getElementById('projects-grid');
    if (projects.length === 0) {
      grid.innerHTML = '<div class="glass-card" style="text-align:center;padding:60px;"><p style="color:var(--text-secondary);font-size:16px;">暂无项目，点击上方按钮开始创作</p></div>';
      return;
    }
    grid.innerHTML = projects.map(p => `
      <div class="glass-card project-card spotlight" data-project-id="${p.id}">
        <button class="project-delete-btn" onclick="event.stopPropagation();deleteProject('${p.id}')" title="删除项目">&times;</button>
        <div onclick="openProject('${p.id}')">
          <h3>${esc(p.name)}</h3>
          <div class="meta">
             ${p.current_step}/10 ·
            ${new Date(p.updated_at * 1000).toLocaleString('zh-CN')}
          </div>
        </div>
      </div>
    `).join('');
    initSpotlight();
  } catch (e) {
    console.error('Load projects error:', e);
  }
}

function showNewProjectModal() {
  document.getElementById('modal-new-project').classList.add('show');
  document.getElementById('new-project-name').focus();
}

function closeModal(id) {
  document.getElementById(id).classList.remove('show');
}

async function createProject() {
  const name = document.getElementById('new-project-name').value.trim();
  if (!name) { showNotification('请填写必填项', 'error'); return; }

  try {
    const result = await api('/api/projects', 'POST', {
      name,
      clip_duration: parseInt(document.getElementById('clip-duration')?.value || '10'),
      art_style: document.getElementById('art-style')?.value || 'anime',
      genre: (document.getElementById('genre')?.value || '').split(',').map(s => s.trim()).filter(Boolean),
      tone: document.getElementById('tone')?.value || '',
      dialogue_style: document.getElementById('dialogue-style')?.value || '',
      episodes: parseInt(document.getElementById('episodes')?.value || '10'),
      episode_duration: parseInt(document.getElementById('episode-duration')?.value || '60'),
    });
    closeModal('modal-new-project');
    openProject(result.project_id);
  } catch (e) {
    showNotification('创建项目失败: ' + e.message, 'error');
  }
}

async function openProject(projectId) {
  try {
    const project = await api(`/api/projects/${projectId}`);
    state.currentProject = project;
    state.currentChapter = 0;

    // Load persistent chat history from backend
    try {
      const chatRes = await api(`/api/projects/${projectId}/chat`);
      if (chatRes.success && chatRes.chat_history) {
        state.projectChats[projectId] = chatRes.chat_history;
      }
    } catch (_) {}

    navigateTo('workspace');
    showStep(Math.max(project.current_step || 2, 2));
    renderChatHistory();
  } catch (e) {
    showNotification('打开项目失败: ' + e.message, 'error');
  }
}

async function deleteProject(projectId) {
  showConfirmModal(
    '确认删除',
    '确定要删除该项目吗？此操作不可恢复。',
    async function() {
      try {
        await api(`/api/projects/${projectId}`, 'DELETE');
        delete state.projectChats[projectId];
        showNotification('项目已删除');
        loadProjects();
      } catch (e) {
        showNotification('删除失败: ' + e.message, 'error');
      }
    }
  );
}

function showConfirmModal(title, message, onConfirm) {
  const overlay = document.getElementById('modal-delete-confirm');
  const titleEl = document.getElementById('modal-delete-title');
  const msgEl = document.getElementById('modal-delete-message');
  const btn = document.getElementById('modal-delete-confirm-btn');
  if (!overlay || !titleEl || !msgEl || !btn) { onConfirm(); return; }
  titleEl.textContent = title;
  msgEl.textContent = message;
  overlay.classList.add('show');
  const newBtn = btn.cloneNode(true);
  btn.parentNode.replaceChild(newBtn, btn);
  newBtn.addEventListener('click', function() {
    closeModal('modal-delete-confirm');
    onConfirm();
  });
}

function toggleChatSidebar() {
  const sidebar = document.getElementById('chat-sidebar');
  const toggleBtn = document.getElementById('chat-toggle-btn');
  if (!sidebar) return;
  const isOpen = sidebar.classList.toggle('expanded');
  if (toggleBtn) {
    toggleBtn.innerHTML = isOpen ? '&#x25B6;' : '&#x25C0;';
    toggleBtn.style.right = isOpen ? '360px' : '0';
  }
}

function renderChatHistory() {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  const pid = state.currentProject?.id || '_global';
  const history = state.projectChats[pid] || [];
  container.innerHTML = history.map(m =>
    `<div class="chat-msg ${m.role === 'user' ? 'user-msg' : 'ai-msg'}"><p>${esc(m.content)}</p></div>`
  ).join('');
  container.scrollTop = container.scrollHeight;
}


// 
//  
// 

function showStep(step) {
  // 
  document.querySelectorAll('.step-item').forEach(el => {
    const s = parseInt(el.dataset.step);
    el.classList.remove('active', 'completed');
    if (s === step) el.classList.add('active');
    else if (s < step) el.classList.add('completed');
  });

  // 
  document.querySelectorAll('.workspace-step').forEach(el => el.classList.remove('active'));
  const target = document.getElementById(`ws-step-${step}`);
  if (target) target.classList.add('active');

  // 
  if (step === 2) restoreOutlinePhase();
  if (step === 3) renderCharacters();
  if (step === 4) renderNovel();
  if (step === 5) renderStoryboard();
  if (step === 6) renderFrames();
  if (step === 7) renderVideoStep();
  if (step === 8) renderComposeStep();
  if (step === 9) renderExportStep();

  // 
  if (state.currentProject) {
    // 只在前进时更新进度，回退不降级
    if (step > (state.currentProject.current_step || 2)) {
      state.currentProject.current_step = step;
    }
    api(`/api/projects/${state.currentProject.id}/save`, 'POST', state.currentProject).catch(() => {});
  }
}

// Step click handler
document.addEventListener('click', e => {
  const stepItem = e.target.closest('.step-item');
  if (stepItem) {
    const step = parseInt(stepItem.dataset.step);
    const maxStep = Math.max(state.currentProject?.current_step || 2, 2);
    if (step <= maxStep) {
      showStep(step);
    } else {
      showNotification('很抱歉，您还没完成当前进度，请先完成第' + maxStep + '步', 'error');
    }
  }
});

// 
//  2 + 
// 

function showOutlinePhase(phase) {
  ['outline-phase-input', 'outline-phase-titles', 'outline-phase-result'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  const target = document.getElementById('outline-phase-' + phase);
  if (target) target.style.display = '';
}

function restoreOutlinePhase() {
  const project = state.currentProject;
  if (!project) { showOutlinePhase('input'); return; }

  // 上传小说模式恢复
  if (project.settings?.novel_source === 'uploaded') {
    switchCreationMode('upload');
    // 如果已经有大纲（说明解析+切割已完成），直接显示大纲
    if (project.outline?.chapters?.length || project.outline?.episodes?.length) {
      renderOutline();
      showOutlinePhase('result');
    } else {
      showOutlinePhase('input');
    }
    return;
  }

  // AI创作模式恢复
  switchCreationMode('ai');
  const ideaInput = document.getElementById('creative-input');
  if (ideaInput && project.settings?.idea) ideaInput.value = project.settings.idea;

  if (project.outline?.episodes?.length) {
    renderOutline();
    showOutlinePhase('result');
  } else if (project.settings?.suggested_titles?.length) {
    state.suggestedTitles = project.settings.suggested_titles;
    renderTitles(state.suggestedTitles);
    showOutlinePhase('titles');
  } else {
    showOutlinePhase('input');
  }
}


function clearCreativeForm() {
  document.getElementById('creative-input').value = '';
  document.getElementById('episodes').value = '10';
  document.getElementById('episode-duration').value = '60';
  document.getElementById('clip-duration').value = '10';
  document.getElementById('clip-duration-display').value = '10';
  document.getElementById('genre').value = '';
  document.getElementById('art-style').value = '';
  document.getElementById('art-style-display').value = '';
  // 
  ['style-tone','style-lighting','style-texture'].forEach(id => {
    const h = document.getElementById(id);
    const d = document.getElementById(id + '-display');
    if (h) h.value = '';
    if (d) d.value = '';
  });
  ['art-style','style-tone','style-lighting','style-texture'].forEach(id => {
    const t = document.getElementById('combobox-trigger-' + id);
    if (t) t.classList.remove('has-value');
  });
  showNotification('表单已清空', 'success');
}

// ── 上传小说模式 ──
let _creationMode = 'ai';
let _parsedNovelResult = null; // 临时存储parse-novel返回的结果

function switchCreationMode(mode) {
  _creationMode = mode;
  // Toggle button active state
  document.querySelectorAll('#creation-mode-toggle .mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });
  // Toggle form sections with animation
  const aiGroup = document.getElementById('creative-input-group');
  const uploadGroup = document.getElementById('novel-upload-group');
  const btn = document.getElementById('btn-start-planning');
  const showGroup = mode === 'ai' ? aiGroup : uploadGroup;
  const hideGroup = mode === 'ai' ? uploadGroup : aiGroup;
  if (hideGroup) {
    hideGroup.classList.add('mode-section-hidden');
    hideGroup.classList.remove('mode-section-enter');
  }
  if (showGroup) {
    showGroup.classList.remove('mode-section-hidden');
    // Force reflow so animation restarts
    showGroup.offsetWidth;
    showGroup.classList.add('mode-section-enter');
  }
  if (btn) btn.textContent = mode === 'ai' ? '开始规划' : '解析小说';
}

function handleNovelFileSelect(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {
    const text = e.target.result;
    const textarea = document.getElementById('novel-text-input');
    if (textarea) textarea.value = text;
    const info = document.getElementById('novel-upload-info');
    if (info) {
      const charCount = text.length;
      const paraCount = text.split(/\n\n+/).filter(p => p.trim()).length;
      info.textContent = `已加载: ${file.name} (${charCount} 字, ${paraCount} 段)`;
      info.style.display = '';
    }
  };
  reader.readAsText(file, 'UTF-8');
}

// Drag-and-drop for upload zone
document.addEventListener('DOMContentLoaded', function() {
  const zone = document.getElementById('novel-upload-zone');
  if (!zone) return;
  zone.addEventListener('click', () => document.getElementById('novel-file-input')?.click());
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('dragover');
    const file = e.dataTransfer?.files?.[0];
    if (file && file.name.endsWith('.txt')) {
      const reader = new FileReader();
      reader.onload = function(ev) {
        const textarea = document.getElementById('novel-text-input');
        if (textarea) textarea.value = ev.target.result;
        const info = document.getElementById('novel-upload-info');
        if (info) {
          const charCount = ev.target.result.length;
          const paraCount = ev.target.result.split(/\n\n+/).filter(p => p.trim()).length;
          info.textContent = `已加载: ${file.name} (${charCount} 字, ${paraCount} 段)`;
          info.style.display = '';
        }
      };
      reader.readAsText(file, 'UTF-8');
    }
  });
});

async function startUploadNovel() {
  const novelText = document.getElementById('novel-text-input')?.value?.trim();
  if (!novelText) { showNotification('请上传或粘贴小说文本', 'error'); return; }
  if (novelText.length < 200) { showNotification('小说文本太短，至少需要200字', 'error'); return; }

  // 保存设置
  const settings = {
    episodes: parseInt(document.getElementById('episodes')?.value || '10'),
    episode_duration: parseInt(document.getElementById('episode-duration')?.value || '60'),
    clip_duration: parseInt(document.getElementById('clip-duration')?.value || '10'),
    art_style: document.getElementById('art-style')?.value || '',
    art_style_display: document.getElementById('art-style-display')?.value || '',
    style_tone: document.getElementById('style-tone')?.value || '',
    style_lighting: document.getElementById('style-lighting')?.value || '',
    style_texture: document.getElementById('style-texture')?.value || '',
    genre: (document.getElementById('genre')?.value || '').split(',').map(s => s.trim()).filter(Boolean),
    novel_source: 'uploaded',
  };
  state.currentProject.settings = { ...state.currentProject.settings, ...settings };

  toggleSynapseLoading(true, 'SYNAPSE 小说解析引擎', '正在分析小说结构，提取角色和大纲...');
  try {
    await api(`/api/projects/${state.currentProject.id}/save`, 'POST', state.currentProject);

    const result = await api(`/api/projects/${state.currentProject.id}/parse-novel`, 'POST', {
      novel_text: novelText
    }, 300000);

    if (!result.success) throw new Error(result.message || '解析失败');

    _parsedNovelResult = result; // 临时保存
    state.suggestedTitles = (result.titles || []).map(t => {
      if (typeof t === 'string') return { title: t, reason: '' };
      return t;
    });
    state.currentProject.settings.suggested_titles = state.suggestedTitles;
    // 保留后端parse-novel已保存的_uploaded_novel和_novel_paragraphs
    state.currentProject._uploaded_novel = novelText;
    state.currentProject._novel_paragraphs = novelText.split(/\n\n+/).filter(p => p.trim());
    await api(`/api/projects/${state.currentProject.id}/save`, 'POST', state.currentProject);

    renderTitles(state.suggestedTitles);
    showOutlinePhase('titles');

    // 修改标题选择行为：选标题后走split-novel而不是doGenerateOutline
    window._uploadModeSelectTitle = function(index) {
      const titles = state.suggestedTitles || [];
      if (index < 0 || index >= titles.length) return;
      const selected = titles[index].title;
      state.currentProject.title = selected;
      doSplitNovel(selected, result.outline);
    };
    window._uploadModeUseCustomTitle = function() {
      const input = document.getElementById('custom-title-input');
      const title = (input?.value || '').trim();
      if (!title) { showNotification('请输入标题', 'error'); return; }
      state.currentProject.title = title;
      doSplitNovel(title, result.outline);
    };

    showNotification('小说解析完成，请选择标题', 'success');
  } catch (e) {
    showNotification('小说解析失败: ' + e.message, 'error');
  } finally {
    toggleSynapseLoading(false);
  }
}

async function doSplitNovel(title, outline) {
  toggleSynapseLoading(true, 'SYNAPSE 小说切割引擎', '正在按段落切割小说到各集...');
  try {
    const result = await api(`/api/projects/${state.currentProject.id}/split-novel`, 'POST', {
      title: title,
      outline: outline,
    });

    if (!result.success) throw new Error(result.message || '切割失败');

    // 重新加载项目数据
    const project = await api(`/api/projects/${state.currentProject.id}`);
    state.currentProject = project;

    // 直接进入角色生成步骤
    showStep(4);
    showNotification(`小说已切割为${result.chapters_count}集`, 'success');
  } catch (e) {
    showNotification('小说切割失败: ' + e.message, 'error');
  } finally {
    toggleSynapseLoading(false);
  }
}

async function startPlanning() {
  // 上传小说模式走独立流程
  if (_creationMode === 'upload') {
    return startUploadNovel();
  }

  const idea = document.getElementById('creative-input').value.trim();
  if (!idea) { showNotification('请填写必填项', 'error'); return; }

  // 
  const settings = {
    idea: idea,
    episodes: parseInt(document.getElementById('episodes')?.value || '10'),
    episode_duration: parseInt(document.getElementById('episode-duration')?.value || '60'),
    clip_duration: parseInt(document.getElementById('clip-duration')?.value || '10'),
    art_style: document.getElementById('art-style')?.value || '',
    art_style_display: document.getElementById('art-style-display')?.value || '',
    style_tone: document.getElementById('style-tone')?.value || '',
    style_lighting: document.getElementById('style-lighting')?.value || '',
    style_texture: document.getElementById('style-texture')?.value || '',
    genre: (document.getElementById('genre')?.value || '').split(',').map(s => s.trim()).filter(Boolean),
  };
  state.currentProject.settings = { ...state.currentProject.settings, ...settings };

  // 
  toggleSynapseLoading(true, 'SYNAPSE 大纲引擎', '正在分析创意，生成标题建议...');
  try {
    await api(`/api/projects/${state.currentProject.id}/save`, 'POST', state.currentProject);
    const result = await api(`/api/projects/${state.currentProject.id}/titles`, 'POST', null, 300000);
    state.suggestedTitles = result.titles || [];
    state.currentProject.settings.suggested_titles = state.suggestedTitles;
    await api(`/api/projects/${state.currentProject.id}/save`, 'POST', state.currentProject);
    renderTitles(state.suggestedTitles);
    showOutlinePhase('titles');
  } catch (e) {
    showNotification('创意分析失败: ' + e.message, 'error');
  } finally {
    toggleSynapseLoading(false);
  }


}

function renderTitles(titles) {
  const grid = document.getElementById('titles-grid');
  if (!grid) return;
  grid.innerHTML = titles.map((t, i) => `
    <div class="glass-card title-card" onclick="selectTitle(${i})" style="cursor:pointer;padding:20px;margin-bottom:12px;transition:all 0.2s;">
      <h3 style="margin:0 0 8px 0;font-size:20px;">${esc(t.title)}</h3>
      <p style="margin:0;color:var(--text-secondary);font-size:14px;">${esc(t.reason)}</p>
    </div>
  `).join('');
}

function selectTitle(index) {
  // 上传小说模式
  if (window._uploadModeSelectTitle) {
    window._uploadModeSelectTitle(index);
    return;
  }
  const titles = state.suggestedTitles || [];
  if (index < 0 || index >= titles.length) return;
  const selected = titles[index].title;
  state.currentProject.title = selected;
  doGenerateOutline(selected);
}

function useCustomTitle() {
  // 上传小说模式
  if (window._uploadModeUseCustomTitle) {
    window._uploadModeUseCustomTitle();
    return;
  }
  const input = document.getElementById('custom-title-input');
  const title = (input?.value || '').trim();
  if (!title) { showNotification('请输入标题', 'error'); return; }
  state.currentProject.title = title;
  doGenerateOutline(title);
}

function skipTitles() {
  // 
  doGenerateOutline('');
}

function backToInput() {
  showOutlinePhase('input');
}

async function doGenerateOutline(selectedTitle) {
  toggleSynapseLoading(true, 'SYNAPSE 漫剧引擎：构建大纲', _outlinePhaseTexts[0]);
  _startOutlinePseudoProgress();
  try {
    // Use streaming endpoint for real-time progress
    const response = await fetch(`${API}/api/projects/${state.currentProject.id}/outline/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: selectedTitle })
    });

    if (!response.ok) throw new Error('请求失败');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let outline = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Process complete SSE messages
      const lines = buffer.split('\n');
      buffer = lines.pop(); // Keep incomplete line in buffer

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));
          if (event.type === 'done') {
            outline = event.outline;
          } else if (event.type === 'error') {
            throw new Error(event.message);
          } else if (event.type === 'chunk') {
            const phaseText = document.getElementById('loading-phase-text');
            if (phaseText && event.content && event.content.includes('[系统]')) {
              phaseText.textContent = event.content.replace(/[\n=]/g, '').trim();
            }
          }
        } catch (e) {
          if (e.message && !e.message.includes('JSON')) throw e;
        }
      }
    }

    if (outline) {
      state.currentProject.outline = outline;
      if (selectedTitle) state.currentProject.title = selectedTitle;
      else if (outline.title) state.currentProject.title = outline.title;
      renderOutline();
      showOutlinePhase('result');
    }
  } catch (e) {
    showNotification('生成大纲失败: ' + e.message, 'error');
  } finally {
    toggleSynapseLoading(false);
  }
}

function renderOutline() {
  const outline = state.currentProject?.outline;
  if (!outline) return;

  const titleEl = document.getElementById('outline-title-display');
  if (titleEl) titleEl.textContent = (state.currentProject.title || '') + ' \u2014 ';

  const container = document.getElementById('outline-cards');
  if (!container) return;

  let html = '';

  // === Helper: section icon ===
  const secIcon = (name) => {
    const m = {'\u6545\u4e8b\u6982\u89c8':'📖','\u4e3b\u9898':'🎯','\u89d2\u8272\u8bbe\u5b9a':'👥','\u4e16\u754c\u89c2\u8bbe\u5b9a':'🌍','\u5206\u96c6\u5927\u7eb2':'🎬','\u58f0\u97f3\u98ce\u683c':'🎵'};
    return m[name] || '📋';
  };

  // === Helper: make a collapsible section ===
  const mkSection = (title, bodyHtml, badge) => {
    return `\n    <div class="outline-section glass-card">
      <div class="outline-section-header" onclick="this.parentElement.classList.toggle('collapsed')">
        <div class="outline-section-title">
          <span class="outline-toggle-icon">\u25be</span>
          <span>${secIcon(title)} ${title}</span>
        </div>
        ${badge ? `<span class="outline-section-badge">${badge}</span>` : ''}
      </div>
      <div class="outline-section-body">
        ${bodyHtml}
      </div>
    </div>`;
  };

  // === Helper: make a collapsible sub-section ===
  const mkSubSection = (title, bodyHtml, extraTag) => {
    return `\n        <div class="outline-sub-section collapsed">
          <div class="outline-sub-header" onclick="event.stopPropagation();this.parentElement.classList.toggle('collapsed')">
            <div class="outline-sub-title">
              <span class="outline-toggle-icon">\u25b8</span>
              <span>${title}</span>
              ${extraTag ? `<span class="outline-role-tag">${extraTag}</span>` : ''}
            </div>
          </div>
          <div class="outline-sub-body">
            ${bodyHtml}
          </div>
        </div>`;
  };

  // === \u6545\u4e8b\u6982\u89c8 (synopsis / overview) ===
  const overviewText = outline.overview || outline.synopsis;
  if (overviewText) {
    html += mkSection('\u6545\u4e8b\u6982\u89c8', `<p style="margin:0;line-height:1.8;font-size:14px;">${esc(overviewText)}</p>`);
  }

  // === \u4e3b\u9898 ===
  if (outline.theme) {
    html += mkSection('\u4e3b\u9898', `<p style="margin:0;line-height:1.8;font-size:14px;">${esc(outline.theme)}</p>`);
  }

  // === \u89d2\u8272\u8bbe\u5b9a ===
  if (outline.characters?.length) {
    let charHtml = '';
    outline.characters.forEach((c) => {
      let details = `<div class="outline-detail-row"><span class="outline-detail-label">\u63cf\u8ff0</span><span class="outline-detail-value">${esc(c.description || '')}</span></div>`;
      if (c.personality) details += `<div class="outline-detail-row"><span class="outline-detail-label">\u6027\u683c</span><span class="outline-detail-value">${esc(c.personality)}</span></div>`;
      if (c.appearance) details += `<div class="outline-detail-row"><span class="outline-detail-label">\u5916\u8c8c</span><span class="outline-detail-value">${esc(c.appearance)}</span></div>`;
      if (c.background) details += `<div class="outline-detail-row"><span class="outline-detail-label">\u80cc\u666f</span><span class="outline-detail-value">${esc(c.background)}</span></div>`;
      if (c.arc) details += `<div class="outline-detail-row"><span class="outline-detail-label">\u89d2\u8272\u5f27</span><span class="outline-detail-value">${esc(c.arc)}</span></div>`;
      if (c.motivation) details += `<div class="outline-detail-row"><span class="outline-detail-label">\u52a8\u673a</span><span class="outline-detail-value">${esc(c.motivation)}</span></div>`;
      charHtml += mkSubSection(esc(c.name), details, esc(c.role || ''));
    });
    html += mkSection('\u89d2\u8272\u8bbe\u5b9a', charHtml, outline.characters.length);
  }

  // === \u4e16\u754c\u89c2\u8bbe\u5b9a ===
  if (outline.worldbuilding) {
    const wb = outline.worldbuilding;
    let wbHtml = '';
    if (typeof wb === 'string') {
      wbHtml = `<p style="margin:0;line-height:1.8;font-size:14px;">${esc(wb)}</p>`;
    } else {
      Object.entries(wb).forEach(([key, val]) => {
        if (val) wbHtml += `<div class="outline-detail-row"><span class="outline-detail-label">${esc(key)}</span><span class="outline-detail-value">${esc(typeof val === 'string' ? val : JSON.stringify(val))}</span></div>`;
      });
    }
    html += mkSection('\u4e16\u754c\u89c2\u8bbe\u5b9a', wbHtml);
  }

  // === \u5206\u96c6\u5927\u7eb2 ===
  const eps = outline.episodes || outline.chapters;
  if (eps?.length) {
    let epsHtml = '';
    eps.forEach((ep, ei) => {
      const epLabel = ep.episode || ('\u7b2c' + (ei + 1) + '\u96c6');
      let epDetails = '';
      if (ep.opening_hook) epDetails += `<div class="outline-detail-row"><span class="outline-detail-label" style="color:var(--purple-lavender)">\u5f00\u573a\u94a9\u5b50</span><span class="outline-detail-value">${esc(ep.opening_hook)}</span></div>`;
      epDetails += `<div class="outline-detail-row"><span class="outline-detail-label">\u6982\u8981</span><span class="outline-detail-value">${esc(ep.summary || '')}</span></div>`;
      if (ep.plot_thread) epDetails += `<div class="outline-detail-row"><span class="outline-detail-label">\u5267\u60c5\u7ebf</span><span class="outline-detail-value">${esc(ep.plot_thread)}</span></div>`;
      if (ep.cliffhanger) epDetails += `<div class="outline-detail-row"><span class="outline-detail-label" style="color:#f59e0b">\u60ac\u5ff5</span><span class="outline-detail-value" style="color:#fbbf24">${esc(ep.cliffhanger)}</span></div>`;
      if (ep.scenes?.length) {
        epDetails += `<div style="margin-top:10px;"><span class="outline-detail-label" style="display:block;margin-bottom:8px;font-weight:600;">\u573a\u666f\u5217\u8868\uff08${ep.scenes.length}\uff09</span>`;
        ep.scenes.forEach(s => {
          epDetails += `<div style="margin-bottom:6px;padding:8px 12px;background:rgba(255,255,255,0.03);border-radius:8px;font-size:13px;border-left:2px solid var(--purple-deep);">`;
          epDetails += `<strong style="color:var(--purple-lavender)">${s.scene_id || ''}</strong> `;
          epDetails += `<span style="color:var(--text-secondary)">${esc(s.description || '')}</span>`;
          if (s.mood) epDetails += `<br><span style="color:var(--text-muted);font-size:12px;">\u6c1b\u56f4: ${esc(s.mood)}</span>`;
          epDetails += `</div>`;
        });
        epDetails += `</div>`;
      }
      const subTitle = `${epLabel}${esc(ep.title ? ' \u2014 ' + ep.title : '')}`;
      epsHtml += mkSubSection(subTitle, epDetails);
    });
    html += mkSection('\u5206\u96c6\u5927\u7eb2', epsHtml, eps.length);
  }

  // === \u58f0\u97f3\u98ce\u683c\u8bbe\u5b9a ===
  const soundStyle = outline.sound_style || outline.soundStyle;
  if (soundStyle) {
    let ssHtml = '';
    if (typeof soundStyle === 'string') {
      ssHtml = `<p style="margin:0;line-height:1.8;font-size:14px;">${esc(soundStyle)}</p>`;
    } else {
      Object.entries(soundStyle).forEach(([key, val]) => {
        if (val) ssHtml += `<div class="outline-detail-row"><span class="outline-detail-label">${esc(key)}</span><span class="outline-detail-value">${esc(typeof val === 'string' ? val : JSON.stringify(val))}</span></div>`;
      });
    }
    html += mkSection('\u58f0\u97f3\u98ce\u683c\u8bbe\u5b9a', ssHtml);
  }

  // Fallback: if nothing rendered, show a message
  if (!html) {
    html = '<div class="glass-card" style="text-align:center;padding:40px;"><p style="color:var(--text-secondary);">\u5927\u7eb2\u6570\u636e\u4e3a\u7a7a\u6216\u683c\u5f0f\u672a\u77e5</p></div>';
  }

  container.innerHTML = html;
}
function modifyOutline() {
  showPromptModal('修改大纲', async (instruction) => {
    toggleSynapseLoading(true, 'SYNAPSE 大纲引擎', '正在修改大纲...');
    try {
      const result = await api(`/api/projects/${state.currentProject.id}/outline/modify`, 'POST', { instruction }, 300000);
      // 前端防御：校验返回的outline结构
      const outline = result.outline;
      if (!outline || typeof outline !== 'object') {
        showNotification('AI返回格式错误，大纲未改变', 'error');
        return;
      }
      const eps = outline.episodes || outline.chapters;
      if (!Array.isArray(eps) || eps.length === 0) {
        showNotification('AI返回的大纲数据不完整，大纲未改变', 'error');
        return;
      }
      state.currentProject.outline = outline;
      renderOutline();
      showNotification('大纲已优化');
    } catch (e) {
      showNotification('修改大纲失败: ' + e.message, 'error');
    } finally {
      toggleSynapseLoading(false);
    }
  });
}

function confirmOutline() {
  showStep(3);
}

// 
//  4
// 

function renderCharacters() {
  const characters = state.currentProject?.characters;
  const grid = document.getElementById('characters-grid');

  if (!characters || characters.length === 0) {
    grid.innerHTML = '<div class="glass-card" style="text-align:center;padding:40px;"><p style="color:var(--text-secondary);font-size:16px;margin-bottom:16px;">尚未生成角色，点击下方按钮开始</p><br><button class="btn btn-primary" onclick="generateCharacters()">生成角色</button></div>';
    return;
  }

  grid.innerHTML = characters.map((c, i) => {
    const prompt = c.prompt || '';
    const isLong = prompt.length > 120;
    const shortPrompt = isLong ? prompt.substring(0, 120) + '...' : prompt;
    const imgSrc = c.image_path ? `${API}/api/file?path=${encodeURIComponent(c.image_path)}&t=${Date.now()}` : '';
    return `
    <div class="glass-card character-card" data-char-index="${i}">
      <div class="character-card-image">
        ${imgSrc ? `<img src="${imgSrc}" alt="${esc(c.name)}" onclick="openLightbox('${imgSrc}')" style="cursor:zoom-in">` : '<div class="character-placeholder"></div>'}
        <label class="character-upload-btn" title="上传定妆照">
          <input type="file" accept="image/*" style="display:none" onchange="handleCharacterUpload('${esc(c.name)}', this.files[0])">
          <span class="upload-icon">+</span>
        </label>
      </div>
      <div class="character-info">
        <h4>${esc(c.name)}</h4>
        <div class="prompt-text collapsed" id="prompt-${i}">
          <span class="prompt-short">${esc(shortPrompt)}</span>
          ${isLong ? `<span class="prompt-full" style="display:none">${esc(prompt)}</span>` : ''}
        </div>
        ${isLong ? `<button class="btn-link prompt-toggle" onclick="togglePromptExpand(${i}, this)">展开全部</button>` : ''}
        ${c.error ? `<p style="color:#f87171;font-size:12px;margin-top:4px;">${esc(c.error)}</p>` : ''}
        <div class="character-actions">
          <button class="btn btn-secondary btn-sm" onclick="retryCharacter('${esc(c.name)}')">重试生成</button>
          <button class="btn btn-secondary btn-sm" onclick="regenerateCharacter('${esc(c.name)}')">重新设计</button>
          <button class="btn btn-secondary btn-sm" onclick="modifyCharacter('${esc(c.name)}')">AI修改</button>
          ${imgSrc ? `<button class="btn btn-secondary btn-sm" onclick="exportCharacter('${esc(c.name)}')">导出</button>` : ''}
        </div>
      </div>
    </div>`;
  }).join('');
}

function togglePromptExpand(index, btn) {
  const el = document.getElementById('prompt-' + index);
  if (!el) return;
  const shortEl = el.querySelector('.prompt-short');
  const fullEl = el.querySelector('.prompt-full');
  if (el.classList.contains('collapsed')) {
    el.classList.remove('collapsed');
    if (shortEl) shortEl.style.display = 'none';
    if (fullEl) fullEl.style.display = 'inline';
    btn.textContent = '收起';
  } else {
    el.classList.add('collapsed');
    if (shortEl) shortEl.style.display = 'inline';
    if (fullEl) fullEl.style.display = 'none';
    btn.textContent = '展开全部';
  }
}

async function exportCharacter(name) {
  const chars = state.currentProject?.characters;
  if (!chars) return;
  const c = chars.find(ch => ch.name === name);
  if (!c || !c.image_path) { showNotification('没有可导出的定妆照', 'error'); return; }
  try {
    const result = await window.pywebview.api.export_poster_to_path(c.image_path, `${name}_定妆照.png`);
    if (result?.success) {
      showNotification('定妆照已保存');
    } else if (!result?.cancelled) {
      showNotification('保存失败: ' + (result?.error || '未知错误'), 'error');
    }
  } catch (e) {
    showNotification('保存失败: ' + e.message, 'error');
  }
}

async function handleCharacterUpload(name, file) {
  console.log('handleCharacterUpload triggered:', name, file);
  if (!file) return;
  const formData = new FormData();
  formData.append('image', file);
  toggleSynapseLoading(true, 'SYNAPSE 角色引擎', '正在上传定妆照...');
  try {
    const result = await api(`/api/projects/${state.currentProject.id}/characters/${encodeURIComponent(name)}/upload`, 'POST', formData);
    const chars = state.currentProject.characters;
    const idx = chars.findIndex(c => c.name === name);
    if (idx >= 0) chars[idx].image_path = result.image_path;
    renderCharacters();
    showNotification('定妆照已更新');
  } catch (e) {
    showNotification('上传失败: ' + e.message, 'error');
  } finally {
    toggleSynapseLoading(false);
  }
}

function modifyCharacter(name) {
  showPromptModal('AI修改角色', async (instruction) => {
    toggleSynapseLoading(true, 'SYNAPSE 角色引擎', '正在修改角色...');
    try {
      const result = await api(`/api/projects/${state.currentProject.id}/characters/${encodeURIComponent(name)}/regenerate`, 'POST', { instruction }, 300000);
      const chars = state.currentProject.characters;
      const idx = chars.findIndex(c => c.name === name);
      if (idx >= 0) {
        chars[idx].prompt = result.prompt;
        chars[idx].image_path = result.image_path;
      }
      renderCharacters();
    } catch (e) {
      showNotification('修改失败: ' + e.message, 'error');
    } finally {
      toggleSynapseLoading(false);
    }
  });
}

async function generateCharacters() {
  toggleSynapseLoading(true, 'SYNAPSE 角色引擎', '正在准备生成角色设定...');
  try {
    const resp = await fetch(`${API}/api/projects/${state.currentProject.id}/characters/generate`, { method: 'POST' });
    if (!resp.ok) {
      let msg = '请求失败';
      try { const e = await resp.json(); msg = e.detail || e.message || msg; } catch(_) {}
      throw new Error(msg);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalCharacters = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // Parse SSE events
      const lines = buffer.split('\n');
      buffer = lines.pop(); // Keep incomplete line
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          if (evt.type === 'progress') {
            const pct = Math.round((evt.completed / evt.total) * 100);
            const charName = evt.character?.name || '';
            const status = evt.character?.error ? '(失败)' : '(完成)';
            toggleSynapseLoading(true, 'SYNAPSE 角色引擎',
              `已完成 ${evt.completed}/${evt.total} 个角色 — ${charName} ${status}`);
            // 更新进度条
            const bar = document.getElementById('synapse-progress-bar');
            const pctEl = document.getElementById('synapse-progress-percent');
            if (bar) bar.style.width = pct + '%';
            if (pctEl) pctEl.innerText = pct + '%';
          } else if (evt.type === 'complete') {
            finalCharacters = evt.characters;
          }
        } catch (_) {}
      }
    }

    if (finalCharacters) {
      state.currentProject.characters = finalCharacters;
      renderCharacters();
    }
  } catch (e) {
    showNotification('角色生成失败: ' + e.message, 'error');
  } finally {
    toggleSynapseLoading(false);
  }
}

async function retryCharacter(name) {
  toggleSynapseLoading(true, 'SYNAPSE 角色引擎', '正在重试生成...');
  try {
    const result = await api(`/api/projects/${state.currentProject.id}/characters/${encodeURIComponent(name)}/retry`, 'POST', null, 300000);
    const chars = state.currentProject.characters;
    const idx = chars.findIndex(c => c.name === name);
    if (idx >= 0) {
      chars[idx].prompt = result.prompt;
      chars[idx].image_path = result.image_path;
      delete chars[idx].error;
    }
    renderCharacters();
    showNotification('重试成功');
  } catch (e) {
    showNotification('重试失败: ' + e.message, 'error');
  } finally {
    toggleSynapseLoading(false);
  }
}

function regenerateCharacter(name) {
  showPromptModal('重新设计角色', async (instruction) => {
    toggleSynapseLoading(true, 'SYNAPSE 角色引擎', '正在重新设计角色...');
    try {
      const result = await api(`/api/projects/${state.currentProject.id}/characters/${encodeURIComponent(name)}/regenerate`, 'POST', { instruction }, 300000);
      const chars = state.currentProject.characters;
      const idx = chars.findIndex(c => c.name === name);
      if (idx >= 0) {
        chars[idx].prompt = result.prompt;
        chars[idx].image_path = result.image_path;
      }
      renderCharacters();
    } catch (e) {
      showNotification('重新设计失败: ' + e.message, 'error');
    } finally {
      toggleSynapseLoading(false);
    }
  });
}

async function confirmCharacters() {
  try {
    await api(`/api/projects/${state.currentProject.id}/characters/confirm`, 'POST', {
      characters: state.currentProject.characters,
    });
    showStep(4);
  } catch (e) {
    showNotification('确认角色失败: ' + e.message, 'error');
  }
}

// 
//  5
// ── 第5步：小说 ──

async function renderNovel() {
  const chapters = state.currentProject?.outline?.episodes || state.currentProject?.outline?.chapters || [];
  const nav = document.getElementById('chapter-nav');
  nav.innerHTML = chapters.map((ch, i) => `
    <div class="chapter-tab ${i === state.currentChapter ? 'active' : ''}" onclick="switchChapter(${i})">${i+1} ${esc(ch.title || '')}</div>
  `).join('');

  // Auto-batch: only generate first 3 chapters, rest user-triggered
  const missing = [];
  for (let i = 0; i < chapters.length; i++) {
    if (!state.currentProject?.chapters?.[String(i)]?.novel_text) {
      missing.push(i);
    }
  }

  if (missing.length > 0) {
    // Only auto-generate first 3 chapters
    const autoBatch = missing.slice(0, 3);
    const manualBatch = missing.slice(3);
    await batchGenerateNovel(autoBatch, chapters.length);
    // If there are more chapters to generate, show a button
    if (manualBatch.length > 0) {
      const bar = document.getElementById('novel-action-bar');
      if (bar) {
        bar.innerHTML += `<button class="btn btn-secondary" onclick="batchGenerateRemaining()">批量生成剩余 ${manualBatch.length} 集</button>`;
      }
    }
  } else {
    loadChapter(state.currentChapter);
    checkNovelComplete();
  }
}

async function batchGenerateNovel(missingIndices, total) {
  await stepGenerateNovel(missingIndices, total);
}

async function batchGenerateRemaining() {
  const chapters = state.currentProject?.outline?.episodes || state.currentProject?.outline?.chapters || [];
  const missing = [];
  for (let i = 0; i < chapters.length; i++) {
    if (!state.currentProject?.chapters?.[String(i)]?.novel_text) {
      missing.push(i);
    }
  }
  if (missing.length > 0) {
    await batchGenerateNovel(missing, chapters.length);
  }
  checkNovelComplete();
}

function checkNovelComplete() {
  const chapters = state.currentProject?.outline?.episodes || state.currentProject?.outline?.chapters || [];
  if (chapters.length === 0) return;
  const allDone = chapters.every((_, i) => state.currentProject?.chapters?.[String(i)]?.novel_text);
  const bar = document.getElementById('novel-action-bar');
  if (!bar) return;
  if (allDone) {
    bar.innerHTML = '<button class="btn btn-primary" onclick="enterStoryboard()">全部小说完成，进入分镜</button>';
  }
}

function enterStoryboard() {
  autoBatchStoryboard().then(() => {
    showStep(5);
  });
}

async function batchGenerateRemainingStoryboard() {
  const chapters = state.currentProject?.outline?.episodes || state.currentProject?.outline?.chapters || [];
  const missing = [];
  for (let i = 0; i < chapters.length; i++) {
    if (!state.currentProject?.storyboards?.[String(i)]?.clips || state.currentProject.storyboards[String(i)].clips.length === 0) {
      missing.push(i);
    }
  }
  if (missing.length === 0) return;
  toggleSynapseLoading(true, 'SYNAPSE 分镜引擎', `正在并行生成 ${missing.length} 集分镜...`);
  const phaseEl = document.getElementById('loading-phase-text');
  const subEl = document.getElementById('synapse-loading-subtext');
  const barEl = document.getElementById('synapse-progress-bar');
  const pctEl = document.getElementById('synapse-progress-percent');
  if (phaseEl) phaseEl.innerText = `正在并行生成 ${missing.length} 集分镜脚本...`;
  if (subEl) subEl.innerText = `共 ${missing.length} 集同时生成中，请耐心等待`;
  if (barEl) barEl.style.width = '50%';
  if (pctEl) pctEl.innerText = '生成中...';
  try {
    const result = await api(`/api/projects/${state.currentProject.id}/storyboard/batch`, 'POST', { chapter_indices: missing }, 1800000);
    state.currentProject.storyboards = state.currentProject.storyboards || {};
    const successKeys = Object.keys(result.results || {});
    for (const k of successKeys) {
      state.currentProject.storyboards[k] = { clips: result.results[k].clips, confirmed: false };
    }
    if (barEl) barEl.style.width = '100%';
    if (pctEl) pctEl.innerText = '100%';
    const errorCount = Object.keys(result.errors || {}).length;
    if (errorCount > 0) {
      const firstErr = Object.entries(result.errors)[0];
      showNotification(`${successKeys.length} 集成功，${errorCount} 集失败（第${Number(firstErr[0])+1}集: ${firstErr[1]}）`);
    } else {
      showNotification(`全部 ${successKeys.length} 集分镜已生成`);
    }
  } catch (e) {
    showNotification('批量生成分镜失败: ' + e.message, 'error');
  }
  toggleSynapseLoading(false);
  renderStoryboard();
}

function checkStoryboardComplete() {
  const chapters = state.currentProject?.outline?.episodes || state.currentProject?.outline?.chapters || [];
  if (chapters.length === 0) return;
  const allDone = chapters.every((_, i) => {
    const sb = state.currentProject?.storyboards?.[String(i)];
    return sb?.clips && sb.clips.length > 0;
  });
  // If all storyboards are generated, the confirm button is already visible
  // No additional UI change needed - user clicks "确认分镜" when ready
}

async function switchChapter(index) {
  state.currentChapter = index;
  document.querySelectorAll('.chapter-tab').forEach((el, i) => {
    el.classList.toggle('active', i === index);
  });
  loadChapter(index);
  // 刷新分镜面板显示对应集数 + 更新action-bar按钮
  renderStoryboard();
}

async function loadChapter(index) {
  const display = document.getElementById('novel-display');
  const chapterData = state.currentProject?.chapters?.[String(index)];

  if (chapterData?.novel_text) {
    const text = chapterData.novel_text;
    // 上传小说模式：隐藏重新生成和AI修改按钮
    const isUploaded = state.currentProject?.settings?.novel_source === 'uploaded';
    const toolbarHtml = isUploaded ? `
      <div class="novel-toolbar">
        <span style="font-size:12px;color:var(--text-muted);">用户上传小说 (只读)</span>
      </div>
    ` : `
      <div class="novel-toolbar">
        <button class="btn btn-secondary btn-sm" onclick="toggleNovelEdit()">编辑</button>
        <div class="novel-toolbar-actions">
          <button class="novel-action-card" onclick="regenerateNovel()">
            <span class="novel-action-icon">&#x21bb;</span>
            <span class="novel-action-label">重新生成本集</span>
          </button>
          <button class="novel-action-card" onclick="showAIModifyPanel()">
            <span class="novel-action-icon">&#x270f;</span>
            <span class="novel-action-label">AI修改</span>
          </button>
        </div>
      </div>
      <div class="novel-ai-modify-panel" id="novel-ai-modify-panel" style="display:none;">
        <div class="novel-ai-modify-header">
          <span>用大白话告诉AI怎么改</span>
          <button class="btn-close-sm" onclick="hideAIModifyPanel()">&#x2715;</button>
        </div>
        <textarea class="novel-ai-modify-input" id="novel-ai-modify-input" placeholder="例如：把开头改得更紧张一些 / 加多一点对话 / 让主角的性格更果断"></textarea>
        <button class="btn btn-primary btn-sm" onclick="submitAIModify()">发送修改指令</button>
      </div>
    `;
    const editAreaHtml = isUploaded ? '' : `<textarea class="novel-edit-area" id="novel-edit-area" style="display:none;">${esc(text)}</textarea>`;
    display.innerHTML = `
      ${toolbarHtml}
      <div class="novel-text" id="novel-text-body">${esc(text)}</div>
      ${editAreaHtml}
    `;
  } else {
    display.innerHTML = `
      <div style="text-align:center;padding:40px;">
        <p style="color:var(--text-secondary);margin-bottom:20px;">第${index+1}集尚未生成小说正文</p>
        <button class="btn btn-primary" onclick="generateNovel(${index})">生成本集小说</button>
      </div>
    `;
  }
  renderEmotionCurve(index);
}

function toggleNovelEdit() {
  const textBody = document.getElementById('novel-text-body');
  const editArea = document.getElementById('novel-edit-area');
  if (!textBody || !editArea) return;

  if (editArea.style.display === 'none') {
    editArea.style.display = 'block';
    editArea.value = textBody.textContent;
    textBody.style.display = 'none';
    editArea.focus();
  } else {
    const newText = editArea.value;
    textBody.textContent = newText;
    textBody.style.display = 'block';
    editArea.style.display = 'none';
    // Save to state
    const idx = state.currentChapter;
    if (state.currentProject?.chapters?.[String(idx)]) {
      state.currentProject.chapters[String(idx)].novel_text = newText;
    }
    // Save to server
    api(`/api/projects/${state.currentProject.id}/novel/${idx}/save`, 'POST', { novel_text: newText }).catch(() => {});
  }
}

async function generateNovel(index) {
  toggleSynapseLoading(true, 'SYNAPSE 小说引擎', `正在创作第${index+1}章...`);
  try {
    const result = await api(`/api/projects/${state.currentProject.id}/novel/${index}`, 'POST', null, 300000);
    state.currentProject.chapters[String(index)] = result.chapter;
    loadChapter(index);
    checkNovelComplete();
  } catch (e) {
    showNotification('小说生成失败: ' + e.message, 'error');
  } finally {
    toggleSynapseLoading(false);
  }
}

function regenerateNovel() {
  generateNovel(state.currentChapter);
}

function modifyNovel() {
  showPromptModal('AI优化小说', async (instruction) => {
    toggleSynapseLoading(true, 'SYNAPSE 小说引擎', '正在修改小说内容...');
    try {
      const result = await api(`/api/projects/${state.currentProject.id}/novel/${state.currentChapter}/modify`, 'POST', { instruction }, 300000);
      state.currentProject.chapters[String(state.currentChapter)].novel_text = result.novel_text;
      loadChapter(state.currentChapter);
    } catch (e) {
      showNotification('修改小说失败: ' + e.message, 'error');
    } finally {
      toggleSynapseLoading(false);
    }
  });
}

function showAIModifyPanel() {
  const panel = document.getElementById('novel-ai-modify-panel');
  if (panel) {
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
  }
}

function hideAIModifyPanel() {
  const panel = document.getElementById('novel-ai-modify-panel');
  if (panel) panel.style.display = 'none';
}

async function submitAIModify() {
  const input = document.getElementById('novel-ai-modify-input');
  if (!input || !input.value.trim()) {
    showNotification('请输入修改指令', 'error');
    return;
  }
  const instruction = input.value.trim();
  hideAIModifyPanel();
  toggleSynapseLoading(true, 'SYNAPSE 小说引擎', '正在按指令修改小说...');
  try {
    const result = await api(`/api/projects/${state.currentProject.id}/novel/${state.currentChapter}/modify`, 'POST', { instruction });
    state.currentProject.chapters[String(state.currentChapter)].novel_text = result.novel_text;
    loadChapter(state.currentChapter);
    showNotification('小说已修改');
  } catch (e) {
    showNotification('修改小说失败: ' + e.message, 'error');
  } finally {
    toggleSynapseLoading(false);
  }
}

// 
//  6
// 

// Auto-batch storyboard generation (called once on enter, not on every render)
async function autoBatchStoryboard() {
  const chapters = state.currentProject?.outline?.chapters || state.currentProject?.outline?.episodes || [];
  const missing = [];
  for (let i = 0; i < chapters.length; i++) {
    if (!state.currentProject?.storyboards?.[String(i)]?.clips || state.currentProject.storyboards[String(i)].clips.length === 0) {
      missing.push(i);
    }
  }
  if (missing.length === 0) return;

  // 全部并行：一次调batch接口生成所有集
  toggleSynapseLoading(true, 'SYNAPSE 分镜引擎', `正在并行生成 ${missing.length} 集分镜...`);
  const phaseEl = document.getElementById('loading-phase-text');
  const subEl = document.getElementById('synapse-loading-subtext');
  const barEl = document.getElementById('synapse-progress-bar');
  const pctEl = document.getElementById('synapse-progress-percent');
  if (phaseEl) phaseEl.innerText = `正在并行生成 ${missing.length} 集分镜脚本...`;
  if (subEl) subEl.innerText = `共 ${missing.length} 集同时生成中，请耐心等待`;
  if (barEl) barEl.style.width = '50%';
  if (pctEl) pctEl.innerText = '生成中...';
  try {
    const result = await api(`/api/projects/${state.currentProject.id}/storyboard/batch`, 'POST', { chapter_indices: missing }, 1800000);
    state.currentProject.storyboards = state.currentProject.storyboards || {};
    const successKeys = Object.keys(result.results || {});
    for (const k of successKeys) {
      state.currentProject.storyboards[k] = { clips: result.results[k].clips, confirmed: false };
    }
    if (barEl) barEl.style.width = '100%';
    if (pctEl) pctEl.innerText = '100%';
    const errorCount = Object.keys(result.errors || {}).length;
    if (errorCount > 0) {
      const firstErr = Object.entries(result.errors)[0];
      showNotification(`${successKeys.length} 集成功，${errorCount} 集失败（第${Number(firstErr[0])+1}集: ${firstErr[1]}）`);
    } else {
      showNotification(`全部 ${successKeys.length} 集分镜已生成`);
    }
    renderStoryboard();
  } catch (e) {
    showNotification('批量生成分镜失败: ' + e.message, 'error');
  }
  toggleSynapseLoading(false);
}

// Pure render: read state and display storyboard for current chapter
function renderStoryboard() {
  const timeline = document.getElementById('storyboard-timeline');
  if (!timeline) return;
  // 计算未生成分镜的集数
  const chapters = state.currentProject?.outline?.episodes || state.currentProject?.outline?.chapters || [];
  const missing = [];
  for (let i = 0; i < chapters.length; i++) {
    const sb = state.currentProject?.storyboards?.[String(i)];
    if (!sb?.clips || sb.clips.length === 0) {
      missing.push(i);
    }
  }
  // 更新action-bar中的批量生成按钮
  const batchBtn = document.getElementById('btn-batch-remaining');
  if (batchBtn) {
    if (missing.length > 0) {
      batchBtn.textContent = `批量生成剩余 ${missing.length} 集分镜`;
      batchBtn.style.display = '';
    } else {
      batchBtn.style.display = 'none';
    }
  }
  renderCurrentChapterStoryboard(missing);
}

function renderCurrentChapterStoryboard(remainingBatch) {
  const chapters = state.currentProject?.outline?.chapters || state.currentProject?.outline?.episodes || [];
  const timeline = document.getElementById('storyboard-timeline');
  if (!timeline) return;

  const storyboard = state.currentProject?.storyboards?.[String(state.currentChapter)];
  const clips = Array.isArray(storyboard?.clips) ? storyboard.clips : (storyboard?.clips?.clips ? storyboard.clips.clips : []);

  if (!clips || clips.length === 0) {
    timeline.innerHTML = `
      <div class="glass-card" style="text-align:center;padding:40px;">
        <p style="color:var(--text-secondary);margin-bottom:12px;">第 ${state.currentChapter + 1} 集</p>
        <div class="chapter-nav" style="justify-content:center;margin-bottom:20px;">
          ${chapters.map((ch, i) => `<div class="chapter-tab ${i === state.currentChapter ? 'active' : ''}" onclick="switchChapter(${i})">${i+1}</div>`).join('')}
        </div>
        <button class="btn btn-primary" onclick="generateStoryboard()">生成分镜脚本</button>
      </div>
    `;
    return;
  }

  // Helper: build A-track HTML (参考图)
  function buildATrack(a) {
    if (!a) return '<p style="color:var(--text-secondary);font-size:12px;">无A轨数据</p>';
    return `
      <div class="track-label" style="color:var(--purple-lavender);font-weight:600;margin-bottom:8px;">A轨 / 参考图</div>
      <div style="margin-bottom:8px;">
        <span style="color:var(--accent-light);font-size:11px;font-weight:600;">场景描述：</span>
        <span style="color:var(--text-primary);font-size:12px;">${esc(a.scene_description || '')}</span>
      </div>
      <div style="margin-bottom:8px;">
        <span style="color:var(--accent-light);font-size:11px;font-weight:600;">镜头：</span>
        <span style="color:var(--text-primary);font-size:12px;">${esc(a.camera || '')}</span>
      </div>
      <div style="margin-bottom:8px;">
        <span style="color:var(--accent-light);font-size:11px;font-weight:600;">Reference Prompt：</span>
        <div style="color:var(--text-secondary);font-size:11px;background:rgba(0,0,0,0.3);padding:8px;border-radius:6px;margin-top:4px;word-break:break-all;line-height:1.5;">${esc(a.reference_prompt || a.image_prompt || '')}</div>
      </div>
      <div>
        <span style="color:var(--accent-light);font-size:11px;font-weight:600;">Negative Prompt：</span>
        <div style="color:var(--text-secondary);font-size:11px;background:rgba(0,0,0,0.3);padding:8px;border-radius:6px;margin-top:4px;word-break:break-all;line-height:1.5;">${esc(a.negative_prompt || '')}</div>
      </div>
    `;
  }

  // Helper: build C-track HTML (尾帧)
  function buildCTrack(c) {
    if (!c) return '<p style="color:var(--text-secondary);font-size:12px;">无C轨数据</p>';
    return `
      <div class="track-label" style="color:var(--purple-lavender);font-weight:600;margin-bottom:8px;">C轨 / 尾帧</div>
      <div style="margin-bottom:8px;">
        <span style="color:var(--accent-light);font-size:11px;font-weight:600;">场景描述：</span>
        <span style="color:var(--text-primary);font-size:12px;">${esc(c.scene_description || '')}</span>
      </div>
      <div style="margin-bottom:8px;">
        <span style="color:var(--accent-light);font-size:11px;font-weight:600;">镜头：</span>
        <span style="color:var(--text-primary);font-size:12px;">${esc(c.camera || '')}</span>
      </div>
      <div style="margin-bottom:8px;">
        <span style="color:var(--accent-light);font-size:11px;font-weight:600;">Tail Frame Prompt：</span>
        <div style="color:var(--text-secondary);font-size:11px;background:rgba(0,0,0,0.3);padding:8px;border-radius:6px;margin-top:4px;word-break:break-all;line-height:1.5;">${esc(c.tail_frame_prompt || '')}</div>
      </div>
      <div>
        <span style="color:var(--accent-light);font-size:11px;font-weight:600;">Negative Prompt：</span>
        <div style="color:var(--text-secondary);font-size:11px;background:rgba(0,0,0,0.3);padding:8px;border-radius:6px;margin-top:4px;word-break:break-all;line-height:1.5;">${esc(c.negative_prompt || '')}</div>
      </div>
    `;
  }

  // Helper: build B-track HTML
  function buildBTrack(b) {
    if (!b) return '<p style="color:var(--text-secondary);font-size:12px;">无B轨数据</p>';
    let html = '<div class="track-label" style="color:var(--purple-lavender);font-weight:600;margin-bottom:8px;">B轨 / 音视频动态</div>';

    // Video Action
    if (b.video_action) {
      html += `
        <div style="margin-bottom:10px;">
          <span style="color:var(--accent-light);font-size:11px;font-weight:600;">Video Action：</span>
          <div style="color:var(--text-secondary);font-size:11px;background:rgba(0,0,0,0.3);padding:8px;border-radius:6px;margin-top:4px;line-height:1.5;">${esc(b.video_action)}</div>
        </div>
      `;
    }

    // Dialogue
    if (b.dialogue && b.dialogue.length > 0) {
      html += '<div style="margin-bottom:10px;"><span style="color:var(--accent-light);font-size:11px;font-weight:600;">Dialogue：</span>';
      b.dialogue.forEach(d => {
        const del = d.delivery || {};
        html += `
          <div style="background:rgba(157,78,221,0.08);border-left:3px solid var(--accent);padding:8px 10px;border-radius:0 6px 6px 0;margin-top:6px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
              <span style="color:var(--accent);font-size:12px;font-weight:600;">${esc(d.character || '?')}</span>
              ${del.gender ? `<span style="font-size:10px;color:var(--text-secondary);background:rgba(255,255,255,0.06);padding:1px 6px;border-radius:4px;">${del.gender}${del.age ? ', '+del.age : ''}</span>` : ''}
              ${del.volume ? `<span style="font-size:10px;color:var(--text-secondary);background:rgba(255,255,255,0.06);padding:1px 6px;border-radius:4px;">${del.volume}</span>` : ''}
              ${del.speed ? `<span style="font-size:10px;color:var(--text-secondary);background:rgba(255,255,255,0.06);padding:1px 6px;border-radius:4px;">${del.speed}</span>` : ''}
            </div>
            <div style="color:var(--text-primary);font-size:13px;font-style:italic;line-height:1.5;">"${esc(d.line || '')}"</div>
            ${d.emotion ? `<div style="color:var(--text-secondary);font-size:11px;margin-top:3px;">${esc(d.emotion)}</div>` : ''}
            ${del.tone ? `<div style="color:var(--purple-lavender);font-size:10px;margin-top:2px;font-style:italic;">Tone: ${esc(del.tone)}</div>` : ''}
          </div>
        `;
      });
      html += '</div>';
    }

    // Narration
    if (b.narration) {
      html += `
        <div style="margin-bottom:10px;">
          <span style="color:var(--accent-light);font-size:11px;font-weight:600;">Narration：</span>
          <div style="color:var(--text-secondary);font-size:11px;font-style:italic;background:rgba(0,0,0,0.3);padding:8px;border-radius:6px;margin-top:4px;line-height:1.5;">${esc(b.narration)}</div>
        </div>
      `;
    }

    // Sound Effects
    if (b.sound_effects && b.sound_effects.length > 0) {
      html += '<div style="margin-bottom:10px;"><span style="color:var(--accent-light);font-size:11px;font-weight:600;">Sound Effects：</span>';
      html += '<div style="display:flex;flex-direction:column;gap:4px;margin-top:4px;">';
      b.sound_effects.forEach(sfx => {
        html += `
          <div style="display:flex;align-items:center;gap:8px;background:rgba(0,0,0,0.2);padding:6px 8px;border-radius:4px;font-size:11px;">
            <span style="color:var(--text-primary);font-weight:500;min-width:60px;">${esc(sfx.name || sfx.type || '')}</span>
            <span style="color:var(--text-secondary);flex:1;">${esc(sfx.description || '')}</span>
          </div>
        `;
      });
      html += '</div></div>';
    }

    // Background Music
    if (b.background_music) {
      const bgm = b.background_music;
      html += `
        <div>
          <span style="color:var(--accent-light);font-size:11px;font-weight:600;">Background Music：</span>
          <div style="background:rgba(0,0,0,0.2);padding:8px;border-radius:6px;margin-top:4px;font-size:11px;">
            ${(bgm.style_and_instruments || bgm.style) ? `<div><span style="color:var(--text-secondary);">Style:</span> <span style="color:var(--text-primary);">${esc(bgm.style_and_instruments || bgm.style || '')}</span></div>` : ''}
            ${(bgm.mood_and_key || bgm.mood) ? `<div><span style="color:var(--text-secondary);">Mood:</span> <span style="color:var(--text-primary);">${esc(bgm.mood_and_key || bgm.mood || '')}</span></div>` : ''}
            ${bgm.tempo ? `<div><span style="color:var(--text-secondary);">Tempo:</span> <span style="color:var(--text-primary);">${esc(bgm.tempo)}</span></div>` : ''}
          </div>
        </div>
      `;
    }

    // Fallback for old format (sfx/bgm_mood strings)
    if (!b.video_action && !b.sound_effects && b.sfx) {
      html += `<div style="margin-bottom:8px;"><span style="color:var(--accent-light);font-size:11px;font-weight:600;">SFX：</span><div style="color:var(--text-secondary);font-size:11px;margin-top:4px;">${esc(b.sfx)}</div></div>`;
    }
    if (!b.background_music && b.bgm_mood) {
      html += `<div><span style="color:var(--accent-light);font-size:11px;font-weight:600;">BGM：</span><div style="color:var(--text-secondary);font-size:11px;margin-top:4px;">${esc(b.bgm_mood)}</div></div>`;
    }

    return html;
  }

  const chapterTabs = chapters.map((ch, i) => `<div class="chapter-tab ${i === state.currentChapter ? 'active' : ''}" onclick="switchChapter(${i})">${i+1}</div>`).join('');

  let html = `<div class="chapter-nav" style="margin-bottom:16px;">${chapterTabs}</div>`;

  // Sort mode toolbar
  if (_sortMode) {
    html += `<div class="sort-toolbar">
      <span class="sort-hint">拖拽卡片调整顺序</span>
      <span class="sort-count">${clips.length} 个片段</span>
      <button class="btn btn-primary btn-sm" onclick="saveSortMode()" style="padding:6px 18px;font-size:12px;">保存排序</button>
      <button class="btn btn-secondary btn-sm" onclick="cancelSortMode()" style="padding:6px 18px;font-size:12px;">取消</button>
    </div>`;
  }

  // Reorder clips in sort mode
  const orderedClips = _sortMode && _sortOrder.length === clips.length
    ? _sortOrder.map(origIdx => ({ clip: clips[origIdx], origIdx }))
    : clips.map((clip, i) => ({ clip, origIdx: i }));

  orderedClips.forEach(({ clip, origIdx }, i) => {
    const a = clip.a_track || {};
    const b = clip.b_track || {};
    const dur = clip.duration || '?';
    const trans = clip.transition || 'cut';
    const sceneDesc = a.scene_description || clip.description || clip.text || '片段 ' + (i+1);

    const charactersInScene = clip.characters_in_scene || [];
    const charBadges = charactersInScene.length > 0
      ? `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;">` + charactersInScene.map(ch => `<span style="font-size:10px;color:var(--accent);background:rgba(157,78,221,0.12);padding:2px 8px;border-radius:10px;">${esc(ch)}</span>`).join('') + `</div>`
      : '';

    html += `
      <div class="clip-card glass-card" style="margin-bottom:12px;" data-clip-idx="${origIdx}" onclick="if(!_sortMode)this.classList.toggle('expanded')">
        <div class="sort-handle"><div class="sort-handle-dots"><span></span><span></span><span></span><span></span><span></span><span></span></div></div>
        <div>
          <div class="clip-header">
            <div style="display:flex;align-items:center;gap:10px;">
              <span class="clip-num">${origIdx+1}</span>
              <span style="color:var(--text-primary);font-size:13px;font-weight:500;">${esc(sceneDesc)}</span>
            </div>
            <div style="display:flex;gap:6px;">
              <span style="font-size:10px;color:var(--text-secondary);background:rgba(255,255,255,0.06);padding:2px 8px;border-radius:4px;">${dur}s</span>
              <span style="font-size:10px;color:var(--purple-lavender);background:rgba(157,78,221,0.1);padding:2px 8px;border-radius:4px;">${esc(trans)}</span>
            </div>
          </div>
          ${charBadges}
          <div class="clip-summary">${esc(sceneDesc)}</div>
          <div class="clip-tracks">
            <div class="track-content">${buildATrack(clip.a_track)}</div>
            <div class="track-content">${buildBTrack(clip.b_track)}</div>
            <div class="track-content">${buildCTrack(clip.c_track)}</div>
          </div>
        </div>
      </div>
    `;
  });

  // 批量生成剩余按钮已移至action-bar（btn-batch-remaining），此处不再生成

  timeline.innerHTML = html;
  if (_sortMode) {
    timeline.classList.add('sort-mode');
    // Make cards draggable
    timeline.querySelectorAll('.clip-card[data-clip-idx]').forEach(card => {
      card.setAttribute('draggable', 'true');
    });
    _initSortDrag();
  } else {
    timeline.classList.remove('sort-mode');
    timeline.querySelectorAll('.clip-card').forEach(card => {
      card.removeAttribute('draggable');
    });
    // Remove insert line if exists
    const line = timeline.querySelector('.sort-insert-line');
    if (line) line.remove();
  }
  checkStoryboardComplete();
}


// ═══ Storyboard Sort Mode ═══
let _sortMode = false;
let _sortOrder = []; // original indices in new order
let _dragSrcIdx = -1;


function aiReview() {
  const prompt = "# Role\n\u4f60\u662f\u4e00\u4f4d\u8d44\u6df1\u7684\u5f71\u89c6\u5267\u672c\u5206\u955c\u6307\u5bfc\u4e0e\u526a\u8f91\u5927\u5e08\uff0c\u7cbe\u901a\u89c6\u542c\u8bed\u8a00\u3001\u620f\u5267\u5f20\u529b\u4ee5\u53ca\u53d9\u4e8b\u65f6\u5e8f\u903b\u8f91\u3002\n# Task\n\u8bf7\u4ed4\u7ec6\u6838\u5bf9\u7528\u6237\u4e0a\u4f20\u7684\u6240\u6709\u5206\u955c\u5267\u672c\u622a\u56fe\u3002\u8bf7\u9488\u5bf9\u6bcf\u4e00\u5f20\u56fe\u7247\uff0c\u6839\u636e\u5176\u4e2d\u5b9e\u9645\u5305\u542b\u7684\u5206\u955c\u6570\u91cf\uff0c\u8bc4\u4f30\u5176\u5185\u90e8\u7684\u5206\u955c\u987a\u5e8f\u662f\u5426\u5b58\u5728\u65f6\u95f4\u7ebf\u5012\u7f6e\u3001\u52a8\u4f5c\u7ebf\u5272\u88c2\u3001\u60c5\u7eea\u524d\u540e\u77db\u76fe\u7b49\u903b\u8f91\u95ee\u9898\u3002\n# Output Constraints (\u94c1\u5f8b)\n1. \u7edd\u5bf9\u4e25\u7981\u8f93\u51fa\u4efb\u4f55\u5f00\u573a\u767d\u3001\u5ba2\u5957\u8bdd\u3001\u89e3\u91ca\u6216\u603b\u7ed3\u9648\u8bcd\uff08\u5982\"\u597d\u7684\"\u3001\"\u6536\u5230\"\u3001\"\u5e0c\u671b\u5bf9\u4f60\u6709\u5e2e\u52a9\"\u7b49\uff09\uff0c\u5fc5\u987b\u76f4\u63a5\u8f93\u51fa\u7b2c\u4e00\u884c\u7ed3\u679c\u3002\n2. \u4e25\u683c\u6309\u7167\u7528\u6237\u4e0a\u4f20\u56fe\u7247\u7684\u5148\u540e\u987a\u5e8f\u8f93\u51fa\uff0c\u4e00\u5f20\u56fe\u7247\u4ec5\u5360\u4e00\u884c\uff08\u4f9d\u6b21\u4e3a\uff1a\u56fe\u4e00\u3001\u56fe\u4e8c\u3001\u56fe\u4e09\u2026\u2026\u4f9d\u6b64\u7c7b\u63a8\uff0c\u6709\u51e0\u5f20\u56fe\u5c31\u8f93\u51fa\u51e0\u884c\uff09\u3002\n3. \u5982\u679c\u8be5\u56fe\u6709\u987a\u5e8f\u95ee\u9898\uff0c\u5fc5\u987b\u63d0\u4f9b\u91cd\u65b0\u7f16\u6392\u540e\u7684[\u6b63\u786e\u987a\u5e8f]\uff08\u9700\u5305\u542b\u8be5\u56fe\u5185\u6240\u6709\u5206\u955c\u5e8f\u53f7\uff09\u4ee5\u53ca100\u5b57\u4ee5\u5185\u7684\u6838\u5fc3\u903b\u8f91\u89e3\u91ca\u3002\n4. \u5982\u679c\u5b8c\u5168\u65e0\u987a\u5e8f\u95ee\u9898\uff0c\u76f4\u63a5\u8f93\u51fa\"\u65e0\u987a\u5e8f\u95ee\u9898\"\uff0c\u540e\u9762\u4e25\u7981\u9644\u52a0\u4efb\u4f55\u89e3\u91ca\u3002\n# Output Format (\u4e25\u683c\u5bf9\u9f50\u6b64\u683c\u5f0f)\n\u56fe\u4e00\uff1a[\u6b63\u786e\u987a\u5e8f\uff1aX-X-X...\uff08\u5305\u542b\u6240\u6709\u5206\u955c\u5e8f\u53f7\uff09 + 100\u5b57\u4ee5\u5185\u6838\u5fc3\u539f\u56e0\u89e3\u91ca / \u65e0\u987a\u5e8f\u95ee\u9898]\n\u56fe\u4e8c\uff1a[\u6b63\u786e\u987a\u5e8f\uff1aX-X-X...\uff08\u5305\u542b\u6240\u6709\u5206\u955c\u5e8f\u53f7\uff09 + 100\u5b57\u4ee5\u5185\u6838\u5fc3\u539f\u56e0\u89e3\u91ca / \u65e0\u987a\u5e8f\u95ee\u9898]\n\u2026\u2026\n\u56feN\uff1a[\u6b63\u786e\u987a\u5e8f\uff1aX-X-X...\uff08\u5305\u542b\u6240\u6709\u5206\u955c\u5e8f\u53f7\uff09 + 100\u5b57\u4ee5\u5185\u6838\u5fc3\u539f\u56e0\u89e3\u91ca / \u65e0\u987a\u5e8f\u95ee\u9898]\n# Example (\u793a\u4f8b\uff0c\u4ec5\u4f9b\u53c2\u8003\u683c\u5f0f)\n\u56fe\u4e00\uff1a\u6b63\u786e\u987a\u5e8f\uff1a1-2-3-4-6-5 \u955c5\u5199\u65e5\u5149\u7167\u5165\u4ee3\u8868\u5929\u4eae\uff0c\u955c6\u5374\u5199\u624b\u673a\u51b7\u5149\u7167\u4eae\u8138\u5e9e\u3002\u903b\u8f91\u4e0a\u5e94\u5148\u5728\u9ed1\u591c\u91cc\u770b\u7740\u624b\u673a\u51b7\u5149\u505a\u51fa\u51b3\u7edd\u51b3\u5b9a\uff0c\u968f\u540e\u71ac\u5230\u6e05\u6668\u65e5\u5149\u7167\u8fdb\u5ba2\u5385\uff0c\u65456\u5e94\u57285\u524d\u3002\n\u56fe\u4e8c\uff1a\u65e0\u987a\u5e8f\u95ee\u9898\n\u56fe\u4e09\uff1a\u6b63\u786e\u987a\u5e8f\uff1a1-4-2-3 \u955c4\u7684\u7ec6\u8282\u53d1\u73b0\u5c5e\u4e8e\u5f00\u64ad\u524d\u7684\u6697\u7ebf\u4f0f\u7b14\uff0c\u82e5\u5f3a\u884c\u63d2\u5728\u6b63\u5728\u76f4\u64ad\u7684\u955c2\u4e0e\u955c3\u4e2d\u95f4\uff0c\u4f1a\u5bfc\u81f4\u4e25\u91cd\u7684\u52a8\u4f5c\u7ebf\u65ad\u88c2\u4e0e\u65f6\u7a7a\u7a7f\u5e2e\uff0c\u6545\u9700\u524d\u7f6e\u3002";
  navigator.clipboard.writeText(prompt).then(() => {
    showNotification('已复制AI审查prompt，请粘贴到AI对话框');
  }).catch(() => {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = prompt;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showNotification('已复制AI审查prompt，请粘贴到AI对话框');
  });
}

function enterSortMode() {
  const sb = state.currentProject?.storyboards?.[String(state.currentChapter)];
  const clips = Array.isArray(sb?.clips) ? sb.clips : [];
  if (clips.length < 2) {
    showNotification('至少需要2个clip才能排序', 'error');
    return;
  }
  _sortMode = true;
  _sortOrder = clips.map((_, i) => i);
  _dragSrcIdx = -1;
  renderStoryboard();
}

function cancelSortMode() {
  _sortMode = false;
  _sortOrder = [];
  _dragSrcIdx = -1;
  renderStoryboard();
}

async function saveSortMode() {
  if (!_sortOrder.length) { cancelSortMode(); return; }
  // Check if order actually changed
  const isSame = _sortOrder.every((v, i) => v === i);
  if (isSame) {
    showNotification('排序未改变');
    cancelSortMode();
    return;
  }
  try {
    toggleSynapseLoading(true, 'SYNAPSE', '正在保存排序...');
    const result = await api(
      `/api/projects/${state.currentProject.id}/storyboard/${state.currentChapter}/reorder`,
      'POST', { order: _sortOrder }, 30000
    );
    if (result.success) {
      // Update local state
      const sb = state.currentProject.storyboards[String(state.currentChapter)];
      const clips = Array.isArray(sb?.clips) ? sb.clips : [];
      const reordered = _sortOrder.map(i => clips[i]);
      sb.clips = reordered;
      // Reset clip_index on each clip
      reordered.forEach((c, i) => { c.clip_index = i; });
      // Also reorder frames if they exist
      const framesData = state.currentProject.frames?.[String(state.currentChapter)];
      if (framesData?.frames) {
        const newFrames = [];
        _sortOrder.forEach((origIdx, newPos) => {
          const f = framesData.frames.find(fr => fr.clip_index === origIdx);
          if (f) {
            f.clip_index = newPos;
            newFrames.push(f);
          }
        });
        framesData.frames = newFrames;
      }
      showNotification('排序已保存');
    } else {
      showNotification('保存失败: ' + (result.message || '未知错误'), 'error');
    }
  } catch (e) {
    showNotification('保存排序失败: ' + e.message, 'error');
  }
  toggleSynapseLoading(false);
  _sortMode = false;
  _sortOrder = [];
  _dragSrcIdx = -1;
  renderStoryboard();
}

let _sortDragBound = false;
function _initSortDrag() {
  const timeline = document.getElementById('storyboard-timeline');
  if (!timeline) return;

  // Insert the floating drop line
  let line = timeline.querySelector('.sort-insert-line');
  if (!line) {
    line = document.createElement('div');
    line.className = 'sort-insert-line';
    timeline.style.position = 'relative';
    timeline.appendChild(line);
  }

  // Only bind listeners once
  if (_sortDragBound) return;
  _sortDragBound = true;

  const cards = () => Array.from(timeline.querySelectorAll('.clip-card[data-clip-idx]'));

  timeline.addEventListener('dragstart', (e) => {
    if (!_sortMode) return;
    const card = e.target.closest('.clip-card');
    if (!card) return;
    _dragSrcIdx = parseInt(card.dataset.clipIdx);
    card.classList.add('dragging');
    // Custom ghost
    const ghost = document.createElement('div');
    ghost.className = 'drag-ghost';
    ghost.id = '_drag_ghost';
    const hdr = card.querySelector('.clip-header');
    const numSpan = hdr?.querySelector('.clip-num');
    const descSpan = numSpan?.nextElementSibling;
    const sceneDesc = descSpan?.textContent || `Clip ${_dragSrcIdx + 1}`;
    const shortDesc = sceneDesc.length > 24 ? sceneDesc.slice(0, 24) + '...' : sceneDesc;
    ghost.innerHTML = `<div style="display:flex;align-items:center;gap:10px;">
      <span class="clip-num">${numSpan?.textContent || (_dragSrcIdx + 1)}</span>
      <span style="color:var(--text-primary);font-size:13px;font-weight:500;white-space:nowrap;">${shortDesc}</span>
    </div>`;
    document.body.appendChild(ghost);
    e.dataTransfer.setDragImage(ghost, ghost.offsetWidth / 2, ghost.offsetHeight / 2);
    e.dataTransfer.effectAllowed = 'move';
    // Position offscreen initially
    requestAnimationFrame(() => { ghost.style.left = '-9999px'; ghost.style.top = '-9999px'; });
  });

  timeline.addEventListener('dragover', (e) => {
    if (!_sortMode) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    // Move custom ghost
    const ghost = document.getElementById('_drag_ghost');
    if (ghost) {
      ghost.style.left = (e.clientX + 12) + 'px';
      ghost.style.top = (e.clientY - 20) + 'px';
    }
    // Find nearest card for insertion line
    const allCards = cards();
    let insertBefore = -1;
    for (let i = 0; i < allCards.length; i++) {
      const rect = allCards[i].getBoundingClientRect();
      const midY = rect.top + rect.height / 2;
      if (e.clientY < midY) {
        insertBefore = i;
        break;
      }
    }
    if (insertBefore === -1) insertBefore = allCards.length;

    // Position the insert line
    const lineEl = timeline.querySelector('.sort-insert-line');
    if (lineEl && allCards.length > 0) {
      lineEl.classList.add('visible');
      let lineTop;
      if (insertBefore >= allCards.length) {
        const lastRect = allCards[allCards.length - 1].getBoundingClientRect();
        const timelineRect = timeline.getBoundingClientRect();
        lineTop = lastRect.bottom - timelineRect.top + 4;
      } else {
        const targetRect = allCards[insertBefore].getBoundingClientRect();
        const timelineRect = timeline.getBoundingClientRect();
        lineTop = targetRect.top - timelineRect.top - 4;
      }
      lineEl.style.top = lineTop + 'px';
    }
  });

  timeline.addEventListener('dragleave', (e) => {
    if (!_sortMode) return;
    if (!timeline.contains(e.relatedTarget)) {
      const lineEl = timeline.querySelector('.sort-insert-line');
      if (lineEl) lineEl.classList.remove('visible');
    }
  });

  timeline.addEventListener('drop', (e) => {
    if (!_sortMode) return;
    e.preventDefault();
    const lineEl = timeline.querySelector('.sort-insert-line');
    if (lineEl) lineEl.classList.remove('visible');

    const allCards = cards();
    let insertBefore = -1;
    for (let i = 0; i < allCards.length; i++) {
      const rect = allCards[i].getBoundingClientRect();
      const midY = rect.top + rect.height / 2;
      if (e.clientY < midY) {
        insertBefore = i;
        break;
      }
    }
    if (insertBefore === -1) insertBefore = allCards.length;

    // Find the source position in current _sortOrder
    const srcPos = _sortOrder.indexOf(_dragSrcIdx);
    if (srcPos === -1) return;

    // Remove from old position, insert at new position
    _sortOrder.splice(srcPos, 1);
    // Adjust insertBefore if needed
    let newInsert = insertBefore;
    if (srcPos < insertBefore) newInsert = Math.max(0, insertBefore - 1);
    _sortOrder.splice(newInsert, 0, _dragSrcIdx);

    // Cleanup ghost immediately (dragend may not fire after re-render)
    const ghost = document.getElementById('_drag_ghost');
    if (ghost) ghost.remove();

    // Re-render in sort mode with new order
    renderStoryboard();
  });

  timeline.addEventListener('dragend', (e) => {
    if (!_sortMode) return;
    // Cleanup
    const ghost = document.getElementById('_drag_ghost');
    if (ghost) ghost.remove();
    cards().forEach(c => c.classList.remove('dragging'));
    const lineEl = timeline.querySelector('.sort-insert-line');
    if (lineEl) lineEl.classList.remove('visible');
    _dragSrcIdx = -1;
  });
}

// 
//  v2  — ///////
// 

//  Canvas 
class ParticleCanvas {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.particles = [];
    this.mouse = { x: -9999, y: -9999 };
    this.resize();
    window.addEventListener('resize', () => this.resize());
    canvas.addEventListener('mousemove', e => {
      this.mouse.x = e.clientX;
      this.mouse.y = e.clientY;
    });
    canvas.addEventListener('mouseleave', () => {
      this.mouse.x = -9999;
      this.mouse.y = -9999;
    });
    this.createParticles();
    this.animate();
  }
  resize() {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  }
  createParticles() {
    const count = Math.floor((this.canvas.width * this.canvas.height) / 12000);
    for (let i = 0; i < count; i++) {
      this.particles.push({
        x: Math.random() * this.canvas.width,
        y: Math.random() * this.canvas.height,
        size: Math.random() * 2 + 0.5,
        speedX: (Math.random() - 0.5) * 0.3,
        speedY: (Math.random() - 0.5) * 0.3,
        opacity: Math.random() * 0.2 + 0.1,
        pulse: Math.random() * Math.PI * 2,
        pulseSpeed: Math.random() * 0.02 + 0.005,
        color: Math.random() > 0.6 ? '#C77DFF' : '#FFFFFF',
      });
    }
  }
  animate() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    for (const p of this.particles) {
      p.x += p.speedX + Math.sin(p.pulse) * 0.15;
      p.y += p.speedY + Math.cos(p.pulse) * 0.1;
      p.pulse += p.pulseSpeed;
      const currentOpacity = p.opacity * (0.7 + Math.sin(p.pulse) * 0.3);
      // Mouse repulsion
      const dx = p.x - this.mouse.x;
      const dy = p.y - this.mouse.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 100 && dist > 0) {
        const force = (100 - dist) / 100 * 2;
        p.x += (dx / dist) * force;
        p.y += (dy / dist) * force;
      }
      if (p.x < 0) p.x = this.canvas.width;
      if (p.x > this.canvas.width) p.x = 0;
      if (p.y < 0) p.y = this.canvas.height;
      if (p.y > this.canvas.height) p.y = 0;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fillStyle = p.color;
      ctx.globalAlpha = currentOpacity;
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    requestAnimationFrame(() => this.animate());
  }
}

//  3DThree.js 
class GlobeScene {
  constructor(container) {
    if (typeof THREE === 'undefined') return;
    this.container = container;
    this.scene = new THREE.Scene();
    this.mouseTarget = { x: 0, y: 0 };
    this.mouseCurrent = { x: 0, y: 0 };
    const w = container.clientWidth || window.innerWidth;
    const h = container.clientHeight || window.innerHeight;
    this.camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 200);
    this.camera.position.set(0, 0.6, 4.5);
    this.camera.lookAt(0, 0, 0);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(w, h);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 0);
    container.appendChild(this.renderer.domElement);

    this.globeGroup = new THREE.Group();
    this.scene.add(this.globeGroup);

    // Lights
    this.scene.add(new THREE.AmbientLight(0x9D4EDD, 0.3));
    const pl1 = new THREE.PointLight(0x9D4EDD, 2, 15); pl1.position.set(3,3,3); this.scene.add(pl1);
    const pl2 = new THREE.PointLight(0x00D9FF, 1.5, 15); pl2.position.set(-3,-2,3); this.scene.add(pl2);

    this.buildOuterWireframe();
    this.buildCodeSphere();
    this.buildGlowShell();
    this.buildLongitudeLines();
    this.buildHUDPanels();
    this.buildRisingParticles();
    this.buildRing();

    this.animate();
    window.addEventListener('resize', () => this.onResize());
    window.addEventListener('mousemove', e => {
      this.mouseTarget.x = (e.clientX / window.innerWidth - 0.5) * 2;
      this.mouseTarget.y = (e.clientY / window.innerHeight - 0.5) * 2;
    });
  }

  buildOuterWireframe() {
    const geo = new THREE.IcosahedronGeometry(1.62, 2);
    const mat = new THREE.MeshBasicMaterial({ color: 0x9D4EDD, wireframe: true, transparent: true, opacity: 0.12 });
    this.icoMesh = new THREE.Mesh(geo, mat);
    this.globeGroup.add(this.icoMesh);
  }

  buildCodeSphere() {
    // Canvas code matrix
    this.codeCanvas = document.createElement('canvas');
    this.codeCanvas.width = 2048;
    this.codeCanvas.height = 1024;
    this.codeCtx = this.codeCanvas.getContext('2d');

    const engChars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
    const digitChars = '0123456789';
    const symbolChars = '{}[]<>|/\\+=*&#@!~^';
    this._randChar = function() {
      const r = Math.random();
      if (r < 0.7) return engChars[Math.floor(Math.random() * engChars.length)];
      if (r < 0.9) return digitChars[Math.floor(Math.random() * digitChars.length)];
      return symbolChars[Math.floor(Math.random() * symbolChars.length)];
    };

    const COLS = 100;
    this._codeCols = [];
    for (let i = 0; i < COLS; i++) {
      const chars = [];
      const len = 80 + Math.floor(Math.random() * 20);
      for (let j = 0; j < len; j++) chars.push(this._randChar());
      this._codeCols.push({ chars, speed: 1.5 + Math.random() * 2.5, offset: Math.random() * 1000 });
    }

    this.codeTexture = new THREE.CanvasTexture(this.codeCanvas);
    this.codeTexture.minFilter = THREE.LinearFilter;
    this.codeTexture.magFilter = THREE.LinearFilter;
    this.codeTexture.wrapS = THREE.RepeatWrapping;
    this.codeTexture.wrapT = THREE.ClampToEdgeWrapping;

    const geo = new THREE.SphereGeometry(1.5, 64, 32);
    const mat = new THREE.MeshBasicMaterial({
      map: this.codeTexture,
      transparent: true,
      opacity: 0.9,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      depthWrite: false
    });
    this.codeSphere = new THREE.Mesh(geo, mat);
    this.globeGroup.add(this.codeSphere);
  }

  _drawCodeTexture(time) {
    const ctx = this.codeCtx;
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, 2048, 1024);

    const COLS = this._codeCols.length;
    const colWidth = 2048 / COLS;
    for (let i = 0; i < COLS; i++) {
      const col = this._codeCols[i];
      const x = i * colWidth + 2;
      const totalChars = col.chars.length;
      const scrollPos = ((time * col.speed * 80 + col.offset) % (totalChars * 14));

      for (let j = 0; j < totalChars; j++) {
        const y = (j * 14 - scrollPos + totalChars * 14) % (totalChars * 14);
        if (y < 0 || y > 1024) continue;

        const headPos = (totalChars * 14 - scrollPos) % (totalChars * 14);
        const distFromHead = ((headPos - y + totalChars * 14) % (totalChars * 14));

        if (Math.random() < 0.002) col.chars[j] = this._randChar();

        const ch = col.chars[j];

        if (distFromHead < 18) {
          ctx.fillStyle = 'rgba(255,255,255,0.95)';
          ctx.font = 'bold 14px Courier New';
          ctx.shadowColor = '#00D9FF';
          ctx.shadowBlur = 8;
        } else if (distFromHead < 54) {
          const t = (distFromHead - 18) / 36;
          const g = Math.floor(255 - t * 100);
          const b = Math.floor(200 - t * 100);
          ctx.fillStyle = 'rgba(0,' + g + ',' + b + ',0.85)';
          ctx.font = '14px Courier New';
          ctx.shadowColor = '#00D9FF';
          ctx.shadowBlur = 4;
        } else {
          const alpha = Math.max(0, 0.6 - (distFromHead - 54) / 400);
          ctx.fillStyle = 'rgba(157,78,221,' + alpha + ')';
          ctx.font = '14px Courier New';
          ctx.shadowColor = 'transparent';
          ctx.shadowBlur = 0;
        }
        ctx.fillText(ch, x, y);
      }
    }
    ctx.shadowBlur = 0;
  }

  buildGlowShell() {
    const geo = new THREE.SphereGeometry(1.55, 32, 32);
    const mat = new THREE.MeshBasicMaterial({ color: 0x9D4EDD, transparent: true, opacity: 0.04, side: THREE.BackSide });
    this.globeGroup.add(new THREE.Mesh(geo, mat));
  }

  buildLongitudeLines() {
    const lineColors = [0x9D4EDD, 0x00D9FF];
    this._longLineData = [];
    for (let i = 0; i < 8; i++) {
      const angle = (i / 8) * Math.PI * 2;
      const points = [];
      const segments = 120;
      for (let j = 0; j <= segments; j++) {
        const phi = (j / segments) * Math.PI;
        const r = 1.52;
        const x = r * Math.sin(phi) * Math.cos(angle);
        const y = r * Math.cos(phi);
        const z = r * Math.sin(phi) * Math.sin(angle);
        points.push(new THREE.Vector3(x, y, z));
      }
      const geo = new THREE.BufferGeometry().setFromPoints(points);
      const mat = new THREE.LineBasicMaterial({ color: lineColors[i % 2], transparent: true, opacity: 0.15 });
      this.globeGroup.add(new THREE.Line(geo, mat));

      const dotGeo = new THREE.SphereGeometry(0.03, 8, 8);
      const dotMat = new THREE.MeshBasicMaterial({ color: i % 2 === 0 ? 0x00D9FF : 0xffffff, transparent: true, opacity: 0.95 });
      const dot = new THREE.Mesh(dotGeo, dotMat);
      this.globeGroup.add(dot);
      const dotGlowGeo = new THREE.SphereGeometry(0.06, 8, 8);
      const dotGlowMat = new THREE.MeshBasicMaterial({ color: 0x00D9FF, transparent: true, opacity: 0.35 });
      dot.add(new THREE.Mesh(dotGlowGeo, dotGlowMat));
      this._longLineData.push({ points, dot, offset: i * 0.125 });
    }
  }

  buildHUDPanels() {
    this._hudPanels = [];
    for (let i = 0; i < 6; i++) {
      const canvas = document.createElement('canvas');
      canvas.width = 256;
      canvas.height = 160;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = 'rgba(10, 5, 30, 0.85)';
      ctx.fillRect(0, 0, 256, 160);
      ctx.strokeStyle = 'rgba(0, 217, 255, 0.6)';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(4, 4, 248, 152);
      ctx.fillStyle = 'rgba(157, 78, 221, 0.3)';
      ctx.fillRect(4, 4, 248, 22);
      ctx.fillStyle = '#00D9FF';
      ctx.font = 'bold 11px monospace';
      ctx.fillText(['NODE_' + String(i).padStart(3,'0'), 'SYS_METRICS', 'DATA_STREAM', 'PKT_ANALYZER', 'NET_TOPOLOGY', 'AUTH_LAYER'][i], 12, 19);
      ctx.fillStyle = 'rgba(157, 78, 221, 0.7)';
      ctx.font = 'bold 11px monospace';
      const snippets = [
        ['0x' + Math.random().toString(16).slice(2,10), 'FLUX: ' + (Math.random()*999).toFixed(1), 'SYNC: OK', 'HASH: ' + Math.random().toString(36).slice(2,10)],
        ['for(i=0;i<n;i++)', '  arr[i]>>2;', '  yield*pipe;', '  return buf;'],
        ['PKT_RX: ' + Math.floor(Math.random()*9999), 'PKT_TX: ' + Math.floor(Math.random()*9999), 'ERR: ' + (Math.random()*0.1).toFixed(4), 'QLEN: ' + Math.floor(Math.random()*256)],
        ['async def recv():', '  data=await io', '  parse(data)', '  emit("data")'],
        ['TOPO: ' + Math.floor(Math.random()*64) + ' nodes', 'EDGE: ' + Math.floor(Math.random()*512), 'LAT: ' + (Math.random()*50).toFixed(1) + 'ms', 'BW: ' + (Math.random()*10).toFixed(2) + 'Gbps'],
        ['AUTH: SHA-256', 'KEY: 0x' + Math.random().toString(16).slice(2,18), 'TOKEN: VALID', 'EXP: ' + Math.floor(Math.random()*3600) + 's']
      ][i];
      snippets.forEach((s, j) => { ctx.fillText(s, 14, 40 + j * 16); });
      ctx.fillStyle = 'rgba(0, 217, 255, 0.08)';
      ctx.fillRect(4, 30, 248, 2);

      const tex = new THREE.CanvasTexture(canvas);
      tex.minFilter = THREE.LinearFilter;
      const panelGeo = new THREE.PlaneGeometry(0.3, 0.2);
      const panelMat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 0.85, side: THREE.DoubleSide, depthWrite: false });
      const panel = new THREE.Mesh(panelGeo, panelMat);
      const radius = 2.2 + Math.random() * 0.5;
      const theta = (i / 6) * Math.PI * 2 + Math.random() * 0.3;
      const phi = Math.random() * Math.PI * 0.6 + Math.PI * 0.2;
      panel.userData = { radius, theta, phi, speed: 0.08 + Math.random() * 0.04 };
      this.globeGroup.add(panel);
      this._hudPanels.push(panel);
    }
  }

  buildRisingParticles() {
    const count = 200;
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    this._pSpeeds = [];
    const purpleC = new THREE.Color(0x9D4EDD);
    const cyanC = new THREE.Color(0x00D9FF);
    for (let i = 0; i < count; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.random() * Math.PI;
      const r = 1.5 + Math.random() * 0.05;
      positions[i*3] = r * Math.sin(phi) * Math.cos(theta);
      positions[i*3+1] = r * Math.cos(phi);
      positions[i*3+2] = r * Math.sin(phi) * Math.sin(theta);
      const c = Math.random() > 0.5 ? purpleC : cyanC;
      colors[i*3] = c.r; colors[i*3+1] = c.g; colors[i*3+2] = c.b;
      this._pSpeeds.push(0.003 + Math.random() * 0.008);
    }
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    this._pGeo = geo;
    this._pMat = new THREE.PointsMaterial({ size: 0.035, vertexColors: true, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true });
    this.globeGroup.add(new THREE.Points(geo, this._pMat));
  }

  buildRing() {
    const geo = new THREE.RingGeometry(1.7, 1.75, 128);
    const mat = new THREE.MeshBasicMaterial({ color: 0x00D9FF, transparent: true, opacity: 0.08, side: THREE.DoubleSide });
    this._ring = new THREE.Mesh(geo, mat);
    this._ring.rotation.x = Math.PI / 2;
    this.globeGroup.add(this._ring);
  }

  animate() {
    requestAnimationFrame(() => this.animate());
    const t = Date.now() * 0.001;

    // Mouse parallax
    this.mouseCurrent.x += (this.mouseTarget.x - this.mouseCurrent.x) * 0.03;
    this.mouseCurrent.y += (this.mouseTarget.y - this.mouseCurrent.y) * 0.03;

    // Globe rotation
    this.globeGroup.rotation.y += 0.003;
    this.globeGroup.rotation.x = Math.sin(t * 0.15) * 0.05 + this.mouseCurrent.y * 0.05;

    // Wireframe counter-rotation
    this.icoMesh.rotation.y = -t * 0.05;
    this.icoMesh.rotation.x = t * 0.02;

    // Traveling dots on longitude lines
    this._longLineData.forEach(ld => {
      const progress = ((t * 0.3 + ld.offset) % 1);
      const idx = Math.floor(progress * (ld.points.length - 1));
      const nextIdx = Math.min(idx + 1, ld.points.length - 1);
      const frac = progress * (ld.points.length - 1) - idx;
      ld.dot.position.lerpVectors(ld.points[idx], ld.points[nextIdx], frac);
    });

    // HUD panels orbiting
    this._hudPanels.forEach(p => {
      p.userData.theta += p.userData.speed * 0.01;
      const d = p.userData;
      p.position.x = d.radius * Math.sin(d.phi) * Math.cos(d.theta);
      p.position.y = d.radius * Math.cos(d.phi);
      p.position.z = d.radius * Math.sin(d.phi) * Math.sin(d.theta);
      p.lookAt(0, 0, 0);
      p.rotateY(Math.PI);
    });

    // Update code matrix texture (every 2 frames for perf)
    if (!this._frameCount) this._frameCount = 0;
    this._frameCount++;
    if (this._frameCount % 2 === 0) {
      this._drawCodeTexture(t);
      this.codeTexture.needsUpdate = true;
    }

    // Rising particles
    const posArr = this._pGeo.getAttribute('position').array;
    for (let i = 0; i < this._pSpeeds.length; i++) {
      const x = posArr[i*3], y = posArr[i*3+1], z = posArr[i*3+2];
      const len = Math.sqrt(x*x + y*y + z*z);
      const nx = x/len, ny = y/len, nz = z/len;
      posArr[i*3] += nx * this._pSpeeds[i];
      posArr[i*3+1] += ny * this._pSpeeds[i];
      posArr[i*3+2] += nz * this._pSpeeds[i];
      const newLen = Math.sqrt(posArr[i*3]**2 + posArr[i*3+1]**2 + posArr[i*3+2]**2);
      if (newLen > 3.0) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.random() * Math.PI;
        const r = 1.5 + Math.random() * 0.05;
        posArr[i*3] = r * Math.sin(phi) * Math.cos(theta);
        posArr[i*3+1] = r * Math.cos(phi);
        posArr[i*3+2] = r * Math.sin(phi) * Math.sin(theta);
      }
    }
    this._pGeo.getAttribute('position').needsUpdate = true;
    this._pMat.opacity = 0.6 + Math.sin(t * 1.5) * 0.2;

    // Ring pulse
    this._ring.scale.setScalar(1 + Math.sin(t * 0.8) * 0.03);
    this._ring.material.opacity = 0.06 + Math.sin(t * 1.2) * 0.03;

    this.renderer.render(this.scene, this.camera);
  }

  onResize() {
    if (!this.container) return;
    const w = this.container.clientWidth, h = this.container.clientHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
  }
}

//  CSSCSS 

//   
function initShootingStars() {
  const canvas = document.getElementById('particle-canvas');
  if (!canvas) return;
  function shoot() {
    const star = document.createElement('div');
    star.style.cssText = `
      position:fixed;z-index:1;pointer-events:none;
      width:120px;height:1px;
      background:linear-gradient(90deg,transparent,#C77DFF,#fff);
      border-radius:1px;
      opacity:0.8;
      left:${Math.random() * 60 + 20}%;
      top:${Math.random() * 30}%;
      transform:rotate(25deg);
      animation:shootingStar 0.6s linear forwards;
    `;
    document.body.appendChild(star);
    setTimeout(() => star.remove(), 700);
    setTimeout(shoot, Math.random() * 15000 + 8000);
  }
  setTimeout(shoot, 3000);
}

//  3D++ 
function initCardEffects() {
  // Card hover effects disabled for performance
}
//   
function initButtonRipple() {
  document.querySelectorAll('.btn').forEach(btn => {
    if (btn._rippleInit) return;
    btn._rippleInit = true;
    btn.addEventListener('click', e => {
      const ripple = document.createElement('span');
      const rect = btn.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height) * 2;
      ripple.style.cssText = `
        position:absolute;border-radius:50%;
        background:rgba(199,125,255,0.4);
        width:${size}px;height:${size}px;
        left:${e.clientX - rect.left - size/2}px;
        top:${e.clientY - rect.top - size/2}px;
        transform:scale(0);opacity:1;
        transition:transform 0.5s ease, opacity 0.5s ease;
        pointer-events:none;z-index:1;
      `;
      btn.appendChild(ripple);
      requestAnimationFrame(() => {
        ripple.style.transform = 'scale(1)';
        ripple.style.opacity = '0';
      });
      setTimeout(() => ripple.remove(), 600);
    });
  });
}

//   +  
function initScrollEffects() {
  const mainContent = document.querySelector('.main-content');
  const progress = document.getElementById('scroll-progress');
  if (!mainContent) return;

  mainContent.addEventListener('scroll', () => {
    const scrollTop = mainContent.scrollTop;
    const scrollHeight = mainContent.scrollHeight - mainContent.clientHeight;
    const ratio = scrollHeight > 0 ? scrollTop / scrollHeight : 0;

    if (progress) {
      progress.style.width = (ratio * 100) + '%';
      // Pulse indicator when scrolled
      if (ratio > 0.01) {
        progress.classList.add('has-progress');
      } else {
        progress.classList.remove('has-progress');
      }
    }

    // Globe is now fixed background — no parallax needed

    // 
    const ambientGlow = document.getElementById('ambient-glow');
    if (ambientGlow) {
      ambientGlow.style.transform = `translate(-50%,-50%) translateY(${scrollTop * 0.05}px)`;
    }

    // 
    document.querySelectorAll('.feature-card, .glass-card').forEach(card => {
      const rect = card.getBoundingClientRect();
      if (rect.top < window.innerHeight * 0.85) {
        card.style.opacity = '1';
        card.style.transform = card.style.transform || 'translateY(0)';
      }
    });
  });
}

//   
function initSidebarBeam() {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar) return;
  if (!sidebar.querySelector('.sidebar-beam')) {
    const beam = document.createElement('div');
    beam.className = 'sidebar-beam';
    beam.style.cssText = `
      position:absolute;left:0;top:0;width:2px;height:60px;
      background:linear-gradient(180deg,transparent,rgba(199,125,255,0.4),transparent);
      border-radius:1px;z-index:10;
      animation:sidebarBeamMove 6s linear infinite;
    `;
    sidebar.appendChild(beam);
  }
}

//   
function initEntranceAnimations() {
  const hero = document.querySelector('.hero');
  if (hero) {
    hero.style.opacity = '0';
    hero.style.transform = 'translateY(30px)';
    hero.style.transition = 'opacity 0.8s ease, transform 0.8s ease';
    setTimeout(() => {
      hero.style.opacity = '1';
      hero.style.transform = 'translateY(0)';
    }, 200);
  }

  // Hero title: split text into chars for stagger animation
  const heroTitle = document.querySelector('.hero-title');
  if (heroTitle) {
    const originalHTML = heroTitle.innerHTML;
    // Split visible text nodes into char spans, preserve existing tags
    const walker = document.createTreeWalker(heroTitle, NodeFilter.SHOW_TEXT, null, false);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    textNodes.forEach(node => {
      const text = node.textContent;
      if (!text.trim()) return;
      // Skip text inside .gradient-text to preserve gradient styling
      if (node.parentElement && node.parentElement.closest('.gradient-text')) return;
      const frag = document.createDocumentFragment();
      for (const ch of text) {
        if (ch === ' ' || ch === '\n') {
          frag.appendChild(document.createTextNode(ch));
        } else {
          const span = document.createElement('span');
          span.className = 'char-span';
          span.textContent = ch;
          frag.appendChild(span);
        }
      }
      node.parentNode.replaceChild(frag, node);
    });
    // Stagger animate chars
    const chars = heroTitle.querySelectorAll('.char-span');
    chars.forEach((ch, i) => {
      setTimeout(() => ch.classList.add('char-in'), 400 + i * 40);
    });
  }

  document.querySelectorAll('.feature-card').forEach((card, i) => {
    // Cards handled by IntersectionObserver now, skip direct animation
  });

  document.querySelectorAll('.menu-item').forEach((item, i) => {
    item.style.opacity = '0';
    item.style.transform = 'translateX(-10px)';
    item.style.transition = `opacity 0.4s ease ${100 + i*50}ms, transform 0.4s ease ${100 + i*50}ms`;
    setTimeout(() => {
      item.style.opacity = '1';
      item.style.transform = 'translateX(0)';
    }, 50);
  });
}

//  v2 
// === License Activation Logic ===
function checkLicense() {
  return new Promise((resolve) => {
    if (!window.pywebview || !window.pywebview.api || typeof pywebview.api.verify_license !== 'function') {
      // No pywebview bridge, skip license check
      resolve(true);
      return;
    }
    pywebview.api.verify_license().then(result => {
      if (result.valid) {
        // Update sidebar with remaining time
        updateSidebarLicense(result);
        resolve(true);
      } else {
        resolve(false);
      }
    }).catch(() => {
      resolve(false);
    });
  });
}

function showLicenseOverlay() {
  return new Promise((resolve) => {
    const overlay = document.getElementById('license-overlay');
    if (!overlay) { resolve(); return; }
    overlay.style.display = 'flex';

    const keyInput = document.getElementById('license-key-input');
    const btn = document.getElementById('license-activate-btn');
    const statusEl = document.getElementById('license-status');

    // Auto-format input
    keyInput.addEventListener('input', function() {
      let v = this.value.replace(/[^A-Za-z0-9]/g, '').toUpperCase();
      if (v.length > 19) v = v.substr(0, 19);
      let f = '';
      for (let i = 0; i < v.length; i++) {
        if (i === 3 || i === 7 || i === 11 || i === 15) f += '-';
        f += v[i];
      }
      this.value = f;
    });

    // Enter key
    keyInput.addEventListener('keypress', function(e) {
      if (e.key === 'Enter') doActivateLicense();
    });

    // Store resolve globally for doActivateLicense to call
    window._licenseResolve = resolve;

    setTimeout(() => keyInput.focus(), 300);
  });
}

function doActivateLicense() {
  const keyInput = document.getElementById('license-key-input');
  const btn = document.getElementById('license-activate-btn');
  const statusEl = document.getElementById('license-status');
  const key = keyInput.value.trim().toUpperCase();

  // Validate format
  if (!key.match(/^SYN-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/)) {
    statusEl.textContent = '卡密格式错误，应为 SYN-XXXX-XXXX-XXXX-XXXX';
    statusEl.className = 'license-status error';
    keyInput.classList.add('license-shake');
    setTimeout(() => keyInput.classList.remove('license-shake'), 500);
    return;
  }

  btn.disabled = true;
  btn.textContent = '激活中...';
  statusEl.textContent = '正在连接服务器...';
  statusEl.className = 'license-status loading';

  pywebview.api.activate_license(key).then(result => {
    if (result.success) {
      statusEl.textContent = '激活成功！有效期至：' + (result.expires_at || '永久');
      statusEl.className = 'license-status success';
      document.getElementById('license-offline-notice').style.display = 'block';

      // Update sidebar
      checkLicense().then(() => {});

      setTimeout(() => {
        const overlay = document.getElementById('license-overlay');
        overlay.style.opacity = '0';
        overlay.style.transition = 'opacity 0.5s';
        setTimeout(() => {
          overlay.style.display = 'none';
          overlay.style.opacity = '';
          if (window._licenseResolve) {
            window._licenseResolve();
            window._licenseResolve = null;
          }
        }, 500);
      }, 1500);
    } else {
      statusEl.textContent = result.message || '激活失败';
      statusEl.className = 'license-status error';
      keyInput.classList.add('license-shake');
      setTimeout(() => keyInput.classList.remove('license-shake'), 500);
    }
  }).catch(() => {
    statusEl.textContent = '网络错误，请检查网络连接';
    statusEl.className = 'license-status error';
  }).finally(() => {
    btn.disabled = false;
    btn.textContent = '激活';
  });
}

function updateSidebarLicense(result) {
  const container = document.getElementById('sidebar-license-info');
  const badge = document.getElementById('license-badge');
  const text = document.getElementById('license-badge-text');
  if (!container || !badge || !text) return;

  container.style.display = 'block';

  if (result.remaining_days === null || result.remaining_days === undefined) {
    // Permanent or unknown
    badge.className = 'license-badge';
    text.textContent = '永久有效';
  } else if (result.remaining_days > 30) {
    badge.className = 'license-badge';
    text.textContent = '剩余 ' + result.remaining_days + ' 天';
  } else if (result.remaining_days > 7) {
    badge.className = 'license-badge warn';
    text.textContent = '剩余 ' + result.remaining_days + ' 天';
  } else if (result.remaining_days > 0) {
    badge.className = 'license-badge danger';
    text.textContent = '仅剩 ' + result.remaining_days + ' 天';
  } else {
    badge.className = 'license-badge expired';
    text.textContent = '已过期';
  }
}

// === Disclaimer Modal Logic ===
function showDisclaimer() {
  return new Promise((resolve) => {
    const modal = document.getElementById('disclaimer-modal');
    if (!modal) { resolve(); return; }
    try {
      if (localStorage.getItem('disclaimer_accepted') === 'true') {
        resolve(); return;
      }
    } catch(e) {}
    modal.style.display = 'flex';
    const card = modal.querySelector('.disclaimer-card');
    setTimeout(() => { if (card) card.classList.add('reveal'); }, 50);
    const body = document.getElementById('disclaimer-body');
    const hint = document.getElementById('disclaimer-hint');
    const checkbox = document.getElementById('disclaimer-checkbox');
    const btn = document.getElementById('disclaimer-agree-btn');
    let scrolledToBottom = false;
    let checked = false;
    function updateButton() {
      if (scrolledToBottom && checked) { btn.disabled = false; }
    }
    // Auto-check: if content doesn't need scroll, enable immediately
    setTimeout(() => {
      if (body.scrollHeight <= body.clientHeight + 30) {
        scrolledToBottom = true;
        if (hint) hint.classList.add('hidden');
        checkbox.disabled = false;
        updateButton();
      }
    }, 150);
    body.addEventListener('scroll', function() {
      const threshold = 30;
      if (body.scrollTop + body.clientHeight >= body.scrollHeight - threshold) {
        scrolledToBottom = true;
        if (hint) hint.classList.add('hidden');
        checkbox.disabled = false;
        updateButton();
      }
    });
    checkbox.addEventListener('change', function() {
      checked = checkbox.checked;
      updateButton();
    });
    btn.addEventListener('click', function() {
      try { localStorage.setItem('disclaimer_accepted', 'true'); } catch(e) {}
      card.style.opacity = '0';
      card.style.transform = 'scale(0.95)';
      card.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
      setTimeout(() => {
        modal.style.display = 'none';
        resolve();
      }, 400);
    });
  });
}

function playBootSplash() {
  return new Promise(resolve => {
    const splash = document.getElementById('boot-splash');
    if (!splash) { resolve(); return; }

    const glowOrb = splash.querySelector('.boot-glow-orb');
    const glassCard = splash.querySelector('.boot-glass-card');
    const subtitle = document.getElementById('boot-subtitle');

    // Phase 1 (0-0.8s): glow orb expand
    setTimeout(() => { if (glowOrb) glowOrb.classList.add('expand'); }, 200);

    // Phase 2 (0.6-1.6s): glass card reveal (blur→sharp, scale 0.6→1)
    setTimeout(() => { if (glassCard) glassCard.classList.add('reveal'); }, 600);

    // Phase 3 (1.8s): typewriter subtitle
    setTimeout(() => {
      if (!subtitle) return;
      subtitle.classList.add('visible');
      const text = '让灵感，化作画面';
      const cursor = document.createElement('span');
      cursor.className = 'boot-cursor';
      subtitle.appendChild(cursor);
      let i = 0;
      const typeInterval = setInterval(() => {
        if (i < text.length) {
          subtitle.insertBefore(document.createTextNode(text[i]), cursor);
          i++;
        } else {
          clearInterval(typeInterval);
          setTimeout(() => cursor.remove(), 600);
        }
      }, 80);
    }, 1800);

    // Phase 4 (3.2s): fade out entire splash
    setTimeout(() => {
      splash.classList.add('fade-out');
      setTimeout(() => {
        splash.style.display = 'none';
        resolve();
      }, 500);
    }, 3200);
  });
}

function initAllEffectsV2() {
  // 
  const particleCanvas = document.getElementById('particle-canvas');
  if (particleCanvas) new ParticleCanvas(particleCanvas);

  // 
  const globeContainer = document.getElementById('globe-container');
  if (globeContainer && typeof THREE !== 'undefined') {
    new GlobeScene(globeContainer);
  }

  // 
  initShootingStars();

  // 
  initCardEffects();

  // 
  initButtonRipple();

  // 
  initScrollEffects();

  // 
  initSidebarBeam();

  // 
  initEntranceAnimations();

  // Feature card scroll-in observer
  initFeatureCardObserver();

  // Aurora color switching
  initAuroraTheme();

  // Button light sweep
  document.querySelectorAll('.btn-primary.btn-lg').forEach(btn => {
    btn.classList.add('light-sweep');
  });
}

// Feature card IntersectionObserver
function initFeatureCardObserver() {
  const cards = document.querySelectorAll('.feature-card');
  if (!cards.length) return;
  cards.forEach(card => card.classList.add('card-hidden'));
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry, idx) => {
      if (entry.isIntersecting) {
        const card = entry.target;
        const delay = parseInt(card.dataset.index || idx) * 80;
        setTimeout(() => {
          card.classList.remove('card-hidden');
          card.classList.add('card-visible');
        }, delay);
        observer.unobserve(card);
      }
    });
  }, { threshold: 0.15 });
  cards.forEach(card => observer.observe(card));
}

// Aurora background color switching per page
function initAuroraTheme() {
  const themes = { home: 'aurora-home', projects: 'aurora-projects', settings: 'aurora-settings' };
  function updateTheme() {
    document.body.classList.remove('aurora-projects', 'aurora-settings', 'aurora-workspace');
    const theme = themes[state.currentPage] || '';
    if (theme && theme !== 'aurora-home') document.body.classList.add(theme);
    if (state.currentProject) document.body.classList.add('aurora-workspace');
  }
  updateTheme();
  const origNav = window._origNavigateForAurora;
  if (!origNav) {
    window._origNavigateForAurora = true;
    const orig = window.navigateTo;
    if (typeof orig === 'function') {
      window.navigateTo = function(page) {
        orig(page);
        updateTheme();
      };
    }
  }
}


// 
//  6
// 

async function generateStoryboard() {
  if (!state.currentProject) return;
  toggleSynapseLoading(true, 'SYNAPSE 分镜引擎', '正在生成分镜脚本...');
  try {
    const result = await api(`/api/projects/${state.currentProject.id}/storyboard/${state.currentChapter}`, 'POST', null, 1800000);
    state.currentProject.storyboards = state.currentProject.storyboards || {};
    state.currentProject.storyboards[String(state.currentChapter)] = { clips: result.storyboard || result, confirmed: false };
    renderStoryboard();
    showNotification('分镜脚本已生成');
  } catch (e) {
    showNotification('分镜生成失败: ' + e.message, 'error');
  }
  toggleSynapseLoading(false);
}

function modifyStoryboard() {
  showPromptModal('AI优化分镜', async (prompt) => {
    toggleSynapseLoading(true, 'SYNAPSE 分镜引擎', '正在AI优化分镜...');
    try {
      const result = await api(`/api/projects/${state.currentProject.id}/storyboard/${state.currentChapter}/modify`, 'POST', { instruction: prompt }, 1800000);
      state.currentProject.storyboards = state.currentProject.storyboards || {};
      state.currentProject.storyboards[String(state.currentChapter)] = { clips: result.storyboard || result, confirmed: false };
      renderStoryboard();
      showNotification('分镜已修改');
    } catch (e) {
      showNotification('修改分镜失败: ' + e.message, 'error');
    }
    toggleSynapseLoading(false);
  });
}

async function confirmStoryboard() {
  if (!state.currentProject) return;

  // 校验：所有集的分镜脚本必须已生成
  const chapters = state.currentProject.outline?.chapters || state.currentProject.outline?.episodes || [];
  const missingChapters = [];
  for (let i = 0; i < chapters.length; i++) {
    const sb = state.currentProject.storyboards?.[String(i)];
    if (!sb?.clips || sb.clips.length === 0) {
      missingChapters.push(i + 1);
    }
  }
  if (missingChapters.length > 0) {
    showNotification(`请先生成全部分镜脚本，以下集数尚未生成：第${missingChapters.join('、')}集`, 'error');
    return;
  }

  toggleSynapseLoading(true, 'SYNAPSE 分镜引擎', '正在确认分镜...');
  const phaseEl = document.getElementById('loading-phase-text');
  try {
    // 确认所有集的分镜
    const chapters = state.currentProject.outline?.chapters || state.currentProject.outline?.episodes || [];
    for (let i = 0; i < chapters.length; i++) {
      if (state.currentProject.storyboards?.[String(i)]) {
        state.currentProject.storyboards[String(i)].confirmed = true;
      }
    }
    state.currentProject.current_step = 6;
    await api(`/api/projects/${state.currentProject.id}/save`, 'POST', state.currentProject);
    showStep(6);
    showNotification('分镜已确认，正在全量生成分镜图...');

    // 全量生成所有集的分镜图（异步模式）
    if (phaseEl) phaseEl.innerText = '正在提交分镜图生成任务...';
    const result = await api(`/api/projects/${state.currentProject.id}/frames/all/generate`, 'POST', null, 30000);

    if (result.skipped) {
      // 全部已完成
      const allFrames = result.all_frames || {};
      state.currentProject.frames = state.currentProject.frames || {};
      for (const ch in allFrames) {
        state.currentProject.frames[ch] = { frames: allFrames[ch] };
      }
      renderFrames();
      showNotification('分镜图已全部就绪，无需重新生成');
    } else if (result.job_id) {
      // 异步轮询进度
      const jobId = result.job_id;
      const total = result.total || 0;
      if (phaseEl) phaseEl.innerText = `正在生成分镜图 0/${total}...`;

      const pollStatus = async () => {
        while (true) {
          await new Promise(r => setTimeout(r, 5000));
          try {
            const status = await api(`/api/projects/${state.currentProject.id}/frames/generate_status?job_id=${jobId}`, 'GET', null, 10000);
            const completed = status.completed || 0;
            const failed = status.failed || 0;
            const inProg = status.in_progress || 0;
            if (phaseEl) phaseEl.innerText = `正在生成分镜图 ${completed}/${total}（进行中: ${inProg}，失败: ${failed}）`;

            if (status.status === 'completed' || status.status === 'failed') {
              return status;
            }
          } catch (e) {
            console.warn('[frame_poll] error:', e.message);
          }
        }
      };

      const finalStatus = await pollStatus();
      // 加载最终结果
      if (finalStatus.all_frames) {
        state.currentProject.frames = state.currentProject.frames || {};
        for (const ch in finalStatus.all_frames) {
          state.currentProject.frames[ch] = { frames: finalStatus.all_frames[ch] };
        }
      } else {
        // 回退：重新获取project
        const fresh = await api(`/api/projects/${state.currentProject.id}`, 'GET', null, 15000);
        if (fresh.frames) state.currentProject.frames = fresh.frames;
      }
      renderFrames();
      const fc = finalStatus.completed || 0;
      const ff = finalStatus.failed || 0;
      if (ff > 0) {
        showNotification(`分镜图生成完成：${fc}成功，${ff}失败`, 'error');
      } else {
        showNotification(`全量分镜图生成完成（${fc}张）`);
      }
    }
  } catch (e) {
    showNotification('确认分镜失败: ' + (e.message || e), 'error');
  }
  toggleSynapseLoading(false);
}

// 
//  7 - 分镜图展示
// 

function renderFrames() {
  const wsStep6 = document.getElementById('ws-step-6');
  if (!wsStep6) return;
  const chapters = state.currentProject?.outline?.chapters || state.currentProject?.outline?.episodes || [];
  const allFrames = state.currentProject?.frames || {};

  // 如果没有任何frames数据，显示空状态
  const hasAnyFrames = Object.values(allFrames).some(ch => (ch.frames || []).some(f => f.status === 'completed'));
  if (!hasAnyFrames) {
    wsStep6.innerHTML = `
      <h2>分镜图</h2>
      <div class="glass-card" style="text-align:center;padding:60px;">
        <p style="color:var(--text-secondary);margin-bottom:16px;">暂无分镜图</p>
        <button class="btn btn-primary" onclick="confirmStoryboard()">生成全部分镜图</button>
      </div>
    `;
    return;
  }

  const chapTabs = chapters.map((ch, i) => {
    const hasFrames = (allFrames[String(i)]?.frames || []).some(f => f.status === 'completed');
    return `<div class="chapter-tab ${i === state.currentChapter ? 'active' : ''} ${hasFrames ? '' : 'no-data'}" onclick="switchFrameChapter(${i})">${i+1}</div>`;
  }).join('');

  wsStep6.innerHTML = `
    <h2>分镜图</h2>
    <div class="chapter-nav">${chapTabs}</div>
    <div id="frame-chapter-content"></div>
    <div class="action-bar">
      <button class="btn btn-secondary" onclick="confirmStoryboard()">重新生成全部</button>
      <button class="btn btn-primary" onclick="generateVideos()">生成视频</button>
    </div>
  `;
  renderFrameChapter(state.currentChapter);
}

function switchFrameChapter(idx) {
  state.currentChapter = idx;
  // 更新tab高亮
  document.querySelectorAll('.chapter-nav .chapter-tab').forEach((t, i) => {
    t.classList.toggle('active', i === idx);
  });
  renderFrameChapter(idx);
}

function _buildCardHTML(type, chIdx, chStr, i, f, clip, trackDesc, trackUrl, trackLabel, trackPrompt) {
  const chars = clip.characters_in_scene || [];
  const sceneDesc = trackPrompt || '';
  const status = f.status || 'pending';
  const hasImg = !!trackUrl;

  let imgHTML = '';
  if (hasImg) {
    imgHTML = `<div class="frame-preview" onclick="openFrameViewer('${trackUrl}')" style="cursor:pointer;">
      <img src="${trackUrl}" alt="${trackLabel}${i+1}" loading="lazy">
    </div>`;
  } else if (status === 'failed' && type === 'a') {
    imgHTML = `<div class="frame-preview">
      <div class="frame-placeholder"><span>生成失败</span>${f.error ? `<br><span style="font-size:10px;color:var(--text-secondary);">${esc(f.error)}</span>` : ''}</div>
    </div>`;
  } else {
    imgHTML = `<div class="frame-preview">
      <div class="frame-placeholder"><span>${trackLabel} ${i+1}</span></div>
    </div>`;
  }

  const regenFn = type === 'a' ? 'regenerateFrame' : 'regenerateTailFrame';
  const uploadFn = type === 'a' ? 'uploadFrame' : 'uploadTailFrame';
  const modifyFn = type === 'a' ? 'modifyFrame' : 'modifyTailFrame';

    return `
    <div class="glass-card frame-card ${type === 'c' ? 'tail-card' : ''}">
      ${imgHTML}
      <div class="frame-info">
        <div class="frame-title">片段 ${i+1} · ${trackDesc}</div>
        ${sceneDesc ? `<div class="frame-scene">${esc(sceneDesc)}</div>` : ''}
        ${chars.length > 0 ? `<div class="frame-chars">${chars.map(c => '<span class="char-tag">' + esc(c) + '</span>').join('')}</div>` : ''}
      </div>
      <div class="frame-actions">
        <button class="btn btn-icon" title="重新生成" onclick="${regenFn}(${chIdx}, ${i})">&#x21bb; 重新生成</button>
        <label class="btn btn-icon" title="本地上传"><input type="file" accept="image/*" style="display:none;" onchange="${uploadFn}(${chIdx}, ${i}, this)">&#x2191; 本地上传</label>
        <button class="btn btn-icon btn-ai-modify" title="AI修改" onclick="${modifyFn}(${chIdx}, ${i})">&#x2728; AI修改</button>
      </div>
    </div>`;
}

function renderFrameChapter(chIdx) {
  const container = document.getElementById('frame-chapter-content');
  if (!container) return;
  const chStr = String(chIdx);
  const frames = state.currentProject?.frames?.[chStr]?.frames || [];
  const storyboard = state.currentProject?.storyboards?.[chStr]?.clips || [];

  if (frames.length === 0) {
    container.innerHTML = `<div class="glass-card" style="text-align:center;padding:40px;"><p style="color:var(--text-secondary);">第${chIdx+1}集暂无分镜图数据</p></div>`;
    return;
  }

  let cardsHTML = '';
  frames.forEach((f, i) => {
    const clip = storyboard[i] || {};
    const aTrack = clip.a_track || {};
    const cTrack = clip.c_track || {};

    // 参考图 URL
    const imgUrl = f.image_url ? (f.image_url + '?t=' + Date.now()) : '';
    // 尾帧 URL
    let tailUrl = '';
    if (f.tail_frame_url) {
      tailUrl = f.tail_frame_url + '?t=' + Date.now();
    } else if (f.tail_frame_path) {
      tailUrl = `/api/projects/${state.currentProject.id}/frames/${chStr}/${f.clip_index}/tail?t=` + Date.now();
    }

    // 参考图卡片
    cardsHTML += _buildCardHTML('a', chIdx, chStr, i, f, clip, '参考图', imgUrl, '参考图', aTrack.scene_description || '');
    // 尾帧卡片
    cardsHTML += _buildCardHTML('c', chIdx, chStr, i, f, clip, '尾帧', tailUrl, '尾帧', cTrack.scene_description || '');
  });

  container.innerHTML = `<div class="frames-grid">${cardsHTML}</div>`;
}

// ── 参考图操作 ──
async function regenerateFrame(chIdx, clipIdx) {
  toggleSynapseLoading(true, 'SYNAPSE 图像引擎', '正在重新生成参考图...');
  try {
    const result = await api(`/api/projects/${state.currentProject.id}/frames/${chIdx}/${clipIdx}/regenerate`, 'POST', { track: 'a' }, 180000);
    const chStr = String(chIdx);
    if (state.currentProject.frames?.[chStr]?.frames) {
      const frame = state.currentProject.frames[chStr].frames.find(f => f.clip_index === clipIdx);
      if (frame) {
        frame.image_path = result.image_path || frame.image_path;
        frame.image_url = result.image_path || frame.image_url;
        frame.status = 'completed';
        if (frame.error) delete frame.error;
      }
    }
    renderFrameChapter(chIdx);
    showNotification('参考图重新生成完成');
  } catch (e) {
    showNotification('重新生成失败: ' + (e.message || e), 'error');
  }
  toggleSynapseLoading(false);
}

async function uploadFrame(chIdx, clipIdx, input) {
  const file = input.files[0];
  if (!file) return;
  toggleSynapseLoading(true, 'SYNAPSE 图像引擎', '正在上传图片...');
  try {
    const formData = new FormData();
    formData.append('image', file);
    formData.append('track', 'a');
    const result = await api(`/api/projects/${state.currentProject.id}/frames/${chIdx}/${clipIdx}/upload`, 'POST', formData);
    const chStr = String(chIdx);
    if (state.currentProject.frames?.[chStr]?.frames) {
      const frame = state.currentProject.frames[chStr].frames.find(f => f.clip_index === clipIdx);
      if (frame) {
        frame.image_path = result.image_path || frame.image_path;
        frame.image_url = result.image_path || frame.image_url;
        frame.status = 'completed';
        if (frame.error) delete frame.error;
      }
    }
    renderFrameChapter(chIdx);
    showNotification('参考图上传成功');
  } catch (e) {
    showNotification('上传失败: ' + (e.message || e), 'error');
  }
  toggleSynapseLoading(false);
  input.value = '';
}

async function modifyFrame(chIdx, clipIdx) {
  showPromptModal('AI修改参考图', async (instruction) => {
    toggleSynapseLoading(true, 'SYNAPSE 图像引擎', '正在AI修改参考图...');
    try {
      const result = await api(`/api/projects/${state.currentProject.id}/frames/${chIdx}/${clipIdx}/regenerate`, 'POST', { instruction, track: 'a' }, 180000);
      const chStr = String(chIdx);
      if (state.currentProject.frames?.[chStr]?.frames) {
        const frame = state.currentProject.frames[chStr].frames.find(f => f.clip_index === clipIdx);
        if (frame) {
          frame.image_path = result.image_path || frame.image_path;
          frame.image_url = result.image_path || frame.image_url;
          frame.status = 'completed';
          if (frame.error) delete frame.error;
        }
      }
      renderFrameChapter(chIdx);
      showNotification('AI修改完成');
    } catch (e) {
      showNotification('AI修改失败: ' + (e.message || e), 'error');
    }
    toggleSynapseLoading(false);
  });
}

// ── 尾帧操作 ──
async function regenerateTailFrame(chIdx, clipIdx) {
  toggleSynapseLoading(true, 'SYNAPSE 图像引擎', '正在重新生成尾帧...');
  try {
    const result = await api(`/api/projects/${state.currentProject.id}/frames/${chIdx}/${clipIdx}/regenerate`, 'POST', { track: 'c' }, 180000);
    const chStr = String(chIdx);
    if (state.currentProject.frames?.[chStr]?.frames) {
      const frame = state.currentProject.frames[chStr].frames.find(f => f.clip_index === clipIdx);
      if (frame) {
        frame.tail_frame_path = result.image_path || frame.tail_frame_path;
        frame.tail_frame_url = result.image_path || frame.tail_frame_url;
      }
    }
    renderFrameChapter(chIdx);
    showNotification('尾帧重新生成完成');
  } catch (e) {
    showNotification('尾帧重新生成失败: ' + (e.message || e), 'error');
  }
  toggleSynapseLoading(false);
}

async function uploadTailFrame(chIdx, clipIdx, input) {
  const file = input.files[0];
  if (!file) return;
  toggleSynapseLoading(true, 'SYNAPSE 图像引擎', '正在上传尾帧...');
  try {
    const formData = new FormData();
    formData.append('image', file);
    formData.append('track', 'c');
    const result = await api(`/api/projects/${state.currentProject.id}/frames/${chIdx}/${clipIdx}/upload`, 'POST', formData);
    const chStr = String(chIdx);
    if (state.currentProject.frames?.[chStr]?.frames) {
      const frame = state.currentProject.frames[chStr].frames.find(f => f.clip_index === clipIdx);
      if (frame) {
        frame.tail_frame_path = result.image_path || frame.tail_frame_path;
        frame.tail_frame_url = result.image_path || frame.tail_frame_url;
      }
    }
    renderFrameChapter(chIdx);
    showNotification('尾帧上传成功');
  } catch (e) {
    showNotification('上传失败: ' + (e.message || e), 'error');
  }
  toggleSynapseLoading(false);
  input.value = '';
}

async function modifyTailFrame(chIdx, clipIdx) {
  showPromptModal('AI修改尾帧', async (instruction) => {
    toggleSynapseLoading(true, 'SYNAPSE 图像引擎', '正在AI修改尾帧...');
    try {
      const result = await api(`/api/projects/${state.currentProject.id}/frames/${chIdx}/${clipIdx}/regenerate`, 'POST', { instruction, track: 'c' }, 180000);
      const chStr = String(chIdx);
      if (state.currentProject.frames?.[chStr]?.frames) {
        const frame = state.currentProject.frames[chStr].frames.find(f => f.clip_index === clipIdx);
        if (frame) {
          frame.tail_frame_path = result.image_path || frame.tail_frame_path;
          frame.tail_frame_url = result.image_path || frame.tail_frame_url;
        }
      }
      renderFrameChapter(chIdx);
      showNotification('尾帧AI修改完成');
    } catch (e) {
      showNotification('AI修改失败: ' + (e.message || e), 'error');
    }
    toggleSynapseLoading(false);
  });
}


function openFrameViewer(imageUrl) {
  let overlay = document.getElementById('frame-viewer-overlay');
  if (overlay) overlay.remove();
  overlay = document.createElement('div');
  overlay.id = 'frame-viewer-overlay';
  overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);z-index:9999;display:flex;align-items:center;justify-content:center;cursor:pointer;';
  overlay.onclick = () => overlay.remove();
  overlay.innerHTML = `<img src="${imageUrl}" style="max-width:95%;max-height:95%;border-radius:8px;">`;
  document.body.appendChild(overlay);
}

// 
//  8
// 

function renderVideos(chIdx) {
  const container = document.getElementById('video-chapter-content');
  if (!container) return;
  const chStr = String(chIdx);
  let videos = state.currentProject?.videos?.[chStr]?.tasks || [];
  // 去重：同一 clip_index 只保留一条，优先 completed > submitted > 有 task_id
  const deduped = new Map();
  for (const v of videos) {
    const key = v.clip_index;
    const existing = deduped.get(key);
    if (!existing) { deduped.set(key, v); continue; }
    const score = (v.status === 'completed' ? 3 : v.status === 'submitted' ? 2 : v.task_id ? 1 : 0);
    const existScore = (existing.status === 'completed' ? 3 : existing.status === 'submitted' ? 2 : existing.task_id ? 1 : 0);
    if (score > existScore) deduped.set(key, v);
  }
  videos = [...deduped.values()].sort((a, b) => (a.clip_index ?? 0) - (b.clip_index ?? 0));
  const storyboard = state.currentProject?.storyboards?.[chStr]?.clips || [];

  if (videos.length === 0) {
    container.innerHTML = `<div class="glass-card" style="text-align:center;padding:40px;"><p style="color:var(--text-secondary);">第${chIdx+1}集暂无视频数据</p></div>`;
    return;
  }

  container.innerHTML = `<div class="videos-grid">${videos.map((v, i) => {
    const clip = storyboard[v.clip_index] || {};
    const aTrack = clip.a_track || {};
    const chars = clip.characters_in_scene || [];
    const sceneDesc = aTrack.scene_description || '';
    const videoUrl = v.video_url || '';
    const status = v.status || 'pending';
    const clipIdx = v.clip_index !== undefined ? v.clip_index : i;

    return `
      <div class="glass-card frame-card video-card">
        <div class="video-preview" onclick="${videoUrl ? `openVideoViewer('${videoUrl}')` : ''}" style="${videoUrl ? 'cursor:pointer;' : ''}">
          ${status === 'completed' && videoUrl
            ? `<video src="${videoUrl}" muted preload="metadata" style="width:100%;aspect-ratio:16/9;border-radius:8px;background:#000;"></video><div class="video-play-overlay">&#9654;</div>`
            : `<div class="frame-placeholder"><span>${status === 'failed' ? '生成失败' : '片段 ' + (clipIdx+1)}</span>${v.error ? `<br><span style="font-size:10px;color:var(--text-secondary);">${esc(v.error)}</span>` : ''}</div>`
          }
        </div>
        <div class="frame-info">
          <div class="frame-title">片段 ${clipIdx+1}</div>
          ${sceneDesc ? `<div class="frame-scene">${esc(sceneDesc)}</div>` : ''}
          ${chars.length > 0 ? `<div class="frame-chars">${chars.map(c => '<span class="char-tag">' + esc(c) + '</span>').join('')}</div>` : ''}
        </div>
        <div class="frame-actions">
          ${status === 'failed' ? `<button class="btn btn-icon" title="重试" onclick="retryVideo(${chIdx}, ${clipIdx})" style="color:#f59e0b;">&#x21bb; 重试</button>` : ''}
          <button class="btn btn-icon" title="重新生成" onclick="regenerateVideo(${chIdx}, ${clipIdx})">&#x21bb; 重新生成</button>
          <label class="btn btn-icon" title="本地上传"><input type="file" accept="video/*" style="display:none;" onchange="uploadVideo(${chIdx}, ${clipIdx}, this)">&#x2191; 本地上传</label>
        </div>
      </div>
    `;
  }).join('')}</div>`;

  // Update state.videos for the chapter
  state.currentProject._videoChapter = chIdx;
}

async function generateVideos() {
  if (!state.currentProject) return;
  // 防重复提交锁
  if (sessionStorage.getItem('_videoGenerating')) {
    showNotification('视频任务正在提交中，请勿重复点击', 'warning');
    return;
  }
  sessionStorage.setItem('_videoGenerating', '1');
  toggleSynapseLoading(true, 'SYNAPSE 视频引擎', '正在全量提交视频生成任务...');
  try {
    // 1. 提交所有集所有片段
    const submitResult = await api(`/api/projects/${state.currentProject.id}/videos/all/generate`, 'POST', null, 120000);

    // 异步提交模式：返回了job_id说明后台在分批提交，轮询提交进度
    if (submitResult.job_id) {
      const jobId = submitResult.job_id;
      let pollCount = 0;
      while (true) {
        await new Promise(r => setTimeout(r, 3000));
        pollCount++;
        let st;
        try {
          st = await api(`/api/projects/${state.currentProject.id}/videos/all/submit_status?job_id=${jobId}`, 'GET', null, 10000);
        } catch(e) { continue; }
        if (!st || !st.success) break;
        const done = st.submitted || 0;
        const errs = st.failed || 0;
        const pct = st.total ? Math.round((done + errs) / st.total * 100) : 0;
        toggleSynapseLoading(true, 'SYNAPSE 视频引擎', `正在提交视频任务 ${done + errs}/${st.total} (${pct}%)`);
        if (st.done) {
          const realResults = st.results || {};
          if (Object.keys(realResults).length > 0) {
            submitResult.results = realResults;
            // 预更新本地state，避免后面的轮询从空project读取
            state.currentProject.videos = state.currentProject.videos || {};
            for (const ch in realResults) {
              state.currentProject.videos[ch] = state.currentProject.videos[ch] || {};
              state.currentProject.videos[ch].tasks = realResults[ch];
            }
            api(`/api/projects/${state.currentProject.id}/save`, 'POST', state.currentProject).catch(() => {});
          }
          break;
        }
        if (pollCount > 1200) break; // 1小时超时保护
      }
    }

    const results = submitResult.results || {};
    let totalTasks = 0, totalSubmitted = 0, totalFailed = 0;
    for (const ch in results) {
      for (const t of results[ch]) {
        totalTasks++;
        if (t.status === 'submitted') totalSubmitted++;
        if (t.status === 'failed') totalFailed++;
      }
    }
    showNotification(`已提交 ${totalSubmitted}/${totalTasks} 个视频任务${totalFailed > 0 ? `，${totalFailed}个提交失败` : ''}，开始轮询...`);

    // 没有实际提交的任务时，不跳转视频页
    if (totalSubmitted === 0) {
      showNotification(totalFailed > 0 ? `${totalFailed}个任务提交失败，请检查分镜图是否完整` : '没有需要生成的视频任务', 'error');
      toggleSynapseLoading(false);
      sessionStorage.removeItem('_videoGenerating');
      return;
    }

    // 有实际任务提交，解锁步骤7
    state.currentProject.current_step = 7;
    api(`/api/projects/${state.currentProject.id}/save`, 'POST', state.currentProject).catch(() => {});

    // 更新本地state（如果上面已预更新，这里是幂等的）
    state.currentProject.videos = state.currentProject.videos || {};
    for (const ch in results) {
      state.currentProject.videos[ch] = state.currentProject.videos[ch] || {};
      state.currentProject.videos[ch].tasks = results[ch];
    }

    // 2. 轮询所有集
    const maxWait = 5400000; // 90分钟
    const pollInterval = 8000;
    const startTime = Date.now();

    while (Date.now() - startTime < maxWait) {
      await new Promise(r => setTimeout(r, pollInterval));
      const elapsed = Math.round((Date.now() - startTime) / 1000);
      toggleSynapseLoading(true, 'SYNAPSE 视频引擎', `正在轮询全部视频生成状态... (${elapsed}s)`);

      try {
        const pollResult = await api(`/api/projects/${state.currentProject.id}/videos/all/poll`, 'GET', null, 180000);
        const pollResults = pollResult.results || {};

        // 更新state - 兼容数据结构：pollResults[ch]可能是数组或{tasks:[...]}对象
        let completed = 0, failed = 0, pending = 0, retrying = 0, downloading = 0;
        for (const ch in pollResults) {
          const tasksArray = Array.isArray(pollResults[ch]) ? pollResults[ch] : (pollResults[ch]?.tasks || []);
          state.currentProject.videos[ch] = state.currentProject.videos[ch] || {};
          state.currentProject.videos[ch].tasks = tasksArray;
          for (const t of tasksArray) {
            if (t.status === 'completed' && t.download_status !== 'failed') completed++;
            else if (t.status === 'failed' || t.download_status === 'failed') failed++;
            else {
              pending++;
              if (t.video_retry_count > 0) retrying++;
              if (t.download_status === 'downloading') downloading++;
            }
          }
        }

        const retryInfo = retrying > 0 ? ` (${retrying}个重试中)` : '';
        const dlInfo = downloading > 0 ? ` [${downloading}个下载中]` : '';
        const totalChapters = Object.keys(pollResults).length;
        const doneChapters = Object.keys(pollResults).filter(ch => {
          const arr = Array.isArray(pollResults[ch]) ? pollResults[ch] : (pollResults[ch]?.tasks || []);
          return arr.every(t => (t.status === 'completed' && t.download_status !== 'failed') || t.status === 'failed' || t.download_status === 'failed');
        }).length;
        toggleSynapseLoading(true, 'SYNAPSE 视频引擎', `视频生成中: ${completed}完成 / ${failed}失败 / ${pending}进行中${retryInfo}${dlInfo} (${elapsed}s)`);
        const subEl = document.getElementById('synapse-loading-subtext');
        if (subEl) subEl.innerText = `总进度：${doneChapters} / ${totalChapters} 集`;

        if (pending === 0) {
          toggleSynapseLoading(false);
          if (completed === 0 && failed > 0) {
            // 全部失败，不跳转，留在当前页面让用户排查
            showNotification(`全部视频生成失败(${failed}个): 请检查分镜图或点击失败项重试`, 'error');
            renderVideos(state.currentChapter);
          } else {
            // 至少有成功的，正常跳转视频页
            renderVideoStep();
            renderVideos(state.currentChapter);
            showNotification(failed > 0 ? `视频生成完成: ${completed}成功, ${failed}失败` : '全部视频生成完成');
            showStep(7);
          }
          sessionStorage.removeItem('_videoGenerating');
          return;
        }
      } catch (pollErr) {
        console.warn('轮询出错，继续重试:', pollErr);
      }
    }

    showNotification('视频生成超时(90分钟)，请稍后手动刷新', 'error');
    renderVideoStep();
    renderVideos(state.currentChapter);
  } catch (e) {
    showNotification('视频生成失败: ' + e.message, 'error');
  }
  sessionStorage.removeItem('_videoGenerating');
  toggleSynapseLoading(false);
}

// 
//  9
// 


function renderVideoStep() {
  const wsStep7 = document.getElementById('ws-step-7');
  if (!wsStep7) return;
  const chapters = state.currentProject?.outline?.chapters || state.currentProject?.outline?.episodes || [];
  const allVideos = state.currentProject?.videos || {};

  const hasAnyVideos = Object.values(allVideos).some(ch => (ch.tasks || []).some(t => t.status === 'completed'));
  if (!hasAnyVideos) {
    wsStep7.innerHTML = `
      <h2>AI视频</h2>
      <div class="glass-card" style="text-align:center;padding:60px;">
        <p style="color:var(--text-secondary);margin-bottom:16px;">暂无视频</p>
        <button class="btn btn-primary" onclick="generateVideos()">生成视频</button>
      </div>
    `;
    return;
  }

  const chapTabs = chapters.map((ch, i) => {
    const hasVideos = (allVideos[String(i)]?.tasks || []).some(t => t.status === 'completed');
    return `<div class="chapter-tab ${i === state.currentChapter ? 'active' : ''} ${hasVideos ? '' : 'no-data'}" onclick="switchVideoChapter(${i})">${i+1}</div>`;
  }).join('');

  wsStep7.innerHTML = `
    <h2>AI视频</h2>
    <div class="chapter-nav">${chapTabs}</div>
    <div id="video-chapter-content"></div>
    <div class="action-bar">
      <button class="btn btn-primary" onclick="enterCompose()">进入后期合成</button>
    </div>
  `;
  renderVideos(state.currentChapter);
}

function switchVideoChapter(idx) {
  state.currentChapter = idx;
  document.querySelectorAll('#ws-step-7 .chapter-nav .chapter-tab').forEach((t, i) => {
    t.classList.toggle('active', i === idx);
  });
  renderVideos(idx);
}

async function retryVideo(chIdx, clipIdx) {
  toggleSynapseLoading(true, 'SYNAPSE 视频引擎', '正在重试视频生成...');
  try {
    const result = await api(`/api/projects/${state.currentProject.id}/videos/${chIdx}/${clipIdx}/retry`, 'POST', {}, 120000);
    if (result.success) {
      showNotification('视频已重新提交');
      // 更新本地state
      const chStr = String(chIdx);
      const tasks = state.currentProject.videos?.[chStr]?.tasks || [];
      const task = tasks.find(t => t.clip_index === clipIdx);
      if (task) {
        task.status = 'submitted';
        task.task_id = result.task?.task_id;
        task.error = '';
      }
      renderVideos(chIdx);
      // 开始轮询
      await pollVideoChapter(chIdx);
    } else {
      showNotification(result.message || '重试失败', 'error');
    }
  } catch (e) {
    showNotification('重试失败: ' + (e.message || e), 'error');
  }
  toggleSynapseLoading(false);
}

async function regenerateVideo(chIdx, clipIdx) {
  if (sessionStorage.getItem('_videoGenerating')) {
    showNotification('视频任务进行中，请稍后再试', 'warning');
    return;
  }
  toggleSynapseLoading(true, 'SYNAPSE 视频引擎', '正在重新生成视频...');
  try {
    const result = await api(`/api/projects/${state.currentProject.id}/videos/${chIdx}/${clipIdx}/regenerate`, 'POST', {}, 120000);
    showNotification('视频已重新提交生成');
    // Start polling for this chapter
    await pollVideoChapter(chIdx);
  } catch (e) {
    showNotification('重新生成失败: ' + (e.message || e), 'error');
  }
  toggleSynapseLoading(false);
}

async function pollVideoChapter(chIdx) {
  const maxWait = 1800000;
  const pollInterval = 8000;
  const startTime = Date.now();
  const total = (state.currentProject.videos?.[String(chIdx)]?.tasks || []).length;

  while (Date.now() - startTime < maxWait) {
    await new Promise(r => setTimeout(r, pollInterval));
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    toggleSynapseLoading(true, 'SYNAPSE 视频引擎', `正在轮询视频生成状态... (${elapsed}s)`);

    try {
      const pollResult = await api(`/api/projects/${state.currentProject.id}/videos/${chIdx}/poll`, 'GET');
      const pollTasks = pollResult.tasks || [];
      state.currentProject.videos[String(chIdx)] = { tasks: pollTasks };

      const completed = pollTasks.filter(t => t.status === 'completed').length;
      const failed = pollTasks.filter(t => t.status === 'failed').length;
      const pending = total - completed - failed;

      if (pending === 0) {
        renderVideos(chIdx);
        if (failed > 0) {
          showNotification(`视频生成完成: ${completed}成功, ${failed}失败`, 'warning');
        } else {
          showNotification('全部视频生成完成');
        }
        return;
      }
    } catch (pollErr) {
      console.warn('轮询出错，继续重试:', pollErr);
    }
  }
  showNotification('视频生成超时', 'error');
  renderVideos(chIdx);
}

async function uploadVideo(chIdx, clipIdx, input) {
  const file = input.files[0];
  if (!file) return;
  toggleSynapseLoading(true, 'SYNAPSE 视频引擎', '正在上传视频...');
  try {
    const formData = new FormData();
    formData.append('video', file);
    const result = await api(`/api/projects/${state.currentProject.id}/videos/${chIdx}/${clipIdx}/upload`, 'POST', formData);
    // Update local state
    const chStr = String(chIdx);
    if (state.currentProject.videos?.[chStr]?.tasks) {
      const task = state.currentProject.videos[chStr].tasks.find(t => t.clip_index === clipIdx);
      if (task) {
        task.video_path = result.video_path || task.video_path;
        task.video_url = (result.video_url || task.video_url) + '?t=' + Date.now();
        task.status = 'completed';
        if (task.error) delete task.error;
      }
    }
    renderVideos(chIdx);
    showNotification('视频上传成功');
  } catch (e) {
    showNotification('上传失败: ' + (e.message || e), 'error');
  }
  toggleSynapseLoading(false);
  input.value = '';
}

function openVideoViewer(videoUrl) {
  let overlay = document.getElementById('video-viewer-overlay');
  if (overlay) overlay.remove();
  overlay = document.createElement('div');
  overlay.id = 'video-viewer-overlay';
  overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.92);z-index:9999;display:flex;align-items:center;justify-content:center;cursor:pointer;';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  overlay.innerHTML = `
    <video src="${videoUrl}" controls autoplay style="max-width:95%;max-height:95%;border-radius:8px;cursor:default;" onclick="event.stopPropagation();"></video>
    <div style="position:absolute;top:20px;right:30px;color:white;font-size:28px;cursor:pointer;" onclick="document.getElementById('video-viewer-overlay').remove();">&#x2715;</div>
  `;
  document.body.appendChild(overlay);
}


function enterCompose() {
  if (!state.currentProject) return;
  showStep(8);
}

async function renderComposeStep() {
  const container = document.getElementById('compose-content');
  if (!container || !state.currentProject) return;

  const chapters = state.currentProject?.outline?.chapters || state.currentProject?.outline?.episodes || [];
  if (!chapters.length) {
    container.innerHTML = `<div class="glass-card" style="text-align:center;padding:60px;">
      <p style="color:var(--text-secondary);margin-bottom:16px;">暂无剧集数据，请先完成大纲</p>
    </div>`;
    return;
  }

  // Fetch compose status
  let statuses = [];
  try {
    const resp = await api(`/api/projects/${state.currentProject.id}/compose/status`, 'GET');
    statuses = resp.chapters || [];
  } catch (e) {
    statuses = chapters.map((ch, i) => ({ index: i, title: ch.title || `第${i+1}集`, has_composed: false, completed_videos: 0, total_clips: 0 }));
  }

  const composedCount = statuses.filter(s => s.has_composed).length;

  const chapterListHTML = statuses.map(s => {
    let statusBadge = '';
    if (s.has_composed) {
      statusBadge = '<span class="compose-status-badge completed">已合成</span>';
    } else if (s.completed_videos > 0) {
      statusBadge = '<span class="compose-status-badge partial">部分就绪</span>';
    } else {
      statusBadge = '<span class="compose-status-badge pending">未就绪</span>';
    }
    const canCompose = s.completed_videos > 0;
    return `<div class="compose-chapter-item" id="compose-ch-${s.index}">
      <div class="compose-chapter-idx">${s.index + 1}</div>
      <div class="compose-chapter-info">
        <div class="compose-chapter-title">${esc(s.title)}</div>
        <div class="compose-chapter-meta">${s.completed_videos}/${s.total_clips} 个视频片段已生成</div>
      </div>
      ${statusBadge}
      <button class="btn btn-secondary compose-btn-sm" onclick="composeChapter(${s.index})" ${canCompose ? '' : 'disabled'}>${s.has_composed ? '重新合成' : '合成'}</button>
    </div>`;
  }).join('');

  container.innerHTML = `
    <div class="glass-card compose-settings">
      <h3>渲染管线</h3>
      <div class="render-preset-row">
        <div class="render-preset-card active" data-preset="standard" onclick="selectRenderPreset('standard')">
          <div class="render-preset-name">标准品质</div>
          <div class="render-preset-desc">画质与速度平衡</div>
          <div class="render-preset-spec">H.264 / 1080p / 30fps / CRF 18</div>
        </div>
        <div class="render-preset-card" data-preset="draft" onclick="selectRenderPreset('draft')">
          <div class="render-preset-name">快速预览</div>
          <div class="render-preset-desc">速度优先，快速检查</div>
          <div class="render-preset-spec">H.264 / 720p / 24fps / CRF 23</div>
        </div>
        <div class="render-preset-card" data-preset="professional" onclick="selectRenderPreset('professional')">
          <div class="render-preset-name">专业品质</div>
          <div class="render-preset-desc">商业级画质，耗时较长</div>
          <div class="render-preset-spec">H.265 / 1080p / 30fps / CRF 15</div>
        </div>
      </div>
      <input type="hidden" id="render-preset" value="standard">

      <h3>合成设置</h3>
      <div class="form-row">
        <div class="form-group"><label>转场效果</label><div class="combobox-trigger" data-combobox="transition">
          <input type="hidden" id="transition" value="none">
          <input type="text" id="transition-display" class="input" value="" readonly placeholder="">
        </div>
        <div id="dropdown-transition" class="combobox-dropdown">
          <div class="combobox-option" data-value="none">无</div>
          <div class="combobox-option" data-value="fade">交叉溶解</div>
          <div class="combobox-option" data-value="fadeblack">闪黑</div>
          <div class="combobox-option" data-value="fadewhite">闪白</div>
          <div class="combobox-option" data-value="dissolve">溶解</div>
          <div class="combobox-option" data-value="wipeleft">左擦除</div>
          <div class="combobox-option" data-value="slideright">右滑入</div>
        </div></div>
        <div class="form-group" style="flex:1;"><label>转场时长</label>
          <div style="display:flex;align-items:center;gap:8px;">
            <input type="range" id="transition-duration" class="input" value="0.5" min="0.3" max="2.0" step="0.1" style="flex:1;" oninput="document.getElementById('transition-dur-label').textContent=this.value+'秒'">
            <span id="transition-dur-label" style="min-width:40px;font-size:13px;color:var(--text-secondary);">0.5秒</span>
          </div>
        </div>
      </div>
      <div class="form-row" style="margin-top:4px;">
        <div class="form-group" style="flex:1;"><label>转场说明</label>
          <div id="transition-desc" style="font-size:12px;color:var(--text-secondary);line-height:1.5;">交叉溶解：两段视频平滑过渡，适合连续叙事</div>
        </div>
      </div>
    </div>
    <div class="glass-card">
      <h3>剧集列表 <span style="font-size:12px;color:var(--text-secondary);font-weight:400;">${composedCount}/${statuses.length} 已合成</span></h3>
      <div class="compose-chapter-list">${chapterListHTML}</div>
      <div id="compose-progress-area"></div>
      <div class="compose-action-bar">
        <button class="btn btn-primary btn-lg" onclick="composeAllChapters()">全部合成</button>
      </div>
    </div>

    <div class="glass-card" style="margin-top:16px;">
      <h3>直接导出</h3>
      <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px;">不加字幕和转场，直接按顺序拼接所有片段。适合二次创作、剪辑加工。</p>
      <div class="form-row" style="align-items:center;">
        <div class="form-group" style="flex:1;">
          <div class="combobox-trigger" data-combobox="raw-export-ch">
            <input type="hidden" id="raw-export-ch" value="0">
            <input type="text" id="raw-export-ch-display" class="input" value="" readonly placeholder="选择要导出的集数">
          </div>
          <div id="dropdown-raw-export-ch" class="combobox-dropdown">
            ${statuses.filter(s => s.completed_videos > 0).map(s =>
              '<div class="combobox-option" data-value="' + s.index + '">' + esc(s.title) + ' (' + s.completed_videos + '/' + s.total_clips + ' 片段)</div>'
            ).join('')}
          </div>
        </div>
        <button class="btn btn-secondary btn-lg" onclick="rawExportChapter()" id="raw-export-btn">导出视频</button>
      </div>
      <div id="raw-export-status" style="margin-top:8px;font-size:13px;color:var(--text-secondary);display:none;"></div>
    </div>

    <div class="glass-card" style="margin-top:16px;">
      <h3>海报设计</h3>
      <div id="poster-section"></div>
    </div>

    <div id="compose-preview-area"></div>
  `;

  // Initialize comboboxes
  if (typeof initAllComboboxes === 'function') initAllComboboxes();

  // Bind preview updates
  setTimeout(() => {
    // Transition combobox → update description
    const transDisplay = document.getElementById('transition-display');
    if (transDisplay) transDisplay.addEventListener('change', () => {
      const val = document.getElementById('transition')?.value || 'none';
      const desc = document.getElementById('transition-desc');
      if (desc) desc.textContent = TRANSITION_DESC[val] || '';
    });
    // Render poster section
    renderPosterSection();
  }, 100);
}

function selectRenderPreset(presetId) {
  document.querySelectorAll('.render-preset-card').forEach(card => {
    card.classList.toggle('active', card.dataset.preset === presetId);
  });
  const hidden = document.getElementById('render-preset');
  if (hidden) hidden.value = presetId;
}

const TRANSITION_DESC = {
  none: '无转场：片段直接切换，适合节奏快的叙事',
  fade: '交叉溶解：两段视频平滑过渡，适合连续叙事',
  fadeblack: '闪黑：画面渐黑再渐亮，适合场景切换/紧张感',
  fadewhite: '闪白：画面渐白再渐亮，适合回忆/梦境/时间跳跃',
  dissolve: '溶解：像素级混合过渡，比交叉溶解更柔和',
  wipeleft: '左擦除：新画面从右侧推进，适合方向性叙事',
  slideright: '右滑入：新画面从左侧滑入，适合平行叙事',
};

function updateSubtitlePreview() {
  // 字幕功能已移除
}

function getComposeSettings() {
  return {
    transition: document.getElementById('transition')?.value || 'none',
    transition_duration: parseFloat(document.getElementById('transition-duration')?.value || '0.5'),
    render_preset: document.getElementById('render-preset')?.value || 'standard',
  };
}

async function composeChapter(chIdx) {
  if (!state.currentProject) return;
  const progressArea = document.getElementById('compose-progress-area');
  if (progressArea) {
    progressArea.innerHTML = `<div class="compose-progress-container">
      <div class="compose-progress-text">正在合成第${chIdx + 1}集...</div>
      <div class="progress-track"><div class="progress-fill" id="compose-progress-fill" style="width:30%;"><div class="light-streak"></div></div></div>
    </div>`;
  }

  try {
    const settings = getComposeSettings();
    const result = await api(`/api/projects/${state.currentProject.id}/compose/${chIdx}`, 'POST', settings, 600000);

    if (progressArea) {
      const fill = document.getElementById('compose-progress-fill');
      if (fill) fill.style.width = '100%';
    }

    showNotification(`第${chIdx + 1}集合成完成`);

    // 刷新剧集列表
    await renderComposeStep();

    // 合成完成，跳转到导出步骤
    showStep(9);
  } catch (e) {
    showNotification('合成失败: ' + (e.message || e), 'error');
    if (progressArea) progressArea.innerHTML = '';
  }
}

async function composeAllChapters() {
  if (!state.currentProject) return;
  const progressArea = document.getElementById('compose-progress-area');
  if (progressArea) {
    progressArea.innerHTML = `<div class="compose-progress-container">
      <div class="compose-progress-text">正在逐集合成...</div>
      <div class="progress-track"><div class="progress-fill" id="compose-progress-fill" style="width:0%;"><div class="light-streak"></div></div></div>
    </div>`;
  }

  // Get chapters that need composing
  let statuses = [];
  try {
    const resp = await api(`/api/projects/${state.currentProject.id}/compose/status`, 'GET');
    statuses = (resp.chapters || []).filter(s => s.completed_videos > 0);
  } catch (e) {
    showNotification('获取状态失败: ' + (e.message || e), 'error');
    return;
  }

  if (!statuses.length) {
    showNotification('没有可合成的剧集', 'warning');
    if (progressArea) progressArea.innerHTML = '';
    return;
  }

  const settings = getComposeSettings();

  let completed = 0;
  let failed = 0;

  // 并行合成，最大3个同时跑（避免ffmpeg把机器跑爆）
  const CONCURRENT = 3;
  for (let i = 0; i < statuses.length; i += CONCURRENT) {
    const batch = statuses.slice(i, i + CONCURRENT);
    const results = await Promise.allSettled(
      batch.map(s => api(`/api/projects/${state.currentProject.id}/compose/${s.index}`, 'POST', settings, 600000))
    );
    for (let j = 0; j < results.length; j++) {
      const r = results[j];
      if (r.status === 'fulfilled') {
        completed++;
      } else {
        failed++;
        console.warn(`合成第${batch[j].index + 1}集失败:`, r.reason);
      }
    }
    // 更新进度
    const pct = Math.round(((completed + failed) / statuses.length) * 100);
    if (progressArea) {
      const fill = document.getElementById('compose-progress-fill');
      const text = progressArea.querySelector('.compose-progress-text');
      if (fill) fill.style.width = pct + '%';
      if (text) text.textContent = `合成进度: ${completed + failed}/${statuses.length} (成功${completed}, 失败${failed})`;
    }
  }

  if (progressArea) {
    const fill = document.getElementById('compose-progress-fill');
    if (fill) fill.style.width = '100%';
  }

  // 刷新剧集列表
  await renderComposeStep();

  if (completed > 0) {
    showNotification(`${completed}/${statuses.length} 集合成完成${failed > 0 ? `，${failed}集失败` : ''}`);
    // 全部合成完成，跳转到导出步骤
    showStep(9);
  } else {
    showNotification('合成失败', 'error');
  }
}

async function rawExportChapter() {
  if (!state.currentProject) return;
  const chIdx = parseInt(document.getElementById('raw-export-ch')?.value || '0');
  const statusEl = document.getElementById('raw-export-status');
  const btn = document.getElementById('raw-export-btn');
  if (btn) btn.disabled = true;
  if (statusEl) { statusEl.style.display = 'block'; statusEl.textContent = '正在拼接视频...'; statusEl.style.color = 'var(--text-secondary)'; }

  try {
    const result = await api(`/api/projects/${state.currentProject.id}/compose/${chIdx}/raw-export`, 'POST', {}, 600000);
    if (result.success) {
      if (statusEl) {
        statusEl.innerHTML = `导出完成! ${result.clip_count} 个片段已拼接`;
        statusEl.style.color = '#22c55e';
        // 保存到本地按钮
        const saveBtn = document.createElement('button');
        saveBtn.className = 'btn btn-primary btn-sm';
        saveBtn.style.cssText = 'margin-left:12px;';
        saveBtn.textContent = '保存到本地';
        saveBtn.onclick = () => exportVideo(`/api/projects/${state.currentProject.id}/compose/${chIdx}/raw-export/save-as`);
        statusEl.appendChild(saveBtn);
      }
      showNotification('直接导出完成');
    }
  } catch (e) {
    if (statusEl) { statusEl.textContent = '导出失败: ' + (e.message || e); statusEl.style.color = '#ef4444'; }
    showNotification('导出失败', 'error');
  }
  if (btn) btn.disabled = false;
}

async function exportVideo(saveAsUrl) {
  try {
    const info = await api(saveAsUrl);
    if (!info.success) { showNotification(info.message || '视频不存在', 'error'); return; }

    if (window.pywebview && window.pywebview.api && window.pywebview.api.export_video_to_path) {
      const result = await window.pywebview.api.export_video_to_path(info.source_path, info.default_name);
      if (result.cancelled) return;
      if (result.success) {
        showNotification('视频已保存: ' + result.path);
      } else {
        showNotification('保存失败: ' + result.error, 'error');
      }
    } else {
      // 非pywebview环境，走后端下载
      window.open('/api/file?path=' + encodeURIComponent(info.source_path), '_blank');
    }
  } catch (e) {
    showNotification('导出失败: ' + (e.message || e), 'error');
  }
}

// ════════════════════════════════════════
//  海报生成功能
// ════════════════════════════════════════

async function renderPosterSection() {
  const section = document.getElementById('poster-section');
  if (!section || !state.currentProject) return;

  // 获取所有分镜图（首帧+尾帧）
  const frames = state.currentProject.frames || {};
  const frameList = [];
  for (const [chIdx, chData] of Object.entries(frames)) {
    for (const f of (chData.frames || [])) {
      if (f.status === 'completed') {
        if (f.image_url) {
          frameList.push({
            chapter: parseInt(chIdx),
            clip_index: f.clip_index,
            frame_type: 'head',
            image_url: f.image_url + '?t=' + Date.now(),
            label: `第${parseInt(chIdx)+1}集-镜头${f.clip_index+1} 首帧`
          });
        }
        if (f.tail_frame_url) {
          frameList.push({
            chapter: parseInt(chIdx),
            clip_index: f.clip_index,
            frame_type: 'tail',
            image_url: f.tail_frame_url + '?t=' + Date.now(),
            label: `第${parseInt(chIdx)+1}集-镜头${f.clip_index+1} 尾帧`
          });
        }
      }
    }
  }

  const poster = state.currentProject.poster || {};
  const defaultTitle = poster.title || state.currentProject.settings?.suggested_titles?.[0]?.title || state.currentProject.name || '';
  const hasPoster = poster.image_url && poster.status === 'completed';
  const posterUrl = hasPoster ? (poster.image_url + '?t=' + Date.now()) : '';

  // 分镜图网格
  const selType = poster.source_frame?.frame_type || 'head';
  const frameGridHTML = frameList.length > 0 ? `
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:6px;margin:8px 0;max-height:200px;overflow-y:auto;">
      ${frameList.map(f => {
        const isSel = poster.source_frame?.chapter === f.chapter && poster.source_frame?.clip_index === f.clip_index && (poster.source_frame?.frame_type || 'head') === f.frame_type;
        const typeLabel = f.frame_type === 'tail' ? '尾' : '首';
        return `
        <div class="poster-frame-thumb"
             data-ch="${f.chapter}" data-clip="${f.clip_index}" data-type="${f.frame_type}"
             onclick="selectPosterFrame(${f.chapter}, ${f.clip_index}, '${f.frame_type}')"
             ondblclick="event.stopPropagation();openPosterViewer('${f.image_url}')"
             title="${f.label} — 单击选择，双击放大"
             style="position:relative;aspect-ratio:16/9;border-radius:6px;overflow:hidden;cursor:pointer;border:2px solid ${isSel ? 'var(--accent)' : 'transparent'};transition:border-color 0.2s;">
          <img src="${f.image_url}" style="width:100%;height:100%;object-fit:cover;" loading="lazy">
          <span style="position:absolute;bottom:2px;right:3px;background:rgba(0,0,0,0.65);color:#fff;font-size:10px;padding:1px 4px;border-radius:3px;pointer-events:none;">${typeLabel}</span>
        </div>`;
      }).join('')}
    </div>
  ` : '<p style="color:var(--text-secondary);font-size:13px;">暂无分镜图，请先生成分镜图</p>';

  section.innerHTML = `
    <p style="font-size:13px;color:var(--text-secondary);margin-bottom:8px;">选择分镜图作为海报基础，AI会在此基础上添加海报设计元素和剧名。</p>

    <div class="form-row">
      <div class="form-group" style="flex:1;">
        <label>剧名</label>
        <input type="text" id="poster-title" class="input" value="${esc(defaultTitle)}" placeholder="输入剧名">
      </div>
    </div>

    <label style="font-size:13px;color:var(--text-secondary);">选择分镜图</label>
    <div id="poster-frame-grid">${frameGridHTML}</div>
    <input type="hidden" id="poster-sel-ch" value="${poster.source_frame?.chapter ?? 0}">
    <input type="hidden" id="poster-sel-clip" value="${poster.source_frame?.clip_index ?? 0}">
    <input type="hidden" id="poster-sel-type" value="${poster.source_frame?.frame_type || 'head'}">

    <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;">
      <button class="btn btn-primary" onclick="generatePoster()" id="poster-gen-btn">生成海报</button>
      <label class="btn btn-secondary" style="cursor:pointer;margin:0;">
        本地上传 <input type="file" accept="image/*" style="display:none;" onchange="uploadPoster(this)">
      </label>
      ${hasPoster ? `
        <button class="btn btn-secondary" onclick="modifyPoster()">AI修改</button>
        <button class="btn btn-secondary" onclick="exportPoster()">导出图片</button>
      ` : ''}
    </div>

    ${hasPoster ? `
      <div style="margin-top:12px;">
        <img src="${posterUrl}" style="max-width:100%;max-height:400px;border-radius:8px;cursor:pointer;" onclick="openPosterViewer('${posterUrl}')" title="点击放大">
      </div>
    ` : ''}
  `;
}

function selectPosterFrame(chIdx, clipIdx, frameType) {
  document.getElementById('poster-sel-ch').value = chIdx;
  document.getElementById('poster-sel-clip').value = clipIdx;
  document.getElementById('poster-sel-type').value = frameType || 'head';
  // Update visual selection
  document.querySelectorAll('.poster-frame-thumb').forEach(el => {
    const match = parseInt(el.dataset.ch) === chIdx && parseInt(el.dataset.clip) === clipIdx && (el.dataset.type || 'head') === (frameType || 'head');
    el.style.borderColor = match ? 'var(--accent)' : 'transparent';
  });
}

async function generatePoster() {
  if (!state.currentProject) return;
  const title = document.getElementById('poster-title')?.value?.trim();
  if (!title) { showNotification('请输入剧名', 'warning'); return; }

  const chIdx = parseInt(document.getElementById('poster-sel-ch')?.value || '0');
  const clipIdx = parseInt(document.getElementById('poster-sel-clip')?.value || '0');
  const frameType = document.getElementById('poster-sel-type')?.value || 'head';
  const btn = document.getElementById('poster-gen-btn');
  if (btn) btn.disabled = true;

  toggleSynapseLoading(true, 'SYNAPSE 海报引擎', '正在生成海报...');
  try {
    const result = await api(`/api/projects/${state.currentProject.id}/poster/generate`, 'POST', {
      title, chapter: chIdx, clip_index: clipIdx, frame_type: frameType
    }, 300000);
    if (result.success) {
      state.currentProject.poster = {
        image_path: result.image_path,
        image_url: result.image_url,
        title: title,
        source_frame: { chapter: chIdx, clip_index: clipIdx, frame_type: frameType },
        status: 'completed'
      };
      renderPosterSection();
      showNotification('海报生成成功');
    }
  } catch (e) {
    showNotification('生成失败: ' + (e.message || e), 'error');
  }
  toggleSynapseLoading(false);
  if (btn) btn.disabled = false;
}

async function uploadPoster(input) {
  const file = input.files[0];
  if (!file) return;
  const title = document.getElementById('poster-title')?.value?.trim() || '';

  toggleSynapseLoading(true, 'SYNAPSE 海报引擎', '正在上传海报...');
  try {
    const formData = new FormData();
    formData.append('image', file);
    formData.append('title', title);
    const result = await api(`/api/projects/${state.currentProject.id}/poster/upload`, 'POST', formData);
    if (result.success) {
      state.currentProject.poster = {
        ...state.currentProject.poster,
        image_path: result.image_path,
        image_url: result.image_url,
        status: 'completed'
      };
      renderPosterSection();
      showNotification('海报上传成功');
    }
  } catch (e) {
    showNotification('上传失败: ' + (e.message || e), 'error');
  }
  toggleSynapseLoading(false);
  input.value = '';
}

function modifyPoster() {
  showPromptModal('AI修改海报', async (instruction) => {
    toggleSynapseLoading(true, 'SYNAPSE 海报引擎', '正在修改海报...');
    try {
      const result = await api(`/api/projects/${state.currentProject.id}/poster/modify`, 'POST', { instruction }, 300000);
      if (result.success) {
        state.currentProject.poster = {
          ...state.currentProject.poster,
          image_path: result.image_path,
          image_url: result.image_url,
          status: 'completed'
        };
        renderPosterSection();
        showNotification('海报修改成功');
      }
    } catch (e) {
      showNotification('修改失败: ' + (e.message || e), 'error');
    }
    toggleSynapseLoading(false);
  });
}

async function exportPoster() {
  try {
    // 1. 获取海报路径信息
    const info = await api(`/api/projects/${state.currentProject.id}/poster/save-as`);
    if (!info.success) { showNotification('海报不存在', 'error'); return; }

    // 2. 调用pywebview原生保存对话框
    if (window.pywebview && window.pywebview.api && window.pywebview.api.export_poster_to_path) {
      const result = await window.pywebview.api.export_poster_to_path(info.source_path, info.default_name);
      if (result.cancelled) return;
      if (result.success) {
        showNotification('海报已保存: ' + result.path);
      } else {
        showNotification('保存失败: ' + result.error, 'error');
      }
    } else {
      // 非pywebview环境，走后端下载
      window.open(`/api/projects/${state.currentProject.id}/poster/export`, '_blank');
    }
  } catch (e) {
    showNotification('导出失败: ' + (e.message || e), 'error');
  }
}

function openPosterViewer(imageUrl) {
  let overlay = document.getElementById('poster-viewer-overlay');
  if (overlay) overlay.remove();
  overlay = document.createElement('div');
  overlay.id = 'poster-viewer-overlay';
  overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.92);z-index:9999;display:flex;align-items:center;justify-content:center;cursor:pointer;';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  overlay.innerHTML = `
    <img src="${imageUrl}" style="max-width:90%;max-height:90%;border-radius:8px;cursor:default;" onclick="event.stopPropagation();">
    <div style="position:absolute;top:20px;right:30px;color:white;font-size:28px;cursor:pointer;" onclick="document.getElementById('poster-viewer-overlay').remove();">&#x2715;</div>
  `;
  document.body.appendChild(overlay);
}

function renderComposePreview(videoPath, chIdx) {
  const area = document.getElementById('compose-preview-area');
  if (!area) return;

  // Convert Windows path to URL
  let videoUrl = videoPath.replace(/\\/g, '/');
  if (videoUrl.match(/^[A-Z]:/i)) {
    videoUrl = '/api/file?path=' + encodeURIComponent(videoPath);
  }

  const label = chIdx >= 0 ? `第${chIdx + 1}集预览` : '完整视频预览';

  area.innerHTML = `
    <div class="compose-preview-container">
      <div class="compose-preview-header">
        <span class="compose-preview-title">${label}</span>
        <button class="btn btn-secondary btn-sm" onclick="openVideoViewer('${esc(videoUrl)}')">全屏播放</button>
      </div>
      <video src="${videoUrl}" controls style="width:100%;max-height:400px;"></video>
    </div>
  `;
}

//
// Export Step
//

let _exportPath = '';

async function renderExportStep() {
  const container = document.getElementById('export-content');
  if (!container || !state.currentProject) return;

  // 获取合成状态
  let chapters = [];
  try {
    const resp = await api(`/api/projects/${state.currentProject.id}/compose/status`, 'GET');
    chapters = (resp.chapters || []).filter(s => s.has_composed);
  } catch (e) {}

  container.innerHTML = `
    <div class="glass-card">
      <h3 style="margin:0 0 16px;font-size:16px;">已合成的视频</h3>
      <div id="export-chapter-list">
        ${chapters.length === 0 ? '<div style="color:var(--text-secondary);padding:12px;">暂无已合成的视频，请先到合成步骤完成合成</div>' :
          chapters.map(ch => `
            <div class="export-chapter-item" style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-radius:8px;margin-bottom:6px;background:rgba(255,255,255,0.03);">
              <span>第${ch.index + 1}集</span>
              <button class="btn btn-secondary btn-sm" onclick="exportVideo('/api/projects/${state.currentProject.id}/compose/${ch.index}/save-as')">保存</button>
            </div>
          `).join('')}
      </div>

      <div id="export-progress-area"></div>

      <div class="compose-action-bar">
        ${chapters.length > 0 ? '<button class="btn btn-primary btn-lg" onclick="doExportVideo()">批量导出全部</button>' : ''}
        ${chapters.length === 0 ? '<button class="btn btn-secondary btn-lg" onclick="showStep(8)">去合成</button>' : ''}
      </div>
    </div>

    <div id="export-result-area"></div>
  `;
}

async function doExportVideo() {
  if (!state.currentProject) return;

  const progressArea = document.getElementById('export-progress-area');
  if (progressArea) {
    progressArea.innerHTML = `<div class="compose-progress-container">
      <div class="compose-progress-text">正在批量导出，请选择保存文件夹...</div>
    </div>`;
  }

  try {
    // 尝试用pywebview原生保存对话框选一个默认路径来提取文件夹
    let targetFolder = '';
    if (window.pywebview && window.pywebview.api && window.pywebview.api.save_file_dialog) {
      const outputDir = `D:\\Phineas\\Synapse\\projects\\${state.currentProject.id}\\output`;
      const result = await window.pywebview.api.save_file_dialog(outputDir, '选择文件夹位置（取消不影响）');
      // 从用户选的文件路径提取文件夹
      if (result) {
        targetFolder = result.replace(/[\\/][^\\/]*$/, '');
      }
    }

    // 如果没选到文件夹，用默认输出目录
    if (!targetFolder) {
      targetFolder = '';
    }

    if (progressArea) {
      const text = progressArea.querySelector('.compose-progress-text');
      if (text) text.textContent = '正在导出全部视频...';
    }

    const result = await api(`/api/projects/${state.currentProject.id}/export/batch`, 'POST', { folder: targetFolder }, 600000);

    if (progressArea) {
      progressArea.innerHTML = `<div class="compose-progress-container">
        <div class="compose-progress-text" style="color:#22c55e;">导出完成! ${result.exported} 个视频已保存</div>
      </div>`;
    }

    showNotification(`导出完成: ${result.exported} 个视频`);

    const resultArea = document.getElementById('export-result-area');
    if (resultArea && result.exported_paths && result.exported_paths.length) {
      const folder = result.exported_paths[0].replace(/[\\/][^\\/]*$/, '');
      resultArea.innerHTML = `
        <div class="export-result">
          <h3 style="margin:0 0 8px;font-size:16px;">导出完成</h3>
          <div class="export-result-path">共 ${result.exported} 个视频已保存到: ${esc(folder)}</div>
          <div class="export-result-actions">
            <button class="btn btn-secondary" onclick="openExportFolder('${esc(folder)}')">打开文件夹</button>
          </div>
        </div>
      `;
    }
  } catch (e) {
    showNotification('导出失败: ' + (e.message || e), 'error');
    if (progressArea) progressArea.innerHTML = '';
  }
}

async function openExportFolder(folderPath) {
  try {
    await api('/api/open-folder', 'POST', { path: folderPath });
  } catch (e) {
    showNotification('打开文件夹失败: ' + (e.message || e), 'error');
  }
}


// 
//  AI 
// 

async function sendChat() {
  const input = document.getElementById('chat-input');
  const msg = input?.value?.trim();
  if (!msg) return;
  input.value = '';
  // Hide chat hint on first message
  const hint = document.getElementById('chat-hint');
  if (hint && !hint.classList.contains('hidden')) hint.classList.add('hidden');

  const pid = state.currentProject?.id || '_global';
  if (!state.projectChats[pid]) state.projectChats[pid] = [];

  const container = document.getElementById('chat-messages');
  if (container) {
    container.innerHTML += `<div class="chat-msg user-msg"><p>${esc(msg)}</p></div>`;
    container.scrollTop = container.scrollHeight;
  }

  try {
    const result = await api(`/api/chat`, 'POST', {
      message: msg,
      project_id: state.currentProject?.id || null,
      history: state.projectChats[pid].slice(-50),
    }, 300000);
    const reply = result?.response || result?.reply || '';
    state.projectChats[pid].push({ role: 'user', content: msg });
    state.projectChats[pid].push({ role: 'assistant', content: reply });
    if (container) {
      let html = '';
      // 显示回复文本（非空时才显示气泡）
      if (reply.trim()) {
        html += `<div class="chat-msg ai-msg"><p>${esc(reply)}</p></div>`;
      }
      // 画风卡片
      if (result.style_generated) {
        const sg = result.style_generated;
        const cardId = 'style-card-' + Date.now();
        html += `<div class="chat-msg ai-msg"><div class="chat-style-card" id="${cardId}">
          <div class="chat-style-card-name">${esc(sg.name)} <span class="chat-style-card-name-en">(${esc(sg.name_en)})</span></div>
          <div class="chat-style-card-prompt">${esc(sg.prompt)}</div>
          <div class="chat-style-card-meta">${esc(sg.tone || '')} / ${esc(sg.lighting || '')}</div>
          <button class="btn btn-primary btn-sm chat-style-save-btn" onclick="saveChatStyle('${cardId}', '${esc(sg.id)}')">保存画风</button>
        </div></div>`;
      }
      container.innerHTML += html;
      container.scrollTop = container.scrollHeight;
    }
    // Persist to backend (await to ensure save completes before window close)
    if (pid !== '_global') {
      try {
        await api(`/api/projects/${pid}/chat`, 'POST', {
          messages: [{ role: 'user', content: msg }, { role: 'assistant', content: reply }]
        });
      } catch (saveErr) {
        console.warn('Chat save failed, queuing for flush:', saveErr);
        if (!window._pendingChatFlush) window._pendingChatFlush = [];
        window._pendingChatFlush.push({ pid, messages: [{ role: 'user', content: msg }, { role: 'assistant', content: reply }] });
      }
    }
  } catch (e) {
    if (container) {
      container.innerHTML += `<div class="chat-msg ai-msg"><p style="color:var(--error);">${esc(e.message)}</p></div>`;
    }
  }
}

// AI
async function saveChatStyle(cardId, styleId) {
  const cardEl = document.getElementById(cardId);
  if (!cardEl) return;
  // styles
  try {
    const res = await fetch('/api/styles');
    const data = await res.json();
    const all = [...(data.presets || []), ...(data.custom || [])];
    const style = all.find(s => s.id === styleId);
    if (!style) {
      // 
      const nameEl = cardEl.querySelector('.chat-style-card-name');
      const promptEl = cardEl.querySelector('.chat-style-card-prompt');
      const metaEl = cardEl.querySelector('.chat-style-card-meta');
      const nameText = nameEl?.childNodes[0]?.textContent?.trim() || styleId;
      const nameEnText = nameEl?.querySelector('.chat-style-card-name-en')?.textContent?.replace(/[()]/g,'').trim() || '';
      const promptText = promptEl?.textContent?.trim() || '';
      const metaParts = (metaEl?.textContent || '').split('/');
      const styleObj = {
        id: styleId,
        name: nameText,
        name_en: nameEnText,
        prompt: promptText,
        tone: metaParts[0]?.trim() || 'neutral',
        lighting: metaParts[1]?.trim() || 'natural',
      };
      await fetch('/api/styles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(styleObj)
      });
    }
    await loadStyles();
    // 
    const btn = cardEl.querySelector('.chat-style-save-btn');
    if (btn) {
      btn.textContent = '已保存';
      btn.disabled = true;
      btn.classList.add('saved');
    }
    showNotification('画风已保存', 'success');
  } catch (e) {
    showNotification('保存画风失败: ' + e.message, 'error');
  }
}


// DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
  // Flow: boot splash -> license check -> (if needed) activation overlay -> disclaimer -> effects
  playBootSplash().then(() => {
    return checkLicense();
  }).then(valid => {
    if (!valid) return showLicenseOverlay();
  }).then(() => {
    return showDisclaimer();
  }).then(() => {
    setTimeout(initAllEffectsV2, 50);
  });

  // 
  const origNavigate = window.navigateTo;
  if (typeof origNavigate === 'function') {
    window.navigateTo = function(page) {
      origNavigate(page);
      setTimeout(() => {
        initCardEffects();
        initButtonRipple();
      }, 200);
    };
  }

  // Titlebar buttons (frameless window)
  setTimeout(() => {
    const btnMin = document.getElementById('btn-minimize');
    const btnClose = document.getElementById('btn-close');
    if (btnMin) btnMin.onclick = () => pywebview.api.minimize();
    if (btnClose) btnClose.onclick = () => pywebview.api.close();

    // Window drag removed — start_move() is a no-op, window is fixed

    // Sync .maximized class for CSS styling (cursor, border changes etc.)
    function checkWindowMaximized() {
      if (window.pywebview && window.pywebview.api && typeof pywebview.api.is_maximized === 'function') {
        pywebview.api.is_maximized().then(function(isMax) {
          var html = document.documentElement;
          html.classList.toggle('win-maximized', isMax);
        });
      }
    }
    checkWindowMaximized();
    window.addEventListener('resize', checkWindowMaximized);
  }, 500);

  // Init custom combobox components
  loadStyles();
  loadStyleModifiers();
  initAllComboboxes();

  // Flush pending chat messages before window close (sendBeacon guarantees delivery)
  window.addEventListener('beforeunload', function() {
    if (!window._pendingChatFlush || window._pendingChatFlush.length === 0) return;
    const grouped = {};
    window._pendingChatFlush.forEach(item => {
      if (!grouped[item.pid]) grouped[item.pid] = [];
      grouped[item.pid].push(...item.messages);
    });
    for (const [pid, msgs] of Object.entries(grouped)) {
      const url = API + '/api/projects/' + pid + '/chat';
      const payload = JSON.stringify({ messages: msgs });
      navigator.sendBeacon(url, new Blob([payload], { type: 'application/json' }));
    }
    window._pendingChatFlush = [];
  });
});

// ===  ===
let allStyles = { presets: [], custom: [] };
let allModifiers = {};

async function loadStyles() {
  try {
    const res = await fetch('/api/styles');
    allStyles = await res.json();
    renderStyleOptions();
  } catch (e) { console.warn('Failed to load styles:', e); }
}

function renderStyleOptions() {
  const presetList = document.getElementById('preset-styles-list');
  const customList = document.getElementById('custom-styles-list');
  const customEmpty = document.getElementById('custom-styles-empty');
  if (!presetList || !customList) return;

  // 
  presetList.innerHTML = allStyles.presets.map(s =>
    '<div class="combobox-option" data-value="' + s.id + '">' + s.name + '</div>'
  ).join('');

  // 
  if (allStyles.custom.length === 0) {
    customList.innerHTML = '<div class="combobox-empty-hint" id="custom-styles-empty"></div>';
  } else {
    customList.innerHTML = allStyles.custom.map(s =>
      '<div class="combobox-option combobox-custom-item" data-value="' + s.id + '">' +
        '<span>' + s.name + '</span>' +
        '<span class="delete-style" data-id="' + s.id + '" onclick="event.stopPropagation();deleteCustomStyle(\'' + s.id + '\')">&#x2715;</span>' +
      '</div>'
    ).join('');
  }

  // art-style dropdown
  const dropdown = document.getElementById('dropdown-art-style');
  if (dropdown) {
    dropdown.querySelectorAll('.combobox-option').forEach(option => {
      option.addEventListener('click', () => {
        const val = option.getAttribute('data-value');
        if (val === undefined) return;
        const hiddenInput = document.getElementById('art-style');
        const displayInput = document.getElementById('art-style-display');
        if (hiddenInput) hiddenInput.value = val;
        if (displayInput) displayInput.value = option.querySelector('span') ? option.querySelector('span').textContent.trim() : option.textContent.trim();
        const trigger = document.getElementById('combobox-trigger-art-style');
        if (trigger) trigger.classList.toggle('has-value', !!val);
        // dropdown
        dropdown.classList.remove('show');
        if (trigger) trigger.classList.remove('open');
      });
    });
    // AI
    const aiBtn = document.getElementById('btn-ai-generate-style');
    if (aiBtn) {
      aiBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        dropdown.classList.remove('show');
        showAIGenerateModal();
      });
    }
  }
}

async function deleteCustomStyle(styleId) {
  try {
    await fetch('/api/styles/' + styleId, { method: 'DELETE' });
    await loadStyles();
    showNotification('画风已删除', 'success');
  } catch (e) { showNotification('删除画风失败: ' + e.message, 'error'); }
}

async function loadStyleModifiers() {
  try {
    const res = await fetch('/api/styles/modifiers');
    allModifiers = await res.json();
    renderModifierOptions('tone', allModifiers.tone || []);
    renderModifierOptions('lighting', allModifiers.lighting || []);
    renderModifierOptions('texture', allModifiers.texture || []);
  } catch (e) { console.warn('Failed to load style modifiers:', e); }
}

function renderModifierOptions(type, options) {
  const container = document.getElementById('style-' + type + '-options');
  if (!container) return;
  container.innerHTML = options.map(m =>
    '<div class="combobox-option" data-value="' + m.id + '">' + m.name + '</div>'
  ).join('');

  // dropdownclickinitAllComboboxes
  const dropdown = document.getElementById('dropdown-style-' + type);
  if (dropdown) {
    dropdown.querySelectorAll('.combobox-option').forEach(option => {
      option.addEventListener('click', () => {
        const val = option.getAttribute('data-value');
        const hiddenInput = document.getElementById('style-' + type);
        const displayInput = document.getElementById('style-' + type + '-display');
        const trigger = document.getElementById('combobox-trigger-style-' + type);
        if (hiddenInput) hiddenInput.value = val;
        if (displayInput) displayInput.value = option.textContent.trim();
        if (trigger) trigger.classList.toggle('has-value', !!val);
        dropdown.classList.remove('show');
      });
    });
  }
}

// AI
function showAIGenerateModal() {
  const existing = document.querySelector('.ai-style-modal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.className = 'ai-style-modal';
  modal.innerHTML =
    '<div class="modal-content">' +
      '<h3>AI生成画风</h3>' +
      '<textarea id="ai-style-desc" placeholder="描述你想要的画风，例如：中国古代水墨风、赛博朋克霓虹风、吉卜力清新风..."></textarea>' +
      '<div id="ai-style-result-container"></div>' +
      '<div class="modal-actions">' +
        '<button class="btn btn-secondary" onclick="this.closest(\'.ai-style-modal\').remove()">取消</button>' +
        '<button class="btn btn-primary" id="btn-ai-style-generate">生成画风</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(modal);

  modal.querySelector('#btn-ai-style-generate').addEventListener('click', async () => {
    const desc = modal.querySelector('#ai-style-desc').value.trim();
    if (!desc) { showNotification('请填写必填项', 'error'); return; }
    const btn = modal.querySelector('#btn-ai-style-generate');
    btn.disabled = true;
    btn.textContent = '生成中...';
    try {
      const res = await fetch('/api/styles/ai-generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: desc })
      });
      const data = await res.json();
      if (data.success && data.style) {
        const container = modal.querySelector('#ai-style-result-container');
        container.innerHTML =
          '<div class="ai-style-result">' +
            '<div class="result-name">' + data.style.name + ' (' + data.style.name_en + ')</div>' +
            '<div class="result-prompt">' + data.style.prompt + '</div>' +
            '<div style="margin-top:8px;font-size:12px;color:var(--text-muted)">色调: ' + data.style.tone + ' | 光影: ' + data.style.lighting + '</div>' +
          '</div>' +
          '<div class="modal-actions" style="margin-top:12px">' +
            '<button class="btn btn-secondary" id="btn-ai-style-regenerate">重新生成</button>' +
            '<button class="btn btn-primary" id="btn-ai-style-save">保存画风</button>' +
          '</div>';
        // 
        container.querySelector('#btn-ai-style-regenerate').addEventListener('click', () => {
          container.innerHTML = '';
          btn.disabled = false;
          btn.textContent = '重新生成';
          btn.click();
        });
        // 
        container.querySelector('#btn-ai-style-save').addEventListener('click', async () => {
          try {
            await fetch('/api/styles', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(data.style)
            });
            await loadStyles();
            modal.remove();
            showNotification('画风已创建: ' + data.style.name, 'success');
          } catch (e) { showNotification('创建画风失败: ' + e.message, 'error'); }
        });
      } else {
        showNotification(data.error || 'AI生成画风失败', 'error');
      }
    } catch (e) {
      showNotification('AI生成画风失败: ' + e.message, 'error');
    }
    btn.disabled = false;
    btn.textContent = 'AI生成画风';
  });
}

// === Custom Combobox Component ===
function initAllComboboxes() {
  document.querySelectorAll('.combobox-trigger').forEach(trigger => {
    try {
    const fieldId = trigger.getAttribute('data-combobox');
    const dropdown = document.getElementById('dropdown-' + fieldId);
    if (!dropdown) return;
    // move to body so parent overflow can't clip it
    document.body.appendChild(dropdown);
    const displayInput = trigger.querySelector('input.input');
    const hiddenInput = trigger.querySelector('input[type="hidden"]');
    const isText = !!hiddenInput;
    let blurTimeout = null;
    if (isText) { trigger.id = 'combobox-trigger-' + fieldId; }

    // mousedownclickmousedown→focus→click
    let isMouseAction = false;
    trigger.addEventListener('mousedown', (e) => {
      if (e.target.closest('.combobox-dropdown')) return;
      isMouseAction = true;
      if (dropdown.classList.contains('show')) { hideDropdown(); }
      else { showDropdown(); displayInput.focus(); }
    });
    displayInput.addEventListener('focus', () => {
      if (!isMouseAction) { showDropdown(); } // Tab
      isMouseAction = false;
    });

    displayInput.addEventListener('blur', () => {
      blurTimeout = setTimeout(() => {
        hideDropdown();
        if (isText) {
          const sel = dropdown.querySelector('.combobox-option[data-value="' + hiddenInput.value + '"]');
          if (sel) {
            const nameSpan = sel.querySelector('span');
            displayInput.value = nameSpan ? nameSpan.textContent.trim() : sel.textContent.trim();
          }
          else { displayInput.value = ''; }
          trigger.classList.toggle('has-value', !!hiddenInput.value);
        }
      }, 200);
    });

    dropdown.addEventListener('mousedown', (e) => { e.preventDefault(); });

    dropdown.querySelectorAll('.combobox-option').forEach(option => {
      option.addEventListener('click', () => {
        const val = option.getAttribute('data-value');
        if (isText) {
          hiddenInput.value = val;
          displayInput.value = option.textContent.trim();
          trigger.classList.toggle('has-value', !!val);
        } else {
          displayInput.value = val;
        }
        hideDropdown();
        displayInput.dispatchEvent(new Event('change', { bubbles: true }));
        displayInput.dispatchEvent(new Event('input', { bubbles: true }));
      });
    });

    if (!isText) {
      displayInput.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          if (!dropdown.classList.contains('show')) { showDropdown(); return; }
          const options = [...dropdown.querySelectorAll('.combobox-option')];
          let ci = options.findIndex(o => o.classList.contains('active'));
          options.forEach(o => o.classList.remove('active'));
          ci = e.key === 'ArrowDown' ? (ci + 1) % options.length : (ci - 1 + options.length) % options.length;
          options[ci].classList.add('active');
          options[ci].scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'Enter' && dropdown.classList.contains('show')) {
          e.preventDefault();
          const active = dropdown.querySelector('.combobox-option.active');
          if (active) { active.click(); }
        } else if (e.key === 'Escape') { hideDropdown(); }
      });
    } else {
      displayInput.setAttribute('tabindex', '0');
      displayInput.addEventListener('keydown', (e) => {
        const options = [...dropdown.querySelectorAll('.combobox-option')];
        let ci = options.findIndex(o => o.classList.contains('active'));
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          if (!dropdown.classList.contains('show')) { showDropdown(); return; }
          if (ci >= 0) options[ci].classList.remove('active');
          ci = (ci < 0) ? 0 : (ci + 1) % options.length;
          options[ci].classList.add('active');
          options[ci].scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          if (!dropdown.classList.contains('show')) return;
          if (ci >= 0) options[ci].classList.remove('active');
          ci = (ci <= 0) ? options.length - 1 : ci - 1;
          options[ci].classList.add('active');
          options[ci].scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'Enter') {
          e.preventDefault();
          if (dropdown.classList.contains('show')) {
            const active = dropdown.querySelector('.combobox-option.active');
            if (active) active.click();
          } else { showDropdown(); }
        } else if (e.key === 'Escape') { hideDropdown(); }
      });
    }

    function showDropdown() {
      if (blurTimeout) { clearTimeout(blurTimeout); blurTimeout = null; }
      document.querySelectorAll('.combobox-dropdown.show').forEach(d => {
        if (d !== dropdown) {
          d.classList.remove('show');
          const did = d.id.replace('dropdown-', '');
          const trig = document.querySelector('.combobox-trigger[data-combobox="' + did + '"]');
          if (trig) trig.classList.remove('open');
        }
      });
      // viewport coords for position:fixed dropdown
      const rect = trigger.getBoundingClientRect();
      dropdown.style.top = (rect.bottom + 4) + 'px';
      dropdown.style.left = rect.left + 'px';
      dropdown.style.width = rect.width + 'px';
      dropdown.classList.add('show');
      trigger.classList.add('open');
      const current = isText ? hiddenInput.value : displayInput.value;
      dropdown.querySelectorAll('.combobox-option').forEach(o => {
        o.classList.toggle('active', o.getAttribute('data-value') === current);
      });
    }
    function hideDropdown() {
      dropdown.classList.remove('show');
      trigger.classList.remove('open');
      dropdown.querySelectorAll('.combobox-option').forEach(o => o.classList.remove('active'));
    }
    } catch(e) { console.warn('Combobox init failed:', fieldId, e); }
  });
}

// ── Reposition open combobox dropdowns on scroll ──
document.addEventListener('scroll', function() {
  document.querySelectorAll('.combobox-dropdown.show').forEach(d => {
    const did = d.id.replace('dropdown-', '');
    const trig = document.querySelector('.combobox-trigger[data-combobox="' + did + '"]');
    if (trig) {
      const rect = trig.getBoundingClientRect();
      d.style.top = (rect.bottom + 4) + 'px';
      d.style.left = rect.left + 'px';
      d.style.width = rect.width + 'px';
    }
  });
}, true);

// ── Image Lightbox ──
let _lightboxScale = 1;
function openLightbox(src) {
  const lb = document.getElementById('image-lightbox');
  const img = document.getElementById('lightbox-img');
  if (!lb || !img) return;
  img.src = src;
  _lightboxScale = 1;
  img.style.transform = 'scale(1)';
  lb.style.display = 'flex';
  requestAnimationFrame(() => lb.classList.add('show'));
}
function closeLightbox(e) {
  if (e && e.target.tagName === 'IMG') return;
  const lb = document.getElementById('image-lightbox');
  if (lb) {
    lb.classList.remove('show');
    setTimeout(() => { lb.style.display = 'none'; }, 250);
  }
}
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    const lb = document.getElementById('image-lightbox');
    if (lb && lb.classList.contains('show')) closeLightbox(e);
  }
});
document.addEventListener('wheel', function(e) {
  const lb = document.getElementById('image-lightbox');
  if (!lb || !lb.classList.contains('show')) return;
  const img = document.getElementById('lightbox-img');
  if (!img) return;
  e.preventDefault();
  _lightboxScale += e.deltaY > 0 ? -0.1 : 0.1;
  _lightboxScale = Math.max(0.3, Math.min(5, _lightboxScale));
  img.style.transform = 'scale(' + _lightboxScale + ')';
}, { passive: false });
