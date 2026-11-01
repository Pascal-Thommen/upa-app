/**
 * Pruebas unitarias de `campus-core.js`: logica de fechas, ordenamiento, temas, QR decodificable,
 * gestor de superposiciones (boton Atras) y cliente de red con servidores TCP reales.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const net = require("node:net");
const jsQR = require("jsqr");

const Core = require("../campus-core.js");
const qrcode = require("../vendor/qrcode.js");

test("isMobileEnvironment: distingue escritorio, movil, iPadOS, standalone y parametro ?app=1", () => {
  assert.equal(
    Core.isMobileEnvironment({
      userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0",
      platform: "Linux x86_64",
      maxTouchPoints: 0,
      coarsePointer: false,
      width: 1440,
      search: "",
    }),
    false,
  );
  assert.equal(
    Core.isMobileEnvironment({
      userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/120.0 Mobile",
      width: 412,
    }),
    true,
  );
  assert.equal(
    Core.isMobileEnvironment({
      userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) Version/17.2 Mobile/15E148 Safari/604.1",
      width: 390,
    }),
    true,
  );
  assert.equal(
    Core.isMobileEnvironment({
      userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
      platform: "MacIntel",
      maxTouchPoints: 5,
      width: 820,
    }),
    true,
  );
  assert.equal(Core.isMobileEnvironment({ userAgent: "Mozilla/5.0", standalone: true }), true);
  assert.equal(Core.isMobileEnvironment({ userAgent: "Mozilla/5.0", search: "?app=1" }), true);

  assert.equal(Core.isBetaEnvironment({ hostname: "upa-beta.eu1.netbird.services", port: "" }), true);
  assert.equal(Core.isBetaEnvironment({ hostname: "localhost", port: "8185" }), true);
  assert.equal(Core.isBetaEnvironment({ hostname: "localhost", port: "8085" }), false);
  assert.equal(Core.isBetaEnvironment({ hostname: "upa.eu1.netbird.services", port: "" }), false);
  assert.equal(Core.isBetaEnvironment({ hostname: "localhost", port: "8085", search: "?env=beta" }), true);
  assert.equal(Core.isBetaEnvironment({ hostname: "localhost", port: "8085", appEnv: "beta" }), true);
});

test("buildQr: genera un SVG valido cuya matriz es leida por un lector QR real (jsQR)", () => {
  const url = "https://upa-beta.eu1.netbird.services/";
  const qr = Core.buildQr(url, qrcode, { margin: 4 });
  assert.match(qr.svg, /^<svg /);
  assert.match(qr.svg, /viewBox="0 0 \d+ \d+"/);

  const scale = 6;
  const side = qr.size * scale;
  const rgba = new Uint8ClampedArray(side * side * 4);
  for (let y = 0; y < side; y += 1) {
    for (let x = 0; x < side; x += 1) {
      const r = Math.floor(y / scale) - qr.margin;
      const c = Math.floor(x / scale) - qr.margin;
      const dark = r >= 0 && c >= 0 && r < qr.modules && c < qr.modules && qr.matrix[r][c];
      const v = dark ? 0 : 255;
      const idx = (y * side + x) * 4;
      rgba[idx] = v;
      rgba[idx + 1] = v;
      rgba[idx + 2] = v;
      rgba[idx + 3] = 255;
    }
  }
  const decoded = jsQR(rgba, side, side);
  assert.ok(decoded, "jsQR debe decodificar la imagen generada");
  assert.equal(decoded.data, url);
});

test("sortFeed y normalizeFeed: fijados arriba y luego orden cronologico descendente", () => {
  const raw = {
    urgent_banners: [{ id: 99, title: "Suspension por tormenta", post_type: "EMERGENCY_BANNER" }],
    posts: [
      { id: 1, title: "Antigua", is_pinned: false, published_at: "2026-10-10T10:00:00Z" },
      { id: 2, title: "Fijada antigua", is_pinned: true, published_at: "2026-10-05T10:00:00Z" },
      { id: 3, title: "Reciente", is_pinned: false, published_at: "2026-10-25T10:00:00Z" },
      { id: 4, title: "Fijada reciente", is_pinned: true, published_at: "2026-10-20T10:00:00Z" },
    ],
  };
  const norm = Core.normalizeFeed(raw);
  assert.equal(norm.banners.length, 1);
  assert.deepEqual(
    norm.posts.map((p) => p.id),
    [4, 2, 3, 1],
  );
  const merged = Core.mergePosts(norm.posts, [
    { id: 3, title: "Duplicada", is_pinned: false, published_at: "2026-10-25T10:00:00Z" },
    { id: 5, title: "Mas reciente", is_pinned: false, published_at: "2026-10-29T10:00:00Z" },
  ]);
  assert.deepEqual(
    merged.map((p) => p.id),
    [4, 2, 5, 3, 1],
  );
});

test("Agenda: agrupa eventos y entregas en horario de Asuncion, filtra por dia y marca el calendario", () => {
  const agenda = {
    events: [
      {
        id: 10,
        title: "Charla de IA",
        description: "Auditorio",
        event_start: "2026-11-05T14:00:00Z", // 11:00 en Asuncion (UTC-3)
        event_end: "2026-11-05T15:00:00Z",
        location: "Edificio 1",
        has_registration: true,
        is_registered: false,
        registered_count: 4,
      },
    ],
    deadlines: [
      {
        id: "dl-1",
        title: "Entrega TP2",
        description: "Subir PDF",
        course_name: "Ingenieria de Software",
        due_date_formatted: "2026-11-05 23:59", // 20:59 en Asuncion
        alternate_link: "https://classroom.google.com/c/1/a/2/details",
      },
      {
        id: "dl-2",
        title: "Lectura previa",
        course_name: "Economia",
        due_date_formatted: "2026-11-02",
        alternate_link: "https://classroom.google.com/c/3/a/4/details",
      },
    ],
  };
  const entries = Core.buildAgendaEntries(agenda);
  assert.equal(entries.length, 3);
  assert.equal(entries[0].id, "dl-2");
  assert.equal(entries[1].id, 10);
  assert.equal(entries[1].timeLabel, "11:00");
  assert.equal(entries[1].endTimeLabel, "12:00");
  assert.equal(entries[1].timeRange, "11:00 - 12:00");
  assert.equal(entries[2].id, "dl-1");
  assert.equal(entries[2].link, "https://classroom.google.com/c/1/a/2/details");

  const sched = Core.formatEventSchedule("2026-11-05T14:00:00Z", "2026-11-05T15:30:00Z");
  assert.equal(sched.dayKey, "2026-11-05");
  assert.equal(sched.day, "5");
  assert.equal(sched.startTime, "11:00");
  assert.equal(sched.endTime, "12:30");
  assert.equal(sched.timeRange, "11:00 - 12:30");

  assert.equal(Core.upcomingEntries(entries, "2026-11-04").length, 2);
  assert.equal(Core.entriesForDay(entries, "2026-11-05").length, 2);
  const grouped = Core.groupAgendaByMonth([
    ...entries,
    {
      key: "event:99",
      kind: "event",
      id: 99,
      title: "Cierre de semestre",
      dayKey: "2026-12-10",
      sortKey: "2026-12-10 09:00",
    },
  ]);
  assert.equal(grouped.length, 2);
  assert.equal(grouped[0].monthKey, "2026-11");
  assert.equal(grouped[0].entries.length, 3);
  assert.equal(grouped[1].monthKey, "2026-12");
  assert.equal(grouped[1].entries.length, 1);
  assert.deepEqual(Core.markedDays(entries), {
    "2026-11-02": { event: false, deadline: true },
    "2026-11-05": { event: true, deadline: true },
  });

  const updated = Core.applyRegistration(entries, { id: 10, is_registered: true, registered_count: 5 });
  assert.equal(updated[1].raw.is_registered, true);
  assert.equal(updated[1].raw.registered_count, 5);
  assert.equal(updated[1].isRegistered, true);
  assert.equal(updated[1].registeredCount, 5);
  assert.equal(entries[2].dueLabel, "Vence 23:59 hs");
  assert.equal(entries[2].courseName, "Ingenieria de Software");

  // Filtro estricto de linea de tiempo futura (sin fallback a diciembre 2024) y carga explicita de mes pasado
  const withHistorical2024 = Core.buildAgendaEntries({
    events: [],
    deadlines: [
      {
        id: "hist-2024",
        title: "Tarea Antigua 2024",
        course_name: "Matematica I",
        due_date_formatted: "2024-12-15 23:59",
        alternate_link: "https://classroom.google.com/c/2024",
      },
    ],
  });
  assert.equal(
    Core.filterAgendaTimeline(withHistorical2024, {
      todayKey: "2026-11-01",
      month: { year: 2026, monthIndex: 10 },
    }).length,
    0,
    "No debe hacer fallback a entradas historicas de 2024 cuando no hay eventos futuros",
  );
  const pastDec2024 = Core.filterAgendaTimeline(withHistorical2024, {
    todayKey: "2026-11-01",
    month: { year: 2024, monthIndex: 11 },
  });
  assert.equal(pastDec2024.length, 1);
  assert.equal(pastDec2024[0].id, "hist-2024");
});

test("monthGrid y shiftMonth: semanas de lunes a domingo", () => {
  const weeks = Core.monthGrid(2026, 9); // octubre 2026: el dia 1 es jueves
  assert.equal(weeks[0][0].key, "2026-09-28");
  assert.equal(weeks[0][3].key, "2026-10-01");
  assert.equal(weeks[0][3].inMonth, true);
  assert.deepEqual(Core.shiftMonth(2026, 0, -1), { year: 2025, monthIndex: 11 });
  assert.deepEqual(Core.shiftMonth(2026, 11, 1), { year: 2027, monthIndex: 0 });
});

test("Temas (3 opciones) y banner de instalacion (Android con prompt, iOS con guia, 14 dias de pausa)", () => {
  assert.equal(Core.normalizeTheme("invalid"), "system");
  assert.equal(Core.resolveTheme("system", true), "dark");
  assert.equal(Core.resolveTheme("system", false), "light");
  assert.equal(Core.resolveTheme("dark", false), "dark");
  assert.equal(Core.resolveTheme("light", true), "light");

  const now = 1_700_000_000_000;
  assert.equal(Core.shouldShowInstallBanner({ platform: "ios", now }), true);
  assert.equal(Core.shouldShowInstallBanner({ platform: "android", hasPrompt: false, now }), false);
  assert.equal(Core.shouldShowInstallBanner({ platform: "android", hasPrompt: true, now }), true);
  assert.equal(Core.shouldShowInstallBanner({ platform: "ios", dismissedAt: now - 1000, now }), false);
  assert.equal(
    Core.shouldShowInstallBanner({ platform: "ios", dismissedAt: now - Core.INSTALL_DISMISS_MS - 1, now }),
    true,
  );
});

test("Sesion, JWT, roles, URLs seguras y avisos proximos", () => {
  const exp = Math.floor(Date.now() / 1000) + 3600;
  const payload = Buffer.from(JSON.stringify({ sub: "7", email: "ana@upa.edu.py", exp })).toString("base64url");
  const token = `eyJhbGciOiJIUzI1NiJ9.${payload}.firma`;
  assert.deepEqual(Core.parseAuthFragment(`#token=${token}`), { token, error: null });
  assert.deepEqual(Core.parseAuthFragment("#auth_error=forbidden_domain"), { token: null, error: "forbidden_domain" });
  assert.match(Core.translateAuthError("forbidden_domain"), /@upa\.edu\.py/);
  assert.equal(Core.isTokenExpired(token), false);
  assert.equal(Core.isTokenExpired(token, (exp + 10) * 1000), true);

  assert.equal(Core.roleLabel({ role: "admin", groups: ["ALL"] }), "Administración");
  assert.equal(Core.roleLabel({ role: "editor", groups: ["ALL"] }), "Redacción");
  assert.equal(Core.roleLabel({ role: "user", groups: ["ALL", "DOCENTES"] }), "Docente");
  assert.equal(Core.roleLabel({ role: "user", groups: ["ALL", "TIE"] }), "Estudiante");
  assert.equal(Core.initials("Carla María Rojas"), "CR");

  assert.equal(Core.safeUrl("javascript:alert(1)"), "");
  assert.equal(Core.safeUrl("//malicioso.example"), "");
  assert.equal(Core.safeUrl("/uploads/cartel.png"), "/uploads/cartel.png");
  assert.equal(Core.safeUrl("https://classroom.google.com/c/1"), "https://classroom.google.com/c/1");

  // Rich-Text Linkifier: URLs (http, https, bit.ly), Hashtags y proteccion estricta contra XSS
  assert.equal(Core.escapeHtml('<script>alert("xss")</script>'), "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;");
  const richHtml = Core.linkifyText(
    "Inscripciones en https://upa.edu.py/foro, http://portal.upa.edu.py o bit.ly/upa-2026. Sumate a #UPA y #Ingeniería2026!",
  );
  assert.match(
    richHtml,
    /<a class="rich-link" href="https:\/\/upa\.edu\.py\/foro" target="_blank" rel="noopener noreferrer">https:\/\/upa\.edu\.py\/foro<\/a>,/,
  );
  assert.match(
    richHtml,
    /<a class="rich-link" href="http:\/\/portal\.upa\.edu\.py" target="_blank" rel="noopener noreferrer">http:\/\/portal\.upa\.edu\.py<\/a>/,
  );
  assert.match(
    richHtml,
    /<a class="rich-link" href="https:\/\/bit\.ly\/upa-2026" target="_blank" rel="noopener noreferrer">bit\.ly\/upa-2026<\/a>\./,
  );
  assert.match(richHtml, /<span class="hashtag">#UPA<\/span>/);
  assert.match(richHtml, /<span class="hashtag">#Ingeniería2026<\/span>!/);

  const xssAttempt = Core.linkifyText(
    ' Texto malicioso <script>alert(1)</script> <img src=x onerror="alert(2)"> https://upa.edu.py/"><script>alert(3)</script> #UPA ',
  );
  assert.equal(xssAttempt.includes("<script>"), false);
  assert.equal(xssAttempt.includes("<img"), false);
  assert.match(xssAttempt, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(xssAttempt, /&lt;img src=x onerror=&quot;alert\(2\)&quot;&gt;/);
  assert.match(
    xssAttempt,
    /<a class="rich-link" href="https:\/\/upa\.edu\.py\/" target="_blank" rel="noopener noreferrer">https:\/\/upa\.edu\.py\/<\/a>&quot;&gt;&lt;script&gt;alert\(3\)&lt;\/script&gt;/,
  );

  // Origen de publicacion (Instagram vs Campus) y resumen sin duplicar primera linea
  assert.equal(Core.postOrigin({ post_type: "INSTAGRAM", is_event: true }), "instagram");
  assert.equal(Core.postOrigin({ post_type: "MANUAL", is_news: true }), "campus");
  assert.equal(Core.postOrigin({ post_type: "EMERGENCY_BANNER" }), "urgent");
  assert.equal(Core.originLabel("instagram"), "Instagram");
  assert.equal(Core.originLabel("campus"), "Campus");
  assert.equal(
    Core.postSummary({
      title: "En el marco del módulo de Comunicación Empresarial...",
      summary: "En el marco del módulo de Comunicación Empresarial, coordinado por la Prof. Norah Giménez.",
    }),
    "",
  );
  assert.equal(
    Core.postSummary({
      title: "Charla de Comunicación Empresarial",
      summary: "Charla de Comunicación Empresarial\nInvitada especial: Andrea Ferreira.",
    }),
    "Invitada especial: Andrea Ferreira.",
  );
  assert.equal(
    Core.postSummary({
      title: "Convocatoria Heidelberg",
      summary: "Postulaciones abiertas hasta noviembre.",
    }),
    "Postulaciones abiertas hasta noviembre.",
  );

  // Deduplicacion de botones de accion en el detalle (Instagram y enlaces identicos)
  const dupInsta = Core.resolveDetailLinks({
    kind: "instagram",
    postType: "INSTAGRAM",
    source: "https://www.instagram.com/p/Cxyz123/",
    sourceLabel: "Ver en Instagram",
    linkUrl: "https://www.instagram.com/p/Cxyz123",
    linkLabel: "Ver en Instagram",
  });
  assert.equal(dupInsta.length, 1);
  assert.equal(dupInsta[0].id, "detail-source");
  assert.equal(dupInsta[0].label, "Ver en Instagram");
  assert.equal(dupInsta[0].isInstagram, true);

  const eventFromInsta = Core.resolveDetailLinks({
    kind: "event",
    postType: "INSTAGRAM",
    source: "https://www.instagram.com/p/Cev999/",
    sourceLabel: "Ver en Instagram",
    linkUrl: "https://www.instagram.com/p/Cev999/",
    linkLabel: "Ver en Instagram",
  });
  assert.equal(eventFromInsta.length, 1);
  assert.equal(eventFromInsta[0].label, "Ver en Instagram");

  const distinctLinks = Core.resolveDetailLinks({
    kind: "news",
    postType: "MANUAL",
    source: "https://upa.edu.py/noticia",
    sourceLabel: "Ver fuente original",
    linkUrl: "https://forms.gle/inscripcion",
    linkLabel: "Formulario",
  });
  assert.equal(distinctLinks.length, 2);

  const nowMs = Date.parse("2026-11-05T10:00:00Z");
  const entries = [
    { key: "deadline:1", kind: "deadline", title: "TP", timeLabel: "20:59", date: new Date("2026-11-05T23:59:00Z"), raw: {} },
    { key: "event:2", kind: "event", title: "Charla", timeLabel: "11:00", date: new Date("2026-11-05T14:00:00Z"), raw: { is_registered: true } },
  ];
  const due = Core.pickDueNotifications({
    prefs: { events: true, announcements: true, deadlines: true },
    entries,
    banners: [{ id: 9, title: "Tormenta" }],
    seen: ["deadline:1"],
    nowMs,
  });
  assert.deepEqual(
    due.map((d) => d.id),
    ["event:2", "banner:9"],
  );
});

test("createOverlayManager: el boton Atras cierra modales sin salir de la aplicacion", () => {
  const listeners = {};
  const stack = [{ state: null }];
  let idx = 0;
  const win = {
    addEventListener: (ev, fn) => {
      listeners[ev] = fn;
    },
    removeEventListener: () => {},
    history: {
      pushState(state) {
        idx += 1;
        stack.splice(idx, stack.length - idx, { state });
      },
      back() {
        idx -= 1;
        listeners.popstate({ state: stack[idx].state });
      },
      go(delta) {
        idx += delta;
        listeners.popstate({ state: stack[idx].state });
      },
    },
  };
  let seen = [];
  const mgr = Core.createOverlayManager(win, (s) => {
    seen = s;
  });
  mgr.open("detail");
  assert.deepEqual(seen, ["detail"]);
  mgr.open("ios");
  assert.deepEqual(seen, ["detail", "ios"]);
  mgr.close();
  assert.deepEqual(seen, ["detail"]);
  mgr.closeAll();
  assert.deepEqual(seen, []);
});

test("createApi: clasifica timeout, puerto cerrado (offline), HTTP 500 y HTTP 401 con servidores reales", async () => {
  // 1. Timeout real: servidor TCP que acepta la conexion pero no responde
  const silent = net.createServer(() => {});
  await new Promise((r) => silent.listen(0, "127.0.0.1", r));
  const silentPort = silent.address().port;
  try {
    const api = Core.createApi({ baseUrl: `http://127.0.0.1:${silentPort}`, timeoutMs: 80 });
    await assert.rejects(
      () => api.feed(),
      (err) => err instanceof Core.ApiError && err.kind === "timeout",
    );
  } finally {
    silent.close();
  }

  // 2. Sin conexion: puerto cerrado
  const closedApi = Core.createApi({ baseUrl: `http://127.0.0.1:${silentPort}`, timeoutMs: 500 });
  await assert.rejects(
    () => closedApi.feed(),
    (err) => err instanceof Core.ApiError && err.kind === "offline",
  );

  // 3. HTTP 401 dispara onUnauthorized y HTTP 500 se traduce a error de servidor
  let unauthorizedCount = 0;
  let nextStatus = 401;
  const srv = http.createServer((req, res) => {
    res.writeHead(nextStatus, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ detail: "fallo" }));
  });
  await new Promise((r) => srv.listen(0, "127.0.0.1", r));
  try {
    const api = Core.createApi({
      baseUrl: `http://127.0.0.1:${srv.address().port}`,
      getToken: () => "jwt",
      onUnauthorized: () => {
        unauthorizedCount += 1;
      },
    });
    await assert.rejects(
      () => api.me(),
      (err) => err.kind === "unauthorized",
    );
    assert.equal(unauthorizedCount, 1);

    nextStatus = 503;
    await assert.rejects(
      () => api.feed(),
      (err) => err.kind === "server" && Core.isConnectivityError(err),
    );
  } finally {
    srv.close();
  }
});
