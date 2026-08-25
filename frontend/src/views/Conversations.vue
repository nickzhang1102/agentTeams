<template>
  <div class="conversations-container">
    <!-- Header Section -->
    <div class="header-section">
      <div class="header-content animate-fade-in">
        <h1 class="page-title text-gradient">对话历史</h1>
        <p class="page-subtitle">管理您的所有对话</p>
      </div>
      <el-button type="primary" @click="showCreateDialog = true" class="create-button">
        <el-icon><Plus /></el-icon>
        <span>新建对话</span>
      </el-button>
    </div>

    <!-- Search and Filters -->
    <div class="filters-section glass-container animate-slide-in">
      <el-input
        v-model="searchText"
        placeholder="搜索对话标题..."
        clearable
        class="search-input"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <!-- Conversations Grid -->
    <div v-loading="loading" class="conversations-grid">
      <div
        v-for="conversation in filteredConversations"
        :key="conversation.id"
        class="conversation-card glass-card animate-fade-in"
        @click="openConversation(conversation)"
      >
        <!-- Card Header -->
        <div class="card-header">
          <h3 class="conversation-title">{{ conversation.title }}</h3>
        </div>

        <!-- Card Meta -->
        <div class="card-meta">
          <div class="meta-item">
            <el-icon><Clock /></el-icon>
            <span>创建: {{ formatTime(conversation.created_at) }}</span>
          </div>
          <div class="meta-item">
            <el-icon><Timer /></el-icon>
            <span>更新: {{ formatTime(conversation.updated_at) }}</span>
          </div>
        </div>

        <!-- Card Actions -->
        <div class="card-actions">
          <el-button
            type="primary"
            size="small"
            @click.stop="openConversation(conversation)"
            class="action-button"
          >
            <el-icon><View /></el-icon>
            <span>打开</span>
          </el-button>
          <el-button
            type="warning"
            size="small"
            @click.stop="editConversation(conversation)"
            class="action-button"
          >
            <el-icon><Edit /></el-icon>
            <span>编辑</span>
          </el-button>
          <el-button
            type="danger"
            size="small"
            @click.stop="deleteConversation(conversation)"
            class="action-button"
          >
            <el-icon><Delete /></el-icon>
            <span>删除</span>
          </el-button>
        </div>
      </div>

      <!-- Empty State -->
      <div v-if="!loading && filteredConversations.length === 0" class="empty-state">
        <svg width="120" height="120" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="empty-icon">
          <path d="M20 2H4C2.9 2 2 2.9 2 4V22L6 18H20C21.1 18 22 17.1 22 16V4C22 2.9 21.1 2 20 2ZM20 16H6L4 18V4H20V16Z" fill="#DB2777" opacity="0.3"/>
        </svg>
        <h3 class="empty-title">暂无对话</h3>
        <p class="empty-subtitle">创建您的第一个对话开始聊天吧</p>
        <el-button type="primary" @click="showCreateDialog = true">
          <el-icon><Plus /></el-icon>
          <span>新建对话</span>
        </el-button>
      </div>
    </div>

    <!-- Create Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      title="新建对话"
      width="500px"
      class="modern-dialog"
    >
      <el-form
        ref="createFormRef"
        :model="createForm"
        :rules="createRules"
        label-width="80px"
      >
        <el-form-item label="标题" prop="title">
          <el-input v-model="createForm.title" placeholder="输入对话标题" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createConversation">创建</el-button>
      </template>
    </el-dialog>

    <!-- Edit Dialog -->
    <el-dialog
      v-model="showEditDialog"
      title="编辑对话"
      width="500px"
      class="modern-dialog"
    >
      <el-form
        ref="editFormRef"
        :model="editForm"
        :rules="editRules"
        label-width="80px"
      >
        <el-form-item label="标题" prop="title">
          <el-input v-model="editForm.title" placeholder="输入对话标题" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="updateConversation">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useConversationsStore } from '@/stores/conversations'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'

const router = useRouter()
const conversationsStore = useConversationsStore()

const loading = ref(false)
const searchText = ref('')
const showCreateDialog = ref(false)
const showEditDialog = ref(false)

const createFormRef = ref(null)
const editFormRef = ref(null)

const createForm = ref({
  title: ''
})

const editForm = ref({
  id: null,
  title: ''
})

const createRules = {
  title: [
    { required: true, message: '请输入标题', trigger: 'blur' }
  ]
}

const editRules = {
  title: [
    { required: true, message: '请输入标题', trigger: 'blur' }
  ]
}

const conversations = computed(() => conversationsStore.conversations)

const filteredConversations = computed(() => {
  if (!searchText.value) return conversations.value
  return conversations.value.filter(c =>
    c.title.toLowerCase().includes(searchText.value.toLowerCase())
  )
})

// 加载对话列表
async function loadConversations() {
  loading.value = true
  const result = await conversationsStore.fetchConversations()
  loading.value = false

  if (!result.success) {
    ElMessage.error(result.error)
  }
}

// 打开对话
function openConversation(conversation) {
  const token = conversation.share_token || conversation.id
  router.push(`/conversation/${token}`)
}

// 创建对话
async function createConversation() {
  if (!createFormRef.value) return

  await createFormRef.value.validate(async (valid) => {
    if (!valid) return

    const result = await conversationsStore.createConversation(createForm.value.title)

    if (result.success) {
      ElMessage.success('创建成功')
      showCreateDialog.value = false
      createForm.value.title = ''
      const token = result.conversation.share_token || result.conversation.id
      router.push(`/conversation/${token}`)
    } else {
      ElMessage.error(result.error)
    }
  })
}

// 编辑对话
function editConversation(conversation) {
  editForm.value = {
    id: conversation.id,
    title: conversation.title
  }
  showEditDialog.value = true
}

// 更新对话
async function updateConversation() {
  if (!editFormRef.value) return

  await editFormRef.value.validate(async (valid) => {
    if (!valid) return

    const result = await conversationsStore.updateConversation(
      editForm.value.id,
      {
        title: editForm.value.title
      }
    )

    if (result.success) {
      ElMessage.success('更新成功')
      showEditDialog.value = false
    } else {
      ElMessage.error(result.error)
    }
  })
}

// 删除对话
async function deleteConversation(conversation) {
  try {
    await ElMessageBox.confirm(
      '确定要删除这个对话吗?此操作不可撤销。',
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    // 在删除前记录是否是当前对话
    const isCurrentConversation = conversationsStore.currentConversation?.id === conversation.id

    const result = await conversationsStore.deleteConversation(conversation.id)

    if (result.success) {
      ElMessage.success('删除成功')

      // 如果删除的是当前对话，跳转到首页
      if (isCurrentConversation) {
        conversationsStore.clearCurrentConversation()
        router.push('/')
      }
    } else {
      ElMessage.error(result.error)
    }
  } catch {
    // 用户取消
  }
}

// 格式化时间
function formatTime(time) {
  return dayjs(time).format('YYYY-MM-DD HH:mm')
}

onMounted(() => {
  loadConversations()
})
</script>

<style scoped>
.conversations-container {
  padding: var(--space-8);
  min-height: 100vh;
  max-width: 1400px;
  margin: 0 auto;
}

/* Header Section */
.header-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-8);
}

.header-content {
  flex: 1;
}

.page-title {
  font-size: var(--text-4xl);
  font-weight: 700;
  margin: 0 0 var(--space-2) 0;
  letter-spacing: -0.025em;
}

.page-subtitle {
  margin: 0;
  font-size: var(--text-lg);
  color: var(--color-text-secondary);
}

.create-button {
  height: 48px;
  padding: 0 var(--space-6);
  font-weight: 600;
  border-radius: var(--radius-lg);
}

/* Filters Section */
.filters-section {
  margin-bottom: var(--space-6);
  padding: var(--space-4);
}

.search-input {
  max-width: 400px;
}

/* Conversations Grid */
.conversations-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--space-6);
  min-height: 400px;
}

/* Conversation Card */
.conversation-card {
  padding: var(--space-6);
  cursor: pointer;
  position: relative;
  overflow: hidden;
}

.conversation-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: linear-gradient(180deg, var(--color-primary) 0%, var(--color-cta) 100%);
  opacity: 0;
  transition: opacity var(--transition-base);
}

.conversation-card:hover::before {
  opacity: 1;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-4);
  gap: var(--space-3);
}

.conversation-title {
  flex: 1;
  font-size: var(--text-lg);
  font-weight: 600;
  margin: 0;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.card-meta {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid rgba(37, 99, 235, 0.1);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.meta-item .el-icon {
  font-size: 16px;
  color: var(--color-primary);
}

.card-actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.action-button {
  flex: 1;
  min-width: 80px;
}

/* Empty State */
.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: var(--space-16) var(--space-4);
}

.empty-icon {
  margin-bottom: var(--space-6);
  opacity: 0.5;
}

.empty-title {
  font-size: var(--text-2xl);
  font-weight: 600;
  margin: 0 0 var(--space-2) 0;
  color: var(--color-text-primary);
}

.empty-subtitle {
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  margin: 0 0 var(--space-6) 0;
}

/* Modern Dialog */
:deep(.modern-dialog) {
  border-radius: var(--radius-xl);
}

:deep(.modern-dialog .el-dialog__header) {
  padding: var(--space-6);
  border-bottom: 1px solid rgba(37, 99, 235, 0.1);
}

:deep(.modern-dialog .el-dialog__body) {
  padding: var(--space-6);
}

:deep(.modern-dialog .el-dialog__footer) {
  padding: var(--space-4) var(--space-6);
  border-top: 1px solid rgba(37, 99, 235, 0.1);
}

/* Responsive */
@media (max-width: 1024px) {
  .conversations-container {
    padding: var(--space-6);
  }

  .conversations-grid {
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  }
}

@media (max-width: 768px) {
  .conversations-container {
    padding: var(--space-4);
  }

  .header-section {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
  }

  .page-title {
    font-size: var(--text-3xl);
  }

  .create-button {
    width: 100%;
  }

  .search-input {
    max-width: 100%;
  }

  .conversations-grid {
    grid-template-columns: 1fr;
    gap: var(--space-4);
  }

  .card-actions {
    flex-direction: column;
  }

  .action-button {
    width: 100%;
  }
}

/* Accessibility */
@media (prefers-reduced-motion: reduce) {
  .conversation-card:hover {
    transform: none;
  }

  .conversation-card:hover::before {
    opacity: 1;
  }
}
</style>
