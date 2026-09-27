// 逆地理编码云函数 — 经纬度 → 城市名
const cloud = require('wx-server-sdk');
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });

// 高德地图 REST API（免费配额：每日 5000 次）
// 注意：生产环境应通过环境变量读取 Key，不要硬编码
const AMAP_KEY = process.env.AMAP_KEY || '9610ffcf985af1994f3d84114f4df62a';

exports.main = async (event) => {
  const { latitude, longitude } = event;
  if (!latitude || !longitude) {
    return { code: -1, msg: '缺少经纬度参数' };
  }

  try {
    const result = await cloud.callFunction({
      name: 'httpRequest',
      data: {
        // 高德逆地理编码：location=经度,纬度（注意顺序！）
        url: `https://restapi.amap.com/v3/geocode/regeo?output=json&location=${longitude},${latitude}&key=${AMAP_KEY}&radius=1000`,
        method: 'GET',
      },
    });

    const data = result.result;
    // 高德 status="1" 表示成功（字符串类型！）
    if (data && data.status === '1' && data.regeocode) {
      const addr = data.regeocode.addressComponent;
      const city = (addr.city || '').replace('市', '') || addr.province || '';
      return {
        code: 0,
        city: city,
        province: addr.province || '',
        district: addr.district || '',
        fullAddress: data.regeocode.formatted_address || '',
      };
    } else {
      return { code: -1, msg: '逆地理编码失败', detail: data };
    }
  } catch (err) {
    // 如果 httpRequest 云函数不存在，直接用 HTTP 请求
    return await reverseByHttp(latitude, longitude);
  }
};

// 退路：直接用 Node.js http 模块请求
async function reverseByHttp(lat, lng) {
  const https = require('https');
  const url = `https://restapi.amap.com/v3/geocode/regeo?output=json&location=${lng},${lat}&key=${AMAP_KEY}&radius=1000`;

  return new Promise((resolve) => {
    https.get(url, (res) => {
      let body = '';
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        try {
          const data = JSON.parse(body);
          if (data.status === '1' && data.regeocode) {
            const addr = data.regeocode.addressComponent;
            const city = (addr.city || '').replace('市', '') || addr.province || '';
            resolve({
              code: 0,
              city,
              province: addr.province || '',
              district: addr.district || '',
              fullAddress: data.regeocode.formatted_address || '',
            });
          } else {
            resolve({ code: -1, msg: 'regeo failed', detail: data });
          }
        } catch (e) {
          resolve({ code: -1, msg: 'parse error' });
        }
      });
    }).on('error', () => {
      resolve({ code: -1, msg: 'network error' });
    });
  });
}
