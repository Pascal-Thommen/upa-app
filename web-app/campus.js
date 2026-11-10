/**
 * UPA Campus PWA: controlador de interfaz (Inicio, Agenda, Perfil) y landing de escritorio.
 * Toda la logica de datos vive en campus-core.js; aqui solo se conecta con el DOM y el navegador.
 */
(function () {
  "use strict";

  const Core = window.UpaCampusCore;
  const firebaseConfig = Core.firebaseConfig;
  const VAPID_PUBLIC_KEY = Core.VAPID_PUBLIC_KEY;
  const FEED_PAGE = 20;
  const REFRESH_AFTER_MS = 60 * 1000;
  const TOKEN_KEY = "upa_campus_token";
  const THEME_KEY = "upa_campus_theme";
  const INSTALL_KEY = "upa_campus_install_dismissed";
  const PUSH_DISMISS_KEY = "dismiss_push_banner";
  const NOTIFIED_KEY = "upa_campus_notified";
  const PUSH_TOKEN_KEY = "upa_campus_fcm_token";
  const FORCE_APP_KEY = "upa_campus_force_app";
  const SW_RELOAD_TS_KEY = "upa_campus_sw_reload_ts";
  const SW_UPDATED_KEY = "upa_campus_sw_updated";
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
    reloadCount: 0,
    pushToken: null,
    hasDeviceToken: false,
    prefs: Core.loadNotificationPrefs(local),
  };

  const pending = new Set();
  let overlays = null;
  let api = null;
  let toastTimer = null;
  let highlightTimer = null;
  let swRegistration = null;
  let swRegisterPromise = null;
  let swControllerBound = false;
  let swHadController = false;
  let swRefreshing = false;
  let pendingSwReload = false;
  const skipWaitingSent = typeof WeakSet === "function" ? new WeakSet() : new Set();
  const watchedSwObjects = typeof WeakSet === "function" ? new WeakSet() : new Set();

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
    state.pushToken = null;
    state.hasDeviceToken = false;
    state.feed = { banners: [], posts: [], received: 0, hasMore: false, loaded: false, error: null };
    state.agenda = { entries: [], loaded: false, error: null };
    state.selectedDay = null;
    state.detail = null;
  }

  async function logout(reason) {
    local.removeItem(TOKEN_KEY);
    local.removeItem(NOTIFIED_KEY);
    local.removeItem(PUSH_TOKEN_KEY);
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
    maybeOpenDeepLinkedPost();
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
    maybeOpenDeepLinkedPost();
    maybeNotify();
  }

  async function refreshAll() {
    const tasks = [loadFeed({ reset: true })];
    if (state.token) {
      tasks.push(loadAgenda(), loadUser());
      if (notificationsSupported() && win.Notification.permission === "granted" && state.prefs.push !== false) {
        tasks.push(syncPushDeviceToken());
      }
    }
    await Promise.all(tasks.map(track));
  }

  /* ------------------------------------------------------------------ inscripcion */

  function resolveRegistrationStatus(item, fallbackStatus) {
    const fb = fallbackStatus !== undefined ? fallbackStatus : null;
    if (!item) return fb;
    if (item.registration_status === "attending" || item.registration_status === "declined") {
      return item.registration_status;
    }
    if (item.registrationStatus === "attending" || item.registrationStatus === "declined") {
      return item.registrationStatus;
    }
    if (item.is_registered || item.isRegistered) return "attending";
    return fb;
  }

  function applyRegistrationUpdate(updated, targetStatus) {
    const targetId = String(updated.id);
    const regStatus =
      targetStatus !== undefined
        ? targetStatus
        : Boolean(updated.is_registered)
          ? "attending"
          : resolveRegistrationStatus(updated, null);
    const isReg = regStatus === "attending";
    state.feed.posts = state.feed.posts.map((p) =>
      String(p.id) === targetId
        ? {
            ...p,
            has_registration: true,
            is_registered: isReg,
            registration_status: regStatus,
            registered_count: 0,
          }
        : p,
    );
    state.agenda.entries = Core.applyRegistration(state.agenda.entries, {
      ...updated,
      is_registered: isReg,
      registration_status: regStatus,
      registered_count: 0,
    });
    cache.set(`feed:${currentUserKey()}`, state.feed);
    const agendaKey = `agenda:${currentUserKey()}`;
    const cachedAgenda = cache.get(agendaKey);
    if (cachedAgenda && cachedAgenda.data && Array.isArray(cachedAgenda.data.events)) {
      cache.set(agendaKey, {
        ...cachedAgenda.data,
        events: cachedAgenda.data.events.map((ev) =>
          String(ev.id) === targetId
            ? {
                ...ev,
                has_registration: true,
                is_registered: isReg,
                registration_status: regStatus,
                registered_count: 0,
              }
            : ev,
        ),
        items: Array.isArray(cachedAgenda.data.items)
          ? cachedAgenda.data.items.map((item) =>
              item.item_type === "EVENT" && String(item.id) === targetId
                ? { ...item, is_registered: isReg, registration_status: regStatus, registered_count: 0 }
                : item,
            )
          : cachedAgenda.data.items,
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
      state.detail.isRegistered = isReg;
      state.detail.registrationStatus = regStatus;
      state.detail.count = 0;
      renderDetailEventCard();
      renderDetailActions();
    }
  }

  async function toggleRegistration(eventId, desiredStatus, currentStatus, button) {
    if (!state.token) {
      toast("Inicia sesión para inscribirte.");
      return;
    }
    if (button) button.disabled = true;
    try {
      if (currentStatus === desiredStatus) {
        if (currentStatus === "attending") {
          const updated = await api.unregister(eventId);
          applyRegistrationUpdate({ ...updated, id: eventId, is_registered: false, registration_status: null }, null);
        } else {
          applyRegistrationUpdate({ id: eventId, is_registered: false, registration_status: null }, null);
        }
        toast("Inscripción cancelada.");
        return;
      }
      const updated = desiredStatus === "attending" ? await api.register(eventId) : await api.unregister(eventId);
      applyRegistrationUpdate(updated, desiredStatus);
      toast(desiredStatus === "attending" ? "Inscripción confirmada." : "Inscripción cancelada.");
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

  function playIcon(size) {
    const px = String(size || 20);
    const svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", px);
    svg.setAttribute("height", px);
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", "play-glyph");
    const path = doc.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M8 5.5v13l11-6.5z");
    path.setAttribute("fill", "currentColor");
    svg.appendChild(path);
    return svg;
  }

  function bindImageFallback(img) {
    img.addEventListener("error", () => {
      img.style.display = "none";
      const previewLink = img.closest(".video-preview-link");
      const mediaWrap = img.closest(".card-media-wrap");
      const detailBox = img.closest("#detail-media");
      img.remove();
      if (previewLink) previewLink.remove();
      if (mediaWrap) {
        const cardOpen = mediaWrap.closest(".card-open");
        const floatingBadge = mediaWrap.querySelector(".badge-floating");
        mediaWrap.remove();
        if (cardOpen && floatingBadge) {
          floatingBadge.classList.remove("badge-floating");
          const cardEl = cardOpen.closest(".card");
          const isEventCard = cardEl && cardEl.getAttribute("data-kind") === "event";
          const evBadge = isEventCard ? kindBadge("event", "Evento", false) : null;
          const cardBody = cardOpen.querySelector(".card-body");
          if (cardBody && !cardBody.querySelector(".card-header")) {
            const metaPin = cardBody.querySelector(".card-meta > .pin");
            const headerRow = h(
              "div",
              { class: "card-header" },
              h("div", { class: "card-badges" }, floatingBadge, evBadge),
              metaPin || null,
            );
            cardBody.prepend(headerRow);
          }
        }
      }
      if (detailBox && !detailBox.querySelector("img, video")) {
        detailBox.hidden = true;
      }
    });
    return img;
  }

  function mediaNode(post, className, controls) {
    const rawUrl = Core.postImageUrl ? Core.postImageUrl(post) : Core.safeUrl(post.media_url || post.image_url);
    const url = /\/campus\/icons\/icon-\d+\.png(\?|#|$)/i.test(rawUrl) ? "" : rawUrl;
    if (!url && !Core.isVideoMedia(post)) return null;
    if (Core.isVideoMedia(post)) {
      const poster = Core.videoPosterUrl(post);
      if (Core.hasPlayableVideoStream(post)) {
        return h("video", {
          class: className,
          src: Core.safeUrl(post.media_url) || null,
          poster: poster || null,
          muted: true,
          playsinline: true,
          preload: "metadata",
          controls: controls ? true : null,
        });
      }
      if (!poster) return null;
      const extUrl = Core.videoExternalUrl(post);
      const badge = h("span", { class: "video-play-badge", "aria-hidden": "true" }, playIcon(18));
      const img = bindImageFallback(
        h("img", {
          class: className,
          src: poster,
          alt: "",
          loading: "lazy",
          decoding: "async",
          referrerpolicy: "no-referrer",
        }),
      );
      if (extUrl) {
        const link = h(
          "a",
          {
            class: "video-preview-link",
            href: extUrl,
            target: "_blank",
            rel: "noopener noreferrer",
            "aria-label": "Ver video en Instagram",
          },
          img,
          badge,
        );
        link.addEventListener("click", (ev) => ev.stopPropagation());
        return link;
      }
      return h("div", { class: "video-preview-link" }, img, badge);
    }
    return bindImageFallback(
      h("img", {
        class: className,
        src: url,
        alt: "",
        loading: "lazy",
        decoding: "async",
        referrerpolicy: "no-referrer",
      }),
    );
  }

  function registrationButton(post) {
    if (!post.is_event || !post.has_registration) return null;
    const ended = post.event_end && Date.parse(post.event_end) < Date.now();
    if (ended) return h("span", { class: "count", text: "Evento finalizado" });
    if (!state.token) return h("a", { class: "btn btn-secondary btn-small", href: "/api/auth/login-google?return_to=campus", text: "Inicia sesión para inscribirte" });
    const regStatus = resolveRegistrationStatus(post, null);
    const isAttending = Boolean(post.is_registered) || regStatus === "attending";
    const isDeclined = !isAttending && regStatus === "declined";
    const currentStatus = isAttending ? "attending" : isDeclined ? "declined" : null;
    const registerCls = isAttending
      ? "btn btn-small btn-rsvp btn-primary btn-registered is-active"
      : isDeclined
        ? "btn btn-small btn-rsvp btn-subtle"
        : "btn btn-small btn-rsvp btn-secondary";
    const declineCls = isDeclined
      ? "btn btn-small btn-rsvp btn-secondary is-active"
      : isAttending
        ? "btn btn-small btn-rsvp btn-subtle"
        : "btn btn-small btn-rsvp btn-secondary";
    const registerBtn = h("button", {
      class: registerCls,
      type: "button",
      "data-register": String(post.id),
      "aria-pressed": isAttending ? "true" : "false",
      text: isAttending ? "Inscrito ✓" : "Sí, asistiré",
    });
    const declineBtn = h("button", {
      class: declineCls,
      type: "button",
      "data-decline": String(post.id),
      "aria-pressed": isDeclined ? "true" : "false",
      text: "No asistiré",
    });
    registerBtn.addEventListener("click", () => track(toggleRegistration(post.id, "attending", currentStatus, registerBtn)));
    declineBtn.addEventListener("click", () => track(toggleRegistration(post.id, "declined", currentStatus, declineBtn)));
    return [registerBtn, declineBtn];
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
      article.append(h("div", { class: "card-actions" }, actions));
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
    renderHomeBanners();
  }

  function renderHome() {
    renderFeed();
    renderHomeBanners();
  }

  /* ------------------------------------------------------------------ detalle */

  function detailFromPost(post) {
    const kind = Core.postKind(post);
    const origin = Core.postOrigin(post);
    const isEvent = Boolean(post.is_event);
    const isInsta = post.post_type === "INSTAGRAM" || origin === "instagram";
    const source = isInsta
      ? Core.normalizeInstagramUrl(post.permalink || post.link_url, {
          isInstagram: true,
          instagramId: post.instagram_id,
          mediaType: post.media_type,
          fallbackIfGeneric: true,
        })
      : Core.safeUrl(post.permalink);
    const linkUrl = isInsta
      ? Core.normalizeInstagramUrl(post.link_url || post.permalink, {
          isInstagram: true,
          instagramId: post.instagram_id,
          mediaType: post.media_type,
          fallbackIfGeneric: true,
        })
      : Core.safeUrl(post.link_url);
    return {
      postId: post.id,
      kind,
      origin,
      isEvent,
      postType: post.post_type || "",
      instagramId: post.instagram_id || "",
      mediaType: post.media_type || "",
      kindLabel: Core.originLabel(origin),
      title: post.title,
      meta: postTimeLine(post) || "",
      text: post.content || post.caption || post.summary || "",
      extra: "",
      media: post,
      source,
      sourceLabel: isInsta ? "Ver en Instagram" : "Ver fuente original",
      linkUrl,
      linkLabel: post.link_label || (isInsta ? "Ver en Instagram" : "Abrir enlace"),
      eventStart: isEvent ? post.event_start || "" : "",
      eventEnd: isEvent ? post.event_end || "" : "",
      location: isEvent ? post.location || "" : "",
      hasRegistration: Boolean(isEvent && post.has_registration),
      eventId: isEvent && post.has_registration ? post.id : null,
      isRegistered: Boolean(post.is_registered),
      registrationStatus: resolveRegistrationStatus(post, null),
      count: 0,
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
        registrationStatus: null,
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
    const registrationStatus =
      entry.registrationStatus !== undefined && entry.registrationStatus !== null
        ? entry.registrationStatus
        : raw.registration_status !== undefined && raw.registration_status !== null
          ? raw.registration_status
          : feedPost.registration_status !== undefined
            ? feedPost.registration_status
            : isRegistered
              ? "attending"
              : null;
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
      registration_status: registrationStatus,
      registered_count: 0,
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
    } else if (d.isRegistered || d.registrationStatus === "attending") {
      statusText = "Inscrito";
      statusClass += " detail-status-registered";
    } else if (d.registrationStatus === "declined") {
      statusText = "No asistirás";
      statusClass += " detail-status-declined";
    } else if (d.hasRegistration || d.eventId) {
      statusText = "Inscripción abierta";
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
      if (!state.token) {
        box.append(
          h("a", {
            class: "btn btn-secondary btn-block",
            id: "detail-register",
            href: "/api/auth/login-google?return_to=campus",
            text: "Inicia sesión para inscribirte",
          }),
        );
      } else {
        const isAttending = Boolean(d.isRegistered) || d.registrationStatus === "attending";
        const isDeclined = !isAttending && d.registrationStatus === "declined";
        const currentStatus = isAttending ? "attending" : isDeclined ? "declined" : null;
        const registerCls = isAttending
          ? "btn btn-rsvp btn-primary btn-registered is-active"
          : isDeclined
            ? "btn btn-rsvp btn-subtle"
            : "btn btn-rsvp btn-secondary";
        const declineCls = isDeclined
          ? "btn btn-rsvp btn-secondary is-active"
          : isAttending
            ? "btn btn-rsvp btn-subtle"
            : "btn btn-rsvp btn-secondary";
        const registerBtn = h("button", {
          class: registerCls,
          type: "button",
          id: "detail-register",
          "aria-pressed": isAttending ? "true" : "false",
          text: isAttending ? "Inscrito ✓" : "Sí, asistiré",
        });
        const declineBtn = h("button", {
          class: declineCls,
          type: "button",
          id: "detail-decline",
          "aria-pressed": isDeclined ? "true" : "false",
          text: "No asistiré",
        });
        registerBtn.addEventListener("click", () => track(toggleRegistration(regEventId, "attending", currentStatus, registerBtn)));
        declineBtn.addEventListener("click", () => track(toggleRegistration(regEventId, "declined", currentStatus, declineBtn)));
        box.append(h("div", { class: "rsvp-actions" }, registerBtn, declineBtn));
      }
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
    if (overlays && overlays.top() !== "detail") {
      overlays.open("detail");
    } else if ($("detail")) {
      $("detail").hidden = false;
    }
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
      const postId = raw.id !== undefined ? raw.id : entry.id;
      const feedPost = state.feed.posts.find((p) => String(p.id) === String(postId)) || {};
      const hasReg = Boolean(
        entry.hasRegistration !== undefined
          ? entry.hasRegistration
          : raw.has_registration !== undefined
            ? raw.has_registration
            : feedPost.has_registration,
      );
      const isReg = Boolean(
        entry.isRegistered !== undefined
          ? entry.isRegistered
          : raw.is_registered !== undefined
            ? raw.is_registered
            : feedPost.is_registered,
      );
      const regStatus =
        entry.registrationStatus !== undefined && entry.registrationStatus !== null
          ? entry.registrationStatus
          : raw.registration_status !== undefined && raw.registration_status !== null
            ? raw.registration_status
            : feedPost.registration_status || (isReg ? "attending" : null);
      const endMs = entry.end instanceof Date ? entry.end.getTime() : Date.parse(raw.event_end || feedPost.event_end || "");
      const ended = Boolean(!Number.isNaN(endMs) && endMs < Date.now());
      let statusBadge = null;
      if (isReg || regStatus === "attending") {
        statusBadge = h("span", { class: "badge badge-registered", text: "Inscrito" });
      } else if (regStatus === "declined") {
        statusBadge = h("span", { class: "badge badge-declined", text: "No asistirás" });
      } else if (hasReg && !ended) {
        statusBadge = h("span", { class: "badge badge-registration-open", text: "Inscripción abierta" });
      }
      infoNode = h(
        "div",
        { class: "agenda-info" },
        h(
          "div",
          { class: "agenda-badges" },
          h("span", { class: "badge badge-campus badge-event" }, upaIcon(12), h("span", { text: "Evento Campus" })),
          statusBadge,
        ),
        h("b", { class: "agenda-title", text: entry.title }),
        h(
          "small",
          { class: "agenda-meta" },
          timeText ? h("span", { class: "agenda-time", text: `${timeText} hs` }) : null,
          timeText ? " · " : null,
          h("span", { class: "agenda-room", text: roomText }),
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
    const isDark = resolved === "dark";
    const themeColor = Core.THEME_COLORS[resolved];
    const bgColor = (Core.THEME_BG_COLORS && Core.THEME_BG_COLORS[resolved]) || (isDark ? "#080e1a" : "#e6edf5");
    const surfaceColor =
      (Core.THEME_SURFACE_COLORS && Core.THEME_SURFACE_COLORS[resolved]) || (isDark ? "#131c2e" : "#ffffff");
    root.setAttribute("data-resolved-theme", resolved);
    root.style.backgroundColor = bgColor;
    root.style.colorScheme = resolved;
    root.style.setProperty("--bg", bgColor);
    root.style.setProperty("--surface", surfaceColor);
    if (doc.body) {
      doc.body.style.backgroundColor = bgColor;
      doc.body.style.colorScheme = resolved;
    }
    const colorSchemeMeta = doc.querySelector('meta[name="color-scheme"]');
    if (colorSchemeMeta) colorSchemeMeta.setAttribute("content", resolved);
    doc.querySelectorAll('meta[name="theme-color"]').forEach((meta) => {
      meta.setAttribute("content", themeColor);
    });
    doc.querySelectorAll(".tabbar").forEach((bar) => {
      bar.style.backgroundColor = surfaceColor;
    });
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
    const pushGranted = notificationsSupported() && win.Notification.permission === "granted";
    const pushActive = Boolean(state.prefs.push && (pushGranted || state.hasDeviceToken));
    doc.querySelectorAll("[data-notify]").forEach((input) => {
      const key = input.getAttribute("data-notify");
      if (key === "push") {
        input.checked = pushActive;
        input.disabled = false;
      } else {
        input.checked = Boolean(state.prefs[key]);
        input.disabled = !pushActive;
        const label = input.closest("label");
        if (label) label.classList.toggle("is-disabled", !pushActive);
        const li = input.closest("li");
        if (li) li.classList.toggle("is-disabled", !pushActive);
      }
    });
  }

  function notificationsSupported() {
    return typeof win.Notification === "function" || (typeof win.Notification === "object" && win.Notification !== null);
  }

  async function resolveSwRegistration() {
    if (swRegistration) return swRegistration;
    if (swRegisterPromise) {
      try {
        const reg = await swRegisterPromise;
        if (reg) {
          swRegistration = reg;
          return reg;
        }
      } catch (_) {
        /* sin registro activo de Service Worker */
      }
    }
    if ("serviceWorker" in win.navigator && typeof win.navigator.serviceWorker.getRegistration === "function") {
      try {
        const reg = await win.navigator.serviceWorker.getRegistration();
        if (reg) {
          swRegistration = reg;
          return reg;
        }
      } catch (_) {
        /* sin registro activo de Service Worker */
      }
    }
    return null;
  }

  async function syncPushDeviceToken() {
    if (!notificationsSupported() || win.Notification.permission !== "granted") {
      return { ok: false, reason: "permission_not_granted" };
    }
    try {
      const existingStored = local.getItem(PUSH_TOKEN_KEY);
      if (existingStored && !Core.isValidFcmToken(existingStored)) {
        local.removeItem(PUSH_TOKEN_KEY);
      }
      const reg = await resolveSwRegistration();
      const fcmToken = await Core.requestFcmToken({
        firebase: win.firebase,
        vapidKey: VAPID_PUBLIC_KEY,
        firebaseConfig,
        serviceWorkerRegistration: reg,
      });
      if (!fcmToken) return { ok: false, reason: "empty_token" };
      state.pushToken = fcmToken;
      local.setItem(PUSH_TOKEN_KEY, fcmToken);
      if (state.token && api && typeof api.registerDeviceToken === "function") {
        const response = await api.registerDeviceToken(fcmToken, "web");
        state.hasDeviceToken = Boolean(response && response.has_device_token);
        renderProfile();
        renderHomeBanners();
        return { ok: true, token: fcmToken, response };
      }
      renderProfile();
      renderHomeBanners();
      return { ok: true, token: fcmToken, response: null };
    } catch (_) {
      return { ok: false, reason: "registration_failed" };
    }
  }

  async function disablePushNotifications() {
    const hint = $("notify-hint");
    if (hint) hint.hidden = true;
    const pushToggle = $("push-opt-in");
    if (pushToggle) pushToggle.checked = false;
    state.prefs.push = false;
    state.pushToken = null;
    state.hasDeviceToken = false;
    local.removeItem(PUSH_TOKEN_KEY);
    Core.saveNotificationPrefs(local, state.prefs);
    renderProfile();
    renderHomeBanners();
    if (state.token && api && typeof api.registerDeviceToken === "function") {
      try {
        await api.registerDeviceToken("", "web");
      } catch (_) {
        /* el estado local ya quedo desactivado aunque no haya red */
      }
    }
    return { ok: true, disabled: true };
  }

  async function enablePushNotifications() {
    const hint = $("notify-hint");
    if (hint) hint.hidden = true;
    const pushToggle = $("push-opt-in");
    if (!notificationsSupported()) {
      if (pushToggle) pushToggle.checked = false;
      state.prefs.push = false;
      Core.saveNotificationPrefs(local, state.prefs);
      renderProfile();
      renderHomeBanners();
      if (hint) {
        hint.textContent = "Este navegador no admite notificaciones. En iPhone, instala la app en la pantalla de inicio.";
        hint.hidden = false;
      }
      return { ok: false, reason: "unsupported" };
    }
    let permission = win.Notification.permission;
    if (permission !== "granted" && typeof win.Notification.requestPermission === "function") {
      try {
        const requested = await win.Notification.requestPermission();
        permission = typeof requested === "string" ? requested : win.Notification.permission;
        if (win.Notification.permission !== permission) {
          try {
            win.Notification.permission = permission;
          } catch (_) {
            /* propiedad de solo lectura en navegador nativo */
          }
        }
      } catch (_) {
        permission = win.Notification.permission || "denied";
      }
    }
    if (permission !== "granted") {
      if (pushToggle) pushToggle.checked = false;
      state.prefs.push = false;
      Core.saveNotificationPrefs(local, state.prefs);
      renderProfile();
      renderHomeBanners();
      if (hint) {
        hint.textContent = "Las notificaciones están bloqueadas en tu navegador. Habilítalas en los ajustes del sitio.";
        hint.hidden = false;
      }
      return { ok: false, reason: permission || "denied" };
    }
    state.prefs.push = true;
    Core.saveNotificationPrefs(local, state.prefs);
    if (pushToggle) pushToggle.checked = true;
    renderProfile();
    renderHomeBanners();
    const synced = await syncPushDeviceToken();
    if (hint && synced.ok) {
      hint.textContent = "Notificaciones Push activadas en este dispositivo.";
      hint.hidden = false;
    }
    maybeNotify();
    return synced;
  }

  async function onNotifyToggle(event) {
    const input = event.target;
    const key = input.getAttribute("data-notify");
    const hint = $("notify-hint");
    if (hint) hint.hidden = true;
    if (key === "push") {
      if (!input.checked) {
        await disablePushNotifications();
        return;
      }
      await enablePushNotifications();
      return;
    }
    state.prefs[key] = input.checked;
    Core.saveNotificationPrefs(local, state.prefs);
    if (!input.checked) {
      renderProfile();
      return;
    }
    if (!notificationsSupported()) {
      hint.textContent = "Este navegador no admite notificaciones. En iPhone, instala la app en la pantalla de inicio.";
      hint.hidden = false;
      return;
    }
    if (win.Notification.permission === "default") {
      try {
        const perm = await win.Notification.requestPermission();
        if (perm === "granted" || win.Notification.permission === "granted") {
          await syncPushDeviceToken();
        }
      } catch (_) {
        /* el navegador rechazo la solicitud */
      }
    }
    if (win.Notification.permission === "denied") {
      hint.textContent = "Las notificaciones están bloqueadas en tu navegador. Habilítalas en los ajustes del sitio.";
      hint.hidden = false;
      return;
    }
    if (win.Notification.permission === "granted") {
      await syncPushDeviceToken();
    }
    maybeNotify();
  }

  let deepLinkConsumed = false;
  let pendingDeepLinkPostId = null;
  const deepLinkFetchAttempted = new Set();
  const deepLinkFetchInFlight = new Set();

  function extractPostId(postIdOrUrl) {
    if (typeof postIdOrUrl === "number" && Number.isFinite(postIdOrUrl)) {
      return String(postIdOrUrl);
    }
    const raw = String(postIdOrUrl || "").trim();
    if (!raw) return "";
    if (/^\d+$/.test(raw)) return raw;
    const m = /(?:^|[?&])post=(\d+)(?:&|#|$)/.exec(raw);
    return m ? m[1] : "";
  }

  function findPostDetailById(postId) {
    const idNum = Number(postId);
    const idStr = String(postId);
    const post = [...(state.feed.banners || []), ...(state.feed.posts || [])].find(
      (p) => p && (Number(p.id) === idNum || String(p.id) === idStr),
    );
    if (post) return detailFromPost(post);
    const entry = (state.agenda.entries || []).find(
      (e) => e && e.kind === "event" && (Number(e.id) === idNum || String(e.id) === idStr),
    );
    if (entry) return detailFromEntry(entry);
    return null;
  }

  function upsertFetchedPost(post) {
    if (!post || post.id === undefined || post.id === null) return;
    if (post.post_type === "EMERGENCY_BANNER") {
      const exists = (state.feed.banners || []).some((b) => String(b.id) === String(post.id));
      if (!exists) state.feed.banners = [post, ...(state.feed.banners || [])];
    } else {
      state.feed.posts = Core.mergePosts([post], state.feed.posts || []);
    }
    renderFeed();
  }

  async function fetchAndOpenDeepLinkedPost(postId) {
    const idStr = String(postId);
    if (!idStr || deepLinkFetchInFlight.has(idStr)) return false;
    deepLinkFetchInFlight.add(idStr);
    deepLinkFetchAttempted.add(idStr);
    try {
      if (api && typeof api.publication === "function") {
        try {
          const fetched = await api.publication(idStr);
          if (fetched && fetched.id !== undefined) {
            upsertFetchedPost(fetched);
            const detail = detailFromPost(fetched);
            deepLinkConsumed = true;
            pendingDeepLinkPostId = null;
            if (state.tab !== "inicio") showTab("inicio");
            openDetail(detail);
            return true;
          }
        } catch (_) {
          /* Si /api/publications/{id} falla, sincronizamos feed y agenda como respaldo */
        }
      }
      if (api) {
        const tasks = [loadFeed({ reset: true })];
        if (state.token) tasks.push(loadAgenda());
        await Promise.all(tasks);
        const detailAfterSync = findPostDetailById(idStr);
        if (detailAfterSync) {
          deepLinkConsumed = true;
          pendingDeepLinkPostId = null;
          if (state.tab !== "inicio") showTab("inicio");
          openDetail(detailAfterSync);
          return true;
        }
      }
      return false;
    } finally {
      deepLinkFetchInFlight.delete(idStr);
    }
  }

  function openPostModal(postIdOrUrl, options) {
    const opts = options || {};
    const postId = extractPostId(postIdOrUrl);
    if (!postId) return false;
    const detail = findPostDetailById(postId);
    if (detail) {
      deepLinkConsumed = true;
      pendingDeepLinkPostId = null;
      if (state.tab !== "inicio") showTab("inicio");
      openDetail(detail);
      return true;
    }
    pendingDeepLinkPostId = postId;
    if (opts.fetchIfMissing !== false && api && !deepLinkFetchAttempted.has(postId)) {
      track(fetchAndOpenDeepLinkedPost(postId));
    }
    return false;
  }

  function maybeOpenDeepLinkedPost() {
    const targetId =
      pendingDeepLinkPostId || (!deepLinkConsumed && !state.detail ? extractPostId(win.location.search) : "");
    if (!targetId) return false;
    return openPostModal(targetId);
  }

  async function showNotification(item) {
    const options = {
      body: item.body,
      tag: item.id,
      badge: "/campus/icons/badge-monochrome.png",
      icon: item.icon || "/campus/icons/transparent-pixel.png",
    };
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

  function renderHomeBanners() {
    const loginEl = $("login-prompt");
    const installEl = $("install-banner");
    const pushEl = $("push-banner");
    const info = installState();
    if ($("install-action")) {
      $("install-action").textContent = info.platform === "ios" ? "Ver cómo" : "Instalar";
    }
    if (!state.token) {
      if (loginEl) loginEl.hidden = false;
      if (installEl) installEl.hidden = true;
      if (pushEl) pushEl.hidden = true;
      return;
    }
    if (loginEl) loginEl.hidden = true;
    const showInstall = Core.shouldShowInstallBanner(info);
    if (showInstall) {
      if (installEl) installEl.hidden = false;
      if (pushEl) pushEl.hidden = true;
      return;
    }
    if (installEl) installEl.hidden = true;
    const pushDismissed = Boolean(local.getItem(PUSH_DISMISS_KEY));
    const showPush =
      notificationsSupported() &&
      win.Notification.permission === "default" &&
      !pushDismissed &&
      !state.prefs.push &&
      !state.hasDeviceToken;
    if (pushEl) pushEl.hidden = !showPush;
  }

  function renderInstallBanner() {
    renderHomeBanners();
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

  function activateWaitingWorker(worker) {
    if (Core.requestSkipWaiting(worker, skipWaitingSent)) {
      toast("Aplicación actualizada");
      return true;
    }
    return false;
  }

  function performSwReload() {
    swRefreshing = true;
    pendingSwReload = false;
    const now = Date.now();
    session.setItem(SW_RELOAD_TS_KEY, String(now));
    session.setItem(SW_UPDATED_KEY, "1");
    toast("Aplicación actualizada");
    state.reloadCount = (state.reloadCount || 0) + 1;
    if (typeof win.__upaOnReload === "function") {
      win.__upaOnReload();
      return;
    }
    if (win.location && typeof win.location.reload === "function") {
      try {
        win.location.reload();
      } catch (_) {
        /* el entorno no permite recargar automaticamente */
      }
    }
  }

  function maybeCompletePendingSwReload() {
    if (!pendingSwReload || swRefreshing) return false;
    if (!Core.canAutoReload(doc)) return false;
    performSwReload();
    return true;
  }

  function watchInstallingWorker(installing, sw) {
    if (!installing || typeof installing.addEventListener !== "function") return;
    if (watchedSwObjects.has(installing)) return;
    watchedSwObjects.add(installing);
    installing.addEventListener("statechange", () => {
      const hasExistingController = Boolean(
        (sw && sw.controller) || swHadController || (swRegistration && swRegistration.active),
      );
      if (installing.state === "installed" && hasExistingController) {
        activateWaitingWorker((swRegistration && swRegistration.waiting) || installing);
      }
    });
  }

  function bindSwRegistration(reg, sw) {
    if (!reg) return;
    swRegistration = reg;
    if (reg.waiting) {
      activateWaitingWorker(reg.waiting);
    }
    if (reg.installing) {
      watchInstallingWorker(reg.installing, sw);
    }
    if (typeof reg.addEventListener === "function" && !watchedSwObjects.has(reg)) {
      watchedSwObjects.add(reg);
      reg.addEventListener("updatefound", () => {
        if (reg.installing) watchInstallingWorker(reg.installing, sw);
        if (reg.waiting) activateWaitingWorker(reg.waiting);
      });
    }
  }

  function checkForSwUpdate() {
    if (maybeCompletePendingSwReload()) return Promise.resolve();
    if (!("serviceWorker" in win.navigator)) return Promise.resolve();
    const sw = win.navigator.serviceWorker;
    const runUpdate = (reg) => {
      if (!reg) return Promise.resolve();
      bindSwRegistration(reg, sw);
      if (typeof reg.update === "function") {
        return Promise.resolve()
          .then(() => reg.update())
          .then((updatedReg) => {
            const activeReg = updatedReg || reg;
            bindSwRegistration(activeReg, sw);
          })
          .catch(() => {});
      }
      return Promise.resolve();
    };
    if (swRegistration) return track(runUpdate(swRegistration));
    if (typeof sw.getRegistration === "function") {
      return track(
        Promise.resolve()
          .then(() => sw.getRegistration())
          .then((reg) => (reg ? runUpdate(reg) : undefined))
          .catch(() => {}),
      );
    }
    return Promise.resolve();
  }

  function onAppReactivated() {
    checkForSwUpdate();
    if (state.token && Date.now() - state.lastRefresh > REFRESH_AFTER_MS) {
      track(refreshAll());
    }
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in win.navigator)) return;
    const secure = win.isSecureContext || /^(localhost|127\.0\.0\.1)$/.test(win.location.hostname);
    if (!secure) return;
    const sw = win.navigator.serviceWorker;
    if (sw.controller) swHadController = true;
    if (!swControllerBound && typeof sw.addEventListener === "function") {
      swControllerBound = true;
      sw.addEventListener("controllerchange", () => {
        if (!swHadController) {
          swHadController = true;
          return;
        }
        const lastReloadAt = Number(session.getItem(SW_RELOAD_TS_KEY)) || 0;
        const decision = Core.shouldReloadOnControllerChange({
          hadController: swHadController,
          refreshing: swRefreshing,
          lastReloadAt,
          now: Date.now(),
          idle: Core.canAutoReload(doc),
        });
        if (decision.reload) {
          performSwReload();
        } else if (decision.defer) {
          pendingSwReload = true;
          toast("Aplicación actualizada");
        }
      });
    }
    swRegisterPromise = Promise.resolve()
      .then(() => sw.register("/sw.js", { scope: "/", updateViaCache: "none" }))
      .then((reg) => {
        if (!reg) return null;
        bindSwRegistration(reg, sw);
        checkForSwUpdate();
        return reg;
      })
      .catch(() => {
        /* sin service worker la app sigue funcionando en linea */
        return null;
      });
    track(swRegisterPromise);
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
    if ($("push-action")) {
      $("push-action").addEventListener("click", () => track(enablePushNotifications()));
    }
    if ($("push-dismiss")) {
      $("push-dismiss").addEventListener("click", () => {
        local.setItem(PUSH_DISMISS_KEY, "1");
        renderHomeBanners();
      });
    }

    const onSwNotificationMessage = (event) => {
      const data = (event && event.data) || {};
      if (data && data.type === "NOTIFICATION_CLICK") {
        const target = data.post_id || data.url;
        const postId = extractPostId(target);
        if (postId) {
          deepLinkConsumed = false;
          deepLinkFetchAttempted.delete(postId);
        }
        openPostModal(target);
      }
    };
    if ("serviceWorker" in win.navigator && typeof win.navigator.serviceWorker.addEventListener === "function") {
      win.navigator.serviceWorker.addEventListener("message", onSwNotificationMessage);
    }
    win.addEventListener("message", onSwNotificationMessage);

    win.addEventListener("online", () => {
      checkForSwUpdate();
      track(refreshAll());
    });
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
    doc.addEventListener("focusout", () => {
      setTimeout(() => maybeCompletePendingSwReload(), 0);
    });
    doc.addEventListener("visibilitychange", () => {
      if (doc.visibilityState === "visible") {
        onAppReactivated();
      }
    });
    win.addEventListener("focus", () => {
      onAppReactivated();
    });
    win.addEventListener("pageshow", (event) => {
      if (event && event.persisted) {
        onAppReactivated();
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
    const swJustUpdated = session.getItem(SW_UPDATED_KEY) === "1";
    if (swJustUpdated) session.removeItem(SW_UPDATED_KEY);
    if (auth && auth.error) toast(Core.translateAuthError(auth.error));
    else if (auth && auth.token) toast("Sesión iniciada.");
    else if (swJustUpdated) toast("Aplicación actualizada");
    if (!win.navigator.onLine) setOffline(true, false);
    await refreshAll();
  }

  async function start() {
    const storedPushToken = local.getItem(PUSH_TOKEN_KEY);
    if (storedPushToken && !Core.isValidFcmToken(storedPushToken)) {
      local.removeItem(PUSH_TOKEN_KEY);
    }
    if (win.firebase && typeof win.firebase.initializeApp === "function" && (!win.firebase.apps || !win.firebase.apps.length)) {
      try {
        win.firebase.initializeApp(firebaseConfig);
      } catch (_) {
        /* Firebase ya inicializado */
      }
    }
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
    firebaseConfig,
    VAPID_PUBLIC_KEY,
    boot,
    start,
    idle: async () => {
      if (bootPromise) await bootPromise;
      while (pending.size) await Promise.allSettled([...pending]);
    },
    openDetail: (detail) => openDetail(detail),
    openPostModal: (postIdOrUrl, options) => {
      const postId = extractPostId(postIdOrUrl);
      if (postId) {
        deepLinkConsumed = false;
        deepLinkFetchAttempted.delete(postId);
      }
      return openPostModal(postIdOrUrl, options);
    },
    refresh: () => track(refreshAll()),
    checkForSwUpdate: () => checkForSwUpdate(),
    enablePushNotifications: () => track(enablePushNotifications()),
    disablePushNotifications: () => track(disablePushNotifications()),
    syncPushDeviceToken: () => track(syncPushDeviceToken()),
    renderHome,
    renderHomeBanners,
    renderAgendaTimeline,
    renderAgendaSingleDay,
    scrollToAgendaDay,
    setAgendaMode,
  };

  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
