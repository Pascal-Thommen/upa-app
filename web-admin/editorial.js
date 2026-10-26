/**
 * Cockpit de Redaccion (web-admin): controlador del DOM.
 *
 * Conecta los formularios y tablas de index.html con el cliente REST de `editorial-core.js`,
 * que a su vez llama a los endpoints reales del backend (/api/news, /api/events, /api/media/upload,
 * /api/news/sync-instagram). Sin datos simulados: todo lo mostrado proviene de la API.
 *
 * Integracion con app.js: `UpaCockpit.configure(...)` (una vez), `UpaCockpit.onUserLoaded(user)`
 * tras validar la sesion y `UpaCockpit.reset()` al cerrar sesion.
 */
(function () {
  "use strict";

  const Core = window.UpaEditorial;
  const MODE_STORAGE_KEY = "upa_view_mode";
  const EDITOR_ROLES = ["admin", "editor"];
  const NOTICE_AUTOHIDE_MS = 7000;

  const $ = (id) => document.getElementById(id);

  const state = {
    config: { getToken: () => null, onUnauthorized: () => {} },
    client: null,
    ready: false,
    allowed: false,
    mode: "editorial",
    panel: "news",
    news: [],
    events: [],
    participantsEventId: null,
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
  // Avisos y errores de formulario
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
      if (control && control.classList.contains("ed-input")) {
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
  // Modo (estudiantes / redaccion) y paneles
  // ---------------------------------------------------------------------------

  function applyMode(mode) {
    state.mode = state.allowed && mode === "editorial" ? "editorial" : "student";
    const editorial = state.mode === "editorial";
    $("student-workspace").classList.toggle("hidden", editorial);
    $("view-editorial").classList.toggle("hidden", !editorial);
    const vGroups = $("view-groups");
    if (vGroups) vGroups.classList.add("hidden");
    const vAdmins = $("view-admins");
    if (vAdmins) vAdmins.classList.add("hidden");
    const vDiag = $("view-diagnostic");
    if (vDiag) vDiag.classList.add("hidden");
    if ($("mode-btn-editorial")) {
      $("mode-btn-editorial").classList.toggle("is-active", editorial);
    }
    if ($("mode-btn-student")) {
      $("mode-btn-student").classList.toggle("is-active", !editorial);
    }
    try {
      localStorage.setItem(MODE_STORAGE_KEY, state.mode);
    } catch (_) {
      /* almacenamiento no disponible: el modo solo dura la sesion de la pagina */
    }
    if (editorial) loadPanelData();
  }

  function applyPanel(panel) {
    state.panel = panel;
    $("ed-panel-news").classList.toggle("hidden", panel !== "news");
    $("ed-panel-events").classList.toggle("hidden", panel !== "events");
    $("ed-tab-news").classList.toggle("is-active", panel === "news");
    $("ed-tab-events").classList.toggle("is-active", panel === "events");
    loadPanelData();
  }

  function loadPanelData() {
    if (!state.allowed || state.mode !== "editorial") return;
    if (state.panel === "news") loadNews();
    else loadEvents();
  }

  // ---------------------------------------------------------------------------
  // Zonas de carga (arrastrar y soltar)
  // ---------------------------------------------------------------------------

  function bindDropzone(zone) {
    const input = zone.querySelector("[data-dz-input]");
    const urlField = zone.querySelector("[data-dz-url]");
    const status = zone.querySelector("[data-dz-status]");
    const preview = zone.querySelector("[data-dz-preview]");
    const pick = zone.querySelector("[data-dz-pick]");

    const dz = {
      uploading: false,
      getUrl: () => urlField.value,
      setStatus(type, message) {
        status.textContent = message || "";
        status.className = `ed-dz-status${type ? ` is-${type}` : ""}`;
      },
      setUrl(url, label) {
        urlField.value = url || "";
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

    pick.addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      input.value = "";
      if (file) handleFile(file);
    });
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
  // Grupos destinatarios
  // ---------------------------------------------------------------------------

  function renderGroupCheckboxes(containerId, selected) {
    const chosen = Array.isArray(selected) ? selected : ["ALL"];
    const known = Core.TARGET_GROUPS.map((g) => g.value);
    const options = Core.TARGET_GROUPS.slice();
    // Grupos existentes fuera del catalogo se conservan para no perderlos al editar
    chosen.filter((g) => !known.includes(g)).forEach((g) => options.push({ value: g, label: g }));
    $(containerId).innerHTML = options
      .map(
        (g) =>
          `<label class="ed-check"><input type="checkbox" value="${Core.escapeHtml(g.value)}"${
            chosen.includes(g.value) ? " checked" : ""
          }> ${Core.escapeHtml(g.label)}</label>`
      )
      .join("");
  }

  function readGroups(containerId) {
    return Array.from($(containerId).querySelectorAll("input[type=checkbox]:checked")).map((el) => el.value);
  }

  // ---------------------------------------------------------------------------
  // Noticias
  // ---------------------------------------------------------------------------

  function readNewsForm() {
    return {
      title: $("ed-news-title").value,
      teaser: $("ed-news-teaser").value,
      content: $("ed-news-content").value,
      category: $("ed-news-category").value,
      targetGroups: readGroups("ed-news-groups"),
      urgent: document.querySelector('input[name="ed-news-urgency"]:checked').value === "urgent",
      pinned: $("ed-news-pinned").checked,
      imageUrl: state.dropzones.news.getUrl(),
      expiresAt: $("ed-news-expires").value,
    };
  }

  function fillNewsForm(values, id) {
    $("ed-news-id").value = id || "";
    $("ed-news-title").value = values.title;
    $("ed-news-teaser").value = values.teaser;
    $("ed-news-content").value = values.content;
    $("ed-news-category").value = values.category;
    renderGroupCheckboxes("ed-news-groups", values.targetGroups);
    document.querySelector(`input[name="ed-news-urgency"][value="${values.urgent ? "urgent" : "normal"}"]`).checked = true;
    $("ed-news-pinned").checked = values.pinned;
    $("ed-news-expires").value = values.expiresAt || "";
    state.dropzones.news.reset();
    if (values.imageUrl) state.dropzones.news.setUrl(values.imageUrl);
    const editing = Boolean(id);
    $("ed-news-form-title").textContent = editing ? `Editar noticia #${id}` : "Nueva noticia";
    $("ed-news-submit").textContent = editing ? "Guardar cambios" : "Publicar noticia";
    $("ed-news-cancel").classList.toggle("hidden", !editing);
    showFieldErrors("news", {});
  }

  function resetNewsForm() {
    fillNewsForm(
      { title: "", teaser: "", content: "", category: "", targetGroups: ["ALL"], urgent: false, pinned: false, imageUrl: "" },
      ""
    );
  }

  async function loadNews() {
    const tbody = $("ed-news-rows");
    tbody.innerHTML = `<tr><td colspan="5" class="ed-empty">Cargando noticias...</td></tr>`;
    try {
      state.news = (await getClient().listNews()) || [];
      tbody.innerHTML = Core.renderNewsRows(state.news);
    } catch (error) {
      tbody.innerHTML = `<tr><td colspan="5" class="ed-empty">${Core.escapeHtml(Core.describeError(error))}</td></tr>`;
    }
  }

  async function submitNews(event) {
    event.preventDefault();
    const values = readNewsForm();
    const errors = Core.validateNewsValues(values);
    showFieldErrors("news", errors);
    if (Object.keys(errors).length > 0) return;
    if (state.dropzones.news.uploading) {
      showNotice("warning", "Espere a que termine la carga del archivo antes de publicar.");
      return;
    }

    const id = $("ed-news-id").value;
    const mode = id ? "update" : "create";
    if (mode === "create" && values.urgent) {
      const ok = window.confirm(
        "Una Eilmeldung envía una notificación push inmediata a los grupos seleccionados. ¿Desea publicarla?"
      );
      if (!ok) return;
    }

    const button = $("ed-news-submit");
    setBusy(button, true, "Guardando...");
    try {
      const payload = Core.buildNewsPayload(values, mode);
      const saved = id ? await getClient().updateNews(id, payload) : await getClient().createNews(payload);
      showNotice("success", id ? `Noticia #${saved.id} actualizada.` : `Noticia publicada (ID ${saved.id}).`);
      resetNewsForm();
      await loadNews();
    } catch (error) {
      showNotice("error", Core.describeError(error));
    } finally {
      setBusy(button, false);
    }
  }

  async function deleteNews(id) {
    const item = state.news.find((n) => String(n.id) === String(id));
    if (!window.confirm(`¿Eliminar definitivamente la noticia "${item ? item.title : id}"?`)) return;
    try {
      await getClient().deleteNews(id);
      showNotice("success", `Noticia #${id} eliminada.`);
      if ($("ed-news-id").value === String(id)) resetNewsForm();
      await loadNews();
    } catch (error) {
      showNotice("error", Core.describeError(error));
    }
  }

  function editNews(id) {
    const item = state.news.find((n) => String(n.id) === String(id));
    if (!item) return;
    fillNewsForm(Core.newsToFormValues(item), item.id);
    $("ed-form-news").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---------------------------------------------------------------------------
  // Eventos
  // ---------------------------------------------------------------------------

  function readEventForm() {
    return {
      title: $("ed-event-title").value,
      description: $("ed-event-description").value,
      location: $("ed-event-location").value,
      date: $("ed-event-date").value,
      startTime: $("ed-event-start").value,
      endTime: $("ed-event-end").value,
      targetGroups: readGroups("ed-event-groups"),
      rsvp: $("ed-event-rsvp").checked,
      imageUrl: state.dropzones.event.getUrl(),
    };
  }

  function fillEventForm(values, id) {
    $("ed-event-id").value = id || "";
    $("ed-event-title").value = values.title;
    $("ed-event-description").value = values.description;
    $("ed-event-location").value = values.location;
    $("ed-event-date").value = values.date;
    $("ed-event-start").value = values.startTime;
    $("ed-event-end").value = values.endTime;
    renderGroupCheckboxes("ed-event-groups", values.targetGroups);
    $("ed-event-rsvp").checked = values.rsvp;
    state.dropzones.event.reset();
    if (values.imageUrl) state.dropzones.event.setUrl(values.imageUrl);
    const editing = Boolean(id);
    $("ed-event-form-title").textContent = editing ? `Editar evento #${id}` : "Nuevo evento";
    $("ed-event-submit").textContent = editing ? "Guardar cambios" : "Crear evento";
    $("ed-event-cancel").classList.toggle("hidden", !editing);
    showFieldErrors("event", {});
  }

  function resetEventForm() {
    fillEventForm(
      {
        title: "",
        description: "",
        location: "",
        date: "",
        startTime: "",
        endTime: "",
        targetGroups: ["ALL"],
        rsvp: false,
        imageUrl: "",
      },
      ""
    );
  }

  async function loadEvents() {
    const tbody = $("ed-event-rows");
    tbody.innerHTML = `<tr><td colspan="5" class="ed-empty">Cargando eventos...</td></tr>`;
    try {
      const includePast = $("ed-events-include-past").checked;
      state.events = (await getClient().listEvents({ upcoming_only: !includePast })) || [];
      tbody.innerHTML = Core.renderEventRows(state.events);
    } catch (error) {
      tbody.innerHTML = `<tr><td colspan="5" class="ed-empty">${Core.escapeHtml(Core.describeError(error))}</td></tr>`;
    }
  }

  async function submitEvent(event) {
    event.preventDefault();
    const values = readEventForm();
    const errors = Core.validateEventValues(values);
    showFieldErrors("event", errors);
    if (Object.keys(errors).length > 0) return;
    if (state.dropzones.event.uploading) {
      showNotice("warning", "Espere a que termine la carga del archivo antes de guardar.");
      return;
    }

    const id = $("ed-event-id").value;
    const button = $("ed-event-submit");
    setBusy(button, true, "Guardando...");
    try {
      const payload = Core.buildEventPayload(values);
      const saved = id ? await getClient().updateEvent(id, payload) : await getClient().createEvent(payload);
      showNotice("success", id ? `Evento #${saved.id} actualizado.` : `Evento creado (ID ${saved.id}).`);
      resetEventForm();
      await loadEvents();
      if (state.participantsEventId && String(state.participantsEventId) === String(saved.id)) {
        showParticipants(saved.id);
      }
    } catch (error) {
      showNotice("error", Core.describeError(error));
    } finally {
      setBusy(button, false);
    }
  }

  async function deleteEvent(id) {
    const item = state.events.find((e) => String(e.id) === String(id));
    if (!window.confirm(`¿Eliminar el evento "${item ? item.title : id}" y todas sus inscripciones?`)) return;
    try {
      await getClient().deleteEvent(id);
      showNotice("success", `Evento #${id} eliminado.`);
      if ($("ed-event-id").value === String(id)) resetEventForm();
      if (String(state.participantsEventId) === String(id)) hideParticipants();
      await loadEvents();
    } catch (error) {
      showNotice("error", Core.describeError(error));
    }
  }

  function editEvent(id) {
    const item = state.events.find((e) => String(e.id) === String(id));
    if (!item) return;
    fillEventForm(Core.eventToFormValues(item), item.id);
    $("ed-form-event").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function hideParticipants() {
    state.participantsEventId = null;
    const panel = $("ed-participants");
    panel.classList.add("hidden");
    panel.innerHTML = "";
  }

  async function showParticipants(id) {
    const panel = $("ed-participants");
    state.participantsEventId = id;
    panel.classList.remove("hidden");
    panel.innerHTML = `<p class="ed-empty">Cargando participantes...</p>`;
    try {
      const data = await getClient().getEventRegistrations(id);
      if (String(state.participantsEventId) !== String(id)) return; // se abrio otro evento entretanto
      panel.innerHTML = Core.renderParticipantsTable(data);
    } catch (error) {
      panel.innerHTML = `<p class="ed-empty">${Core.escapeHtml(Core.describeError(error))}</p>`;
      showNotice("error", Core.describeError(error));
    }
  }

  // ---------------------------------------------------------------------------
  // Sincronizacion con Instagram
  // ---------------------------------------------------------------------------

  async function syncInstagram() {
    const button = $("ed-btn-sync");
    const statusEl = $("ed-sync-status");
    setBusy(button, true, "Sincronizando...");
    statusEl.textContent = "Consultando Instagram...";
    try {
      const result = await getClient().syncInstagram();
      const summary = Core.describeSyncResult(result);
      showNotice(summary.type, summary.message);
      statusEl.textContent = `Última sincronización: ${new Date().toLocaleTimeString("es-PY", {
        hour: "2-digit",
        minute: "2-digit",
      })}`;
      if (state.panel === "news") await loadNews();
    } catch (error) {
      statusEl.textContent = "Sincronización fallida";
      showNotice("error", Core.describeError(error));
    } finally {
      setBusy(button, false);
    }
  }

  // ---------------------------------------------------------------------------
  // Inicializacion
  // ---------------------------------------------------------------------------

  function bindTableActions(tbodyId, handlers) {
    $(tbodyId).addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      const handler = handlers[button.getAttribute("data-action")];
      if (handler) handler(button.getAttribute("data-id"));
    });
  }

  function initOnce() {
    if (state.ready) return;
    state.ready = true;

    $("ed-news-category").innerHTML =
      `<option value="">Sin categoría</option>` +
      Core.CATEGORIES.map((c) => `<option value="${Core.escapeHtml(c.value)}">${Core.escapeHtml(c.label)}</option>`).join("");

    document.querySelectorAll("[data-dropzone]").forEach(bindDropzone);
    resetNewsForm();
    resetEventForm();

    $("mode-btn-editorial").addEventListener("click", () => applyMode("editorial"));
    $("mode-btn-student").addEventListener("click", () => applyMode("student"));
    $("ed-tab-news").addEventListener("click", () => applyPanel("news"));
    $("ed-tab-events").addEventListener("click", () => applyPanel("events"));

    $("ed-form-news").addEventListener("submit", submitNews);
    $("ed-news-cancel").addEventListener("click", resetNewsForm);
    $("ed-news-reload").addEventListener("click", loadNews);
    bindTableActions("ed-news-rows", { "edit-news": editNews, "delete-news": deleteNews });

    $("ed-form-event").addEventListener("submit", submitEvent);
    $("ed-event-cancel").addEventListener("click", resetEventForm);
    $("ed-events-reload").addEventListener("click", loadEvents);
    $("ed-events-include-past").addEventListener("change", loadEvents);
    bindTableActions("ed-event-rows", {
      "edit-event": editEvent,
      "delete-event": deleteEvent,
      "participants-event": showParticipants,
    });

    $("ed-btn-sync").addEventListener("click", syncInstagram);
  }

  const UpaCockpit = {
    /**
     * Registra como obtener el token de sesion y que hacer cuando expira (HTTP 401).
     * Opcionales: baseUrl, timeoutMs y uploadTimeoutMs del cliente REST.
     */
    configure(config) {
      state.config = { ...state.config, ...config };
      state.client = null;
    },

    /** Se invoca tras validar la sesion: muestra el cockpit solo a administradores y redaccion. */
    onUserLoaded(user) {
      state.allowed = EDITOR_ROLES.includes(String((user && user.role) || "").toLowerCase());
      $("mode-switch").classList.toggle("hidden", !state.allowed);
      if (!state.allowed) {
        applyMode("student");
        return;
      }
      initOnce();
      let stored = null;
      try {
        stored = localStorage.getItem(MODE_STORAGE_KEY);
      } catch (_) {
        stored = null;
      }
      applyMode(stored === "student" ? "student" : "editorial");
    },

    /** Oculta el cockpit y descarta el estado al cerrar sesion. */
    reset() {
      state.allowed = false;
      state.news = [];
      state.events = [];
      state.participantsEventId = null;
      const switcher = $("mode-switch");
      if (switcher) switcher.classList.add("hidden");
      const editorial = $("view-editorial");
      if (editorial) editorial.classList.add("hidden");
      const student = $("student-workspace");
      if (student) student.classList.remove("hidden");
    },
  };

  window.UpaCockpit = UpaCockpit;
})();
