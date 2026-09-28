/**
 * ============================================================================
 * pages/generate/index.js — AI生成中页面（核心转发 + 轮询逻辑）
 * ============================================================================
 * 这是连接前端和后端的桥梁页面，核心流程：
 *   1. 读取 create 页面保存的表单数据
 *   2. POST /api/v1/trips/generate → 获取 tripId
 *   3. 每 3 秒 GET /api/v1/trips/:id/status → 轮询进度
 *   4. 完成后存储结果 → 跳转 complete 页面
 *   5. 用户返回时 → DELETE cancel 取消任务
 * 
 * 设计模式：异步任务 + 轮询（适合长时间处理如 LLM 调用的场景）
 *   而不是 WebSocket 或 SSE（杀鸡不用牛刀）
 * ============================================================================
 */
var mockTips = require('../../utils/mock').mockTravelTips;          // 旅行小贴士
var getTravelTipsByCity = require('../../utils/mock').getTravelTipsByCity;  // 按城市筛选
var util = require('../../utils/util');
var api = require('../../utils/api');                                // API 调用模块

Page({
  data: {
    // 步骤指示器
    stepData: [
      { num: 1, label: '基本信息', status: 'completed', labelColor: '#22C55E' },
      { num: 2, label: '偏好设置', status: 'completed', labelColor: '#22C55E' },
      { num: 3, label: '生成行程', status: 'active', labelColor: '#06B6D4' },
    ],
    // 5个生成步骤，初始状态：第1步 loading，其余 waiting
    progressSteps: [
      { text: '分析你的偏好和需求', status: 'loading' },
      { text: '检索目的地景点和餐厅', status: 'waiting' },
      { text: '规划每日路线和时间', status: 'waiting' },
      { text: '计算预算和费用明细', status: 'waiting' },
      { text: '优化行程，确保体验最佳', status: 'waiting' },
    ],
    currentTip: '',            // 当前轮播的旅行小贴士
    // 模式三态：connecting=请求已发出等待响应, backend=已拿到 tripId 真实生成, failed=请求失败
    mode: 'connecting',
    diagnosis: '',             // 失败时的诊断信息（页面可见，便于长按复制反馈）
    timer: null,               // setInterval 定时器 ID（页面离开时清除）
    safeTop: 0,
  },

  onLoad: function() {
    var app = getApp();
    var form = util.getStorageItem('tripFormData') || {};  // 读取 create 保存的表单
    var dest = form.destination || '';
    
    // 按目的地筛选旅行小贴士（生成过程中轮播展示）
    var tips = getTravelTipsByCity(dest);
    var tipIdx = Math.floor(Math.random() * tips.length);
    this._tips = tips;

    this.setData({
      currentTip: tips[tipIdx].tip,
      safeTop: app.globalData.statusBarHeight,
    });

    console.log('[Generate] 表单:', JSON.stringify(form));
    
    if (form.destination) {
      this._callBackend(form);        // 有目的地 → 调后端真实生成
    } else {
      // 无数据 → 返回创建页
      wx.showToast({ title: '请先填写行程信息', icon: 'none', duration: 2000 });
      setTimeout(function() { wx.navigateBack(); }, 2000);
    }
  },

  // 页面关闭时取消后端任务 + 清理定时器
  onUnload: function() {
    if (this.data.timer) clearInterval(this.data.timer);
    if (this._tripId) {
      console.log('[Generate] 取消后端任务:', this._tripId);
      wx.cloud.callContainer({
        config: { env: 'cloud1-d2gzje1i7ba287acb' },
        path: '/api/v1/trips/' + this._tripId + '/cancel',
        method: 'DELETE',
        header: { 'X-WX-SERVICE': 'ai-travel-backend' },
        timeout: 3000,
      });
    }
  },

  // 用户点击返回按钮 → 确认弹窗
  onBack: function() {
    var that = this;
    wx.showModal({
      title: '确定返回吗？',
      content: '返回将取消当前生成，调整设置后可重新生成',
      success: function(res) {
        if (res.confirm) {
          if (that.data.timer) clearInterval(that.data.timer);
          wx.navigateBack();
        }
      },
    });
  },

  // ===== 后端调用 =====
  _callBackend: function(form) {
    var that = this;
    // 构建后端所需的 payload（与 Pydantic TripFormData Schema 对应）
    var payload = {
      origin: form.origin || '',
      destination: form.destination,
      startDate: form.startDate || '',
      endDate: form.endDate || '',
      adults: form.adults || 2,
      children: form.children || 0,
      style: form.style || 'deep',
      interests: form.interests || ['museum', 'food'],
      budget: form.budget || 'comfort',
      accommodation: form.accommodation || 'comfort',
      specialNeeds: form.specialNeeds || '',
    };

    console.log('[Generate] 提交后端:', payload.destination);
    console.log('[Generate] 是否已登录:', api.hasToken(), '目的地:', payload.destination);

    api.generateTrip(payload).then(function(res) {
      if (!res || !res.tripId) {
        throw { code: -2, msg: '后端未返回 tripId: ' + JSON.stringify(res) };
      }
      that._tripId = res.tripId;              // 保存 tripId（用于取消和轮询）
      that.setData({ mode: 'backend' });
      console.log('[Generate] 后端模式 tripId:', res.tripId);
      that._pollStatus(res.tripId);           // 开始轮询进度
    }).catch(function(err) {
      // API 调用失败 → 弹窗提示，不再静默降级
      console.error('[Generate] 后端调用失败:', 'code=' + err.code, 'via=' + err.via, JSON.stringify(err.msg));
      // 把可复制的诊断信息直接显示在页面上（体验版无需开调试也能拿到）
      that.setData({
        mode: 'failed',
        diagnosis: 'code=' + err.code + ' via=' + (err.via || '-') + ' msg=' + (typeof err.msg === 'string' ? err.msg : JSON.stringify(err.msg)),
      });
      wx.hideLoading();

      // 注意：err.msg 可能是对象（如 {detail:"登录已过期"}），必须先转字符串再截取，
      // 否则 .substring 会抛 TypeError，导致弹窗不显示、页面卡死在生成页
      var detail = typeof err.msg === 'string' ? err.msg : JSON.stringify(err.msg || err);
      var content = err.code === 401
        ? '登录已失效（401），自动重试仍失败。请删除小程序后重新进入'
        : '后端服务暂时不可用（' + err.code + '）：' + detail.substring(0, 100);

      wx.showModal({
        title: '生成失败',
        content: content,
        showCancel: false,
        confirmText: '返回修改',
        success: function() { wx.navigateBack(); }
      });
    });
  },

  /**
   * ================================================================
   * _pollStatus — 轮询后端生成进度（每 3 秒请求一次状态）
   * ================================================================
   * 后端 Agent 在各节点中更新内存字典 _generation_tasks[trip_id]
   * 前端通过 GET /:id/status 读取此字典获取最新进度
   * 
   * 最大轮询 60 次（3分钟），超时自动停止
   * 连续失败 10 次视为连接断开
   */
  _pollStatus: function(tripId) {
    var that = this;
    var retryCount = 0;
    var maxRetries = 60;                     // 最多 60 次 × 3 秒 = 3 分钟

    // stepMap: 后端 currentStep 关键词 → 前端步骤索引
    var stepMap = { '分析': 0, '检索': 1, '规划': 2, '计算预算': 3, '优化': 4 };

    this.data.timer = setInterval(function() {
      retryCount++;
      if (retryCount > maxRetries) {
        clearInterval(that.data.timer);
        wx.showModal({
          title: '生成超时', content: '行程生成超时（已等待3分钟），请返回重试',
          showCancel: false, confirmText: '返回',
          success: function() { wx.navigateBack(); }
        });
        return;
      }

      api.getTripStatus(tripId).then(function(status) {
        if (status.status === 'cancelled') {
          clearInterval(that.data.timer);
          return;
        }

        // 根据 currentStep 更新前端进度条
        var stepName = status.currentStep || '';
        var activeIdx = 0;
        for (var key in stepMap) { if (stepName.indexOf(key) >= 0) activeIdx = stepMap[key]; }
        if (status.progress >= 95) activeIdx = 4;

        var steps = that.data.progressSteps.map(function(s, i) {
          return { text: s.text, status: i < activeIdx ? 'completed' : (i === activeIdx ? 'loading' : 'waiting') };
        });
        that.setData({ progressSteps: steps });

        // 完成 → 存结果 → 跳转
        if (status.status === 'completed' && status.result) {
          clearInterval(that.data.timer);
          var done = that.data.progressSteps.map(function(s) { return { text: s.text, status: 'completed' }; });
          that.setData({ progressSteps: done });
          util.setStorageItem('tripResult', status.result);
          setTimeout(function() { wx.redirectTo({ url: '/pages/complete/index' }); }, 500);
        }

        // 失败 → 提示
        if (status.status === 'failed') {
          clearInterval(that.data.timer);
          wx.showModal({
            title: '生成失败', content: 'AI 行程生成过程中出错，请返回调整参数后重试',
            showCancel: false, confirmText: '返回修改',
            success: function() { wx.navigateBack(); }
          });
        }
      }).catch(function(err) {
        console.error('[Generate] 轮询失败(' + retryCount + '/' + maxRetries + '):', err);
        if (retryCount > 10) {
          clearInterval(that.data.timer);
          wx.showModal({
            title: '连接失败', content: '无法连接到后端服务，请检查网络后重试',
            showCancel: false, confirmText: '返回',
            success: function() { wx.navigateBack(); }
          });
        }
      });
    }, 3000);                              // 每 3 秒轮询一次
  },
});
