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
    groupCatalog: Core ? Core.TARGET_GROUPS.slice() : [],
    editingItem: null,
    reminders: [30],
    participantsPubId: null,
    dropzones: {},
    noticeTimer: null,
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

  function refreshGroupsCatalog(groups) {
    const merged = Core.TARGET_GROUPS.map((g) => ({ value: g.value, label: g.label }));
    const seen = new Set(merged.map((g) => g.value.toUpperCase()));
    if (Array.isArray(groups)) {
      groups.forEach((g) => {
        if (!g || !g.id) return;
        const val = String(g.id).toUpperCase();
        if (!seen.has(val)) {
          seen.add(val);
          merged.push({ value: val, label: g.name || val });
        }
      });
    }
    state.groupCatalog = merged;
  }

  async function syncAvailableGroups() {
    try {
      const groups = await getClient().listGroups();
      refreshGroupsCatalog(groups);
    } catch (_) {
      /* mantiene catálogo base si falla la red */
    }
  }

  function resolveGroupOptions(selected) {
    const chosen = Array.isArray(selected) ? selected : [];
    const options = state.groupCatalog.slice();
    const known = new Set(options.map((g) => g.value));
    chosen.forEach((val) => {
      if (val && !known.has(val)) {
        known.add(val);
        options.push({ value: val, label: val });
      }
    });
    return options;
  }

  function renderTargetGroupCheckboxes(selected) {
    const container = $("ed-pub-target-groups");
    if (!container) return;
    const chosen = Array.isArray(selected) && selected.length ? selected : ["ALL"];
    const options = resolveGroupOptions(chosen);
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
        const currentEventNotify = readCheckedValues("ed-pub-event-notify-groups").filter((g) =>
          currentTargets.includes(g)
        );
        renderSubsetGroupCheckboxes("ed-pub-notify-groups", currentTargets, currentNotify);
        renderSubsetGroupCheckboxes("ed-pub-event-notify-groups", currentTargets, currentEventNotify);
      });
    });
  }

  function renderSubsetGroupCheckboxes(containerId, targetGroups, selectedSubset) {
    const container = $(containerId);
    if (!container) return;
    const targets = Array.isArray(targetGroups) ? targetGroups : [];
    const chosen = Array.isArray(selectedSubset) ? selectedSubset : [];
    if (targets.length === 0) {
      container.innerHTML = `<span class="ed-subtle">Seleccione primero al menos un grupo destinatario arriba.</span>`;
      return;
    }
    const catalog = resolveGroupOptions(targets);
    const subsetOptions = targets.map((val) => catalog.find((c) => c.value === val) || { value: val, label: val });
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
  // Recordatorios dinámicos del evento (número + unidad: minutos, horas, días)
  // ---------------------------------------------------------------------------

  const REMINDER_UNITS = [
    { key: "minutos", factor: 1, label: "minutos antes" },
    { key: "horas", factor: 60, label: "horas antes" },
    { key: "dias", factor: 1440, label: "días antes" },
  ];

  function reminderToParts(mins) {
    const n = Number(mins) || 0;
    if (n > 0 && n % 1440 === 0) return { value: n / 1440, unit: "dias" };
    if (n > 0 && n % 60 === 0) return { value: n / 60, unit: "horas" };
    return { value: n, unit: "minutos" };
  }

  function partsToMinutes(value, unit) {
    const unitDef = REMINDER_UNITS.find((u) => u.key === unit) || REMINDER_UNITS[0];
    return Math.round((Number(value) || 0) * unitDef.factor);
  }

  function syncRemindersFromDom() {
    const container = $("ed-reminders-list");
    if (!container) return;
    const rows = Array.from(container.querySelectorAll("[data-reminder-idx]"));
    if (rows.length > 0) {
      state.reminders = rows.map((row) => {
        const valueEl = row.querySelector("[data-reminder-value]");
        const unitEl = row.querySelector("[data-reminder-unit]");
        return partsToMinutes(valueEl ? valueEl.value : 0, unitEl ? unitEl.value : "minutos");
      });
    }
  }

  function renderRemindersList(reminders) {
    state.reminders = Array.isArray(reminders) ? reminders.map((r) => Number(r) || 0) : [];
    const container = $("ed-reminders-list");
    if (!container) return;
    if (state.reminders.length === 0) {
      container.innerHTML = `<span class="ed-subtle">Sin recordatorios activos.</span>`;
      return;
    }
    container.innerHTML = state.reminders
      .map((mins, idx) => {
        const parts = reminderToParts(mins);
        const unitOptions = REMINDER_UNITS.map(
          (u) => `<option value="${u.key}"${parts.unit === u.key ? " selected" : ""}>${u.label}</option>`
        ).join("");
        return `
        <div class="ed-reminder-row" data-reminder-idx="${idx}">
          <input type="number" min="0" max="43200" step="1" data-reminder-value value="${Core.escapeHtml(
            parts.value
          )}" aria-label="Cantidad de tiempo antes del evento">
          <select data-reminder-unit aria-label="Unidad de tiempo">${unitOptions}</select>
          <button type="button" class="text-slate-400 hover:text-red-600 font-bold px-1" data-remove-reminder="${idx}" title="Quitar recordatorio">&times;</button>
        </div>`;
      })
      .join("");

    container.querySelectorAll("[data-reminder-value], [data-reminder-unit]").forEach((el) => {
      el.addEventListener("input", () => syncRemindersFromDom());
      el.addEventListener("change", () => syncRemindersFromDom());
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
      getUrl: () => (urlField ? urlField.value : ""),
      setStatus(type, message) {
        if (!status) return;
        status.textContent = message || "";
        status.className = `ed-dz-status${type ? ` is-${type}` : ""}`;
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
        const media = Core.isImageUrl(safe)
          ? `<img src="${Core.escapeHtml(safe)}" alt="Vista previa">`
          : `<a class="ed-link" href="${Core.escapeHtml(safe)}" target="_blank" rel="noopener noreferrer">${Core.escapeHtml(
              label || "Documento adjunto"
            )}</a>`;
        preview.innerHTML = `${media}<button type="button" class="ed-btn ed-btn-secondary ed-btn-sm" data-dz-remove>Quitar</button>`;
        preview.classList.remove("hidden");
        preview.querySelector("[data-dz-remove]").addEventListener("click", () => {
          dz.setUrl("");
          dz.setStatus("", "");
        });
      },
      reset() {
        dz.setUrl("");
        dz.setStatus("", "");
      },
    };

    async function handleFile(file) {
      if (dz.uploading) return;
      const check = Core.validateUploadFile(file);
      if (!check.ok) {
        dz.setStatus("error", check.message);
        return;
      }
      dz.uploading = true;
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
  // Reglas dinámicas de tipo, fecha de publicación y secciones
  // ---------------------------------------------------------------------------

  function applyTypeAndSectionRules() {
    const typeSelect = $("ed-pub-type");
    const publishMode = $("ed-pub-publish-mode");
    const publishedInput = $("ed-pub-published-at");
    const publishedHint = $("ed-pub-published-hint");
    const isNewsCb = $("ed-pub-is-news");
    const isEventCb = $("ed-pub-is-event");
    const newsLockHint = $("ed-news-lock-hint");
    const eventLockHint = $("ed-event-lock-hint");
    const newsNotifyHint = $("ed-news-notify-hint");
    const newsBox = $("ed-section-news");
    const eventBox = $("ed-section-event");
    const newsFields = $("ed-news-fields");
    const eventFields = $("ed-event-fields");

    if (!typeSelect || !isNewsCb || !isEventCb) return;

    const isInstagramItem = Boolean(state.editingItem && state.editingItem.post_type === Core.POST_TYPE_INSTAGRAM);
    const igOpt = typeSelect.querySelector('option[value="INSTAGRAM"]');
    if (igOpt) igOpt.disabled = !isInstagramItem;

    if (isInstagramItem) {
      typeSelect.value = Core.POST_TYPE_INSTAGRAM;
      typeSelect.disabled = true;
    } else {
      if (typeSelect.value === Core.POST_TYPE_INSTAGRAM) {
        typeSelect.value = Core.POST_TYPE_NORMAL;
      }
      typeSelect.disabled = false;
    }

    const postType = typeSelect.value;

    // Reglas de fecha de publicación
    if (isInstagramItem) {
      publishMode.value = "on_save";
      publishMode.disabled = true;
      publishedInput.classList.add("hidden");
      publishedInput.disabled = true;
      const origDate = Core.formatDateTime(state.editingItem.published_at || state.editingItem.created_at);
      publishedHint.textContent = origDate
        ? `Fecha original de Instagram: ${origDate} (bloqueada)`
        : "Fecha original de Instagram (bloqueada)";
    } else {
      publishMode.disabled = false;
      publishedInput.disabled = false;
      const scheduled = publishMode.value === "scheduled";
      publishedInput.classList.toggle("hidden", !scheduled);
      if (scheduled) {
        publishedHint.textContent = "La publicación será visible a partir de esa fecha y hora.";
      } else if (state.editingItem && (state.editingItem.published_at || state.editingItem.created_at)) {
        publishedHint.textContent = `Publicada: ${Core.formatDateTime(
          state.editingItem.published_at || state.editingItem.created_at
        )}`;
      } else {
        publishedHint.textContent = "Se registrará la fecha exacta al guardar.";
      }
    }

    // Reglas de sección Noticia vs Evento
    if (postType === Core.POST_TYPE_INSTAGRAM) {
      isNewsCb.checked = true;
      isNewsCb.disabled = true;
      newsLockHint.textContent = "Obligatoria en publicaciones de Instagram";
      if (newsNotifyHint) {
        newsNotifyHint.textContent = "Al guardar se enviará notificación a los grupos marcados.";
      }
      isEventCb.disabled = false;
      eventLockHint.textContent = "";
    } else if (postType === Core.POST_TYPE_URGENT) {
      isNewsCb.checked = true;
      isNewsCb.disabled = true;
      newsLockHint.textContent = "Obligatoria en avisos urgentes";
      if (newsNotifyHint) {
        newsNotifyHint.textContent = "El aviso urgente enviará notificación push al publicar.";
      }
      isEventCb.checked = false;
      isEventCb.disabled = true;
      eventLockHint.textContent = "No disponible en avisos urgentes";
    } else {
      isNewsCb.disabled = false;
      newsLockHint.textContent = "";
      if (newsNotifyHint) {
        newsNotifyHint.textContent = "Seleccione los grupos que recibirán notificación al publicar.";
      }
      isEventCb.disabled = false;
      eventLockHint.textContent = "";
    }

    const showNews = isNewsCb.checked;
    const showEvent = isEventCb.checked;
    newsFields.classList.toggle("hidden", !showNews);
    newsBox.classList.toggle("is-open", showNews);
    eventFields.classList.toggle("hidden", !showEvent);
    eventBox.classList.toggle("is-open", showEvent);
  }

  // ---------------------------------------------------------------------------
  // Lectura y llenado del formulario unificado
  // ---------------------------------------------------------------------------

  function readPublicationForm() {
    syncRemindersFromDom();
    return {
      title: $("ed-pub-title").value,
      postType: $("ed-pub-type").value,
      hasRegistration: $("ed-pub-rsvp").checked,
      targetGroups: readCheckedValues("ed-pub-target-groups"),
      publishMode: $("ed-pub-publish-mode").value,
      publishedAt: $("ed-pub-published-at").value,
      isNews: $("ed-pub-is-news").checked,
      notifyGroups: readCheckedValues("ed-pub-notify-groups"),
      caption: $("ed-pub-caption").value,
      content: $("ed-pub-content").value,
      detailText: $("ed-pub-detail-text").value,
      category: $("ed-pub-category").value,
      pinned: $("ed-pub-pinned").checked,
      expiresAt: $("ed-pub-expires").value,
      imageUrl: state.dropzones.pub ? state.dropzones.pub.getUrl() : "",
      linkLabel: $("ed-pub-link-label").value,
      linkUrl: $("ed-pub-link-url").value,
      isEvent: $("ed-pub-is-event").checked,
      eventStart: $("ed-pub-event-start").value,
      eventEnd: $("ed-pub-event-end").value,
      location: $("ed-pub-location").value,
      eventNotifyGroups: readCheckedValues("ed-pub-event-notify-groups"),
      reminders: state.reminders.slice(),
    };
  }

  function fillPublicationForm(values, rawItem) {
    state.editingItem = rawItem || null;
    const editing = Boolean(values.id);

    $("ed-pub-id").value = values.id || "";
    $("ed-pub-title").value = values.title || "";

    const igOpt = $("ed-pub-type").querySelector('option[value="INSTAGRAM"]');
    if (igOpt) igOpt.disabled = values.postType !== Core.POST_TYPE_INSTAGRAM;
    $("ed-pub-type").value = values.postType || Core.POST_TYPE_NORMAL;

    $("ed-pub-rsvp").checked = Boolean(values.hasRegistration);
    $("ed-pub-publish-mode").value = values.publishMode || "on_save";
    $("ed-pub-published-at").value = values.publishedAt || "";

    renderTargetGroupCheckboxes(values.targetGroups);
    renderSubsetGroupCheckboxes("ed-pub-notify-groups", values.targetGroups, values.notifyGroups);
    renderSubsetGroupCheckboxes("ed-pub-event-notify-groups", values.targetGroups, values.eventNotifyGroups);

    $("ed-pub-is-news").checked = Boolean(values.isNews);
    $("ed-pub-caption").value = values.caption || "";
    $("ed-pub-content").value = values.content || "";
    $("ed-pub-detail-text").value = values.detailText || "";
    $("ed-pub-category").value = values.category || "";
    $("ed-pub-pinned").checked = Boolean(values.pinned);
    $("ed-pub-expires").value = values.expiresAt || "";
    $("ed-pub-link-label").value = values.linkLabel || "";
    $("ed-pub-link-url").value = values.linkUrl || "";

    if (state.dropzones.pub) {
      state.dropzones.pub.reset();
      if (values.imageUrl) state.dropzones.pub.setUrl(values.imageUrl);
    }

    $("ed-pub-is-event").checked = Boolean(values.isEvent);
    $("ed-pub-event-start").value = values.eventStart || "";
    $("ed-pub-event-end").value = values.eventEnd || "";
    $("ed-pub-location").value = values.location || "";
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
          badge.textContent = values.isEdited ? "Editado" : "Pendiente";
          badge.className = `ed-badge ${values.isEdited ? "ed-badge-ok" : "ed-badge-warn"}`;
        }
      }
    }

    hideParticipants();
    showFieldErrors("pub", {});
    applyTypeAndSectionRules();
  }

  // ---------------------------------------------------------------------------
  // Historial de auditoría (visible únicamente para administradores)
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
      el.classList.toggle("hidden", !html);
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
      el.classList.toggle("hidden", !html);
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
    if (listCard) listCard.classList.remove("hidden");
    if (editorCard) editorCard.classList.add("hidden");
  }

  async function openNewPublication() {
    await syncAvailableGroups();
    const defaults = Core.publicationToFormValues({
      post_type: Core.POST_TYPE_NORMAL,
      is_news: true,
      is_event: false,
      target_groups: ["ALL"],
      reminders: [30],
    });
    fillPublicationForm(defaults, null);
    const histEl = $("ed-pub-history");
    if (histEl) {
      histEl.classList.add("hidden");
      histEl.innerHTML = "";
    }
    $("ed-publications-list-card").classList.add("hidden");
    $("ed-editor-card").classList.remove("hidden");
  }

  async function openEditPublication(id) {
    await syncAvailableGroups();
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

  async function loadPublications() {
    const tbody = $("ed-pub-rows");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="5" class="ed-empty">Cargando publicaciones...</td></tr>`;
    try {
      state.publications = (await getClient().listPublications({ include_scheduled: true })) || [];
      renderFilteredRows();
      loadListHistory();
    } catch (error) {
      tbody.innerHTML = `<tr><td colspan="5" class="ed-empty">${Core.escapeHtml(Core.describeError(error))}</td></tr>`;
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
    ["view-groups", "view-admins", "view-diagnostic"].forEach((vid) => {
      const v = $(vid);
      if (v) v.classList.add("hidden");
    });
    if ($("mode-btn-editorial")) $("mode-btn-editorial").classList.toggle("is-active", editorial);
    if ($("mode-btn-student")) $("mode-btn-student").classList.toggle("is-active", !editorial);
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

    const catSelect = $("ed-pub-category");
    if (catSelect) {
      catSelect.innerHTML =
        `<option value="">Sin categoría</option>` +
        Core.CATEGORIES.map((c) => `<option value="${Core.escapeHtml(c.value)}">${Core.escapeHtml(c.label)}</option>`).join("");
    }

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
    if ($("ed-form-pub")) $("ed-form-pub").addEventListener("submit", submitPublication);

    if ($("ed-pub-type")) $("ed-pub-type").addEventListener("change", applyTypeAndSectionRules);
    if ($("ed-pub-publish-mode")) $("ed-pub-publish-mode").addEventListener("change", applyTypeAndSectionRules);
    if ($("ed-pub-is-news")) $("ed-pub-is-news").addEventListener("change", applyTypeAndSectionRules);
    if ($("ed-pub-is-event")) {
      $("ed-pub-is-event").addEventListener("change", () => {
        if ($("ed-pub-is-event").checked && state.reminders.length === 0 && !state.editingItem) {
          renderRemindersList([30]);
        }
        applyTypeAndSectionRules();
      });
    }
    if ($("ed-btn-add-reminder")) $("ed-btn-add-reminder").addEventListener("click", addReminderRow);

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

  const UpaCockpit = {
    configure(config) {
      state.config = { ...state.config, ...config };
      state.client = null;
    },

    onUserLoaded(user) {
      state.allowed = userHasPublicationsPerm(user);
      state.isAdmin = String((user && user.role) || "").toLowerCase() === "admin";
      if (!state.allowed) {
        const editorialEl = $("view-editorial");
        if (editorialEl) editorialEl.classList.add("hidden");
        return;
      }
      initOnce();
      syncAvailableGroups();
    },

    reset() {
      state.allowed = false;
      state.isAdmin = false;
      state.publications = [];
      state.editingItem = null;
      state.participantsPubId = null;
      const editorial = $("view-editorial");
      if (editorial) editorial.classList.add("hidden");
      const student = $("student-workspace");
      if (student) student.classList.remove("hidden");
    },

    applyMode,
    loadPanelData,
    refreshGroupsCatalog,
    openEditPublication,
    openNewPublication,
  };

  window.UpaCockpit = UpaCockpit;
})();
