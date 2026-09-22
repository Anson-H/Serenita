export function ListCount({ total, unit, label }: { total: number; unit: string; label: string }) {
  return total > 0 ? <p className="object-list-count">共 {total} {unit}{label}</p> : null;
}
