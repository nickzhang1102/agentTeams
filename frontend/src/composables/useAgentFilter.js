/**
 * Agent 筛选共享逻辑
 *
 * 将 Tab → is_system 映射、搜索、分类筛选等抽成 composable，
 * 供 AgentsPage.vue 复用。
 */
import { ref, computed } from 'vue'

/**
 * @param {Object} options
 * @param {Function} options.fetchFn - 列表加载函数，接收 { page, search, is_system, category, ... }
 * @param {number} [options.defaultPerPage=12] - 每页条数
 */
export function useAgentFilter({ fetchFn, defaultPerPage = 500 }) {
  const activeTab = ref('all')
  const searchText = ref('')
  const currentPage = ref(1)

  /** 从 activeTab 推导筛选参数 */
  const isSystemParam = computed(() => {
    if (activeTab.value === 'system') return 'true'
    if (activeTab.value === 'custom') return 'false'
    return undefined
  })

  /** 从 activeTab 推导 category 参数（非 all/system/custom 时视为 category） */
  const categoryParam = computed(() => {
    if (['all', 'system', 'custom'].includes(activeTab.value)) return undefined
    return activeTab.value
  })

  /** 构建请求参数 */
  function buildParams(page = 1, append = false) {
    const params = { page, perPage: defaultPerPage }
    if (searchText.value) params.search = searchText.value
    // category 优先于 is_system
    if (categoryParam.value) {
      params.category = categoryParam.value
    } else if (isSystemParam.value) {
      params.is_system = isSystemParam.value
    }
    if (append) params.append = true
    return params
  }

  /** 首次加载 / 筛选变化 */
  function handleFilterChange(page = 1) {
    currentPage.value = page
    return fetchFn(buildParams(page))
  }

  /** 翻页 */
  function handlePageChange(page) {
    currentPage.value = page
    return fetchFn(buildParams(page))
  }

  /** 加载更多（移动端无限滚动） */
  function loadMore() {
    currentPage.value++
    return fetchFn(buildParams(currentPage.value, true))
  }

  return {
    activeTab,
    searchText,
    currentPage,
    isSystemParam,
    categoryParam,
    handleFilterChange,
    handlePageChange,
    loadMore,
  }
}
