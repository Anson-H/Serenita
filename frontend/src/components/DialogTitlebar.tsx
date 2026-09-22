import { NavigationTitle } from "./NavigationTitle";
import { ChevronLeftIcon, XIcon } from "./icons";

export function DialogTitlebar({ id, title, onClose, onBack, busy = false, closeLabel = `关闭${title}` }: {
  id: string;
  title: string;
  onClose: () => void;
  onBack?: () => void;
  busy?: boolean;
  closeLabel?: string;
}) {
  return <header className="dialog-titlebar">
    <NavigationTitle id={id} tabIndex={-1} data-modal-initial-focus title={title} />
    {onBack ? <button className="control control--titlebar control--icon control--ghost titlebar-icon-control dialog-back-button" type="button" aria-label="返回上一级" disabled={busy} onClick={onBack}><ChevronLeftIcon /></button> : null}
    <button className="control control--titlebar control--icon control--ghost titlebar-icon-control" type="button" aria-label={closeLabel} disabled={busy} onClick={onClose}><XIcon /></button>
  </header>;
}
