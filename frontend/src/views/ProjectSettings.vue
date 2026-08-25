<template>
  <div class="project-settings-page">
    <div class="page-header">
      <div>
        <h1>{{ t('home.projectSettings.title') }}</h1>
        <p>{{ t('home.projectSettings.description') }}</p>
      </div>
      <el-button @click="router.push('/')">{{ t('home.projectSettings.backHome') }}</el-button>
    </div>

    <el-alert
      v-if="!canEdit"
      :title="t('home.projectSettings.readOnly')"
      type="info"
      :closable="false"
      show-icon
      class="permission-alert"
    />

    <el-card v-loading="loading" class="settings-card">
      <template #header>
        <div class="card-header">
          <div>
            <strong>{{ t('home.projectSettings.llm.title') }}</strong>
            <span>{{ t('home.projectSettings.llm.description') }}</span>
          </div>
          <el-button v-if="canEdit" type="primary" :icon="Plus" @click="openCreateDialog">
            {{ t('home.projectSettings.llm.add') }}
          </el-button>
        </div>
      </template>

      <el-empty v-if="!loading && models.length === 0" :description="t('home.projectSettings.llm.empty')" />
      <el-table v-else :data="models" stripe>
        <el-table-column prop="display_name" :label="t('home.projectSettings.llm.name')" min-width="160" />
        <el-table-column prop="model_id" :label="t('home.projectSettings.llm.modelId')" min-width="160" />
        <el-table-column prop="provider" :label="t('home.projectSettings.llm.provider')" width="120" />
        <el-table-column :label="t('home.projectSettings.status')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">
              {{ row.is_enabled ? t('home.projectSettings.enabled') : t('home.projectSettings.disabled') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('home.projectSettings.llm.default')" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="warning" size="small">{{ t('home.projectSettings.llm.default') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canEdit" :label="t('home.projectSettings.actions')" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" :icon="Connection" @click="testModel(row)" :loading="row._testing">
              {{ t('home.projectSettings.llm.test') }}
            </el-button>
            <el-button size="small" type="primary" :icon="Edit" @click="openEditDialog(row)">
              {{ t('home.projectSettings.edit') }}
            </el-button>
            <el-popconfirm :title="t('home.projectSettings.llm.deleteConfirm')" @confirm="deleteModel(row)">
              <template #reference>
                <el-button size="small" type="danger" :icon="Delete" />
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-loading="loading" class="settings-card">
      <template #header>
        <div class="card-header">
          <div>
            <strong>{{ t('home.projectSettings.search.title') }}</strong>
            <span>{{ t('home.projectSettings.search.description') }}</span>
          </div>
        </div>
      </template>
      <div class="search-settings">
        <div v-for="setting in searchSettings" :key="setting.key" class="search-setting">
          <div class="search-info">
            <div class="search-name">{{ setting.key === 'EXA_API_KEY' ? 'Exa' : 'Tavily' }}</div>
            <div class="search-key">{{ setting.key }}</div>
          </div>
          <div class="search-value">
            <template v-if="canEdit && editingSetting === setting.key">
              <el-input
                v-model="settingDraft"
                type="password"
                show-password
                :placeholder="t('home.projectSettings.search.keepSecret')"
                @keyup.enter="saveSetting(setting.key)"
              />
              <el-button type="primary" :loading="savingSetting" @click="saveSetting(setting.key)">{{ t('home.projectSettings.save') }}</el-button>
              <el-button @click="cancelSettingEdit">{{ t('home.projectSettings.cancel') }}</el-button>
            </template>
            <template v-else>
              <el-tag :type="setting.is_configured ? 'success' : 'info'" size="small">
                {{ setting.is_configured ? t('home.projectSettings.configured') : t('home.projectSettings.notConfigured') }}
              </el-tag>
              <span v-if="setting.is_configured" class="masked-value">{{ setting.value }}</span>
              <el-button v-if="canEdit" type="primary" link @click="startSettingEdit(setting)">{{ t('home.projectSettings.edit') }}</el-button>
            </template>
          </div>
        </div>
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEditing ? t('home.projectSettings.llm.edit') : t('home.projectSettings.llm.add')" width="560px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item :label="t('home.projectSettings.llm.modelId')" prop="model_id">
          <el-input v-model="form.model_id" :disabled="isEditing" />
        </el-form-item>
        <el-form-item :label="t('home.projectSettings.llm.name')" prop="display_name">
          <el-input v-model="form.display_name" />
        </el-form-item>
        <el-form-item label="Base URL" prop="base_url"><el-input v-model="form.base_url" /></el-form-item>
        <el-form-item label="API Key" :prop="isEditing ? '' : 'api_key'">
          <el-input v-model="form.api_key" type="password" show-password :placeholder="isEditing ? t('home.projectSettings.llm.keepApiKey') : ''" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="Context"><el-input-number v-model="form.context_limit" :min="1" style="width: 100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="Max output"><el-input-number v-model="form.max_output_tokens" :min="1" style="width: 100%" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item :label="t('home.projectSettings.llm.provider')"><el-input v-model="form.provider" /></el-form-item></el-col>
          <el-col :span="6"><el-form-item :label="t('home.projectSettings.enabled')"><el-switch v-model="form.is_enabled" /></el-form-item></el-col>
          <el-col :span="6"><el-form-item :label="t('home.projectSettings.llm.defaultModel')"><el-switch v-model="form.is_default" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('home.projectSettings.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveModel">{{ t('home.projectSettings.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Connection, Delete, Edit, Plus } from '@element-plus/icons-vue'
import api from '@/utils/api'

const router = useRouter()
const { t } = useI18n()
const loading = ref(false)
const saving = ref(false)
const savingSetting = ref(false)
const canEdit = ref(false)
const models = ref([])
const searchSettings = ref([])
const dialogVisible = ref(false)
const isEditing = ref(false)
const editingId = ref(null)
const formRef = ref(null)
const editingSetting = ref('')
const settingDraft = ref('')

const defaultForm = () => ({
  model_id: '', display_name: '', base_url: '', api_key: '', context_limit: 128000,
  max_output_tokens: 32768, provider: '', is_enabled: true, is_default: false, sort_order: 0
})
const form = reactive(defaultForm())
const rules = computed(() => ({
  model_id: [{ required: true, message: t('home.projectSettings.llm.required'), trigger: 'blur' }],
  display_name: [{ required: true, message: t('home.projectSettings.llm.required'), trigger: 'blur' }],
  base_url: [{ required: true, message: t('home.projectSettings.llm.required'), trigger: 'blur' }],
  api_key: [{ required: true, message: t('home.projectSettings.llm.required'), trigger: 'blur' }]
}))

async function loadConfig() {
  loading.value = true
  try {
    const response = await api.get('/api/project/config')
    canEdit.value = Boolean(response.data.can_edit)
    models.value = (response.data.models || []).map(model => ({ ...model, _testing: false }))
    searchSettings.value = response.data.search_settings || []
  } catch {
    ElMessage.error(t('home.projectSettings.loadFailed'))
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  isEditing.value = false
  editingId.value = null
  Object.assign(form, defaultForm())
  dialogVisible.value = true
}

function openEditDialog(row) {
  isEditing.value = true
  editingId.value = row.id
  Object.assign(form, {
    ...defaultForm(),
    model_id: row.model_id,
    display_name: row.display_name,
    base_url: row.base_url || '',
    context_limit: row.context_limit,
    max_output_tokens: row.max_output_tokens,
    provider: row.provider || '',
    is_enabled: row.is_enabled,
    is_default: row.is_default,
    sort_order: row.sort_order,
    api_key: ''
  })
  dialogVisible.value = true
}

async function saveModel() {
  try { await formRef.value?.validate() } catch { return }
  saving.value = true
  try {
    if (isEditing.value) await api.put(`/api/project/llm-models/${editingId.value}`, form)
    else await api.post('/api/project/llm-models', form)
    ElMessage.success(t('home.projectSettings.saved'))
    dialogVisible.value = false
    await loadConfig()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || t('home.projectSettings.saveFailed'))
  } finally { saving.value = false }
}

async function deleteModel(row) {
  try {
    await api.delete(`/api/project/llm-models/${row.id}`)
    ElMessage.success(t('home.projectSettings.deleted'))
    await loadConfig()
  } catch (error) { ElMessage.error(error.response?.data?.detail || t('home.projectSettings.saveFailed')) }
}

async function testModel(row) {
  row._testing = true
  try {
    const response = await api.post(`/api/project/llm-models/${row.id}/test`)
    ElMessage[response.data.ok ? 'success' : 'warning'](response.data.ok ? t('home.projectSettings.llm.testOk') : (response.data.error || t('home.projectSettings.llm.testFailed')))
    await loadConfig()
  } catch { ElMessage.error(t('home.projectSettings.llm.testFailed')) }
  finally { row._testing = false }
}

function startSettingEdit(setting) { editingSetting.value = setting.key; settingDraft.value = '' }
function cancelSettingEdit() { editingSetting.value = ''; settingDraft.value = '' }
async function saveSetting(key) {
  savingSetting.value = true
  try {
    const response = await api.put(`/api/project/config/settings/${key}`, { value: settingDraft.value })
    const index = searchSettings.value.findIndex(item => item.key === key)
    if (index >= 0 && response.data.setting) searchSettings.value[index] = response.data.setting
    ElMessage.success(t('home.projectSettings.saved'))
    cancelSettingEdit()
  } catch (error) { ElMessage.error(error.response?.data?.detail || t('home.projectSettings.saveFailed')) }
  finally { savingSetting.value = false }
}

onMounted(loadConfig)
</script>

<style scoped>
.project-settings-page { max-width: 1180px; margin: 0 auto; padding: 32px 24px 64px; color: var(--color-text); }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 20px; }
.page-header h1 { margin: 0 0 8px; font-size: 28px; }
.page-header p { margin: 0; color: var(--color-text-secondary); }
.permission-alert { margin-bottom: 16px; }
.settings-card { margin-bottom: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.card-header div { display: flex; flex-direction: column; gap: 4px; }
.card-header span { font-size: 13px; font-weight: 400; color: var(--el-text-color-secondary); }
.search-settings { display: flex; flex-direction: column; }
.search-setting { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 16px 0; border-bottom: 1px solid var(--el-border-color-lighter); }
.search-setting:last-child { border-bottom: 0; }
.search-name { font-weight: 600; }
.search-key { margin-top: 4px; color: var(--el-text-color-secondary); font: 12px monospace; }
.search-value { display: flex; align-items: center; gap: 8px; min-width: 280px; justify-content: flex-end; }
.masked-value { color: var(--el-text-color-secondary); font: 12px monospace; }
@media (max-width: 720px) { .project-settings-page { padding: 24px 12px 48px; } .page-header { flex-direction: column; } .search-setting { align-items: flex-start; flex-direction: column; } .search-value { min-width: 0; width: 100%; justify-content: flex-start; flex-wrap: wrap; } }
</style>
