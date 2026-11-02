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
  assert.deepEqual(Core.PERMISSION_KEYS, ["publicaciones", "grupos", "roles", "apis", "ia", "historial"]);
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

test("validatePublicationValues: limites de longitud, categorias y tipos de medio", () => {
  const base = {
    title: "Titulo",
    postType: "MANUAL",
    isNews: true,
    isEvent: false,
    caption: "",
    content: "",
    category: "",
    targetGroups: ["ALL"],
  };
  assert.deepEqual(Core.validatePublicationValues(base), {});
  assert.ok(Core.validatePublicationValues({ ...base, title: "   " }).title);
  assert.ok(Core.validatePublicationValues({ ...base, title: "x".repeat(256) }).title);
  assert.ok(Core.validatePublicationValues({ ...base, caption: "x".repeat(301) }).caption);
  assert.ok(Core.validatePublicationValues({ ...base, category: "INVENTADA" }).category);
  assert.ok(Core.validatePublicationValues({ ...base, targetGroups: [] }).targetGroups);

  const pdfPayload = Core.buildPublicationPayload({
    ...base,
    imageUrl: "http://localhost/uploads/doc.pdf",
  });
  assert.equal(pdfPayload.media_type, "");
});

test("publicationToFormValues: reconstruye campos unificados de noticia y evento", () => {
  const startIso = new Date(2030, 5, 15, 10, 0).toISOString();
  const endIso = new Date(2030, 5, 15, 12, 30).toISOString();
  const values = Core.publicationToFormValues({
    id: 5,
    title: "Charla",
    caption: "B",
    content: "C",
    category: "MELDUNG",
    target_groups: ["ALL", "Semester_4"],
    post_type: "MANUAL",
    is_news: true,
    is_event: true,
    event_start: startIso,
    event_end: endIso,
    location: "Auditorio",
    has_registration: true,
    is_pinned: false,
    media_url: "/uploads/x.png",
  });
  assert.deepEqual(values.targetGroups, ["ALL", "Semester_4"]);
  assert.equal(values.caption, "B");
  assert.equal(values.imageUrl, "/uploads/x.png");
  assert.equal(values.isEvent, true);
  assert.equal(values.hasRegistration, true);
  assert.equal(values.eventStart, "15/06/2030 10:00");
  assert.equal(values.eventEnd, "12:30");

  // Sin event_end definido, el campo Fin del evento queda vacio (sin pre-relleno automatico)
  const withoutEnd = Core.publicationToFormValues({
    id: 6,
    title: "Charla sin hora de fin",
    is_news: false,
    is_event: true,
    event_start: startIso,
    event_end: null,
  });
  assert.equal(withoutEnd.eventStart, "15/06/2030 10:00");
  assert.equal(withoutEnd.eventEnd, "");
});

test("fecha y hora locales: formato paraguayo DD/MM/YYYY, reloj 24h HH:mm y validacion de horas invalidas", () => {
  const iso = Core.localDateTimeToIso("2030-06-15", "14:30");
  assert.equal(iso, new Date(2030, 5, 15, 14, 30).toISOString());
  assert.equal(Core.localDateTimeToIso("15/06/2030", "14:30"), iso);
  assert.deepEqual(Core.isoToLocalParts(iso), { date: "2030-06-15", time: "14:30" });
  assert.equal(Core.isoToParaguayDateTime(iso), "15/06/2030 14:30");
  assert.equal(Core.isoToTime24(iso), "14:30");
  assert.equal(Core.datetimeLocalToIso("15/06/2030 14:30"), iso);
  assert.equal(Core.localDateTimeToIso("", "14:30"), null);
  assert.equal(Core.localDateTimeToIso("2030-13-45", "14:30"), null);
  assert.equal(Core.localDateTimeToIso("45/13/2030", "14:30"), null);
  assert.equal(Core.localDateTimeToIso("2030-06-15", "25:99"), null);
  assert.equal(Core.localDateTimeToIso("2030-02-31", "10:00"), null);
  assert.equal(Core.localDateTimeToIso("31/02/2030", "10:00"), null);

  // Mascaras progresivas de entrada (DD/MM/YYYY HH:mm y HH:mm)
  assert.equal(Core.maskDateTimeInput("251120261830"), "25/11/2026 18:30");
  assert.equal(Core.maskTime24Input("1830"), "18:30");
  assert.equal(Core.isValidTime24("00:00"), true);
  assert.equal(Core.isValidTime24("23:59"), true);
  assert.equal(Core.isValidTime24("24:00"), false);
  assert.equal(Core.isValidTime24("25:99"), false);
  assert.equal(Core.isValidTime24("10:00 PM"), false);

  // Errores claros de validacion ante fechas u horas invalidas en eventos
  const invalidStartErrs = Core.validatePublicationValues({
    title: "Evento",
    postType: "MANUAL",
    targetGroups: ["ALL"],
    isNews: false,
    isEvent: true,
    eventStart: "31/02/2026 25:99",
    eventEnd: "",
  });
  assert.equal(invalidStartErrs.eventStart, Core.TEXTS.errEventStartInvalid);

  const invalidEndTimeErrs = Core.validatePublicationValues({
    title: "Evento",
    postType: "MANUAL",
    targetGroups: ["ALL"],
    isNews: false,
    isEvent: true,
    eventStart: "15/08/2030 14:00",
    eventEnd: "25:99",
  });
  assert.equal(invalidEndTimeErrs.eventEnd, Core.TEXTS.errEventEndInvalid);

  const endBeforeStartErrs = Core.validatePublicationValues({
    title: "Evento",
    postType: "MANUAL",
    targetGroups: ["ALL"],
    isNews: false,
    isEvent: true,
    eventStart: "15/08/2030 14:00",
    eventEnd: "12:30",
  });
  assert.equal(endBeforeStartErrs.eventEnd, Core.TEXTS.errEndBeforeStart);
});

test("safeUrl y renderPublicationRows escapan HTML hostil y descartan URLs peligrosas", () => {
  const html = Core.renderPublicationRows([
    {
      id: 7,
      title: "<script>alert('x')</script>",
      caption: '"><img src=x onerror=alert(1)>',
      category: "MELDUNG",
      post_type: "EMERGENCY_BANNER",
      is_news: true,
      is_event: false,
      target_groups: ["<b>ALL</b>"],
      media_url: "javascript:alert(1)",
    },
  ]);
  assert.ok(!html.includes("<script>"), "no debe quedar un <script> sin escapar");
  assert.ok(!html.includes("<img src=x"), "no debe quedar una etiqueta img inyectada");
  assert.ok(!html.includes("javascript:"), "la URL javascript: no debe renderizarse");
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(html.includes("Aviso urgente"));
  assert.ok(html.includes('data-pub-id="7"'));
  assert.equal(Core.safeUrl("javascript:alert(1)"), "");
  assert.equal(Core.safeUrl("//evil.test/x.png"), "");
  assert.equal(Core.safeUrl("/uploads/a.png"), "/uploads/a.png");
  assert.equal(Core.safeUrl("https://ok.test/a.png"), "https://ok.test/a.png");
});

test("renderParticipantsTable muestra datos reales y estados vacios", () => {
  const table = Core.renderParticipantsTable(
    {
      title: "Charla",
      attending_count: 1,
      declined_count: 1,
      registrations: [
        { full_name: "Ana <i>", email: "ana@upa.edu.py", status: "attending", registered_at: "2030-06-01T10:00:00Z" },
        { full_name: "Luis", email: "luis@upa.edu.py", status: "declined", registered_at: "2030-06-01T11:00:00Z" },
      ],
    },
    { timeZone: "UTC" }
  );
  assert.ok(table.includes("ana@upa.edu.py"));
  assert.ok(table.includes("Ana &lt;i&gt;"));
  assert.ok(table.includes("1 inscritos"));
  assert.ok(table.includes("1 no asisten"));
  assert.ok(table.includes("No asiste"));
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
      () => client.listPublications(),
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
    () => client.listPublications(),
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
  assert.ok(html.includes("9 inscritos / 2 no asisten"));

  const aiHtml = Core.renderPublicationRows(
    [
      {
        id: 43,
        title: "Evento extraído con IA",
        summary: "Charla en Aula Magna",
        post_type: "INSTAGRAM",
        is_news: true,
        is_event: true,
        is_edited: false,
        is_ai_generated: true,
        status: "ai",
        published_at: "2030-06-15T12:00:00Z",
        event_start: "2030-06-20T15:00:00Z",
      },
    ],
    { timeZone: "UTC" }
  );
  assert.ok(aiHtml.includes("ed-badge-ai"));
  assert.ok(aiHtml.includes(">IA<"));

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

test("autocompletar con IA: applyAiSuggestionsToFormValues completa solo campos vacios y preserva los existentes", () => {
  assert.equal(Core.TEXTS.aiAutocompleteButton, "Autocompletar con IA");
  assert.equal(Core.TEXTS.aiAutocompleteBusy, "Analizando contenido e imagen...");
  assert.equal(Core.TEXTS.aiAutocompleteSuccess, "Campos completados por IA");
  assert.equal(
    Core.TEXTS.aiAutocompleteError,
    "No se pudo autocompletar: Verifique la clave de IA en Control de IA"
  );

  assert.equal(Core.normalizeAiDatetimeLocal("2026-11-20T18:30"), "20/11/2026 18:30");
  assert.equal(Core.normalizeAiDatetimeLocal("2026-11-20 18:30:00"), "20/11/2026 18:30");
  assert.equal(Core.normalizeAiDatetimeLocal("2026-11-20"), "20/11/2026 09:00");
  assert.equal(Core.normalizeAiTime24("2026-11-20T20:00"), "20:00");
  assert.equal(Core.normalizeAiTime24("20:00"), "20:00");

  const currentForm = {
    title: "Título ya escrito por el editor",
    postType: "MANUAL",
    hasRegistration: false,
    targetGroups: [],
    isNews: true,
    caption: "",
    content: "Charla el 20 de noviembre a las 18:30 en el Auditorio Central.",
    linkLabel: "",
    linkUrl: "",
    isEvent: false,
    eventStart: "",
    eventEnd: "",
    location: "",
  };

  const aiSuggestions = {
    title: "Título de la IA que debe ignorarse",
    caption: "Resumen breve sugerido por IA",
    content: "Contenido de la IA que debe ignorarse",
    is_event: true,
    event_start: "2026-11-20T18:30",
    event_end: "2026-11-20T20:00",
    location: "Auditorio Central",
    target_groups: ["TIE", "TI"],
    has_registration: true,
    link_label: "Inscribirse aquí",
    link_url: "https://upa.edu.py/inscripcion",
  };

  const merged = Core.applyAiSuggestionsToFormValues(currentForm, aiSuggestions);
  assert.equal(merged.title, "Título ya escrito por el editor", "No debe sobreescribir el título existente");
  assert.equal(
    merged.content,
    "Charla el 20 de noviembre a las 18:30 en el Auditorio Central.",
    "No debe sobreescribir el contenido existente"
  );
  assert.equal(merged.caption, "Resumen breve sugerido por IA");
  assert.equal(merged.isEvent, true);
  assert.equal(merged.eventStart, "20/11/2026 18:30");
  assert.equal(merged.eventEnd, "20:00");
  assert.equal(merged.location, "Auditorio Central");
  assert.deepEqual(merged.targetGroups, ["TIE", "TI"]);
  assert.equal(merged.hasRegistration, true);
  assert.equal(merged.linkLabel, "Inscribirse aquí");
  assert.equal(merged.linkUrl, "https://upa.edu.py/inscripcion");

  // Si el usuario ya había elegido grupos destinatarios y lugar, tampoco se sobreescriben
  const withGroupsAndLoc = {
    ...currentForm,
    targetGroups: ["PI"],
    location: "Sala de Conferencias 2",
  };
  const mergedPreserved = Core.applyAiSuggestionsToFormValues(withGroupsAndLoc, aiSuggestions);
  assert.deepEqual(mergedPreserved.targetGroups, ["PI"]);
  assert.equal(mergedPreserved.location, "Sala de Conferencias 2");

  // SRV-229: Si solo hay título sin imagen ni texto base (caption/content), no se inventan eventos ni textos
  const titleOnlyForm = {
    title: "Solo un título mínimo",
    postType: "MANUAL",
    hasRegistration: false,
    targetGroups: [],
    isNews: true,
    caption: "",
    content: "",
    imageUrl: "",
    isEvent: false,
    eventStart: "",
    eventEnd: "",
    location: "",
  };
  const mergedTitleOnly = Core.applyAiSuggestionsToFormValues(titleOnlyForm, aiSuggestions);
  assert.equal(mergedTitleOnly.isEvent, false);
  assert.equal(mergedTitleOnly.eventStart, "");
  assert.equal(mergedTitleOnly.eventEnd, "");
  assert.equal(mergedTitleOnly.location, "");
  assert.equal(mergedTitleOnly.caption, "");
  assert.equal(mergedTitleOnly.content, "");
  assert.equal(mergedTitleOnly.hasRegistration, false);

  // SRV-232: RSVP por defecto al detectar un evento incluso si has_registration no viene en la sugerencia,
  // y recordatorios de fin de semana ([1440, 30]) para sábado/domingo vs [30] de lunes a viernes
  assert.deepEqual(Core.defaultRemindersForEventStart("28/11/2026 18:00"), [1440, 30]); // Sábado
  assert.deepEqual(Core.defaultRemindersForEventStart("29/11/2026 10:00"), [1440, 30]); // Domingo
  assert.deepEqual(Core.defaultRemindersForEventStart("2026-11-28T18:00"), [1440, 30]); // Sábado ISO
  assert.deepEqual(Core.defaultRemindersForEventStart("25/11/2026 18:30"), [30]); // Miércoles
  assert.deepEqual(Core.defaultRemindersForEventStart("27/11/2026 18:00"), [30]); // Viernes

  const weekendSuggestionsWithoutRsvpFlag = {
    caption: "Jornada sabatina UPA",
    is_event: true,
    event_start: "2026-11-28T10:00",
    location: "Campus UPA",
  };
  const mergedWeekend = Core.applyAiSuggestionsToFormValues(currentForm, weekendSuggestionsWithoutRsvpFlag);
  assert.equal(mergedWeekend.isEvent, true);
  assert.equal(mergedWeekend.hasRegistration, true);
  assert.deepEqual(mergedWeekend.reminders, [1440, 30]);

  const nonEventSuggestions = {
    caption: "Comunicado institucional sin evento",
    is_event: false,
  };
  const mergedNonEvent = Core.applyAiSuggestionsToFormValues(currentForm, nonEventSuggestions);
  assert.equal(mergedNonEvent.isEvent, false);
  assert.equal(mergedNonEvent.hasRegistration, false);
});

test("DOM Publicaciones Editor: boton Autocompletar con IA muestra estado de carga, rellena solo campos vacios y maneja errores", async () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const { JSDOM } = require("jsdom");

  const webAdminDir = path.resolve(__dirname, "..");
  let html = fs.readFileSync(path.join(webAdminDir, "index.html"), "utf8");
  html = html.replace(/<script\s+src="[^"]*"><\/script>/g, "");

  const dom = new JSDOM(html, {
    url: "http://127.0.0.1:8185/dashboard/publicaciones",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const { window } = dom;
  const { document } = window;

  let autocompleteMode = "success";
  let aiConfiguredState = false;
  let lastAutocompleteBody = null;
  let busyTextObserved = "";

  window.AbortController = AbortController;
  window.FormData = FormData;
  window.File = File;
  window.Blob = Blob;
  window.confirm = () => true;
  window.alert = () => {};
  window.Element.prototype.scrollIntoView = function () {};
  window.localStorage.setItem("upa_access_token", "test-jwt-token");

  window.fetch = async (input, init) => {
    const url = String(input);
    if (url.endsWith("/api/auth/me")) {
      return new Response(
        JSON.stringify({
          id: 1,
          email: "pascal.thommen@upa.edu.py",
          full_name: "Pascal Thommen",
          role: "admin",
          permissions: ["publicaciones", "grupos", "roles", "apis", "historial"],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    if (url.includes("/api/ai/config")) {
      return new Response(
        JSON.stringify({
          configured: aiConfiguredState,
          masked_key: aiConfiguredState ? "AIza********1234" : "",
          source: aiConfiguredState ? "database" : "none",
          model: "gemini-1.5-flash",
          system_prompt: "Eres el asistente editorial inteligente de la UPA.",
          system_prompt_autocomplete: "Eres el asistente editorial inteligente de la UPA.",
          system_prompt_instagram: "Eres el analizador multimodal de Instagram de la UPA.",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    if (url.includes("/api/groups")) {
      return new Response(
        JSON.stringify([
          { id: "ALL", name: "Toda la comunidad UPA" },
          { id: "TIE", name: "Ingeniería Empresarial" },
          { id: "TI", name: "Tecnologías de la Información" },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    if (url.includes("/api/publications/autocomplete-ai")) {
      const btn = document.getElementById("ed-pub-autocomplete-ai");
      busyTextObserved = btn ? btn.textContent.trim() : "";
      lastAutocompleteBody = init && init.body ? JSON.parse(init.body) : {};
      if (autocompleteMode === "error") {
        return new Response(
          JSON.stringify({
            detail: "No se pudo autocompletar: Verifique la clave de IA en Control de IA.",
          }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response(
        JSON.stringify({
          caption: "Resumen generado por Gemini",
          is_event: true,
          event_start: "2026-11-25T18:30",
          event_end: "2026-11-25T20:00",
          location: "Auditorio Central",
          target_groups: ["TIE"],
          has_registration: true,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response(JSON.stringify([]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  for (const script of ["editorial-core.js", "editorial.js"]) {
    window.eval(fs.readFileSync(path.join(webAdminDir, script), "utf8"));
  }

  window.UpaCockpit.configure({ getToken: () => "test-jwt-token" });
  window.UpaCockpit.onUserLoaded({
    id: 1,
    email: "pascal.thommen@upa.edu.py",
    role: "admin",
    permissions: ["publicaciones", "grupos", "roles", "apis", "historial"],
  });
  await window.UpaCockpit.openNewPublication();

  const aiBtn = document.getElementById("ed-pub-autocomplete-ai");
  assert.ok(aiBtn, "El botón Autocompletar con IA debe existir en el editor");
  assert.equal(aiBtn.textContent.trim(), "Autocompletar con IA");

  // 1. Sin token de Gemini configurado: botón deshabilitado, gris y con tooltip explicativo
  assert.equal(aiBtn.disabled, true);
  assert.equal(aiBtn.getAttribute("aria-disabled"), "true");
  assert.ok(aiBtn.classList.contains("is-disabled"));
  assert.ok(aiBtn.getAttribute("title").includes("Configure un token válido de Gemini"));
  assert.equal(document.getElementById("ed-pub-event-end").value, "");

  // 2. Al configurar token válido de Gemini: botón se habilita
  aiConfiguredState = true;
  await window.UpaCockpit.openNewPublication();
  assert.equal(aiBtn.disabled, false);
  assert.equal(aiBtn.getAttribute("aria-disabled"), "false");
  assert.ok(!aiBtn.classList.contains("is-disabled"));

  // Si el usuario pulsa Autocompletar con solo un título (sin afiche/foto ni texto base), recibe aviso informativo y no se inventan fechas
  document.getElementById("ed-pub-title").value = "Solo título sin contexto";
  aiBtn.click();
  await new Promise((r) => setTimeout(r, 50));
  assert.equal(document.getElementById("ed-pub-is-event").checked, false);
  assert.equal(document.getElementById("ed-pub-event-start").value, "");
  assert.equal(document.getElementById("ed-pub-caption").value, "");
  assert.equal(document.getElementById("ed-notice").textContent, Core.TEXTS.aiAutocompleteContextHint);

  // El usuario ingresa título y contenido, dejando el resto vacío
  document.getElementById("ed-pub-title").value = "Seminario de Robótica (Usuario)";
  document.getElementById("ed-pub-content").value = "El 25 de noviembre a las 18:30 hs en el Auditorio Central para TIE.";

  aiBtn.click();
  await new Promise((r) => setTimeout(r, 50));

  assert.equal(busyTextObserved, "Analizando contenido e imagen...");
  assert.equal(aiBtn.disabled, false);
  assert.equal(aiBtn.textContent.trim(), "Autocompletar con IA");
  assert.equal(lastAutocompleteBody.title, "Seminario de Robótica (Usuario)");

  // Verificar que los campos del usuario se conservaron y los vacíos se completaron en DD/MM/YYYY HH:mm y HH:mm
  assert.equal(document.getElementById("ed-pub-title").value, "Seminario de Robótica (Usuario)");
  assert.equal(document.getElementById("ed-pub-caption").value, "Resumen generado por Gemini");
  assert.equal(document.getElementById("ed-pub-is-event").checked, true);
  assert.equal(document.getElementById("ed-pub-event-start").value, "25/11/2026 18:30");
  assert.equal(document.getElementById("ed-pub-event-end").value, "20:00");
  assert.equal(document.getElementById("ed-pub-location").value, "Auditorio Central");
  assert.equal(document.getElementById("ed-pub-rsvp").checked, true);
  const checkedGroups = Array.from(
    document.querySelectorAll("#ed-pub-target-groups input[type=checkbox]:checked")
  ).map((el) => el.value);
  assert.deepEqual(checkedGroups, ["TIE"]);
  assert.equal(document.getElementById("ed-notice").textContent, "Campos completados por IA");

  // 3. Validación en vivo de horas inválidas en los campos de evento
  const endInput = document.getElementById("ed-pub-event-end");
  endInput.value = "25:99";
  endInput.dispatchEvent(new window.Event("blur"));
  assert.equal(
    document.querySelector('[data-error-for="pub-eventEnd"]').textContent,
    Core.TEXTS.errEventEndInvalid
  );

  // 4. Caso de error en llamada a IA (cuota agotada o clave revocada)
  autocompleteMode = "error";
  aiBtn.click();
  await new Promise((r) => setTimeout(r, 50));
  assert.ok(
    document
      .getElementById("ed-notice")
      .textContent.includes("No se pudo autocompletar: Verifique la clave de IA en Control de IA")
  );

  // 5. SRV-232: Activar Evento manualmente activa RSVP por defecto; fecha en fin de semana fija [1440, 30]
  await window.UpaCockpit.openNewPublication();
  assert.equal(document.getElementById("ed-pub-rsvp").checked, false);
  const isEventCheckbox = document.getElementById("ed-pub-is-event");
  isEventCheckbox.checked = true;
  isEventCheckbox.dispatchEvent(new window.Event("change"));
  assert.equal(document.getElementById("ed-pub-rsvp").checked, true);

  const startInput = document.getElementById("ed-pub-event-start");
  startInput.value = "28/11/2026 10:00"; // Sábado
  startInput.dispatchEvent(new window.Event("change"));
  const reminderRowsSat = document.querySelectorAll("#ed-reminders-list [data-reminder-row]");
  assert.equal(reminderRowsSat.length, 2);
  assert.equal(reminderRowsSat[0].querySelector("input[data-reminder-value]").value, "1");
  assert.equal(reminderRowsSat[0].querySelector("select[data-reminder-unit]").value, "days");
  assert.equal(reminderRowsSat[1].querySelector("input[data-reminder-value]").value, "30");
  assert.equal(reminderRowsSat[1].querySelector("select[data-reminder-unit]").value, "minutes");

  startInput.value = "25/11/2026 10:00"; // Miércoles
  startInput.dispatchEvent(new window.Event("change"));
  const reminderRowsWed = document.querySelectorAll("#ed-reminders-list [data-reminder-row]");
  assert.equal(reminderRowsWed.length, 1);
  assert.equal(reminderRowsWed[0].querySelector("input[data-reminder-value]").value, "30");
  assert.equal(reminderRowsWed[0].querySelector("select[data-reminder-unit]").value, "minutes");

  // 6. SRV-232: Dropzone usa URL.createObjectURL(file) para vista previa inmediata sin icono roto
  let createdBlobUrl = "";
  window.URL.createObjectURL = () => {
    createdBlobUrl = "blob:http://127.0.0.1:8185/local-preview-123";
    return createdBlobUrl;
  };
  window.URL.revokeObjectURL = () => {};
  const origFetch = window.fetch;
  window.fetch = async (input, init) => {
    const url = String(input);
    if (url.includes("/api/media/upload")) {
      return new Response(
        JSON.stringify({
          url: "/uploads/abcdef1234567890abcdef1234567890.png",
          filename: "abcdef1234567890abcdef1234567890.png",
          content_type: "image/png",
          size_bytes: 128,
        }),
        { status: 201, headers: { "Content-Type": "application/json" } }
      );
    }
    return origFetch(input, init);
  };

  const dzZone = document.querySelector('[data-dropzone="pub"]');
  const testImgFile = new window.File([new Uint8Array([137, 80, 78, 71])], "afiche-evento.png", {
    type: "image/png",
  });
  const dropEvt = new window.Event("drop");
  Object.defineProperty(dropEvt, "dataTransfer", {
    value: { files: [testImgFile] },
  });
  dzZone.dispatchEvent(dropEvt);
  await new Promise((r) => setTimeout(r, 50));

  const previewImg = dzZone.querySelector("[data-dz-preview] img");
  assert.ok(previewImg, "Debe renderizar la etiqueta <img> en la vista previa del dropzone");
  assert.equal(previewImg.getAttribute("src"), "/uploads/abcdef1234567890abcdef1234567890.png");
  assert.equal(document.getElementById("ed-pub-image-url").value, "/uploads/abcdef1234567890abcdef1234567890.png");

  window.close();
});
