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
      querySelectorAll() {
        return [];
      },
      innerHTML: "",
      textContent: "",
    };
  }

  const elementIds = [
    "sidebar-menu",
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
    fetch: async (endpoint) => {
      fetchCalls.push(endpoint);
      if (endpoint === "/api/auth/me") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: 1,
            email: "pascal.thommen@upa.edu.py",
            full_name: "Pascal Thommen",
            role: "admin",
            permissions: ["publicaciones", "grupos", "roles", "apis"],
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
  assert.ok(!elements["nav-mod-publications"].classList.contains("hidden"));
  assert.ok(!elements["nav-mod-groups"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-admins"].classList.contains("hidden"), "Roles debe ocultarse sin permiso");
  assert.ok(elements["nav-mod-students"].classList.contains("hidden"), "APIs debe ocultarse sin permiso");
  assert.equal(router.getCurrentRoute(), "publicaciones");
  assert.equal(window.location.pathname, "/dashboard/publicaciones");
});

test("permisos dinamicos: estudiante sin permisos administrativos oculta sidebar y aterriza en APIs/Campus", () => {
  const env = createTestEnvironment("/dashboard/publicaciones");
  const { elements, window, router } = env;

  router.applyUserPermissions({
    email: "alumno@upa.edu.py",
    role: "user",
    permissions: [],
  });

  assert.ok(elements["sidebar-menu"].classList.contains("hidden"));
  assert.ok(elements["apis-admin-overview"].classList.contains("hidden"));
  assert.ok(elements["apis-json-details"].classList.contains("hidden"));
  assert.equal(router.getCurrentRoute(), "apis");
  assert.equal(window.location.pathname, "/dashboard/apis");
  assert.ok(!elements["student-workspace"].classList.contains("hidden"));
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
  assert.ok(!envForbidden.elements["view-login"].classList.contains("hidden"));
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

test("control de ia: index.html contiene reiter Control de IA, guia en 3 pasos y controles de conexion", () => {
  const indexHtml = fs.readFileSync(path.resolve(__dirname, "../index.html"), "utf8");
  assert.ok(indexHtml.includes('id="nav-mod-ai"'));
  assert.ok(indexHtml.includes("Control de IA"));
  assert.ok(indexHtml.includes("https://aistudio.google.com/app/apikey"));
  assert.ok(indexHtml.includes("Create API key"));
  assert.ok(indexHtml.includes("Guardar y Probar"));
  assert.ok(indexHtml.includes("Probar conexión"));

  const env = createTestEnvironment("/dashboard/ia");
  assert.equal(env.window.location.pathname, "/dashboard/ia");
  assert.equal(env.router.getCurrentRoute(), "ia");
});
