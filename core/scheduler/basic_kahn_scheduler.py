"""
基础 Kahn 调度器（无优先级，无关键路径计算）
作为消融实验的对照组，与 PriorityScheduler 对比
"""

import logging
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field

from core.scheduler.dag_builder import DAGBuilder

logger = logging.getLogger(__name__)


@dataclass
class SchedulePlan:
    layers: List[List[str]] = field(default_factory=list)
    node_priorities: Dict[str, float] = field(default_factory=dict)
    total_layers: int = 0
    total_nodes: int = 0
    critical_path_length: float = 0.0
    
    def add_layer(self, nodes: List[str]):
        self.layers.append(nodes)
        self.total_layers += 1
        self.total_nodes += len(nodes)
    
    def to_dict(self) -> Dict:
        return {
            'layers': self.layers,
            'node_priorities': self.node_priorities,
            'total_layers': self.total_layers,
            'total_nodes': self.total_nodes,
            'critical_path_length': self.critical_path_length
        }


class BasicKahnScheduler:
    """
    基础 Kahn 拓扑排序调度器
    - 不计算优先级
    - 就绪队列按 FIFO 顺序（先入先出）
    - 作为消融实验的对照组
    """
    
    def __init__(self, max_concurrency: int = 8, cost_func: Optional[Callable] = None):
        self.W = max_concurrency
        self.cost_func = cost_func or (lambda node: node.estimated_cost)
        self.priorities: Dict[str, float] = {}
    
    def schedule(self, dag: DAGBuilder) -> SchedulePlan:
        plan = SchedulePlan()
        
        # 计算每个节点的耗时（用于关键路径计算，但调度时不使用）
        in_degree: Dict[str, int] = {}
        node_costs: Dict[str, float] = {}
        
        for node_id in dag.get_all_nodes():
            in_degree[node_id] = dag.get_in_degree(node_id)
            node = dag.get_node(node_id)
            node_costs[node_id] = self.cost_func(node) if node else 1.0
            self.priorities[node_id] = 0.0  # 无优先级，全部为0
        
        # 就绪队列：入度为0的节点，FIFO顺序
        ready_queue: List[str] = [nid for nid, deg in in_degree.items() if deg == 0]
        
        remaining = set(dag.get_all_nodes())
        total_layers = 0
        
        # 记录每个节点的最早完成时间（用于计算关键路径）
        earliest_finish: Dict[str, float] = {}
        for node_id in dag.get_all_nodes():
            if dag.get_in_degree(node_id) == 0:
                earliest_finish[node_id] = node_costs.get(node_id, 1.0)
        
        while ready_queue and remaining:
            # 取前W个节点作为当前层（FIFO）
            layer_size = min(len(ready_queue), self.W)
            current_layer = ready_queue[:layer_size]
            ready_queue = ready_queue[layer_size:]
            
            plan.add_layer(current_layer)
            total_layers += 1
            
            # 更新入度
            for node_id in current_layer:
                remaining.discard(node_id)
                for succ_id in dag.get_successors(node_id):
                    if succ_id in remaining:
                        in_degree[succ_id] -= 1
                        # 计算最早完成时间
                        finish_time = earliest_finish.get(node_id, 0) + node_costs.get(succ_id, 1.0)
                        if succ_id not in earliest_finish or finish_time > earliest_finish[succ_id]:
                            earliest_finish[succ_id] = finish_time
                        if in_degree[succ_id] == 0:
                            ready_queue.append(succ_id)
        
        # 计算关键路径：取最大最早完成时间
        if earliest_finish:
            plan.critical_path_length = max(earliest_finish.values())
        else:
            plan.critical_path_length = 0
        
        plan.node_priorities = self.priorities
        plan.total_layers = len(plan.layers)
        plan.total_nodes = sum(len(layer) for layer in plan.layers)
        
        logger.info(f"Basic Kahn: {plan.total_nodes} nodes in {plan.total_layers} layers")
        logger.info(f"Critical path: {plan.critical_path_length:.3f}s")
        
        return plan
