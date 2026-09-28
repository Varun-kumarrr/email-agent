const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const isEmail = (value: string) => EMAIL_RE.test(value.trim());

/** Split "a@x.com, b@y.com; c@z.com" (commas, semicolons, spaces, newlines) into a list. */
export function parseEmailList(text: string): string[] {
  return text
    .split(/[\s,;]+/)
    .map((e) => e.trim())
    .filter(Boolean);
}

/** Returns the first invalid address, or null when all are valid. */
export function firstInvalidEmail(list: string[]): string | null {
  return list.find((e) => !isEmail(e)) ?? null;
}
