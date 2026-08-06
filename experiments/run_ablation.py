#!/usr/bin/env python3
"""
消融实验 (论文4.3.2节)
对比 基础Kahn（无优先级） vs 关键路径优先级调度
"""

import sys
import os
import json
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scheduler.dag_builder import DAGBuilder
from core.scheduler.priority_scheduler import PriorityScheduler
from core.scheduler.basic_kahn_scheduler import BasicKahnScheduler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_scenario(yaml_path: str, scheduler_type: str = 'priority'):
    builder = DAGBuilder()
    builder.load_yaml(yaml_path)
    
    if not builder.validate():
        logger.error(f"DAG validation failed: {yaml_path}")
        return None
    
    if scheduler_type == 'priority':
        scheduler = PriorityScheduler(max_concurrency=8)
        label = 'priority'
    else:
        scheduler = BasicKahnScheduler(max_concurrency=8)
        label = 'basic_kahn'
    
    plan = scheduler.schedule(builder)
    
    return {
        'scenario': os.path.basename(yaml_path),
        'scheduler': label,
        'total_nodes': plan.total_nodes,
        'total_layers': plan.total_layers,
        'critical_path_length': plan.critical_path_length
    }


def main():
    # 基准场景 + 恶意场景
    scenarios = [
        'config/scenarios/baseline_20.yaml',
        'config/scenarios/baseline_50.yaml',
        'config/scenarios/baseline_100.yaml',
        'config/scenarios/malicious_privacy.yaml',
        'config/scenarios/malicious_phishing.yaml',
        'config/scenarios/malicious_ransomware.yaml'
    ]
    
    results = []
    for yaml_path in scenarios:
        logger.info(f"=" * 60)
        logger.info(f"Running: {yaml_path}")
        
        # 关键路径优先级调度
        result_priority = run_scenario(yaml_path, 'priority')
        if result_priority:
            results.append(result_priority)
        
        # 基础Kahn调度（无优先级）
        result_basic = run_scenario(yaml_path, 'basic_kahn')
        if result_basic:
            results.append(result_basic)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'output/groundtruth/ablation_results_{timestamp}.json'
    os.makedirs('output/groundtruth', exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Results saved to: {output_file}")
    
    print("\n" + "=" * 80)
    print("ABLATION EXPERIMENT SUMMARY")
    print("=" * 80)
    print(f"{'Scenario':<22} {'Scheduler':<14} {'Layers':<8} {'Critical Path':<12} {'Gain':<10}")
    print("-" * 80)
    
    # 分组显示
    for i in range(0, len(results), 2):
        if i+1 < len(results):
            r1 = results[i]      # priority
            r2 = results[i+1]    # basic_kahn
            gain = r2['critical_path_length'] - r1['critical_path_length']
            name = r1['scenario'].replace('.yaml', '')
            print(f"{name:<22} {r1['scheduler']:<14} {r1['total_layers']:<8} {r1['critical_path_length']:<12.2f} {gain:<10.2f}")
            print(f"{'':<22} {r2['scheduler']:<14} {r2['total_layers']:<8} {r2['critical_path_length']:<12.2f} {'':<10}")
        else:
            r = results[i]
            name = r['scenario'].replace('.yaml', '')
            print(f"{name:<22} {r['scheduler']:<14} {r['total_layers']:<8} {r['critical_path_length']:<12.2f}")
    print("=" * 80)


if __name__ == '__main__':
    main()
