/**
 * 后端 API 服务 — 云托管内部调用（无需域名）
 *
 * wx.cloud.callContainer 正确用法（微信官方文档）：
 *   1. config.env  → 环境 ID
 *   2. path        → 纯 API 路径（如 /api/v1/trips/generate）
 *   3. header['X-WX-SERVICE'] → 服务名称（如 ai-travel-backend）
 *
 *   不要把服务名拼在 path 里！不用 config.name！
 */
var envId = 'cloud1-d2gzje1i7ba287acb';

function callCloudRun(path, options) {
  return new Promise(function(resolve, reject) {

    wx.cloud.callContainer({
      config: { env: envId },
      path: path,                              // 纯 API 路径，不带服务名前缀
      method: options.method || 'GET',
      data: options.data || {},
      header: {
      'X-WX-SERVICE': 'ai-travel-backend',
      'Authorization': 'Bearer ' + (function() {
      try { return getApp().globalData.token || wx.getStorageSync('user_token') || ''; } catch(e) { return ''; }
      })(),
      'content-type': 'application/json',
      },
      timeout: options.timeout || 30000,
      success: function(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject({ code: res.statusCode, msg: res.data });
        }
      },
      fail: function(err) {
        reject({ code: -1, msg: err.errMsg || '网络请求失败' });
      },
    });
  });
}

// 开发环境 localhost 用 wx.request，上线自动切 callContainer
function isDev() {
  try {
    var url = getApp().globalData.apiBaseUrl;
    return !url || url.indexOf('localhost') >= 0 || url.indexOf('127.0.0.1') >= 0;
  } catch(e) { return false; }
}

function devRequest(url, options) {
  return new Promise(function(resolve, reject) {
    var base = 'http://localhost:8080';
    wx.request({
      url: base + url,
      method: options.method || 'GET',
      data: options.data,
      header: {
      'content-type': 'application/json',
      'Authorization': 'Bearer ' + (wx.getStorageSync('user_token') || ''),
      },
      timeout: options.timeout || 30000,
      success: function(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject({ code: res.statusCode, msg: res.data });
        }
      },
      fail: function(err) {
        reject({ code: -1, msg: err.errMsg });
      },
    });
  });
}

function apiCall(path, options) {
  if (isDev()) return devRequest(path, options);
  return callCloudRun(path, options);
}

module.exports = {
  generateTrip: function(formData) {
    return apiCall('/api/v1/trips/generate', { method: 'POST', data: formData, timeout: 30000 });
  },
  getTripStatus: function(tripId) {
    return apiCall('/api/v1/trips/' + tripId + '/status', { timeout: 10000 });
  },
  getTripResult: function(tripId) {
    return apiCall('/api/v1/trips/' + tripId, { timeout: 10000 });
  },
  checkHealth: function() {
    return apiCall('/health', { timeout: 5000 });
  },
};
