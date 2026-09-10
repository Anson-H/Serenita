"""Explicit, repeatable demo generation. Never executed by application startup."""
import argparse,json,math
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from backend.app.application.services import ApplicationServices
from backend.app.repositories.auth_repository import AuthRepository
from backend.app.schemas.body_metric import CATALOG,MEALS
ZONE=ZoneInfo('Asia/Shanghai')

def generate_records(today=None,days=90):
    today=today or datetime.now(ZONE).date()
    def record(kind,at,key,data,end=None,metric='',precision=None):
        return {'kind':kind,'metric':metric,'starts_at':at.isoformat(),'ends_at':end.isoformat() if end else None,'precision':precision or ('interval' if end else 'instant'),'timezone':'Asia/Shanghai','source':'虚构演示数据','device':'Serenita 演示设备','origin':'demo','external_id':f'demo:{key}:{at.isoformat()}','notes':'用于界面体验的虚构数据，不代表任何人的实际健康状况。','data':data}
    for ago in range(days-1,-1,-1):
        date=today-timedelta(days=ago); day=datetime.combine(date,datetime.min.time(),ZONE); wave=math.sin(ago*.38)
        body={'height':172,'weight':round(68.4+ago*.024+wave*.3,1),'waist':round(78+ago*.01+wave*.2,1),'body_fat':round(20.2+wave*.5,1),'bone_mass':2.8,'body_water':39.8,'protein_mass':10.5,'subcutaneous_fat':17.6,'visceral_fat':7}
        body['bmi']=round(body['weight']/1.72**2,1);body['fat_mass']=round(body['weight']*body['body_fat']/100,1)
        for metric,value in body.items(): yield record('measurement',day+timedelta(hours=7,minutes=10),metric,{'value':value,'unit':CATALOG[metric]['unit']},metric=metric)
        for metric,value in {'steps':round(7400+1800*wave),'active_energy':round(420+80*wave),'stand_hours':11+(ago%3),'exercise_minutes':35+(ago%5)*6}.items():
            yield record('measurement',day,metric,{'value':value,'unit':CATALOG[metric]['unit']},end=day+timedelta(days=1),metric=metric,precision='day')
        for metric,value in {'resting_heart_rate':round(61+wave*3),'night_heart_rate':round(56+wave*2),'hrv':round(48+wave*8),'temperature':round(36.5+wave*.1,1),'blood_oxygen':98+ago%2,'blood_pressure':116+ago%6}.items():
            data={'value':value,'unit':CATALOG[metric]['unit']}
            if metric=='blood_pressure':data.update(secondary_value=74+ago%5,pulse=66)
            if metric=='hrv':data['method']='SDNN'
            if metric=='night_heart_rate': data['basis']='虚构的睡眠期间记录，23:10–06:40'
            yield record('measurement',day+timedelta(hours=7,minutes=20),metric,data,metric=metric)
        start=day-timedelta(minutes=50); stages=[]; current=start
        durations=[('light',35),('deep',55),('light',65),('rem',25),('awake',10),('light',60),('deep',35),('rem',45),('light',55),('awake',5),('rem',40)]
        for i,(stage,minutes) in enumerate(durations):
            end=current+timedelta(minutes=minutes)
            stages.append({'stage_id':f'stage-{i}','stage':stage,'starts_at':current.isoformat(),'ends_at':end.isoformat()});current=end
        yield record('sleep',start,'sleep',{'score':83+ago%9,'score_max':100,'score_basis':'虚构演示评分','stages':stages},current)
        if ago<30:
            names=['燕麦牛奶与鸡蛋','原味酸奶','杂粮饭与鸡胸肉','苹果与坚果','糙米饭与清蒸鱼','温牛奶']
            for i,(meal_type,label) in enumerate(MEALS.items()):
                energy=[390,130,620,180,510,110][i];carb=[48,14,76,23,56,10][i];protein=[20,8,37,4,34,7][i];fat=[12,5,18,8,17,4][i]
                at=day+timedelta(hours=[7,10,12,15,18,21][i],minutes=30)
                yield record('meal',at,meal_type,{'meal_type':meal_type,'estimated':True,'basis':'虚构演示营养值','foods':[{'food_id':f'food-{i}','name':names[i],'amount':[300,150,450,150,400,200][i],'amount_unit':'g','energy':energy,'carbohydrate':carb,'protein':protein,'fat':fat,'basis':'虚构演示数据'}]})
            yield record('workout',day+timedelta(hours=17,minutes=20),'workout',{'activity':'户外快走' if ago%2 else '轻松跑步','duration_minutes':40,'distance_km':round(4.3+wave*.2,2),'energy':245},day+timedelta(hours=18))
        if ago<14:
            for i in range(96):
                at=day+timedelta(minutes=i*15)
                yield record('measurement',at,'heart_rate',{'value':round(66+11*math.sin(i*.14)+4*math.cos(i*.7+ago)),'unit':'次/分'},metric='heart_rate')
                yield record('measurement',at,'blood_glucose',{'value':round(5.2+.35*math.sin(i*.13)+1.5*sum(math.exp(-((i-p)/4)**2) for p in (33,51,77)),2),'unit':'mmol/L','method':'模拟连续监测','context':'虚构演示数据'},metric='blood_glucose')
        else:
            yield record('measurement',day+timedelta(hours=8),'heart_rate',{'value':68,'unit':'次/分'},metric='heart_rate')
            yield record('measurement',day+timedelta(hours=8),'blood_glucose',{'value':5.2,'unit':'mmol/L','context':'空腹；虚构数据'},metric='blood_glucose')

def template_records():
    records=list(generate_records(days=1))
    return list({r['external_id']:r for r in records[:40]+[r for r in records if r['kind'] in ('meal','workout')]}.values())

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--account',default='admin');parser.add_argument('--output',default='artifacts/body-metrics-demo.json');args=parser.parse_args()
    services=ApplicationServices();account=AuthRepository(paths=services.paths).account_by_login(args.account)
    if not account: raise SystemExit('请先建立本地测试账号。')
    actor=account['account_id']; members=services.member_service.list_members(actor)['members']
    member=next((m for m in members if m['member_name']=='身体指标演示'),None)
    if member is None: member=services.member_service.create_member(actor,{'member_name':'身体指标演示','sex':'male','birth_date':'1992-06-15'})
    member_id=member['member_id']; records=list(generate_records()); content=json.dumps({'format':'serenita-body-metrics','records':records},ensure_ascii=False,indent=2).encode()
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(content)
    preview=services.body_metrics.preview(actor,member_id,output.name,content)
    result,started=services.body_metrics.start_import(actor,member_id,preview['import_id'],{})
    if started: services.body_metrics.run_import(actor,member_id,preview['import_id'])
    result=services.body_metrics.imports(actor,member_id,preview['import_id'])
    print(json.dumps({'member_id':member_id,'path':f'/health/{member_id}/body-metrics','records':len(records),'import':result},ensure_ascii=False))
if __name__=='__main__':main()
