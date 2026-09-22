import memoryStepNames from './memoryStepNames.json';

export {memoryStepNames};
const names:Record<string,string> = {...Object.fromEntries(memoryStepNames.roots),...memoryStepNames.labels};
const numbered:Record<string,string> = memoryStepNames.numbered;

export function memoryStepTitle(id:string):string {
  if(id.startsWith('validated:'))return `${memoryStepTitle(id.slice('validated:'.length))}（已校验输出）`;
  if(id.startsWith('extraction:'))return memoryStepTitle(id.slice('extraction:'.length));
  if(names[id])return names[id];
  const [prefix,number]=id.split(':');
  if(number!==undefined&&numbered[prefix])return `${numbered[prefix]} · ${number}`;
  if(names[prefix])return names[prefix];
  return prefix.endsWith('_context')?memoryStepNames.context_label:'处理步骤';
}
