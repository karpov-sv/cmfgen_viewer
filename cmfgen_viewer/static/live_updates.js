/* Shared SSE connection for navigation and all runtime panels on this page. */
(function () {
  "use strict";
  if (!window.EventSource) return;
  const endpoint = document.currentScript.dataset.eventsUrl;
  const listeners = new Map();
  let source = null;
  let connectTimer = null;
  let ready = document.readyState !== "loading";

  function dispatch(topic, payload) {
    (listeners.get(topic) || []).forEach(callback => callback(payload));
  }

  function close() {
    if (connectTimer !== null) window.clearTimeout(connectTimer);
    connectTimer = null;
    const previous = source;
    source = null;
    if (previous) previous.close();
  }

  function connect() {
    close();
    if (document.hidden || !ready) return;
    const url = new URL(endpoint, window.location.href);
    for (const topic of listeners.keys()) {
      if (topic.startsWith("runtime:")) url.searchParams.append("runtime", topic.slice(8));
    }
    const stream = new EventSource(url.href);
    source = stream;
    stream.onopen = () => {
      if (source === stream) dispatch("connection", true);
    };
    stream.onerror = () => {
      // EventSource reconnects automatically; consumers can use their JSON
      // fallback until a fresh stream and initial snapshots arrive.
      if (source === stream) dispatch("connection", false);
    };
    for (const event of ["tasks", "runtime", "runtime-error"]) {
      stream.addEventListener(event, message => {
        if (source !== stream) return;
        try {
          const payload = JSON.parse(message.data);
          if (event === "tasks") dispatch("tasks", payload);
          else if (event === "runtime") dispatch("runtime:" + payload.key, payload.runtime);
          else dispatch("runtime-error:" + payload.key, payload);
        } catch (_error) {
          dispatch("connection", false);
        }
      });
    }
  }

  window.CmfgenLiveUpdates = {
    subscribe(topic, callback) {
      if (!listeners.has(topic)) listeners.set(topic, []);
      listeners.get(topic).push(callback);
      // Collect subscriptions from the navigation and deferred runtime script
      // before opening a single connection.
      if (connectTimer !== null) window.clearTimeout(connectTimer);
      if (ready) connectTimer = window.setTimeout(connect, 0);
    }
  };
  document.addEventListener("DOMContentLoaded", () => {
    ready = true;
    connect();
  }, {once: true});
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) close();
    else connect();
  });
  window.addEventListener("pagehide", close);
  window.addEventListener("pageshow", event => {
    if (event.persisted) connect();
  });
})();
