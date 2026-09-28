/**
 * ============================================================================
 * app.js — 微信小程序入口文件
 * ============================================================================
 * App() 是小程序的"应用生命周期"入口，全局唯一，所有页面共享
 * 
 * 微信小程序加载流程：
 *   1. 用户打开小程序 → 微信客户端下载代码包
 *   2. 执行 app.js → App({ onLaunch }) → 触发 onLaunch 生命周期
 *   3. 渲染第一个页面（app.json pages 数组的第一项）
 *   4. 每个页面有自己的 Page({ onLoad, onShow, ... }) 生命周期
 * 
 * 面试考点：App vs Page 的区别？
 *   - App: 应用级，全局唯一，管理全局生命周期和 globalData
 *   - Page: 页面级，每个页面独立，管理页面生命周期和数据绑定
 *   - App 的 onLaunch 只执行一次，Page 的 onLoad 每次进入页面都执行
 * ============================================================================
 */
var api = require('./utils/api');              // API 调用模块（云托管 + 401 自动重登）

App({
  // ========================================================================
  // onLaunch: 应用启动生命周期（只执行一次）
  // ========================================================================
  onLaunch: function () {
    // ----- 初始化微信云开发 -----
    // wx.cloud: 微信云开发 SDK，集成云函数/云数据库/云存储/云托管
    // 判断基础库版本 >= 2.2.3（云开发的最低要求版本）
    if (!wx.cloud) {
      console.error('请使用 2.2.3 或以上的基础库以使用云能力');
    } else {
      wx.cloud.init({
        env: 'cloud1-d2gzje1i7ba287acb',   // 云开发环境 ID（在微信云开发控制台创建）
        traceUser: true,                     // 是否追踪用户访问（用于云开发后台统计）
      });
      // 注意：wx.cloud.init() 后，小程序就天然拥有登录态
      // 后续 wx.cloud.database() / wx.cloud.callContainer() 都会自动携带用户身份
    }

    // ----- 系统信息（安全区适配） -----
    // 微信小程序需要适配刘海屏等异形屏幕
    // getSystemInfoSync(): 同步获取系统信息（阻塞执行，适合启动时使用）
    const sysInfo = wx.getSystemInfoSync();
    // getMenuButtonBoundingClientRect(): 获取右上角胶囊按钮的位置
    // 用于计算自定义导航栏的高度偏移
    const menuButton = wx.getMenuButtonBoundingClientRect();

    // 保存常用系统参数到 globalData（全局共享数据）
    // this 在 App 的 onLaunch 中指向 App 实例本身
    this.globalData.statusBarHeight = sysInfo.statusBarHeight;   // 状态栏高度（刘海屏约44px）
    this.globalData.safeAreaBottom = sysInfo.safeArea            // 底部安全区高度
      ? (sysInfo.screenHeight - sysInfo.safeArea.bottom)          // Home Indicator 区域
      : 0;
    // 导航栏高度 = 状态栏 + 胶囊按钮高度 + 胶囊上下边距
    this.globalData.navBarHeight = sysInfo.statusBarHeight 
      + menuButton.height 
      + (menuButton.top - sysInfo.statusBarHeight) * 2;
    this.globalData.screenHeight = sysInfo.screenHeight;
    this.globalData.screenWidth = sysInfo.screenWidth;
    this.globalData.pixelRatio = sysInfo.pixelRatio;

    // ----- 微信用户登录 ----（获取 openid 作为用户唯一标识）
    this.wxLogin();

    // ----- 获取腾讯地图 Key ----（从后端动态拉取，不在前端硬编码）
    this.fetchMapKey();
  },

  /**
   * ========================================================================
   * wxLogin — 微信小程序登录获取 openid
   * ========================================================================
   * 登录流程（3步）：
   *   1. wx.login() → 获取临时 code（5分钟有效，只能用一次）
   *   2. POST /api/v1/auth/login { code } → 后端调微信 code2session → 返回 openid
   *   3. 缓存 openid 到本地 storage → 后续 API 请求在 header 中附带
   * 
   * 为什么先检查缓存？
   *   - wx.login() 每次调用都会生成新的 code，没必要重复登录
   *   - 优先读缓存，减少网络请求，提升启动速度
   * 
   * 面试考点：wx.login 的 code 为什么只能用一次？
   *   - 防重放攻击：如果 code 可以重复使用，截获者可以无限冒充用户
   *   - 微信后台 mark-as-used：jscode2session 成功后 code 立即失效
   */
  wxLogin: function () {
    var that = this;
    var cachedToken = wx.getStorageSync('user_token');
    var cachedOpenid = wx.getStorageSync('user_openid');
    if (cachedToken && cachedOpenid) {
      // 先填充缓存，让启动瞬间的请求不至于空 token
      that.globalData.token = cachedToken;
      that.globalData.openid = cachedOpenid;
      that.globalData.userId = wx.getStorageSync('user_id') || '';
      console.log('[Login] 已有缓存 token，仍继续刷新');
    }
    // 注意：这里不能 return！
    // JWT 有效期 7 天，缓存的 token 过期后若不重新 wx.login，所有请求都会 401。
    // 每次启动都刷新一次，成本极低（一次 wx.login + 一次后端请求）。

    // Step 1: 调微信登录接口获取临时 code
    wx.login({
      success: function (loginRes) {
        if (!loginRes.code) {
          console.warn('[Login] wx.login 未返回 code');
          return;
        }

        // Step 2: 调后端 /api/v1/auth/login 用 code 换 openid
        // api.request: 云托管内部调用，不经过公网（无需配置域名）
        api.request('/api/v1/auth/login', {
          method: 'POST',
          data: { code: loginRes.code },
          timeout: 10000,
        }).then(function (data) {
          if (data && data.token) {
              that.globalData.openid = data.openid;
              that.globalData.token = data.token;
              that.globalData.userId = data.user_id;
              wx.setStorageSync('user_openid', data.openid);
              wx.setStorageSync('user_token', data.token);
              wx.setStorageSync('user_id', data.user_id);
              console.log('[Login] 登录成功, user_id:', data.user_id);
              // 将用户信息存入 CloudBase users 集合
              var db = wx.cloud.database();
              db.collection('users').where({
                openid: data.openid
              }).count().then(function(countRes) {
                if (countRes.total === 0) {
                  db.collection('users').add({
                    data: {
                      user_id: data.user_id,
                      openid: data.openid,
                      nickname: data.nickname || '',
                      avatar_url: data.avatar_url || '',
                      created_at: db.serverDate(),
                      last_login: db.serverDate(),
                    }
                  });
                } else {
                  db.collection('users').where({
                    openid: data.openid
                  }).update({
                    data: { last_login: db.serverDate() }
                  });
                }
              });
          } else {
            console.warn('[Login] 后端未返回 token:', JSON.stringify(data));
          }
        }).catch(function (err) {
          console.warn('[Login] 登录失败，使用游客模式:', JSON.stringify(err));
          // 不阻塞应用：登录失败时后端 deps.py 会返回 "dev_user_001"
        });
      },
      fail: function (err) {
        console.warn('[Login] wx.login 失败:', err.errMsg);
      }
    });
  },

  /**
   * ========================================================================
   * fetchMapKey — 从后端获取高德地图 API Key
   * ========================================================================
   * 设计原因：API Key 是敏感信息，不应硬编码在前端
   * 后端从 .env 读取 → 通过 /api/v1/config/map-key 下发 → 前端使用
   * 如果后端不可达，降级使用本地硬编码的 Key（_fallbackMapKey）
   */
  fetchMapKey() {
    var that = this;
    // wx.request: 微信小程序的 HTTP 请求 API（类似浏览器的 fetch）
    // 注意：需要在微信后台配置 request 合法域名
    wx.request({
      url: that.globalData.apiBaseUrl + '/api/v1/config/map-key',
      method: 'GET',
      timeout: 5000,                          // 5秒超时（启动时不宜等待太久）
      success: function (res) {
        if (res.statusCode === 200 && res.data && res.data.amapKey) {
          that.globalData.amapKey = res.data.amapKey;
          console.log('[App] 地图Key已从后端获取');
        }
      },
      fail: function () {
        // 降级：后端不可达时使用本地硬编码的 Key
        console.log('[App] 使用本地Key:', that.globalData._fallbackMapKey);
        that.globalData.amapKey = that.globalData._fallbackMapKey;
      },
    });
  },

  /**
   * ========================================================================
   * globalData — 全局共享数据
   * ========================================================================
   * 所有页面通过 getApp().globalData.xxx 访问
   * 
   * 注意：globalData 中的数据修改后不会自动通知页面刷新
   * 需要页面在 onShow 中主动读取最新值
   * 
   * openid 说明：
   *   - 微信用户对此小程序的唯一标识
   *   - 不同小程序之间的 openid 不同（同一用户在不同小程序有不同 openid）
   *   - 是用户数据隔离的核心标识
   */
  globalData: {
    openid: '',                                                    // 微信用户唯一标识
    token: '',         // 新增：JWT Token
    userId: '',        // 新增：用户 ID
    _fallbackMapKey: '',                                             // 高德地图 Key（后备，需替换为实际 Key）
    amapKey: '',                                                   // 高德地图 Key（从后端获取）
    apiBaseUrl: 'https://ai-travel-backend-262776-10-1427844883.sh.run.tcloudbase.com', // 后端 API 地址
    statusBarHeight: 0,    // 状态栏高度
    safeAreaBottom: 0,     // 底部安全区高度
    navBarHeight: 0,       // 自定义导航栏总高度
    screenHeight: 0,       // 屏幕高度
    screenWidth: 0,        // 屏幕宽度
    pixelRatio: 1,         // 设备像素比
  },
});
