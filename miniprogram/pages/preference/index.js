const { mockFormOptions } = require('../../utils/mock');
const { setStorageItem, getStorageItem } = require('../../utils/util');

Page({
  data: {
    stepData: [
      { num: 1, label: '基本信息', status: 'completed', labelColor: '#22C55E' },
      { num: 2, label: '偏好设置', status: 'active', labelColor: '#06B6D4' },
      { num: 3, label: '生成行程', status: 'waiting', labelColor: '#94A3B8' },
    ],
    styles: [],
    interests: [],
    budgets: [],
    accommodations: [],
    selectedStyle: 'leisure',
    selectedInterests: ['food', 'museum', 'family'],
    selectedBudget: 'comfort',
    selectedAccommodation: 'comfort',
    specialNeeds: '',
    safeTop: 0,
    safeBottom: 0,
  },

  onLoad() {
    const app = getApp();
    this.setData({
      styles: mockFormOptions.styles,
      interests: mockFormOptions.interests,
      budgets: mockFormOptions.budgets,
      accommodations: mockFormOptions.accommodations,
      safeTop: app.globalData.statusBarHeight,
      safeBottom: app.globalData.safeAreaBottom,
    });
    const saved = getStorageItem('tripFormData');
    if (saved) {
      this.setData({
        selectedStyle: saved.style || 'leisure',
        selectedInterests: saved.interests || ['food', 'museum', 'family'],
        selectedBudget: saved.budget || 'comfort',
        selectedAccommodation: saved.accommodation || 'comfort',
        specialNeeds: saved.specialNeeds || '',
      });
    }
  },

  onBack() { wx.navigateBack(); },
  onSelectStyle(e) { this.setData({ selectedStyle: e.currentTarget.dataset.value }); },

  onToggleInterest(e) {
    const val = e.currentTarget.dataset.value;
    const arr = [...this.data.selectedInterests];
    const idx = arr.indexOf(val);
    idx > -1 ? arr.splice(idx, 1) : arr.push(val);
    this.setData({ selectedInterests: arr });
  },

  onSelectBudget(e) { this.setData({ selectedBudget: e.currentTarget.dataset.value }); },
  onSelectAccommodation(e) { this.setData({ selectedAccommodation: e.currentTarget.dataset.value }); },
  onNeedsInput(e) { this.setData({ specialNeeds: e.detail.value }); },

  onPrev() { wx.navigateBack(); },

  onGenerate() {
    const saved = getStorageItem('tripFormData') || {};
    setStorageItem('tripFormData', {
      ...saved,
      style: this.data.selectedStyle,
      interests: this.data.selectedInterests,
      budget: this.data.selectedBudget,
      accommodation: this.data.selectedAccommodation,
      specialNeeds: this.data.specialNeeds,
    });
    wx.navigateTo({ url: '/pages/generate/index' });
  },
});
