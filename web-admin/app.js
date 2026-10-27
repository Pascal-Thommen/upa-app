/**
 * Portal Institucional UPA (web-admin).
 *
 * Gestiona autenticación institucional (@upa.edu.py), navegación SPA con permisos dinámicos
 * por módulo (Publicaciones, Grupos, Roles, APIs), edición limpia de Grupos con selector
 * unificado (Google Workspace + correos), matriz interactiva de Roles en PostgreSQL y vista
 * consolidada de APIs en vivo + telemetría técnica.
 */

const STORAGE_KEY = "upa_access_token";
const CANONICAL_PERMS = ["publicaciones", "grupos", "roles", "apis"];

const DOM_ELEMENTS = {
  viewLogin: document.getElementById("view-login"),
  viewDashboard: document.getElementById("view-dashboard"),
  formLogin: document.getElementById("form-login"),
  inputToken: document.getElementById("input-token"),
  inputClassroomToken: document.getElementById("input-classroom-token"),
  loginAlert: document.getElementById("login-alert"),
  authActions: document.getElementById("auth-actions"),
  userMenuWrapper: document.getElementById("user-menu-wrapper"),
  userMenuBtn: document.getElementById("user-menu-btn"),
  userProfileDropdown: document.getElementById("user-profile-dropdown"),
  btnLogout: document.getElementById("btn-logout"),
  userFullName: document.getElementById("user-full-name"),
  userEmail: document.getElementById("user-email"),
  userAvatar: document.getElementById("user-avatar"),
  userRoleBadge: document.getElementById("user-role-badge"),
  userClassroomSyncBadge: document.getElementById("user-classroom-sync-badge"),
  tileMailgroups: document.getElementById("tile-mailgroups"),
  userGroupsContainer: document.getElementById("user-groups-container"),
  groupsCount: document.getElementById("groups-count"),
  coursesContainer: document.getElementById("courses-container"),
  coursesCount: document.getElementById("courses-count"),
  deadlinesContainer: document.getElementById("deadlines-container"),
  deadlinesCount: document.getElementById("deadlines-count"),
  feedContainer: document.getElementById("feed-container"),
  feedCountBadge: document.getElementById("feed-count-badge"),
  calendarGrid: document.getElementById("calendar-grid"),
  calMonthTitle: document.getElementById("cal-month-title"),
  calPrev: document.getElementById("cal-prev"),
  calNext: document.getElementById("cal-next"),
  selectedDateLabel: document.getElementById("selected-date-label"),
  classroomPermissionAlert: document.getElementById("classroom-permission-alert"),
  btnOpenClassroomModal: document.getElementById("btn-open-classroom-modal"),
  modalClassroom: document.getElementById("modal-classroom"),
  formClassroomToken: document.getElementById("form-classroom-token"),
  modalInputClassroomToken: document.getElementById("modal-input-classroom-token"),
  btnCloseClassroomModal: document.getElementById("btn-close-classroom-modal"),
  btnCancelClassroom: document.getElementById("btn-cancel-classroom"),
  btnRefresh: document.getElementById("btn-refresh"),
  diagBackend: document.getElementById("diag-backend"),
  diagEnv: document.getElementById("diag-env"),
};

const state = {
  currentUser: null,
  courses: [],
  deadlines: [],
  feedPosts: [],
  diagnostics: null,
  currentMonth: new Date().getMonth(),
  currentYear: new Date().getFullYear(),
  selectedDate: null,
  groupEditor: {
    editingId: "",
    isSystem: false,
    workspaceOptions: [],
    selectedWorkspaceGroups: [],
    emails: [],
  },
};

function escapeHtml(value) {
  if (typeof window !== "undefined" && window.UpaEditorial && window.UpaEditorial.escapeHtml) {
    return window.UpaEditorial.escapeHtml(value);
  }
  return String(value === null || value === undefined ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderAuditHtml(entries, options) {
  if (typeof window !== "undefined" && window.UpaEditorial && window.UpaEditorial.renderHistoryEntries) {
    return window.UpaEditorial.renderHistoryEntries(entries, options);
  }
  return "";
}

function isCurrentUserAdmin() {
  return Boolean(state.currentUser && String(state.currentUser.role || "").toLowerCase() === "admin");
}

function normalizeUserPermissions(user) {
  if (!user) return [];
  if (Array.isArray(user.permissions)) {
    const map = {
      publicaciones: "publicaciones",
      "publicaciones y eventos": "publicaciones",
      grupos: "grupos",
      "grupos y audiencias": "grupos",
      roles: "roles",
      "gestión de roles": "roles",
      "gestion de roles": "roles",
      apis: "apis",
      "diagnóstico de apis": "apis",
      "diagnostico de apis": "apis",
    };
    const out = [];
    user.permissions.forEach((raw) => {
      const key = map[String(raw || "").trim().toLowerCase()];
      if (key && !out.includes(key)) out.push(key);
    });
    return out;
  }
  const role = String(user.role || "").toLowerCase();
  if (role === "admin") return CANONICAL_PERMS.slice();
  if (role === "editor") return ["publicaciones"];
  return [];
}

function getStoredToken() {
  return localStorage.getItem(STORAGE_KEY) || localStorage.getItem("upa_auth_token");
}

function setStoredToken(token) {
  if (token) {
    localStorage.setItem(STORAGE_KEY, token);
    localStorage.setItem("upa_auth_token", token);
  } else {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem("upa_auth_token");
  }
}

function closeUserDropdown() {
  if (DOM_ELEMENTS.userProfileDropdown) {
    DOM_ELEMENTS.userProfileDropdown.classList.add("hidden");
  }
  if (DOM_ELEMENTS.userMenuBtn && DOM_ELEMENTS.userMenuBtn.setAttribute) {
    DOM_ELEMENTS.userMenuBtn.setAttribute("aria-expanded", "false");
  }
}

function logout() {
  setStoredToken(null);
  state.currentUser = null;
  closeUserDropdown();
  document.documentElement.classList.remove("has-auth");
  showLoginView();
  showLoginAlert("Sesión finalizada correctamente.", "info");
}

function showLoginAlert(message, type = "error") {
  const alertEl = DOM_ELEMENTS.loginAlert;
  if (!alertEl) return;

  alertEl.textContent = message;
  alertEl.className = "mb-4 p-3 rounded-lg text-xs font-medium border block ";

  if (type === "error") {
    alertEl.className += "bg-red-50 text-red-800 border-red-200";
  } else if (type === "info") {
    alertEl.className += "bg-blue-50 text-blue-800 border-blue-200";
  } else if (type === "success") {
    alertEl.className += "bg-emerald-50 text-emerald-800 border-emerald-200";
  }
}

function showModuleNotice(elementId, type, message) {
  const el = document.getElementById(elementId);
  if (!el) return;
  if (!message) {
    el.className = "hidden ed-notice";
    el.textContent = "";
    return;
  }
  el.textContent = message;
  el.className = `ed-notice is-${type}`;
}

function showLoginView() {
  if (window.UpaCockpit) window.UpaCockpit.reset();
  if (DOM_ELEMENTS.viewLogin) DOM_ELEMENTS.viewLogin.classList.remove("hidden");
  if (DOM_ELEMENTS.viewDashboard) DOM_ELEMENTS.viewDashboard.classList.add("hidden");
  if (DOM_ELEMENTS.authActions) DOM_ELEMENTS.authActions.classList.add("hidden");
}

function showDashboardView() {
  document.documentElement.classList.add("has-auth");
  if (DOM_ELEMENTS.viewLogin) DOM_ELEMENTS.viewLogin.classList.add("hidden");
  if (DOM_ELEMENTS.viewDashboard) DOM_ELEMENTS.viewDashboard.classList.remove("hidden");
  if (DOM_ELEMENTS.authActions) DOM_ELEMENTS.authActions.classList.remove("hidden");
}

async function apiRequest(endpoint, options = {}) {
  const token = getStoredToken();
  const headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return fetch(endpoint, {
    ...options,
    headers,
  });
}

async function checkHealth() {
  if (!DOM_ELEMENTS.diagBackend) return;
  try {
    const res = await fetch("/health");
    if (res.ok) {
      const data = await res.json();
      DOM_ELEMENTS.diagBackend.textContent = data.service || "Activo";
      if (DOM_ELEMENTS.diagEnv) DOM_ELEMENTS.diagEnv.textContent = data.environment || "Producción";
    } else {
      DOM_ELEMENTS.diagBackend.textContent = "Error";
    }
  } catch (_) {
    DOM_ELEMENTS.diagBackend.textContent = "Error";
  }
}

function setApiStatusBadge(elementId, statusKey) {
  const el = document.getElementById(elementId);
  if (!el) return;
  if (statusKey === "active") {
    el.textContent = "Activo";
    el.className = "ed-badge ed-badge-ok";
  } else if (statusKey === "error") {
    el.textContent = "Error";
    el.className = "ed-badge ed-badge-urgent";
  } else {
    el.textContent = "Sin configurar";
    el.className = "ed-badge ed-badge-neutral";
  }
}

/**
 * Carga el perfil del usuario autenticado.
 */
async function loadUserProfile() {
  try {
    const res = await apiRequest("/api/auth/me");
    if (res.status === 401) {
      logout();
      showLoginAlert("Su sesión ha expirado. Inicie sesión nuevamente.", "info");
      return null;
    }

    if (!res.ok) {
      throw new Error(`Error ${res.status} al obtener perfil`);
    }

    const user = await res.json();
    state.currentUser = user;
    renderUserProfile(user);
    showDashboardView(user);
    applyUserPermissions(user);
    return user;
  } catch (error) {
    console.error("Fallo al cargar perfil:", error);
    showLoginView();
    showLoginAlert("No fue posible validar la sesión institucional.", "error");
    return null;
  }
}

/**
 * Actualiza en caliente los permisos del usuario actual cuando se modifica su propia fila en Roles.
 */
async function refreshCurrentUserPermissions() {
  try {
    const res = await apiRequest("/api/auth/me");
    if (!res.ok) return;
    const user = await res.json();
    state.currentUser = user;
    renderUserProfile(user);
    if (window.UpaCockpit) window.UpaCockpit.onUserLoaded(user);
    applyUserPermissions(user);
  } catch (_) {
    /* conserva el estado actual si falla la red */
  }
}

/**
 * Renderiza el menú compacto de perfil en el encabezado y la tarjeta privada de grupos Workspace.
 */
function renderUserProfile(user) {
  const fullName = user.full_name || (user.email ? user.email.split("@")[0] : "Usuario");
  if (DOM_ELEMENTS.userFullName) DOM_ELEMENTS.userFullName.textContent = fullName;
  if (DOM_ELEMENTS.userEmail) DOM_ELEMENTS.userEmail.textContent = user.email || "";

  const initials = fullName
    .split(" ")
    .filter(Boolean)
    .map((n) => n[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  if (DOM_ELEMENTS.userAvatar) DOM_ELEMENTS.userAvatar.textContent = initials || "U";

  const role = String(user.role || "user").toUpperCase();
  const roleLabels = { ADMIN: "ADMIN", EDITOR: "EDITOR" };
  if (DOM_ELEMENTS.userRoleBadge) {
    DOM_ELEMENTS.userRoleBadge.textContent = roleLabels[role] || "ESTUDIANTE";
  }

  const hasClassroom = Boolean(user.has_classroom_token);
  if (DOM_ELEMENTS.userClassroomSyncBadge) {
    DOM_ELEMENTS.userClassroomSyncBadge.textContent = hasClassroom
      ? "Classroom: Activo"
      : "Classroom: Sin configurar";
    DOM_ELEMENTS.userClassroomSyncBadge.className = hasClassroom
      ? "text-[11px] text-emerald-700 font-semibold mt-1"
      : "text-[11px] text-slate-500 mt-1";
  }
  if (DOM_ELEMENTS.classroomPermissionAlert) {
    DOM_ELEMENTS.classroomPermissionAlert.classList.toggle("hidden", hasClassroom);
  }
  setApiStatusBadge("api-status-classroom", hasClassroom ? "active" : "unconfigured");

  // Regla de privacidad para el mosaico personal de grupos de Google Workspace
  const isExclusiveUser = String(user.email || "").toLowerCase() === "pascal.thommen@upa.edu.py";
  const realGoogleGroups =
    Array.isArray(user.google_groups) && user.google_groups.length > 0
      ? user.google_groups
      : Array.isArray(user.groups)
        ? user.groups.filter((g) => g !== "ALL" && g !== "TIE")
        : [];

  if (DOM_ELEMENTS.tileMailgroups) {
    if (isExclusiveUser && realGoogleGroups.length > 0) {
      DOM_ELEMENTS.tileMailgroups.classList.remove("hidden");
      if (DOM_ELEMENTS.groupsCount) DOM_ELEMENTS.groupsCount.textContent = `${realGoogleGroups.length}`;
      if (DOM_ELEMENTS.userGroupsContainer) {
        DOM_ELEMENTS.userGroupsContainer.innerHTML = realGoogleGroups
          .map((grp) => {
            const name = typeof grp === "object" && grp !== null ? grp.name || grp.email || grp.id || "" : String(grp);
            const email = typeof grp === "object" && grp !== null ? grp.email || "" : "";
            return `
              <div class="p-2.5 rounded-xl bg-slate-50 border border-slate-200/80">
                <span class="text-xs font-semibold text-slate-800 block truncate">${escapeHtml(name)}</span>
                ${email ? `<span class="text-[11px] text-slate-500 font-mono block truncate">${escapeHtml(email)}</span>` : ""}
              </div>
            `;
          })
          .join("");
      }
    } else {
      DOM_ELEMENTS.tileMailgroups.classList.add("hidden");
    }
  }
}

/**
 * Carga los cursos activos de Google Classroom.
 */
async function loadClassroomCourses() {
  const container = DOM_ELEMENTS.coursesContainer;
  if (!container) return;
  container.innerHTML = `
    <div class="flex items-center justify-center p-6 text-slate-400 gap-2">
      <div class="spinner"></div>
      <span class="text-xs">Consultando cursos...</span>
    </div>
  `;

  try {
    const res = await apiRequest("/api/classroom/courses");
    if (res.status === 401) {
      logout();
      return;
    }

    if (!res.ok) {
      container.innerHTML = `
        <div class="p-4 rounded-lg bg-slate-50 text-slate-600 text-xs">
          Classroom sin configurar o sin acceso activo (HTTP ${res.status}).
        </div>
      `;
      if (DOM_ELEMENTS.coursesCount) DOM_ELEMENTS.coursesCount.textContent = "0";
      if (res.status >= 500) setApiStatusBadge("api-status-classroom", "error");
      return;
    }

    const courses = await res.json();
    state.courses = Array.isArray(courses) ? courses : [];
    if (DOM_ELEMENTS.coursesCount) DOM_ELEMENTS.coursesCount.textContent = `${state.courses.length}`;
    if (state.currentUser && state.currentUser.has_classroom_token) {
      setApiStatusBadge("api-status-classroom", "active");
    }

    if (state.courses.length === 0) {
      container.innerHTML = `
        <div class="p-6 text-center text-slate-400 text-xs border border-dashed border-slate-200 rounded-lg">
          Sin cursos activos en este periodo.
        </div>
      `;
      return;
    }

    container.innerHTML = state.courses
      .map((c) => {
        const link = c.alternate_link || `https://classroom.google.com/c/${encodeURIComponent(c.id)}`;
        return `
          <div class="course-card flex flex-col justify-between gap-1.5">
            <div>
              <h4 class="font-bold text-xs text-slate-900">${escapeHtml(c.name)}</h4>
              <p class="text-[11px] text-slate-500">${escapeHtml(c.section || "Sin sección")}${
                c.room ? ` &bull; Aula: ${escapeHtml(c.room)}` : ""
              }</p>
            </div>
            <div class="flex items-center justify-between pt-1.5 border-t border-slate-200/70 text-[11px]">
              <span class="text-[10px] text-slate-400 font-mono">ID: ${escapeHtml(c.id)}</span>
              <a href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer" class="btn-classroom-link">
                <span>Abrir curso</span>
                <span>&nearr;</span>
              </a>
            </div>
          </div>
        `;
      })
      .join("");
  } catch (error) {
    console.error("Fallo al obtener cursos:", error);
    container.innerHTML = `
      <div class="p-4 rounded-lg bg-red-50 text-red-700 text-xs">
        Error de red al consultar Google Classroom.
      </div>
    `;
    if (DOM_ELEMENTS.coursesCount) DOM_ELEMENTS.coursesCount.textContent = "Error";
    setApiStatusBadge("api-status-classroom", "error");
  }
}

/**
 * Carga las tareas y entregas de Google Classroom.
 */
async function loadClassroomDeadlines() {
  try {
    const res = await apiRequest("/api/classroom/deadlines");
    if (res.status === 401) {
      logout();
      return;
    }

    if (!res.ok) {
      if (DOM_ELEMENTS.deadlinesCount) DOM_ELEMENTS.deadlinesCount.textContent = "0";
      renderDeadlinesList([]);
      return;
    }

    const data = await res.json();
    state.deadlines = Array.isArray(data) ? data : data.deadlines || [];
    if (DOM_ELEMENTS.deadlinesCount) {
      DOM_ELEMENTS.deadlinesCount.textContent = `${state.deadlines.length}`;
    }

    renderCalendar();
    renderDeadlinesList(state.deadlines);
  } catch (error) {
    console.error("Fallo al obtener plazos:", error);
    if (DOM_ELEMENTS.deadlinesCount) DOM_ELEMENTS.deadlinesCount.textContent = "Error";
  }
}

function renderCalendar() {
  const grid = DOM_ELEMENTS.calendarGrid;
  if (!grid || !DOM_ELEMENTS.calMonthTitle) return;

  const monthNames = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
  ];

  DOM_ELEMENTS.calMonthTitle.textContent = `${monthNames[state.currentMonth]} ${state.currentYear}`;

  const dayHeaders = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"];
  let html = dayHeaders.map((dh) => `<div class="cal-day-header">${dh}</div>`).join("");

  const firstDayIndex = (new Date(state.currentYear, state.currentMonth, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(state.currentYear, state.currentMonth + 1, 0).getDate();

  for (let i = 0; i < firstDayIndex; i++) {
    html += `<div class="cal-day is-empty"></div>`;
  }

  const deadlineDaysMap = {};
  state.deadlines.forEach((d) => {
    const formatted = d.due_date_formatted || "";
    const dateKey = formatted.split(" ")[0];
    if (dateKey) {
      deadlineDaysMap[dateKey] = (deadlineDaysMap[dateKey] || 0) + 1;
    }
  });

  for (let day = 1; day <= daysInMonth; day++) {
    const mm = String(state.currentMonth + 1).padStart(2, "0");
    const dd = String(day).padStart(2, "0");
    const dateKey = `${state.currentYear}-${mm}-${dd}`;
    const hasDeadline = Boolean(deadlineDaysMap[dateKey]);
    const isSelected = state.selectedDate === dateKey;

    const classes = ["cal-day", hasDeadline ? "has-deadline" : "", isSelected ? "is-selected" : ""]
      .filter(Boolean)
      .join(" ");

    html += `<div class="${classes}" data-date="${dateKey}">${day}</div>`;
  }

  grid.innerHTML = html;
}

function formatDeadlineBadge(item) {
  let dateObj = null;
  if (item.due_date && item.due_date.year && item.due_date.month && item.due_date.day) {
    dateObj = new Date(item.due_date.year, item.due_date.month - 1, item.due_date.day);
  } else if (item.due_date_formatted) {
    const parts = item.due_date_formatted.split(" ")[0].split("-");
    if (parts.length === 3) {
      dateObj = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    }
  }
  const dayNames = ["DOM", "LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB"];
  if (dateObj && !Number.isNaN(dateObj.getTime())) {
    const dayOfWeek = dayNames[dateObj.getDay()];
    const dayNum = String(dateObj.getDate()).padStart(2, "0");
    return { dayOfWeek, dayNum };
  }
  return { dayOfWeek: "PLAZO", dayNum: "--" };
}

/**
 * Renderiza la lista limpia de entregas (sin insignias de puntaje "pts").
 */
function renderDeadlinesList(items) {
  const container = DOM_ELEMENTS.deadlinesContainer;
  if (!container) return;

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="p-6 text-center text-slate-400 text-xs border border-dashed border-slate-200 rounded-xl">
        No hay entregas pendientes en este periodo.
      </div>
    `;
    return;
  }

  container.innerHTML = items
    .map((d) => {
      const link = d.alternate_link || "https://classroom.google.com";
      const badge = formatDeadlineBadge(d);
      const timeStr = d.due_time
        ? `${String(d.due_time.hours || 0).padStart(2, "0")}:${String(d.due_time.minutes || 0).padStart(2, "0")} hs`
        : d.due_date_formatted
          ? d.due_date_formatted.split(" ")[1] || ""
          : "";

      return `
        <div class="flex items-start gap-3 p-3 rounded-xl bg-slate-50 border border-slate-200/80 hover:bg-slate-100/60 transition">
          <div class="flex flex-col items-center justify-center w-11 h-11 rounded-xl bg-white border border-slate-200 text-center flex-shrink-0">
            <span class="text-[10px] font-extrabold text-[#6c9339] leading-tight uppercase">${escapeHtml(
              badge.dayOfWeek
            )}</span>
            <span class="text-sm font-extrabold text-slate-900 leading-tight">${escapeHtml(badge.dayNum)}</span>
          </div>
          <div class="flex-1 min-w-0 space-y-1">
            <span class="text-[10px] font-bold text-slate-500 uppercase tracking-wide block truncate">${escapeHtml(
              d.course || "Classroom"
            )}</span>
            <h4 class="font-bold text-xs text-slate-900 truncate" title="${escapeHtml(d.title)}">${escapeHtml(
              d.title
            )}</h4>
            <div class="flex items-center justify-between pt-0.5 text-[11px] text-slate-400">
              <span class="font-mono text-[10px] text-slate-500">${escapeHtml(timeStr)}</span>
              <a href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer" class="text-[11px] font-semibold text-blue-700 hover:text-blue-900">
                Ver tarea &nearr;
              </a>
            </div>
          </div>
        </div>
      `;
    })
    .join("");
}

/**
 * Carga las publicaciones del feed institucional e Instagram de manera tolerante a nulos.
 */
async function loadCampusFeed() {
  const container = DOM_ELEMENTS.feedContainer;
  const badge = DOM_ELEMENTS.feedCountBadge;
  if (!container) return;

  container.innerHTML = `
    <div class="col-span-full flex items-center justify-center p-8 text-slate-400 gap-2">
      <div class="spinner"></div>
      <span class="text-xs">Cargando publicaciones del feed...</span>
    </div>
  `;

  try {
    const res = await apiRequest("/api/v1/feed");
    if (!res.ok) {
      container.innerHTML = `
        <div class="col-span-full p-4 rounded-lg bg-red-50 text-red-700 text-xs">
          Error al consultar el feed institucional (HTTP ${res.status}).
        </div>
      `;
      if (badge) {
        badge.textContent = "Error";
        badge.className = "ed-badge ed-badge-urgent";
      }
      setApiStatusBadge("api-status-instagram", "error");
      return;
    }

    const data = await res.json();
    const posts = Array.isArray(data && data.posts) ? data.posts : [];
    state.feedPosts = posts;
    if (badge) {
      badge.textContent = posts.length > 0 ? `Activo · ${posts.length}` : "0 publicaciones";
      badge.className = posts.length > 0 ? "ed-badge ed-badge-ok" : "ed-badge ed-badge-neutral";
    }

    if (posts.length === 0) {
      container.innerHTML = `
        <div class="col-span-full p-8 text-center text-slate-400 text-xs border border-dashed border-slate-200 rounded-lg">
          No hay publicaciones registradas en el feed.
        </div>
      `;
      return;
    }

    container.innerHTML = posts
      .slice(0, 8)
      .map((post) => {
        const title = post.title || post.summary || "Publicación UPA";
        const dateStr = post.published_at ? new Date(post.published_at).toLocaleDateString("es-PY") : "";
        const linkUrl = post.link_url || post.permalink || "";
        const linkLabel = post.link_label || (post.post_type === "INSTAGRAM" ? "Ver en Instagram" : "Abrir enlace");
        const isIg = post.post_type === "INSTAGRAM";

        const imageHtml = post.image_url
          ? `<img src="${escapeHtml(post.image_url)}" alt="" class="feed-card-img" loading="lazy">`
          : `<div class="feed-card-placeholder">UPA Campus</div>`;

        return `
          <article class="feed-card">
            ${imageHtml}
            <div class="p-3 flex-1 flex flex-col justify-between space-y-2">
              <div>
                <div class="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                  <span class="ed-badge ${isIg ? "ed-badge-social" : "ed-badge-neutral"}">${
                    isIg ? "Instagram" : "Campus"
                  }</span>
                  <span>${escapeHtml(dateStr)}</span>
                </div>
                <h4 class="font-bold text-xs text-slate-900 line-clamp-2" title="${escapeHtml(title)}">${escapeHtml(
                  title
                )}</h4>
              </div>
              <div class="pt-2 border-t border-slate-100 flex items-center justify-between text-xs">
                <span class="text-[10px] text-slate-400">${isIg ? "@upalemana" : "UPA"}</span>
                ${
                  linkUrl
                    ? `<a href="${escapeHtml(
                        linkUrl
                      )}" target="_blank" rel="noopener noreferrer" class="btn-classroom-link">${escapeHtml(
                        linkLabel
                      )} &nearr;</a>`
                    : ""
                }
              </div>
            </div>
          </article>
        `;
      })
      .join("");
  } catch (error) {
    console.error("Fallo al obtener feed:", error);
    container.innerHTML = `
      <div class="col-span-full p-4 rounded-lg bg-red-50 text-red-700 text-xs">
        Error de red al consultar el feed del campus.
      </div>
    `;
    if (badge) {
      badge.textContent = "Error";
      badge.className = "ed-badge ed-badge-urgent";
    }
    setApiStatusBadge("api-status-instagram", "error");
  }
}

function getAppJsonData() {
  return {
    portal: "UPA Mobile Campus Platform",
    api_version: "1.0.0",
    generated_at: new Date().toISOString(),
    user: state.currentUser,
    deadlines: state.deadlines,
    courses: state.courses,
    campus_feed: state.feedPosts,
  };
}

/**
 * Actualiza los indicadores consistentes (Activo / Sin configurar / Error) y el contrato JSON.
 */
async function updateJsonView() {
  const rawJsonOutput = document.getElementById("raw-json-output");
  if (rawJsonOutput) {
    rawJsonOutput.textContent = "Consultando telemetría del sistema en tiempo real...";
  }
  try {
    const res = await apiRequest("/api/system/diagnostics");
    if (res.ok) {
      const diag = await res.json();
      state.diagnostics = diag;

      setApiStatusBadge("api-status-oauth", "active");
      setApiStatusBadge(
        "api-status-directory",
        diag.directory_sync && (diag.directory_sync.service_account_configured || diag.directory_sync.enabled)
          ? "active"
          : "unconfigured"
      );

      const classroomActive = Boolean(
        (state.currentUser && state.currentUser.has_classroom_token) ||
          (diag.classroom_api && diag.classroom_api.user_token_present)
      );
      setApiStatusBadge("api-status-classroom", classroomActive ? "active" : "unconfigured");

      const igConfigured = Boolean(
        (diag.application && diag.application.instagram_configured) ||
          (diag.instagram_api && diag.instagram_api.configured)
      );
      const igHasPosts = Array.isArray(state.feedPosts) && state.feedPosts.some((p) => p.post_type === "INSTAGRAM");
      setApiStatusBadge("api-status-instagram", igConfigured || igHasPosts ? "active" : "unconfigured");

      if (rawJsonOutput) {
        rawJsonOutput.textContent = JSON.stringify(
          {
            diagnostico_sistema: diag,
            contrato_app_movil: getAppJsonData(),
          },
          null,
          2
        );
      }
      return;
    }
    setApiStatusBadge("api-status-directory", "error");
  } catch (err) {
    console.error("Error consultando diagnósticos:", err);
    setApiStatusBadge("api-status-directory", "error");
  }
  if (rawJsonOutput) {
    rawJsonOutput.textContent = JSON.stringify(getAppJsonData(), null, 2);
  }
}

async function refreshDashboard() {
  await checkHealth();
  const user = await loadUserProfile();
  if (user) {
    if (window.UpaCockpit) window.UpaCockpit.onUserLoaded(user);
    if (window.UpaRouter && typeof window.UpaRouter.reapplyCurrentRoute === "function") {
      window.UpaRouter.reapplyCurrentRoute();
    }
    await Promise.all([loadClassroomCourses(), loadClassroomDeadlines(), loadCampusFeed()]);
    await updateJsonView();
  }
}

window.handleGoogleCredentialResponse = async function (response) {
  if (!response || !response.credential) {
    showLoginAlert("No se recibió credencial de Google OAuth.", "error");
    return;
  }
  showLoginAlert("Autenticando con Google OAuth (@upa.edu.py)...", "info");
  try {
    const res = await fetch("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: response.credential }),
    });
    if (res.ok) {
      const authData = await res.json();
      setStoredToken(authData.access_token);
      showLoginAlert("Inicio de sesión exitoso.", "success");
      await refreshDashboard();
      return;
    }
    if (res.status === 403) {
      const err = await res.json().catch(() => ({}));
      showLoginAlert(err.detail || "Acceso restringido a cuentas @upa.edu.py.", "error");
      return;
    }
    const errText = await res.text();
    showLoginAlert(`Error al autenticar: ${errText}`, "error");
  } catch (error) {
    console.error("Fallo al procesar login de Google:", error);
    showLoginAlert("Error de conexión durante el inicio de sesión.", "error");
  }
};

async function handleLoginSubmit(event) {
  event.preventDefault();
  const token = DOM_ELEMENTS.inputToken ? DOM_ELEMENTS.inputToken.value.trim() : "";
  const classroomToken = DOM_ELEMENTS.inputClassroomToken ? DOM_ELEMENTS.inputClassroomToken.value.trim() : "";

  if (!token) {
    showLoginAlert("Ingrese un correo institucional o JWT de sesión.", "error");
    return;
  }

  showLoginAlert("Validando acceso...", "info");

  try {
    if (token.includes("@")) {
      const devLoginResp = await fetch("/api/auth/dev-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: token,
          classroom_token: classroomToken || null,
        }),
      });
      if (devLoginResp.ok) {
        const authData = await devLoginResp.json();
        setStoredToken(authData.access_token);
        showLoginAlert("Inicio de sesión exitoso.", "success");
        await refreshDashboard();
        return;
      }
      const err = await devLoginResp.json().catch(() => ({}));
      showLoginAlert(err.detail || "Correo institucional no autorizado.", "error");
      return;
    }

    const googleLoginResp = await fetch("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_token: token,
        classroom_token: classroomToken || null,
      }),
    });

    if (googleLoginResp.ok) {
      const authData = await googleLoginResp.json();
      setStoredToken(authData.access_token);
      showLoginAlert("Inicio de sesión exitoso.", "success");
      await refreshDashboard();
      return;
    }

    if (googleLoginResp.status === 403) {
      const err = await googleLoginResp.json().catch(() => ({}));
      showLoginAlert(err.detail || "Acceso restringido a correos @upa.edu.py.", "error");
      return;
    }

    setStoredToken(token);
    const testMeResp = await apiRequest("/api/auth/me");
    if (testMeResp.ok) {
      if (classroomToken) {
        await apiRequest("/api/auth/classroom-token", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ classroom_token: classroomToken }),
        });
      }
      showLoginAlert("Sesión validada correctamente.", "success");
      await refreshDashboard();
      return;
    }

    setStoredToken(null);
    showLoginAlert("Token inválido o expirado.", "error");
  } catch (error) {
    console.error("Error durante el inicio de sesión:", error);
    setStoredToken(null);
    showLoginAlert("Error de conexión con el servidor.", "error");
  }
}

async function handleClassroomTokenSubmit(event) {
  event.preventDefault();
  const token = DOM_ELEMENTS.modalInputClassroomToken ? DOM_ELEMENTS.modalInputClassroomToken.value.trim() : "";
  if (!token) return;

  try {
    const res = await apiRequest("/api/auth/classroom-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ classroom_token: token }),
    });

    if (res.ok) {
      if (DOM_ELEMENTS.modalClassroom) DOM_ELEMENTS.modalClassroom.classList.add("hidden");
      if (DOM_ELEMENTS.modalInputClassroomToken) DOM_ELEMENTS.modalInputClassroomToken.value = "";
      await refreshDashboard();
    } else {
      alert("No se pudo guardar el token de Google Classroom.");
    }
  } catch (error) {
    console.error("Error al actualizar token de Classroom:", error);
    alert("Error de red al actualizar el token de Classroom.");
  }
}

// ===========================================================================
// Módulo 2: Grupos (lista limpia + editor unificado + historial admin)
// ===========================================================================

let appGroupsCache = [];

async function fetchAppGroups() {
  try {
    const res = await apiRequest("/api/groups");
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data)) {
        appGroupsCache = data
          .slice()
          .sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "es", { sensitivity: "base" }));
        if (window.UpaCockpit && typeof window.UpaCockpit.refreshGroupsCatalog === "function") {
          window.UpaCockpit.refreshGroupsCatalog(appGroupsCache);
        }
        return appGroupsCache;
      }
    }
  } catch (err) {
    console.error("Error cargando grupos:", err);
  }
  return appGroupsCache;
}

async function fetchWorkspaceDirectoryGroups() {
  try {
    const res = await apiRequest("/api/groups/google-workspace");
    if (res.ok) {
      const data = await res.json();
      if (data && Array.isArray(data.groups)) {
        state.groupEditor.workspaceOptions = data.groups
          .slice()
          .sort((a, b) =>
            String(a.name || a.email || "").localeCompare(String(b.name || b.email || ""), "es", {
              sensitivity: "base",
            })
          );
        return state.groupEditor.workspaceOptions;
      }
    }
  } catch (_) {
    /* mantiene opciones conocidas */
  }
  return state.groupEditor.workspaceOptions || [];
}

async function loadAuditTrailInto(elementId, entityType, key) {
  const el = document.getElementById(elementId);
  if (!el) return;
  if (!isCurrentUserAdmin()) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  const url =
    key !== undefined && key !== null && key !== ""
      ? `/api/history/${encodeURIComponent(entityType)}/${encodeURIComponent(key)}`
      : `/api/history/${encodeURIComponent(entityType)}`;
  try {
    const res = await apiRequest(url);
    if (!res.ok) {
      el.classList.add("hidden");
      el.innerHTML = "";
      return;
    }
    const entries = await res.json();
    const html = renderAuditHtml(entries, { showTarget: !key });
    el.innerHTML = html;
    el.classList.toggle("hidden", !html);
  } catch (_) {
    el.classList.add("hidden");
    el.innerHTML = "";
  }
}

function showGroupsListPanel() {
  const listPanel = document.getElementById("groups-list-panel");
  const editorPanel = document.getElementById("group-editor-panel");
  if (listPanel) listPanel.classList.remove("hidden");
  if (editorPanel) editorPanel.classList.add("hidden");
  showModuleNotice("groups-notice", "", "");
}

function renderWorkspacePicker() {
  const container = document.getElementById("group-workspace-picker");
  if (!container) return;
  const selected = state.groupEditor.selectedWorkspaceGroups;
  const catalog = state.groupEditor.workspaceOptions.slice();
  const knownValues = new Set(catalog.map((g) => g.email || g.name));
  selected.forEach((val) => {
    if (val && !knownValues.has(val)) {
      knownValues.add(val);
      catalog.push({ id: val, name: val, email: val });
    }
  });

  catalog.sort((a, b) =>
    String(a.name || a.email || "").localeCompare(String(b.name || b.email || ""), "es", { sensitivity: "base" })
  );

  if (catalog.length === 0) {
    container.innerHTML = `<span class="ed-subtle">No hay grupos detectados aún; agregue uno abajo si corresponde.</span>`;
    return;
  }

  const filterInput = document.getElementById("group-workspace-filter");
  const filterText = (filterInput && filterInput.value ? filterInput.value : "").trim().toLowerCase();
  const visibleCatalog = filterText
    ? catalog.filter((g) => {
        const name = String(g.name || "").toLowerCase();
        const email = String(g.email || "").toLowerCase();
        return name.includes(filterText) || email.includes(filterText);
      })
    : catalog;

  if (visibleCatalog.length === 0) {
    container.innerHTML = `<span class="ed-subtle">Ningún grupo de Google Workspace coincide con el filtro.</span>`;
    return;
  }

  container.innerHTML = visibleCatalog
    .map((g) => {
      const value = g.email || g.name;
      const label = g.email && g.name && g.name !== g.email ? `${g.name} (${g.email})` : value;
      const checked = selected.includes(value);
      return `<label class="ed-check bg-white px-2.5 py-1 rounded-lg border border-slate-200">
        <input type="checkbox" data-ws-group="${escapeHtml(value)}"${checked ? " checked" : ""}>
        <span>${escapeHtml(label)}</span>
      </label>`;
    })
    .join("");

  container.querySelectorAll("input[data-ws-group]").forEach((cb) => {
    cb.addEventListener("change", () => {
      const val = cb.getAttribute("data-ws-group");
      if (cb.checked) {
        if (!state.groupEditor.selectedWorkspaceGroups.includes(val)) {
          state.groupEditor.selectedWorkspaceGroups.push(val);
        }
      } else {
        state.groupEditor.selectedWorkspaceGroups = state.groupEditor.selectedWorkspaceGroups.filter((x) => x !== val);
      }
    });
  });
}

function renderGroupEmailsChips() {
  const container = document.getElementById("group-emails-chips");
  if (!container) return;
  const emails = state.groupEditor.emails;
  if (emails.length === 0) {
    container.innerHTML = `<span class="ed-subtle">Sin cuentas individuales agregadas.</span>`;
    return;
  }
  container.innerHTML = emails
    .map(
      (email, idx) => `
      <span class="chip-tag">
        <span class="font-mono">${escapeHtml(email)}</span>
        <button type="button" data-remove-email="${idx}" aria-label="Quitar ${escapeHtml(email)}">&times;</button>
      </span>`
    )
    .join("");

  container.querySelectorAll("button[data-remove-email]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.getAttribute("data-remove-email"));
      state.groupEditor.emails.splice(idx, 1);
      renderGroupEmailsChips();
    });
  });
}

async function openGroupEditor(group) {
  showModuleNotice("groups-notice", "", "");
  await fetchWorkspaceDirectoryGroups();

  const editing = Boolean(group && group.id);
  state.groupEditor.editingId = editing ? group.id : "";
  state.groupEditor.isSystem = Boolean(group && group.is_system);

  const wsList =
    group && Array.isArray(group.google_groups) && group.google_groups.length > 0
      ? group.google_groups.slice()
      : group && group.google_group
        ? [group.google_group]
        : [];
  state.groupEditor.selectedWorkspaceGroups = wsList;
  state.groupEditor.emails = group && Array.isArray(group.emails) ? group.emails.slice() : [];

  const idInput = document.getElementById("group-edit-id");
  const nameInput = document.getElementById("group-input-name");
  const descInput = document.getElementById("group-input-description");
  const titleEl = document.getElementById("group-editor-title");
  const deleteBtn = document.getElementById("btn-group-delete");

  if (idInput) idInput.value = editing ? group.id : "";
  if (nameInput) nameInput.value = editing ? group.name || "" : "";
  if (descInput) descInput.value = editing ? group.description || "" : "";
  if (titleEl) titleEl.textContent = editing ? "Editar grupo" : "Nuevo grupo";
  if (deleteBtn) deleteBtn.classList.toggle("hidden", !editing || state.groupEditor.isSystem);

  renderWorkspacePicker();
  renderGroupEmailsChips();

  const listPanel = document.getElementById("groups-list-panel");
  const editorPanel = document.getElementById("group-editor-panel");
  if (listPanel) listPanel.classList.add("hidden");
  if (editorPanel) editorPanel.classList.remove("hidden");

  if (editing) {
    loadAuditTrailInto("group-item-history", "group", group.id);
  } else {
    const hist = document.getElementById("group-item-history");
    if (hist) {
      hist.classList.add("hidden");
      hist.innerHTML = "";
    }
  }
}

function summarizeGroupMembers(group) {
  const ws =
    Array.isArray(group.google_groups) && group.google_groups.length > 0
      ? group.google_groups
      : group.google_group
        ? [group.google_group]
        : [];
  const emails = Array.isArray(group.emails) ? group.emails : [];
  const parts = [];
  if (ws.length > 0) parts.push(`${ws.length} ${ws.length === 1 ? "grupo Workspace" : "grupos Workspace"}`);
  if (emails.length > 0) parts.push(`${emails.length} ${emails.length === 1 ? "cuenta" : "cuentas"}`);
  return parts.length > 0 ? parts.join(" · ") : "Sin miembros vinculados";
}

function renderGroupsListItems(groups) {
  const container = document.getElementById("groups-list-container");
  if (!container) return;

  const list = Array.isArray(groups)
    ? groups
        .slice()
        .sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "es", { sensitivity: "base" }))
    : [];

  if (list.length === 0) {
    container.innerHTML = `<div class="p-6 text-center text-xs text-slate-400">No hay grupos registrados.</div>`;
    return;
  }

  const filterInput = document.getElementById("groups-filter-input");
  const filterText = (filterInput && filterInput.value ? filterInput.value : "").trim().toLowerCase();
  const visible = filterText
    ? list.filter((g) => {
        const name = String(g.name || "").toLowerCase();
        const desc = String(g.description || "").toLowerCase();
        const ws = Array.isArray(g.google_groups) ? g.google_groups.join(" ").toLowerCase() : "";
        return name.includes(filterText) || desc.includes(filterText) || ws.includes(filterText);
      })
    : list;

  if (visible.length === 0) {
    container.innerHTML = `<div class="p-6 text-center text-xs text-slate-400">Ningún grupo coincide con el filtro.</div>`;
    return;
  }

  container.innerHTML = visible
    .map(
      (g) => `
      <div class="group-row" data-group-id="${escapeHtml(g.id)}" tabindex="0">
        <div class="min-w-0">
          <div class="font-bold text-sm text-slate-900 truncate">${escapeHtml(g.name)}</div>
        </div>
        <div class="flex items-center gap-3 text-xs text-slate-500 flex-shrink-0">
          <span>${escapeHtml(summarizeGroupMembers(g))}</span>
          <span class="text-slate-400">&rarr;</span>
        </div>
      </div>`
    )
    .join("");

  container.querySelectorAll("[data-group-id]").forEach((row) => {
    const open = () => {
      const id = row.getAttribute("data-group-id");
      const found = appGroupsCache.find((item) => item.id === id);
      if (found) openGroupEditor(found);
    };
    row.addEventListener("click", open);
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        open();
      }
    });
  });
}

async function renderGroupsModule() {
  showGroupsListPanel();
  const container = document.getElementById("groups-list-container");
  if (!container) return;
  container.innerHTML = `<div class="p-6 text-center text-xs text-slate-400">Cargando grupos...</div>`;
  const groups = await fetchAppGroups();
  renderGroupsListItems(groups);
  loadAuditTrailInto("groups-list-history", "group");
}

// ===========================================================================
// Módulo 3: Roles (matriz interactiva de permisos + historial admin)
// ===========================================================================

let appAdminsCache = [];

async function fetchAppAdmins() {
  try {
    const res = await apiRequest("/api/roles");
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data)) {
        appAdminsCache = data;
        return appAdminsCache;
      }
    }
  } catch (err) {
    console.error("Error cargando roles:", err);
  }
  return appAdminsCache;
}

async function renderAdminsModule() {
  const tbody = document.getElementById("admin-table-rows");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-xs text-slate-400">Cargando permisos...</td></tr>`;
  const admins = await fetchAppAdmins();

  if (!Array.isArray(admins) || admins.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-xs text-slate-400">No hay cuentas autorizadas.</td></tr>`;
    return;
  }

  tbody.innerHTML = admins
    .map((adm) => {
      const perms = normalizeUserPermissions(adm);
      const cells = CANONICAL_PERMS.map(
        (key) => `
          <td class="py-3 px-3 text-center">
            <input type="checkbox"
                   data-role-email="${escapeHtml(adm.email)}"
                   data-perm-key="${escapeHtml(key)}"
                   ${perms.includes(key) ? "checked" : ""}
                   aria-label="${escapeHtml(key)} para ${escapeHtml(adm.email)}"
                   class="w-4 h-4 rounded text-[#6c9339] focus:ring-[#6c9339] cursor-pointer">
          </td>`
      ).join("");

      return `
        <tr class="hover:bg-slate-50/70" data-admin-row="${escapeHtml(adm.email)}">
          <td class="py-3 px-3">
            <div class="font-bold text-slate-900">${escapeHtml(adm.name || adm.email.split("@")[0])}</div>
            <div class="font-mono text-[11px] text-slate-500">${escapeHtml(adm.email)}</div>
          </td>
          ${cells}
          <td class="py-3 px-3 text-right">
            <button type="button" data-remove-admin="${escapeHtml(adm.email)}" class="text-xs text-red-600 hover:text-red-800 font-semibold">
              Quitar
            </button>
          </td>
        </tr>
      `;
    })
    .join("");

  tbody.querySelectorAll("input[data-role-email]").forEach((cb) => {
    cb.addEventListener("change", async () => {
      const email = cb.getAttribute("data-role-email");
      const row = tbody.querySelector(`tr[data-admin-row="${CSS && CSS.escape ? CSS.escape(email) : email}"]`) || cb.closest("tr");
      const updatedPerms = row
        ? Array.from(row.querySelectorAll("input[data-perm-key]:checked")).map((el) => el.getAttribute("data-perm-key"))
        : [];

      try {
        const res = await apiRequest(`/api/roles/${encodeURIComponent(email)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ permissions: updatedPerms }),
        });
        if (!res.ok) {
          cb.checked = !cb.checked;
          const err = await res.json().catch(() => ({}));
          showModuleNotice("roles-notice", "error", err.detail || "No se pudo actualizar el permiso.");
          return;
        }
        const saved = await res.json();
        const idx = appAdminsCache.findIndex((item) => item.email === email);
        if (idx >= 0) appAdminsCache[idx] = saved;
        showModuleNotice("roles-notice", "success", `Permisos actualizados para ${email}.`);

        if (state.currentUser && String(state.currentUser.email || "").toLowerCase() === email.toLowerCase()) {
          await refreshCurrentUserPermissions();
        }
        loadAuditTrailInto("roles-history", "role");
      } catch (_) {
        cb.checked = !cb.checked;
        showModuleNotice("roles-notice", "error", "Error de red al guardar los permisos.");
      }
    });
  });

  tbody.querySelectorAll("button[data-remove-admin]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const email = btn.getAttribute("data-remove-admin");
      if (!confirm(`¿Quitar todos los permisos administrativos de ${email}?`)) return;
      try {
        const res = await apiRequest(`/api/roles/${encodeURIComponent(email)}`, { method: "DELETE" });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          showModuleNotice("roles-notice", "error", err.detail || "No se pudo quitar la cuenta.");
          return;
        }
        showModuleNotice("roles-notice", "success", `Acceso revocado para ${email}.`);
        await renderAdminsModule();
        if (state.currentUser && String(state.currentUser.email || "").toLowerCase() === email.toLowerCase()) {
          await refreshCurrentUserPermissions();
        }
      } catch (_) {
        showModuleNotice("roles-notice", "error", "Error de conexión al revocar el acceso.");
      }
    });
  });

  loadAuditTrailInto("roles-history", "role");
}

// ===========================================================================
// Enrutamiento SPA de los 4 módulos y control dinámico de permisos en sidebar
// ===========================================================================

const ROUTE_CONFIG = {
  publicaciones: {
    path: "/dashboard/publicaciones",
    btnId: "nav-mod-publications",
    viewId: "view-editorial",
    perm: "publicaciones",
  },
  grupos: {
    path: "/dashboard/grupos",
    btnId: "nav-mod-groups",
    viewId: "view-groups",
    perm: "grupos",
  },
  roles: {
    path: "/dashboard/roles",
    btnId: "nav-mod-admins",
    viewId: "view-admins",
    perm: "roles",
  },
  apis: {
    path: "/dashboard/apis",
    btnId: "nav-mod-students",
    viewId: "student-workspace",
    perm: "apis",
  },
};

let currentActiveRoute = "publicaciones";
let allowedModulePerms = null; // null antes de autenticar; array tras cargar usuario

function resolveRoute(rawPath) {
  if (!rawPath) {
    return { name: "publicaciones", path: "/dashboard/publicaciones", isRedirect: true };
  }
  let path = String(rawPath).split("?")[0].split("#")[0].replace(/\/+$/, "");
  if (!path) path = "/dashboard";
  const lower = path.toLowerCase();

  if (lower === "/dashboard/publicaciones" || lower === "/dashboard/noticias" || lower === "/dashboard/eventos") {
    return {
      name: "publicaciones",
      path: "/dashboard/publicaciones",
      isRedirect: lower !== "/dashboard/publicaciones",
    };
  }
  if (lower === "/dashboard/grupos" || lower === "/dashboard/groups") {
    return { name: "grupos", path: "/dashboard/grupos", isRedirect: lower !== "/dashboard/grupos" };
  }
  if (lower === "/dashboard/roles" || lower === "/dashboard/admins") {
    return { name: "roles", path: "/dashboard/roles", isRedirect: lower !== "/dashboard/roles" };
  }
  if (
    lower === "/dashboard/apis" ||
    lower === "/dashboard/estudiantes" ||
    lower === "/dashboard/students" ||
    lower === "/dashboard/diagnostico" ||
    lower === "/dashboard/diagnostic" ||
    lower === "/dashboard/control"
  ) {
    return { name: "apis", path: "/dashboard/apis", isRedirect: lower !== "/dashboard/apis" };
  }

  return { name: "publicaciones", path: "/dashboard/publicaciones", isRedirect: true };
}

function syncNavClasses(routeName) {
  const config = ROUTE_CONFIG[routeName] || ROUTE_CONFIG.publicaciones;
  Object.values(ROUTE_CONFIG).forEach((c) => {
    const btn = document.getElementById(c.btnId);
    if (!btn) return;
    const isHidden = btn.classList.contains("hidden") && Array.isArray(allowedModulePerms);
    btn.className =
      "sidebar-nav-btn w-full flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl font-semibold text-xs transition text-left text-slate-600 hover:text-slate-900 hover:bg-slate-100" +
      (isHidden ? " hidden" : "");
  });

  const activeBtn = document.getElementById(config.btnId);
  if (activeBtn) {
    const isHidden = activeBtn.classList.contains("hidden") && Array.isArray(allowedModulePerms);
    activeBtn.className =
      "sidebar-nav-btn is-active w-full flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl font-semibold text-xs transition text-left text-white bg-[#6c9339] shadow-2xs" +
      (isHidden ? " hidden" : "");
  }
}

function applyUserPermissions(user) {
  const perms = normalizeUserPermissions(user);
  allowedModulePerms = perms;

  const sidebar = document.getElementById("sidebar-menu");
  if (sidebar) {
    sidebar.classList.toggle("hidden", perms.length === 0);
  }

  Object.values(ROUTE_CONFIG).forEach((cfg) => {
    const btn = document.getElementById(cfg.btnId);
    if (btn) {
      btn.classList.toggle("hidden", !perms.includes(cfg.perm));
    }
  });

  const apisOverview = document.getElementById("apis-admin-overview");
  const apisJsonDetails = document.getElementById("apis-json-details");
  const hasApisPerm = perms.includes("apis");
  if (apisOverview) apisOverview.classList.toggle("hidden", !hasApisPerm);
  if (apisJsonDetails) apisJsonDetails.classList.toggle("hidden", !hasApisPerm);

  if (perms.length === 0) {
    if (currentActiveRoute !== "apis") {
      applyRoute("apis", { updateUrl: true, replace: true });
    }
    return;
  }

  const currentCfg = ROUTE_CONFIG[currentActiveRoute];
  if (!currentCfg || !perms.includes(currentCfg.perm)) {
    const fallback = CANONICAL_PERMS.find((p) => perms.includes(p)) || "apis";
    applyRoute(fallback, { updateUrl: true, replace: true });
  } else {
    syncNavClasses(currentActiveRoute);
  }
}

function applyRoute(routeName, options = {}) {
  let effectiveRoute = ROUTE_CONFIG[routeName] ? routeName : "publicaciones";

  if (Array.isArray(allowedModulePerms)) {
    if (allowedModulePerms.length === 0) {
      effectiveRoute = "apis";
    } else if (!allowedModulePerms.includes(ROUTE_CONFIG[effectiveRoute].perm)) {
      effectiveRoute = CANONICAL_PERMS.find((p) => allowedModulePerms.includes(p)) || "apis";
    }
  }

  const config = ROUTE_CONFIG[effectiveRoute] || ROUTE_CONFIG.publicaciones;
  const canonicalPath = config.path;
  const shouldUpdateUrl = options.updateUrl !== false;

  if (shouldUpdateUrl && typeof window !== "undefined" && window.history) {
    const currentPath = (window.location.pathname || "").replace(/\/+$/, "") || "/dashboard";
    if (options.replace || options.isRedirect || currentPath !== canonicalPath) {
      if (options.push && !options.replace && !options.isRedirect && effectiveRoute === routeName) {
        window.history.pushState({ route: effectiveRoute }, "", canonicalPath);
      } else {
        window.history.replaceState({ route: effectiveRoute }, "", canonicalPath);
      }
    }
  }

  currentActiveRoute = effectiveRoute;
  try {
    localStorage.setItem("upa_active_route", effectiveRoute);
  } catch (_) {}

  syncNavClasses(effectiveRoute);

  Object.values(ROUTE_CONFIG).forEach((c) => {
    const v = document.getElementById(c.viewId);
    if (v) v.classList.add("hidden");
  });
  const legacyDiag = document.getElementById("view-diagnostic");
  if (legacyDiag) legacyDiag.classList.add("hidden");

  const activeView = document.getElementById(config.viewId);
  if (activeView) activeView.classList.remove("hidden");

  const edBtn = document.getElementById("mode-btn-editorial");
  const stBtn = document.getElementById("mode-btn-student");

  if (effectiveRoute === "publicaciones") {
    if (edBtn) edBtn.classList.add("is-active");
    if (stBtn) stBtn.classList.remove("is-active");
    if (window.UpaCockpit && typeof window.UpaCockpit.loadPanelData === "function") {
      window.UpaCockpit.loadPanelData();
    }
  } else if (effectiveRoute === "apis") {
    if (stBtn) stBtn.classList.add("is-active");
    if (edBtn) edBtn.classList.remove("is-active");
    updateJsonView();
  } else if (effectiveRoute === "grupos") {
    if (edBtn) edBtn.classList.remove("is-active");
    if (stBtn) stBtn.classList.remove("is-active");
    renderGroupsModule();
  } else if (effectiveRoute === "roles") {
    if (edBtn) edBtn.classList.remove("is-active");
    if (stBtn) stBtn.classList.remove("is-active");
    renderAdminsModule();
  }
}

function navigate(targetPath, options = {}) {
  const resolved = resolveRoute(targetPath);
  const shouldPush = options.push !== false && !options.replace && !resolved.isRedirect;
  applyRoute(resolved.name, {
    updateUrl: true,
    push: shouldPush,
    replace: !shouldPush || options.replace || resolved.isRedirect,
    isRedirect: resolved.isRedirect,
  });
}

const UpaRouter = {
  ROUTES: {
    PUBLICACIONES: "/dashboard/publicaciones",
    GRUPOS: "/dashboard/grupos",
    ROLES: "/dashboard/roles",
    APIS: "/dashboard/apis",
    DIAGNOSTICO: "/dashboard/apis",
    ESTUDIANTES: "/dashboard/apis",
  },
  resolveRoute,
  applyRoute,
  applyUserPermissions,
  navigate,
  syncNavClasses,
  getCurrentRoute() {
    return currentActiveRoute;
  },
  reapplyCurrentRoute() {
    applyRoute(currentActiveRoute, { updateUrl: false });
  },
  init() {
    const initialResolved = resolveRoute(
      typeof window !== "undefined" ? window.location.pathname : "/dashboard/publicaciones"
    );
    applyRoute(initialResolved.name, {
      updateUrl: true,
      push: false,
      replace: initialResolved.isRedirect,
      isRedirect: initialResolved.isRedirect,
    });

    if (typeof window !== "undefined") {
      window.addEventListener("popstate", () => {
        const popResolved = resolveRoute(window.location.pathname);
        applyRoute(popResolved.name, {
          updateUrl: popResolved.isRedirect,
          push: false,
          replace: true,
          isRedirect: popResolved.isRedirect,
        });
      });
    }
  },
};

window.UpaRouter = UpaRouter;

// ===========================================================================
// Inicialización de eventos del DOM
// ===========================================================================

function setupGroupsFormHandlers() {
  const btnCreateGroup = document.getElementById("btn-create-group");
  const btnBack = document.getElementById("btn-group-back");
  const btnCancel = document.getElementById("btn-group-cancel");
  const btnDelete = document.getElementById("btn-group-delete");
  const btnAddWs = document.getElementById("btn-add-ws-custom");
  const inputWs = document.getElementById("group-input-ws-custom");
  const btnAddEmail = document.getElementById("btn-add-group-email");
  const inputEmail = document.getElementById("group-input-email");
  const formGroup = document.getElementById("form-group-editor");
  const groupsFilterInput = document.getElementById("groups-filter-input");
  const wsFilterInput = document.getElementById("group-workspace-filter");

  if (groupsFilterInput) {
    groupsFilterInput.addEventListener("input", () => renderGroupsListItems(appGroupsCache));
  }
  if (wsFilterInput) {
    wsFilterInput.addEventListener("input", () => renderWorkspacePicker());
  }

  if (btnCreateGroup) btnCreateGroup.addEventListener("click", () => openGroupEditor(null));
  if (btnBack) btnBack.addEventListener("click", showGroupsListPanel);
  if (btnCancel) btnCancel.addEventListener("click", showGroupsListPanel);

  if (btnAddWs && inputWs) {
    const addWs = () => {
      const val = inputWs.value.trim();
      if (!val) return;
      if (!state.groupEditor.selectedWorkspaceGroups.includes(val)) {
        state.groupEditor.selectedWorkspaceGroups.push(val);
      }
      inputWs.value = "";
      renderWorkspacePicker();
    };
    btnAddWs.addEventListener("click", addWs);
    inputWs.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        addWs();
      }
    });
  }

  if (btnAddEmail && inputEmail) {
    const addEmail = () => {
      const val = inputEmail.value.trim().toLowerCase();
      if (!val) return;
      if (!val.includes("@")) {
        showModuleNotice("groups-notice", "error", "Ingrese un correo válido.");
        return;
      }
      if (!state.groupEditor.emails.includes(val)) {
        state.groupEditor.emails.push(val);
      }
      inputEmail.value = "";
      showModuleNotice("groups-notice", "", "");
      renderGroupEmailsChips();
    };
    btnAddEmail.addEventListener("click", addEmail);
    inputEmail.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        addEmail();
      }
    });
  }

  if (formGroup) {
    formGroup.addEventListener("submit", async (e) => {
      e.preventDefault();
      const nameEl = document.getElementById("group-input-name");
      const descEl = document.getElementById("group-input-description");
      const name = nameEl ? nameEl.value.trim() : "";
      const description = descEl ? descEl.value.trim() : "";
      if (!name) {
        showModuleNotice("groups-notice", "error", "El nombre del grupo es obligatorio.");
        return;
      }

      const wsGroups = state.groupEditor.selectedWorkspaceGroups.slice();
      const payload = {
        name,
        description,
        google_groups: wsGroups,
        google_group: wsGroups[0] || "",
        emails: state.groupEditor.emails.slice(),
      };

      const editingId = state.groupEditor.editingId;
      try {
        const res = await apiRequest(
          editingId ? `/api/groups/${encodeURIComponent(editingId)}` : "/api/groups",
          {
            method: editingId ? "PUT" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          }
        );
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          showModuleNotice("groups-notice", "error", err.detail || "No se pudo guardar el grupo.");
          return;
        }
        await renderGroupsModule();
        showModuleNotice("groups-notice", "success", editingId ? "Grupo actualizado." : "Grupo creado.");
      } catch (_) {
        showModuleNotice("groups-notice", "error", "Error de conexión al guardar el grupo.");
      }
    });
  }

  if (btnDelete) {
    btnDelete.addEventListener("click", async () => {
      const id = state.groupEditor.editingId;
      if (!id) return;
      if (!confirm("¿Eliminar este grupo de forma permanente?")) return;
      try {
        const res = await apiRequest(`/api/groups/${encodeURIComponent(id)}`, { method: "DELETE" });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          showModuleNotice("groups-notice", "error", err.detail || "No se pudo eliminar el grupo.");
          return;
        }
        await renderGroupsModule();
        showModuleNotice("groups-notice", "success", "Grupo eliminado.");
      } catch (_) {
        showModuleNotice("groups-notice", "error", "Error de conexión al eliminar el grupo.");
      }
    });
  }
}

function setupRolesFormHandlers() {
  const formAddAdmin = document.getElementById("form-add-admin");
  if (!formAddAdmin) return;

  formAddAdmin.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("input-admin-email");
    const email = (input ? input.value : "").trim().toLowerCase();
    if (!email.endsWith("@upa.edu.py")) {
      showModuleNotice("roles-notice", "error", "El correo debe pertenecer al dominio @upa.edu.py.");
      return;
    }

    const perms = [];
    if (document.getElementById("perm-publications")?.checked) perms.push("publicaciones");
    if (document.getElementById("perm-groups")?.checked) perms.push("grupos");
    if (document.getElementById("perm-admins")?.checked) perms.push("roles");
    if (document.getElementById("perm-diagnostic")?.checked) perms.push("apis");

    try {
      const res = await apiRequest("/api/roles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          name: email
            .split("@")[0]
            .replace(/\./g, " ")
            .replace(/\b\w/g, (l) => l.toUpperCase()),
          permissions: perms,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showModuleNotice("roles-notice", "error", err.detail || "No se pudo autorizar la cuenta.");
        return;
      }
      if (input) input.value = "";
      ["perm-publications", "perm-groups", "perm-admins", "perm-diagnostic"].forEach((cbId) => {
        const cb = document.getElementById(cbId);
        if (cb) cb.checked = false;
      });
      showModuleNotice("roles-notice", "success", `Cuenta ${email} autorizada.`);
      await renderAdminsModule();
      if (state.currentUser && String(state.currentUser.email || "").toLowerCase() === email) {
        await refreshCurrentUserPermissions();
      }
    } catch (_) {
      showModuleNotice("roles-notice", "error", "Error de conexión al autorizar la cuenta.");
    }
  });
}

function setupSidebarNavigation() {
  const btnPubs = document.getElementById("nav-mod-publications");
  const btnGroups = document.getElementById("nav-mod-groups");
  const btnAdmins = document.getElementById("nav-mod-admins");
  const btnDiag = document.getElementById("nav-mod-diagnostic");
  const btnStudents = document.getElementById("nav-mod-students");
  const headerLogoLink = document.getElementById("header-logo-link");

  if (btnPubs) btnPubs.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.PUBLICACIONES));
  if (btnGroups) btnGroups.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.GRUPOS));
  if (btnAdmins) btnAdmins.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.ROLES));
  if (btnDiag) btnDiag.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.APIS));
  if (btnStudents) btnStudents.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.APIS));
  if (headerLogoLink) {
    headerLogoLink.addEventListener("click", (e) => {
      e.preventDefault();
      UpaRouter.navigate(UpaRouter.ROUTES.PUBLICACIONES);
    });
  }

  const modeBtnStudent = document.getElementById("mode-btn-student");
  if (modeBtnStudent) modeBtnStudent.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.APIS));

  const modeBtnEditorial = document.getElementById("mode-btn-editorial");
  if (modeBtnEditorial) {
    modeBtnEditorial.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.PUBLICACIONES));
  }

  UpaRouter.init();
  setupGroupsFormHandlers();
  setupRolesFormHandlers();
}

function init() {
  if (window.UpaCockpit) {
    window.UpaCockpit.configure({
      getToken: getStoredToken,
      onUnauthorized: () => {
        logout();
        showLoginAlert("Su sesión ha expirado. Inicie sesión nuevamente.", "info");
      },
    });
  }

  if (DOM_ELEMENTS.formLogin) DOM_ELEMENTS.formLogin.addEventListener("submit", handleLoginSubmit);
  if (DOM_ELEMENTS.btnRefresh) DOM_ELEMENTS.btnRefresh.addEventListener("click", refreshDashboard);
  if (DOM_ELEMENTS.btnLogout) DOM_ELEMENTS.btnLogout.addEventListener("click", logout);

  if (DOM_ELEMENTS.userMenuBtn && DOM_ELEMENTS.userProfileDropdown) {
    DOM_ELEMENTS.userMenuBtn.addEventListener("click", (e) => {
      if (e && e.stopPropagation) e.stopPropagation();
      const willOpen = DOM_ELEMENTS.userProfileDropdown.classList.contains("hidden");
      DOM_ELEMENTS.userProfileDropdown.classList.toggle("hidden", !willOpen);
      if (DOM_ELEMENTS.userMenuBtn.setAttribute) {
        DOM_ELEMENTS.userMenuBtn.setAttribute("aria-expanded", willOpen ? "true" : "false");
      }
    });
    document.addEventListener("click", (e) => {
      if (
        DOM_ELEMENTS.userMenuWrapper &&
        DOM_ELEMENTS.userMenuWrapper.contains &&
        e &&
        e.target &&
        !DOM_ELEMENTS.userMenuWrapper.contains(e.target)
      ) {
        closeUserDropdown();
      }
    });
  }

  if (DOM_ELEMENTS.btnOpenClassroomModal) {
    DOM_ELEMENTS.btnOpenClassroomModal.addEventListener("click", () => {
      if (DOM_ELEMENTS.modalClassroom) DOM_ELEMENTS.modalClassroom.classList.remove("hidden");
      if (DOM_ELEMENTS.modalInputClassroomToken && DOM_ELEMENTS.modalInputClassroomToken.focus) {
        DOM_ELEMENTS.modalInputClassroomToken.focus();
      }
    });
  }

  if (DOM_ELEMENTS.btnCloseClassroomModal) {
    DOM_ELEMENTS.btnCloseClassroomModal.addEventListener("click", () => {
      if (DOM_ELEMENTS.modalClassroom) DOM_ELEMENTS.modalClassroom.classList.add("hidden");
    });
  }

  if (DOM_ELEMENTS.btnCancelClassroom) {
    DOM_ELEMENTS.btnCancelClassroom.addEventListener("click", () => {
      if (DOM_ELEMENTS.modalClassroom) DOM_ELEMENTS.modalClassroom.classList.add("hidden");
    });
  }

  if (DOM_ELEMENTS.formClassroomToken) {
    DOM_ELEMENTS.formClassroomToken.addEventListener("submit", handleClassroomTokenSubmit);
  }

  const btnOpenRawJson = document.getElementById("btn-open-raw-json");
  const btnCopyJson = document.getElementById("btn-copy-json");

  if (btnOpenRawJson) {
    btnOpenRawJson.addEventListener("click", () => {
      const payload = state.diagnostics
        ? { diagnostico_sistema: state.diagnostics, contrato_app_movil: getAppJsonData() }
        : getAppJsonData();
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank");
    });
  }

  if (btnCopyJson) {
    btnCopyJson.addEventListener("click", async () => {
      const payload = state.diagnostics
        ? { diagnostico_sistema: state.diagnostics, contrato_app_movil: getAppJsonData() }
        : getAppJsonData();
      try {
        await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
        btnCopyJson.textContent = "Copiado";
        setTimeout(() => {
          btnCopyJson.textContent = "Copiar JSON";
        }, 2000);
      } catch (_) {
        alert("JSON copiado al portapapeles.");
      }
    });
  }

  checkHealth();
  setupSidebarNavigation();

  try {
    const urlParams = new URLSearchParams(window.location.search);
    const tokenFromUrl = urlParams.get("token");
    if (tokenFromUrl) {
      setStoredToken(tokenFromUrl);
      document.documentElement.classList.add("has-auth");
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  } catch (_) {}

  const existingToken = getStoredToken();
  if (existingToken) {
    document.documentElement.classList.add("has-auth");
    if (DOM_ELEMENTS.viewLogin) DOM_ELEMENTS.viewLogin.classList.add("hidden");
    if (DOM_ELEMENTS.viewDashboard) DOM_ELEMENTS.viewDashboard.classList.remove("hidden");
    refreshDashboard();
  } else {
    document.documentElement.classList.remove("has-auth");
    showLoginView();
  }
}

document.addEventListener("DOMContentLoaded", init);
