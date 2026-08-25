<template>
  <div class="doc-list">
    <!-- 分类 Tab（动态渲染） -->
    <div class="tabs">
      <button
        :class="['tab', { active: currentCategory === null }]"
        @click="$emit('category-change', null)"
      >
        {{ t('knowledge.documents.all') }}
      </button>
      <button
        v-for="cat in categories"
        :key="cat.key"
        :class="['tab', { active: currentCategory === cat.key }]"
        @click="$emit('category-change', cat.key)"
      >
        {{ cat.label }}
        <span v-if="cat.count > 0" class="tab-count">{{ cat.count }}</span>
      </button>
    </div>

    <!-- 搜索框 -->
    <div class="search-wrapper">
      <el-input
        v-model="localSearchQuery"
        :placeholder="t('knowledge.documents.searchPlaceholder')"
        clearable
        @input="$emit('search-change', localSearchQuery)"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <!-- 文档列表 -->
    <el-table
      :data="documents"
      v-loading="loading"
      :empty-text="t('knowledge.documents.empty')"
      class="doc-table"
    >
      <el-table-column :label="t('knowledge.documents.filename')" min-width="200">
        <template #default="{ row }">
          <div class="filename-cell">
            <el-icon class="file-icon"><Document /></el-icon>
            <span>{{ row.original_filename || row.filename }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column :label="t('knowledge.documents.category')" prop="category" width="100">
        <template #default="{ row }">
          <el-tag :type="getCategoryTagType(row.category)" size="small">
            {{ getCategoryLabel(row.category) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('knowledge.documents.size')" prop="file_size" width="100">
        <template #default="{ row }">
          {{ formatFileSize(row.file_size) }}
        </template>
      </el-table-column>

      <el-table-column :label="t('knowledge.documents.status')" prop="status" width="100">
        <template #default="{ row }">
          <el-tag :type="getStatusTagType(row.status)" size="small">
            {{ getStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('knowledge.documents.uploadedAt')" prop="uploaded_at" width="150">
        <template #default="{ row }">
          {{ formatDate(row.uploaded_at) }}
        </template>
      </el-table-column>

      <el-table-column :label="t('knowledge.documents.operations')" width="200" fixed="right">
        <template #default="{ row }">
          <el-button
            type="primary"
            size="small"
            text
            @click="$emit('preview', row)"
          >
            <el-icon><View /></el-icon>
            {{ t('knowledge.actions.preview') }}
          </el-button>
          <el-button
            type="primary"
            size="small"
            text
            @click="$emit('download', row)"
          >
            <el-icon><Download /></el-icon>
            {{ t('knowledge.actions.download') }}
          </el-button>
          <el-button
            type="danger"
            size="small"
            text
            @click="$emit('delete', row)"
          >
            <el-icon><Delete /></el-icon>
            {{ t('knowledge.actions.delete') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 无匹配结果提示 -->
    <div v-if="!loading && documents.length === 0 && searchQuery" class="no-match">
      <el-icon :size="24" color="#909399"><Search /></el-icon>
      <p>{{ t('knowledge.documents.noMatch') }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search, Document, Download, Delete, View } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

const { t } = useI18n()

const props = defineProps({
  documents: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  },
  currentCategory: {
    type: String,
    default: null
  },
  searchQuery: {
    type: String,
    default: ''
  },
  categories: {
    type: Array,
    default: () => []
  }
})

defineEmits(['category-change', 'search-change', 'preview', 'download', 'delete'])

// 本地搜索状态
const localSearchQuery = ref(props.searchQuery)

// 监听外部 searchQuery 变化
watch(() => props.searchQuery, (val) => {
  localSearchQuery.value = val
})

// 分类标签映射（从 categories 动态构建）
const categoryLabelMap = computed(() => {
  const map = {}
  props.categories.forEach(cat => {
    map[cat.key] = { label: cat.label, type: getCategoryTypeByIndex(cat.key) }
  })
  return map
})

// 根据 key 位置分配 tag type（第一个=primary，第二个=success，第三个=warning，其他=info）
function getCategoryTypeByIndex(key) {
  const index = props.categories.findIndex(cat => cat.key === key)
  const types = ['primary', 'success', 'warning', 'info']
  return types[index] || 'info'
}

function getCategoryLabel(category) {
  return categoryLabelMap.value[category]?.label || category || t('knowledge.categories.uncategorized')
}

function getCategoryTagType(category) {
  return categoryLabelMap.value[category]?.type || 'info'
}

// 状态映射
const statusMap = {
  pending: { key: 'knowledge.status.pending', type: 'warning' },
  processing: { key: 'knowledge.status.processing', type: 'info' },
  indexed: { key: 'knowledge.status.indexed', type: 'success' },
  failed: { key: 'knowledge.status.failed', type: 'danger' }
}

function getStatusLabel(status) {
  return statusMap[status]?.key ? t(statusMap[status].key) : status
}

function getStatusTagType(status) {
  return statusMap[status]?.type || 'info'
}

// 格式化文件大小
function formatFileSize(bytes) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

// 格式化日期
function formatDate(dateStr) {
  if (!dateStr) return '-'
  return dayjs(dateStr).format('YYYY-MM-DD HH:mm')
}
</script>

<style scoped lang="scss">
.doc-list {
  /* 无额外包装，由父级 tabs-container 提供卡片容器 */
}

/* Tab 样式 — 指示线风格，无内部分割线 */
.tabs {
  display: flex;
  gap: 0;
  margin-bottom: var(--spacing-md);
}

.tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: var(--spacing-sm) var(--spacing-md);
  background: transparent;
  border: none;
  font-size: var(--font-size-sm);
  color: #64748B;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-in-out);
  position: relative;

  &::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 2px;
    background: var(--color-primary);
    border-radius: 1px;
    transition: width var(--duration-fast) var(--ease-in-out);
  }

  &:hover {
    color: var(--color-primary);
  }

  &.active {
    color: var(--color-primary);
    font-weight: 600;

    &::after {
      width: 100%;
    }
  }
}

.tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  background: rgba(37, 99, 235, 0.1);
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-primary);
}

/* 搜索框 — 无阴影，融入背景 */
.search-wrapper {
  margin-bottom: var(--spacing-md);

  :deep(.el-input__wrapper) {
    border-radius: var(--radius-lg);
    box-shadow: none !important;
    border: 1px solid var(--color-border);
    transition: all var(--duration-fast) var(--ease-in-out);

    &:hover,
    &.is-focus {
      border-color: var(--color-primary);
      box-shadow: none !important;
    }
  }
}

/* 文件名单元格 */
.filename-cell {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.file-icon {
  color: var(--color-primary);
  font-size: 18px;
}

/* 无匹配结果 */
.no-match {
  text-align: center;
  padding: var(--spacing-2xl);
  color: #94A3B8;

  p {
    margin-top: var(--spacing-sm);
    font-size: var(--font-size-sm);
  }
}

/* 表格 — 无边框，干净融入 */
.doc-table {
  margin-top: var(--spacing-sm);

  :deep(.el-table__inner-wrapper) {
    &::before {
      display: none;
    }
  }

  :deep(.el-table__border-left-patch) {
    display: none;
  }

  :deep(.el-table__header th) {
    background: transparent;
    font-weight: 600;
    color: #475569;
    font-size: var(--font-size-sm);
    border-bottom: 1px solid var(--color-border) !important;
  }

  :deep(.el-table__row) {
    transition: background var(--duration-fast) var(--ease-in-out);

    &:hover {
      background: #F8FAFC !important;
    }

    td {
      border-bottom: none !important;
    }
  }

  :deep(.el-table__cell) {
    padding: 10px 0;
  }

  :deep(.el-button) {
    transition: all var(--duration-fast) var(--ease-in-out);

    &:hover {
      transform: translateY(-1px);
    }
  }
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: var(--spacing-3xl);
  color: #94A3B8;

  .empty-icon {
    font-size: 48px;
    margin-bottom: var(--spacing-md);
    opacity: 0.5;
  }

  p {
    margin-bottom: var(--spacing-sm);
  }

  .empty-hint {
    font-size: var(--font-size-sm);
    color: #CBD5E1;
  }
}
</style>
