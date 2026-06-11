/**
 * script.js – AI SQL Assistant
 * Frontend logic: API calls, SQL highlighting, history, validation, toasts.
 */

'use strict';

// ─── Constants ───────────────────────────────────────────────────────────────
const API_URL      = '/generate';
const MAX_HISTORY  = 8;
const CHAR_LIMIT   = 1000;

const SQL_KEYWORDS = [
  'SELECT','FROM','WHERE','AND','OR','NOT','IN','IS','NULL','LIKE',
  'ORDER','BY','GROUP','HAVING','LIMIT','OFFSET','JOIN','LEFT','RIGHT',
  'INNER','OUTER','FULL','CROSS','ON','AS','DISTINCT','INSERT','INTO',
  'VALUES','UPDATE','SET','DELETE','CREATE','TABLE','DROP','ALTER','ADD',
  'COLUMN','PRIMARY','KEY','FOREIGN','REFERENCES','INDEX','VIEW',
  'UNION','ALL','CASE','WHEN','THEN','ELSE','END','EXISTS','BETWEEN',
  'ASC','DESC','WITH','RETURNING','YEAR','MONTH','DATE','CURRENT_DATE',
  'CURRENT_TIMESTAMP',
];

const SQL_FUNCTIONS = [
  'COUNT','SUM','AVG','MAX','MIN','COALESCE','IFNULL','NULLIF',
  'ROUND','FLOOR','CEIL','ABS','LENGTH','UPPER','LOWER','TRIM',
  'SUBSTRING','CONCAT','NOW','CURDATE','DATEADD','DATEDIFF',
  'CAST','CONVERT','ISNULL',
];

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const queryInput       = document.getElementById('queryInput');
const charCount        = document.getElementById('charCount');
const generateBtn      = document.getElementById('generateBtn');
const clearBtn         = document.getElementById('clearBtn');
const btnIcon          = document.getElementById('btnIcon');
const btnText          = document.getElementById('btnText');
const errorBanner      = document.getElementById('errorBanner');
const errorText        = document.getElementById('errorText');
const outputPlaceholder= document.getElementById('outputPlaceholder');
const sqlResultWrapper = document.getElementById('sqlResultWrapper');
const sqlOutput        = document.getElementById('sqlOutput');
const copyBtn          = document.getElementById('copyBtn');
const methodBadge      = document.getElementById('methodBadge');
const validationPanel  = document.getElementById('validationPanel');
const historyList      = document.getElementById('historyList');
const historyEmpty     = document.getElementById('historyEmpty');
const toastContainer   = document.getElementById('toastContainer');

// ─── State ────────────────────────────────────────────────────────────────────
let history = [];
let lastSQL = '';

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Load history from localStorage
  try {
    const stored = JSON.parse(localStorage.getItem('sqlHistory') || '[]');
    if (Array.isArray(stored)) { history = stored; renderHistory(); }
  } catch { /* ignore */ }

  attachEventListeners();
  queryInput.focus();
});

// ─── Event listeners ──────────────────────────────────────────────────────────
function attachEventListeners() {
  // Character counter
  queryInput.addEventListener('input', handleInputChange);

  // Generate on Ctrl/Cmd + Enter
  queryInput.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') generateSQL();
  });

  generateBtn.addEventListener('click', generateSQL);
  clearBtn.addEventListener('click', clearAll);
  copyBtn.addEventListener('click', copySQL);

  // Example chips
  document.querySelectorAll('.example-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      queryInput.value = chip.dataset.query;
      handleInputChange();
      queryInput.focus();
    });
  });
}

// ─── Input handling ───────────────────────────────────────────────────────────
function handleInputChange() {
  const len = queryInput.value.length;
  charCount.textContent = `${len} / ${CHAR_LIMIT}`;

  charCount.classList.toggle('warning', len > 800);
  charCount.classList.toggle('danger',  len > 950);
  hideError();
}

// ─── Core: Generate SQL ───────────────────────────────────────────────────────
async function generateSQL() {
  const query = queryInput.value.trim();

  if (!query) {
    showError('Please enter a query before generating SQL.');
    queryInput.focus();
    return;
  }

  setLoadingState(true);
  hideError();
  hideResult();

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });

    const data = await response.json();

    if (!response.ok || data.error) {
      throw new Error(data.error || `Server error (${response.status})`);
    }

    lastSQL = data.sql || '';
    displayResult(lastSQL, data.method || 'rule-based');
    addToHistory(query, lastSQL);
    showToast('✅ SQL generated successfully!', 'success');

  } catch (err) {
    showError(err.message || 'Failed to generate SQL. Please try again.');
    showToast('❌ Generation failed.', 'error');
  } finally {
    setLoadingState(false);
  }
}

// ─── UI State helpers ─────────────────────────────────────────────────────────
function setLoadingState(loading) {
  if (loading) {
    generateBtn.classList.add('btn-loading');
    generateBtn.disabled = true;
    btnIcon.innerHTML = '<div class="spinner"></div>';
    btnText.textContent = 'Generating…';
  } else {
    generateBtn.classList.remove('btn-loading');
    generateBtn.disabled = false;
    btnIcon.textContent = '⚡';
    btnText.textContent = 'Generate SQL';
  }
}

function showError(msg) {
  errorText.textContent = msg;
  errorBanner.classList.add('visible');
}

function hideError() {
  errorBanner.classList.remove('visible');
}

function hideResult() {
  sqlResultWrapper.classList.remove('visible');
  outputPlaceholder.style.display = 'flex';
  validationPanel.classList.remove('visible');
  methodBadge.classList.remove('visible', 'openai', 'rule');
}

// ─── Display result ───────────────────────────────────────────────────────────
function displayResult(sql, method) {
  // Syntax-highlight and render
  sqlOutput.innerHTML = highlightSQL(sql);

  // Show wrapper, hide placeholder
  outputPlaceholder.style.display = 'none';
  sqlResultWrapper.classList.add('visible');

  // Method badge
  methodBadge.classList.add('visible');
  if (method === 'openai') {
    methodBadge.textContent = '✦ OpenAI';
    methodBadge.className = 'method-badge visible openai';
  } else {
    methodBadge.textContent = '⚙ Rule-based';
    methodBadge.className = 'method-badge visible rule';
  }

  // Validate
  runValidation(sql);
}

// ─── SQL Syntax Highlighter ───────────────────────────────────────────────────
function highlightSQL(sql) {
  // Escape HTML first
  let h = escapeHtml(sql);

  // Comments  (-- ...)
  h = h.replace(/(--[^\n]*)/g, '<span class="cm">$1</span>');

  // String literals
  h = h.replace(/('(?:[^'\\]|\\.)*')/g, '<span class="str">$1</span>');

  // Numbers
  h = h.replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="num">$1</span>');

  // SQL functions (must come before keywords)
  const fnPattern = new RegExp(`\\b(${SQL_FUNCTIONS.join('|')})\\s*(?=\\()`, 'gi');
  h = h.replace(fnPattern, '<span class="fn">$1</span>');

  // SQL keywords
  const kwPattern = new RegExp(`\\b(${SQL_KEYWORDS.join('|')})\\b`, 'gi');
  h = h.replace(kwPattern, (m) => `<span class="kw">${m.toUpperCase()}</span>`);

  // Operators
  h = h.replace(/([=<>!]+|[*])/g, '<span class="op">$1</span>');

  return h;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ─── SQL Validation ───────────────────────────────────────────────────────────
function runValidation(sql) {
  const upper = sql.toUpperCase();

  const checks = [
    { id: 'valSelect',    pass: /\bSELECT\b|\bCOUNT\b|\bSUM\b|\bAVG\b|\bMAX\b|\bMIN\b/.test(upper), label: 'Contains SELECT or aggregate' },
    { id: 'valFrom',      pass: /\bFROM\b/.test(upper),                                              label: 'Contains FROM clause'        },
    { id: 'valSemicolon', pass: sql.trim().endsWith(';'),                                             label: 'Ends with semicolon'         },
    { id: 'valKeywords',  pass: !/select|from|where|order|group/i.test(sql.replace(/'[^']*'/g,'')),  label: 'Keywords are uppercase'      },
  ];

  checks.forEach(({ id, pass, label }) => {
    const el = document.getElementById(id);
    el.classList.toggle('pass', pass);
    el.classList.toggle('fail', !pass);
    el.innerHTML = `<span class="validation-icon">${pass ? '✓' : '✗'}</span> ${label}`;
  });

  validationPanel.classList.add('visible');
}

// ─── Copy to clipboard ────────────────────────────────────────────────────────
async function copySQL() {
  if (!lastSQL) return;

  try {
    await navigator.clipboard.writeText(lastSQL);
    copyBtn.textContent = '✅ Copied!';
    copyBtn.classList.add('copied');
    showToast('📋 SQL copied to clipboard!', 'success');

    setTimeout(() => {
      copyBtn.textContent = '📋 Copy';
      copyBtn.classList.remove('copied');
    }, 2000);
  } catch {
    // Fallback for older browsers
    const ta = document.createElement('textarea');
    ta.value = lastSQL;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('📋 SQL copied!', 'success');
  }
}

// ─── Clear ────────────────────────────────────────────────────────────────────
function clearAll() {
  queryInput.value = '';
  lastSQL = '';
  charCount.textContent = `0 / ${CHAR_LIMIT}`;
  charCount.classList.remove('warning', 'danger');
  hideError();
  hideResult();
  queryInput.focus();
}

// ─── History ──────────────────────────────────────────────────────────────────
function addToHistory(query, sql) {
  const entry = { query, sql, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) };
  history.unshift(entry);
  if (history.length > MAX_HISTORY) history.pop();

  try { localStorage.setItem('sqlHistory', JSON.stringify(history)); } catch { /* ignore */ }
  renderHistory();
}

function renderHistory() {
  if (history.length === 0) {
    historyEmpty.style.display = 'block';
    // Remove any existing items
    document.querySelectorAll('.history-item').forEach(el => el.remove());
    return;
  }

  historyEmpty.style.display = 'none';
  historyList.innerHTML = '';

  history.forEach((entry, i) => {
    const item = document.createElement('div');
    item.className = 'history-item';
    item.setAttribute('role', 'listitem');
    item.setAttribute('tabindex', '0');
    item.setAttribute('aria-label', `History item: ${entry.query}`);
    item.innerHTML = `
      <span class="history-query" title="${escapeHtml(entry.query)}">${escapeHtml(entry.query)}</span>
      <span class="history-time">${entry.time}</span>
    `;
    item.addEventListener('click', () => restoreHistory(i));
    item.addEventListener('keydown', (e) => { if (e.key === 'Enter') restoreHistory(i); });
    historyList.appendChild(item);
  });
}

function restoreHistory(index) {
  const entry = history[index];
  if (!entry) return;

  queryInput.value = entry.query;
  handleInputChange();
  lastSQL = entry.sql;
  displayResult(entry.sql, 'rule-based');
  queryInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// ─── Toast notifications ──────────────────────────────────────────────────────
function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toast.setAttribute('role', 'status');
  toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'toastOut 0.3s ease forwards';
    toast.addEventListener('animationend', () => toast.remove());
  }, 3000);
}
