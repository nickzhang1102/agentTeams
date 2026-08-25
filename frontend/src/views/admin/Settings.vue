<template>
  <div class="admin-settings">
    <div class="page-header">
      <h2>{{ t('admin.nav.settings') }}</h2>
      <p class="page-desc">{{ t('admin.settings.description') }}</p>
    </div>

    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>{{ t('admin.settings.list') }}</span>
          <el-button type="primary" :icon="Refresh" @click="loadData" size="small">{{ t('admin.actions.refresh') }}</el-button>
        </div>
      </template>

      <el-empty v-if="!loading && adminStore.settings.length === 0" :description="t('admin.settings.empty')" />

      <div v-else class="settings-list">
        <div v-for="item in adminStore.settings" :key="item.id || item.key" class="setting-item">
          <div class="setting-info">
            <div class="setting-key">{{ item.key }}</div>
            <div class="setting-desc" v-if="item.description">{{ item.description }}</div>
          </div>
          <div class="setting-value">
            <template v-if="editingKey === item.key">
              <el-input
                v-model="editingValue"
                :type="item.is_secret ? 'password' : 'text'"
                :show-password="item.is_secret"
                :placeholder="item.is_secret ? t('admin.settings.keepSecret') : ''"
                size="small"
                style="width: 260px"
                @keyup.enter="saveSetting(item.key)"
              />
              <el-button type="primary" size="small" @click="saveSetting(item.key)" :loading="saving">{{ t('admin.actions.save') }}</el-button>
              <el-button size="small" @click="cancelEdit">{{ t('admin.actions.cancel') }}</el-button>
            </template>
            <template v-else>
              <span class="value-text">
                {{ item.is_secret
                  ? (item.is_configured ? t('admin.settings.secretConfigured') : t('admin.settings.secretMissing'))
                  : item.value }}
              </span>
              <el-button type="primary" link size="small" @click="startEdit(item)">
                <el-icon><Edit /></el-icon>
                {{ t('admin.actions.edit') }}
              </el-button>
            </template>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Refresh, Edit } from '@element-plus/icons-vue'
import { useAdminStore } from '@/stores/admin'

const adminStore = useAdminStore()
const { t } = useI18n()

const loading = ref(false)
const saving = ref(false)
const editingKey = ref('')
const editingValue = ref('')

async function loadData() {
  loading.value = true
  try {
    await adminStore.fetchSettings()
  } finally {
    loading.value = false
  }
}

function startEdit(item) {
  editingKey.value = item.key
  editingValue.value = item.is_secret ? '' : item.value
}

function cancelEdit() {
  editingKey.value = ''
  editingValue.value = ''
}

async function saveSetting(key) {
  saving.value = true
  try {
    const result = await adminStore.updateSetting(key, editingValue.value)
    if (result.success) {
      ElMessage.success(t('admin.settings.updated'))
      cancelEdit()
    } else {
      ElMessage.error(result.error || t('admin.errors.updateFailed'))
    }
  } catch {
    ElMessage.error(t('admin.settings.updateFailed'))
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style lang="scss" scoped>
.admin-settings {
  max-width: 1000px;
}

.page-header {
  margin-bottom: 20px;

  h2 {
    margin: 0 0 8px;
    font-size: 20px;
    color: var(--el-text-color-primary);
  }

  .page-desc {
    margin: 0;
    color: var(--el-text-color-secondary);
    font-size: 14px;
  }
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  font-size: 15px;
}

.settings-list {
  display: flex;
  flex-direction: column;
}

.setting-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);

  &:last-child {
    border-bottom: none;
  }
}

.setting-info {
  flex: 1;
  min-width: 0;
}

.setting-key {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}

.setting-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.setting-value {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.value-text {
  font-size: 14px;
  color: var(--el-text-color-regular);
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}

@media (max-width: 768px) {
  .setting-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .setting-value {
    width: 100%;
    flex-wrap: wrap;

    .el-input {
      width: 100% !important;
    }
  }
}
</style>
