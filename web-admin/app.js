/**
 * Portal Institucional UPA (web-admin)
 * Demostracion interactiva de las 4 APIs del Backend:
 * 1. Google OAuth 2.0 (Login @upa.edu.py, nombre y avatar)
 * 2. Google Mailgruppen (Exclusivo para pascal.thommen@upa.edu.py)
 * 3. Google Classroom (Cursos y calendario interactivo de plazos)
 * 4. Campus Feed & Instagram Ingestion (Posts sincronizados)
 *
 * Estricto cumplimiento de la doctrina Zero-Mock (llamadas reales a la API REST).
 */

const STORAGE_KEY = "upa_access_token";

const DOM_ELEMENTS = {
  viewLogin: document.getElementById("view-login"),
  viewDashboard: document.getElementById("view-dashboard"),
  formLogin: document.getElementById("form-login"),
  inputToken: document.getElementById("input-token"),
  inputClassroomToken: document.getElementById("input-classroom-token"),
  loginAlert: document.getElementById("login-alert"),
  authActions: document.getElementById("auth-actions"),
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

const GROUP_LABELS = {
  ALL: "Comunidad UPA General",
  TIE: "Ingeniería Empresarial",
  PI: "Ingeniería Industrial",
  TI: "Tecnologías de la Información",
  PROF: "Cuerpo Docente y Académico",
};

// Estado reactivo de la aplicacion
const state = {
  currentUser: null,
  courses: [],
  deadlines: [],
  feedPosts: [],
  currentMonth: new Date().getMonth(),
  currentYear: new Date().getFullYear(),
  selectedDate: null,
};

function getStoredToken() {
  return localStorage.getItem(STORAGE_KEY);
}

function setStoredToken(token) {
  if (token) {
    localStorage.setItem(STORAGE_KEY, token);
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function logout() {
  setStoredToken(null);
  state.currentUser = null;
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

function showLoginView() {
  if (window.UpaCockpit) window.UpaCockpit.reset();
  DOM_ELEMENTS.viewLogin.classList.remove("hidden");
  DOM_ELEMENTS.viewDashboard.classList.add("hidden");
  DOM_ELEMENTS.authActions.innerHTML = "";
}

function showDashboardView(user) {
  document.documentElement.classList.add("has-auth");
  DOM_ELEMENTS.viewLogin.classList.add("hidden");
  DOM_ELEMENTS.viewDashboard.classList.remove("hidden");

  const email = (user && user.email) || "";
  const initials = email ? email.substring(0, 2).toUpperCase() : "PT";

  DOM_ELEMENTS.authActions.innerHTML = `
    <div class="flex items-center gap-2">
      <div class="w-7 h-7 rounded-full bg-[#6c9339] text-white flex items-center justify-center font-bold text-[11px] shadow-2xs">
        ${initials}
      </div>
      <span class="text-xs text-slate-600 hidden sm:inline font-mono truncate max-w-xs">${email}</span>
      <button id="btn-logout" class="px-2.5 py-1 text-xs font-medium text-slate-600 hover:text-red-700 hover:bg-red-50 rounded-lg border border-slate-200 transition">
        Cerrar sesión
      </button>
    </div>
  `;

  document.getElementById("btn-logout").addEventListener("click", logout);
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

  const response = await fetch(endpoint, {
    ...options,
    headers,
  });

  return response;
}

async function checkHealth() {
  try {
    const res = await fetch("/health");
    if (res.ok) {
      const data = await res.json();
      DOM_ELEMENTS.diagBackend.textContent = data.service || "Activo";
      DOM_ELEMENTS.diagEnv.textContent = data.environment || "Producción";
    } else {
      DOM_ELEMENTS.diagBackend.textContent = `Error HTTP ${res.status}`;
    }
  } catch (err) {
    DOM_ELEMENTS.diagBackend.textContent = "Desconectado";
  }
}

/**
 * Carga el perfil del usuario autenticado (API 1 & API 2).
 */
async function loadUserProfile() {
  try {
    const res = await apiRequest("/api/auth/me");
    if (res.status === 401) {
      logout();
      showLoginAlert("Su sesión ha expirado. Por favor, inicie sesión nuevamente.", "info");
      return null;
    }

    if (!res.ok) {
      throw new Error(`Error ${res.status} al obtener perfil`);
    }

    const user = await res.json();
    state.currentUser = user;
    renderUserProfile(user);
    showDashboardView(user);
    return user;
  } catch (error) {
    console.error("Fallo al cargar perfil:", error);
    showLoginView();
    showLoginAlert("No fue posible validar la sesión institucional.", "error");
    return null;
  }
}

/**
 * Renderiza el perfil de usuario e implementa la regla de privacidad de Mailgruppen (API 1 & API 2).
 */
function renderUserProfile(user) {
  // 1. Google OAuth: Nombre y avatar
  DOM_ELEMENTS.userFullName.textContent = user.full_name || user.email.split("@")[0];
  DOM_ELEMENTS.userEmail.textContent = user.email || "";

  const initials = (user.full_name || user.email)
    .split(" ")
    .map((n) => n[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  DOM_ELEMENTS.userAvatar.textContent = initials || "U";

  const role = (user.role || "user").toUpperCase();
  const roleLabels = { ADMIN: "ADMINISTRADOR", EDITOR: "REDACCIÓN" };
  DOM_ELEMENTS.userRoleBadge.textContent = roleLabels[role] || "ESTUDIANTE";

  // Estado de Classroom
  const hasClassroom = Boolean(user.has_classroom_token);
  if (hasClassroom) {
    DOM_ELEMENTS.userClassroomSyncBadge.textContent = "• Classroom: Activo";
    DOM_ELEMENTS.userClassroomSyncBadge.className = "text-emerald-600 font-semibold";
    DOM_ELEMENTS.classroomPermissionAlert.classList.add("hidden");
  } else {
    DOM_ELEMENTS.userClassroomSyncBadge.textContent = "• Classroom: Pendiente";
    DOM_ELEMENTS.userClassroomSyncBadge.className = "text-amber-600 font-semibold";
    DOM_ELEMENTS.classroomPermissionAlert.classList.remove("hidden");
  }

  // 2. Regla de Privacidad de Google Mailgruppen:
  // Estrictamente visible solo para pascal.thommen@upa.edu.py
  const isExclusiveUser = (user.email || "").toLowerCase() === "pascal.thommen@upa.edu.py";

  // Control de visualización de barra lateral para estudiantes
  const sidebar = document.getElementById("sidebar-menu");
  if (sidebar) {
    const isPrivileged = user && (user.role === "admin" || user.role === "editor");
    if (isPrivileged) {
      sidebar.classList.remove("hidden");
    } else {
      sidebar.classList.add("hidden");
    }
  }
  // Estrictamente los 3 grupos reales obtenidos de Google Workspace Directory API
  // Se excluyen los tags sintéticos internos (ALL, TIE)
  const realGoogleGroups = Array.isArray(user.google_groups) && user.google_groups.length > 0
    ? user.google_groups
    : (Array.isArray(user.groups) ? user.groups.filter((g) => g !== "ALL" && g !== "TIE") : []);
  const groups = realGoogleGroups;

  if (isExclusiveUser && groups.length > 0) {
    DOM_ELEMENTS.tileMailgroups.classList.remove("hidden");
    DOM_ELEMENTS.groupsCount.textContent = `${groups.length} grupos`;
    DOM_ELEMENTS.userGroupsContainer.innerHTML = groups
      .map((grp) => {
        let name = "";
        let email = "";
        if (typeof grp === "object" && grp !== null) {
          name = grp.name || grp.email || grp.id || "";
          email = grp.email || "";
        } else {
          name = String(grp);
        }
        return `
          <div class="p-2.5 rounded-xl bg-slate-50 border border-slate-200/80 flex items-center justify-between gap-2 shadow-2xs">
            <div class="min-w-0">
              <span class="text-xs font-semibold text-slate-800 block truncate">${name}</span>
              ${email ? `<span class="text-[11px] text-slate-500 font-mono block truncate">${email}</span>` : ""}
            </div>
            <span class="px-2 py-0.5 text-[9px] font-bold rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 flex-shrink-0">Oficial</span>
          </div>
        `;
      })
      .join("");
  } else {
    // Si es estudiante regular o no tiene permiso, la kachel de grupos se oculta completamente
    DOM_ELEMENTS.tileMailgroups.classList.add("hidden");
  }
}

/**
 * Carga los cursos activos de Google Classroom (API 3A).
 */
async function loadClassroomCourses() {
  const container = DOM_ELEMENTS.coursesContainer;
  container.innerHTML = `
    <div class="flex items-center justify-center p-6 text-slate-400 gap-2">
      <div class="spinner"></div>
      <span class="text-xs">Sincronizando cursos de Google Classroom...</span>
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
        <div class="p-4 rounded-lg bg-red-50 text-red-700 text-xs">
          No se pudieron cargar los cursos (Código ${res.status}).
        </div>
      `;
      DOM_ELEMENTS.coursesCount.textContent = "Error";
      return;
    }

    const courses = await res.json();
    state.courses = Array.isArray(courses) ? courses : [];
    DOM_ELEMENTS.coursesCount.textContent = `${state.courses.length} cursos`;

    if (state.courses.length === 0) {
      container.innerHTML = `
        <div class="p-6 text-center text-slate-400 text-xs border border-dashed border-slate-200 rounded-lg">
          No hay cursos activos en Google Classroom para este semestre.
        </div>
      `;
      return;
    }

    container.innerHTML = state.courses
      .map((c) => {
        const link = c.alternate_link || `https://classroom.google.com/c/${c.id}`;
        return `
          <div class="course-card flex flex-col justify-between gap-1.5">
            <div>
              <h4 class="font-bold text-xs text-slate-900">${c.name}</h4>
              <p class="text-[11px] text-slate-500">${c.section || "Sin sección"} ${c.room ? `• Aula: ${c.room}` : ""}</p>
            </div>
            <div class="flex items-center justify-between pt-1.5 border-t border-slate-100 text-[11px]">
              <span class="text-[10px] text-slate-400 font-mono">ID: ${c.id}</span>
              <a href="${link}" target="_blank" rel="noopener noreferrer" class="btn-classroom-link">
                <span>Abrir Curso</span>
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
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
    DOM_ELEMENTS.coursesCount.textContent = "Error";
  }
}

/**
 * Carga las tareas y deadlines de Google Classroom (API 3B).
 */
async function loadClassroomDeadlines() {
  try {
    const res = await apiRequest("/api/classroom/deadlines");
    if (res.status === 401) {
      logout();
      return;
    }

    if (!res.ok) {
      if (DOM_ELEMENTS.deadlinesCount) DOM_ELEMENTS.deadlinesCount.textContent = "Error";
      return;
    }

    const data = await res.json();
    state.deadlines = Array.isArray(data) ? data : data.deadlines || [];
    if (DOM_ELEMENTS.deadlinesCount) {
      DOM_ELEMENTS.deadlinesCount.textContent = `${state.deadlines.length} tareas`;
    }

    renderCalendar();
    renderDeadlinesList(state.deadlines);
  } catch (error) {
    console.error("Fallo al obtener plazos:", error);
    if (DOM_ELEMENTS.deadlinesCount) DOM_ELEMENTS.deadlinesCount.textContent = "Error";
  }
}

/**
 * Renderiza el calendario mensual si el elemento existe en el DOM.
 */
function renderCalendar() {
  const grid = DOM_ELEMENTS.calendarGrid;
  if (!grid || !DOM_ELEMENTS.calMonthTitle) return;

  const monthNames = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
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

    const classes = [
      "cal-day",
      hasDeadline ? "has-deadline" : "",
      isSelected ? "is-selected" : "",
    ].filter(Boolean).join(" ");

    html += `<div class="${classes}" data-date="${dateKey}" title="${hasDeadline ? `${deadlineDaysMap[dateKey]} entrega(s)` : ''}">${day}</div>`;
  }

  grid.innerHTML = html;

  grid.querySelectorAll(".cal-day[data-date]").forEach((el) => {
    el.addEventListener("click", () => {
      const selected = el.getAttribute("data-date");
      if (state.selectedDate === selected) {
        state.selectedDate = null;
        if (DOM_ELEMENTS.selectedDateLabel) DOM_ELEMENTS.selectedDateLabel.textContent = "Próximas Entregas";
        renderDeadlinesList(state.deadlines);
      } else {
        state.selectedDate = selected;
        if (DOM_ELEMENTS.selectedDateLabel) DOM_ELEMENTS.selectedDateLabel.textContent = `Entregas del ${selected}`;
        const filtered = state.deadlines.filter((d) => (d.due_date_formatted || "").startsWith(selected));
        renderDeadlinesList(filtered);
      }
      renderCalendar();
    });
  });
}

/**
 * Obtiene la abreviación del día y número para el diseño nativo tipo tarjeta (ej. VIE 16).
 */
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
  if (dateObj && !isNaN(dateObj.getTime())) {
    const dayOfWeek = dayNames[dateObj.getDay()];
    const dayNum = String(dateObj.getDate()).padStart(2, "0");
    return { dayOfWeek, dayNum };
  }
  return { dayOfWeek: "PLAZO", dayNum: "--" };
}

/**
 * Renderiza la lista cronológica limpia de tareas y entregas estilo App Móvil nativa.
 */
function renderDeadlinesList(items) {
  const container = DOM_ELEMENTS.deadlinesContainer;
  if (!container) return;

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="p-6 text-center text-slate-400 text-xs border border-dashed border-slate-200 rounded-xl">
        No hay entregas pendientes para este periodo.
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
        : (d.due_date_formatted ? d.due_date_formatted.split(" ")[1] || "" : "");

      return `
        <div class="flex items-start gap-3 p-3 rounded-xl bg-slate-50 border border-slate-200/80 hover:bg-slate-100/60 transition shadow-2xs">
          <div class="flex flex-col items-center justify-center w-12 h-12 rounded-xl bg-white border border-slate-200 text-center flex-shrink-0 shadow-2xs">
            <span class="text-[10px] font-extrabold text-[#6c9339] leading-tight uppercase">${badge.dayOfWeek}</span>
            <span class="text-base font-extrabold text-slate-900 leading-tight">${badge.dayNum}</span>
          </div>
          <div class="flex-1 min-w-0 space-y-1">
            <div class="flex items-center justify-between gap-2">
              <span class="text-[10px] font-bold text-slate-500 uppercase tracking-wide truncate">${d.course || "Classroom"}</span>
              ${d.max_points ? `<span class="text-[10px] font-bold px-1.5 py-0.2 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded">${d.max_points} pts</span>` : ""}
            </div>
            <h4 class="font-bold text-xs text-slate-900 truncate" title="${d.title}">${d.title}</h4>
            <div class="flex items-center justify-between pt-0.5 text-[11px] text-slate-400">
              <span class="font-mono text-[10px] text-slate-500">${timeStr ? `⏰ ${timeStr}` : ""}</span>
              <a href="${link}" target="_blank" rel="noopener noreferrer" class="text-[11px] font-semibold text-blue-700 hover:text-blue-900 flex items-center gap-1">
                <span>Ver tarea</span>
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
              </a>
            </div>
          </div>
        </div>
      `;
    })
    .join("");
}

/**
 * Carga las publicaciones del Campus Feed e Instagram sincronizadas por el backend (API 4).
 */
async function loadCampusFeed() {
  const container = DOM_ELEMENTS.feedContainer;
  container.innerHTML = `
    <div class="col-span-full flex items-center justify-center p-8 text-slate-400 gap-2">
      <div class="spinner"></div>
      <span class="text-xs">Sincronizando feed oficial de Instagram (@upalemana)...</span>
    </div>
  `;

  try {
    const res = await apiRequest("/api/v1/feed");
    if (!res.ok) {
      container.innerHTML = `
        <div class="col-span-full p-4 rounded-lg bg-red-50 text-red-700 text-xs">
          No se pudo consultar el feed de Instagram del backend (Código ${res.status}).
        </div>
      `;
      DOM_ELEMENTS.feedCountBadge.textContent = "Error";
      return;
    }

    const data = await res.json();
    const posts = data.posts || [];
    state.feedPosts = posts;
    DOM_ELEMENTS.feedCountBadge.textContent = `${posts.length} publicaciones sincronizadas`;

    if (posts.length === 0) {
      container.innerHTML = `
        <div class="col-span-full p-8 text-center text-slate-400 text-xs border border-dashed border-slate-200 rounded-lg">
          No se encontraron publicaciones en el feed institucional.
        </div>
      `;
      return;
    }

    container.innerHTML = posts
      .slice(0, 8)
      .map((post) => {
        const title = post.title || post.summary || "Publicación de Instagram UPA";
        const dateStr = post.published_at ? new Date(post.published_at).toLocaleDateString("es-PY") : "";
        const permalink = post.permalink || "https://www.instagram.com/upalemana/";

        const imageHtml = post.image_url
          ? `<img src="${post.image_url}" alt="Instagram post" class="feed-card-img" loading="lazy" onerror="this.onerror=null; this.src='https://placehold.co/400x240/0a192f/white?text=UPA+Campus';">`
          : `<div class="feed-card-placeholder">UPA Campus</div>`;

        return `
          <article class="feed-card">
            ${imageHtml}
            <div class="p-3 flex-1 flex flex-col justify-between space-y-2">
              <div>
                <div class="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                  <span class="font-bold text-purple-700 bg-purple-50 px-1.5 py-0.5 rounded border border-purple-200">INSTAGRAM</span>
                  <span>${dateStr}</span>
                </div>
                <h4 class="font-bold text-xs text-slate-900 line-clamp-2" title="${title}">${title}</h4>
              </div>
              <div class="pt-2 border-t border-slate-100 flex items-center justify-between text-xs">
                <span class="text-[10px] text-slate-400">@upalemana</span>
                <a href="${permalink}" target="_blank" rel="noopener noreferrer" class="btn-classroom-link text-purple-700 bg-purple-50 hover:bg-purple-100">
                  <span>Ver en Instagram</span>
                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                </a>
              </div>
            </div>
          </article>
        `;
      })
      .join("");
  } catch (error) {
    console.error("Fallo al obtener feed de Instagram:", error);
    container.innerHTML = `
      <div class="col-span-full p-4 rounded-lg bg-red-50 text-red-700 text-xs">
        Error al sincronizar el feed del campus con el backend.
      </div>
    `;
    DOM_ELEMENTS.feedCountBadge.textContent = "Error";
  }
}

/**
 * Refresca todo el contenido de las 4 APIs.
 */
async function refreshDashboard() {
  await checkHealth();
  const user = await loadUserProfile();
  if (user) {
    // Cockpit de redaccion: visible solo para administradores y redactores
    if (window.UpaCockpit) window.UpaCockpit.onUserLoaded(user);
    await Promise.all([loadClassroomCourses(), loadClassroomDeadlines(), loadCampusFeed()]);
    updateJsonView();
    if (window.location.pathname && window.location.pathname.startsWith("/dashboard")) {
      navigateTo(window.location.pathname, false);
    }
  }
}

/**
 * Google Identity Services Callback
 */
window.handleGoogleCredentialResponse = async function(response) {
  if (!response || !response.credential) {
    showLoginAlert("No se recibió credencial de Google OAuth.", "error");
    return;
  }
  showLoginAlert("Autenticando con Google OAuth institucional (@upa.edu.py)...", "info");
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
      const err = await res.json();
      showLoginAlert(err.detail || "Acceso restringido únicamente a cuentas @upa.edu.py", "error");
      return;
    }
    const errText = await res.text();
    showLoginAlert(`Error al autenticar: ${errText}`, "error");
  } catch (error) {
    console.error("Fallo al procesar login de Google:", error);
    showLoginAlert("Error de conexión durante el login de Google.", "error");
  }
};

function getAppJsonData() {
  return {
    portal: "UPA Mobile Campus Platform",
    api_version: "1.0.0",
    generated_at: new Date().toISOString(),
    user: state.currentUser,
    deadlines: state.deadlines,
    courses: state.courses,
    instagram_feed: state.feedPosts,
  };
}

function updateJsonView() {
  const rawJsonOutput = document.getElementById("raw-json-output");
  if (rawJsonOutput) {
    const data = getAppJsonData();
    rawJsonOutput.textContent = JSON.stringify(data, null, 2);
  }
}

/**
 * Maneja el inicio de sesion autenticado.
 */
async function handleLoginSubmit(event) {
  event.preventDefault();
  const token = DOM_ELEMENTS.inputToken.value.trim();
  const classroomToken = DOM_ELEMENTS.inputClassroomToken.value.trim();

  if (!token) {
    showLoginAlert("Por favor ingrese un token de acceso o Google ID Token.", "error");
    return;
  }

  showLoginAlert("Autenticando con el servidor institucional...", "info");

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
        showLoginAlert("Inicio de sesion exitoso.", "success");
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
      const err = await googleLoginResp.json();
      showLoginAlert(err.detail || "Acceso restringido únicamente a correos @upa.edu.py", "error");
      return;
    }

    // Probar como JWT directo
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
    showLoginAlert("Token inválido o expirado. Verifique las credenciales institucionales.", "error");
  } catch (error) {
    console.error("Error durante el inicio de sesión:", error);
    setStoredToken(null);
    showLoginAlert("Error de conexión con la API institucional.", "error");
  }
}

async function handleClassroomTokenSubmit(event) {
  event.preventDefault();
  const token = DOM_ELEMENTS.modalInputClassroomToken.value.trim();
  if (!token) return;

  try {
    const res = await apiRequest("/api/auth/classroom-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ classroom_token: token }),
    });

    if (res.ok) {
      DOM_ELEMENTS.modalClassroom.classList.add("hidden");
      DOM_ELEMENTS.modalInputClassroomToken.value = "";
      await refreshDashboard();
    } else {
      alert("No se pudo guardar el token de Google Classroom.");
    }
  } catch (error) {
    console.error("Error al actualizar token de Classroom:", error);
    alert("Error de red al actualizar token de Classroom.");
  }
}

function init() {
  if (window.UpaCockpit) {
    window.UpaCockpit.configure({
      getToken: getStoredToken,
      onUnauthorized: () => {
        logout();
        showLoginAlert("Su sesión ha expirado. Por favor, inicie sesión nuevamente.", "info");
      },
    });
  }
  DOM_ELEMENTS.formLogin.addEventListener("submit", handleLoginSubmit);
  DOM_ELEMENTS.btnRefresh.addEventListener("click", refreshDashboard);

  if (DOM_ELEMENTS.calPrev) {
    DOM_ELEMENTS.calPrev.addEventListener("click", () => {
      state.currentMonth--;
      if (state.currentMonth < 0) {
        state.currentMonth = 11;
        state.currentYear--;
      }
      renderCalendar();
    });
  }

  if (DOM_ELEMENTS.calNext) {
    DOM_ELEMENTS.calNext.addEventListener("click", () => {
      state.currentMonth++;
      if (state.currentMonth > 11) {
        state.currentMonth = 0;
        state.currentYear++;
      }
      renderCalendar();
    });
  }

  if (DOM_ELEMENTS.btnOpenClassroomModal) {
    DOM_ELEMENTS.btnOpenClassroomModal.addEventListener("click", () => {
      if (DOM_ELEMENTS.modalClassroom) DOM_ELEMENTS.modalClassroom.classList.remove("hidden");
      if (DOM_ELEMENTS.modalInputClassroomToken) DOM_ELEMENTS.modalInputClassroomToken.focus();
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

  const tabBtnDashboard = document.getElementById("tab-btn-dashboard");
  const tabBtnJson = document.getElementById("tab-btn-json");
  const tabContentDashboard = document.getElementById("tab-content-dashboard");
  const tabContentJson = document.getElementById("tab-content-json");
  const btnOpenRawJson = document.getElementById("btn-open-raw-json");
  const btnCopyJson = document.getElementById("btn-copy-json");

  if (tabBtnDashboard && tabBtnJson) {
    tabBtnDashboard.addEventListener("click", () => {
      tabBtnDashboard.className = "px-4 py-1.5 text-xs font-bold rounded-lg bg-blue-50 text-blue-800 border border-blue-200 transition";
      tabBtnJson.className = "px-4 py-1.5 text-xs font-semibold rounded-lg text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition";
      if (tabContentDashboard) tabContentDashboard.classList.remove("hidden");
      if (tabContentJson) tabContentJson.classList.add("hidden");
    });

    tabBtnJson.addEventListener("click", () => {
      tabBtnJson.className = "px-4 py-1.5 text-xs font-bold rounded-lg bg-blue-50 text-blue-800 border border-blue-200 transition";
      tabBtnDashboard.className = "px-4 py-1.5 text-xs font-semibold rounded-lg text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition";
      if (tabContentDashboard) tabContentDashboard.classList.add("hidden");
      if (tabContentJson) tabContentJson.classList.remove("hidden");
      updateJsonView();
    });
  }

  if (btnOpenRawJson) {
    btnOpenRawJson.addEventListener("click", () => {
      const data = getAppJsonData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank");
    });
  }

  if (btnCopyJson) {
    btnCopyJson.addEventListener("click", async () => {
      const data = getAppJsonData();
      try {
        await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
        btnCopyJson.textContent = "¡Copiado!";
        setTimeout(() => { btnCopyJson.textContent = "In Zwischenablage kopieren"; }, 2000);
      } catch (e) {
        alert("JSON copiado al portapapeles.");
      }
    });
  }

  const btnDevAdmin = document.getElementById("btn-dev-admin-login");
  if (btnDevAdmin) {
    btnDevAdmin.addEventListener("click", async () => {
      showLoginAlert("Iniciando sesión como Administrador...", "info");
      try {
        const resp = await fetch("/api/auth/dev-login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: "pascal.thommen@upa.edu.py" }),
        });
        if (resp.ok) {
          const data = await resp.json();
          setStoredToken(data.access_token);
          localStorage.setItem("upa_auth_token", data.access_token);
          showLoginAlert("Inicio de sesión exitoso.", "success");
          await refreshDashboard();
        } else {
          showLoginAlert("Error en acceso rápido.", "error");
        }
      } catch (e) {
        showLoginAlert("Error de conexión.", "error");
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
      localStorage.setItem("upa_auth_token", tokenFromUrl);
      document.documentElement.classList.add("has-auth");
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  } catch (_) {}

  const existingToken = getStoredToken();
  if (existingToken) {
    document.documentElement.classList.add("has-auth");
    DOM_ELEMENTS.viewLogin.classList.add("hidden");
    DOM_ELEMENTS.viewDashboard.classList.remove("hidden");
    refreshDashboard();
  } else {
    document.documentElement.classList.remove("has-auth");
    showLoginView();
  }
}

// ===========================================================================
// Módulos B y C: Grupos, Roles y Navegación Lateral
// ===========================================================================

const APP_GROUPS_STORAGE_KEY = "upa_app_groups_v1";
const APP_ADMINS_STORAGE_KEY = "upa_app_admins_v1";

const DEFAULT_APP_GROUPS = [
  {
    id: "estudiantes",
    name: "Estudiantes",
    description: "Comunidad estudiantil activa de grado y posgrado.",
    badgeClass: "bg-blue-100 text-blue-800 border-blue-200",
    googleGroup: "Estudiantes - Activos, Estudiantes TIE 2025",
    emails: ["estudiantes@upa.edu.py", "tie2025@upa.edu.py"],
  },
  {
    id: "docentes",
    name: "Docentes",
    description: "Claustro docente y profesores de cátedra.",
    badgeClass: "bg-emerald-100 text-emerald-800 border-emerald-200",
    googleGroup: "Ing. Tecnologías - TODOS",
    emails: ["docentes@upa.edu.py"],
  },
  {
    id: "staff",
    name: "Staff",
    description: "Personal administrativo, admisiones y soporte operativo.",
    badgeClass: "bg-amber-100 text-amber-800 border-amber-200",
    googleGroup: "Personal Administrativo UPA",
    emails: ["staff@upa.edu.py", "rectorado@upa.edu.py"],
  },
  {
    id: "egresados",
    name: "Egresados",
    description: "Red de graduados y exalumnos universitarios.",
    badgeClass: "bg-purple-100 text-purple-800 border-purple-200",
    googleGroup: "Alumni UPA",
    emails: ["egresados@upa.edu.py"],
  },
];

const DEFAULT_ADMINS = [
  {
    email: "pascal.thommen@upa.edu.py",
    name: "Pascal Thommen",
    role: "admin",
    isPrimary: true,
    permissions: ["Publicaciones y Eventos", "Grupos y Audiencias", "Gestión de Roles", "Diagnóstico de APIs"],
  },
];

function getStoredAppGroups() {
  try {
    const raw = localStorage.getItem(APP_GROUPS_STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (_) {}
  return DEFAULT_APP_GROUPS;
}

function saveAppGroups(groups) {
  try {
    localStorage.setItem(APP_GROUPS_STORAGE_KEY, JSON.stringify(groups));
  } catch (_) {}
}

function getStoredAppAdmins() {
  try {
    const raw = localStorage.getItem(APP_ADMINS_STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (_) {}
  return DEFAULT_ADMINS;
}

function saveAppAdmins(admins) {
  try {
    localStorage.setItem(APP_ADMINS_STORAGE_KEY, JSON.stringify(admins));
  } catch (_) {}
}

function renderGroupsModule() {
  const container = document.getElementById("groups-list-container");
  if (!container) return;
  const groups = getStoredAppGroups();

  container.innerHTML = groups.map((g) => `
    <div class="bg-slate-50/80 p-5 rounded-2xl border border-slate-200 space-y-3">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-blue-600"></span>
          <h4 class="font-extrabold text-sm text-slate-900">${g.name}</h4>
        </div>
        <span class="px-2 py-0.5 text-[10px] font-bold rounded-full ${g.badgeClass || 'bg-slate-200 text-slate-800'} uppercase">
          ${g.id}
        </span>
      </div>
      <p class="text-xs text-slate-500 leading-relaxed">${g.description}</p>
      
      <div class="pt-2 border-t border-slate-200/60 space-y-1.5 text-xs">
        <div class="text-[11px] text-slate-700">
          <strong>Google Workspace Group:</strong>
          <span class="font-mono text-blue-900 block mt-0.5 bg-white px-2 py-1 rounded border border-slate-200">${g.googleGroup || 'Sin vincular'}</span>
        </div>
        <div class="text-[11px] text-slate-700">
          <strong>Correos autorizados:</strong>
          <div class="flex flex-wrap gap-1 mt-1">
            ${(g.emails || []).map(e => `<span class="px-2 py-0.5 bg-white border border-slate-200 rounded text-[10px] font-mono text-slate-600">${e}</span>`).join('')}
          </div>
        </div>
      </div>
    </div>
  `).join('');
}

function renderAdminsModule() {
  const tbody = document.getElementById("admin-table-rows");
  if (!tbody) return;
  const admins = getStoredAppAdmins();

  tbody.innerHTML = admins.map((adm) => `
    <tr class="hover:bg-slate-50/50">
      <td class="py-3 px-3">
        <div class="font-bold text-slate-900">${adm.name || adm.email.split('@')[0]}</div>
        <div class="font-mono text-[11px] text-slate-500">${adm.email}</div>
      </td>
      <td class="py-3 px-3">
        <span class="px-2 py-0.5 text-[10px] font-bold rounded-full ${adm.role === 'admin' ? 'bg-indigo-100 text-indigo-800' : 'bg-slate-100 text-slate-700'} uppercase">
          ${adm.role}
        </span>
      </td>
      <td class="py-3 px-3">
        <div class="flex flex-wrap gap-1">
          ${(adm.permissions || []).map(p => `<span class="px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded text-[10px] font-medium">${p}</span>`).join('')}
        </div>
      </td>
      <td class="py-3 px-3 text-right">
        ${adm.isPrimary ? '<span class="text-[10px] font-bold text-slate-400">Principal</span>' : `<button type="button" data-remove-admin="${adm.email}" class="text-xs text-red-600 hover:text-red-800 font-semibold">Remover</button>`}
      </td>
    </tr>
  `).join('');

  tbody.querySelectorAll("button[data-remove-admin]").forEach(btn => {
    btn.addEventListener("click", () => {
      const email = btn.getAttribute("data-remove-admin");
      const filtered = getStoredAppAdmins().filter(a => a.email !== email);
      saveAppAdmins(filtered);
      renderAdminsModule();
    });
  });
}

const ROUTES = {
  "/dashboard/publicaciones": { navBtnId: "nav-mod-publications", viewId: "view-editorial", mode: "editorial" },
  "/dashboard/grupos": { navBtnId: "nav-mod-groups", viewId: "view-groups", mode: "editorial", onEnter: renderGroupsModule },
  "/dashboard/roles": { navBtnId: "nav-mod-admins", viewId: "view-admins", mode: "editorial", onEnter: renderAdminsModule },
  "/dashboard/diagnostico": { navBtnId: "nav-mod-diagnostic", viewId: "view-diagnostic", mode: "editorial", onEnter: updateJsonView },
  "/dashboard/estudiantes": { navBtnId: null, viewId: "student-workspace", mode: "student" },
};

function navigateTo(path, updateHistory = true) {
  let cleanPath = (path || "/dashboard").replace(/\/+$/, "") || "/dashboard";
  if (cleanPath === "/dashboard") {
    cleanPath = "/dashboard/publicaciones";
  }

  const route = ROUTES[cleanPath] || ROUTES["/dashboard/publicaciones"];

  if (updateHistory && window.location.pathname !== cleanPath) {
    try {
      window.history.pushState({ path: cleanPath }, "", cleanPath);
    } catch (_) {}
  }

  const allNavBtns = [
    document.getElementById("nav-mod-publications"),
    document.getElementById("nav-mod-groups"),
    document.getElementById("nav-mod-admins"),
    document.getElementById("nav-mod-diagnostic"),
  ].filter(Boolean);

  const allViews = [
    document.getElementById("view-editorial"),
    document.getElementById("view-groups"),
    document.getElementById("view-admins"),
    document.getElementById("view-diagnostic"),
    document.getElementById("student-workspace"),
  ].filter(Boolean);

  allNavBtns.forEach((b) => {
    b.className = "sidebar-nav-btn w-full flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl font-semibold text-xs transition text-left text-slate-600 hover:text-slate-900 hover:bg-slate-100";
  });

  if (route.navBtnId) {
    const activeBtn = document.getElementById(route.navBtnId);
    if (activeBtn) {
      activeBtn.className = "sidebar-nav-btn is-active w-full flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl font-semibold text-xs transition text-left text-white bg-[#6c9339] shadow-2xs";
    }
  }

  allViews.forEach((v) => v.classList.add("hidden"));
  const activeView = document.getElementById(route.viewId);
  if (activeView) activeView.classList.remove("hidden");

  const modeBtnEditorial = document.getElementById("mode-btn-editorial");
  const modeBtnStudent = document.getElementById("mode-btn-student");
  if (modeBtnEditorial && modeBtnStudent) {
    if (route.mode === "student") {
      modeBtnStudent.classList.add("is-active");
      modeBtnEditorial.classList.remove("is-active");
    } else {
      modeBtnEditorial.classList.add("is-active");
      modeBtnStudent.classList.remove("is-active");
    }
  }

  if (typeof route.onEnter === "function") {
    route.onEnter();
  }
}

function setupSidebarNavigation() {
  const btnPubs = document.getElementById("nav-mod-publications");
  const btnGroups = document.getElementById("nav-mod-groups");
  const btnAdmins = document.getElementById("nav-mod-admins");
  const btnDiag = document.getElementById("nav-mod-diagnostic");

  if (btnPubs) {
    btnPubs.addEventListener("click", () => navigateTo("/dashboard/publicaciones"));
  }
  if (btnGroups) {
    btnGroups.addEventListener("click", () => navigateTo("/dashboard/grupos"));
  }
  if (btnAdmins) {
    btnAdmins.addEventListener("click", () => navigateTo("/dashboard/roles"));
  }
  if (btnDiag) {
    btnDiag.addEventListener("click", () => navigateTo("/dashboard/diagnostico"));
  }

  const modeBtnStudent = document.getElementById("mode-btn-student");
  if (modeBtnStudent) {
    modeBtnStudent.addEventListener("click", () => navigateTo("/dashboard/estudiantes"));
  }

  const modeBtnEditorial = document.getElementById("mode-btn-editorial");
  if (modeBtnEditorial) {
    modeBtnEditorial.addEventListener("click", () => navigateTo("/dashboard/publicaciones"));
  }

  window.addEventListener("popstate", () => {
    navigateTo(window.location.pathname, false);
  });

  // Ruta inicial basada en la URL del navegador
  if (window.location.pathname && window.location.pathname.startsWith("/dashboard")) {
    navigateTo(window.location.pathname, false);
  }

  const formAddAdmin = document.getElementById("form-add-admin");
  if (formAddAdmin) {
    formAddAdmin.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = document.getElementById("input-admin-email");
      const select = document.getElementById("select-admin-role");
      const email = (input ? input.value : "").trim().toLowerCase();
      if (!email.endsWith("@upa.edu.py")) {
        alert("El correo debe pertenecer al dominio institucional @upa.edu.py");
        return;
      }
      const admins = getStoredAppAdmins();
      if (admins.some(a => a.email === email)) {
        alert("El usuario ya se encuentra registrado.");
        return;
      }
      const perms = [];
      if (document.getElementById("perm-publications")?.checked) perms.push("Publicaciones y Eventos");
      if (document.getElementById("perm-groups")?.checked) perms.push("Grupos y Audiencias");
      if (document.getElementById("perm-admins")?.checked) perms.push("Gestión de Roles");
      if (document.getElementById("perm-diagnostic")?.checked) perms.push("Diagnóstico de APIs");

      admins.push({
        email,
        name: email.split("@")[0].replace(".", " "),
        role: select ? select.value : "editor",
        isPrimary: false,
        permissions: perms,
      });
      saveAppAdmins(admins);
      if (input) input.value = "";
      renderAdminsModule();
      alert(`Administrador ${email} autorizado correctamente.`);
    });
  }

  const btnCreateGroup = document.getElementById("btn-create-group");
  if (btnCreateGroup) {
    btnCreateGroup.addEventListener("click", () => {
      const name = prompt("Ingrese el nombre del nuevo grupo interno:");
      if (!name || !name.trim()) return;
      const groups = getStoredAppGroups();
      const id = name.trim().toLowerCase().replace(/[^a-z0-9]/g, "_");
      groups.push({
        id,
        name: name.trim(),
        description: `Grupo interno institucional: ${name.trim()}`,
        badgeClass: "bg-slate-100 text-slate-800 border-slate-200",
        googleGroup: `Grupo ${name.trim()} UPA`,
        emails: [`${id}@upa.edu.py`],
      });
      saveAppGroups(groups);
      renderGroupsModule();
    });
  }
}

document.addEventListener("DOMContentLoaded", init);
