"""Fixed host call into the unchanged routing kernel; never starts production.

Input is a trusted host event, not instructions found inside an attachment.
The small adapter accepts simulator form fields and explicit legacy labels.
All coverage decisions and routing conversation state belong to RoutingNode.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True

BASE = Path(__file__).resolve().parent
CONFIG = json.loads((BASE / 'routing-config.json').read_text())
_name = 'ada_bundled_routing_' + hashlib.sha256(str(BASE).encode()).hexdigest()[:12]
if _name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _name, BASE / 'routing_unit/__init__.py',
        submodule_search_locations=[str(BASE / 'routing_unit')])
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    _spec.loader.exec_module(_module)
kernel = sys.modules[_name]


class HostSemanticAdapter(kernel.DemoSemanticAdapter):
    def extract(self, message, state):
        out = super().extract(message, state)
        text = message['text']
        data = message.get('host_fields', {})
        positive = re.sub(r'(?:不要|不需要|不用|不做|不是|无需)[^，,。；;]*(?:[，,。；;]|$)', '', text)
        # Compatibility with the existing simulator labels; no route selection here.
        if re.search(r'完整评论报告|评论分析报告|评论报告', positive):
            out['domains'] = list(dict.fromkeys(out['domains'] + ['social']))
            out['mode'] = 'full'
        if '人群报告' in positive:
            out['domains'] = list(dict.fromkeys(out['domains'] + ['audience']))
            out['mode'] = 'full'
        if re.search(r'地区统计|地区汇总|报名表', positive):
            out['actions'] = list(dict.fromkeys(out['actions'] + ['aggregate']))
        for field, pattern in [('object', r'对象[：:]\s*([^；;\n]+)'),
                               ('period', r'周期[：:]\s*([^；;\n]+)')]:
            match = re.search(pattern, text)
            if match and field not in out['facts']:
                out['facts'][field] = match.group(1).strip()
        if re.search(r'明确修正|修订|裁决|采用', text):
            out['explicit_revision'] = True
        for field in ('object', 'period', 'dedup_key', 'metric'):
            if field in data:
                out['facts'][field] = data[field]
        if 'topic' in data:
            out['domains'] = [data['topic']] if data['topic'] else []
            if data['topic']:
                out['mode'] = 'full'
        if data.get('action'):
            out['actions'] = list(dict.fromkeys(out['actions'] + [data['action']]))
        if data.get('human') and not any(a in out['actions'] for a in CONFIG['human_methods']):
            out['actions'].append('offline_interview')
        if data.get('dataset'):
            out['facts']['dataset'] = 'provided_reference'
        # A structured form revision is explicit; natural conversation still uses
        # the original kernel's self-revision and multi-party conflict rules.
        if data.get('_explicit_revision'):
            out['explicit_revision'] = True
        # Defaults are host configuration, not claimed as a user statement.
        if 'deduplicate' in out['actions'] and not out['facts'].get('dedup_key'):
            out['facts']['dedup_key'] = CONFIG['defaults']['dedup_key']
        if 'aggregate' in out['actions'] and not out['facts'].get('metric'):
            out['facts']['metric'] = CONFIG['defaults']['metric']
        return out


def call(event, state=None):
    data = copy.deepcopy(event.get('data', {}))
    message = {'event_id': event['event_id'], 'user_id': event['actor'],
               'text': event.get('text', ''), 'host_fields': data}
    node = kernel.RoutingNode(semantic=HostSemanticAdapter(), admin_user_ids=['admin'])
    output = node.handle(message, state)
    result = output['result']
    normalized = result.get('normalized_request', {})
    facts = {k: v['value'] for k, v in normalized.get('facts', {}).items() if v}
    topics = [CONFIG['topic_bindings'][i] for i in result.get('topic_ids', [])
              if i in CONFIG['topic_bindings']]
    methods = [item['capability_id'] for item in result.get('g_items', [])]
    actions = [CONFIG['action_bindings'].get(i) for i in methods]
    unsupported = [i for i, action in zip(methods, actions) if action is None]
    blockers = []
    unmapped_topics = [i for i in result.get('topic_ids', []) if i not in CONFIG['topic_bindings']]
    if unmapped_topics:
        blockers.append('尚无 Topic 执行绑定：' + '、'.join(unmapped_topics))
    if len(topics) > 1:
        blockers.append('当前生产替身一次只执行一个 Topic；请拆分需求，原路由的多 Topic 方案已保留。')
    if unsupported:
        blockers.append('路由已识别，但尚无对应生产适配：' + '、'.join(unsupported))
    if len(set(a for a in actions if a)) > 1:
        blockers.append('当前局部生产替身一次只执行一种动作；请拆分，不能丢弃其余交付项。')
    if facts.get('dedup_key') and facts['dedup_key'] != CONFIG['defaults']['dedup_key']:
        blockers.append('当前去重生产替身仅支持配置键 id；路由所选其他键不能按 id 偷换执行。')
    if 'aggregate' in actions and facts.get('metric') != CONFIG['defaults']['metric']:
        blockers.append('当前地区统计替身仅支持 count；不得把均值或求和要求替换为计数。')
    output['projection'] = {'facts': {k: v for k, v in facts.items() if k in ('object', 'period')},
                            'topic': topics[0] if len(topics) == 1 else None,
                            'action': next((a for a in actions if a), None),
                            'human': bool(result.get('h_gaps')),
                            'execution_blockers': blockers}
    output['host_defaults'] = CONFIG['defaults']
    return output


def main():
    parser = argparse.ArgumentParser(description='宿主固定调用路由；不会启动生产')
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--state', required=True, type=Path)
    args = parser.parse_args()
    if args.state.resolve().is_relative_to(BASE.parents[2]):
        parser.error('路由运行状态必须放在资源包之外')
    event = json.loads(args.input.read_text())
    state = json.loads(args.state.read_text()) if args.state.exists() else None
    result = call(event, state)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    temp = args.state.with_suffix(args.state.suffix + '.tmp')
    temp.write_text(json.dumps(result['state'], ensure_ascii=False, indent=2))
    temp.replace(args.state)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['result']['status'] in ('invalid_event', 'invalid_assessment') else 0


if __name__ == '__main__':
    raise SystemExit(main())
