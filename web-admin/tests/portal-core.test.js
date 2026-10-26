/**
 * Pruebas de la logica pura del Portal Institucional (portal-core.js), sin DOM ni red.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const Core = require("../portal-core.js");

const REAL_GROUPS = [
  { id: "01a", name: "Estudiantes Activos", email: "estudiantes.activos@upa.edu.py", description: "Grupo base" },
  { id: "02b", name: "Ing. Tecnologías", email: "ing.tecnologias@upa.edu.py", description: "" },
  { id: "03c", name: "Personal Administrativo", email: "administrativo@upa.edu.py", description: "" },
];

test("grupos: los objetos de la API 2 se normalizan sin perder nombre ni correo", () => {
  const groups = Core.normalizeGoogleGroups(REAL_GROUPS);
  assert.equal(groups.length, 3);
  assert.deepEqual(groups[0], REAL_GROUPS[0]);
});

test("grupos: valores nulos, vacios o incompletos se descartan o se completan", () => {
  assert.deepEqual(Core.normalizeGoogleGroups(null), []);
  assert.deepEqual(Core.normalizeGoogleGroups([null, "", {}, { name: "  " }]), []);
  assert.deepEqual(Core.normalizeGoogleGroups([{ email: "solo@upa.edu.py" }]), [
    { id: "", name: "solo@upa.edu.py", email: "solo@upa.edu.py", description: "" },
  ]);
  assert.deepEqual(Core.normalizeGoogleGroups(["TI"]), [{ id: "", name: "TI", email: "", description: "" }]);
});

test("grupos: el perfil prefiere google_groups y omite las etiquetas sinteticas ALL y TIE", () => {
  assert.equal(Core.groupsFromUser({ google_groups: REAL_GROUPS, groups: ["ALL"] }).length, 3);
  const fallback = Core.groupsFromUser({ google_groups: [], groups: ["ALL", "TIE", "PI"] });
  assert.deepEqual(fallback.map((g) => g.name), ["PI"]);
  assert.deepEqual(Core.groupsFromUser(null), []);
});

test("render: cada grupo muestra nombre y correo real, nunca [object Object]", () => {
  const html = Core.renderGroupBadges(REAL_GROUPS);
  assert.ok(!html.includes("[object Object]"));
  assert.equal((html.match(/class="group-badge"/g) || []).length, 3);
  for (const g of REAL_GROUPS) {
    assert.ok(html.includes(g.name));
    assert.ok(html.includes(g.email));
  }
});

test("render: el contenido de los grupos se escapa (sin inyeccion HTML)", () => {
  const html = Core.renderGroupBadges([{ name: '<img src=x onerror="alert(1)">', email: "a@upa.edu.py", description: '"><b>' }]);
  assert.ok(!html.includes("<img"));
  assert.ok(!html.includes("<b>"));
  assert.ok(html.includes("&lt;img"));
});

test("sesion: se detecta token almacenado o token entrante en la URL", () => {
  const store = (value) => ({ getItem: (key) => (key === Core.ACCESS_TOKEN_KEY ? value : null) });
  assert.equal(Core.hasStoredSession(store("jwt"), ""), true);
  assert.equal(Core.hasStoredSession(store(null), "?token=abc.def"), true);
  assert.equal(Core.hasStoredSession(store(null), "?auth_error=missing_code"), false);
  assert.equal(Core.hasStoredSession(store(null), "?token="), false);
  assert.equal(Core.hasStoredSession(store(null), ""), false);
});

test("sesion: la clave heredada upa_auth_token ya no cuenta como sesion", () => {
  const legacyOnly = { getItem: (key) => (key === Core.LEGACY_TOKEN_KEY ? "viejo" : null) };
  assert.equal(Core.hasStoredSession(legacyOnly, ""), false);
});

test("sesion: un almacenamiento inaccesible no rompe el arranque", () => {
  const broken = {
    getItem() {
      throw new Error("SecurityError");
    },
  };
  assert.equal(Core.hasStoredSession(broken, ""), false);
});
