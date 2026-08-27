<template>
  <div class="llm-models-page">
    <div class="page-title">
      <h2>{{ t('admin.llmModels.title') }}</h2>
      <p>{{ t('admin.llmModels.description') }}</p>
    </div>

    <el-card shadow="hover" class="section-card">
      <template #header>
        <div class="card-header">
          <span>{{ t('admin.llmModels.list') }}</span>
          <el-button type="primary" :icon="Plus" @click="openCreateDialog">{{ t('admin.llmModels.add') }}</el-button>
        </div>
      </template>

      <el-table
        :data="models"
        v-loading="loading"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="model_id" :label="t('admin.llmModels.modelId')" min-width="160" />
        <el-table-column prop="display_name" :label="t('admin.llmModels.displayName')" min-width="160" />
        <el-table-column :label="t('admin.common.status')" width="80" align="center">
          <template #default="{ row }">
            <el-tooltip
              v-if="row.last_test_at"
              :content="testStatusTooltip(row)"
              placement="top"
            >
              <span
                class="status-dot"
                :class="row.last_test_ok === true ? 'status-ok' : row.last_test_ok === false ? 'status-fail' : 'status-unknown'"
              />
            </el-tooltip>
            <span v-else class="status-dot status-unknown" />
          </template>
        </el-table-column>
        <el-table-column label="Context" width="100" align="right">
          <template #default="{ row }">{{ formatNumber(row.context_limit) }}</template>
        </el-table-column>
        <el-table-column label="Max Output" width="100" align="right">
          <template #default="{ row }">{{ formatNumber(row.max_output_tokens) }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.llmModels.enabled')" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">
              {{ row.is_enabled ? t('admin.status.active') : t('admin.status.inactive') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.llmModels.default')" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="warning" size="small">{{ t('admin.llmModels.default') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="API Key" width="140">
          <template #default="{ row }">
            <span class="api-key-masked">{{ row.api_key_masked || '****' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.llmModels.lastTest')" width="160">
          <template #default="{ row }">
            <span v-if="row.last_test_at" class="test-time">
              {{ formatTime(row.last_test_at) }}
            </span>
            <span v-else class="test-time text-muted">{{ t('admin.llmModels.notTested') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.common.operations')" width="240" fixed="right">
          <template #default="{ row }">
            <el-button size="small" :icon="Connection" @click="testModel(row)" :loading="row._testing">
              {{ t('admin.actions.test') }}
            </el-button>
            <el-button size="small" type="primary" :icon="Edit" @click="openEditDialog(row)">
              {{ t('admin.actions.edit') }}
            </el-button>
            <el-popconfirm :title="t('admin.llmModels.deleteConfirm')" @confirm="deleteModel(row)">
              <template #reference>
                <el-button size="small" type="danger" :icon="Delete">{{ t('admin.actions.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? t('admin.llmModels.editTitle') : t('admin.llmModels.add')"
      width="min(560px, calc(100vw - 32px))"
      destroy-on-close
    >
      <el-form :model="form" label-width="110px" label-position="right" ref="formRef" :rules="rules">
        <el-form-item :label="t('admin.llmModels.modelId')" prop="model_id">
          <el-input v-model="form.model_id" :disabled="isEditing" :placeholder="t('admin.llmModels.modelIdPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('admin.llmModels.displayName')" prop="display_name">
          <el-input v-model="form.display_name" :placeholder="t('admin.llmModels.displayNamePlaceholder')" />
        </el-form-item>
        <el-form-item label="Base URL" prop="base_url">
          <el-input v-model="form.base_url" :placeholder="t('admin.llmModels.baseUrlPlaceholder')" />
          <div class="form-tip">{{ t('admin.llmModels.baseUrlTip') }}</div>
        </el-form-item>
        <el-form-item label="API Key" :prop="isEditing ? '' : 'api_key'">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="isEditing ? t('admin.llmModels.keepApiKey') : t('admin.llmModels.apiKeyPlaceholder')"
          />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="Context Limit">
              <el-input-number v-model="form.context_limit" :min="1" :step="1000" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Max Output">
              <el-input-number v-model="form.max_output_tokens" :min="1" :step="1000" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('admin.llmModels.sortOrder')">
              <el-input-number v-model="form.sort_order" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('admin.llmModels.enabled')">
              <el-switch v-model="form.is_enabled" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="24">
            <el-form-item :label="t('admin.llmModels.defaultModel')">
              <el-switch v-model="form.is_default" />
              <span class="switch-tip">{{ t('admin.llmModels.defaultTip') }}</span>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button :icon="Connection" :loading="testingConfig" @click="testDialogConfig">
            {{ t('admin.llmModels.testConnection') }}
          </el-button>
          <div class="dialog-footer-main">
            <el-button @click="dialogVisible = false">{{ t('admin.actions.cancel') }}</el-button>
            <el-button type="primary" @click="saveModel" :loading="saving">
              {{ isEditing ? t('admin.actions.save') : t('admin.actions.create') }}
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, reactive, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Plus, Edit, Delete, Connection } from '@element-plus/icons-vue'
import api from '@/utils/api'
import { formatLocaleDateTime, formatLocaleNumber } from '@/utils/localeFormat'

const { t, locale } = useI18n()

const loading = ref(false)
const saving = ref(false)
const testingConfig = ref(false)
const autoFilledName = ref('')
const models = ref([])
const dialogVisible = ref(false)
const isEditing = ref(false)
const editingId = ref(null)
const formRef = ref(null)

const defaultForm = () => ({
  model_id: '',
  display_name: '',
  base_url: '',
  api_key: '',
  context_limit: 128000,
  max_output_tokens: 32768,
  is_enabled: true,
  is_default: false,
  sort_order: 0,
})

const form = reactive(defaultForm())

const rules = computed(() => ({
  model_id: [{ required: true, message: t('admin.llmModels.validation.modelId'), trigger: 'blur' }],
  display_name: [{ required: true, message: t('admin.llmModels.validation.displayName'), trigger: 'blur' }],
  base_url: [{ required: true, message: t('admin.llmModels.validation.baseUrl'), trigger: 'blur' }],
  api_key: [{ required: true, message: t('admin.llmModels.validation.apiKey'), trigger: 'blur' }],
}))

// 加载模型列表
async function loadModels() {
  loading.value = true
  try {
    const res = await api.get('/api/admin/llm-models')
    models.value = (res.data.models || []).map(m => ({ ...m, _testing: false }))
  } catch (e) {
    ElMessage.error(t('admin.llmModels.loadFailed'))
  } finally {
    loading.value = false
  }
}

// 测试连通性
async function testModel(row) {
  row._testing = true
  try {
    const res = await api.post(`/api/admin/llm-models/${row.id}/test`)
    const { ok, latency_ms, error } = res.data
    if (ok) {
      ElMessage.success(t('admin.llmModels.testSucceeded', { model: row.model_id, latency: formatNumber(latency_ms) }))
    } else {
      ElMessage.warning(t('admin.llmModels.testFailed', { model: row.model_id, error }))
    }
    // 刷新列表以更新 last_test_* 字段
    await loadModels()
  } catch (e) {
    ElMessage.error(t('admin.llmModels.testRequestFailed'))
  } finally {
    row._testing = false
  }
}

// 弹窗内“测试连通”：直接用表单当前值探测，不依赖是否已保存（编辑时留空 Key 自动复用已保存密钥）
async function testDialogConfig() {
  const modelId = String(form.model_id || '').trim()
  if (!modelId) {
    ElMessage.warning(t('admin.llmModels.testNeedsModelId'))
    return
  }
  if (!String(form.base_url || '').trim()) {
    ElMessage.warning(t('admin.llmModels.testNeedsBaseUrl'))
    return
  }
  if (!isEditing.value && !form.api_key) {
    ElMessage.warning(t('admin.llmModels.testNeedsApiKey'))
    return
  }
  testingConfig.value = true
  try {
    const res = await api.post('/api/admin/llm-models/test-config', {
      model_id: modelId,
      base_url: String(form.base_url).trim(),
      api_key: form.api_key || '',
      id: isEditing.value ? editingId.value : null,
    })
    const { ok, latency_ms, error } = res.data
    if (ok) {
      ElMessage.success(t('admin.llmModels.testSucceeded', { model: modelId, latency: formatNumber(latency_ms) }))
    } else {
      ElMessage.warning(t('admin.llmModels.testFailed', { model: modelId, error }))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || t('admin.llmModels.testRequestFailed'))
  } finally {
    testingConfig.value = false
  }
}

// 模型 ID 录入后自动同步显示名称；若用户手动改过名称则不再覆盖
watch(() => form.model_id, (val) => {
  if (!val || isEditing.value) return
  if (!form.display_name || form.display_name === autoFilledName.value) {
    form.display_name = val
    autoFilledName.value = val
  }
})

// 打开新增弹窗
function openCreateDialog() {
  isEditing.value = false
  editingId.value = null
  autoFilledName.value = ''
  Object.assign(form, defaultForm())
  dialogVisible.value = true
}

// 打开编辑弹窗
function openEditDialog(row) {
  isEditing.value = true
  editingId.value = row.id
  Object.assign(form, {
    model_id: row.model_id,
    display_name: row.display_name,
    base_url: row.base_url || '',
    api_key: '',
    context_limit: row.context_limit,
    max_output_tokens: row.max_output_tokens,
    is_enabled: row.is_enabled,
    is_default: row.is_default,
    sort_order: row.sort_order,
  })
  dialogVisible.value = true
}

// 保存模型
async function saveModel() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  saving.value = true
  try {
    if (isEditing.value) {
      await api.put(`/api/admin/llm-models/${editingId.value}`, form)
      ElMessage.success(t('admin.llmModels.updated'))
    } else {
      await api.post('/api/admin/llm-models', form)
      ElMessage.success(t('admin.llmModels.created'))
    }
    dialogVisible.value = false
    await loadModels()
  } catch (e) {
    const msg = e.response?.data?.detail || t('admin.errors.operationFailed')
    ElMessage.error(msg)
  } finally {
    saving.value = false
  }
}

// 删除模型
async function deleteModel(row) {
  try {
    await api.delete(`/api/admin/llm-models/${row.id}`)
    ElMessage.success(t('admin.llmModels.deleted'))
    await loadModels()
  } catch (e) {
    ElMessage.error(t('admin.errors.deleteFailed'))
  }
}

// 格式化数字（加千分位）
function formatNumber(n) {
  if (!n) return '-'
  return formatLocaleNumber(n, locale.value)
}

// 格式化时间
function formatTime(iso) {
  if (!iso) return ''
  return formatLocaleDateTime(iso, locale.value, { year: undefined })
}

function testStatusTooltip(row) {
  if (row.last_test_ok) return t('admin.llmModels.latencyAvailable')
  return t('admin.llmModels.testError', {
    error: row.last_test_error || t('admin.status.unknown')
  })
}

onMounted(loadModels)
</script>

<style scoped>
.llm-models-page {
  padding: 20px;
}
.page-title {
  margin-bottom: 20px;
}
.page-title h2 {
  margin: 0 0 4px 0;
  font-size: 22px;
}
.page-title p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.status-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.status-ok {
  background-color: #67c23a;
}
.status-fail {
  background-color: #f56c6c;
}
.status-unknown {
  background-color: #dcdfe6;
}
.api-key-masked {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.test-time {
  font-size: 12px;
}
.text-muted {
  color: var(--el-text-color-placeholder);
}
.section-card {
  margin-bottom: 16px;
}
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}
.dialog-footer-main {
  display: flex;
}
.form-tip {
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.switch-tip {
  margin-left: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
