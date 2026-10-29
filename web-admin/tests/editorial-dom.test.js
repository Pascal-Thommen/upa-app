/**
 * Pruebas de interfaz del Cockpit de Redaccion con DOM real (jsdom) contra el backend REAL.
 *
 * Se carga `index.html` y se ejecutan los scripts reales de web-admin (editorial-core.js,
 * editorial.js, app.js). Las unicas piezas sustituidas son APIs del navegador que jsdom no ofrece:
 * `fetch` (redirigido con Node fetch al servidor uvicorn real), AbortController/FormData/File de Node,
 * `confirm` y `scrollIntoView`. Los clics, formularios y arrastres disparan el codigo de produccion,
 * y cada resultado se contrasta con una lectura independiente de la API.
 *
 * Variables (las fija backend/tests/test_web_admin_cockpit.py): UPA_BASE_URL, UPA_EXPIRED_TOKEN.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const zlib = require("node:zlib");

const BASE_URL = process.env.UPA_BASE_URL;
const EXPIRED_TOKEN = process.env.UPA_EXPIRED_TOKEN;
const live = { skip: BASE_URL ? false : "UPA_BASE_URL no definido (se ejecuta desde pytest)" };

const { JSDOM, VirtualConsole } = BASE_URL ? require("jsdom") : {};
const WEB_ADMIN = path.resolve(__dirname, "..");
const STORAGE_KEY = "upa_access_token";
const RUN_ID = Math.random().toString(36).slice(2, 8);

// ---------------------------------------------------------------------------
// Archivos reales
// ---------------------------------------------------------------------------

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let i = 0; i < 8; i += 1) crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}

function makePng() {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(2, 0);
  header.writeUInt32BE(2, 4);
  header.set([8, 2, 0, 0, 0], 8);
  const scanlines = Buffer.concat([0, 1].map(() => Buffer.from([0, 255, 0, 0, 255, 0, 0])));
  return Buffer.concat([
    Buffer.from("89504e470d0a1a0a", "hex"),
    pngChunk("IHDR", header),
    pngChunk("IDAT", zlib.deflateSync(scanlines)),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

const PNG_BYTES = makePng();
const pngFile = (name) => new File([PNG_BYTES], name || "afiche.png", { type: "image/png" });

// ---------------------------------------------------------------------------
// Acceso independiente a la API real (verificacion de resultados)
// ---------------------------------------------------------------------------

async function api(pathname, token, options) {
  const opts = options || {};
  const response = await fetch(`${BASE_URL}${pathname}`, {
    method: opts.method || "GET",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.json ? { "Content-Type": "application/json" } : {}),
    },
    body: opts.json ? JSON.stringify(opts.json) : undefined,
  });
  const text = await response.text();
  return { status: response.status, body: text ? JSON.parse(text) : null };
}

const TEST_TOKENS = process.env.UPA_TEST_TOKENS ? JSON.parse(process.env.UPA_TEST_TOKENS) : {};

async function loadTestToken(email) {
  const token = TEST_TOKENS[email];
  assert.ok(token, `JWT de prueba disponible para ${email}`);
  const response = await fetch(`${BASE_URL}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  assert.equal(response.status, 200, `/api/auth/me ${email}`);
  return token;
}

const tokens = {};

test("preparacion: sesiones reales de administrador, redaccion y estudiantes", live, async () => {
  tokens.admin = await loadTestToken("admin@upa.edu.py");
  tokens.editor = await loadTestToken("redaccion@upa.edu.py");
  tokens.student1 = await loadTestToken("dom.estudiante1@upa.edu.py");
  tokens.student2 = await loadTestToken("dom.estudiante2@upa.edu.py");
  assert.ok(tokens.admin && tokens.editor && tokens.student1 && tokens.student2);
});

// ---------------------------------------------------------------------------
// Portal en jsdom
// ---------------------------------------------------------------------------

async function openPortal(token, options) {
  const opts = options || {};
  let html = fs.readFileSync(path.join(WEB_ADMIN, "index.html"), "utf8");
  // Los <script src> (CDN de Tailwind, solo estilos) se quitan; los scripts de web-admin se evaluan abajo.
  html = html.replace(/<script\s+src="[^"]*"><\/script>/g, "");

  const pageErrors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (error) => pageErrors.push(error.message));

  const dom = new JSDOM(html, {
    url: `${BASE_URL}/dashboard/`,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole,
  });
  const { window } = dom;
  const document = window.document;

  const confirmations = [];
  const portal = {
    window,
    document,
    pageErrors,
    confirmations,
    confirmAnswer: true,
    $: (id) => document.getElementById(id),
  };

  window.fetch = (input, init) => fetch(new URL(String(input), `${BASE_URL}/`).toString(), init);
  window.AbortController = AbortController;
  window.FormData = FormData;
  window.File = File;
  window.Blob = Blob;
  window.confirm = (message) => {
    confirmations.push(message);
    return portal.confirmAnswer;
  };
  window.alert = () => {};
  window.Element.prototype.scrollIntoView = function scrollIntoView() {};
  if (opts.mode) window.localStorage.setItem("upa_view_mode", opts.mode);
  if (token) window.localStorage.setItem(STORAGE_KEY, token);

  for (const script of ["editorial-core.js", "editorial.js", "app.js"]) {
    window.eval(fs.readFileSync(path.join(WEB_ADMIN, script), "utf8"));
  }
  document.dispatchEvent(new window.Event("DOMContentLoaded"));

  portal.close = () => window.close();
  portal.click = (el) => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
  portal.submit = (form) => form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  portal.change = (el) => el.dispatchEvent(new window.Event("change", { bubbles: true }));
  portal.drop = (zone, file) => {
    const event = new window.Event("drop", { bubbles: true, cancelable: true });
    Object.defineProperty(event, "dataTransfer", { value: { files: [file] } });
    zone.dispatchEvent(event);
  };
  portal.visible = (id) => !portal.$(id).classList.contains("hidden");
  portal.waitFor = async (predicate, message, timeoutMs) => {
    const limit = Date.now() + (timeoutMs || 8000);
    for (;;) {
      let value;
      try {
        value = predicate();
      } catch (_) {
        value = false;
      }
      if (value) return value;
      if (Date.now() > limit) {
        throw new Error(`Tiempo agotado esperando: ${message}`);
      }
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
  };
  portal.waitForNotice = (fragment) =>
    portal.waitFor(() => portal.$("ed-notice").textContent.includes(fragment), `aviso "${fragment}"`);
  portal.waitForEditorial = async () => {
    await portal.waitFor(() => portal.visible("view-editorial"), "cockpit visible");
    await portal.waitFor(
      () => !portal.$("ed-news-rows").textContent.includes("Cargando"),
      "tabla de noticias cargada"
    );
  };
  portal.rowFor = (tbodyId, attr, id) => portal.$(tbodyId).querySelector(`tr[${attr}="${id}"]`);
  return portal;
}

function assertNoPageErrors(portal) {
  assert.deepEqual(portal.pageErrors, [], "la pagina no debe registrar errores de JavaScript");
}

function dayParts(offsetDays) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// ---------------------------------------------------------------------------
// Navegacion y permisos
// ---------------------------------------------------------------------------

test("navegacion: el administrador ve el cockpit y puede alternar con la vista de estudiantes", live, async () => {
  const p = await openPortal(tokens.admin);
  try {
    await p.waitForEditorial();
    assert.ok(p.visible("mode-switch"));
    assert.equal(p.$("user-role-badge").textContent, "ADMINISTRADOR");
    assert.ok(!p.visible("student-workspace"));
    assert.ok(p.$("mode-btn-editorial").classList.contains("is-active"));

    // Catalogos renderizados desde el nucleo
    assert.deepEqual(
      Array.from(p.$("ed-news-category").options).map((o) => o.value),
      ["", "MELDUNG", "ANKUENDIGUNG", "VERANSTALTUNG", "STELLENANGEBOT"]
    );
    const groups = Array.from(p.$("ed-news-groups").querySelectorAll("input"));
    assert.deepEqual(groups.map((g) => g.value), ["ALL", "TIE", "PI", "TI", "PROF"]);
    assert.deepEqual(groups.filter((g) => g.checked).map((g) => g.value), ["ALL"]);

    p.click(p.$("mode-btn-student"));
    assert.ok(p.visible("student-workspace"));
    assert.ok(!p.visible("view-editorial"));
    assert.equal(p.window.localStorage.getItem("upa_view_mode"), "student");
    assert.ok(p.$("mode-btn-student").classList.contains("is-active"));

    p.click(p.$("mode-btn-editorial"));
    assert.ok(p.visible("view-editorial") && !p.visible("student-workspace"));
    assertNoPageErrors(p);
  } finally {
    p.close();
  }
});

test("navegacion: la redaccion ve el cockpit; un estudiante no ve ningun acceso", live, async () => {
  const editor = await openPortal(tokens.editor);
  try {
    await editor.waitForEditorial();
    assert.equal(editor.$("user-role-badge").textContent, "REDACCIÓN");
    assert.ok(editor.visible("mode-switch"));
    assertNoPageErrors(editor);
  } finally {
    editor.close();
  }

  const student = await openPortal(tokens.student1);
  try {
    await student.waitFor(() => student.visible("view-dashboard"), "dashboard del estudiante");
    await student.waitFor(() => student.$("user-role-badge").textContent === "ESTUDIANTE", "rol estudiante");
    assert.ok(!student.visible("mode-switch"), "el estudiante no ve el conmutador");
    assert.ok(!student.visible("view-editorial"), "el cockpit permanece oculto");
    assert.ok(student.visible("student-workspace"));
    assert.equal(student.$("ed-news-rows").innerHTML, "", "no se cargaron datos de gestion");
    assertNoPageErrors(student);
  } finally {
    student.close();
  }
});

// ---------------------------------------------------------------------------
// Noticias
// ---------------------------------------------------------------------------

test("noticias: errores de subida (10 MB, tipo) y validacion de formulario en la interfaz", live, async () => {
  const p = await openPortal(tokens.admin);
  try {
    await p.waitForEditorial();
    const zone = p.document.querySelector('[data-dropzone="news"]');
    const status = zone.querySelector("[data-dz-status]");
    const urlField = p.$("ed-news-image-url");

    const big = new File([Buffer.concat([PNG_BYTES, Buffer.alloc(10 * 1024 * 1024)])], "enorme.png", {
      type: "image/png",
    });
    p.drop(zone, big);
    assert.match(status.textContent, /10 MB/);
    assert.ok(status.classList.contains("is-error"));
    assert.equal(urlField.value, "");

    p.drop(zone, new File([Buffer.from("texto")], "nota.txt", { type: "text/plain" }));
    assert.match(status.textContent, /Tipo de archivo no permitido/);
    assert.equal(urlField.value, "");

    // Contenido falsificado: el cliente lo deja pasar y el servidor real lo rechaza con su mensaje
    p.drop(zone, new File([Buffer.from("no soy una imagen")], "falso.png", { type: "image/png" }));
    await p.waitFor(() => /contenido/.test(status.textContent), "rechazo del servidor");
    assert.ok(status.classList.contains("is-error"));
    assert.equal(urlField.value, "");
    assert.ok(!zone.classList.contains("is-uploading"), "la zona se libera tras el error");

    // Formulario vacio: errores por campo y ninguna publicacion
    const before = (await api("/api/news?limit=100", tokens.admin)).body.length;
    p.$("ed-news-groups").querySelectorAll("input").forEach((box) => (box.checked = false));
    p.submit(p.$("ed-form-news"));
    assert.equal(p.document.querySelector('[data-error-for="news-title"]').textContent, "El título es obligatorio.");
    assert.equal(
      p.document.querySelector('[data-error-for="news-targetGroups"]').textContent,
      "Seleccione al menos un grupo destinatario."
    );
    assert.ok(p.$("ed-news-title").classList.contains("has-error"));
    assert.equal((await api("/api/news?limit=100", tokens.admin)).body.length, before);
    assertNoPageErrors(p);
  } finally {
    p.close();
  }
});

test("noticias: subir afiche, publicar, editar y eliminar desde la interfaz", live, async () => {
  const p = await openPortal(tokens.admin);
  const title = `Convocatoria de becas ${RUN_ID}`;
  try {
    await p.waitForEditorial();
    const zone = p.document.querySelector('[data-dropzone="news"]');
    const urlField = p.$("ed-news-image-url");

    // Subida por arrastrar y soltar contra /api/media/upload real
    p.drop(zone, pngFile("afiche-becas.png"));
    await p.waitFor(() => urlField.value, "URL del archivo subido");
    const posterUrl = urlField.value;
    assert.match(posterUrl, /\/uploads\/[0-9a-f]{32}\.png$/);
    assert.ok(zone.querySelector("[data-dz-preview] img"), "se muestra la vista previa");
    assert.equal(zone.querySelector("[data-dz-preview] img").getAttribute("src"), posterUrl);
    assert.match(zone.querySelector("[data-dz-status]").textContent, /Archivo subido: afiche-becas\.png/);
    const served = await fetch(posterUrl);
    assert.equal(served.status, 200);
    assert.deepEqual(Buffer.from(await served.arrayBuffer()), PNG_BYTES);

    // Publicar
    p.$("ed-news-title").value = title;
    p.$("ed-news-teaser").value = "Postulaciones abiertas";
    p.$("ed-news-content").value = "Presenta tu proyecto en secretaria academica.";
    p.$("ed-news-category").value = "ANKUENDIGUNG";
    p.$("ed-news-groups").querySelector('input[value="TIE"]').checked = true;
    p.$("ed-news-pinned").checked = true;
    p.submit(p.$("ed-form-news"));
    await p.waitForNotice("Noticia publicada");
    assert.ok(p.$("ed-notice").classList.contains("is-success"));

    const listed = (await api("/api/news?limit=100", tokens.admin)).body;
    const created = listed.find((n) => n.title === title);
    assert.ok(created, "la noticia existe en el backend");
    assert.equal(created.caption, "Postulaciones abiertas");
    assert.equal(created.content, "Presenta tu proyecto en secretaria academica.");
    assert.equal(created.category, "ANKUENDIGUNG");
    assert.deepEqual(created.target_groups.sort(), ["ALL", "TIE"]);
    assert.equal(created.post_type, "MANUAL");
    assert.equal(created.is_pinned, true);
    assert.equal(created.media_url, posterUrl);
    await p.waitFor(() => p.rowFor("ed-news-rows", "data-news-id", created.id), "fila en la tabla");
    assert.ok(p.rowFor("ed-news-rows", "data-news-id", created.id).textContent.includes(title));
    assert.equal(p.$("ed-news-title").value, "", "el formulario se vacia tras publicar");
    assert.equal(urlField.value, "", "la zona de carga se reinicia");

    // Editar
    p.click(p.rowFor("ed-news-rows", "data-news-id", created.id).querySelector('[data-action="edit-news"]'));
    assert.equal(p.$("ed-news-form-title").textContent, `Editar noticia #${created.id}`);
    assert.equal(p.$("ed-news-submit").textContent, "Guardar cambios");
    assert.equal(p.$("ed-news-title").value, title);
    assert.equal(p.$("ed-news-category").value, "ANKUENDIGUNG");
    assert.deepEqual(
      Array.from(p.$("ed-news-groups").querySelectorAll("input:checked")).map((b) => b.value).sort(),
      ["ALL", "TIE"]
    );
    assert.equal(urlField.value, posterUrl, "el afiche actual se conserva al editar");
    p.$("ed-news-title").value = `${title} (plazo extendido)`;
    p.submit(p.$("ed-form-news"));
    await p.waitForNotice(`Noticia #${created.id} actualizada`);

    const edited = (await api(`/api/news/${created.id}`, tokens.admin)).body;
    assert.equal(edited.title, `${title} (plazo extendido)`);
    assert.equal(edited.caption, created.caption);
    assert.equal(edited.content, created.content);
    assert.equal(edited.category, "ANKUENDIGUNG");
    assert.equal(edited.media_url, posterUrl);
    assert.deepEqual(edited.target_groups.sort(), ["ALL", "TIE"]);

    // Eliminar (con confirmacion)
    p.confirmAnswer = false;
    p.click(p.rowFor("ed-news-rows", "data-news-id", created.id).querySelector('[data-action="delete-news"]'));
    assert.match(p.confirmations.at(-1), /plazo extendido/);
    assert.equal((await api(`/api/news/${created.id}`, tokens.admin)).status, 200, "cancelar no elimina");
    p.confirmAnswer = true;
    p.click(p.rowFor("ed-news-rows", "data-news-id", created.id).querySelector('[data-action="delete-news"]'));
    await p.waitForNotice(`Noticia #${created.id} eliminada`);
    await p.waitFor(() => !p.rowFor("ed-news-rows", "data-news-id", created.id), "fila eliminada");
    assert.equal((await api(`/api/news/${created.id}`, tokens.admin)).status, 404);
    assertNoPageErrors(p);
  } finally {
    p.close();
  }
});

test("noticias: la Eilmeldung exige confirmacion y se guarda como EMERGENCY_BANNER", live, async () => {
  const p = await openPortal(tokens.admin);
  const title = `Aviso urgente ${RUN_ID}`;
  try {
    await p.waitForEditorial();
    p.$("ed-news-title").value = title;
    p.$("ed-news-teaser").value = "Clases suspendidas";
    p.document.querySelector('input[name="ed-news-urgency"][value="urgent"]').checked = true;

    p.confirmAnswer = false;
    p.submit(p.$("ed-form-news"));
    assert.match(p.confirmations.at(-1), /notificación push/);
    await new Promise((resolve) => setTimeout(resolve, 150));
    const none = (await api("/api/news?limit=100", tokens.admin)).body.find((n) => n.title === title);
    assert.equal(none, undefined, "sin confirmacion no se publica");

    p.confirmAnswer = true;
    p.submit(p.$("ed-form-news"));
    await p.waitForNotice("Noticia publicada");
    const created = (await api("/api/news?limit=100", tokens.admin)).body.find((n) => n.title === title);
    assert.ok(created);
    assert.equal(created.post_type, "EMERGENCY_BANNER");
    await p.waitFor(() => p.rowFor("ed-news-rows", "data-news-id", created.id), "fila de la Eilmeldung");
    assert.ok(p.rowFor("ed-news-rows", "data-news-id", created.id).textContent.includes("Eilmeldung"));
    await api(`/api/news/${created.id}`, tokens.admin, { method: "DELETE" });
    assertNoPageErrors(p);
  } finally {
    p.close();
  }
});

test("noticias: contenido hostil se muestra como texto y nunca se ejecuta", live, async () => {
  const p = await openPortal(tokens.admin);
  const hostile = `<img src=x onerror="window.__xss=1"> ${RUN_ID}`;
  try {
    await p.waitForEditorial();
    p.$("ed-news-title").value = hostile;
    p.$("ed-news-teaser").value = "<script>window.__xss=2</script>";
    p.submit(p.$("ed-form-news"));
    await p.waitForNotice("Noticia publicada");
    const created = (await api("/api/news?limit=100", tokens.admin)).body.find((n) => n.title === hostile);
    assert.ok(created, "el titulo se guarda tal cual");
    await p.waitFor(() => p.rowFor("ed-news-rows", "data-news-id", created.id), "fila hostil");
    const row = p.rowFor("ed-news-rows", "data-news-id", created.id);
    assert.equal(row.querySelector("img"), null, "no se creo ninguna etiqueta img");
    assert.equal(row.querySelector("script"), null);
    assert.ok(row.textContent.includes(hostile), "se ve el texto literal");
    assert.equal(p.window.__xss, undefined);
    await api(`/api/news/${created.id}`, tokens.admin, { method: "DELETE" });
    assertNoPageErrors(p);
  } finally {
    p.close();
  }
});

// ---------------------------------------------------------------------------
// Eventos y participantes
// ---------------------------------------------------------------------------

test("eventos: validacion, creacion con afiche, participantes reales, edicion y borrado", live, async () => {
  const p = await openPortal(tokens.admin);
  const title = `Charla de Inteligencia Artificial ${RUN_ID}`;
  try {
    await p.waitForEditorial();
    p.click(p.$("ed-tab-events"));
    await p.waitFor(() => p.visible("ed-panel-events") && !p.visible("ed-panel-news"), "panel de eventos");
    await p.waitFor(() => !p.$("ed-event-rows").textContent.includes("Cargando"), "tabla de eventos");

    // Validacion de fecha, hora y rango
    p.submit(p.$("ed-form-event"));
    const err = (field) => p.document.querySelector(`[data-error-for="event-${field}"]`).textContent;
    assert.equal(err("title"), "El título es obligatorio.");
    assert.equal(err("date"), "La fecha del evento es obligatoria.");
    assert.equal(err("startTime"), "La hora de inicio es obligatoria.");
    p.$("ed-event-title").value = title;
    p.$("ed-event-date").value = dayParts(2);
    p.$("ed-event-start").value = "10:00";
    p.$("ed-event-end").value = "09:00";
    p.submit(p.$("ed-form-event"));
    assert.equal(err("endTime"), "La hora de finalización no puede ser anterior al inicio.");
    assert.equal(err("title"), "");

    // Alta completa con afiche
    p.$("ed-event-end").value = "12:00";
    p.$("ed-event-description").value = "Disertante invitado.";
    p.$("ed-event-location").value = "Auditorio Edificio 1";
    p.$("ed-event-rsvp").checked = true;
    p.drop(p.document.querySelector('[data-dropzone="event"]'), pngFile("afiche-evento.png"));
    await p.waitFor(() => p.$("ed-event-image-url").value, "afiche del evento");
    const posterUrl = p.$("ed-event-image-url").value;
    p.submit(p.$("ed-form-event"));
    await p.waitForNotice("Evento creado");

    const events = (await api("/api/events?upcoming_only=false&limit=100", tokens.admin)).body;
    const created = events.find((e) => e.title === title);
    assert.ok(created, "el evento existe en el backend");
    assert.equal(created.location, "Auditorio Edificio 1");
    assert.equal(created.description, "Disertante invitado.");
    assert.equal(created.has_registration, true);
    assert.equal(created.image_url, posterUrl);
    assert.equal(
      new Date(created.event_start).getTime(),
      new Date(`${dayParts(2)}T10:00:00`).getTime(),
      "la hora local del formulario se guarda como instante UTC correcto"
    );
    assert.equal(new Date(created.event_end).getTime(), new Date(`${dayParts(2)}T12:00:00`).getTime());
    await p.waitFor(() => p.rowFor("ed-event-rows", "data-event-id", created.id), "fila del evento");
    assert.ok(p.rowFor("ed-event-rows", "data-event-id", created.id).textContent.includes("RSVP activo"));

    // Inscripciones reales de dos estudiantes -> tabla de participantes
    for (const token of [tokens.student1, tokens.student2]) {
      assert.equal((await api(`/api/events/${created.id}/register`, token, { method: "POST" })).status, 200);
    }
    p.click(p.rowFor("ed-event-rows", "data-event-id", created.id).querySelector('[data-action="participants-event"]'));
    await p.waitFor(() => p.$("ed-participants").textContent.includes("2 inscritos"), "tabla de participantes");
    const panelText = p.$("ed-participants").textContent;
    assert.ok(panelText.includes("dom.estudiante1@upa.edu.py") && panelText.includes("Carla Rojas"));
    assert.ok(panelText.includes("dom.estudiante2@upa.edu.py") && panelText.includes("Diego Vera"));
    assert.equal(p.$("ed-participants").querySelectorAll("tbody tr").length, 2);

    // Editar: el formulario recupera fecha y horas locales, y la tabla de participantes se refresca
    p.click(p.rowFor("ed-event-rows", "data-event-id", created.id).querySelector('[data-action="edit-event"]'));
    assert.equal(p.$("ed-event-form-title").textContent, `Editar evento #${created.id}`);
    assert.equal(p.$("ed-event-date").value, dayParts(2));
    assert.equal(p.$("ed-event-start").value, "10:00");
    assert.equal(p.$("ed-event-end").value, "12:00");
    assert.equal(p.$("ed-event-rsvp").checked, true);
    assert.equal(p.$("ed-event-image-url").value, posterUrl);
    p.$("ed-event-location").value = "Aula Magna";
    p.$("ed-event-start").value = "15:00";
    p.$("ed-event-end").value = "17:00";
    p.submit(p.$("ed-form-event"));
    await p.waitForNotice(`Evento #${created.id} actualizado`);
    const updated = (await api(`/api/events/${created.id}`, tokens.admin)).body;
    assert.equal(updated.location, "Aula Magna");
    assert.equal(new Date(updated.event_start).getTime(), new Date(`${dayParts(2)}T15:00:00`).getTime());
    assert.equal(updated.registered_count, 2, "las inscripciones se conservan");
    assert.equal(updated.title, title);
    assert.ok(p.visible("ed-participants"));

    // Eliminar
    p.click(p.rowFor("ed-event-rows", "data-event-id", created.id).querySelector('[data-action="delete-event"]'));
    assert.match(p.confirmations.at(-1), /inscripciones/);
    await p.waitForNotice(`Evento #${created.id} eliminado`);
    await p.waitFor(() => !p.rowFor("ed-event-rows", "data-event-id", created.id), "fila eliminada");
    assert.ok(!p.visible("ed-participants"), "el panel de participantes se oculta");
    assert.equal((await api(`/api/events/${created.id}/registrations`, tokens.admin)).status, 404);
    assertNoPageErrors(p);
  } finally {
    p.close();
  }
});

test("eventos: el filtro 'Incluir pasados' consulta la agenda completa", live, async () => {
  const past = new Date(Date.now() - 3 * 24 * 3600 * 1000);
  const pastTitle = `Evento pasado ${RUN_ID}`;
  const createdPast = await api("/api/events", tokens.admin, {
    method: "POST",
    json: { title: pastTitle, event_start: past.toISOString(), target_groups: ["ALL"] },
  });
  assert.equal(createdPast.status, 201);

  const p = await openPortal(tokens.admin);
  try {
    await p.waitForEditorial();
    p.click(p.$("ed-tab-events"));
    await p.waitFor(() => !p.$("ed-event-rows").textContent.includes("Cargando"), "tabla de eventos");
    assert.ok(!p.$("ed-event-rows").textContent.includes(pastTitle), "por defecto solo eventos futuros");
    p.$("ed-events-include-past").checked = true;
    p.change(p.$("ed-events-include-past"));
    await p.waitFor(() => p.$("ed-event-rows").textContent.includes(pastTitle), "evento pasado visible");
    assertNoPageErrors(p);
  } finally {
    p.close();
    await api(`/api/events/${createdPast.body.id}`, tokens.admin, { method: "DELETE" });
  }
});

// ---------------------------------------------------------------------------
// Instagram
// ---------------------------------------------------------------------------

test("instagram: el boton sincroniza contra el endpoint real y muestra el estado", live, async () => {
  const p = await openPortal(tokens.admin);
  try {
    await p.waitForEditorial();
    const button = p.$("ed-btn-sync");
    const label = button.textContent;
    p.click(button);
    assert.ok(button.disabled, "el boton se bloquea durante la sincronizacion");
    await p.waitForNotice("Sincronización omitida");
    assert.ok(p.$("ed-notice").classList.contains("is-warning"));
    assert.match(p.$("ed-notice").textContent, /INSTAGRAM_ACCESS_TOKEN/);
    assert.match(p.$("ed-sync-status").textContent, /^Última sincronización: \d{2}:\d{2}$/);
    assert.equal(button.disabled, false);
    assert.equal(button.textContent, label);
    assertNoPageErrors(p);
  } finally {
    p.close();
  }
});

// ---------------------------------------------------------------------------
// Sesion expirada, timeouts y red
// ---------------------------------------------------------------------------

test("sesion: un token vencido al cargar vuelve al login con aviso", live, async () => {
  const p = await openPortal(EXPIRED_TOKEN);
  try {
    await p.waitFor(() => p.visible("view-login"), "pantalla de login");
    assert.match(p.$("login-alert").textContent, /sesión ha expirado/);
    assert.ok(!p.visible("view-dashboard"));
    assert.ok(!p.visible("view-editorial"));
    assertNoPageErrors(p);
  } finally {
    p.close();
  }
});

test("sesion: si el token vence durante el trabajo, la accion cierra la sesion y oculta el cockpit", live, async () => {
  const p = await openPortal(tokens.admin);
  try {
    await p.waitForEditorial();
    p.window.localStorage.setItem(STORAGE_KEY, EXPIRED_TOKEN);
    p.click(p.$("ed-news-reload"));
    await p.waitFor(() => p.visible("view-login"), "retorno al login");
    assert.match(p.$("login-alert").textContent, /sesión ha expirado/);
    assert.ok(!p.visible("view-editorial"));
    assert.ok(!p.visible("mode-switch"));
    assert.equal(p.window.localStorage.getItem(STORAGE_KEY), null, "el token vencido se descarta");
    assertNoPageErrors(p);
  } finally {
    p.close();
  }
});

test("red: timeout y servidor inaccesible se muestran sin cerrar la sesion", live, async () => {
  const sockets = new Set();
  const hanging = net.createServer((socket) => {
    sockets.add(socket);
    socket.on("data", () => {});
    socket.on("close", () => sockets.delete(socket));
    socket.on("error", () => {});
  });
  await new Promise((resolve) => hanging.listen(0, "127.0.0.1", resolve));
  const hangUrl = `http://127.0.0.1:${hanging.address().port}`;

  const probe = net.createServer();
  await new Promise((resolve) => probe.listen(0, "127.0.0.1", resolve));
  const closedUrl = `http://127.0.0.1:${probe.address().port}`;
  await new Promise((resolve) => probe.close(resolve));

  const p = await openPortal(tokens.admin);
  try {
    await p.waitForEditorial();

    p.window.UpaCockpit.configure({ baseUrl: hangUrl, timeoutMs: 250, uploadTimeoutMs: 250 });
    p.click(p.$("ed-news-reload"));
    await p.waitFor(() => /tardó demasiado/.test(p.$("ed-news-rows").textContent), "mensaje de timeout en la tabla");

    p.drop(p.document.querySelector('[data-dropzone="news"]'), pngFile("lento.png"));
    await p.waitFor(() => /tardó demasiado/.test(p.document.querySelector('[data-dropzone="news"] [data-dz-status]').textContent), "timeout de subida");
    assert.equal(p.$("ed-news-image-url").value, "");

    p.$("ed-news-title").value = "No debe publicarse";
    p.submit(p.$("ed-form-news"));
    await p.waitForNotice("tardó demasiado");
    assert.ok(p.$("ed-notice").classList.contains("is-error"));
    assert.equal(p.$("ed-news-title").value, "No debe publicarse", "el texto del formulario no se pierde");
    assert.equal(p.$("ed-news-submit").disabled, false, "el boton se libera tras el error");

    p.window.UpaCockpit.configure({ baseUrl: closedUrl, timeoutMs: 1500 });
    p.click(p.$("ed-events-reload"));
    p.click(p.$("ed-tab-events"));
    await p.waitFor(() => /No se pudo contactar con el servidor/.test(p.$("ed-event-rows").textContent), "mensaje de red");

    assert.ok(p.visible("view-dashboard"), "un fallo de red no cierra la sesion");
    assert.ok(p.window.localStorage.getItem(STORAGE_KEY));
    const titles = (await api("/api/news?limit=100", tokens.admin)).body.map((n) => n.title);
    assert.ok(!titles.includes("No debe publicarse"));
    assertNoPageErrors(p);
  } finally {
    p.close();
    sockets.forEach((s) => s.destroy());
    await new Promise((resolve) => hanging.close(resolve));
  }
});
