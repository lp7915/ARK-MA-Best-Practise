"""Deliberately limited, deterministic AC simulation. Never calls a network."""
from __future__ import annotations
import copy
import hashlib
import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import uuid

VERSION = '1.2.0'
IDS = {'validate':'AC-01','deduplicate':'AC-02','metrics':'AC-03','merge':'AC-04','chart':'AC-05','save':'AC-06'}

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()

def envelope(rows, schema=None, source='synthetic'):
    schema = copy.deepcopy(schema) if schema is not None else [{'name':k,'type':'number' if type(v) in (int,float) else 'string','nullable':True} for k,v in (rows[0] if rows else {}).items()]
    return {'schema':schema,'rows':copy.deepcopy(rows),'meta':{'source':source,'row_count':len(rows)}}

def dataset(value):
    if not isinstance(value,dict) or not all(k in value for k in ('schema','rows','meta')): raise ValueError('需要标准数据信封 schema/rows/meta')
    if not isinstance(value['rows'],list) or not isinstance(value['schema'],list): raise ValueError('rows/schema 必须是数组')
    names=[f['name'] for f in value['schema']]
    if len(names)!=len(set(names)): raise ValueError('schema 字段重名')
    for row in value['rows']:
        if not isinstance(row,dict) or set(row)-set(names): raise ValueError('数据行与 schema 不匹配')
    return value

def reject_options(params, allowed):
    unknown=set(params)-set(allowed)
    if unknown: raise ValueError('模拟未支持参数：'+','.join(sorted(unknown)))

def redact(value):
    if isinstance(value,dict):
        return {k:('[REDACTED]' if any(x in k.lower() for x in ('secret','token','password','api_key','authorization')) else redact(v)) for k,v in value.items()}
    if isinstance(value,list): return [redact(v) for v in value]
    return value

def execute(action, payload):
    original=copy.deepcopy(payload)
    receipt={'receipt_id':None,'capability_id':IDS.get(action,'unknown'),'capability_version':VERSION,'invoked_at':datetime.now(timezone.utc).isoformat(),'input_summary':{},'params':redact(payload.get('params',{})),'output_summary':{},'deltas':{},'status':'success','warnings':[],'errors':[]}
    try:
        params=payload.get('params',{})
        if action=='save':
            reject_options(params,{'mode'})
            target=payload['target']
            if set(target)-{'backend','index_key'}:raise ValueError('模拟未支持该存储目标参数')
            if target.get('backend','fs')!='fs' or params.get('mode','append')!='append': raise ValueError('仅支持 fs/append')
            root=Path(payload['output_root']).resolve()
            key=target['index_key']
            if not isinstance(key,str) or not key or Path(key).is_absolute() or '..' in Path(key).parts: raise ValueError('非法 index_key')
            folder=(root/key).resolve()
            if not folder.is_relative_to(root): raise ValueError('路径越界')
            folder.mkdir(parents=True,exist_ok=True)
            stored=[]
            for item in payload.get('receipts',[]):
                rid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:12]
                clean=redact(copy.deepcopy(item));clean['receipt_id']=rid
                path=folder/(rid+'.json');path.write_text(json.dumps(clean,ensure_ascii=False,indent=2))
                stored.append({'receipt_id':rid,'capability_id':item.get('capability_id'),'location':str(path.relative_to(root)),'backend':'fs','stored_at':receipt['invoked_at']})
            index=folder/'index.json'
            prior=json.loads(index.read_text()) if index.exists() else []
            index.write_text(json.dumps(prior+stored,ensure_ascii=False,indent=2))
            output={'stored':stored,'artifacts_stored':[],'index_entry':{'index_key':key,'receipt_count':len(prior)+len(stored),'artifact_count':0,'bundle_location':None}}
            receipt['deltas']={'stored':len(stored),'artifacts':0,'backend':'fs'}
        elif action=='merge':
            reject_options(params,set())
            rules=payload.get('rules',{})
            if set(rules)-{'schema_align','type_conflict','provenance_field'}: raise ValueError('模拟不支持 field_map 或内联去重')
            if rules.get('schema_align','union')!='union' or rules.get('type_conflict','fail')!='fail': raise ValueError('模拟仅 union/type_conflict=fail')
            batches=payload['batches']
            if not batches or len({b['batch_id'] for b in batches})!=len(batches): raise ValueError('批次为空或标识重复')
            fields={};rows=[];nulls={};prov=[]
            pf=rules.get('provenance_field','_batch')
            for b in batches:
                d=dataset(b['dataset'])
                for f in d['schema']:
                    if f['name']==pf: raise ValueError('溯源字段碰撞')
                    if f['name'] in fields and fields[f['name']]['type']!=f['type']: raise ValueError('字段类型冲突')
                    fields[f['name']]=f
            for b in batches:
                d=b['dataset'];missing=set(fields)-{f['name'] for f in d['schema']}
                if missing: nulls[b['batch_id']]=sorted(missing)
                rows.extend([{**{k:r.get(k) for k in fields},pf:b['batch_id']} for r in d['rows']])
                prov.append({'batch_id':b['batch_id'],'row_count':len(d['rows']),'meta':d['meta']})
            merged=envelope(rows,list(fields.values())+[{'name':pf,'type':'string','nullable':False}]);merged['meta']['provenance']=prov
            output={'merged':merged,'schema_report':{'mode':'union','unified_fields':list(fields),'added_as_null':nulls,'dropped_fields':[]},'conflict_log':[]}
            receipt['deltas']={'batches':len(batches),'input_rows':len(rows),'merged':len(rows),'conflicts':0,'removed_by_dedup':0}
            if nulls:receipt['status']='partial'
        else:
            d=dataset(payload['dataset']);names={f['name'] for f in d['schema']};rows=d['rows']
            receipt['input_summary']={'row_count':len(rows),'schema_fields':len(names),'source':d['meta'].get('source')}
            if action=='validate':
                reject_options(params,{'on_error','normalize'})
                if params.get('normalize',False):raise ValueError('模拟不支持 normalize')
                mode=params.get('on_error','reject_row')
                if mode not in ('reject_row','annotate_only'):raise ValueError('非法 on_error')
                rules=payload.get('rules',{});fr=rules.get('field_rules',[])
                if set(rules)-{'field_rules'}:raise ValueError('模拟不支持跨字段规则')
                for f in fr:
                    if set(f)-{'field','required','type','enum','desc'}: raise ValueError('未支持的校验规则')
                    if f['field'] not in names:raise ValueError('规则引用不存在字段')
                    if f.get('type') not in (None,'string','integer','number','enum'):raise ValueError('未支持的字段类型校验')
                valid=[];invalid=[];by_rule={}
                for row in rows:
                    errs=[]
                    for f in fr:
                        v=row.get(f['field']);t=f.get('type');missing=v is None or v==''
                        ok=not(f.get('required') and missing)
                        if not missing and t:
                            ok=ok and ((t=='string' and isinstance(v,str)) or (t=='integer' and type(v)==int) or (t=='number' and type(v) in (int,float) and math.isfinite(v)) or (t=='enum' and v in f.get('enum',[])))
                        if not ok:
                            rule=f['field']+':'+str(t or 'required');by_rule[rule]=by_rule.get(rule,0)+1
                            errs.append({'field':f['field'],'rule':rule,'msg':'不满足显式字段规则'})
                    if errs:
                        annotated={**row,'_errors':errs};invalid.append(annotated)
                        if mode=='annotate_only': valid.append(annotated)
                    else:valid.append(row)
                errschema=d['schema']+[{'name':'_errors','type':'json','nullable':True}]
                output={'valid_rows':envelope(valid,errschema if mode=='annotate_only' else d['schema']),'invalid_rows':envelope(invalid,errschema),'summary':{'total':len(rows),'valid':len(rows)-len(invalid),'invalid':len(invalid),'by_rule':by_rule}}
                receipt['deltas']={'invalid':len(invalid),'by_rule':by_rule}
                if invalid:receipt['status']='partial'
            elif action=='deduplicate':
                reject_options(params,{'keep_removed'})
                rules=payload['rules']
                if set(rules)-{'key_fields','match_mode','survivor'}:raise ValueError('未支持的去重规则')
                keys=rules['key_fields'];policy=rules.get('survivor',{}).get('policy','first')
                if set(rules.get('survivor',{}))-{'policy'}:raise ValueError('模拟不支持去重附加幸存策略')
                if not keys or not set(keys)<=names:raise ValueError('去重键不存在')
                if rules.get('match_mode','exact')!='exact' or policy not in ('first','last'):raise ValueError('模拟仅 exact + first/last')
                groups={}
                for i,row in enumerate(rows):groups.setdefault(json.dumps([row.get(k) for k in keys],sort_keys=True),[]).append(i)
                kept=set();removed=[];dups=[]
                for indices in groups.values():
                    pick=indices[0] if policy=='first' else indices[-1];kept.add(pick)
                    if len(indices)>1:
                        gid='dup-'+str(pick);dups.append({'group_id':gid,'size':len(indices),'key':{k:rows[pick].get(k) for k in keys},'survivor_index':indices.index(pick),'match':'exact','score':None})
                        removed.extend([{**rows[i],'_dup_group':gid,'_reason':'由输入行 '+str(pick)+' 取代'} for i in indices if i!=pick])
                output={'deduped_rows':envelope([r for i,r in enumerate(rows) if i in kept],d['schema']),'removed_rows':envelope(removed if params.get('keep_removed',True) else [],d['schema']+[{'name':'_dup_group','type':'string'},{'name':'_reason','type':'string'}]),'dup_groups':dups}
                receipt['deltas']={'input':len(rows),'removed':len(removed),'groups':len(dups),'max_group':max([len(x) for x in groups.values()],default=0)}
            elif action=='metrics':
                reject_options(params,{'null_policy','round'})
                if params.get('null_policy','skip')!='skip':raise ValueError('模拟仅 null_policy=skip')
                defs=payload['metrics_def'];dims=defs.get('dimensions',[]);metrics=defs['metrics']
                if set(defs)-{'dimensions','metrics'}:raise ValueError('模拟不支持 filters')
                if not set(dims)<=names or not metrics:raise ValueError('维度或指标缺失')
                for m in metrics:
                    if set(m)-{'name','agg','field','caliber'}:raise ValueError('未支持的指标定义参数')
                    if not m.get('caliber'):raise ValueError('指标缺 caliber 口径')
                    if m['agg'] not in ('count','sum','avg'):raise ValueError('模拟仅 count/sum/avg')
                    if m['agg']!='count' and m.get('field') not in names:raise ValueError('指标字段不存在')
                groups={}
                for row in rows:groups.setdefault(tuple(row.get(k) for k in dims),[]).append(row)
                table=[]
                for key,group in sorted(groups.items(),key=lambda item:str(item[0])):
                    out=dict(zip(dims,key))
                    for m in metrics:
                        vals=[r[m['field']] for r in group if m.get('field') in r and r[m['field']] is not None]
                        if m['agg']!='count' and any(type(v) not in (int,float) or not math.isfinite(v) for v in vals):raise ValueError('非数值不能聚合')
                        v=len(group) if m['agg']=='count' else (sum(vals) if m['agg']=='sum' else sum(vals)/len(vals) if vals else None)
                        out[m['name']]=round(v,params['round']) if v is not None and 'round' in params else v
                    table.append(out)
                output={'metric_table':envelope(table,[next(f for f in d['schema'] if f['name']==k) for k in dims]+[{'name':m['name'],'type':'number'} for m in metrics]),'metric_manifest':[{**m,'formula':m['agg']+'('+m.get('field','rows')+')','null_policy':'skip','div_zero':'not-applicable'} for m in metrics]}
                receipt['deltas']={'input_rows':len(rows),'metrics':len(metrics),'groups':len(groups),'div_zero_hits':0}
                if not rows:receipt['status']='partial'
            elif action=='chart':
                reject_options(params,{'format','width','height'})
                c=payload['chart_def'];x=c['encodings']['x'];y=c['encodings']['y']
                if c.get('type')!='bar' or params.get('format','svg')!='svg':raise ValueError('模拟仅 bar/svg')
                if x not in names or not isinstance(y,str) or y not in names:raise ValueError('图表字段不存在或不支持多 y')
                if any(type(r.get(y)) not in (int,float) or not math.isfinite(r[y]) or r[y]<0 for r in rows):raise ValueError('SVG 柱图要求非负有限数值')
                width=params.get('width',960);height=params.get('height',540)
                if type(width)!=int or type(height)!=int or width<200 or height<200:raise ValueError('图表尺寸非法')
                maximum=max([r[y] for r in rows]+[1]);step=(width-120)/max(len(rows),1)
                svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#f4f7f6"/><text x="50" y="36" font-size="22">{html.escape(c.get("title","样本统计"))}</text>']
                for i,r in enumerate(rows):
                    h=(height-150)*r[y]/maximum;xx=60+i*step
                    svg.append(f'<rect x="{xx}" y="{height-70-h}" width="{step*0.65}" height="{h}" fill="#167a65"/><text x="{xx}" y="{height-40}" font-size="15">{html.escape(str(r.get(x)))}</text><text x="{xx}" y="{height-80-h}" font-size="15">{r[y]}</text>')
                svg.append('</svg>');content=''.join(svg)
                output={'artifact':{'format':'svg','content_ref':content,'bytes':len(content.encode())},'chart_meta':{'type':'bar','title':c.get('title'),'encodings_resolved':{'x':x,'y':[y],'series':None},'data_rows':len(rows),'theme':'simulation','dimensions':f'{width}x{height}'}}
                receipt['deltas']={'charts':1,'data_rows':len(rows),'type':'bar','format':'svg'}
                if not rows:receipt['status']='partial'
            else:raise ValueError('未知 action')
        receipt['output_summary']={'sha256':digest(output)}
        return {'status':receipt['status'],'output':output,'receipt':receipt}
    except (ValueError,KeyError,TypeError,IndexError,OSError) as exc:
        receipt.update(status='failed',errors=[str(exc)])
        return {'status':'failed','output':None,'receipt':receipt}
    finally:
        assert payload==original,'原子动作不能修改调用者输入'

if __name__=='__main__':
    import sys
    request=json.loads(Path(sys.argv[1]).read_text())
    print(json.dumps(execute(request['action'],request['payload']),ensure_ascii=False,indent=2))
