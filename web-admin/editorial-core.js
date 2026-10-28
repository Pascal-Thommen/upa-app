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
    errEndBeforeStart: "La hora de finalización no puede ser anterior al inicio.",
    errGroupRequired: "Seleccione al menos un grupo destinatario.",
    errCategoryInvalid: "Categoría no válida.",
    errExpiresRequired: "Indique la fecha y hora de vigencia para fijar la publicación.",
    errExpiresInvalid: "La fecha de vigencia no es válida.",
    errPublishedInvalid: "La fecha programada de publicación no es válida.",
    errPublishedPast: "La fecha programada de publicación no puede estar en el pasado.",
    errSectionRequired: "Active al menos una sección: Noticia o Evento.",
    errUrgentNoEvent: "Los avisos urgentes no admiten sección de Evento.",
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
    if (status >= 500) return new ApiError("server", TEXTS.errServer, status, detail);
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

  function localDateTimeToIso(date, time) {
    if (!date || !time) return null;
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
    const timeMatch = /^(\d{2}):(\d{2})$/.exec(time);
    if (!match || !timeMatch) return null;
    const [year, month, day, hour, minute] = [match[1], match[2], match[3], timeMatch[1], timeMatch[2]].map(Number);
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

  /** Convierte un ISO-8601 a valor `YYYY-MM-DDTHH:MM` para inputs `datetime-local`. */
  function isoToDatetimeLocal(iso) {
    const parts = isoToLocalParts(iso);
    return parts.date && parts.time ? `${parts.date}T${parts.time}` : "";
  }

  /** Convierte un valor `datetime-local` (`YYYY-MM-DDTHH:MM`) a ISO-8601 UTC. */
  function datetimeLocalToIso(localVal) {
    const clean = String(localVal || "").trim();
    if (!clean) return null;
    const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(clean);
    if (!match) return null;
    return localDateTimeToIso(match[1], match[2]);
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
      if (String(v.detailText || "").length > LIMITS.detailText) {
        errors.detailText = `El texto adicional no puede superar ${LIMITS.detailText} caracteres.`;
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
      const startIso = datetimeLocalToIso(v.eventStart);
      if (!startIso) {
        errors.eventStart = TEXTS.errEventStartRequired;
      } else if (v.eventEnd) {
        const endIso = datetimeLocalToIso(v.eventEnd);
        if (!endIso || new Date(endIso) < new Date(startIso)) {
          errors.eventEnd = TEXTS.errEndBeforeStart;
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
      detail_text: isNews ? String(v.detailText || "").trim() : "",
      category: isNews ? String(v.category || "").trim() : "",
      is_pinned: isNews ? Boolean(v.pinned) : false,
      expires_at: isNews && v.expiresAt ? datetimeLocalToIso(v.expiresAt) : null,
      media_url: imageUrl,
      media_type: mediaTypeForUrl(imageUrl),
      link_label: isNews ? String(v.linkLabel || "").trim() : "",
      link_url: isNews ? String(v.linkUrl || "").trim() : "",
      is_event: isEvent,
      event_start: isEvent ? datetimeLocalToIso(v.eventStart) : null,
      event_end: isEvent && v.eventEnd ? datetimeLocalToIso(v.eventEnd) : null,
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
      detailText: p.detail_text || "",
      category: p.category || "",
      pinned: Boolean(p.is_pinned),
      expiresAt: isoToDatetimeLocal(p.expires_at),
      imageUrl: p.media_url || p.image_url || "",
      permalink: p.permalink || "",
      linkLabel,
      linkUrl,
      isEvent,
      eventStart: isoToDatetimeLocal(p.event_start),
      eventEnd: isoToDatetimeLocal(p.event_end),
      location: p.location || "",
      eventNotifyGroups,
      reminders,
      viewsCount: Number(p.views_count || 0),
      attendingCount: Number(p.attending_count || 0),
      declinedCount: Number(p.declined_count || 0),
      isEdited: p.is_edited !== undefined ? Boolean(p.is_edited) : postType !== POST_TYPE_INSTAGRAM,
    };
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
          ? `<img src="${escapeHtml(img)}" alt="" class="ed-thumb" loading="lazy">`
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
        const editBadge = isEdited
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
      return `<tr class="ed-audit-row"><td class="ed-audit-time">${when}</td><td class="ed-audit-who">${who}</td><td class="ed-audit-action">${verb}${target}${changes}</td></tr>`;
    });
    return `<div class="ed-audit-trail"><div class="ed-audit-heading">Historial:</div><table class="ed-audit-table"><tbody>${rows.join("")}</tbody></table></div>`;
  }

  // ---------------------------------------------------------------------------
  // Compatibilidad con formularios individuales (/api/news y /api/events)
  // ---------------------------------------------------------------------------

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

      // Compatibilidad con endpoints de noticias y eventos
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
    localDateTimeToIso,
    isoToLocalParts,
    isoToDatetimeLocal,
    datetimeLocalToIso,
    formatDateTime,
    categoryLabel,
    cleanGroups,
    cleanReminders,
    validatePublicationValues,
    buildPublicationPayload,
    publicationToFormValues,
    renderPublicationRows,
    renderHistoryEntries,
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
