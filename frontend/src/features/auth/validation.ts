const userNameSpacePattern = /\s/;

export function validateUserNameForSignUp(userName: string) {
  if (!userName.trim()) {
    return "用户名称不能为空。";
  }
  if (userNameSpacePattern.test(userName)) {
    return "用户名称不能包含空格。";
  }
  return "";
}
