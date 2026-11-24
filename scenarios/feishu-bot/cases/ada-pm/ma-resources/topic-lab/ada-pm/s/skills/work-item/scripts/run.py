"""One real worker's file operations; no agent dispatch, model or network calls."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import uuid
from datetime import datetime, timezone
from jsonschema import Draft202012Validator

sys.dont_write_bytecode = True
PACKAGE = Path(__file__).resolve().parents[1]
VERSION = json.loads((PACKAGE / 'references/version.json').read_text())['version']
PARAMS = json.loads((PACKAGE / 'references/parameters.json').read_text())
spec = importlib.util.spec_from_file_location('work_item_atomic', PACKAGE / 'lib/atomic.py')
atomic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(atomic)


def read(path):
    return json.loads(Path(path).read_text())


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(contract, value):
    Draft202012Validator(read(PACKAGE / 'contracts' / (contract + '.json'))).validate(value)


class Worker:
    def __init__(self, role, context, workspace):
        self.role, self.ctx = role, context
        self.workspace = Path(workspace).resolve()
        if self.workspace.is_relative_to(PACKAGE):
            raise ValueError('Workspace必须位于资源包之外')
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.artifacts, self.receipts, self.checks = [], [], []
        validate('handoff.pm-worker', context)
        if context['recipient'] != role:
            raise ValueError('Context.recipient与本次真实角色不一致')
        if type(context['confirmation_version']) is not int or context['confirmation_version'] <= 0:
            raise ValueError('需要正整数的有效确认版本')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', context['run_id']):
            raise ValueError('run_id必须为安全的非空关联标识')
        if not context['sources'] or not all(isinstance(x.get('ref'), str) and x['ref'] for x in context['sources']):
            raise ValueError('Context需要实际输入来源引用')
        if not context['inputs']:
            raise ValueError('Context.inputs[0]需指向已保存的采用输入')
        self.input_path = self.safe(context['inputs'][0], exists=True)
        payload = read(self.input_path)
        for field, expected in [('run_id', context['run_id']), ('confirmation_version', context['confirmation_version'])]:
            if isinstance(payload, dict) and field in payload and payload[field] != expected:
                raise ValueError('采用输入与Context的' + field + '不一致')
        self.facts = payload.get('facts', payload)
        if not isinstance(self.facts, dict) or any(not isinstance(self.facts.get(k), str) or not self.facts[k].strip() for k in ('object', 'period', 'purpose')):
            raise ValueError('采用输入缺对象、周期或用途')
        self.folder = self.safe(Path('runs') / context['run_id'] / 'artifacts' / role / uuid.uuid4().hex[:12])
        self.upstream = context['upstream_artifacts']

    def safe(self, value, exists=False):
        path = Path(value)
        path = (path if path.is_absolute() else self.workspace / path).resolve()
        if not path.is_relative_to(self.workspace) or path.is_relative_to(PACKAGE):
            raise ValueError('路径越出Workspace或进入稳定资源包')
        if exists and not path.is_file():
            raise ValueError('文件不存在：' + str(value))
        return path

    def put(self, filename, content, kind):
        path = self.safe(self.folder / filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else encoded(content))
        item = {'artifact_id': 'art-' + uuid.uuid4().hex, 'version': '1.0.0',
                'sha256': digest(path), 'path': str(path.relative_to(self.workspace)),
                'producer': self.role, 'task_id': self.ctx['task_id'], 'run_id': self.ctx['run_id'],
                'kind': kind, 'confirmation_version': self.ctx['confirmation_version'],
                'source_refs': [x['ref'] for x in self.ctx['sources']], 'copies': [],
                'resource_version': VERSION, 'created_at': datetime.now(timezone.utc).isoformat()}
        validate('output.artifact', item)
        self.artifacts.append(item)
        return item

    def check_upstream(self):
        ids = set()
        for item in self.upstream:
            if not item.get('artifact_id') or item['artifact_id'] in ids:
                raise ValueError('上游产物缺编号或重复')
            ids.add(item['artifact_id'])
            if item.get('run_id') != self.ctx['run_id'] or item.get('task_id', self.ctx['task_id']) != self.ctx['task_id']:
                raise ValueError('上游产物不属于当前任务/运行')
            version = item.get('confirmation_version', item.get('plan_version'))
            if type(version) is not int or version != self.ctx['confirmation_version']:
                raise ValueError('上游产物对应不同确认版本')
            if not isinstance(item.get('version'), str) or not item['version']:
                raise ValueError('上游产物缺内容版本')
            if not re.fullmatch('[a-f0-9]{64}', item.get('sha256', '')):
                raise ValueError('上游产物缺有效摘要')
            path = self.safe(item.get('path', ''), exists=True)
            if not path.stat().st_size:
                raise ValueError('上游产物为空：' + item['artifact_id'])
            if digest(path) != item['sha256']:
                raise ValueError('上游产物摘要不一致：' + item['artifact_id'])

    def call(self, action, payload, filename):
        params = copy.deepcopy(PARAMS[action])
        params.update(payload)
        result = atomic.execute(action, params)
        self.receipts.append(result['receipt'])
        self.put(filename + '-receipt.json', result['receipt'], 'receipt')
        if result['status'] == 'failed':
            raise ValueError(action + '失败：' + ';'.join(result['receipt']['errors']))
        self.put(filename + '.json', result['output'], 'data')
        return result['output']

    def produce(self):
        facts = self.facts
        topic, action = facts.get('topic'), facts.get('action')
        if self.role == 't' and topic not in ('social', 'audience'):
            raise ValueError('t只执行已声明的social/audience Demo Topic')
        if self.role == 'g' and action not in ('deduplicate', 'aggregate'):
            raise ValueError('g只执行明确的deduplicate/aggregate局部动作')
        data = facts.get('extra_dataset') if self.role == 'g' and topic else facts.get('dataset')
        if self.role == 'g' and topic:
            if not data:
                raise ValueError('t+g必须提供独立extra_dataset，不能重复Topic内部工作')
            main = facts.get('dataset', {})
            if data.get('schema') == main.get('schema') and data.get('rows') == main.get('rows'):
                raise ValueError('局部工作与Topic使用相同数据，不能冒充独立剩余')
        validate('input.envelope', data)
        if not data['rows']:
            raise ValueError('输入为空，不生成专业结论')
        merged = self.call('merge', {'batches': [{'batch_id': 'adopted-input', 'dataset': data}]}, '01-merged')['merged']
        fields = copy.deepcopy(PARAMS['validate']['rules']['field_rules'])
        if self.role == 't' or action == 'aggregate':
            fields.append({'field': 'region', 'required': True, 'type': 'string'})
        if self.role == 't' and topic == 'social':
            fields.extend([{'field': 'text', 'required': True, 'type': 'string'},
                           {'field': 'sentiment', 'required': True, 'type': 'enum',
                            'enum': ['positive', 'neutral', 'negative', 'unknown']}])
        valid = self.call('validate', {'dataset': merged, 'rules': {'field_rules': fields}}, '02-validation')['valid_rows']
        if not valid['rows']:
            raise ValueError('全部样本无效；已保存校验和剔除明细')
        dedup = self.call('deduplicate', {'dataset': valid}, '03-dedup')['deduped_rows']
        metrics = None
        if self.role == 't' or action == 'aggregate':
            metrics = self.call('metrics', {'dataset': dedup}, '04-metrics')
            chart = atomic.execute('chart', {**copy.deepcopy(PARAMS['chart']), 'dataset': metrics['metric_table']})
            self.receipts.append(chart['receipt'])
            self.put('05-chart-receipt.json', chart['receipt'], 'receipt')
            if chart['status'] == 'failed':
                raise ValueError('chart失败：' + ';'.join(chart['receipt']['errors']))
            self.put('05-chart.svg', chart['output']['artifact']['content_ref'], 'chart')
        if self.role == 't' and topic == 'social':
            definitions = copy.deepcopy(PARAMS['metrics']['metrics_def'])
            definitions['dimensions'] = ['sentiment']
            definitions['metrics'][0]['caliber'] = '按有效去重合成样本的显式sentiment标签计数，不代表真实模型标注'
            self.call('metrics', {'dataset': dedup, 'metrics_def': definitions}, '06-sentiment')
        report = '# ' + self.role + ' 合成Demo阶段结果\n\n'
        report += '对象：' + facts['object'] + '；周期：' + facts['period'] + '\n\n'
        report += f"原始{len(data['rows'])}行，有效{len(valid['rows'])}行，去重后{len(dedup['rows'])}行。\n\n"
        if metrics:
            report += '## 本次计算\n\n' + encoded(metrics['metric_table']['rows']) + '\n\n口径：' + encoded(metrics['metric_manifest']) + '\n\n'
        report += '## 来源与限制\n\n仅使用本次采用输入和明确参数。合成样本/显式标签，不外推真实总体、购买或因果。此文件是确定性Demo替身的阶段结果，不冒充模型专业报告。\n'
        self.put('07-report.md', report, 'report')
        saved = atomic.execute('save', {**copy.deepcopy(PARAMS['save']), 'receipts': self.receipts,
                                       'output_root': str(self.folder / 'receipts')})
        if saved['status'] == 'failed':
            raise ValueError('原子回执保存失败')
        self.put('08-atomic-receipt-index.json', saved['output'], 'receipt')

    def inspect(self):
        issues = []
        try:
            self.check_upstream()
        except (ValueError, KeyError, OSError) as exc:
            issues.append(str(exc))
        production = [a for a in self.upstream if a.get('producer') in ('t', 'g')]
        if not production:
            issues.append('缺少待检查的t/g产物')
        for role in sorted({a.get('producer') for a in production}):
            selected = [a for a in production if a['producer'] == role]
            if not any(a.get('kind') == 'report' for a in selected) or not any(a.get('kind') == 'data' for a in selected):
                issues.append(role + '缺必要报告或数据')
            expected = ['01-merged.json', '02-validation.json', '03-dedup.json', '07-report.md']
            if role == 't' or self.facts.get('action') == 'aggregate':
                expected.extend(['04-metrics.json', '05-chart.svg'])
            if role == 't' and self.facts.get('topic') == 'social':
                expected.append('06-sentiment.json')
            names = {Path(a.get('path', '')).name for a in selected}
            issues.extend(role + '缺必需阶段文件：' + name for name in expected if name not in names)
        check = {'conclusion': '失败' if issues else '通过', 'rules_version': VERSION,
                 'executor': 'validator', 'task_id': self.ctx['task_id'],
                 'run_id': self.ctx['run_id'], 'confirmation_version': self.ctx['confirmation_version'],
                 'artifacts': [{'artifact_id': a.get('artifact_id'), 'version': a.get('version'),
                                'sha256': a.get('sha256')} for a in production],
                 'evidence': issues or ['实际文件存在、摘要匹配、同run/确认版本、必要报告与数据齐备'],
                 'limitations': ['结构和文件检查，不替代模型或业务专业质量验收']}
        self.checks.append(check)
        self.put('validation.json', check, 'validation')
        if issues:
            raise ValueError('必要检查失败：' + ';'.join(issues))

    def check_complete_results(self, required, need_validator):
        paths = self.ctx['scope'].get('upstream_results')
        if not isinstance(paths, list) or not paths or any(not isinstance(p, str) or not p for p in paths):
            raise ValueError('s需要scope.upstream_results列出上游完整标准返回JSON文件')
        expected = set(required) | ({'validator'} if need_validator else set())
        if any(a.get('producer') not in expected for a in self.upstream):
            raise ValueError('Context包含不属于当前依赖的上游生产者')
        found = {}
        for ref in paths:
            result = read(self.safe(ref, exists=True))
            validate('output.worker-result', result)
            role = result['recipient']
            if role == 's' or role not in expected or role in found:
                raise ValueError('上游返回角色多余、重复或引用了s自己的返回')
            if (result.get('status') != 'complete' or result.get('task_id') != self.ctx['task_id']
                    or result.get('run_id') != self.ctx['run_id']
                    or result.get('confirmation_version') != self.ctx['confirmation_version']):
                raise ValueError('上游标准返回未完整完成或任务/运行/确认版本不匹配：' + role)
            actual = result['artifacts']
            context_items = [a for a in self.upstream if a['producer'] == role]
            # path 的绝对/相对表示不影响产物身份；按内容身份(id/version/sha256/kind)比对，
            # 避免 Context 把 path 写成绝对路径（甚至 runs/run-001 重复拼接）而返回里是相对路径时被误判不一致。
            def _ident(a):
                return (a.get('artifact_id'), a.get('version'), a.get('sha256'), a.get('kind'))
            if (not actual or len({a.get('artifact_id') for a in actual}) != len(actual)
                    or sorted(_ident(a) for a in actual) != sorted(_ident(a) for a in context_items)):
                raise ValueError('上游完整返回的产物对象与Context不一致：' + role)
            if role == 'validator':
                checks = result.get('checks')
                files = [read(self.safe(a['path'], exists=True)) for a in actual if a.get('kind') == 'validation']
                if not checks or checks != files or any(c.get('conclusion') != '通过' for c in checks):
                    raise ValueError('validator完整返回缺通过检查或与实际validation文件不一致')
            found[role] = result
        if set(found) != expected:
            raise ValueError('缺少必需角色的完整标准返回：' + ','.join(sorted(expected - set(found))))
        return paths

    def integrate(self, draft=None):
        if self.facts.get('human'):
            raise ValueError('h负责最终整合的路径禁止s重复整合')
        self.check_upstream()
        required = self.ctx['scope'].get('production_required')
        if required is None:
            required = (['t'] if self.facts.get('topic') else []) + (['g'] if self.facts.get('action') else [])
        if not isinstance(required, list) or not required or any(r not in ('t', 'g') for r in required):
            raise ValueError('scope.production_required需明确非空t/g依赖')
        for role in required:
            items = [a for a in self.upstream if a.get('producer') == role]
            if not any(a.get('kind') == 'report' for a in items) or not any(a.get('kind') == 'data' for a in items):
                raise ValueError('所需' + role + '报告/数据尚未齐备')
        need_validator = self.ctx['scope'].get('require_validator', 't' in required)
        if type(need_validator) is not bool:
            raise ValueError('scope.require_validator必须为布尔值')
        if 't' in required and not need_validator:
            raise ValueError('完整Topic的必要validator不能关闭')
        result_paths = self.check_complete_results(required, need_validator)
        if need_validator:
            checks = [read(self.safe(a['path'], exists=True)) for a in self.upstream
                      if a.get('producer') == 'validator' and a.get('kind') == 'validation']
            checked = set()
            for check in checks:
                if (check.get('conclusion') != '通过' or check.get('run_id') != self.ctx['run_id']
                        or check.get('rules_version') != VERSION or check.get('executor') != 'validator'
                        or check.get('confirmation_version') != self.ctx['confirmation_version']):
                    raise ValueError('上游必要检查失败或版本不一致')
                checked.update((a['artifact_id'], a['version'], a['sha256']) for a in check.get('artifacts', []))
            targets = [a for a in self.upstream if a.get('producer') in required
                       and (a['producer'] == 't' or 't' not in required)]
            if not checks or any((a['artifact_id'], a['version'], a['sha256']) not in checked for a in targets):
                raise ValueError('缺少覆盖当前实际产物的通过检查')
        if draft is None:
            raise ValueError('s须先阅读真实上游并由本Agent撰写Markdown草稿，再用--draft保存；脚本不代写整合结论')
        path = self.safe(draft, exists=True)
        text = path.read_text()
        if path.suffix.lower() != '.md' or not text.strip():
            raise ValueError('s草稿须为Workspace内非空Markdown')
        self.put('integrated.md', text, 'strategy')
        self.put('integration-sources.json', {'draft_source': str(path.relative_to(self.workspace)),
                 'draft_sha256': digest(path), 'upstream_artifacts': self.upstream,
                 'upstream_results': [{'path': str(self.safe(p).relative_to(self.workspace)),
                                       'sha256': digest(self.safe(p))} for p in result_paths],
                 'limitation': '脚本只核验依赖与保存本Agent稿件；整合专业质量由业务验收'}, 'index')

    def result(self, error=None):
        value = {'recipient': self.role, 'work_item': self.ctx['work_item'],
                 'task_id': self.ctx['task_id'], 'run_id': self.ctx['run_id'],
                 'confirmation_version': self.ctx['confirmation_version'],
                 'artifacts': self.artifacts, 'evidence': [a['artifact_id'] for a in self.artifacts],
                 'limitations': ['合成Demo能力及文件操作；无外部系统、模型调用或子Agent创建'],
                 'status': 'failed' if error else 'complete', 'checks': self.checks,
                 'atomic_receipts': self.receipts, 'resource_version': VERSION}
        if error:
            value['limitations'].append(str(error))
        validate('output.worker-result', value)
        return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=['t', 'g', 'validator', 's'], required=True)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--draft', type=Path)
    args = parser.parse_args()
    worker = None
    output_allowed = False
    try:
        worker = Worker(args.role, read(args.context), args.workspace)
        output = worker.safe(args.output)
        protected = [worker.input_path, args.context.resolve()] + [worker.safe(a['path']) for a in worker.upstream]
        protected.extend(worker.safe(p) for p in worker.ctx['scope'].get('upstream_results', []) if isinstance(p, str))
        if output in protected or (args.draft and output == worker.safe(args.draft)):
            raise ValueError('返回文件不能覆盖采用输入、Context、上游产物或整合草稿')
        output_allowed = True
        if args.role in ('t', 'g'):
            worker.check_upstream()
            worker.produce()
        elif args.role == 'validator':
            worker.inspect()
        else:
            worker.integrate(args.draft)
        result = worker.result()
    except Exception as exc:
        if worker is None:
            print(encoded({'status': 'failed', 'error': str(exc).split('\n')[0]}))
            return 1
        result = worker.result(str(exc).split('\n')[0])
        if not output_allowed:
            print(encoded(result))
            return 1
        try:
            output = worker.safe(args.output)
        except ValueError:
            print(encoded(result))
            return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded(result))
    print(encoded(result))
    return 0 if result['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
