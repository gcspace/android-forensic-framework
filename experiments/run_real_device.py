#!/usr/bin/env python3
"""
真实 ADB 执行 + 痕迹采集脚本
在真实设备/模拟器上执行原子操作，记录实际耗时
"""

import sys
import os
import json
import time
import logging
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scheduler.dag_builder import DAGBuilder
from core.scheduler.priority_scheduler import PriorityScheduler
from core.scheduler.basic_kahn_scheduler import BasicKahnScheduler
from core.executor.adb_manager import get_pool
from core.executor.atomic_ops import AtomicFactory
from core.collector.file_snapshot import get_collector, get_boot_time_ms

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_scenario_on_device(yaml_path: str, api_level: int = 33, scheduler_type: str = 'priority', max_concurrency: int = 8):
    """在真实设备上运行场景"""
    logger.info(f"Loading scenario: {yaml_path}")
    
    # 构建DAG
    builder = DAGBuilder()
    builder.load_yaml(yaml_path)
    
    # 选择调度器
    if scheduler_type == 'basic':
        scheduler = BasicKahnScheduler(max_concurrency=max_concurrency)
        logger.info(f"Using BasicKahnScheduler (max_concurrency={max_concurrency})")
    else:
        scheduler = PriorityScheduler(max_concurrency=max_concurrency)
        logger.info(f"Using PriorityScheduler (max_concurrency={max_concurrency})")
    
    plan = scheduler.schedule(builder)
    logger.info(f"Schedule: {plan.total_layers} layers, {plan.total_nodes} nodes")
    
    # 获取设备
    pool = get_pool()
    devices = pool.get_device_list()
    if not devices:
        logger.error("No devices found")
        return None
    
    serial = devices[0]
    logger.info(f"Using device: {serial}")
    
    # 执行
    start_time = time.time()
    atom_records = []
    for layer_idx, layer in enumerate(plan.layers):
        logger.info(f"Layer {layer_idx+1}/{plan.total_layers}: {len(layer)} nodes")
        for node_id in layer:
            node_data = builder.get_node(node_id)
            logger.info(f"  Executing: {node_id} ({node_data.op_type})")
            
            params = node_data.params if hasattr(node_data, 'params') else {}
            op = AtomicFactory.create(
                node_data.op_type,
                api_level=api_level,
                serial=serial,
                params=params
            )
            result = op.execute()
            # 记录原子执行信息
            atom_records.append({
                'id': node_id,
                'op_type': node_data.op_type,
                'success': result.success,
                'duration_ms': result.duration_ms,
                'timestamp_start': result.timestamp_start,
                'timestamp_end': result.timestamp_end,
                'error': result.error
            })
            if result.success:
                logger.info(f"    ✅ {node_id} completed in {result.duration_ms:.2f}ms")
            else:
                logger.warning(f"    ❌ {node_id} failed: {result.error}")
    
    total_time = time.time() - start_time
    logger.info(f"总耗时: {total_time:.2f}s")
    
    return {
        'total_nodes': plan.total_nodes,
        'total_layers': plan.total_layers,
        'total_time': total_time,
        'scheduler': scheduler_type,
        'max_concurrency': max_concurrency,
        'timestamp': datetime.now().isoformat(),
        'atoms': atom_records
    
    }


def main():
    parser = argparse.ArgumentParser(description='Run real device experiment with configurable scheduler and concurrency')
    parser.add_argument('api_level', type=int, help='API level (e.g., 33)')
    parser.add_argument('config', type=str, help='Path to YAML config file')
    parser.add_argument('--scheduler', type=str, default='priority', choices=['priority', 'basic'],
                        help='Scheduler type: priority (default) or basic (Kahn)')
    parser.add_argument('--max-concurrency', type=int, default=8,
                        help='ADB max concurrent sessions (default: 8)')
    args = parser.parse_args()
    
    logger.info(f"Running on API {args.api_level}: {args.config}")
    logger.info(f"Scheduler: {args.scheduler}")
    logger.info(f"Max concurrency: {args.max_concurrency}")
    
    result = run_scenario_on_device(
        args.config,
        api_level=args.api_level,
        scheduler_type=args.scheduler,
        max_concurrency=args.max_concurrency
    )
    
    if result:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'output/groundtruth/real_execution_{timestamp}.json'
        os.makedirs('output/groundtruth', exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info(f"Results saved to: {output_file}")
        print(f"\n=== 执行摘要 ===")
        print(f"API: {args.api_level}")
        print(f"节点数: {result['total_nodes']}")
        print(f"层数: {result['total_layers']}")
        print(f"总耗时: {result['total_time']:.2f}s")
        print(f"调度器: {result['scheduler']}")
        print(f"最大并发: {result['max_concurrency']}")
    else:
        print("实验失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
