/**
 * ============================================================================
 * pages/my/index.js — "我的"页面
 * ============================================================================
 * 功能：
 *   1. 用户信息卡片（头像 + ID）
 *   2. 统计面板（行程数 / 旅行天数 / 最爱目的地）
 *   3. 历史行程列表（从 CloudBase 云数据库加载）
 *   4. 空状态（无数据时展示引导文案）
 * 
 * 数据来源：wx.cloud.database().collection('trips')
 * 聚合计算：
 *   - totalTrips: 总行程数 = 列表长度
 *   - totalDays:   总天数 = 所有行程天数的累加和
 *   - favoriteDest: 最常目的地 = 遍历统计出现次数最多的
 * ============================================================================
 */
var { setStorageItem } = require('../../utils/util');

Page({
  data: {
    historyTrips: [],        // 历史行程列表
    safeTop: 0,
    safeBottom: 0,
    totalTrips: 0,           // 统计：总行程数
    totalDays: 0,            // 统计：总旅行天数
    favoriteDest: '',        // 统计：最爱目的地
  },

  onLoad: function() {
    var app = getApp();
    this.setData({
      safeTop: app.globalData.statusBarHeight,
      safeBottom: app.globalData.safeAreaBottom,
    });
  },

  onShow: function() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 1 });
    }
    this.loadTrips();                       // 每次显示刷新数据
  },

  /**
   * ================================================================
   * loadTrips — 从云数据库加载全部行程 + 计算统计面板数据
   * ================================================================
   * 
   * Array.reduce(): JavaScript 归并方法
   *   语法：array.reduce(callback, initialValue)
   *   callback(accumulator, currentValue) → 返回累积值
   *   例如：[1,2,3].reduce((sum, n) => sum + n, 0) → 6
   * 
   * destCount 统计算法：
   *   遍历 trips → 每个目的地计数+1 → 找出出现次数最多的
   *   { '成都': 2, '西安': 1 } → favoriteDest = '成都'
   */
  loadTrips: function() {
    var that = this;
    var db = wx.cloud.database();
    db.collection('trips')
      .orderBy('createdAt', 'desc')
      .limit(50)                           // 最多显示50条（分页未实现）
      .get()
      .then(function(res) {
        var trips = (res.data || []).map(function(item, i) {
          var startDate = item.startDate || '';
          var endDate = item.endDate || '';
          
          // 提取月份和日期（用于左侧日期方块展示）
          var month = '', day = '';
          if (startDate) {
            var parts = startDate.split(/[-.]/);
            if (parts.length >= 2) { month = parts[1] + '月'; day = parts[2]; }
          }
          
          // 标签：兴趣列表用逗号拼接
          var tags = (item.interests || []).join(', ');
          
          return {
            id: item._id,                          // 云数据库自动生成的唯一 ID
            title: item.title || item.destination + '之旅',
            destination: item.destination || '',
            startDate: startDate,
            endDate: endDate,
            days: item.days || 0,
            people: item.people || 0,
            tags: tags,
            budget: item.totalBudget || 0,
            month: month,
            day: day,
            statusText: '已完成',
            fullData: item.fullData || item,       // 完整数据（点击查看详情用）
          };
        });

        // ===== 统计计算 =====
        var totalTrips = trips.length;             // 行程总数
        // reduce: 累加所有行程的天数
        var totalDays = trips.reduce(function(s, t) { return s + (t.days || 0); }, 0);
        
        // 统计每个目的地出现次数 → 找出最多的
        var destCount = {};                        // { '成都': 2, '西安': 1 }
        trips.forEach(function(t) { 
          var d = t.destination; 
          if (d) destCount[d] = (destCount[d] || 0) + 1; 
        });
        var favoriteDest = '', maxCount = 0;
        for (var k in destCount) {                 // for...in 遍历对象键名
          if (destCount[k] > maxCount) { 
            maxCount = destCount[k]; 
            favoriteDest = k; 
          }
        }

        that.setData({
          historyTrips: trips,
          totalTrips: totalTrips,
          totalDays: totalDays,
          favoriteDest: favoriteDest,
        });
      })
      .catch(function(err) {
        console.error('[我的] 加载失败:', err);
        that.setData({ historyTrips: [], totalTrips: 0, totalDays: 0, favoriteDest: '' });
      });
  },

  /**
   * 点击行程 → 跳转详情页
   * 与首页的 onTapTrip 逻辑相同
   */
  onTapTrip: function(e) {
    var trip = e.currentTarget.dataset.trip;
    if (trip.fullData) {
      setStorageItem('tripResult', trip.fullData);
    } else {
      setStorageItem('tripResult', {
        title: trip.title, destination: trip.destination,
        startDate: trip.startDate, endDate: trip.endDate,
        days: trip.days, people: trip.people, totalBudget: trip.budget || 0,
        budgetPerPerson: trip.people ? Math.round((trip.budget || 0) / trip.people) : 0,
      });
    }
    wx.navigateTo({ url: '/pages/result/index' });
  },

  onNewPlan: function() {
    wx.navigateTo({ url: '/pages/create/index' });
  },
});
