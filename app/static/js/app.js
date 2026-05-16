/* ═══════════════════════════════════════════════════════════════
   AI Fraud Detection System  —  Frontend v2
   Sidebar SPA · Vanilla JS · Chart.js 4
═══════════════════════════════════════════════════════════════ */
'use strict';

// ─── State ───────────────────────────────────────────────────────────────────
const State = {
  token:       localStorage.getItem('fd_token'),
  user:        JSON.parse(localStorage.getItem('fd_user') || 'null'),
  currentView: 'dashboard',
  txPage:      1,
  alertPage:   1,
  custPage:    1,
  charts:      {},
};

// ─── API Client ───────────────────────────────────────────────────────────────
const API = {
  base: '/api',

  async req(endpoint, opts = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...(State.token ? { Authorization: `Bearer ${State.token}` } : {}),
      ...(opts.headers || {}),
    };
    try {
      const res  = await fetch(this.base + endpoint, { ...opts, headers });
      if (res.status === 401) { logout(); return null; }
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      return data;
    } catch (e) {
      if (e.message === 'Failed to fetch') throw new Error('Cannot reach server. Is it running?');
      throw e;
    }
  },

  get:  ep       => API.req(ep),
  post: (ep, b)  => API.req(ep, { method: 'POST', body: JSON.stringify(b) }),
  put:  (ep, b)  => API.req(ep, { method: 'PUT',  body: JSON.stringify(b) }),
};

// ─── SVG icon snippets ────────────────────────────────────────────────────────
const ICONS = {
  check:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`,
  x:       `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  warn:    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
  info:    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
  shield:  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
  close:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  alert:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>`,
  blocked: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>`,
  flagged: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>`,
  arrow:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>`,
};

// ─── Toast Notifications ───────────────────────────────────────────────────────
function toast(msg, type = 'info', duration = 3800) {
  const iconMap = { success: ICONS.check, error: ICONS.x, warning: ICONS.warn, info: ICONS.info };
  const el = document.createElement('div');
  el.className = `fd-toast ${type}`;
  el.innerHTML = `<span class="t-icon">${iconMap[type] || ICONS.info}</span><span class="t-msg">${esc(msg)}</span>`;
  const container = document.getElementById('toast-container');
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(16px)'; el.style.transition = 'all .3s'; setTimeout(() => el.remove(), 300); }, duration);
}

// ─── Live Clock ───────────────────────────────────────────────────────────────
function startClock() {
  const el = document.getElementById('live-clock');
  if (!el) return;
  const tick = () => {
    const now = new Date();
    el.textContent = now.toLocaleTimeString('en-US', { hour12: false });
  };
  tick();
  setInterval(tick, 1000);
}

// ─── Auth ─────────────────────────────────────────────────────────────────────
// Holds the short-lived temp token while waiting for TOTP code
State.tempToken = null;

async function login() {
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const btn      = document.getElementById('login-btn');
  const errEl    = document.getElementById('login-error');

  if (!username || !password) {
    errEl.innerHTML = `${ICONS.warn} Please enter username and password.`;
    return;
  }

  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Signing in…`;
  errEl.textContent = '';

  try {
    const data = await API.post('/auth/login', { username, password });

    if (data.requires_2fa) {
      // Admin has 2FA — show the TOTP step
      State.tempToken = data.temp_token;
      _showLogin2FAStep();
      return;
    }

    _completeLogin(data);
  } catch (e) {
    errEl.innerHTML = `${ICONS.warn} ${e.message || 'Login failed.'}`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg> Sign In`;
  }
}

async function verify2FA() {
  const code   = (document.getElementById('login-totp')?.value || '').trim().replace(/\s/g, '');
  const btn    = document.getElementById('verify-2fa-btn');
  const errEl  = document.getElementById('login-2fa-error');
  errEl.textContent = '';

  if (!code || code.length !== 6) {
    errEl.innerHTML = `${ICONS.warn} Enter the 6-digit code from your authenticator app.`;
    return;
  }

  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Verifying…`;

  try {
    const res = await fetch('/api/auth/2fa/verify', {
      method:  'POST',
      headers: {
        'Content-Type':  'application/json',
        'Authorization': `Bearer ${State.tempToken}`,
      },
      body: JSON.stringify({ code }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Verification failed');
    _completeLogin(data);
  } catch (e) {
    errEl.innerHTML = `${ICONS.warn} ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px"><polyline points="20 6 9 17 4 12"/></svg> Verify Code`;
  }
}

function cancelLogin() {
  State.tempToken = null;
  _hideLogin2FAStep();
  document.getElementById('login-totp').value = '';
  document.getElementById('login-2fa-error').textContent = '';
}

function _showLogin2FAStep() {
  document.getElementById('login-username').closest('.login-field').style.display = 'none';
  document.getElementById('login-password').closest('.login-field').style.display = 'none';
  document.getElementById('login-error').style.display  = 'none';
  document.getElementById('login-btn').style.display    = 'none';
  document.getElementById('login-2fa-step').style.display = '';
  setTimeout(() => document.getElementById('login-totp')?.focus(), 80);
}

function _hideLogin2FAStep() {
  document.getElementById('login-username').closest('.login-field').style.display = '';
  document.getElementById('login-password').closest('.login-field').style.display = '';
  document.getElementById('login-error').style.display  = '';
  document.getElementById('login-btn').style.display    = '';
  document.getElementById('login-2fa-step').style.display = 'none';
}

function _completeLogin(data) {
  State.token     = data.access_token;
  State.user      = data.user;
  State.tempToken = null;
  localStorage.setItem('fd_token', State.token);
  localStorage.setItem('fd_user',  JSON.stringify(State.user));

  _hideLogin2FAStep();
  document.getElementById('login-page').style.display = 'none';
  document.getElementById('main-app').style.display   = '';

  setUserInfo(State.user);
  initApp();
}

function fillDemo(username, password) {
  document.getElementById('login-username').value = username;
  document.getElementById('login-password').value = password;
  document.getElementById('login-username').focus();
}

function togglePassword() {
  const input = document.getElementById('login-password');
  const label = document.getElementById('login-show-pass');
  if (input.type === 'password') {
    input.type = 'text';
    label.textContent = 'Hide';
  } else {
    input.type = 'password';
    label.textContent = 'Show';
  }
}

function goHome() {
  if (State.token) {
    showView('dashboard');
  } else {
    document.getElementById('main-app').style.display   = 'none';
    document.getElementById('login-page').style.display = '';
  }
}

function logout() {
  State.token     = null;
  State.user      = null;
  State.tempToken = null;
  localStorage.removeItem('fd_token');
  localStorage.removeItem('fd_user');
  document.getElementById('main-app').style.display   = 'none';
  document.getElementById('login-page').style.display = '';
  document.getElementById('btn-2fa-setup').style.display = 'none';
  Object.values(State.charts).forEach(c => c?.destroy?.());
  State.charts = {};
}

// ─── 2FA Management Modal ─────────────────────────────────────────────────────
async function open2FAModal() {
  try {
    const st = await API.get('/auth/2fa/status');

    if (st.totp_enabled) {
      // 2FA is active — offer to disable
      showModal(`
        <div class="modal-header">
          <h3>Two-Factor Authentication</h3>
          <button class="modal-close" onclick="closeModal()">${ICONS.close}</button>
        </div>
        <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:1.1rem">
          <span class="badge badge-approved">${ICONS.check} Active</span>
          <span style="font-size:0.84rem;color:var(--text-2)">Your account is protected by TOTP authentication</span>
        </div>
        <p style="font-size:0.84rem;color:var(--text-2);margin-bottom:1.1rem">
          To disable 2FA enter a valid code from your authenticator app:
        </p>
        <div class="login-field" style="margin-bottom:0.75rem">
          <label>Authenticator Code</label>
          <input id="modal-totp-code" class="fd-input" type="text" maxlength="6"
                 inputmode="numeric" placeholder="000000" autocomplete="off">
        </div>
        <div id="modal-2fa-err" style="color:var(--danger);font-size:0.82rem;min-height:1.2rem;margin-bottom:0.5rem"></div>
        <div style="display:flex;gap:0.5rem;justify-content:flex-end">
          <button class="fd-btn fd-btn-ghost" onclick="closeModal()">Cancel</button>
          <button class="fd-btn fd-btn-danger" onclick="disable2FA()">Disable 2FA</button>
        </div>`);
    } else {
      // 2FA not set up — generate QR and show setup flow
      const setup = await API.post('/auth/2fa/setup');
      const qrHtml = setup.qr_code
        ? `<img src="${setup.qr_code}" alt="QR Code" style="width:160px;height:160px;border-radius:8px;border:3px solid #fff;display:block;margin:0 auto 0.75rem">`
        : '';
      showModal(`
        <div class="modal-header">
          <h3>Set Up Two-Factor Authentication</h3>
          <button class="modal-close" onclick="closeModal()">${ICONS.close}</button>
        </div>
        <p style="font-size:0.83rem;color:var(--text-2);margin-bottom:1rem">
          Scan this QR code with <strong>Google Authenticator</strong>, <strong>Authy</strong>, or any TOTP app.
          Then enter the 6-digit code below to activate.
        </p>
        ${qrHtml}
        <div style="background:var(--surface-2);border-radius:6px;padding:0.6rem 0.75rem;margin-bottom:1rem;font-size:0.76rem">
          <span style="color:var(--text-3)">Manual key:</span>
          <code class="mono" style="color:var(--accent);font-size:0.82rem;word-break:break-all">${esc(setup.secret)}</code>
        </div>
        <div class="login-field" style="margin-bottom:0.75rem">
          <label>Confirm with Authenticator Code</label>
          <input id="modal-totp-code" class="fd-input" type="text" maxlength="6"
                 inputmode="numeric" placeholder="000000" autocomplete="off">
        </div>
        <div id="modal-2fa-err" style="color:var(--danger);font-size:0.82rem;min-height:1.2rem;margin-bottom:0.5rem"></div>
        <div style="display:flex;gap:0.5rem;justify-content:flex-end">
          <button class="fd-btn fd-btn-ghost" onclick="closeModal()">Cancel</button>
          <button class="fd-btn fd-btn-primary" onclick="enable2FA()">Activate 2FA</button>
        </div>`);
    }
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function enable2FA() {
  const code = (document.getElementById('modal-totp-code')?.value || '').trim();
  const errEl = document.getElementById('modal-2fa-err');
  errEl.textContent = '';
  try {
    await API.post('/auth/2fa/enable', { code });
    closeModal();
    toast('2FA activated — your account is now protected', 'success');
    // Update stored user state
    if (State.user) { State.user.totp_enabled = true; localStorage.setItem('fd_user', JSON.stringify(State.user)); }
  } catch (e) {
    errEl.textContent = e.message;
  }
}

async function disable2FA() {
  const code = (document.getElementById('modal-totp-code')?.value || '').trim();
  const errEl = document.getElementById('modal-2fa-err');
  errEl.textContent = '';
  try {
    await API.post('/auth/2fa/disable', { code });
    closeModal();
    toast('2FA disabled', 'info');
    if (State.user) { State.user.totp_enabled = false; localStorage.setItem('fd_user', JSON.stringify(State.user)); }
  } catch (e) {
    errEl.textContent = e.message;
  }
}

function setUserInfo(user) {
  if (!user) return;
  set('nav-username', user.username);
  set('nav-role',     user.role);
  const initials = user.username.slice(0, 2).toUpperCase();
  set('user-avatar-initials', initials);

  const isAdmin = user.role === 'admin';

  // Show 2FA button only for admin accounts
  const btn2fa = document.getElementById('btn-2fa-setup');
  if (btn2fa) btn2fa.style.display = isAdmin ? '' : 'none';

  // Admin-only sidebar items
  const navRules = document.getElementById('nav-rules');
  if (navRules) navRules.style.display = isAdmin ? '' : 'none';

  // Style the role badge in sidebar
  const roleEl = document.getElementById('nav-role');
  if (roleEl) {
    roleEl.style.color = isAdmin ? 'var(--danger)' : 'var(--accent)';
    roleEl.style.fontWeight = isAdmin ? '700' : '500';
  }
}

// ─── View Navigation (Sidebar) ────────────────────────────────────────────────
const VIEW_META = {
  dashboard:    { title: 'Dashboard',           subtitle: 'Overview & Analytics' },
  transactions: { title: 'Transactions',         subtitle: 'All processed transactions' },
  alerts:       { title: 'Fraud Alerts',         subtitle: 'Suspicious activity alerts' },
  submit:       { title: 'Submit Transaction',   subtitle: 'Process & analyze a transaction' },
  customers:    { title: 'Customers',            subtitle: 'Customer risk profiles' },
  rules:        { title: 'Detection Rules',      subtitle: 'Configure fraud rule engine' },
  assistant:    { title: 'AI Assistant',         subtitle: 'Claude claude-opus-4-6 · Adaptive thinking' },
  ofac:         { title: 'OFAC Sanctions',       subtitle: 'US Treasury SDN list screening & compliance' },
  demo:         { title: 'Live Demo',            subtitle: 'See the fraud detection pipeline in action' },
  monitor:      { title: 'Live Monitor',         subtitle: 'Real-time streaming analytics & threshold monitoring' },
};

function showView(name) {
  // Block analyst from accessing admin-only views
  const adminOnlyViews = ['rules'];
  if (adminOnlyViews.includes(name) && State.user?.role !== 'admin') {
    showToast('Access denied — this section is for administrators only.', 'error');
    return;
  }

  // Hide all views
  document.querySelectorAll('.fd-view').forEach(el => el.style.display = 'none');
  // Deactivate all nav items
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

  // Show target view
  const view = document.getElementById(`view-${name}`);
  if (view) { view.style.display = ''; }

  // Activate nav item
  const navItem = document.querySelector(`[data-view="${name}"]`);
  if (navItem) navItem.classList.add('active');

  // Update topbar
  const meta = VIEW_META[name] || {};
  set('topbar-title',    meta.title    || name);
  set('topbar-subtitle', meta.subtitle || '');

  State.currentView = name;

  // Load data for view
  if (name === 'dashboard')    loadDashboard();
  if (name === 'transactions') loadTransactions();
  if (name === 'alerts')       loadAlerts();
  if (name === 'rules')        loadRules();
  if (name === 'customers')    loadCustomers();
  if (name === 'assistant')    initAssistant();
  if (name === 'ofac')         loadOfacView();
  if (name === 'demo')         initDemo();
  if (name === 'monitor')      initMonitor();
}

function refreshCurrentView() {
  showView(State.currentView);
}

// ─── Dashboard ────────────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const [stats, trend, riskDist, alertTypes, topAlerts] = await Promise.all([
      API.get('/dashboard/stats'),
      API.get('/dashboard/trend?days=7'),
      API.get('/dashboard/risk-dist'),
      API.get('/dashboard/alert-types'),
      API.get('/dashboard/top-alerts'),
    ]);
    renderKPIs(stats);
    renderTrendChart(trend);
    renderRiskDistChart(riskDist);
    renderAlertTypesChart(alertTypes);
    renderTopAlerts(topAlerts);
    updateAlertBadge(stats.alerts?.unresolved || 0);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function updateAlertBadge(count) {
  const badge = document.getElementById('nav-alert-count');
  if (!badge) return;
  if (count > 0) { badge.style.display = ''; badge.textContent = count > 99 ? '99+' : count; }
  else { badge.style.display = 'none'; }
}

function renderKPIs(s) {
  const tx = s.transactions || {};
  const al = s.alerts       || {};
  const fi = s.financial    || {};
  const cu = s.customers    || {};

  animateCount('kpi-total-tx',   tx.total || 0);
  set('kpi-today-tx',    `+${tx.today || 0} today`);

  set('kpi-fraud-rate',  `${tx.fraud_rate || 0}%`);
  set('kpi-fraud-count', `${tx.fraud || 0} flagged / blocked`);

  animateCount('kpi-alerts', al.unresolved || 0);
  set('kpi-alerts-sub',  `${al.total || 0} total alerts`);

  set('kpi-amount',    `$${formatNum(fi.total_amount || 0)}`);
  set('kpi-fraud-amt', `$${formatNum(fi.fraud_amount || 0)} at risk`);

  animateCount('kpi-customers', cu.total || 0);
  set('kpi-high-risk',   `${cu.high_risk || 0} high-risk`);

  const avgRisk = fi.avg_risk_score || 0;
  set('kpi-avg-risk',    `${(avgRisk * 100).toFixed(1)}%`);
  set('kpi-model-status', 'ML Active');
}

// Animated number counter
function animateCount(id, target, duration = 700) {
  const el = document.getElementById(id);
  if (!el) return;
  const start = parseInt(el.textContent.replace(/\D/g, '')) || 0;
  const diff  = target - start;
  if (diff === 0) { el.textContent = target.toLocaleString(); return; }
  const startTime = performance.now();
  const tick = now => {
    const t = Math.min((now - startTime) / duration, 1);
    const ease = t < 0.5 ? 2*t*t : -1+(4-2*t)*t;
    el.textContent = Math.round(start + diff * ease).toLocaleString();
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// Chart theme helpers
const CHART_DEFAULTS = {
  color:     getComputedStyle(document.documentElement).getPropertyValue('--text-2').trim() || '#8b92b8',
  gridColor: 'rgba(255,255,255,0.05)',
  font:      { family: "'Inter', sans-serif", size: 11 },
};

function renderTrendChart(trend) {
  const ctx = document.getElementById('trend-chart');
  if (!ctx) return;
  State.charts.trend?.destroy();

  State.charts.trend = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: trend.map(d => d.label),
      datasets: [
        {
          label: 'Legitimate',
          data: trend.map(d => d.legitimate),
          backgroundColor: 'rgba(0,212,170,0.55)',
          borderColor:     'rgba(0,212,170,0.9)',
          borderWidth: 1,
          borderRadius: 4,
        },
        {
          label: 'Fraud',
          data: trend.map(d => d.fraud),
          backgroundColor: 'rgba(239,68,68,0.65)',
          borderColor:     'rgba(239,68,68,0.95)',
          borderWidth: 1,
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#8b92b8', font: CHART_DEFAULTS.font, boxWidth: 12, padding: 16 } },
        tooltip: { backgroundColor: '#1e2240', borderColor: 'rgba(255,255,255,0.12)', borderWidth: 1, titleColor: '#e8eaf6', bodyColor: '#8b92b8' },
      },
      scales: {
        x: { stacked: true, ticks: { color: '#8b92b8', font: CHART_DEFAULTS.font }, grid: { color: CHART_DEFAULTS.gridColor } },
        y: { stacked: true, ticks: { color: '#8b92b8', font: CHART_DEFAULTS.font }, grid: { color: CHART_DEFAULTS.gridColor } },
      },
    },
  });
}

function renderRiskDistChart(dist) {
  const ctx = document.getElementById('risk-dist-chart');
  if (!ctx) return;
  State.charts.riskDist?.destroy();

  State.charts.riskDist = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Low', 'Medium', 'High', 'Critical'],
      datasets: [{
        data: [dist.low, dist.medium, dist.high, dist.critical],
        backgroundColor: ['#22c55e', '#f59e0b', '#f97316', '#ef4444'],
        borderColor:     '#1a1d3a',
        borderWidth: 3,
        hoverOffset: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: { position: 'bottom', labels: { color: '#8b92b8', padding: 14, font: CHART_DEFAULTS.font, boxWidth: 10 } },
        tooltip: { backgroundColor: '#1e2240', borderColor: 'rgba(255,255,255,0.12)', borderWidth: 1, titleColor: '#e8eaf6', bodyColor: '#8b92b8' },
      },
    },
  });
}

function renderAlertTypesChart(types) {
  const ctx = document.getElementById('alert-types-chart');
  if (!ctx || !types.length) return;
  State.charts.alertTypes?.destroy();

  const top = types.slice(0, 7);
  const colours = ['#7c6af7','#ef4444','#f59e0b','#22c55e','#00d4aa','#f97316','#6358e8'];

  State.charts.alertTypes = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: top.map(t => t.type.replace(/_/g, ' ')),
      datasets: [{
        label: 'Alerts',
        data: top.map(t => t.count),
        backgroundColor: colours,
        borderRadius: 5,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: '#1e2240', borderColor: 'rgba(255,255,255,0.12)', borderWidth: 1, titleColor: '#e8eaf6', bodyColor: '#8b92b8' },
      },
      scales: {
        x: { ticks: { color: '#8b92b8', font: CHART_DEFAULTS.font }, grid: { color: CHART_DEFAULTS.gridColor } },
        y: { ticks: { color: '#8b92b8', font: { ...CHART_DEFAULTS.font, size: 10 } }, grid: { display: false } },
      },
    },
  });
}

function renderTopAlerts(alerts) {
  const tbody = document.getElementById('top-alerts-body');
  if (!tbody) return;
  if (!alerts.length) {
    tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state" style="padding:1.5rem"><p>No open alerts — system is clean</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = alerts.map(a => {
    const tx = a.transaction || {};
    return `
      <tr onclick="openAlertModal(${a.id})">
        <td><span class="badge badge-${a.severity}">${a.severity}</span></td>
        <td><code class="mono" style="font-size:0.72rem">${esc(a.alert_type)}</code></td>
        <td class="cell-dim">$${formatNum(tx.amount || 0)}</td>
        <td class="cell-dim" style="max-width:200px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${esc(a.description || '')}</td>
        <td class="cell-dim">${timeAgo(a.created_at)}</td>
      </tr>`;
  }).join('');
}

// ─── Transactions View ────────────────────────────────────────────────────────
function clearTxFilters() {
  ['tx-search', 'tx-filter-min', 'tx-filter-max', 'tx-filter-country'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const status = document.getElementById('tx-filter-status');
  const risk   = document.getElementById('tx-filter-risk');
  if (status) status.value = '';
  if (risk)   risk.value   = '';
  loadTransactions(1);
}

async function loadTransactions(page = 1) {
  State.txPage = page;
  const status    = document.getElementById('tx-filter-status')?.value || '';
  const riskLevel = document.getElementById('tx-filter-risk')?.value   || '';
  const search    = document.getElementById('tx-search')?.value.trim() || '';
  const minAmt    = document.getElementById('tx-filter-min')?.value.trim()     || '';
  const maxAmt    = document.getElementById('tx-filter-max')?.value.trim()     || '';
  const country   = document.getElementById('tx-filter-country')?.value.trim() || '';

  let qs = `?page=${page}&per_page=15`;
  if (status)    qs += `&status=${encodeURIComponent(status)}`;
  if (riskLevel) qs += `&risk_level=${encodeURIComponent(riskLevel)}`;
  if (search)    qs += `&search=${encodeURIComponent(search)}`;
  if (minAmt)    qs += `&min_amount=${encodeURIComponent(minAmt)}`;
  if (maxAmt)    qs += `&max_amount=${encodeURIComponent(maxAmt)}`;
  if (country)   qs += `&country=${encodeURIComponent(country)}`;

  showSkeleton('tx-tbody', 8);

  try {
    const data = await API.get(`/transactions${qs}`);
    renderTransactionTable(data.transactions);
    renderPagination('tx-pagination', data.current_page, data.pages, loadTransactions);
    set('tx-total-info', `${data.total.toLocaleString()} transaction${data.total !== 1 ? 's' : ''}`);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderTransactionTable(txs) {
  const tbody = document.getElementById('tx-tbody');
  if (!txs.length) {
    tbody.innerHTML = `<tr><td colspan="8"><div class="empty-state"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg><h4>No Transactions</h4><p>No transactions match your filter criteria</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = txs.map(t => {
    const score = t.combined_score ?? null;
    const rl    = t.risk_level || 'low';
    const scoreHtml = score !== null
      ? `<div class="risk-bar-wrap">
           <div class="risk-bar"><div class="risk-fill ${rl}" style="width:${(score*100).toFixed(0)}%"></div></div>
           <span class="risk-pct">${(score*100).toFixed(0)}%</span>
         </div>`
      : '<span class="text-faint">—</span>';

    const initials = (t.customer_name || '?').slice(0, 2).toUpperCase();
    return `
      <tr onclick="openTxModal(${t.id})">
        <td><span class="mono cell-dim" style="font-size:0.72rem">${esc(t.transaction_id.substring(0, 8))}…</span></td>
        <td>
          <div class="cust-cell">
            <div class="cust-avatar">${initials}</div>
            <div>
              <div>${esc(t.customer_name || '')}</div>
              <div class="cell-dim mono" style="font-size:0.7rem">${esc(t.customer_code || '')}</div>
            </div>
          </div>
        </td>
        <td><strong>$${formatNum(t.amount)}</strong> <span class="text-faint" style="font-size:0.75rem">${esc(t.currency)}</span></td>
        <td>
          <div>${esc(t.merchant_name || '')}</div>
          <div class="cell-dim" style="font-size:0.73rem">${esc(t.merchant_category || '')}</div>
        </td>
        <td><span class="badge badge-${t.status}">${statusDot(t.status)} ${t.status}</span></td>
        <td>${scoreHtml}</td>
        <td><span class="risk-badge ${rl}">${rl}</span></td>
        <td class="cell-dim" style="font-size:0.78rem;white-space:nowrap">${formatDate(t.timestamp)}</td>
      </tr>`;
  }).join('');
}

// ─── Alerts View ──────────────────────────────────────────────────────────────
async function loadAlerts(page = 1) {
  State.alertPage = page;
  const severity   = document.getElementById('al-filter-sev')?.value      || '';
  const isResolved = document.getElementById('al-filter-resolved')?.value  || '';

  let qs = `?page=${page}&per_page=15`;
  if (severity)       qs += `&severity=${severity}`;
  if (isResolved !== '') qs += `&is_resolved=${isResolved}`;

  showSkeleton('alerts-tbody', 7);

  try {
    const data = await API.get(`/alerts${qs}`);
    renderAlertsTable(data.alerts);
    renderPagination('alerts-pagination', data.current_page, data.pages, loadAlerts);
    set('alerts-total-info', `${data.total.toLocaleString()} alert${data.total !== 1 ? 's' : ''}`);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderAlertsTable(alerts) {
  const tbody = document.getElementById('alerts-tbody');
  if (!alerts.length) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg><h4>No Alerts</h4><p>No alerts match your filter criteria</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = alerts.map(a => `
    <tr style="cursor:pointer" onclick="openAlertModal(${a.id})">
      <td><span class="badge badge-${a.severity}">${a.severity}</span></td>
      <td><code class="mono" style="font-size:0.73rem">${esc(a.alert_type)}</code></td>
      <td style="max-width:260px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${esc(a.description || '')}</td>
      <td><span class="mono cell-dim" style="font-size:0.73rem">#${a.transaction_id}</span></td>
      <td>
        ${a.is_resolved
          ? `<span class="badge badge-approved">${ICONS.check} Resolved</span>`
          : `<span class="badge badge-flagged">${ICONS.alert} Open</span>`}
      </td>
      <td class="cell-dim" style="font-size:0.78rem;white-space:nowrap">${formatDate(a.created_at)}</td>
      <td onclick="event.stopPropagation()">
        ${!a.is_resolved
          ? `<button class="fd-btn fd-btn-ghost fd-btn-sm" onclick="resolveAlert(${a.id}, this)">Resolve</button>`
          : `<span class="text-faint" style="font-size:0.73rem">${a.resolved_at ? formatDate(a.resolved_at) : 'Resolved'}</span>`}
      </td>
    </tr>`).join('');
}

async function resolveAlert(id, btn) {
  const notes = prompt('Resolution notes (optional):') ?? '';
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';
  try {
    await API.put(`/alerts/${id}/resolve`, { notes });
    toast('Alert resolved successfully', 'success');
    loadAlerts(State.alertPage);
    loadDashboard();
  } catch (e) {
    toast(e.message, 'error');
    btn.disabled = false;
    btn.textContent = 'Resolve';
  }
}

// ─── Submit Transaction ───────────────────────────────────────────────────────
async function populateCustomerDropdown() {
  try {
    const data = await API.get('/customers?per_page=100');
    const sel  = document.getElementById('tx-customer-id');
    if (!sel) return;
    sel.innerHTML = '<option value="">— Select Customer —</option>' +
      data.customers.map(c =>
        `<option value="${esc(c.customer_id)}">${esc(c.name)} (${esc(c.customer_id)})</option>`
      ).join('');
  } catch (e) {
    console.error('Could not load customers:', e);
  }
}

async function submitTransaction(e) {
  e.preventDefault();
  const btn      = document.getElementById('submit-tx-btn');
  const resultEl = document.getElementById('result-box');
  const phEl     = document.getElementById('result-placeholder');

  const payload = {
    customer_id:       document.getElementById('tx-customer-id').value,
    amount:            parseFloat(document.getElementById('tx-amount').value),
    merchant_name:     document.getElementById('tx-merchant').value,
    merchant_category: document.getElementById('tx-category').value,
    location:          document.getElementById('tx-location').value,
    card_type:         document.getElementById('tx-card-type').value,
    transaction_type:  document.getElementById('tx-type').value,
    currency:          'USD',
  };

  if (!payload.customer_id || !payload.amount || !payload.merchant_name) {
    toast('Please fill in all required fields', 'warning');
    return;
  }

  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Analyzing…`;
  resultEl.style.display = 'none';

  try {
    const resp     = await API.post('/transactions', payload);
    const analysis = resp.fraud_analysis;
    const rs       = analysis.risk_score;
    const status   = analysis.status;

    const statusIcons = { approved: ICONS.check, flagged: ICONS.warn, blocked: ICONS.blocked };
    const statusColor = scoreColour(rs.combined_score);

    if (phEl) phEl.style.display = 'none';
    resultEl.style.display = '';
    resultEl.innerHTML = `
      <div class="result-card">
        <div class="result-status-row">
          <div class="result-status-icon ${status}">${statusIcons[status] || ICONS.info}</div>
          <div>
            <div class="result-status-label ${status}">${status.toUpperCase()}</div>
            <div class="result-status-msg">${esc(analysis.recommendation)}</div>
          </div>
        </div>

        <div class="score-grid">
          <div class="score-box">
            <div class="val" style="color:${statusColor}">${(rs.combined_score*100).toFixed(1)}%</div>
            <div class="lbl">Combined Score</div>
          </div>
          <div class="score-box">
            <div class="val" style="color:var(--accent)">${(rs.rule_score*100).toFixed(1)}%</div>
            <div class="lbl">Rule Score</div>
          </div>
          <div class="score-box">
            <div class="val" style="color:var(--indigo)">${(rs.ml_score*100).toFixed(1)}%</div>
            <div class="lbl">ML Score</div>
          </div>
        </div>

        ${analysis.rule_violations.length ? `
          <div style="margin-top:1rem">
            <div style="font-size:0.72rem;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.5rem">Rule Violations</div>
            <div class="violations-list">
              ${analysis.rule_violations.map(v => `
                <div class="violation-item">
                  ${ICONS.warn}
                  <span>${esc(v.description)}</span>
                </div>`).join('')}
            </div>
          </div>` : `
          <div style="margin-top:0.75rem;padding:0.6rem 0.75rem;background:var(--success-dim);border:1px solid rgba(76,175,80,0.2);border-radius:6px;font-size:0.8rem;color:var(--success);display:flex;align-items:center;gap:0.5rem">
            ${ICONS.check} No rule violations detected
          </div>`}

        ${(analysis.alerts_generated > 0) ? `
          <div style="margin-top:0.75rem;padding:0.55rem 0.75rem;background:var(--danger-dim);border:1px solid rgba(214,69,69,0.2);border-radius:6px;font-size:0.8rem;color:var(--danger);display:flex;align-items:center;gap:0.5rem">
            ${ICONS.alert} Fraud alert generated — analyst review required
          </div>` : ''}

        <div style="margin-top:1rem;padding-top:0.75rem;border-top:1px solid var(--border);font-size:0.75rem;color:var(--text-3);display:flex;align-items:center;justify-content:space-between">
          <span>TX: <code class="mono">${esc(resp.transaction.transaction_id.substring(0,12))}…</code></span>
          <span class="risk-badge ${rs.risk_level}">${rs.risk_level}</span>
        </div>
      </div>`;

    toast(`Transaction ${status}`, status === 'approved' ? 'success' : status === 'flagged' ? 'warning' : 'error');
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `${ICONS.shield} Analyze &amp; Submit`;
  }
}

// ─── Rules View ───────────────────────────────────────────────────────────────
async function loadRules() {
  try {
    const rules = await API.get('/dashboard/rules');
    renderRulesTable(rules);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderRulesTable(rules) {
  const tbody = document.getElementById('rules-tbody');
  if (!tbody) return;
  tbody.innerHTML = rules.map(r => `
    <tr>
      <td><code class="mono" style="font-size:0.78rem;color:var(--accent)">${esc(r.rule_name)}</code></td>
      <td class="cell-dim">${esc(r.description)}</td>
      <td><span class="badge badge-low">${esc(r.rule_type)}</span></td>
      <td>
        <input class="fd-input" style="width:95px" type="number" step="any"
          value="${r.threshold ?? ''}" id="rule-thr-${r.id}"
          onchange="updateRule(${r.id})">
      </td>
      <td>
        <input class="fd-input" style="width:80px" type="number" step="0.05" min="0" max="1"
          value="${r.weight}" id="rule-wt-${r.id}"
          onchange="updateRule(${r.id})">
      </td>
      <td>
        <button class="rule-toggle ${r.is_active ? 'on' : ''}"
          id="rule-tog-${r.id}" onclick="toggleRule(${r.id}, this)"
          title="${r.is_active ? 'Enabled' : 'Disabled'}">
        </button>
      </td>
    </tr>`).join('');
}

async function updateRule(id) {
  const thr = document.getElementById(`rule-thr-${id}`)?.value;
  const wt  = document.getElementById(`rule-wt-${id}`)?.value;
  try {
    await API.put(`/dashboard/rules/${id}`, {
      threshold: thr !== '' ? parseFloat(thr) : null,
      weight:    parseFloat(wt),
    });
    toast('Rule updated', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function toggleRule(id, btn) {
  const isOn = btn.classList.contains('on');
  try {
    await API.put(`/dashboard/rules/${id}`, { is_active: !isOn });
    btn.classList.toggle('on');
    btn.title = isOn ? 'Disabled' : 'Enabled';
    toast(`Rule ${isOn ? 'disabled' : 'enabled'}`, isOn ? 'warning' : 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ─── Customers View ───────────────────────────────────────────────────────────
async function loadCustomers(page = 1) {
  State.custPage = page;
  const search    = document.getElementById('cust-search')?.value.trim() || '';
  const riskLevel = document.getElementById('cust-risk')?.value          || '';

  let qs = `?page=${page}&per_page=15`;
  if (search)    qs += `&search=${encodeURIComponent(search)}`;
  if (riskLevel) qs += `&risk_level=${riskLevel}`;

  showSkeleton('customers-tbody', 7);

  try {
    const data = await API.get(`/customers${qs}`);
    renderCustomersTable(data.customers);
    renderPagination('customers-pagination', data.current_page, data.pages, loadCustomers);
    set('customers-total-info', `${data.total.toLocaleString()} customer${data.total !== 1 ? 's' : ''}`);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderCustomersTable(customers) {
  const tbody = document.getElementById('customers-tbody');
  if (!customers.length) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state"><p>No customers found</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = customers.map(c => {
    const initials = c.name.slice(0, 2).toUpperCase();
    return `
      <tr>
        <td>
          <div class="cust-cell">
            <div class="cust-avatar">${initials}</div>
            <div>${esc(c.name)}</div>
          </div>
        </td>
        <td><span class="mono cell-dim" style="font-size:0.78rem">${esc(c.customer_id)}</span></td>
        <td class="cell-dim">${esc(c.country)} / ${esc(c.city || '—')}</td>
        <td class="cell-dim" style="text-transform:capitalize">${esc(c.account_type)}</td>
        <td><strong>$${formatNum(c.avg_transaction_amount)}</strong></td>
        <td class="cell-dim">${c.total_transactions.toLocaleString()}</td>
        <td><span class="risk-badge ${c.risk_level}">${c.risk_level}</span></td>
      </tr>`;
  }).join('');
}

// ─── Transaction Detail Modal ─────────────────────────────────────────────────
async function openTxModal(id) {
  try {
    const t  = await API.get(`/transactions/${id}`);
    const rs = t.risk_score_detail;

    showModal(`
      <div class="modal-header">
        <h3>Transaction Detail</h3>
        <button class="modal-close" onclick="closeModal()">${ICONS.close}</button>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;margin-bottom:1.25rem">
        <div class="detail-row" style="grid-column:1/-1">
          <span class="detail-label">Transaction ID</span>
          <code class="mono" style="font-size:0.78rem">${esc(t.transaction_id)}</code>
        </div>
        <div class="detail-row"><span class="detail-label">Status</span><span class="detail-value"><span class="badge badge-${t.status}">${t.status}</span></span></div>
        <div class="detail-row"><span class="detail-label">Amount</span><span class="detail-value"><strong>$${formatNum(t.amount)}</strong> ${esc(t.currency)}</span></div>
        <div class="detail-row"><span class="detail-label">Customer</span><span class="detail-value">${esc(t.customer_name || '—')}</span></div>
        <div class="detail-row"><span class="detail-label">Merchant</span><span class="detail-value">${esc(t.merchant_name || '—')}</span></div>
        <div class="detail-row"><span class="detail-label">Category</span><span class="detail-value">${esc(t.merchant_category || '—')}</span></div>
        <div class="detail-row"><span class="detail-label">Location</span><span class="detail-value">${esc(t.location || '—')}</span></div>
        <div class="detail-row"><span class="detail-label">Card Type</span><span class="detail-value" style="text-transform:capitalize">${esc(t.card_type || '—')}</span></div>
        <div class="detail-row" style="grid-column:1/-1"><span class="detail-label">Timestamp</span><span class="detail-value">${formatDate(t.timestamp)}</span></div>
      </div>

      ${rs ? `
        <div style="border-top:1px solid var(--border);padding-top:1rem;margin-bottom:0.75rem">
          <div style="font-size:0.72rem;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.75rem">Risk Analysis</div>
          <div class="score-grid">
            <div class="score-box"><div class="val" style="color:${scoreColour(rs.combined_score)}">${(rs.combined_score*100).toFixed(1)}%</div><div class="lbl">Combined</div></div>
            <div class="score-box"><div class="val" style="color:var(--accent)">${(rs.rule_score*100).toFixed(1)}%</div><div class="lbl">Rule Score</div></div>
            <div class="score-box"><div class="val" style="color:var(--indigo)">${(rs.ml_score*100).toFixed(1)}%</div><div class="lbl">ML Score</div></div>
          </div>
          ${rs.rule_violations.length ? `
            <div class="violations-list" style="margin-top:0.75rem">
              ${rs.rule_violations.map(v => `<div class="violation-item">${ICONS.warn}<span>${esc(v.description)}</span></div>`).join('')}
            </div>` : ''}
        </div>` : ''}

      ${t.alerts?.length ? `
        <div style="border-top:1px solid var(--border);padding-top:0.75rem">
          <div style="font-size:0.72rem;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.5rem">Alerts (${t.alerts.length})</div>
          ${t.alerts.map(a => `
            <div style="display:flex;align-items:center;gap:0.5rem;margin:0.35rem 0;font-size:0.82rem">
              <span class="badge badge-${a.severity}">${a.severity}</span>
              <span class="cell-dim">${esc(a.description)}</span>
            </div>`).join('')}
        </div>` : ''}

      <div style="display:flex;gap:0.5rem;margin-top:1.25rem;justify-content:flex-end">
        <button class="fd-btn fd-btn-ghost" onclick="closeModal()">Close</button>
        ${!t.is_reviewed ? `
          <button class="fd-btn fd-btn-success" onclick="markReviewed(${t.id},'approved')">${ICONS.check} Mark Legitimate</button>
          <button class="fd-btn fd-btn-danger"  onclick="markReviewed(${t.id},'blocked')">${ICONS.blocked} Confirm Fraud</button>` : ''}
      </div>`);
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function openAlertModal(id) {
  try {
    const a = await API.get(`/alerts/${id}`);
    showModal(`
      <div class="modal-header">
        <h3>Alert Detail</h3>
        <button class="modal-close" onclick="closeModal()">${ICONS.close}</button>
      </div>
      <div style="display:flex;gap:0.5rem;align-items:center;margin-bottom:1rem">
        <span class="badge badge-${a.severity}">${a.severity}</span>
        <code class="mono" style="font-size:0.78rem">${esc(a.alert_type)}</code>
        ${a.is_resolved
          ? `<span class="badge badge-approved">${ICONS.check} Resolved</span>`
          : `<span class="badge badge-flagged">${ICONS.alert} Open</span>`}
      </div>
      <p style="font-size:0.875rem;color:var(--text);margin-bottom:0.75rem">${esc(a.description || '')}</p>

      ${a.risk_factors?.length ? `
        <div style="font-size:0.72rem;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.5rem">Risk Factors</div>
        <div class="violations-list">
          ${a.risk_factors.map(f => `<div class="violation-item">${ICONS.warn}<span>${esc(f)}</span></div>`).join('')}
        </div>` : ''}

      ${a.transaction ? `
        <div style="border-top:1px solid var(--border);padding-top:0.75rem;margin-top:0.75rem">
          <div style="font-size:0.72rem;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.4rem">Related Transaction</div>
          <div class="detail-row"><span class="detail-label">Amount</span><span class="detail-value"><strong>$${formatNum(a.transaction.amount)}</strong></span></div>
          <div class="detail-row"><span class="detail-label">Merchant</span><span class="detail-value">${esc(a.transaction.merchant_name || '—')}</span></div>
          <div class="detail-row"><span class="detail-label">Time</span><span class="detail-value">${formatDate(a.transaction.timestamp)}</span></div>
        </div>` : ''}

      <div style="display:flex;gap:0.5rem;margin-top:1.25rem;justify-content:flex-end">
        <button class="fd-btn fd-btn-ghost" onclick="closeModal()">Close</button>
        ${!a.is_resolved ? `<button class="fd-btn fd-btn-success" onclick="resolveAlertModal(${a.id})">${ICONS.check} Resolve Alert</button>` : ''}
      </div>`);
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function resolveAlertModal(id) {
  const notes = prompt('Resolution notes (optional):') ?? '';
  try {
    await API.put(`/alerts/${id}/resolve`, { notes });
    toast('Alert resolved', 'success');
    closeModal();
    loadAlerts(State.alertPage);
    loadDashboard();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function markReviewed(id, action) {
  try {
    await API.put(`/transactions/${id}/review`, { is_reviewed: true, is_fraud: action === 'blocked', status: action });
    toast(`Transaction marked as ${action}`, 'success');
    closeModal();
    loadTransactions(State.txPage);
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ─── Modal helpers ────────────────────────────────────────────────────────────
function showModal(html) {
  let backdrop = document.getElementById('modal-backdrop');
  if (!backdrop) {
    backdrop = document.createElement('div');
    backdrop.id = 'modal-backdrop';
    backdrop.className = 'fd-backdrop';
    backdrop.onclick = e => { if (e.target === backdrop) closeModal(); };
    document.body.appendChild(backdrop);
  }
  backdrop.innerHTML = `<div class="fd-modal">${html}</div>`;
  backdrop.style.display = 'flex';
}

function closeModal() {
  const el = document.getElementById('modal-backdrop');
  if (el) el.style.display = 'none';
}

// ─── Pagination ───────────────────────────────────────────────────────────────
function renderPagination(containerId, current, total, loadFn) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (total <= 1) { el.innerHTML = ''; return; }

  let html = `<button class="pg-btn" onclick="${loadFn.name}(${current-1})" ${current===1?'disabled':''}>‹</button>`;
  for (const p of pageRange(current, total)) {
    html += p === '…'
      ? `<span class="pg-btn" style="cursor:default">…</span>`
      : `<button class="pg-btn ${p===current?'active':''}" onclick="${loadFn.name}(${p})">${p}</button>`;
  }
  html += `<button class="pg-btn" onclick="${loadFn.name}(${current+1})" ${current===total?'disabled':''}>›</button>`;
  el.innerHTML = html;
}

function pageRange(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i+1);
  const pages = [1];
  if (current > 3) pages.push('…');
  for (let i = Math.max(2, current-1); i <= Math.min(total-1, current+1); i++) pages.push(i);
  if (current < total-2) pages.push('…');
  pages.push(total);
  return pages;
}

// ─── Utilities ────────────────────────────────────────────────────────────────
function set(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function esc(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function formatNum(n) {
  if (n === null || n === undefined) return '—';
  if (n >= 1_000_000) return (n/1_000_000).toFixed(1)+'M';
  if (n >= 10_000)    return (n/1_000).toFixed(1)+'K';
  return parseFloat(n).toLocaleString('en-US', { minimumFractionDigits:2, maximumFractionDigits:2 });
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-US', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' });
}

function timeAgo(iso) {
  if (!iso) return '—';
  const s = (Date.now() - new Date(iso)) / 1000;
  if (s < 60)    return 'just now';
  if (s < 3600)  return `${Math.round(s/60)}m ago`;
  if (s < 86400) return `${Math.round(s/3600)}h ago`;
  return `${Math.round(s/86400)}d ago`;
}

function statusDot(s) {
  const dots = { approved:'●', flagged:'▲', blocked:'■', pending:'○' };
  return `<span style="font-size:0.55rem">${dots[s]||'·'}</span>`;
}

function scoreColour(score) {
  if (score >= 0.75) return 'var(--critical)';
  if (score >= 0.55) return 'var(--danger)';
  if (score >= 0.35) return 'var(--warning)';
  return 'var(--success)';
}

function showSkeleton(tbodyId, cols) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  const cell = `<td><div style="height:13px;background:var(--surface-3);border-radius:4px;animation:skeletonPulse 1.4s ease-in-out infinite"></div></td>`;
  tbody.innerHTML = Array(5).fill(`<tr>${Array(cols).fill(cell).join('')}</tr>`).join('');
}

// ─── OFAC Sanctions ───────────────────────────────────────────────────────────
const OFAC = { sdnPage: 1, sdnSearchTimer: null };

async function loadOfacView() {
  if (State.user?.role === 'admin') {
    const btn = document.getElementById('ofac-refresh-btn');
    if (btn) btn.style.display = '';
  }
  // Load everything in parallel — SDN list is now always visible on open
  await Promise.all([
    loadOfacStatus(),
    loadAgeViolations(),
    loadOfacHistory(),
    loadSdnPrograms(),
  ]);
  loadSdnList(1);   // always load the list immediately
}

// Keep the two search inputs in sync
function copyToScreenInput(val) {
  const el = document.getElementById('ofac-check-name');
  if (el) el.value = val;
}
function copyToSdnSearch(val) {
  const el = document.getElementById('sdn-search');
  if (el) el.value = val;
}

// ── Status ────────────────────────────────────────────────────────────────────
async function loadOfacStatus() {
  try {
    const data = await API.get('/compliance/ofac/status');
    const total = data.total_entries || 0;

    set('ofac-total-entries',  total.toLocaleString());
    set('ofac-header-count',   total.toLocaleString());

    const lu = data.last_update ? new Date(data.last_update).toLocaleString() : 'Never';
    set('ofac-last-update', lu);

    const pill = document.getElementById('ofac-service-pill');
    if (pill) {
      const ok = data.operational;
      pill.textContent = ok ? '● Operational' : '● Seeding…';
      pill.className   = `badge ${ok ? 'badge-approved' : 'badge-flagged'}`;
    }
  } catch (e) {
    set('ofac-total-entries', 'Error');
  }
}

// ── SDN List (paginated + searchable) ────────────────────────────────────────
async function loadSdnPrograms() {
  try {
    const programs = await API.get('/compliance/ofac/programs');
    const sel = document.getElementById('sdn-program-filter');
    if (!sel) return;
    programs.slice(0, 30).forEach(p => {
      const opt = document.createElement('option');
      opt.value = p; opt.textContent = p;
      sel.appendChild(opt);
    });
  } catch (_) {}
}

function debouncedSdnSearch() {
  clearTimeout(OFAC.sdnSearchTimer);
  OFAC.sdnSearchTimer = setTimeout(() => loadSdnList(1), 320);
}

async function loadSdnList(page = 1) {
  OFAC.sdnPage = page;
  const q       = document.getElementById('sdn-search')?.value.trim()       || '';
  const type    = document.getElementById('sdn-type-filter')?.value         || '';
  const program = document.getElementById('sdn-program-filter')?.value      || '';

  showSkeleton('sdn-list-tbody', 5);

  try {
    const params = new URLSearchParams({ page, per_page: 25 });
    if (q)       params.set('q',       q);
    if (type)    params.set('type',    type);
    if (program) params.set('program', program);

    const data  = await API.get(`/compliance/ofac/entries?${params}`);
    const tbody = document.getElementById('sdn-list-tbody');
    if (!tbody) return;

    set('sdn-total-info', `${(data.total || 0).toLocaleString()} entr${data.total !== 1 ? 'ies' : 'y'}`);

    if (!data.items?.length) {
      tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state"><p>No SDN entries match your filters</p></div></td></tr>`;
      document.getElementById('sdn-pagination').innerHTML = '';
      return;
    }

    const offset = (data.page - 1) * data.per_page;
    tbody.innerHTML = data.items.map((e, i) => `
      <tr>
        <td class="cell-dim" style="font-size:0.75rem;width:50px">${offset + i + 1}</td>
        <td>
          <div style="font-weight:600;font-size:0.85rem;color:var(--text)">${esc(e.name)}</div>
        </td>
        <td>${sdnTypeBadge(e.type)}</td>
        <td>
          ${(e.program || '').split(/\s+/).filter(Boolean).map(p =>
            `<span class="source-pill" style="font-size:0.67rem">${esc(p)}</span>`
          ).join(' ')}
        </td>
        <td style="font-size:0.75rem;color:var(--text-3);max-width:260px;
                   overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
            title="${esc(e.remarks || '')}">${esc((e.remarks || '').substring(0, 80) || '—')}</td>
      </tr>`).join('');

    renderPagination('sdn-pagination', data.page, data.pages, loadSdnList);
  } catch (e) {
    toast(e.message, 'error');
  }
}

function sdnTypeBadge(type) {
  const map = {
    individual: ['badge-flagged', 'Individual'],
    entity:     ['badge-blocked', 'Entity'],
    vessel:     ['', 'Vessel'],
    aircraft:   ['', 'Aircraft'],
  };
  const [cls, label] = map[(type || '').toLowerCase()] || ['', type || '—'];
  return `<span class="badge ${cls}" style="font-size:0.68rem;text-transform:capitalize">${esc(label)}</span>`;
}

// ── Age Violations ────────────────────────────────────────────────────────────
async function loadAgeViolations() {
  try {
    const data       = await API.get('/compliance/age-violations');
    const violations = data.violations || [];

    set('ofac-age-violations', violations.length);
    const navBadge   = document.getElementById('nav-ofac-badge');
    const countBadge = document.getElementById('age-viol-count-badge');
    if (navBadge)   { navBadge.style.display   = violations.length ? '' : 'none'; navBadge.textContent   = violations.length; }
    if (countBadge) { countBadge.style.display = violations.length ? '' : 'none'; countBadge.textContent = violations.length; }

    const wrap = document.getElementById('age-violations-table-wrap');
    if (!wrap) return;

    if (!violations.length) {
      wrap.innerHTML = `
        <div style="text-align:center;padding:2.5rem;color:var(--success)">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:32px;height:32px;display:block;margin:0 auto 0.6rem"><polyline points="20 6 9 17 4 12"/></svg>
          <div style="font-weight:600;font-size:0.9rem">No Age Violations Found</div>
          <div style="font-size:0.8rem;color:var(--text-3);margin-top:0.3rem">All ${data.total_checked} customers with known DOB are within the 18–100 range.</div>
        </div>`;
      return;
    }

    wrap.innerHTML = `
      <table class="fd-table">
        <thead><tr>
          <th>Customer</th><th>ID</th><th>Country</th>
          <th>Date of Birth</th><th>Age</th><th>Violation</th><th>Reason</th>
        </tr></thead>
        <tbody>
          ${violations.map(v => `
            <tr>
              <td>
                <div class="cust-cell">
                  <div class="cust-avatar" style="background:var(--danger)">${esc(v.name.slice(0,2).toUpperCase())}</div>
                  <div style="font-weight:600">${esc(v.name)}</div>
                </div>
              </td>
              <td class="cell-dim mono" style="font-size:0.75rem">${esc(v.customer_id)}</td>
              <td class="cell-dim">${esc(v.country)}</td>
              <td class="cell-dim">${esc(v.date_of_birth || '—')}</td>
              <td><strong style="color:var(--danger)">${v.age}</strong></td>
              <td><span class="badge badge-blocked" style="font-size:0.68rem">${esc(v.violation)}</span></td>
              <td style="font-size:0.78rem;color:var(--text-2)">${esc(v.reason)}</td>
            </tr>`).join('')}
        </tbody>
      </table>`;
  } catch (e) {
    const wrap = document.getElementById('age-violations-table-wrap');
    if (wrap) wrap.innerHTML = `<div style="color:var(--danger);padding:1rem">Error: ${esc(e.message)}</div>`;
  }
}

// ── Update History ────────────────────────────────────────────────────────────
async function loadOfacHistory() {
  try {
    const updates = await API.get('/compliance/ofac/updates');
    const tbody   = document.getElementById('ofac-history-tbody');
    if (!tbody) return;

    if (!updates.length) {
      tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state" style="padding:1.5rem"><p>No update history yet — first update runs at 02:00</p></div></td></tr>`;
      return;
    }

    tbody.innerHTML = updates.map((u, i) => {
      const cls = u.status === 'success' ? 'badge-approved' : u.status === 'running' ? 'badge-flagged' : 'badge-blocked';
      return `<tr>
        <td class="cell-dim" style="font-size:0.75rem">${i + 1}</td>
        <td><span class="badge ${cls}">${esc(u.status)}</span></td>
        <td class="cell-dim">${(u.entries_added || 0).toLocaleString()}</td>
        <td class="cell-dim">${(u.entries_total || 0).toLocaleString()}</td>
        <td style="font-size:0.75rem;color:var(--danger);max-width:200px;
                   overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          ${esc(u.error_message || '—')}
        </td>
        <td class="cell-dim" style="font-size:0.78rem;white-space:nowrap">
          ${u.updated_at ? new Date(u.updated_at).toLocaleString() : '—'}
        </td>
      </tr>`;
    }).join('');
  } catch (_) {}
}

// ── Name Screening ────────────────────────────────────────────────────────────
function ofacThresholdUpdate(val) {
  set('ofac-thresh-val', val + '%');
  set('ofac-threshold-display', val + '%');
}

function ofacQuickTest(name) {
  const inp = document.getElementById('ofac-check-name');
  if (inp) { inp.value = name; checkOfacName(); }
}

function clearOfacScreen() {
  const inp = document.getElementById('ofac-check-name');
  if (inp) inp.value = '';
  const res = document.getElementById('ofac-check-result');
  if (res) res.innerHTML = `
    <div class="ofac-result-placeholder">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="width:38px;height:38px;color:var(--text-3);display:block;margin:0 auto 0.75rem"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
      <div style="font-size:0.88rem;font-weight:600;color:var(--text-2)">Awaiting Screening</div>
      <div style="font-size:0.78rem;color:var(--text-3);margin-top:0.3rem">Enter a name and click Screen Name</div>
    </div>`;
}

async function checkOfacName() {
  const input     = document.getElementById('ofac-check-name');
  const threshEl  = document.getElementById('ofac-threshold');
  const resultEl  = document.getElementById('ofac-check-result');
  const name      = (input?.value || '').trim();
  const threshold = parseInt(threshEl?.value || '82') / 100;

  if (!name) { toast('Enter a name to screen', 'warning'); input?.focus(); return; }

  const total = document.getElementById('ofac-total-entries')?.textContent || '—';
  resultEl.innerHTML = `
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
                height:160px;color:var(--text-3);gap:0.75rem">
      <span class="spinner" style="width:22px;height:22px;border-width:3px"></span>
      <div style="font-size:0.82rem">Screening against <strong style="color:var(--accent)">${total}</strong> SDN entries…</div>
    </div>`;

  try {
    const data = await API.post('/compliance/ofac/check', { name, threshold });

    if (data.matched && data.match) {
      const m   = data.match;
      const sim = Math.round(m.similarity * 100);
      resultEl.innerHTML = `
        <div style="background:var(--danger-dim);border:2px solid rgba(214,69,69,0.4);
                    border-radius:var(--r-md);padding:1.25rem;animation:msgIn .2s ease">
          <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:1rem">
            <div style="width:34px;height:34px;border-radius:50%;background:var(--danger);
                        display:flex;align-items:center;justify-content:center;flex-shrink:0">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" style="width:16px;height:16px"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
            </div>
            <div>
              <div style="color:var(--danger);font-weight:700;font-size:0.95rem">⛔ SDN MATCH FOUND</div>
              <div style="font-size:0.72rem;color:var(--text-3)">Transaction must be blocked immediately</div>
            </div>
            <div style="margin-left:auto;text-align:center">
              <div style="font-size:1.4rem;font-weight:800;color:var(--danger)">${sim}%</div>
              <div style="font-size:0.68rem;color:var(--text-3)">similarity</div>
            </div>
          </div>
          <div class="detail-row"><span class="detail-label">Queried</span><span class="detail-value">${esc(name)}</span></div>
          <div class="detail-row"><span class="detail-label">SDN Entry</span><span class="detail-value" style="color:var(--danger);font-weight:700">${esc(m.match_name)}</span></div>
          <div class="detail-row"><span class="detail-label">Type</span><span class="detail-value" style="text-transform:capitalize">${esc(m.sdn_type || '—')}</span></div>
          <div class="detail-row"><span class="detail-label">Programme</span>
            <span class="detail-value">
              ${(m.program || '').split(/\s+/).filter(Boolean).map(p =>
                `<span class="source-pill" style="background:rgba(245,158,11,.12);color:var(--warning);border-color:rgba(245,158,11,.2)">${esc(p)}</span>`
              ).join(' ') || '—'}
            </span>
          </div>
          ${m.remarks ? `
          <div class="detail-row">
            <span class="detail-label">Remarks</span>
            <span class="detail-value" style="font-size:0.73rem;max-width:220px;text-align:right;line-height:1.4">
              ${esc(m.remarks.substring(0,150))}${m.remarks.length>150?'…':''}
            </span>
          </div>` : ''}
          <div style="margin-top:0.9rem;padding:0.55rem 0.7rem;background:rgba(214,69,69,0.12);
                      border-radius:var(--r-sm);font-size:0.76rem;color:var(--danger);font-weight:600">
            ⚠️ Escalate to Compliance Officer. Do NOT process any transactions for this entity.
          </div>
        </div>`;
    } else {
      resultEl.innerHTML = `
        <div style="background:var(--success-dim);border:2px solid rgba(76,175,80,0.3);
                    border-radius:var(--r-md);padding:1.25rem;text-align:center;animation:msgIn .2s ease">
          <div style="width:44px;height:44px;border-radius:50%;background:rgba(76,175,80,.15);
                      border:2px solid var(--success);display:flex;align-items:center;
                      justify-content:center;margin:0 auto 0.75rem">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="var(--success)" stroke-width="2.5" style="width:20px;height:20px"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
          <div style="color:var(--success);font-weight:700;font-size:0.92rem">✓ No SDN Match</div>
          <div style="color:var(--text-3);font-size:0.79rem;margin-top:0.5rem;line-height:1.5">
            <strong style="color:var(--text-2)">"${esc(name)}"</strong> does not appear on the OFAC SDN list<br>
            at the <strong>${Math.round(threshold*100)}%</strong> similarity threshold.
          </div>
          <div style="margin-top:0.6rem;font-size:0.72rem;color:var(--text-3)">
            Screened against ${total} entries
          </div>
        </div>`;
    }
  } catch (e) {
    resultEl.innerHTML = `
      <div style="background:var(--warning-dim);border:1px solid rgba(245,158,11,.3);
                  border-radius:var(--r-md);padding:1rem;text-align:center">
        <div style="color:var(--warning);font-weight:600;margin-bottom:0.4rem">Screening Error</div>
        <div style="font-size:0.8rem;color:var(--text-3)">${esc(e.message)}</div>
      </div>`;
  }
}

async function triggerOfacRefresh() {
  if (!confirm('Force a full download of the OFAC SDN list now?\n\nThis may take up to 60 seconds.')) return;
  const btn = document.getElementById('ofac-refresh-btn');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Downloading…'; }
  try {
    const data = await API.post('/compliance/ofac/refresh', {});
    const n    = (data.result?.total || data.result?.added || 0).toLocaleString();
    toast(`SDN list refreshed — ${n} entries stored`, 'success', 5000);
    await loadOfacView();
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg> Force Refresh SDN List`;
    }
  }
}

// ─── AI Assistant (RAG Chat) ─────────────────────────────────────────────────
const Chat = { messages: [], isTyping: false, initialized: false };

function initAssistant() {
  if (!Chat.initialized) {
    loadSuggestions();
    loadKbStatus();
    Chat.initialized = true;
  }
  // Focus input
  setTimeout(() => document.getElementById('chat-input')?.focus(), 100);
}

async function loadSuggestions() {
  try {
    const suggestions = await API.get('/assistant/suggestions');
    const container   = document.getElementById('suggestions-container');
    if (!container) return;

    // Group by category
    const groups = {};
    suggestions.forEach(s => {
      if (!groups[s.category]) groups[s.category] = [];
      groups[s.category].push(s.text);
    });

    container.innerHTML = Object.entries(groups).map(([cat, items]) => `
      <div class="suggestion-group">
        <div class="suggestion-cat">${esc(cat)}</div>
        ${items.map(q => `
          <button class="suggestion-btn" onclick="askSuggestion(${JSON.stringify(esc(q))})">${esc(q)}</button>
        `).join('')}
      </div>
    `).join('');
  } catch (e) {
    const container = document.getElementById('suggestions-container');
    if (container) container.innerHTML = `<div style="font-size:0.78rem;color:var(--text-3)">Could not load suggestions.</div>`;
  }
}

async function loadKbStatus() {
  try {
    const data    = await API.get('/assistant/status');
    const details = data.details || {};
    const ok      = data.status === 'operational';
    set('kb-status', ok ? '✓ Connected' : '✗ No API Key');
    set('kb-docs',   details.model          ?? '—');
    set('kb-chunks', details.context_window ?? '—');
    set('kb-model',  details.provider       ?? '—');
    const el = document.getElementById('kb-status');
    if (el) el.className = 'detail-value ' + (ok ? 'text-success' : 'text-danger');
  } catch (e) {
    set('kb-status', 'Error');
  }
}

function askSuggestion(q) {
  const input = document.getElementById('chat-input');
  if (input) { input.value = q; sendMessage(); }
}

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const query = (input?.value || '').trim();
  if (!query || Chat.isTyping) return;

  input.value = '';
  appendMessage('user', query);

  // Show typing indicator
  Chat.isTyping = true;
  showTypingIndicator();

  const btn = document.getElementById('chat-send-btn');
  if (btn) btn.disabled = true;

  try {
    // Build history in Anthropic format (map 'bot' → 'assistant')
    const history = Chat.messages.map(m => ({
      role:    m.role === 'bot' ? 'assistant' : 'user',
      content: m.content,
    }));

    const data = await API.post('/assistant/chat', { query, history });
    hideTypingIndicator();
    appendMessage('bot', data.answer, data.sources, data.confidence, data.intent);

    // Hide confidence bar — Claude API always returns 1.0, no need to display
    const confBar = document.getElementById('chat-confidence-bar');
    if (confBar) confBar.style.display = 'none';
  } catch (e) {
    hideTypingIndicator();
    appendMessage('bot', `⚠️ Error: ${e.message || 'Could not reach assistant.'}`, [], 0, 'error');
  } finally {
    Chat.isTyping = false;
    if (btn) btn.disabled = false;
    input?.focus();
  }
}

function appendMessage(role, content, sources = [], confidence = 0, intent = '') {
  const container = document.getElementById('chat-messages');
  if (!container) return;

  const isBot  = role === 'bot';
  const ts     = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  const mdHtml = isBot ? renderMarkdown(content) : `<p>${esc(content)}</p>`;

  const sourcesHtml = (sources && sources.length)
    ? `<div class="msg-sources">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:11px;height:11px"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        ${sources.map(s => `<span class="source-pill">${esc(s)}</span>`).join('')}
       </div>`
    : '';

  const intentHtml = (intent && intent !== 'general' && intent !== 'greeting' && intent !== 'error' && intent !== 'acknowledgement')
    ? `<span class="intent-tag">${esc(intent.replace('_', ' '))}</span>`
    : '';

  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;
  div.innerHTML = `
    ${isBot ? `<div class="msg-avatar">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
    </div>` : ''}
    <div class="msg-content">
      <div class="msg-bubble">${mdHtml}</div>
      ${sourcesHtml}
      <div class="msg-meta">
        ${isBot ? `FraudGuard AI ${intentHtml} · ` : ''}${ts}
      </div>
    </div>`;

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  Chat.messages.push({ role, content, ts });
}

function renderMarkdown(text) {
  if (!text) return '';
  return text
    // Bold **text**
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    // Italic *text*
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    // Code `text`
    .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
    // Numbered list
    .replace(/^(\d+)\.\s+(.+)$/gm, '<li>$2</li>')
    // Bullet list
    .replace(/^[-•]\s+(.+)$/gm, '<li>$1</li>')
    // Wrap consecutive <li> in <ul>
    .replace(/(<li>[\s\S]*?<\/li>)(?=\s*<li>|$)/g, m => `<ul style="margin:0.4rem 0 0.4rem 1.1rem;line-height:1.75">${m}</ul>`)
    // Double newline → paragraph break
    .replace(/\n\n/g, '</p><p style="margin-top:0.5rem">')
    // Single newline → <br>
    .replace(/\n/g, '<br>')
    // Wrap in paragraph
    .replace(/^(?!<[uop])/, '<p>')
    .replace(/(?<![>])$/, '</p>');
}

function showTypingIndicator() {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  const div = document.createElement('div');
  div.className = 'chat-msg bot';
  div.id = 'typing-indicator';
  div.innerHTML = `
    <div class="msg-avatar">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
    </div>
    <div class="msg-content">
      <div class="msg-bubble">
        <div class="typing-indicator">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function hideTypingIndicator() {
  document.getElementById('typing-indicator')?.remove();
}

function clearChat() {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  Chat.messages = [];
  container.innerHTML = `
    <div class="chat-msg bot">
      <div class="msg-avatar">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
      </div>
      <div class="msg-content">
        <div class="msg-bubble">
          <p>Chat cleared. How can I help you with fraud detection?</p>
        </div>
        <div class="msg-meta">FraudGuard AI · Ready</div>
      </div>
    </div>`;
  const confBar = document.getElementById('chat-confidence-bar');
  if (confBar) confBar.style.display = 'none';
  document.getElementById('chat-input')?.focus();
}




// ─── App Init ─────────────────────────────────────────────────────────────────
function initApp() {
  showView('dashboard');
  populateCustomerDropdown();
  startClock();
}

// ─── Boot ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Inject keyframes
  const style = document.createElement('style');
  style.textContent = `
    @keyframes skeletonPulse {
      0%, 100% { opacity: 0.35; }
      50%       { opacity: 0.7;  }
    }`;
  document.head.appendChild(style);

  // Enter key on login
  document.getElementById('login-password')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') login();
  });
  document.getElementById('login-username')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('login-password')?.focus();
  });

  // ESC closes modal
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

  // Auto-login if token exists
  if (State.token && State.user) {
    document.getElementById('login-page').style.display = 'none';
    document.getElementById('main-app').style.display   = '';
    setUserInfo(State.user);
    initApp();
  }
});

// ═══════════════════════════════════════════════════════════════
// LIVE DEMO
// ═══════════════════════════════════════════════════════════════
const DEMO_SCENARIOS = {
  ofac: {
    customer_id: 'CUST1001', amount: 5000, merchant_name: 'International Transfers LLC',
    location: 'US', card_type: 'credit', device_id: 'DEV-001',
    explain: 'The customer name on this account matches an OFAC SDN entry. The transaction is blocked instantly at Stage 0 before rule or ML scoring.'
  },
  high_amount: {
    customer_id: 'CUST1001', amount: 85000, merchant_name: 'Wire Transfer Corp',
    location: 'RU', card_type: 'credit', device_id: 'UNKNOWN-9x8f',
    explain: 'HIGH_AMOUNT ($85,000), HIGH_RISK_COUNTRY (Russia), ROUND_AMOUNT, and NEW_DEVICE all fire — pushing the combined score above 0.75.'
  },
  velocity: {
    customer_id: 'CUST1001', amount: 950, merchant_name: 'Online Casino',
    location: 'US', card_type: 'credit', device_id: 'DEV-MOB-22',
    explain: 'Rapid repeated transactions trigger HIGH_FREQUENCY and RAPID_SUCCESSION. The combined score lands in the flagged range (0.45–0.75).'
  },
  age: {
    customer_id: 'CUST1002', amount: 200, merchant_name: 'Gaming Store',
    location: 'US', card_type: 'debit', device_id: 'DEV-PC-55',
    explain: 'Customer CUST1002 is under 18. The compliance pre-check blocks the transaction immediately before any scoring occurs.'
  },
  normal: {
    customer_id: 'CUST1003', amount: 42.99, merchant_name: 'Amazon',
    location: 'US', card_type: 'credit', device_id: 'DEV-HOME-01',
    explain: 'A low-value domestic purchase from a known customer with no suspicious signals. All checks pass and the transaction is approved.'
  },
};

let _currentScenario = 'high_amount';

async function initDemo() {
  // Load real customers from the DB so demo scenarios always have a valid customer_id
  try {
    const result = await API.req('/customers?per_page=5');
    if (result && result.customers && result.customers.length > 0) {
      // Use the first available customer for general scenarios
      const firstId = result.customers[0].customer_id;

      // Try to find customers with specific risk traits for the age/normal scenarios
      let youngId  = firstId;   // ideally an under-18 customer (for age scenario)
      let normalId = firstId;   // ideally a low-risk customer (for normal scenario)

      result.customers.forEach(function(c) {
        if (c.age !== undefined && c.age !== null && c.age < 18) youngId = c.customer_id;
        if (c.risk_level === 'low') normalId = c.customer_id;
      });

      // Patch all scenarios with real IDs
      DEMO_SCENARIOS.ofac.customer_id       = firstId;
      DEMO_SCENARIOS.high_amount.customer_id = firstId;
      DEMO_SCENARIOS.velocity.customer_id   = firstId;
      DEMO_SCENARIOS.age.customer_id        = youngId;
      DEMO_SCENARIOS.normal.customer_id     = normalId;
    }
  } catch(e) {
    // If customer load fails, leave the hardcoded IDs — runDemo will report a clear error
    console.warn('Demo: could not load customers —', e.message);
  }
  selectScenario('high_amount');
}

function selectScenario(key) {
  _currentScenario = key;
  const s = DEMO_SCENARIOS[key];
  if (!s) return;
  document.querySelectorAll('.demo-scenario').forEach(el => el.classList.remove('active'));
  const card = document.querySelector('[data-scenario="' + key + '"]');
  if (card) card.classList.add('active');
  document.getElementById('demo-customer-id').value = s.customer_id;
  document.getElementById('demo-amount').value      = s.amount;
  document.getElementById('demo-merchant').value    = s.merchant_name;
  document.getElementById('demo-location').value    = s.location;
  document.getElementById('demo-device').value      = s.device_id;
  const cs = document.getElementById('demo-card-type');
  if (cs) cs.value = s.card_type;
  document.getElementById('demo-explain-text').textContent = s.explain;
  document.getElementById('demo-result').style.display       = 'none';
  document.getElementById('demo-result-empty').style.display = '';
  document.getElementById('demo-loading').style.display      = 'none';
}

async function runDemo() {
  const btn = document.getElementById('demo-run-btn');
  btn.disabled = true;
  document.getElementById('demo-result').style.display       = 'none';
  document.getElementById('demo-result-empty').style.display = 'none';
  document.getElementById('demo-loading').style.display      = '';
  const payload = {
    customer_id:      document.getElementById('demo-customer-id').value.trim(),
    amount:           parseFloat(document.getElementById('demo-amount').value),
    currency:         'USD',
    merchant_name:    document.getElementById('demo-merchant').value.trim(),
    merchant_category:'retail',
    location:         document.getElementById('demo-location').value.trim().toUpperCase(),
    card_type:        document.getElementById('demo-card-type').value,
    transaction_type: 'purchase',
    device_id:        document.getElementById('demo-device').value.trim(),
  };
  try {
    const resp = await API.req('/transactions', { method: 'POST', body: JSON.stringify(payload) });
    document.getElementById('demo-loading').style.display = 'none';
    if (resp) renderDemoResult(resp);
  } catch(e) {
    document.getElementById('demo-loading').style.display      = 'none';
    document.getElementById('demo-result-empty').style.display = '';
    toast('Demo error: ' + e.message, 'error');
  }
  btn.disabled = false;
}

function renderDemoResult(data) {
  const analysis   = data.fraud_analysis || data;
  const status     = (analysis.status || 'unknown').toLowerCase();
  const scores     = analysis.risk_score || {};
  const ruleScore  = scores.rule_score     || 0;
  const mlScore    = scores.ml_score       || 0;
  const combined   = scores.combined_score || 0;
  const riskLevel  = (scores.risk_level    || 'low').toUpperCase();
  const violations = analysis.rule_violations || analysis.violations || [];
  const txId       = data.transaction_id   || data.id || '';

  const banner  = document.getElementById('demo-status-banner');
  const iconEl  = document.getElementById('demo-status-icon');
  const labelEl = document.getElementById('demo-status-label');
  const subEl   = document.getElementById('demo-status-sub');

  banner.className = 'demo-status-banner demo-status-' + status;
  iconEl.innerHTML = status === 'approved'
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="width:22px;height:22px"><polyline points="20 6 9 17 4 12"/></svg>'
    : status === 'flagged'
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="width:22px;height:22px"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="width:22px;height:22px"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>';
  labelEl.textContent = status.toUpperCase();
  subEl.textContent   = txId ? 'TX: ' + String(txId).slice(0,18) + (String(txId).length > 18 ? '...' : '') : '';

  _setBar('demo-bar-rule',     'demo-val-rule',     ruleScore);
  _setBar('demo-bar-ml',       'demo-val-ml',       mlScore);
  _setBar('demo-bar-combined', 'demo-val-combined', combined);

  const rlEl = document.getElementById('demo-risk-level');
  rlEl.textContent = riskLevel;
  rlEl.className   = 'demo-risk-level demo-risk-' + riskLevel.toLowerCase();

  const vContainer = document.getElementById('demo-violations');
  if (violations.length === 0) {
    vContainer.innerHTML = '<div class="demo-violation demo-violation-ok"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="width:13px;height:13px"><polyline points="20 6 9 17 4 12"/></svg> No rules triggered — transaction is clean</div>';
  } else {
    vContainer.innerHTML = violations.map(function(v) {
      return '<div class="demo-violation"><svg viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" style="width:13px;height:13px;flex-shrink:0"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg><strong>' + (v.rule||v.type||'?') + '</strong>: ' + (v.description||v.message||'') + '</div>';
    }).join('');
  }

  const isComplianceBlock = combined >= 1.0 && mlScore === 0 && ruleScore === 0;
  const pipeEl = document.getElementById('demo-pipeline');
  const stages = [
    { name: 'Compliance Pre-Check', skipped: false },
    { name: 'Velocity Count',       skipped: isComplianceBlock },
    { name: 'Rule Engine',          skipped: isComplianceBlock },
    { name: 'ML Scoring',           skipped: isComplianceBlock },
    { name: 'Score Aggregation',    skipped: isComplianceBlock },
    { name: 'Disposition & Alerts', skipped: false },
  ];
  pipeEl.innerHTML = stages.map(function(st) {
    return '<div class="demo-pipe-step ' + (st.skipped ? 'skipped' : 'done') + '">'
      + (st.skipped
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:11px;height:11px"><line x1="5" y1="12" x2="19" y2="12"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="width:11px;height:11px"><polyline points="20 6 9 17 4 12"/></svg>')
      + ' ' + st.name + '</div>';
  }).join('');

  document.getElementById('demo-result').style.display = '';
}

function _setBar(barId, valId, score) {
  const bar = document.getElementById(barId);
  const val = document.getElementById(valId);
  const pct = Math.round(score * 100);
  bar.style.width      = pct + '%';
  bar.style.background = score >= 0.75 ? '#ef4444' : score >= 0.45 ? '#f59e0b' : '#22c55e';
  val.textContent      = pct + '%';
}

// ═══════════════════════════════════════════════════════════════
// LIVE MONITOR
// ═══════════════════════════════════════════════════════════════
let _monitorPoller  = null;
let _monitorSSE     = null;
let _monitorRunning = false;

function initMonitor() {
  if (_monitorRunning) return;
  _monitorRunning = true;
  _startMonitorPolling();
  _loadMonitorThresholds();
}

function _stopMonitor() {
  _monitorRunning = false;
  if (_monitorPoller)  { clearInterval(_monitorPoller); _monitorPoller = null; }
  if (_monitorSSE)     { _monitorSSE.close(); _monitorSSE = null; }
  _setMonitorStatus(false);
}

// Called when user leaves the monitor view
const _origShowView = showView;
(function() {
  const _prev = showView;
  window.showView = function(name) {
    if (name !== 'monitor' && _monitorRunning) _stopMonitor();
    _prev(name);
  };
})();

function _startMonitorPolling() {
  _pollMonitor();
  _monitorPoller = setInterval(_pollMonitor, 4000);
  _setMonitorStatus(true);
}

async function _pollMonitor() {
  try {
    const data = await API.req('/monitor/realtime');
    if (data) _renderMonitorSnapshot(data);

    const evtData = await API.req('/monitor/events?limit=30');
    if (evtData && evtData.events) _renderFeed(evtData.events);
  } catch(e) {
    _setMonitorStatus(false);
  }
}

function _setMonitorStatus(online) {
  const el = document.getElementById('mon-stream-status');
  if (!el) return;
  const dot = el.querySelector('.mon-live-dot');
  if (dot) {
    dot.className = 'mon-live-dot ' + (online ? 'online' : 'offline');
  }
  el.innerHTML = (online
    ? '<span class="mon-live-dot online"></span> Live'
    : '<span class="mon-live-dot offline"></span> Offline');
  if (online) {
    const luEl = document.getElementById('mon-last-updated');
    if (luEl) luEl.textContent = 'Updated ' + new Date().toLocaleTimeString();
  }
}

function _renderMonitorSnapshot(data) {
  const tp  = data.throughput         || {};
  const out = data.outcomes_last_1hr  || {};

  _setText('mon-tx-rate',   tp.rate_per_min  !== undefined ? tp.rate_per_min.toFixed(1) : '0.0');
  _setText('mon-total',     out.total    !== undefined ? out.total    : '0');
  _setText('mon-blocked',   out.blocked  !== undefined ? out.blocked  : '0');
  _setText('mon-flagged',   out.flagged  !== undefined ? out.flagged  : '0');
  _setText('mon-approved',  out.approved !== undefined ? out.approved : '0');
  _setText('mon-block-rate', out.block_rate !== undefined ? (out.block_rate * 100).toFixed(1) + '% of total' : '0% of total');
  _setText('mon-flag-rate',  out.flag_rate  !== undefined ? (out.flag_rate  * 100).toFixed(1) + '% of total' : '0% of total');

  const amt = data.amount_last_1hr || 0;
  _setText('mon-amount', amt >= 1000000
    ? '$' + (amt/1000000).toFixed(1) + 'M'
    : amt >= 1000 ? '$' + (amt/1000).toFixed(1) + 'K'
    : '$' + amt.toFixed(0));

  // System alerts
  const alerts = data.system_alerts || [];
  const alertEl = document.getElementById('mon-sys-alerts');
  if (alertEl) {
    if (alerts.length === 0) {
      alertEl.innerHTML = '<span style="color:var(--success)">✓ No system alerts — all thresholds within normal range.</span>';
    } else {
      alertEl.innerHTML = alerts.map(function(a) {
        return '<div class="mon-sys-alert"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:13px;height:13px;flex-shrink:0;color:var(--danger)"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/></svg>'
          + '<strong>' + a.type + '</strong>: ' + a.message + '</div>';
      }).join('');
    }
    // Flash nav badge
    const badge = document.getElementById('nav-monitor-badge');
    if (badge) badge.style.display = alerts.length > 0 ? '' : 'none';
  }

  // Network
  const net = data.network || {};
  const netEl = document.getElementById('mon-network');
  if (netEl) {
    const sharedDevices = (net.top_shared_devices || []);
    const sharedIPs     = (net.top_shared_ips     || []);
    let html = '<div class="mon-net-stat"><div class="mon-net-val ' + (net.shared_devices > 0 ? 'danger' : '') + '">'
      + (net.shared_devices || 0) + '</div><div class="mon-net-lbl">Shared Devices</div></div>'
      + '<div class="mon-net-stat"><div class="mon-net-val ' + (net.shared_ips > 0 ? 'warn' : '') + '">'
      + (net.shared_ips || 0) + '</div><div class="mon-net-lbl">Shared IPs</div></div>';

    if (sharedDevices.length > 0) {
      html += '<div class="mon-net-section">Top Shared Devices</div>';
      html += sharedDevices.map(function(d) {
        return '<div class="mon-net-row"><span class="mon-net-key">' + d.device + '</span>'
          + '<span class="mon-net-badge danger">' + d.customers + ' accounts</span></div>';
      }).join('');
    }
    if (sharedIPs.length > 0) {
      html += '<div class="mon-net-section">Top Shared IPs</div>';
      html += sharedIPs.map(function(ip) {
        return '<div class="mon-net-row"><span class="mon-net-key">' + ip.ip + '</span>'
          + '<span class="mon-net-badge warn">' + ip.customers + ' accounts</span></div>';
      }).join('');
    }
    if (!sharedDevices.length && !sharedIPs.length) {
      html += '<div style="color:var(--text-3);font-size:0.8rem;padding:0.75rem">No shared infrastructure detected.</div>';
    }
    netEl.innerHTML = html;
  }
}

function _renderFeed(events) {
  const feed = document.getElementById('mon-feed');
  if (!feed) return;
  if (!events || !events.length) {
    feed.innerHTML = '<div class="mon-feed-empty">No transactions yet. Run the <strong>Demo</strong> or submit a transaction — events appear here in real time.</div>';
    return;
  }
  feed.innerHTML = events.slice(0, 25).map(function(e) {
    const statusClass = e.status === 'blocked' ? 'feed-blocked'
                      : e.status === 'flagged'  ? 'feed-flagged'
                      : 'feed-approved';
    // Show local time (convert from UTC ISO string)
    let ts = '—';
    if (e.ts) {
      try { ts = new Date(e.ts + 'Z').toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'}); }
      catch(_) { ts = e.ts.slice(11, 19); }
    }
    const hits = e.threshold_hits || 0;
    const scoreVal = ((e.combined_score||0)*100).toFixed(0);
    const scoreColor = e.combined_score >= 0.75 ? 'var(--danger)' : e.combined_score >= 0.45 ? 'var(--warning)' : 'var(--success)';
    return '<div class="mon-feed-row ' + statusClass + '">'
      + '<span class="mon-feed-time">' + ts + '</span>'
      + '<span class="mon-feed-cust">' + (e.customer_id || '?') + '</span>'
      + '<span class="mon-feed-amt">$' + (e.amount || 0).toLocaleString(undefined, {maximumFractionDigits:0}) + '</span>'
      + '<span class="mon-feed-score" style="color:' + scoreColor + ';font-weight:600">' + scoreVal + '%</span>'
      + '<span class="mon-feed-status ' + statusClass + '">' + (e.status||'?').toUpperCase() + '</span>'
      + (hits > 0 ? '<span class="mon-feed-hits">⚡' + hits + '</span>' : '<span></span>')
      + '</div>';
  }).join('');
}

async function _loadMonitorThresholds() {
  try {
    const data = await API.req('/monitor/thresholds');
    if (!data) return;
    const el = document.getElementById('mon-thresholds');
    if (!el) return;
    const groups = [
      ['score_thresholds',    'Score Thresholds'],
      ['velocity_thresholds', 'Velocity Thresholds'],
      ['network_thresholds',  'Network Thresholds'],
      ['system_thresholds',   'System Thresholds'],
    ];
    el.innerHTML = groups.map(function(g) {
      const group = data[g[0]] || {};
      return '<div class="mon-th-group">'
        + '<div class="mon-th-group-title">' + g[1] + '</div>'
        + Object.entries(group).map(function(entry) {
            return '<div class="mon-th-row">'
              + '<span class="mon-th-key">' + entry[0] + '</span>'
              + '<span class="mon-th-val">' + entry[1].value + '</span>'
              + '<span class="mon-th-desc">' + entry[1].description + '</span>'
              + '</div>';
          }).join('')
        + '</div>';
    }).join('');
  } catch(e) {}
}

function _setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
