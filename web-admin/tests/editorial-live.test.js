/**
 * Pruebas de integracion del Cockpit de Redaccion contra el backend REAL (sin mocks).
 *
 * El cliente `editorial-core.js` (el mismo codigo que usa el navegador) opera contra un servidor
 * uvicorn con base de datos SQLite persistente y subida de archivos real a disco.
 * Lo lanza `backend/tests/test_web_admin_cockpit.py`, que fija las variables de entorno:
 *   UPA_BASE_URL       URL del backend en ejecucion
 *   UPA_EXPIRED_TOKEN  JWT firmado por el backend pero ya vencido
 *
 * Cubre: subida (OK, >10 MB, tipo erroneo, contenido falsificado), noticias (crear, leer,
 * editar, eliminar, Eilmeldung), eventos (crear, editar, RSVP, participantes, eliminar),
 * Instagram, permisos por rol y sesion expirada.
 */
const test = require("node:test");
const assert = require("node:assert/strict");

const Core = require("../editorial-core.js");

const BASE_URL = process.env.UPA_BASE_URL;
const EXPIRED_TOKEN = process.env.UPA_EXPIRED_TOKEN;
const live = { skip: BASE_URL ? false : "UPA_BASE_URL no definido (se ejecuta desde pytest)" };

// Archivos binarios reales (cabeceras y estructura validas)
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
  header.writeUInt32BE(2, 0); // ancho
  header.writeUInt32BE(2, 4); // alto
  header.set([8, 2, 0, 0, 0], 8); // 8 bits, RGB
  const scanlines = Buffer.concat([0, 1].map(() => Buffer.from([0, 255, 0, 0, 255, 0, 0])));
  return Buffer.concat([
    Buffer.from("89504e470d0a1a0a", "hex"),
    pngChunk("IHDR", header),
    pngChunk("IDAT", require("node:zlib").deflateSync(scanlines)),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

const PNG_BYTES = makePng();
const PDF_BYTES = Buffer.from("%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n");

const sessions = {};
const ctx = {};

const TEST_TOKENS = process.env.UPA_TEST_TOKENS ? JSON.parse(process.env.UPA_TEST_TOKENS) : {};

async function loadTestSession(email) {
  const token = TEST_TOKENS[email];
  assert.ok(token, `JWT de prueba disponible para ${email}`);
  const response = await fetch(`${BASE_URL}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  assert.equal(response.status, 200, `/api/auth/me ${email}`);
  const user = await response.json();
  return { access_token: token, user };
}

function clientFor(token, extra) {
  return Core.createClient({ baseUrl: BASE_URL, getToken: () => token, ...(extra || {}) });
}

async function rawFetch(path, token, method) {
  return fetch(`${BASE_URL}${path}`, {
    method: method || "GET",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

function tomorrowParts() {
  const d = new Date();
  d.setDate(d.getDate() + 2);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

test("preparacion: sesiones reales para administrador, redaccion y estudiantes", live, async () => {
  const removedDevLogin = await fetch(`${BASE_URL}/api/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "admin@upa.edu.py" }),
  });
  assert.equal(removedDevLogin.status, 404, "/api/auth/dev-login eliminado (404)");

  sessions.admin = await loadTestSession("admin@upa.edu.py");
  assert.equal(sessions.admin.user.role, "admin");
  sessions.editor = await loadTestSession("redaccion@upa.edu.py");
  assert.equal(sessions.editor.user.role, "editor");
  sessions.student1 = await loadTestSession("ana.gomez@upa.edu.py");
  sessions.student2 = await loadTestSession("luis.benitez@upa.edu.py");
  assert.equal(sessions.student1.user.role, "user");
  ctx.admin = clientFor(sessions.admin.access_token);
  ctx.editor = clientFor(sessions.editor.access_token);
  ctx.student = clientFor(sessions.student1.access_token);
});

test("subida: un PNG real se guarda y se entrega con el mismo contenido", live, async () => {
  const blob = new Blob([PNG_BYTES], { type: "image/png" });
  const result = await ctx.admin.uploadMedia(new File([blob], "afiche.png", { type: "image/png" }));
  assert.match(result.url, /\/uploads\/[0-9a-f]{32}\.png$/);
  assert.equal(result.content_type, "image/png");
  assert.equal(result.size_bytes, PNG_BYTES.length);
  assert.match(result.filename, /^[0-9a-f]{32}\.png$/);

  const served = await fetch(result.url);
  assert.equal(served.status, 200);
  assert.equal(served.headers.get("content-type"), "image/png");
  assert.deepEqual(Buffer.from(await served.arrayBuffer()), PNG_BYTES);
  ctx.posterUrl = result.url;
});

test("subida: un PDF real es aceptado con tipo application/pdf", live, async () => {
  const result = await ctx.admin.uploadMedia(new File([PDF_BYTES], "programa.pdf", { type: "application/pdf" }));
  assert.match(result.url, /\.pdf$/);
  assert.equal(result.content_type, "application/pdf");
  assert.equal(result.size_bytes, PDF_BYTES.length);
});

test("subida: archivo de mas de 10 MB rechazado en el cliente y tambien por el servidor", live, async () => {
  const big = Buffer.concat([PNG_BYTES, Buffer.alloc(10 * 1024 * 1024 - PNG_BYTES.length + 1)]);
  assert.equal(big.length, 10 * 1024 * 1024 + 1);
  const file = new File([big], "enorme.png", { type: "image/png" });

  await assert.rejects(
    () => ctx.admin.uploadMedia(file),
    (err) => err.kind === "upload_too_large" && /10 MB/.test(err.message)
  );

  // Sin validacion de cliente: el backend real debe rechazarlo igualmente (HTTP 400)
  await assert.rejects(
    () => ctx.admin.uploadMedia(file, { skipClientValidation: true }),
    (err) => err.kind === "validation" && err.status === 400 && /10 MB/.test(err.message)
  );
});

test("subida: tipo erroneo y contenido falsificado rechazados con mensaje legible", live, async () => {
  const text = new File([Buffer.from("hola mundo")], "nota.txt", { type: "text/plain" });
  await assert.rejects(
    () => ctx.admin.uploadMedia(text),
    (err) => err.kind === "upload_type"
  );
  await assert.rejects(
    () => ctx.admin.uploadMedia(text, { skipClientValidation: true }),
    (err) => err.kind === "validation" && err.status === 400 && /no permitido/.test(err.message)
  );

  // Declara PNG pero el contenido es texto: el servidor valida los bytes reales
  const fake = new File([Buffer.from("esto no es una imagen")], "falso.png", { type: "image/png" });
  await assert.rejects(
    () => ctx.admin.uploadMedia(fake),
    (err) => err.kind === "validation" && err.status === 400 && /contenido/.test(err.message)
  );

  const empty = new File([Buffer.alloc(0)], "vacio.png", { type: "image/png" });
  await assert.rejects(
    () => ctx.admin.uploadMedia(empty),
    (err) => err.kind === "upload_empty"
  );
});

test("noticias: crear con afiche, categoria y grupos persiste el payload exacto", live, async () => {
  const values = {
    title: "Convocatoria de becas 2030",
    teaser: "Postulaciones abiertas hasta fin de mes",
    content: "Los estudiantes pueden presentar su proyecto en secretaria academica.",
    category: "ANKUENDIGUNG",
    targetGroups: ["ALL", "TIE"],
    urgent: false,
    pinned: true,
    imageUrl: ctx.posterUrl,
  };
  assert.deepEqual(Core.validateNewsValues(values), {});
  const created = await ctx.admin.createNews(Core.buildNewsPayload(values, "create"));

  assert.ok(Number.isInteger(created.id) && created.id > 0);
  assert.equal(created.title, values.title);
  assert.equal(created.caption, values.teaser);
  assert.equal(created.content, values.content);
  assert.equal(created.post_type, "MANUAL");
  assert.equal(created.category, "ANKUENDIGUNG");
  assert.deepEqual(created.target_groups, ["ALL", "TIE"]);
  assert.equal(created.is_pinned, true);
  assert.equal(created.media_url, ctx.posterUrl);
  assert.equal(created.image_url, ctx.posterUrl);
  assert.equal(created.media_type, "IMAGE");
  ctx.newsId = created.id;

  // Lectura independiente: un estudiante del grupo ve la noticia con los mismos datos
  const listed = await ctx.student.listNews();
  const found = listed.find((n) => n.id === created.id);
  assert.ok(found, "la noticia aparece en el feed del estudiante");
  assert.equal(found.title, values.title);
  assert.equal(found.media_url, ctx.posterUrl);
  assert.equal(found.category, "ANKUENDIGUNG");
});

test("noticias: Eilmeldung se guarda como EMERGENCY_BANNER con vigencia", live, async () => {
  const values = {
    title: "Clases suspendidas por tormenta",
    teaser: "Hoy no hay clases presenciales",
    content: "",
    category: "MELDUNG",
    targetGroups: ["ALL"],
    urgent: true,
    pinned: true,
    imageUrl: "",
    expiresAt: "2099-01-01T08:00",
  };
  const created = await ctx.admin.createNews(Core.buildNewsPayload(values, "create"));
  assert.equal(created.post_type, "EMERGENCY_BANNER");
  assert.equal(created.is_pinned, true);
  assert.equal(created.media_url, "");
  ctx.urgentId = created.id;

  const listed = await ctx.admin.listNews();
  const urgentItems = listed.filter((n) => n.post_type === "EMERGENCY_BANNER");
  assert.ok(urgentItems.some((n) => n.id === created.id));
  assert.equal(listed[0].is_pinned, true, "las fijadas aparecen primero");
});

test("noticias: editar cambia solo lo indicado y permite vaciar categoria e imagen", live, async () => {
  const current = (await ctx.admin.listNews()).find((n) => n.id === ctx.newsId);
  const form = Core.newsToFormValues(current);
  form.title = "Convocatoria de becas 2030 (plazo extendido)";
  form.category = "";
  form.imageUrl = "";
  form.targetGroups = ["ALL"];
  const updated = await ctx.admin.updateNews(ctx.newsId, Core.buildNewsPayload(form, "update"));

  assert.equal(updated.id, ctx.newsId);
  assert.equal(updated.title, "Convocatoria de becas 2030 (plazo extendido)");
  assert.equal(updated.caption, current.caption, "el teaser se conserva");
  assert.equal(updated.content, current.content, "el texto se conserva");
  assert.equal(updated.category, "");
  assert.equal(updated.media_url, "");
  assert.deepEqual(updated.target_groups, ["ALL"]);
  assert.equal(updated.post_type, "MANUAL");

  const reread = await ctx.admin.listNews();
  assert.equal(reread.find((n) => n.id === ctx.newsId).title, updated.title);
});

test("noticias: categoria inventada y titulo vacio son rechazados por el servidor", live, async () => {
  await assert.rejects(
    () => ctx.admin.createNews({ title: "X", category: "INVENTADA", target_groups: ["ALL"] }),
    (err) => err.kind === "validation" && err.status === 400 && /Categoria invalida/.test(err.message)
  );
  await assert.rejects(
    () => ctx.admin.createNews({ title: "   ", target_groups: ["ALL"] }),
    (err) => err.kind === "validation" && err.status === 400
  );
});

test("noticias: eliminar quita la publicacion y un segundo intento devuelve not_found", live, async () => {
  const response = await ctx.admin.deleteNews(ctx.urgentId);
  assert.equal(response.status, "deleted");
  assert.equal(response.id, ctx.urgentId);
  const listed = await ctx.admin.listNews();
  assert.ok(!listed.some((n) => n.id === ctx.urgentId));
  await assert.rejects(
    () => ctx.admin.deleteNews(ctx.urgentId),
    (err) => err.kind === "not_found" && err.status === 404
  );
  await assert.rejects(
    () => ctx.admin.updateNews(ctx.urgentId, { title: "fantasma" }),
    (err) => err.kind === "not_found"
  );
});

test("eventos: crear con RSVP, lugar, horario y afiche persiste el payload exacto", live, async () => {
  const values = {
    title: "Charla: Inteligencia Artificial",
    description: "Disertante invitado en el auditorio principal.",
    location: "Auditorio Edificio 1",
    date: tomorrowParts(),
    startTime: "10:00",
    endTime: "12:00",
    targetGroups: ["ALL", "TIE"],
    rsvp: true,
    imageUrl: ctx.posterUrl,
  };
  assert.deepEqual(Core.validateEventValues(values), {});
  const created = await ctx.admin.createEvent(Core.buildEventPayload(values));

  assert.ok(created.id > 0);
  assert.equal(created.title, values.title);
  assert.equal(created.description, values.description);
  assert.equal(created.location, values.location);
  assert.equal(new Date(created.event_start).getTime(), new Date(Core.localDateTimeToIso(values.date, "10:00")).getTime());
  assert.equal(new Date(created.event_end).getTime(), new Date(Core.localDateTimeToIso(values.date, "12:00")).getTime());
  assert.equal(created.has_registration, true);
  assert.deepEqual(created.target_groups, ["ALL", "TIE"]);
  assert.equal(created.image_url, ctx.posterUrl);
  assert.equal(created.registered_count, 0);
  ctx.eventId = created.id;

  const listed = await ctx.admin.listEvents();
  const found = listed.find((e) => e.id === created.id);
  assert.ok(found, "el evento aparece en la agenda");
  assert.equal(found.title, values.title);
  assert.deepEqual(Core.eventToFormValues(found).date, values.date);
  assert.equal(Core.eventToFormValues(found).startTime, "10:00");

  // La agenda de un estudiante del grupo lo incluye, aunque no sea una noticia
  const studentEvents = await ctx.student.listEvents();
  assert.ok(studentEvents.some((e) => e.id === created.id));
  const newsFeed = await ctx.student.listNews();
  assert.ok(!newsFeed.some((n) => n.title === values.title), "un evento no se publica como noticia");
});

test("eventos: fin anterior al inicio y titulo vacio son rechazados por el servidor", live, async () => {
  const start = Core.localDateTimeToIso(tomorrowParts(), "10:00");
  const earlier = Core.localDateTimeToIso(tomorrowParts(), "09:00");
  await assert.rejects(
    () => ctx.admin.createEvent({ title: "Evento invalido", event_start: start, event_end: earlier }),
    (err) => err.kind === "validation" && err.status === 400 && /finalizacion/.test(err.message)
  );
  await assert.rejects(
    () => ctx.admin.createEvent({ title: "  ", event_start: start }),
    (err) => err.kind === "validation" && err.status === 400
  );
  await assert.rejects(
    () => ctx.admin.createEvent({ title: "Sin fecha" }),
    (err) => err.kind === "validation" && err.status === 422 && /event_start/.test(err.message)
  );
});

test("participantes: inscripciones reales de estudiantes aparecen en la tabla del evento", live, async () => {
  for (const key of ["student1", "student2"]) {
    const response = await rawFetch(`/api/events/${ctx.eventId}/register`, sessions[key].access_token, "POST");
    assert.equal(response.status, 200, `inscripcion de ${key}`);
  }

  const data = await ctx.admin.getEventRegistrations(ctx.eventId);
  assert.equal(data.event_id, ctx.eventId);
  assert.equal(data.title, "Charla: Inteligencia Artificial");
  assert.equal(data.has_registration, true);
  assert.equal(data.attending_count, 2);
  assert.deepEqual(
    data.registrations.map((r) => r.email).sort(),
    ["ana.gomez@upa.edu.py", "luis.benitez@upa.edu.py"]
  );
  const ana = data.registrations.find((r) => r.email === "ana.gomez@upa.edu.py");
  assert.equal(ana.full_name, "Ana Gomez");
  assert.equal(ana.status, "attending");
  assert.equal(ana.user_id, sessions.student1.user.id);
  assert.ok(!Number.isNaN(new Date(ana.registered_at).getTime()));

  const html = Core.renderParticipantsTable(data);
  assert.ok(html.includes("ana.gomez@upa.edu.py") && html.includes("Luis Benitez") && html.includes("2 inscritos"));

  const listed = await ctx.admin.listEvents();
  assert.equal(listed.find((e) => e.id === ctx.eventId).registered_count, 2);

  // Baja de una inscripcion: la tabla se actualiza
  const unregister = await rawFetch(`/api/events/${ctx.eventId}/register`, sessions.student2.access_token, "DELETE");
  assert.equal(unregister.status, 200);
  const after = await ctx.admin.getEventRegistrations(ctx.eventId);
  assert.equal(after.attending_count, 1);
  assert.deepEqual(after.registrations.map((r) => r.email), ["ana.gomez@upa.edu.py"]);
});

test("eventos: editar horario y lugar mantiene las inscripciones", live, async () => {
  const current = (await ctx.admin.listEvents()).find((e) => e.id === ctx.eventId);
  const form = Core.eventToFormValues(current);
  form.location = "Aula Magna";
  form.startTime = "15:00";
  form.endTime = "17:30";
  form.title = "Charla: IA y sociedad";
  assert.deepEqual(Core.validateEventValues(form), {});
  const updated = await ctx.admin.updateEvent(ctx.eventId, Core.buildEventPayload(form));

  assert.equal(updated.title, "Charla: IA y sociedad");
  assert.equal(updated.location, "Aula Magna");
  assert.equal(new Date(updated.event_start).getTime(), new Date(Core.localDateTimeToIso(form.date, "15:00")).getTime());
  assert.equal(new Date(updated.event_end).getTime(), new Date(Core.localDateTimeToIso(form.date, "17:30")).getTime());
  assert.equal(updated.has_registration, true);
  assert.equal(updated.registered_count, 1);
  assert.equal(updated.description, current.description, "la descripcion se conserva");

  await assert.rejects(
    () => ctx.admin.updateEvent(ctx.eventId, { event_end: Core.localDateTimeToIso(form.date, "08:00") }),
    (err) => err.kind === "validation" && err.status === 400
  );
});

test("eventos: eliminar borra evento e inscripciones", live, async () => {
  const response = await ctx.admin.deleteEvent(ctx.eventId);
  assert.equal(response.status, "deleted");
  assert.ok(!(await ctx.admin.listEvents()).some((e) => e.id === ctx.eventId));
  await assert.rejects(
    () => ctx.admin.getEventRegistrations(ctx.eventId),
    (err) => err.kind === "not_found" && err.status === 404
  );
  await assert.rejects(
    () => ctx.admin.deleteEvent(ctx.eventId),
    (err) => err.kind === "not_found"
  );
});

test("instagram: la sincronizacion manual devuelve un estado interpretable", live, async () => {
  const result = await ctx.admin.syncInstagram();
  assert.equal(result.status, "skipped", "el servidor de prueba no tiene credenciales de Instagram");
  assert.equal(result.synced_count, 0);
  const summary = Core.describeSyncResult(result);
  assert.equal(summary.type, "warning");
  assert.match(summary.message, /INSTAGRAM_ACCESS_TOKEN/);
});

test("permisos: la redaccion publica; un estudiante recibe 403 en todas las acciones de gestion", live, async () => {
  const byEditor = await ctx.editor.createNews(
    Core.buildNewsPayload({ title: "Nota de redaccion", targetGroups: ["ALL"], category: "MELDUNG" }, "create")
  );
  assert.equal(byEditor.title, "Nota de redaccion");
  assert.equal(byEditor.category, "MELDUNG");
  await ctx.editor.deleteNews(byEditor.id);

  const forbidden = (err) => err.kind === "forbidden" && err.status === 403 && /permisos/.test(err.message);
  await assert.rejects(() => ctx.student.createNews({ title: "No autorizado", target_groups: ["ALL"] }), forbidden);
  await assert.rejects(() => ctx.student.updateNews(ctx.newsId, { title: "No autorizado" }), forbidden);
  await assert.rejects(() => ctx.student.deleteNews(ctx.newsId), forbidden);
  await assert.rejects(
    () => ctx.student.createEvent({ title: "No autorizado", event_start: new Date().toISOString() }),
    forbidden
  );
  await assert.rejects(() => ctx.student.getEventRegistrations(1), forbidden);
  await assert.rejects(() => ctx.student.syncInstagram(), forbidden);
  await assert.rejects(
    () => ctx.student.uploadMedia(new File([PNG_BYTES], "bloqueado.png", { type: "image/png" })),
    forbidden
  );
  await assert.rejects(() => ctx.student.listGroups(), forbidden);

  // La noticia sigue intacta tras los intentos no autorizados
  assert.ok((await ctx.admin.listNews()).some((n) => n.id === ctx.newsId));
});

test("sesion expirada: HTTP 401 dispara el cierre de sesion exactamente una vez", live, async () => {
  assert.ok(EXPIRED_TOKEN, "pytest entrega un JWT vencido real");
  for (const token of [EXPIRED_TOKEN, "token-invalido", null]) {
    let expiredCalls = 0;
    const client = clientFor(token, { onUnauthorized: () => (expiredCalls += 1) });
    await assert.rejects(
      () => client.listNews(),
      (err) => err.kind === "unauthorized" && err.status === 401 && /sesión ha expirado/.test(err.message)
    );
    assert.equal(expiredCalls, 1, `token ${token ? token.slice(0, 8) : "(ninguno)"}`);
  }

  let uploadCalls = 0;
  const client = clientFor(EXPIRED_TOKEN, { onUnauthorized: () => (uploadCalls += 1) });
  const file = new File([PNG_BYTES], "a.png", { type: "image/png" });
  await assert.rejects(
    () => client.uploadMedia(file),
    (err) => err.kind === "unauthorized"
  );
  assert.equal(uploadCalls, 1);
});

test("publicaciones unificadas: crear hibrido Noticia+Evento, RSVP con baja, vistas e historial admin", live, async () => {
  const eventStart = `${tomorrowParts()}T14:00`;
  const eventEnd = `${tomorrowParts()}T16:00`;
  const values = {
    title: "Simposio de Ingeniería y Gestión",
    postType: "MANUAL",
    hasRegistration: true,
    targetGroups: ["ALL"],
    publishMode: "on_save",
    isNews: true,
    notifyGroups: ["ALL"],
    caption: "Inscripciones abiertas",
    content: "Actividad conjunta para estudiantes y docentes.",
    detailText: "Incluye certificado de participación.",
    linkLabel: "Agenda PDF",
    linkUrl: "https://upa.edu.py/simposio",
    category: "VERANSTALTUNG",
    isEvent: true,
    eventStart,
    eventEnd,
    location: "Auditorio Central",
    eventNotifyGroups: ["ALL"],
    reminders: [30, 120],
    imageUrl: ctx.posterUrl,
  };
  assert.deepEqual(Core.validatePublicationValues(values), {});
  const created = await ctx.editor.createPublication(Core.buildPublicationPayload(values));
  assert.equal(created.is_news, true);
  assert.equal(created.is_event, true);
  assert.deepEqual(created.reminders, [30, 120]);
  assert.equal(created.detail_text, "Incluye certificado de participación.");

  // Vistas unicas y RSVP (asistencia + baja)
  const v1 = await ctx.student.markPublicationViewed(created.id);
  const v2 = await ctx.student.markPublicationViewed(created.id);
  assert.equal(v1.views_count, 1);
  assert.equal(v2.views_count, 1);

  await ctx.student.submitPublicationRsvp(created.id, "attending");
  const student2Client = clientFor(sessions.student2.access_token);
  await student2Client.submitPublicationRsvp(created.id, "attending");
  const afterDecline = await student2Client.submitPublicationRsvp(created.id, "declined");
  assert.equal(afterDecline.attending_count, 1);
  assert.equal(afterDecline.declined_count, 1);

  // Quitar todos los recordatorios dejando lista vacia []
  const updated = await ctx.editor.updatePublication(created.id, { reminders: [] });
  assert.deepEqual(updated.reminders, []);

  // Historial visible para admin (200) y prohibido para editor y estudiante (403)
  const history = await ctx.admin.getHistory("post", created.id);
  assert.ok(Array.isArray(history) && history.length >= 2);
  await assert.rejects(
    () => ctx.editor.getHistory("post", created.id),
    (err) => err.kind === "forbidden" && err.status === 403
  );
  await assert.rejects(
    () => ctx.student.getHistory("post"),
    (err) => err.kind === "forbidden" && err.status === 403
  );

  await ctx.editor.deletePublication(created.id);
});

test("grupos y matriz de roles en vivo contra SQLite/PostgreSQL", live, async () => {
  const ws = await ctx.admin.listWorkspaceGroups();
  assert.ok(Array.isArray(ws.groups));

  const grp = await ctx.admin.createGroup({
    name: "Cohorte Innovación",
    description: "",
    google_groups: ["innovacion@upa.edu.py"],
    emails: ["ana.gomez@upa.edu.py"],
  });
  assert.equal(grp.name, "Cohorte Innovación");
  assert.deepEqual(grp.google_groups, ["innovacion@upa.edu.py"]);

  const updGrp = await ctx.admin.updateGroup(grp.id, {
    name: "Cohorte Innovación 2026",
    google_groups: ["innovacion@upa.edu.py"],
    emails: ["ana.gomez@upa.edu.py", "luis.benitez@upa.edu.py"],
  });
  assert.equal(updGrp.name, "Cohorte Innovación 2026");
  assert.equal(updGrp.emails.length, 2);
  await ctx.admin.deleteGroup(grp.id);

  // Matriz de roles: autorizar cuenta con permisos especificos y actualizarla
  const assigned = await ctx.admin.assignRole({
    email: "coordinador.test@upa.edu.py",
    name: "Coordinador Test",
    permissions: ["publicaciones", "grupos"],
  });
  assert.deepEqual(assigned.permissions, ["publicaciones", "grupos"]);

  const updatedRole = await ctx.admin.updateRole("coordinador.test@upa.edu.py", {
    permissions: ["grupos", "apis"],
  });
  assert.deepEqual(updatedRole.permissions, ["grupos", "apis"]);
  await ctx.admin.revokeRole("coordinador.test@upa.edu.py");

  // Control de IA: guardar clave de Gemini y consultar clave enmascarada
  const aiBefore = await ctx.admin.getAiConfig();
  assert.equal(typeof aiBefore.configured, "boolean");
  const aiSaved = await ctx.admin.saveAiConfig("AIzaSyLiveCockpitKey1234");
  assert.equal(aiSaved.configured, true);
  assert.equal(aiSaved.masked_key, "AIza********1234");
  assert.equal(aiSaved.source, "database");
});
