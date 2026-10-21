/**
 * Nucleo del Cockpit de Redaccion (web-admin).
 *
 * Modulo sin dependencias del DOM: constantes, validacion de formularios, construccion de payloads,
 * formateo, renderizado seguro de tablas (HTML escapado) y cliente REST con timeout.
 * Se carga en el navegador como `window.UpaEditorial` y en Node (`require`) para las pruebas
 * de integracion contra el backend real.
 *
 * Los textos visibles al usuario estan centralizados en `TEXTS` y los catalogos (categorias,
 * grupos, tipos de archivo) en constantes, para poder adaptarlos facilmente al diseno institucional.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.UpaEditorial = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ---------------------------------------------------------------------------
  // Catalogos y constantes (alineados con el backend)
  // ---------------------------------------------------------------------------

  const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
  const DEFAULT_TIMEOUT_MS = 15000;
  const UPLOAD_TIMEOUT_MS = 60000;

  /** Tipos MIME aceptados por POST /api/media/upload (el servidor ademas valida por contenido). */
  const ALLOWED_UPLOAD_TYPES = ["image/jpeg", "image/png", "image/webp", "application/pdf"];

  const CATEGORIES = [
    { value: "MELDUNG", label: "Meldung del campus" },
    { value: "ANKUENDIGUNG", label: "Anuncio" },
    { value: "VERANSTALTUNG", label: "Aviso de evento" },
    { value: "STELLENANGEBOT", label: "Oferta laboral" },
  ];

  const TARGET_GROUPS = [
    { value: "ALL", label: "Toda la comunidad UPA" },
    { value: "TIE", label: "Ingeniería Empresarial" },
    { value: "PI", label: "Ingeniería Industrial" },
    { value: "TI", label: "Tecnologías de la Información" },
    { value: "PROF", label: "Cuerpo docente" },
  ];

  const POST_TYPE_NORMAL = "MANUAL";
  const POST_TYPE_URGENT = "EMERGENCY_BANNER";

  const LIMITS = { title: 255, teaser: 300, content: 20000, location: 255, description: 20000 };

  const TEXTS = {
    errTimeout: "La solicitud tardó demasiado y fue cancelada. Verifique la conexión e intente nuevamente.",
    errNetwork: "No se pudo contactar con el servidor. Verifique la conexión a la red.",
    errUnauthorized: "Su sesión ha expirado. Inicie sesión nuevamente.",
    errForbidden: "No tiene permisos de redacción para esta acción.",
    errNotFound: "El elemento ya no existe (posiblemente fue eliminado).",
    errServer: "Error interno del servidor. Intente nuevamente más tarde.",
    errUploadTooLarge: "El archivo supera el límite de 10 MB.",
    errUploadType: "Tipo de archivo no permitido. Formatos válidos: JPG, PNG, WEBP y PDF.",
    errUploadEmpty: "El archivo está vacío.",
    errUploadMissing: "Seleccione un archivo para subir.",
    errTitleRequired: "El título es obligatorio.",
    errDateRequired: "La fecha del evento es obligatoria.",
    errStartRequired: "La hora de inicio es obligatoria.",
    errEndBeforeStart: "La hora de finalización no puede ser anterior al inicio.",
    errGroupRequired: "Seleccione al menos un grupo destinatario.",
    errCategoryInvalid: "Categoría no válida.",
    errExpiresInvalid: "La fecha de vigencia no es válida.",
  };

  // ---------------------------------------------------------------------------
  // Errores de API
  // ---------------------------------------------------------------------------

  /**
   * Error tipificado. `kind`: timeout | network | unauthorized | forbidden | not_found |
   * validation | client | server | upload_too_large | upload_type | upload_empty | upload_missing
   */
  class ApiError extends Error {
    constructor(kind, message, status, detail) {
      super(message);
      this.name = "ApiError";
      this.kind = kind;
      this.status = status || 0;
      this.detail = detail === undefined ? null : detail;
    }
  }

  /** Extrae un texto legible del campo `detail` de FastAPI (string o lista de errores 422). */
  function extractDetailMessage(detail) {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (item && typeof item === "object") {
            const loc = Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(".") : "";
            return loc ? `${loc}: ${item.msg}` : String(item.msg || "");
          }
          return String(item);
        })
        .filter(Boolean)
        .join("; ");
    }
    return "";
  }

  function errorFromResponse(status, body) {
    const detail = body && typeof body === "object" ? body.detail : undefined;
    const detailText = extractDetailMessage(detail);
    if (status === 401) return new ApiError("unauthorized", TEXTS.errUnauthorized, status, detail);
    if (status === 403) return new ApiError("forbidden", TEXTS.errForbidden, status, detail);
    if (status === 404) return new ApiError("not_found", detailText || TEXTS.errNotFound, status, detail);
    if (status === 400 || status === 413 || status === 422) {
      return new ApiError("validation", detailText || `Datos inválidos (HTTP ${status}).`, status, detail);
    }
    if (status >= 500) return new ApiError("server", TEXTS.errServer, status, detail);
    return new ApiError("client", detailText || `Error HTTP ${status}.`, status, detail);
  }

  /** Mensaje para mostrar en la interfaz a partir de cualquier error capturado. */
  function describeError(error) {
    if (error instanceof ApiError) return error.message;
    if (error && error.message) return error.message;
    return TEXTS.errServer;
  }

  // ---------------------------------------------------------------------------
  // Validacion de archivos
  // ---------------------------------------------------------------------------

  /**
   * Valida un archivo antes de subirlo (tamaño y tipo). No sustituye la validacion del servidor,
   * evita transferir archivos que serian rechazados.
   * @returns {{ok: boolean, kind?: string, message?: string}}
   */
  function validateUploadFile(file) {
    if (!file) return { ok: false, kind: "upload_missing", message: TEXTS.errUploadMissing };
    if (!file.size) return { ok: false, kind: "upload_empty", message: TEXTS.errUploadEmpty };
    if (file.size > MAX_UPLOAD_BYTES) {
      return { ok: false, kind: "upload_too_large", message: TEXTS.errUploadTooLarge };
    }
    const type = String(file.type || "").split(";")[0].trim().toLowerCase();
    if (!ALLOWED_UPLOAD_TYPES.includes(type)) {
      return { ok: false, kind: "upload_type", message: TEXTS.errUploadType };
    }
    return { ok: true };
  }

  // ---------------------------------------------------------------------------
  // Utilidades de formato y seguridad
  // ---------------------------------------------------------------------------

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /** Solo permite URLs http(s) o rutas relativas al servidor; evita `javascript:` y similares. */
  function safeUrl(url) {
    const clean = String(url || "").trim();
    if (/^https?:\/\//i.test(clean)) return clean;
    if (clean.startsWith("/") && !clean.startsWith("//")) return clean;
    return "";
  }

  function isImageUrl(url) {
    return /\.(jpe?g|png|webp)(\?.*)?$/i.test(String(url || "").trim());
  }

  function mediaTypeForUrl(url) {
    return isImageUrl(url) ? "IMAGE" : "";
  }

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  /** Combina fecha (YYYY-MM-DD) y hora (HH:MM) locales del navegador en un ISO-8601 UTC. */
  function localDateTimeToIso(date, time) {
    if (!date || !time) return null;
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
    const timeMatch = /^(\d{2}):(\d{2})$/.exec(time);
    if (!match || !timeMatch) return null;
    const [year, month, day, hour, minute] = [match[1], match[2], match[3], timeMatch[1], timeMatch[2]].map(Number);
    const d = new Date(year, month - 1, day, hour, minute, 0, 0);
    // Rechaza valores que el constructor Date "corrige" (mes 13, 31 de febrero, hora 25, etc.)
    const exact =
      d.getFullYear() === year &&
      d.getMonth() === month - 1 &&
      d.getDate() === day &&
      d.getHours() === hour &&
      d.getMinutes() === minute;
    if (!exact) return null;
    return d.toISOString();
  }

  /** Inverso de `localDateTimeToIso`: devuelve {date, time} en hora local. */
  function isoToLocalParts(iso) {
    const d = new Date(iso);
    if (!iso || Number.isNaN(d.getTime())) return { date: "", time: "" };
    return {
      date: `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`,
      time: `${pad2(d.getHours())}:${pad2(d.getMinutes())}`,
    };
  }

  function formatDateTime(iso, options) {
    const d = new Date(iso);
    if (!iso || Number.isNaN(d.getTime())) return "";
    const opts = options || {};
    return d.toLocaleString(opts.locale || "es-PY", {
      timeZone: opts.timeZone,
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function categoryLabel(value) {
    const found = CATEGORIES.find((c) => c.value === value);
    return found ? found.label : "";
  }

  // ---------------------------------------------------------------------------
  // Formulario de noticias: validacion y payload
  // ---------------------------------------------------------------------------

  function cleanGroups(groups) {
    const list = Array.isArray(groups) ? groups : [];
    return list.map((g) => String(g).trim()).filter(Boolean);
  }

  /**
   * @param {object} v {title, teaser, content, category, targetGroups[], urgent, pinned, imageUrl, expiresAt}
   * @returns {Object<string,string>} errores por campo (vacio si es valido)
   */
  function validateNewsValues(v) {
    const errors = {};
    const title = String(v.title || "").trim();
    if (!title) errors.title = TEXTS.errTitleRequired;
    else if (title.length > LIMITS.title) errors.title = `El título no puede superar ${LIMITS.title} caracteres.`;
    if (String(v.teaser || "").length > LIMITS.teaser) {
      errors.teaser = `El teaser no puede superar ${LIMITS.teaser} caracteres.`;
    }
    if (String(v.content || "").length > LIMITS.content) {
      errors.content = `El texto no puede superar ${LIMITS.content} caracteres.`;
    }
    if (v.category && !CATEGORIES.some((c) => c.value === v.category)) {
      errors.category = TEXTS.errCategoryInvalid;
    }
    if (cleanGroups(v.targetGroups).length === 0) errors.targetGroups = TEXTS.errGroupRequired;
    if (v.expiresAt) {
      const t = new Date(v.expiresAt).getTime();
      if (Number.isNaN(t)) errors.expiresAt = TEXTS.errExpiresInvalid;
    }
    return errors;
  }

  /**
   * Construye el cuerpo para POST /api/news (create) o PUT /api/news/{id} (update).
   * En update se pueden vaciar campos de texto enviando cadena vacia; expires_at solo se envia si existe.
   */
  function buildNewsPayload(v, mode) {
    const isUpdate = mode === "update";
    const imageUrl = String(v.imageUrl || "").trim();
    const payload = {
      title: String(v.title || "").trim(),
      caption: String(v.teaser || "").trim(),
      content: String(v.content || "").trim(),
      post_type: v.urgent ? POST_TYPE_URGENT : POST_TYPE_NORMAL,
      category: v.category || "",
      is_pinned: Boolean(v.pinned),
      target_groups: cleanGroups(v.targetGroups),
      media_url: imageUrl,
      media_type: mediaTypeForUrl(imageUrl),
    };
    if (!isUpdate) {
      payload.is_news = true;
      payload.is_event = false;
    }
    if (v.expiresAt) {
      payload.expires_at = new Date(v.expiresAt).toISOString();
    }
    return payload;
  }

  /** Valores de formulario a partir de una noticia del backend (para editar). */
  function newsToFormValues(news) {
    return {
      title: news.title || "",
      teaser: news.caption || "",
      content: news.content || "",
      category: news.category || "",
      targetGroups: Array.isArray(news.target_groups) ? news.target_groups.slice() : ["ALL"],
      urgent: news.post_type === POST_TYPE_URGENT,
      pinned: Boolean(news.is_pinned),
      imageUrl: news.media_url || news.image_url || "",
      expiresAt: "",
    };
  }

  // ---------------------------------------------------------------------------
  // Formulario de eventos: validacion y payload
  // ---------------------------------------------------------------------------

  /**
   * @param {object} v {title, description, location, date, startTime, endTime, targetGroups[], rsvp, imageUrl}
   */
  function validateEventValues(v) {
    const errors = {};
    const title = String(v.title || "").trim();
    if (!title) errors.title = TEXTS.errTitleRequired;
    else if (title.length > LIMITS.title) errors.title = `El título no puede superar ${LIMITS.title} caracteres.`;
    if (String(v.description || "").length > LIMITS.description) {
      errors.description = `La descripción no puede superar ${LIMITS.description} caracteres.`;
    }
    if (String(v.location || "").length > LIMITS.location) {
      errors.location = `El lugar no puede superar ${LIMITS.location} caracteres.`;
    }
    if (!v.date || !localDateTimeToIso(v.date, "00:00")) errors.date = TEXTS.errDateRequired;
    if (!v.startTime || !/^\d{2}:\d{2}$/.test(v.startTime)) errors.startTime = TEXTS.errStartRequired;
    if (!errors.date && !errors.startTime && v.endTime) {
      const start = localDateTimeToIso(v.date, v.startTime);
      const end = localDateTimeToIso(v.date, v.endTime);
      if (!end || new Date(end) < new Date(start)) errors.endTime = TEXTS.errEndBeforeStart;
    }
    if (cleanGroups(v.targetGroups).length === 0) errors.targetGroups = TEXTS.errGroupRequired;
    return errors;
  }

  /** Construye el cuerpo para POST /api/events o PUT /api/events/{id}. */
  function buildEventPayload(v) {
    const imageUrl = String(v.imageUrl || "").trim();
    const payload = {
      title: String(v.title || "").trim(),
      description: String(v.description || "").trim(),
      location: String(v.location || "").trim(),
      event_start: localDateTimeToIso(v.date, v.startTime),
      has_registration: Boolean(v.rsvp),
      target_groups: cleanGroups(v.targetGroups),
      image_url: imageUrl,
      media_type: mediaTypeForUrl(imageUrl),
    };
    if (v.endTime) payload.event_end = localDateTimeToIso(v.date, v.endTime);
    return payload;
  }

  /** Valores de formulario a partir de un evento del backend (para editar). */
  function eventToFormValues(event) {
    const start = isoToLocalParts(event.event_start);
    const end = isoToLocalParts(event.event_end);
    return {
      title: event.title || "",
      description: event.description || "",
      location: event.location || "",
      date: start.date,
      startTime: start.time,
      endTime: end.date === start.date ? end.time : "",
      targetGroups: Array.isArray(event.target_groups) ? event.target_groups.slice() : ["ALL"],
      rsvp: Boolean(event.has_registration),
      imageUrl: event.image_url || "",
    };
  }

  // ---------------------------------------------------------------------------
  // Renderizado seguro (todo el contenido dinamico se escapa)
  // ---------------------------------------------------------------------------

  function groupBadges(groups) {
    return (Array.isArray(groups) ? groups : [])
      .map((g) => `<span class="ed-badge ed-badge-info">${escapeHtml(g)}</span>`)
      .join(" ");
  }

  function renderNewsRows(items) {
    if (!items || items.length === 0) {
      return `<tr><td colspan="5" class="ed-empty">Aún no hay noticias publicadas.</td></tr>`;
    }
    return items
      .map((n) => {
        const urgent = n.post_type === POST_TYPE_URGENT;
        const isInstagram = n.post_type === "INSTAGRAM";
        const typeBadge = urgent
          ? `<span class="ed-badge ed-badge-urgent">Eilmeldung</span>`
          : isInstagram
            ? `<span class="ed-badge ed-badge-social">Instagram</span>`
            : `<span class="ed-badge ed-badge-neutral">Normal</span>`;
        const img = safeUrl(n.media_url || n.image_url);
        const thumb = img && isImageUrl(img) ? `<img src="${escapeHtml(img)}" alt="" class="ed-thumb" loading="lazy">` : "";
        return `<tr data-news-id="${escapeHtml(n.id)}">
          <td class="ed-cell-title">${thumb}<div><div class="ed-title">${escapeHtml(n.title)}</div><div class="ed-subtle">${escapeHtml(
            n.caption
          )}</div></div></td>
          <td>${escapeHtml(categoryLabel(n.category)) || "&mdash;"}</td>
          <td>${typeBadge}</td>
          <td>${groupBadges(n.target_groups)}</td>
          <td class="ed-actions">
            <button type="button" class="ed-btn ed-btn-secondary ed-btn-sm" data-action="edit-news" data-id="${escapeHtml(
              n.id
            )}">Editar</button>
            <button type="button" class="ed-btn ed-btn-danger ed-btn-sm" data-action="delete-news" data-id="${escapeHtml(
              n.id
            )}">Eliminar</button>
          </td>
        </tr>`;
      })
      .join("");
  }

  function renderEventRows(items, options) {
    const opts = options || {};
    if (!items || items.length === 0) {
      return `<tr><td colspan="5" class="ed-empty">No hay eventos para mostrar.</td></tr>`;
    }
    return items
      .map((e) => {
        const when = formatDateTime(e.event_start, opts);
        const rsvp = e.has_registration
          ? `<span class="ed-badge ed-badge-ok">RSVP activo &bull; ${escapeHtml(e.registered_count)}</span>`
          : `<span class="ed-badge ed-badge-neutral">Sin RSVP</span>`;
        return `<tr data-event-id="${escapeHtml(e.id)}">
          <td class="ed-cell-title"><div><div class="ed-title">${escapeHtml(e.title)}</div><div class="ed-subtle">${escapeHtml(
            e.location
          )}</div></div></td>
          <td>${escapeHtml(when)}</td>
          <td>${rsvp}</td>
          <td>${groupBadges(e.target_groups)}</td>
          <td class="ed-actions">
            <button type="button" class="ed-btn ed-btn-secondary ed-btn-sm" data-action="participants-event" data-id="${escapeHtml(
              e.id
            )}">Participantes</button>
            <button type="button" class="ed-btn ed-btn-secondary ed-btn-sm" data-action="edit-event" data-id="${escapeHtml(
              e.id
            )}">Editar</button>
            <button type="button" class="ed-btn ed-btn-danger ed-btn-sm" data-action="delete-event" data-id="${escapeHtml(
              e.id
            )}">Eliminar</button>
          </td>
        </tr>`;
      })
      .join("");
  }

  function renderParticipantsTable(response, options) {
    const opts = options || {};
    const regs = (response && response.registrations) || [];
    const header = `<div class="ed-participants-head"><strong>${escapeHtml(
      response ? response.title : ""
    )}</strong><span class="ed-badge ed-badge-ok">${escapeHtml(
      response ? response.attending_count : 0
    )} inscritos</span></div>`;
    if (regs.length === 0) {
      return `${header}<p class="ed-empty">Todavía no hay participantes inscritos.</p>`;
    }
    const rows = regs
      .map((r) => {
        const attending = r.status === "attending";
        return `<tr>
          <td>${escapeHtml(r.full_name)}</td>
          <td class="ed-mono">${escapeHtml(r.email)}</td>
          <td>${
            attending
              ? `<span class="ed-badge ed-badge-ok">Asiste</span>`
              : `<span class="ed-badge ed-badge-neutral">${escapeHtml(r.status)}</span>`
          }</td>
          <td>${escapeHtml(formatDateTime(r.registered_at, opts))}</td>
        </tr>`;
      })
      .join("");
    return `${header}<table class="ed-table"><thead><tr><th>Nombre</th><th>Correo</th><th>Estado</th><th>Inscripción</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  /** Texto de estado para la sincronizacion con Instagram a partir de la respuesta del backend. */
  function describeSyncResult(result) {
    const r = result || {};
    if (r.status === "skipped") {
      return {
        type: "warning",
        message: `Sincronización omitida: ${r.message || "sin credenciales de Instagram configuradas."}`,
      };
    }
    if (r.status === "success") {
      const synced = Number(r.synced_count || 0);
      if (synced === 0) {
        return {
          type: "info",
          message: r.message || "Sincronización completada: no se recibieron publicaciones nuevas.",
        };
      }
      return {
        type: "success",
        message: `Sincronización completada: ${synced} publicaciones (${Number(r.created_count || 0)} nuevas, ${Number(
          r.updated_count || 0
        )} actualizadas).`,
      };
    }
    return { type: "error", message: "Respuesta inesperada del servidor al sincronizar Instagram." };
  }

  // ---------------------------------------------------------------------------
  // Cliente REST
  // ---------------------------------------------------------------------------

  /**
   * @param {object} config
   * @param {string} [config.baseUrl]            prefijo de URL (vacio en el navegador, mismo origen)
   * @param {function():string|null} config.getToken  devuelve el JWT de sesion
   * @param {function} [config.onUnauthorized]   se invoca ante HTTP 401 (sesion expirada)
   * @param {number} [config.timeoutMs]          timeout por solicitud JSON
   * @param {number} [config.uploadTimeoutMs]    timeout para cargas de archivos
   * @param {function} [config.fetchImpl]        implementacion de fetch (por defecto la global)
   */
  function createClient(config) {
    const baseUrl = (config && config.baseUrl) || "";
    const getToken = (config && config.getToken) || (() => null);
    const onUnauthorized = (config && config.onUnauthorized) || (() => {});
    const timeoutMs = (config && config.timeoutMs) || DEFAULT_TIMEOUT_MS;
    const uploadTimeoutMs = (config && config.uploadTimeoutMs) || UPLOAD_TIMEOUT_MS;
    const fetchImpl = (config && config.fetchImpl) || ((...args) => fetch(...args));

    async function request(method, path, opts) {
      const options = opts || {};
      const controller = new AbortController();
      const limit = options.timeoutMs || timeoutMs;
      let timedOut = false;
      const timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, limit);

      const headers = { Accept: "application/json" };
      const token = getToken();
      if (token) headers.Authorization = `Bearer ${token}`;

      let body;
      if (options.formData) {
        body = options.formData; // el navegador fija el boundary multipart
      } else if (options.json !== undefined) {
        headers["Content-Type"] = "application/json";
        body = JSON.stringify(options.json);
      }

      try {
        let response;
        let text;
        try {
          response = await fetchImpl(baseUrl + path, { method, headers, body, signal: controller.signal });
          text = await response.text();
        } catch (err) {
          if (timedOut) throw new ApiError("timeout", TEXTS.errTimeout, 0);
          throw new ApiError("network", TEXTS.errNetwork, 0);
        }

        let parsed = null;
        if (text) {
          try {
            parsed = JSON.parse(text);
          } catch (_) {
            parsed = null;
          }
        }

        if (response.ok) return parsed;

        const error = errorFromResponse(response.status, parsed);
        if (error.kind === "unauthorized") onUnauthorized(error);
        throw error;
      } finally {
        clearTimeout(timer);
      }
    }

    const qs = (params) => {
      const entries = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null);
      return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
    };

    return {
      request,
      getMe: () => request("GET", "/api/auth/me"),

      listNews: (params) => request("GET", `/api/news${qs({ limit: 100, ...params })}`),
      createNews: (payload) => request("POST", "/api/news", { json: payload }),
      updateNews: (id, payload) => request("PUT", `/api/news/${encodeURIComponent(id)}`, { json: payload }),
      deleteNews: (id) => request("DELETE", `/api/news/${encodeURIComponent(id)}`),

      listEvents: (params) => request("GET", `/api/events${qs({ upcoming_only: true, limit: 100, ...params })}`),
      createEvent: (payload) => request("POST", "/api/events", { json: payload }),
      updateEvent: (id, payload) => request("PUT", `/api/events/${encodeURIComponent(id)}`, { json: payload }),
      deleteEvent: (id) => request("DELETE", `/api/events/${encodeURIComponent(id)}`),
      getEventRegistrations: (id) => request("GET", `/api/events/${encodeURIComponent(id)}/registrations`),

      syncInstagram: () => request("POST", "/api/news/sync-instagram", { timeoutMs: uploadTimeoutMs }),

      /**
       * Sube un archivo a POST /api/media/upload. Valida tamaño y tipo en el cliente,
       * salvo que `skipClientValidation` sea verdadero (usado para verificar el rechazo del servidor).
       */
      async uploadMedia(file, uploadOptions) {
        const skip = uploadOptions && uploadOptions.skipClientValidation;
        if (!skip) {
          const check = validateUploadFile(file);
          if (!check.ok) throw new ApiError(check.kind, check.message, 0);
        }
        const formData = new FormData();
        formData.append("file", file, file.name || "upload");
        return request("POST", "/api/media/upload", { formData, timeoutMs: uploadTimeoutMs });
      },
    };
  }

  return {
    MAX_UPLOAD_BYTES,
    DEFAULT_TIMEOUT_MS,
    ALLOWED_UPLOAD_TYPES,
    CATEGORIES,
    TARGET_GROUPS,
    POST_TYPE_NORMAL,
    POST_TYPE_URGENT,
    TEXTS,
    ApiError,
    describeError,
    extractDetailMessage,
    validateUploadFile,
    escapeHtml,
    safeUrl,
    isImageUrl,
    localDateTimeToIso,
    isoToLocalParts,
    formatDateTime,
    categoryLabel,
    validateNewsValues,
    buildNewsPayload,
    newsToFormValues,
    validateEventValues,
    buildEventPayload,
    eventToFormValues,
    renderNewsRows,
    renderEventRows,
    renderParticipantsTable,
    describeSyncResult,
    createClient,
  };
});
