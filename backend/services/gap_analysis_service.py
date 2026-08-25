"""知识图谱缺口分析服务

分析 graph.json 结构，识别知识薄弱区域和跨领域缺口：
1. 节点度数分析 → 弱节点 / 孤立节点
2. Community 桥接分析 → 缺失桥接
3. 生成文档补充建议 + 覆盖分
"""

import logging
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)

# 常量
WEAK_DEGREE_THRESHOLD = 2  # 弱节点度数阈值（degree ≤ 此值）
COVERAGE_WEIGHTS = (40, 30, 30)  # 覆盖分权重：(弱节点, 孤立节点, 桥接缺失)


class GapAnalysisService:
    """知识图谱缺口分析服务（无状态）"""

    def analyze(self, graph_data: dict) -> dict:
        """对 graph.json 数据执行缺口分析

        Args:
            graph_data: {"nodes": [...], "links": [...]}]

        Returns:
            完整分析结果 dict，见 design doc 返回结构
        """
        nodes = graph_data.get('nodes', [])
        links = graph_data.get('links', graph_data.get('edges', []))

        # 构建邻接表 + 度数
        degree, adjacency = self._build_degree_map(nodes, links)

        # 节点分析
        weak_nodes = self._find_weak_nodes(nodes, degree)
        isolated_nodes = [n for n in weak_nodes if n['degree'] == 0]

        # Community 分析
        community_analysis = self._analyze_communities(nodes, links, degree)
        missing_bridges = self._find_missing_bridges(nodes, links, community_analysis)

        # 建议
        suggestions = self._generate_suggestions(
            weak_nodes, isolated_nodes, community_analysis, missing_bridges
        )

        # 覆盖分
        total_communities = len(community_analysis)
        total_possible_bridges = total_communities * (total_communities - 1) // 2
        coverage_score = self._compute_coverage_score(
            len(nodes), len(weak_nodes), len(isolated_nodes),
            len(missing_bridges), total_possible_bridges
        )

        return {
            'summary': {
                'total_nodes': len(nodes),
                'total_edges': len(links),
                'total_communities': total_communities,
                'weak_node_count': len(weak_nodes),
                'isolated_node_count': len(isolated_nodes),
                'missing_bridge_count': len(missing_bridges),
                'coverage_score': round(coverage_score, 1),
            },
            'weak_nodes': weak_nodes,
            'isolated_nodes': isolated_nodes,
            'community_analysis': community_analysis,
            'missing_bridges': missing_bridges,
            'suggestions': suggestions,
        }

    # === 内部方法 ===

    @staticmethod
    def _build_degree_map(
        nodes: list, links: list
    ) -> tuple[dict[str, int], dict[str, list[str]]]:
        """构建度数表和邻接表"""
        degree: dict[str, int] = defaultdict(int)
        adjacency: dict[str, list[str]] = defaultdict(list)

        for link in links:
            src = link.get('source', '')
            tgt = link.get('target', '')
            if not src or not tgt:
                continue
            degree[src] += 1
            degree[tgt] += 1
            adjacency[src].append(tgt)
            adjacency[tgt].append(src)

        # 确保所有节点都在度数表中（孤立节点 degree=0）
        for node in nodes:
            nid = node.get('id', '')
            if nid:
                degree.setdefault(nid, 0)

        return dict(degree), dict(adjacency)

    @staticmethod
    def _find_weak_nodes(nodes: list, degree: dict[str, int]) -> list[dict]:
        """识别弱节点（degree ≤ 阈值），按度数升序排列"""
        weak = []
        for node in nodes:
            nid = node.get('id', '')
            d = degree.get(nid, 0)
            if d <= WEAK_DEGREE_THRESHOLD:
                weak.append({
                    'id': nid,
                    'label': node.get('label', ''),
                    'degree': d,
                    'community': node.get('community'),
                    'source_file': node.get('source_file', ''),
                })
        weak.sort(key=lambda x: x['degree'])
        return weak

    @staticmethod
    def _analyze_communities(
        nodes: list, links: list, degree: dict[str, int]
    ) -> list[dict]:
        """分析每个 community 的内部结构"""
        # 预构建 node_id → community 映射
        node_community: dict[str, Optional[int]] = {}
        community_nodes: dict[int, list[str]] = defaultdict(list)
        community_labels: dict[int, list[str]] = defaultdict(list)
        for node in nodes:
            nid = node.get('id', '')
            cid = node.get('community')
            node_community[nid] = cid
            if cid is not None:
                community_nodes[cid].append(nid)
                if len(community_labels[cid]) < 3:
                    community_labels[cid].append(node.get('label', ''))

        # 计算 community 内部边数 + community 间桥接
        community_internal_edges: dict[int, int] = defaultdict(int)
        bridge_map: dict[int, set[int]] = defaultdict(set)

        for link in links:
            src_cid = node_community.get(link.get('source', ''))
            tgt_cid = node_community.get(link.get('target', ''))
            if src_cid is None or tgt_cid is None:
                continue
            if src_cid == tgt_cid:
                community_internal_edges[src_cid] += 1
            else:
                bridge_map[src_cid].add(tgt_cid)
                bridge_map[tgt_cid].add(src_cid)

        result = []
        for cid in sorted(community_nodes.keys()):
            nids = community_nodes[cid]
            node_count = len(nids)
            internal_edges = community_internal_edges.get(cid, 0)
            avg_degree = (
                sum(degree.get(nid, 0) for nid in nids) / node_count
                if node_count > 0 else 0
            )
            result.append({
                'community_id': cid,
                'node_count': node_count,
                'internal_edges': internal_edges,
                'avg_degree': round(avg_degree, 2),
                'bridge_communities': sorted(bridge_map.get(cid, set())),
                'label': '、'.join(community_labels.get(cid, [])),
            })

        return result

    @staticmethod
    def _find_missing_bridges(
        nodes: list, links: list, community_analysis: list[dict]
    ) -> list[dict]:
        """识别 community 对之间缺失的桥接"""
        # 已有桥接的 community 对
        node_community = {}
        for node in nodes:
            node_community[node.get('id', '')] = node.get('community')

        connected_pairs = set()
        for link in links:
            src_cid = node_community.get(link.get('source', ''))
            tgt_cid = node_community.get(link.get('target', ''))
            if src_cid is not None and tgt_cid is not None and src_cid != tgt_cid:
                pair = (min(src_cid, tgt_cid), max(src_cid, tgt_cid))
                connected_pairs.add(pair)

        # 标签映射
        label_map = {c['community_id']: c['label'] for c in community_analysis}

        # 所有 community 对
        all_cids = [c['community_id'] for c in community_analysis]
        missing = []
        for i, cid_a in enumerate(all_cids):
            for cid_b in all_cids[i + 1:]:
                pair = (min(cid_a, cid_b), max(cid_a, cid_b))
                if pair not in connected_pairs:
                    missing.append({
                        'community_a': pair[0],
                        'community_b': pair[1],
                        'community_a_label': label_map.get(pair[0], ''),
                        'community_b_label': label_map.get(pair[1], ''),
                        'suggestion': (
                            f'补充连接 {label_map.get(pair[0], f"社区{pair[0]}")}'
                            f'与 {label_map.get(pair[1], f"社区{pair[1]}")}'
                            f'的交叉领域文档'
                        ),
                    })

        return missing

    @staticmethod
    def _generate_suggestions(
        weak_nodes: list,
        isolated_nodes: list,
        community_analysis: list[dict],
        missing_bridges: list[dict],
    ) -> list[dict]:
        """基于分析结果生成补充建议"""
        suggestions = []

        # 孤立节点建议
        if isolated_nodes:
            labels = [n['label'] for n in isolated_nodes[:5]]
            suggestions.append({
                'type': 'isolated_node',
                'description': (
                    f'{len(isolated_nodes)} 个完全孤立节点'
                    f'（{"、".join(labels)}{"..." if len(isolated_nodes) > 5 else ""}），'
                    f'建议补充关联文档将其接入图谱'
                ),
                'priority': 'high',
                'related_communities': list({
                    n['community'] for n in isolated_nodes if n['community'] is not None
                }),
            })

        # 弱社区建议
        weak_community_ids = []
        for ca in community_analysis:
            if ca['node_count'] == 0:
                continue
            weak_ratio = sum(
                1 for n in weak_nodes if n['community'] == ca['community_id']
            ) / ca['node_count']
            if weak_ratio > 0.5:
                weak_community_ids.append(ca['community_id'])

        if weak_community_ids:
            labels = [
                ca['label'] for ca in community_analysis
                if ca['community_id'] in weak_community_ids
            ][:3]
            suggestions.append({
                'type': 'weak_community',
                'description': (
                    f'社区 {", ".join(str(c) for c in weak_community_ids[:5])}'
                    f' 超过半数节点度数偏低，'
                    f'建议补充{"、".join(labels)}领域的关联文档'
                ),
                'priority': 'high',
                'related_communities': weak_community_ids,
            })

        # 缺失桥接建议
        if missing_bridges:
            for bridge in missing_bridges[:5]:
                suggestions.append({
                    'type': 'missing_bridge',
                    'description': bridge['suggestion'],
                    'priority': 'medium',
                    'related_communities': [
                        bridge['community_a'], bridge['community_b']
                    ],
                })

        # 稀疏社区建议
        for ca in community_analysis:
            if ca['node_count'] < 2:
                continue
            if ca['internal_edges'] < ca['node_count'] * 0.5:
                suggestions.append({
                    'type': 'sparse_community',
                    'description': (
                        f'社区 {ca["community_id"]}（{ca["label"]}）'
                        f'内部连接稀疏（{ca["internal_edges"]} 边 / {ca["node_count"]} 节点），'
                        f'建议补充领域内关联文档'
                    ),
                    'priority': 'low',
                    'related_communities': [ca['community_id']],
                })

        return suggestions

    @staticmethod
    def _compute_coverage_score(
        total_nodes: int,
        weak_count: int,
        isolated_count: int,
        missing_bridge_count: int,
        total_possible_bridges: int,
    ) -> float:
        """计算覆盖分（0-100）

        coverage = 100 - (weak_ratio * 40 + isolated_ratio * 30 + bridge_gap_ratio * 30)
        """
        if total_nodes == 0:
            return 0.0

        weak_ratio = weak_count / total_nodes
        isolated_ratio = isolated_count / total_nodes
        bridge_gap_ratio = (
            missing_bridge_count / total_possible_bridges
            if total_possible_bridges > 0 else 0
        )

        w_weak, w_iso, w_bridge = COVERAGE_WEIGHTS
        score = 100 - (
            weak_ratio * w_weak
            + isolated_ratio * w_iso
            + bridge_gap_ratio * w_bridge
        )
        return max(0.0, min(100.0, score))
