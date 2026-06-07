// router.js — tiny dependency-free hash router (ES module).
//
// Public API:
//   registerRoute(hash, mountFn)  — register a view. `hash` like '#/', '#/new'.
//                                   `mountFn(container, ctx)` returns an optional
//                                   cleanup function (or void) called before the
//                                   next view mounts.
//   start(opts)                   — opts {container, ctx, fallback:'#/'}. Reads
//                                   location.hash, mounts the matching route, and
//                                   listens for 'hashchange'.
//   navigate(hash)                — sets location.hash (triggers a mount).
//
// No external dependencies. Robust to unknown hashes (uses `fallback`).

/** @typedef {(container: Element, ctx: any) => (void | (() => void))} MountFn */

/** @type {Map<string, MountFn>} */
const routes = new Map();

/** Active router instance state (set by start). */
let active = null;

/**
 * Normalize a hash into the canonical form used as a route key.
 *
 * Strips a leading '#', drops any query string, ensures a leading '/'.
 * Empty / bare '#' becomes '#/'.
 *
 * @param {string} hash
 * @returns {string} canonical hash, e.g. '#/', '#/new'
 */
export function normalizeHash(hash) {
  let h = (hash == null ? "" : String(hash)).trim();
  if (h.startsWith("#")) h = h.slice(1);
  // Drop query/search portion (e.g. '#/files?session=x' -> '/files').
  const q = h.indexOf("?");
  if (q !== -1) h = h.slice(0, q);
  if (!h.startsWith("/")) h = "/" + h;
  // Collapse a bare '/' duplicate produced by inputs like '#'.
  if (h === "//") h = "/";
  return "#" + h;
}

/**
 * Register a route. Re-registering an existing hash replaces its mount fn.
 *
 * @param {string} hash  e.g. '#/', '#/new'
 * @param {MountFn} mountFn
 */
export function registerRoute(hash, mountFn) {
  if (typeof mountFn !== "function") {
    throw new TypeError("registerRoute(hash, mountFn): mountFn must be a function");
  }
  routes.set(normalizeHash(hash), mountFn);
}

/**
 * Resolve the mount fn for a hash, falling back when unknown.
 *
 * @param {string} hash
 * @param {string} fallback
 * @returns {{ hash: string, mountFn: MountFn | null }}
 */
function resolve(hash, fallback) {
  const key = normalizeHash(hash);
  if (routes.has(key)) return { hash: key, mountFn: routes.get(key) };
  const fb = normalizeHash(fallback || "#/");
  if (routes.has(fb)) return { hash: fb, mountFn: routes.get(fb) };
  return { hash: key, mountFn: null };
}

/**
 * Run the current view's cleanup (if any), swallowing errors so a faulty
 * cleanup can never wedge navigation.
 */
function runCleanup() {
  if (active && typeof active.cleanup === "function") {
    try {
      active.cleanup();
    } catch (err) {
      // Best-effort: a broken cleanup must not block the next mount.
      // eslint-disable-next-line no-console
      console.error("router: cleanup threw", err);
    }
  }
  if (active) active.cleanup = null;
}

/**
 * Mount the view for the current location.hash. Tears down the previous view
 * first by invoking its returned cleanup.
 *
 * Idempotent per resolved hash: if the resolved route is already mounted this
 * is a no-op. That makes navigate()'s synchronous render harmless even when the
 * browser later fires a redundant 'hashchange' for the same hash (jsdom does).
 *
 * @param {boolean} [force] re-mount even if the resolved hash is unchanged.
 */
function render(force = false) {
  if (!active) return;
  const { hash, mountFn } = resolve(location.hash, active.fallback);
  if (!force && active.current === hash) return;

  runCleanup();
  active.current = hash;

  if (!mountFn) {
    // No route and no usable fallback — leave the container untouched.
    active.cleanup = null;
    return;
  }

  let cleanup = null;
  try {
    const ret = mountFn(active.container, active.ctx);
    if (typeof ret === "function") cleanup = ret;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("router: mount threw for " + hash, err);
  }
  active.cleanup = cleanup;
}

/**
 * Start the router: mount the route matching the current hash and listen for
 * 'hashchange'. Calling start() again replaces the previous instance (after
 * tearing it down) so it is safe in hot-reload / test scenarios.
 *
 * @param {{container: Element, ctx?: any, fallback?: string}} [opts]
 * @returns {() => void} a stop() function that removes the listener and runs cleanup.
 */
export function start(opts = {}) {
  const { container, ctx = {}, fallback = "#/" } = opts;
  if (!container) {
    throw new TypeError("start(opts): opts.container is required");
  }

  // Tear down any previously running instance.
  if (active) stop();

  active = {
    container,
    ctx,
    fallback,
    current: null,
    cleanup: null,
    onHashChange: () => render(),
  };

  window.addEventListener("hashchange", active.onHashChange);
  render();

  return stop;
}

/**
 * Stop the active router: remove the listener and run the current cleanup.
 * Idempotent.
 */
export function stop() {
  if (!active) return;
  window.removeEventListener("hashchange", active.onHashChange);
  runCleanup();
  active = null;
}

/**
 * Navigate to a hash. Setting location.hash emits a 'hashchange' event, which
 * drives render(). If the hash is unchanged, force a re-render so navigate()
 * is always idempotent and observable.
 *
 * @param {string} hash
 */
export function navigate(hash) {
  const next = normalizeHash(hash);
  // Setting location.hash emits 'hashchange', but browsers (and jsdom) dispatch
  // it asynchronously. Set the hash for URL correctness, then render() now so
  // navigation is synchronous and deterministic. render() is idempotent per
  // resolved hash, so the later async 'hashchange' becomes a no-op.
  location.hash = next;
  render();
}

/**
 * @returns {string | null} the currently mounted route hash, or null if not started.
 */
export function currentRoute() {
  return active ? active.current : null;
}
