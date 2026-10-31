/**
 * Service Worker de UPA Campus PWA.
 *
 * Precachea el shell estatico (HTML, CSS, JS, iconos) para que la aplicacion abra incluso sin red.
 * Las respuestas de /api/* nunca se guardan aqui (pueden ser privadas); la app las gestiona por usuario
 * y las borra al cerrar sesion.
 */
"use strict";

const VERSION = "1.0.1";
const SHELL_CACHE = `upa-campus-shell-${VERSION}`;
const SHELL_FILES = [
  "/",
  "/manifest.webmanifest",
  "/campus/campus.css?v=1.0.0",
  "/campus/campus-core.js?v=1.0.0",
  "/campus/vendor/qrcode.js?v=1.0.0",
  "/campus/campus.js?v=1.0.0",
  "/campus/icons/upa-logo.png",
  "/campus/icons/favicon-32.png",
  "/campus/icons/apple-touch-icon.png",
  "/campus/icons/icon-192.png",
  "/campus/icons/icon-512.png",
  "/campus/icons/icon-maskable-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_FILES))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k.startsWith("upa-campus-") && k !== SHELL_CACHE).map((k) => caches.delete(k))),
      )
      .then(() => self.clients.claim()),
  );
});

function isCampusAsset(pathname) {
  return pathname === "/manifest.webmanifest" || pathname.startsWith("/campus/");
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
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(SHELL_CACHE).then((cache) => cache.put("/", copy));
          }
          return response;
        })
        .catch(() => caches.open(SHELL_CACHE).then((cache) => cache.match("/", { ignoreSearch: true }))),
    );
    return;
  }

  if (isCampusAsset(url.pathname)) {
    event.respondWith(
      caches.open(SHELL_CACHE).then(async (cache) => {
        const cached = await cache.match(request);
        try {
          const response = await fetch(request);
          if (response.ok) cache.put(request, response.clone());
          return response;
        } catch (_) {
          return cached;
        }
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
