<template>
  <div class="graph-explorer" ref="explorerRef">
    <!-- 状态判断 -->
    <div v-if="loading" class="explorer-loading">
      <el-skeleton :rows="5" animated />
    </div>

    <div v-else-if="!graphData || !graphData.nodes || graphData.nodes.length === 0" class="explorer-empty">
      <el-empty :description="t('knowledge.graph.empty')">
        <template #description>
          <p>{{ t('knowledge.graph.emptyHint') }}</p>
        </template>
        <el-button type="primary" @click="handleRefreshIndex">
          {{ t('knowledge.actions.refreshIndex') }}
        </el-button>
      </el-empty>
    </div>

    <div v-else class="explorer-main">
      <!-- 缺口分析面板（左侧） -->
      <transition name="slide-left">
        <KnowledgeGapPanel
          v-if="showGapPanel"
          :data="knowledgeStore.gapAnalysis"
          :loading="knowledgeStore.gapAnalysisLoading"
          @close="showGapPanel = false; clearGapHighlight()"
          @highlight-weak="onHighlightWeak"
          @highlight-bridge="onHighlightBridge"
        />
      </transition>

      <!-- 工具栏 -->
      <div class="explorer-toolbar">
        <CommunityFilter
          :communities="graphData.communities"
          :selected="selectedCommunities"
          @change="onCommunityChange"
        />
        <div class="toolbar-right">
          <el-tooltip :content="t('knowledge.graph.gapAnalysis')">
            <el-button
              :type="showGapPanel ? 'primary' : 'default'"
              :icon="Warning"
              @click="toggleGapPanel"
            />
          </el-tooltip>
          <el-switch
            v-model="showBridgeEdges"
            :active-text="t('knowledge.graph.bridgeEdges')"
            class="bridge-switch"
          />
          <el-tooltip :content="isFullscreen ? t('knowledge.actions.exitFullscreen') : t('knowledge.actions.fullscreen')">
            <el-button :icon="isFullscreen ? Aim : FullScreen" @click="toggleFullscreen" />
          </el-tooltip>
        </div>
      </div>

      <!-- 图谱画布 -->
      <div class="graph-canvas" ref="canvasRef">
        <svg ref="svgRef" />
      </div>

      <!-- 节点详情侧边栏 -->
      <transition name="slide">
        <NodeDetailPanel
          v-if="selectedNode"
          :node="selectedNode"
          :neighbors="selectedNodeNeighbors"
          :bridges="selectedNodeBridges"
          :doc-map="graphData.doc_map"
          @close="selectedNode = null"
          @select-node="onSelectNode"
          @preview-document="$emit('preview-document', $event)"
        />
      </transition>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useKnowledgeStore } from '@/stores/knowledge'
import { ElMessage } from 'element-plus'
import { FullScreen, Aim, Warning } from '@element-plus/icons-vue'
import * as d3 from 'd3'
import CommunityFilter from './CommunityFilter.vue'
import NodeDetailPanel from './NodeDetailPanel.vue'
import KnowledgeGapPanel from './KnowledgeGapPanel.vue'

const emit = defineEmits(['preview-document'])
const { t } = useI18n()

const knowledgeStore = useKnowledgeStore()

// === 状态 ===
const loading = ref(false)
const graphData = ref(null)
const selectedNode = ref(null)
const selectedCommunities = ref(new Set())
const showBridgeEdges = ref(false)
const isFullscreen = ref(false)
const showGapPanel = ref(false)
const gapHighlightMode = ref(null)  // null | {type:'weak', nodeId} | {type:'bridge', cA, cB}
const explorerRef = ref(null)
const canvasRef = ref(null)
const svgRef = ref(null)

// D3 实例
let simulation = null
let svg = null
let linkGroup = null
let nodeGroup = null
let labelGroup = null

// === 计算属性 ===

// 可见节点（community 筛选）
const visibleNodes = computed(() => {
  if (!graphData.value) return []
  if (selectedCommunities.value.size === 0) return graphData.value.nodes
  return graphData.value.nodes.filter(n => selectedCommunities.value.has(n.community))
})

// 可见边（两端节点均可见）
const visibleLinks = computed(() => {
  if (!graphData.value) return []
  const nodeIds = new Set(visibleNodes.value.map(n => n.id))
  return graphData.value.links.filter(l => {
    const src = typeof l.source === 'object' ? l.source.id : l.source
    const tgt = typeof l.target === 'object' ? l.target.id : l.target
    return nodeIds.has(src) && nodeIds.has(tgt)
  })
})

// 桥接边集合（连接不同 source_file 的边）
const bridgeEdgeKeys = computed(() => {
  if (!graphData.value) return new Set()
  const keys = new Set()
  const nodeMap = new Map(graphData.value.nodes.map(n => [n.id, n]))
  for (const link of graphData.value.links) {
    const srcId = typeof link.source === 'object' ? link.source.id : link.source
    const tgtId = typeof link.target === 'object' ? link.target.id : link.target
    const srcNode = nodeMap.get(srcId)
    const tgtNode = nodeMap.get(tgtId)
    if (srcNode && tgtNode && srcNode.source_file && tgtNode.source_file &&
        srcNode.source_file !== tgtNode.source_file) {
      keys.add(`${srcId}::${tgtId}`)
      keys.add(`${tgtId}::${srcId}`)
    }
  }
  return keys
})

// 选中节点的邻居
const selectedNodeNeighbors = computed(() => {
  if (!selectedNode.value || !graphData.value) return []
  const sid = selectedNode.value.id
  const neighborIds = new Set()
  for (const link of graphData.value.links) {
    const src = typeof link.source === 'object' ? link.source.id : link.source
    const tgt = typeof link.target === 'object' ? link.target.id : link.target
    if (src === sid) neighborIds.add(tgt)
    if (tgt === sid) neighborIds.add(src)
  }
  const nodeMap = new Map(graphData.value.nodes.map(n => [n.id, n]))
  return [...neighborIds].map(id => nodeMap.get(id)).filter(Boolean)
})

// 选中节点的桥接边
const selectedNodeBridges = computed(() => {
  if (!selectedNode.value || !graphData.value) return []
  const sid = selectedNode.value.id
  const bridges = []
  const nodeMap = new Map(graphData.value.nodes.map(n => [n.id, n]))
  for (const link of graphData.value.links) {
    const src = typeof link.source === 'object' ? link.source.id : link.source
    const tgt = typeof link.target === 'object' ? link.target.id : link.target
    if (src === sid || tgt === sid) {
      const otherId = src === sid ? tgt : src
      const otherNode = nodeMap.get(otherId)
      if (otherNode && selectedNode.value.source_file !== otherNode.source_file) {
        bridges.push({ node: otherNode, relation: link.relation })
      }
    }
  }
  return bridges
})

// === 方法 ===

function onCommunityChange(newSelected) {
  selectedCommunities.value = newSelected
}

function onSelectNode(node) {
  selectedNode.value = node
}

function toggleFullscreen() {
  if (!explorerRef.value) return
  if (!document.fullscreenElement) {
    explorerRef.value.requestFullscreen().catch(() => {
      ElMessage.warning(t('knowledge.graph.fullscreenUnsupported'))
    })
  } else {
    document.exitFullscreen()
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
}

async function handleRefreshIndex() {
  try {
    const result = await knowledgeStore.refreshIndex()
    if (result.success) {
      const total = result.result?.total || 0
      if (total > 0) {
        ElMessage.info(t('knowledge.messages.refreshProcessing', { total }))
        // 轮询等待后台处理完成
        const deadline = Date.now() + 120000
        while (Date.now() < deadline) {
          await new Promise(r => setTimeout(r, 3000))
          const s = await knowledgeStore.fetchStatus()
          if (s.success && s.status?.pending_docs === 0) break
        }
      }
      ElMessage.success(t('knowledge.messages.refreshDone'))
      await loadGraphData()
    } else {
      ElMessage.error(result.error || t('knowledge.messages.refreshFailed'))
    }
  } catch {
    ElMessage.error(t('knowledge.messages.refreshFailed'))
  }
}

// === 缺口分析 ===

async function toggleGapPanel() {
  showGapPanel.value = !showGapPanel.value
  if (showGapPanel.value && !knowledgeStore.gapAnalysis && !knowledgeStore.gapAnalysisLoading) {
    await knowledgeStore.fetchGapAnalysis()
  }
}

function onHighlightWeak(nodeId) {
  // 清除现有选中
  selectedNode.value = null
  gapHighlightMode.value = { type: 'weak', nodeId }
  updateGapHighlights()
}

function onHighlightBridge(cA, cB) {
  selectedNode.value = null
  gapHighlightMode.value = { type: 'bridge', cA, cB }
  updateGapHighlights()
}

function clearGapHighlight() {
  gapHighlightMode.value = null
  updateGapHighlights()
}

function updateGapHighlights() {
  if (!nodeGroup || !linkGroup || !labelGroup) return

  const mode = gapHighlightMode.value
  if (!mode) {
    // 重置所有节点样式
    nodeGroup.transition().duration(200)
      .attr('opacity', 1)
      .attr('r', 8)
      .attr('stroke', '#fff')
      .attr('stroke-width', 1.5)
    labelGroup.transition().duration(200).attr('opacity', 1)
    linkGroup.transition().duration(200)
      .attr('stroke', '#ddd')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 1)
    return
  }

  if (mode.type === 'weak') {
    // 高亮弱节点：红色 + 放大
    nodeGroup.transition().duration(200)
      .attr('opacity', d => d.id === mode.nodeId ? 1 : 0.15)
      .attr('r', d => d.id === mode.nodeId ? 14 : 8)
      .attr('stroke', d => d.id === mode.nodeId ? '#ef4444' : '#fff')
      .attr('stroke-width', d => d.id === mode.nodeId ? 3 : 1.5)
    labelGroup.transition().duration(200)
      .attr('opacity', d => d.id === mode.nodeId ? 1 : 0.1)
    linkGroup.transition().duration(200)
      .attr('stroke-opacity', 0.05)
  }

  if (mode.type === 'bridge') {
    // 高亮两个 community 的节点
    const targetCommunities = new Set([mode.cA, mode.cB])
    nodeGroup.transition().duration(200)
      .attr('opacity', d => targetCommunities.has(d.community) ? 1 : 0.1)
      .attr('r', d => targetCommunities.has(d.community) ? 10 : 6)
      .attr('stroke', d => targetCommunities.has(d.community) ? '#ef4444' : '#fff')
      .attr('stroke-width', d => targetCommunities.has(d.community) ? 2.5 : 1)
    labelGroup.transition().duration(200)
      .attr('opacity', d => targetCommunities.has(d.community) ? 1 : 0.05)
    linkGroup.transition().duration(200)
      .attr('stroke-opacity', 0.05)
  }
}

// === D3 渲染 ===

async function loadGraphData() {
  loading.value = true
  try {
    const result = await knowledgeStore.fetchGraphData()
    if (result.success && result.data) {
      graphData.value = result.data
      // 先关闭 loading 让模板渲染 SVG（v-else 分支）
      loading.value = false
      await nextTick()
      renderGraph()
      return
    }
    loading.value = false
  } catch {
    ElMessage.error(t('knowledge.graph.loadFailed'))
    loading.value = false
  }
}

function renderGraph() {
  if (!svgRef.value || !graphData.value) return

  const container = svgRef.value.parentElement
  const width = container.clientWidth || 800
  const height = container.clientHeight || 500

  // 清空
  d3.select(svgRef.value).selectAll('*').remove()

  svg = d3.select(svgRef.value)
    .attr('width', width)
    .attr('height', height)

  // 缩放层
  const g = svg.append('g')
  svg.call(d3.zoom()
    .scaleExtent([0.1, 4])
    .on('zoom', (event) => g.attr('transform', event.transform))
  )

  // 箭头定义（桥接边）
  svg.append('defs').append('marker')
    .attr('id', 'arrowhead')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 20)
    .attr('refY', 0)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', '#ef4444')

  // 深拷贝数据（D3 会修改原数据）
  const nodes = graphData.value.nodes.map(n => ({ ...n }))
  const links = graphData.value.links.map(l => ({ ...l }))

  // 力导向模拟
  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(80))
    .force('charge', d3.forceManyBody().strength(-120))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(16))
    .alphaDecay(0.05)
    .velocityDecay(0.4)

  // 预计算 120 tick 再渲染，避免逐帧 DOM 更新卡顿
  simulation.tick(120)
  simulation.alpha(0.08).restart()

  // 边
  linkGroup = g.append('g').attr('class', 'links')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('stroke', '#ddd')
    .attr('stroke-width', 1)
    .attr('stroke-opacity', 0.6)

  // 节点
  nodeGroup = g.append('g').attr('class', 'nodes')
    .selectAll('circle')
    .data(nodes)
    .join('circle')
    .attr('r', 8)
    .attr('fill', d => communityColor(d.community))
    .attr('stroke', '#fff')
    .attr('stroke-width', 1.5)
    .style('cursor', 'pointer')
    .on('click', (event, d) => {
      event.stopPropagation()
      gapHighlightMode.value = null  // 清除缺口高亮
      selectedNode.value = d
    })
    .call(d3.drag()
      .on('start', dragStarted)
      .on('drag', dragged)
      .on('end', dragEnded)
    )

  // 标签
  labelGroup = g.append('g').attr('class', 'labels')
    .selectAll('text')
    .data(nodes)
    .join('text')
    .text(d => truncateLabel(d.label))
    .attr('font-size', 10)
    .attr('dx', 12)
    .attr('dy', 4)
    .attr('fill', '#666')
    .style('pointer-events', 'none')

  // 点击空白取消选中
  svg.on('click', () => { selectedNode.value = null })

  // tick 更新位置
  simulation.on('tick', () => {
    linkGroup
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y)

    nodeGroup
      .attr('cx', d => d.x)
      .attr('cy', d => d.y)

    labelGroup
      .attr('x', d => d.x)
      .attr('y', d => d.y)
  })
}

// 颜色方案（18 communities）
const COLORS = [
  '#4f46e5', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#6366f1',
  '#06b6d4', '#84cc16', '#e11d48', '#a855f7', '#22d3ee',
  '#eab308', '#64748b', '#78716c'
]

function communityColor(communityId) {
  if (communityId == null) return '#94a3b8'
  return COLORS[communityId % COLORS.length]
}

function truncateLabel(label) {
  if (!label) return ''
  return label.length > 12 ? label.slice(0, 12) + '…' : label
}

// 拖拽
function dragStarted(event) {
  if (!event.active) simulation.alphaTarget(0.3).restart()
  event.subject.fx = event.subject.x
  event.subject.fy = event.subject.y
}

function dragged(event) {
  event.subject.fx = event.x
  event.subject.fy = event.y
}

function dragEnded(event) {
  if (!event.active) simulation.alphaTarget(0)
  event.subject.fx = null
  event.subject.fy = null
}

// === 高亮逻辑 ===

function updateHighlights() {
  if (!nodeGroup || !linkGroup || !labelGroup) return

  const sel = selectedNode.value
  const neighborIds = sel ? new Set(selectedNodeNeighbors.value.map(n => n.id)) : new Set()

  // 节点高亮
  nodeGroup
    .transition().duration(200)
    .attr('opacity', d => {
      if (!sel) return 1
      return (d.id === sel.id || neighborIds.has(d.id)) ? 1 : 0.15
    })
    .attr('r', d => (sel && d.id === sel.id) ? 12 : 8)

  // 标签高亮
  labelGroup
    .transition().duration(200)
    .attr('opacity', d => {
      if (!sel) return 1
      return (d.id === sel.id || neighborIds.has(d.id)) ? 1 : 0.1
    })

  // 边高亮
  linkGroup
    .transition().duration(200)
    .attr('stroke-opacity', d => {
      if (!sel) return 0.6
      const src = typeof d.source === 'object' ? d.source.id : d.source
      const tgt = typeof d.target === 'object' ? d.target.id : d.target
      return (src === sel.id || tgt === sel.id) ? 0.8 : 0.05
    })
    .attr('stroke-width', d => {
      if (!sel) return 1
      const src = typeof d.source === 'object' ? d.source.id : d.source
      const tgt = typeof d.target === 'object' ? d.target.id : d.target
      return (src === sel.id || tgt === sel.id) ? 2 : 1
    })
}

// 桥接边样式更新
function updateBridgeEdges() {
  if (!linkGroup) return

  linkGroup
    .transition().duration(300)
    .attr('stroke', d => {
      if (showBridgeEdges.value) {
        const src = typeof d.source === 'object' ? d.source.id : d.source
        const tgt = typeof d.target === 'object' ? d.target.id : d.target
        if (bridgeEdgeKeys.value.has(`${src}::${tgt}`)) return '#ef4444'
      }
      return '#ddd'
    })
    .attr('stroke-dasharray', d => {
      if (showBridgeEdges.value) {
        const src = typeof d.source === 'object' ? d.source.id : d.source
        const tgt = typeof d.target === 'object' ? d.target.id : d.target
        if (bridgeEdgeKeys.value.has(`${src}::${tgt}`)) return '6,3'
      }
      return 'none'
    })
    .attr('stroke-width', d => {
      if (showBridgeEdges.value) {
        const src = typeof d.source === 'object' ? d.source.id : d.source
        const tgt = typeof d.target === 'object' ? d.target.id : d.target
        if (bridgeEdgeKeys.value.has(`${src}::${tgt}`)) return 2.5
      }
      return 1
    })
}

// Community 筛选后重渲染可见性
function updateVisibility() {
  if (!nodeGroup || !linkGroup || !labelGroup) return

  const nodeIds = new Set(visibleNodes.value.map(n => n.id))

  nodeGroup.transition().duration(300)
    .attr('opacity', d => nodeIds.has(d.id) ? 1 : 0.05)

  labelGroup.transition().duration(300)
    .attr('opacity', d => nodeIds.has(d.id) ? 1 : 0.05)

  linkGroup.transition().duration(300)
    .attr('stroke-opacity', d => {
      const src = typeof d.source === 'object' ? d.source.id : d.source
      const tgt = typeof d.target === 'object' ? d.target.id : d.target
      return (nodeIds.has(src) && nodeIds.has(tgt)) ? 0.6 : 0.02
    })
}

// === Watch ===

watch(selectedNode, () => {
  updateHighlights()
  if (selectedNode.value) {
    gapHighlightMode.value = null
    updateGapHighlights()
  }
})
watch(showBridgeEdges, updateBridgeEdges)
watch(gapHighlightMode, updateGapHighlights)
watch(selectedCommunities, updateVisibility, { deep: true })

// === 生命周期 ===

onMounted(() => {
  loadGraphData()
  document.addEventListener('fullscreenchange', onFullscreenChange)
})

onUnmounted(() => {
  if (simulation) simulation.stop()
  document.removeEventListener('fullscreenchange', onFullscreenChange)
})
</script>

<style scoped lang="scss">
.graph-explorer {
  min-height: 400px;
}

.explorer-loading {
  padding: var(--spacing-xl);
}

.explorer-empty {
  padding: var(--spacing-xl) 0;

  p {
    color: var(--color-text-secondary, #909399);
    font-size: var(--font-size-sm, 14px);
    margin: var(--spacing-sm, 8px) 0;
  }
}

.explorer-main {
  display: flex;
  flex-direction: column;
  height: 600px;
  border-radius: var(--radius-md, 8px);
  overflow: hidden;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, #e4e7ed);
}

.explorer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm, 8px) var(--spacing-md, 16px);
  border-bottom: 1px solid var(--color-border, #e4e7ed);
  background: var(--color-bg-page, #f5f7fa);
  flex-wrap: wrap;
  gap: var(--spacing-sm, 8px);
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
}

.bridge-switch {
  --el-switch-on-color: #ef4444;
}

.graph-canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
  background: #fafbfc;
}

.graph-canvas svg {
  display: block;
  width: 100%;
  height: 100%;
}

/* 侧边栏滑入动画 */
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}

/* 左侧缺口面板滑入动画 */
.slide-left-enter-active,
.slide-left-leave-active {
  transition: transform 0.3s ease;
}

.slide-left-enter-from,
.slide-left-leave-to {
  transform: translateX(-100%);
}

/* 全屏样式 */
.graph-explorer:fullscreen {
  background: var(--color-bg-page, #f5f7fa);
  padding: var(--spacing-md, 16px);
}

.graph-explorer:fullscreen .explorer-main {
  height: calc(100vh - 32px);
}

@media (max-width: 768px) {
  .explorer-main {
    height: 400px;
  }

  .explorer-toolbar {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
