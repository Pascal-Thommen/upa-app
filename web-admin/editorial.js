/**
 * Controlador de Publicaciones Unificadas (web-admin).
 *
 * Conecta la vista de lista y el editor modular de `index.html` con el cliente REST real de
 * `editorial-core.js` (`/api/publications`, `/api/media/upload`, `/api/news/sync-instagram`,
 * `/api/history/post`). Sin datos simulados: toda lectura y escritura ocurre contra PostgreSQL.
 */
(function () {
  "use strict";

  const Core = window.UpaEditorial;
  const MODE_STORAGE_KEY = "upa_view_mode";
  const NOTICE_AUTOHIDE_MS = 7000;

  const $ = (id) => document.getElementById(id);

  const state = {
    config: { getToken: () => null, onUnauthorized: () => {} },
    client: null,
    ready: false,
    allowed: false,
    isAdmin: false,
    mode: "editorial",
    filter: "all",
    publications: [],
    publicationsLoaded: false,
    groupCatalog: [],
    editingItem: null,
    reminders: [30],
    participantsPubId: null,
    dropzones: {},
    noticeTimer: null,
    aiConfigured: false,
  };

  function getClient() {
    if (!state.client) {
      state.client = Core.createClient({
        baseUrl: state.config.baseUrl,
        timeoutMs: state.config.timeoutMs,
        uploadTimeoutMs: state.config.uploadTimeoutMs,
        getToken: () => state.config.getToken(),
        onUnauthorized: (err) => state.config.onUnauthorized(err),
      });
    }
    return state.client;
  }

  // ---------------------------------------------------------------------------
  // Avisos y errores de validación
  // ---------------------------------------------------------------------------

  function showNotice(type, message) {
    const el = $("ed-notice");
    if (!el) return;
    clearTimeout(state.noticeTimer);
    el.textContent = message;
    el.className = `ed-notice is-${type}`;
    if (type === "success" || type === "info") {
      state.noticeTimer = setTimeout(hideNotice, NOTICE_AUTOHIDE_MS);
    }
  }

  function hideNotice() {
    const el = $("ed-notice");
    if (el) el.className = "hidden ed-notice";
  }

  function showFieldErrors(prefix, errors) {
    document.querySelectorAll(`[data-error-for^="${prefix}-"]`).forEach((el) => {
      const field = el.getAttribute("data-error-for").slice(prefix.length + 1);
      const message = errors[field] || "";
      el.textContent = message;
      const control = el.previousElementSibling;
      if (control && control.classList && control.classList.contains("ed-input")) {
        control.classList.toggle("has-error", Boolean(message));
      }
    });
  }

  function setBusy(button, busy, busyLabel) {
    if (!button) return;
    if (busy) {
      button.dataset.label = button.textContent;
      button.textContent = busyLabel;
      button.disabled = true;
    } else {
      if (button.dataset.label) button.textContent = button.dataset.label;
      button.disabled = false;
    }
  }

  // ---------------------------------------------------------------------------
  // Catálogo dinámico de grupos
  // ---------------------------------------------------------------------------

  let groupsSynced = false;
  let groupsSyncPromise = null;

  function refreshGroupsCatalog(groups) {
    if (!Array.isArray(groups)) return;
    const catalog = [];
    const seen = new Set();
    groups.forEach((g) => {
      if (!g || !g.id) return;
      const val = String(g.id).trim();
      const key = val.toLowerCase();
      if (val && !seen.has(key)) {
        seen.add(key);
        catalog.push({ value: val, label: String(g.name || val).trim() });
      }
    });
    catalog.sort((a, b) => String(a.label || "").localeCompare(String(b.label || ""), "es", { sensitivity: "base" }));
    state.groupCatalog = catalog;
    groupsSynced = true;
  }

  async function syncAvailableGroups(force) {
    if (groupsSynced && !force) return state.groupCatalog;
    if (groupsSyncPromise && !force) return groupsSyncPromise;
    groupsSyncPromise = (async () => {
      try {
        const groups = await getClient().listGroups();
        refreshGroupsCatalog(groups);
      } catch (_) {
        /* mantiene catálogo actual si falla la red */
      } finally {
        groupsSyncPromise = null;
      }
      return state.groupCatalog;
    })();
    return groupsSyncPromise;
  }

  function resolveGroupOptions() {
    return state.groupCatalog.slice();
  }

  function normalizeSelectedTargetGroups(selected, options) {
    const list = Array.isArray(selected) ? selected : [];
    const opts = Array.isArray(options) ? options : resolveGroupOptions();
    const allIds = opts.map((g) => g.value);
    if (list.length === 0) return [];
    const upperSet = new Set(list.map((v) => String(v || "").trim().toUpperCase()));
    if (upperSet.has("ALL")) {
      return allIds;
    }
    const lowerMap = new Map(opts.map((g) => [g.value.toLowerCase(), g.value]));
    const matched = [];
    list.forEach((v) => {
      const found = lowerMap.get(String(v || "").trim().toLowerCase());
      if (found && !matched.includes(found)) matched.push(found);
    });
    return matched;
  }

  function renderTargetGroupCheckboxes(selected) {
    const container = $("ed-pub-target-groups");
    if (!container) return;
    const options = resolveGroupOptions();
    if (options.length === 0) {
      container.innerHTML = `<span class="ed-subtle">No hay grupos registrados en el módulo Grupos.</span>`;
      return;
    }
    const chosen = normalizeSelectedTargetGroups(selected, options);
    container.innerHTML = options
      .map(
        (g) =>
          `<label class="ed-check"><input type="checkbox" value="${Core.escapeHtml(g.value)}"${
            chosen.includes(g.value) ? " checked" : ""
          }> <span>${Core.escapeHtml(g.label)}</span></label>`
      )
      .join("");
    container.querySelectorAll("input[type=checkbox]").forEach((cb) => {
      cb.addEventListener("change", () => {
        const currentTargets = readCheckedValues("ed-pub-target-groups");
        const currentNotify = readCheckedValues("ed-pub-notify-groups").filter((g) => currentTargets.includes(g));
        const prevEventNotify = readCheckedValues("ed-pub-event-notify-groups").filter((g) =>
          currentTargets.includes(g)
        );
        if (cb.checked && !prevEventNotify.includes(cb.value)) {
          prevEventNotify.push(cb.value);
        }
        renderSubsetGroupCheckboxes("ed-pub-notify-groups", currentTargets, currentNotify);
        renderSubsetGroupCheckboxes("ed-pub-event-notify-groups", currentTargets, prevEventNotify);
      });
    });
  }

  function renderSubsetGroupCheckboxes(containerId, targetGroups, selectedSubset) {
    const container = $(containerId);
    if (!container) return;
    const options = resolveGroupOptions();
    const targets = normalizeSelectedTargetGroups(targetGroups, options);
    const chosen = normalizeSelectedTargetGroups(selectedSubset, options).filter((g) => targets.includes(g));
    if (targets.length === 0) {
      container.innerHTML = `<span class="ed-subtle">Seleccione primero al menos un grupo destinatario arriba.</span>`;
      return;
    }
    const subsetOptions = targets.map((val) => options.find((c) => c.value === val) || { value: val, label: val });
    container.innerHTML = subsetOptions
      .map(
        (g) =>
          `<label class="ed-check"><input type="checkbox" value="${Core.escapeHtml(g.value)}"${
            chosen.includes(g.value) ? " checked" : ""
          }> <span>${Core.escapeHtml(g.label)}</span></label>`
      )
      .join("");
  }

  function readCheckedValues(containerId) {
    const container = $(containerId);
    if (!container) return [];
    return Array.from(container.querySelectorAll("input[type=checkbox]:checked")).map((el) => el.value);
  }

  // ---------------------------------------------------------------------------
  // Recordatorios dinámicos del evento (valor numérico + unidad de tiempo)
  // ---------------------------------------------------------------------------

  function syncRemindersFromDom() {
    const container = $("ed-reminders-list");
    if (!container) return;
    const rows = Array.from(container.querySelectorAll("[data-reminder-row]"));
    if (rows.length > 0) {
      state.reminders = rows
        .map((row) => {
          const valInput = row.querySelector("input[data-reminder-value]");
          const unitSelect = row.querySelector("select[data-reminder-unit]");
          const val = valInput ? valInput.value : 30;
          const unit = unitSelect ? unitSelect.value : "minutes";
          return Core.partsToReminderMinutes(val, unit);
        })
        .filter((m) => m !== null);
    }
  }

  function renderRemindersList(reminders) {
    state.reminders = Array.isArray(reminders) ? reminders.slice() : [];
    const container = $("ed-reminders-list");
    if (!container) return;
    if (state.reminders.length === 0) {
      container.innerHTML = `<span class="ed-subtle">Sin recordatorios activos.</span>`;
      return;
    }
    const units = Core.REMINDER_UNITS || [
      { value: "minutes", label: "minutos" },
      { value: "hours", label: "horas" },
      { value: "days", label: "días" },
    ];
    container.innerHTML = state.reminders
      .map((mins, idx) => {
        const parts = Core.reminderToParts ? Core.reminderToParts(mins) : { value: mins, unit: "minutes" };
        const unitOptions = units
          .map(
            (u) =>
              `<option value="${Core.escapeHtml(u.value)}"${
                u.value === parts.unit ? " selected" : ""
              }>${Core.escapeHtml(u.label)}</option>`
          )
          .join("");
        return `
        <div class="ed-reminder-row" data-reminder-row="${idx}">
          <input type="number" min="1" max="43200" step="1" data-reminder-value="${idx}" value="${Core.escapeHtml(
            parts.value
          )}" aria-label="Cantidad de tiempo antes del evento">
          <select data-reminder-unit="${idx}" class="ed-input py-1 px-2 text-xs w-auto" aria-label="Unidad de tiempo del recordatorio">
            ${unitOptions}
          </select>
          <span>antes</span>
          <button type="button" class="text-slate-400 hover:text-red-600 font-bold px-1" data-remove-reminder="${idx}" title="Quitar recordatorio">&times;</button>
        </div>`;
      })
      .join("");

    container.querySelectorAll("[data-reminder-row]").forEach((row) => {
      const idx = Number(row.getAttribute("data-reminder-row"));
      const valInput = row.querySelector("input[data-reminder-value]");
      const unitSelect = row.querySelector("select[data-reminder-unit]");
      const updateIdx = () => {
        if (Number.isNaN(idx)) return;
        const mins = Core.partsToReminderMinutes(
          valInput ? valInput.value : 30,
          unitSelect ? unitSelect.value : "minutes"
        );
        if (mins !== null) state.reminders[idx] = mins;
      };
      if (valInput) valInput.addEventListener("input", updateIdx);
      if (unitSelect) unitSelect.addEventListener("change", updateIdx);
    });

    container.querySelectorAll("button[data-remove-reminder]").forEach((btn) => {
      btn.addEventListener("click", () => {
        syncRemindersFromDom();
        const idx = Number(btn.getAttribute("data-remove-reminder"));
        state.reminders.splice(idx, 1);
        renderRemindersList(state.reminders);
      });
    });
  }

  function addReminderRow() {
    syncRemindersFromDom();
    const clean = Core.cleanReminders(state.reminders);
    let nextVal = 30;
    if (clean.includes(30) && !clean.includes(1440)) nextVal = 1440;
    else if (clean.includes(30) && !clean.includes(60)) nextVal = 60;
    else if (clean.length > 0) nextVal = clean[clean.length - 1] + 60;
    state.reminders.push(nextVal);
    renderRemindersList(state.reminders);
  }

  // ---------------------------------------------------------------------------
  // Zona de carga de archivos
  // ---------------------------------------------------------------------------

  function bindDropzone(zone) {
    const input = zone.querySelector("[data-dz-input]");
    const urlField = zone.querySelector("[data-dz-url]");
    const status = zone.querySelector("[data-dz-status]");
    const preview = zone.querySelector("[data-dz-preview]");
    const pick = zone.querySelector("[data-dz-pick]");

    const dz = {
      uploading: false,
      readOnly: false,
      lastFile: null,
      getUrl: () => (urlField ? urlField.value : ""),
      getFile: () => dz.lastFile,
      setStatus(type, message) {
        if (!status) return;
        status.textContent = message || "";
        status.className = `ed-dz-status${type ? ` is-${type}` : ""}`;
      },
      setReadOnly(locked) {
        dz.readOnly = Boolean(locked);
        if (input) input.disabled = dz.readOnly;
        if (pick) pick.disabled = dz.readOnly;
        zone.classList.toggle("opacity-75", dz.readOnly);
        if (preview) {
          const removeBtn = preview.querySelector("[data-dz-remove]");
          if (removeBtn) removeBtn.classList.toggle("hidden", dz.readOnly);
        }
      },
      setUrl(url, label) {
        if (urlField) urlField.value = url || "";
        if (!preview) return;
        if (!url) {
          preview.classList.add("hidden");
          preview.innerHTML = "";
          return;
        }
        const safe = Core.safeUrl(url);
        let media = "";
        if (Core.isVideoUrl && Core.isVideoUrl(safe)) {
          media = `<video src="${Core.escapeHtml(safe)}" controls class="max-h-56 w-full rounded-lg"></video>`;
        } else if (Core.isImageUrl(safe)) {
          media = `<img src="${Core.escapeHtml(safe)}" alt="Vista previa">`;
        } else {
          media = `<a class="ed-link" href="${Core.escapeHtml(safe)}" target="_blank" rel="noopener noreferrer">${Core.escapeHtml(
            label || "Documento adjunto"
          )}</a>`;
        }
        const hideRemove = dz.readOnly ? " hidden" : "";
        preview.innerHTML = `${media}<button type="button" class="ed-btn ed-btn-secondary ed-btn-sm${hideRemove}" data-dz-remove>Quitar</button>`;
        preview.classList.remove("hidden");
        preview.querySelector("[data-dz-remove]").addEventListener("click", () => {
          if (dz.readOnly) return;
          dz.lastFile = null;
          dz.setUrl("");
          dz.setStatus("", "");
        });
      },
      reset() {
        dz.lastFile = null;
        dz.setUrl("");
        dz.setStatus("", "");
      },
    };

    async function handleFile(file) {
      if (dz.uploading || dz.readOnly) return;
      const check = Core.validateUploadFile(file);
      if (!check.ok) {
        dz.setStatus("error", check.message);
        return;
      }
      dz.uploading = true;
      dz.lastFile = file;
      zone.classList.add("is-uploading");
      dz.setStatus("", `Subiendo ${file.name}...`);
      try {
        const result = await getClient().uploadMedia(file);
        dz.setUrl(result.url, file.name);
        dz.setStatus("ok", `Archivo subido: ${file.name}`);
      } catch (error) {
        dz.setStatus("error", Core.describeError(error));
      } finally {
        dz.uploading = false;
        zone.classList.remove("is-uploading");
      }
    }

    if (pick && input) pick.addEventListener("click", () => input.click());
    if (input) {
      input.addEventListener("change", () => {
        const file = input.files && input.files[0];
        input.value = "";
        if (file) handleFile(file);
      });
    }
    ["dragenter", "dragover"].forEach((evt) =>
      zone.addEventListener(evt, (e) => {
        e.preventDefault();
        zone.classList.add("is-dragover");
      })
    );
    ["dragleave", "drop"].forEach((evt) =>
      zone.addEventListener(evt, (e) => {
        e.preventDefault();
        zone.classList.remove("is-dragover");
      })
    );
    zone.addEventListener("drop", (e) => {
      const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) handleFile(file);
    });

    state.dropzones[zone.getAttribute("data-dropzone")] = dz;
  }

  // ---------------------------------------------------------------------------
  // Vista previa directa del enlace de acción y reglas de fecha / secciones
  // ---------------------------------------------------------------------------

  function resolveTestableLinkUrl(rawVal) {
    const clean = String(rawVal || "").trim();
    if (!clean) return "";
    const direct = Core.safeUrl(clean);
    if (direct) return direct;
    if (/^[a-z0-9.-]+\.[a-z]{2,}(\/.*)?$/i.test(clean)) {
      return `https://${clean}`;
    }
    return "";
  }

  function syncLinkPreview() {
    const linkInput = $("ed-pub-link-url");
    const previewEl = $("ed-pub-link-preview");
    if (!previewEl) return;
    const targetUrl = resolveTestableLinkUrl(linkInput ? linkInput.value : "");
    if (targetUrl) {
      previewEl.setAttribute("href", targetUrl);
      previewEl.setAttribute("target", "_blank");
      previewEl.setAttribute("rel", "noopener noreferrer");
      previewEl.setAttribute("aria-disabled", "false");
      previewEl.classList.remove("opacity-50", "pointer-events-none");
    } else {
      previewEl.setAttribute("href", "#");
      previewEl.setAttribute("aria-disabled", "true");
      previewEl.classList.add("opacity-50", "pointer-events-none");
    }
  }

  function isEditingAlreadyPublished() {
    if (!state.editingItem || !state.editingItem.id) return false;
    const rawPub = state.editingItem.published_at || state.editingItem.created_at;
    if (!rawPub) return true;
    const ms = new Date(rawPub).getTime();
    return Number.isNaN(ms) || ms <= Date.now() + 60000;
  }

  function applyTypeAndSectionRules() {
    const scheduledCb = $("ed-pub-scheduled");
    const publishedInput = $("ed-pub-published-at");
    const publishedHint = $("ed-pub-published-hint");
    const isNewsCb = $("ed-pub-is-news");
    const isEventCb = $("ed-pub-is-event");
    const pinnedCb = $("ed-pub-pinned");
    const expiresWrap = $("ed-pub-expires-wrap");
    const expiresInput = $("ed-pub-expires");
    const captionInput = $("ed-pub-caption");
    const contentInput = $("ed-pub-content");
    const linkLabelInput = $("ed-pub-link-label");
    const linkUrlInput = $("ed-pub-link-url");
    const newsLockHint = $("ed-news-lock-hint");
    const eventLockHint = $("ed-event-lock-hint");
    const newsNotifyHint = $("ed-news-notify-hint");
    const newsBox = $("ed-section-news");
    const eventBox = $("ed-section-event");
    const newsFields = $("ed-news-fields");
    const eventFields = $("ed-event-fields");

    if (!isNewsCb || !isEventCb) return;

    const postType =
      state.editingItem && state.editingItem.post_type
        ? String(state.editingItem.post_type).toUpperCase()
        : Core.POST_TYPE_NORMAL;
    const isInstagramItem = postType === Core.POST_TYPE_INSTAGRAM;
    const alreadyPublished = isEditingAlreadyPublished();

    // Reglas de fecha de publicación programada (ed-pub-scheduled + ed-pub-published-at)
    if (isInstagramItem) {
      if (scheduledCb) {
        scheduledCb.checked = false;
        scheduledCb.disabled = true;
      }
      if (publishedInput) {
        publishedInput.classList.add("hidden");
        publishedInput.disabled = true;
        publishedInput.readOnly = true;
      }
      if (publishedHint) {
        const origDate = Core.formatDateTime(state.editingItem.published_at || state.editingItem.created_at);
        publishedHint.textContent = origDate
          ? `Fecha original de Instagram: ${origDate} (bloqueada)`
          : "Fecha original de Instagram (bloqueada)";
      }
    } else if (alreadyPublished) {
      if (scheduledCb) {
        scheduledCb.checked = false;
        scheduledCb.disabled = true;
      }
      if (publishedInput) {
        publishedInput.classList.add("hidden");
        publishedInput.disabled = true;
        publishedInput.readOnly = true;
      }
      if (publishedHint) {
        const origDate = Core.formatDateTime(state.editingItem.published_at || state.editingItem.created_at);
        publishedHint.textContent = origDate
          ? `Publicada: ${origDate} (ya publicada)`
          : "Publicación activa (ya publicada)";
      }
    } else {
      if (scheduledCb) scheduledCb.disabled = false;
      const scheduled = Boolean(scheduledCb && scheduledCb.checked);
      if (publishedInput) {
        publishedInput.disabled = !scheduled;
        publishedInput.readOnly = !scheduled;
        publishedInput.classList.toggle("hidden", !scheduled);
      }
      if (publishedHint) {
        if (scheduled) {
          publishedHint.textContent = "La publicación será visible a partir de esa fecha y hora (DD/MM/YYYY HH:mm).";
        } else {
          publishedHint.textContent = "Se registrará la fecha exacta al guardar.";
        }
      }
    }

    // Reglas de fijar arriba (ed-pub-pinned) y fecha de vigencia obligatoria (ed-pub-expires)
    const isPinned = Boolean(pinnedCb && pinnedCb.checked);
    if (expiresWrap) expiresWrap.classList.toggle("hidden", !isPinned);
    if (expiresInput) expiresInput.required = isPinned;

    // Barrera de protección de solo lectura para campos sincronizados de Instagram
    [captionInput, contentInput, linkLabelInput, linkUrlInput].forEach((field) => {
      if (!field) return;
      field.readOnly = isInstagramItem;
      field.disabled = isInstagramItem;
    });
    if (state.dropzones.pub && typeof state.dropzones.pub.setReadOnly === "function") {
      state.dropzones.pub.setReadOnly(isInstagramItem);
    }
    if (isInstagramItem && state.editingItem) {
      if (captionInput && Core.extractInstagramTeaser) {
        captionInput.value = Core.extractInstagramTeaser(state.editingItem.content || state.editingItem.caption);
      }
      if (linkUrlInput) {
        linkUrlInput.value = state.editingItem.permalink || state.editingItem.link_url || "";
      }
    }

    // Reglas de sección Noticia vs Evento
    if (isInstagramItem) {
      isNewsCb.checked = true;
      isNewsCb.disabled = true;
      if (newsLockHint) newsLockHint.textContent = "Campos sincronizados de Instagram en modo lectura";
      if (newsNotifyHint) {
        newsNotifyHint.textContent = "Al guardar se enviará notificación a los grupos marcados.";
      }
      isEventCb.disabled = false;
      if (eventLockHint) eventLockHint.textContent = "";
    } else if (postType === Core.POST_TYPE_URGENT) {
      isNewsCb.checked = true;
      isNewsCb.disabled = true;
      if (newsLockHint) newsLockHint.textContent = "Obligatoria en avisos urgentes";
      if (newsNotifyHint) {
        newsNotifyHint.textContent = "El aviso urgente enviará notificación push al publicar.";
      }
      isEventCb.checked = false;
      isEventCb.disabled = true;
      if (eventLockHint) eventLockHint.textContent = "No disponible en avisos urgentes";
    } else {
      isNewsCb.disabled = false;
      if (newsLockHint) newsLockHint.textContent = "";
      if (newsNotifyHint) {
        newsNotifyHint.textContent = "Seleccione los grupos que recibirán notificación al publicar.";
      }
      isEventCb.disabled = false;
      if (eventLockHint) eventLockHint.textContent = "";
    }

    const showNews = isNewsCb.checked;
    const showEvent = isEventCb.checked;
    if (newsFields) newsFields.classList.toggle("hidden", !showNews);
    if (newsBox) newsBox.classList.toggle("is-open", showNews);
    if (eventFields) eventFields.classList.toggle("hidden", !showEvent);
    if (eventBox) eventBox.classList.toggle("is-open", showEvent);
    syncLinkPreview();
  }

  // ---------------------------------------------------------------------------
  // Lectura y llenado del formulario unificado
  // ---------------------------------------------------------------------------

  function readPublicationForm() {
    syncRemindersFromDom();
    const alreadyPublished = isEditingAlreadyPublished();
    const scheduled = !alreadyPublished && Boolean($("ed-pub-scheduled") && $("ed-pub-scheduled").checked);
    const postType =
      state.editingItem && state.editingItem.post_type
        ? String(state.editingItem.post_type).toUpperCase()
        : Core.POST_TYPE_NORMAL;
    return {
      title: $("ed-pub-title") ? $("ed-pub-title").value : "",
      postType,
      hasRegistration: Boolean($("ed-pub-rsvp") && $("ed-pub-rsvp").checked),
      targetGroups: readCheckedValues("ed-pub-target-groups"),
      scheduled,
      isPublished: alreadyPublished,
      publishMode: scheduled ? "scheduled" : alreadyPublished ? "published" : "on_save",
      publishedAt: $("ed-pub-published-at") ? $("ed-pub-published-at").value : "",
      isNews: Boolean($("ed-pub-is-news") && $("ed-pub-is-news").checked),
      notifyGroups: readCheckedValues("ed-pub-notify-groups"),
      caption: $("ed-pub-caption") ? $("ed-pub-caption").value : "",
      content: $("ed-pub-content") ? $("ed-pub-content").value : "",
      pinned: Boolean($("ed-pub-pinned") && $("ed-pub-pinned").checked),
      expiresAt: $("ed-pub-expires") ? $("ed-pub-expires").value : "",
      imageUrl: state.dropzones.pub ? state.dropzones.pub.getUrl() : "",
      linkLabel: $("ed-pub-link-label") ? $("ed-pub-link-label").value : "",
      linkUrl: $("ed-pub-link-url") ? $("ed-pub-link-url").value : "",
      isEvent: Boolean($("ed-pub-is-event") && $("ed-pub-is-event").checked),
      eventStart: $("ed-pub-event-start") ? $("ed-pub-event-start").value : "",
      eventEnd: $("ed-pub-event-end") ? $("ed-pub-event-end").value : "",
      location: $("ed-pub-location") ? $("ed-pub-location").value : "",
      eventNotifyGroups: readCheckedValues("ed-pub-event-notify-groups"),
      reminders: state.reminders.slice(),
    };
  }

  function fillPublicationForm(values, rawItem) {
    state.editingItem = rawItem || null;
    const editing = Boolean(values.id);

    if ($("ed-pub-id")) $("ed-pub-id").value = values.id || "";
    if ($("ed-pub-title")) $("ed-pub-title").value = values.title || "";

    if ($("ed-pub-rsvp")) $("ed-pub-rsvp").checked = Boolean(values.hasRegistration);
    if ($("ed-pub-scheduled")) {
      $("ed-pub-scheduled").checked = Boolean(values.scheduled || values.publishMode === "scheduled");
    }
    if ($("ed-pub-published-at")) $("ed-pub-published-at").value = values.publishedAt || "";

    renderTargetGroupCheckboxes(values.targetGroups);
    renderSubsetGroupCheckboxes("ed-pub-notify-groups", values.targetGroups, values.notifyGroups);
    renderSubsetGroupCheckboxes(
      "ed-pub-event-notify-groups",
      values.targetGroups,
      Array.isArray(values.eventNotifyGroups) && values.eventNotifyGroups.length
        ? values.eventNotifyGroups
        : values.targetGroups
    );

    if ($("ed-pub-is-news")) $("ed-pub-is-news").checked = Boolean(values.isNews);
    if ($("ed-pub-caption")) $("ed-pub-caption").value = values.caption || "";
    if ($("ed-pub-content")) $("ed-pub-content").value = values.content || "";
    if ($("ed-pub-pinned")) $("ed-pub-pinned").checked = Boolean(values.pinned);
    if ($("ed-pub-expires")) $("ed-pub-expires").value = values.expiresAt || "";
    if ($("ed-pub-link-label")) $("ed-pub-link-label").value = values.linkLabel || "";
    if ($("ed-pub-link-url")) $("ed-pub-link-url").value = values.linkUrl || "";

    if (state.dropzones.pub) {
      state.dropzones.pub.setReadOnly(false);
      state.dropzones.pub.reset();
      if (values.imageUrl) state.dropzones.pub.setUrl(values.imageUrl);
    }

    if ($("ed-pub-is-event")) $("ed-pub-is-event").checked = Boolean(values.isEvent);
    if ($("ed-pub-event-start")) $("ed-pub-event-start").value = values.eventStart || "";
    if ($("ed-pub-event-end")) $("ed-pub-event-end").value = values.eventEnd || "";
    if ($("ed-pub-location")) $("ed-pub-location").value = values.location || "";
    renderRemindersList(Array.isArray(values.reminders) ? values.reminders : [30]);

    $("ed-pub-form-title").textContent = editing ? "Editar publicación" : "Nueva publicación";
    $("ed-btn-delete-pub").classList.toggle("hidden", !editing);

    const metricsBar = $("ed-metrics-bar");
    if (metricsBar) {
      metricsBar.classList.toggle("hidden", !editing);
      if (editing) {
        $("ed-metric-views").textContent = `${Number(values.viewsCount || 0)} vistas`;
        $("ed-metric-attending").textContent = `${Number(values.attendingCount || 0)} inscritos`;
        $("ed-metric-declined").textContent = `${Number(values.declinedCount || 0)} bajas`;
        const badge = $("ed-metric-edited");
        if (badge) {
          if (values.isAiGenerated && !values.isEdited) {
            badge.textContent = "IA";
            badge.className = "ed-badge ed-badge-ai";
          } else if (values.isEdited) {
            badge.textContent = values.isAiGenerated ? "Editado · IA" : "Editado";
            badge.className = "ed-badge ed-badge-ok";
          } else {
            badge.textContent = "Pendiente";
            badge.className = "ed-badge ed-badge-warn";
          }
        }
      }
    }

    hideParticipants();
    showFieldErrors("pub", {});
    applyTypeAndSectionRules();
    syncAiButtonState();
  }

  // ---------------------------------------------------------------------------
  // Historial de auditoría (visible con permiso historial o rol admin)
  // ---------------------------------------------------------------------------

  async function loadListHistory() {
    const el = $("ed-list-history");
    if (!el) return;
    if (!state.isAdmin) {
      el.classList.add("hidden");
      el.innerHTML = "";
      return;
    }
    try {
      const entries = await getClient().getHistory("post");
      const html = Core.renderHistoryEntries(entries, { showTarget: true });
      el.innerHTML = html;
      const listCard = $("ed-publications-list-card");
      const listVisible = !listCard || !listCard.classList.contains("hidden");
      el.classList.toggle("hidden", !html || !listVisible);
    } catch (_) {
      el.classList.add("hidden");
      el.innerHTML = "";
    }
  }

  async function loadItemHistory(id) {
    const el = $("ed-pub-history");
    if (!el) return;
    if (!state.isAdmin || !id) {
      el.classList.add("hidden");
      el.innerHTML = "";
      return;
    }
    try {
      const entries = await getClient().getHistory("post", id);
      const html = Core.renderHistoryEntries(entries, { showTarget: false });
      el.innerHTML = html;
      const editorCard = $("ed-editor-card");
      const editorVisible = !editorCard || !editorCard.classList.contains("hidden");
      el.classList.toggle("hidden", !html || !editorVisible);
    } catch (_) {
      el.classList.add("hidden");
      el.innerHTML = "";
    }
  }

  // ---------------------------------------------------------------------------
  // Navegación Lista <-> Editor y operaciones CRUD
  // ---------------------------------------------------------------------------

  function openListView() {
    state.editingItem = null;
    hideParticipants();
    const listCard = $("ed-publications-list-card");
    const editorCard = $("ed-editor-card");
    const listHist = $("ed-list-history");
    const pubHist = $("ed-pub-history");
    if (listCard) listCard.classList.remove("hidden");
    if (editorCard) editorCard.classList.add("hidden");
    if (pubHist) pubHist.classList.add("hidden");
    if (listHist) {
      listHist.classList.toggle("hidden", !state.isAdmin || !listHist.innerHTML);
    }
  }

  async function openNewPublication() {
    await Promise.all([syncAvailableGroups(true), syncAiAvailability()]);
    const allGroupIds = state.groupCatalog.map((g) => g.value);
    const defaults = Core.publicationToFormValues({
      post_type: Core.POST_TYPE_NORMAL,
      is_news: true,
      is_event: false,
      target_groups: allGroupIds,
      reminders: [30],
    });
    defaults.targetGroups = allGroupIds.slice();
    defaults.eventNotifyGroups = allGroupIds.slice();
    defaults.eventStart = "";
    defaults.eventEnd = "";
    fillPublicationForm(defaults, null);
    const listHist = $("ed-list-history");
    if (listHist) listHist.classList.add("hidden");
    const histEl = $("ed-pub-history");
    if (histEl) {
      histEl.classList.add("hidden");
      histEl.innerHTML = "";
    }
    $("ed-publications-list-card").classList.add("hidden");
    $("ed-editor-card").classList.remove("hidden");
  }

  async function openEditPublication(id) {
    await Promise.all([syncAvailableGroups(true), syncAiAvailability()]);
    let item = state.publications.find((p) => String(p.id) === String(id)) || null;
    try {
      item = await getClient().getPublication(id);
    } catch (error) {
      if (!item) {
        showNotice("error", Core.describeError(error));
        return;
      }
    }
    fillPublicationForm(Core.publicationToFormValues(item), item);
    const listHist = $("ed-list-history");
    if (listHist) listHist.classList.add("hidden");
    $("ed-publications-list-card").classList.add("hidden");
    $("ed-editor-card").classList.remove("hidden");
    loadItemHistory(item.id);
  }

  function renderFilteredRows() {
    const tbody = $("ed-pub-rows");
    if (!tbody) return;
    let items = state.publications;
    if (state.filter === "news") {
      items = items.filter((p) => Boolean(p.is_news));
    } else if (state.filter === "events") {
      items = items.filter((p) => Boolean(p.is_event));
    }
    tbody.innerHTML = Core.renderPublicationRows(items);
  }

  function applyFilter(filterName) {
    state.filter = filterName || "all";
    ["all", "news", "events"].forEach((key) => {
      const btn = $(`ed-filter-${key}`);
      if (btn) btn.classList.toggle("is-active", key === state.filter);
    });
    renderFilteredRows();
  }

  async function loadPublications(options) {
    const opts = options || {};
    const tbody = $("ed-pub-rows");
    if (!tbody) return;
    if (state.publicationsLoaded || state.publications.length > 0) {
      renderFilteredRows();
    } else if (!opts.silent) {
      tbody.innerHTML = `<tr><td colspan="5" class="ed-empty">Cargando publicaciones...</td></tr>`;
    }
    try {
      const [pubs] = await Promise.all([
        getClient().listPublications({ include_scheduled: true }),
        loadListHistory(),
      ]);
      state.publications = pubs || [];
      state.publicationsLoaded = true;
      renderFilteredRows();
    } catch (error) {
      if (!state.publicationsLoaded) {
        tbody.innerHTML = `<tr><td colspan="5" class="ed-empty">${Core.escapeHtml(Core.describeError(error))}</td></tr>`;
      }
    }
  }

  function syncAiButtonState() {
    const btn = $("ed-pub-autocomplete-ai");
    const wrap = $("ed-pub-autocomplete-ai-wrap");
    if (!btn) return;
    if (btn.classList.contains("is-loading")) return;
    const enabled = Boolean(state.aiConfigured);
    const tooltip = enabled
      ? (Core.TEXTS && Core.TEXTS.aiAutocompleteEnabledTooltip) ||
        "Autocompletar campos vacíos con Google Gemini Flash"
      : (Core.TEXTS && Core.TEXTS.aiAutocompleteDisabledTooltip) ||
        "Configure un token válido de Gemini en la pestaña IA para habilitar el autocompletado.";
    btn.disabled = !enabled;
    btn.setAttribute("aria-disabled", enabled ? "false" : "true");
    btn.classList.toggle("is-disabled", !enabled);
    btn.setAttribute("title", tooltip);
    if (wrap) wrap.setAttribute("title", tooltip);
  }

  async function syncAiAvailability() {
    try {
      const cfg = await getClient().getAiConfig();
      if (cfg && typeof cfg.configured === "boolean") {
        state.aiConfigured = cfg.configured;
      }
    } catch (_) {
      /* mantiene estado actual si falla la red */
    }
    syncAiButtonState();
    return state.aiConfigured;
  }

  function setAiBusy(button, busy) {
    if (!button) return;
    const busyLabel = (Core.TEXTS && Core.TEXTS.aiAutocompleteBusy) || "Analizando contenido e imagen...";
    if (busy) {
      if (!button.dataset.origHtml) {
        button.dataset.origHtml = button.innerHTML;
      }
      button.innerHTML = `<span class="ed-ai-spinner" aria-hidden="true"></span><span>${Core.escapeHtml(
        busyLabel
      )}</span>`;
      button.disabled = true;
      button.classList.add("is-loading");
    } else {
      if (button.dataset.origHtml) {
        button.innerHTML = button.dataset.origHtml;
      }
      button.classList.remove("is-loading");
      syncAiButtonState();
    }
  }

  async function autocompletePublicationWithAi() {
    if (!state.aiConfigured) {
      showNotice(
        "warning",
        (Core.TEXTS && Core.TEXTS.aiAutocompleteDisabledTooltip) ||
          "Configure un token válido de Gemini en la pestaña IA para habilitar el autocompletado."
      );
      return null;
    }
    if (state.dropzones.pub && state.dropzones.pub.uploading) {
      showNotice("warning", "Espere a que finalice la subida del archivo antes de autocompletar.");
      return null;
    }

    const button = $("ed-pub-autocomplete-ai");
    const values = readPublicationForm();
    const options = resolveGroupOptions();
    const allIds = options.map((g) => g.value);
    const isUntouchedNewOrInstagram = !state.editingItem || state.editingItem.is_edited === false;
    const isAllDefaultSelected =
      isUntouchedNewOrInstagram &&
      allIds.length > 0 &&
      values.targetGroups.length === allIds.length &&
      allIds.every((id) => values.targetGroups.includes(id));
    const effectiveTargetGroups = isAllDefaultSelected ? [] : values.targetGroups;

    const reqPayload = {
      title: values.title,
      caption: values.caption,
      content: values.content,
      location: values.location,
      event_start: values.eventStart,
      event_end: values.eventEnd,
      target_groups: effectiveTargetGroups,
      link_label: values.linkLabel,
      link_url: values.linkUrl,
      media_url: values.imageUrl,
      post_type: values.postType,
      is_news: values.isNews,
      is_event: values.isEvent,
      has_registration: values.hasRegistration,
    };

    const file = state.dropzones.pub && state.dropzones.pub.getFile ? state.dropzones.pub.getFile() : null;
    setAiBusy(button, true);
    try {
      const suggestions = await getClient().autocompletePublicationAi(reqPayload, file);
      const baseForMerge = { ...values, targetGroups: effectiveTargetGroups };
      const merged = Core.applyAiSuggestionsToFormValues(baseForMerge, suggestions);

      const titleEl = $("ed-pub-title");
      if (titleEl && !titleEl.value.trim() && merged.title) {
        titleEl.value = merged.title;
      }

      const captionEl = $("ed-pub-caption");
      if (captionEl && !captionEl.readOnly && !captionEl.disabled && !captionEl.value.trim() && merged.caption) {
        captionEl.value = merged.caption;
      }

      const contentEl = $("ed-pub-content");
      if (contentEl && !contentEl.readOnly && !contentEl.disabled && !contentEl.value.trim() && merged.content) {
        contentEl.value = merged.content;
      }

      const linkLabelEl = $("ed-pub-link-label");
      if (
        linkLabelEl &&
        !linkLabelEl.readOnly &&
        !linkLabelEl.disabled &&
        !linkLabelEl.value.trim() &&
        merged.linkLabel
      ) {
        linkLabelEl.value = merged.linkLabel;
      }

      const linkUrlEl = $("ed-pub-link-url");
      if (linkUrlEl && !linkUrlEl.readOnly && !linkUrlEl.disabled && !linkUrlEl.value.trim() && merged.linkUrl) {
        linkUrlEl.value = merged.linkUrl;
      }

      if (effectiveTargetGroups.length === 0 && Array.isArray(merged.targetGroups) && merged.targetGroups.length > 0) {
        renderTargetGroupCheckboxes(merged.targetGroups);
        const normalizedTargets = readCheckedValues("ed-pub-target-groups");
        const targetList = normalizedTargets.length > 0 ? normalizedTargets : merged.targetGroups;
        const currentNotify = readCheckedValues("ed-pub-notify-groups").filter((g) => targetList.includes(g));
        renderSubsetGroupCheckboxes("ed-pub-notify-groups", targetList, currentNotify);
        renderSubsetGroupCheckboxes("ed-pub-event-notify-groups", targetList, targetList);
      }

      if (!values.hasRegistration && merged.hasRegistration && $("ed-pub-rsvp")) {
        $("ed-pub-rsvp").checked = true;
      }

      if (!values.isEvent && merged.isEvent && $("ed-pub-is-event") && !$("ed-pub-is-event").disabled) {
        $("ed-pub-is-event").checked = true;
        if (state.reminders.length === 0) {
          renderRemindersList([30]);
        }
        const currentTargets = readCheckedValues("ed-pub-target-groups");
        const currentEventNotify = readCheckedValues("ed-pub-event-notify-groups");
        if (currentEventNotify.length === 0 && currentTargets.length > 0) {
          renderSubsetGroupCheckboxes("ed-pub-event-notify-groups", currentTargets, currentTargets);
        }
      }

      const startEl = $("ed-pub-event-start");
      if (startEl && !startEl.value.trim() && merged.eventStart) {
        startEl.value = merged.eventStart;
      }

      const endEl = $("ed-pub-event-end");
      if (endEl && !endEl.value.trim() && merged.eventEnd) {
        endEl.value = merged.eventEnd;
      }

      const locEl = $("ed-pub-location");
      if (locEl && !locEl.value.trim() && merged.location) {
        locEl.value = merged.location;
      }

      showFieldErrors("pub", {});
      applyTypeAndSectionRules();
      showNotice("success", (Core.TEXTS && Core.TEXTS.aiAutocompleteSuccess) || "Campos completados por IA");
      return suggestions;
    } catch (error) {
      const fallbackMsg =
        (Core.TEXTS && Core.TEXTS.aiAutocompleteError) ||
        "No se pudo autocompletar: Verifique la clave de IA en Control de IA";
      const rawMsg = Core.describeError(error);
      const msg = rawMsg && rawMsg.includes(fallbackMsg) ? rawMsg : fallbackMsg;
      showNotice("error", msg);
      return null;
    } finally {
      setAiBusy(button, false);
    }
  }

  async function submitPublication(event) {
    event.preventDefault();
    const values = readPublicationForm();
    const errors = Core.validatePublicationValues(values);
    showFieldErrors("pub", errors);
    if (Object.keys(errors).length > 0) return;

    if (state.dropzones.pub && state.dropzones.pub.uploading) {
      showNotice("warning", "Espere a que finalice la subida del archivo antes de guardar.");
      return;
    }

    const id = $("ed-pub-id").value;
    const button = $("ed-pub-submit");
    setBusy(button, true, "Guardando...");
    try {
      const payload = Core.buildPublicationPayload(values);
      const saved = id
        ? await getClient().updatePublication(id, payload)
        : await getClient().createPublication(payload);
      showNotice("success", id ? "Publicación actualizada." : "Publicación guardada.");
      openListView();
      await loadPublications();
      return saved;
    } catch (error) {
      showNotice("error", Core.describeError(error));
      return null;
    } finally {
      setBusy(button, false);
    }
  }

  async function deleteCurrentPublication() {
    const id = $("ed-pub-id").value;
    if (!id) return;
    const title = $("ed-pub-title").value || `#${id}`;
    if (!window.confirm(`¿Eliminar definitivamente "${title}"?`)) return;

    const btn = $("ed-btn-delete-pub");
    setBusy(btn, true, "Eliminando...");
    try {
      await getClient().deletePublication(id);
      showNotice("success", "Publicación eliminada.");
      openListView();
      await loadPublications();
    } catch (error) {
      showNotice("error", Core.describeError(error));
    } finally {
      setBusy(btn, false);
    }
  }

  function hideParticipants() {
    state.participantsPubId = null;
    const panel = $("ed-participants");
    if (panel) {
      panel.classList.add("hidden");
      panel.innerHTML = "";
    }
    const btn = $("ed-btn-toggle-participants");
    if (btn) btn.textContent = "Ver participantes";
  }

  async function toggleParticipants() {
    const id = $("ed-pub-id").value;
    if (!id) return;
    const panel = $("ed-participants");
    const btn = $("ed-btn-toggle-participants");
    if (!panel.classList.contains("hidden") && String(state.participantsPubId) === String(id)) {
      hideParticipants();
      return;
    }
    state.participantsPubId = id;
    panel.classList.remove("hidden");
    panel.innerHTML = `<p class="ed-empty">Cargando participantes...</p>`;
    if (btn) btn.textContent = "Ocultar participantes";
    try {
      const data = await getClient().getPublicationRegistrations(id);
      if (String(state.participantsPubId) !== String(id)) return;
      panel.innerHTML = Core.renderParticipantsTable(data);
    } catch (error) {
      panel.innerHTML = `<p class="ed-empty">${Core.escapeHtml(Core.describeError(error))}</p>`;
    }
  }

  async function syncInstagram() {
    const button = $("ed-btn-sync");
    const statusEl = $("ed-sync-status");
    setBusy(button, true, "Sincronizando...");
    if (statusEl) statusEl.textContent = "Consultando Instagram...";
    try {
      const result = await getClient().syncInstagram();
      const summary = Core.describeSyncResult(result);
      showNotice(summary.type, summary.message);
      if (statusEl) {
        statusEl.textContent = `Sincronizado ${new Date().toLocaleTimeString("es-PY", {
          hour: "2-digit",
          minute: "2-digit",
        })}`;
      }
      await loadPublications();
    } catch (error) {
      if (statusEl) statusEl.textContent = "Error al sincronizar";
      showNotice("error", Core.describeError(error));
    } finally {
      setBusy(button, false);
    }
  }

  // ---------------------------------------------------------------------------
  // Modos e inicialización
  // ---------------------------------------------------------------------------

  function applyMode(mode) {
    state.mode = state.allowed && mode === "editorial" ? "editorial" : "student";
    const editorial = state.mode === "editorial";
    const studentEl = $("student-workspace");
    const editorialEl = $("view-editorial");
    if (studentEl) studentEl.classList.toggle("hidden", editorial);
    if (editorialEl) editorialEl.classList.toggle("hidden", !editorial);
    ["view-groups", "view-admins", "view-ai"].forEach((vid) => {
      const v = $(vid);
      if (v) v.classList.add("hidden");
    });
    if (window.UpaRouter && typeof window.UpaRouter.syncNavClasses === "function") {
      window.UpaRouter.syncNavClasses(editorial ? "publicaciones" : "apis");
    }
    try {
      localStorage.setItem(MODE_STORAGE_KEY, state.mode);
    } catch (_) {
      /* almacenamiento no disponible */
    }
    if (editorial) loadPanelData();
  }

  function loadPanelData() {
    if (!state.allowed) return;
    openListView();
    loadPublications();
  }

  function initOnce() {
    if (state.ready) return;
    state.ready = true;

    document.querySelectorAll("[data-dropzone]").forEach(bindDropzone);

    ["all", "news", "events"].forEach((key) => {
      const btn = $(`ed-filter-${key}`);
      if (btn) btn.addEventListener("click", () => applyFilter(key));
    });

    if ($("ed-btn-new-pub")) $("ed-btn-new-pub").addEventListener("click", openNewPublication);
    if ($("ed-btn-back")) $("ed-btn-back").addEventListener("click", openListView);
    if ($("ed-pub-cancel")) $("ed-pub-cancel").addEventListener("click", openListView);
    if ($("ed-btn-delete-pub")) $("ed-btn-delete-pub").addEventListener("click", deleteCurrentPublication);
    if ($("ed-btn-toggle-participants")) {
      $("ed-btn-toggle-participants").addEventListener("click", toggleParticipants);
    }
    if ($("ed-btn-sync")) $("ed-btn-sync").addEventListener("click", syncInstagram);
    if ($("ed-pub-autocomplete-ai")) {
      $("ed-pub-autocomplete-ai").addEventListener("click", autocompletePublicationWithAi);
    }
    if ($("ed-form-pub")) $("ed-form-pub").addEventListener("submit", submitPublication);

    if ($("ed-pub-scheduled")) $("ed-pub-scheduled").addEventListener("change", applyTypeAndSectionRules);
    if ($("ed-pub-pinned")) $("ed-pub-pinned").addEventListener("change", applyTypeAndSectionRules);
    if ($("ed-pub-is-news")) $("ed-pub-is-news").addEventListener("change", applyTypeAndSectionRules);
    if ($("ed-pub-link-url")) {
      $("ed-pub-link-url").addEventListener("input", syncLinkPreview);
      $("ed-pub-link-url").addEventListener("change", syncLinkPreview);
    }
    if ($("ed-pub-link-preview")) {
      $("ed-pub-link-preview").addEventListener("click", (e) => {
        if ($("ed-pub-link-preview").getAttribute("aria-disabled") === "true") {
          e.preventDefault();
        }
      });
    }
    if ($("ed-pub-is-event")) {
      $("ed-pub-is-event").addEventListener("change", () => {
        if ($("ed-pub-is-event").checked) {
          if (state.reminders.length === 0 && !state.editingItem) {
            renderRemindersList([30]);
          }
          const currentTargets = readCheckedValues("ed-pub-target-groups");
          const currentEventNotify = readCheckedValues("ed-pub-event-notify-groups");
          if (currentEventNotify.length === 0 && currentTargets.length > 0) {
            renderSubsetGroupCheckboxes("ed-pub-event-notify-groups", currentTargets, currentTargets);
          }
        }
        applyTypeAndSectionRules();
      });
    }
    if ($("ed-btn-add-reminder")) $("ed-btn-add-reminder").addEventListener("click", addReminderRow);

    document.querySelectorAll('[data-mask="datetime"]').forEach((inputEl) => {
      inputEl.addEventListener("input", () => {
        if (Core.maskDateTimeInput && /^[\d/\s:]*$/.test(inputEl.value)) {
          const masked = Core.maskDateTimeInput(inputEl.value);
          if (masked !== inputEl.value) inputEl.value = masked;
        }
      });
    });

    document.querySelectorAll('[data-mask="time"]').forEach((inputEl) => {
      inputEl.addEventListener("input", () => {
        if (Core.maskTime24Input && /^[\d:]*$/.test(inputEl.value)) {
          const masked = Core.maskTime24Input(inputEl.value);
          if (masked !== inputEl.value) inputEl.value = masked;
        }
      });
    });

    const validateEventTimeFieldsLive = () => {
      const isEv = Boolean($("ed-pub-is-event") && $("ed-pub-is-event").checked);
      if (!isEv) return;
      const values = readPublicationForm();
      const errs = Core.validatePublicationValues(values);
      const startErrEl = document.querySelector('[data-error-for="pub-eventStart"]');
      const endErrEl = document.querySelector('[data-error-for="pub-eventEnd"]');
      const startIn = $("ed-pub-event-start");
      const endIn = $("ed-pub-event-end");
      if (startErrEl && startIn && startIn.value.trim()) {
        startErrEl.textContent = errs.eventStart || "";
        startIn.classList.toggle("has-error", Boolean(errs.eventStart));
      } else if (startErrEl && startIn && !startIn.value.trim()) {
        startErrEl.textContent = "";
        startIn.classList.remove("has-error");
      }
      if (endErrEl && endIn) {
        endErrEl.textContent = errs.eventEnd || "";
        endIn.classList.toggle("has-error", Boolean(errs.eventEnd));
      }
    };

    ["ed-pub-event-start", "ed-pub-event-end"].forEach((id) => {
      const el = $(id);
      if (el) {
        el.addEventListener("change", validateEventTimeFieldsLive);
        el.addEventListener("blur", validateEventTimeFieldsLive);
      }
    });

    const tbody = $("ed-pub-rows");
    if (tbody) {
      tbody.addEventListener("click", (event) => {
        const row = event.target.closest("tr[data-pub-id]");
        if (row) openEditPublication(row.getAttribute("data-pub-id"));
      });
      tbody.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          const row = event.target.closest("tr[data-pub-id]");
          if (row) {
            event.preventDefault();
            openEditPublication(row.getAttribute("data-pub-id"));
          }
        }
      });
    }
  }

  function userHasPublicationsPerm(user) {
    if (!user) return false;
    if (Array.isArray(user.permissions)) {
      return user.permissions.includes("publicaciones");
    }
    const role = String(user.role || "").toLowerCase();
    return role === "admin" || role === "editor";
  }

  function userHasHistoryPerm(user) {
    if (!user) return false;
    if (Array.isArray(user.permissions)) {
      return user.permissions.some((p) => String(p || "").trim().toLowerCase() === "historial");
    }
    const role = String(user.role || "").toLowerCase();
    return role === "admin";
  }

  const UpaCockpit = {
    configure(config) {
      state.config = { ...state.config, ...config };
      state.client = null;
    },

    onUserLoaded(user) {
      state.allowed = userHasPublicationsPerm(user);
      state.isAdmin = userHasHistoryPerm(user);
      if (!state.isAdmin) {
        ["ed-list-history", "ed-pub-history"].forEach((id) => {
          const el = $(id);
          if (el) {
            el.classList.add("hidden");
            el.innerHTML = "";
          }
        });
      }
      if (!state.allowed) {
        const editorialEl = $("view-editorial");
        if (editorialEl) editorialEl.classList.add("hidden");
        return;
      }
      initOnce();
      syncAvailableGroups();
      syncAiAvailability();
    },

    reset() {
      state.allowed = false;
      state.isAdmin = false;
      state.aiConfigured = false;
      state.publications = [];
      state.publicationsLoaded = false;
      state.groupCatalog = [];
      state.editingItem = null;
      state.participantsPubId = null;
      groupsSynced = false;
      groupsSyncPromise = null;
      syncAiButtonState();
      const editorial = $("view-editorial");
      if (editorial) editorial.classList.add("hidden");
      const student = $("student-workspace");
      if (student) student.classList.remove("hidden");
    },

    setAiConfigured(configured) {
      state.aiConfigured = Boolean(configured);
      syncAiButtonState();
    },

    applyMode,
    loadPanelData,
    refreshGroupsCatalog,
    openEditPublication,
    openNewPublication,
  };

  window.UpaCockpit = UpaCockpit;
})();
