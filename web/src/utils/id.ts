// crypto.randomUUID() only exists in secure contexts (HTTPS, or the
// `localhost` origin specifically) -- it's undefined when the app is
// reached over plain HTTP on a LAN IP, which self-hosted CircuitForge
// instances are explicitly meant to support. These ids are only used as
// Vue :key/list identifiers, never for anything security-sensitive, so a
// non-cryptographic fallback is fine.
export function genId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}
