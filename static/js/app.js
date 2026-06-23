/**
 * Reputation Agent Frontend — Lazy-loaded & responsive
 */

const API = '';
let ws = null;
let chartInstance = null;
let analyticsCharts = {};
let currentPage = 'dashboard';
let state = { campaigns: [], accounts: [], templates: [], queue: [], logs: [], latest_scores: [], settings: {} };
const pageLoaded = {};

// ===== CLIENT-SIDE CACHE =====
function cacheKey(name) { return 'ra_cache_' + name; }
function cacheGet(name) {
    try {
        const raw = localStorage.getItem(cacheKey(name));
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        // Ignore cache older than 10 minutes
        if (Date.now() - parsed.ts > 10 * 60 * 1000) return null;
        return parsed.data;
    } catch (e) { return null; }
}
function cacheSet(name, data) {
    try { localStorage.setItem(cacheKey(name), JSON.stringify({ ts: Date.now(), data })); } catch (e) {}
}

// ===== INIT =====
document.addEventListener('DOMContentLoaded', async () => {
    try {
        await api('GET', '/api/auth/me');
        initApp();
    } catch (e) {
        window.location.href = '/login';
    }
});

async function initApp() {
    initNav();
    initButtons();
    initForms();
    initChart();
    await loadBootstrap();
    loadPage('dashboard');
    connectWS();
}

async function loadBootstrap() {
    try {
        const data = await api('GET', '/api/bootstrap');
        state.accounts = data.accounts || [];
        state.campaigns = data.campaigns || [];
        state.templates = data.templates || [];
        state.stats = data.stats || {};
        state.logs = data.logs || [];
        state.latest_scores = data.reputation || [];
        state.settings = data.settings || {};
        cacheSet('accounts', state.accounts);
        cacheSet('campaigns', { campaigns: state.campaigns, accounts: state.accounts, templates: state.templates });
        cacheSet('templates', state.templates);
        cacheSet('dashboard', { stats: state.stats, logs: state.logs, latest_scores: state.latest_scores });
        cacheSet('settings', state.settings);
    } catch (e) {
        console.error('bootstrap failed', e);
    }
}

// ===== API =====
async function api(method, path, body = null) {
    const opts = { method, headers: {} };
    if (body) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
    }
    const res = await fetch(`${API}${path}`, opts);
    if (res.status === 401) {
        window.location.href = '/login';
        throw new Error('Unauthorized');
    }
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

// ===== NAVIGATION =====
function initNav() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            switchPage(link.dataset.page);
        });
    });
    document.getElementById('logout-btn').addEventListener('click', async () => {
        await api('POST', '/api/auth/logout');
        window.location.href = '/login';
    });
}

function switchPage(page) {
    currentPage = page;
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    document.querySelector(`.nav-link[data-page="${page}"]`).classList.add('active');
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(`page-${page}`).classList.add('active');
    document.getElementById('page-title').textContent = page.charAt(0).toUpperCase() + page.slice(1);
    loadPage(page);
}

function renderPageFromCache(page) {
    if (page === 'dashboard') {
        const cached = cacheGet('dashboard');
        if (cached) updateDashboard(cached);
    } else if (page === 'campaigns') {
        const cached = cacheGet('campaigns');
        if (cached) {
            updateCampaignsGrid(cached.campaigns);
            populateCampaignFormSelects();
        }
    } else if (page === 'accounts') {
        const cached = cacheGet('accounts');
        if (cached) updateAccountsTable(cached);
    } else if (page === 'templates') {
        const cached = cacheGet('templates');
        if (cached) updateTemplatesTable(cached);
    } else if (page === 'queue') {
        const cached = cacheGet('queue');
        if (cached) updateQueueTable(cached);
    } else if (page === 'settings') {
        const cached = cacheGet('settings');
        if (cached) populateSettingsForm(cached);
    }
}

async function loadPage(page) {
    setPageLoading(page, true);
    renderPageFromCache(page);
    try {
        if (page === 'dashboard') await loadDashboard();
        else if (page === 'campaigns') await loadCampaigns();
        else if (page === 'accounts') await loadAccounts();
        else if (page === 'templates') await loadTemplates();
        else if (page === 'queue') await loadQueue();
        else if (page === 'analytics') await renderAnalytics();
        else if (page === 'settings') await loadSettings();
        pageLoaded[page] = true;
    } catch (e) {
        toast(e.message, 'error');
    } finally {
        setPageLoading(page, false);
    }
}

function setPageLoading(page, loading) {
    const content = document.getElementById(`page-${page}`);
    if (!content) return;
    content.classList.toggle('page-loading', loading);
}

// ===== LIVE UPDATES =====
// Refresh only the currently visible page every 30 seconds.
function connectWS() {
    const badge = document.getElementById('ws-status');
    badge.textContent = 'Live';
    badge.className = 'badge badge-green';
    setInterval(async () => {
        // Don't hammer the server when the tab is in the background.
        if (document.hidden) return;
        try {
            await loadPage(currentPage);
            badge.textContent = 'Live';
            badge.className = 'badge badge-green';
        } catch (e) {
            badge.textContent = 'Disconnected';
            badge.className = 'badge badge-red';
        }
    }, 60000);
}

// ===== DASHBOARD =====
async function loadDashboard() {
    const [stats, logs, scores] = await Promise.all([
        api('GET', '/api/stats').catch(() => ({})),
        api('GET', '/api/logs?limit=100').catch(() => []),
        api('GET', '/api/reputation').catch(() => []),
    ]);
    state.stats = stats;
    state.logs = logs;
    state.latest_scores = scores;
    const payload = { stats, logs, latest_scores: scores };
    cacheSet('dashboard', payload);
    updateDashboard(payload);
}

function updateDashboard(data) {
    if (data.stats) {
        setStat('stat-campaigns', data.stats.campaigns);
        setStat('stat-accounts', data.stats.accounts);
        setStat('stat-pending', data.stats.pending);
        setStat('stat-sent', data.stats.sent);
        setStat('stat-moved', data.stats.moved);
        setStat('stat-replied', data.stats.replied);
        setStat('stat-sent-today', data.stats.sent_today || 0);
        setStat('stat-sent-week', data.stats.sent_this_week || 0);
        updateScoreCircle(data.stats.avg_score || 0);
    }
    if (data.logs) updateLogs(data.logs);
    if (data.latest_scores) updateChart(data.latest_scores);
}

function setStat(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.textContent !== String(val)) {
        el.textContent = val;
        el.style.transform = 'scale(1.2)';
        setTimeout(() => el.style.transform = 'scale(1)', 180);
    }
}

function updateScoreCircle(score) {
    const numberEl = document.getElementById('score-number');
    const circle = document.getElementById('score-circle');
    if (!numberEl || !circle) return;
    numberEl.textContent = Math.round(score);
    const c = 314;
    circle.style.strokeDasharray = c;
    circle.style.strokeDashoffset = c - (score / 100) * c;
    circle.style.stroke = score >= 80 ? '#22c55e' : score >= 50 ? '#f59e0b' : '#ef4444';
}

function updateLogs(logs) {
    const container = document.getElementById('log-container');
    if (!container) return;
    if (!logs || !logs.length) {
        container.innerHTML = '<div class="log-entry empty">Waiting for activity...</div>';
        return;
    }
    container.innerHTML = logs.slice(0, 40).map(l => `
        <div class="log-entry">
            <span class="log-time">${fmtTimeShort(l.created_at)}</span>
            <span class="log-level ${l.level}">${l.level}</span>
            <span class="log-msg">${esc(l.message)}</span>
        </div>
    `).join('');
    container.scrollTop = 0;
}

// ===== CHARTS =====
function initChart() {
    const ctx = document.getElementById('reputationChart');
    if (!ctx) return;
    Chart.defaults.color = '#8b92a8';
    Chart.defaults.font.family = 'Inter';
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { font: { size: 11 } } },
                y: { grid: { color: 'rgba(255,255,255,0.03)' }, beginAtZero: true, max: 100, ticks: { font: { size: 11 } } }
            }
        }
    });
}

function updateChart(scores) {
    if (!chartInstance || !scores) return;
    const labels = scores.map(s => s.date ? s.date.slice(5) : '');
    const data = scores.map(s => s.score || 0);
    chartInstance.data.labels = labels;
    chartInstance.data.datasets = [{
        label: 'Avg Reputation Score',
        data,
        borderColor: '#6366f1',
        backgroundColor: 'rgba(99,102,241,0.1)',
        borderWidth: 2, fill: true, tension: 0.4,
        pointRadius: 3, pointHoverRadius: 6,
        pointBackgroundColor: '#6366f1', pointBorderColor: '#fff', pointBorderWidth: 2
    }];
    chartInstance.update('none');
}

// ===== CAMPAIGNS =====
async function loadCampaigns() {
    const [campaigns, accounts, templates] = await Promise.all([
        api('GET', '/api/campaigns').catch(() => []),
        api('GET', '/api/accounts').catch(() => []),
        api('GET', '/api/templates').catch(() => []),
    ]);
    state.campaigns = campaigns;
    state.accounts = accounts;
    state.templates = templates;
    cacheSet('campaigns', { campaigns, accounts, templates });
    updateCampaignsGrid(campaigns);
    populateCampaignFormSelects();
}

function updateCampaignsGrid(campaigns) {
    const grid = document.getElementById('campaigns-grid');
    if (!grid) return;
    if (!campaigns || !campaigns.length) {
        grid.innerHTML = '<div class="card" style="padding:30px;text-align:center;color:var(--text-dim)">No campaigns yet. Create one to start warming up.</div>';
        return;
    }
    grid.innerHTML = campaigns.map(c => `
        <div class="campaign-card">
            <div class="campaign-card-header">
                <div><h3>${esc(c.name)}</h3><span class="badge ${c.status === 'active' ? 'badge-green' : 'badge-yellow'}">${c.status}</span></div>
            </div>
            <div class="campaign-card-meta">
                <p><strong>Domain:</strong> ${esc(c.domain_name)}</p>
                <p><strong>Sender:</strong> ${esc(c.sender_email || '-')}</p>
                <p><strong>Template:</strong> ${esc(c.template_name || 'Default')}</p>
                <p><strong>Peers:</strong> ${c.peer_count} · <strong>Target:</strong> ${c.daily_target}/day</p>
            </div>
            <div class="campaign-card-actions">
                <button class="btn btn-sm ${c.status === 'active' ? 'btn-secondary' : 'btn-primary'}" onclick="toggleCampaign(${c.id}, '${c.status === 'active' ? 'paused' : 'active'}')">${c.status === 'active' ? 'Pause' : 'Activate'}</button>
                <button class="btn btn-sm btn-secondary" onclick="runCampaignTick(${c.id})">Tick</button>
                <button class="btn btn-sm btn-danger" onclick="deleteCampaign(${c.id})">Delete</button>
            </div>
        </div>
    `).join('');
}

async function toggleCampaign(id, status) {
    try { await api('PATCH', `/api/campaigns/${id}`, { status }); toast(`Campaign ${status}`, 'success'); loadCampaigns(); }
    catch (e) { toast(e.message, 'error'); }
}

async function runCampaignTick(id) {
    try { await api('POST', `/api/campaigns/${id}/tick`); toast('Campaign tick queued', 'info'); }
    catch (e) { toast(e.message, 'error'); }
}

async function deleteCampaign(id) {
    if (!confirm('Delete this campaign?')) return;
    try { await api('DELETE', `/api/campaigns/${id}`); toast('Campaign deleted', 'info'); loadCampaigns(); }
    catch (e) { toast(e.message, 'error'); }
}

// ===== ACCOUNTS =====
async function loadAccounts() {
    const accounts = await api('GET', '/api/accounts').catch(() => []);
    state.accounts = accounts;
    cacheSet('accounts', accounts);
    updateAccountsTable(accounts);
}

function updateAccountsTable(accounts) {
    const tbody = document.getElementById('accounts-table');
    if (!tbody) return;
    if (!accounts || !accounts.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">No accounts connected</td></tr>';
        return;
    }
    tbody.innerHTML = accounts.map(a => `
        <tr>
            <td><strong>${esc(a.email)}</strong></td>
            <td><span class="badge ${a.role === 'sender' ? 'badge-blue' : ''}">${a.role}</span></td>
            <td>
                <div style="display:flex;align-items:center;gap:8px">
                    <div style="width:60px;height:6px;background:var(--border);border-radius:3px;overflow:hidden">
                        <div style="width:${a.health_score}%;height:100%;background:${healthColor(a.health_score)}"></div>
                    </div>
                    <span>${a.health_score}</span>
                </div>
            </td>
            <td><span class="badge ${a.status === 'active' ? 'badge-green' : 'badge-red'}">${a.status}</span></td>
            <td>${a.last_check ? fmtTime(a.last_check) : '-'}</td>
            <td>
                <button class="btn btn-sm btn-secondary" onclick="editAccount(${a.id})">Edit</button>
                <button class="btn btn-sm btn-secondary" onclick="checkAccount(${a.id})">Check</button>
                <button class="btn btn-sm btn-outline" onclick="deleteAccount(${a.id})">Delete</button>
            </td>
        </tr>
    `).join('');
}

function healthColor(score) {
    return score >= 80 ? '#22c55e' : score >= 50 ? '#f59e0b' : '#ef4444';
}

async function checkAccount(id) {
    try {
        const res = await api('POST', `/api/accounts/${id}/check`);
        toast(res.healthy ? 'Account healthy' : `Unhealthy: ${res.error || 'unknown'}`, res.healthy ? 'success' : 'error');
        loadAccounts();
    } catch (e) { toast(e.message, 'error'); }
}

async function deleteAccount(id) {
    if (!confirm('Delete this account?')) return;
    try { await api('DELETE', `/api/accounts/${id}`); toast('Account deleted', 'info'); loadAccounts(); }
    catch (e) { toast(e.message, 'error'); }
}

async function updateAccountPassword(id) {
    const password = prompt('Enter the new app password for this sender:');
    if (!password) return;
    try {
        await api('PATCH', `/api/accounts/${id}`, { password });
        toast('Password updated', 'success');
        loadAccounts();
    } catch (e) { toast(e.message, 'error'); }
}

function editAccount(id) {
    const account = state.accounts.find(a => a.id === id);
    if (!account) return;
    document.getElementById('account-edit-id').value = account.id;
    document.getElementById('account-edit-email').value = account.email;
    document.getElementById('account-edit-provider').value = account.provider || 'zoho';
    document.getElementById('account-edit-role').value = account.role;
    document.getElementById('account-edit-status').value = account.status || 'active';
    document.getElementById('account-edit-password').value = '';
    const pwGroup = document.getElementById('account-edit-password-group');
    if (pwGroup) pwGroup.style.display = account.role === 'sender' ? 'block' : 'none';
    openModal('account-edit-modal');
}

// ===== TEMPLATES =====
async function loadTemplates() {
    const templates = await api('GET', '/api/templates').catch(() => []);
    state.templates = templates;
    cacheSet('templates', templates);
    updateTemplatesTable(templates);
}

function updateTemplatesTable(templates) {
    const tbody = document.getElementById('templates-table');
    if (!tbody) return;
    if (!templates || !templates.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">No templates</td></tr>';
        return;
    }
    tbody.innerHTML = templates.map(t => `
        <tr>
            <td><strong>${esc(t.name)}</strong></td>
            <td>${esc(t.subject_template)}</td>
            <td>${esc(t.variables_json || '-')}</td>
            <td>${t.is_default ? '<span class="badge badge-green">Yes</span>' : '-'}</td>
            <td><button class="btn btn-sm btn-outline" onclick="deleteTemplate(${t.id})">Delete</button></td>
        </tr>
    `).join('');
}

async function deleteTemplate(id) {
    if (!confirm('Delete this template?')) return;
    try { await api('DELETE', `/api/templates/${id}`); toast('Template deleted', 'info'); loadTemplates(); }
    catch (e) { toast(e.message, 'error'); }
}

async function previewTemplate() {
    const fd = new FormData(document.getElementById('template-form'));
    try {
        const res = await api('POST', '/api/templates/preview', {
            subject_template: fd.get('subject_template'),
            body_template: fd.get('body_template'),
            reply_template: fd.get('reply_template'),
            variables_json: fd.get('variables_json')
        });
        const box = document.getElementById('template-preview');
        box.classList.remove('hidden');
        box.innerHTML = `<h4>Preview</h4><p><strong>Subject:</strong> ${esc(res.subject)}</p><p><strong>Body:</strong><br>${esc(res.body)}</p><p><strong>Reply:</strong><br>${esc(res.reply)}</p>`;
    } catch (e) { toast(e.message, 'error'); }
}

// ===== QUEUE =====
async function loadQueue(status = null) {
    const path = status ? `/api/sends?status=${status}&limit=100` : '/api/sends?limit=100';
    try {
        const jobs = await api('GET', path);
        state.queue = jobs;
        cacheSet('queue', jobs);
        updateQueueTable(jobs);
    } catch (e) { toast(e.message, 'error'); }
}

function updateQueueTable(jobs) {
    const tbody = document.getElementById('queue-table');
    if (!tbody) return;
    if (!jobs || !jobs.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">No queue jobs</td></tr>';
        return;
    }
    tbody.innerHTML = jobs.slice(0, 100).map(j => `
        <tr>
            <td>${esc(j.campaign_name || '-')}</td>
            <td>${esc(j.from_email || '-')}</td>
            <td>${esc(j.to_email || '-')}</td>
            <td>${esc(j.subject || '-')}</td>
            <td><span class="badge ${statusBadge(j.status)}">${j.status}</span></td>
            <td>${j.retry_count}</td>
            <td>${j.sent_at ? fmtTime(j.sent_at) : fmtTime(j.scheduled_at)}</td>
        </tr>
    `).join('');
}

function statusBadge(status) {
    if (status === 'sent') return 'badge-green';
    if (status === 'pending') return 'badge-blue';
    if (status === 'failed') return 'badge-red';
    if (status === 'running') return 'badge-yellow';
    return '';
}

async function retryFailed() {
    try { await api('POST', '/api/sends/retry-failed'); toast('Failed jobs retried', 'success'); loadQueue(); }
    catch (e) { toast(e.message, 'error'); }
}

async function clearPending() {
    if (!confirm('Delete all pending emails?')) return;
    try { await api('POST', '/api/sends/clear-pending'); toast('Pending emails cleared', 'info'); loadQueue(); }
    catch (e) { toast(e.message, 'error'); }
}

// ===== ANALYTICS =====
async function renderAnalytics() {
    const grid = document.getElementById('analytics-grid');
    if (!grid) return;
    if (!state.campaigns || !state.campaigns.length) {
        grid.innerHTML = '<div class="card" style="padding:30px;text-align:center;color:var(--text-dim)">Create campaigns to see analytics</div>';
        return;
    }
    grid.innerHTML = '';
    for (const c of state.campaigns) {
        try {
            const history = await api('GET', `/api/reputation/${c.id}?days=30`);
            const card = document.createElement('div');
            card.className = 'analytics-card';
            card.innerHTML = `<h3>${esc(c.name)} <span style="font-size:0.8rem;color:var(--text-muted);font-weight:400">${esc(c.domain_name)}</span></h3><div class="analytics-chart"><canvas id="chart-campaign-${c.id}"></canvas></div>`;
            grid.appendChild(card);
            renderCampaignChart(c.id, history);
        } catch (e) {}
    }
}

function renderCampaignChart(campaignId, history) {
    const ctx = document.getElementById(`chart-campaign-${campaignId}`);
    if (!ctx) return;
    if (analyticsCharts[campaignId]) analyticsCharts[campaignId].destroy();
    analyticsCharts[campaignId] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: history.map(h => h.date.slice(5)),
            datasets: [{
                label: 'Score',
                data: history.map(h => h.score),
                borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,0.1)',
                borderWidth: 2, fill: true, tension: 0.4, pointRadius: 2
            }, {
                label: 'Inbox %',
                data: history.map(h => h.inbox_rate),
                borderColor: '#22c55e', backgroundColor: 'transparent',
                borderWidth: 2, tension: 0.4, pointRadius: 2, borderDash: [4, 4]
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { labels: { boxWidth: 12, font: { size: 11 } } } },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 10 } } },
                y: { grid: { color: 'rgba(255,255,255,0.03)' }, beginAtZero: true, max: 100, ticks: { font: { size: 10 } } }
            }
        }
    });
}

// ===== SETTINGS =====
async function loadSettings() {
    const [settings, campaigns, accounts, templates] = await Promise.all([
        api('GET', '/api/settings').catch(() => ({})),
        api('GET', '/api/campaigns').catch(() => []),
        api('GET', '/api/accounts').catch(() => []),
        api('GET', '/api/templates').catch(() => []),
    ]);
    state.settings = settings;
    state.campaigns = campaigns;
    state.accounts = accounts;
    state.templates = templates;
    cacheSet('settings', settings);
    cacheSet('campaigns', { campaigns, accounts, templates });
    populateSettingsForm(settings);
    populateCampaignFormSelects();
}

function populateCampaignFormSelects() {
    const senderSelect = document.getElementById('campaign-sender-select');
    const templateSelect = document.getElementById('campaign-template-select');
    const peerSelect = document.getElementById('campaign-peer-select');
    if (!senderSelect || !templateSelect || !peerSelect) return;
    const senders = state.accounts.filter(a => a.role === 'sender');
    const peers = state.accounts.filter(a => a.role === 'peer');
    senderSelect.innerHTML = senders.map(s => `<option value="${s.id}">${esc(s.email)}</option>`).join('') || '<option disabled>No sender</option>';
    templateSelect.innerHTML = state.templates.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join('') || '<option value="">Default</option>';
    peerSelect.innerHTML = peers.map(p => `<option value="${p.id}">${esc(p.email)}</option>`).join('') || '<option disabled>No peers</option>';
}

function populateSettingsForm(settings) {
    if (!settings) return;
    const form = document.getElementById('settings-form');
    if (!form) return;
    for (const [k, v] of Object.entries(settings)) {
        const input = form.querySelector(`[name="${k}"]`);
        if (input) input.value = v;
    }
}

// ===== FORMS & MODALS =====
function initForms() {
    document.getElementById('campaign-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const peerSelect = document.getElementById('campaign-peer-select');
        const peers = Array.from(peerSelect.selectedOptions).map(o => parseInt(o.value));
        try {
            await api('POST', '/api/campaigns', {
                name: fd.get('name'),
                domain_name: fd.get('domain_name'),
                sender_account_id: parseInt(fd.get('sender_account_id')),
                template_id: parseInt(fd.get('template_id')) || null,
                peer_account_ids: peers,
                daily_target: parseInt(fd.get('daily_target')),
                ramp_weeks: parseInt(fd.get('ramp_weeks')),
                tick_interval: parseInt(fd.get('tick_interval')),
                active_start: parseInt(fd.get('active_start')),
                active_end: parseInt(fd.get('active_end')),
                timezone: fd.get('timezone'),
            });
            toast('Campaign created', 'success');
            closeModal('campaign-modal');
            e.target.reset();
            loadPage('campaigns');
        } catch (err) { toast(err.message, 'error'); }
    });

    const accountRoleSelect = document.getElementById('account-role-select');
    const accountPasswordGroup = document.getElementById('account-password-group');
    function toggleAccountPassword() {
        if (accountRoleSelect && accountPasswordGroup) {
            accountPasswordGroup.style.display = accountRoleSelect.value === 'sender' ? 'block' : 'none';
        }
    }
    if (accountRoleSelect) {
        accountRoleSelect.addEventListener('change', toggleAccountPassword);
        toggleAccountPassword();
    }

    document.getElementById('account-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const role = fd.get('role');
        const password = fd.get('password');
        if (role === 'sender' && !password) {
            toast('Sender accounts require an app password', 'error');
            return;
        }
        try {
            await api('POST', '/api/accounts', {
                email: fd.get('email'),
                password: role === 'sender' ? password : '',
                role: role,
                provider: fd.get('provider') || 'zoho'
            });
            toast('Account added', 'success');
            closeModal('account-modal');
            e.target.reset();
            toggleAccountPassword();
            loadPage('accounts');
        } catch (err) { toast(err.message, 'error'); }
    });

    const accountEditForm = document.getElementById('account-edit-form');
    if (accountEditForm) {
        accountEditForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fd = new FormData(e.target);
            const id = fd.get('id');
            const payload = { status: fd.get('status') };
            const password = fd.get('password');
            if (password) payload.password = password;
            try {
                await api('PATCH', `/api/accounts/${id}`, payload);
                toast('Profile saved', 'success');
                closeModal('account-edit-modal');
                loadPage('accounts');
            } catch (err) { toast(err.message, 'error'); }
        });
    }

    document.getElementById('template-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
            await api('POST', '/api/templates', {
                name: fd.get('name'),
                subject_template: fd.get('subject_template'),
                body_template: fd.get('body_template'),
                reply_template: fd.get('reply_template'),
                variables_json: fd.get('variables_json')
            });
            toast('Template saved', 'success');
            closeModal('template-modal');
            e.target.reset();
            document.getElementById('template-preview').classList.add('hidden');
            loadPage('templates');
        } catch (err) { toast(err.message, 'error'); }
    });

    document.getElementById('settings-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
            await api('POST', '/api/settings', {
                tick_interval_minutes: parseInt(fd.get('tick_interval_minutes')),
                active_hours_start: parseInt(fd.get('active_hours_start')),
                active_hours_end: parseInt(fd.get('active_hours_end')),
                move_probability: parseFloat(fd.get('move_probability')),
                open_probability: parseFloat(fd.get('open_probability')),
                reply_probability: parseFloat(fd.get('reply_probability')),
            });
            toast('Settings saved', 'success');
        } catch (err) { toast(err.message, 'error'); }
    });

    const setupWarmupForm = document.getElementById('setup-warmup-form');
    if (setupWarmupForm) {
        setupWarmupForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fd = new FormData(e.target);
            const btn = e.target.querySelector('button[type="submit"]');
            btn.disabled = true;
            btn.textContent = 'Setting up...';
            try {
                const res = await api('POST', '/api/setup/warmup', {
                    sender_app_password: fd.get('sender_app_password'),
                    daily_target: parseInt(fd.get('daily_target')),
                    ramp_weeks: parseInt(fd.get('ramp_weeks')),
                    tick_interval: 5,
                    active_start: parseInt(fd.get('active_start')),
                    active_end: parseInt(fd.get('active_end')),
                    timezone: fd.get('timezone'),
                    tick_now: fd.get('tick_now') === 'on',
                    overwrite_passwords: fd.get('overwrite_passwords') === 'on',
                });
                toast(`Created ${res.campaigns_created} campaign(s) using ${res.peers_used} peer(s)`, 'success');
                closeModal('setup-warmup-modal');
                e.target.reset();
                loadPage('campaigns');
            } catch (err) { toast(err.message, 'error'); }
            finally {
                btn.disabled = false;
                btn.textContent = 'Setup & Send';
            }
        });
    }
}

function initButtons() {
    document.getElementById('btn-bulk-send').addEventListener('click', async () => {
        const btn = document.getElementById('btn-bulk-send');
        btn.disabled = true;
        try {
            const res = await api('POST', '/api/sends/bulk?limit=100');
            toast(`Bulk send complete: ${res.queued} queued, ${res.sent} sent`, 'success');
        } catch (e) { toast(e.message, 'error'); }
        finally { btn.disabled = false; }
    });

    document.getElementById('btn-process-queue').addEventListener('click', async () => {
        try { await api('POST', '/api/sends/process?limit=10'); toast('Queue processing started', 'info'); }
        catch (e) { toast(e.message, 'error'); }
    });
}

// ===== MODAL HELPERS =====
function openModal(id) {
    document.getElementById(id).classList.add('active');
    if (id === 'campaign-modal') {
        Promise.all([
            state.accounts.length ? Promise.resolve(state.accounts) : api('GET', '/api/accounts').catch(() => []),
            state.templates.length ? Promise.resolve(state.templates) : api('GET', '/api/templates').catch(() => []),
        ]).then(([accounts, templates]) => {
            state.accounts = accounts;
            state.templates = templates;
            populateCampaignFormSelects();
        });
    }
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

// ===== UTILS =====
function esc(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
}

function fmtTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'));
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function fmtTimeShort(iso) {
    if (!iso) return '-';
    const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'));
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function toast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(100%)'; setTimeout(() => el.remove(), 300); }, 3500);
}

// Expose globals for inline onclick
window.openModal = openModal;
window.closeModal = closeModal;
window.toggleCampaign = toggleCampaign;
window.runCampaignTick = runCampaignTick;
window.deleteCampaign = deleteCampaign;
window.checkAccount = checkAccount;
window.deleteAccount = deleteAccount;
window.deleteTemplate = deleteTemplate;
window.previewTemplate = previewTemplate;
window.loadQueue = loadQueue;
window.retryFailed = retryFailed;
