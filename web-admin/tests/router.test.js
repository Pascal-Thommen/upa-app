/**
 * Pruebas unitarias y de navegacion del Router de Web-Admin (UpaRouter).
 *
 * Valida:
 * - Resolucion de rutas canonicas (/dashboard/publicaciones, /dashboard/grupos, etc.)
 * - Resolucion de alias compatibles (/dashboard/noticias, /dashboard/admins, etc.)
 * - Redireccion de rutas no reconocidas a /dashboard/publicaciones (Criterio 2)
 * - Actualizacion de historial mediante History API (pushState / replaceState)
 * - Navegacion por botones atras/adelante (evento popstate) (Criterio 1)
 * - Deep linking y persistencia en recarga F5 (Criterio 1 y 3)
 * - Alternancia de visibilidad de vistas y clases activas en botones de sidebar
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

// Cargar codigo de app.js en un entorno DOM simulado
function createTestEnvironment(initialPath = "/dashboard/publicaciones") {
  const historyStack = [{ url: initialPath, state: {} }];
  let historyIndex = 0;
  const eventListeners = {};

  const window = {
    location: {
      pathname: initialPath,
      search: "",
      hash: "",
    },
    history: {
      pushState(state, title, url) {
        historyIndex++;
        historyStack.splice(historyIndex, historyStack.length - historyIndex, { url, state });
        window.location.pathname = url;
      },
      replaceState(state, title, url) {
        historyStack[historyIndex] = { url, state };
        window.location.pathname = url;
      },
      back() {
        if (historyIndex > 0) {
          historyIndex--;
          window.location.pathname = historyStack[historyIndex].url;
          if (eventListeners["popstate"]) {
            eventListeners["popstate"].forEach(cb => cb({ state: historyStack[historyIndex].state }));
          }
        }
      },
      forward() {
        if (historyIndex < historyStack.length - 1) {
          historyIndex++;
          window.location.pathname = historyStack[historyIndex].url;
          if (eventListeners["popstate"]) {
            eventListeners["popstate"].forEach(cb => cb({ state: historyStack[historyIndex].state }));
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
        eventListeners[event] = eventListeners[event].filter(cb => cb !== callback);
      }
    },
  };

  const elements = {};

  function makeElement(id) {
    let classes = new Set(["hidden"]);
    const listeners = {};
    return {
      id,
      get className() {
        return Array.from(classes).join(" ");
      },
      set className(val) {
        classes = new Set(String(val || "").trim().split(/\s+/).filter(Boolean));
      },
      classList: {
        add(...cls) {
          cls.forEach(c => classes.add(c));
        },
        remove(...cls) {
          cls.forEach(c => classes.delete(c));
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
          listeners["click"].forEach(cb => cb({ preventDefault() {} }));
        }
      },
      querySelectorAll() {
        return [];
      },
      innerHTML: "",
    };
  }

  // Registrar elementos clave del dashboard
  const elementIds = [
    "nav-mod-publications",
    "nav-mod-groups",
    "nav-mod-admins",
    "nav-mod-diagnostic",
    "nav-mod-students",
    "header-logo-link",
    "view-editorial",
    "view-groups",
    "view-admins",
    "view-diagnostic",
    "student-workspace",
    "mode-btn-editorial",
    "mode-btn-student",
    "ed-tab-news",
    "ed-tab-events",
  ];

  elementIds.forEach(id => {
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
      Object.keys(localStorageData).forEach(k => delete localStorageData[k]);
    },
  };

  // Cargar codigo de app.js extrayendo UpaRouter
  const appJsContent = fs.readFileSync(path.resolve(__dirname, "../app.js"), "utf8");

  const context = {
    window,
    document,
    localStorage,
    console,
    navigator: { clipboard: { writeText: async () => {} } },
    URLSearchParams: class {
      get() { return null; }
    },
    Blob: class {},
    URL: { createObjectURL: () => "" },
    fetch: async () => ({ ok: true, json: async () => [] }),
    renderGroupsModule: () => {},
    renderAdminsModule: () => {},
    updateJsonView: () => {},
    loadUserProfile: async () => ({ role: "admin", email: "admin@upa.edu.py" }),
    checkHealth: async () => {},
    loadClassroomCourses: async () => {},
    loadClassroomDeadlines: async () => {},
    loadCampusFeed: async () => {},
  };

  const fn = new Function(...Object.keys(context), appJsContent);
  fn(...Object.values(context));

  return {
    window,
    document,
    elements,
    router: window.UpaRouter,
  };
}

// ---------------------------------------------------------------------------
// 1. Pruebas de Resolucion de Rutas
// ---------------------------------------------------------------------------

test("resolucion: rutas canonicas de los 5 modulos principales", () => {
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

  assert.deepEqual(r.resolveRoute("/dashboard/diagnostico"), {
    name: "diagnostico",
    path: "/dashboard/diagnostico",
    isRedirect: false,
  });

  assert.deepEqual(r.resolveRoute("/dashboard/estudiantes"), {
    name: "estudiantes",
    path: "/dashboard/estudiantes",
    isRedirect: false,
  });
});

test("resolucion: alias y tolerancia a mayusculas/barras", () => {
  const env = createTestEnvironment();
  const r = env.router;

  assert.equal(r.resolveRoute("/dashboard/noticias").name, "publicaciones");
  assert.equal(r.resolveRoute("/dashboard/eventos").name, "publicaciones");
  assert.equal(r.resolveRoute("/dashboard/groups").name, "grupos");
  assert.equal(r.resolveRoute("/dashboard/admins").name, "roles");
  assert.equal(r.resolveRoute("/dashboard/diagnostic").name, "diagnostico");
  assert.equal(r.resolveRoute("/dashboard/students").name, "estudiantes");
  assert.equal(r.resolveRoute("/DASHBOARD/ROLES/").name, "roles");
});

test("resolucion: rutas no reconocidas redirigen a /dashboard/publicaciones", () => {
  const env = createTestEnvironment();
  const r = env.router;

  const testCases = [
    "/dashboard",
    "/dashboard/",
    "/dashboard/inexistente",
    "/dashboard/modulo-xyz",
    "/dashboard/admin/extra",
    "/otra-cosa",
    "",
    null,
  ];

  for (const tc of testCases) {
    const res = r.resolveRoute(tc);
    assert.equal(res.name, "publicaciones", `Caso ${tc} debe resolver a publicaciones`);
    assert.equal(res.path, "/dashboard/publicaciones", `Caso ${tc} debe apuntar a /dashboard/publicaciones`);
    assert.equal(res.isRedirect, true, `Caso ${tc} debe marcarse como redireccion`);
  }
});

// ---------------------------------------------------------------------------
// 2. Pruebas de Navegacion Interactiva y History API (pushState)
// ---------------------------------------------------------------------------

test("navegacion: clic en pestanas actualiza la URL con pushState y alterna vistas", () => {
  const env = createTestEnvironment("/dashboard/publicaciones");
  const { elements, window, router } = env;

  // Iniciar con publicaciones
  assert.equal(window.location.pathname, "/dashboard/publicaciones");
  assert.ok(!elements["view-editorial"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-publications"].classList.contains("is-active"));

  // Navegar a Grupos
  elements["nav-mod-groups"].click();
  assert.equal(window.location.pathname, "/dashboard/grupos");
  assert.ok(!elements["view-groups"].classList.contains("hidden"), "view-groups debe ser visible");
  assert.ok(elements["view-editorial"].classList.contains("hidden"), "view-editorial debe estar oculto");
  assert.ok(elements["nav-mod-groups"].classList.contains("is-active"));
  assert.ok(!elements["nav-mod-publications"].classList.contains("is-active"));

  // Navegar a Roles
  elements["nav-mod-admins"].click();
  assert.equal(window.location.pathname, "/dashboard/roles");
  assert.ok(!elements["view-admins"].classList.contains("hidden"));
  assert.ok(elements["view-groups"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-admins"].classList.contains("is-active"));

  // Navegar a Diagnostico
  elements["nav-mod-diagnostic"].click();
  assert.equal(window.location.pathname, "/dashboard/diagnostico");
  assert.ok(!elements["view-diagnostic"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-diagnostic"].classList.contains("is-active"));

  // Navegar a Estudiantes
  elements["nav-mod-students"].click();
  assert.equal(window.location.pathname, "/dashboard/estudiantes");
  assert.ok(!elements["student-workspace"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-students"].classList.contains("is-active"));

  // Clic en logo institucional regresa a Publicaciones
  elements["header-logo-link"].click();
  assert.equal(window.location.pathname, "/dashboard/publicaciones");
  assert.ok(!elements["view-editorial"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-publications"].classList.contains("is-active"));
});

// ---------------------------------------------------------------------------
// 3. Pruebas de Botones Atras / Adelante (popstate)
// ---------------------------------------------------------------------------

test("historial: botones atras y adelante del navegador alternan modulos correctamente", () => {
  const env = createTestEnvironment("/dashboard/publicaciones");
  const { elements, window } = env;

  // Realizar secuencia de navegacion: publicaciones -> grupos -> roles
  elements["nav-mod-groups"].click();
  assert.equal(window.location.pathname, "/dashboard/grupos");

  elements["nav-mod-admins"].click();
  assert.equal(window.location.pathname, "/dashboard/roles");
  assert.ok(!elements["view-admins"].classList.contains("hidden"));

  // Simular clic en boton atras del navegador -> debe volver a grupos
  window.history.back();
  assert.equal(window.location.pathname, "/dashboard/grupos");
  assert.ok(!elements["view-groups"].classList.contains("hidden"), "view-groups debe estar activo tras retroceder");
  assert.ok(elements["view-admins"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-groups"].classList.contains("is-active"));

  // Simular otro clic atras -> debe volver a publicaciones
  window.history.back();
  assert.equal(window.location.pathname, "/dashboard/publicaciones");
  assert.ok(!elements["view-editorial"].classList.contains("hidden"), "view-editorial activo");
  assert.ok(elements["nav-mod-publications"].classList.contains("is-active"));

  // Simular clic adelante -> avanza a grupos
  window.history.forward();
  assert.equal(window.location.pathname, "/dashboard/grupos");
  assert.ok(!elements["view-groups"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-groups"].classList.contains("is-active"));

  // Simular clic adelante -> avanza a roles
  window.history.forward();
  assert.equal(window.location.pathname, "/dashboard/roles");
  assert.ok(!elements["view-admins"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-admins"].classList.contains("is-active"));
});

// ---------------------------------------------------------------------------
// 4. Pruebas de Deep Linking y Persistencia en Recarga (F5)
// ---------------------------------------------------------------------------

test("deep linking: carga directa de /dashboard/grupos activa el modulo de grupos", () => {
  const env = createTestEnvironment("/dashboard/grupos");
  const { elements, window, router } = env;

  // Al inicializar en /dashboard/grupos, debe mantenerse esa URL y activar la vista
  assert.equal(window.location.pathname, "/dashboard/grupos");
  assert.equal(router.getCurrentRoute(), "grupos");
  assert.ok(!elements["view-groups"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-groups"].classList.contains("is-active"));
  assert.ok(elements["view-editorial"].classList.contains("hidden"));
});

test("deep linking: carga directa de /dashboard/roles activa la consola de roles", () => {
  const env = createTestEnvironment("/dashboard/roles");
  const { elements, window, router } = env;

  assert.equal(window.location.pathname, "/dashboard/roles");
  assert.equal(router.getCurrentRoute(), "roles");
  assert.ok(!elements["view-admins"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-admins"].classList.contains("is-active"));
});

test("deep linking: ruta desconocida en carga directa redirige a /dashboard/publicaciones", () => {
  const env = createTestEnvironment("/dashboard/subruta-invalida-xyz");
  const { elements, window, router } = env;

  // Debe haber reemplazado la URL con /dashboard/publicaciones
  assert.equal(window.location.pathname, "/dashboard/publicaciones");
  assert.equal(router.getCurrentRoute(), "publicaciones");
  assert.ok(!elements["view-editorial"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-publications"].classList.contains("is-active"));
});

test("deep linking: carga directa de /dashboard/diagnostico activa el modulo diagnostico", () => {
  const env = createTestEnvironment("/dashboard/diagnostico");
  const { elements, window, router } = env;

  assert.equal(window.location.pathname, "/dashboard/diagnostico");
  assert.equal(router.getCurrentRoute(), "diagnostico");
  assert.ok(!elements["view-diagnostic"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-diagnostic"].classList.contains("is-active"));
});

test("deep linking: carga directa de /dashboard/estudiantes activa la vista estudiantil", () => {
  const env = createTestEnvironment("/dashboard/estudiantes");
  const { elements, window, router } = env;

  assert.equal(window.location.pathname, "/dashboard/estudiantes");
  assert.equal(router.getCurrentRoute(), "estudiantes");
  assert.ok(!elements["student-workspace"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-students"].classList.contains("is-active"));
});

test("modo selector: botones de modo editorial y estudiante activan las rutas correspondientes", () => {
  const env = createTestEnvironment("/dashboard/publicaciones");
  const { elements, window, router } = env;

  elements["mode-btn-student"].click();
  assert.equal(window.location.pathname, "/dashboard/estudiantes");
  assert.equal(router.getCurrentRoute(), "estudiantes");
  assert.ok(!elements["student-workspace"].classList.contains("hidden"));

  elements["mode-btn-editorial"].click();
  assert.equal(window.location.pathname, "/dashboard/publicaciones");
  assert.equal(router.getCurrentRoute(), "publicaciones");
  assert.ok(!elements["view-editorial"].classList.contains("hidden"));
});

test("persistencia: reapplyCurrentRoute mantiene el modulo activo y su vista", () => {
  const env = createTestEnvironment("/dashboard/roles");
  const { elements, window, router } = env;

  assert.equal(router.getCurrentRoute(), "roles");
  assert.ok(!elements["view-admins"].classList.contains("hidden"));

  // Simular evento que intente re-aplicar o recargar
  router.reapplyCurrentRoute();
  assert.equal(router.getCurrentRoute(), "roles");
  assert.equal(window.location.pathname, "/dashboard/roles");
  assert.ok(!elements["view-admins"].classList.contains("hidden"));
  assert.ok(elements["nav-mod-admins"].classList.contains("is-active"));
});
