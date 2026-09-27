/**
 * ============================================================================
 * util.js — 通用工具函数库
 * ============================================================================
 * 设计原则：
 *   1. 纯函数（无副作用）：相同输入保证相同输出
 *   2. 容错处理：try/catch 包裹存储操作（可能因用户拒绝授权等失败）
 *   3. CommonJS 导出：小程序使用 require() 语法加载
 * 
 * 面试考点：CommonJS vs ESModule？
 *   - CommonJS: require/module.exports，同步加载，Node.js 默认
 *   - ESModule: import/export，静态分析，浏览器原生支持
 *   - 微信小程序目前使用 CommonJS（因为基于 JavaScriptCore 引擎）
 * ============================================================================
 */

/**
 * 格式化日期为 yyyy.MM.dd（用于卡片展示，如 2025.06.01）
 * 
 * padStart(2, '0'): 保证月份和日期都是2位（'6' → '06'）
 * getMonth() 返回 0-11，所以需要 +1
 */
function formatDate(date) {
  if (!date) return '';
  const d = new Date(date);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}.${m}.${day}`;              // 模板字符串：ES6 的字符串拼接语法
}

/**
 * 格式化日期为 yyyy-MM-dd（ISO标准格式，用于后端交互）
 */
function formatDateISO(date) {
  if (!date) return '';
  const d = new Date(date);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * 格式化价格为 ¥xxx（带千分位分隔符）
 * toLocaleString('zh-CN'): 根据中文地区的数字格式自动加千分位
 * 例如：3860 → "¥3,860"
 */
function formatPrice(price) {
  return '¥' + Number(price).toLocaleString('zh-CN');
}

/**
 * 同步读取本地存储
 * 
 * wx.getStorageSync(key): 微信小程序的同步存储 API
 * 同步 vs 异步：同步简单但会阻塞主线程，适合读取小数据；异步不阻塞但需要回调
 * try/catch: 存储可能因用户拒绝存储权限等原因失败
 */
function getStorageItem(key) {
  try {
    return wx.getStorageSync(key);
  } catch (e) {
    return null;                           // 失败返回 null，调用方判空
  }
}

/**
 * 同步写入本地存储
 * 返回 true/false 表示操作成功/失败
 */
function setStorageItem(key, value) {
  try {
    wx.setStorageSync(key, value);
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * 同步删除本地存储项
 */
function removeStorageItem(key) {
  try {
    wx.removeStorageSync(key);
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * 计算两个日期之间的天数和晚数
 * 
 * 返回：{ days: N, nights: N-1 }
 * 例如：6月1日~6月3日 = 3天2晚
 * 
 * 日期格式兼容：支持 yyyy-MM-dd 和 yyyy.MM.dd（统一转为 / 分隔符）
 * 时间戳相减 → 毫秒数 → 除以每天的毫秒数 → 天数
 */
function calcDays(startDate, endDate) {
  if (!startDate || !endDate) return { days: 0, nights: 0 };
  const start = new Date(startDate);
  const end = new Date(endDate);
  const diffTime = end.getTime() - start.getTime();      // 毫秒级时间差
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)); // 向上取整
  return {
    days: diffDays + 1,                    // 含首尾的天数（如1日~3日=3天）
    nights: diffDays,                      // 住宿晚数
  };
}

// CommonJS 模块导出（小程序 require() 接收这个对象）
module.exports = {
  formatDate,
  formatDateISO,
  formatPrice,
  getStorageItem,
  setStorageItem,
  removeStorageItem,
  calcDays,
};
