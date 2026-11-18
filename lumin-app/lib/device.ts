const DEVICE_KEY = 'lumin-device-id';

// Stable anonymous id for this browser or phone, so the same person coming back counts as one unique viewer (and one search on a
// video). Signed-in people are identified by the server from their account, whatever this says.
export function deviceId(): string {
  try {
    let id = window.localStorage.getItem(DEVICE_KEY);
    if (!id) {
      id = (crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`).slice(0, 36);
      window.localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  } catch {
    return '';
  }
}
