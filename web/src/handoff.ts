// Text pasted on the list page for the Claude bridge, handed to the workspace in memory only (never in the URL or
// in storage). peek() has no side effect (safe in React state initializers); the workspace calls clear() once mounted.
let pending: { id: string; text: string } | null = null;

export function giveBridgeText(id: string, text: string): void {
  pending = { id, text };
}

export function peekBridgeText(id: string): string | null {
  return pending && pending.id === id ? pending.text : null;
}

export function clearBridgeText(): void {
  pending = null;
}
