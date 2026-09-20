(() => {
  'use strict';

  const API = '';
  const state = {
    user: null,
    projects: [],
    project: null,
    panel: 'overview',
    charts: {},
    checkoutPlan: null,
    socket: null,
    liveRefreshTimer: null,
    editTaskId: null,
    activeDocumentId: null,
    editingDocumentId: null,
    taskAssigneeFilter: 'all',
    activityMemberFilter: 'all',
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const el = (id) => document.getElementById(id);

  function esc(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }

  async function api(path, options = {}) {
    try {
      const response = await fetch(API + path, {
        credentials: 'include',
        headers: {'Content-Type': 'application/json', ...(options.headers || {})},
        ...options,
      });
      const data = await response.json().catch(() => ({}));
      return {ok: response.ok, status: response.status, data};
    } catch (error) {
      return {ok: false, status: 0, data: {error: 'Could not reach the RoWatch server.'}};
    }
  }

  function toast(message) {
    const node = el('toast');
    node.textContent = message;
    node.classList.add('show');
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => node.classList.remove('show'), 2200);
  }

  function fmtDuration(seconds = 0) {
    seconds = Math.max(0, Number(seconds) || 0);
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h) return `${h}h ${m}m`;
    return `${m}m`;
  }

  function compactNumber(value = 0) {
    const n = Number(value) || 0;
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 100_000 ? 0 : 1)}K`;
    return n.toLocaleString();
  }

  function fmtDate(iso, withTime = true) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    return new Intl.DateTimeFormat(undefined, withTime ? {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    } : {year: 'numeric', month: 'short', day: 'numeric'}).format(d);
  }

  function roleName(role) {
    return role === 'co_admin' ? 'Co-admin' : role === 'owner' ? 'Owner' : 'Member';
  }

  function isAdmin() {
    return state.project && ['owner', 'co_admin'].includes(state.project.role);
  }

  function isOwner() {
    return state.project?.role === 'owner';
  }

  function setView(name) {
    $$('.view').forEach(v => v.classList.remove('active'));
    el(`view-${name}`)?.classList.add('active');
    el('publicNav').style.display = name === 'home' ? '' : 'none';
    window.scrollTo({top: 0, behavior: 'auto'});
  }

  async function route(name) {
    closeSidebar();
    if (name === 'home') {
      state.project = null;
      setView('home');
      history.replaceState(null, '', location.pathname);
      return;
    }
    if (name === 'login' || name === 'register') {
      setView(name);
      return;
    }
    if (name === 'projects') {
      if (!state.user) return route('login');
      state.project = null;
      setView('projects');
      syncUserUI();
      await loadProjects();
      return;
    }
    if (name === 'account') {
      if (!state.user) return route('login');
      if (state.project) return openPanel('account');
      return openStandaloneAccount();
    }
  }

  function applyTheme(theme) {
    const next = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('rowatch-theme', next);
    if (el('themeLabel')) el('themeLabel').textContent = next === 'dark' ? 'Dark' : 'Light';
    if (state.project && state.panel && ['overview', 'analytics'].includes(state.panel)) {
      setTimeout(() => openPanel(state.panel), 0);
    }
  }

  function toggleTheme() {
    applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  }

  function syncUserUI() {
    const username = state.user?.username || 'Account';
    const initial = username.slice(0, 1).toUpperCase() || 'R';
    ['projectsUsername','dashboardUsername','sideUsername'].forEach(id => { if (el(id)) el(id).textContent = username; });
    ['projectsAvatar','dashboardAvatar'].forEach(id => { if (el(id)) el(id).textContent = initial; });
  }

  async function checkAuth() {
    const {ok, data} = await api('/auth/me');
    if (ok) {
      state.user = data;
      syncUserUI();
    }
  }

  function connectLiveUpdates() {
    if (!state.user || !window.io || state.socket) return;
    state.socket = window.io({transports: ['websocket', 'polling']});
    state.socket.on('connect', () => {
      if (state.project) state.socket.emit('join_project', {project_id: state.project.id});
    });
    state.socket.on('project_update', update => {
      if (!state.project || update.project_id !== state.project.id) return;
      if (!['overview', 'activity', 'analytics', 'tasks', 'documents'].includes(state.panel)) return;
      clearTimeout(state.liveRefreshTimer);
      if (update.type === 'task_updated') {
        if (state.panel === 'tasks') state.liveRefreshTimer = setTimeout(() => loadTasks(true), 120);
        return;
      }
      if (update.type === 'document_updated') {
        if (state.panel === 'documents' && !state.editingDocumentId) state.liveRefreshTimer = setTimeout(() => loadDocuments(true), 120);
        return;
      }
      if (state.panel === 'tasks' || state.panel === 'documents') return;
      if (update.type === 'session_heartbeat' || update.type === 'instance_event') {
        // Patch and animate KPI text only; never remount the dashboard panel.
        state.liveRefreshTimer = setTimeout(refreshLiveKpis, 150);
        return;
      }
      state.liveRefreshTimer = setTimeout(() => openPanel(state.panel), 250);
    });
  }

  function joinLiveProject() {
    connectLiveUpdates();
    if (state.socket?.connected && state.project) {
      state.socket.emit('join_project', {project_id: state.project.id});
    }
  }

  async function refreshLiveKpis() {
    if (state.panel !== 'overview' || !state.project) return;
    const result = await api(isAdmin()
      ? `/dashboard/${state.project.id}/overview`
      : `/dashboard/${state.project.id}/me`);
    if (!result.ok || !state.project || state.panel !== 'overview') return;

    let stats;
    let activeCount;
    if (isAdmin()) {
      const members = result.data.members || [];
      stats = members.reduce((total, member) => {
        Object.keys(total).forEach(key => { total[key] += Number(member.stats[key]) || 0; });
        return total;
      }, {total_seconds:0, parts_added:0, parts_removed:0, ui_added:0, ui_removed:0});
      activeCount = members.filter(member => member.active).length;
    } else {
      stats = result.data.stats;
      activeCount = (result.data.sessions || []).filter(session => session.active).length;
    }

    const updateCard = (label, value, sub) => {
      const card = $$('.kpi', el('panelContent')).find(node => $('span', node)?.textContent === label);
      if (!card) return;
      const valueNode = $('strong', card);
      const subNode = $('small', card);
      const changed = valueNode.textContent !== String(value)
        || (sub !== undefined && subNode.textContent !== String(sub));
      valueNode.textContent = value;
      if (sub !== undefined) subNode.textContent = sub;
      if (changed) {
        card.classList.remove('live-change');
        void card.offsetWidth;
        card.classList.add('live-change');
      }
    };
    updateCard(isAdmin() ? 'Total development time' : 'My development time', fmtDuration(stats.total_seconds));
    updateCard('Parts', compactNumber(stats.parts_added), `${compactNumber(stats.parts_removed)} removed`);
    updateCard('UI components', compactNumber(stats.ui_added), `${compactNumber(stats.ui_removed)} removed`);
    updateConnectionBadge(activeCount ? 'Active Studio session' : 'No active Studio session', activeCount > 0);
  }

  async function login(event) {
    event.preventDefault();
    const error = el('loginError');
    error.textContent = '';
    const {ok, data} = await api('/auth/login', {
      method: 'POST',
      body: JSON.stringify({username: el('loginId').value.trim(), password: el('loginPw').value}),
    });
    if (!ok) return error.textContent = data.error || 'Login failed.';
    await checkAuth();
    connectLiveUpdates();
    await route('projects');
  }

  async function register(event) {
    event.preventDefault();
    const error = el('registerError');
    error.textContent = '';
    const {ok, data} = await api('/auth/register', {
      method: 'POST',
      body: JSON.stringify({username: el('regUser').value.trim(), email: el('regEmail').value.trim(), password: el('regPw').value}),
    });
    if (!ok) return error.textContent = data.error || 'Registration failed.';
    await checkAuth();
    connectLiveUpdates();
    await route('projects');
  }

  async function logout() {
    await api('/auth/logout', {method: 'POST'});
    state.user = null;
    state.project = null;
    destroyCharts();
    state.socket?.disconnect();
    state.socket = null;
    await route('home');
  }

  async function loadProjects() {
    const target = el('projectsList');
    target.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
    const {ok, data} = await api('/projects/');
    if (!ok) {
      if (data.error === 'Unauthorized') return route('login');
      target.innerHTML = `<div class="empty-state"><h2>Could not load projects</h2><p>${esc(data.error || 'Try again.')}</p></div>`;
      return;
    }
    state.projects = data;
    if (!data.length) {
      target.innerHTML = `<div class="empty-state"><h2>No projects yet</h2><p>Create your first project, then connect Roblox Studio from the dashboard.</p><button class="btn btn-primary" type="button" id="emptyCreateProject">Create project</button></div>`;
      el('emptyCreateProject').addEventListener('click', openCreateProject);
      return;
    }
    target.innerHTML = data.map(p => `
      <article class="project-card" tabindex="0" data-project-id="${esc(p.id)}" aria-label="Open ${esc(p.name)}">
        <div class="project-card-head"><h2>${esc(p.name)}</h2></div>
        <p class="muted">Open the project dashboard, Studio integration, analytics, and team controls.</p>
        <div class="project-card-meta"><span>${p.member_count} member${p.member_count === 1 ? '' : 's'}</span><span>${esc(roleName(p.role))}</span><span>Created ${esc(fmtDate(p.created_at, false))}</span></div>
      </article>`).join('');
    $$('.project-card', target).forEach(card => {
      const open = () => openProject(card.dataset.projectId);
      card.addEventListener('click', open);
      card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    });
  }

  function openCreateProject() {
    el('newProjectName').value = '';
    el('createProjectError').textContent = '';
    el('createProjectDialog').showModal();
    setTimeout(() => el('newProjectName').focus(), 0);
  }

  async function createProject(event) {
    event.preventDefault();
    const error = el('createProjectError');
    error.textContent = '';
    const name = el('newProjectName').value.trim();
    const {ok, data} = await api('/projects/', {method: 'POST', body: JSON.stringify({name})});
    if (!ok) return error.textContent = data.error || 'Could not create project.';
    el('createProjectDialog').close();
    toast('Project created');
    await loadProjects();
    await openProject(data.id);
  }

  async function openProject(projectId) {
    const {ok, data} = await api(`/projects/${projectId}`);
    if (!ok) return toast(data.error || 'Could not open project.');
    state.project = data;
    state.panel = 'overview';
    syncProjectChrome();
    joinLiveProject();
    setView('dashboard');
    await openPanel('overview');
  }

  function syncProjectChrome() {
    if (!state.project) return;
    el('sidebarProjectName').textContent = state.project.name;
    el('sidebarProjectPlan').textContent = roleName(state.project.role);
    $$('.admin-only').forEach(node => node.style.display = isAdmin() ? '' : 'none');
    syncUserUI();
    applyTheme(localStorage.getItem('rowatch-theme') || 'light');
  }

  async function openPanel(name) {
    if (!state.project && name !== 'account') return route('projects');
    if (['analytics','members','settings'].includes(name) && !isAdmin()) name = 'overview';
    state.panel = name;
    $$('.side-nav button').forEach(button => button.classList.toggle('active', button.dataset.panel === name));
    const titles = {overview:'Overview',activity:'Activity',tasks:'Tasks',documents:'Documentation',analytics:'Analytics',members:'Members',integration:'Studio Integration',settings:'Project Settings',account:'Account'};
    el('panelTitle').textContent = titles[name] || 'Dashboard';
    el('topbarBreadcrumb').textContent = name === 'account' ? 'RoWatch / Account' : `${state.project.name} / ${titles[name]}`;
    const content = el('panelContent');
    content.innerHTML = '<div class="skeleton"></div>';
    closeSidebar();

    const loaders = {overview: loadOverview, activity: loadActivity, tasks: loadTasks, documents: loadDocuments, analytics: loadAnalytics, members: loadMembers, integration: loadIntegration, settings: loadSettings, account: loadAccountPanel};
    await loaders[name]?.();
  }

  async function loadOverview() {
    destroyCharts();
    const content = el('panelContent');
    if (!isAdmin()) return loadMemberOverview();

    const [{ok, data}, activityResult] = await Promise.all([
      api(`/dashboard/${state.project.id}/overview`),
      api(`/dashboard/${state.project.id}/activity`),
    ]);
    if (!ok) return renderError(content, data.error);
    const members = data.members || [];
    const totalSeconds = members.reduce((sum, m) => sum + m.stats.total_seconds, 0);
    const charsAdded = members.reduce((sum, m) => sum + m.stats.chars_added, 0);
    const charsRemoved = members.reduce((sum, m) => sum + m.stats.chars_removed, 0);
    const sessions = members.reduce((sum, m) => sum + m.stats.total_sessions, 0);
    const recent = activityResult.ok ? activityResult.data.slice(0, 7) : [];
    updateConnectionBadge(members.some(m => m.active) ? 'Active Studio session' : 'No active Studio session', members.some(m => m.active));

    content.innerHTML = `
      <div class="kpi-grid">
        ${kpi('Total development time', fmtDuration(totalSeconds), 'Across all project members')}
        ${kpi('Characters added', compactNumber(charsAdded), `${compactNumber(charsRemoved)} removed`)}
        ${kpi('Sessions', sessions.toLocaleString(), `${members.filter(m => m.active).length} active now`)}
        ${kpi('Team size', members.length.toLocaleString(), `${members.filter(m => m.role !== 'member').length} admins`)}
        ${kpi('Parts', compactNumber(members.reduce((sum,m)=>sum+m.stats.parts_added,0)), `${compactNumber(members.reduce((sum,m)=>sum+m.stats.parts_removed,0))} removed`)}
        ${kpi('UI components', compactNumber(members.reduce((sum,m)=>sum+m.stats.ui_added,0)), `${compactNumber(members.reduce((sum,m)=>sum+m.stats.ui_removed,0))} removed`)}
      </div>
      <div class="dashboard-grid">
        <section class="panel-card"><div class="panel-card-head"><div><h2>Activity — last 14 days</h2><p>Completed and active sessions by day.</p></div></div><div class="chart-box"><canvas id="overviewDailyChart"></canvas></div></section>
        <section class="panel-card"><div class="panel-card-head"><div><h2>Member sessions</h2><p>Session count by developer.</p></div></div><div class="chart-box"><canvas id="overviewMemberChart"></canvas></div></section>
      </div>
      <section class="panel-card"><div class="panel-card-head"><div><h2>Recent activity</h2><p>Latest Studio activity.</p></div><button class="mini-btn" type="button" data-go-panel="activity">View all</button></div>${recent.length ? activityTable(recent) : emptyInline('No activity yet', 'Start a Studio session to populate this feed.')}</section>`;

    $$('[data-go-panel]', content).forEach(b => b.addEventListener('click', () => openPanel(b.dataset.goPanel)));
    await renderOverviewCharts(members);
  }

  async function loadMemberOverview() {
    const content = el('panelContent');
    const {ok, data} = await api(`/dashboard/${state.project.id}/me`);
    if (!ok) return renderError(content, data.error);
    const s = data.stats;
    updateConnectionBadge((data.sessions || []).some(session => session.active) ? 'Your Studio session is active' : 'No active Studio session', (data.sessions || []).some(session => session.active));
    content.innerHTML = `
      <div class="kpi-grid">
        ${kpi('My development time', fmtDuration(s.total_seconds), 'All retained sessions')}
        ${kpi('Characters added', compactNumber(s.chars_added), `${compactNumber(s.chars_removed)} removed`)}
        ${kpi('Scripts opened', s.scripts_opened.toLocaleString(), 'Recorded Studio activity')}
        ${kpi('Sessions', s.total_sessions.toLocaleString(), 'Tracked sessions')}
        ${kpi('Parts', compactNumber(s.parts_added), `${compactNumber(s.parts_removed)} removed`)}
        ${kpi('UI components', compactNumber(s.ui_added), `${compactNumber(s.ui_removed)} removed`)}
      </div>
      <section class="panel-card"><div class="panel-card-head"><div><h2>My session history</h2><p>Your activity in ${esc(state.project.name)}.</p></div></div>${sessionTable(data.sessions || [])}</section>`;
  }

  async function renderOverviewCharts(members) {
    const {ok, data} = await api(`/dashboard/${state.project.id}/charts/daily`);
    if (!window.Chart) return;
    const vars = themeChartColors();
    if (ok) {
      const days = Object.keys(data).sort().slice(-14);
      state.charts.daily = new Chart(el('overviewDailyChart'), {
        type: 'line',
        data: {labels: days.map(d => new Date(`${d}T00:00:00`).toLocaleDateString(undefined,{month:'short',day:'numeric'})), datasets:[{data:days.map(d => data[d].seconds / 3600), borderColor:vars.accent, backgroundColor:vars.accentSoft, fill:true, pointRadius:2, pointHoverRadius:4, tension:.25, borderWidth:2}]},
        options: chartOptions('Hours'),
      });
    }
    state.charts.members = new Chart(el('overviewMemberChart'), {
      type: 'bar',
      data: {labels: members.map(m => m.username), datasets:[{data:members.map(m => m.stats.total_sessions), backgroundColor:vars.accent, borderRadius:2}]},
      options: chartOptions('Sessions'),
    });
  }

  async function loadActivity() {
    const content = el('panelContent');
    let events = [];
    let members = [];
    if (isAdmin()) {
      const [activityResult, membersResult] = await Promise.all([
        api(`/dashboard/${state.project.id}/activity`),
        api(`/projects/${state.project.id}/members`),
      ]);
      if (!activityResult.ok) return renderError(content, activityResult.data.error);
      events = activityResult.data;
      members = membersResult.ok ? membersResult.data : [];
    } else {
      const result = await api(`/dashboard/${state.project.id}/me`);
      if (!result.ok) return renderError(content, result.data.error);
      events = (result.data.sessions || []).flatMap(session => [
        ...(session.events || []).map(event => ({...event, username: state.user.username, session_id: session.id})),
        ...(session.instance_events || []).map(event => ({...event, username: state.user.username, session_id: session.id, script: event.instance_name, event_type: `${event.category}_${event.action}`})),
      ]).sort((a,b) => String(b.occurred_at).localeCompare(String(a.occurred_at)));
      members = [{username: state.user.username}];
      state.activityMemberFilter = 'all';
    }
    if (state.activityMemberFilter !== 'all' && !members.some(member => member.username === state.activityMemberFilter)) {
      state.activityMemberFilter = 'all';
    }
    const visibleEvents = state.activityMemberFilter === 'all'
      ? events
      : events.filter(event => event.username === state.activityMemberFilter);
    const filter = isAdmin() ? `<div class="activity-filter"><label>Filter by member<select id="activityMemberFilter"><option value="all">All members</option>${members.map(member=>`<option value="${esc(member.username)}" ${state.activityMemberFilter===member.username?'selected':''}>${esc(member.username)}</option>`).join('')}</select></label><span class="role-box">${visibleEvents.length}/${events.length} shown</span></div>` : '';
    content.innerHTML = `<div class="toolbar"><div><h2>${isAdmin() ? 'Project activity' : 'My activity'}</h2><p>Newest Studio events first. Up to 200 are shown.</p></div>${filter}</div>${visibleEvents.length ? activityTable(visibleEvents.slice(0,200)) : emptyInline('No matching activity', state.activityMemberFilter==='all'?'Connect the plugin and start a session.':'This member has no recorded activity.')}`;
    el('activityMemberFilter')?.addEventListener('change', event => {
      state.activityMemberFilter = event.target.value;
      loadActivity();
    });
  }

  function renderMarkdown(markdown = '') {
    const inline = value => value
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    const lines = esc(markdown).split(/\r?\n/);
    let html = '';
    let inList = false;
    for (const line of lines) {
      const item = line.match(/^[-*] (.+)$/);
      if (item) {
        if (!inList) { html += '<ul>'; inList = true; }
        html += `<li>${inline(item[1])}</li>`;
        continue;
      }
      if (inList) { html += '</ul>'; inList = false; }
      if (/^### /.test(line)) html += `<h3>${inline(line.slice(4))}</h3>`;
      else if (/^## /.test(line)) html += `<h2>${inline(line.slice(3))}</h2>`;
      else if (/^# /.test(line)) html += `<h1>${inline(line.slice(2))}</h1>`;
      else if (/^&gt; /.test(line)) html += `<blockquote>${inline(line.slice(5))}</blockquote>`;
      else if (line.trim()) html += `<p>${inline(line)}</p>`;
      else html += '<br>';
    }
    if (inList) html += '</ul>';
    return html;
  }

  async function loadTasks(quiet = false) {
    const content = el('panelContent');
    const [tasksResult, membersResult] = await Promise.all([
      api(`/workspace/${state.project.id}/tasks`),
      api(`/projects/${state.project.id}/members`),
    ]);
    if (!tasksResult.ok) return renderError(content, tasksResult.data.error);
    const tasks = tasksResult.data.items || [];
    const taskUsage = tasksResult.data.usage;
    const members = membersResult.ok ? membersResult.data : [];
    if (state.taskAssigneeFilter !== 'all' && !members.some(member => member.user_id === state.taskAssigneeFilter)) {
      state.taskAssigneeFilter = 'all';
    }
    const visibleTasks = state.taskAssigneeFilter === 'all'
      ? tasks
      : tasks.filter(task => task.assignments.some(item => item.user_id === state.taskAssigneeFilter));
    const editing = tasks.find(task => task.id === state.editTaskId);
    const memberChecks = members.map(member => `<label class="assignee-option"><input type="checkbox" name="taskAssignee" value="${esc(member.user_id)}" ${editing?.assignments.some(item=>item.user_id===member.user_id)?'checked':''}/><span>${esc(member.username)}</span><small>${esc(roleName(member.role))}</small></label>`).join('');
    const editor = isAdmin() ? `<section class="panel-card task-editor"><div class="panel-card-head"><div><h2>${editing?'Edit task':'Create task'}</h2><p>Assign one task to one or more project members.</p></div></div><div class="task-form-grid"><label>Title<input id="taskTitle" maxlength="200" value="${esc(editing?.title||'')}" placeholder="Ship inventory UI"/></label><label>Due date<input id="taskDue" type="date" value="${esc(editing?.due_at?.slice(0,10)||'')}"/></label></div><label>Description (Markdown)<textarea id="taskDescription" rows="4" placeholder="## Acceptance criteria">${esc(editing?.description_md||'')}</textarea></label><div class="assignee-grid">${memberChecks || '<span class="muted">Add project members before assigning tasks.</span>'}</div><div class="task-actions"><button id="saveTask" class="btn btn-primary" type="button">${editing?'Save changes':'Create task'}</button>${editing?'<button id="cancelTaskEdit" class="btn btn-secondary" type="button">Cancel</button>':''}</div><p id="taskError" class="form-error"></p></section>` : '';
    const cards = visibleTasks.map(task => {
      const mine = task.assigned_to_me;
      const assignees = task.assignments.map(item=>`<span class="assignee-chip ${item.completed?'done':''}">${item.completed?'✓ ':''}${esc(item.username)}</span>`).join('');
      return `<article class="task-card ${task.my_completed?'task-done':''}"><div class="task-check">${mine?`<input type="checkbox" data-task-complete="${esc(task.id)}" ${task.my_completed?'checked':''} aria-label="Complete ${esc(task.title)}"/>`:'<span>•</span>'}</div><div class="task-body"><div class="task-title-row"><h2>${esc(task.title)}</h2><span>${task.completed_count}/${task.assignments.length} complete</span></div>${task.description_md?`<div class="markdown task-markdown">${renderMarkdown(task.description_md)}</div>`:''}<div class="task-meta">${task.due_at?`<span>Due ${esc(fmtDate(task.due_at,false))}</span>`:'<span>No due date</span>'}<span>Created by ${esc(task.created_by)}</span></div><div class="assignee-chips">${assignees||'<span class="muted">Unassigned</span>'}</div></div>${isAdmin()?`<div class="task-admin-actions"><button class="mini-btn" data-edit-task="${esc(task.id)}">Edit</button><button class="mini-btn danger" data-delete-task="${esc(task.id)}">Delete</button></div>`:''}</article>`;
    }).join('');
    const filterOptions = [`<option value="all">All members</option>`, ...members.map(member => `<option value="${esc(member.user_id)}" ${state.taskAssigneeFilter===member.user_id?'selected':''}>${esc(member.username)}</option>`)].join('');
    content.innerHTML = `<div class="toolbar"><div><h2>Team tasks</h2><p>Completion is tracked separately for every assignee.</p></div><div class="task-filter"><label>Filter by assignee<select id="taskAssigneeFilter">${filterOptions}</select></label><span class="role-box">${visibleTasks.length}/${tasks.length} shown · ${taskUsage.limit===null?'Unlimited':`${taskUsage.current}/${taskUsage.limit}`}</span></div></div>${editor}<div class="task-list">${cards || emptyInline('No matching tasks', state.taskAssigneeFilter==='all'?(isAdmin()?'Create the first team task above.':'Your project admins have not created tasks yet.'):'No tasks are assigned to this member.')}</div>`;
    el('taskAssigneeFilter').value = state.taskAssigneeFilter;
    el('taskAssigneeFilter').addEventListener('change', event => { state.taskAssigneeFilter=event.target.value; loadTasks(true); });
    el('saveTask')?.addEventListener('click', saveTask);
    el('cancelTaskEdit')?.addEventListener('click',()=>{state.editTaskId=null;loadTasks();});
    $$('[data-task-complete]',content).forEach(node=>node.addEventListener('change',()=>toggleTask(node.dataset.taskComplete,node.checked)));
    $$('[data-edit-task]',content).forEach(node=>node.addEventListener('click',()=>{state.editTaskId=node.dataset.editTask;loadTasks();}));
    $$('[data-delete-task]',content).forEach(node=>node.addEventListener('click',()=>deleteTask(node.dataset.deleteTask)));
  }

  async function saveTask() {
    const title = el('taskTitle').value.trim();
    const assignee_ids = $$('input[name="taskAssignee"]:checked').map(node=>node.value);
    const payload = {title, description_md:el('taskDescription').value, due_at:el('taskDue').value||null, assignee_ids};
    const path = state.editTaskId ? `/workspace/${state.project.id}/tasks/${state.editTaskId}` : `/workspace/${state.project.id}/tasks`;
    const result = await api(path,{method:state.editTaskId?'PATCH':'POST',body:JSON.stringify(payload)});
    if(!result.ok) return el('taskError').textContent=result.data.error||'Could not save task.';
    state.editTaskId=null; toast('Task saved'); await loadTasks(true);
  }

  async function toggleTask(taskId, completed) {
    const result = await api(`/workspace/${state.project.id}/tasks/${taskId}/complete`,{method:'POST',body:JSON.stringify({completed})});
    if(!result.ok){toast(result.data.error||'Could not update task.');return loadTasks(true);}
    await loadTasks(true);
  }

  async function deleteTask(taskId) {
    if(!confirm('Delete this task for every assignee?')) return;
    const result=await api(`/workspace/${state.project.id}/tasks/${taskId}`,{method:'DELETE'});
    if(!result.ok)return toast(result.data.error||'Could not delete task.');
    if(state.editTaskId===taskId)state.editTaskId=null;toast('Task deleted');await loadTasks(true);
  }

  async function loadDocuments(quiet = false) {
    const content=el('panelContent');
    const result=await api(`/workspace/${state.project.id}/documents`);
    if(!result.ok)return renderError(content,result.data.error);
    const documents=result.data.items || [];
    const documentUsage=result.data.usage;
    if(!documents.some(doc=>doc.id===state.activeDocumentId))state.activeDocumentId=documents[0]?.id||null;
    const selected=documents.find(doc=>doc.id===state.activeDocumentId);
    const list=documents.map(doc=>`<button class="document-link ${doc.id===state.activeDocumentId?'active':''}" data-document-id="${esc(doc.id)}"><strong>${esc(doc.title)}</strong><small>Updated ${esc(fmtDate(doc.updated_at))}</small></button>`).join('');
    let detail;
    const editingDocument = selected && isAdmin() && state.editingDocumentId === selected.id;
    if(editingDocument)detail=`<div class="document-editor"><input id="documentTitle" maxlength="200" value="${esc(selected.title)}"/><textarea id="documentContent" rows="18" placeholder="# Documentation">${esc(selected.content_md)}</textarea><div class="task-actions"><button id="saveDocument" class="btn btn-primary">Save document</button><button id="cancelDocumentEdit" class="btn btn-secondary">Cancel</button><button id="deleteDocument" class="btn btn-danger">Delete</button></div><h3>Preview</h3><div class="markdown document-preview">${renderMarkdown(selected.content_md)}</div></div>`;
    else if(selected)detail=`<article class="document-reader"><div class="document-reader-head"><h1>${esc(selected.title)}</h1>${isAdmin()?'<button id="editDocument" class="btn btn-primary">Edit document</button>':''}</div><div class="markdown">${renderMarkdown(selected.content_md)}</div></article>`;
    else detail=emptyInline('No documentation yet',isAdmin()?'Create the first Markdown document.':'Project admins have not added documentation yet.');
    content.innerHTML=`<div class="toolbar"><div><h2>Project documentation</h2><p>Write guides, specifications, notes, and team knowledge in Markdown.</p></div><div class="task-filter"><span class="role-box">${documentUsage.limit===null?'Unlimited':`${documentUsage.current}/${documentUsage.limit} documents`}</span>${isAdmin()?'<button id="newDocument" class="btn btn-primary">+ New document</button>':''}</div></div><div class="documents-layout"><aside class="documents-list">${list||'<span class="muted">No documents</span>'}</aside><section class="panel-card">${detail}</section></div>`;
    $$('[data-document-id]',content).forEach(node=>node.addEventListener('click',()=>{state.activeDocumentId=node.dataset.documentId;state.editingDocumentId=null;loadDocuments();}));
    el('newDocument')?.addEventListener('click',createDocument);
    el('editDocument')?.addEventListener('click',()=>{state.editingDocumentId=state.activeDocumentId;loadDocuments();});
    el('cancelDocumentEdit')?.addEventListener('click',()=>{state.editingDocumentId=null;loadDocuments();});
    el('saveDocument')?.addEventListener('click',saveDocument);
    el('deleteDocument')?.addEventListener('click',deleteDocument);
    el('documentContent')?.addEventListener('input', event => {
      const preview = $('.document-preview', content);
      if (preview) preview.innerHTML = renderMarkdown(event.target.value);
    });
  }

  async function createDocument(){
    const title=prompt('Document title');if(!title?.trim())return;
    const result=await api(`/workspace/${state.project.id}/documents`,{method:'POST',body:JSON.stringify({title:title.trim(),content_md:'# '+title.trim()+'\n'})});
    if(!result.ok)return toast(result.data.error||'Could not create document.');
    state.activeDocumentId=result.data.id;state.editingDocumentId=null;await loadDocuments(true);
  }

  async function saveDocument(){
    const result=await api(`/workspace/${state.project.id}/documents/${state.activeDocumentId}`,{method:'PATCH',body:JSON.stringify({title:el('documentTitle').value.trim(),content_md:el('documentContent').value})});
    if(!result.ok)return toast(result.data.error||'Could not save document.');state.editingDocumentId=null;toast('Document saved');await loadDocuments(true);
  }

  async function deleteDocument(){
    if(!confirm('Permanently delete this document?'))return;
    const result=await api(`/workspace/${state.project.id}/documents/${state.activeDocumentId}`,{method:'DELETE'});
    if(!result.ok)return toast(result.data.error||'Could not delete document.');state.activeDocumentId=null;state.editingDocumentId=null;toast('Document deleted');await loadDocuments(true);
  }

  async function loadAnalytics() {
    destroyCharts();
    const content = el('panelContent');
    const [overview, daily] = await Promise.all([api(`/dashboard/${state.project.id}/overview`), api(`/dashboard/${state.project.id}/charts/daily`)]);
    if (!overview.ok) return renderError(content, overview.data.error);
    const members = overview.data.members || [];
    const totalAdded = members.reduce((s,m) => s + m.stats.chars_added,0);
    const totalRemoved = members.reduce((s,m) => s + m.stats.chars_removed,0);
    const activeDays = daily.ok ? Object.keys(daily.data).length : 0;
    content.innerHTML = `
      <div class="kpi-grid">
        ${kpi('Active days', activeDays, 'Within the last 30 days')}
        ${kpi('Code change volume', compactNumber(totalAdded + totalRemoved), 'Added + removed characters')}
        ${kpi('Average time / member', fmtDuration(members.length ? members.reduce((s,m)=>s+m.stats.total_seconds,0)/members.length : 0), 'Across current team')}
        ${kpi('Average sessions / member', members.length ? (members.reduce((s,m)=>s+m.stats.total_sessions,0)/members.length).toFixed(1) : '0', 'Across current team')}
      </div>
      <div class="dashboard-grid">
        <section class="panel-card"><div class="panel-card-head"><div><h2>Development time</h2><p>Hours tracked per day during the last 30 days.</p></div></div><div class="chart-box"><canvas id="analyticsTime"></canvas></div></section>
        <section class="panel-card"><div class="panel-card-head"><div><h2>Code change volume</h2><p>Characters added per day.</p></div></div><div class="chart-box"><canvas id="analyticsCode"></canvas></div></section>
      </div>
      <section class="panel-card"><div class="panel-card-head"><div><h2>Member performance</h2><p>Raw tracked totals; interpret them in the context of each developer's work.</p></div></div>${memberStatsTable(members)}</section>`;
    if (!window.Chart || !daily.ok) return;
    const days = Object.keys(daily.data).sort();
    const labels = days.map(d => new Date(`${d}T00:00:00`).toLocaleDateString(undefined,{month:'short',day:'numeric'}));
    const vars = themeChartColors();
    state.charts.analyticsTime = new Chart(el('analyticsTime'), {type:'line', data:{labels,datasets:[{data:days.map(d=>daily.data[d].seconds/3600),borderColor:vars.accent,backgroundColor:vars.accentSoft,fill:true,tension:.25,borderWidth:2,pointRadius:1}]},options:chartOptions('Hours')});
    state.charts.analyticsCode = new Chart(el('analyticsCode'), {type:'bar', data:{labels,datasets:[{data:days.map(d=>daily.data[d].chars_added),backgroundColor:vars.accent,borderRadius:2}]},options:chartOptions('Characters')});
  }

  async function loadMembers() {
    const content = el('panelContent');
    const {ok, data} = await api(`/projects/${state.project.id}/members`);
    if (!ok) return renderError(content, data.error);
    content.innerHTML = `
      <div class="toolbar"><div><h2>Project members</h2><p>${data.length} member${data.length === 1 ? '' : 's'} currently have project access.</p></div><button id="inviteMemberButton" class="btn btn-primary" type="button">+ Invite member</button></div>
      <div class="data-table-wrap"><table class="data-table"><thead><tr><th>User</th><th>Role</th><th>Joined</th><th>Actions</th></tr></thead><tbody>${data.map(m => `<tr><td><strong>${esc(m.username)}</strong></td><td><span class="role-box">${esc(roleName(m.role))}</span></td><td>${esc(fmtDate(m.joined_at,false))}</td><td>${memberActions(m)}</td></tr>`).join('')}</tbody></table></div>`;
    el('inviteMemberButton').addEventListener('click', () => { el('inviteUsername').value=''; el('inviteError').textContent=''; el('inviteDialog').showModal(); });
    $$('[data-member-role]', content).forEach(b => b.addEventListener('click', () => changeMemberRole(b.dataset.userId, b.dataset.memberRole)));
    $$('[data-member-remove]', content).forEach(b => b.addEventListener('click', () => removeMember(b.dataset.userId, b.dataset.username)));
  }

  function memberActions(member) {
    if (!isOwner() || member.role === 'owner') return '<span class="muted">—</span>';
    const next = member.role === 'co_admin' ? 'member' : 'co_admin';
    return `<div class="member-actions"><button class="mini-btn" type="button" data-member-role="${next}" data-user-id="${esc(member.user_id)}">Make ${next === 'co_admin' ? 'co-admin' : 'member'}</button><button class="mini-btn danger" type="button" data-member-remove data-user-id="${esc(member.user_id)}" data-username="${esc(member.username)}">Remove</button></div>`;
  }

  async function inviteMember(event) {
    event.preventDefault();
    const error = el('inviteError');
    error.textContent = '';
    const {ok, data} = await api(`/projects/${state.project.id}/members/invite`, {method:'POST', body:JSON.stringify({username:el('inviteUsername').value.trim()})});
    if (!ok) return error.textContent = data.error || 'Could not invite member.';
    el('inviteDialog').close(); toast(`${data.username} added`); await loadMembers();
  }

  async function changeMemberRole(userId, role) {
    const {ok, data} = await api(`/projects/${state.project.id}/members/${userId}/role`, {method:'PATCH', body:JSON.stringify({role})});
    if (!ok) return toast(data.error || 'Could not change role.');
    toast(`Role changed to ${roleName(role)}`); await loadMembers();
  }

  async function removeMember(userId, username) {
    if (!confirm(`Remove ${username} from this project?`)) return;
    const {ok, data} = await api(`/projects/${state.project.id}/members/${userId}`, {method:'DELETE'});
    if (!ok) return toast(data.error || 'Could not remove member.');
    toast(`${username} removed`); await loadMembers();
  }

  async function loadIntegration() {
    const content = el('panelContent');
    const key = state.project.project_key;
    content.innerHTML = `
      <div class="settings-stack">
        <section class="settings-row"><h2>Roblox Studio connection</h2><p>Use the RoWatch plugin to connect Studio activity to this project.</p><ol class="setup-list"><li><strong>Install the plugin.</strong> Use <code class="mono">plugin/RoWatch.lua</code> from this package.</li><li><strong>Allow HTTP Requests</strong> in Roblox Studio game settings.</li><li><strong>Set the server URL</strong> in the plugin to this RoWatch deployment.</li><li><strong>Connect with your username and project key.</strong></li><li><strong>Start a session</strong> before working and end it when you're done.</li></ol></section>
        <section class="settings-row"><h2>Project key</h2><p>${key ? 'Admins can copy this key for the Studio plugin.' : 'Your role does not expose the project key. Ask an owner or co-admin for it.'}</p>${key ? `<div class="key-line"><input id="integrationKey" readonly value="${esc(key)}"/><button id="copyIntegrationKey" class="btn btn-secondary" type="button">Copy key</button></div>` : ''}</section>
        <section class="settings-row"><h2>Plugin API</h2><p>The plugin authenticates each request with <code class="mono">X-Project-Key</code> and <code class="mono">X-Username</code>.</p><div class="integration-code">GET /api/events/ping\nPOST /api/events/session/start\nPOST /api/events/session/end\nPOST /api/events/session/heartbeat\nPOST /api/events/script/open\nPOST /api/events/script/close\nPOST /api/events/instance/change</div></section>
      </div>`;
    el('copyIntegrationKey')?.addEventListener('click', () => copyText(key, 'Project key copied'));
  }

  async function loadSettings() {
    const content = el('panelContent');
    const p = state.project;
    content.innerHTML = `
      <div class="settings-stack">
        <section class="settings-row"><h2>Project details</h2><p>${isOwner() ? 'Rename the project. Changes are visible to every member.' : 'Only the project owner can rename this project.'}</p><div class="key-line"><input id="projectNameInput" value="${esc(p.name)}" ${isOwner() ? '' : 'readonly'}/>${isOwner() ? '<button id="saveProjectName" class="btn btn-primary" type="button">Save</button>' : ''}</div></section>
        <section class="settings-row"><h2>Project key</h2><p>${isOwner() ? 'Regenerating the key disconnects existing Studio plugin configurations until they use the new key.' : 'Only the owner can regenerate the key.'}</p><div class="key-line"><input readonly id="settingsProjectKey" value="${esc(p.project_key || 'Hidden')}"/>${isOwner() ? '<button id="regenProjectKey" class="btn btn-secondary" type="button">Regenerate</button>' : ''}</div></section>
        ${isOwner() ? '<section class="settings-row danger-zone"><h2>Delete project</h2><p>Permanently deletes this project, its memberships, sessions, and script events.</p><button id="deleteProject" class="btn btn-danger" type="button">Delete project</button></section>' : ''}
      </div>`;
    el('saveProjectName')?.addEventListener('click', saveProjectName);
    el('regenProjectKey')?.addEventListener('click', regenerateProjectKey);
    el('deleteProject')?.addEventListener('click', deleteProject);
  }

  async function saveProjectName() {
    const name = el('projectNameInput').value.trim();
    const {ok, data} = await api(`/projects/${state.project.id}`, {method:'PATCH', body:JSON.stringify({name})});
    if (!ok) return toast(data.error || 'Could not rename project.');
    state.project.name = data.name;
    syncProjectChrome();
    el('topbarBreadcrumb').textContent = `${state.project.name} / Project Settings`;
    toast('Project renamed');
  }

  async function regenerateProjectKey() {
    if (!confirm('Regenerate the project key? Existing plugin connections will stop working.')) return;
    const {ok, data} = await api(`/projects/${state.project.id}/key`, {method:'POST'});
    if (!ok) return toast(data.error || 'Could not regenerate key.');
    state.project.project_key = data.project_key;
    el('settingsProjectKey').value = data.project_key;
    toast('Project key regenerated');
  }

  async function deleteProject() {
    const typed = prompt(`Type ${state.project.name} to permanently delete this project.`);
    if (typed !== state.project.name) return;
    const {ok, data} = await api(`/projects/${state.project.id}`, {method:'DELETE'});
    if (!ok) return toast(data.error || 'Could not delete project.');
    toast('Project deleted');
    await route('projects');
  }

  function planChooserHtml() {
    const current = state.user?.plan || 'free';
    const expires = state.user?.plan_expires_at ? `Expires ${fmtDate(state.user.plan_expires_at,false)}` : (current === 'free' ? 'No expiry' : 'Active');
    const plans = [
      {id:'free',price:'$0',period:'forever',features:['1 owned project','5 members per project','10 tasks · 3 documents','7 days history']},
      {id:'pro',price:'$5.99',period:'month',features:['3 owned projects','15 members per project','Unlimited tasks & documents','60 days history']},
      {id:'studio',price:'$14.99',period:'month',features:['Unlimited projects','Unlimited members','Unlimited tasks & documents','Unlimited history']},
    ];
    const adminGenerator = state.user?.is_admin ? `<section class="admin-code-generator"><h3>Admin · Generate upgrade codes</h3><div class="code-generator-grid"><label>Plan<select data-code-plan><option value="pro">Pro</option><option value="studio">Studio</option></select></label><label>Duration (days)<input data-code-days type="number" min="1" max="3650" value="30"/></label><label>Quantity<input data-code-quantity type="number" min="1" max="100" value="1"/></label><button class="btn btn-secondary" type="button" data-generate-codes>Generate</button></div><p class="form-error" data-code-admin-error></p><textarea data-generated-codes rows="4" readonly placeholder="New raw codes appear here once"></textarea></section>` : '';
    return `<section class="account-plans"><div class="panel-card-head"><div><h2>Account plan</h2><p>Your plan applies to every project you own. Current: <strong>${esc(current.toUpperCase())}</strong> · ${esc(expires)}</p></div></div><div class="account-plan-grid">${plans.map(plan=>`<article class="account-plan-card ${current===plan.id?'current':''}"><div><h3>${plan.id[0].toUpperCase()+plan.id.slice(1)}</h3>${current===plan.id?'<span class="plan-tag">Current</span>':''}</div><p class="account-plan-price"><strong>${plan.price}</strong><span> / ${plan.period}</span></p><ul>${plan.features.map(feature=>`<li>${esc(feature)}</li>`).join('')}</ul><button class="btn ${(current===plan.id||(plan.id==='free'&&current!=='free'))?'btn-secondary':'btn-primary'} full" type="button" data-account-plan="${plan.id}" ${(current===plan.id||(plan.id==='free'&&current!=='free'))?'disabled':''}>${current===plan.id?'Current plan':plan.id==='free'?'Available after paid term':`Use ${plan.id[0].toUpperCase()+plan.id.slice(1)} code`}</button></article>`).join('')}</div><section class="redeem-code-box"><div><h3>Redeem upgrade code</h3><p>Enter the 64-character hexadecimal code supplied by RoWatch.</p></div><div class="redeem-code-line"><input data-upgrade-code maxlength="64" autocomplete="off" spellcheck="false" placeholder="64-character upgrade code"/><button class="btn btn-primary" type="button" data-redeem-code>Redeem</button></div><p class="form-error" data-redeem-error></p></section>${adminGenerator}</section>`;
  }

  function wireAccountPlanButtons(root=document) {
    $$('[data-account-plan]',root).forEach(button=>button.addEventListener('click',()=>{
      if(button.dataset.accountPlan === 'free'){
        button.closest('dialog')?.close();
        openCheckout('free');
      } else {
        const input=$('[data-upgrade-code]',root);
        input?.focus();
        input?.scrollIntoView({behavior:'smooth',block:'center'});
      }
    }));
    $('[data-redeem-code]',root)?.addEventListener('click',()=>redeemUpgradeCode(root));
    $('[data-upgrade-code]',root)?.addEventListener('keydown',event=>{if(event.key==='Enter')redeemUpgradeCode(root);});
    $('[data-generate-codes]',root)?.addEventListener('click',()=>generateUpgradeCodes(root));
  }

  async function redeemUpgradeCode(root) {
    const input=$('[data-upgrade-code]',root);
    const error=$('[data-redeem-error]',root);
    const code=input.value.trim();
    error.textContent='';
    const result=await api('/payments/codes/redeem',{method:'POST',body:JSON.stringify({code})});
    if(!result.ok)return error.textContent=result.data.error||'Could not redeem code.';
    await checkAuth();
    input.value='';
    toast(`${result.data.plan.toUpperCase()} activated for ${result.data.duration_days} days`);
    if(root.closest('dialog')){root.closest('dialog').close();await route('projects');}
    else await loadAccountPanel();
  }

  async function generateUpgradeCodes(root) {
    const error=$('[data-code-admin-error]',root);
    const output=$('[data-generated-codes]',root);
    error.textContent='';output.value='';
    const result=await api('/payments/codes',{method:'POST',body:JSON.stringify({plan:$('[data-code-plan]',root).value,duration_days:Number($('[data-code-days]',root).value),quantity:Number($('[data-code-quantity]',root).value)})});
    if(!result.ok)return error.textContent=result.data.error||'Could not generate codes.';
    output.value=result.data.codes.map(item=>item.code).join('\n');
    toast(`${result.data.codes.length} upgrade code${result.data.codes.length===1?'':'s'} generated`);
  }

  async function loadAccountPanel() {
    const content = el('panelContent');
    const result = await api('/auth/me');
    if (!result.ok) return renderError(content, result.data.error);
    state.user = result.data; syncUserUI();
    content.innerHTML = `<div class="account-panel"><section class="panel-card"><div class="panel-card-head"><div><h2>Account details</h2><p>Your RoWatch username is also used by the Roblox Studio plugin.</p></div></div><div class="account-grid"><label>Username<input id="accountUsername" value="${esc(state.user.username)}"/></label><label>Email<input id="accountEmail" type="email" value="${esc(state.user.email)}"/></label></div><button id="saveAccount" class="btn btn-primary" type="button">Save account</button></section>${planChooserHtml()}</div>`;
    el('saveAccount').addEventListener('click', saveAccountFromPanel);
    wireAccountPlanButtons(content);
  }

  async function saveAccountFromPanel() {
    const username = el('accountUsername').value.trim();
    const email = el('accountEmail').value.trim();
    const {ok,data} = await api('/auth/me',{method:'PATCH',body:JSON.stringify({username,email})});
    if (!ok) return toast(data.error || 'Could not update account.');
    state.user = {...state.user,...data}; syncUserUI(); toast('Account updated');
  }

  async function openStandaloneAccount() {
    let dialog = el('standaloneAccountDialog');
    if (!dialog) {
      dialog = document.createElement('dialog');
      dialog.id = 'standaloneAccountDialog';
      dialog.className = 'dialog account-dialog';
      document.body.appendChild(dialog);
    }
    const result = await api('/auth/me');
    if (!result.ok) return toast(result.data.error || 'Could not load account.');
    state.user = result.data; syncUserUI();
    dialog.innerHTML = `<form id="standaloneAccountForm"><div class="dialog-head"><div><h2>Account</h2><p>Your username and plan apply across RoWatch.</p></div><button type="button" class="dialog-x" data-standalone-close>×</button></div><label>Username<input id="standaloneUsername" value="${esc(state.user.username)}"/></label><label>Email<input id="standaloneEmail" type="email" value="${esc(state.user.email)}"/></label><p id="standaloneAccountError" class="form-error"></p><div class="dialog-actions"><button type="button" class="btn btn-secondary" id="standaloneLogout">Log out</button><button type="submit" class="btn btn-primary">Save</button></div></form>${planChooserHtml()}`;
    $('[data-standalone-close]',dialog).addEventListener('click',()=>dialog.close());
    el('standaloneLogout').addEventListener('click',()=>{dialog.close();logout();});
    wireAccountPlanButtons(dialog);
    el('standaloneAccountForm').addEventListener('submit', async e => {
      e.preventDefault();
      const {ok,data} = await api('/auth/me',{method:'PATCH',body:JSON.stringify({username:el('standaloneUsername').value.trim(),email:el('standaloneEmail').value.trim()})});
      if(!ok) return el('standaloneAccountError').textContent=data.error||'Could not save.';
      state.user={...state.user,...data};syncUserUI();dialog.close();toast('Account updated');
    });
    dialog.showModal();
  }

  async function openCheckout(plan) {
    state.checkoutPlan = plan;
    if (!state.user) return route('register');
    if(plan !== 'free'){
      toast('Redeem your upgrade code in Account');
      return route('account');
    }
    toast(state.user.plan === 'free' ? 'Your account is already on Free' : 'Paid plans return to Free only when their term expires');
    return route('account');
  }

  async function checkout(event) {
    event.preventDefault();
    const error = el('checkoutError');
    error.textContent = '';
    const {ok,data} = await api('/payments/checkout',{method:'POST',body:JSON.stringify({plan:state.checkoutPlan,duration_months:Number(el('checkoutDuration').value),method:'dummy'})});
    if(!ok) return error.textContent=data.error||'Checkout failed.';
    el('checkoutDialog').close();
    await checkAuth();
    if(state.project){
      const refreshed=await api(`/projects/${state.project.id}`);
      if(refreshed.ok){state.project=refreshed.data;syncProjectChrome();}
      if(state.panel==='account')await loadAccountPanel();
    } else if(el('view-projects').classList.contains('active')) {
      await loadProjects();
    }
    toast(`${state.checkoutPlan} account plan activated`);
  }

  function kpi(label, value, sub) {
    return `<div class="kpi"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(sub)}</small></div>`;
  }

  function activityTable(events) {
    return `<div class="data-table-wrap"><table class="data-table"><thead><tr><th>Member</th><th>Target</th><th>Event</th><th>Change</th><th>Time</th></tr></thead><tbody>${events.map(e=>`<tr><td><strong>${esc(e.username || state.user?.username || 'User')}</strong></td><td class="mono">${esc(e.script || e.script_name || e.instance_name || '—')}</td><td><span class="event-box">${esc(String(e.event_type || '').replace('_',' '))}</span></td><td>${e.count ? esc(`×${e.count} ${e.class_name || ''}`) : `<span class="positive">+${Number(e.chars_added)||0}</span> / <span class="negative">-${Number(e.chars_removed)||0}</span>`}</td><td class="muted">${esc(fmtDate(e.occurred_at))}</td></tr>`).join('')}</tbody></table></div>`;
  }

  function sessionTable(sessions) {
    if (!sessions.length) return emptyInline('No sessions yet', 'Connect Studio and start your first session.');
    return `<div class="data-table-wrap"><table class="data-table"><thead><tr><th>Started</th><th>Duration</th><th>Scripts</th><th>Status</th></tr></thead><tbody>${sessions.map(s=>`<tr><td>${esc(fmtDate(s.started_at))}</td><td>${esc(fmtDuration(s.duration_sec))}</td><td>${(s.events||[]).filter(e=>e.event_type==='open').length}</td><td class="${s.active?'status-live':''}">${s.active?'● Active':'Ended'}</td></tr>`).join('')}</tbody></table></div>`;
  }

  function memberStatsTable(members) {
    return `<div class="data-table-wrap"><table class="data-table"><thead><tr><th>Member</th><th>Role</th><th>Time</th><th>Sessions</th><th>Code +/−</th><th>Parts +/−</th><th>UI +/−</th><th>Status</th></tr></thead><tbody>${members.map(m=>`<tr><td><strong>${esc(m.username)}</strong></td><td><span class="role-box">${esc(roleName(m.role))}</span></td><td>${esc(fmtDuration(m.stats.total_seconds))}</td><td>${m.stats.total_sessions}</td><td><span class="positive">+${compactNumber(m.stats.chars_added)}</span> / <span class="negative">-${compactNumber(m.stats.chars_removed)}</span></td><td><span class="positive">+${compactNumber(m.stats.parts_added)}</span> / <span class="negative">-${compactNumber(m.stats.parts_removed)}</span></td><td><span class="positive">+${compactNumber(m.stats.ui_added)}</span> / <span class="negative">-${compactNumber(m.stats.ui_removed)}</span></td><td class="${m.active?'status-live':'muted'}">${m.active?'● Active':'Idle'}</td></tr>`).join('')}</tbody></table></div>`;
  }

  function emptyInline(title, message) {
    return `<div class="empty-state"><h2>${esc(title)}</h2><p>${esc(message)}</p></div>`;
  }

  function renderError(target, message) {
    target.innerHTML = emptyInline('Could not load this page', message || 'Try again.');
  }

  function chartOptions(yLabel) {
    const vars = themeChartColors();
    return {responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{displayColors:false}},scales:{x:{grid:{display:false},ticks:{color:vars.muted,font:{size:10},maxRotation:0,autoSkip:true,maxTicksLimit:7},border:{color:vars.border}},y:{beginAtZero:true,grid:{color:vars.border},ticks:{color:vars.muted,font:{size:10}},border:{display:false},title:{display:false,text:yLabel}}}};
  }

  function themeChartColors() {
    const styles = getComputedStyle(document.documentElement);
    return {accent:styles.getPropertyValue('--accent').trim(), accentSoft:styles.getPropertyValue('--accent-soft').trim(), muted:styles.getPropertyValue('--muted').trim(), border:styles.getPropertyValue('--border').trim()};
  }

  function destroyCharts() {
    Object.values(state.charts).forEach(chart => { try { chart.destroy(); } catch (_) {} });
    state.charts = {};
  }

  async function copyText(text, successMessage='Copied') {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {
      const area = document.createElement('textarea');
      area.value = text; area.style.position='fixed'; area.style.opacity='0'; document.body.appendChild(area); area.select(); document.execCommand('copy'); area.remove();
    }
    toast(successMessage);
  }

  function updateConnectionBadge(text, good = false) {
    const badge = el('connectionBadge');
    if (!badge) return;
    badge.textContent = text;
    badge.classList.toggle('good', good);
  }

  function openSidebar() { el('sidebar').classList.add('open'); el('sidebarBackdrop').classList.add('show'); }
  function closeSidebar() { el('sidebar').classList.remove('open'); el('sidebarBackdrop').classList.remove('show'); }

  function setupInteractionFeedback() {
    const selector = '.btn, .mini-btn, .icon-btn, .account-chip, .document-link, .side-nav button, .my-projects-btn';
    document.addEventListener('pointerdown', event => {
      const target = event.target.closest(selector);
      if (!target || target.disabled || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      target.classList.remove('interaction-pop');
      void target.offsetWidth;
      target.classList.add('interaction-pop');
    });
    document.addEventListener('animationend', event => {
      if (event.animationName === 'interactionPop') event.target.classList.remove('interaction-pop');
    });
  }

  function wireEvents() {
    $$('[data-route]').forEach(node => node.addEventListener('click', e => { e.preventDefault(); route(node.dataset.route); }));
    $$('[data-panel]').forEach(node => node.addEventListener('click', () => openPanel(node.dataset.panel)));
    $$('[data-plan]').forEach(node => node.addEventListener('click', () => openCheckout(node.dataset.plan)));
    $$('[data-dialog-close]').forEach(node => node.addEventListener('click', () => node.closest('dialog').close()));

    el('loginForm').addEventListener('submit', login);
    el('registerForm').addEventListener('submit', register);
    el('createProjectForm').addEventListener('submit', createProject);
    el('inviteForm').addEventListener('submit', inviteMember);
    el('checkoutForm').addEventListener('submit', checkout);
    el('createProjectBtn').addEventListener('click', openCreateProject);
    el('logoutButton').addEventListener('click', logout);
    el('themeToggle').addEventListener('click', toggleTheme);
    el('publicTheme').addEventListener('click', toggleTheme);
    el('projectsTheme').addEventListener('click', toggleTheme);
    el('sidebarMobileButton').addEventListener('click', openSidebar);
    el('sidebarClose').addEventListener('click', closeSidebar);
    el('sidebarBackdrop').addEventListener('click', closeSidebar);
  }

  async function init() {
    applyTheme(localStorage.getItem('rowatch-theme') || 'light');
    setupInteractionFeedback();
    wireEvents();
    await checkAuth();
    syncUserUI();
    connectLiveUpdates();
    await route(state.user ? 'projects' : 'home');
  }

  init();
})();
