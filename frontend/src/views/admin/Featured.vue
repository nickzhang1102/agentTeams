<template>
  <div class="admin-featured">
    <div class="page-title">
      <h2>{{ t('admin.featured.title') }}</h2>
      <p>{{ t('admin.featured.description') }}</p>
    </div>

    <el-card shadow="hover" class="section-card">
      <template #header>
        <div class="card-header">
          <span>{{ t('admin.featured.conversationList') }}</span>
          <el-button type="primary" size="small" @click="handleRefresh">{{ t('admin.actions.refresh') }}</el-button>
        </div>
      </template>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-input
          v-model="searchQuery"
          :placeholder="t('admin.featured.searchTitle')"
          clearable
          style="width: 200px"
          @clear="handleFilterChange"
          @keyup.enter="handleFilterChange"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select
          v-model="selectedCategory"
          :placeholder="t('admin.dashboard.allCategories')"
          clearable
          style="width: 140px"
          @change="handleFilterChange"
        >
          <el-option :label="t('admin.status.all')" value="all" />
          <el-option
            v-for="option in categoryOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <el-button type="primary" @click="handleFilterChange">{{ t('admin.actions.filter') }}</el-button>
        <el-button @click="handleResetFilters">{{ t('admin.actions.reset') }}</el-button>
      </div>

      <!-- 错误提示 -->
      <el-alert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        show-icon
        closable
        @close="errorMessage = null"
        style="margin-bottom: 16px"
      />

      <!-- 表格 -->
      <el-table
        :data="conversations"
        v-loading="loading"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="title" :label="t('admin.dashboard.title')" min-width="250" show-overflow-tooltip />
        <el-table-column prop="category" :label="t('admin.common.category')" width="100">
          <template #default="{ row }">
            <el-tag :type="getCategoryType(row.category)" size="small">
              {{ getCategoryLabel(row.category) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="t('admin.common.status')" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.featured.featured')" width="100" align="center">
          <template #default="{ row }">
            <el-switch
              v-model="row.is_featured"
              @change="(val) => handleToggleFeatured(row, val)"
              :loading="row._updating"
            />
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.featured.order')" width="100" align="center">
          <template #default="{ row }">
            <el-input-number
              v-if="row.is_featured"
              v-model="row.featured_order"
              :min="0"
              :max="999"
              size="small"
              controls-position="right"
              style="width: 80px"
              @change="(val) => handleUpdateOrder(row, val)"
            />
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" :label="t('admin.common.updatedAt')" width="170">
          <template #default="{ row }">
            {{ formatTime(row.updated_at) }}
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import api from '@/utils/api'
import { formatLocaleDateTime } from '@/utils/localeFormat'

const { t, locale } = useI18n()

// 状态
const loading = ref(false)
const errorMessage = ref(null)
const conversations = ref([])
const searchQuery = ref('')
const selectedCategory = ref('all')
const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(0)

// 分类映射（Element Plus tag type）
const categoryMap = Object.fromEntries(
  Object.entries({
    technology: 'primary',
    business: 'success',
    medical: 'danger',
    investment: 'warning',
    science: 'info',
    writing: '',
    legal: 'primary',
    education: 'success',
    lifestyle: 'warning',
    other: 'info',
  }).map(([key, type]) => [key, { type }])
)

const categoryOptions = computed(() => Object.keys(categoryMap).map(value => ({
  value,
  label: getCategoryLabel(value)
})))

// 状态映射（Element Plus tag type）
const statusMap = {
  'new': 'info',
  'analyzing': 'warning',
  'error': 'danger',
  'completed': 'success',
}

const getCategoryType = (category) => categoryMap[category]?.type || 'info'
const getStatusType = (status) => statusMap[status] || 'info'
const getCategoryLabel = (category) => t(`admin.dashboard.categories.${category}`, category)
const getStatusLabel = (status) => t(`admin.dashboard.statuses.${status}`, status)

const formatTime = (time) => {
  if (!time) return '-'
  return formatLocaleDateTime(time, locale.value)
}

// 获取列表
const fetchConversations = async () => {
  loading.value = true
  errorMessage.value = null
  try {
    const params = {
      page: currentPage.value,
      per_page: pageSize.value
    }
    if (searchQuery.value) params.search = searchQuery.value
    if (selectedCategory.value && selectedCategory.value !== 'all') {
      params.category = selectedCategory.value
    }

    const response = await api.get('/api/admin/featured-conversations', { params })
    conversations.value = response.data.conversations
    total.value = response.data.pagination.total
  } catch (error) {
    errorMessage.value = error.response?.data?.error || t('admin.featured.loadFailed')
    console.error('获取对话列表失败:', error)
  } finally {
    loading.value = false
  }
}

// 切换精选状态
const handleToggleFeatured = async (row, isFeatured) => {
  row._updating = true
  try {
    await api.put('/api/admin/featured-conversations', {
      conversation_id: row.id,
      is_featured: isFeatured,
      featured_order: isFeatured ? (row.featured_order || 0) : 0
    })
    ElMessage.success(t(isFeatured ? 'admin.featured.enabled' : 'admin.featured.disabled'))
  } catch (error) {
    // 回滚状态
    row.is_featured = !isFeatured
    ElMessage.error(error.response?.data?.error || t('admin.errors.updateFailed'))
    console.error('更新精选状态失败:', error)
  } finally {
    row._updating = false
  }
}

// 更新排序
const handleUpdateOrder = async (row, order) => {
  try {
    await api.put('/api/admin/featured-conversations', {
      conversation_id: row.id,
      is_featured: true,
      featured_order: order
    })
    ElMessage.success(t('admin.featured.orderUpdated'))
  } catch (error) {
    ElMessage.error(error.response?.data?.error || t('admin.featured.orderUpdateFailed'))
    console.error('更新排序失败:', error)
  }
}

// 筛选
const handleFilterChange = () => {
  currentPage.value = 1
  fetchConversations()
}

// 重置筛选
const handleResetFilters = () => {
  searchQuery.value = ''
  selectedCategory.value = 'all'
  currentPage.value = 1
  fetchConversations()
}

// 刷新
const handleRefresh = () => {
  fetchConversations()
}

// 分页
const handleSizeChange = (size) => {
  pageSize.value = size
  currentPage.value = 1
  fetchConversations()
}

const handlePageChange = (page) => {
  currentPage.value = page
  fetchConversations()
}

// 生命周期
onMounted(() => {
  fetchConversations()
})
</script>

<style scoped>
.admin-featured {
  padding: 20px;
}

.page-title {
  margin-bottom: 24px;
}

.page-title h2 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
}

.page-title p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.section-card {
  margin-bottom: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.text-muted {
  color: var(--el-text-color-secondary);
}
</style>
