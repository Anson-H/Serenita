import type {ReactNode} from 'react';
import {ContentDialog} from '../../components/ContentDialog';
export type MedicationNavigation = {title:string;onBack:()=>void};
export function MedicationCreateDialog({onClose,children,formId,navigation,saving=false}:{onClose:()=>void;children:ReactNode;formId:string;navigation:MedicationNavigation|null;saving?:boolean}) {
  return <ContentDialog title={navigation?.title??'创建用药计划'} creation busy={saving} onClose={onClose} onBack={navigation?.onBack} actions={navigation?undefined:<button className="control control--primary" type="submit" form={formId} disabled={saving}>完成</button>}>{children}</ContentDialog>;
}
