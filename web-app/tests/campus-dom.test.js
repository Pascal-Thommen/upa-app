/**
 * Pruebas de interfaz de UPA Campus PWA con DOM real (jsdom) contra el backend REAL.
 *
 * Carga `web-app/index.html` y ejecuta los scripts de produccion (`campus-core.js`, `qrcode.js`,
 * `campus.js`) sobre una instancia real de FastAPI + SQLite levantada por pytest.
 * Cubre landing de escritorio con QR, uso inmediato sin instalar, Inicio (fijados, noticias,
 * eventos, inscripcion/cancelacion, detalle a pantalla completa y boton Atras), Agenda
 * (lista superior + calendario inferior con filtro por dia), Perfil (tema de 3 vias,
 * interruptores de notificaciones y cierre de sesion) y fallos reales de red.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const jsQR = require("jsqr");

const BASE_URL = process.env.UPA_BASE_URL;
const EXPIRED_TOKEN = process.env.UPA_EXPIRED_TOKEN;
const TEST_TOKENS = process.env.UPA_TEST_TOKENS ? JSON.parse(process.env.UPA_TEST_TOKENS) : {};
const live = { skip: BASE_URL ? false : "UPA_BASE_URL no definido (se ejecuta desde pytest)" };

const { JSDOM, VirtualConsole } = BASE_URL ? require("jsdom") : {};
const WEB_APP = path.resolve(__dirname, "..");

const ANDROID_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36";
const IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Version/17.2 Mobile/15E148 Safari/604.1";
const DESKTOP_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36";

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

async function openCampus(options) {
  const opts = options || {};
  let html = fs.readFileSync(path.join(WEB_APP, "index.html"), "utf8");
  html = html.replace(/<script\s+src="[^"]*"><\/script>/g, "");

  const pageErrors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (err) => pageErrors.push(err.message));

  const dom = new JSDOM(html, {
    url: `${BASE_URL}${opts.url || "/"}`,
    userAgent: opts.userAgent || ANDROID_UA,
    runScripts: "dangerously",
    pretendToBeVisual: true,
    virtualConsole,
  });
  const { window } = dom;
  const document = window.document;
  Object.defineProperty(window.navigator, "userAgent", {
    value: opts.userAgent || ANDROID_UA,
    configurable: true,
  });

  let networkTarget = opts.networkTarget || BASE_URL;
  window.fetch = (input, init) => fetch(new URL(String(input), `${networkTarget}/`).toString(), init);
  window.AbortController = AbortController;
  window.matchMedia = (query) => ({
    matches: query.includes("dark") ? Boolean(opts.prefersDark) : query.includes("coarse") ? opts.userAgent !== DESKTOP_UA : false,
    media: query,
    addEventListener: () => {},
  });
  if (opts.serviceWorker) {
    Object.defineProperty(window.navigator, "serviceWorker", {
      value: opts.serviceWorker,
      configurable: true,
    });
  }
  if (opts.storage) {
    for (const [k, v] of Object.entries(opts.storage)) window.localStorage.setItem(k, v);
  }
  if (opts.token) window.localStorage.setItem("upa_campus_token", opts.token);

  for (const file of ["campus-core.js", "vendor/qrcode.js", "campus.js"]) {
    window.eval(fs.readFileSync(path.join(WEB_APP, file), "utf8"));
  }
  await window.UpaCampus.boot();
  await window.UpaCampus.idle();
  assert.deepEqual(pageErrors, []);

  return {
    window,
    document,
    $: (id) => document.getElementById(id),
    setNetworkTarget: (target) => {
      networkTarget = target;
    },
    click: async (el) => {
      el.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
      await new Promise((r) => setTimeout(r, 15));
      await window.UpaCampus.idle();
    },
    close: () => window.close(),
  };
}

const seeded = {};

test("preparacion: creacion de publicaciones reales (noticia, fijada, urgente y evento con registro)", live, async () => {
  const admin = TEST_TOKENS["admin@upa.edu.py"];
  assert.ok(admin);

  const urgent = await api("/api/publications", admin, {
    method: "POST",
    json: {
      title: "Aviso de prueba: clases virtuales por lluvia",
      content: "Las clases de hoy pasan a modalidad virtual.",
      post_type: "EMERGENCY_BANNER",
      is_news: true,
      is_event: false,
      is_pinned: true,
      expires_at: "2027-12-01T23:59:00Z",
      target_groups: ["ALL"],
    },
  });
  assert.equal(urgent.status, 201);
  seeded.urgentId = urgent.body.id;

  const news = await api("/api/publications", admin, {
    method: "POST",
    json: {
      title: "Convocatoria de intercambio en Heidelberg",
      caption: "Postulaciones abiertas hasta noviembre.",
      content: "Presenta tu carpeta académica en Secretaría. Requisitos: promedio mínimo 4.0 y nivel B2.",
      media_url: "/campus/icons/icon-512.png",
      media_type: "IMAGE",
      permalink: "https://upa.edu.py/intercambio",
      is_news: true,
      is_event: false,
      is_pinned: false,
      target_groups: ["ALL"],
    },
  });
  assert.equal(news.status, 201);
  seeded.newsId = news.body.id;

  const start = new Date(Date.now() + 3 * 24 * 3600 * 1000);
  start.setUTCHours(14, 0, 0, 0);
  const end = new Date(start.getTime() + 3600 * 1000);
  seeded.eventDayKey = start.toISOString().slice(0, 10);

  const event = await api("/api/publications", admin, {
    method: "POST",
    json: {
      title: "Foro de Ingeniería Empresarial 2026",
      caption: "Auditorio principal, inscripción previa.",
      content: "Panel con egresados en https://upa.edu.py/foro y bit.ly/foro-upa26. <script>window.__xss=1</script> #UPA #Ingeniería",
      permalink: "https://upa.edu.py/foro-2026",
      is_news: true,
      is_event: true,
      is_pinned: true,
      expires_at: "2027-12-01T23:59:00Z",
      event_start: start.toISOString(),
      event_end: end.toISOString(),
      location: "Auditorio Edificio 1",
      has_registration: true,
      target_groups: ["ALL"],
    },
  });
  assert.equal(event.status, 201);
  seeded.eventId = event.body.id;
});

test("Escritorio: muestra landing con telefono interactivo real en marco negro junto al codigo QR dinamico", live, async () => {
  const app = await openCampus({ userAgent: DESKTOP_UA });
  try {
    assert.equal(app.$("landing").hidden, false);
    assert.equal(app.$("app").hidden, false);
    assert.equal(app.$("app").classList.contains("app-framed"), true);
    assert.equal(app.document.querySelector(".phone-mockup .phone-frame #phone-screen #app"), app.$("app"), "La app interactiva real debe vivir dentro del marco de smartphone en escritorio");
    assert.match(app.$("landing").textContent, /Escanea con tu celular para abrir la app/);
    assert.ok(app.document.querySelector(".phone-mockup .phone-frame"), "Debe mostrar el marco negro realista de smartphone");
    assert.equal(app.document.querySelector(".phone-notch"), null, "No debe existir Apple-Notch en el marco del smartphone");
    assert.equal(app.document.querySelector(".phone-speaker"), null, "No debe existir altavoz de notch");
    assert.equal(app.document.querySelector(".phone-camera"), null, "No debe existir camara de notch");
    assert.equal(app.$("try-web-link"), null, "No debe existir el enlace Probar la versión web aquí");
    assert.equal(/Probar la versión web aquí/.test(app.$("landing").textContent), false);
    assert.equal(app.document.querySelector(".landing-points"), null, "No debe mostrar la lista larga de texto en escritorio");
    assert.equal(app.$("admin-link").getAttribute("href"), "/dashboard/");
    assert.equal(app.$("admin-link").textContent.trim(), "Acceso Administrativo");
    assert.equal(app.$("qr-url").textContent, `${BASE_URL}/`);

    // La app dentro del telefono en escritorio es la PWA interactiva real (no un mockup estatico)
    await app.click(app.document.querySelector('[data-tab="perfil"]'));
    assert.equal(app.$("view-perfil").hidden, false);
    const landingDarkSignet = app.document.querySelector(".landing-header .upa-signet.logo-dark");
    const landingLightLogo = app.document.querySelector(".landing-header .upa-signet.logo-light");
    assert.ok(landingLightLogo && landingDarkSignet, "El logo en escritorio debe ser el signet vectorial de 3 letras UPA en ambos modos");
    assert.equal(app.document.querySelector('img[src*="upa-logo"]'), null, "No debe existir el logo bitmap upa-logo.png");
    await app.click(app.document.querySelector('[data-theme-option="dark"]'));
    assert.equal(app.document.documentElement.getAttribute("data-resolved-theme"), "dark");
    assert.equal(landingDarkSignet.hidden, false);
    assert.equal(landingLightLogo.hidden, true);
    await app.click(app.document.querySelector('[data-theme-option="light"]'));
    assert.equal(app.document.documentElement.getAttribute("data-resolved-theme"), "light");
    assert.equal(landingDarkSignet.hidden, true);
    assert.equal(landingLightLogo.hidden, false);
    await app.click(app.document.querySelector('[data-tab="inicio"]'));
    assert.equal(app.$("view-inicio").hidden, false);
    app.window.dispatchEvent(new app.window.Event("resize"));
    assert.equal(app.$("app").classList.contains("app-framed"), true);

    const svg = app.$("qr-box").querySelector("svg");
    assert.ok(svg, "El contenedor QR debe incluir un SVG generado dinamicamente");
    const qr = app.window.UpaCampusCore.buildQr(`${BASE_URL}/`, app.window.qrcode, { margin: 2 });
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
    assert.equal(jsQR(rgba, side, side).data, `${BASE_URL}/`);
  } finally {
    app.close();
  }
});

test("Movil sin instalar: abre directamente la app; banner de instalacion en Android e iOS sin bloqueo", live, async () => {
  const ios = await openCampus({ userAgent: IPHONE_UA });
  try {
    assert.equal(ios.$("landing").hidden, true);
    assert.equal(ios.$("app").hidden, false);
    assert.equal(ios.$("install-banner").hidden, false);
    assert.equal(ios.$("install-action").textContent, "Ver cómo");
    await ios.click(ios.$("install-action"));
    assert.equal(ios.$("ios-sheet").hidden, false);
    assert.match(ios.$("ios-sheet").textContent, /Añadir a pantalla de inicio/);
    await ios.click(ios.$("ios-close"));
    assert.equal(ios.$("ios-sheet").hidden, true);
    await ios.click(ios.$("install-dismiss"));
    assert.equal(ios.$("install-banner").hidden, true);
  } finally {
    ios.close();
  }

  const android = await openCampus({ userAgent: ANDROID_UA });
  try {
    assert.equal(android.$("install-banner").hidden, true);
    let prompted = 0;
    const fakePrompt = new android.window.Event("beforeinstallprompt", { cancelable: true });
    fakePrompt.prompt = async () => {
      prompted += 1;
    };
    fakePrompt.userChoice = Promise.resolve({ outcome: "accepted" });
    android.window.dispatchEvent(fakePrompt);
    assert.equal(android.$("install-banner").hidden, false);
    assert.equal(android.$("install-action").textContent, "Instalar");
    await android.click(android.$("install-action"));
    assert.equal(prompted, 1);
  } finally {
    android.close();
  }
});

test("Inicio: fijados arriba, inscripcion y cancelacion en tarjeta, detalle y boton Atras de Android", live, async () => {
  const student = TEST_TOKENS["ana.gomez@upa.edu.py"];
  const app = await openCampus({ url: `/#token=${student}` });
  try {
    assert.equal(app.window.location.hash, "");
    assert.equal(app.$("urgent-list").children.length >= 1, true);
    assert.match(app.$("urgent-list").textContent, /clases virtuales por lluvia/);

    const cards = [...app.$("feed-list").querySelectorAll(".card")];
    assert.ok(cards.length >= 2);
    assert.match(cards[0].textContent, /Fijado/);
    assert.match(cards[0].textContent, /Foro de Ingeniería Empresarial 2026/);

    // Publicacion sin imagen (!media): badges prominentes (Campus y Evento) arriba a la izquierda en .card-header
    const eventHeaderBadges = [...cards[0].querySelectorAll(".card-header .card-badges .badge")];
    assert.equal(eventHeaderBadges.length, 2, "El evento sin imagen debe mostrar badges de origen (Campus) y tipo (Evento) en el encabezado");
    assert.equal(eventHeaderBadges[0].textContent.trim(), "Campus");
    assert.equal(eventHeaderBadges[1].textContent.trim(), "Evento");

    // Detalle estructurado de un evento: orden estricto detail-media -> detail-title -> detail-text -> detail-event-card -> detail-actions
    await app.click(cards[0].querySelector(".card-open"));
    assert.equal(app.$("detail").hidden, false);
    const detailMedia = app.$("detail-media");
    const detailTitle = app.$("detail-title");
    const detailText = app.$("detail-text");
    const detailEventCard = app.$("detail-event-card");
    const detailActions = app.$("detail-actions");
    const FOLLOWING = app.window.Node.DOCUMENT_POSITION_FOLLOWING;
    assert.ok(detailMedia.compareDocumentPosition(detailTitle) & FOLLOWING, "detail-media debe preceder a detail-title");
    assert.ok(detailTitle.compareDocumentPosition(detailText) & FOLLOWING, "detail-title debe preceder a detail-text");
    assert.ok(detailText.compareDocumentPosition(detailEventCard) & FOLLOWING, "detail-text debe preceder a detail-event-card");
    assert.ok(detailEventCard.compareDocumentPosition(detailActions) & FOLLOWING, "detail-event-card debe preceder a detail-actions");

    // Rich-Text Linkifier en #detail-text: URLs clicables, Hashtags formateados y XSS neutralizado
    const textLinks = [...detailText.querySelectorAll("a.rich-link")];
    assert.equal(textLinks.length, 2, "Debe convertir las URLs https y bit.ly en enlaces clicables");
    assert.equal(textLinks[0].getAttribute("href"), "https://upa.edu.py/foro");
    assert.equal(textLinks[0].getAttribute("target"), "_blank");
    assert.equal(textLinks[0].getAttribute("rel"), "noopener noreferrer");
    assert.equal(textLinks[1].getAttribute("href"), "https://bit.ly/foro-upa26");
    const hashtags = [...detailText.querySelectorAll("span.hashtag")].map((el) => el.textContent);
    assert.deepEqual(hashtags, ["#UPA", "#Ingeniería"]);
    assert.equal(detailText.querySelectorAll("script").length, 0, "No debe inyectar etiquetas <script> en el DOM");
    assert.equal(app.window.__xss, undefined, "El intento de XSS debe quedar completamente neutralizado");

    assert.equal(detailEventCard.hidden, false, "El detalle de un evento debe renderizar el bloque estructurado #detail-event-card");
    assert.ok(detailEventCard.querySelector(".detail-date-tile"), "Debe incluir mosaico de fecha (dia/mes)");
    assert.match(detailEventCard.textContent, /Horario: \d{2}:\d{2} - \d{2}:\d{2} hs/);
    assert.match(detailEventCard.textContent, /Lugar/);
    assert.match(detailEventCard.textContent, /Auditorio Edificio 1/);
    assert.match(app.$("detail-event-status").textContent, /Inscripción abierta/);
    app.window.history.back();
    await new Promise((r) => setTimeout(r, 20));
    assert.equal(app.$("detail").hidden, true);

    const regBtn = app.document.querySelector(`[data-register="${seeded.eventId}"]`);
    assert.ok(regBtn);
    assert.equal(regBtn.textContent, "Inscripción");

    await app.click(regBtn);
    const updatedBtn = app.document.querySelector(`[data-register="${seeded.eventId}"]`);
    assert.equal(updatedBtn.textContent, "Cancelar inscripción");
    const check1 = await api("/api/v1/agenda", student);
    const ev1 = check1.body.events.find((e) => e.id === seeded.eventId);
    assert.equal(ev1.is_registered, true);

    await app.click(updatedBtn);
    assert.equal(app.document.querySelector(`[data-register="${seeded.eventId}"]`).textContent, "Inscripción");
    const check2 = await api("/api/v1/agenda", student);
    const ev2 = check2.body.events.find((e) => e.id === seeded.eventId);
    assert.equal(ev2.is_registered, false);

    // Detalle a pantalla completa, badge Campus flotante con "U" verde y enlace a la fuente original
    const openNews = app.document.querySelector(`[data-post-id="${seeded.newsId}"]`);
    const newsFloatingBadge = openNews.querySelector(".card-media-wrap > .badge.badge-campus.badge-floating");
    assert.ok(newsFloatingBadge, "La publicacion interna con imagen debe tener el badge Campus flotando arriba a la izquierda sobre la imagen");
    assert.ok(newsFloatingBadge.querySelector("svg.upa-u-glyph"), "El badge Campus debe incluir la U verde de la UPA");
    assert.equal(newsFloatingBadge.textContent.trim(), "Campus");
    assert.equal(openNews.querySelector(".card-meta .badge"), null, "El badge no debe duplicarse debajo de la imagen");

    await app.click(openNews);
    assert.equal(app.$("detail").hidden, false);
    assert.equal(app.$("detail-kind").classList.contains("badge-campus"), true);
    assert.ok(app.$("detail-kind").querySelector("svg.upa-u-glyph"));
    assert.equal(app.$("detail-kind").textContent.trim(), "Campus");
    assert.equal(app.$("detail-title").textContent, "Convocatoria de intercambio en Heidelberg");
    assert.match(app.$("detail-text").textContent, /promedio mínimo 4\.0/);
    assert.equal(app.$("detail-event-card").hidden, true, "Las publicaciones sin evento deben ocultar limpiamente #detail-event-card");
    assert.equal(app.$("detail-source").getAttribute("href"), "https://upa.edu.py/intercambio");

    // Boton Atras de Android (popstate) cierra el detalle sin salir de la aplicacion
    app.window.history.back();
    await new Promise((r) => setTimeout(r, 20));
    assert.equal(app.$("detail").hidden, true);
    assert.equal(app.$("app").hidden, false);

    // Publicacion de Instagram: insignia flotante arriba a la izquierda con icono oficial de camara y un unico boton "Ver en Instagram"
    const igCard = app.document.querySelector('.card[data-kind="instagram"]');
    assert.ok(igCard, "Debe existir la tarjeta de Instagram en el feed");
    const igBadge = igCard.querySelector(".card-media-wrap > .badge.badge-instagram.badge-floating");
    assert.ok(igBadge, "La tarjeta de Instagram debe tener el badge-instagram flotando sobre la imagen");
    assert.ok(igBadge.querySelector("svg.ig-glyph"), "El badge de Instagram debe incluir el icono de camara");
    assert.equal(igBadge.textContent.trim(), "Instagram");
    assert.equal(igCard.querySelector(".card-meta .badge"), null, "El badge de Instagram no debe duplicarse en card-meta");

    await app.click(igCard.querySelector(".card-open"));
    assert.equal(app.$("detail").hidden, false);
    assert.equal(app.$("detail-kind").classList.contains("badge-instagram"), true);
    assert.ok(app.$("detail-kind").querySelector("svg.ig-glyph"));
    const detailLinks = [...app.$("detail-actions").querySelectorAll("a.btn")];
    assert.equal(detailLinks.length, 1, "El detalle de Instagram debe mostrar exactamente un boton de enlace");
    assert.equal(detailLinks[0].textContent.trim(), "Ver en Instagram");
    assert.equal(detailLinks[0].getAttribute("href"), "https://www.instagram.com/p/DerQoIzjtYf/");
    app.window.history.back();
    await new Promise((r) => setTimeout(r, 20));
  } finally {
    app.close();
  }
});

test("Agenda: lista cronologica arriba, calendario mensual abajo y filtrado al tocar un dia", live, async () => {
  const student = TEST_TOKENS["ana.gomez@upa.edu.py"];
  const app = await openCampus({ token: student });
  try {
    await app.click(app.document.querySelector('[data-tab="agenda"]'));
    assert.equal(app.$("view-agenda").hidden, false);
    assert.match(app.$("agenda-list").textContent, /Foro de Ingeniería Empresarial 2026/);

    // Navegar en el calendario hasta el mes del evento si cae en el mes siguiente
    const targetMonth = Number(seeded.eventDayKey.slice(5, 7)) - 1;
    if (app.window.UpaCampus.state.month.monthIndex !== targetMonth) {
      await app.click(app.$("cal-next"));
    }

    const dayCell = app.document.querySelector(`[data-day="${seeded.eventDayKey}"]`);
    assert.ok(dayCell, "El dia del evento debe existir en la cuadricula mensual");
    assert.ok(dayCell.querySelector(".dot-event"), "El dia del evento debe tener punto indicador");
    assert.ok(app.$("agenda-list").querySelector(".agenda-month-header"), "La linea de tiempo debe agrupar por mes");

    let smoothScrolled = 0;
    const agendaTop = app.document.querySelector(".agenda-top");
    agendaTop.scrollTo = (opts) => {
      if (opts && opts.behavior === "smooth") smoothScrolled += 1;
    };

    await app.click(dayCell);
    const selectedCell = app.document.querySelector(`[data-day="${seeded.eventDayKey}"]`);
    assert.equal(selectedCell.classList.contains("selected"), true);
    assert.equal(app.$("agenda-clear").hidden, false);
    assert.equal(smoothScrolled >= 1, true, "Tocar un dia en el calendario debe hacer smooth scroll al evento");
    const highlighted = app.$("agenda-list").querySelector(`.agenda-item[data-agenda-day="${seeded.eventDayKey}"].agenda-item-highlight`);
    assert.ok(highlighted, "El evento del dia seleccionado debe resaltarse en la linea de tiempo");

    // Abrir evento desde Agenda (detailFromEntry) renderiza exactamente la misma estructura armonizada que desde Inicio (detailFromPost)
    await app.click(highlighted.querySelector(".agenda-open"));
    assert.equal(app.$("detail").hidden, false);
    assert.equal(app.$("detail-title").textContent, "Foro de Ingeniería Empresarial 2026");
    assert.equal(app.$("detail-text").querySelectorAll("a.rich-link").length, 2, "El detalle desde Agenda debe aplicar linkifyText al texto");
    assert.equal(app.$("detail-text").querySelectorAll("span.hashtag").length, 2, "El detalle desde Agenda debe resaltar los hashtags");
    assert.equal(app.$("detail-event-card").hidden, false, "El detalle desde Agenda debe mostrar #detail-event-card debajo del texto");
    assert.ok(app.$("detail-actions").querySelector("#detail-register"), "El detalle desde Agenda debe incluir el boton de inscripcion");
    assert.ok(app.$("detail-actions").querySelector("#detail-source"), "El detalle desde Agenda debe incluir el boton de fuente original");
    app.window.history.back();
    await new Promise((r) => setTimeout(r, 20));
    assert.equal(app.$("detail").hidden, true);

    await app.click(app.$("agenda-clear"));
    assert.equal(app.$("agenda-clear").hidden, true);

    // El modo modular de dia individual (renderAgendaSingleDay / setAgendaMode) sigue disponible y funcional
    app.window.UpaCampus.setAgendaMode("single-day");
    await app.click(app.document.querySelector(`[data-day="${seeded.eventDayKey}"]`));
    assert.equal(app.$("agenda-list").querySelectorAll(".agenda-month-header").length, 0);
    assert.equal(app.$("agenda-list").querySelectorAll(".agenda-item").length >= 1, true);
    app.window.UpaCampus.setAgendaMode("timeline");
    assert.ok(app.$("agenda-list").querySelector(".agenda-month-header"));

    // Tarea de Google Classroom: icono de enlace externo salta a Classroom
    const withDeadline = app.window.UpaCampusCore.buildAgendaEntries({
      events: [],
      deadlines: [
        {
          id: "cw-101",
          title: "Entrega Proyecto Final",
          description: "Repositorio y memoria técnica",
          course_name: "Ingeniería de Software",
          due_date_formatted: `${seeded.eventDayKey} 23:59`,
          alternate_link: "https://classroom.google.com/c/100/a/cw-101/details",
        },
      ],
    });
    app.window.UpaCampus.state.agenda.entries.push(...withDeadline);
    await app.click(app.document.querySelector(`[data-day="${seeded.eventDayKey}"]`));
    const extLink = app.$("agenda-list").querySelector(".agenda-kind-deadline a.ext-link");
    assert.ok(extLink, "La tarea de Classroom debe mostrar el enlace externo con icono");
    assert.equal(extLink.getAttribute("href"), "https://classroom.google.com/c/100/a/cw-101/details");
    assert.equal(extLink.getAttribute("target"), "_blank");
    assert.ok(extLink.querySelector("svg"));
  } finally {
    app.close();
  }
});

test("Perfil: datos del usuario, cambio de tema en 3 modos, notificaciones y cierre de sesion", live, async () => {
  const student = TEST_TOKENS["ana.gomez@upa.edu.py"];
  const app = await openCampus({ token: student, prefersDark: true });
  try {
    await app.click(app.document.querySelector('[data-tab="perfil"]'));
    assert.equal(app.$("profile-name").textContent, "Ana Gomez");
    assert.equal(app.$("profile-email").textContent, "ana.gomez@upa.edu.py");
    assert.equal(app.$("profile-role").textContent, "Estudiante");
    assert.equal(app.$("profile-avatar").textContent, "AG");
    assert.equal(app.$("profile-groups"), null, "El contenedor #profile-groups no debe existir en el perfil");

    const meta = app.document.querySelector('meta[name="theme-color"]');
    const topbarLightLogo = app.document.querySelector(".topbar .upa-signet.logo-light");
    const topbarDarkSignet = app.document.querySelector(".topbar .upa-signet.logo-dark");
    assert.ok(topbarLightLogo && topbarDarkSignet, "Deben existir las variantes clara (signet verde #6c9339) y oscura (signet blanco UPA) en la barra superior");
    assert.equal(topbarLightLogo.tagName.toLowerCase(), "svg");
    assert.equal(topbarDarkSignet.tagName.toLowerCase(), "svg");

    await app.click(app.document.querySelector('[data-theme-option="dark"]'));
    assert.equal(app.document.documentElement.getAttribute("data-theme"), "dark");
    assert.equal(app.document.documentElement.getAttribute("data-resolved-theme"), "dark");
    assert.equal(meta.getAttribute("content"), "#0f172a");
    assert.equal(topbarDarkSignet.hidden, false, "En modo oscuro debe mostrarse el signet blanco monocromo UPA");
    assert.equal(topbarLightLogo.hidden, true, "En modo oscuro debe ocultarse el logo con recuadro blanco");

    await app.click(app.document.querySelector('[data-theme-option="light"]'));
    assert.equal(app.document.documentElement.getAttribute("data-theme"), "light");
    assert.equal(app.document.documentElement.getAttribute("data-resolved-theme"), "light");
    assert.equal(meta.getAttribute("content"), "#ffffff");
    assert.equal(topbarDarkSignet.hidden, true);
    assert.equal(topbarLightLogo.hidden, false);

    await app.click(app.document.querySelector('[data-theme-option="system"]'));
    assert.equal(app.document.documentElement.hasAttribute("data-theme"), false);
    assert.equal(app.document.documentElement.getAttribute("data-resolved-theme"), "dark");
    assert.equal(meta.getAttribute("content"), "#0f172a");
    assert.equal(topbarDarkSignet.hidden, false);
    assert.equal(topbarLightLogo.hidden, true);

    const swEvents = app.document.querySelector('[data-notify="events"]');
    swEvents.checked = false;
    swEvents.dispatchEvent(new app.window.Event("change", { bubbles: true }));
    await app.window.UpaCampus.idle();
    assert.equal(JSON.parse(app.window.localStorage.getItem("upa_campus_notifications")).events, false);

    await app.click(app.$("btn-logout"));
    assert.equal(app.window.localStorage.getItem("upa_campus_token"), null);
    assert.equal(app.window.localStorage.getItem("upa_campus_cache_feed:u3"), null);
    assert.equal(app.$("profile-guest").hidden, false);
    assert.equal(app.$("profile-user").hidden, true);
  } finally {
    app.close();
  }
});

test("Resiliencia: modo sin conexion con datos guardados, fallo sin cache y token vencido", live, async () => {
  const student = TEST_TOKENS["ana.gomez@upa.edu.py"];

  // 1. Carga en linea y luego caida de red: conserva los datos y muestra el aviso offline
  const app = await openCampus({ token: student });
  try {
    assert.equal(app.$("offline-banner").hidden, true);
    app.setNetworkTarget("http://127.0.0.1:1");
    await app.click(app.$("btn-refresh"));
    assert.equal(app.$("offline-banner").hidden, false);
    assert.match(app.$("offline-banner").textContent, /Sin conexión/);
    assert.ok(app.$("feed-list").children.length >= 2, "Las publicaciones en cache deben seguir visibles");
  } finally {
    app.close();
  }

  // 2. Arranque en frio sin red y sin cache: mensaje claro con boton Reintentar (sin colapso)
  const cold = await openCampus({ networkTarget: "http://127.0.0.1:1" });
  try {
    assert.equal(cold.$("offline-banner").hidden, false);
    assert.equal(cold.$("feed-status").hidden, false);
    assert.match(cold.$("feed-status").textContent, /Sin conexión/);
    assert.ok(cold.$("feed-status").querySelector("button"));
  } finally {
    cold.close();
  }

  // 3. Token vencido: se limpia al iniciar sin bloquear la aplicacion
  const expired = await openCampus({ token: EXPIRED_TOKEN });
  try {
    assert.equal(expired.window.localStorage.getItem("upa_campus_token"), null);
    assert.equal(expired.$("login-prompt").hidden, false);
  } finally {
    expired.close();
  }
});

test("Beta y Auto-Update SW: muestra badge BETA en instancia beta y gestiona updatefound/controllerchange", live, async () => {
  const swListeners = {};
  const regListeners = {};
  const installingWorker = {
    state: "installing",
    listeners: {},
    postMessages: [],
    addEventListener(ev, fn) {
      this.listeners[ev] = fn;
    },
    postMessage(msg) {
      this.postMessages.push(msg);
    },
  };
  let updateCalled = 0;
  const fakeSw = {
    controller: {},
    addEventListener(ev, fn) {
      swListeners[ev] = fn;
    },
    register: async () => ({
      installing: installingWorker,
      waiting: null,
      update: async () => {
        updateCalled += 1;
      },
      addEventListener(ev, fn) {
        regListeners[ev] = fn;
      },
    }),
  };

  const betaApp = await openCampus({ url: "/?env=beta", serviceWorker: fakeSw });
  try {
    assert.equal(betaApp.$("beta-badge").hidden, false, "En instancia Beta debe mostrarse el badge BETA en la barra superior");
    assert.equal(betaApp.$("beta-badge").textContent, "BETA");
    assert.equal(betaApp.$("profile-beta-badge").hidden, false, "En instancia Beta debe mostrarse el badge BETA en el perfil");
    assert.equal(updateCalled >= 1, true, "Debe invocar reg.update() al registrar el Service Worker");

    // Simular nueva version detectada por el Service Worker (updatefound -> installed -> SKIP_WAITING)
    assert.ok(regListeners.updatefound, "Debe escuchar el evento updatefound");
    regListeners.updatefound();
    installingWorker.state = "installed";
    installingWorker.listeners.statechange();
    assert.equal(betaApp.$("toast").hidden, false);
    assert.match(betaApp.$("toast").textContent, /Nueva versión disponible/);
    assert.equal(installingWorker.postMessages.length, 1);
    assert.equal(installingWorker.postMessages[0].type, "SKIP_WAITING");

    // Simular cambio de controlador (controllerchange)
    assert.ok(swListeners.controllerchange, "Debe escuchar el evento controllerchange");
    swListeners.controllerchange();
    assert.match(betaApp.$("toast").textContent, /Nueva versión disponible/);
  } finally {
    betaApp.close();
  }
});
