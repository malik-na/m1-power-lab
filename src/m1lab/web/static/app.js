(() => {
  "use strict";

  const connection = document.querySelector("#connection-state");
  const updateStrip = document.querySelector("#update-strip");
  const updateMessage = document.querySelector("#update-message");
  const toast = document.querySelector("#command-toast");
  const currentView = document.body.dataset.view || "overview";
  const sessionId = document.body.dataset.sessionId || "none";
  const cursorKey = `m1lab:event-cursor:${sessionId}:${currentView}`;
  let lastEventAt = Date.now();
  let toastTimer;
  let eventSource = null;

  function cookie(name) {
    const entry = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
    return entry ? decodeURIComponent(entry.slice(name.length + 1)) : "";
  }

  function setConnection(state, label) {
    if (!connection) return;
    connection.className = `connection-pill is-${state}`;
    connection.querySelector("span:last-child").textContent = label;
  }

  function showToast(message, error = false) {
    if (!toast) return;
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.toggle("is-error", error);
    toast.hidden = false;
    toastTimer = setTimeout(() => { toast.hidden = true; }, 5500);
  }

  async function submitCommand({ kind, expectedRevision, targetId = null, payload = {}, commandId = null }) {
    const response = await fetch("/api/commands", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": cookie("m1lab_csrf"),
      },
      body: JSON.stringify({
        command_id: commandId || crypto.randomUUID(),
        kind,
        expected_revision: expectedRevision || document.querySelector('meta[name="m1lab-revision"]').content,
        target_id: targetId,
        payload,
      }),
    });
    const result = await response.json().catch(() => ({ detail: "Invalid coordinator response." }));
    if (!response.ok) throw Object.assign(new Error(result.message || result.detail || "Command rejected."), { result });
    return result;
  }

  document.querySelectorAll(".command-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;
      const button = form.querySelector('button[type="submit"]');
      const formData = new FormData(form);
      const payload = Object.fromEntries(formData.entries());
      form.dataset.commandId ||= crypto.randomUUID();
      button.disabled = true;
      try {
        const receipt = await submitCommand({
          kind: form.dataset.commandKind,
          expectedRevision: form.dataset.expectedRevision,
          targetId: form.dataset.targetId || null,
          payload,
          commandId: form.dataset.commandId,
        });
        showToast(`${receipt.status}: ${receipt.message}`);
        delete form.dataset.commandId;
        form.reset();
        updateStrip.hidden = false;
        updateMessage.textContent = "Command recorded. Refresh to see authoritative state.";
      } catch (error) {
        showToast(error.message || "Command could not be submitted.", true);
      } finally {
        button.disabled = false;
      }
    });
  });

  document.querySelector("#refresh-state")?.addEventListener("click", () => window.location.reload());

  function connectEvents() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    if (!navigator.onLine) {
      setConnection("offline", "Offline");
      return;
    }
    const cursor = localStorage.getItem(cursorKey);
    const source = new EventSource(`/api/events${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`);
    eventSource = source;
    setConnection("connecting", "Connecting");
    source.onopen = () => {
      lastEventAt = Date.now();
      setConnection("live", "Live");
    };
    source.onmessage = (event) => {
      lastEventAt = Date.now();
      setConnection("live", "Live");
      if (event.lastEventId) localStorage.setItem(cursorKey, event.lastEventId);
      let data = {};
      try { data = JSON.parse(event.data); } catch (_) { return; }
      if (data.kind === "heartbeat") return;
      updateStrip.hidden = false;
      updateMessage.textContent = data.kind === "snapshot_required"
        ? "Live history has a gap. Refresh the current snapshot."
        : (data.payload?.summary || "New coordinator state is available.");
    };
    source.onerror = () => {
      setConnection(navigator.onLine ? "stale" : "offline", navigator.onLine ? "Reconnecting" : "Offline");
    };
  }

  function pushKeyBytes(base64Url) {
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0));
  }

  async function updatePushControls() {
    const controls = document.querySelector("#push-controls");
    const enable = document.querySelector("#push-enable");
    const disable = document.querySelector("#push-disable");
    const status = document.querySelector("#push-status");
    if (!controls || !enable || !disable || !status) return;
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return;
    try {
      const response = await fetch("/api/push/config", { credentials: "same-origin", cache: "no-store" });
      const config = await response.json();
      if (!response.ok || !config.enabled || !config.public_key) return;
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      controls.hidden = false;
      enable.hidden = Boolean(subscription && config.enrolled);
      disable.hidden = !subscription || !config.enrolled;
      status.textContent = Notification.permission === "denied"
        ? "Notifications are blocked in browser settings."
        : (subscription && config.enrolled ? "Notifications are enabled." : "Notifications are off.");

      enable.onclick = async () => {
        enable.disabled = true;
        try {
          const permission = Notification.permission === "granted"
            ? "granted"
            : await Notification.requestPermission();
          if (permission !== "granted") {
            status.textContent = "Notification permission was not granted.";
            return;
          }
          const active = await registration.pushManager.getSubscription() || await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: pushKeyBytes(config.public_key),
          });
          const value = active.toJSON();
          const result = await fetch("/api/push/subscription", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": cookie("m1lab_csrf") },
            body: JSON.stringify({ endpoint: value.endpoint, keys: value.keys }),
          });
          if (!result.ok) throw new Error("The server could not save this subscription.");
          enable.hidden = true;
          disable.hidden = false;
          status.textContent = "Notifications are enabled.";
        } catch (error) {
          status.textContent = error.message || "Could not enable notifications.";
        } finally {
          enable.disabled = false;
        }
      };

      disable.onclick = async () => {
        disable.disabled = true;
        try {
          const active = await registration.pushManager.getSubscription();
          if (active) {
            const value = active.toJSON();
            const response = await fetch("/api/push/subscription", {
              method: "DELETE",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json", "X-CSRF-Token": cookie("m1lab_csrf") },
              body: JSON.stringify({ endpoint: value.endpoint, keys: value.keys }),
            });
            if (!response.ok) throw new Error("The server could not revoke this subscription.");
            await active.unsubscribe();
          }
          enable.hidden = false;
          disable.hidden = true;
          status.textContent = "Notifications are off.";
        } catch (error) {
          status.textContent = error.message || "Could not turn off notifications.";
        } finally {
          disable.disabled = false;
        }
      };
    } catch (_) {
      controls.hidden = true;
    }
  }

  window.addEventListener("online", connectEvents);
  window.addEventListener("offline", () => {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    setConnection("offline", "Offline");
  });
  setInterval(() => {
    if (navigator.onLine && Date.now() - lastEventAt > 30000) setConnection("stale", "Stale");
  }, 5000);

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/service-worker.js")
      .then(updatePushControls)
      .catch(() => {}));
  }
  connectEvents();
})();
