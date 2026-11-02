/**
 * Service Worker de UPA Campus PWA.
 *
 * Precachea el shell estatico (HTML, CSS, JS, iconos) para que la aplicacion abra incluso sin red.
 * Las respuestas de /api/* nunca se guardan aqui (pueden ser privadas); la app las gestiona por usuario
 * y las borra al cerrar sesion.
 */
"use strict";

const VERSION = "1.0.3";
const SHELL_CACHE = `upa-campus-shell-${VERSION}`;
const SHELL_FILES = [
  "/",
  "/manifest.webmanifest",
  "/campus/campus.css?v=1.0.3",
  "/campus/campus-core.js?v=1.0.3",
  "/campus/vendor/qrcode.js?v=1.0.3",
  "/campus/campus.js?v=1.0.3",
  "/campus/icons/favicon.svg",
  "/campus/icons/favicon-32.png",
  "/campus/icons/apple-touch-icon.png",
  "/campus/icons/icon-192.png",
  "/campus/icons/icon-512.png",
  "/campus/icons/icon-maskable-512.png",
];

async function precacheShell(cache) {
  if (typeof fetch === "function" && typeof cache.put === "function") {
    await Promise.all(
      SHELL_FILES.map(async (url) => {
        const response = await fetch(url, { cache: "no-cache" });
        if (!response || !response.ok) {
          throw new Error(`No se pudo precachear ${url}`);
        }
        await cache.put(url, typeof response.clone === "function" ? response.clone() : response);
      }),
    );
    return;
  }
  if (typeof cache.addAll === "function") {
    await cache.addAll(SHELL_FILES);
  }
}

async function putAndInvalidateOldVersions(cache, request, response) {
  await cache.put(request, response);
  if (typeof cache.keys !== "function" || typeof cache.delete !== "function") return;
  const targetUrl = new URL(typeof request === "string" ? request : request.url, self.location.origin);
  const keys = await cache.keys();
  await Promise.all(
    keys
      .filter((entry) => {
        const entryUrl = new URL(typeof entry === "string" ? entry : entry.url, self.location.origin);
        return entryUrl.pathname === targetUrl.pathname && entryUrl.search !== targetUrl.search;
      })
      .map((entry) => cache.delete(entry)),
  );
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => precacheShell(cache))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

function isCampusAsset(pathname) {
  return pathname === "/manifest.webmanifest" || pathname.startsWith("/campus/");
}

function isShellCodeOrStyleAsset(pathname) {
  return (
    pathname === "/manifest.webmanifest" ||
    pathname.endsWith(".js") ||
    pathname.endsWith(".css") ||
    pathname.endsWith(".webmanifest")
  );
}

function isNavigationToApp(request, pathname) {
  return request.mode === "navigate" && (pathname === "/" || pathname === "/index.html");
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/dashboard")) return;

  if (isNavigationToApp(request, url.pathname)) {
    event.respondWith(
      caches.open(SHELL_CACHE).then(async (cache) => {
        try {
          const response = await fetch(request, { cache: "no-cache" });
          if (response && response.ok) {
            await cache.put("/", response.clone());
            return response;
          }
          const fallback = await cache.match("/", { ignoreSearch: true });
          return fallback || response;
        } catch (_) {
          return cache.match("/", { ignoreSearch: true });
        }
      }),
    );
    return;
  }

  if (isCampusAsset(url.pathname)) {
    if (isShellCodeOrStyleAsset(url.pathname)) {
      event.respondWith(
        caches.open(SHELL_CACHE).then(async (cache) => {
          const cached = (await cache.match(request)) || (await cache.match(url.pathname, { ignoreSearch: true }));
          try {
            const response = await fetch(request, { cache: "no-cache" });
            if (response && response.ok) {
              await putAndInvalidateOldVersions(cache, request, response.clone());
              return response;
            }
            return cached || response;
          } catch (_) {
            return cached;
          }
        }),
      );
      return;
    }

    event.respondWith(
      caches.open(SHELL_CACHE).then(async (cache) => {
        const cached = (await cache.match(request)) || (await cache.match(url.pathname, { ignoreSearch: true }));
        const networkFetch = fetch(request, { cache: "no-cache" })
          .then(async (response) => {
            if (response && response.ok) {
              await putAndInvalidateOldVersions(cache, request, response.clone());
            }
            return response;
          })
          .catch(() => cached);
        return cached || networkFetch;
      }),
    );
  }
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      if (list.length > 0 && "focus" in list[0]) return list[0].focus();
      return self.clients.openWindow("/");
    }),
  );
});
