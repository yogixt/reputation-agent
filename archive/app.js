/**
 * Reputation Agent Frontend
 */

const API_BASE = '';
let ws = null;
let reconnectTimer = null;
let chartInstance = null;
let currentPage = 'dashboard';

// ===== INIT =====
document.addEventListener('DOMContentLoaded', () => {
    initNav();
    initForms();
    initButtons();
    initChart();
    loadAllData();
    connectWS();
});

// ===== NAVIGATION =====
function initNav() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const page = link.dataset.page;
            switchPage(page);
        });
    });
}

function switchPage(page) {
    currentPage = page;
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    document.querySelector(`.nav-link[data-page="${page}"]`).classList.add('active');
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(`page-${page}`).classList.add('active');
    document.getElementById('page-title').textContent = page.charAt(0).toUpperCase() + page.slice(1);
}

// ===== WEBSOCKET =====
function connectWS() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = () => {
        updateWSStatus(true);
        toast('Connected to agent', 'success');
    };
    ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        handleWSMessage(msg);
    };
    ws.onclose = () => {
        updateWSStatus(false);
        reconnectTimer = setTimeout(connectWS, 3000);
    };
    ws.onerror = () => {
        updateWSStatus(false);
    };
}

function handleWSMessage(msg) {
    if (msg.type === 'update') {
        updateStats(msg.stats);
        updateLogs(msg.logs);
        updateDomainsTable(msg.domains);
        updateAccountsTable(msg.accounts);
    } else if (msg.type === 'agent_status') {
        updateAgentStatus(msg.running);
    }
}

function updateWSStatus(connected) {
    const el = document.getElementById('ws-status');
    el.textContent = connected ? 'Connected' : 'Disconnected';
    el.className = 'badge' + (connected ? ' badge-green' : ' badge-red');
}

// ===== REST API =====
async function api(method, path, body = null) {
    const opts = { method, headers: {} };
    if (body) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
    }
    const res = await fetch(`${API_BASE}${path}`, opts);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

// ===== FORMS =====
function initForms() {
    document.getElementById('domain-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
            await api('POST', '/api/domains', {
                domain: fd.get('domain'),
                sender_email: fd.get('sender_email'),
                daily_target: parseInt(fd.get('daily_target'))
            });
            toast('Domain added', 'success');
            e.target.reset();
            loadDomains();
        } catch (err) {
            toast('Failed: ' + err.message, 'error');
        }
    });

    document.getElementById('account-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
            await api('POST', '/api/accounts', {
                email: fd.get('email'),
                password: fd.get('password'),
                role: fd.get('role')
            });
            toast('Account added', 'success');
            e.target.reset();
            loadAccounts();
        } catch (err) {
            toast('Failed: ' + err.message, 'error');
        }
    });
}

// ===== BUTTONS =====
function initButtons() {
    document.getElementById('btn-start').addEventListener('click', async () => {
        try {
            await api('POST', '/api/agent/start');
            toast('Agent started', 'success');
            updateAgentStatus(true);
        } catch (err) {
            toast(err.message, 'error');
        }
    });

    document.getElementById('btn-stop').addEventListener('click', async () => {
        try {
            await api('POST', '/api/agent/stop');
            toast('Agent stopped', 'info');
            updateAgentStatus(false);
        } catch (err) {
            toast(err.message, 'error');
        }
    });

    document.getElementById('chart-range').addEventListener('change', () => {
        loadReputationHistory();
    });
}

function updateAgentStatus(running) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('agent-status-text');
    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');

    if (running) {
        dot.className = 'status-dot active';
        text.textContent = 'Agent Running';
        btnStart.classList.add('hidden');
        btnStop.classList.remove('hidden');
    } else {
        dot.className = 'status-dot';
        text.textContent = 'Agent Stopped';
        btnStart.classList.remove('hidden');
        btnStop.classList.add('hidden');
    }
}

// ===== DATA LOADING =====
async function loadAllData() {
    loadStats();
    loadDomains();
    loadAccounts();
    loadReputationHistory();
    loadSends();
    loadLogs();
    checkAgentStatus();
}

async function loadStats() {
    try {
        const stats = await api('GET', '/api/stats');
        updateStats(stats);
    } catch (e) {}
}

async function loadDomains() {
    try {
        const domains = await api('GET', '/api/domains');
        updateDomainsTable(domains);
    } catch (e) {}
}

async function loadAccounts() {
    try {
        const accounts = await api('GET', '/api/accounts');
        updateAccountsTable(accounts);
    } catch (e) {}
}

async function loadReputationHistory() {
    try {
        const days = parseInt(document.getElementById('chart-range').value) || 30;
        const data = await api('GET', `/api/reputation?domain_id=1&days=${days}`);
        updateChart(data);
        updateScoreCircle(data);
    } catch (e) {}
}

async function loadSends() {
    try {
        const sends = await api('GET', '/api/sends?limit=50');
        updateSendsTable(sends);
    } catch (e) {}
}

async function loadLogs() {
    try {
        const logs = await api('GET', '/api/logs?limit=100');
        updateLogs(logs);
    } catch (e) {}
}

async function checkAgentStatus() {
    try {
        const status = await api('GET', '/api/agent/status');
        updateAgentStatus(status.running);
    } catch (e) {}
}

// ===== UI UPDATES =====
function updateStats(stats) {
    if (!stats) return;
    animateValue('stat-domains', stats.domains);
    animateValue('stat-peers', stats.peers);
    animateValue('stat-sent', stats.sent);
    animateValue('stat-opened', stats.opened);
    animateValue('stat-replied', stats.replied);
    animateValue('stat-moved', stats.moved);
}

function animateValue(id, target) {
    const el = document.getElementById(id);
    const current = parseInt(el.textContent) || 0;
    if (current === target) return;
    el.textContent = target;
    el.style.transform = 'scale(1.2)';
    setTimeout(() => el.style.transform = 'scale(1)', 200);
}

function updateDomainsTable(domains) {
    const tbody = document.getElementById('domains-table');
    if (!domains || !domains.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">No domains configured yet</td></tr>';
        return;
    }
    tbody.innerHTML = domains.map(d => `
        <tr>
            <td><strong>${esc(d.domain)}</strong></td>
            <td>${esc(d.sender_email || '-')}</td>
            <td>${d.daily_target || 5}</td>
            <td><span class="badge badge-green">${d.status || 'active'}</span></td>
            <td><button class="btn btn-outline btn-sm" onclick="deleteDomain(${d.id})">Delete</button></td>
        </tr>
    `).join('');
}

function updateAccountsTable(accounts) {
    const tbody = document.getElementById('accounts-table');
    if (!accounts || !accounts.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty">No accounts connected yet</td></tr>';
        return;
    }
    tbody.innerHTML = accounts.map(a => `
        <tr>
            <td><strong>${esc(a.email)}</strong></td>
            <td><span class="badge ${a.role === 'sender' ? 'badge-blue' : ''}">${a.role}</span></td>
            <td><span class="badge badge-green">${a.status || 'active'}</span></td>
            <td><button class="btn btn-outline btn-sm" onclick="deleteAccount(${a.id})">Delete</button></td>
        </tr>
    `).join('');
}

function updateSendsTable(sends) {
    const tbody = document.getElementById('sends-table');
    if (!sends || !sends.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">No sends yet</td></tr>';
        return;
    }
    tbody.innerHTML = sends.map(s => `
        <tr>
            <td>${esc(s.from)}</td>
            <td>${esc(s.to)}</td>
            <td>${esc(s.subject || '-')}</td>
            <td><span class="badge ${s.status === 'sent' ? 'badge-green' : 'badge-blue'}">${s.status}</span></td>
            <td>${fmtTime(s.time)}</td>
        </tr>
    `).join('');
}

function updateLogs(logs) {
    const container = document.getElementById('log-container');
    const logsTable = document.getElementById('logs-table');

    // Dashboard live log
    if (!logs || !logs.length) {
        container.innerHTML = '<div class="log-entry empty">Waiting for agent activity...</div>';
        return;
    }
    const recent = logs.slice(0, 30);
    container.innerHTML = recent.map(l => `
        <div class="log-entry">
            <span class="log-time">${fmtTimeShort(l.time)}</span>
            <span class="log-level ${l.level}">${l.level}</span>
            <span class="log-msg">${esc(l.message)}</span>
        </div>
    `).join('');
    container.scrollTop = 0;

    // Activity page table
    if (logsTable) {
        logsTable.innerHTML = logs.slice(0, 50).map(l => `
            <tr>
                <td><span class="badge ${l.level === 'error' ? 'badge-red' : l.level === 'warning' ? '' : 'badge-green'}">${l.level}</span></td>
                <td>${esc(l.message)}</td>
                <td>${fmtTime(l.time)}</td>
            </tr>
        `).join('');
    }
}

function updateScoreCircle(data) {
    const scoreNum = document.getElementById('score-number');
    const scoreCircle = document.getElementById('score-circle');
    let score = 0;
    if (data && data.length) {
        const latest = data[data.length - 1];
        score = latest.score || 0;
    }
    scoreNum.textContent = Math.round(score);
    const circumference = 314;
    const offset = circumference - (score / 100) * circumference;
    scoreCircle.style.strokeDashoffset = offset;
    // Color based on score
    if (score >= 80) scoreCircle.style.stroke = '#22c55e';
    else if (score >= 50) scoreCircle.style.stroke = '#f59e0b';
    else scoreCircle.style.stroke = '#ef4444';
}

// ===== CHART =====
function initChart() {
    const ctx = document.getElementById('reputationChart').getContext('2d');
    Chart.defaults.color = '#8b91a7';
    Chart.defaults.font.family = 'Inter';
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1a1d27',
                    borderColor: '#2a2e3a',
                    borderWidth: 1,
                    padding: 12,
                    titleFont: { size: 13, weight: 600 },
                    bodyFont: { size: 12 }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.03)' },
                    ticks: { font: { size: 11 } }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.03)' },
                    beginAtZero: true,
                    max: 100,
                    ticks: { font: { size: 11 } }
                }
            }
        }
    });
}

function updateChart(data) {
    if (!chartInstance) return;
    const labels = data.map(d => d.date.slice(5));
    const scores = data.map(d => d.score || 0);
    chartInstance.data.labels = labels;
    chartInstance.data.datasets = [{
        label: 'Reputation Score',
        data: scores,
        borderColor: '#6366f1',
        backgroundColor: 'rgba(99,102,241,0.1)',
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 3,
        pointHoverRadius: 6,
        pointBackgroundColor: '#6366f1',
        pointBorderColor: '#fff',
        pointBorderWidth: 2
    }];
    chartInstance.update('none');
}

// ===== DELETE ACTIONS =====
async function deleteDomain(id) {
    if (!confirm('Delete this domain?')) return;
    try {
        await api('DELETE', `/api/domains/${id}`);
        toast('Domain deleted', 'info');
        loadDomains();
    } catch (err) {
        toast('Failed: ' + err.message, 'error');
    }
}

async function deleteAccount(id) {
    if (!confirm('Delete this account?')) return;
    try {
        await api('DELETE', `/api/accounts/${id}`);
        toast('Account deleted', 'info');
        loadAccounts();
    } catch (err) {
        toast('Failed: ' + err.message, 'error');
    }
}

// ===== UTILS =====
function esc(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
}

function fmtTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function fmtTimeShort(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function toast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateX(100%)';
        setTimeout(() => el.remove(), 300);
    }, 3000);
}

// Expose for inline onclick handlers
window.deleteDomain = deleteDomain;
window.deleteAccount = deleteAccount;
