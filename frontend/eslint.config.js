import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'

export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'coverage/**', 'playwright-report/**', 'test-results/**']
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.{js,jsx,cjs,mjs,vue}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.jest
      }
    },
    rules: {
      'no-undef': 'error',
      'no-unused-vars': ['warn', { args: 'none', ignoreRestSiblings: true }],
      'vue/no-unused-vars': 'warn',
      'vue/multi-word-component-names': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
      // 现有代码存在大量格式化历史遗留。将这些规则设为 warn，
      // 既能让问题可见，又不会让首次接入 CI 门禁变得无法落地。
      'no-useless-assignment': 'warn',
      'no-useless-escape': 'warn',
      'no-irregular-whitespace': 'warn',
      'preserve-caught-error': 'warn',
      'vue/no-side-effects-in-computed-properties': 'warn'
    }
  }
]
