<template>
  <div class="node-detail-panel">
    <div class="panel-header">
      <h3 class="panel-title">{{ node.label }}</h3>
      <el-button :icon="Close" text @click="$emit('close')" />
    </div>

    <el-scrollbar class="panel-body">
      <!-- 基本信息 -->
      <div class="detail-section">
        <div class="detail-row">
          <span class="detail-label">{{ t('knowledge.graph.community', { id: '' }).trim() }}</span>
          <span class="detail-value">
            <span class="community-dot" :style="{ background: communityColor(node.community) }" />
            {{ node.community }}
          </span>
        </div>
        <div class="detail-row" v-if="node.source_file">
          <span class="detail-label">{{ t('knowledge.graph.sourceDocument') }}</span>
          <span class="detail-value source-file">
            <el-link
              v-if="docInfo"
              type="primary"
              @click="$emit('preview-document', docInfo.doc_id)"
            >
              {{ docInfo.filename }}
            </el-link>
            <span v-else class="no-doc">{{ t('knowledge.graph.documentNotIndexed') }}</span>
          </span>
        </div>
        <div class="detail-row" v-if="node.file_type">
          <span class="detail-label">{{ t('knowledge.graph.fileType') }}</span>
          <span class="detail-value">{{ node.file_type }}</span>
        </div>
      </div>

      <!-- 邻居节点 -->
      <div class="detail-section" v-if="neighbors.length > 0">
        <h4 class="section-title">{{ t('knowledge.graph.neighbors', { count: neighbors.length }) }}</h4>
        <div class="neighbor-list">
          <div
            v-for="n in neighbors.slice(0, 20)"
            :key="n.id"
            class="neighbor-item"
            @click="$emit('select-node', n)"
          >
            <span class="neighbor-dot" :style="{ background: communityColor(n.community) }" />
            <span class="neighbor-label">{{ n.label }}</span>
          </div>
          <div v-if="neighbors.length > 20" class="more-hint">
            {{ t('knowledge.graph.moreNodes', { count: neighbors.length - 20 }) }}
          </div>
        </div>
      </div>

      <!-- 桥接边 -->
      <div class="detail-section" v-if="bridges.length > 0">
        <h4 class="section-title">
          {{ t('knowledge.graph.bridgeSection') }}
          <el-tag size="small" type="danger">{{ bridges.length }}</el-tag>
        </h4>
        <div class="bridge-list">
          <div
            v-for="b in bridges"
            :key="b.node.id"
            class="bridge-item"
            @click="$emit('select-node', b.node)"
          >
            <el-icon color="#ef4444"><Connection /></el-icon>
            <span class="bridge-label">{{ b.node.label }}</span>
            <span class="bridge-relation">{{ b.relation }}</span>
          </div>
        </div>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Close, Connection } from '@element-plus/icons-vue'

const COLORS = [
  '#4f46e5', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#6366f1',
  '#06b6d4', '#84cc16', '#e11d48', '#a855f7', '#22d3ee',
  '#eab308', '#64748b', '#78716c'
]

const props = defineProps({
  node: { type: Object, required: true },
  neighbors: { type: Array, default: () => [] },
  bridges: { type: Array, default: () => [] },
  docMap: { type: Object, default: () => ({}) }
})

defineEmits(['close', 'select-node', 'preview-document'])
const { t } = useI18n()

function communityColor(id) {
  if (id == null) return '#94a3b8'
  return COLORS[id % COLORS.length]
}

const docInfo = computed(() => {
  if (!props.node.source_file) return null
  const prefix = props.node.source_file.split('/')[0]
  return props.docMap[prefix] || null
})
</script>

<style scoped>
.node-detail-panel {
  position: absolute;
  top: 0;
  right: 0;
  width: 300px;
  height: 100%;
  background: var(--color-bg-card, #fff);
  border-left: 1px solid var(--color-border, #e4e7ed);
  box-shadow: -4px 0 12px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  z-index: 20;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--color-border, #e4e7ed);
}

.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 8px;
}

.panel-body {
  flex: 1;
  padding: 16px;
}

.detail-section {
  margin-bottom: 20px;
}

.detail-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #f5f5f5;
}

.detail-label {
  font-size: 13px;
  color: var(--color-text-secondary, #909399);
  flex-shrink: 0;
}

.detail-value {
  font-size: 13px;
  color: var(--color-text, #303133);
  display: flex;
  align-items: center;
  gap: 6px;
  text-align: right;
}

.community-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.no-doc {
  color: var(--color-text-placeholder, #c0c4cc);
  font-style: italic;
  font-size: 12px;
}

.section-title {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text, #303133);
  display: flex;
  align-items: center;
  gap: 6px;
}

.neighbor-list,
.bridge-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.neighbor-item,
.bridge-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}

.neighbor-item:hover,
.bridge-item:hover {
  background: #f5f7fa;
}

.neighbor-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.neighbor-label {
  font-size: 13px;
  color: var(--color-text, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bridge-label {
  flex: 1;
  font-size: 13px;
  color: var(--color-text, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bridge-relation {
  font-size: 11px;
  color: var(--color-text-secondary, #909399);
  flex-shrink: 0;
}

.more-hint {
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
  padding: 4px 8px;
  text-align: center;
}

@media (max-width: 768px) {
  .node-detail-panel {
    width: 100%;
    height: 50%;
    top: auto;
    bottom: 0;
    border-left: none;
    border-top: 1px solid var(--color-border, #e4e7ed);
  }
}
</style>
