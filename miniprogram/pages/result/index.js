const { getStorageItem } = require('../../utils/util');

// 天气 → 图标映射
const WEATHER_ICONS = {
  '晴': '☀️', '多云': '⛅', '阴': '☁️', '阵雨': '🌦️', '小雨': '🌧️',
  '中雨': '🌧️', '大雨': '⛈️', '暴雨': '⛈️', '雷阵雨': '⛈️',
  '雪': '🌨️', '小雪': '🌨️', '中雪': '❄️', '大雪': '❄️',
  '雾': '🌫️', '霾': '🌫️', '沙尘': '💨', '风': '💨',
};

function getWeather(dateStr, weatherData, dayIndex) {
  if (!weatherData || !weatherData.forecast) return null;
  var forecasts = weatherData.forecast || [];
  var cast = forecasts.find(function(f) { return f.date === dateStr; });
  if (!cast && dayIndex < forecasts.length) cast = forecasts[dayIndex];
  if (!cast) cast = forecasts.find(function(f) { return f.date === 'Day' + (dayIndex + 1); });
  if (cast) {
    var isHist = cast.isHistorical || cast.note;
    return {
      icon: isHist ? '📊' : (WEATHER_ICONS[cast.dayWeather] || '🌤️'),
      weather: isHist ? (cast.dayWeather || '往年') : cast.dayWeather,
      temp: cast.nightTemp && cast.dayTemp ? cast.nightTemp + '°~' + cast.dayTemp + '°' : '',
      dayTemp: cast.dayTemp || '',
      nightTemp: cast.nightTemp || '',
      isHistorical: !!isHist,
      note: isHist ? (cast.note || '往年同期平均') : '',
    };
  }
  return { icon: '🌤️', weather: '--', temp: '', isHistorical: false };
}

Page({
  data: {
    trip: null,
    currentTab: 0,
    selectedDay: 1,
    currentDayPlan: null,
    budgetCategories: [],
    dateWeather: [],
    safeTop: 0,
    safeBottom: 0,
    mapMarkers: [],
    mapPolylines: [],
    mapCenter: { latitude: 39.9042, longitude: 116.4074 },
  },

  onLoad() {
    var app = getApp();
    var trip = getStorageItem('tripResult');
    
    // 没有真实数据 → 提示并返回
    if (!trip) {
      wx.showToast({ title: '暂无行程数据，请先生成行程', icon: 'none', duration: 2000 });
      setTimeout(function() { wx.navigateBack(); }, 2000);
      return;
    }
    var dateWeather = (trip.dailyPlan || []).map(function(d, i) {
      var dStr = (trip.startDate || '').replace(/\./g, '-');
      var date = new Date(dStr);
      date.setDate(date.getDate() + i);
      var y = date.getFullYear();
      var m = String(date.getMonth() + 1).padStart(2, '0');
      var day = String(date.getDate()).padStart(2, '0');
      var fullDate = y + '-' + m + '-' + day;
      return { day: d.day, idx: i };
    });
    // 合并天气数据
    dateWeather = dateWeather.map(function(item) {
      return Object.assign({}, item, getWeather('', trip.weather, item.idx));
    });
    this.setData({
      trip: trip,
      currentDayPlan: trip.dailyPlan[0],
      dateWeather: dateWeather,
      safeTop: app.globalData.statusBarHeight,
      safeBottom: app.globalData.safeAreaBottom,
    });
    this.buildBudgetCategories(trip);
    this.buildMapData(trip.dailyPlan[0]);
  },

  onReady() {
    var that = this;
    setTimeout(function() { that.drawPieChart(); }, 500);
  },

  onBack() {
    wx.navigateBack({ delta: 1 });
  },

  onTabSwitch(e) {
    var tab = e.currentTarget.dataset.tab;
    this.setData({ currentTab: tab });
    if (tab === 1) {
      var that = this;
      setTimeout(function() { that.drawPieChart(); }, 300);
    }
  },

  onSwiperChange(e) {
    var current = e.detail.current;
    this.setData({ currentTab: current });
    if (current === 1) {
      var that = this;
      setTimeout(function() { that.drawPieChart(); }, 300);
    }
  },

  onSelectDay(e) {
    var day = e.currentTarget.dataset.day;
    var plan = this.data.trip.dailyPlan.find(function(d) { return d.day === day; });
    this.setData({ selectedDay: day, currentDayPlan: plan || null });
    this.buildMapData(plan);
  },

  drawPieChart() {
    var query = wx.createSelectorQuery();
    query.select('#budgetPie').fields({ node: true, size: true }).exec(function(res) {
      if (!res[0] || !res[0].node) { this.drawPieChartLegacy(); return; }
      var canvas = res[0].node;
      var ctx = canvas.getContext('2d');
      var dpr = wx.getSystemInfoSync().pixelRatio;
      canvas.width = res[0].width * dpr;
      canvas.height = res[0].height * dpr;
      ctx.scale(dpr, dpr);
      this.renderPie(ctx, res[0].width, res[0].height);
    }.bind(this));
  },

  drawPieChartLegacy() {
    var ctx = wx.createCanvasContext('budgetPie', this);
    this.renderPie(ctx, 120, 120);
    ctx.draw();
  },

  renderPie(ctx, w, h) {
    if (!this.data.trip || !this.data.trip.budgetPieData) return;
    var data = this.data.trip.budgetPieData;
    var cx = w / 2, cy = h / 2;
    var outerR = Math.min(w, h) / 2 - 4;
    var innerR = outerR * 0.55;
    var total = data.reduce(function(s, i) { return s + i.value; }, 0);
    ctx.clearRect(0, 0, w, h);
    var startAngle = -Math.PI / 2;
    data.forEach(function(item) {
      var sweep = (item.value / total) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(cx + innerR * Math.cos(startAngle), cy + innerR * Math.sin(startAngle));
      ctx.arc(cx, cy, outerR, startAngle, startAngle + sweep);
      ctx.arc(cx, cy, innerR, startAngle + sweep, startAngle, true);
      ctx.closePath();
      ctx.fillStyle = item.color;
      ctx.fill();
      startAngle += sweep;
    });
    ctx.beginPath();
    ctx.arc(cx, cy, innerR - 2, 0, Math.PI * 2);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
  },

  buildBudgetCategories(trip) {
    if (!trip || !trip.budgetDetail) return;
    var bd = trip.budgetDetail;
    var cats = [
      { key: 'accommodation', title: '住宿费用', icon: '\ueb39', color: '#3B82F6', total: bd.accommodation.total, items: bd.accommodation.items, tips: bd.accommodation.tips, expanded: false },
      { key: 'food', title: '餐饮费用', icon: '\uf044', color: '#22C55E', total: bd.food.total, items: bd.food.items, tips: bd.food.tips, expanded: false },
      { key: 'transport', title: '交通费用', icon: '\ueb13', color: '#F59E0B', total: bd.transport.total, items: bd.transport.items, tips: null, expanded: false },
      { key: 'tickets', title: '门票及其他', icon: '\uf20d', color: '#EF4444', total: bd.tickets.total, items: bd.tickets.items, tips: bd.tickets.discountNote, expanded: false },
    ];
    this.setData({ budgetCategories: cats });
  },

  onToggleCategory(e) {
    var key = e.currentTarget.dataset.key;
    var cats = this.data.budgetCategories.map(function(c) {
      if (c.key === key) c.expanded = !c.expanded;
      return c;
    });
    this.setData({ budgetCategories: cats });
  },

  onRegenerate() {
    wx.navigateTo({ url: '/pages/generate/index' });
  },

  /**
   * buildMapData — 从 dailyPlan 提取坐标构建地图 markers 和 polyline
   *
   * 数据来源：_fix_coordinates() 通过高德地理编码为每个行程点填充的 latitude/longitude
   * 无坐标的地点（如"酒店午休"、"返程晚餐"）会被跳过
   *
   * 面试考点：微信 map 组件的 markers 和 polyline 的区别？
   * - markers: 地图上的标记点，每个点有 id/latitude/longitude/iconPath/callout
   * - polyline: 地图上的折线，连接多个坐标点形成路线
   * - 两者组合实现"景点路线"可视化
   */
  buildMapData(dayPlan) {
    if (!dayPlan || !dayPlan.periods) {
      this.setData({ mapMarkers: [], mapPolylines: [], mapCenter: { latitude: 39.9042, longitude: 116.4074 } });
      return;
    }

    var markers = [];
    var points = [];
    var markerColors = ['#EF4444', '#F59E0B', '#3B82F6', '#22C55E', '#8B5CF6', '#EC4899', '#06B6D4', '#F97316'];

    dayPlan.periods.forEach(function(period) {
      if (!period.items) return;
      period.items.forEach(function(item) {
        var lat = item.latitude;
        var lng = item.longitude;
        // 跳过无坐标或坐标为 0 的地点（非实体地点）
        if (lat == null || lng == null || (lat === 0 && lng === 0)) return;

        var idx = markers.length;
        markers.push({
          id: idx,
          latitude: lat,
          longitude: lng,
          title: item.name,
          width: 30,
          height: 30,
          callout: {
            content: (idx + 1) + '. ' + item.name,
            color: '#1F2937',
            fontSize: 13,
            borderRadius: 8,
            bgColor: '#FFFFFF',
            padding: 10,
            display: 'ALWAYS',
          },
          label: {
            content: String(idx + 1),
            color: '#FFFFFF',
            fontSize: 14,
            x: 15,
            y: 15,
            anchorX: 0,
            anchorY: 0,
            borderRadius: 12,
            bgColor: '#3B82F6',
            padding: 4,
          },
        });
        points.push({ latitude: lat, longitude: lng });
      });
    });

    // 默认中心：北京或第一个 marker 的坐标
    var center = markers.length > 0
      ? { latitude: markers[0].latitude, longitude: markers[0].longitude }
      : { latitude: 39.9042, longitude: 116.4074 };

    this.setData({
      mapMarkers: markers,
      mapPolylines: markers.length > 1 ? [{
        points: points,
        color: '#3B82F6',
        width: 4,
        borderColor: '#FFFFFF',
        borderWidth: 2,
        arrowLine: true,
      }] : [],
      mapCenter: center,
    });
  },

  /**
   * onMapMarkerTap — 点击地图标记点 → 跳转腾讯地图小程序查看详情
   *
   * 用户点击标记后直接跳腾讯地图小程序，查看该景点的详细信息（位置/评价/周边等）
   * 如果腾讯地图未安装，降级到微信内置地图
   */
  onMapMarkerTap(e) {
    var markerId = e.detail.markerId;
    var marker = this.data.mapMarkers[markerId];
    if (!marker) return;

    var that = this;
    // 跳转腾讯地图小程序，展示该地点详情
    wx.navigateToMiniProgram({
      appId: 'wx7643d5f831302ab0',                     // 腾讯地图小程序 AppId
      path: 'modules/poi/pages/index/index?keyword=' + encodeURIComponent(marker.title) +
            '&center=' + marker.latitude + ',' + marker.longitude,
      fail: function() {
        // 降级：没装腾讯地图时用微信内置地图
        wx.showToast({ title: '腾讯地图未安装，使用微信地图', icon: 'none', duration: 1500 });
        wx.openLocation({
          latitude: marker.latitude,
          longitude: marker.longitude,
          name: marker.title,
          address: marker.title,
          scale: 16,
        });
      },
    });
  },

  onSave() {
    var trip = this.data.trip;
    if (!trip) return;
    wx.showLoading({ title: '保存中...' });
    
    var db = wx.cloud.database();
    db.collection('trips').add({
      data: {
        title: trip.title || '',
        destination: trip.destination || '',
        startDate: trip.startDate || '',
        endDate: trip.endDate || '',
        days: trip.days || 0,
        nights: trip.nights || 0,
        people: trip.people || 0,
        adults: trip.adults || 0,
        children: trip.children || 0,
        style: trip.style || '',
        interests: trip.interests || [],
        totalBudget: trip.totalBudget || 0,
        budgetPerPerson: trip.budgetPerPerson || 0,
        budgetLevel: trip.budgetLevel || '',
        budgetDetail: trip.budgetDetail || {},
        budgetPieData: trip.budgetPieData || [],
        dailyPlan: trip.dailyPlan || [],
        weather: trip.weather || {},
        saveTips: trip.saveTips || [],
        fullData: trip,  // 完整原始数据
        createdAt: db.serverDate(),
      },
      success: function() {
        wx.hideLoading();
        wx.showToast({ title: '行程已保存到云数据库', icon: 'success' });
      },
      fail: function(err) {
        wx.hideLoading();
        console.error('保存失败:', err);
        wx.showToast({ title: '保存失败，请重试', icon: 'none' });
      },
    });
  },
});
