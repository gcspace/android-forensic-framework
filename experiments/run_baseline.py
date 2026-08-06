#!/usr/bin/env python3
"""
基准场景性能对照实验 (论文4.3.1节)
比较串行基线 vs DAG并发调度
"""

import sys
import os
import json
import time
import logging
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scheduler.dag_builder import DAGBuilder
from core.scheduler.priority_scheduler import PriorityScheduler, SerialBaselineScheduler
from core.executor.adb_manager import get_pool
from core.executor.atomic_ops import AtomicFactory
from core.collector.file_snapshot import get_collector, get_boot_time_ms

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_scenario(yaml_path: str, mode: str = 'concurrent', api_level: int = 33):
    """
    运行单个场景
    
    Args:
        yaml_path: 场景配置文件路径
        mode: 'serial' 或 'concurrent'
        api_level: 设备API版本
    
    Returns:
        执行结果统计
    """
    logger.info(f"Loading scenario: {yaml_path}")
    
    # 1. 构建DAG
    builder = DAGBuilder()
    builder.load_yaml(yaml_path)
    
    # 2. 验证DAG（环路检测）
    if not builder.validate():
        logger.error("DAG validation failed")
        return None
    
    logger.info(f"DAG loaded: {builder.get_node_count()} nodes, {builder.get_edge_count()} edges")
    
    # 3. 创建调度器
    if mode == 'serial':
        scheduler = SerialBaselineScheduler()
        logger.info("Using Serial Baseline Scheduler")
    else:
        scheduler = PriorityScheduler(max_concurrency=8)
        logger.info("Using Priority Scheduler (concurrent, W=8)")
    
    # 4. 生成调度计划
    start_time = time.time()
    plan = scheduler.schedule(builder)
    scheduling_time = time.time() - start_time
    
    logger.info(f"Scheduling completed: {plan.total_layers} layers, {plan.total_nodes} nodes")
    
    # 5. 统计结果（模拟执行，使用预估耗时）
    total_exec_time = 0
    layer_times = []
    
    for layer_idx, layer_nodes in enumerate(plan.layers):
        layer_duration = 0
        for node_id in layer_nodes:
            node = builder.get_node(node_id)
            if node:
                layer_duration += node.estimated_cost
        total_exec_time += layer_duration
        layer_times.append({
            'layer': layer_idx + 1,
            'nodes': layer_nodes,
            'estimated_duration': layer_duration
        })
    
    # 6. 返回结果
    result = {
        'scenario': os.path.basename(yaml_path),
        'mode': mode,
        'api_level': api_level,
        'total_nodes': plan.total_nodes,
        'total_layers': plan.total_layers,
        'critical_path_length': plan.critical_path_length,
        'scheduling_time': scheduling_time,
        'estimated_execution_time': total_exec_time,
        'layers': layer_times,
        'node_priorities': plan.node_priorities
    }
    
    return result


def main():
    """主函数：运行所有基准场景"""
    scenarios = [
        ('config/scenarios/baseline_20.yaml', 20),
        ('config/scenarios/baseline_50.yaml', 50),
        ('config/scenarios/baseline_100.yaml', 100),
    ]
    
    results = []
    
    # 检查ADB设备（仅提示，不影响模拟执行）
    pool = get_pool()
    devices = pool.get_device_list()
    if devices:
        logger.info(f"Connected devices: {devices}")
    else:
        logger.warning("No ADB devices detected. Running in simulation mode (using estimated costs).")
    
    for yaml_path, expected_nodes in scenarios:
        logger.info("=" * 60)
        logger.info(f"Running scenario: {yaml_path}")
        
        # 并发模式
        result_conc = run_scenario(yaml_path, mode='concurrent', api_level=33)
        if result_conc:
            result_conc['expected_nodes'] = expected_nodes
            results.append(result_conc)
        
        # 串行模式（基线）
        result_serial = run_scenario(yaml_path, mode='serial', api_level=33)
        if result_serial:
            result_serial['expected_nodes'] = expected_nodes
            results.append(result_serial)
    
    # 保存结果
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'output/groundtruth/baseline_results_{timestamp}.json'
    
    os.makedirs('output/groundtruth', exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logger.info("=" * 60)
    logger.info(f"Results saved to: {output_file}")
    
    # 打印摘要
    print("\n" + "=" * 80)
    print("BASELINE EXPERIMENT SUMMARY")
    print("=" * 80)
    print(f"{'Scenario':<20} {'Mode':<12} {'Nodes':<8} {'Layers':<8} {'Critical Path':<15}")
    print("-" * 80)
    for r in results:
        name = os.path.basename(r['scenario']).replace('.yaml', '')
        print(f"{name:<20} {r['mode']:<12} {r['total_nodes']:<8} {r['total_layers']:<8} {r['critical_path_length']:<15.2f}")
    print("=" * 80)


if __name__ == '__main__':
    main()
