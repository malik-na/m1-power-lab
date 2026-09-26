const SHELL_CACHE = "m1lab-shell-v2";
const SHELL = [
  "/static/app.css",
  "/static/app.js",
  "/static/icon.svg",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/apple-touch-icon.png",
  "/manifest.webmanifest"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== SHELL_CACHE).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isShell = event.request.method === "GET" && url.origin === self.location.origin &&
    (url.pathname.startsWith("/static/") || url.pathname === "/manifest.webmanifest");
  if (!isShell) return;
  event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
});

self.addEventListener("push", (event) => {
  let data = { title: "M1 Power Lab", body: "The workbench needs attention.", path: "/overview" };
  try { data = { ...data, ...event.data.json() }; } catch (_) {}
  if (!["/overview", "/approvals"].includes(data.path)) data.path = "/overview";
  event.waitUntil(self.registration.showNotification(data.title, {
    body: data.body,
    icon: "/static/icon-192.png",
    data: { path: data.path },
    tag: data.tag || "m1lab-update"
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const requested = event.notification.data?.path;
  const path = ["/overview", "/approvals"].includes(requested) ? requested : "/overview";
  event.waitUntil(clients.openWindow(path));
});
