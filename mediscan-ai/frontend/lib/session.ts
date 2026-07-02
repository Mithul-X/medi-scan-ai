// Browser-side session identity: a UUID stored in localStorage, generated
// once per device/browser. No auth, no cookies, no server-side session
// store — the backend just keys SQLite rows off whatever string we send it.

const SESSION_KEY = "mediscan_session_id";

function generateUuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Fallback for older browsers without crypto.randomUUID
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Returns the current session id, creating and persisting one if it
 * doesn't exist yet. Safe to call on every render — cheap localStorage read.
 */
export function getSessionId(): string {
  if (typeof window === "undefined") {
    // Server-side render path — caller should only use this client-side,
    // but return a placeholder rather than throwing during SSR.
    return "ssr-placeholder";
  }

  let id = window.localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = generateUuid();
    window.localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export function resetSessionId(): string {
  const id = generateUuid();
  if (typeof window !== "undefined") {
    window.localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}
