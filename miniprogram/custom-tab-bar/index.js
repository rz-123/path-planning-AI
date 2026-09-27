Component({
  data: {
    selected: 0,
    show: true,
  },

  attached() {
    const app = getApp();
    this.setData({ safeBottom: app.globalData.safeAreaBottom });
  },

  methods: {
    switchTab(e) {
      const data = e.currentTarget.dataset;
      wx.switchTab({ url: data.path });
    },
  },

  pageLifetimes: {
    show() {
      const pages = getCurrentPages();
      const currentPage = pages[pages.length - 1];
      const route = '/' + currentPage.route;

      // 只在 首页 和 我的 显示 TabBar
      const tabPages = [
        '/pages/index/index',
        '/pages/my/index',
      ];

      const isTabPage = tabPages.includes(route);
      this.setData({ show: isTabPage });

      if (route === '/pages/index/index') {
        this.setData({ selected: 0 });
      } else if (route === '/pages/my/index') {
        this.setData({ selected: 1 });
      }
    },
  },
});
