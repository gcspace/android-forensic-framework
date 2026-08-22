"""
关键路径优先级调度器 (论文第2.3节)
- 静态优先级计算: P(a_i) = cost(a_i) + max(P(a_j))  (公式4)
- Kahn拓扑排序 + 优先级调度
- 最大并发数: W=8
"""

import logging
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field

from core.scheduler.dag_builder import DAGBuilder, AtomicNode

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


class PriorityScheduler:
    def __init__(self, max_concurrency: int = 8, cost_func: Optional[Callable] = None):
        self.W = max_concurrency
        self.cost_func = cost_func or (lambda node: node.estimated_cost)
        self.priorities: Dict[str, float] = {}
    
    def compute_priorities(self, dag: DAGBuilder) -> Dict[str, float]:
        """
        计算所有节点的静态优先级
        公式(4): P(a_i) = cost(a_i) + max_{a_j in succ(a_i)} P(a_j)
        边界条件: 出度为0的汇点原子 P(a_sink) = cost(a_sink)
        """
        self.priorities = {}
        nodes = dag.get_all_nodes()
        if not nodes:
            return {}
        
        visited = set()
        
        def dfs(node_id: str) -> float:
            if node_id in visited:
                return self.priorities.get(node_id, 0)
            
            visited.add(node_id)
            node = dag.get_node(node_id)
            cost = self.cost_func(node) if node else 1.0
            
            successors = dag.get_successors(node_id)
            
            if not successors:
                # 汇点节点: P(a_sink) = cost(a_sink)
                self.priorities[node_id] = cost
                return cost
            
            # 内部节点: P(a_i) = cost(a_i) + max(P(a_j))
            max_succ_priority = 0.0
            for succ_id in successors:
                if succ_id not in visited:
                    dfs(succ_id)
                p_succ = self.priorities.get(succ_id, 0)
                if p_succ > max_succ_priority:
                    max_succ_priority = p_succ
            
            self.priorities[node_id] = cost + max_succ_priority
            return self.priorities[node_id]
        
        for node_id in nodes:
            if node_id not in visited:
                dfs(node_id)
        
        if self.priorities:
            self.critical_path_length = max(self.priorities.values())
        else:
            self.critical_path_length = 0
        
        logger.info(f"Computed priorities for {len(self.priorities)} nodes")
        logger.info(f"Critical path length: {self.critical_path_length:.3f}s")
        
        return self.priorities
    
    def schedule(self, dag: DAGBuilder) -> SchedulePlan:
        plan = SchedulePlan()
        self.compute_priorities(dag)
        plan.node_priorities = self.priorities.copy()
        plan.critical_path_length = self.critical_path_length
        
        in_degree: Dict[str, int] = {}
        for node_id in dag.get_all_nodes():
            in_degree[node_id] = dag.get_in_degree(node_id)
        
        ready_queue: List[str] = [nid for nid, deg in in_degree.items() if deg == 0]
        ready_queue.sort(key=lambda x: self.priorities.get(x, 0), reverse=True)
        
        remaining = set(dag.get_all_nodes())
        
        while ready_queue and remaining:
            layer_size = len(ready_queue)  # 每层执行所有就绪原子，不受 W 限制
            current_layer = ready_queue[:layer_size]
            ready_queue = ready_queue[layer_size:]
            plan.add_layer(current_layer)
            
            for node_id in current_layer:
                remaining.discard(node_id)
                for succ_id in dag.get_successors(node_id):
                    if succ_id in remaining:
                        in_degree[succ_id] -= 1
                        if in_degree[succ_id] == 0:
                            ready_queue.append(succ_id)
            
            ready_queue.sort(key=lambda x: self.priorities.get(x, 0), reverse=True)
        
        if remaining:
            logger.warning(f"Unreachable nodes: {remaining}")
        
        plan.total_layers = len(plan.layers)
        plan.total_nodes = sum(len(layer) for layer in plan.layers)
        
        logger.info(f"Scheduled {plan.total_nodes} nodes in {plan.total_layers} layers")
        
        return plan


class SerialBaselineScheduler:
    def __init__(self, cost_func: Optional[Callable] = None):
        self.cost_func = cost_func or (lambda node: node.estimated_cost)
        self.priorities: Dict[str, float] = {}
    
    def schedule(self, dag: DAGBuilder) -> SchedulePlan:
        plan = SchedulePlan()
        
        try:
            import networkx as nx
            topo_order = list(nx.topological_sort(dag.graph))
        except nx.NetworkXError:
            logger.error("DAG contains cycle, cannot perform topological sort")
            return plan
        
        serial_time = 0.0
        for node_id in topo_order:
            plan.add_layer([node_id])
            node = dag.get_node(node_id)
            cost = self.cost_func(node) if node else 1.0
            self.priorities[node_id] = cost
            serial_time += cost
        
        plan.node_priorities = self.priorities
        plan.total_nodes = len(topo_order)
        plan.total_layers = len(topo_order)
        plan.critical_path_length = serial_time
        
        logger.info(f"Serial schedule: {plan.total_nodes} nodes, total time: {serial_time:.3f}s")
        
        return plan
