/**
 * Lightweight HTMX interaction event logger.
 * Logs to browser console with structured categories.
 * Sends critical errors to the server audit endpoint.
 */
(function () {
  const LOG_PREFIX = "[PractAS]";
  function log(level, category, message, detail) {
    const entry = {
      t: new Date().toISOString(),
      level,
      category,
      message,
      detail: detail || null,
    };
    if (level === "ERROR") {
      console.error(LOG_PREFIX, JSON.stringify(entry));
    } else if (level === "WARN") {
      console.warn(LOG_PREFIX, JSON.stringify(entry));
    } else {
      console.info(LOG_PREFIX, JSON.stringify(entry));
    }
    if (level === "ERROR") {
      _sendToServer(entry);
    }
  }
  function _sendToServer(entry) {
    try {
      navigator.sendBeacon("/client-error-log", JSON.stringify(entry));
    } catch (_) {
      // sendBeacon not available - silent fail
    }
  }
  // -- HTMX lifecycle events -----------------------------------------------
  document.body.addEventListener("htmx:beforeRequest", function (evt) {
    log("INFO", "htmx.request", "Sending request", {
      url: evt.detail.requestConfig?.path,
      method: evt.detail.requestConfig?.verb,
    });
  });
  document.body.addEventListener("htmx:afterRequest", function (evt) {
    const status = evt.detail.xhr?.status;
    if (status && status >= 400) {
      log("ERROR", "htmx.response", "Request returned error status", {
        url: evt.detail.requestConfig?.path,
        status,
      });
    }
  });
  document.body.addEventListener("htmx:responseError", function (evt) {
    log("ERROR", "htmx.responseError", "HTMX response error", {
      url: evt.detail.requestConfig?.path,
      status: evt.detail.xhr?.status,
    });
  });
  document.body.addEventListener("htmx:sendError", function (evt) {
    log("ERROR", "htmx.sendError", "HTMX failed to send request (network?)", {
      url: evt.detail.requestConfig?.path,
    });
  });
  document.body.addEventListener("htmx:timeout", function (evt) {
    log("WARN", "htmx.timeout", "HTMX request timed out", {
      url: evt.detail.requestConfig?.path,
    });
  });
  document.body.addEventListener("htmx:swapError", function (evt) {
    log("ERROR", "htmx.swapError", "HTMX DOM swap failed", {
      target: evt.detail.target?.id,
    });
  });
  // -- Global JS error handler ---------------------------------------------
  window.addEventListener("error", function (evt) {
    log("ERROR", "js.unhandled", evt.message, {
      file: evt.filename,
      line: evt.lineno,
    });
  });
  window.addEventListener("unhandledrejection", function (evt) {
    log("ERROR", "js.promise", "Unhandled promise rejection", {
      reason: String(evt.reason),
    });
  });
  log("INFO", "init", "HTMX logger initialized");
})();
