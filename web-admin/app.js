/**
 * Portal Institucional UPA (web-admin)
 * Logica de cliente para autenticacion, perfil institucional y sincronizacion con Google Classroom.
 * Cumple estrictamente con la doctrina Zero-Mock (llamadas reales a la API REST).
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
  systemStatusText: document.getElementById("system-status-text"),
  systemStatusIndicator: document.getElementById("system-status-indicator"),
  userFullName: document.getElementById("user-full-name"),
  userEmail: document.getElementById("user-email"),
  userRoleBadge: document.getElementById("user-role-badge"),
  userGroupsContainer: document.getElementById("user-groups-container"),
  groupsCount: document.getElementById("groups-count"),
  userClassroomStatus: document.getElementById("user-classroom-status"),
  coursesContainer: document.getElementById("courses-container"),
  coursesCount: document.getElementById("courses-count"),
  deadlinesContainer: document.getElementById("deadlines-container"),
  deadlinesCount: document.getElementById("deadlines-count"),
  classroomPermissionAlert: document.getElementById("classroom-permission-alert"),
  classroomAlertTitle: document.getElementById("classroom-alert-title"),
  classroomAlertDesc: document.getElementById("classroom-alert-desc"),
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

/**
 * Obtiene el token de autenticacion guardado en el almacenamiento local.
 */
function getStoredToken() {
  return localStorage.getItem(STORAGE_KEY);
}

/**
 * Guarda el token de acceso en el almacenamiento local.
 */
function setStoredToken(token) {
  if (token) {
    localStorage.setItem(STORAGE_KEY, token);
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

/**
 * Elimina la sesion actual y muestra la vista de autenticacion.
 */
function logout() {
  setStoredToken(null);
  showLoginView();
  showLoginAlert("Sesión finalizada correctamente.", "info");
}

/**
 * Muestra alertas en el formulario de inicio de sesion.
 */
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

/**
 * Muestra la vista de inicio de sesion y oculta el panel principal.
 */
function showLoginView() {
  DOM_ELEMENTS.viewLogin.classList.remove("hidden");
  DOM_ELEMENTS.viewDashboard.classList.add("hidden");
  DOM_ELEMENTS.authActions.innerHTML = "";
}

/**
 * Muestra el panel principal y oculta la vista de autenticacion.
 */
function showDashboardView(user) {
  DOM_ELEMENTS.viewLogin.classList.add("hidden");
  DOM_ELEMENTS.viewDashboard.classList.remove("hidden");

  DOM_ELEMENTS.authActions.innerHTML = `
    <span class="text-xs text-slate-300 hidden sm:inline font-mono truncate max-w-xs">${user.email}</span>
    <button id="btn-logout" class="px-3 py-1.5 text-xs font-medium bg-red-600 hover:bg-red-700 text-white rounded-lg shadow transition">
      Cerrar Sesión
    </button>
  `;

  document.getElementById("btn-logout").addEventListener("click", logout);
}

/**
 * Ejecuta una peticion autenticada hacia la API REST del backend.
 */
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

/**
 * Comprueba el estado de salud y conectividad del backend.
 */
async function checkHealth() {
  try {
    const res = await fetch("/health");
    if (res.ok) {
      const data = await res.json();
      DOM_ELEMENTS.systemStatusText.textContent = "Backend Conectado";
      DOM_ELEMENTS.diagBackend.textContent = data.service || "Activo";
      DOM_ELEMENTS.diagEnv.textContent = data.environment || "Producción";
    } else {
      DOM_ELEMENTS.systemStatusText.textContent = "Servicio Inestable";
      DOM_ELEMENTS.diagBackend.textContent = `Error HTTP ${res.status}`;
    }
  } catch (err) {
    DOM_ELEMENTS.systemStatusText.textContent = "Sin Conexión API";
    DOM_ELEMENTS.diagBackend.textContent = "Desconectado";
  }
}

/**
 * Carga el perfil del usuario autenticado y sus grupos de correo institucional.
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
    renderUserProfile(user);
    showDashboardView(user);
    return user;
  } catch (error) {
    console.error("Fallo al cargar perfil:", error);
    showLoginView();
    showLoginAlert("No fue posible validar la sesión con el servidor.", "error");
    return null;
  }
}

/**
 * Dibuja los datos del usuario y sus grupos de correo en el panel institucional.
 */
function renderUserProfile(user) {
  DOM_ELEMENTS.userFullName.textContent = user.full_name || "Usuario UPA";
  DOM_ELEMENTS.userEmail.textContent = user.email || "";

  const role = (user.role || "user").toUpperCase();
  DOM_ELEMENTS.userRoleBadge.textContent = role === "ADMIN" ? "ADMINISTRADOR" : "ESTUDIANTE";

  const groups = Array.isArray(user.groups) ? user.groups : ["ALL"];
  DOM_ELEMENTS.groupsCount.textContent = `${groups.length} grupo${groups.length === 1 ? "" : "s"}`;

  DOM_ELEMENTS.userGroupsContainer.innerHTML = groups
    .map((grp) => {
      const label = GROUP_LABELS[grp] || grp;
      const badgeClass = `group-badge group-badge-${grp.toLowerCase()}` in {}
        ? `group-badge-${grp.toLowerCase()}`
        : "group-badge-default";

      return `
        <span class="group-badge ${badgeClass}" title="${label}">
          <span>${grp}</span>
          <span class="ml-1 text-[10px] opacity-75 font-normal">&bull; ${label}</span>
        </span>
      `;
    })
    .join("");

  // Estado del token de Classroom
  const hasClassroom = Boolean(user.has_classroom_token);
  if (hasClassroom) {
    DOM_ELEMENTS.userClassroomStatus.textContent = "Vinculado Activo";
    DOM_ELEMENTS.userClassroomStatus.className = "font-semibold text-emerald-600";
    DOM_ELEMENTS.classroomPermissionAlert.classList.add("hidden");
  } else {
    DOM_ELEMENTS.userClassroomStatus.textContent = "Pendiente de Vinculación";
    DOM_ELEMENTS.userClassroomStatus.className = "font-semibold text-amber-600";
    DOM_ELEMENTS.classroomPermissionAlert.classList.remove("hidden");
    DOM_ELEMENTS.classroomAlertTitle.textContent = "Permisos de Google Classroom requeridos";
    DOM_ELEMENTS.classroomAlertDesc.textContent = "No se detectaron credenciales de Classroom. Ingrese su token para visualizar asignaturas y entregas.";
  }
}

/**
 * Carga los cursos activos de Google Classroom.
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
    const statusHeader = res.headers.get("X-Classroom-Status");

    if (res.status === 401) {
      logout();
      return;
    }

    if (!res.ok) {
      container.innerHTML = `
        <div class="p-4 rounded-lg bg-red-50 border border-red-100 text-red-700 text-xs">
          No se pudieron sincronizar los cursos activos (Código ${res.status}).
        </div>
      `;
      DOM_ELEMENTS.coursesCount.textContent = "Error";
      return;
    }

    const courses = await res.json();
    DOM_ELEMENTS.coursesCount.textContent = `${courses.length} curso${courses.length === 1 ? "" : "s"}`;

    if (!Array.isArray(courses) || courses.length === 0) {
      if (statusHeader === "missing_token" || statusHeader === "permission_denied") {
        container.innerHTML = `
          <div class="p-4 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs">
            <p class="font-semibold mb-1">Permisos no concedidos</p>
            <p>La cuenta no cuenta con permisos activos para consultar Google Classroom. Conecte su token de acceso.</p>
          </div>
        `;
      } else {
        container.innerHTML = `
          <div class="p-6 text-center text-slate-400 text-xs border border-dashed border-slate-200 rounded-lg">
            No se encontraron cursos activos registrados en Google Classroom para este semestre.
          </div>
        `;
      }
      return;
    }

    container.innerHTML = courses
      .map((c) => {
        const link = c.alternate_link || `https://classroom.google.com/c/${c.id}`;
        return `
          <div class="course-card flex flex-col justify-between gap-2">
            <div>
              <h4 class="font-bold text-sm text-slate-900">${c.name}</h4>
              <p class="text-xs text-slate-500">${c.section || "Sin sección especificada"} ${c.room ? `&bull; Aula: ${c.room}` : ""}</p>
            </div>
            <div class="flex items-center justify-between pt-2 border-t border-slate-100 text-xs">
              <span class="text-[10px] text-slate-400 font-mono">ID: ${c.id}</span>
              <a href="${link}" target="_blank" rel="noopener noreferrer" class="btn-classroom-link">
                <span>Abrir Curso</span>
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>
                </svg>
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
        Error de red al consultar Google Classroom. Compruebe la conectividad del servidor.
      </div>
    `;
    DOM_ELEMENTS.coursesCount.textContent = "Error";
  }
}

/**
 * Carga las tareas y fechas limite pendientes de Google Classroom.
 */
async function loadClassroomDeadlines() {
  const container = DOM_ELEMENTS.deadlinesContainer;
  container.innerHTML = `
    <div class="flex items-center justify-center p-6 text-slate-400 gap-2">
      <div class="spinner"></div>
      <span class="text-xs">Consultando tareas y fechas límite...</span>
    </div>
  `;

  try {
    const res = await apiRequest("/api/classroom/deadlines");
    const statusHeader = res.headers.get("X-Classroom-Status");

    if (res.status === 401) {
      logout();
      return;
    }

    if (!res.ok) {
      container.innerHTML = `
        <div class="p-4 rounded-lg bg-red-50 border border-red-100 text-red-700 text-xs">
          No se pudieron cargar los plazos de Classroom (Código ${res.status}).
        </div>
      `;
      DOM_ELEMENTS.deadlinesCount.textContent = "Error";
      return;
    }

    const data = await res.json();
    const deadlines = Array.isArray(data) ? data : data.deadlines || [];
    DOM_ELEMENTS.deadlinesCount.textContent = `${deadlines.length} tarea${deadlines.length === 1 ? "" : "s"}`;

    if (deadlines.length === 0) {
      if (statusHeader === "missing_token" || statusHeader === "permission_denied") {
        container.innerHTML = `
          <div class="p-4 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs">
            <p class="font-semibold mb-1">Permisos no configurados</p>
            <p>Se requiere autorización de Classroom para sincronizar las tareas pendientes.</p>
          </div>
        `;
      } else {
        container.innerHTML = `
          <div class="p-6 text-center text-slate-400 text-xs border border-dashed border-slate-200 rounded-lg">
            🎉 ¡Al día! No hay tareas ni entregas pendientes registradas en Google Classroom.
          </div>
        `;
      }
      return;
    }

    container.innerHTML = deadlines
      .map((d) => {
        const link = d.alternate_link || `https://classroom.google.com`;
        const dateStr = d.due_date_formatted || (d.due_date ? JSON.stringify(d.due_date) : "Sin fecha límite");
        const maxPointsStr = d.max_points ? `${d.max_points} pts` : "";

        return `
          <div class="deadline-card is-normal flex flex-col justify-between gap-2">
            <div>
              <div class="flex items-center justify-between gap-2">
                <span class="text-[11px] font-semibold text-blue-800 uppercase tracking-wide truncate">${d.course || "Google Classroom"}</span>
                ${maxPointsStr ? `<span class="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">${maxPointsStr}</span>` : ""}
              </div>
              <h4 class="font-bold text-sm text-slate-900 mt-1">${d.title}</h4>
              ${d.description ? `<p class="text-xs text-slate-500 mt-0.5 line-clamp-2">${d.description}</p>` : ""}
            </div>

            <div class="flex items-center justify-between pt-2 border-t border-slate-100 text-xs">
              <div class="flex items-center gap-1.5 text-slate-600 font-medium">
                <svg class="w-3.5 h-3.5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <span>${dateStr}</span>
              </div>
              <a href="${link}" target="_blank" rel="noopener noreferrer" class="btn-classroom-link">
                <span>Ver Tarea</span>
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>
                </svg>
              </a>
            </div>
          </div>
        `;
      })
      .join("");
  } catch (error) {
    console.error("Fallo al obtener deadlines:", error);
    container.innerHTML = `
      <div class="p-4 rounded-lg bg-red-50 text-red-700 text-xs">
        Error al consultar las fechas límite de entrega en el servidor.
      </div>
    `;
    DOM_ELEMENTS.deadlinesCount.textContent = "Error";
  }
}

/**
 * Actualiza toda la informacion del dashboard de forma reactiva.
 */
async function refreshDashboard() {
  await checkHealth();
  const user = await loadUserProfile();
  if (user) {
    await Promise.all([loadClassroomCourses(), loadClassroomDeadlines()]);
  }
}

/**
 * Maneja el envio del formulario de inicio de sesion.
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

  // Determinar si es un Google ID Token (largo JWT de Google) o un JWT directo de la aplicacion
  // Se intenta validar contra POST /api/auth/google si es ID Token, o directamente GET /api/auth/me
  try {
    // 1. Probar login via POST /api/auth/google
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

    // 2. Si falla con 403 (Dominio no permitido), reportar inmediatamente
    if (googleLoginResp.status === 403) {
      const err = await googleLoginResp.json();
      showLoginAlert(err.detail || "Acceso restringido únicamente a correos @upa.edu.py", "error");
      return;
    }

    // 3. Probar como Session JWT directo contra GET /api/auth/me
    setStoredToken(token);
    const testMeResp = await apiRequest("/api/auth/me");
    if (testMeResp.ok) {
      // Si se proporciono token de Classroom, vincularlo
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

/**
 * Maneja la vinculacion de token de Google Classroom desde el modal.
 */
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

/**
 * Inicializacion de eventos y arranque de la aplicacion.
 */
function init() {
  DOM_ELEMENTS.formLogin.addEventListener("submit", handleLoginSubmit);
  DOM_ELEMENTS.btnRefresh.addEventListener("click", refreshDashboard);

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

  // Inicializar estado de salud
  checkHealth();

  // Si hay token almacenado, intentar cargar dashboard inmediatamente
  const existingToken = getStoredToken();
  if (existingToken) {
    refreshDashboard();
  } else {
    showLoginView();
  }
}

// Iniciar al cargar el DOM
document.addEventListener("DOMContentLoaded", init);
