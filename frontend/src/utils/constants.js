/**
 * 共享常量 - 分类与状态映射
 *
 * 各组件基于此基础映射派生自己的样式（CSS class / Element Plus tag type）。
 */

export const CATEGORY_LABELS = {
  technology: '技术',
  business: '商业',
  medical: '医疗',
  investment: '投资',
  science: '科学',
  writing: '写作',
  legal: '法律',
  education: '教育',
  lifestyle: '生活',
  other: '其他',
}

export const STATUS_LABELS = {
  new: '新增',
  analyzing: '分析中',
  error: '有报错',
  completed: '已完成',
}

/** 获取分类中文标签，未知分类返回 '其他' */
export const getCategoryLabel = (category) => CATEGORY_LABELS[category] || '其他'

/** 获取状态中文标签，未知状态返回原值 */
export const getStatusLabel = (status) => STATUS_LABELS[status] || status
