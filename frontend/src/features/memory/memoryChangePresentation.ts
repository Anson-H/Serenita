import type {MemoryChangeTarget} from "../../api/memory/memoryApi";
import {MEDICAL_HISTORY_FIELDS} from "../../api/medicalHistory/medicalHistoryTypes";
import {bodyMetricPath, healthPathForMember, medicalLogPath, medicationBatchPath, medicationPath, reportPathForReport, type RoutePath} from '../../app/routes';

export function memoryChangeTargetPath(memberId: string, target: MemoryChangeTarget): RoutePath {
  switch (target.resource_type) {
    case 'member':
    case 'medical_history': return `${healthPathForMember(memberId)}?section=information`;
    case 'medical_log': return medicalLogPath(memberId, target.resource_id);
    case 'report': return reportPathForReport(target.resource_id, memberId);
    case 'medication_plan': return medicationPath(memberId, 'plans', target.resource_id);
    case 'medication_batch': return medicationBatchPath(memberId, target.medication_id, target.resource_id);
    case 'body_record': return `${bodyMetricPath(memberId)}?record=${encodeURIComponent(target.resource_id)}`;
  }
}

export const memoryResourceLabels: Record<string, string> = {
  member: '成员基本信息', medical_history: '既往史', medical_log: '健康日记', report: '医疗报告', report_source: '医疗报告来源',
  medication: '药品', medication_plan: '用药计划', medication_batch: '药品批次', body_record: '身体指标记录',
  body_file: '身体指标附件', medication_source: '药品原件'
};
const commonFieldLabels: Record<string, string> = {
  '/member_name': '成员名称', '/relationship': '关系', '/sex': '性别', '/birth_date': '出生日期', '/blood_type': '血型',
  '/title': '标题', '/content': '内容', '/recorded_on': '记录日期', '/report_name': '医疗报告名称', '/report_type': '医疗报告类型',
  '/report_time': '就诊时间', '/institution_name': '就诊机构', '/report_body': '医疗报告内容', '/notes': '备注',
  ...Object.fromEntries(MEDICAL_HISTORY_FIELDS.map(([field, label]) => [`/${field}`, label]))
};
export type MemoryCitation = {quotes: string[]};
export function changeFieldLabel(path: string, resourceType = ''): string {
  if (resourceType === 'medical_log' && path === '/content') return '日记内容';
  if (resourceType === 'medical_log' && path === '/title') return '日记标题';
  return commonFieldLabels[path] || path;
}
