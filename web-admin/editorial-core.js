/**
 * Nucleo del Portal Institucional y Cockpit Editorial (web-admin).
 *
 * Modulo sin dependencias del DOM: constantes, validacion de formularios, construccion de payloads,
 * formateo, renderizado seguro de tablas (HTML escapado) y cliente REST con timeout.
 * Se carga en el navegador como `window.UpaEditorial` y en Node (`require`) para las pruebas
 * unitarias y de integracion contra el backend real.
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

  /** Claves canonicas de permisos del portal. */
  const PERMISSION_KEYS = ["publicaciones", "grupos", "roles", "apis", "historial"];

  /** Tipos MIME aceptados por POST /api/media/upload (el servidor ademas valida por contenido). */
  const ALLOWED_UPLOAD_TYPES = [
    "image/jpeg",
    "image/png",
    "image/webp",
    "video/mp4",
    "video/webm",
    "application/pdf",
  ];

  const CATEGORIES = [
    { value: "MELDUNG", label: "Comunicado del campus" },
    { value: "ANKUENDIGUNG", label: "Anuncio" },
    { value: "VERANSTALTUNG", label: "Actividad académica" },
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
  const POST_TYPE_INSTAGRAM = "INSTAGRAM";

  const LIMITS = {
    title: 255,
    teaser: 300,
    content: 20000,
    detailText: 20000,
    location: 255,
    description: 20000,
    linkLabel: 120,
    linkUrl: 1024,
  };

  const TEXTS = {
    errTimeout: "La solicitud tardó demasiado y fue cancelada. Verifique la conexión e intente nuevamente.",
    errNetwork: "No se pudo contactar con el servidor. Verifique la conexión a la red.",
    errUnauthorized: "Su sesión ha expirado. Inicie sesión nuevamente.",
    errForbidden: "No tiene permisos de redacción para esta acción.",
    errNotFound: "El elemento ya no existe (posiblemente fue eliminado).",
    errServer: "Error interno del servidor. Intente nuevamente más tarde.",
    errUploadTooLarge: "El archivo supera el límite de 10 MB.",
    errUploadType: "Tipo de archivo no permitido. Formatos válidos: JPG, PNG, WEBP, MP4, WEBM y PDF.",
    errUploadEmpty: "El archivo está vacío.",
    errUploadMissing: "Seleccione un archivo para subir.",
    errTitleRequired: "El título es obligatorio.",
    errDateRequired: "La fecha del evento es obligatoria.",
    errStartRequired: "La hora de inicio es obligatoria.",
    errEventStartRequired: "Indique la fecha y hora de inicio del evento.",
    errEventStartInvalid: "Fecha u hora de inicio inválida. Use el formato DD/MM/YYYY HH:mm (24h).",
    errEventEndInvalid: "Hora de finalización inválida. Use el formato de 24 horas HH:mm.",
    errEndBeforeStart: "La hora de finalización no puede ser anterior al inicio.",
    errGroupRequired: "Seleccione al menos un grupo destinatario.",
    errCategoryInvalid: "Categoría no válida.",
    errExpiresRequired: "Indique la fecha y hora de vigencia para fijar la publicación.",
    errExpiresInvalid: "La fecha de vigencia no es válida (use DD/MM/YYYY HH:mm).",
    errPublishedInvalid: "La fecha programada de publicación no es válida (use DD/MM/YYYY HH:mm).",
    errPublishedPast: "La fecha programada de publicación no puede estar en el pasado.",
    errSectionRequired: "Active al menos una sección: Noticia o Evento.",
    errUrgentNoEvent: "Los avisos urgentes no admiten sección de Evento.",
    aiAutocompleteButton: "Autocompletar con IA",
    aiAutocompleteBusy: "Analizando contenido e imagen...",
    aiAutocompleteSuccess: "Campos completados por IA",
    aiAutocompleteError: "No se pudo autocompletar: Verifique la clave de IA en Control de IA",
    aiAutocompleteDisabledTooltip:
      "Configure un token válido de Gemini en la pestaña IA para habilitar el autocompletado.",
    aiAutocompleteEnabledTooltip: "Autocompletar campos vacíos con Google Gemini Flash",
  };

  // ---------------------------------------------------------------------------
  // Errores de API
  // ---------------------------------------------------------------------------

  class ApiError extends Error {
    constructor(kind, message, status, detail) {
      super(message);
      this.name = "ApiError";
      this.kind = kind;
      this.status = status || 0;
      this.detail = detail === undefined ? null : detail;
    }
  }

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
    if (status === 403) return new ApiError("forbidden", detailText || TEXTS.errForbidden, status, detail);
    if (status === 404) return new ApiError("not_found", detailText || TEXTS.errNotFound, status, detail);
    if (status === 400 || status === 413 || status === 422) {
      return new ApiError("validation", detailText || `Datos inválidos (HTTP ${status}).`, status, detail);
    }
    if (status >= 500) return new ApiError("server", detailText || TEXTS.errServer, status, detail);
    return new ApiError("client", detailText || `Error HTTP ${status}.`, status, detail);
  }

  function describeError(error) {
    if (error instanceof ApiError) return error.message;
    if (error && error.message) return error.message;
    return TEXTS.errServer;
  }

  // ---------------------------------------------------------------------------
  // Validacion de archivos
  // ---------------------------------------------------------------------------

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

  function safeUrl(url) {
    const clean = String(url || "").trim();
    if (/^https?:\/\//i.test(clean)) return clean;
    if (clean.startsWith("/") && !clean.startsWith("//")) return clean;
    return "";
  }

  function isImageUrl(url) {
    return /\.(jpe?g|png|webp)(\?.*)?$/i.test(String(url || "").trim());
  }

  function isVideoUrl(url) {
    return /\.(mp4|webm|mov)(\?.*)?$/i.test(String(url || "").trim());
  }

  function mediaTypeForUrl(url) {
    if (isVideoUrl(url)) return "VIDEO";
    if (isImageUrl(url)) return "IMAGE";
    return "";
  }

  function extractInstagramTeaser(text) {
    if (!text) return "";
    const lines = String(text)
      .replace(/\r/g, "")
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    if (!lines.length) return "";
    return lines.slice(0, 2).join("\n").slice(0, LIMITS.teaser);
  }

  const REMINDER_UNITS = [
    { value: "minutes", label: "minutos", factor: 1 },
    { value: "hours", label: "horas", factor: 60 },
    { value: "days", label: "días", factor: 1440 },
  ];

  function reminderToParts(totalMinutes) {
    const mins = Number(totalMinutes);
    if (!Number.isFinite(mins) || mins <= 0) {
      return { value: 30, unit: "minutes" };
    }
    if (mins % 1440 === 0) return { value: mins / 1440, unit: "days" };
    if (mins % 60 === 0) return { value: mins / 60, unit: "hours" };
    return { value: mins, unit: "minutes" };
  }

  function partsToReminderMinutes(value, unit) {
    const num = Number(value);
    if (!Number.isFinite(num) || num < 0) return null;
    const found = REMINDER_UNITS.find((u) => u.value === unit) || REMINDER_UNITS[0];
    return Math.round(num * found.factor);
  }

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function isValidTime24(timeVal) {
    const clean = String(timeVal || "").trim();
    return /^([01]\d|2[0-3]):([0-5]\d)$/.test(clean);
  }

  function parseParaguayDate(dateStr) {
    const clean = String(dateStr || "").trim();
    const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(clean);
    if (!match) return null;
    const day = Number(match[1]);
    const month = Number(match[2]);
    const year = Number(match[3]);
    if (year < 1900 || year > 2100 || month < 1 || month > 12 || day < 1 || day > 31) return null;
    const d = new Date(year, month - 1, day);
    if (d.getFullYear() !== year || d.getMonth() !== month - 1 || d.getDate() !== day) return null;
    return { day, month, year, isoDate: `${year}-${pad2(month)}-${pad2(day)}` };
  }

  function localDateTimeToIso(date, time) {
    if (!date || !time) return null;
    let normalizedDate = String(date).trim();
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(normalizedDate)) {
      const py = parseParaguayDate(normalizedDate);
      if (!py) return null;
      normalizedDate = py.isoDate;
    }
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(normalizedDate);
    const cleanTime = String(time).trim();
    if (!match || !isValidTime24(cleanTime)) return null;
    const [hour, minute] = cleanTime.split(":").map(Number);
    const [year, month, day] = [match[1], match[2], match[3]].map(Number);
    const d = new Date(year, month - 1, day, hour, minute, 0, 0);
    const exact =
      d.getFullYear() === year &&
      d.getMonth() === month - 1 &&
      d.getDate() === day &&
      d.getHours() === hour &&
      d.getMinutes() === minute;
    if (!exact) return null;
    return d.toISOString();
  }

  function isoToLocalParts(iso) {
    const d = new Date(iso);
    if (!iso || Number.isNaN(d.getTime())) return { date: "", time: "" };
    return {
      date: `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`,
      time: `${pad2(d.getHours())}:${pad2(d.getMinutes())}`,
    };
  }

  /** Convierte un ISO-8601 a formato paraguayo `DD/MM/YYYY HH:mm` (24 horas). */
  function isoToParaguayDateTime(iso) {
    const clean = String(iso || "").trim();
    if (!clean) return "";
    const pyMatch = /^(\d{2}\/\d{2}\/\d{4})\s+(\d{2}:\d{2})$/.exec(clean);
    if (pyMatch && parseParaguayDate(pyMatch[1]) && isValidTime24(pyMatch[2])) {
      return `${pyMatch[1]} ${pyMatch[2]}`;
    }
    const d = new Date(clean);
    if (Number.isNaN(d.getTime())) return "";
    return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()} ${pad2(d.getHours())}:${pad2(
      d.getMinutes()
    )}`;
  }

  /** Extrae la hora en formato estricto 24h `HH:mm` desde un ISO-8601 o cadena de hora. */
  function isoToTime24(val) {
    const clean = String(val || "").trim();
    if (!clean) return "";
    if (isValidTime24(clean)) return clean;
    const pyMatch = /^(\d{2}\/\d{2}\/\d{4})\s+(\d{2}:\d{2})(?::\d{2})?$/.exec(clean);
    if (pyMatch && isValidTime24(pyMatch[2])) return pyMatch[2];
    const isoLocalMatch = /^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2})(?::\d{2})?$/.exec(clean);
    if (isoLocalMatch && isValidTime24(isoLocalMatch[2])) return isoLocalMatch[2];
    const d = new Date(clean);
    if (Number.isNaN(d.getTime())) return "";
    return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  }

  /** Convierte un ISO-8601 a valor de formulario `DD/MM/YYYY HH:mm` (24h). */
  function isoToDatetimeLocal(iso) {
    return isoToParaguayDateTime(iso);
  }

  /** Convierte un valor `DD/MM/YYYY HH:mm` (o `YYYY-MM-DDTHH:mm`) a ISO-8601 UTC. */
  function datetimeLocalToIso(localVal) {
    const clean = String(localVal || "").trim();
    if (!clean) return null;
    const pyMatch = /^(\d{2}\/\d{2}\/\d{4})\s+(\d{2}:\d{2})$/.exec(clean);
    if (pyMatch) {
      return localDateTimeToIso(pyMatch[1], pyMatch[2]);
    }
    const isoMatch = /^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2})(?::\d{2})?$/.exec(clean);
    if (isoMatch) {
      return localDateTimeToIso(isoMatch[1], isoMatch[2]);
    }
    return null;
  }

  /** Resuelve la hora de fin opcional (`HH:mm` o fecha+hora) sobre la fecha de `eventStartVal`. */
  function resolveEventEndIso(eventStartVal, eventEndVal) {
    const cleanEnd = String(eventEndVal || "").trim();
    if (!cleanEnd) return null;
    if (isValidTime24(cleanEnd)) {
      const cleanStart = String(eventStartVal || "").trim();
      const pyStart = /^(\d{2}\/\d{2}\/\d{4})\s+/.exec(cleanStart);
      if (pyStart) {
        return localDateTimeToIso(pyStart[1], cleanEnd);
      }
      const isoStart = /^(\d{4}-\d{2}-\d{2})[T\s]/.exec(cleanStart);
      if (isoStart) {
        return localDateTimeToIso(isoStart[1], cleanEnd);
      }
      const startIso = datetimeLocalToIso(cleanStart);
      if (startIso) {
        const parts = isoToLocalParts(startIso);
        return localDateTimeToIso(parts.date, cleanEnd);
      }
      return null;
    }
    return datetimeLocalToIso(cleanEnd);
  }

  /** Aplica mascara progresiva `DD/MM/YYYY HH:mm` cuando el usuario escribe digitos. */
  function maskDateTimeInput(raw) {
    const val = String(raw || "");
    if (!/^[\d/\s:]*$/.test(val)) return val;
    const digits = val.replace(/\D/g, "").slice(0, 12);
    if (!digits) return "";
    let out = digits.slice(0, 2);
    if (digits.length > 2) out += "/" + digits.slice(2, 4);
    if (digits.length > 4) out += "/" + digits.slice(4, 8);
    if (digits.length > 8) out += " " + digits.slice(8, 10);
    if (digits.length > 10) out += ":" + digits.slice(10, 12);
    return out;
  }

  /** Aplica mascara progresiva `HH:mm` (24h) cuando el usuario escribe digitos. */
  function maskTime24Input(raw) {
    const val = String(raw || "");
    if (!/^[\d:]*$/.test(val)) return val;
    const digits = val.replace(/\D/g, "").slice(0, 4);
    if (!digits) return "";
    if (digits.length <= 2) return digits;
    return `${digits.slice(0, 2)}:${digits.slice(2, 4)}`;
  }

  function formatDateTime(iso, options) {
    const d = new Date(iso);
    if (!iso || Number.isNaN(d.getTime())) return "";
    const opts = options || {};
    return d.toLocaleString(opts.locale || "es-PY", {
      timeZone: opts.timeZone,
      hour12: false,
      hourCycle: "h23",
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

  function cleanGroups(groups) {
    const list = Array.isArray(groups) ? groups : [];
    const seen = new Set();
    const out = [];
    for (const raw of list) {
      const val = String(raw || "").trim();
      if (val && !seen.has(val)) {
        seen.add(val);
        out.push(val);
      }
    }
    return out;
  }

  function cleanReminders(reminders) {
    if (!Array.isArray(reminders)) return [];
    const seen = new Set();
    for (const raw of reminders) {
      if (raw === "" || raw === null || raw === undefined) continue;
      const n = Number(raw);
      if (Number.isInteger(n) && n >= 0 && n <= 43200) {
        seen.add(n);
      }
    }
    return Array.from(seen).sort((a, b) => a - b);
  }

  // ---------------------------------------------------------------------------
  // Modelo unificado de Publicaciones (Noticia, Evento o ambos)
  // ---------------------------------------------------------------------------

  function validatePublicationValues(v) {
    const errors = {};
    const title = String(v.title || "").trim();
    if (!title) errors.title = TEXTS.errTitleRequired;
    else if (title.length > LIMITS.title) errors.title = `El título no puede superar ${LIMITS.title} caracteres.`;

    const postType = String(v.postType || POST_TYPE_NORMAL).toUpperCase();
    const isNews = postType === POST_TYPE_INSTAGRAM || postType === POST_TYPE_URGENT ? true : Boolean(v.isNews);
    const isEvent = postType === POST_TYPE_URGENT ? false : Boolean(v.isEvent);

    if (postType === POST_TYPE_URGENT && v.isEvent) {
      errors.section = TEXTS.errUrgentNoEvent;
    } else if (!isNews && !isEvent) {
      errors.section = TEXTS.errSectionRequired;
    }

    if (cleanGroups(v.targetGroups).length === 0) {
      errors.targetGroups = TEXTS.errGroupRequired;
    }

    const isScheduled = Boolean(v.scheduled) || v.publishMode === "scheduled";
    if (isScheduled && postType !== POST_TYPE_INSTAGRAM && !v.isPublished) {
      const pubIso = datetimeLocalToIso(v.publishedAt);
      if (!pubIso) {
        errors.publishedAt = TEXTS.errPublishedInvalid;
      } else if (new Date(pubIso).getTime() < Date.now() - 120000) {
        errors.publishedAt = TEXTS.errPublishedPast;
      }
    }

    if (isNews) {
      if (String(v.caption || "").length > LIMITS.teaser) {
        errors.caption = `El resumen no puede superar ${LIMITS.teaser} caracteres.`;
      }
      if (String(v.content || "").length > LIMITS.content) {
        errors.content = `El texto principal no puede superar ${LIMITS.content} caracteres.`;
      }
      if (v.category && !CATEGORIES.some((c) => c.value === v.category)) {
        errors.category = TEXTS.errCategoryInvalid;
      }
      if (v.pinned) {
        if (!v.expiresAt || !datetimeLocalToIso(v.expiresAt)) {
          errors.expiresAt = v.expiresAt ? TEXTS.errExpiresInvalid : TEXTS.errExpiresRequired;
        }
      } else if (v.expiresAt && !datetimeLocalToIso(v.expiresAt)) {
        errors.expiresAt = TEXTS.errExpiresInvalid;
      }
    }

    if (isEvent) {
      const rawStart = String(v.eventStart || "").trim();
      const rawEnd = String(v.eventEnd || "").trim();
      const startIso = datetimeLocalToIso(rawStart);
      if (!rawStart) {
        errors.eventStart = TEXTS.errEventStartRequired;
      } else if (!startIso) {
        errors.eventStart = TEXTS.errEventStartInvalid;
      }
      if (rawEnd) {
        const validEndFormat = isValidTime24(rawEnd) || Boolean(datetimeLocalToIso(rawEnd));
        if (!validEndFormat) {
          errors.eventEnd = TEXTS.errEventEndInvalid;
        } else if (startIso) {
          const endIso = resolveEventEndIso(rawStart, rawEnd);
          if (!endIso) {
            errors.eventEnd = TEXTS.errEventEndInvalid;
          } else if (new Date(endIso) < new Date(startIso)) {
            errors.eventEnd = TEXTS.errEndBeforeStart;
          }
        }
      }
      if (String(v.location || "").length > LIMITS.location) {
        errors.location = `El lugar no puede superar ${LIMITS.location} caracteres.`;
      }
    }

    return errors;
  }

  function buildPublicationPayload(v) {
    const postType = String(v.postType || POST_TYPE_NORMAL).toUpperCase();
    const isNews = postType === POST_TYPE_INSTAGRAM || postType === POST_TYPE_URGENT ? true : Boolean(v.isNews);
    const isEvent = postType === POST_TYPE_URGENT ? false : Boolean(v.isEvent);
    const targetGroups = cleanGroups(v.targetGroups);
    const imageUrl = String(v.imageUrl || "").trim();
    const isScheduled = Boolean(v.scheduled) || v.publishMode === "scheduled";
    const rawCaption = isNews
      ? postType === POST_TYPE_INSTAGRAM
        ? extractInstagramTeaser(v.content || v.caption)
        : String(v.caption || "").trim()
      : "";

    const payload = {
      title: String(v.title || "").trim(),
      post_type: postType,
      has_registration: Boolean(v.hasRegistration),
      target_groups: targetGroups.length ? targetGroups : ["ALL"],
      published_at:
        postType !== POST_TYPE_INSTAGRAM && isScheduled ? datetimeLocalToIso(v.publishedAt) : null,
      is_news: isNews,
      notify_groups: isNews ? cleanGroups(v.notifyGroups) : [],
      caption: rawCaption,
      content: isNews ? String(v.content || "").trim() : "",
      category: isNews ? String(v.category || "").trim() : "",
      is_pinned: isNews ? Boolean(v.pinned) : false,
      expires_at: isNews && v.expiresAt ? datetimeLocalToIso(v.expiresAt) : null,
      media_url: imageUrl,
      media_type: mediaTypeForUrl(imageUrl),
      link_label: isNews ? String(v.linkLabel || "").trim() : "",
      link_url: isNews ? String(v.linkUrl || "").trim() : "",
      is_event: isEvent,
      event_start: isEvent ? datetimeLocalToIso(v.eventStart) : null,
      event_end: isEvent && String(v.eventEnd || "").trim() ? resolveEventEndIso(v.eventStart, v.eventEnd) : null,
      location: isEvent ? String(v.location || "").trim() : "",
      event_notify_groups: isEvent ? cleanGroups(v.eventNotifyGroups) : [],
      reminders: isEvent ? cleanReminders(v.reminders) : [],
    };
    return payload;
  }

  function publicationToFormValues(pub) {
    const p = pub || {};
    const postType = String(p.post_type || POST_TYPE_NORMAL).toUpperCase();
    const isNews = p.is_news !== undefined ? Boolean(p.is_news) : true;
    const isEvent = Boolean(p.is_event);
    const reminders = Array.isArray(p.reminders) ? p.reminders.slice() : [30];
    const targetGroups = Array.isArray(p.target_groups) && p.target_groups.length ? p.target_groups.slice() : ["ALL"];
    const linkUrl = p.link_url || (postType === POST_TYPE_INSTAGRAM ? p.permalink || "" : "");
    const linkLabel = p.link_label || (postType === POST_TYPE_INSTAGRAM && linkUrl ? "Ver en Instagram" : "");
    const caption =
      postType === POST_TYPE_INSTAGRAM ? extractInstagramTeaser(p.content || p.caption) : p.caption || "";
    const eventNotifyGroups =
      Array.isArray(p.event_notify_groups) && p.event_notify_groups.length
        ? p.event_notify_groups.slice()
        : targetGroups.slice();

    const rawPubDate = p.published_at || p.created_at || "";
    const pubMs = p.published_at ? new Date(p.published_at).getTime() : NaN;
    const isFutureScheduled = Boolean(
      p.published_at &&
        !Number.isNaN(pubMs) &&
        pubMs > Date.now() + 60000 &&
        postType !== POST_TYPE_INSTAGRAM
    );
    const isPublished = Boolean(p.id && !isFutureScheduled);

    return {
      id: p.id || "",
      title: p.title || "",
      postType,
      hasRegistration: Boolean(p.has_registration),
      targetGroups,
      scheduled: isFutureScheduled,
      isPublished,
      publishMode: isFutureScheduled ? "scheduled" : isPublished ? "published" : "on_save",
      publishedAt: isFutureScheduled ? isoToDatetimeLocal(p.published_at) : "",
      publishedAtIso: rawPubDate,
      isNews,
      notifyGroups: Array.isArray(p.notify_groups) ? p.notify_groups.slice() : [],
      caption,
      content: p.content || "",
      category: p.category || "",
      pinned: Boolean(p.is_pinned),
      expiresAt: isoToDatetimeLocal(p.expires_at),
      imageUrl: p.media_url || p.image_url || "",
      permalink: p.permalink || "",
      linkLabel,
      linkUrl,
      isEvent,
      eventStart: isoToParaguayDateTime(p.event_start),
      eventEnd: p.event_end ? isoToTime24(p.event_end) : "",
      location: p.location || "",
      eventNotifyGroups,
      reminders,
      viewsCount: Number(p.views_count || 0),
      attendingCount: Number(p.attending_count || 0),
      declinedCount: Number(p.declined_count || 0),
      isEdited: p.is_edited !== undefined ? Boolean(p.is_edited) : postType !== POST_TYPE_INSTAGRAM,
      isAiGenerated: Boolean(p.is_ai_generated || p.status === "ai"),
    };
  }

  function normalizeAiDatetimeLocal(raw) {
    const clean = String(raw || "").trim();
    if (!clean) return "";
    const pyMatch = /^(\d{2}\/\d{2}\/\d{4})\s+(\d{2}:\d{2})(?::\d{2})?$/.exec(clean);
    if (pyMatch && parseParaguayDate(pyMatch[1]) && isValidTime24(pyMatch[2])) {
      return `${pyMatch[1]} ${pyMatch[2]}`;
    }
    const localMatch = /^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}:\d{2})(?::\d{2})?$/.exec(clean);
    if (localMatch && isValidTime24(localMatch[4])) {
      const pyDate = `${localMatch[3]}/${localMatch[2]}/${localMatch[1]}`;
      if (parseParaguayDate(pyDate)) {
        return `${pyDate} ${localMatch[4]}`;
      }
    }
    const dateOnlyMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(clean);
    if (dateOnlyMatch) {
      const pyDate = `${dateOnlyMatch[3]}/${dateOnlyMatch[2]}/${dateOnlyMatch[1]}`;
      if (parseParaguayDate(pyDate)) {
        return `${pyDate} 09:00`;
      }
    }
    const pyDateOnly = /^(\d{2}\/\d{2}\/\d{4})$/.exec(clean);
    if (pyDateOnly && parseParaguayDate(pyDateOnly[1])) {
      return `${pyDateOnly[1]} 09:00`;
    }
    return isoToParaguayDateTime(clean);
  }

  function normalizeAiTime24(raw) {
    const clean = String(raw || "").trim();
    if (!clean) return "";
    return isoToTime24(clean);
  }

  function applyAiSuggestionsToFormValues(currentValues, suggestions) {
    const cur = currentValues || {};
    const sug = suggestions && typeof suggestions === "object" ? suggestions : {};
    const next = {
      ...cur,
      targetGroups: Array.isArray(cur.targetGroups) ? cur.targetGroups.slice() : [],
      notifyGroups: Array.isArray(cur.notifyGroups) ? cur.notifyGroups.slice() : [],
      eventNotifyGroups: Array.isArray(cur.eventNotifyGroups) ? cur.eventNotifyGroups.slice() : [],
      reminders: Array.isArray(cur.reminders) ? cur.reminders.slice() : [30],
    };

    if (!String(next.title || "").trim() && typeof sug.title === "string" && sug.title.trim()) {
      next.title = sug.title.trim().slice(0, LIMITS.title);
    }
    if (!String(next.caption || "").trim() && typeof sug.caption === "string" && sug.caption.trim()) {
      next.caption = sug.caption.trim().slice(0, LIMITS.teaser);
    }
    if (!String(next.content || "").trim() && typeof sug.content === "string" && sug.content.trim()) {
      next.content = sug.content.trim().slice(0, LIMITS.content);
    }
    if (
      !String(next.category || "").trim() &&
      typeof sug.category === "string" &&
      CATEGORIES.some((c) => c.value === sug.category.trim())
    ) {
      next.category = sug.category.trim();
    }
    const rawLinkLabel = sug.link_label !== undefined ? sug.link_label : sug.linkLabel;
    if (!String(next.linkLabel || "").trim() && typeof rawLinkLabel === "string" && rawLinkLabel.trim()) {
      next.linkLabel = rawLinkLabel.trim().slice(0, LIMITS.linkLabel);
    }
    const rawLinkUrl = sug.link_url !== undefined ? sug.link_url : sug.linkUrl;
    if (!String(next.linkUrl || "").trim() && typeof rawLinkUrl === "string" && rawLinkUrl.trim()) {
      next.linkUrl = rawLinkUrl.trim().slice(0, LIMITS.linkUrl);
    }
    if (!String(next.location || "").trim() && typeof sug.location === "string" && sug.location.trim()) {
      next.location = sug.location.trim().slice(0, LIMITS.location);
    }

    const rawStart = sug.event_start !== undefined ? sug.event_start : sug.eventStart;
    if (!String(next.eventStart || "").trim() && typeof rawStart === "string" && rawStart.trim()) {
      const formattedStart = normalizeAiDatetimeLocal(rawStart);
      if (formattedStart) next.eventStart = formattedStart;
    }

    const rawEnd = sug.event_end !== undefined ? sug.event_end : sug.eventEnd;
    if (!String(next.eventEnd || "").trim() && typeof rawEnd === "string" && rawEnd.trim()) {
      const formattedEnd = normalizeAiTime24(rawEnd);
      if (formattedEnd) next.eventEnd = formattedEnd;
    }

    const currentGroups = cleanGroups(next.targetGroups);
    const suggestedGroups = cleanGroups(sug.target_groups !== undefined ? sug.target_groups : sug.targetGroups);
    if (currentGroups.length === 0 && suggestedGroups.length > 0) {
      next.targetGroups = suggestedGroups;
    }

    const postType = String(next.postType || POST_TYPE_NORMAL).toUpperCase();
    if (postType !== POST_TYPE_URGENT && !next.isEvent) {
      const eventInferred =
        sug.is_event === true ||
        sug.isEvent === true ||
        Boolean(next.eventStart && !String(cur.eventStart || "").trim()) ||
        Boolean(next.location && !String(cur.location || "").trim());
      if (eventInferred) {
        next.isEvent = true;
      }
    }

    if (!next.hasRegistration && (sug.has_registration === true || sug.hasRegistration === true)) {
      next.hasRegistration = true;
    }

    return next;
  }

  function renderPublicationRows(items, options) {
    const opts = options || {};
    if (!items || items.length === 0) {
      return `<tr><td colspan="5" class="ed-empty">No hay publicaciones para mostrar.</td></tr>`;
    }
    return items
      .map((item) => {
        const img = safeUrl(item.media_url || item.image_url);
        const thumb = img
          ? `<a href="${escapeHtml(img)}" target="_blank" rel="noopener noreferrer" class="ed-thumb-link" title="Abrir original"><img src="${escapeHtml(img)}" alt="" class="ed-thumb" loading="lazy"></a>`
          : `<div class="ed-thumb-placeholder" aria-hidden="true">UPA</div>`;

        const sectionTags = [];
        if (item.is_news) sectionTags.push(`<span class="ed-badge ed-badge-info">Noticias</span>`);
        if (item.is_event) sectionTags.push(`<span class="ed-badge ed-badge-ok">Eventos</span>`);

        const postType = String(item.post_type || "MANUAL").toUpperCase();
        const typeBadge =
          postType === POST_TYPE_URGENT
            ? `<span class="ed-badge ed-badge-urgent">Aviso urgente</span>`
            : postType === POST_TYPE_INSTAGRAM
              ? `<span class="ed-badge ed-badge-social">Instagram</span>`
              : `<span class="ed-badge ed-badge-neutral">Interna</span>`;

        const views = Number(item.views_count || 0);
        const attending = Number(item.attending_count || 0);
        const declined = Number(item.declined_count || 0);
        const showRsvp = Boolean(item.has_registration) || attending > 0 || declined > 0;
        const metricsHtml = `<div class="ed-metrics-inline">
          <span title="Estudiantes que abrieron la publicación">${escapeHtml(views)} vistas</span>
          ${
            showRsvp
              ? `<span class="ed-subtle">&bull; ${escapeHtml(attending)} inscritos / ${escapeHtml(declined)} bajas</span>`
              : ""
          }
        </div>`;

        const isEdited = item.is_edited !== undefined ? Boolean(item.is_edited) : postType !== POST_TYPE_INSTAGRAM;
        const isAiGenerated = Boolean(item.is_ai_generated || item.status === "ai");
        const editBadge = isAiGenerated
          ? isEdited
            ? `<span class="ed-badge ed-badge-ok">Editado</span> <span class="ed-badge ed-badge-ai" title="Evento extraído automáticamente con IA">IA</span>`
            : `<span class="ed-badge ed-badge-ai" title="Evento extraído automáticamente con IA">IA</span>`
          : isEdited
            ? `<span class="ed-badge ed-badge-ok">Editado</span>`
            : `<span class="ed-badge ed-badge-warn">Pendiente</span>`;

        const pubDate = formatDateTime(item.published_at || item.created_at, opts);
        const eventDate = item.is_event && item.event_start ? formatDateTime(item.event_start, opts) : "";
        const subtitle = item.summary || item.caption || "";

        return `<tr class="ed-clickable-row" data-pub-id="${escapeHtml(item.id)}" tabindex="0">
          <td class="ed-cell-title">
            ${thumb}
            <div class="min-w-0">
              <div class="ed-title truncate">${escapeHtml(item.title)}</div>
              <div class="ed-subtle truncate">${escapeHtml(subtitle)}</div>
              <div class="ed-subtle">${escapeHtml(pubDate)}${eventDate ? ` &bull; Evento: ${escapeHtml(eventDate)}` : ""}</div>
            </div>
          </td>
          <td><div class="flex flex-wrap gap-1">${sectionTags.join(" ")}</div></td>
          <td>${typeBadge}</td>
          <td>${metricsHtml}</td>
          <td>${editBadge}</td>
        </tr>`;
      })
      .join("");
  }

  function renderHistoryEntries(entries, options) {
    const opts = options || {};
    if (!Array.isArray(entries) || entries.length === 0) {
      return "";
    }
    const rows = entries.slice(0, 10).map((entry) => {
      const when = entry.created_at ? escapeHtml(formatDateTime(entry.created_at, opts)) : "&mdash;";
      const who = escapeHtml(entry.admin_name || entry.admin_email || "Admin");
      const verb = escapeHtml(entry.verb || entry.action || "actualizó");
      const target =
        opts.showTarget && entry.target_label ? ` <span class="font-medium">${escapeHtml(entry.target_label)}</span>` : "";
      const changes =
        Array.isArray(entry.changes) && entry.changes.length > 0
          ? ` (${escapeHtml(entry.changes.join(", "))})`
          : "";
      const detail = entry.detail ? ` <span class="ed-audit-detail">${escapeHtml(entry.detail)}</span>` : "";
      return `<tr class="ed-audit-row"><td class="ed-audit-time">${when}</td><td class="ed-audit-who">${who}</td><td class="ed-audit-action">${verb}${target}${changes}${detail}</td></tr>`;
    });
    return `<div class="ed-audit-trail"><div class="ed-audit-heading">Historial:</div><table class="ed-audit-table"><tbody>${rows.join("")}</tbody></table></div>`;
  }

  function renderParticipantsTable(response, options) {
    const opts = options || {};
    const regs = (response && response.registrations) || [];
    const declinedCount = response && response.declined_count ? Number(response.declined_count) : 0;
    const declinedHtml = declinedCount > 0 ? ` <span class="ed-badge ed-badge-neutral">${escapeHtml(declinedCount)} bajas</span>` : "";
    const header = `<div class="ed-participants-head"><strong>${escapeHtml(
      response ? response.title : ""
    )}</strong><div><span class="ed-badge ed-badge-ok">${escapeHtml(
      response ? response.attending_count : 0
    )} inscritos</span>${declinedHtml}</div></div>`;
    if (regs.length === 0) {
      return `${header}<p class="ed-empty">Todavía no hay participantes inscritos.</p>`;
    }
    const rows = regs
      .map((r) => {
        const attending = r.status === "attending";
        const label = attending ? "Asiste" : r.status === "declined" ? "Baja" : r.status;
        return `<tr>
          <td>${escapeHtml(r.full_name)}</td>
          <td class="ed-mono">${escapeHtml(r.email)}</td>
          <td>${
            attending
              ? `<span class="ed-badge ed-badge-ok">${escapeHtml(label)}</span>`
              : `<span class="ed-badge ed-badge-neutral">${escapeHtml(label)}</span>`
          }</td>
          <td>${escapeHtml(formatDateTime(r.registered_at, opts))}</td>
        </tr>`;
      })
      .join("");
    return `${header}<table class="ed-table"><thead><tr><th>Nombre</th><th>Correo</th><th>Estado</th><th>Inscripción</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

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
        body = options.formData;
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
      const entries = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "");
      return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
    };

    return {
      request,
      getMe: () => request("GET", "/api/auth/me"),

      // Publicaciones unificadas
      listPublications: (params) => request("GET", `/api/publications${qs({ limit: 150, ...params })}`),
      getPublication: (id) => request("GET", `/api/publications/${encodeURIComponent(id)}`),
      createPublication: (payload) => request("POST", "/api/publications", { json: payload }),
      updatePublication: (id, payload) => request("PUT", `/api/publications/${encodeURIComponent(id)}`, { json: payload }),
      deletePublication: (id) => request("DELETE", `/api/publications/${encodeURIComponent(id)}`),
      getPublicationRegistrations: (id) => request("GET", `/api/publications/${encodeURIComponent(id)}/registrations`),
      submitPublicationRsvp: (id, status) =>
        request("POST", `/api/publications/${encodeURIComponent(id)}/rsvp`, { json: { status } }),
      markPublicationViewed: (id) => request("POST", `/api/publications/${encodeURIComponent(id)}/view`),

      // Grupos
      listGroups: () => request("GET", "/api/groups"),
      listWorkspaceGroups: () => request("GET", "/api/groups/google-workspace"),
      createGroup: (payload) => request("POST", "/api/groups", { json: payload }),
      updateGroup: (id, payload) => request("PUT", `/api/groups/${encodeURIComponent(id)}`, { json: payload }),
      deleteGroup: (id) => request("DELETE", `/api/groups/${encodeURIComponent(id)}`),

      // Roles
      listRoles: () => request("GET", "/api/roles"),
      assignRole: (payload) => request("POST", "/api/roles", { json: payload }),
      updateRole: (email, payload) => request("PUT", `/api/roles/${encodeURIComponent(email)}`, { json: payload }),
      revokeRole: (email) => request("DELETE", `/api/roles/${encodeURIComponent(email)}`),

      // Historial de auditoria (solo administradores)
      getHistory: (entityType, key) =>
        key !== undefined && key !== null && key !== ""
          ? request("GET", `/api/history/${encodeURIComponent(entityType)}/${encodeURIComponent(key)}`)
          : request("GET", `/api/history/${encodeURIComponent(entityType)}`),

      // Control de IA (Google Gemini)
      getAiConfig: () => request("GET", "/api/ai/config"),
      saveAiConfig: (apiKeyOrPayload, systemPrompt) => {
        const json =
          apiKeyOrPayload && typeof apiKeyOrPayload === "object"
            ? apiKeyOrPayload
            : systemPrompt !== undefined
              ? { api_key: apiKeyOrPayload, system_prompt: systemPrompt }
              : { api_key: apiKeyOrPayload };
        return request("POST", "/api/ai/config", { json });
      },
      testAiConnection: (apiKey) =>
        request("POST", "/api/ai/test-connection", apiKey ? { json: { api_key: apiKey } } : {}),
      autocompletePublicationAi(payload, file) {
        if (file) {
          const formData = new FormData();
          formData.append("data", JSON.stringify(payload || {}));
          formData.append("file", file, file.name || "upload");
          return request("POST", "/api/publications/autocomplete-ai", { formData, timeoutMs: uploadTimeoutMs });
        }
        return request("POST", "/api/publications/autocomplete-ai", {
          json: payload || {},
          timeoutMs: uploadTimeoutMs,
        });
      },

      syncInstagram: () => request("POST", "/api/publications/sync-instagram", { timeoutMs: uploadTimeoutMs }),

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
    PERMISSION_KEYS,
    CATEGORIES,
    TARGET_GROUPS,
    REMINDER_UNITS,
    POST_TYPE_NORMAL,
    POST_TYPE_URGENT,
    POST_TYPE_INSTAGRAM,
    TEXTS,
    ApiError,
    describeError,
    extractDetailMessage,
    validateUploadFile,
    escapeHtml,
    safeUrl,
    isImageUrl,
    isVideoUrl,
    mediaTypeForUrl,
    extractInstagramTeaser,
    reminderToParts,
    partsToReminderMinutes,
    isValidTime24,
    parseParaguayDate,
    localDateTimeToIso,
    isoToLocalParts,
    isoToParaguayDateTime,
    isoToTime24,
    isoToDatetimeLocal,
    datetimeLocalToIso,
    resolveEventEndIso,
    maskDateTimeInput,
    maskTime24Input,
    formatDateTime,
    categoryLabel,
    cleanGroups,
    cleanReminders,
    validatePublicationValues,
    buildPublicationPayload,
    publicationToFormValues,
    normalizeAiDatetimeLocal,
    normalizeAiTime24,
    applyAiSuggestionsToFormValues,
    renderPublicationRows,
    renderHistoryEntries,
    renderParticipantsTable,
    describeSyncResult,
    createClient,
  };
});
