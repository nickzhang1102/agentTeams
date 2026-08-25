<template>
  <div class="knowledge-page">
    <!-- 顶部导航 -->
    <header class="header">
      <div class="header-content">
        <div class="header-left">
          <el-button text class="back-btn" @click="router.push('/')">
            <el-icon><ArrowLeft /></el-icon>
            <span>{{ t('knowledge.header.backHome') }}</span>
          </el-button>
        </div>
        <div class="header-center">
          <h1 class="page-title">{{ t('knowledge.header.title') }}</h1>
        </div>
        <div class="header-right">
          <UserMenuDropdown :auth-store="authStore" />
        </div>
      </div>
    </header>

    <!-- 统计区 -->
    <section class="stats-bar">
      <div class="container-wide stats-inner">
        <div class="stat-pill">
          <span class="stat-label">{{ t('knowledge.stats.totalDocs') }}</span>
          <span class="stat-num">{{ knowledgeStore.status.total_docs }}</span>
        </div>
        <div class="stat-pill">
          <span class="stat-label">{{ t('knowledge.stats.indexedDocs') }}</span>
          <span class="stat-num">{{ knowledgeStore.status.indexed_docs }}</span>
        </div>
        <div class="stat-pill">
          <span class="stat-label">{{ t('knowledge.stats.pendingDocs') }}</span>
          <span class="stat-num">{{ knowledgeStore.status.pending_docs }}</span>
        </div>
      </div>
    </section>

    <!-- 主内容：全宽 -->
    <main class="main-content">
      <div class="container-wide">
        <!-- Tab 容器 -->
        <div class="tabs-container animate-slide-up">
          <div class="tabs-header">
            <div class="tabs">
              <button
                :class="['tab', { active: activeTab === 'documents' }]"
                @click="activeTab = 'documents'"
              >
                <el-icon class="tab-icon"><Document /></el-icon>
                {{ t('knowledge.tabs.documents') }}
              </button>
              <button
                :class="['tab', { active: activeTab === 'graph' }]"
                @click="activeTab = 'graph'"
              >
                <el-icon class="tab-icon"><Connection /></el-icon>
                {{ t('knowledge.tabs.graph') }}
              </button>
              <button
                :class="['tab', { active: activeTab === 'categories' }]"
                @click="activeTab = 'categories'"
              >
                <el-icon class="tab-icon"><Grid /></el-icon>
                {{ t('knowledge.tabs.categories') }}
              </button>
            </div>

            <!-- 上传按钮（仅文档列表 Tab 显示） -->
            <el-button
              v-if="activeTab === 'documents'"
              type="primary"
              :icon="Upload"
              @click="showUploadDialog"
            >
              {{ t('knowledge.actions.upload') }}
            </el-button>

            <!-- 新增分类按钮（仅分类管理 Tab 显示） -->
            <el-button
              v-if="activeTab === 'categories'"
              type="primary"
              :icon="Plus"
              @click="categoryManageRef?.showCreateDialog()"
            >
              {{ t('knowledge.actions.addCategory') }}
            </el-button>

            <!-- 刷新索引按钮 -->
            <el-button
              type="warning"
              :icon="Refresh"
              :loading="refreshing"
              @click="handleRefreshIndex"
            >
              {{ t('knowledge.actions.refreshIndex') }}
            </el-button>
          </div>

          <!-- Tab 内容 -->
          <div class="tabs-content">
            <KnowledgeDocList
              v-if="activeTab === 'documents'"
              :documents="filteredDocuments"
              :loading="knowledgeStore.loading"
              :current-category="currentCategory"
              :search-query="searchQuery"
              :categories="knowledgeStore.categories"
              @category-change="onCategoryChange"
              @search-change="onSearchChange"
              @preview="onPreview"
              @download="onDownload"
              @delete="onDelete"
            />

            <KnowledgeGraphExplorer
              v-else-if="activeTab === 'graph'"
              @preview-document="onPreviewById"
            />

            <KnowledgeCategoryManage
              v-else-if="activeTab === 'categories'"
              ref="categoryManageRef"
            />
          </div>
        </div>
      </div>
    </main>

    <!-- 上传弹窗 -->
    <KnowledgeUpload
      :visible="uploadDialogVisible"
      @close="uploadDialogVisible = false"
      @success="onUploadSuccess"
    />

    <!-- 预览弹窗 -->
    <el-dialog
      v-model="previewDialogVisible"
      :title="previewDialogTitle"
      width="780px"
      top="5vh"
      class="preview-dialog"
      destroy-on-close
    >
      <div v-loading="previewLoading" class="preview-content">
        <MarkdownRenderer
          v-if="previewContent"
          :content="previewContent"
        />
        <el-empty v-else-if="!previewLoading" :description="t('knowledge.preview.empty')" />
      </div>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useKnowledgeStore } from '@/stores/knowledge'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, Connection, Grid, Refresh, Upload, Plus, ArrowLeft } from '@element-plus/icons-vue'
import KnowledgeDocList from '@/components/knowledge/KnowledgeDocList.vue'
import KnowledgeUpload from '@/components/knowledge/KnowledgeUpload.vue'
import KnowledgeGraphExplorer from '@/components/knowledge/KnowledgeGraphExplorer.vue'
import KnowledgeCategoryManage from '@/components/knowledge/KnowledgeCategoryManage.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import UserMenuDropdown from '@/components/UserMenuDropdown.vue'
import api from '@/utils/api'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()
const knowledgeStore = useKnowledgeStore()

// 状态
const currentCategory = ref(null)
const searchQuery = ref('')
const uploadDialogVisible = ref(false)
const activeTab = ref('documents')
const categoryManageRef = ref(null)
const refreshing = ref(false)

// 预览弹窗
const previewDialogVisible = ref(false)
const previewLoading = ref(false)
const previewContent = ref('')
const previewFilename = ref('')

// 计算属性
const filteredDocuments = computed(() => {
  let docs = knowledgeStore.documents
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    docs = docs.filter(doc =>
      doc.filename.toLowerCase().includes(query)
    )
  }
  return docs
})

const previewDialogTitle = computed(() => (
  previewFilename.value
    ? t('knowledge.preview.titleWithFile', { filename: previewFilename.value })
    : t('knowledge.preview.title')
))

// 方法
function onCategoryChange(category) {
  currentCategory.value = category
  knowledgeStore.fetchDocuments(category)
}

function onSearchChange(query) {
  searchQuery.value = query
}

async function onDownload(doc) {
  try {
    await knowledgeStore.downloadDocument(doc.id, doc.filename)
    ElMessage.success(t('knowledge.messages.downloadSuccess'))
  } catch (error) {
    ElMessage.error(error.response?.data?.error || t('knowledge.messages.downloadFailed'))
  }
}

async function onPreview(doc) {
  previewDialogVisible.value = true
  previewLoading.value = true
  previewContent.value = ''
  previewFilename.value = doc.filename

  try {
    const result = await knowledgeStore.previewDocument(doc.id)
    if (result.success) {
      previewContent.value = result.data.content
    } else {
      previewContent.value = t('knowledge.preview.failedWithReason', { error: result.error })
    }
  } catch {
    previewContent.value = t('knowledge.preview.retry')
  } finally {
    previewLoading.value = false
  }
}

async function onPreviewById(docId) {
  previewDialogVisible.value = true
  previewLoading.value = true
  previewContent.value = ''
  previewFilename.value = ''

  try {
    const result = await knowledgeStore.previewDocument(docId)
    if (result.success) {
      previewContent.value = result.data.content
      previewFilename.value = result.data.filename || ''
    } else {
      previewContent.value = t('knowledge.preview.failedWithReason', { error: result.error })
    }
  } catch {
    previewContent.value = t('knowledge.preview.retry')
  } finally {
    previewLoading.value = false
  }
}

async function onDelete(doc) {
  try {
    await ElMessageBox.confirm(
      t('knowledge.messages.deleteDocument', { filename: doc.filename }),
      t('knowledge.messages.deleteTitle'),
      {
        confirmButtonText: t('knowledge.actions.confirmDelete'),
        cancelButtonText: t('knowledge.actions.cancel'),
        type: 'warning'
      }
    )

    await knowledgeStore.deleteDocument(doc.id)
    ElMessage.success(t('knowledge.messages.deleteSuccess'))
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.error || t('knowledge.messages.deleteFailed'))
    }
  }
}

function showUploadDialog() {
  uploadDialogVisible.value = true
}

async function handleRefreshIndex() {
  refreshing.value = true
  try {
    const result = await knowledgeStore.refreshIndex()
    if (result.success) {
      const total = result.result?.total || 0
      if (total === 0) {
        // 无文档需处理，翻译可能在后台进行，稍等后刷新
        ElMessage.success(t('knowledge.messages.refreshAlreadyLatest'))
        await knowledgeStore.fetchGraphData()
      } else {
        ElMessage.info(t('knowledge.messages.refreshProcessing', { total }))
        // 轮询等待后台处理完成
        await pollUntilDone()
        ElMessage.success(t('knowledge.messages.refreshDone'))
      }
      await Promise.all([
        knowledgeStore.fetchDocuments(),
        knowledgeStore.fetchStatus(),
        knowledgeStore.fetchGraphData(),
      ])
    } else {
      ElMessage.error(result.error || t('knowledge.messages.refreshFailed'))
    }
  } catch {
    ElMessage.error(t('knowledge.messages.refreshFailed'))
  } finally {
    refreshing.value = false
  }
}

async function pollUntilDone(maxWait = 120000, interval = 3000) {
  const deadline = Date.now() + maxWait
  while (Date.now() < deadline) {
    await new Promise(r => setTimeout(r, interval))
    try {
      const res = await api.get('/api/knowledge/status')
      if (res.data.pending_docs === 0) return
    } catch { /* ignore */ }
  }
}

async function onUploadSuccess(doc) {
  // 上传成功后刷新状态统计
  await knowledgeStore.fetchStatus()
}

// 生命周期
onMounted(async () => {
  // 刷新用户信息，确保 is_admin 等字段为最新（避免 localStorage 缓存过期数据）
  await authStore.fetchCurrentUser()

  await Promise.all([
    knowledgeStore.fetchDocuments(),
    knowledgeStore.fetchStatus(),
    knowledgeStore.fetchCategories()
  ])
})
</script>

<style scoped lang="scss">
.knowledge-page {
  min-height: 100vh;
  background: var(--color-background);
}

/* 头部导航 — 统一风格 */
.header {
  position: sticky;
  top: 0;
  background: var(--color-card);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--color-border);
  z-index: 100;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 var(--spacing-md);
}

.header-left {
  display: flex;
  align-items: center;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-in-out);
}
.back-btn:hover {
  background: var(--color-hover);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.header-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.page-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text);
  margin: 0;
}

.header-right {
  display: flex;
  align-items: center;
}

/* 全宽容器 — 数据密集页 */
.container-wide {
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 var(--spacing-md);
}

@media (min-width: 768px) {
  .container-wide { padding: 0 var(--spacing-xl); }
}

@media (min-width: 1280px) {
  .container-wide { padding: 0 var(--spacing-2xl); }
}

/* 统计条 */
.stats-bar {
  padding: var(--spacing-md) 0;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-card);
}

.stats-inner {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.stat-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-md);
  background: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  transition: all var(--duration-fast) var(--ease-in-out);

  &:hover {
    border-color: var(--color-primary);
    background: rgba(37, 99, 235, 0.04);
  }
}

.stat-label {
  font-size: var(--font-size-xs);
  color: #94A3B8;
  font-weight: 500;
}

.stat-num {
  font-family: var(--font-heading);
  font-size: var(--font-size-sm);
  font-weight: 700;
  color: var(--color-primary);
}

/* 主内容 */
.main-content {
  padding: var(--spacing-lg) 0 var(--spacing-2xl);

  @media (min-width: 768px) {
    padding: var(--spacing-xl) 0 var(--spacing-3xl);
  }
}

/* Tab 容器 */
.tabs-container {
  background: var(--color-card);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border);
  overflow: hidden;
  transition: all var(--duration-normal) var(--ease-in-out);

  &:hover {
    box-shadow: 0 4px 16px rgba(37, 99, 235, 0.06);
  }
}

.tabs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-xl);
  border-bottom: 1px solid var(--color-border);
}

.tabs {
  display: flex;
  gap: 0;
}

/* Tab 指示线风格 — 与主页 cases-section 对齐 */
.tab {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-md) var(--spacing-lg);
  background: transparent;
  border: none;
  font-family: var(--font-body);
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--color-text);
  cursor: pointer;
  transition: all var(--duration-normal) var(--ease-in-out);
  position: relative;

  &::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 2px;
    background: var(--color-primary);
    border-radius: 1px;
    transition: width var(--duration-normal) var(--ease-in-out);
  }

  &:hover {
    color: var(--color-primary);
  }

  &.active {
    color: var(--color-primary);
    font-weight: 600;

    &::after {
      width: 24px;
    }
  }
}

.tab-icon {
  font-size: 16px;
}

.tabs-content {
  padding: var(--spacing-md);

  @media (min-width: 768px) {
    padding: var(--spacing-md) var(--spacing-lg);
  }
}

@media (max-width: 600px) {
  .tabs-header {
    flex-direction: column;
    gap: var(--spacing-sm);
  }

  .page-title {
    font-size: var(--font-size-h3);
  }
}

/* 预览弹窗 */
.preview-content {
  max-height: 65vh;
  overflow-y: auto;
  padding: var(--spacing-md);
  background: #FAFBFC;
  border-radius: var(--radius-md);
  line-height: 1.7;
  font-size: var(--font-size-sm);
}
</style>
