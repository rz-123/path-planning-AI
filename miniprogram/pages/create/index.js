/**
 * ============================================================================
 * pages/create/index.js — 创建行程（2步表单）
 * ============================================================================
 * 页面交互流程：
 *   Step 1（基本信息）: 起始地 + 目的地 + 日期 + 人数
 *   Step 2（偏好设置）: 风格 + 兴趣 + 预算 + 住宿 + 特殊需求
 * 
 * 数据流转：
 *   填写 → 存 Storage(tripFormData) → generate 页面读取 → POST /api/v1/trips/generate
 * 
 * 核心技术点：
 *   - Swiper 组件实现步骤切换（左右滑动）
 *   - 城市选择器弹窗（搜索 + 按字母索引）
 *   - Picker 日期选择器
 *   - 表单数据本地存储（断点续填）
 * ============================================================================
 */
// require: 导入依赖模块（CommonJS 语法）
const { mockFormOptions } = require('../../utils/mock');     // 表单选项（风格/兴趣列表等）
const { setStorageItem, getStorageItem } = require('../../utils/util');  // 本地存储工具
const { hotCities, cityGroups, alphabet, allCitiesFlat } = require('../../utils/cities'); // 城市数据

Page({
  data: {
    currentStep: 0,                    // 当前步骤索引（0=基本信息，1=偏好设置）

    // ===== 步骤指示器数据 =====
    // step-indicator 组件接收此数组渲染进度条
    stepData: [
      { num: 1, label: '基本信息', status: 'active', labelColor: '#0891B2' },
      { num: 2, label: '偏好设置', status: 'waiting', labelColor: '#94A3B8' },
      { num: 3, label: '生成行程', status: 'waiting', labelColor: '#94A3B8' },
    ],

    // ===== 基本信息字段 =====
    selectedOrigin: '',                // 选中的起始城市
    originInputValue: '',              // 起始地输入框值（双向绑定）
    selectedDest: '',                  // 选中的目的地城市
    destInputValue: '',                // 目的地输入框值
    showCityPicker: false,             // 是否显示城市选择器弹窗
    cityPickerTarget: 'dest',          // 弹窗选中的目标字段（'origin' | 'dest'）
    hotCities: hotCities,              // 热门城市列表
    cityGroups: cityGroups,            // 按字母分组的全国城市
    alphabet: alphabet,                // A-Z 字母索引
    allCitiesFlat: allCitiesFlat,      // 扁平城市列表（用于搜索）
    allCityNames: allCitiesFlat.map(c => c.name),  // 用于校验
    citySearchKeyword: '',             // 城市搜索关键词
    startDate: '',                     // 开始日期
    endDate: '',                       // 结束日期
    days: 0,                           // 计算出的总天数
    nights: 0,                         // 计算出的总晚数
    todayStr: '',                      // 今天的日期字符串（用于 date picker 的 start 限制）
    endMinDate: '',                    // 结束日期的最早可选值
    adults: 2,                         // 成人数量（默认2人）
    children: 0,                       // 小孩数量
    selectedTransport: 'plane',        // 出行方式（已废弃展示，后端默认 train）

    // ===== 偏好设置字段 =====
    styles: [],                        // 风格选项列表（从 mockFormOptions 加载）
    interests: [],                     // 兴趣选项列表
    budgets: [],                       // 预算选项列表
    accommodations: [],                // 住宿选项列表
    selectedStyle: 'leisure',          // 选中的风格
    selectedInterests: ['food', 'museum', 'family'],  // 选中的兴趣（多选，数组）
    selectedBudget: 'comfort',         // 选中的预算档位
    selectedAccommodation: 'comfort',  // 选中的住宿偏好
    specialNeeds: '',                  // 特殊需求文本

    safeTop: 0,                        // 安全区
    safeBottom: 0,
  },

  /**
   * onLoad — 页面加载初始化
   * 
   * 1. 计算今天的日期（用于日期选择器的最小值限制）
   * 2. 加载表单选项数据（风格/兴趣/预算/住宿）
   * 3. 恢复之前填写但未提交的表单（断点续填功能）
   */
  onLoad() {
    const app = getApp();
    const today = new Date();
    const y = today.getFullYear();
    const m = String(today.getMonth() + 1).padStart(2, '0');
    const d = String(today.getDate()).padStart(2, '0');
    const todayStr = `${y}-${m}-${d}`;        // 如 "2025-06-01"

    this.setData({
      styles: mockFormOptions.styles,          // 从 mock 加载选项列表
      interests: mockFormOptions.interests,
      budgets: mockFormOptions.budgets,
      accommodations: mockFormOptions.accommodations,
      todayStr,
      safeTop: app.globalData.statusBarHeight,
      safeBottom: app.globalData.safeAreaBottom,
    });

    // --- 恢复预选目的地（如从首页点击热门城市跳转过来） ---
    const preselected = getStorageItem('preselectedDest');
    if (preselected) this.setData({ selectedDest: preselected, destInputValue: preselected });

    // --- 恢复上次填写未提交的表单 ---
    const saved = getStorageItem('tripFormData');
    if (saved) {
      this.setData({
        selectedOrigin: saved.origin || '',
        originInputValue: saved.origin || '',
        selectedDest: saved.destination || this.data.selectedDest,
        destInputValue: saved.destination || this.data.destInputValue,
        startDate: saved.startDate || '',
        endDate: saved.endDate || '',
        adults: saved.adults || 2,
        children: saved.children || 0,
        selectedTransport: saved.transport || 'plane',
        selectedStyle: saved.style || 'leisure',
        selectedInterests: saved.interests || ['food', 'museum', 'family'],
        selectedBudget: saved.budget || 'comfort',
        selectedAccommodation: saved.accommodation || 'comfort',
        specialNeeds: saved.specialNeeds || '',
      });
      if (saved.startDate) this.setData({ endMinDate: saved.startDate });
      if (saved.startDate && saved.endDate) this.calcDays(saved.startDate, saved.endDate);
    }
  },

  // ===== Swiper 步骤切换 =====
  onSwiperChange(e) {
    // e.detail.current: Swiper 当前页索引
    const step = e.detail.current;
    this.setData({ currentStep: step });
    this.updateStepIndicator(step);            // 更新顶部步骤指示器
  },

  // 点击"下一步" → 从基本信息切换到偏好设置
  goNext() {
    const totalPeople = this.data.adults + this.data.children;
    const origin = this.data.selectedOrigin.trim();
    const dest = this.data.selectedDest.trim();

    // 表单验证（前端校验，避免提交无效数据到后端）
    if (!dest) return wx.showToast({ title: '请先选择目的地', icon: 'none' });
    if (!this.data.startDate) return wx.showToast({ title: '请选择出行日期', icon: 'none' });
    if (this.data.adults < 1) return wx.showToast({ title: '至少需要1位成人', icon: 'none' });

    // 校验城市名不是省份（省份不能作为目的地）
    if (origin && !this.isCityName(origin)) {
      return wx.showToast({ title: '起始地请输入城市名', icon: 'none' });
    }
    if (dest && !this.isCityName(dest)) {
      return wx.showToast({ title: '目的地请输入城市名', icon: 'none' });
    }

    // 保存基本信息到 Storage（跨页面传递数据的方式）
    setStorageItem('tripFormData', {
      origin: this.data.selectedOrigin,
      destination: this.data.selectedDest,
      startDate: this.data.startDate,
      endDate: this.data.endDate,
      adults: this.data.adults,
      children: this.data.children,
      people: totalPeople,
    });

    this.setData({ currentStep: 1 });         // 切换到偏好设置
    this.updateStepIndicator(1);
  },

  // 返回上一步
  goPrev() {
    this.setData({ currentStep: 0 });
    this.updateStepIndicator(0);
  },

  // 点击"生成行程" → 合并偏好到表单 → 跳转 generate 页面
  onGenerate() {
    const saved = getStorageItem('tripFormData') || {};
    setStorageItem('tripFormData', {
      ...saved,                              // 展开运算符：合并基本信息
      style: this.data.selectedStyle,        // 追加偏好设置字段
      interests: this.data.selectedInterests,
      budget: this.data.selectedBudget,
      accommodation: this.data.selectedAccommodation,
      specialNeeds: this.data.specialNeeds,
    });
    wx.navigateTo({ url: '/pages/generate/index' });
  },

  /**
   * 更新步骤指示器状态
   * @param {number} step - 当前步骤 0 或 1
   */
  updateStepIndicator(step) {
    // 状态映射表：行=步骤数，列=3个步骤的状态
    const map = [
      ['active', 'waiting', 'waiting'],       // step=0：基本信息在编辑
      ['completed', 'active', 'waiting'],     // step=1：偏好设置在编辑
    ];
    const colors = [
      ['#0891B2', '#94A3B8', '#94A3B8'],
      ['#22C55E', '#06B6D4', '#94A3B8'],
    ];
    this.setData({
      stepData: [
        { num: 1, label: '基本信息', status: map[step][0], labelColor: colors[step][0] },
        { num: 2, label: '偏好设置', status: map[step][1], labelColor: colors[step][1] },
        { num: 3, label: '生成行程', status: map[step][2], labelColor: colors[step][2] },
      ],
    });
  },

  // ===== 目的地相关 =====
  onDestInput(e) { const v = e.detail.value; this.setData({ destInputValue: v, selectedDest: v }); },
  onToggleCityPicker(e) {
    const target = e.currentTarget.dataset.target || 'dest';
    this.setData({ showCityPicker: !this.data.showCityPicker, cityPickerTarget: target, citySearchKeyword: '' });
  },
  onCitySelect(e) {
    const city = e.currentTarget.dataset.city;
    const target = this.data.cityPickerTarget;
    if (target === 'origin') {
      this.setData({ selectedOrigin: city, originInputValue: city, showCityPicker: false, citySearchKeyword: '' });
    } else {
      this.setData({ selectedDest: city, destInputValue: city, showCityPicker: false, citySearchKeyword: '' });
    }
  },
  // 随机推荐目的地
  onRandomDest() {
    const random = hotCities[Math.floor(Math.random() * hotCities.length)];
    this.setData({ selectedDest: random, destInputValue: random });
  },
  onCitySearch(e) { this.setData({ citySearchKeyword: e.detail.value }); },
  onAlphabetTap(e) { this.setData({ cityScrollTo: 'letter-' + e.currentTarget.dataset.letter }); },
  onCloseCityPicker() { this.setData({ showCityPicker: false, citySearchKeyword: '' }); },
  preventBubble() {},    // 阻止事件冒泡（点击弹窗内部不关闭弹窗）

  // ===== 起始地 =====
  onOriginInput(e) { const v = e.detail.value; this.setData({ originInputValue: v, selectedOrigin: v }); },
  // 失焦校验：输入的不是城市名则提示
  onOriginBlur(e) {
    const v = e.detail.value.trim();
    if (v && !this.isCityName(v)) {
      wx.showToast({ title: '请输入城市名（非省份）', icon: 'none', duration: 1500 });
    }
  },
  onDestBlur(e) {
    const v = e.detail.value.trim();
    if (v && !this.isCityName(v)) {
      wx.showToast({ title: '请输入城市名（非省份）', icon: 'none', duration: 1500 });
    }
  },

  // 判断输入是否为城市名（排除省份名）
  isCityName(name) {
    if (!name) return false;
    // 正则匹配中国所有省级行政区名称 → 不是城市
    if (/^(广东|广西|山东|山西|河南|河北|湖南|湖北|江苏|江西|浙江|安徽|福建|甘肃|贵州|辽宁|吉林|黑龙江|云南|四川|陕西|青海|海南|台湾|宁夏|西藏|新疆|内蒙古|香港|澳门)$/.test(name)) return false;
    return true;
  },

  // ===== 日期选择 =====
  // Picker 组件的 bindchange 事件：用户选择日期后触发
  onStartDateChange(e) {
    const start = e.detail.value;
    this.setData({ startDate: start, endMinDate: start });  // 结束日期不能早于开始日期
    if (this.data.endDate && this.data.endDate < start) this.setData({ endDate: '', days: 0, nights: 0 });
    if (start && this.data.endDate) this.calcDays(start, this.data.endDate);
  },
  onEndDateChange(e) {
    const end = e.detail.value;
    this.setData({ endDate: end });
    if (this.data.startDate && end) this.calcDays(this.data.startDate, end);
  },
  // 计算天数和晚数
  calcDays(start, end) {
    if (!start || !end) return;
    const s = new Date(start.replace(/-/g, '/'));  // 兼容 iOS 日期格式
    const e = new Date(end.replace(/-/g, '/'));
    const diff = Math.ceil((e - s) / (1000 * 60 * 60 * 24));  // 毫秒→天数
    if (diff >= 0) this.setData({ days: diff + 1, nights: diff });
  },

  // ===== 人数加减 =====
  onMinusAdult() { if (this.data.adults > 1) this.setData({ adults: this.data.adults - 1 }); },
  onPlusAdult() { if (this.data.adults < 10) this.setData({ adults: this.data.adults + 1 }); },
  onMinusChild() { if (this.data.children > 0) this.setData({ children: this.data.children - 1 }); },
  onPlusChild() { if (this.data.children < 5) this.setData({ children: this.data.children + 1 }); },

  // ===== 偏好设置 =====
  onSelectStyle(e) { this.setData({ selectedStyle: e.currentTarget.dataset.value }); },
  // 兴趣多选：点击切换选中状态
  onToggleInterest(e) {
    const val = e.currentTarget.dataset.value;
    const arr = [...this.data.selectedInterests];   // 浅拷贝数组（避免直接修改原数组）
    const idx = arr.indexOf(val);
    idx > -1 ? arr.splice(idx, 1) : arr.push(val);  // toggle: 有则删，无则加
    this.setData({ selectedInterests: arr });
  },
  onSelectBudget(e) { this.setData({ selectedBudget: e.currentTarget.dataset.value }); },
  onSelectAccommodation(e) { this.setData({ selectedAccommodation: e.currentTarget.dataset.value }); },
  onNeedsInput(e) { this.setData({ specialNeeds: e.detail.value }); },

  // 返回上一页
  onBack() { wx.navigateBack(); },
});
