export function validateAccountNameForSignUp(accountName: string) {
  const normalized = accountName.trim();
  if (!normalized) {
    return "账号名称不能为空。";
  }
  if (Array.from(normalized).length > 50) {
    return "账号名称不能超过 50 个字符。";
  }
  return "";
}
