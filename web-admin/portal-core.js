/**
 * Logica pura del Portal Institucional UPA (sin DOM): normalizacion de grupos de Google
 * Workspace y deteccion de sesion almacenada. Se usa en el navegador (window.UpaPortalCore)
 * y en las pruebas de Node.js (require).
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.UpaPortalCore = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const ACCESS_TOKEN_KEY = "upa_access_token";
  const LEGACY_TOKEN_KEY = "upa_auth_token";

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /**
   * La API devuelve cada grupo como objeto {id, name, email, description}; las etiquetas
   * logicas (ALL, TIE...) llegan como texto. Ambas formas se reducen al mismo objeto.
   */
  function normalizeGoogleGroup(group) {
    if (group == null) return null;
    if (typeof group === "object") {
      const name = String(group.name || "").trim();
      const email = String(group.email || "").trim();
      if (!name && !email) return null;
      return {
        id: String(group.id || ""),
        name: name || email,
        email,
        description: String(group.description || "").trim(),
      };
    }
    const text = String(group).trim();
    return text ? { id: "", name: text, email: "", description: "" } : null;
  }

  function normalizeGoogleGroups(groups) {
    if (!Array.isArray(groups)) return [];
    return groups.map(normalizeGoogleGroup).filter(Boolean);
  }

  /**
   * Grupos reales de Google Workspace del perfil. Si el backend solo entrega etiquetas
   * (campo `groups`), se omiten las etiquetas sinteticas internas (ALL, TIE).
   */
  function groupsFromUser(user) {
    const detailed = normalizeGoogleGroups(user && user.google_groups);
    if (detailed.length > 0) return detailed;
    const tags = Array.isArray(user && user.groups) ? user.groups : [];
    return normalizeGoogleGroups(tags.filter((g) => g !== "ALL" && g !== "TIE"));
  }

  function renderGroupBadges(groups) {
    return normalizeGoogleGroups(groups)
      .map((g) => {
        const title = g.description || g.email || g.name;
        const email = g.email
          ? `<span class="group-badge-email">${escapeHtml(g.email)}</span>`
          : "";
        return (
          `<span class="group-badge" title="${escapeHtml(title)}">` +
          `<span class="group-badge-name">${escapeHtml(g.name)}</span>${email}</span>`
        );
      })
      .join("");
  }

  /** Hay sesion almacenada o un token entrante en la URL (retorno del flujo OAuth). */
  function hasStoredSession(storage, search) {
    let stored = null;
    try {
      stored = storage && storage.getItem(ACCESS_TOKEN_KEY);
    } catch (_) {
      stored = null;
    }
    if (stored) return true;
    return /[?&]token=[^&]+/.test(String(search || ""));
  }

  return {
    ACCESS_TOKEN_KEY,
    LEGACY_TOKEN_KEY,
    escapeHtml,
    normalizeGoogleGroup,
    normalizeGoogleGroups,
    groupsFromUser,
    renderGroupBadges,
    hasStoredSession,
  };
});
