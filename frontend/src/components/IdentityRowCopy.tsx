import type { ReactNode } from 'react';
import { ControlRowContent } from './ControlRowContent';

export function IdentityRowCopy({title,description,className='',tooltip=title}:{title:string;description?:ReactNode;className?:string;tooltip?:string}) {
  return <ControlRowContent className={`identity-row-copy ${className}`} title={title} description={description} tooltip={tooltip} emphasis="strong" />;
}
