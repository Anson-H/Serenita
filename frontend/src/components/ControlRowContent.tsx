import type { ReactNode } from 'react';

export function ControlRowContent({ title, description, icon, className = '', tooltip = title, emphasis = 'regular', singleLineDescription = false }: {
  title: string;
  description?: ReactNode;
  icon?: ReactNode;
  className?: string;
  tooltip?: string;
  emphasis?: 'regular' | 'strong';
  singleLineDescription?: boolean;
}) {
  return <span className={`control-row-content ${className}`}>
    {icon ? <span className="control-row-icon" aria-hidden="true">{icon}</span> : null}
    <span className="control-row-copy" data-emphasis={emphasis}>
      <span className="control-row-title" title={tooltip}>{title}</span>
      {description ? <span className="control-row-description" data-single-line={singleLineDescription || undefined} title={typeof description === 'string' ? description : undefined}>{description}</span> : null}
    </span>
  </span>;
}
