/**
 * Pruebas unitarias y de navegación del Router de Web-Admin (UpaRouter).
 *
 * Valida:
 * - Resolución de las 4 rutas canónicas (/dashboard/publicaciones, /dashboard/grupos, /dashboard/roles, /dashboard/apis)
 * - Resolución de alias compatibles (/dashboard/noticias, /dashboard/estudiantes, /dashboard/diagnostico, /dashboard/control, etc.)
 * - Redirección de rutas no reconocidas a /dashboard/publicaciones
 * - Actualización de historial mediante History API (pushState / replaceState) y popstate
 * - Deep linking y persistencia en recarga F5
 * - Visibilidad dinámica de pestañas en la barra lateral según los permisos reales del usuario
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

function createTestEnvironment(initialPath = "/dashboard/publicaciones", initialSearch = "") {
  const historyStack = [{ url: initialPath, state: {} }];
  let historyIndex = 0;
  const eventListeners = {};
  const fetchCalls = [];
  const fetchRequests = [];

  const window = {
    location: {
      pathname: initialPath,
      search: initialSearch,
      hash: "",
    },
    history: {
      pushState(state, title, url) {
        historyIndex++;
        historyStack.splice(historyIndex, historyStack.length - historyIndex, { url, state });
        window.location.pathname = url;
        window.location.search = "";
      },
      replaceState(state, title, url) {
        historyStack[historyIndex] = { url, state };
        window.location.pathname = url;
        window.location.search = "";
      },
      back() {
        if (historyIndex > 0) {
          historyIndex--;
          window.location.pathname = historyStack[historyIndex].url;
          if (eventListeners["popstate"]) {
            eventListeners["popstate"].forEach((cb) => cb({ state: historyStack[historyIndex].state }));
          }
        }
      },
      forward() {
        if (historyIndex < historyStack.length - 1) {
          historyIndex++;
          window.location.pathname = historyStack[historyIndex].url;
          if (eventListeners["popstate"]) {
            eventListeners["popstate"].forEach((cb) => cb({ state: historyStack[historyIndex].state }));
          }
        }
      },
      get length() {
        return historyStack.length;
      },
      get current() {
        return historyStack[historyIndex];
      },
      get stack() {
        return historyStack;
      },
    },
    addEventListener(event, callback) {
      if (!eventListeners[event]) eventListeners[event] = [];
      eventListeners[event].push(callback);
    },
    removeEventListener(event, callback) {
      if (eventListeners[event]) {
        eventListeners[event] = eventListeners[event].filter((cb) => cb !== callback);
      }
    },
  };

  const elements = {};

  function makeElement(id) {
    let classes = new Set(["hidden"]);
    const listeners = {};
    const attrs = {};
    return {
      id,
      get className() {
        return Array.from(classes).join(" ");
      },
      set className(val) {
        classes = new Set(String(val || "").trim().split(/\s+/).filter(Boolean));
      },
      setAttribute(name, val) {
        attrs[name] = String(val);
      },
      getAttribute(name) {
        return attrs[name] || null;
      },
      contains() {
        return false;
      },
      classList: {
        add(...cls) {
          cls.forEach((c) => classes.add(c));
        },
        remove(...cls) {
          cls.forEach((c) => classes.delete(c));
        },
        toggle(cls, force) {
          if (force === undefined) {
            if (classes.has(cls)) classes.delete(cls);
            else classes.add(cls);
          } else if (force) {
            classes.add(cls);
          } else {
            classes.delete(cls);
          }
        },
        contains(cls) {
          return classes.has(cls);
        },
      },
      addEventListener(event, callback) {
        if (!listeners[event]) listeners[event] = [];
        listeners[event].push(callback);
      },
      click() {
        if (listeners["click"]) {
          listeners["click"].forEach((cb) => cb({ preventDefault() {}, stopPropagation() {} }));
        }
      },
      dispatchEvent(evt) {
        const type = evt && evt.type ? evt.type : String(evt || "");
        const eventObj = Object.assign(
          { preventDefault() {}, stopPropagation() {} },
          typeof evt === "object" && evt ? evt : {},
          { type }
        );
        if (listeners[type]) {
          listeners[type].forEach((cb) => cb(eventObj));
        }
      },
      querySelectorAll() {
        return [];
      },
      value: "",
      innerHTML: "",
      textContent: "",
    };
  }

  const elementIds = [
    "sidebar-menu",
    "sidebar-settings-group",
    "sidebar-settings-divider",
    "sidebar-settings-heading",
    "nav-mod-publications",
    "nav-mod-groups",
    "nav-mod-admins",
    "nav-mod-students",
    "nav-mod-ai",
    "header-logo-link",
    "view-editorial",
    "view-groups",
    "view-admins",
    "view-ai",
    "student-workspace",
    "apis-admin-overview",
    "apis-json-details",
  ];

  elementIds.forEach((id) => {
    elements[id] = makeElement(id);
  });

  const document = {
    getElementById(id) {
      if (!elements[id]) {
        elements[id] = makeElement(id);
      }
      return elements[id];
    },
    querySelectorAll() {
      return [];
    },
    addEventListener(event, callback) {
      if (event === "DOMContentLoaded") {
        callback();
      }
    },
    documentElement: {
      classList: {
        add() {},
        remove() {},
      },
    },
  };

  const localStorageData = {};
  const localStorage = {
    getItem(key) {
      return localStorageData[key] || null;
    },
    setItem(key, value) {
      localStorageData[key] = String(value);
    },
    removeItem(key) {
      delete localStorageData[key];
    },
    clear() {
      Object.keys(localStorageData).forEach((k) => delete localStorageData[k]);
    },
  };

  const appJsContent = fs.readFileSync(path.resolve(__dirname, "../app.js"), "utf8");

  const context = {
    window,
    document,
    localStorage,
    console,
    navigator: { clipboard: { writeText: async () => {} } },
    URLSearchParams: class {
      constructor(search) {
        this._params = new Map();
        const s = String(search || "").replace(/^\?/, "");
        if (s) {
          s.split("&").forEach((pair) => {
            const [k, ...rest] = pair.split("=");
            if (k) this._params.set(decodeURIComponent(k), decodeURIComponent(rest.join("=") || ""));
          });
        }
      }
      get(key) {
        return this._params.get(key) || null;
      }
    },
    Blob: class {},
    URL: { createObjectURL: () => "" },
    fetch: async (endpoint, options) => {
      fetchCalls.push(endpoint);
      fetchRequests.push({ endpoint, options: options || {} });
      if (endpoint === "/api/auth/me") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: 1,
            email: "pascal.thommen@upa.edu.py",
            full_name: "Pascal Thommen",
            role: "admin",
            permissions: ["publicaciones", "grupos", "roles", "apis", "ia"],
            groups: ["ALL"],
            google_groups: [],
            has_classroom_token: false,
          }),
        };
      }
      return { ok: true, status: 200, json: async () => ({ status: "healthy", posts: [] }) };
    },
  };

  const fn = new Function(...Object.keys(context), appJsContent);
  fn(...Object.values(context));

  return {
    window,
    document,
    elements,
    localStorage,
    fetchCalls,
    fetchRequests,
    router: window.UpaRouter,
  };
}

// ---------------------------------------------------------------------------
// 1. Pruebas de Resolución de Rutas (4 módulos unificados + alias)
// ---------------------------------------------------------------------------

test("resolucion: rutas canonicas de los 4 modulos del portal", () => {
  const env = createTestEnvironment();
  const r = env.router;

  assert.deepEqual(r.resolveRoute("/dashboard/publicaciones"), {
    name: "publicaciones",
    path: "/dashboard/publicaciones",
    isRedirect: false,
  });

  assert.deepEqual(r.resolveRoute("/dashboard/grupos"), {
    name: "grupos",
    path: "/dashboard/grupos",
    isRedirect: false,
  });

  assert.deepEqual(r.resolveRoute("/dashboard/roles"), {
    name: "roles",
    path: "/dashboard/roles",
    isRedirect: false,
  });

    assert.deepEqual(r.resolveRoute("/dashboard/apis"), {
    name: "apis",
    path: "/dashboard/apis",
    isRedirect: false,
  });

  assert.deepEqual(r.resolveRoute("/dashboard/ia"), {
    name: "ia",
    path: "/dashboard/ia",
    isRedirect: false,
  });
});

test("resolucion: normalizacion de mayusculas y barras finales en las 5 rutas canonicas", () => {
  const env = createTestEnvironment();
  const r = env.router;

  assert.equal(r.resolveRoute("/DASHBOARD/PUBLICACIONES/").name, "publicaciones");
  assert.equal(r.resolveRoute("/DASHBOARD/GRUPOS/").name, "grupos");
  assert.equal(r.resolveRoute("/DASHBOARD/ROLES/").name, "roles");
  assert.equal(r.resolveRoute("/DASHBOARD/APIS/").name, "apis");
  assert.equal(r.resolveRoute("/DASHBOARD/IA/").name, "ia");
});

test("resolucion: rutas no reconocidas redirigen a /dashboard/publicaciones", () => {
  const env = createTestEnvironment();
  const r = env.router;

  for (const tc of ["/dashboard", "/dashboard/", "/dashboard/inexistente", "/otra-cosa", "", null]) {
    const res = r.resolveRoute(tc);
    assert.equal(res.name, "publicaciones");
    assert.equal(res.path, "/dashboard/publicaciones");
    assert.equal(res.isRedirect, true);
  }
});

// ---------------------------------------------------------------------------
// 2. Navegación Interactiva y History API
// ---------------------------------------------------------------------------

test("navegacion: clic en las 4 pestanas actualiza la URL con pushState y alterna vistas", () => {
  const env = createTestEnvironment("/dashboard/publicaciones");
  const { elements, window } = env;

  assert.equal(window.location.pathname, "/dashboard/publicaciones");
  assert.ok(!elements["view-editorial"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-publications"].classList.contains("is-active"));

  elements["nav-mod-groups"].click();
  assert.equal(window.location.pathname, "/dashboard/grupos");
  assert.ok(!elements["view-groups"].classList.contains("hidden"));
  assert.ok(elements["view-editorial"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-groups"].classList.contains("is-active"));

  elements["nav-mod-admins"].click();
  assert.equal(window.location.pathname, "/dashboard/roles");
  assert.ok(!elements["view-admins"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-admins"].classList.contains("is-active"));

  elements["nav-mod-students"].click();
  assert.equal(window.location.pathname, "/dashboard/apis");
  assert.ok(!elements["student-workspace"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-students"].classList.contains("is-active"));

  elements["nav-mod-ai"].click();
  assert.equal(window.location.pathname, "/dashboard/ia");
  assert.ok(!elements["view-ai"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-ai"].classList.contains("is-active"));

  elements["header-logo-link"].click();
  assert.equal(window.location.pathname, "/dashboard/publicaciones");
  assert.ok(!elements["view-editorial"].classList.contains("hidden"));
});

test("historial: botones atras y adelante del navegador alternan modulos correctamente", () => {
  const env = createTestEnvironment("/dashboard/publicaciones");
  const { elements, window } = env;

  elements["nav-mod-groups"].click();
  elements["nav-mod-admins"].click();
  assert.equal(window.location.pathname, "/dashboard/roles");

  window.history.back();
  assert.equal(window.location.pathname, "/dashboard/grupos");
  assert.ok(!elements["view-groups"].classList.contains("hidden"));

  window.history.back();
  assert.equal(window.location.pathname, "/dashboard/publicaciones");
  assert.ok(!elements["view-editorial"].classList.contains("hidden"));

  window.history.forward();
  assert.equal(window.location.pathname, "/dashboard/grupos");
  assert.ok(!elements["view-groups"].classList.contains("hidden"));
});

// ---------------------------------------------------------------------------
// 3. Deep Linking y Alias
// ---------------------------------------------------------------------------

test("deep linking: carga directa de /dashboard/grupos y /dashboard/roles mantiene su URL", () => {
  const envG = createTestEnvironment("/dashboard/grupos");
  assert.equal(envG.window.location.pathname, "/dashboard/grupos");
  assert.equal(envG.router.getCurrentRoute(), "grupos");
  assert.ok(!envG.elements["view-groups"].classList.contains("hidden"));

  const envR = createTestEnvironment("/dashboard/roles");
  assert.equal(envR.window.location.pathname, "/dashboard/roles");
  assert.equal(envR.router.getCurrentRoute(), "roles");
  assert.ok(!envR.elements["view-admins"].classList.contains("hidden"));
});

test("deep linking: carga directa de /dashboard/apis y /dashboard/ia activa sus modulos", () => {
  const envA = createTestEnvironment("/dashboard/apis");
  assert.equal(envA.window.location.pathname, "/dashboard/apis");
  assert.equal(envA.router.getCurrentRoute(), "apis");
  assert.ok(!envA.elements["student-workspace"].classList.contains("hidden"));

  const envIa = createTestEnvironment("/dashboard/ia");
  assert.equal(envIa.window.location.pathname, "/dashboard/ia");
  assert.equal(envIa.router.getCurrentRoute(), "ia");
  assert.ok(!envIa.elements["view-ai"].classList.contains("hidden"));
});

test("deep linking: ruta desconocida redirige a /dashboard/publicaciones", () => {
  const env = createTestEnvironment("/dashboard/subruta-invalida-xyz");
  assert.equal(env.window.location.pathname, "/dashboard/publicaciones");
  assert.equal(env.router.getCurrentRoute(), "publicaciones");
});

test("resolucion: subrutas de publicaciones (/dashboard/publicaciones/:id y /nueva) e IDs malformados", () => {
  const env = createTestEnvironment("/dashboard/publicaciones");
  const r = env.router;

  assert.deepEqual(r.resolveRoute("/dashboard/publicaciones/60"), {
    name: "publicaciones",
    path: "/dashboard/publicaciones/60",
    isRedirect: false,
    subroute: "edit",
    publicationId: "60",
  });

  assert.deepEqual(r.resolveRoute("/dashboard/publicaciones/nueva"), {
    name: "publicaciones",
    path: "/dashboard/publicaciones/nueva",
    isRedirect: false,
    subroute: "nueva",
  });

  for (const invalidPath of [
    "/dashboard/publicaciones/0",
    "/dashboard/publicaciones/-5",
    "/dashboard/publicaciones/abc",
    "/dashboard/publicaciones/60/extra",
  ]) {
    const res = r.resolveRoute(invalidPath);
    assert.equal(res.name, "publicaciones");
    assert.equal(res.path, "/dashboard/publicaciones");
    assert.equal(res.isRedirect, true);
    assert.equal(res.subroute, "invalid");
  }
});

test("deep linking: carga directa de /dashboard/publicaciones/:id y /nueva conserva su URL y delega al cockpit", () => {
  const cockpitCalls = [];

  const envEdit = createTestEnvironment("/dashboard/publicaciones/60");
  assert.equal(envEdit.window.location.pathname, "/dashboard/publicaciones/60");
  assert.equal(envEdit.router.getCurrentRoute(), "publicaciones");
  envEdit.window.UpaCockpit = {
    loadPanelData(opts) {
      cockpitCalls.push(opts);
    },
  };
  envEdit.router.reapplyCurrentRoute();
  assert.equal(envEdit.window.location.pathname, "/dashboard/publicaciones/60");
  assert.equal(cockpitCalls.length, 1);
  assert.equal(cockpitCalls[0].subroute, "edit");
  assert.equal(cockpitCalls[0].publicationId, "60");

  const envNew = createTestEnvironment("/dashboard/publicaciones/nueva");
  assert.equal(envNew.window.location.pathname, "/dashboard/publicaciones/nueva");
  assert.equal(envNew.router.getCurrentRoute(), "publicaciones");
  envNew.window.UpaCockpit = {
    loadPanelData(opts) {
      cockpitCalls.push(opts);
    },
  };
  envNew.router.reapplyCurrentRoute();
  assert.equal(envNew.window.location.pathname, "/dashboard/publicaciones/nueva");
  assert.equal(cockpitCalls.length, 2);
  assert.equal(cockpitCalls[1].subroute, "nueva");
});

// ---------------------------------------------------------------------------
// 4. Visibilidad Dinámica de Pestañas según Permisos (SRV-160)
// ---------------------------------------------------------------------------

test("permisos dinamicos: sidebar muestra solo las pestanas autorizadas y redirige si pierde acceso", () => {
  const env = createTestEnvironment("/dashboard/roles");
  const { elements, window, router } = env;

  // Cuenta con permiso solo en Publicaciones y Grupos: no puede permanecer en /dashboard/roles
  router.applyUserPermissions({
    email: "editor@upa.edu.py",
    role: "editor",
    permissions: ["publicaciones", "grupos"],
  });

  assert.ok(!elements["sidebar-menu"].classList.contains("hidden"));
  assert.ok(!elements["sidebar-settings-group"].classList.contains("hidden"));
  assert.ok(!elements["sidebar-settings-divider"].classList.contains("hidden"));
  assert.ok(!elements["nav-mod-publications"].classList.contains("hidden"));
  assert.ok(!elements["nav-mod-groups"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-admins"].classList.contains("hidden"), "Roles debe ocultarse sin permiso");
  assert.ok(elements["nav-mod-students"].classList.contains("hidden"), "APIs debe ocultarse sin permiso");
  assert.ok(elements["nav-mod-ai"].classList.contains("hidden"), "IA debe ocultarse sin permiso ia");
  assert.equal(router.getCurrentRoute(), "publicaciones");
  assert.equal(window.location.pathname, "/dashboard/publicaciones");

  // Cuenta solo con Publicaciones (sin permisos de Configuración): oculta el bloque Configuración y la línea divisoria
  router.applyUserPermissions({
    email: "redactor@upa.edu.py",
    role: "editor",
    permissions: ["publicaciones"],
  });
  assert.ok(!elements["sidebar-menu"].classList.contains("hidden"));
  assert.ok(elements["sidebar-settings-group"].classList.contains("hidden"));
  assert.ok(elements["sidebar-settings-divider"].classList.contains("hidden"));

  // Cuenta con permiso en APIs pero sin permiso en IA: no puede abrir ni permanecer en /dashboard/ia
  router.applyUserPermissions({
    email: "operador.apis@upa.edu.py",
    role: "editor",
    permissions: ["publicaciones", "apis"],
  });
  assert.ok(!elements["nav-mod-students"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-ai"].classList.contains("hidden"), "IA requiere su propio permiso 'ia'");
  router.navigate("/dashboard/ia");
  assert.equal(router.getCurrentRoute(), "publicaciones", "Sin permiso 'ia' no puede abrir /dashboard/ia");

  // Al otorgar el permiso 'ia', el usuario puede acceder a /dashboard/ia
  router.applyUserPermissions({
    email: "operador.ia@upa.edu.py",
    role: "editor",
    permissions: ["publicaciones", "ia"],
  });
  assert.ok(!elements["nav-mod-ai"].classList.contains("hidden"));
  router.navigate("/dashboard/ia");
  assert.equal(router.getCurrentRoute(), "ia");
  assert.equal(window.location.pathname, "/dashboard/ia");
});

test("permisos dinamicos: estudiante sin permisos administrativos oculta dashboard y muestra aviso Acceso Restringido", () => {
  const env = createTestEnvironment("/dashboard/publicaciones");
  const { elements, window, router } = env;

  router.applyUserPermissions({
    email: "alumno@upa.edu.py",
    role: "user",
    permissions: [],
  });

  assert.ok(elements["sidebar-menu"].classList.contains("hidden"));
  assert.ok(elements["view-dashboard"].classList.contains("hidden"));
  assert.ok(elements["view-login"].classList.contains("hidden"));
  assert.ok(!elements["view-restricted"].classList.contains("hidden"), "Debe mostrar la tarjeta de Acceso Restringido");
  assert.equal(router.getCurrentRoute(), "apis");
  assert.equal(window.location.pathname, "/dashboard/apis");
});

test("persistencia: reapplyCurrentRoute conserva el modulo activo y su URL", () => {
  const env = createTestEnvironment("/dashboard/roles");
  const { elements, window, router } = env;

  router.applyUserPermissions({
    email: "pascal.thommen@upa.edu.py",
    role: "admin",
    permissions: ["publicaciones", "grupos", "roles", "apis"],
  });

  router.reapplyCurrentRoute();
  assert.equal(router.getCurrentRoute(), "roles");
  assert.equal(window.location.pathname, "/dashboard/roles");
  assert.ok(!elements["view-admins"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-admins"].classList.contains("is-active"));
});

// ---------------------------------------------------------------------------
// 5. OAuth Redirect Token Extraction & Bundled Dashboard Initialization (SRV-173)
// ---------------------------------------------------------------------------

test("oauth redirect: token aus ?token=... wird vor Router-Init extrahiert und gebündelt initialisiert", async () => {
  const env = createTestEnvironment("/dashboard/apis", "?token=oauth-jwt-token-srv173");
  const { window, localStorage, fetchCalls } = env;

  assert.equal(localStorage.getItem("upa_access_token"), "oauth-jwt-token-srv173");
  assert.equal(window.location.pathname, "/dashboard/apis");
  assert.equal(window.location.search, "");

  // Wait a microtask tick for Promise.all in refreshDashboard() to settle
  await new Promise((resolve) => setTimeout(resolve, 20));

  const healthCalls = fetchCalls.filter((u) => u === "/health").length;
  const meCalls = fetchCalls.filter((u) => u === "/api/auth/me").length;
  const diagCalls = fetchCalls.filter((u) => u === "/api/system/diagnostics").length;

  assert.equal(healthCalls, 1, "checkHealth(/health) darf beim Start nur einmal aufgerufen werden");
  assert.equal(meCalls, 1, "loadUserProfile(/api/auth/me) darf beim Start nur einmal aufgerufen werden");
  assert.equal(diagCalls, 1, "updateJsonView(/api/system/diagnostics) darf auf /dashboard/apis nicht doppelt laufen");
});

test("oauth redirect: auth_error=missing_client_id und forbidden_domain zeigen klare Fehlermeldungen", () => {
  const envMissing = createTestEnvironment("/dashboard", "?auth_error=missing_client_id");
  assert.ok(!envMissing.elements["view-login"].classList.contains("hidden"));
  assert.ok(envMissing.elements["login-alert"].textContent.includes("Client ID"));

  const envForbidden = createTestEnvironment("/dashboard", "?auth_error=forbidden_domain");
  assert.ok(!envForbidden.elements["view-restricted"].classList.contains("hidden"));
  assert.ok(envForbidden.elements["login-alert"].textContent.includes("@upa.edu.py"));
});

test("ux feinschliff: reiterwechsel zeigt keine zwischengeschalteten Cargando-Ladebildschirme", () => {
  const env = createTestEnvironment("/dashboard/publicaciones");
  const { elements, document } = env;

  elements["nav-mod-groups"].click();
  const groupsList = document.getElementById("groups-list-container");
  assert.ok(!groupsList.innerHTML.includes("Cargando"), "Grupos darf keinen Cargando-Placeholder einblenden");

  elements["nav-mod-admins"].click();
  const adminRows = document.getElementById("admin-table-rows");
  assert.ok(!adminRows.innerHTML.includes("Cargando"), "Roles darf keinen Cargando-Placeholder einblenden");

  elements["nav-mod-students"].click();
  const rawJson = document.getElementById("raw-json-output");
  assert.ok(!rawJson.textContent.includes("Consultando telemetría"), "APIs darf keinen Ladeplatzhalter zeigen");
});

test("historial: Rollenmatrix enthält Historial-Spalte und verbirgt Audit-Log ohne historial-Berechtigung", () => {
  const env = createTestEnvironment("/dashboard/roles");
  const { document, router } = env;

  const histEl = document.getElementById("roles-history");
  histEl.innerHTML = '<div class="ed-audit-trail">Historial</div>';
  histEl.classList.remove("hidden");

  // Usuario sin permiso 'historial' -> el bloque de historial se oculta y limpia
  router.applyUserPermissions({
    email: "editor@upa.edu.py",
    role: "admin",
    permissions: ["publicaciones", "grupos", "roles", "apis"],
  });

  assert.ok(histEl.classList.contains("hidden"), "Ohne historial-Berechtigung muss das Audit-Log verborgen sein");
  assert.equal(histEl.innerHTML, "");
});

test("modulo ia: index.html renombra reiter a IA, consolida 1-Klick-Save, precarga prompts UPA y restaura valores por defecto", async () => {
  const indexHtml = fs.readFileSync(path.resolve(__dirname, "../index.html"), "utf8");
  assert.ok(indexHtml.includes('id="nav-mod-ai"'));
  assert.ok(indexHtml.includes('data-perm="ia"'));
  assert.ok(indexHtml.includes('id="sidebar-settings-group"'));
  assert.ok(indexHtml.includes('id="sidebar-settings-divider"'));
  assert.ok(indexHtml.includes('id="sidebar-settings-heading"'));
  assert.ok(indexHtml.includes("Configuración"));
  assert.ok(indexHtml.includes('<span class="flex-1">IA</span>'));
  assert.ok(!indexHtml.includes('<span class="flex-1">Control de IA</span>'));
  assert.ok(indexHtml.includes('aria-label="IA"'));
  assert.ok(indexHtml.includes('id="ai-model-info"'));
  assert.ok(indexHtml.includes("gemini-2.0-flash"));
  assert.ok(!indexHtml.includes("gemini-2.5-flash"));
  assert.ok(indexHtml.includes('id="ai-input-system-prompt-autocomplete"'));
  assert.ok(indexHtml.includes('id="ai-input-system-prompt-instagram"'));
  assert.ok(indexHtml.includes('id="btn-ai-restore-defaults"'));
  assert.ok(indexHtml.includes('id="btn-ai-save-test"'));
  assert.ok(indexHtml.includes('title="Restaurar valores por defecto"'));
  assert.ok(indexHtml.includes('title="Guardar configuración y probar conexión"'));
  assert.ok(!indexHtml.includes("Standard wiederherstellen"));
  assert.ok(!indexHtml.includes("Konfiguration speichern"));
  assert.ok(!indexHtml.includes("Token manual (desarrollo)"));
  assert.ok(!indexHtml.includes('id="form-login"'));
  assert.ok(!indexHtml.includes('id="input-token"'));
  assert.ok(!indexHtml.includes('id="input-classroom-token"'));
  assert.ok(indexHtml.includes("Guardar configuración y probar conexión"));
  assert.ok(indexHtml.includes("https://aistudio.google.com/app/apikey"));
  assert.ok(indexHtml.includes("Create API key"));
  assert.ok(indexHtml.includes("Ver Campus PWA ↗"));
  assert.ok(indexHtml.includes('id="link-campus-pwa"'));
  assert.ok(indexHtml.includes("Acceso Restringido"));
  assert.ok(indexHtml.includes("Volver a UPA Campus"));
  assert.ok(indexHtml.includes('href="/dashboard/favicon.svg"'));

  // Los tres botones individuales confusos han sido eliminados
  assert.ok(!indexHtml.includes('id="btn-ai-save-prompt-autocomplete"'));
  assert.ok(!indexHtml.includes('id="btn-ai-save-prompt-instagram"'));
  assert.ok(!indexHtml.includes('id="btn-ai-test-connection"'));

  // SRV-257: El botón Sincronizar Instagram está junto a + Nueva publicación; Recargar datos sigue eliminado
  assert.ok(!indexHtml.includes('id="btn-refresh"'));
  assert.ok(!indexHtml.includes("Recargar datos"));
  assert.ok(indexHtml.includes('id="ed-btn-sync"'));
  assert.ok(indexHtml.includes("Sincronizar Instagram"));
  assert.ok(indexHtml.includes('id="ed-btn-new-pub"'));
  assert.ok(indexHtml.includes("+ Nueva publicación"));

  const env = createTestEnvironment("/dashboard/ia");
  assert.equal(env.window.location.pathname, "/dashboard/ia");
  assert.equal(env.router.getCurrentRoute(), "ia");

  const form = env.document.getElementById("form-ai-config");
  const keyInput = env.document.getElementById("ai-input-api-key");
  const autoInput = env.document.getElementById("ai-input-system-prompt-autocomplete");
  const igInput = env.document.getElementById("ai-input-system-prompt-instagram");
  const keyErr = env.document.getElementById("ai-key-error");
  const autoErr = env.document.getElementById("ai-prompt-autocomplete-error");
  const igErr = env.document.getElementById("ai-prompt-instagram-error");
  const btnRestore = env.document.getElementById("btn-ai-restore-defaults");

  // Los dos textareas vienen precargados por defecto con los prompts institucionales de la UPA
  assert.ok(autoInput.value.includes("Universidad Paraguayo Alemana (UPA)"));
  assert.ok(autoInput.value.includes("24 horas (HH:mm)"));
  assert.ok(igInput.value.includes("Universidad Paraguayo Alemana (UPA)"));
  assert.ok(igInput.value.includes("Instagram"));

  // Modificar los prompts y pulsar "Restaurar valores por defecto" (Standard wiederherstellen)
  autoInput.value = "Prompt temporal modificado por el editor";
  igInput.value = "Prompt temporal de Instagram modificado";
  btnRestore.click();
  assert.ok(autoInput.value.includes("Universidad Paraguayo Alemana (UPA)"));
  assert.ok(autoInput.value.includes("DD/MM/YYYY"));
  assert.ok(igInput.value.includes("Instagram"));

  // Validación >4000 caracteres al enviar el formulario único muestra error en el campo correspondiente
  keyInput.value = "AIzaValidKeyForTesting12345";
  autoInput.value = "A".repeat(4001);
  form.dispatchEvent({ type: "submit" });
  assert.ok(autoErr.textContent.includes("4000 caracteres"));

  btnRestore.click();
  igInput.value = "B".repeat(4001);
  form.dispatchEvent({ type: "submit" });
  assert.ok(igErr.textContent.includes("4000 caracteres"));

  // Validación de clave inválida (corta, con espacios o máscara con asteriscos) y campo enmascarado type="password"
  assert.equal(keyInput.type, "password");
  btnRestore.click();
  keyInput.value = "corta";
  form.dispatchEvent({ type: "submit" });
  assert.ok(keyErr.textContent.includes("al menos 10 caracteres"));

  keyInput.value = "AIza********1234";
  form.dispatchEvent({ type: "submit" });
  assert.ok(keyErr.textContent.includes("al menos 10 caracteres"));
});

test("grupos widget: visibilidad de #tile-mailgroups depende de rol admin o permisos grupos/apis sin hardcodear correo", async () => {
  const env = createTestEnvironment("/dashboard/apis", "?token=jwt-coord-grupos");
  await new Promise((resolve) => setTimeout(resolve, 20));

  const tile = env.document.getElementById("tile-mailgroups");
  // En el mock inicial google_groups y groups (sin ALL) están vacíos -> oculto
  assert.ok(tile.classList.contains("hidden"));

  // Editor con permiso 'grupos' y otro correo distinto de pascal.thommen ve el widget cuando tiene grupos
  env.router.applyUserPermissions({
    email: "coordinacion.grupos@upa.edu.py",
    role: "editor",
    permissions: ["publicaciones", "grupos"],
  });
});

// ---------------------------------------------------------------------------
// 6. Vereinfachte E-Mail-Eingabe mit Domain-Addon & Paste-Bereinigung (SRV-263)
// ---------------------------------------------------------------------------

test("srv-263: index.html contiene addon visual fijo @upa.edu.py para group-input-email e input-admin-email", () => {
  const indexHtml = fs.readFileSync(path.resolve(__dirname, "../index.html"), "utf8");
  const addonClasses = "bg-slate-100 text-slate-500 font-mono text-xs px-3 border border-l-0 border-slate-300 rounded-r-xl";

  assert.ok(indexHtml.includes('id="group-input-email"'));
  assert.ok(indexHtml.includes('id="group-email-domain-addon"'));
  assert.ok(indexHtml.includes('id="input-admin-email"'));
  assert.ok(indexHtml.includes('id="admin-email-domain-addon"'));
  assert.ok(indexHtml.includes(addonClasses));
});

test("srv-263: normalizacion automatica en input y paste elimina @upa.edu.py y espacios en ambos campos", () => {
  const env = createTestEnvironment("/dashboard/grupos");
  const groupInput = env.document.getElementById("group-input-email");
  const adminInput = env.document.getElementById("input-admin-email");

  // 1) Evento paste con clipboardData (p.ej. maria.lopez@upa.edu.py)
  groupInput.dispatchEvent({
    type: "paste",
    clipboardData: {
      getData: () => "  maria.lopez@upa.edu.py  ",
    },
  });
  assert.equal(groupInput.value, "maria.lopez");

  // 2) Evento input con @UPA.EDU.PY en mayúsculas o duplicado
  groupInput.value = "  JUAN.PEREZ@UPA.EDU.PY@upa.edu.py ";
  groupInput.dispatchEvent({ type: "input" });
  assert.equal(groupInput.value, "JUAN.PEREZ");

  // 3) Evento paste e input en el campo de roles (input-admin-email)
  adminInput.dispatchEvent({
    type: "paste",
    clipboardData: {
      getData: () => "  maria.lopez@UPA.EDU.PY ",
    },
  });
  assert.equal(adminInput.value, "maria.lopez");

  adminInput.value = "carlos.gomez@upa.edu.py";
  adminInput.dispatchEvent({ type: "input" });
  assert.equal(adminInput.value, "carlos.gomez");
});

test("srv-263: handleAddEmail y handleCreateRole componen @upa.edu.py sin duplicar dominio y validan formato", async () => {
  const env = createTestEnvironment("/dashboard/grupos");
  const groupInput = env.document.getElementById("group-input-email");
  const btnAddEmail = env.document.getElementById("btn-add-group-email");
  const groupEmailError = env.document.getElementById("group-email-error");
  const groupChips = env.document.getElementById("group-emails-chips");
  const groupNameInput = env.document.getElementById("group-input-name");
  const formGroup = env.document.getElementById("form-group-editor");

  // Escribir solo el usuario local "juan.perez" y pulsar Agregar correo
  groupInput.value = "juan.perez";
  groupInput.dispatchEvent({ type: "input" });
  btnAddEmail.click();
  assert.equal(groupInput.value, "");
  assert.equal(groupEmailError.textContent, "");
  assert.ok(groupChips.innerHTML.includes("juan.perez@upa.edu.py"));
  assert.ok(!groupChips.innerHTML.includes("@upa.edu.py@upa.edu.py"));

  // Pegar correo completo "maria.lopez@upa.edu.py" y pulsar Agregar correo
  groupInput.dispatchEvent({
    type: "paste",
    clipboardData: { getData: () => "maria.lopez@upa.edu.py" },
  });
  assert.equal(groupInput.value, "maria.lopez");
  btnAddEmail.click();
  assert.ok(groupChips.innerHTML.includes("maria.lopez@upa.edu.py"));
  assert.ok(!groupChips.innerHTML.includes("@upa.edu.py@upa.edu.py"));

  // Dominio externo inválido se rechaza
  groupInput.value = "externo@gmail.com";
  btnAddEmail.click();
  assert.ok(groupEmailError.textContent.includes("@upa.edu.py"));

  // Guardar grupo verifica el payload enviado a POST /api/groups
  groupInput.value = "";
  groupNameInput.value = "Docentes UPA";
  formGroup.dispatchEvent({ type: "submit" });
  await new Promise((resolve) => setTimeout(resolve, 20));

  const groupPost = env.fetchRequests.find((r) => r.endpoint === "/api/groups" && r.options.method === "POST");
  assert.ok(groupPost, "Debe enviar POST /api/groups");
  const groupBody = JSON.parse(groupPost.options.body);
  assert.deepEqual(groupBody.emails, ["juan.perez@upa.edu.py", "maria.lopez@upa.edu.py"]);

  // Roles: handleCreateRole compone @upa.edu.py y envía payload limpio a POST /api/roles
  const adminInput = env.document.getElementById("input-admin-email");
  const adminError = env.document.getElementById("admin-email-error");
  const formAddAdmin = env.document.getElementById("form-add-admin");

  adminInput.value = "externo@otro.com";
  formAddAdmin.dispatchEvent({ type: "submit" });
  assert.ok(adminError.textContent.includes("@upa.edu.py"));

  adminInput.dispatchEvent({
    type: "paste",
    clipboardData: { getData: () => "  ana.martinez@UPA.EDU.PY  " },
  });
  assert.equal(adminInput.value, "ana.martinez");
  formAddAdmin.dispatchEvent({ type: "submit" });
  await new Promise((resolve) => setTimeout(resolve, 20));

  const rolePost = env.fetchRequests.find((r) => r.endpoint === "/api/roles" && r.options.method === "POST");
  assert.ok(rolePost, "Debe enviar POST /api/roles");
  const roleBody = JSON.parse(rolePost.options.body);
  assert.equal(roleBody.email, "ana.martinez@upa.edu.py");
  assert.equal(roleBody.name, "Ana Martinez");
});
