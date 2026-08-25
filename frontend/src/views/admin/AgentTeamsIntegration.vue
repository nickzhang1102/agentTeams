<template>
  <div class="agentteams-integration">
    <div class="page-header">
      <div>
        <h2>{{ t('admin.nav.agentteamsIntegration') }}</h2>
        <p class="page-desc">{{ t('admin.agentteams.description') }}</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="loadConfig">{{ t('admin.actions.refresh') }}</el-button>
    </div>

    <div class="status-grid">
      <el-card>
        <div class="metric-label">{{ t('admin.agentteams.integrationStatus') }}</div>
        <div class="metric-value">
          <el-tag :type="form.enabled ? 'success' : 'info'">
            {{ form.enabled ? t('admin.status.enabled') : t('admin.agentteams.stopped') }}
          </el-tag>
        </div>
      </el-card>
      <el-card>
        <div class="metric-label">{{ t('admin.agentteams.integrationKey') }}</div>
        <div class="metric-value">
          <span>{{ config?.has_integration_key ? config.integration_key_masked : t('admin.agentteams.notGenerated') }}</span>
        </div>
      </el-card>
    </div>

    <el-alert
      v-if="generatedKey"
      type="success"
      show-icon
      :closable="false"
      class="generated-alert"
    >
      <template #title>{{ t('admin.agentteams.newKeyGenerated') }}</template>
      <div class="generated-key-row">
        <el-input v-model="generatedKey" readonly />
        <el-button type="primary" :icon="CopyDocument" @click="copyGeneratedKey">{{ t('admin.actions.copy') }}</el-button>
      </div>
    </el-alert>

    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>{{ t('admin.agentteams.config') }}</span>
          <el-button type="primary" :icon="Key" :loading="generating" @click="generateKey">
            {{ t('admin.agentteams.generateKey') }}
          </el-button>
        </div>
      </template>

      <el-form label-width="150px" class="config-form">
        <el-form-item :label="t('admin.agentteams.enableIntegration')">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item :label="t('admin.agentteams.setKeyManually')">
          <el-input
            v-model="form.integration_key"
            type="password"
            show-password
            :placeholder="t('admin.agentteams.keyPlaceholder')"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveConfig">{{ t('admin.agentteams.saveConfig') }}</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { CopyDocument, Key, Refresh } from '@element-plus/icons-vue'
import { useAdminStore } from '@/stores/admin'
import { copyToClipboard } from '@/utils/clipboard'

const adminStore = useAdminStore()
const { t } = useI18n()
const loading = ref(false)
const saving = ref(false)
const generating = ref(false)
const generatedKey = ref('')

const form = reactive({
  enabled: true,
  integration_key: '',
})

const config = computed(() => adminStore.agentteamsIntegration)

function applyConfig(data) {
  form.enabled = Boolean(data.enabled)
  form.integration_key = ''
  generatedKey.value = data.generated_integration_key || ''
}

async function loadConfig() {
  loading.value = true
  try {
    const result = await adminStore.fetchAgentTeamsIntegration()
    if (result.success) {
      applyConfig(result.config)
    } else {
      ElMessage.error(result.error)
    }
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  saving.value = true
  try {
    // Keep the everyday form limited to the connection contract.  Token TTL
    // and service-account identity remain deployment defaults/advanced data;
    // omitting them prevents a normal save from resetting existing values.
    const result = await adminStore.updateAgentTeamsIntegration({
      enabled: form.enabled,
      integration_key: form.integration_key,
    })
    if (result.success) {
      applyConfig(result.config)
      ElMessage.success(t('admin.agentteams.configSaved'))
    } else {
      ElMessage.error(result.error)
    }
  } finally {
    saving.value = false
  }
}

async function generateKey() {
  generating.value = true
  try {
    const result = await adminStore.generateAgentTeamsIntegrationKey()
    if (result.success) {
      applyConfig(result.config)
      ElMessage.success(t('admin.agentteams.keyGenerated'))
    } else {
      ElMessage.error(result.error)
    }
  } finally {
    generating.value = false
  }
}

async function copyGeneratedKey() {
  if (!generatedKey.value) return
  const ok = await copyToClipboard(generatedKey.value)
  if (ok) {
    ElMessage.success(t('admin.agentteams.copied'))
  } else {
    ElMessage.error(t('admin.agentteams.copyFailed'))
  }
}

onMounted(loadConfig)
</script>

<style lang="scss" scoped>
.agentteams-integration {
  max-width: 1100px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
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

.status-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.metric-label {
  margin-bottom: 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.metric-value {
  min-height: 28px;
  display: flex;
  align-items: center;
  color: var(--el-text-color-primary);
  font-size: 18px;
  font-weight: 600;
}

.generated-alert {
  margin-bottom: 16px;
}

.generated-key-row {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.config-form {
  max-width: 720px;
}

.field-hint {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
}

@media (max-width: 900px) {
  .status-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .page-header,
  .generated-key-row {
    align-items: stretch;
    flex-direction: column;
  }

  .status-grid {
    grid-template-columns: 1fr;
  }
}
</style>
