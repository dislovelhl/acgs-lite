/// Generate a unique request ID.
export function generateRequestId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).substring(2, 10);
  return `gw_${timestamp}_${random}`;
}
