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
    activityPage: 1,
    activitySearch: '',
    taskComposerOpen: false,
    taskColumns: [],
    editingTaskColumnId: null,
    deletingTaskColumnId: null,
    taskDragActive: false,
    taskRefreshPending: false,
    actionConfirmResolve: null,
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
      if (response.status === 403 && data.consent_required && path !== '/auth/consent') {
        if (state.user) {
          state.user.consent_required = true;
          state.user.current_consent_version = data.consent_version || state.user.current_consent_version;
          queueMicrotask(showLegalConsent);
        }
      }
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
    return role === 'co_admin' ? 'Project manager' : role === 'owner' ? 'Owner' : 'Member';
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
    el('publicNav').style.display = ['home', 'privacy', 'terms'].includes(name) ? '' : 'none';
    window.scrollTo({top: 0, behavior: 'auto'});
  }

  async function route(name, updateHistory = true) {
    closeSidebar();
    if (name === 'home') {
      state.project = null;
      setView('home');
      if (updateHistory && location.pathname !== '/') history.pushState(null, '', '/');
      return;
    }
    if (name === 'privacy' || name === 'terms') {
      state.project = null;
      setView(name);
      const path = `/${name}`;
      if (updateHistory && location.pathname !== path) history.pushState(null, '', path);
      requestAnimationFrame(() => {
        const section = location.hash && document.getElementById(location.hash.slice(1));
        if (section) section.scrollIntoView();
      });
      return;
    }
    if (name === 'login' || name === 'register') {
      setView(name);
      return;
    }
    if (name === 'projects') {
      if (!state.user) return route('login');
      if (state.user.consent_required) {
        setView('projects');
        showLegalConsent();
        return;
      }
      state.project = null;
      setView('projects');
      syncUserUI();
      await loadProjects();
      return;
    }
    if (name === 'account') {
      if (!state.user) return route('login');
      if (state.user.consent_required) { showLegalConsent(); return; }
      setView('account');
      syncUserUI();
      await loadAccountPage();
      return;
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

  function avatarColor(username) {
    const palette = ['#0c66e4', '#1f845a', '#c25100', '#7e4eab', '#ae2e24', '#227d9b', '#5e4db2', '#00875a'];
    const letter = String(username || 'R').trim().slice(0, 1).toUpperCase() || 'R';
    return palette[(letter.charCodeAt(0) - 65 + palette.length) % palette.length];
  }

  function syncUserUI() {
    const username = state.user?.username || 'Account';
    const initial = username.trim().slice(0, 1).toUpperCase() || 'R';
    ['projectsUsername','dashboardUsername','accountUsername','sideUsername'].forEach(id => { if (el(id)) el(id).textContent = username; });
    ['projectsAvatar','dashboardAvatar','accountAvatar'].forEach(id => {
      const node = el(id);
      if (!node) return;
      node.textContent = initial;
      node.style.backgroundColor = avatarColor(username);
      node.style.color = '#fff';
    });
  }

  async function checkAuth() {
    const {ok, data} = await api('/auth/me');
    if (ok) {
      state.user = data;
      syncUserUI();
    }
  }

  function showLegalConsent() {
    if (!state.user?.consent_required) return;
    const dialog = el('legalConsentDialog');
    el('legalConsentVersion').textContent = state.user.current_consent_version || 'Current';
    el('legalConsentCheckbox').checked = false;
    el('legalConsentAccept').disabled = true;
    el('legalConsentError').textContent = '';
    if (!dialog.open) dialog.showModal();
  }

  async function acceptCurrentConsent(event) {
    event.preventDefault();
    const checkbox = el('legalConsentCheckbox');
    const error = el('legalConsentError');
    if (!checkbox.checked) {
      error.textContent = 'Check the consent box to continue.';
      return;
    }
    const result = await api('/auth/consent', {
      method: 'POST',
      body: JSON.stringify({accepted: true}),
    });
    if (!result.ok) {
      error.textContent = result.data.error || 'Could not save consent.';
      return;
    }
    Object.assign(state.user, result.data, {
      current_consent_version: result.data.tracking_consent_version,
      consent_required: false,
    });
    el('legalConsentDialog').close();
    if (state.socket) {
      state.socket.disconnect();
      state.socket = null;
    }
    connectLiveUpdates();
    await route('projects');
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
      if (update.type === 'task_updated' || update.type === 'task_board_updated') {
        if (state.panel === 'tasks') {
          if (state.taskDragActive) state.taskRefreshPending = true;
          else state.liveRefreshTimer = setTimeout(() => loadTasks(true), 120);
        }
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
    const result = await api('/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        username: el('regUser').value.trim(),
        email: el('regEmail').value.trim(),
        password: el('regPw').value,
        tracking_consent: el('regTrackingConsent').checked,
      }),
    });
    if (!result.ok) return error.textContent = result.data.error || 'Registration failed.';
    await checkAuth();
    connectLiveUpdates();
    await route('projects');
  }


  async function logout() {
    await api('/auth/logout', {method: 'POST'});
    if (el('legalConsentDialog')?.open) el('legalConsentDialog').close();
    state.user = null;
    state.project = null;
    destroyCharts();
    state.socket?.disconnect();
    state.socket = null;
    await route('home');
  }

  async function loadProjects() {
    const target = el('projectsList');
    target.innerHTML = '<div class="projects-skeleton" aria-label="Loading projects"><div class="skeleton skeleton-project-card"><i></i><b></b><span></span><small></small></div><div class="skeleton skeleton-project-card"><i></i><b></b><span></span><small></small></div><div class="skeleton skeleton-project-card"><i></i><b></b><span></span><small></small></div></div>';
    const {ok, data} = await api('/projects/');
    if (!ok) {
      if (data.error === 'Unauthorized') return route('login');
      target.innerHTML = `<div class="empty-state"><h2>Could not load projects</h2><p>${esc(data.error || 'Try again.')}</p></div>`;
      return;
    }
    state.projects = data;
    target.innerHTML = data.map(p => `
      <article class="project-card" tabindex="0" data-project-id="${esc(p.id)}" aria-label="Open ${esc(p.name)}">
        <div class="project-card-head"><h2>${esc(p.name)}</h2></div>
        <p class="muted">${p.member_count} member${p.member_count === 1 ? '' : 's'} · ${esc(roleName(p.role))}</p>
        <div class="project-card-meta"><span>Created ${esc(fmtDate(p.created_at, false))}</span></div>
      </article>`).join('') + '<button class="create-project-card" id="createProjectBtn" type="button"><span>+</span>Create new project</button>';
    el('createProjectBtn').addEventListener('click', openCreateProject);
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
    el('sidebarProjectPlan').textContent = '';
    $$('.admin-only').forEach(node => node.style.display = isAdmin() ? '' : 'none');
    syncUserUI();
    applyTheme(localStorage.getItem('rowatch-theme') || 'light');
  }

  async function openPanel(name) {
    if (!state.project && name !== 'account') return route('projects');
    if (['analytics','members'].includes(name) && !isAdmin()) name = 'overview';
    state.panel = name;
    $$('.side-nav button').forEach(button => button.classList.toggle('active', button.dataset.panel === name));
    const titles = {overview:'Overview',activity:'Activity',tasks:'Tasks',documents:'Documentation',analytics:'Analytics',members:'Members',settings:'Project Settings',account:'Account'};
    const descriptions = {overview:`${state.project.name} development summary.`,activity:'',tasks:'Organize project work and assignments.',documents:'Project notes, setup guides, and shared references.',analytics:'Development time, code change volume, and member performance.',members:'',settings:`Manage settings for ${state.project.name}.`,account:'Manage your RoWatch account.'};
    el('panelTitle').textContent = name === 'members' ? '' : (titles[name] || 'Dashboard');
    el('panelDescription').textContent = descriptions[name] || '';
    el('topbarBreadcrumb').textContent = name === 'account' ? 'RoWatch / Account' : `${state.project.name} / ${titles[name]}`;
    const content = el('panelContent');
    content.innerHTML = '<div class="panel-skeleton" aria-label="Loading dashboard"><div class="skeleton-kpis"><div class="skeleton skeleton-kpi"><i></i><b></b><span></span></div><div class="skeleton skeleton-kpi"><i></i><b></b><span></span></div><div class="skeleton skeleton-kpi"><i></i><b></b><span></span></div><div class="skeleton skeleton-kpi"><i></i><b></b><span></span></div></div><div class="skeleton-panels"><div class="skeleton skeleton-panel"></div><div class="skeleton skeleton-panel"></div></div></div>';
    closeSidebar();

    const loaders = {overview: loadOverview, activity: loadActivity, tasks: loadTasks, documents: loadDocuments, analytics: loadAnalytics, members: loadMembers, settings: loadSettings, account: loadAccountPanel};
    await loaders[name]?.();
  }

  async function loadOverview() {
    destroyCharts();
    const content = el('panelContent');
    if (!isAdmin()) return loadMemberOverview();

    const [{ok, data}, activityResult] = await Promise.all([
      api(`/dashboard/${state.project.id}/overview`),
      api(`/dashboard/${state.project.id}/activity?page=1`),
    ]);
    if (!ok) return renderError(content, data.error);
    const members = data.members || [];
    const totalSeconds = members.reduce((sum, m) => sum + m.stats.total_seconds, 0);
    const charsAdded = members.reduce((sum, m) => sum + m.stats.chars_added, 0);
    const charsRemoved = members.reduce((sum, m) => sum + m.stats.chars_removed, 0);
    const sessions = members.reduce((sum, m) => sum + m.stats.total_sessions, 0);
    const recent = activityResult.ok ? (activityResult.data.items || []).slice(0, 7) : [];

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
        <div class="overview-side-stack">
          <section class="panel-card online-members-panel"><div class="panel-card-head"><div><h2>Currently online</h2><p>Active in this project now.</p></div><span class="online-count">${members.filter(member=>member.active).length}</span></div>${members.some(member=>member.active)?`<div class="online-member-list">${members.filter(member=>member.active).map(member=>`<div class="online-member"><span class="presence-dot"></span><strong>${esc(member.username)}</strong><small>${esc(roleName(member.role))}</small></div>`).join('')}</div>`:emptyInline('Nobody online','No project member has an active Studio session.')}</section>
          <section class="panel-card"><div class="panel-card-head"><div><h2>Member sessions</h2><p>Session count by developer.</p></div></div><div class="chart-box compact-chart"><canvas id="overviewMemberChart"></canvas></div></section>
        </div>
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
    const params = new URLSearchParams({page:String(state.activityPage), q:state.activitySearch});
    if (isAdmin() && state.activityMemberFilter !== 'all') params.set('member', state.activityMemberFilter);
    const requests = [api(`/dashboard/${state.project.id}/activity?${params}`)];
    if (isAdmin()) requests.push(api(`/projects/${state.project.id}/members`));
    const [activityResult, membersResult] = await Promise.all(requests);
    if (!activityResult.ok) return renderError(content, activityResult.data.error);
    const activity = activityResult.data;
    const events = activity.items || [];
    const members = isAdmin() && membersResult?.ok ? membersResult.data : [];
    if (state.activityMemberFilter !== 'all' && !members.some(member => member.username === state.activityMemberFilter)) {
      state.activityMemberFilter = 'all';
      state.activityPage = 1;
      return loadActivity();
    }
    const memberFilter = isAdmin() ? `<label>Member<select id="activityMemberFilter"><option value="all">All members</option>${members.map(member=>`<option value="${esc(member.username)}" ${state.activityMemberFilter===member.username?'selected':''}>${esc(member.username)}</option>`).join('')}</select></label>` : '';
    const exportButton = isAdmin() && state.project.plan !== 'free' ? `<a class="btn btn-secondary" href="/dashboard/${state.project.id}/export.csv" download>Export CSV</a>` : '';
    const pager = `<div class="activity-pager"><button id="activityPrevious" class="btn btn-secondary" type="button" ${activity.page<=1?'disabled':''}>Previous</button><span>Page ${activity.page} of ${activity.pages} · ${activity.total} results</span><button id="activityNext" class="btn btn-secondary" type="button" ${activity.page>=activity.pages?'disabled':''}>Next</button></div>`;
    content.innerHTML = `<div class="toolbar activity-toolbar"><div class="activity-query"><label>Search activity<input id="activitySearch" type="search" maxlength="100" value="${esc(state.activitySearch)}" placeholder="Member, target, event, or class" /></label>${memberFilter}</div><div class="toolbar-actions">${exportButton}</div></div>${events.length ? activityTable(events) : emptyInline('No matching activity', 'Try a different search or member filter.')}${pager}`;
    let searchTimer;
    el('activitySearch')?.addEventListener('input', event => {
      clearTimeout(searchTimer);
      const value = event.target.value;
      searchTimer = setTimeout(() => { state.activitySearch=value.trim(); state.activityPage=1; loadActivity(); }, 300);
    });
    el('activityMemberFilter')?.addEventListener('change', event => { state.activityMemberFilter=event.target.value; state.activityPage=1; loadActivity(); });
    el('activityPrevious')?.addEventListener('click', () => { state.activityPage=Math.max(1,state.activityPage-1); loadActivity(); });
    el('activityNext')?.addEventListener('click', () => { state.activityPage+=1; loadActivity(); });
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

  function taskCardMarkup(task) {
    const mine = task.assigned_to_me;
    const assignees = task.assignments.map(item=>`<span class="assignee-chip ${item.completed?'done':''}">${item.completed?'✓ ':''}${esc(item.username)}</span>`).join('');
    return `<article class="task-card ${task.my_completed?'task-done':''}" data-task-id="${esc(task.id)}" ${isAdmin()?'draggable="true"':''}><div class="task-check">${mine?`<input type="checkbox" data-task-complete="${esc(task.id)}" ${task.my_completed?'checked':''} aria-label="Complete ${esc(task.title)}"/>`:'<span>•</span>'}</div><div class="task-body"><div class="task-title-row"><h2>${esc(task.title)}</h2><span>${task.completed_count}/${task.assignments.length} complete</span></div>${task.description_md?`<div class="markdown task-markdown">${renderMarkdown(task.description_md)}</div>`:''}<div class="task-meta">${task.due_at?`<span>Due ${esc(fmtDate(task.due_at,false))}</span>`:'<span>No due date</span>'}<span>Created by ${esc(task.created_by)}</span></div><div class="assignee-chips">${assignees||'<span class="muted">Unassigned</span>'}</div></div>${isAdmin()?`<div class="task-admin-actions"><button class="icon-btn" data-edit-task="${esc(task.id)}" title="Edit task" aria-label="Edit task"><i data-lucide="pencil"></i></button><button class="icon-btn danger" data-delete-task="${esc(task.id)}" title="Delete task" aria-label="Delete task"><i data-lucide="trash-2"></i></button></div>`:''}</article>`;
  }

  async function loadTasks(quiet = false) {
    const content = el('panelContent');
    const [tasksResult, membersResult] = await Promise.all([api(`/workspace/${state.project.id}/tasks`), api(`/projects/${state.project.id}/members`)]);
    if (!tasksResult.ok) return renderError(content, tasksResult.data.error);
    const tasks = tasksResult.data.items || [];
    const columns = (tasksResult.data.columns || []).sort((a,b)=>a.position-b.position);
    state.taskColumns = columns;
    const taskUsage = tasksResult.data.usage;
    const members = membersResult.ok ? membersResult.data : [];
    if (state.taskAssigneeFilter !== 'all' && !members.some(member => member.user_id === state.taskAssigneeFilter)) state.taskAssigneeFilter = 'all';
    const visibleTasks = state.taskAssigneeFilter === 'all' ? tasks : tasks.filter(task => task.assignments.some(item => item.user_id === state.taskAssigneeFilter));
    const editing = tasks.find(task => task.id === state.editTaskId);
    const memberChecks = members.map(member => `<label class="assignee-option"><input type="checkbox" name="taskAssignee" value="${esc(member.user_id)}" ${editing?.assignments.some(item=>item.user_id===member.user_id)?'checked':''}/><span>${esc(member.username)}</span><small>${esc(roleName(member.role))}</small></label>`).join('');
    const columnOptions = columns.map(column=>`<option value="${esc(column.id)}" ${(editing?.column_id||columns[0]?.id)===column.id?'selected':''}>${esc(column.name)}</option>`).join('');
    const editor = isAdmin() && (state.taskComposerOpen || editing) ? `<section class="panel-card task-editor"><div class="panel-card-head task-editor-head"><div><h2>${editing?'Edit task':'Create task'}</h2><p>Assign one task to one or more project members.</p></div><button id="closeTaskEditor" class="dialog-x" type="button" aria-label="Close task editor">×</button></div><div class="task-form-grid"><label>Title<input id="taskTitle" maxlength="32" value="${esc(editing?.title||'')}" placeholder="Ship inventory UI"/></label><label>Column<select id="taskColumn">${columnOptions}</select></label><label>Due date<input id="taskDue" type="date" value="${esc(editing?.due_at?.slice(0,10)||'')}"/></label></div><label>Description (Markdown)<textarea id="taskDescription" rows="4" placeholder="## Acceptance criteria">${esc(editing?.description_md||'')}</textarea></label><div class="assignee-help"><strong>Assign task to</strong><span>Select the checkboxes for the people responsible. You can choose multiple people.</span></div><div class="assignee-grid">${memberChecks || '<span class="muted">Add project members before assigning tasks.</span>'}</div><div class="task-actions"><button id="saveTask" class="btn btn-primary" type="button">${editing?'Save changes':'Create task'}</button><button id="cancelTaskEdit" class="btn btn-secondary" type="button">Cancel</button></div><p id="taskError" class="form-error"></p></section>` : '';
    const filterOptions = [`<option value="all">All members</option>`, ...members.map(member => `<option value="${esc(member.user_id)}" ${state.taskAssigneeFilter===member.user_id?'selected':''}>${esc(member.username)}</option>`)].join('');
    const board = columns.map(column=>{
      const cards=visibleTasks.filter(task=>task.column_id===column.id).sort((a,b)=>a.position-b.position).map(taskCardMarkup).join('');
      return `<section class="task-column" data-column-id="${esc(column.id)}" ${isAdmin()?'draggable="true"':''}><header class="task-column-head"><div class="task-column-title">${isAdmin()?'<i class="column-grip" data-lucide="grip-vertical"></i>':''}<strong>${esc(column.name)}</strong><span>${column.task_count}</span></div>${isAdmin()?`<div class="column-actions"><button class="icon-btn" data-rename-column="${esc(column.id)}" title="Rename column" aria-label="Rename ${esc(column.name)}"><i data-lucide="pencil"></i></button><button class="icon-btn danger" data-delete-column="${esc(column.id)}" title="Delete column" aria-label="Delete ${esc(column.name)}"><i data-lucide="trash-2"></i></button></div>`:''}</header><div class="task-column-list" data-column-drop="${esc(column.id)}">${cards||'<div class="column-empty">Drop tasks here</div>'}</div></section>`;
    }).join('');
    content.innerHTML = `<div class="toolbar task-toolbar"><div></div><div class="task-filter"><label>Filter by assignee<select id="taskAssigneeFilter">${filterOptions}</select></label>${isAdmin()?'<button id="addTaskColumnButton" class="btn btn-secondary" type="button"><i data-lucide="columns-3"></i> Add column</button><button id="createTaskButton" class="btn btn-primary" type="button">+ Create task</button>':''}<span class="role-box">${visibleTasks.length}/${tasks.length} shown · ${taskUsage.limit===null?'Unlimited':`${taskUsage.current}/${taskUsage.limit}`}</span></div></div><div id="taskBoard" class="task-board">${board}</div>`;
    const taskDialog = el('taskEditorDialog');
    el('taskDialogContent').innerHTML = editor;
    if (editor && !taskDialog.open) taskDialog.showModal();
    if (!editor && taskDialog.open) taskDialog.close();
    el('createTaskButton')?.addEventListener('click',()=>{state.editTaskId=null;state.taskComposerOpen=true;loadTasks(true);});
    el('addTaskColumnButton')?.addEventListener('click',()=>openTaskColumnDialog());
    el('taskAssigneeFilter').value = state.taskAssigneeFilter;
    el('taskAssigneeFilter').addEventListener('change', event => { state.taskAssigneeFilter=event.target.value; loadTasks(true); });
    el('saveTask')?.addEventListener('click', saveTask);
    el('closeTaskEditor')?.addEventListener('click', closeTaskEditor);
    el('cancelTaskEdit')?.addEventListener('click', closeTaskEditor);
    $$('[data-task-complete]',content).forEach(node=>node.addEventListener('change',()=>toggleTask(node.dataset.taskComplete,node.checked)));
    $$('[data-edit-task]',content).forEach(node=>node.addEventListener('click',()=>{state.editTaskId=node.dataset.editTask;state.taskComposerOpen=true;loadTasks();}));
    $$('[data-delete-task]',content).forEach(node=>node.addEventListener('click',()=>deleteTask(node.dataset.deleteTask)));
    $$('[data-rename-column]',content).forEach(node=>node.addEventListener('click',()=>openTaskColumnDialog(columns.find(column=>column.id===node.dataset.renameColumn))));
    $$('[data-delete-column]',content).forEach(node=>node.addEventListener('click',()=>openDeleteTaskColumn(node.dataset.deleteColumn)));
    if (isAdmin()) wireTaskBoardDrag();
    window.lucide?.createIcons();
  }

  function openTaskColumnDialog(column = null) {
    state.editingTaskColumnId = column?.id || null;
    el('taskColumnDialogTitle').textContent = column ? 'Rename column' : 'New column';
    el('taskColumnName').value = column?.name || '';
    el('taskColumnError').textContent = '';
    el('taskColumnSubmit').textContent = column ? 'Save name' : 'Create column';
    el('taskColumnDialog').showModal();
    setTimeout(()=>el('taskColumnName').focus(),0);
  }

  async function saveTaskColumn(event) {
    event.preventDefault();
    const name=el('taskColumnName').value.trim();
    const path=state.editingTaskColumnId?`/workspace/${state.project.id}/task-columns/${state.editingTaskColumnId}`:`/workspace/${state.project.id}/task-columns`;
    const result=await api(path,{method:state.editingTaskColumnId?'PATCH':'POST',body:JSON.stringify({name})});
    if(!result.ok)return el('taskColumnError').textContent=result.data.error||'Could not save column.';
    el('taskColumnDialog').close(); state.editingTaskColumnId=null; toast('Column saved'); await loadTasks(true);
  }

  function openDeleteTaskColumn(columnId) {
    const column=state.taskColumns.find(item=>item.id===columnId);
    if(!column)return;
    state.deletingTaskColumnId=columnId;
    el('deleteTaskColumnMessage').textContent=column.task_count?`${column.task_count} task${column.task_count===1?'':'s'} will be moved before “${column.name}” is deleted.`:`“${column.name}” is empty and can be deleted safely.`;
    const destinations=state.taskColumns.filter(item=>item.id!==columnId);
    el('deleteTaskColumnDestinationWrap').hidden=!column.task_count;
    el('deleteTaskColumnDestination').innerHTML=destinations.map(item=>`<option value="${esc(item.id)}">${esc(item.name)}</option>`).join('');
    el('deleteTaskColumnError').textContent='';
    el('deleteTaskColumnSubmit').textContent=column.task_count?'Move tasks and delete':'Delete column';
    el('deleteTaskColumnDialog').showModal();
  }

  async function deleteTaskColumn(event) {
    event.preventDefault();
    const column=state.taskColumns.find(item=>item.id===state.deletingTaskColumnId);
    const payload=column?.task_count?{destination_column_id:el('deleteTaskColumnDestination').value}:{};
    const result=await api(`/workspace/${state.project.id}/task-columns/${state.deletingTaskColumnId}`,{method:'DELETE',body:JSON.stringify(payload)});
    if(!result.ok)return el('deleteTaskColumnError').textContent=result.data.error||'Could not delete column.';
    el('deleteTaskColumnDialog').close(); state.deletingTaskColumnId=null; toast(result.data.moved_tasks?'Tasks moved and column deleted':'Column deleted'); await loadTasks(true);
  }

  function animateBoardMove(container, item, before) {
    const nodes=[...container.children].filter(node=>node!==item && !node.classList.contains('column-empty'));
    const previous=new Map(nodes.map(node=>[node,node.getBoundingClientRect()]));
    container.insertBefore(item,before || null);
    nodes.forEach(node=>{const old=previous.get(node),now=node.getBoundingClientRect();const x=old.left-now.left,y=old.top-now.top;if(x||y)node.animate([{transform:`translate(${x}px,${y}px)`},{transform:'translate(0,0)'}],{duration:220,easing:'cubic-bezier(.2,.8,.2,1)'});});
  }

  function wireTaskBoardDrag() {
    const board=el('taskBoard');
    let draggedTask=null,draggedColumn=null;
    $$('.task-card',board).forEach(card=>card.addEventListener('dragstart',event=>{event.stopPropagation();draggedTask=card;state.taskDragActive=true;card.classList.add('dragging');event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',card.dataset.taskId);}));
    $$('.task-column',board).forEach(column=>{
      column.addEventListener('dragstart',event=>{if(draggedTask||event.target.closest('.task-card'))return;draggedColumn=column;state.taskDragActive=true;column.classList.add('dragging-column');event.dataTransfer.effectAllowed='move';});
      column.addEventListener('dragend',()=>{column.classList.remove('dragging-column');draggedColumn=null;finishTaskDrag();});
    });
    board.addEventListener('dragover',event=>{if(!draggedColumn||draggedTask)return;event.preventDefault();const siblings=$$('.task-column:not(.dragging-column)',board);const before=siblings.find(node=>event.clientX<node.getBoundingClientRect().left+node.offsetWidth/2);animateBoardMove(board,draggedColumn,before);});
    board.addEventListener('drop',async event=>{if(!draggedColumn||draggedTask)return;event.preventDefault();const ids=$$('.task-column',board).map(node=>node.dataset.columnId);const result=await api(`/workspace/${state.project.id}/task-columns/reorder`,{method:'PUT',body:JSON.stringify({column_ids:ids})});if(!result.ok)toast(result.data.error||'Could not reorder columns.');await loadTasks(true);});
    $$('[data-column-drop]',board).forEach(list=>{
      list.addEventListener('dragenter',event=>{if(draggedTask){event.preventDefault();list.classList.add('drop-active');}});
      list.addEventListener('dragleave',event=>{if(!list.contains(event.relatedTarget))list.classList.remove('drop-active');});
      list.addEventListener('dragover',event=>{if(!draggedTask)return;event.preventDefault();event.dataTransfer.dropEffect='move';const empty=$('.column-empty',list);empty?.remove();const siblings=$$('.task-card:not(.dragging)',list);const before=siblings.find(node=>event.clientY<node.getBoundingClientRect().top+node.offsetHeight/2);animateBoardMove(list,draggedTask,before);});
      list.addEventListener('drop',async event=>{if(!draggedTask)return;event.preventDefault();event.stopPropagation();list.classList.remove('drop-active');const taskId=draggedTask.dataset.taskId,columnId=list.dataset.columnDrop,position=$$('.task-card',list).indexOf(draggedTask);const result=await api(`/workspace/${state.project.id}/tasks/${taskId}/move`,{method:'POST',body:JSON.stringify({column_id:columnId,position})});if(!result.ok)toast(result.data.error||'Could not move task.');else toast('Task moved');await loadTasks(true);});
    });
    $$('.task-card',board).forEach(card=>card.addEventListener('dragend',()=>{card.classList.remove('dragging');$$('.drop-active',board).forEach(node=>node.classList.remove('drop-active'));draggedTask=null;finishTaskDrag();}));
  }

  function finishTaskDrag(){state.taskDragActive=false;if(state.taskRefreshPending){state.taskRefreshPending=false;loadTasks(true);}}

  function closeTaskEditor() {
    state.editTaskId = null;
    state.taskComposerOpen = false;
    if (el('taskEditorDialog').open) el('taskEditorDialog').close();
    loadTasks(true);
  }

  async function saveTask() {
    const title = el('taskTitle').value.trim();
    const assignee_ids = $$('input[name="taskAssignee"]:checked').map(node=>node.value);
    const payload = {title, column_id:el('taskColumn').value, description_md:el('taskDescription').value, due_at:el('taskDue').value||null, assignee_ids};
    const path = state.editTaskId ? `/workspace/${state.project.id}/tasks/${state.editTaskId}` : `/workspace/${state.project.id}/tasks`;
    const result = await api(path,{method:state.editTaskId?'PATCH':'POST',body:JSON.stringify(payload)});
    if(!result.ok) return el('taskError').textContent=result.data.error||'Could not save task.';
    state.editTaskId=null; state.taskComposerOpen=false; el('taskEditorDialog').close(); toast('Task saved'); await loadTasks(true);
  }

  async function toggleTask(taskId, completed) {
    const result = await api(`/workspace/${state.project.id}/tasks/${taskId}/complete`,{method:'POST',body:JSON.stringify({completed})});
    if(!result.ok){toast(result.data.error||'Could not update task.');return loadTasks(true);}
    await loadTasks(true);
  }

  function requestConfirmation({title='Confirm action',message='',confirmLabel='Confirm',phrase=''}) {
    const dialog=el('actionConfirmDialog');
    el('actionConfirmTitle').textContent=title;
    el('actionConfirmMessage').textContent=message;
    el('actionConfirmSubmit').textContent=confirmLabel;
    el('actionConfirmPhraseWrap').hidden=!phrase;
    el('actionConfirmPhrase').value='';
    el('actionConfirmPhrase').dataset.expected=phrase;
    el('actionConfirmError').textContent='';
    dialog.showModal();
    setTimeout(()=>el('actionConfirmCancel').focus(),0);
    return new Promise(resolve=>{state.actionConfirmResolve=resolve;});
  }

  function finishConfirmation(accepted) {
    const resolve=state.actionConfirmResolve;
    state.actionConfirmResolve=null;
    if(el('actionConfirmDialog').open)el('actionConfirmDialog').close();
    resolve?.(accepted);
  }

  async function deleteTask(taskId) {
    if(!await requestConfirmation({title:'Delete task?',message:'This removes the task for every assignee.',confirmLabel:'Delete task'})) return;
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
    const documentWordLimit = documentUsage.plan === 'free' ? 1028 : null;
    const documentFooter = selected ? `<footer class="document-meta-footer"><span>Created by <strong>${esc(selected.created_by)}</strong></span><span>Last modified by <strong>${esc(selected.updated_by || selected.created_by)}</strong></span></footer>` : '';
    if(editingDocument)detail=`<div class="document-editor"><input id="documentTitle" maxlength="32" value="${esc(selected.title)}"/><textarea id="documentContent" rows="18" placeholder="# Documentation">${esc(selected.content_md)}</textarea><div id="documentContentCount" class="content-counter" aria-live="polite"></div><div class="task-actions"><button id="saveDocument" class="btn btn-primary">Save document</button><button id="cancelDocumentEdit" class="btn btn-secondary">Cancel</button><button id="deleteDocument" class="btn btn-danger">Delete</button></div><h3>Preview</h3><div class="markdown document-preview">${renderMarkdown(selected.content_md)}</div>${documentFooter}</div>`;
    else if(selected)detail=`<article class="document-reader"><div class="document-reader-head"><h1>${esc(selected.title)}</h1>${isAdmin()?'<button id="editDocument" class="btn btn-primary">Edit document</button>':''}</div><div class="markdown">${renderMarkdown(selected.content_md)}</div>${documentFooter}</article>`;
    else detail=emptyInline('No documentation yet',isAdmin()?'Create the first Markdown document.':'Project admins have not added documentation yet.');
    content.innerHTML=`<div class="toolbar documents-toolbar"><div></div><div class="task-filter"><span class="role-box">${documentUsage.limit===null?'Unlimited':`${documentUsage.current}/${documentUsage.limit} documents`}</span>${isAdmin()?'<button id="newDocument" class="btn btn-primary">+ New document</button>':''}</div></div><div class="documents-layout"><aside class="documents-list">${list||'<span class="muted">No documents</span>'}</aside><section class="panel-card">${detail}</section></div>`;
    $$('[data-document-id]',content).forEach(node=>node.addEventListener('click',()=>{state.activeDocumentId=node.dataset.documentId;state.editingDocumentId=null;loadDocuments();}));
    el('newDocument')?.addEventListener('click',openDocumentTitleDialog);
    el('editDocument')?.addEventListener('click',()=>{state.editingDocumentId=state.activeDocumentId;loadDocuments();});
    el('cancelDocumentEdit')?.addEventListener('click',()=>{state.editingDocumentId=null;loadDocuments();});
    el('saveDocument')?.addEventListener('click',saveDocument);
    el('deleteDocument')?.addEventListener('click',deleteDocument);
    const updateDocumentCounter = value => {
      const counter = el('documentContentCount');
      if (!counter) return;
      const words = String(value || '').trim() ? String(value).trim().split(/\s+/).length : 0;
      const characters = String(value || '').length;
      counter.textContent = documentWordLimit === null
        ? `${characters.toLocaleString()} characters · ${words.toLocaleString()} words`
        : `${characters.toLocaleString()} characters · ${words.toLocaleString()} / ${documentWordLimit.toLocaleString()} words`;
      counter.classList.toggle('over-limit', documentWordLimit !== null && words > documentWordLimit);
    };
    const documentContent = el('documentContent');
    if (documentContent) updateDocumentCounter(documentContent.value);
    documentContent?.addEventListener('input', event => {
      updateDocumentCounter(event.target.value);
      const preview = $('.document-preview', content);
      if (preview) preview.innerHTML = renderMarkdown(event.target.value);
    });
  }

  function openDocumentTitleDialog(){
    el('newDocumentTitle').value='';
    el('documentTitleError').textContent='';
    el('documentTitleDialog').showModal();
    setTimeout(()=>el('newDocumentTitle').focus(),0);
  }

  async function createDocument(event){
    event?.preventDefault();
    const title=el('newDocumentTitle').value.trim();if(!title)return;
    const result=await api(`/workspace/${state.project.id}/documents`,{method:'POST',body:JSON.stringify({title:title.trim(),content_md:'# '+title.trim()+'\n'})});
    if(!result.ok)return el('documentTitleError').textContent=result.data.error||'Could not create document.';
    el('documentTitleDialog').close();
    state.activeDocumentId=result.data.id;state.editingDocumentId=null;await loadDocuments(true);
  }

  async function saveDocument(){
    const result=await api(`/workspace/${state.project.id}/documents/${state.activeDocumentId}`,{method:'PATCH',body:JSON.stringify({title:el('documentTitle').value.trim(),content_md:el('documentContent').value})});
    if(!result.ok)return toast(result.data.error||'Could not save document.');state.editingDocumentId=null;toast('Document saved');await loadDocuments(true);
  }

  async function deleteDocument(){
    if(!await requestConfirmation({title:'Delete document?',message:'This document will be permanently removed.',confirmLabel:'Delete document'}))return;
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
      <div class="data-table-wrap"><table class="data-table"><thead><tr><th>User</th><th>Role</th><th>Presence</th><th>Joined</th><th>Actions</th></tr></thead><tbody>${data.map(m => `<tr><td><strong>${esc(m.username)}</strong></td><td><span class="role-box">${esc(roleName(m.role))}</span></td><td>${m.active?'<span class="member-presence online"><i></i>Online</span>':m.last_seen?`<span class="member-presence"><i></i>Last seen ${esc(fmtDate(m.last_seen))}</span>`:'<span class="member-presence"><i></i>Offline</span>'}</td><td>${esc(fmtDate(m.joined_at,false))}</td><td>${memberActions(m)}</td></tr>`).join('')}</tbody></table></div>`;
    el('inviteMemberButton').addEventListener('click', () => { el('inviteUsername').value=''; el('inviteError').textContent=''; el('inviteDialog').showModal(); });
    $$('[data-member-role]', content).forEach(b => b.addEventListener('click', () => changeMemberRole(b.dataset.userId, b.dataset.memberRole)));
    $$('[data-member-remove]', content).forEach(b => b.addEventListener('click', () => removeMember(b.dataset.userId, b.dataset.username)));
  }

  function memberActions(member) {
    if (!isOwner() || member.role === 'owner') return '<span class="muted">—</span>';
    const next = member.role === 'co_admin' ? 'member' : 'co_admin';
    return `<div class="member-actions"><button class="mini-btn" type="button" data-member-role="${next}" data-user-id="${esc(member.user_id)}">Make ${next === 'co_admin' ? 'Project manager' : 'member'}</button><button class="mini-btn danger" type="button" data-member-remove data-user-id="${esc(member.user_id)}" data-username="${esc(member.username)}">Remove</button></div>`;
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
    if (!await requestConfirmation({title:'Remove member?',message:`Remove ${username} from this project?`,confirmLabel:'Remove member'})) return;
    const {ok, data} = await api(`/projects/${state.project.id}/members/${userId}`, {method:'DELETE'});
    if (!ok) return toast(data.error || 'Could not remove member.');
    toast(`${username} removed`); await loadMembers();
  }

  async function loadSettings() {
    const content = el('panelContent');
    const p = state.project;
    content.innerHTML = `
      <div class="settings-stack">
        <section class="settings-row"><h2>Roblox Studio connection</h2><p>Studio authenticates as your RoWatch account and loads every project you belong to.</p><div class="dialog-actions integration-actions"><a class="btn btn-primary" href="https://create.roblox.com/store/asset/92589984687196/RoWatch-Beta" target="_blank" rel="noopener noreferrer">Install RoWatch from Creator Store</a></div><ol class="setup-list"><li><strong>Install the plugin</strong> from the Roblox Creator Store using the button above.</li><li><strong>Allow HTTP Requests</strong> in Roblox Studio game settings.</li><li><strong>Open Account</strong> and copy your Studio API key.</li><li><strong>Paste the API key</strong> into the plugin and select this project.</li><li><strong>Start a session</strong> before working and end it when you are done.</li></ol></section>
        <section class="settings-row"><h2>Access control</h2><p>The plugin can select this project only while the API-key owner is a project member. Removing a member immediately removes their access.</p></section>
        <section class="settings-row"><h2>Project details</h2><p>${isOwner() ? 'Rename the project. Changes are visible to every member.' : 'Only the project owner can rename this project.'}</p><div class="key-line"><input id="projectNameInput" maxlength="32" value="${esc(p.name)}" ${isOwner() ? '' : 'readonly'}/>${isOwner() ? '<button id="saveProjectName" class="btn btn-primary" type="button">Save</button>' : ''}</div></section>
        ${isOwner() ? '<section class="settings-row danger-zone"><h2>Delete project</h2><p>Permanently deletes this project, its memberships, sessions, and script events.</p><button id="deleteProject" class="btn btn-danger" type="button">Delete project</button></section>' : ''}
      </div>`;
    el('saveProjectName')?.addEventListener('click', saveProjectName);
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

  async function deleteProject() {
    if (!await requestConfirmation({title:'Delete project?',message:'This permanently removes the project, memberships, sessions, and activity.',confirmLabel:'Delete project',phrase:state.project.name})) return;
    const {ok, data} = await api(`/projects/${state.project.id}`, {method:'DELETE'});
    if (!ok) return toast(data.error || 'Could not delete project.');
    toast('Project deleted');
    await route('projects');
  }

  function planChooserHtml() {
    const current = state.user?.plan || 'free';
    const expires = state.user?.plan_expires_at ? `Expires ${fmtDate(state.user.plan_expires_at,false)}` : (current === 'free' ? 'No expiry' : 'Active');
    const plans = [
      {id:'free',price:'$0',period:'forever',features:['1 owned project','5 members per project','10 tasks · 3 documents','1,028 words per document','7 days history']},
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
    else if(el('view-account').classList.contains('active')) await loadAccountPage();
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

  function accountContentHtml(apiKey) {
    const visibleKey = apiKey.api_key || apiKey.masked_key || 'Not generated';
    return `<section class="panel-card"><div class="panel-card-head"><div><h2>Account details</h2><p>Your username identifies you across project activity.</p></div></div><div class="account-grid"><label>Username<input data-account-username maxlength="32" value="${esc(state.user.username)}"/></label><label>Email<input data-account-email type="email" value="${esc(state.user.email)}"/></label></div><button class="btn btn-primary" type="button" data-save-account>Save account</button></section><section class="panel-card api-key-card"><div class="panel-card-head"><div><h2>Studio API key</h2><p>Paste this account key into the plugin. It will fetch every project you belong to.</p></div></div><div class="redeem-code-line"><input class="mono" data-account-api-key value="${esc(visibleKey)}" readonly/><button class="btn btn-secondary" type="button" data-copy-api-key ${apiKey.api_key?'':'disabled'}>Copy</button></div><p class="muted">${apiKey.api_key?'This is the only time the complete key is shown.':'Only the key prefix is stored for display. Regenerate if you no longer have the complete key.'}</p><div class="dialog-actions"><button class="btn btn-secondary" type="button" data-regenerate-api-key>Regenerate API key</button></div><p class="form-error" data-api-key-error></p></section>`;
  }

  function wireAccountContent(root) {
    $('[data-save-account]', root)?.addEventListener('click', async () => {
      const result = await api('/auth/me', {
        method: 'PATCH',
        body: JSON.stringify({
          username: $('[data-account-username]', root).value.trim(),
          email: $('[data-account-email]', root).value.trim(),
        }),
      });
      if (!result.ok) return toast(result.data.error || 'Could not save account.');
      state.user = {...state.user, ...result.data};
      syncUserUI();
      toast('Account updated');
    });
    $('[data-copy-api-key]', root)?.addEventListener('click', () => {
      copyText($('[data-account-api-key]', root).value, 'API key copied');
    });
    $('[data-regenerate-api-key]', root)?.addEventListener('click', async () => {
      if (!await requestConfirmation({title:'Regenerate API key?',message:'Every connected Studio plugin will be signed out immediately.',confirmLabel:'Regenerate key'})) return;
      const result = await api('/auth/api-key/regenerate', {method:'POST', body:'{}'});
      if (!result.ok) return $('[data-api-key-error]', root).textContent = result.data.error || 'Could not regenerate API key.';
      const input = $('[data-account-api-key]', root);
      input.value = result.data.api_key;
      $('[data-copy-api-key]', root).disabled = false;
      toast('API key regenerated');
    });
  }

  async function loadAccountPanel() {
    const content = el('panelContent');
    const result = await api('/auth/me');
    if (!result.ok) return renderError(content, result.data.error);
    state.user = result.data; syncUserUI();
    const keyResult = await api('/auth/api-key', {method:'POST', body:'{}'});
    content.innerHTML = `<div class="account-panel">${accountContentHtml(keyResult.data)}${planChooserHtml()}</div>`;
    wireAccountContent(content);
    wireAccountPlanButtons(content);
  }

  function switchAccountSection(name) {
    $$('.account-page-section').forEach(section=>section.hidden=section.dataset.accountPane!==name);
    $$('[data-account-section]').forEach(button=>button.classList.toggle('active',button.dataset.accountSection===name));
  }

  async function loadAccountPage() {
    const content = el('accountPageContent');
    content.innerHTML = '<div class="panel-skeleton"><div class="skeleton skeleton-panel"></div><div class="skeleton skeleton-panel"></div></div>';
    const result = await api('/auth/me');
    if (!result.ok) return renderError(content, result.data.error);
    state.user = result.data;
    syncUserUI();
    const keyResult = await api('/auth/api-key', {method:'POST', body:'{}'});
    content.innerHTML = '<section id="account-profile" class="account-page-section">' + accountContentHtml(keyResult.data) + '</section><section id="account-plan" class="account-page-section">' + planChooserHtml() + '</section><section id="account-appearance" class="account-page-section appearance-section"><div><h2>Appearance</h2><p>Choose the interface theme used across the landing page and application.</p></div><button id="accountAppearanceToggle" class="btn btn-secondary" type="button">Toggle light / dark</button></section>';
    const apiCard = content.querySelector('.api-key-card');
    if (apiCard) {
      const studioSection=document.createElement('section');
      studioSection.id='account-studio';
      studioSection.className='account-page-section';
      studioSection.dataset.accountPane='studio';
      content.insertBefore(studioSection, el('account-plan'));
      studioSection.appendChild(apiCard);
    }
    el('account-profile').dataset.accountPane='profile';
    el('account-plan').dataset.accountPane='plan';
    el('account-appearance').dataset.accountPane='appearance';
    wireAccountContent(content);
    wireAccountPlanButtons(content);
    el('accountAppearanceToggle')?.addEventListener('click', toggleTheme);
    switchAccountSection('profile');
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
    const keyResult = await api('/auth/api-key', {method:'POST', body:'{}'});
    dialog.innerHTML = `<div class="dialog-head"><div><h2>Account</h2><p>Profile, Studio access, and account plan.</p></div><button type="button" class="dialog-x" data-standalone-close>x</button></div>${accountContentHtml(keyResult.data)}${planChooserHtml()}<div class="dialog-actions"><button type="button" class="btn btn-secondary" id="standaloneLogout">Log out</button></div>`;
    $('[data-standalone-close]',dialog).addEventListener('click',()=>dialog.close());
    el('standaloneLogout').addEventListener('click',()=>{dialog.close();logout();});
    wireAccountContent(dialog);
    wireAccountPlanButtons(dialog);
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
    el('legalConsentForm').addEventListener('submit', acceptCurrentConsent);
    el('legalConsentCheckbox').addEventListener('change', event => { el('legalConsentAccept').disabled = !event.target.checked; });
    el('legalConsentLogout').addEventListener('click', logout);
    el('legalConsentDialog').addEventListener('cancel', event => event.preventDefault());
    el('createProjectForm').addEventListener('submit', createProject);
    el('inviteForm').addEventListener('submit', inviteMember);
    el('checkoutForm').addEventListener('submit', checkout);
    el('documentTitleForm').addEventListener('submit', createDocument);
    el('taskColumnForm').addEventListener('submit', saveTaskColumn);
    el('deleteTaskColumnForm').addEventListener('submit', deleteTaskColumn);
    el('actionConfirmForm').addEventListener('submit',event=>{
      event.preventDefault();
      const expected=el('actionConfirmPhrase').dataset.expected||'';
      if(expected && el('actionConfirmPhrase').value!==expected){
        el('actionConfirmError').textContent='Type the exact name to continue.';
        return;
      }
      finishConfirmation(true);
    });
    el('actionConfirmCancel').addEventListener('click',()=>finishConfirmation(false));
    el('actionConfirmDialog').addEventListener('cancel',event=>{event.preventDefault();finishConfirmation(false);});
    el('taskEditorDialog').addEventListener('cancel',event=>{event.preventDefault();closeTaskEditor();});

    el('createProjectBtn')?.addEventListener('click', openCreateProject);
    el('logoutButton')?.addEventListener('click', logout);
    el('themeToggle')?.addEventListener('click', toggleTheme);
    el('publicTheme')?.addEventListener('click', toggleTheme);
    el('projectsTheme').addEventListener('click', toggleTheme);
    el('dashboardTheme')?.addEventListener('click', toggleTheme);
    el('accountTheme')?.addEventListener('click', toggleTheme);
    $$('[data-logout]').forEach(button=>button.addEventListener('click',logout));
    $$('[data-account-section]').forEach(button=>button.addEventListener('click',()=>switchAccountSection(button.dataset.accountSection)));
    const closeUserMenus = () => {
      $$('.user-menu').forEach(menu=>menu.hidden=true);
      $$('[data-user-menu]').forEach(trigger=>trigger.setAttribute('aria-expanded','false'));
    };
    $$('[data-user-menu]').forEach(button=>button.addEventListener('click',event=>{
      event.stopPropagation();
      const menu=button.nextElementSibling;
      const opening=menu.hidden;
      closeUserMenus();
      menu.hidden=!opening;
      button.setAttribute('aria-expanded',String(opening));
      if(opening) menu.querySelector('button')?.focus({preventScroll:true});
    }));
    $$('.user-menu').forEach(menu=>menu.addEventListener('click',event=>event.stopPropagation()));
    document.addEventListener('click',closeUserMenus);
    document.addEventListener('keydown',event=>{if(event.key==='Escape')closeUserMenus();});
    el('sidebarMobileButton').addEventListener('click', openSidebar);
    el('sidebarClose').addEventListener('click', closeSidebar);
    el('sidebarBackdrop').addEventListener('click', closeSidebar);
    window.addEventListener('popstate', () => {
      const page = location.pathname === '/privacy' ? 'privacy' : location.pathname === '/terms' ? 'terms' : 'home';
      route(page, false);
    });
  }

  async function init() {
    applyTheme(localStorage.getItem('rowatch-theme') || 'light');
    setupInteractionFeedback();
    window.lucide?.createIcons();
    wireEvents();
    await checkAuth();
    syncUserUI();
    connectLiveUpdates();
    const publicPage = location.pathname === '/privacy' ? 'privacy' : location.pathname === '/terms' ? 'terms' : null;
    await route(publicPage || (state.user ? 'projects' : 'home'), false);
  }

  init();
})();
