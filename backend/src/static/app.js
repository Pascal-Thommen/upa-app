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
  btnConnectClassroom: document.getElementById("btn-connect-classroom"),
  btnOpenClassroomModal: document.getElementById("btn-open-classroom-modal"),
  modalClassroom: document.getElementById("modal-classroom"),
  modalBtnConnectGoogle: document.getElementById("modal-btn-connect-google"),
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

function showLoginView() {
  document.documentElement.classList.remove("has-auth");
  DOM_ELEMENTS.viewLogin.classList.remove("hidden");
  DOM_ELEMENTS.viewDashboard.classList.add("hidden");
  DOM_ELEMENTS.authActions.innerHTML = "";
}

function showDashboardView(user) {
  DOM_ELEMENTS.viewLogin.classList.add("hidden");
  DOM_ELEMENTS.viewDashboard.classList.remove("hidden");

  DOM_ELEMENTS.authActions.innerHTML = `
    <span class="text-xs text-slate-300 hidden sm:inline font-mono truncate max-w-xs">${user.email}</span>
    <button id="btn-logout" class="px-3 py-1 text-xs font-medium bg-red-600 hover:bg-red-700 text-white rounded-md shadow transition">
      Salir
    </button>
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
  DOM_ELEMENTS.userRoleBadge.textContent = role === "ADMIN" ? "ADMINISTRADOR" : "ESTUDIANTE";

  // Estado de Classroom
  const hasClassroom = Boolean(user.has_classroom_token);
  if (hasClassroom) {
    DOM_ELEMENTS.userClassroomSyncBadge.textContent = "• Classroom: Activo";
    DOM_ELEMENTS.userClassroomSyncBadge.className = "text-emerald-600 font-semibold";
    DOM_ELEMENTS.classroomPermissionAlert.classList.add("hidden");
  } else {
    DOM_ELEMENTS.userClassroomSyncBadge.textContent = "• Classroom: Sin vincular (Clic para conectar)";
    DOM_ELEMENTS.userClassroomSyncBadge.className = "text-blue-700 hover:text-blue-900 font-semibold cursor-pointer underline";
    DOM_ELEMENTS.classroomPermissionAlert.classList.remove("hidden");
  }

  // 2. Regla de Privacidad de Google Mailgruppen:
  // Estrictamente visible solo para pascal.thommen@upa.edu.py
  const isExclusiveUser = (user.email || "").toLowerCase() === "pascal.thommen@upa.edu.py";
  const groups = Array.isArray(user.groups) ? user.groups : [];

  if (isExclusiveUser && groups.length > 0) {
    DOM_ELEMENTS.tileMailgroups.classList.remove("hidden");
    DOM_ELEMENTS.groupsCount.textContent = `${groups.length} grupos`;
    DOM_ELEMENTS.userGroupsContainer.innerHTML = groups
      .map((grp) => {
        const label = GROUP_LABELS[grp] || grp;
        return `
          <span class="group-badge group-badge-all" title="${label}">
            <span>${grp}</span>
            <span class="ml-1 text-[10px] opacity-75 font-normal">&bull; ${label}</span>
          </span>
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
      DOM_ELEMENTS.deadlinesCount.textContent = "Error";
      return;
    }

    const data = await res.json();
    state.deadlines = Array.isArray(data) ? data : data.deadlines || [];
    DOM_ELEMENTS.deadlinesCount.textContent = `${state.deadlines.length} tareas`;

    renderCalendar();
    renderDeadlinesList(state.deadlines);
  } catch (error) {
    console.error("Fallo al obtener plazos:", error);
    DOM_ELEMENTS.deadlinesCount.textContent = "Error";
  }
}

/**
 * Renderiza el calendario mensual interactivo.
 */
function renderCalendar() {
  const grid = DOM_ELEMENTS.calendarGrid;
  const monthNames = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
  ];

  DOM_ELEMENTS.calMonthTitle.textContent = `${monthNames[state.currentMonth]} ${state.currentYear}`;

  // Encabezados de días
  const dayHeaders = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"];
  let html = dayHeaders.map((dh) => `<div class="cal-day-header">${dh}</div>`).join("");

  const firstDayIndex = (new Date(state.currentYear, state.currentMonth, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(state.currentYear, state.currentMonth + 1, 0).getDate();

  // Días vacíos previos
  for (let i = 0; i < firstDayIndex; i++) {
    html += `<div class="cal-day is-empty"></div>`;
  }

  // Mapear deadlines por día en formato YYYY-MM-DD
  const deadlineDaysMap = {};
  state.deadlines.forEach((d) => {
    const formatted = d.due_date_formatted || "";
    const dateKey = formatted.split(" ")[0];
    if (dateKey) {
      deadlineDaysMap[dateKey] = (deadlineDaysMap[dateKey] || 0) + 1;
    }
  });

  // Días del mes
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

  // Añadir listener para seleccionar fecha
  grid.querySelectorAll(".cal-day[data-date]").forEach((el) => {
    el.addEventListener("click", () => {
      const selected = el.getAttribute("data-date");
      if (state.selectedDate === selected) {
        state.selectedDate = null;
        DOM_ELEMENTS.selectedDateLabel.textContent = "Próximas Entregas";
        renderDeadlinesList(state.deadlines);
      } else {
        state.selectedDate = selected;
        DOM_ELEMENTS.selectedDateLabel.textContent = `Entregas del ${selected}`;
        const filtered = state.deadlines.filter((d) => (d.due_date_formatted || "").startsWith(selected));
        renderDeadlinesList(filtered);
      }
      renderCalendar();
    });
  });
}

/**
 * Renderiza la lista de tareas y deadlines.
 */
function renderDeadlinesList(items) {
  const container = DOM_ELEMENTS.deadlinesContainer;

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="p-4 text-center text-slate-400 text-xs border border-dashed border-slate-200 rounded-lg">
        No hay entregas pendientes para esta fecha.
      </div>
    `;
    return;
  }

  container.innerHTML = items
    .map((d) => {
      const link = d.alternate_link || `https://classroom.google.com`;
      const dateStr = d.due_date_formatted || "Sin fecha";
      return `
        <div class="deadline-card is-normal flex flex-col justify-between gap-1.5">
          <div>
            <div class="flex items-center justify-between">
              <span class="text-[10px] font-bold text-blue-800 uppercase truncate">${d.course || "Classroom"}</span>
              ${d.max_points ? `<span class="text-[10px] font-semibold text-slate-500">${d.max_points} pts</span>` : ""}
            </div>
            <h4 class="font-bold text-xs text-slate-900 mt-0.5">${d.title}</h4>
          </div>
          <div class="flex items-center justify-between pt-1 border-t border-slate-100 text-[11px]">
            <span class="text-amber-700 font-medium">📅 ${dateStr}</span>
            <a href="${link}" target="_blank" rel="noopener noreferrer" class="btn-classroom-link">
              <span>Ver Tarea</span>
              <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
            </a>
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
      if (!authData.user || !authData.user.has_classroom_token) {
        setTimeout(() => {
          if (DOM_ELEMENTS.modalClassroom) {
            DOM_ELEMENTS.modalClassroom.classList.remove("hidden");
          }
        }, 600);
      }
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

const GOOGLE_CLIENT_ID = "567912225771-7cf17vkfujmhb4itu2lri0ttssavfmcg.apps.googleusercontent.com";
const CLASSROOM_SCOPES = [
  "https://www.googleapis.com/auth/classroom.courses.readonly",
  "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
].join(" ");

let tokenClient = null;

/**
 * Inicia el flujo oficial de consentimiento Google OAuth 2.0 para Classroom.
 * Solicita acceso a asignaturas y tareas sin requerir copiar tokens manualmente.
 */
function connectGoogleClassroom() {
  if (typeof google === "undefined" || !google.accounts || !google.accounts.oauth2) {
    alert("El servicio de Google Identity Services se está cargando. Por favor intente en unos segundos.");
    return;
  }

  try {
    if (!tokenClient) {
      tokenClient = google.accounts.oauth2.initTokenClient({
        client_id: GOOGLE_CLIENT_ID,
        scope: CLASSROOM_SCOPES,
        hint: state.currentUser ? state.currentUser.email : "",
        callback: async (tokenResponse) => {
          if (tokenResponse.error) {
            console.error("Google Classroom Consent Error:", tokenResponse);
            alert("No se concedió autorización para Google Classroom: " + (tokenResponse.error_description || tokenResponse.error));
            return;
          }
          if (tokenResponse.access_token) {
            try {
              const res = await apiRequest("/api/auth/classroom-token", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ classroom_token: tokenResponse.access_token }),
              });
              if (res.ok) {
                if (DOM_ELEMENTS.modalClassroom) {
                  DOM_ELEMENTS.modalClassroom.classList.add("hidden");
                }
                await refreshDashboard();
              } else {
                alert("Error al registrar el token de Classroom en el servidor.");
              }
            } catch (err) {
              console.error("Error al registrar classroom token:", err);
              alert("Error de conexión al guardar el token.");
            }
          }
        },
      });
    }

    tokenClient.requestAccessToken({ prompt: "consent" });
  } catch (err) {
    console.error("Error al solicitar acceso a Google Classroom:", err);
    alert("No se pudo iniciar el flujo de consentimiento de Google Classroom.");
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

async function init() {
  DOM_ELEMENTS.formLogin.addEventListener("submit", handleLoginSubmit);
  DOM_ELEMENTS.btnRefresh.addEventListener("click", refreshDashboard);

  if (DOM_ELEMENTS.btnConnectClassroom) {
    DOM_ELEMENTS.btnConnectClassroom.addEventListener("click", connectGoogleClassroom);
  }
  if (DOM_ELEMENTS.modalBtnConnectGoogle) {
    DOM_ELEMENTS.modalBtnConnectGoogle.addEventListener("click", connectGoogleClassroom);
  }
  if (DOM_ELEMENTS.userClassroomSyncBadge) {
    DOM_ELEMENTS.userClassroomSyncBadge.addEventListener("click", () => {
      if (!state.currentUser || !state.currentUser.has_classroom_token) {
        connectGoogleClassroom();
      }
    });
  }

  DOM_ELEMENTS.calPrev.addEventListener("click", () => {
    state.currentMonth--;
    if (state.currentMonth < 0) {
      state.currentMonth = 11;
      state.currentYear--;
    }
    renderCalendar();
  });

  DOM_ELEMENTS.calNext.addEventListener("click", () => {
    state.currentMonth++;
    if (state.currentMonth > 11) {
      state.currentMonth = 0;
      state.currentYear++;
    }
    renderCalendar();
  });

  DOM_ELEMENTS.btnOpenClassroomModal.addEventListener("click", () => {
    DOM_ELEMENTS.modalClassroom.classList.remove("hidden");
    DOM_ELEMENTS.modalInputClassroomToken.focus();
  });

  DOM_ELEMENTS.btnCloseClassroomModal.addEventListener("click", () => {
    DOM_ELEMENTS.modalClassroom.classList.add("hidden");
  });

  DOM_ELEMENTS.btnCancelClassroom.addEventListener("click", () => {
    DOM_ELEMENTS.modalClassroom.classList.add("hidden");
  });

  DOM_ELEMENTS.formClassroomToken.addEventListener("submit", handleClassroomTokenSubmit);

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

  checkHealth();

  // Verarbeitet Rückleitung aus dem Google OAuth 2.0 Web Redirect Flow
  const urlParams = new URLSearchParams(window.location.search);
  const tokenFromUrl = urlParams.get("token");
  const authError = urlParams.get("auth_error");

  if (tokenFromUrl) {
    setStoredToken(tokenFromUrl);
    window.history.replaceState({}, document.title, window.location.pathname);
    DOM_ELEMENTS.viewLogin.classList.add("hidden");
    DOM_ELEMENTS.viewDashboard.classList.remove("hidden");
    await refreshDashboard();
    return;
  }

  if (authError) {
    showLoginAlert("Error de autenticación Google: " + authError, "error");
  }

  const existingToken = getStoredToken();
  if (existingToken) {
    DOM_ELEMENTS.viewLogin.classList.add("hidden");
    DOM_ELEMENTS.viewDashboard.classList.remove("hidden");
    await refreshDashboard();
  } else {
    showLoginView();
  }
}

document.addEventListener("DOMContentLoaded", init);
