/**
 * UPA Campus PWA: logica pura y cliente de API (sin dependencias del DOM).
 *
 * Se carga en el navegador como `window.UpaCampusCore` y en Node (pruebas) mediante require().
 * Todo el acceso a red pasa por `createApi`, que normaliza errores (sin conexion, timeout,
 * sesion expirada) para que la interfaz muestre siempre un mensaje claro en espanol.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.UpaCampusCore = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const TIMEZONE = "America/Asuncion";
  const LOCALE = "es-PY";
  const THEMES = ["system", "light", "dark"];
  const THEME_COLORS = { light: "#ffffff", dark: "#0f172a" };
  const INSTALL_DISMISS_MS = 14 * 24 * 60 * 60 * 1000;
  const NOTIFY_WINDOW_MS = 24 * 60 * 60 * 1000;
  const DEFAULT_TIMEOUT_MS = 12000;
  const DEFAULT_NOTIFICATIONS = { events: true, announcements: true, deadlines: true };

  /* ------------------------------------------------------------------ errores y API */

  class ApiError extends Error {
    constructor(kind, status, message) {
      super(message);
      this.name = "ApiError";
      this.kind = kind;
      this.status = status || 0;
    }
  }

  const ERROR_MESSAGES = {
    offline: "Sin conexión a internet. Revisa tu red e inténtalo de nuevo.",
    timeout: "El servidor tardó demasiado en responder. Inténtalo de nuevo.",
    unauthorized: "Tu sesión expiró. Inicia sesión nuevamente.",
    forbidden: "No tienes permiso para realizar esta acción.",
    notfound: "El contenido ya no está disponible.",
    server: "El servidor no está disponible en este momento. Inténtalo más tarde.",
    http: "No se pudo completar la solicitud.",
  };

  function friendlyError(error) {
    if (error && error.kind && ERROR_MESSAGES[error.kind]) return ERROR_MESSAGES[error.kind];
    return ERROR_MESSAGES.http;
  }

  function isConnectivityError(error) {
    return Boolean(error && (error.kind === "offline" || error.kind === "timeout" || error.kind === "server"));
  }

  function createApi(options) {
    const opts = options || {};
    const baseUrl = (opts.baseUrl || "").replace(/\/$/, "");
    const timeoutMs = opts.timeoutMs || DEFAULT_TIMEOUT_MS;
    const getToken = opts.getToken || (() => null);
    const onUnauthorized = opts.onUnauthorized || (() => {});
    const fetchImpl = opts.fetchImpl || ((...args) => globalThis.fetch(...args));

    async function request(path, init) {
      const settings = init || {};
      const headers = { Accept: "application/json" };
      const token = settings.auth === false ? null : getToken();
      if (token) headers.Authorization = `Bearer ${token}`;

      const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
      let timer = null;
      const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => {
          if (controller) controller.abort();
          reject(new ApiError("timeout", 0, ERROR_MESSAGES.timeout));
        }, timeoutMs);
      });

      let response;
      try {
        response = await Promise.race([
          fetchImpl(`${baseUrl}${path}`, {
            method: settings.method || "GET",
            headers,
            signal: controller ? controller.signal : undefined,
          }),
          timeout,
        ]);
      } catch (error) {
        if (error instanceof ApiError) throw error;
        if (error && error.name === "AbortError") throw new ApiError("timeout", 0, ERROR_MESSAGES.timeout);
        throw new ApiError("offline", 0, ERROR_MESSAGES.offline);
      } finally {
        clearTimeout(timer);
      }

      if (response.status === 401) {
        if (token) onUnauthorized();
        throw new ApiError("unauthorized", 401, ERROR_MESSAGES.unauthorized);
      }
      if (response.status === 403) throw new ApiError("forbidden", 403, await readDetail(response, "forbidden"));
      if (response.status === 404) throw new ApiError("notfound", 404, await readDetail(response, "notfound"));
      if (response.status >= 500) throw new ApiError("server", response.status, ERROR_MESSAGES.server);
      if (!response.ok) throw new ApiError("http", response.status, await readDetail(response, "http"));

      try {
        return await response.json();
      } catch (_) {
        throw new ApiError("server", response.status, ERROR_MESSAGES.server);
      }
    }

    async function readDetail(response, kind) {
      try {
        const body = await response.json();
        if (body && typeof body.detail === "string" && body.detail.trim()) return body.detail;
      } catch (_) {
        /* cuerpo no JSON: se usa el mensaje estandar */
      }
      return ERROR_MESSAGES[kind];
    }

    return {
      health: () => request("/health", { auth: false }),
      me: () => request("/api/auth/me"),
      feed: (params) => {
        const p = params || {};
        const query = new URLSearchParams({ limit: String(p.limit || 20), offset: String(p.offset || 0) });
        return request(`/api/v1/feed?${query.toString()}`);
      },
      agenda: () => request("/api/v1/agenda"),
      register: (eventId) => request(`/api/events/${encodeURIComponent(eventId)}/register`, { method: "POST" }),
      unregister: (eventId) => request(`/api/events/${encodeURIComponent(eventId)}/register`, { method: "DELETE" }),
    };
  }

  /* ------------------------------------------------------------------ sesion */

  function looksLikeJwt(token) {
    return typeof token === "string" && /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(token);
  }

  function parseAuthFragment(hash) {
    const raw = String(hash || "").replace(/^#/, "");
    if (!raw) return { token: null, error: null };
    const params = new URLSearchParams(raw);
    const token = params.get("token");
    const error = params.get("auth_error");
    return {
      token: looksLikeJwt(token) ? token : null,
      error: error ? error.slice(0, 64) : null,
    };
  }

  function translateAuthError(code) {
    const map = {
      forbidden_domain: "Acceso restringido. Solo se permiten cuentas institucionales (@upa.edu.py).",
      token_exchange_failed: "No se pudo completar la autenticación con Google. Inténtalo nuevamente.",
      missing_code: "Google no devolvió el código de autorización. Inténtalo nuevamente.",
      missing_client_id: "La configuración de acceso del servidor está incompleta.",
      missing_id_token: "Google no devolvió la identidad de la cuenta. Inténtalo nuevamente.",
      invalid_id_token: "No se pudo verificar la cuenta de Google. Inténtalo nuevamente.",
      access_denied: "El acceso fue cancelado o la cuenta no está autorizada.",
    };
    return map[code] || "No se pudo iniciar sesión. Inténtalo nuevamente.";
  }

  function decodeJwtPayload(token) {
    if (!looksLikeJwt(token)) return null;
    try {
      const b64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
      const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
      const json =
        typeof atob === "function"
          ? decodeURIComponent(
              atob(padded)
                .split("")
                .map((c) => `%${c.charCodeAt(0).toString(16).padStart(2, "0")}`)
                .join(""),
            )
          : Buffer.from(padded, "base64").toString("utf8");
      return JSON.parse(json);
    } catch (_) {
      return null;
    }
  }

  function isTokenExpired(token, nowMs) {
    const payload = decodeJwtPayload(token);
    if (!payload || typeof payload.exp !== "number") return true;
    return payload.exp * 1000 <= (nowMs === undefined ? Date.now() : nowMs);
  }

  function roleLabel(user) {
    if (!user) return "";
    const groups = (user.groups || []).map((g) => String(g).toUpperCase());
    if (user.role === "admin") return "Administración";
    if (user.role === "editor") return "Redacción";
    if (groups.includes("DOCENTES") || groups.includes("PROF")) return "Docente";
    return "Estudiante";
  }

  function initials(name) {
    const parts = String(name || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    if (!parts.length) return "U";
    return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
  }

  /* ------------------------------------------------------------------ entorno, tema, instalacion */

  function isMobileEnvironment(env) {
    const e = env || {};
    if (/(^|[?&])app=1(&|$)/.test(String(e.search || ""))) return true;
    if (e.standalone) return true;
    if (/Android|iPhone|iPad|iPod|Mobile|CriOS|FxiOS/i.test(String(e.userAgent || ""))) return true;
    if (e.platform === "MacIntel" && Number(e.maxTouchPoints) > 1) return true;
    return Boolean(e.coarsePointer) && Number(e.width) <= 1024;
  }

  function normalizeTheme(value) {
    return THEMES.includes(value) ? value : "system";
  }

  function resolveTheme(preference, prefersDark) {
    const pref = normalizeTheme(preference);
    if (pref === "system") return prefersDark ? "dark" : "light";
    return pref;
  }

  function detectInstallPlatform(env) {
    const e = env || {};
    if (e.standalone) return "standalone";
    const ua = String(e.userAgent || "");
    if (/iPhone|iPad|iPod/i.test(ua) || (e.platform === "MacIntel" && Number(e.maxTouchPoints) > 1)) return "ios";
    if (/Android/i.test(ua)) return "android";
    return "other";
  }

  function shouldShowInstallBanner(state) {
    const s = state || {};
    const now = s.now === undefined ? Date.now() : s.now;
    if (s.dismissedAt && now - s.dismissedAt < INSTALL_DISMISS_MS) return false;
    if (s.platform === "ios") return true;
    if (s.platform === "android") return Boolean(s.hasPrompt);
    return false;
  }

  /* ------------------------------------------------------------------ fechas */

  function dayKey(value, timeZone) {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: timeZone || TIMEZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  }

  function formatTime(value, timeZone) {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat(LOCALE, {
      timeZone: timeZone || TIMEZONE,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  }

  function keyToDate(key) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(key || "");
    if (!m) return null;
    return new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12, 0, 0));
  }

  function formatDayLong(key) {
    const date = keyToDate(key);
    if (!date) return "";
    const text = new Intl.DateTimeFormat(LOCALE, {
      timeZone: "UTC",
      weekday: "long",
      day: "numeric",
      month: "long",
    }).format(date);
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function formatDayShort(key) {
    const date = keyToDate(key);
    if (!date) return { day: "", month: "" };
    return {
      day: String(date.getUTCDate()),
      month: new Intl.DateTimeFormat(LOCALE, { timeZone: "UTC", month: "short" })
        .format(date)
        .replace(".", "")
        .toUpperCase(),
    };
  }

  function formatMonthLabel(year, monthIndex) {
    const date = new Date(Date.UTC(year, monthIndex, 1, 12));
    const text = new Intl.DateTimeFormat(LOCALE, { timeZone: "UTC", month: "long", year: "numeric" }).format(date);
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function formatPublished(value) {
    const key = dayKey(value);
    if (!key) return "";
    const short = formatDayShort(key);
    return `${short.day} ${short.month.toLowerCase()} ${key.slice(0, 4)}`;
  }

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function monthGrid(year, monthIndex) {
    const first = new Date(Date.UTC(year, monthIndex, 1, 12));
    const offset = (first.getUTCDay() + 6) % 7;
    const cells = [];
    for (let i = 0; i < 42; i += 1) {
      const d = new Date(Date.UTC(year, monthIndex, 1 - offset + i, 12));
      cells.push({
        key: `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`,
        day: d.getUTCDate(),
        inMonth: d.getUTCMonth() === monthIndex,
      });
    }
    const weeks = [];
    for (let i = 0; i < 42; i += 7) weeks.push(cells.slice(i, i + 7));
    return weeks.filter((week, idx) => idx < 5 || week.some((c) => c.inMonth));
  }

  function shiftMonth(year, monthIndex, delta) {
    const d = new Date(Date.UTC(year, monthIndex + delta, 1, 12));
    return { year: d.getUTCFullYear(), monthIndex: d.getUTCMonth() };
  }

  /* ------------------------------------------------------------------ contenido */

  function safeUrl(value) {
    const url = String(value || "").trim();
    if (!url) return "";
    if (/^https?:\/\//i.test(url)) return url;
    if (url.startsWith("/") && !url.startsWith("//")) return url;
    return "";
  }

  function isVideoMedia(post) {
    if (!post) return false;
    if (/VIDEO/i.test(String(post.media_type || ""))) return true;
    return /\.(mp4|webm|mov)(\?|#|$)/i.test(String(post.media_url || ""));
  }

  function postKind(post) {
    if (post.post_type === "EMERGENCY_BANNER") return "urgent";
    if (post.is_event) return "event";
    if (post.post_type === "INSTAGRAM") return "instagram";
    return "news";
  }

  function postOrigin(post) {
    if (!post) return "campus";
    if (post.post_type === "EMERGENCY_BANNER") return "urgent";
    if (post.post_type === "INSTAGRAM") return "instagram";
    return "campus";
  }

  function originLabel(origin) {
    return { urgent: "Aviso urgente", instagram: "Instagram", campus: "Campus" }[origin] || "Campus";
  }

  function kindLabel(kind) {
    return { urgent: "Aviso urgente", event: "Evento", instagram: "Instagram", campus: "Campus", news: "Campus", deadline: "Tarea" }[kind] || "";
  }

  function postSummary(post) {
    if (!post) return "";
    const raw = String(post.summary || post.content || "").trim();
    if (!raw) return "";
    const title = String(post.title || "").trim();
    const prefix = title.replace(/(?:\.\.\.|…)+$/, "").trim();
    if (prefix && raw.startsWith(prefix)) {
      const nl = raw.indexOf("\n");
      return nl === -1 ? "" : raw.slice(nl + 1).trim();
    }
    return raw;
  }

  function resolveDetailLinks(detail) {
    const d = detail || {};
    const linkUrl = safeUrl(d.linkUrl);
    const source = safeUrl(d.source);
    const norm = (u) => u.replace(/\/+$/, "").toLowerCase();
    const isInstaType = d.kind === "instagram" || String(d.postType || "").toUpperCase() === "INSTAGRAM";
    const isInstaLink = (u, lbl) => /instagram\.com/i.test(u) || lbl === "Ver en Instagram";
    const sameTarget = Boolean(linkUrl && source && norm(linkUrl) === norm(source));
    const bothInsta = Boolean(linkUrl && source && isInstaLink(linkUrl, d.linkLabel) && isInstaLink(source, d.sourceLabel));

    if (isInstaType || sameTarget || bothInsta) {
      const href = source || linkUrl;
      if (!href) return [];
      const isInstagram = isInstaType || isInstaLink(href, d.sourceLabel) || isInstaLink(href, d.linkLabel);
      return [
        {
          id: "detail-source",
          href,
          label: isInstagram ? "Ver en Instagram" : d.sourceLabel || d.linkLabel || "Ver fuente original",
          isInstagram,
        },
      ];
    }

    const out = [];
    if (linkUrl) {
      const isInstagram = isInstaLink(linkUrl, d.linkLabel);
      out.push({
        id: "detail-link",
        href: linkUrl,
        label: d.linkLabel || (isInstagram ? "Ver en Instagram" : "Abrir enlace"),
        isInstagram,
      });
    }
    if (source) {
      const isInstagram = isInstaLink(source, d.sourceLabel);
      out.push({
        id: "detail-source",
        href: source,
        label: d.sourceLabel || (isInstagram ? "Ver en Instagram" : "Ver fuente original"),
        isInstagram,
      });
    }
    return out;
  }

  function publishedMs(post) {
    const ms = Date.parse(post.published_at || post.created_at || "");
    return Number.isNaN(ms) ? 0 : ms;
  }

  function sortFeed(posts) {
    return (posts || [])
      .map((post, index) => ({ post, index }))
      .sort((a, b) => {
        const pin = Number(Boolean(b.post.is_pinned)) - Number(Boolean(a.post.is_pinned));
        if (pin !== 0) return pin;
        const time = publishedMs(b.post) - publishedMs(a.post);
        return time !== 0 ? time : a.index - b.index;
      })
      .map((entry) => entry.post);
  }

  function normalizeFeed(response) {
    const data = response || {};
    return {
      banners: Array.isArray(data.urgent_banners) ? data.urgent_banners : [],
      posts: sortFeed(Array.isArray(data.posts) ? data.posts : []),
    };
  }

  function mergePosts(current, incoming) {
    const seen = new Set();
    const merged = [];
    for (const post of [...current, ...incoming]) {
      if (seen.has(post.id)) continue;
      seen.add(post.id);
      merged.push(post);
    }
    return sortFeed(merged);
  }

  function parseClassroomDue(formatted) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(String(formatted || "").trim());
    if (!m) return { date: null, dayKey: "", hasTime: false };
    if (m[4] === undefined) return { date: null, dayKey: `${m[1]}-${m[2]}-${m[3]}`, hasTime: false };
    const date = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5])));
    return { date, dayKey: dayKey(date), hasTime: true };
  }

  function buildAgendaEntries(agenda) {
    const data = agenda || {};
    const entries = [];
    for (const ev of Array.isArray(data.events) ? data.events : []) {
      const start = new Date(ev.event_start);
      if (Number.isNaN(start.getTime())) continue;
      const endDate = ev.event_end ? new Date(ev.event_end) : null;
      entries.push({
        key: `event:${ev.id}`,
        kind: "event",
        id: ev.id,
        title: ev.title,
        description: ev.description || ev.summary || "",
        dayKey: dayKey(start),
        sortKey: `${dayKey(start)} ${formatTime(start)}`,
        timeLabel: formatTime(start),
        place: ev.location || "",
        link: "",
        date: start,
        end: endDate && !Number.isNaN(endDate.getTime()) ? endDate : null,
        raw: ev,
      });
    }
    for (const dl of Array.isArray(data.deadlines) ? data.deadlines : []) {
      const due = parseClassroomDue(dl.due_date_formatted);
      if (!due.dayKey) continue;
      entries.push({
        key: `deadline:${dl.id}`,
        kind: "deadline",
        id: dl.id,
        title: dl.title,
        description: dl.description || "",
        dayKey: due.dayKey,
        sortKey: `${due.dayKey} ${due.hasTime ? formatTime(due.date) : "23:59"}`,
        timeLabel: due.hasTime ? formatTime(due.date) : "",
        place: dl.course_name || dl.course || "",
        link: safeUrl(dl.alternate_link),
        date: due.date,
        end: null,
        raw: dl,
      });
    }
    entries.sort((a, b) => (a.sortKey < b.sortKey ? -1 : a.sortKey > b.sortKey ? 1 : a.key < b.key ? -1 : 1));
    return entries;
  }

  function upcomingEntries(entries, todayKey) {
    return (entries || []).filter((e) => e.dayKey >= todayKey);
  }

  function entriesForDay(entries, key) {
    return (entries || []).filter((e) => e.dayKey === key);
  }

  function groupAgendaByMonth(entries) {
    const groups = [];
    let current = null;
    for (const entry of entries || []) {
      const m = /^(\d{4})-(\d{2})-\d{2}$/.exec(String(entry.dayKey || ""));
      if (!m) continue;
      const year = Number(m[1]);
      const monthIndex = Number(m[2]) - 1;
      const monthKey = `${m[1]}-${m[2]}`;
      if (!current || current.monthKey !== monthKey) {
        current = {
          monthKey,
          year,
          monthIndex,
          label: formatMonthLabel(year, monthIndex),
          entries: [],
        };
        groups.push(current);
      }
      current.entries.push(entry);
    }
    return groups;
  }

  function markedDays(entries) {
    const marks = {};
    for (const e of entries || []) {
      const mark = marks[e.dayKey] || (marks[e.dayKey] = { event: false, deadline: false });
      mark[e.kind] = true;
    }
    return marks;
  }

  function applyRegistration(entries, updatedEvent) {
    return (entries || []).map((e) => {
      if (e.kind !== "event" || e.id !== updatedEvent.id) return e;
      return { ...e, raw: { ...e.raw, ...updatedEvent } };
    });
  }

  /* ------------------------------------------------------------------ almacenamiento y avisos */

  function createCache(storage, prefix) {
    const base = prefix || "upa_campus_cache_";
    return {
      set(key, data, now) {
        try {
          storage.setItem(base + key, JSON.stringify({ savedAt: now === undefined ? Date.now() : now, data }));
          return true;
        } catch (_) {
          return false;
        }
      },
      get(key) {
        try {
          const raw = storage.getItem(base + key);
          if (!raw) return null;
          const parsed = JSON.parse(raw);
          return parsed && typeof parsed.savedAt === "number" ? parsed : null;
        } catch (_) {
          return null;
        }
      },
      clear() {
        const keys = [];
        for (let i = 0; i < storage.length; i += 1) {
          const k = storage.key(i);
          if (k && k.startsWith(base)) keys.push(k);
        }
        keys.forEach((k) => storage.removeItem(k));
        return keys.length;
      },
    };
  }

  function loadNotificationPrefs(storage) {
    try {
      const parsed = JSON.parse(storage.getItem("upa_campus_notifications") || "null");
      if (parsed && typeof parsed === "object") {
        return {
          events: parsed.events !== false,
          announcements: parsed.announcements !== false,
          deadlines: parsed.deadlines !== false,
        };
      }
    } catch (_) {
      /* preferencias corruptas: se restauran los valores por defecto */
    }
    return { ...DEFAULT_NOTIFICATIONS };
  }

  function saveNotificationPrefs(storage, prefs) {
    storage.setItem("upa_campus_notifications", JSON.stringify(prefs));
  }

  function pickDueNotifications(input) {
    const { prefs, entries, banners, seen, nowMs } = input;
    const now = nowMs === undefined ? Date.now() : nowMs;
    const seenSet = new Set(seen || []);
    const out = [];
    for (const entry of entries || []) {
      if (!entry.date) continue;
      const delta = entry.date.getTime() - now;
      if (delta <= 0 || delta > NOTIFY_WINDOW_MS) continue;
      if (entry.kind === "deadline" && prefs.deadlines && !seenSet.has(entry.key)) {
        out.push({ id: entry.key, title: "Tarea próxima a vencer", body: `${entry.title} vence hoy a las ${entry.timeLabel}.` });
      }
      if (entry.kind === "event" && prefs.events && entry.raw.is_registered && !seenSet.has(entry.key)) {
        out.push({ id: entry.key, title: "Tu evento comienza pronto", body: `${entry.title} a las ${entry.timeLabel}.` });
      }
    }
    if (prefs.announcements) {
      for (const banner of banners || []) {
        const id = `banner:${banner.id}`;
        if (!seenSet.has(id)) out.push({ id, title: "Aviso urgente", body: banner.title });
      }
    }
    return out;
  }

  /* ------------------------------------------------------------------ navegacion (boton Atras de Android) */

  function createOverlayManager(win, onChange) {
    const stack = [];
    const notify = () => {
      if (onChange) onChange(stack.slice());
    };

    function onPopState(event) {
      const depth = (event && event.state && event.state.upaDepth) || 0;
      let changed = false;
      while (stack.length > depth) {
        stack.pop();
        changed = true;
      }
      if (changed) notify();
    }
    win.addEventListener("popstate", onPopState);

    return {
      open(name) {
        stack.push(name);
        win.history.pushState({ upaDepth: stack.length, overlay: name }, "");
        notify();
      },
      close() {
        if (stack.length) win.history.back();
      },
      closeAll() {
        if (stack.length) win.history.go(-stack.length);
      },
      top() {
        return stack.length ? stack[stack.length - 1] : null;
      },
      depth() {
        return stack.length;
      },
      destroy() {
        win.removeEventListener("popstate", onPopState);
      },
    };
  }

  /* ------------------------------------------------------------------ codigo QR */

  function buildQr(text, qrFactory, options) {
    const opts = options || {};
    const margin = opts.margin === undefined ? 4 : opts.margin;
    const qr = qrFactory(0, "M");
    qr.addData(String(text));
    qr.make();
    const count = qr.getModuleCount();
    const matrix = [];
    for (let r = 0; r < count; r += 1) {
      const row = [];
      for (let c = 0; c < count; c += 1) row.push(qr.isDark(r, c));
      matrix.push(row);
    }
    const size = count + margin * 2;
    let path = "";
    for (let r = 0; r < count; r += 1) {
      for (let c = 0; c < count; c += 1) {
        if (matrix[r][c]) path += `M${c + margin} ${r + margin}h1v1h-1z`;
      }
    }
    const svg =
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" shape-rendering="crispEdges" role="img" aria-label="Código QR">` +
      `<rect width="${size}" height="${size}" fill="#ffffff"/><path d="${path}" fill="#0a192f"/></svg>`;
    return { svg, matrix, modules: count, margin, size };
  }

  return {
    TIMEZONE,
    THEMES,
    THEME_COLORS,
    INSTALL_DISMISS_MS,
    ApiError,
    createApi,
    friendlyError,
    isConnectivityError,
    looksLikeJwt,
    parseAuthFragment,
    translateAuthError,
    decodeJwtPayload,
    isTokenExpired,
    roleLabel,
    initials,
    isMobileEnvironment,
    normalizeTheme,
    resolveTheme,
    detectInstallPlatform,
    shouldShowInstallBanner,
    dayKey,
    formatTime,
    formatDayLong,
    formatDayShort,
    formatMonthLabel,
    formatPublished,
    monthGrid,
    shiftMonth,
    safeUrl,
    isVideoMedia,
    postKind,
    postOrigin,
    originLabel,
    kindLabel,
    postSummary,
    resolveDetailLinks,
    sortFeed,
    normalizeFeed,
    mergePosts,
    parseClassroomDue,
    buildAgendaEntries,
    upcomingEntries,
    entriesForDay,
    groupAgendaByMonth,
    markedDays,
    applyRegistration,
    createCache,
    loadNotificationPrefs,
    saveNotificationPrefs,
    pickDueNotifications,
    createOverlayManager,
    buildQr,
  };
});
