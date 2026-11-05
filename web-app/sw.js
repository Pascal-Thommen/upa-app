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
const firebaseConfig = {
  apiKey: "AIzaSyCvDxaM-b3uIS1s-yStQuX9yVONSwD1RCo",
  authDomain: "upa-campus-app.firebaseapp.com",
  projectId: "upa-campus-app",
  storageBucket: "upa-campus-app.firebasestorage.app",
  messagingSenderId: "872606189485",
  appId: "1:872606189485:web:a919d0acc99c6197614324",
};
const VAPID_PUBLIC_KEY =
  "BNfsctw3qDvmsunaO45-JUwRouboQWtn4zXAyr5ejvVYt7ZipU_VLWozAsrlFPo2nXXMNFYLMH1k_RrSqSz-Lj8";
const DEFAULT_NOTIFICATION_ICON = "/campus/icons/icon-192.png";
const DEFAULT_NOTIFICATION_BADGE = "/campus/icons/favicon-32.png";
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

function parsePushPayload(event) {
  let raw = {};
  if (event && event.data) {
    try {
      if (typeof event.data.json === "function") {
        raw = event.data.json() || {};
      } else if (typeof event.data.text === "function") {
        raw = JSON.parse(event.data.text() || "{}");
      } else if (typeof event.data === "object") {
        raw = event.data;
      }
    } catch (_) {
      const text = typeof event.data.text === "function" ? String(event.data.text() || "").trim() : "";
      raw = text ? { notification: { title: "UPA Campus", body: text } } : {};
    }
  }
  const notification = (raw && typeof raw.notification === "object" && raw.notification) || {};
  const data = (raw && typeof raw.data === "object" && raw.data) || {};
  const title = String(notification.title || data.title || raw.title || "UPA Campus").trim() || "UPA Campus";
  const body = String(notification.body || data.body || raw.body || "").trim();
  const icon = String(notification.icon || data.icon || raw.icon || DEFAULT_NOTIFICATION_ICON).trim();
  const badge = String(notification.badge || data.badge || raw.badge || DEFAULT_NOTIFICATION_BADGE).trim();
  const postId = data.post_id || raw.post_id || "";
  const deepLink =
    data.url ||
    notification.click_action ||
    raw.url ||
    (postId ? `/?post=${encodeURIComponent(String(postId))}` : "/");
  const tag = String(notification.tag || data.tag || (postId ? `post:${postId}` : "upa-campus-push"));
  return {
    title,
    options: {
      body,
      icon,
      badge,
      tag,
      data: {
        ...data,
        projectId: firebaseConfig.projectId,
        vapidKey: VAPID_PUBLIC_KEY,
        url: deepLink,
        post_id: postId ? String(postId) : undefined,
      },
    },
  };
}

self.addEventListener("push", (event) => {
  const { title, options } = parsePushPayload(event);
  const showPromise =
    self.registration && typeof self.registration.showNotification === "function"
      ? self.registration.showNotification(title, options)
      : Promise.resolve();
  if (event && typeof event.waitUntil === "function") {
    event.waitUntil(showPromise);
  }
});

self.addEventListener("notificationclick", (event) => {
  if (event.notification && typeof event.notification.close === "function") {
    event.notification.close();
  }
  const notifData = (event.notification && event.notification.data) || {};
  const targetUrl =
    notifData.url ||
    (notifData.post_id ? `/?post=${encodeURIComponent(String(notifData.post_id))}` : "/");
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      if (list.length > 0 && "focus" in list[0]) {
        const client = list[0];
        if (targetUrl && targetUrl !== "/" && typeof client.navigate === "function") {
          return client.navigate(targetUrl).then(() => client.focus());
        }
        if (targetUrl && targetUrl !== "/" && typeof client.postMessage === "function") {
          client.postMessage({ type: "NOTIFICATION_CLICK", url: targetUrl, post_id: notifData.post_id || null });
        }
        return client.focus();
      }
      return self.clients.openWindow(targetUrl || "/");
    }),
  );
});
