"""知识图谱提取服务

封装 graphify extract CLI 调用，支持：
- 从 OCR 输出的 Markdown 目录生成 graph.json
- 使用后台数据库配置的默认 LLM
- 与 knowledge_api 状态联动（OCR indexed → graphify indexed）
"""

import logging
import json
import os
import subprocess
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _normalize_node_sources(node: dict) -> list[str]:
    """读取旧/新 provenance 形状并回写结构化来源列表。"""
    raw = node.get('source_files') or node.get('source_file')
    values = raw if isinstance(raw, (list, tuple, set)) else [raw]
    sources = []
    for value in values:
        if not isinstance(value, str):
            continue
        for source in value.split(','):
            source = source.strip()
            if source and source not in sources:
                sources.append(source)
    if sources:
        node['source_files'] = sources
        node['source_file'] = sources[0]
    return sources


class GraphifyExtractor:
    """知识图谱提取服务"""

    # 配置常量
    TIMEOUT = 600  # API 超时秒数
    MAX_CONCURRENCY = 4  # 并发语义块数

    def __init__(self, db_session=None):
        """
        LLM 配置由后台 ``llm_models`` 表的默认模型提供。

        Args:
            db_session: SQLAlchemy session（用于状态联动）
        """
        self.db_session = db_session

    # === 核心方法 ===

    def extract_directory(self, markdown_dir: str, output_dir: str) -> dict:
        """
        提取目录下所有 Markdown 文件生成图谱

        Args:
            markdown_dir: Markdown 输入目录（OCR 输出）
            output_dir: graphify 输出目录

        Returns:
            {
                'success': bool,
                'nodes': int,
                'edges': int,
                'communities': int,
                'graph_path': str,      # graph.json 路径
                'report_path': str,     # GRAPH_REPORT.md 路径
                'html_path': str,       # graph.html 路径
                'tokens': dict,         # {input: N, output: N}
                'error': str | None
            }
        """
        # 验证目录存在
        if not os.path.isdir(markdown_dir):
            return {
                'success': False,
                'nodes': 0,
                'edges': 0,
                'communities': 0,
                'graph_path': None,
                'report_path': None,
                'html_path': None,
                'tokens': {'input': 0, 'output': 0},
                'error': 'Directory not found'
            }

        # 检查 Markdown 文件
        md_files = list(Path(markdown_dir).rglob('*.md'))
        if not md_files:
            return {
                'success': False,
                'nodes': 0,
                'edges': 0,
                'communities': 0,
                'graph_path': None,
                'report_path': None,
                'html_path': None,
                'tokens': {'input': 0, 'output': 0},
                'error': 'No Markdown files found'
            }

        try:
            # 执行 graphify CLI
            result = self._run_graphify_cli(markdown_dir, output_dir)

            if result['success']:
                # 翻译节点标签为中文
                graph_json_path = str(Path(output_dir) / 'graphify-out' / 'graph.json')
                if os.path.exists(graph_json_path):
                    self._translate_graph_labels(graph_json_path)

                # 解析输出统计
                stats = self._parse_graph_stats(output_dir)
                result.update(stats)

            return result

        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'nodes': 0,
                'edges': 0,
                'communities': 0,
                'graph_path': None,
                'report_path': None,
                'html_path': None,
                'tokens': {'input': 0, 'output': 0},
                'error': 'graphify CLI timeout'
            }
        except Exception as e:
            logger.exception(f'Graphify extraction failed: {markdown_dir}')
            return {
                'success': False,
                'nodes': 0,
                'edges': 0,
                'communities': 0,
                'graph_path': None,
                'report_path': None,
                'html_path': None,
                'tokens': {'input': 0, 'output': 0},
                'error': str(e)
            }

    def extract_document(self, doc_id: int) -> dict:
        """
        提取单个 KnowledgeDocument（状态联动）

        流程：
        1. 读取 KnowledgeDocument，获取 markdown_path
        2. 验证 OCR 已完成（status='indexed' from OCR）
        3. 调用 extract_directory
        4. 更新 graphify_processed_at + graph_nodes/graph_edges

        Args:
            doc_id: KnowledgeDocument ID

        Returns:
            {'success': bool, 'graph_path': str | None, 'error': str | None}
        """
        if not self.db_session:
            return {
                'success': False,
                'graph_path': None,
                'error': 'DB session not provided'
            }

        from models import KnowledgeDocument

        # 读取文档记录
        doc = self.db_session.get(KnowledgeDocument, doc_id)
        if not doc:
            return {
                'success': False,
                'graph_path': None,
                'error': 'Document not found'
            }

        # 验证 OCR 已完成（OCR 阶段会将 status 设为 'indexed'）
        if doc.status != 'indexed':
            return {
                'success': False,
                'graph_path': None,
                'error': 'OCR not completed'
            }

        # 验证 Markdown 目录存在
        if not doc.markdown_path or not os.path.isdir(doc.markdown_path):
            doc.graphify_error = 'Markdown directory not found'
            doc.graphify_processed_at = datetime.now(timezone.utc)
            self.db_session.commit()
            return {
                'success': False,
                'graph_path': None,
                'error': 'Markdown directory not found'
            }

        # 计算输出目录 — graphify 会自动创建 graphify-out/ 子目录
        doc_dir = Path(doc.original_path).parent.parent  # documents/{doc_id}/

        try:
            # 执行提取（传入 doc_dir，graphify 自动在其下创建 graphify-out/）
            result = self.extract_directory(doc.markdown_path, str(doc_dir))

            if result['success']:
                # 更新成功状态
                doc.graphify_error = None
                doc.graphify_processed_at = datetime.now(timezone.utc)
                doc.graph_nodes = result.get('nodes', 0)
                doc.graph_edges = result.get('edges', 0)
                self.db_session.commit()

                # 增量合并用户图谱（单文档提取用增量，避免全量重扫）
                self._merge_user_graph_incremental(doc.uploaded_by, doc_id, result)

                # embedding 同步（graph.json 更新后）
                try:
                    from services.embedding_service import get_embedding_service
                    get_embedding_service().sync_user_embeddings(doc.uploaded_by)
                except Exception:
                    logger.exception('Embedding sync failed after extract, graph still usable')

                return {
                    'success': True,
                    'graph_path': result.get('graph_path'),
                    'nodes': result.get('nodes'),
                    'edges': result.get('edges'),
                    'error': None
                }
            else:
                # 更新失败状态（保持 OCR indexed，记录错误）
                doc.graphify_error = result.get('error')
                doc.graphify_processed_at = datetime.now(timezone.utc)
                self.db_session.commit()

                return {
                    'success': False,
                    'graph_path': None,
                    'error': result.get('error')
                }

        except Exception as e:
            logger.exception(f'Graphify extraction failed for document {doc_id}')
            doc.graphify_error = str(e)
            doc.graphify_processed_at = datetime.now(timezone.utc)
            self.db_session.commit()

            return {
                'success': False,
                'graph_path': None,
                'error': str(e)
            }

    # === 内部方法 ===

    def _run_graphify_cli(self, input_dir: str, output_dir: str) -> dict:
        """
        执行 graphify extract CLI

        命令格式：
        graphify extract <input_dir> --backend ollama --out <output_dir>

        LLM 配置只从后台数据库的默认模型读取。

        Returns:
            {
                'success': bool,
                'output': str,     # CLI 输出
                'error': str | None
            }
        """
        from services.llm_service import LLMConfigurationError, resolve_model_info

        try:
            model_info = resolve_model_info(db_session=self.db_session)
        except LLMConfigurationError as exc:
            return {
                'success': False,
                'output': '',
                'error': str(exc),
            }
        base_url = model_info['base_url']
        api_key = model_info['api_key']
        model = model_info['model_id']

        # 构建命令 — 使用 ollama 后端（唯一支持 OLLAMA_BASE_URL 环境变量覆盖的后端）
        # graphify 的 openai 后端 base_url 硬编码为 api.openai.com，无法自定义
        cmd = [
            'graphify', 'extract', input_dir,
            '--backend', 'ollama',
            '--out', output_dir,
            '--max-concurrency', str(self.MAX_CONCURRENCY),
            '--api-timeout', str(self.TIMEOUT),
        ]

        # 设置环境变量（ollama 后端读取 OLLAMA_BASE_URL + OLLAMA_API_KEY）
        env = os.environ.copy()
        env['OLLAMA_BASE_URL'] = base_url
        if api_key:
            env['OLLAMA_API_KEY'] = api_key
        env['OLLAMA_MODEL'] = model

        logger.info(f'Running graphify extract: {input_dir} -> {output_dir}')
        logger.debug(f'OLLAMA_BASE_URL={base_url}, OLLAMA_MODEL={model}')

        # 执行命令
        try:
            proc = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT + 60,  # 比内部超时多 60s
            )

            if proc.returncode == 0:
                # extract 成功后运行 cluster-only 生成 graph.html + GRAPH_REPORT.md
                cluster_cmd = ['graphify', 'cluster-only', output_dir]
                cluster_env = env.copy()
                try:
                    cluster_proc = subprocess.run(
                        cluster_cmd,
                        env=cluster_env,
                        capture_output=True,
                        text=True,
                        timeout=self.TIMEOUT + 60,
                    )
                    if cluster_proc.returncode != 0:
                        logger.warning(f'graphify cluster-only failed: {cluster_proc.stderr[:200]}')
                except Exception as e:
                    logger.warning(f'graphify cluster-only error: {e}')

                return {
                    'success': True,
                    'output': proc.stdout,
                    'error': None
                }
            else:
                error_msg = proc.stderr or proc.stdout or 'Unknown error'
                logger.error(f'graphify CLI failed: {error_msg}')
                return {
                    'success': False,
                    'output': proc.stdout,
                    'error': error_msg.strip()
                }

        except subprocess.TimeoutExpired:
            logger.error(f'graphify CLI timeout for {input_dir}')
            raise
        except FileNotFoundError:
            return {
                'success': False,
                'output': '',
                'error': 'graphify CLI not found. Install with: pip install graphifyy'
            }

    def _parse_graph_stats(self, output_dir: str) -> dict:
        """
        解析 graphify 输出目录获取图谱统计

        Returns:
            {
                'graph_path': str,
                'report_path': str,
                'html_path': str,
                'nodes': int,
                'edges': int,
                'communities': int,
                'tokens': dict
            }
        """
        # graphify 自动创建 graphify-out/ 子目录
        output_path = Path(output_dir) / 'graphify-out'
        graph_json = output_path / 'graph.json'
        report_md = output_path / 'GRAPH_REPORT.md'
        graph_html = output_path / 'graph.html'

        stats = {
            'graph_path': str(graph_json) if graph_json.exists() else None,
            'report_path': str(report_md) if report_md.exists() else None,
            'html_path': str(graph_html) if graph_html.exists() else None,
            'nodes': 0,
            'edges': 0,
            'communities': 0,
            'tokens': {'input': 0, 'output': 0}
        }

        # 解析 graph.json
        if graph_json.exists():
            try:
                import json
                data = json.loads(graph_json.read_text(encoding='utf-8'))
                stats['nodes'] = len(data.get('nodes', []))
                # graph.json 使用 'links' 或 'edges'
                edges = data.get('links', data.get('edges', []))
                stats['edges'] = len(edges)
                # communities 存储在节点属性中
                communities = set()
                for node in data.get('nodes', []):
                    cid = node.get('community')
                    if cid is not None:
                        communities.add(cid)
                stats['communities'] = len(communities)
            except Exception as e:
                logger.warning(f'Failed to parse graph.json: {e}')

        # 从 GRAPH_REPORT.md 解析 token 统计
        if report_md.exists():
            try:
                content = report_md.read_text(encoding='utf-8')
                # 匹配 Token 统计行
                match = re.search(r'Token[^:]*:\s*(\d+)\s*in\s*/\s*(\d+)\s*out', content)
                if match:
                    stats['tokens'] = {
                        'input': int(match.group(1)),
                        'output': int(match.group(2))
                    }
            except Exception as e:
                logger.warning(f'Failed to parse GRAPH_REPORT.md: {e}')

        return stats

    def _translate_graph_labels(self, graph_json_path: str) -> None:
        """将图谱节点 label 从英文翻译为中文（原地修改 graph.json）

        使用 LLM 批量翻译所有 node label，单次请求完成。
        翻译失败时静默跳过，不影响图谱可用性。
        """
        import json

        try:
            data = json.loads(Path(graph_json_path).read_text(encoding='utf-8'))
        except Exception:
            return

        nodes = data.get('nodes', [])
        if not nodes:
            return

        # 收集需要翻译的 label（跳过已是中文的）
        labels_to_translate = {}
        for node in nodes:
            label = node.get('label', '')
            if label and not any('一' <= ch <= '鿿' for ch in label):
                labels_to_translate[node['id']] = label

        if not labels_to_translate:
            return

        # 构建翻译请求
        id_label_pairs = [
            {"id": nid, "label": lbl}
            for nid, lbl in labels_to_translate.items()
        ]

        prompt = (
            "将以下知识图谱节点标签翻译为简洁的中文。"
            "仅返回 JSON 数组，格式: [{\"id\": \"原id\", \"label\": \"中文标签\"}]。"
            "不要添加任何解释。\n\n"
            + json.dumps(id_label_pairs, ensure_ascii=False)
        )

        try:
            from services.llm_service import create_llm_service
            from db import get_db_session

            # 从 DB 获取默认模型配置
            trans_db = get_db_session()
            try:
                llm = create_llm_service(db_session=trans_db)
            finally:
                trans_db.close()

            response_text = llm.call_sync(
                message=prompt,
                system_prompt="你是翻译助手。仅返回 JSON 数组，不要添加任何解释或 markdown 格式。",
                max_tokens=4096,
            )
            # 解析翻译结果
            # 提取 JSON 数组（兼容 markdown 代码块）
            import re
            json_match = re.search(r'\[.*\]', response_text, re.S)
            if not json_match:
                logger.warning('Translation response not valid JSON array, skipping')
                return

            translations = json.loads(json_group) if (json_group := json_match.group()) else []
            trans_map = {item['id']: item['label'] for item in translations if 'id' in item and 'label' in item}

            # 回写翻译结果
            translated_count = 0
            for node in nodes:
                nid = node.get('id', '')
                if nid in trans_map:
                    node['label'] = trans_map[nid]
                    translated_count += 1

            if translated_count > 0:
                Path(graph_json_path).write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
                logger.info(f'Translated {translated_count}/{len(labels_to_translate)} node labels to Chinese')

        except Exception:
            logger.exception('Graph label translation failed, keeping original labels')

    def _merge_user_graph_incremental(self, user_id: int, doc_id: int, extract_result: dict):
        """增量合并单文档图谱到用户级图谱

        读现有 user_{id}_graph.json（仅一次），将新文档的节点和链接合并后写回。
        采用临时文件 + os.replace 原子替换，保证并发安全。

        合并规则：
        - 节点：按 id 去重，已存在则合并属性（label 保留原节点，数值字段取 max，
          source_files 以数组追加新文档路径，其余字段以新值覆盖）。
        - 链接：按 (source, target) 去重追加，同 source+target 只保留一条。
        """
        try:
            from config import Config

            user_json_path = Path(Config.get_user_graph_path(user_id))
            user_json_path.parent.mkdir(parents=True, exist_ok=True)

            # 读现有图谱
            existing: dict = {'nodes': [], 'links': [], 'directed': True}
            if user_json_path.exists():
                try:
                    existing = json.loads(user_json_path.read_text(encoding='utf-8'))
                except (json.JSONDecodeError, OSError):
                    logger.warning(f'User graph corrupt, will overwrite: {user_json_path}')

            # 构建现有节点索引
            existing_nodes: dict[str, dict] = {}
            for existing_node in existing.get('nodes', []):
                if existing_node.get('id'):
                    _normalize_node_sources(existing_node)
                    existing_nodes[existing_node['id']] = existing_node
            existing_links_set: set[tuple[str, str]] = set()
            for lnk in existing.get('links', []):
                src, tgt = lnk.get('source'), lnk.get('target')
                if src and tgt:
                    existing_links_set.add((src, tgt))

            # 读新文档图谱
            doc_graph_path = extract_result.get('graph_path')
            if not doc_graph_path or not os.path.exists(doc_graph_path):
                return

            doc_data = json.loads(Path(doc_graph_path).read_text(encoding='utf-8'))

            # 合并节点
            merged_count = 0
            for node in doc_data.get('nodes', []):
                nid = node.get('id')
                if not nid:
                    continue
                new_sources = _normalize_node_sources(node)
                if nid in existing_nodes:
                    old = existing_nodes[nid]
                    # 合并策略：label/社区保留原节点，数值取 max，source_files 追加
                    old['_weight'] = max(old.get('_weight', 0), node.get('_weight', 0))
                    old['_degree'] = max(old.get('_degree', 0), node.get('_degree', 0))
                    merged_sources = _normalize_node_sources(old)
                    for source in new_sources:
                        if source not in merged_sources:
                            merged_sources.append(source)
                    if merged_sources:
                        old['source_files'] = merged_sources
                        old['source_file'] = merged_sources[0]
                    # community 取新值（新提取更准确）
                    if node.get('community') is not None:
                        old['community'] = node['community']
                else:
                    existing_nodes[nid] = node
                    merged_count += 1

            # 合并链接
            for lnk in doc_data.get('links', doc_data.get('edges', [])):
                src, tgt = lnk.get('source'), lnk.get('target')
                if src and tgt and (src, tgt) not in existing_links_set:
                    existing_links_set.add((src, tgt))
                    existing['links'].append(lnk)

            # 更新节点列表
            existing['nodes'] = list(existing_nodes.values())
            existing['directed'] = True

            # 原子写入
            fd, tmp_path = tempfile.mkstemp(
                suffix='.json', dir=str(user_json_path.parent)
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, str(user_json_path))
            except BaseException:
                # 写入失败则清理临时文件
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            logger.info(
                f'User graph incremental merge: user_id={user_id}, doc_id={doc_id}, '
                f'new_nodes={merged_count}, total={len(existing["nodes"])} nodes, '
                f'{len(existing["links"])} links -> {user_json_path}'
            )

        except Exception:
            logger.exception(f'Failed to incremental merge user graph: user_id={user_id}, doc_id={doc_id}')

    def _merge_user_graph(self, user_id: int):
        """合并指定用户的所有文档图谱为用户级图谱

        扫描该用户所有 indexed 文档的 graphify-out/graph.json，
        按 node.id 去重合并节点，边直接追加，
        输出到 data/knowledge/user_{user_id}_graph.json。
        """
        try:
            import json
            from config import Config
            from models import KnowledgeDocument

            user_json_path = Path(Config.get_user_graph_path(user_id))
            user_json_path.parent.mkdir(parents=True, exist_ok=True)

            # 查询该用户所有 indexed 文档
            docs = self.db_session.query(KnowledgeDocument).filter(
                KnowledgeDocument.uploaded_by == user_id,
                KnowledgeDocument.status == 'indexed',
            ).all()

            all_nodes_by_id = {}
            all_links = []

            for doc in docs:
                if not doc.original_path:
                    continue
                doc_dir = Path(doc.original_path).parent.parent  # documents/{doc_id}/
                graph_json = doc_dir / 'graphify-out' / 'graph.json'
                if not graph_json.exists():
                    continue
                try:
                    data = json.loads(graph_json.read_text(encoding='utf-8'))
                    for node in data.get('nodes', []):
                        nid = node.get('id')
                        if not nid:
                            continue
                        new_sources = _normalize_node_sources(node)
                        if nid not in all_nodes_by_id:
                            all_nodes_by_id[nid] = node
                            continue
                        existing_node = all_nodes_by_id[nid]
                        merged_sources = _normalize_node_sources(existing_node)
                        for source in new_sources:
                            if source not in merged_sources:
                                merged_sources.append(source)
                        if merged_sources:
                            existing_node['source_files'] = merged_sources
                            existing_node['source_file'] = merged_sources[0]
                    for link in data.get('links', data.get('edges', [])):
                        all_links.append(link)
                except Exception as e:
                    logger.warning(f'Failed to read {graph_json}: {e}')

            merged = {
                'nodes': list(all_nodes_by_id.values()),
                'links': all_links,
                'directed': True
            }
            user_json_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')

            # 翻译节点标签为中文
            self._translate_graph_labels(str(user_json_path))

            logger.info(f'User graph merged: user_id={user_id}, {len(all_nodes_by_id)} nodes, {len(all_links)} links -> {user_json_path}')

        except Exception:
            logger.exception(f'Failed to merge user graph: user_id={user_id}')

    def rebuild_user_graph(self, user_id: int):
        """删除文档后重建用户图谱（公开方法）

        删除旧图谱 JSON 文件后重新合并该用户剩余文档的图谱。
        """
        try:
            from config import Config
            # 删除旧 JSON 文件
            p = Path(Config.get_user_graph_path(user_id))
            if p.exists():
                p.unlink()
            # 重建
            self._merge_user_graph(user_id)

            # embedding 同步（图谱重建后）
            try:
                from services.embedding_service import get_embedding_service
                get_embedding_service().sync_user_embeddings(user_id)
            except Exception:
                logger.exception('Embedding sync failed after rebuild, graph still usable')

            logger.info(f'User graph rebuilt: user_id={user_id}')
        except Exception:
            logger.exception(f'Failed to rebuild user graph: user_id={user_id}')
