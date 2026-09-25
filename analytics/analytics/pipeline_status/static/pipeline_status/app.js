/*
 * Alpine.js components for the pipeline status page.
 *
 * These live in a file served from our own origin rather than inline in the
 * template, so that the page's Content-Security-Policy needs no 'unsafe-inline'
 * for scripts. Loaded before alpine.min.js; both are deferred, so this has
 * registered its components by the time Alpine initialises.
 */
document.addEventListener("alpine:init", () => {
  /* Client-side filtering of the failed jobs table. */
  Alpine.data("jobFilter", () => ({
    query: "",

    /*
     * Each row carries its searchable text in a data attribute, and we read that
     * attribute rather than interpolating job names into an Alpine expression.
     * Job and branch names come from anyone who can open a PR, so they must never
     * end up inside evaluated code.
     */
    matches(el) {
      const query = this.query.trim().toLowerCase();
      return query === "" || (el.dataset.search || "").includes(query);
    },

    clear() {
      this.query = "";
    },
  }));

  /* Opt-in page reload, for watching a pipeline that is still running. */
  Alpine.data("autoRefresh", (intervalSeconds) => ({
    enabled: false,
    remaining: intervalSeconds,

    init() {
      this.enabled = this.readPreference();
      setInterval(() => this.tick(), 1000);
    },

    tick() {
      if (!this.enabled) {
        this.remaining = intervalSeconds;
        return;
      }

      this.remaining -= 1;
      if (this.remaining <= 0) {
        window.location.reload();
      }
    },

    toggle() {
      this.enabled = !this.enabled;
      this.remaining = intervalSeconds;
      this.writePreference();
    },

    /*
     * Storage can be unavailable (private browsing, blocked site data), and the
     * preference is only a convenience, so failures are ignored rather than
     * breaking the page.
     */
    readPreference() {
      try {
        return window.localStorage.getItem("pipelineStatusAutoRefresh") === "true";
      } catch (error) {
        return false;
      }
    },

    writePreference() {
      try {
        window.localStorage.setItem(
          "pipelineStatusAutoRefresh",
          String(this.enabled),
        );
      } catch (error) {
        /* ignored */
      }
    },
  }));
});
