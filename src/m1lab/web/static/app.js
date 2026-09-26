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
    if (!navigator.onLine) {
      setConnection("offline", "Offline");
      return;
    }
    const cursor = localStorage.getItem(cursorKey);
    const source = new EventSource(`/api/events${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`);
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

  window.addEventListener("online", () => { setConnection("connecting", "Connecting"); });
  window.addEventListener("offline", () => setConnection("offline", "Offline"));
  setInterval(() => {
    if (navigator.onLine && Date.now() - lastEventAt > 30000) setConnection("stale", "Stale");
  }, 5000);

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/service-worker.js").catch(() => {}));
  }
  connectEvents();
})();
