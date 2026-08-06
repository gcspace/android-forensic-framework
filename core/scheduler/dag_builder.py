"""
DAG构建与环路检测模块
- YAML场景解析: 读取原子节点和依赖边
- DAG图构建: 基于NetworkX
- 三色标记环路检测: DFS算法 (论文2.4节)
- 拓扑排序准备: 计算入度、就绪队列
"""

import yaml
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

import networkx as nx

logger = logging.getLogger(__name__)


class NodeColor(Enum):
    """三色标记状态"""
    WHITE = 0   # 未访问
    GRAY = 1    # 访问中（在递归栈中）
    BLACK = 2   # 已完成


@dataclass
class AtomicNode:
    """DAG中的原子节点"""
    id: str
    op_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    api_level: int = 33
    estimated_cost: float = 1.0  # 预估执行耗时（秒）
    priority: float = 0.0        # 静态优先级（由调度器计算）
    depends_on: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'op_type': self.op_type,
            'params': self.params,
            'api_level': self.api_level,
            'estimated_cost': self.estimated_cost,
            'priority': self.priority,
            'depends_on': self.depends_on
        }


class DAGBuilder:
    """
    DAG构建器
    - 从YAML解析场景配置
    - 构建NetworkX有向图
    - 执行三色标记环路检测
    """
    
    def __init__(self):
        self.graph = nx.DiGraph()
        self.nodes: Dict[str, AtomicNode] = {}
        self.node_colors: Dict[str, NodeColor] = {}
        self.cycle_detected = False
        self.cycle_path: List[str] = []
    
    def load_yaml(self, yaml_path: str) -> 'DAGBuilder':
        """
        从YAML文件加载场景配置
        预期格式:
            name: 场景名称
            api_level: 33
            nodes:
              - id: click_1
                type: UI_CLICK
                params: {x: 100, y: 200}
                depends_on: []
                estimated_cost: 0.5
              - id: create_file
                type: FILE_CREATE
                params: {path: test.txt}
                depends_on: [click_1]
        """
        with open(yaml_path, 'r') as f:
            config = yaml.safe_load(f)
        
        return self.load_dict(config)
    
    def load_dict(self, config: Dict) -> 'DAGBuilder':
        """从字典加载场景配置"""
        api_level = config.get('api_level', 33)
        
        for node_data in config.get('nodes', []):
            node_id = node_data.get('id')
            if not node_id:
                raise ValueError("Node missing 'id' field")
            
            node = AtomicNode(
                id=node_id,
                op_type=node_data.get('type', 'UI_CLICK'),
                params=node_data.get('params', {}),
                api_level=api_level,
                estimated_cost=node_data.get('estimated_cost', 1.0),
                depends_on=node_data.get('depends_on', [])
            )
            
            self.add_node(node)
        
        # 添加依赖边
        for node in self.nodes.values():
            for dep_id in node.depends_on:
                if dep_id in self.nodes:
                    self.graph.add_edge(dep_id, node.id)
                else:
                    logger.warning(f"Node '{node.id}' depends on unknown node '{dep_id}'")
        
        return self
    
    def add_node(self, node: AtomicNode) -> 'DAGBuilder':
        """添加节点到DAG"""
        self.nodes[node.id] = node
        self.graph.add_node(node.id, data=node)
        return self
    
    def add_edge(self, from_id: str, to_id: str) -> 'DAGBuilder':
        """添加依赖边 from_id -> to_id (to_id依赖from_id)"""
        if from_id not in self.nodes or to_id not in self.nodes:
            raise ValueError(f"Invalid edge: {from_id} -> {to_id}")
        self.graph.add_edge(from_id, to_id)
        return self
    
    def detect_cycle(self) -> Tuple[bool, List[str]]:
        """
        三色标记DFS环路检测 (论文2.4节)
        返回: (是否存在环路, 环路上的节点列表)
        """
        # 初始化所有节点为白色（未访问）
        self.node_colors = {node_id: NodeColor.WHITE for node_id in self.nodes}
        self.cycle_detected = False
        self.cycle_path = []
        
        for node_id in self.nodes:
            if self.node_colors[node_id] == NodeColor.WHITE:
                self._dfs_visit(node_id, [])
                if self.cycle_detected:
                    break
        
        return self.cycle_detected, self.cycle_path
    
    def _dfs_visit(self, node_id: str, path: List[str]):
        """DFS访问单个节点"""
        if self.cycle_detected:
            return
        
        self.node_colors[node_id] = NodeColor.GRAY
        path.append(node_id)
        
        for successor in self.graph.successors(node_id):
            if self.node_colors[successor] == NodeColor.WHITE:
                self._dfs_visit(successor, path)
            elif self.node_colors[successor] == NodeColor.GRAY:
                # 发现回边 -> 存在环路
                self.cycle_detected = True
                # 提取环路上的节点
                idx = path.index(successor)
                self.cycle_path = path[idx:] + [successor]
                return
        
        self.node_colors[node_id] = NodeColor.BLACK
        path.pop()
    
    def validate(self) -> bool:
        """
        验证DAG合法性
        1. 无环路
        2. 所有依赖存在
        3. 无孤立节点（可选）
        """
        has_cycle, cycle_path = self.detect_cycle()
        if has_cycle:
            logger.error(f"Cycle detected: {' -> '.join(cycle_path)}")
            return False
        
        # 检查所有依赖是否存在
        for node_id, node in self.nodes.items():
            for dep_id in node.depends_on:
                if dep_id not in self.nodes:
                    logger.error(f"Node '{node_id}' depends on non-existent node '{dep_id}'")
                    return False
        
        return True
    
    def get_ready_nodes(self) -> List[str]:
        """
        获取就绪节点（入度为0）
        用于调度器的初始化
        """
        in_degrees = dict(self.graph.in_degree())
        return [nid for nid, deg in in_degrees.items() if deg == 0]
    
    def get_in_degree(self, node_id: str) -> int:
        """获取节点的入度"""
        return self.graph.in_degree(node_id)
    
    def get_out_degree(self, node_id: str) -> int:
        """获取节点的出度"""
        return self.graph.out_degree(node_id)
    
    def get_successors(self, node_id: str) -> List[str]:
        """获取节点的后继节点列表"""
        return list(self.graph.successors(node_id))
    
    def get_predecessors(self, node_id: str) -> List[str]:
        """获取节点的前驱节点列表"""
        return list(self.graph.predecessors(node_id))
    
    def get_node(self, node_id: str) -> Optional[AtomicNode]:
        """获取节点数据"""
        return self.nodes.get(node_id)
    
    def get_all_nodes(self) -> List[str]:
        """获取所有节点ID列表"""
        return list(self.nodes.keys())
    
    def get_edge_count(self) -> int:
        """获取边数量"""
        return self.graph.number_of_edges()
    
    def get_node_count(self) -> int:
        """获取节点数量"""
        return self.graph.number_of_nodes()
    
    def to_dict(self) -> Dict:
        """导出为字典"""
        return {
            'nodes': [node.to_dict() for node in self.nodes.values()],
            'edges': list(self.graph.edges()),
            'valid': self.validate()
        }
    
    def to_yaml(self, output_path: str):
        """导出为YAML文件"""
        data = {
            'nodes': [
                {
                    'id': nid,
                    'type': node.op_type,
                    'params': node.params,
                    'depends_on': node.depends_on,
                    'estimated_cost': node.estimated_cost
                }
                for nid, node in self.nodes.items()
            ]
        }
        with open(output_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)


# 便捷函数
def build_dag_from_yaml(yaml_path: str) -> DAGBuilder:
    """从YAML文件构建DAG"""
    builder = DAGBuilder()
    builder.load_yaml(yaml_path)
    return builder


def build_dag_from_dict(config: Dict) -> DAGBuilder:
    """从字典构建DAG"""
    builder = DAGBuilder()
    builder.load_dict(config)
    return builder
