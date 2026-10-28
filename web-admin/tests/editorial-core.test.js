/**
 * Pruebas unitarias del nucleo del Cockpit de Redaccion (sin backend).
 *
 * Verifican la logica pura (validacion, payloads, escape HTML) y, mediante servidores TCP locales,
 * los casos de red que el backend real no puede producir de forma determinista:
 * timeout de la solicitud y servidor inaccesible.
 *
 * Ejecucion: node --test web-admin/tests/editorial-core.test.js
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const net = require("node:net");

const Core = require("../editorial-core.js");

const MB = 1024 * 1024;

function fakeFile(size, type) {
  return { size, type, name: "archivo" };
}

test("validateUploadFile: acepta 10 MB exactos y rechaza 10 MB + 1 byte", () => {
  assert.deepEqual(Core.PERMISSION_KEYS, ["publicaciones", "grupos", "roles", "apis", "historial"]);
  assert.equal(Core.MAX_UPLOAD_BYTES, 10 * MB);
  assert.deepEqual(Core.validateUploadFile(fakeFile(10 * MB, "image/png")), { ok: true });
  const tooLarge = Core.validateUploadFile(fakeFile(10 * MB + 1, "image/png"));
  assert.equal(tooLarge.ok, false);
  assert.equal(tooLarge.kind, "upload_too_large");
  assert.match(tooLarge.message, /10 MB/);
});

test("validateUploadFile: rechaza tipos no permitidos, archivos vacios y ausencia de archivo", () => {
  for (const type of ["text/plain", "image/gif", "application/zip", "image/svg+xml", ""]) {
    const result = Core.validateUploadFile(fakeFile(1024, type));
    assert.equal(result.ok, false, `tipo ${type || "(vacio)"} debe rechazarse`);
    assert.equal(result.kind, "upload_type");
  }
  assert.equal(Core.validateUploadFile(fakeFile(0, "image/png")).kind, "upload_empty");
  assert.equal(Core.validateUploadFile(null).kind, "upload_missing");
});

test("validateUploadFile: acepta JPG, PNG, WEBP, MP4, WEBM y PDF (incluido parametro charset)", () => {
  for (const type of [
    "image/jpeg",
    "image/png",
    "image/webp",
    "video/mp4",
    "video/webm",
    "application/pdf",
    "IMAGE/PNG; charset=binary",
  ]) {
    assert.equal(Core.validateUploadFile(fakeFile(2048, type)).ok, true, type);
  }
});

test("uploadMedia: el cliente rechaza antes de enviar (sin llamada de red)", async () => {
  let calls = 0;
  const client = Core.createClient({
    getToken: () => "t",
    fetchImpl: async () => {
      calls += 1;
      throw new Error("no deberia llamarse");
    },
  });
  await assert.rejects(
    () => client.uploadMedia(fakeFile(11 * MB, "image/png")),
    (err) => err instanceof Core.ApiError && err.kind === "upload_too_large"
  );
  await assert.rejects(
    () => client.uploadMedia(fakeFile(10, "text/plain")),
    (err) => err instanceof Core.ApiError && err.kind === "upload_type"
  );
  assert.equal(calls, 0);
});

test("validateNewsValues: titulo obligatorio, limites, categoria y grupos", () => {
  const base = { title: "Titulo", teaser: "", content: "", category: "", targetGroups: ["ALL"] };
  assert.deepEqual(Core.validateNewsValues(base), {});
  assert.ok(Core.validateNewsValues({ ...base, title: "   " }).title);
  assert.ok(Core.validateNewsValues({ ...base, title: "x".repeat(256) }).title);
  assert.ok(Core.validateNewsValues({ ...base, teaser: "x".repeat(301) }).teaser);
  assert.ok(Core.validateNewsValues({ ...base, category: "INVENTADA" }).category);
  assert.ok(Core.validateNewsValues({ ...base, targetGroups: [] }).targetGroups);
  assert.ok(Core.validateNewsValues({ ...base, expiresAt: "no-es-fecha" }).expiresAt);
});

test("buildNewsPayload: Eilmeldung, categoria, imagen y vigencia llegan al payload", () => {
  const values = {
    title: "  Cierre del campus  ",
    teaser: "Por tormenta",
    content: "Texto completo",
    category: "ANKUENDIGUNG",
    targetGroups: ["ALL", " TIE "],
    urgent: true,
    pinned: true,
    imageUrl: "https://api.upa.edu.py/uploads/abc.png",
    expiresAt: "2030-01-02T10:30",
  };
  const create = Core.buildNewsPayload(values, "create");
  assert.equal(create.title, "Cierre del campus");
  assert.equal(create.caption, "Por tormenta");
  assert.equal(create.content, "Texto completo");
  assert.equal(create.post_type, "EMERGENCY_BANNER");
  assert.equal(create.category, "ANKUENDIGUNG");
  assert.deepEqual(create.target_groups, ["ALL", "TIE"]);
  assert.equal(create.is_pinned, true);
  assert.equal(create.media_url, "https://api.upa.edu.py/uploads/abc.png");
  assert.equal(create.media_type, "IMAGE");
  assert.equal(create.is_news, true);
  assert.equal(create.is_event, false);
  assert.equal(create.expires_at, new Date("2030-01-02T10:30").toISOString());

  const update = Core.buildNewsPayload({ ...values, urgent: false, imageUrl: "", expiresAt: "" }, "update");
  assert.equal(update.post_type, "MANUAL");
  assert.equal(update.media_url, "");
  assert.equal(update.media_type, "");
  assert.ok(!("is_news" in update) && !("is_event" in update) && !("expires_at" in update));
});

test("buildNewsPayload: un PDF no se marca como IMAGE", () => {
  const payload = Core.buildNewsPayload(
    { title: "Afiche", targetGroups: ["ALL"], imageUrl: "http://localhost/uploads/doc.pdf" },
    "create"
  );
  assert.equal(payload.media_type, "");
});

test("newsToFormValues: conserva grupos fuera del catalogo y el tipo urgente", () => {
  const values = Core.newsToFormValues({
    title: "A",
    caption: "B",
    content: "C",
    category: "MELDUNG",
    target_groups: ["ALL", "Semester_4"],
    post_type: "EMERGENCY_BANNER",
    is_pinned: true,
    media_url: "/uploads/x.png",
  });
  assert.deepEqual(values.targetGroups, ["ALL", "Semester_4"]);
  assert.equal(values.urgent, true);
  assert.equal(values.teaser, "B");
  assert.equal(values.imageUrl, "/uploads/x.png");
});

test("fecha y hora locales: ida y vuelta consistente a ISO UTC", () => {
  const iso = Core.localDateTimeToIso("2030-06-15", "14:30");
  assert.equal(iso, new Date(2030, 5, 15, 14, 30).toISOString());
  assert.deepEqual(Core.isoToLocalParts(iso), { date: "2030-06-15", time: "14:30" });
  assert.equal(Core.localDateTimeToIso("", "14:30"), null);
  assert.equal(Core.localDateTimeToIso("2030-13-45", "14:30"), null);
  assert.equal(Core.localDateTimeToIso("2030-06-15", "25:99"), null);
  assert.equal(Core.localDateTimeToIso("2030-02-31", "10:00"), null);
});

test("validateEventValues: fecha, inicio, fin posterior y grupos", () => {
  const base = {
    title: "Charla",
    description: "",
    location: "",
    date: "2030-06-15",
    startTime: "10:00",
    endTime: "12:00",
    targetGroups: ["ALL"],
  };
  assert.deepEqual(Core.validateEventValues(base), {});
  assert.ok(Core.validateEventValues({ ...base, title: "" }).title);
  assert.ok(Core.validateEventValues({ ...base, date: "" }).date);
  assert.ok(Core.validateEventValues({ ...base, startTime: "" }).startTime);
  assert.ok(Core.validateEventValues({ ...base, endTime: "09:59" }).endTime);
  assert.deepEqual(Core.validateEventValues({ ...base, endTime: "" }), {});
  assert.ok(Core.validateEventValues({ ...base, targetGroups: [] }).targetGroups);
});

test("buildEventPayload: instantes UTC, RSVP, grupos e imagen", () => {
  const payload = Core.buildEventPayload({
    title: " Charla IA ",
    description: "Descripcion",
    location: "Auditorio",
    date: "2030-06-15",
    startTime: "10:00",
    endTime: "12:00",
    targetGroups: ["TIE"],
    rsvp: true,
    imageUrl: "https://x.test/uploads/a.webp",
  });
  assert.equal(payload.title, "Charla IA");
  assert.equal(payload.event_start, new Date(2030, 5, 15, 10, 0).toISOString());
  assert.equal(payload.event_end, new Date(2030, 5, 15, 12, 0).toISOString());
  assert.equal(payload.has_registration, true);
  assert.deepEqual(payload.target_groups, ["TIE"]);
  assert.equal(payload.image_url, "https://x.test/uploads/a.webp");
  assert.equal(payload.media_type, "IMAGE");

  const noEnd = Core.buildEventPayload({ title: "x", date: "2030-06-15", startTime: "10:00", targetGroups: ["ALL"] });
  assert.ok(!("event_end" in noEnd));
  assert.equal(noEnd.has_registration, false);
});

test("eventToFormValues: reconstruye fecha y horas locales del evento", () => {
  const values = Core.eventToFormValues({
    title: "Charla",
    description: "D",
    location: "L",
    event_start: new Date(2030, 5, 15, 10, 0).toISOString(),
    event_end: new Date(2030, 5, 15, 12, 30).toISOString(),
    target_groups: ["ALL"],
    has_registration: true,
    image_url: "",
  });
  assert.equal(values.date, "2030-06-15");
  assert.equal(values.startTime, "10:00");
  assert.equal(values.endTime, "12:30");
  assert.equal(values.rsvp, true);
});

test("renderNewsRows escapa HTML hostil y descarta URLs peligrosas", () => {
  const html = Core.renderNewsRows([
    {
      id: 7,
      title: "<script>alert('x')</script>",
      caption: '"><img src=x onerror=alert(1)>',
      category: "MELDUNG",
      post_type: "EMERGENCY_BANNER",
      target_groups: ["<b>ALL</b>"],
      media_url: "javascript:alert(1)",
    },
  ]);
  assert.ok(!html.includes("<script>"), "no debe quedar un <script> sin escapar");
  assert.ok(!html.includes("<img src=x"), "no debe quedar una etiqueta img inyectada");
  assert.ok(!html.includes("javascript:"), "la URL javascript: no debe renderizarse");
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(html.includes("Eilmeldung"));
  assert.ok(html.includes('data-id="7"'));
  assert.equal(Core.safeUrl("javascript:alert(1)"), "");
  assert.equal(Core.safeUrl("//evil.test/x.png"), "");
  assert.equal(Core.safeUrl("/uploads/a.png"), "/uploads/a.png");
  assert.equal(Core.safeUrl("https://ok.test/a.png"), "https://ok.test/a.png");
});

test("renderEventRows y renderParticipantsTable muestran datos reales y estados vacios", () => {
  const events = Core.renderEventRows(
    [
      {
        id: 3,
        title: "Charla",
        location: "Auditorio",
        event_start: "2030-06-15T13:00:00Z",
        has_registration: true,
        registered_count: 12,
        target_groups: ["ALL"],
      },
    ],
    { timeZone: "UTC" }
  );
  assert.ok(events.includes("RSVP activo"));
  assert.ok(events.includes("12"));
  assert.ok(events.includes("15/06/2030"));
  assert.ok(events.includes('data-action="participants-event"'));
  assert.ok(Core.renderEventRows([]).includes("No hay eventos"));

  const table = Core.renderParticipantsTable(
    {
      title: "Charla",
      attending_count: 1,
      registrations: [
        { full_name: "Ana <i>", email: "ana@upa.edu.py", status: "attending", registered_at: "2030-06-01T10:00:00Z" },
      ],
    },
    { timeZone: "UTC" }
  );
  assert.ok(table.includes("ana@upa.edu.py"));
  assert.ok(table.includes("Ana &lt;i&gt;"));
  assert.ok(table.includes("1 inscritos"));
  assert.ok(Core.renderParticipantsTable({ title: "X", attending_count: 0, registrations: [] }).includes("Todavía no hay"));
});

test("describeSyncResult: estados success, skipped, sin novedades e inesperado", () => {
  const ok = Core.describeSyncResult({ status: "success", synced_count: 5, created_count: 2, updated_count: 3 });
  assert.equal(ok.type, "success");
  assert.match(ok.message, /5 publicaciones \(2 nuevas, 3 actualizadas\)/);
  assert.equal(Core.describeSyncResult({ status: "success", synced_count: 0 }).type, "info");
  const skipped = Core.describeSyncResult({ status: "skipped", message: "Sin credenciales" });
  assert.equal(skipped.type, "warning");
  assert.match(skipped.message, /Sin credenciales/);
  assert.equal(Core.describeSyncResult(null).type, "error");
});

test("extractDetailMessage: texto simple y lista de errores 422 de FastAPI", () => {
  assert.equal(Core.extractDetailMessage("Falla"), "Falla");
  assert.equal(
    Core.extractDetailMessage([{ loc: ["body", "event_start"], msg: "Field required" }]),
    "event_start: Field required"
  );
  assert.equal(Core.extractDetailMessage(undefined), "");
});

test("timeout: un servidor que no responde cancela la solicitud con ApiError timeout", async () => {
  const sockets = new Set();
  const server = net.createServer((socket) => {
    sockets.add(socket);
    socket.on("data", () => {}); // acepta la solicitud y nunca contesta
    socket.on("close", () => sockets.delete(socket));
    socket.on("error", () => {});
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  try {
    const client = Core.createClient({ baseUrl: `http://127.0.0.1:${port}`, getToken: () => "t", timeoutMs: 200 });
    const started = Date.now();
    await assert.rejects(
      () => client.listNews(),
      (err) => err instanceof Core.ApiError && err.kind === "timeout" && /demasiado/.test(err.message)
    );
    assert.ok(Date.now() - started < 3000, "el timeout debe disparar rapido");

    const upload = Core.createClient({
      baseUrl: `http://127.0.0.1:${port}`,
      getToken: () => "t",
      uploadTimeoutMs: 200,
    });
    await assert.rejects(
      () => upload.uploadMedia(new Blob([Buffer.from("89504e470d0a1a0a", "hex")], { type: "image/png" }), {}),
      (err) => err instanceof Core.ApiError && err.kind === "timeout"
    );
  } finally {
    sockets.forEach((s) => s.destroy());
    await new Promise((resolve) => server.close(resolve));
  }
});

test("red: un servidor inaccesible produce ApiError network", async () => {
  const probe = net.createServer();
  await new Promise((resolve) => probe.listen(0, "127.0.0.1", resolve));
  const { port } = probe.address();
  await new Promise((resolve) => probe.close(resolve)); // el puerto queda cerrado
  const client = Core.createClient({ baseUrl: `http://127.0.0.1:${port}`, getToken: () => "t", timeoutMs: 2000 });
  await assert.rejects(
    () => client.listEvents(),
    (err) => err instanceof Core.ApiError && err.kind === "network" && /red/.test(err.message)
  );
});

test("modelo unificado: validatePublicationValues y buildPublicationPayload para hibrido, urgente e Instagram", () => {
  const hybrid = {
    title: "Jornada de puertas abiertas",
    postType: "MANUAL",
    hasRegistration: true,
    targetGroups: ["ALL", "TIE"],
    publishMode: "scheduled",
    publishedAt: "2030-08-10T09:00",
    isNews: true,
    notifyGroups: ["TIE"],
    caption: "Resumen",
    content: "Contenido principal",
    detailText: "Detalle exclusivo app",
    category: "VERANSTALTUNG",
    pinned: true,
    expiresAt: "2030-08-20T18:00",
    imageUrl: "/uploads/jornada.png",
    linkLabel: "Inscribirse",
    linkUrl: "https://upa.edu.py/jornada",
    isEvent: true,
    eventStart: "2030-08-15T10:00",
    eventEnd: "2030-08-15T13:00",
    location: "Campus San Lorenzo",
    eventNotifyGroups: ["TIE"],
    reminders: [60, 15, 15],
  };

  assert.deepEqual(Core.validatePublicationValues(hybrid), {});
  const payload = Core.buildPublicationPayload(hybrid);
  assert.equal(payload.is_news, true);
  assert.equal(payload.is_event, true);
  assert.equal(payload.has_registration, true);
  assert.equal(payload.detail_text, "Detalle exclusivo app");
  assert.equal(payload.link_label, "Inscribirse");
  assert.equal(payload.link_url, "https://upa.edu.py/jornada");
  assert.deepEqual(payload.reminders, [15, 60]);
  assert.ok(payload.published_at);

  // Al menos una seccion requerida
  assert.ok(Core.validatePublicationValues({ ...hybrid, isNews: false, isEvent: false }).section);

  // Eilmeldung no admite Evento
  assert.ok(Core.validatePublicationValues({ ...hybrid, postType: "EMERGENCY_BANNER", isEvent: true }).section);

  // Instagram bloquea fecha programada en payload (published_at -> null para conservar fecha original en backend)
  const igPayload = Core.buildPublicationPayload({ ...hybrid, postType: "INSTAGRAM" });
  assert.equal(igPayload.published_at, null);
  assert.equal(igPayload.is_news, true);

  // Vigencia obligatoria cuando se fija arriba (pinned: true)
  assert.ok(Core.validatePublicationValues({ ...hybrid, pinned: true, expiresAt: "" }).expiresAt);
  assert.deepEqual(Core.validatePublicationValues({ ...hybrid, pinned: false, expiresAt: "" }), {});

  // Deteccion automatica de VIDEO, resumen de 2 lineas de Instagram y unidades de recordatorio
  const videoPayload = Core.buildPublicationPayload({
    ...hybrid,
    imageUrl: "https://api.upa.edu.py/uploads/campus.mp4",
  });
  assert.equal(videoPayload.media_type, "VIDEO");
  assert.equal(
    Core.extractInstagramTeaser("Linea 1\nLinea 2\nLinea 3\nLinea 4"),
    "Linea 1\nLinea 2"
  );
  assert.deepEqual(Core.reminderToParts(30), { value: 30, unit: "minutes" });
  assert.deepEqual(Core.reminderToParts(120), { value: 2, unit: "hours" });
  assert.deepEqual(Core.reminderToParts(1440), { value: 1, unit: "days" });
  assert.equal(Core.partsToReminderMinutes(2, "hours"), 120);
  assert.equal(Core.partsToReminderMinutes(1, "days"), 1440);
});

test("renderPublicationRows y renderHistoryEntries muestran etiquetas, metricas y escapan XSS", () => {
  const html = Core.renderPublicationRows(
    [
      {
        id: 42,
        title: "Post <script>alert(1)</script>",
        summary: "Resumen",
        post_type: "INSTAGRAM",
        is_news: true,
        is_event: true,
        has_registration: true,
        views_count: 18,
        attending_count: 9,
        declined_count: 2,
        is_edited: false,
        published_at: "2030-06-15T12:00:00Z",
        event_start: "2030-06-20T15:00:00Z",
      },
    ],
    { timeZone: "UTC" }
  );
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("Noticias") && html.includes("Eventos"));
  assert.ok(html.includes("Instagram"));
  assert.ok(html.includes("Pendiente"));
  assert.ok(html.includes("18 vistas"));
  assert.ok(html.includes("9 inscritos / 2 bajas"));

  const hist = Core.renderHistoryEntries(
    [
      {
        admin_name: "Pascal <b>",
        verb: "editó",
        target_label: "Foro UPA",
        changes: ["título", "recordatorios"],
        created_at: "2030-06-15T12:00:00Z",
      },
      {
        admin_name: "Ana",
        verb: "creó",
        target_label: "Foro UPA",
        changes: [],
        created_at: "2030-06-14T09:00:00Z",
      },
    ],
    { showTarget: true, timeZone: "UTC" }
  );
  assert.ok(hist.includes("Historial"));
  assert.ok(hist.includes('<table class="ed-audit-table"'));
  assert.equal((hist.match(/<tr class="ed-audit-row">/g) || []).length, 2);
  assert.ok(hist.includes("Pascal &lt;b&gt;"));
  assert.ok(hist.includes("(título, recordatorios)"));
});

test("programacion diferida: rechaza fechas en el pasado y bloquea reprogramacion incoherente en publicaciones ya emitidas", () => {
  const base = {
    title: "Comunicado oficial",
    postType: "MANUAL",
    targetGroups: ["estudiantes"],
    publishMode: "scheduled",
    publishedAt: "2020-01-01T08:00",
    isNews: true,
    isEvent: false,
  };
  const errs = Core.validatePublicationValues(base);
  assert.ok(errs.publishedAt, "Una fecha de publicación programada en el pasado debe ser rechazada");

  const alreadyPublishedForm = Core.publicationToFormValues({
    id: 10,
    title: "Post ya publicado",
    post_type: "MANUAL",
    is_news: true,
    is_event: false,
    target_groups: ["estudiantes"],
    published_at: "2024-05-01T10:00:00Z",
  });
  assert.equal(alreadyPublishedForm.scheduled, false, "Un post ya publicado no debe abrirse como programado");
  assert.equal(alreadyPublishedForm.isPublished, true);

  const futureScheduledForm = Core.publicationToFormValues({
    id: 11,
    title: "Post futuro",
    post_type: "MANUAL",
    is_news: true,
    is_event: false,
    target_groups: ["estudiantes"],
    published_at: "2035-05-01T10:00:00Z",
  });
  assert.equal(futureScheduledForm.scheduled, true, "Un post con fecha futura debe abrirse como programado");
  assert.equal(futureScheduledForm.isPublished, false);
});

test("formatDateTime usa 24 horas sin a. m. / p. m. y historial muestra detalle de permisos", () => {
  const out = Core.formatDateTime("2030-06-15T14:15:00Z", { timeZone: "UTC" });
  assert.ok(out.includes("14:15"), out);
  assert.ok(!/[ap]\.?\s?m\.?/i.test(out), out);
  const night = Core.formatDateTime("2030-06-15T00:05:00Z", { timeZone: "UTC" });
  assert.ok(night.includes("00:05"), night);
  const hist = Core.renderHistoryEntries(
    [{ admin_name: "A", verb: "modificó", changes: ["permisos"], detail: "permisos: +publicaciones, -historial", created_at: "2030-06-15T14:15:00Z" }],
    { timeZone: "UTC" }
  );
  assert.ok(hist.includes("permisos: +publicaciones, -historial"));
});
