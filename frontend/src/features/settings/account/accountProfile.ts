export const accountIdentifierPattern = /^[A-Za-z0-9_-]{1,20}$/;

export function accountNameLength(value: string) {
  return Array.from(value).length;
}

