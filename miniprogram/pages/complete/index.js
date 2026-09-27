/**
 * ============================================================================
 * pages/complete/index.js — 行程生成完成页
 * ============================================================================
 * 这是生成完成后的"摘要预览页"，展示行程的关键信息
 * 用户可以从这里跳转到详细行程页或重新生成
 * ============================================================================
 */
const { getStorageItem } = require('../../utils/util');

// 循环色板：最多支持10天不同颜色
const DAY_COLORS = ['#06B6D4','#8B5CF6','#F97316','#22C55E','#EF4444','#EC4899','#14B8A6','#EAB308','#6366F1','#F43F5E'];

Page({
  data: {
    tripResult: null,        // 行程结果（从 Storage 读取）
    dayColors: DAY_COLORS,   // 天数标签颜色数组
    safeTop: 0,
  },

  onLoad() {
    const app = getApp();
    const result = getStorageItem('tripResult');  // 从本地存储读取生成结果
    this.setData({
      tripResult: result,
      dayColors: DAY_COLORS,
      safeTop: app.globalData.statusBarHeight,
    });
  },

  // 返回 → 切到首页 Tab
  onBack() {
    wx.switchTab({ url: '/pages/index/index' });  // switchTab: 跳转到 TabBar 页面
  },

  // 查看完整行程 → result 页面
  onViewDetail() {
    wx.navigateTo({ url: '/pages/result/index' });
  },

  // 重新生成 → 回到 generate 页面
  onRegenerate() {
    wx.redirectTo({ url: '/pages/generate/index' });  // redirectTo: 关闭当前页再跳转
  },
});
