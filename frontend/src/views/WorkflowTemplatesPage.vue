<template>
  <div class="templates-page">
    <!-- 顶部导航 -->
    <header class="header">
      <div class="header-content">
        <div class="header-left">
          <el-button text class="back-btn" @click="handleBack">
            <el-icon><ArrowLeft /></el-icon>
            <span>{{ t('workflowTemplatesPage.back') }}</span>
          </el-button>
        </div>
        <div class="header-center">
          <h1 class="page-title">{{ t('workflowTemplatesPage.title') }}</h1>
        </div>
        <div class="header-right">
          <UserMenuDropdown :auth-store="authStore" />
        </div>
      </div>
    </header>

    <div class="page-body">
      <div class="page-actions">
        <el-button type="primary" @click="openCreate">+ {{ t('workflowTemplatesPage.create') }}</el-button>
      </div>

    <!-- 分类 Tab -->
    <el-tabs v-model="activeTab" class="category-tabs" @tab-change="onTabChange">
      <el-tab-pane :label="t('workflowTemplatesPage.tabs.all')" name="all" />
      <el-tab-pane :label="t('workflowTemplatesPage.tabs.system')" name="system" />
      <el-tab-pane :label="t('workflowTemplatesPage.tabs.fast')" name="fast" />
      <el-tab-pane :label="t('workflowTemplatesPage.tabs.mine')" name="mine" />
    </el-tabs>

    <!-- 模板列表 -->
    <div class="template-grid" v-loading="store.loading">
      <el-card
        v-for="tpl in store.templates"
        :key="tpl.id"
        class="template-card"
        shadow="hover"
      >
        <div class="tpl-header">
        <div class="tpl-title">{{ catalogLabel(tpl) }}</div>
          <div class="tpl-meta">
            <el-tag v-if="tpl.is_system" size="small" type="info">{{ t('workflowTemplatesPage.system') }}</el-tag>
            <el-tag v-else size="small" type="success">{{ t('workflowTemplatesPage.custom') }}</el-tag>
            <el-tag v-if="tpl.skip_assessment" size="small" type="warning">{{ t('workflowTemplatesPage.fastMode') }}</el-tag>
            <span class="tpl-usage">{{ t('workflowTemplatesPage.usageCount', { count: tpl.usage_count }) }}</span>
          </div>
        </div>

        <p class="tpl-desc">{{ tpl.description || t('workflowTemplatesPage.noDescription') }}</p>

        <div class="tpl-config">
          <span v-if="displayAgents(tpl).length">{{ t('workflowTemplatesPage.agents', { names: displayAgents(tpl).map(catalogLabel).join(t('common.lists.separator')) }) }}</span>
          <span v-else-if="tpl.pack_id">{{ t('workflowTemplatesPage.pack', { id: tpl.pack_id }) }}</span>
          <span>{{ t('workflowTemplatesPage.threshold', { value: tpl.assessment_threshold }) }}</span>
        </div>

        <div class="tpl-actions">
          <el-button size="small" type="primary" @click="handleApply(tpl)">{{ t('workflowTemplatesPage.apply') }}</el-button>
          <el-button size="small" @click="openView(tpl)">{{ t('workflowTemplatesPage.view') }}</el-button>
          <el-button v-if="!tpl.is_system" size="small" @click="openEdit(tpl)">{{ t('workflowTemplatesPage.edit') }}</el-button>
          <el-button v-if="!tpl.is_system" size="small" type="danger" @click="handleDelete(tpl)">{{ t('workflowTemplatesPage.delete') }}</el-button>
        </div>
      </el-card>

      <el-empty v-if="!store.loading && store.templates.length === 0" :description="t('workflowTemplatesPage.empty')" />
    </div>

    <!-- 分页 -->
    <div class="pagination-wrapper" v-if="store.pagination.total > store.pagination.per_page">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="store.pagination.per_page"
        :total="store.pagination.total"
        layout="total, prev, pager, next"
        background
        @current-change="onPageChange"
      />
    </div>
    </div><!-- /.page-body -->

    <!-- 创建/编辑弹窗 -->
    <WorkflowTemplateDialog
      v-model="showDialog"
      :template="editingTemplate"
      :readonly="dialogReadonly"
      @saved="onSaved"
    />

    <!-- 一键启动弹窗 -->
    <el-dialog v-model="showApplyDialog" :title="t('workflowTemplatesPage.applyTitle')" width="480px">
      <el-form :model="applyForm" label-width="80px">
        <el-form-item :label="t('workflowTemplatesPage.message')" required>
          <el-input
            v-model="applyForm.message"
            type="textarea"
            :rows="3"
            :placeholder="t('workflowTemplatesPage.messagePlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showApplyDialog = false">{{ t('workflowTemplatesPage.cancel') }}</el-button>
        <el-button type="primary" :loading="applying" @click="confirmApply">{{ t('workflowTemplatesPage.startAnalysis') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { useWorkflowTemplateStore } from '@/stores/workflowTemplate'
import { useAuthStore } from '@/stores/auth'
import { useConversationsStore } from '@/stores/conversations'
import { useLeaderStore } from '@/stores/leader'
import UserMenuDropdown from '@/components/UserMenuDropdown.vue'
import WorkflowTemplateDialog from './WorkflowTemplateDialog.vue'
import { catalogLabel } from '@/utils/catalog'

const router = useRouter()
const { t } = useI18n()
const store = useWorkflowTemplateStore()
const authStore = useAuthStore()
const conversationsStore = useConversationsStore()
const leaderStore = useLeaderStore()

const activeTab = ref('all')

function handleBack() {
  router.push('/')
}
const currentPage = ref(1)
const showDialog = ref(false)
const editingTemplate = ref(null)
const dialogReadonly = ref(false)
const showApplyDialog = ref(false)
const applying = ref(false)
const applyTarget = ref(null)
const applyForm = ref({ message: '' })

function fetchList() {
  const params = { page: currentPage.value, per_page: 20 }
  if (activeTab.value === 'system') params.is_system = true
  else if (activeTab.value === 'mine') params.is_system = false
  else if (activeTab.value === 'fast') params.skip_assessment = true
  store.fetchTemplates(params)
}

function onTabChange() {
  currentPage.value = 1
  fetchList()
}

function onPageChange(page) {
  currentPage.value = page
  fetchList()
}

function openCreate() {
  editingTemplate.value = null
  dialogReadonly.value = false
  showDialog.value = true
}

function openEdit(tpl) {
  editingTemplate.value = { ...tpl }
  dialogReadonly.value = false
  showDialog.value = true
}

function openView(tpl) {
  editingTemplate.value = { ...tpl }
  dialogReadonly.value = true
  showDialog.value = true
}

function displayAgents(tpl) {
  return tpl.resolved_agents?.length ? tpl.resolved_agents : (tpl.agents || [])
}

function onSaved() {
  showDialog.value = false
  editingTemplate.value = null
  fetchList()
}

async function handleDelete(tpl) {
  try {
    await ElMessageBox.confirm(t('workflowTemplatesPage.deletePrompt', { name: catalogLabel(tpl) }), t('workflowTemplatesPage.deleteTitle'), {
      confirmButtonText: t('workflowTemplatesPage.delete'),
      cancelButtonText: t('workflowTemplatesPage.cancel'),
      type: 'warning',
    })
    const result = await store.deleteTemplate(tpl.id)
    if (result.success) {
      ElMessage.success(t('workflowTemplatesPage.deleteSuccess'))
    } else {
      ElMessage.error(result.error)
    }
  } catch { /* 取消 */ }
}

function handleApply(tpl) {
  applyTarget.value = tpl
  applyForm.value = { message: '' }
  showApplyDialog.value = true
}

async function confirmApply() {
  if (!applyForm.value.message.trim()) {
    ElMessage.warning(t('workflowTemplatesPage.messageRequired'))
    return
  }
  applying.value = true
  try {
    // 先创建对话
    const convResult = await conversationsStore.createConversation(
      applyForm.value.message.trim(),
      true,
      null,
    )
    if (!convResult.success) {
      ElMessage.error(t('workflowTemplatesPage.createConversationFailed'))
      return
    }

    const conversationId = convResult.conversation.id
    const shareToken = convResult.conversation.share_token

    // 传递启动数据给 Leader
    leaderStore.pendingSessionData = {
      message: applyForm.value.message.trim(),
      fileIds: [],
      templateId: applyTarget.value.id,
    }

    showApplyDialog.value = false
    router.push(`/chat/${shareToken || conversationId}`)
  } catch (err) {
    ElMessage.error(err.message || t('workflowTemplatesPage.startFailed'))
  } finally {
    applying.value = false
  }
}

onMounted(() => fetchList())
</script>

<style lang="scss" scoped>
.templates-page {
  min-height: 100vh;
  background: var(--color-background);
}

/* 头部导航 */
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
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
}

.header-left { display: flex; align-items: center; }

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

.header-right { display: flex; align-items: center; }

/* 页面内容 */
.page-body {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.page-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 20px;
}

.category-tabs {
  margin-bottom: 16px;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  min-height: 200px;
}

.template-card {
  cursor: default;
  transition: transform 0.2s;
}
.template-card:hover {
  transform: translateY(-2px);
}

.tpl-header {
  margin-bottom: 8px;
}

.tpl-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 6px;
}

.tpl-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.tpl-usage {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.tpl-desc {
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
  margin: 0 0 10px;
}

.tpl-config {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.tpl-actions {
  display: flex;
  gap: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 10px;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

@media (max-width: 767px) {
  .page-body { padding: 12px; }
  .template-grid { grid-template-columns: 1fr; }
  .header-center {
    position: static;
    transform: none;
  }
  .page-title {
    font-size: var(--font-size-base);
  }
}
</style>
