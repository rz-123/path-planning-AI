/**
 * 常量定义
 */

// 状态颜色映射
const STATUS_COLORS = {
  completed: { bg: '#EFF6FF', text: '#3B82F6' },
  draft: { bg: '#FFF7ED', text: '#F97316' },
  loading: { bg: '#ECFEFF', text: '#06B6D4' },
};

// 出行方式图标映射
const TRANSPORT_ICONS = {
  plane: '\uf005',
  train: '\uf223',
  car: '\ueb39',
  bus: '\ueb13',
};

module.exports = {
  STATUS_COLORS,
  TRANSPORT_ICONS,
};
