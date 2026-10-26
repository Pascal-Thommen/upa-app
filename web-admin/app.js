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
  const profileContainer = document.getElementById("user-profile-container");
  if (profileContainer) profileContainer.classList.add("hidden");
  const dropdown = document.getElementById("user-profile-dropdown");
  if (dropdown) dropdown.classList.add("hidden");
}

function showDashboardView(user) {
  document.documentElement.classList.add("has-auth");
  DOM_ELEMENTS.viewLogin.classList.add("hidden");
  DOM_ELEMENTS.viewDashboard.classList.remove("hidden");

  const email = (user && user.email) || "";
  const name = (user && user.full_name) || (email ? email.split("@")[0].replace(".", " ") : "Usuario");
  const initials = email ? email.substring(0, 2).toUpperCase() : "U";

  const profileContainer = document.getElementById("user-profile-container");
  if (profileContainer) {
    profileContainer.classList.remove("hidden");
  }
  const displayEmail = document.getElementById("user-display-email");
  if (displayEmail) displayEmail.textContent = email;
  const displayName = document.getElementById("user-display-name");
  if (displayName) displayName.textContent = name;
  const userAvatar = document.getElementById("user-avatar");
  if (userAvatar) userAvatar.textContent = initials;
  const dropdownAvatar = document.getElementById("dropdown-avatar");
  if (dropdownAvatar) dropdownAvatar.textContent = initials;

  const btnLogout = document.getElementById("btn-logout");
  if (btnLogout && !btnLogout.dataset.bound) {
    btnLogout.dataset.bound = "true";
    btnLogout.addEventListener("click", logout);
  }
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
  const email = user.email || "";
  const name = user.full_name || email.split("@")[0];
  DOM_ELEMENTS.userFullName.textContent = name;
  DOM_ELEMENTS.userEmail.textContent = email;

  const initials = (user.full_name || email)
    .split(" ")
    .map((n) => n[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  DOM_ELEMENTS.userAvatar.textContent = initials || "U";
  const dropdownAvatar = document.getElementById("dropdown-avatar");
  if (dropdownAvatar) dropdownAvatar.textContent = initials || "U";
  const displayName = document.getElementById("user-display-name");
  if (displayName) displayName.textContent = name;
  const displayEmail = document.getElementById("user-display-email");
  if (displayEmail) displayEmail.textContent = email;

  const appPreviewName = document.getElementById("app-preview-user-name");
  if (appPreviewName) appPreviewName.textContent = name;
  const appPreviewEmail = document.getElementById("app-preview-user-email");
  if (appPreviewEmail) appPreviewEmail.textContent = email;

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
    if (window.UpaRouter && typeof window.UpaRouter.reapplyCurrentRoute === "function") {
      window.UpaRouter.reapplyCurrentRoute();
    }
    await Promise.all([loadClassroomCourses(), loadClassroomDeadlines(), loadCampusFeed()]);
    updateJsonView();
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

async function updateJsonView() {
  const rawJsonOutput = document.getElementById("raw-json-output");
  if (!rawJsonOutput) return;
  rawJsonOutput.textContent = "Consultando telemetría del sistema en tiempo real...";
  try {
    const res = await apiRequest("/api/system/diagnostics");
    if (res.ok) {
      const diagData = await res.json();
      const combined = {
        diagnostico_sistema_postgresql: diagData,
        contexto_aplicacion_movil: getAppJsonData(),
      };
      rawJsonOutput.textContent = JSON.stringify(combined, null, 2);

      // Actualizar tarjetas informativas de telemetría
      const dbUsers = document.getElementById("telemetry-db-users");
      if (dbUsers && diagData.database) {
        dbUsers.textContent = diagData.database.total_users ?? 0;
        const dbDetail = document.getElementById("telemetry-db-detail");
        if (dbDetail) {
          dbDetail.textContent = `${diagData.database.dialect || 'PostgreSQL'} • ${diagData.database.total_groups || 0} grupos • ${diagData.database.total_posts || 0} publicaciones`;
        }
      }
      const dirGroups = document.getElementById("telemetry-dir-groups");
      if (dirGroups && diagData.directory_sync) {
        dirGroups.textContent = diagData.directory_sync.cached_groups_count ?? (diagData.database ? diagData.database.total_groups : 0);
      }
      const crCourses = document.getElementById("telemetry-classroom-courses");
      if (crCourses && diagData.classroom_api) {
        crCourses.textContent = state.courses ? state.courses.length : 0;
      }
      const srvBadge = document.getElementById("telemetry-server-badge");
      if (srvBadge && diagData.application) {
        srvBadge.textContent = diagData.application.zero_mock_certified ? "100% Zero-Mock" : "Activo";
      }
      return;
    }
  } catch (err) {
    console.error("Error consultando diagnósticos:", err);
  }
  const data = getAppJsonData();
  rawJsonOutput.textContent = JSON.stringify(data, null, 2);
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

let appGroupsCache = [];
let appAdminsCache = [];

async function fetchAppGroups() {
  try {
    const res = await apiRequest("/api/groups");
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data)) {
        appGroupsCache = data;
        if (window.UPAEditorialCore && Array.isArray(window.UPAEditorialCore.TARGET_GROUPS)) {
          appGroupsCache.forEach((g) => {
            if (!window.UPAEditorialCore.TARGET_GROUPS.some((tg) => tg.value === g.id.toUpperCase() || tg.value === g.id)) {
              window.UPAEditorialCore.TARGET_GROUPS.push({ value: g.id.toUpperCase(), label: g.name });
            }
          });
        }
        return appGroupsCache;
      }
    }
  } catch (err) {
    console.error("Error cargando grupos desde PostgreSQL:", err);
  }
  return appGroupsCache;
}

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
    console.error("Error cargando roles desde PostgreSQL:", err);
  }
  return appAdminsCache;
}

function openEditGroupModal(group) {
  const modal = document.getElementById("modal-edit-group");
  if (!modal) return;
  const inputId = document.getElementById("edit-group-id");
  const labelId = document.getElementById("modal-group-id-label");
  const inputName = document.getElementById("edit-group-name");
  const inputDesc = document.getElementById("edit-group-description");
  const inputGoogle = document.getElementById("edit-group-google");
  const inputEmails = document.getElementById("edit-group-emails");

  if (inputId) inputId.value = group.id;
  if (labelId) labelId.textContent = `ID: ${group.id}`;
  if (inputName) inputName.value = group.name || "";
  if (inputDesc) inputDesc.value = group.description || "";
  if (inputGoogle) inputGoogle.value = group.google_group || "";
  if (inputEmails) inputEmails.value = (group.emails || []).join(", ");

  modal.classList.remove("hidden");
}

function closeEditGroupModal() {
  const modal = document.getElementById("modal-edit-group");
  if (modal) modal.classList.add("hidden");
}

async function renderGroupsModule() {
  const tbody = document.getElementById("groups-table-rows");
  const fallbackContainer = document.getElementById("groups-list-container");
  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-xs text-slate-500 font-medium">Cargando grupos institucionales desde base de datos...</td></tr>`;
  }
  const groups = await fetchAppGroups();

  if (!Array.isArray(groups) || groups.length === 0) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-xs text-slate-400">No hay grupos institucionales registrados.</td></tr>`;
    if (fallbackContainer) fallbackContainer.innerHTML = `<div class="col-span-full p-6 text-center text-xs text-slate-400">No hay grupos.</div>`;
    return;
  }

  if (tbody) {
    tbody.innerHTML = groups.map((g) => `
      <tr class="hover:bg-slate-50/70 transition" data-group-row="${g.id}">
        <td class="py-3 px-3.5">
          <span class="px-2 py-0.5 text-[10px] font-bold rounded-full ${g.badge_class || 'bg-slate-100 text-slate-800 border border-slate-200'} uppercase font-mono">
            ${g.id}
          </span>
        </td>
        <td class="py-3 px-3.5">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full ${g.is_system ? 'bg-[#6c9339]' : 'bg-blue-600'}"></span>
            <span class="font-bold text-slate-900">${g.name}</span>
          </div>
        </td>
        <td class="py-3 px-3.5 text-slate-600 max-w-xs truncate" title="${g.description || ''}">
          ${g.description || '<span class="text-slate-400 italic">Sin descripción</span>'}
        </td>
        <td class="py-3 px-3.5">
          ${g.google_group ? `<span class="px-2 py-0.5 bg-slate-100 text-blue-900 font-mono text-[10px] rounded border border-slate-200">${g.google_group}</span>` : '<span class="text-slate-400 italic">Sin vincular</span>'}
        </td>
        <td class="py-3 px-3.5">
          <div class="flex flex-wrap gap-1 max-w-xs">
            ${(g.emails || []).map(e => `<span class="px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded text-[10px] font-mono border border-slate-200">${e}</span>`).join('')}
          </div>
        </td>
        <td class="py-3 px-3.5 text-right whitespace-nowrap">
          <div class="flex items-center justify-end gap-1.5">
            <button type="button" data-edit-group="${g.id}" class="px-2.5 py-1 text-xs font-semibold text-[#6c9339] hover:bg-[#6c9339]/10 rounded-lg transition cursor-pointer">
              Editar
            </button>
            ${!g.is_system ? `<button type="button" data-delete-group="${g.id}" title="Eliminar grupo" class="px-2.5 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 rounded-lg transition cursor-pointer">Eliminar</button>` : '<span class="text-[10px] font-bold text-slate-300 uppercase px-1">Sistema</span>'}
          </div>
        </td>
      </tr>
    `).join('');

    tbody.querySelectorAll("button[data-edit-group]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-edit-group");
        const group = groups.find((grp) => grp.id === id);
        if (group) openEditGroupModal(group);
      });
    });

    tbody.querySelectorAll("button[data-delete-group]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-delete-group");
        if (!confirm(`¿Desea eliminar el grupo '${id}' permanentemente?`)) return;
        try {
          const res = await apiRequest(`/api/groups/${encodeURIComponent(id)}`, { method: "DELETE" });
          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            alert(err.detail || "Error al eliminar el grupo.");
            return;
          }
          await renderGroupsModule();
        } catch (e) {
          alert("Error de conexión al eliminar grupo.");
        }
      });
    });
  }
}

async function renderAdminsModule() {
  const tbody = document.getElementById("admin-table-rows");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="7" class="p-6 text-center text-xs text-slate-400">Cargando administradores desde PostgreSQL...</td></tr>`;
  const admins = await fetchAppAdmins();

  if (!Array.isArray(admins) || admins.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="p-6 text-center text-xs text-slate-400">No hay administradores registrados.</td></tr>`;
    return;
  }

  const PERM_KEYS = [
    { key: "Publicaciones y Eventos", label: "Publicaciones" },
    { key: "Grupos y Audiencias", label: "Grupos" },
    { key: "Gestión de Roles", label: "Roles" },
    { key: "Diagnóstico de APIs", label: "Diagnóstico" },
  ];

  tbody.innerHTML = admins.map((adm) => {
    const isPrimary = adm.is_primary || (adm.email || "").toLowerCase() === "pascal.thommen@upa.edu.py";
    const permCells = PERM_KEYS.map((p) => {
      const checked = (adm.permissions || []).includes(p.key) || isPrimary;
      const disabled = isPrimary ? "disabled" : "";
      return `
        <td class="py-3 px-2 text-center">
          <input type="checkbox"
                 data-perm-email="${adm.email}"
                 data-perm-key="${p.key}"
                 ${checked ? "checked" : ""}
                 ${disabled}
                 title="${p.label} para ${adm.email}"
                 class="w-4 h-4 rounded text-[#6c9339] focus:ring-[#6c9339] cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed">
        </td>
      `;
    }).join('');

    return `
      <tr class="hover:bg-slate-50/60 transition" data-role-row="${adm.email}">
        <td class="py-3 px-3.5">
          <div class="font-bold text-slate-900">${adm.name || adm.email.split('@')[0]}</div>
          <div class="font-mono text-[11px] text-slate-500">${adm.email}</div>
        </td>
        <td class="py-3 px-3.5">
          <span class="px-2 py-0.5 text-[10px] font-bold rounded-full ${adm.role === 'admin' ? 'bg-indigo-100 text-indigo-800' : 'bg-slate-100 text-slate-700'} uppercase">
            ${adm.role}
          </span>
        </td>
        ${permCells}
        <td class="py-3 px-3.5 text-right whitespace-nowrap">
          ${isPrimary
            ? '<span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Protegido</span>'
            : `<button type="button"
                       data-remove-admin="${adm.email}"
                       title="Revocar rol y permisos"
                       class="p-1.5 text-red-600 hover:text-white hover:bg-red-600 rounded-lg border border-red-200 transition cursor-pointer inline-flex items-center justify-center">
                 <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
               </button>`
          }
        </td>
      </tr>
    `;
  }).join('');

  // Checkboxes directos con actualización inmediata en PostgreSQL
  tbody.querySelectorAll("input[data-perm-email]").forEach((chk) => {
    chk.addEventListener("change", async () => {
      const email = chk.getAttribute("data-perm-email");
      const row = chk.closest("tr");
      const activePerms = [];
      row.querySelectorAll("input[data-perm-email]").forEach((c) => {
        if (c.checked) activePerms.push(c.getAttribute("data-perm-key"));
      });
      try {
        const res = await apiRequest(`/api/roles/${encodeURIComponent(email)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ permissions: activePerms }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          alert(err.detail || "Error al actualizar permisos.");
          await renderAdminsModule();
          return;
        }
      } catch (e) {
        alert("Error de conexión al actualizar permisos.");
        await renderAdminsModule();
      }
    });
  });

  // Papelera de revocación
  tbody.querySelectorAll("button[data-remove-admin]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const email = btn.getAttribute("data-remove-admin");
      if (!confirm(`¿Desea revocar definitivamente la autorización para ${email}?`)) return;
      try {
        const res = await apiRequest(`/api/roles/${encodeURIComponent(email)}`, { method: "DELETE" });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          alert(err.detail || "Error al revocar rol.");
          return;
        }
        await renderAdminsModule();
      } catch (e) {
        alert("Error de conexión al revocar rol.");
      }
    });
  });
}

// ===========================================================================
// Enrutamiento URL Dedicado por Modulo (History API, Deep Linking y F5)
// ===========================================================================

const ROUTE_CONFIG = {
  publicaciones: {
    path: "/dashboard/publicaciones",
    btnId: "nav-mod-publications",
    viewId: "view-editorial",
  },
  grupos: {
    path: "/dashboard/grupos",
    btnId: "nav-mod-groups",
    viewId: "view-groups",
  },
  roles: {
    path: "/dashboard/roles",
    btnId: "nav-mod-admins",
    viewId: "view-admins",
  },
  diagnostico: {
    path: "/dashboard/diagnostico",
    btnId: "nav-mod-diagnostic",
    viewId: "view-diagnostic",
  },
  estudiantes: {
    path: "/dashboard/estudiantes",
    btnId: "nav-mod-students",
    viewId: "student-workspace",
  },
  app: {
    path: "/dashboard/app",
    btnId: "nav-mod-app",
    viewId: "view-app",
  },
};

let currentActiveRoute = "publicaciones";

function resolveRoute(rawPath) {
  if (!rawPath) {
    return { name: "publicaciones", path: "/dashboard/publicaciones", isRedirect: true };
  }
  let path = String(rawPath).split("?")[0].split("#")[0].replace(/\/+$/, "");
  if (!path) path = "/dashboard";
  const lower = path.toLowerCase();

  if (lower === "/dashboard/publicaciones" || lower === "/dashboard/noticias" || lower === "/dashboard/eventos") {
    return { name: "publicaciones", path: "/dashboard/publicaciones", isRedirect: lower !== "/dashboard/publicaciones" };
  }
  if (lower === "/dashboard/grupos" || lower === "/dashboard/groups") {
    return { name: "grupos", path: "/dashboard/grupos", isRedirect: lower !== "/dashboard/grupos" };
  }
  if (lower === "/dashboard/roles" || lower === "/dashboard/admins") {
    return { name: "roles", path: "/dashboard/roles", isRedirect: lower !== "/dashboard/roles" };
  }
  if (lower === "/dashboard/diagnostico" || lower === "/dashboard/diagnostic") {
    return { name: "diagnostico", path: "/dashboard/diagnostico", isRedirect: lower !== "/dashboard/diagnostico" };
  }
  if (lower === "/dashboard/estudiantes" || lower === "/dashboard/students") {
    return { name: "estudiantes", path: "/dashboard/estudiantes", isRedirect: lower !== "/dashboard/estudiantes" };
  }
  if (lower === "/dashboard/app" || lower === "/dashboard/mobile" || lower === "/dashboard/aplicacion") {
    return { name: "app", path: "/dashboard/app", isRedirect: lower !== "/dashboard/app" };
  }

  // Cualquier ruta no reconocida redirige a /dashboard/publicaciones
  return { name: "publicaciones", path: "/dashboard/publicaciones", isRedirect: true };
}

function syncNavClasses(routeName) {
  const config = ROUTE_CONFIG[routeName] || ROUTE_CONFIG.publicaciones;
  const allBtns = Object.values(ROUTE_CONFIG)
    .map(c => document.getElementById(c.btnId))
    .filter(Boolean);

  allBtns.forEach(btn => {
    btn.className = "sidebar-nav-btn w-full flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl font-semibold text-xs transition text-left text-slate-600 hover:text-slate-900 hover:bg-slate-100";
  });

  const activeBtn = document.getElementById(config.btnId);
  if (activeBtn) {
    activeBtn.className = "sidebar-nav-btn is-active w-full flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl font-semibold text-xs transition text-left text-white bg-[#6c9339] shadow-2xs";
  }
}

function applyRoute(routeName, options = {}) {
  const config = ROUTE_CONFIG[routeName] || ROUTE_CONFIG.publicaciones;
  const canonicalPath = config.path;
  const shouldUpdateUrl = options.updateUrl !== false;

  if (shouldUpdateUrl && typeof window !== "undefined" && window.history) {
    const currentPath = (window.location.pathname || "").replace(/\/+$/, "") || "/dashboard";
    if (options.replace || options.isRedirect || currentPath !== canonicalPath) {
      if (options.push && !options.replace && !options.isRedirect) {
        window.history.pushState({ route: routeName }, "", canonicalPath);
      } else {
        window.history.replaceState({ route: routeName }, "", canonicalPath);
      }
    }
  }

  currentActiveRoute = routeName;
  try {
    localStorage.setItem("upa_active_route", routeName);
  } catch (_) {}

  syncNavClasses(routeName);

  const allViews = Object.values(ROUTE_CONFIG)
    .map(c => document.getElementById(c.viewId))
    .filter(Boolean);
  allViews.forEach(v => v.classList.add("hidden"));

  const activeView = document.getElementById(config.viewId);
  if (activeView) {
    activeView.classList.remove("hidden");
  }

  const edBtn = document.getElementById("mode-btn-editorial");
  const stBtn = document.getElementById("mode-btn-student");

  if (routeName === "publicaciones") {
    if (edBtn) edBtn.classList.add("is-active");
    if (stBtn) stBtn.classList.remove("is-active");
    if (window.UpaCockpit && typeof window.UpaCockpit.loadPanelData === "function") {
      window.UpaCockpit.loadPanelData();
    }
  } else if (routeName === "estudiantes") {
    if (stBtn) stBtn.classList.add("is-active");
    if (edBtn) edBtn.classList.remove("is-active");
  } else if (routeName === "grupos") {
    if (edBtn) edBtn.classList.remove("is-active");
    if (stBtn) stBtn.classList.remove("is-active");
    renderGroupsModule();
  } else if (routeName === "roles") {
    if (edBtn) edBtn.classList.remove("is-active");
    if (stBtn) stBtn.classList.remove("is-active");
    renderAdminsModule();
  } else if (routeName === "diagnostico") {
    if (edBtn) edBtn.classList.remove("is-active");
    if (stBtn) stBtn.classList.remove("is-active");
    updateJsonView();
  } else if (routeName === "app") {
    if (edBtn) edBtn.classList.remove("is-active");
    if (stBtn) stBtn.classList.remove("is-active");
    if (state.currentUser) {
      const u = state.currentUser;
      const previewName = document.getElementById("app-preview-user-name");
      if (previewName) previewName.textContent = u.full_name || u.email.split("@")[0];
      const previewEmail = document.getElementById("app-preview-user-email");
      if (previewEmail) previewEmail.textContent = u.email || "";
    }
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
    DIAGNOSTICO: "/dashboard/diagnostico",
    ESTUDIANTES: "/dashboard/estudiantes",
    APP: "/dashboard/app",
  },
  resolveRoute,
  applyRoute,
  navigate,
  syncNavClasses,
  getCurrentRoute() {
    return currentActiveRoute;
  },
  reapplyCurrentRoute() {
    applyRoute(currentActiveRoute, { updateUrl: false });
  },
  init() {
    const initialResolved = resolveRoute(typeof window !== "undefined" ? window.location.pathname : "/dashboard/publicaciones");
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

function setupSidebarNavigation() {
  const btnPubs = document.getElementById("nav-mod-publications");
  const btnGroups = document.getElementById("nav-mod-groups");
  const btnAdmins = document.getElementById("nav-mod-admins");
  const btnDiag = document.getElementById("nav-mod-diagnostic");
  const btnStudents = document.getElementById("nav-mod-students");
  const btnApp = document.getElementById("nav-mod-app");
  const headerLogoLink = document.getElementById("header-logo-link");

  if (btnPubs) {
    btnPubs.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.PUBLICACIONES));
  }
  if (btnGroups) {
    btnGroups.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.GRUPOS));
  }
  if (btnAdmins) {
    btnAdmins.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.ROLES));
  }
  if (btnDiag) {
    btnDiag.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.DIAGNOSTICO));
  }
  if (btnStudents) {
    btnStudents.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.ESTUDIANTES));
  }
  if (btnApp) {
    btnApp.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.APP));
  }
  if (headerLogoLink) {
    headerLogoLink.addEventListener("click", (e) => {
      e.preventDefault();
      UpaRouter.navigate(UpaRouter.ROUTES.PUBLICACIONES);
    });
  }

  const modeBtnStudent = document.getElementById("mode-btn-student");
  if (modeBtnStudent) {
    modeBtnStudent.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.ESTUDIANTES));
  }

  const modeBtnEditorial = document.getElementById("mode-btn-editorial");
  if (modeBtnEditorial) {
    modeBtnEditorial.addEventListener("click", () => UpaRouter.navigate(UpaRouter.ROUTES.PUBLICACIONES));
  }

  // Interacción del Menú Desplegable de Perfil en el Encabezado
  const btnProfileToggle = document.getElementById("btn-profile-toggle");
  const profileDropdown = document.getElementById("user-profile-dropdown");
  if (btnProfileToggle && profileDropdown) {
    btnProfileToggle.addEventListener("click", (e) => {
      e.stopPropagation();
      profileDropdown.classList.toggle("hidden");
      btnProfileToggle.setAttribute("aria-expanded", !profileDropdown.classList.contains("hidden"));
    });
  }

  document.addEventListener("click", (e) => {
    const profileContainer = document.getElementById("user-profile-container");
    const dropdown = document.getElementById("user-profile-dropdown");
    if (dropdown && !dropdown.classList.contains("hidden")) {
      if (!profileContainer || !profileContainer.contains(e.target)) {
        dropdown.classList.add("hidden");
        const toggle = document.getElementById("btn-profile-toggle");
        if (toggle) toggle.setAttribute("aria-expanded", "false");
      }
    }
  });

  const btnOpenClassroomDropdown = document.getElementById("btn-open-classroom-dropdown");
  if (btnOpenClassroomDropdown) {
    btnOpenClassroomDropdown.addEventListener("click", () => {
      const dropdown = document.getElementById("user-profile-dropdown");
      if (dropdown) dropdown.classList.add("hidden");
      if (DOM_ELEMENTS.modalClassroom) DOM_ELEMENTS.modalClassroom.classList.remove("hidden");
    });
  }

  UpaRouter.init();

  const formAddAdmin = document.getElementById("form-add-admin");
  if (formAddAdmin) {
    formAddAdmin.addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = document.getElementById("input-admin-email");
      const select = document.getElementById("select-admin-role");
      const email = (input ? input.value : "").trim().toLowerCase();
      if (!email.endsWith("@upa.edu.py")) {
        alert("El correo debe pertenecer al dominio institucional @upa.edu.py");
        return;
      }
      const perms = [
        "Publicaciones y Eventos",
        "Grupos y Audiencias",
        "Gestión de Roles",
        "Diagnóstico de APIs",
      ];
      try {
        const res = await apiRequest("/api/roles", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email,
            name: email.split("@")[0].replace(".", " ").replace(/\b\w/g, l => l.toUpperCase()),
            role: select ? select.value : "editor",
            permissions: perms,
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          alert(err.detail || "Error al autorizar administrador.");
          return;
        }
        if (input) input.value = "";
        await renderAdminsModule();
        alert(`Administrador ${email} autorizado correctamente en PostgreSQL.`);
      } catch (err) {
        alert("Error de conexión al autorizar administrador.");
      }
    });
  }

  const btnCreateGroup = document.getElementById("btn-create-group");
  if (btnCreateGroup) {
    btnCreateGroup.addEventListener("click", async () => {
      const name = prompt("Ingrese el nombre del nuevo grupo institucional:");
      if (!name || !name.trim()) return;
      const desc = prompt("Descripción breve del grupo (opcional):") || "";
      const googleGrp = prompt("Nombre de Google Workspace Group vinculado (opcional):") || "";

      try {
        const res = await apiRequest("/api/groups", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name.trim(),
            description: desc.trim() || undefined,
            google_group: googleGrp.trim() || undefined,
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          alert(err.detail || "Error creando grupo.");
          return;
        }
        await renderGroupsModule();
        alert(`Grupo '${name.trim()}' creado exitosamente en PostgreSQL.`);
      } catch (err) {
        alert("Error de conexión al crear grupo.");
      }
    });
  }

  const formEditGroup = document.getElementById("form-edit-group");
  if (formEditGroup) {
    formEditGroup.addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = document.getElementById("edit-group-id").value;
      const name = document.getElementById("edit-group-name").value.trim();
      const description = document.getElementById("edit-group-description").value.trim();
      const googleGroup = document.getElementById("edit-group-google").value.trim();
      const emailsRaw = document.getElementById("edit-group-emails").value;
      const emails = emailsRaw.split(",").map(em => em.trim()).filter(Boolean);

      try {
        const res = await apiRequest(`/api/groups/${encodeURIComponent(id)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            description: description || undefined,
            google_group: googleGroup || undefined,
            emails: emails.length > 0 ? emails : undefined,
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          alert(err.detail || "Error al actualizar el grupo.");
          return;
        }
        closeEditGroupModal();
        await renderGroupsModule();
        alert(`Grupo '${id}' actualizado con éxito en PostgreSQL.`);
      } catch (err) {
        alert("Error de conexión al guardar grupo.");
      }
    });
  }

  const btnCloseGrp = document.getElementById("btn-close-group-modal");
  if (btnCloseGrp) btnCloseGrp.addEventListener("click", closeEditGroupModal);
  const btnCancelGrp = document.getElementById("btn-cancel-group");
  if (btnCancelGrp) btnCancelGrp.addEventListener("click", closeEditGroupModal);
}

document.addEventListener("DOMContentLoaded", init);
