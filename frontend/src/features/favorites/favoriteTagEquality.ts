
export function sameFavoriteTags(left: string[], right: string[]) {
  return left.length === right.length && left.every((tag, index) => tag === right[index]);
}
