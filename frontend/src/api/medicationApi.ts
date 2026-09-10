import { request, requestResponse, API_BASE_URL } from './request';
import type { MedicationKind, MedicationFilters, MedicationBatch, Medication, MedicationOfKind, MedicationChangesByKind } from './medicationTypes';
export const medicationEndpoints = { medication: 'medications', plan: 'medication-plans' };
export const medicationIdFields = { medication: 'medication_id', plan: 'medication_plan_id' };
export const medicationBase = (member: string, kind: MedicationKind, id?: string) => `/members/${encodeURIComponent(member)}/${medicationEndpoints[kind]}${id ? '/'+encodeURIComponent(id) : ''}`;
export function listMedications<K extends MedicationKind>(member: string, kind: K, filters: MedicationFilters, cursor?: string, signal?: AbortSignal) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, String(value));
  if (cursor) params.set('cursor', cursor);
  return request<{items: MedicationOfKind<K>[]; total: number; next_cursor: string | null}>(medicationBase(member,kind)+'?'+params, {signal});
}
export const readMedication = <K extends MedicationKind>(member: string,kind: K,id: string,signal?: AbortSignal) => request<MedicationOfKind<K>>(medicationBase(member,kind,id),{signal});
export const saveMedication = (member: string,kind: 'plan',values: MedicationChangesByKind['plan'],id?: string,requestId?: string) => request<MedicationOfKind<'plan'>>(medicationBase(member,kind,id),{method:id?'PATCH':'POST',headers:requestId?{'Idempotency-Key':requestId}:{},body:JSON.stringify(values)});
export const deleteMedication = (member: string,kind: 'plan',id: string) => request(medicationBase(member,kind,id),{method:'DELETE'});
export const saveBatch = (member: string,medicationId: string,values: Record<string,unknown>,id?: string,requestId?: string) => request<MedicationBatch>(medicationBase(member,'medication',medicationId)+'/batches'+(id?'/'+encodeURIComponent(id):''),{method:id?'PATCH':'POST',headers:requestId?{'Idempotency-Key':requestId}:{},body:JSON.stringify(values)});
export const deleteBatch = (member: string,medicationId: string,id: string) => request(medicationBase(member,'medication',medicationId)+'/batches/'+encodeURIComponent(id),{method:'DELETE'});
export function addMedicationSources(medicationId: string, files: File[], requestId: string) {
  const body = new FormData();
  for (const file of files) body.append('files', file);
  return request<Medication>(catalogueBase(medicationId) + '/source-files', {
    method: 'POST', headers: {'Idempotency-Key': requestId}, body,
  });
}
export const medicationSourceUrl = (member: string, medicationId: string, resourceId: string) => API_BASE_URL + (member ? medicationBase(member, 'medication', medicationId) : catalogueBase(medicationId)) + '/source-files/' + encodeURIComponent(resourceId);
export async function readMedicationSource(member: string, medicationId: string, resourceId: string, signal?: AbortSignal) {
  const response = await requestResponse((member ? medicationBase(member, 'medication', medicationId) : catalogueBase(medicationId)) + '/source-files/' + encodeURIComponent(resourceId), {signal});
  return response.blob();
}

const catalogueBase = (id?: string) => '/medication-catalog' + (id ? '/' + encodeURIComponent(id) : '');
export const listMedicationCatalog = (query='', cursor?: string, signal?: AbortSignal) => request<{items:Medication[];total:number;next_cursor:string|null}>(catalogueBase()+'?'+new URLSearchParams({query,...(cursor?{cursor}:{})}),{signal});
export const readMedicationCatalog = (id:string, signal?:AbortSignal) => request<Medication>(catalogueBase(id),{signal});
export const saveMedicationCatalog = (values:MedicationChangesByKind['medication'],id?:string,requestId?:string) => request<Medication>(catalogueBase(id),{method:id?'PATCH':'POST',headers:requestId?{'Idempotency-Key':requestId}:{},body:JSON.stringify(values)});
export const deleteMedicationCatalog = (id:string) => request(catalogueBase(id),{method:'DELETE'});
