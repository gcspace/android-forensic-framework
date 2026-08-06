#!/usr/bin/env python3
"""
恶意场景量化测试 (论文4.3.4节)
"""

import sys
import os
import json
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scheduler.dag_builder import DAGBuilder
from core.scheduler.priority_scheduler import PriorityScheduler, SerialBaselineScheduler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_scenario(yaml_path: str, mode: str = 'concurrent'):
    builder = DAGBuilder()
    builder.load_yaml(yaml_path)
    
    if not builder.validate():
        logger.error(f"DAG validation failed: {yaml_path}")
        return None
    
    if mode == 'serial':
        scheduler = SerialBaselineScheduler()
    else:
        scheduler = PriorityScheduler(max_concurrency=8)
    
    plan = scheduler.schedule(builder)
    
    return {
        'scenario': os.path.basename(yaml_path),
        'mode': mode,
        'total_nodes': plan.total_nodes,
        'total_layers': plan.total_layers,
        'critical_path_length': plan.critical_path_length,
        'node_priorities': plan.node_priorities
    }


def main():
    scenarios = [
        'config/scenarios/malicious_privacy.yaml',
        'config/scenarios/malicious_phishing.yaml',
        'config/scenarios/malicious_ransomware.yaml'
    ]
    
    results = []
    for yaml_path in scenarios:
        logger.info(f"=" * 60)
        logger.info(f"Running: {yaml_path}")
        
        result_conc = run_scenario(yaml_path, 'concurrent')
        if result_conc:
            results.append(result_conc)
        
        result_serial = run_scenario(yaml_path, 'serial')
        if result_serial:
            results.append(result_serial)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'output/groundtruth/malicious_results_{timestamp}.json'
    os.makedirs('output/groundtruth', exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Results saved to: {output_file}")
    
    print("\n" + "=" * 80)
    print("MALICIOUS SCENARIO SUMMARY")
    print("=" * 80)
    print(f"{'Scenario':<25} {'Mode':<12} {'Layers':<8} {'Critical Path':<15}")
    print("-" * 80)
    for r in results:
        name = r['scenario'].replace('.yaml', '')
        print(f"{name:<25} {r['mode']:<12} {r['total_layers']:<8} {r['critical_path_length']:<15.2f}")
    print("=" * 80)


if __name__ == '__main__':
    main()
