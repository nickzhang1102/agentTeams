export function catalogLabel(item) {
  return item?.label || item?.name || item?.key || ''
}
