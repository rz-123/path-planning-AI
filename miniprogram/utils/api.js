/**
 * 后端 API 服务 — 云托管内部调用（无需域名）
 *
 * wx.cloud.callContainer 正确用法（微信官方文档）：
 *   1. config.env  → 环境 ID
 *   2. path        → 纯 API 路径（如 /api/v1/trips/generate）
 *   3. header['X-WX-SERVICE'] → 服务名称（如 ai-travel-backend）
 *
 *   不要把服务名拼在 path 里！不用 config.name！
 *
 * 关于公网域名降级（重要）：
 *   云托管默认域名（*.run.tcloudbase.com）**不允许**配置进小程序 request 合法域名
 *   （微信后台会提示"云托管域名仅用作测试使用，不可用在正式环境下"），
 *   因此体验版/正式版**不能**用 wx.request 走公网。正式环境唯一正确通道就是 callContainer。
 *   只有当你给云托管服务绑定了「已备案的自定义域名」并把它加进小程序合法域名后，
 *   才可以把下面的 ENABLE_PUBLIC_FALLBACK 改成 true 并同步修改 publicBase。
 */
var ENABLE_PUBLIC_FALLBACK = false;
var envId = 'cloud1-d2gzje1i7ba287acb';
var serviceName = 'ai-travel-backend';
var publicBase = 'https://ai-travel-backend-262776-10-1427844883.sh.run.tcloudbase.com';

// 取 token：globalData 优先，其次本地 storage（体验版首次启动时登录是异步的）
function getToken() {
  try {
    return getApp().globalData.token || wx.getStorageSync('user_token') || '';
  } catch (e) {
    return wx.getStorageSync('user_token') || '';
  }
}

function buildHeader() {
  return {
    'X-WX-SERVICE': serviceName,
    'Authorization': 'Bearer ' + getToken(),
    'content-type': 'application/json',
  };
}

// ===== 通道 1：云托管内网调用 =====
function callCloudRun(path, options) {
  return new Promise(function (resolve, reject) {
    wx.cloud.callContainer({
      config: { env: envId },
      path: path,                              // 纯 API 路径，不带服务名前缀
      method: options.method || 'GET',
      data: options.data || {},
      header: buildHeader(),
      timeout: options.timeout || 30000,
      success: function (res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject({ code: res.statusCode, msg: res.data, via: 'cloudrun' });
        }
      },
      fail: function (err) {
        reject({ code: -1, msg: err.errMsg || '网络请求失败', via: 'cloudrun' });
      },
    });
  });
}

// ===== 通道 2：公网域名（仅在绑定自定义域名后启用） =====
function publicRequest(path, options) {
  return new Promise(function (resolve, reject) {
    wx.request({
      url: publicBase + path,
      method: options.method || 'GET',
      data: options.data || {},
      header: buildHeader(),
      timeout: options.timeout || 30000,
      success: function (res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject({ code: res.statusCode, msg: res.data, via: 'public' });
        }
      },
      fail: function (err) {
        reject({ code: -1, msg: err.errMsg || '网络请求失败', via: 'public' });
      },
    });
  });
}

// 开发环境 localhost 用 wx.request，上线自动切 callContainer
function isDev() {
  try {
    var url = getApp().globalData.apiBaseUrl;
    return !url || url.indexOf('localhost') >= 0 || url.indexOf('127.0.0.1') >= 0;
  } catch (e) { return false; }
}

function devRequest(url, options) {
  return new Promise(function (resolve, reject) {
    var base = 'http://localhost:8080';
    wx.request({
      url: base + url,
      method: options.method || 'GET',
      data: options.data,
      header: buildHeader(),
      timeout: options.timeout || 30000,
      success: function (res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject({ code: res.statusCode, msg: res.data, via: 'dev' });
        }
      },
      fail: function (err) {
        reject({ code: -1, msg: err.errMsg, via: 'dev' });
      },
    });
  });
}

// ===== 登录：wx.login + 后端换 token =====
// token 有效期 7 天，过期后必须重新走一遍 wx.login 才能拿到新 token
function loginAndGetToken() {
  return new Promise(function (resolve, reject) {
    wx.login({
      success: function (loginRes) {
        if (!loginRes.code) {
          reject({ code: -3, msg: 'wx.login 未返回 code' });
          return;
        }
        // _retried: 登录接口本身不需要 token，跳过 401 重试分支，避免死循环
        apiCall('/api/v1/auth/login', {
          method: 'POST',
          data: { code: loginRes.code },
          timeout: 10000,
          _retried: true,
        }).then(function (data) {
          if (!data || !data.token) {
            reject({ code: -4, msg: '登录未返回 token: ' + JSON.stringify(data) });
            return;
          }
          try {
            var app = getApp();
            app.globalData.token = data.token;
            app.globalData.openid = data.openid;
            app.globalData.userId = data.user_id;
          } catch (e) { /* onLaunch 阶段 getApp() 可能不可用，storage 已兜底 */ }
          wx.setStorageSync('user_token', data.token);
          wx.setStorageSync('user_openid', data.openid);
          wx.setStorageSync('user_id', data.user_id);
          console.log('[API] token 已刷新, user_id:', data.user_id);
          resolve(data.token);
        }).catch(reject);
      },
      fail: function (err) {
        reject({ code: -5, msg: 'wx.login 失败: ' + err.errMsg });
      },
    });
  });
}

// ===== 统一入口：401 自动重新登录后重试 =====
function apiCall(path, options) {
  options = options || {};
  if (isDev()) return devRequest(path, options);

  return callCloudRun(path, options).catch(function (err) {
    // token 过期/失效 → 重新 wx.login 拿新 token 后重试一次（只重试一次，避免死循环）
    if (err.code === 401 && !options._retried) {
      console.warn('[API] 收到 401，重新登录后重试:', path);
      return loginAndGetToken().then(function () {
        return apiCall(path, {
          method: options.method,
          data: options.data,
          timeout: options.timeout,
          _retried: true,
        });
      }).catch(function (loginErr) {
        console.error('[API] 重新登录失败:', JSON.stringify(loginErr));
        throw err;                         // 抛出原始 401，交由页面提示
      });
    }

    // 默认不降级：云托管默认域名无法作为小程序合法域名，公网请求在体验版/正式版必然失败
    if (ENABLE_PUBLIC_FALLBACK && (err.code === -1 || err.code >= 500)) {
      console.warn('[API] 云托管调用失败，降级公网域名:', path, JSON.stringify(err));
      return publicRequest(path, options);
    }
    throw err;
  });
}

module.exports = {
  request: apiCall,
  loginAndGetToken: loginAndGetToken,
  // 供排查使用：当前是否拿到登录 token
  hasToken: function () { return !!getToken(); },
  generateTrip: function (formData) {
    return apiCall('/api/v1/trips/generate', { method: 'POST', data: formData, timeout: 30000 });
  },
  getTripStatus: function (tripId) {
    return apiCall('/api/v1/trips/' + tripId + '/status', { timeout: 10000 });
  },
  getTripResult: function (tripId) {
    return apiCall('/api/v1/trips/' + tripId, { timeout: 10000 });
  },
  checkHealth: function () {
    return apiCall('/health', { timeout: 5000 });
  },
};
