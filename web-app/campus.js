/**
 * UPA Campus PWA: controlador de interfaz (Inicio, Agenda, Perfil) y landing de escritorio.
 * Toda la logica de datos vive en campus-core.js; aqui solo se conecta con el DOM y el navegador.
 */
(function () {
  "use strict";

  const Core = window.UpaCampusCore;
  const FEED_PAGE = 20;
  const REFRESH_AFTER_MS = 60 * 1000;
  const TOKEN_KEY = "upa_campus_token";
  const THEME_KEY = "upa_campus_theme";
  const INSTALL_KEY = "upa_campus_install_dismissed";
  const NOTIFIED_KEY = "upa_campus_notified";
  const FORCE_APP_KEY = "upa_campus_force_app";
  const WEEKDAYS = ["L", "M", "M", "J", "V", "S", "D"];

  const doc = document;
  const win = window;
  const $ = (id) => doc.getElementById(id);

  function safeStorage(kind) {
    try {
      const s = win[kind];
      s.setItem("__upa_probe", "1");
      s.removeItem("__upa_probe");
      return s;
    } catch (_) {
      const data = {};
      return {
        get length() {
          return Object.keys(data).length;
        },
        key: (i) => Object.keys(data)[i] || null,
        getItem: (k) => (k in data ? data[k] : null),
        setItem: (k, v) => {
          data[k] = String(v);
        },
        removeItem: (k) => {
          delete data[k];
        },
      };
    }
  }

  const local = safeStorage("localStorage");
  const session = safeStorage("sessionStorage");
  const cache = Core.createCache(local);

  const state = {
    token: null,
    user: null,
    feed: { banners: [], posts: [], received: 0, hasMore: false, loaded: false, error: null },
    agenda: { entries: [], loaded: false, error: null },
    tab: "inicio",
    month: null,
    selectedDay: null,
    detail: null,
    offline: false,
    installPrompt: null,
    lastRefresh: 0,
    prefs: Core.loadNotificationPrefs(local),
  };

  const pending = new Set();
  let overlays = null;
  let api = null;
  let toastTimer = null;

  function track(promise) {
    pending.add(promise);
    const done = () => pending.delete(promise);
    promise.then(done, done);
    return promise;
  }

  /* ------------------------------------------------------------------ utilidades DOM */

  function h(tag, attrs, ...children) {
    const el = doc.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") el.className = value;
      else if (key === "text") el.textContent = value;
      else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
      else el.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      el.append(child.nodeType ? child : doc.createTextNode(String(child)));
    }
    return el;
  }

  function clear(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function toast(message) {
    const el = $("toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.hidden = true;
    }, 3500);
  }

  function externalIcon() {
    const svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "20");
    svg.setAttribute("height", "20");
    svg.setAttribute("aria-hidden", "true");
    const path = doc.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5");
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "2");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    svg.appendChild(path);
    return svg;
  }

  function instagramIcon(size) {
    const px = String(size || 14);
    const svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", px);
    svg.setAttribute("height", px);
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", "ig-glyph");
    const rect = doc.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", "2");
    rect.setAttribute("y", "2");
    rect.setAttribute("width", "20");
    rect.setAttribute("height", "20");
    rect.setAttribute("rx", "5");
    rect.setAttribute("ry", "5");
    rect.setAttribute("fill", "none");
    rect.setAttribute("stroke", "currentColor");
    rect.setAttribute("stroke-width", "2.2");
    const circle = doc.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", "12");
    circle.setAttribute("cy", "12");
    circle.setAttribute("r", "4.5");
    circle.setAttribute("fill", "none");
    circle.setAttribute("stroke", "currentColor");
    circle.setAttribute("stroke-width", "2.2");
    const dot = doc.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", "17.5");
    dot.setAttribute("cy", "6.5");
    dot.setAttribute("r", "1.3");
    dot.setAttribute("fill", "currentColor");
    svg.append(rect, circle, dot);
    return svg;
  }

  function kindBadge(kind, labelText) {
    const label = labelText || Core.kindLabel(kind);
    if (kind === "instagram") {
      return h("span", { class: "badge badge-instagram" }, instagramIcon(13), h("span", { text: label }));
    }
    if (kind === "urgent") {
      return h("span", { class: "badge badge-urgent", text: label });
    }
    return h("span", { class: "badge", text: label });
  }

  /* ------------------------------------------------------------------ entorno y sesion */

  function readEnvironment() {
    const nav = win.navigator;
    const match = (q) => (typeof win.matchMedia === "function" ? win.matchMedia(q).matches : false);
    const search = String(win.location.search || "");
    const forced = session.getItem(FORCE_APP_KEY) === "1";
    return {
      userAgent: nav.userAgent || "",
      platform: nav.platform || "",
      maxTouchPoints: nav.maxTouchPoints || 0,
      coarsePointer: match("(pointer: coarse)"),
      standalone: match("(display-mode: standalone)") || nav.standalone === true,
      width: win.innerWidth || 0,
      search: forced && !/app=1/.test(search) ? `${search}&app=1` : search,
    };
  }

  function currentUserKey() {
    const payload = state.token ? Core.decodeJwtPayload(state.token) : null;
    return payload && payload.sub ? `u${payload.sub}` : "anon";
  }

  function consumeAuthFragment() {
    const result = Core.parseAuthFragment(win.location.hash);
    if (result.token) {
      local.setItem(TOKEN_KEY, result.token);
      session.setItem(FORCE_APP_KEY, "1");
    }
    if (result.token || result.error || win.location.hash) {
      try {
        win.history.replaceState(null, "", win.location.pathname + win.location.search);
      } catch (_) {
        /* el historial no admite replaceState en este contexto */
      }
    }
    return result;
  }

  function loadStoredToken() {
    const token = local.getItem(TOKEN_KEY);
    if (!token) return null;
    if (Core.isTokenExpired(token)) {
      local.removeItem(TOKEN_KEY);
      return null;
    }
    return token;
  }

  async function purgeBrowserCaches() {
    if (!("caches" in win)) return;
    try {
      const keys = await win.caches.keys();
      await Promise.all(keys.filter((k) => k.startsWith("upa-campus-runtime")).map((k) => win.caches.delete(k)));
    } catch (_) {
      /* sin acceso a Cache Storage: no hay nada que limpiar */
    }
  }

  function resetSessionState() {
    state.token = null;
    state.user = null;
    state.feed = { banners: [], posts: [], received: 0, hasMore: false, loaded: false, error: null };
    state.agenda = { entries: [], loaded: false, error: null };
    state.selectedDay = null;
    state.detail = null;
  }

  async function logout(reason) {
    local.removeItem(TOKEN_KEY);
    local.removeItem(NOTIFIED_KEY);
    session.removeItem(FORCE_APP_KEY);
    cache.clear();
    resetSessionState();
    if (overlays) overlays.closeAll();
    renderAll();
    setOffline(false);
    track(purgeBrowserCaches());
    if (reason) toast(reason);
    await track(loadFeed({ reset: true }));
  }

  /* ------------------------------------------------------------------ conectividad */

  function setOffline(offline, hasCache) {
    state.offline = offline;
    const banner = $("offline-banner");
    $("app").classList.toggle("is-offline", offline);
    banner.hidden = !offline;
    banner.textContent = offline
      ? hasCache
        ? "Sin conexión. Mostrando los últimos datos guardados."
        : "Sin conexión. Algunos datos no están disponibles."
      : "";
  }

  function statusBox(el, message, retry) {
    clear(el);
    if (!message) {
      el.hidden = true;
      return;
    }
    el.hidden = false;
    el.append(h("p", { text: message }));
    if (retry) el.append(h("button", { class: "btn btn-secondary btn-small", type: "button", text: "Reintentar", onclick: retry }));
  }

  /* ------------------------------------------------------------------ carga de datos */

  async function loadUser() {
    if (!state.token) return;
    const key = `user:${currentUserKey()}`;
    const cached = cache.get(key);
    if (cached && !state.user) state.user = cached.data;
    try {
      state.user = await api.me();
      cache.set(key, state.user);
    } catch (error) {
      if (error.kind === "unauthorized") return;
      if (!state.user) state.user = null;
    }
    renderProfile();
  }

  async function loadFeed(options) {
    const reset = !options || options.reset !== false;
    const key = `feed:${currentUserKey()}`;

    if (reset && !state.feed.loaded) {
      const cached = cache.get(key);
      if (cached) {
        state.feed = { ...cached.data, loaded: true, error: null };
        renderFeed();
      }
    }

    const offset = reset ? 0 : state.feed.received;
    try {
      const response = await api.feed({ limit: FEED_PAGE, offset });
      const normalized = Core.normalizeFeed(response);
      const received = Array.isArray(response.posts) ? response.posts.length : 0;
      state.feed = {
        banners: reset ? normalized.banners : state.feed.banners,
        posts: reset ? normalized.posts : Core.mergePosts(state.feed.posts, normalized.posts),
        received: offset + received,
        hasMore: received >= FEED_PAGE,
        loaded: true,
        error: null,
      };
      cache.set(key, { ...state.feed, error: null });
      setOffline(false);
      state.lastRefresh = Date.now();
    } catch (error) {
      if (error.kind === "unauthorized") return;
      const hasData = state.feed.posts.length > 0 || state.feed.banners.length > 0;
      if (Core.isConnectivityError(error)) setOffline(true, hasData);
      state.feed.loaded = true;
      if (!hasData) state.feed.error = Core.friendlyError(error);
      else if (!reset) toast(Core.friendlyError(error));
    }
    renderFeed();
    maybeNotify();
  }

  async function loadAgenda() {
    if (!state.token) {
      state.agenda = { entries: [], loaded: true, error: null };
      renderAgenda();
      return;
    }
    const key = `agenda:${currentUserKey()}`;
    if (!state.agenda.loaded) {
      const cached = cache.get(key);
      if (cached) {
        state.agenda = { entries: Core.buildAgendaEntries(cached.data), loaded: true, error: null };
        renderAgenda();
      }
    }
    try {
      const response = await api.agenda();
      cache.set(key, response);
      state.agenda = { entries: Core.buildAgendaEntries(response), loaded: true, error: null };
      setOffline(false);
    } catch (error) {
      if (error.kind === "unauthorized") return;
      const hasData = state.agenda.entries.length > 0;
      if (Core.isConnectivityError(error)) setOffline(true, hasData);
      state.agenda.loaded = true;
      if (!hasData) state.agenda.error = Core.friendlyError(error);
    }
    renderAgenda();
    maybeNotify();
  }

  async function refreshAll() {
    const tasks = [loadFeed({ reset: true })];
    if (state.token) tasks.push(loadAgenda(), loadUser());
    await Promise.all(tasks.map(track));
  }

  /* ------------------------------------------------------------------ inscripcion */

  function applyRegistrationUpdate(updated) {
    state.feed.posts = state.feed.posts.map((p) =>
      p.id === updated.id ? { ...p, is_registered: updated.is_registered, registered_count: updated.registered_count } : p,
    );
    state.agenda.entries = Core.applyRegistration(state.agenda.entries, updated);
    cache.set(`feed:${currentUserKey()}`, state.feed);
    renderFeed();
    renderAgenda();
    if (state.detail && state.detail.eventId === updated.id) {
      state.detail.isRegistered = updated.is_registered;
      state.detail.count = updated.registered_count;
      renderDetailActions();
    }
  }

  async function toggleRegistration(eventId, currentlyRegistered, button) {
    if (!state.token) {
      toast("Inicia sesión para inscribirte.");
      return;
    }
    if (button) button.disabled = true;
    try {
      const updated = currentlyRegistered ? await api.unregister(eventId) : await api.register(eventId);
      applyRegistrationUpdate(updated);
      toast(updated.is_registered ? "Inscripción confirmada." : "Inscripción cancelada.");
    } catch (error) {
      if (Core.isConnectivityError(error)) setOffline(true, true);
      if (error.kind !== "unauthorized") toast(Core.friendlyError(error));
    } finally {
      if (button) button.disabled = false;
    }
  }

  /* ------------------------------------------------------------------ render: inicio */

  function postTimeLine(post) {
    if (post.is_event && post.event_start) {
      const key = Core.dayKey(post.event_start);
      const short = Core.formatDayShort(key);
      const parts = [`${short.day} ${short.month.toLowerCase()}`, Core.formatTime(post.event_start)];
      if (post.location) parts.push(post.location);
      return parts.join(" · ");
    }
    return Core.formatPublished(post.published_at);
  }

  function mediaNode(post, className, controls) {
    const url = Core.safeUrl(post.media_url || post.image_url);
    if (!url) return null;
    if (Core.isVideoMedia(post)) {
      return h("video", { class: className, src: url, muted: true, playsinline: true, preload: "metadata", controls: controls ? true : null });
    }
    return h("img", { class: className, src: url, alt: "", loading: "lazy", decoding: "async" });
  }

  function registrationButton(post) {
    if (!post.is_event || !post.has_registration) return null;
    const ended = post.event_end && Date.parse(post.event_end) < Date.now();
    if (ended) return h("span", { class: "count", text: "Evento finalizado" });
    if (!state.token) return h("a", { class: "btn btn-secondary btn-small", href: "/api/auth/login-google?return_to=campus", text: "Inicia sesión para inscribirte" });
    const registered = Boolean(post.is_registered);
    const button = h("button", {
      class: `btn btn-small ${registered ? "btn-secondary" : "btn-primary"}`,
      type: "button",
      "data-register": String(post.id),
      text: registered ? "Cancelar inscripción" : "Inscripción",
    });
    button.addEventListener("click", () => track(toggleRegistration(post.id, registered, button)));
    return button;
  }

  function feedCard(post, urgent) {
    const kind = urgent ? "urgent" : Core.postKind(post);
    const media = urgent ? null : mediaNode(post, "card-media");
    const open = h(
      "button",
      { class: "card-open", type: "button", "data-post-id": String(post.id) },
      media,
      h(
        "div",
        { class: "card-body" },
        h(
          "div",
          { class: "card-meta" },
          kindBadge(kind),
          post.is_pinned ? h("span", { class: "pin", text: "Fijado" }) : null,
          h("span", { text: postTimeLine(post) }),
        ),
        h("h3", { class: "card-title", text: post.title }),
        h("p", { class: "card-summary", text: post.summary || post.content || "" }),
      ),
    );
    open.addEventListener("click", () => openDetail(detailFromPost(post)));

    const actions = urgent ? null : registrationButton(post);
    const article = h("article", { class: `card ${urgent ? "card-urgent" : ""}`, "data-kind": kind }, open);
    if (actions) {
      article.append(
        h("div", { class: "card-actions" }, actions, post.registered_count > 0 ? h("span", { class: "count", text: `${post.registered_count} inscritos` }) : null),
      );
    }
    return article;
  }

  function renderFeed() {
    const list = $("feed-list");
    const urgent = $("urgent-list");
    clear(list);
    clear(urgent);
    state.feed.banners.forEach((b) => urgent.append(feedCard(b, true)));
    state.feed.posts.forEach((p) => list.append(feedCard(p, false)));
    const empty = !state.feed.posts.length && !state.feed.banners.length;
    if (empty && state.feed.error) statusBox($("feed-status"), state.feed.error, () => track(loadFeed({ reset: true })));
    else if (empty && state.feed.loaded) statusBox($("feed-status"), "Todavía no hay publicaciones para mostrar.");
    else statusBox($("feed-status"), "");
    $("feed-more").hidden = !state.feed.hasMore;
    $("login-prompt").hidden = Boolean(state.token);
  }

  /* ------------------------------------------------------------------ detalle */

  function detailFromPost(post) {
    const kind = Core.postKind(post);
    return {
      kind,
      postType: post.post_type || "",
      kindLabel: Core.kindLabel(kind),
      title: post.title,
      meta: postTimeLine(post) || "",
      text: post.content || post.summary || "",
      extra: "",
      media: post,
      source: Core.safeUrl(post.permalink),
      sourceLabel: post.post_type === "INSTAGRAM" ? "Ver en Instagram" : "Ver fuente original",
      linkUrl: Core.safeUrl(post.link_url),
      linkLabel: post.link_label || "Abrir enlace",
      eventId: post.is_event && post.has_registration ? post.id : null,
      isRegistered: Boolean(post.is_registered),
      count: post.registered_count || 0,
      ended: Boolean(post.is_event && post.event_end && Date.parse(post.event_end) < Date.now()),
    };
  }

  function detailFromEntry(entry) {
    const raw = entry.raw;
    if (entry.kind === "deadline") {
      const when = entry.timeLabel ? `${Core.formatDayLong(entry.dayKey)} · ${entry.timeLabel}` : Core.formatDayLong(entry.dayKey);
      return {
        kind: "deadline",
        postType: "",
        kindLabel: "Tarea de Google Classroom",
        title: entry.title,
        meta: [entry.place, when].filter(Boolean).join(" · "),
        text: entry.description,
        extra: "",
        media: null,
        source: "",
        sourceLabel: "",
        linkUrl: entry.link,
        linkLabel: "Abrir en Google Classroom",
        eventId: null,
        isRegistered: false,
        count: 0,
        ended: false,
      };
    }
    const when = `${Core.formatDayLong(entry.dayKey)} · ${entry.timeLabel}`;
    return {
      kind: "event",
      postType: (raw && raw.post_type) || "",
      kindLabel: "Evento",
      title: entry.title,
      meta: [when, entry.place].filter(Boolean).join(" · "),
      text: raw.description || raw.summary || "",
      extra: "",
      media: { media_url: raw.image_url, media_type: "" },
      source: Core.safeUrl(raw.permalink),
      sourceLabel: raw.post_type === "INSTAGRAM" ? "Ver en Instagram" : "Ver fuente original",
      linkUrl: Core.safeUrl(raw.link_url),
      linkLabel: raw.link_label || "Abrir enlace",
      eventId: raw.has_registration ? raw.id : null,
      isRegistered: Boolean(raw.is_registered),
      count: raw.registered_count || 0,
      ended: Boolean(entry.end && entry.end.getTime() < Date.now()),
    };
  }

  function renderDetailActions() {
    const d = state.detail;
    const box = $("detail-actions");
    clear(box);
    if (!d) return;
    if (d.eventId && !d.ended) {
      const button = h("button", {
        class: `btn btn-block ${d.isRegistered ? "btn-secondary" : "btn-primary"}`,
        type: "button",
        id: "detail-register",
        text: d.isRegistered ? "Cancelar inscripción" : "Inscripción",
      });
      button.addEventListener("click", () => track(toggleRegistration(d.eventId, d.isRegistered, button)));
      box.append(button);
      if (d.count > 0) box.append(h("p", { class: "muted small", text: `${d.count} personas inscritas` }));
    }
    const links = Core.resolveDetailLinks(d);
    for (const item of links) {
      box.append(
        h(
          "a",
          {
            class: `btn btn-secondary btn-block ${item.isInstagram ? "btn-instagram" : ""}`.trim(),
            id: item.id,
            href: item.href,
            target: "_blank",
            rel: "noopener noreferrer",
          },
          item.isInstagram ? instagramIcon(18) : null,
          h("span", { text: item.label }),
          externalIcon(),
        ),
      );
    }
  }

  function openDetail(detail) {
    state.detail = detail;
    const kindEl = $("detail-kind");
    clear(kindEl);
    kindEl.className = `badge ${detail.kind === "instagram" ? "badge-instagram" : detail.kind === "urgent" ? "badge-urgent" : ""}`.trim();
    if (detail.kind === "instagram") {
      kindEl.append(instagramIcon(13), h("span", { text: detail.kindLabel }));
    } else {
      kindEl.textContent = detail.kindLabel;
    }
    $("detail-title").textContent = detail.title;
    $("detail-meta").textContent = detail.meta;
    $("detail-text").textContent = detail.text;
    const extra = $("detail-extra");
    extra.textContent = detail.extra;
    extra.hidden = !detail.extra;
    const mediaBox = $("detail-media");
    clear(mediaBox);
    const media = detail.media ? mediaNode(detail.media, "detail-image", true) : null;
    if (media) mediaBox.append(media);
    renderDetailActions();
    $("detail").querySelector(".overlay-body").scrollTop = 0;
    overlays.open("detail");
  }

  function onOverlayChange(stack) {
    const detailOpen = stack.includes("detail");
    $("detail").hidden = !detailOpen;
    $("ios-sheet").hidden = !stack.includes("ios");
    if (!detailOpen) {
      state.detail = null;
      const video = $("detail-media").querySelector("video");
      if (video) video.pause();
      clear($("detail-media"));
    }
  }

  /* ------------------------------------------------------------------ render: agenda */

  function todayKey() {
    return Core.dayKey(new Date());
  }

  function agendaItem(entry) {
    const short = Core.formatDayShort(entry.dayKey);
    const sub = [entry.timeLabel, entry.place].filter(Boolean).join(" · ");
    const open = h(
      "button",
      { class: "agenda-open", type: "button", "data-entry": entry.key },
      h("div", { class: "date-tile" }, h("strong", { text: short.day }), h("span", { text: short.month })),
      h(
        "div",
        { class: "agenda-info" },
        h("b", { text: entry.title }),
        h("small", { text: `${Core.kindLabel(entry.kind)}${sub ? " · " + sub : ""}` }),
        entry.kind === "event" && entry.raw.is_registered ? h("small", { text: " · Inscrito" }) : null,
      ),
    );
    open.addEventListener("click", () => openDetail(detailFromEntry(entry)));
    const item = h("li", { class: `agenda-item agenda-kind-${entry.kind}` }, open);
    if (entry.kind === "deadline" && entry.link) {
      item.append(
        h("a", { class: "ext-link", href: entry.link, target: "_blank", rel: "noopener noreferrer", "aria-label": `Abrir ${entry.title} en Google Classroom`, title: "Abrir en Google Classroom" }, externalIcon()),
      );
    }
    return item;
  }

  function renderAgendaList() {
    const list = $("agenda-list");
    clear(list);
    const entries = state.selectedDay
      ? Core.entriesForDay(state.agenda.entries, state.selectedDay)
      : Core.upcomingEntries(state.agenda.entries, todayKey());
    $("agenda-heading").textContent = state.selectedDay ? Core.formatDayLong(state.selectedDay) : "Próximos eventos y tareas";
    $("agenda-clear").hidden = !state.selectedDay;
    entries.forEach((e) => list.append(agendaItem(e)));
    const statusEl = $("agenda-status");
    if (!state.token) {
      statusBox(statusEl, "Inicia sesión con tu cuenta @upa.edu.py para ver tu agenda y tus tareas de Classroom.");
    } else if (state.agenda.error && !state.agenda.entries.length) {
      statusBox(statusEl, state.agenda.error, () => track(loadAgenda()));
    } else if (state.agenda.loaded && !entries.length) {
      statusBox(statusEl, state.selectedDay ? "No hay eventos ni tareas para este día." : "No hay eventos ni tareas próximos.");
    } else {
      statusBox(statusEl, "");
    }
  }

  function renderCalendar() {
    if (!state.month) {
      const [y, m] = todayKey().split("-").map(Number);
      state.month = { year: y, monthIndex: m - 1 };
    }
    const { year, monthIndex } = state.month;
    $("cal-label").textContent = Core.formatMonthLabel(year, monthIndex);
    const marks = Core.markedDays(state.agenda.entries);
    const grid = $("cal-grid");
    clear(grid);
    WEEKDAYS.forEach((d) => grid.append(h("div", { class: "cal-dow", text: d })));
    const today = todayKey();
    for (const week of Core.monthGrid(year, monthIndex)) {
      for (const cell of week) {
        const mark = marks[cell.key];
        const classes = ["cal-day"];
        if (!cell.inMonth) classes.push("out");
        if (cell.key === today) classes.push("today");
        if (cell.key === state.selectedDay) classes.push("selected");
        const button = h(
          "button",
          { class: classes.join(" "), type: "button", "data-day": cell.key, "aria-pressed": cell.key === state.selectedDay ? "true" : "false", "aria-label": Core.formatDayLong(cell.key) },
          h("span", { text: String(cell.day) }),
          h("span", { class: "dots" }, mark && mark.event ? h("i", { class: "dot dot-event" }) : null, mark && mark.deadline ? h("i", { class: "dot dot-deadline" }) : null),
        );
        button.addEventListener("click", () => selectDay(cell.key));
        grid.append(button);
      }
    }
  }

  function selectDay(key) {
    state.selectedDay = state.selectedDay === key ? null : key;
    renderAgenda();
  }

  function renderAgenda() {
    renderAgendaList();
    renderCalendar();
  }

  /* ------------------------------------------------------------------ render: perfil y tema */

  function applyTheme(preference) {
    const theme = Core.normalizeTheme(preference);
    const root = doc.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    const prefersDark = typeof win.matchMedia === "function" && win.matchMedia("(prefers-color-scheme: dark)").matches;
    const meta = doc.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", Core.THEME_COLORS[Core.resolveTheme(theme, prefersDark)]);
    doc.querySelectorAll("[data-theme-option]").forEach((btn) => {
      btn.setAttribute("aria-checked", btn.getAttribute("data-theme-option") === theme ? "true" : "false");
    });
    return theme;
  }

  function setTheme(preference) {
    const theme = applyTheme(preference);
    local.setItem(THEME_KEY, theme);
  }

  function renderProfile() {
    const user = state.user;
    $("profile-guest").hidden = Boolean(state.token);
    $("profile-user").hidden = !state.token;
    $("btn-logout").hidden = !state.token;
    if (state.token) {
      const name = (user && user.full_name) || "Usuario UPA";
      $("profile-avatar").textContent = Core.initials(name);
      $("profile-name").textContent = name;
      $("profile-email").textContent = (user && user.email) || "";
      if ($("profile-role")) $("profile-role").textContent = user ? Core.roleLabel(user) : "";
    }
    doc.querySelectorAll("[data-notify]").forEach((input) => {
      input.checked = Boolean(state.prefs[input.getAttribute("data-notify")]);
    });
  }

  function notificationsSupported() {
    return typeof win.Notification === "function";
  }

  async function onNotifyToggle(event) {
    const input = event.target;
    state.prefs[input.getAttribute("data-notify")] = input.checked;
    Core.saveNotificationPrefs(local, state.prefs);
    const hint = $("notify-hint");
    hint.hidden = true;
    if (!input.checked) return;
    if (!notificationsSupported()) {
      hint.textContent = "Este navegador no admite notificaciones. En iPhone, instala la app en la pantalla de inicio.";
      hint.hidden = false;
      return;
    }
    if (win.Notification.permission === "default") {
      try {
        await win.Notification.requestPermission();
      } catch (_) {
        /* el navegador rechazo la solicitud */
      }
    }
    if (win.Notification.permission === "denied") {
      hint.textContent = "Las notificaciones están bloqueadas en tu navegador. Habilítalas en los ajustes del sitio.";
      hint.hidden = false;
      return;
    }
    maybeNotify();
  }

  async function showNotification(item) {
    const options = { body: item.body, tag: item.id, icon: "/campus/icons/icon-192.png", badge: "/campus/icons/favicon-32.png" };
    try {
      if ("serviceWorker" in win.navigator) {
        const registration = await win.navigator.serviceWorker.getRegistration();
        if (registration) {
          await registration.showNotification(item.title, options);
          return;
        }
      }
      new win.Notification(item.title, options);
    } catch (_) {
      /* la plataforma no permite mostrar la notificacion */
    }
  }

  function maybeNotify() {
    if (!state.token || !notificationsSupported() || win.Notification.permission !== "granted") return;
    let seen = [];
    try {
      seen = JSON.parse(local.getItem(NOTIFIED_KEY) || "[]");
    } catch (_) {
      seen = [];
    }
    const due = Core.pickDueNotifications({ prefs: state.prefs, entries: state.agenda.entries, banners: state.feed.banners, seen });
    if (!due.length) return;
    due.forEach((item) => track(showNotification(item)));
    local.setItem(NOTIFIED_KEY, JSON.stringify([...seen, ...due.map((d) => d.id)].slice(-200)));
  }

  /* ------------------------------------------------------------------ navegacion */

  const TITLES = { inicio: "Inicio", agenda: "Agenda", perfil: "Perfil" };

  function showTab(tab) {
    state.tab = tab;
    ["inicio", "agenda", "perfil"].forEach((name) => {
      $(`view-${name}`).hidden = name !== tab;
    });
    doc.querySelectorAll(".tab").forEach((btn) => {
      if (btn.getAttribute("data-tab") === tab) btn.setAttribute("aria-current", "page");
      else btn.removeAttribute("aria-current");
    });
    $("view-title").textContent = TITLES[tab];
    if (tab === "agenda") {
      renderAgenda();
      if (!state.agenda.loaded || Date.now() - state.lastRefresh > REFRESH_AFTER_MS) track(loadAgenda());
    }
    if (tab === "perfil") renderProfile();
  }

  function renderAll() {
    renderFeed();
    renderAgenda();
    renderProfile();
    showTab(state.tab);
  }

  /* ------------------------------------------------------------------ instalacion */

  function installState() {
    const env = readEnvironment();
    let dismissedAt = 0;
    try {
      dismissedAt = Number(local.getItem(INSTALL_KEY)) || 0;
    } catch (_) {
      dismissedAt = 0;
    }
    return {
      platform: Core.detectInstallPlatform(env),
      hasPrompt: Boolean(state.installPrompt),
      dismissedAt,
    };
  }

  function renderInstallBanner() {
    const info = installState();
    const show = Core.shouldShowInstallBanner(info);
    $("install-banner").hidden = !show;
    $("install-action").textContent = info.platform === "ios" ? "Ver cómo" : "Instalar";
  }

  async function onInstallAction() {
    const info = installState();
    if (info.platform === "ios") {
      overlays.open("ios");
      return;
    }
    if (!state.installPrompt) return;
    const promptEvent = state.installPrompt;
    state.installPrompt = null;
    try {
      await promptEvent.prompt();
      await promptEvent.userChoice;
    } catch (_) {
      /* el usuario cerro el dialogo de instalacion */
    }
    renderInstallBanner();
  }

  /* ------------------------------------------------------------------ landing de escritorio */

  function isDesktopWebPreview() {
    const baseEnv = { ...readEnvironment(), search: "" };
    return !Core.isMobileEnvironment(baseEnv);
  }

  function updateDesktopReturnBar() {
    const bar = $("desktop-return-bar");
    if (bar) bar.hidden = !isDesktopWebPreview();
  }

  function showLanding() {
    $("landing").hidden = false;
    $("app").hidden = true;
    if ($("desktop-return-bar")) $("desktop-return-bar").hidden = true;
    const url = `${win.location.origin}/`;
    $("qr-url").textContent = url;
    const box = $("qr-box");
    clear(box);
    try {
      const qr = Core.buildQr(url, win.qrcode, { margin: 2 });
      box.innerHTML = qr.svg;
    } catch (_) {
      box.textContent = url;
    }
  }

  function returnToLanding() {
    session.removeItem(FORCE_APP_KEY);
    try {
      win.history.replaceState(null, "", win.location.pathname);
    } catch (_) {
      /* el historial no admite replaceState en este contexto */
    }
    if (overlays) overlays.closeAll();
    showLanding();
  }

  /* ------------------------------------------------------------------ arranque */

  function registerServiceWorker() {
    if (!("serviceWorker" in win.navigator)) return;
    const secure = win.isSecureContext || /^(localhost|127\.0\.0\.1)$/.test(win.location.hostname);
    if (!secure) return;
    win.navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      /* sin service worker la app sigue funcionando en linea */
    });
  }

  let eventsBound = false;

  function bindEvents() {
    if (eventsBound) return;
    eventsBound = true;
    const tryWeb = $("try-web-link") || doc.querySelector(".landing-link");
    if (tryWeb) {
      tryWeb.addEventListener("click", (event) => {
        event.preventDefault();
        session.setItem(FORCE_APP_KEY, "1");
        try {
          win.history.replaceState(null, "", "/?app=1");
        } catch (_) {
          /* el historial no admite replaceState en este contexto */
        }
        track(enterApp({}));
      });
    }
    if ($("btn-back-landing")) {
      $("btn-back-landing").addEventListener("click", () => returnToLanding());
    }
    doc.querySelectorAll(".tab").forEach((btn) => btn.addEventListener("click", () => showTab(btn.getAttribute("data-tab"))));
    $("btn-refresh").addEventListener("click", () => {
      toast("Actualizando…");
      track(refreshAll());
    });
    $("feed-more").addEventListener("click", () => track(loadFeed({ reset: false })));
    $("detail-close").addEventListener("click", () => overlays.close());
    $("ios-close").addEventListener("click", () => overlays.close());
    $("agenda-clear").addEventListener("click", () => {
      state.selectedDay = null;
      renderAgenda();
    });
    $("cal-prev").addEventListener("click", () => {
      state.month = Core.shiftMonth(state.month.year, state.month.monthIndex, -1);
      renderCalendar();
    });
    $("cal-next").addEventListener("click", () => {
      state.month = Core.shiftMonth(state.month.year, state.month.monthIndex, 1);
      renderCalendar();
    });
    doc.querySelectorAll("[data-theme-option]").forEach((btn) => btn.addEventListener("click", () => setTheme(btn.getAttribute("data-theme-option"))));
    doc.querySelectorAll("[data-notify]").forEach((input) => input.addEventListener("change", (ev) => track(onNotifyToggle(ev))));
    $("btn-logout").addEventListener("click", () => track(logout("Sesión cerrada.")));
    $("install-action").addEventListener("click", () => track(onInstallAction()));
    $("install-dismiss").addEventListener("click", () => {
      local.setItem(INSTALL_KEY, String(Date.now()));
      renderInstallBanner();
    });

    win.addEventListener("online", () => track(refreshAll()));
    win.addEventListener("offline", () => setOffline(true, state.feed.posts.length > 0));
    win.addEventListener("beforeinstallprompt", (event) => {
      event.preventDefault();
      state.installPrompt = event;
      renderInstallBanner();
    });
    win.addEventListener("appinstalled", () => {
      state.installPrompt = null;
      renderInstallBanner();
    });
    doc.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && overlays && overlays.depth()) overlays.close();
    });
    doc.addEventListener("visibilitychange", () => {
      if (doc.visibilityState === "visible" && state.token && Date.now() - state.lastRefresh > REFRESH_AFTER_MS) track(refreshAll());
    });
    if (typeof win.matchMedia === "function") {
      const query = win.matchMedia("(prefers-color-scheme: dark)");
      if (query.addEventListener) query.addEventListener("change", () => applyTheme(local.getItem(THEME_KEY)));
    }
  }

  async function enterApp(auth) {
    $("landing").hidden = true;
    $("app").hidden = false;
    updateDesktopReturnBar();
    if (!api) {
      api = Core.createApi({
        baseUrl: "",
        getToken: () => state.token,
        onUnauthorized: () => {
          if (state.token) track(logout("Tu sesión expiró. Inicia sesión nuevamente."));
        },
      });
    }
    if (!overlays) overlays = Core.createOverlayManager(win, onOverlayChange);
    bindEvents();
    registerServiceWorker();
    renderInstallBanner();
    renderAll();
    if (auth && auth.error) toast(Core.translateAuthError(auth.error));
    else if (auth && auth.token) toast("Sesión iniciada.");
    if (!win.navigator.onLine) setOffline(true, false);
    await refreshAll();
  }

  async function start() {
    applyTheme(local.getItem(THEME_KEY));
    const auth = consumeAuthFragment();
    state.token = loadStoredToken();
    bindEvents();

    const env = readEnvironment();
    if (!Core.isMobileEnvironment(env)) {
      showLanding();
      return;
    }
    if (/(^|[?&])app=1(&|$)/.test(String(win.location.search || ""))) session.setItem(FORCE_APP_KEY, "1");

    await enterApp(auth);
  }

  let bootPromise = null;
  function boot() {
    if (!bootPromise) bootPromise = track(start());
    return bootPromise;
  }

  win.UpaCampus = {
    state,
    boot,
    start,
    idle: async () => {
      if (bootPromise) await bootPromise;
      while (pending.size) await Promise.allSettled([...pending]);
    },
    openDetail: (detail) => openDetail(detail),
    refresh: () => track(refreshAll()),
  };

  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
