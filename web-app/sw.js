/**
 * Service Worker de UPA Campus PWA.
 *
 * Precachea el shell estatico (HTML, CSS, JS, iconos) para que la aplicacion abra incluso sin red.
 * Las respuestas de /api/* nunca se guardan aqui (pueden ser privadas); la app las gestiona por usuario
 * y las borra al cerrar sesion.
 */
"use strict";

const VERSION = "1.0.6";
const SHELL_CACHE = `upa-campus-shell-${VERSION}`;
const FIREBASE_APP_COMPAT_URL = "https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js";
const FIREBASE_MESSAGING_COMPAT_URL = "https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js";
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
const DEFAULT_NOTIFICATION_ICON = "/campus/icons/transparent-pixel.png";
const DEFAULT_NOTIFICATION_BADGE = "/campus/icons/badge-monochrome.png";

if (typeof importScripts === "function") {
  try {
    importScripts(FIREBASE_APP_COMPAT_URL, FIREBASE_MESSAGING_COMPAT_URL);
  } catch (_) {
    /* En modo sin conexion el Service Worker mantiene el soporte push nativo */
  }
}
const SHELL_FILES = [
  "/",
  "/manifest.webmanifest",
  "/campus/campus.css?v=1.0.6",
  "/campus/campus-core.js?v=1.0.6",
  "/campus/vendor/qrcode.js?v=1.0.6",
  "/campus/campus.js?v=1.0.6",
  "/campus/icons/favicon.svg",
  "/campus/icons/favicon-32.png",
  "/campus/icons/apple-touch-icon.png",
  "/campus/icons/icon-192.png",
  "/campus/icons/icon-512.png",
  "/campus/icons/icon-maskable-512.png",
  "/campus/icons/badge-monochrome.png",
  "/campus/icons/transparent-pixel.png",
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

function isFallbackNotificationIcon(url) {
  return /\/campus\/icons\/(?:icon-\d+|icon-maskable-\d+|apple-touch-icon|favicon-32)\.png(\?|#|$)/i.test(
    String(url || "").trim(),
  );
}

function extractPostIdFromUrl(url) {
  const m = /(?:^|[?&])post=([^&#]+)/.exec(String(url || ""));
  return m ? decodeURIComponent(m[1]).trim() : "";
}

function toRelativeAppUrl(pathOrUrl, postId) {
  const raw = String(pathOrUrl || "").trim();
  if (raw) {
    try {
      const parsed = new URL(raw, self.location.origin);
      if (parsed.origin === self.location.origin) {
        return `${parsed.pathname || "/"}${parsed.search || ""}${parsed.hash || ""}`;
      }
      return parsed.href;
    } catch (_) {
      return raw.startsWith("/") ? raw : `/${raw}`;
    }
  }
  return postId ? `/?post=${encodeURIComponent(postId)}` : "/";
}

function toAbsoluteAppUrl(pathOrUrl, postId) {
  const relative = toRelativeAppUrl(pathOrUrl, postId);
  try {
    return new URL(relative, self.location.origin).href;
  } catch (_) {
    return relative;
  }
}

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
  } else if (event && typeof event === "object" && (event.notification || event.data || event.fcmOptions || event.webpush)) {
    raw = event;
  }
  if (raw && typeof raw.FCM_MSG === "object" && raw.FCM_MSG) {
    raw = raw.FCM_MSG;
  }
  const webpush = (raw && typeof raw.webpush === "object" && raw.webpush) || {};
  const webpushNotif = (webpush && typeof webpush.notification === "object" && webpush.notification) || {};
  const webpushFcmOptions = (webpush && typeof webpush.fcm_options === "object" && webpush.fcm_options) || {};
  const notification = (raw && typeof raw.notification === "object" && raw.notification) || {};
  const data = (raw && typeof raw.data === "object" && raw.data) || {};
  const fcmOptions = (raw && typeof raw.fcmOptions === "object" && raw.fcmOptions) || {};
  const title =
    String(notification.title || webpushNotif.title || data.title || raw.title || "UPA Campus").trim() || "UPA Campus";
  const rawBody = String(notification.body || webpushNotif.body || data.body || raw.body || "").trim();
  const body = rawBody.toLowerCase() === title.toLowerCase() ? "" : rawBody;
  const rawIcon = String(
    notification.icon ||
      notification.image ||
      webpushNotif.icon ||
      webpushNotif.image ||
      data.icon ||
      data.image ||
      raw.icon ||
      raw.image ||
      "",
  ).trim();
  const icon = !rawIcon || isFallbackNotificationIcon(rawIcon) ? DEFAULT_NOTIFICATION_ICON : rawIcon;
  const rawBadge = String(
    notification.badge || webpushNotif.badge || data.badge || raw.badge || DEFAULT_NOTIFICATION_BADGE,
  ).trim();
  const badge = !rawBadge || isFallbackNotificationIcon(rawBadge) ? DEFAULT_NOTIFICATION_BADGE : rawBadge;
  const rawLink =
    data.url ||
    fcmOptions.link ||
    webpushFcmOptions.link ||
    notification.click_action ||
    webpushNotif.click_action ||
    raw.url ||
    "";
  const postId = String(data.post_id || raw.post_id || extractPostIdFromUrl(rawLink) || "").trim();
  const deepLink = toRelativeAppUrl(rawLink, postId);
  const tag = String(notification.tag || data.tag || (postId ? `post:${postId}` : "upa-campus-push"));
  const options = {
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
  };
  return { title, options };
}

function showCampusNotification(payloadOrEvent) {
  const { title, options } = parsePushPayload(payloadOrEvent);
  return self.registration && typeof self.registration.showNotification === "function"
    ? self.registration.showNotification(title, options)
    : Promise.resolve();
}

function resolveNotificationClickTarget(notification) {
  const rawData = (notification && notification.data) || {};
  const fcmMsg = (rawData && typeof rawData.FCM_MSG === "object" && rawData.FCM_MSG) || {};
  const fcmData = (fcmMsg && typeof fcmMsg.data === "object" && fcmMsg.data) || {};
  const fcmOptions = (fcmMsg && typeof fcmMsg.fcmOptions === "object" && fcmMsg.fcmOptions) || {};
  const webpush = (fcmMsg && typeof fcmMsg.webpush === "object" && fcmMsg.webpush) || {};
  const webpushFcmOptions = (webpush && typeof webpush.fcm_options === "object" && webpush.fcm_options) || {};
  const tagPostId =
    notification && typeof notification.tag === "string" && /^post:(\d+)$/.test(notification.tag)
      ? notification.tag.slice(5)
      : "";
  const rawUrl =
    rawData.url ||
    fcmData.url ||
    fcmOptions.link ||
    webpushFcmOptions.link ||
    (tagPostId ? `/?post=${tagPostId}` : "");
  const postId = String(
    rawData.post_id || fcmData.post_id || extractPostIdFromUrl(rawUrl) || tagPostId || "",
  ).trim();
  const targetUrl = toRelativeAppUrl(rawUrl, postId);
  const absoluteUrl = toAbsoluteAppUrl(targetUrl, postId);
  return { targetUrl, absoluteUrl, postId: postId || null };
}

self.addEventListener("push", (event) => {
  if (event && typeof event.stopImmediatePropagation === "function") {
    event.stopImmediatePropagation();
  }
  const showPromise = showCampusNotification(event);
  if (event && typeof event.waitUntil === "function") {
    event.waitUntil(showPromise);
  }
});

self.addEventListener("notificationclick", (event) => {
  if (event && typeof event.stopImmediatePropagation === "function") {
    event.stopImmediatePropagation();
  }
  if (event.notification && typeof event.notification.close === "function") {
    event.notification.close();
  }
  const { targetUrl, absoluteUrl, postId } = resolveNotificationClickTarget(event.notification);
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(async (list) => {
      const appClients = (list || []).filter((c) => {
        if (!c || !c.url) return true;
        try {
          const u = new URL(c.url, self.location.origin);
          return u.origin === self.location.origin && !u.pathname.startsWith("/dashboard");
        } catch (_) {
          return true;
        }
      });
      const visibleClient =
        appClients.find((c) => c && c.visibilityState === "visible") ||
        (list || []).find((c) => c && c.visibilityState === "visible") ||
        null;
      if (visibleClient) {
        if (typeof visibleClient.postMessage === "function") {
          try {
            visibleClient.postMessage({
              type: "NOTIFICATION_CLICK",
              url: targetUrl || "/",
              post_id: postId,
            });
          } catch (_) {
            /* ignorar si el cliente no acepta postMessage */
          }
        }
        let focused = false;
        let activeClient = visibleClient;
        if (typeof visibleClient.focus === "function") {
          try {
            const candidate = await visibleClient.focus();
            activeClient = candidate || visibleClient;
            focused = Boolean(
              activeClient && activeClient.focused !== false && activeClient.visibilityState === "visible",
            );
          } catch (_) {
            focused = false;
          }
        }
        if (targetUrl && targetUrl !== "/" && typeof activeClient.navigate === "function") {
          try {
            const navClient = await activeClient.navigate(targetUrl);
            if (navClient) activeClient = navClient;
          } catch (_) {
            /* Si navigate no esta permitido, postMessage o openWindow abre el detalle */
          }
        }
        if (focused) {
          return activeClient;
        }
      }
      if (self.clients && typeof self.clients.openWindow === "function") {
        return self.clients.openWindow(absoluteUrl || targetUrl || "/");
      }
      return visibleClient || appClients[0] || (list && list[0]) || undefined;
    }),
  );
});

if (typeof firebase !== "undefined" && firebase && typeof firebase.initializeApp === "function") {
  try {
    if (!firebase.apps || !firebase.apps.length) {
      firebase.initializeApp(firebaseConfig);
    }
    if (typeof firebase.messaging === "function") {
      const messaging = firebase.messaging();
      if (messaging && typeof messaging.onBackgroundMessage === "function") {
        messaging.onBackgroundMessage((payload) => showCampusNotification({ data: payload }));
      }
    }
  } catch (_) {
    /* Firebase Messaging se sincroniza cuando el entorno del navegador lo permite */
  }
}
