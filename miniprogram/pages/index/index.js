/**
 * ============================================================================
 * pages/index/index.js — 首页逻辑
 * ============================================================================
 * Page() 生命周期执行顺序：
 *   1. onLoad()     — 页面首次加载时触发，适合初始化数据
 *   2. onShow()     — 页面显示/切前台时触发，适合刷新数据
 *   3. onReady()    — 页面首次渲染完成时触发，适合操作DOM
 *   4. onHide()     — 页面隐藏时触发
 *   5. onUnload()   — 页面卸载时触发
 * 
 * 首页核心功能：
 *   - 显示热门目的地卡片（静态数据）
 *   - 从 CloudBase 加载用户的最近 3 条行程
 *   - 空状态展示（首次使用/无数据时）
 *   - 点击行程跳转详情页
 * ============================================================================
 */

// require(): CommonJS 模块导入
// ../../utils/mock: 从当前文件向上两级目录（pages/index → pages → miniprogram根）
// 然后进入 utils/mock
var mockHotDests = require('../../utils/mock').mockHotDestinations;

/**
 * Page({}): 注册页面
 * data 对象中的所有属性会自动绑定到 WXML 模板中
 * 
 * 面试考点：小程序 data vs Vue data vs React state？
 *   - 小程序: Page({ data: {} })，通过 this.setData() 更新（类似 React setState）
 *   - Vue:     data() 返回响应式对象，直接赋值触发更新
 *   - React:   useState / this.state，通过 setState 更新
 *   - 小程序 setData 是异步的（类似 React），但数据量大时有性能问题
 */
Page({
  // ===== 页面数据（WXML 模板通过 {{变量名}} 绑定） =====
  data: {
    hotDests: [],          // 热门目的地列表
    recentTrips: [],       // 用户最近行程（从 CloudBase 加载）
    userInfo: null,        // 用户信息（预留）
    loading: true,         // 加载状态（控制 loading 动画）
    safeTop: 0,            // 顶部安全区高度（状态栏）
    safeBottom: 0,         // 底部安全区高度（Home Indicator）
  },

  /**
   * onLoad — 页面首次加载
   * 只执行一次，适合初始化不常变化的数据
   * 
   * getApp(): 获取全局 App 实例，访问 app.js 中的 globalData
   */
  onLoad: function() {
    var app = getApp();                    // 获取全局 App 实例
    this.setData({
      hotDests: mockHotDests,              // 热门目的地（静态数据，只需加载一次）
      safeTop: app.globalData.statusBarHeight,
      safeBottom: app.globalData.safeAreaBottom,
    });
  },

  /**
   * onShow — 页面每次显示时触发
   * 与 onLoad 的区别：onShow 在"从其他页面返回"时也会触发
   * 
   * 为什么在 onShow 中刷新行程？
   *   - 用户可能在 create 页面生成了新行程 → 返回首页需要看到更新
   *   - onShow 保证每次看到首页都是最新数据
   * 
   * getTabBar(): 获取自定义 TabBar 实例（如果使用自定义 TabBar）
   * 由于现在改为原生 TabBar，这行代码实际无效，但保留无妨
   */
  onShow: function() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 0 });
    }
    this.loadRecentTrips();                // 每次显示都刷新行程列表
  },

  /**
   * ============================================================
   * loadRecentTrips — 从 CloudBase 云数据库加载用户最近行程
   * ============================================================
   * 
   * wx.cloud.database()：获取云数据库实例
   * collection('trips')：选择 trips 集合（类似 SQL 的 table）
   * orderBy('createdAt', 'desc')：按创建时间倒序（最新的在前）
   * limit(3)：只取前 3 条（首页不需要全部展示）
   * get()：执行查询（返回 Promise）
   * 
   * 面试考点：云数据库查询和 SQL 的对应关系？
   *   - collection('trips')     = FROM trips
   *   - orderBy('createdAt','desc') = ORDER BY createdAt DESC
   *   - limit(3)                = LIMIT 3
   *   - .get()                  = SELECT *（NoSQL 默认返回全部字段）
   * 
   * map()：数组转换方法，对每个元素应用函数并返回新数组
   * item._id：云数据库自动生成的文档 ID
   * item.fullData：保存时存储的完整行程数据（TripResult JSON）
   */
  loadRecentTrips: function() {
    var that = this;                       // 保存 this 引用（回调函数中 this 指向不同）
    that.setData({ loading: true });       // 显示加载状态
    
    var db = wx.cloud.database();          // 获取云数据库实例
    db.collection('trips')                 // 选择 trips 集合
      .orderBy('createdAt', 'desc')        // 按创建时间倒序（最新在前）
      .limit(3)                            // 只取前3条
      .get()                               // 执行查询 → Promise
      .then(function(res) {                // 查询成功
        // map(): 将云数据库的文档格式转为前端需要的格式
        var trips = (res.data || []).map(function(item) {
          var startDate = item.startDate || '';
          var endDate = item.endDate || '';
          
          // 从日期中提取月份和日期（用于展示）
          var month = '', day = '';
          if (startDate) {
            var parts = startDate.split(/[-.]/);   // 正则拆分：- 或 . 两种分隔符
            if (parts.length >= 2) { month = parts[1]; day = parts[2]; }
          }
          
          return {
            id: item._id,                          // 云数据库文档 ID
            title: item.title || (item.destination || '') + '之旅',  // 标题兜底
            destination: item.destination || '',
            startDate: startDate.replace(/\./g, '-'),  // 统一分隔符
            endDate: endDate.replace(/\./g, '-'),
            days: item.days || 0,
            nights: item.nights || 0,
            people: item.people || 0,
            budget: item.totalBudget || 0,
            month: month,
            day: day,
            fullData: item.fullData || item,       // 完整行程数据（用于跳转详情页）
          };
        });
        that.setData({ recentTrips: trips, loading: false });
      })
      .catch(function(err) {                       // 查询失败
        console.log('[首页] 加载行程失败:', err);
        that.setData({ recentTrips: [], loading: false });  // 失败不影响页面展示
      });
  },

  /**
   * 点击"开始规划"按钮 → 跳转到创建页面
   * 
   * wx.navigateTo: 保留当前页面，跳转到新页面（可返回）
   * wx.redirectTo: 关闭当前页面，跳转到新页面（不可返回）
   * wx.switchTab:   跳转到 TabBar 页面（关闭其他非 TabBar 页面）
   */
  onStartPlan: function() {
    wx.navigateTo({ url: '/pages/create/index' });
  },

  /**
   * 点击行程卡片 → 跳转详情页
   * 
   * e.currentTarget.dataset.trip: 从 WXML 的 data-trip="{{item}}" 获取数据
   * dataset: WXML 中所有 data-* 属性的集合，自动做驼峰转换（data-trip-name → tripName）
   */
  onTapTrip: function(e) {
    var trip = e.currentTarget.dataset.trip;  // 获取传入的行程数据
    var util = require('../../utils/util');
    // 将行程数据写入本地存储 → result 页面读取
    if (trip.fullData) {
      util.setStorageItem('tripResult', trip.fullData);
    } else {
      // 只有摘要没有完整数据时，构造一个最小结果
      util.setStorageItem('tripResult', {
        title: trip.title, destination: trip.destination,
        startDate: trip.startDate, endDate: trip.endDate,
        days: trip.days, people: trip.people, totalBudget: trip.budget,
        budgetPerPerson: trip.people ? Math.round(trip.budget / trip.people) : 0,
      });
    }
    wx.navigateTo({ url: '/pages/result/index' });
  },

  /**
   * 点击热门目的地 → 提示暂未开发
   * 后续可扩展为：点击热门目的地直接预填到创建表单
   */
  onTapDest: function() {
    wx.showToast({ title: '暂未开发，请点击开始规划', icon: 'none', duration: 2000 });
  },

  /**
   * 点击"查看全部" → 切换到"我的"Tab 页面
   */
  onViewAll: function() {
    wx.switchTab({ url: '/pages/my/index' });
  },
});
