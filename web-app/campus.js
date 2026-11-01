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
  const DEFAULT_AGENDA_MODE = "timeline";
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
    agendaMode: DEFAULT_AGENDA_MODE,
    detail: null,
    offline: false,
    isBeta: false,
    installPrompt: null,
    lastRefresh: 0,
    prefs: Core.loadNotificationPrefs(local),
  };

  const pending = new Set();
  let overlays = null;
  let api = null;
  let toastTimer = null;
  let highlightTimer = null;
  let swRegistration = null;

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
    if (toastTimer && typeof toastTimer.unref === "function") toastTimer.unref();
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

  function upaIcon(size) {
    const px = String(size || 13);
    const svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", px);
    svg.setAttribute("height", px);
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", "upa-u-glyph");
    const path = doc.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M4 3h5v10.2c0 2.2 1.2 3.5 3 3.5s3-1.3 3-3.5V3h5v10.2C20 18.5 16.8 21 12 21S4 18.5 4 13.2V3z");
    path.setAttribute("fill", "currentColor");
    svg.appendChild(path);
    return svg;
  }

  function classroomIcon(size) {
    const px = String(size || 13);
    const svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", px);
    svg.setAttribute("height", px);
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", "classroom-glyph");
    const board = doc.createElementNS("http://www.w3.org/2000/svg", "rect");
    board.setAttribute("x", "2");
    board.setAttribute("y", "3");
    board.setAttribute("width", "20");
    board.setAttribute("height", "16");
    board.setAttribute("rx", "2.5");
    board.setAttribute("fill", "none");
    board.setAttribute("stroke", "currentColor");
    board.setAttribute("stroke-width", "2");
    const head = doc.createElementNS("http://www.w3.org/2000/svg", "circle");
    head.setAttribute("cx", "12");
    head.setAttribute("cy", "9.5");
    head.setAttribute("r", "2.4");
    head.setAttribute("fill", "currentColor");
    const body = doc.createElementNS("http://www.w3.org/2000/svg", "path");
    body.setAttribute("d", "M7.5 16c0-2.1 2-3.4 4.5-3.4s4.5 1.3 4.5 3.4M6 21h12");
    body.setAttribute("fill", "none");
    body.setAttribute("stroke", "currentColor");
    body.setAttribute("stroke-width", "2");
    body.setAttribute("stroke-linecap", "round");
    svg.append(board, head, body);
    return svg;
  }

  function kindBadge(kind, labelText, floating) {
    const floatCls = floating ? " badge-floating" : "";
    if (kind === "instagram") {
      return h("span", { class: `badge badge-instagram${floatCls}` }, instagramIcon(13), h("span", { text: labelText || "Instagram" }));
    }
    if (kind === "campus" || kind === "news") {
      return h("span", { class: `badge badge-campus${floatCls}` }, upaIcon(13), h("span", { text: labelText || "Campus" }));
    }
    if (kind === "deadline" || kind === "classroom") {
      return h("span", { class: `badge badge-classroom${floatCls}` }, classroomIcon(13), h("span", { text: labelText || "Google Classroom" }));
    }
    if (kind === "event") {
      return h("span", { class: `badge badge-event${floatCls}`, text: labelText || "Evento" });
    }
    if (kind === "urgent") {
      return h("span", { class: `badge badge-urgent${floatCls}`, text: labelText || Core.kindLabel(kind) });
    }
    return h("span", { class: `badge${floatCls}`, text: labelText || Core.kindLabel(kind) });
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
      hostname: win.location.hostname || "",
      port: win.location.port || "",
      search: forced && !/app=1/.test(search) ? `${search}&app=1` : search,
    };
  }

  function updateBetaIndicator(appEnv) {
    const isBeta =
      state.isBeta ||
      Core.isBetaEnvironment({
        hostname: win.location.hostname || "",
        port: win.location.port || "",
        search: win.location.search || "",
        appEnv: appEnv || "",
      });
    state.isBeta = isBeta;
    ["beta-badge", "landing-beta-badge", "profile-beta-badge"].forEach((id) => {
      const el = $(id);
      if (el) el.hidden = !isBeta;
    });
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
    const targetId = String(updated.id);
    state.feed.posts = state.feed.posts.map((p) =>
      String(p.id) === targetId
        ? { ...p, is_registered: updated.is_registered, registered_count: updated.registered_count }
        : p,
    );
    state.agenda.entries = Core.applyRegistration(state.agenda.entries, updated);
    cache.set(`feed:${currentUserKey()}`, state.feed);
    const agendaKey = `agenda:${currentUserKey()}`;
    const cachedAgenda = cache.get(agendaKey);
    if (cachedAgenda && cachedAgenda.data && Array.isArray(cachedAgenda.data.events)) {
      cache.set(agendaKey, {
        ...cachedAgenda.data,
        events: cachedAgenda.data.events.map((ev) =>
          String(ev.id) === targetId
            ? { ...ev, is_registered: updated.is_registered, registered_count: updated.registered_count }
            : ev,
        ),
      });
    }
    renderFeed();
    renderAgenda();
    if (
      state.detail &&
      (String(state.detail.eventId) === targetId || String(state.detail.postId) === targetId)
    ) {
      state.detail.hasRegistration = true;
      state.detail.eventId = updated.id;
      state.detail.isRegistered = Boolean(updated.is_registered);
      state.detail.count = Number(updated.registered_count) || 0;
      renderDetailEventCard();
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
    if (!url && !Core.isVideoMedia(post)) return null;
    if (Core.isVideoMedia(post)) {
      const poster = Core.videoPosterUrl(post);
      return h("video", {
        class: className,
        src: url || null,
        poster,
        muted: true,
        playsinline: true,
        preload: "metadata",
        controls: controls ? true : null,
      });
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
    const origin = urgent ? "urgent" : Core.postOrigin(post);
    const media = urgent ? null : mediaNode(post, "card-media");
    const badge = kindBadge(origin, Core.originLabel(origin), Boolean(media));
    const eventBadge = !urgent && post.is_event ? kindBadge("event", "Evento", false) : null;
    const mediaWrap = media ? h("div", { class: "card-media-wrap" }, media, badge) : null;
    const headerRow = !media
      ? h(
          "div",
          { class: "card-header" },
          h("div", { class: "card-badges" }, badge, eventBadge),
          post.is_pinned ? h("span", { class: "pin", text: "Fijado" }) : null,
        )
      : null;
    const summaryText = Core.postSummary(post);
    const open = h(
      "button",
      { class: "card-open", type: "button", "data-post-id": String(post.id) },
      mediaWrap,
      h(
        "div",
        { class: "card-body" },
        headerRow,
        h(
          "div",
          { class: "card-meta" },
          media && post.is_pinned ? h("span", { class: "pin", text: "Fijado" }) : null,
          h("span", { class: "card-time", text: postTimeLine(post) }),
        ),
        h("h3", { class: "card-title", text: post.title }),
        summaryText ? h("p", { class: "card-summary", text: summaryText }) : null,
      ),
    );
    open.addEventListener("click", () => openDetail(detailFromPost(post)));

    const actions = urgent ? null : registrationButton(post);
    const article = h("article", { class: `card ${urgent ? "card-urgent" : ""}`.trim(), "data-kind": kind, "data-origin": origin }, open);
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
    const origin = Core.postOrigin(post);
    const isEvent = Boolean(post.is_event);
    return {
      postId: post.id,
      kind,
      origin,
      isEvent,
      postType: post.post_type || "",
      kindLabel: Core.originLabel(origin),
      title: post.title,
      meta: postTimeLine(post) || "",
      text: post.content || post.caption || post.summary || "",
      extra: "",
      media: post,
      source: Core.safeUrl(post.permalink),
      sourceLabel: post.post_type === "INSTAGRAM" ? "Ver en Instagram" : "Ver fuente original",
      linkUrl: Core.safeUrl(post.link_url),
      linkLabel: post.link_label || "Abrir enlace",
      eventStart: isEvent ? post.event_start || "" : "",
      eventEnd: isEvent ? post.event_end || "" : "",
      location: isEvent ? post.location || "" : "",
      hasRegistration: Boolean(isEvent && post.has_registration),
      eventId: isEvent && post.has_registration ? post.id : null,
      isRegistered: Boolean(post.is_registered),
      count: post.registered_count || 0,
      ended: Boolean(isEvent && post.event_end && Date.parse(post.event_end) < Date.now()),
    };
  }

  function detailFromEntry(entry) {
    const raw = entry.raw || {};
    if (entry.kind === "deadline") {
      const dueTime = entry.timeLabel || "23:59";
      const dueLabel = entry.dueLabel || `Vence ${dueTime} hs`;
      const when = `${Core.formatDayLong(entry.dayKey)} · ${dueLabel}`;
      return {
        postId: entry.id,
        kind: "deadline",
        origin: "deadline",
        isEvent: false,
        postType: "",
        kindLabel: "Google Classroom",
        title: entry.title,
        meta: [entry.place, when].filter(Boolean).join(" · "),
        text: entry.description,
        extra: "",
        media: null,
        source: "",
        sourceLabel: "",
        linkUrl: entry.link,
        linkLabel: "Abrir en Google Classroom",
        eventStart: "",
        eventEnd: "",
        location: "",
        hasRegistration: false,
        eventId: null,
        isRegistered: false,
        count: 0,
        ended: false,
      };
    }
    const postId = raw.id !== undefined ? raw.id : entry.id;
    const feedPost = state.feed.posts.find((p) => String(p.id) === String(postId)) || {};
    const permalink = raw.permalink || feedPost.permalink || entry.link || "";
    const isInsta = Boolean(
      raw.post_type === "INSTAGRAM" ||
        feedPost.post_type === "INSTAGRAM" ||
        /instagram\.com/i.test(String(permalink)),
    );
    const hasRegistration = Boolean(
      entry.hasRegistration || raw.has_registration || feedPost.has_registration,
    );
    const isRegistered = Boolean(
      entry.isRegistered !== undefined
        ? entry.isRegistered
        : raw.is_registered !== undefined
          ? raw.is_registered
          : feedPost.is_registered,
    );
    const registeredCount =
      entry.registeredCount !== undefined
        ? entry.registeredCount
        : raw.registered_count !== undefined
          ? raw.registered_count
          : feedPost.registered_count || 0;
    return detailFromPost({
      ...feedPost,
      ...raw,
      id: postId,
      is_event: true,
      post_type: isInsta ? "INSTAGRAM" : raw.post_type || feedPost.post_type || "MANUAL",
      title: entry.title || raw.title || feedPost.title || "",
      content: raw.content || feedPost.content || raw.description || entry.description || raw.summary || feedPost.summary || "",
      summary: raw.summary || feedPost.summary || entry.description || "",
      media_url: raw.media_url || feedPost.media_url || raw.image_url || feedPost.image_url || "",
      image_url: raw.image_url || feedPost.image_url || raw.media_url || feedPost.media_url || "",
      media_type: raw.media_type || feedPost.media_type || "",
      permalink,
      link_url: raw.link_url || feedPost.link_url || "",
      link_label: raw.link_label || feedPost.link_label || "",
      event_start: raw.event_start || feedPost.event_start || (entry.date ? entry.date.toISOString() : ""),
      event_end: raw.event_end || feedPost.event_end || (entry.end ? entry.end.toISOString() : ""),
      location: entry.place || raw.location || feedPost.location || "",
      has_registration: hasRegistration,
      is_registered: isRegistered,
      registered_count: registeredCount,
    });
  }

  function renderDetailEventCard() {
    const card = $("detail-event-card");
    if (!card) return;
    clear(card);
    const d = state.detail;
    if (!d || (d.kind !== "event" && !d.isEvent) || !d.eventStart) {
      card.hidden = true;
      return;
    }
    const sched = Core.formatEventSchedule(d.eventStart, d.eventEnd);
    if (!sched.dayKey) {
      card.hidden = true;
      return;
    }
    let statusText = "Entrada libre";
    let statusClass = "badge detail-status-badge";
    if (d.ended) {
      statusText = "Evento finalizado";
      statusClass += " detail-status-ended";
    } else if (d.isRegistered) {
      statusText = d.count > 0 ? `Inscrito · ${d.count} inscritos` : "Inscrito";
      statusClass += " detail-status-registered";
    } else if (d.hasRegistration || d.eventId) {
      statusText = d.count > 0 ? `Inscripción abierta · ${d.count} inscritos` : "Inscripción abierta";
    }

    card.append(
      h(
        "div",
        { class: "detail-event-head" },
        h("div", { class: "date-tile detail-date-tile" }, h("strong", { text: sched.day }), h("span", { text: sched.month })),
        h(
          "div",
          { class: "detail-event-primary" },
          h("strong", { class: "detail-event-date", text: sched.dateLong }),
          h("span", { class: "detail-event-time", text: `Horario: ${sched.timeRange} hs` }),
        ),
      ),
      h(
        "div",
        { class: "detail-event-rows" },
        h(
          "div",
          { class: "detail-event-row" },
          h("span", { class: "detail-event-label", text: "Lugar" }),
          h("strong", { class: "detail-event-value", text: d.location || "Campus UPA" }),
        ),
        h(
          "div",
          { class: "detail-event-row" },
          h("span", { class: "detail-event-label", text: "Estado" }),
          h("span", { class: statusClass, id: "detail-event-status", text: statusText }),
        ),
      ),
    );
    card.hidden = false;
  }

  function renderDetailActions() {
    const d = state.detail;
    const box = $("detail-actions");
    clear(box);
    if (!d) return;
    const regEventId = d.eventId || (d.hasRegistration ? d.postId : null);
    if (regEventId && !d.ended) {
      const button = h("button", {
        class: `btn btn-block ${d.isRegistered ? "btn-secondary" : "btn-primary"}`,
        type: "button",
        id: "detail-register",
        text: d.isRegistered ? "Cancelar inscripción" : "Inscripción",
      });
      button.addEventListener("click", () => track(toggleRegistration(regEventId, d.isRegistered, button)));
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
    const origin =
      detail.origin ||
      (detail.postType === "INSTAGRAM" || detail.kind === "instagram"
        ? "instagram"
        : detail.kind === "urgent"
          ? "urgent"
          : detail.kind === "deadline"
            ? "deadline"
            : "campus");
    if (origin === "instagram") {
      kindEl.className = "badge badge-instagram";
      kindEl.append(instagramIcon(13), h("span", { text: detail.kindLabel || "Instagram" }));
    } else if (origin === "campus") {
      kindEl.className = "badge badge-campus";
      kindEl.append(upaIcon(13), h("span", { text: detail.kindLabel || "Campus" }));
    } else if (origin === "deadline") {
      kindEl.className = "badge badge-classroom";
      kindEl.append(classroomIcon(13), h("span", { text: detail.kindLabel || "Google Classroom" }));
    } else if (origin === "urgent") {
      kindEl.className = "badge badge-urgent";
      kindEl.textContent = detail.kindLabel || "Aviso urgente";
    } else {
      kindEl.className = "badge";
      kindEl.textContent = detail.kindLabel;
    }
    const mediaBox = $("detail-media");
    clear(mediaBox);
    const media = detail.media ? mediaNode(detail.media, "detail-image", true) : null;
    if (media) mediaBox.append(media);
    mediaBox.hidden = !media;

    $("detail-title").textContent = detail.title;
    $("detail-meta").textContent = detail.meta;
    $("detail-meta").hidden = Boolean((detail.kind === "event" || detail.isEvent) && detail.eventStart);

    const textEl = $("detail-text");
    textEl.innerHTML = Core.linkifyText(detail.text);
    textEl.hidden = !detail.text;

    const extra = $("detail-extra");
    extra.innerHTML = Core.linkifyText(detail.extra);
    extra.hidden = !detail.extra;

    renderDetailEventCard();
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
    const raw = entry.raw || {};
    let infoNode;

    if (entry.kind === "deadline") {
      const dueTime = entry.timeLabel || "23:59";
      const dueText = entry.dueLabel || `Vence ${dueTime} hs`;
      const courseText = entry.courseName || entry.place || raw.course_name || raw.course || "Google Classroom";
      infoNode = h(
        "div",
        { class: "agenda-info" },
        h(
          "div",
          { class: "agenda-badges" },
          kindBadge("deadline", "Google Classroom", false),
          h("span", { class: "agenda-due-badge", text: dueText }),
        ),
        h("b", { class: "agenda-title", text: entry.title }),
        h(
          "small",
          { class: "agenda-meta" },
          h("span", { class: "agenda-course", text: courseText }),
          " · ",
          h("span", { class: "agenda-due", text: dueText }),
        ),
      );
    } else {
      const timeText = entry.timeRange || entry.timeLabel;
      const roomText = entry.place || raw.location || "Campus UPA";
      const regCount =
        entry.registeredCount !== undefined ? entry.registeredCount : Number(raw.registered_count) || 0;
      const isReg = Boolean(entry.isRegistered !== undefined ? entry.isRegistered : raw.is_registered);
      const attendeesText = `${regCount} inscritos`;
      infoNode = h(
        "div",
        { class: "agenda-info" },
        h(
          "div",
          { class: "agenda-badges" },
          h("span", { class: "badge badge-campus badge-event" }, upaIcon(12), h("span", { text: "Evento Campus" })),
          isReg ? h("span", { class: "badge badge-registered", text: "Inscrito" }) : null,
        ),
        h("b", { class: "agenda-title", text: entry.title }),
        h(
          "small",
          { class: "agenda-meta" },
          timeText ? h("span", { class: "agenda-time", text: `${timeText} hs` }) : null,
          timeText ? " · " : null,
          h("span", { class: "agenda-room", text: roomText }),
          " · ",
          h("span", { class: "agenda-attendees", text: attendeesText }),
        ),
      );
    }

    const open = h(
      "button",
      { class: "agenda-open", type: "button", "data-entry": entry.key },
      h(
        "div",
        { class: `date-tile date-tile-${entry.kind}` },
        h("strong", { text: short.day }),
        h("span", { text: short.month }),
      ),
      infoNode,
    );
    open.addEventListener("click", () => openDetail(detailFromEntry(entry)));
    const item = h("li", { class: `agenda-item agenda-kind-${entry.kind}`, "data-agenda-day": entry.dayKey }, open);
    if (entry.kind === "deadline" && entry.link) {
      item.append(
        h("a", { class: "ext-link", href: entry.link, target: "_blank", rel: "noopener noreferrer", "aria-label": `Abrir ${entry.title} en Google Classroom`, title: "Abrir en Google Classroom" }, externalIcon()),
      );
    }
    return item;
  }

  function renderAgendaStatus(entries, emptyMessage) {
    const statusEl = $("agenda-status");
    if (!state.token) {
      statusBox(statusEl, "Inicia sesión con tu cuenta @upa.edu.py para ver tu agenda y tus tareas de Classroom.");
    } else if (state.agenda.error && !state.agenda.entries.length) {
      statusBox(statusEl, state.agenda.error, () => track(loadAgenda()));
    } else if (state.agenda.loaded && !entries.length) {
      statusBox(statusEl, emptyMessage);
    } else {
      statusBox(statusEl, "");
    }
  }

  /**
   * Modo alternativo de agenda por dia individual (conservado como modulo conmutable).
   * Filtra la lista superior exclusivamente al dia seleccionado (`state.selectedDay`).
   * Se activa mediante `UpaCampus.setAgendaMode("single-day")` o invocando `renderAgendaSingleDay()`.
   */
  function renderAgendaSingleDay() {
    const list = $("agenda-list");
    clear(list);
    const entries = state.selectedDay
      ? Core.entriesForDay(state.agenda.entries, state.selectedDay)
      : Core.upcomingEntries(state.agenda.entries, todayKey());
    $("agenda-heading").textContent = state.selectedDay ? Core.formatDayLong(state.selectedDay) : "Próximos eventos y tareas";
    $("agenda-clear").hidden = !state.selectedDay;
    entries.forEach((e) => list.append(agendaItem(e)));
    renderAgendaStatus(entries, state.selectedDay ? "No hay eventos ni tareas para este día." : "No hay eventos próximos");
  }

  /**
   * Modo predeterminado de linea de tiempo cronologica (`state.agendaMode === "timeline"`).
   * Filtra estrictamente desde `todayKey()` hacia el futuro (sin caer en datos historicos),
   * y solo muestra meses pasados cuando el usuario los selecciona explicitamente en el calendario.
   */
  function renderAgendaTimeline() {
    const list = $("agenda-list");
    clear(list);
    const today = todayKey();
    const pastMonth = Boolean(
      state.month && Core.isPastMonth(state.month.year, state.month.monthIndex, today),
    );
    const entries = Core.filterAgendaTimeline(state.agenda.entries, {
      todayKey: today,
      month: state.month,
    });
    const groups = Core.groupAgendaByMonth(entries);
    $("agenda-heading").textContent = pastMonth
      ? Core.formatMonthLabel(state.month.year, state.month.monthIndex)
      : "Próximos eventos y tareas";
    $("agenda-clear").hidden = !state.selectedDay;
    for (const group of groups) {
      list.append(h("li", { class: "agenda-month-header", "data-month": group.monthKey, text: group.label }));
      for (const entry of group.entries) {
        const item = agendaItem(entry);
        if (state.selectedDay && entry.dayKey === state.selectedDay) {
          item.classList.add("agenda-item-highlight");
        }
        list.append(item);
      }
    }
    renderAgendaStatus(entries, "No hay eventos próximos");
  }

  function scrollToAgendaDay(key) {
    const list = $("agenda-list");
    if (!list) return false;
    clearTimeout(highlightTimer);
    list.querySelectorAll(".agenda-item-highlight").forEach((el) => el.classList.remove("agenda-item-highlight"));
    if (!key) return false;
    const matches = [...list.querySelectorAll(`.agenda-item[data-agenda-day="${key}"]`)];
    if (!matches.length) return false;
    matches.forEach((el) => el.classList.add("agenda-item-highlight"));
    const first = matches[0];
    const container = doc.querySelector(".agenda-top");
    if (container && typeof container.scrollTo === "function") {
      const top = Math.max(0, (first.offsetTop || 0) - (container.offsetTop || 0) - 8);
      container.scrollTo({ top, behavior: "smooth" });
    }
    if (typeof first.scrollIntoView === "function") {
      first.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    highlightTimer = setTimeout(() => {
      matches.forEach((el) => el.classList.remove("agenda-item-highlight"));
    }, 1800);
    if (highlightTimer && typeof highlightTimer.unref === "function") highlightTimer.unref();
    return true;
  }

  function renderAgendaList() {
    if (state.agendaMode === "single-day") {
      renderAgendaSingleDay();
    } else {
      renderAgendaTimeline();
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
    if (state.agendaMode === "single-day") {
      state.selectedDay = state.selectedDay === key ? null : key;
      renderAgenda();
      return;
    }
    state.selectedDay = key;
    renderAgenda();
    scrollToAgendaDay(key);
  }

  function setAgendaMode(mode) {
    state.agendaMode = mode === "single-day" ? "single-day" : "timeline";
    renderAgenda();
  }

  function renderAgenda() {
    if (!state.month) {
      const [y, m] = todayKey().split("-").map(Number);
      state.month = { year: y, monthIndex: m - 1 };
    }
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
    const resolved = Core.resolveTheme(theme, prefersDark);
    root.setAttribute("data-resolved-theme", resolved);
    const meta = doc.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", Core.THEME_COLORS[resolved]);
    const isDark = resolved === "dark";
    doc.querySelectorAll(".logo-light").forEach((el) => {
      el.hidden = isDark;
    });
    doc.querySelectorAll(".logo-dark").forEach((el) => {
      el.hidden = !isDark;
    });
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
      const name = (user && user.full_name) || (user && user.email ? user.email.split("@")[0] : "Cuenta UPA");
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
    const enteringAgenda = tab === "agenda" && state.tab !== "agenda";
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
      if (enteringAgenda) {
        const [y, m] = todayKey().split("-").map(Number);
        state.month = { year: y, monthIndex: m - 1 };
        state.selectedDay = null;
      }
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

  function renderQrCode() {
    const url = `${win.location.origin}/`;
    if ($("qr-url")) $("qr-url").textContent = url;
    const box = $("qr-box");
    if (!box) return;
    clear(box);
    try {
      const qr = Core.buildQr(url, win.qrcode, { margin: 2 });
      box.innerHTML = qr.svg;
    } catch (_) {
      box.textContent = url;
    }
  }

  function mountAppLayout(framed) {
    const appEl = $("app");
    const screen = $("phone-screen");
    if (framed && screen) {
      if (appEl.parentElement !== screen) screen.appendChild(appEl);
      appEl.classList.add("app-framed");
      $("landing").hidden = false;
      appEl.hidden = false;
      if ($("desktop-return-bar")) $("desktop-return-bar").hidden = true;
      renderQrCode();
    } else {
      if (appEl.parentElement !== doc.body) doc.body.appendChild(appEl);
      appEl.classList.remove("app-framed");
      $("landing").hidden = true;
      appEl.hidden = false;
      updateDesktopReturnBar();
    }
  }

  function showLanding() {
    mountAppLayout(true);
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
    const sw = win.navigator.serviceWorker;
    const hadController = Boolean(sw.controller);
    let refreshing = false;
    if (typeof sw.addEventListener === "function") {
      sw.addEventListener("controllerchange", () => {
        if (refreshing) return;
        refreshing = true;
        toast("Nueva versión disponible");
        if (hadController && win.location && typeof win.location.reload === "function") {
          try {
            win.location.reload();
          } catch (_) {
            /* el entorno no permite recargar automaticamente */
          }
        }
      });
    }
    sw.register("/sw.js", { scope: "/" })
      .then((reg) => {
        if (!reg) return;
        swRegistration = reg;
        if (typeof reg.update === "function") {
          reg.update().catch(() => {});
        }
        if (reg.waiting && typeof reg.waiting.postMessage === "function") {
          toast("Nueva versión disponible");
          reg.waiting.postMessage({ type: "SKIP_WAITING" });
        }
        if (typeof reg.addEventListener === "function") {
          reg.addEventListener("updatefound", () => {
            const installing = reg.installing;
            if (!installing || typeof installing.addEventListener !== "function") return;
            installing.addEventListener("statechange", () => {
              if (installing.state === "installed" && sw.controller) {
                toast("Nueva versión disponible");
                if (typeof installing.postMessage === "function") {
                  installing.postMessage({ type: "SKIP_WAITING" });
                }
              }
            });
          });
        }
      })
      .catch(() => {
        /* sin service worker la app sigue funcionando en linea */
      });
  }

  let eventsBound = false;

  function bindEvents() {
    if (eventsBound) return;
    eventsBound = true;
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
      clearTimeout(highlightTimer);
      const container = doc.querySelector(".agenda-top");
      if (container && typeof container.scrollTo === "function") {
        container.scrollTo({ top: 0, behavior: "smooth" });
      }
      renderAgenda();
    });
    $("cal-prev").addEventListener("click", () => {
      state.month = Core.shiftMonth(state.month.year, state.month.monthIndex, -1);
      state.selectedDay = null;
      renderAgenda();
    });
    $("cal-next").addEventListener("click", () => {
      state.month = Core.shiftMonth(state.month.year, state.month.monthIndex, 1);
      state.selectedDay = null;
      renderAgenda();
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
      if (doc.visibilityState === "visible") {
        if (swRegistration && typeof swRegistration.update === "function") {
          swRegistration.update().catch(() => {});
        }
        if (state.token && Date.now() - state.lastRefresh > REFRESH_AFTER_MS) track(refreshAll());
      }
    });
    win.addEventListener("resize", () => {
      const env = readEnvironment();
      mountAppLayout(!Core.isMobileEnvironment(env));
    });
    if (typeof win.matchMedia === "function") {
      const query = win.matchMedia("(prefers-color-scheme: dark)");
      if (query.addEventListener) query.addEventListener("change", () => applyTheme(local.getItem(THEME_KEY)));
    }
  }

  async function enterApp(auth, options) {
    const opts = options || {};
    const framed = Boolean(opts.framed);
    mountAppLayout(framed);
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
    updateBetaIndicator();
    const auth = consumeAuthFragment();
    state.token = loadStoredToken();
    bindEvents();

    if (/(^|[?&])app=1(&|$)/.test(String(win.location.search || ""))) session.setItem(FORCE_APP_KEY, "1");
    const env = readEnvironment();
    const isMobile = Core.isMobileEnvironment(env);

    await enterApp(auth, { framed: !isMobile });
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
    renderAgendaTimeline,
    renderAgendaSingleDay,
    scrollToAgendaDay,
    setAgendaMode,
  };

  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
