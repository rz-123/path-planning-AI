/**
 * ============================================================================
 * mock.js — 静态数据（热门目的地、表单选项、旅行小贴士等）
 * ============================================================================
 * 这些数据是纯静态内容，不依赖后端 API，用于：
 *   1. 首页热门目的地卡片
 *   2. 创建页面的表单选项（风格/兴趣/预算/住宿）
 *   3. 生成页面的旅行小贴士轮播
 * 
 * 注：现在后端已经正常工作，行程数据从 CloudBase 数据库加载
 *     但静态选项数据（表单选项、旅行小贴士）仍然使用 mock
 * ============================================================================
 */
const { getStorageItem, setStorageItem } = require('./util');

// ===== 热门目的地（首页横向滚动卡片） =====
const mockHotDestinations = [
  { id: 'chengdu', name: '成都', tags: '美食之都 | 亲子友好',
    image: 'https://prototype-prod-1254106194.cos.ap-beijing.myqcloud.com/calicat/file/ai/canvas/image/1978661049371021312.jpg',
    description: '熊猫基地、宽窄巷子、火锅美食', basePrice: 2500 },
  { id: 'xian', name: '西安', tags: '历史名城 | 红色基地',
    image: 'https://prototype-prod-1254106194.cos.ap-beijing.myqcloud.com/calicat/file/ai/canvas/image/2016616910647046144.jpg',
    description: '兵马俑、大雁塔、回民街', basePrice: 2200 },
  { id: 'sanya', name: '三亚', tags: '海滨度假 | 休闲放松',
    image: 'https://prototype-prod-1254106194.cos.ap-beijing.myqcloud.com/calicat/file/ai/canvas/image/2044594822205407232.jpg',
    description: '天涯海角、亚龙湾、海鲜大餐', basePrice: 3500 },
  { id: 'beijing', name: '北京', tags: '文化古都 | 博物馆众多',
    image: 'https://prototype-prod-1254106194.cos.ap-beijing.myqcloud.com/calicat/file/ai/canvas/image/2034545798036070400.jpg',
    description: '故宫、长城、国博、胡同', basePrice: 2800 },
];

// ===== 最近规划列表（首页使用，现在优先从 CloudBase 加载） =====
const mockRecentTrips = [
  { id: 'trip_001', title: '成都3日亲子游', startDate: '2024.06.10', endDate: '2024.06.12',
    tags: '亲子乐园, 美食', status: 'completed', statusText: '已完成', budget: 3200,
    destination: '成都', people: 3, days: 3 },
  { id: 'trip_002', title: '西安红色文化之旅', startDate: '2024.07.15', endDate: '2024.07.18',
    tags: '红色基地, 博物馆', status: 'draft', statusText: '草稿', budget: 4500,
    destination: '西安', people: 2, days: 4 },
];

// ===== 表单选项数据（创建页面的风格/兴趣/预算/住宿选项） =====
const mockFormOptions = {
  styles: [
    { label: '轻松休闲', value: 'leisure', icon: '\uef30' },
    { label: '深度打卡', value: 'deep', icon: '\ueb31' },
    { label: '文艺小资', value: 'artistic', icon: '\uf04a' },
    { label: '特种兵式', value: 'intensive', icon: '\uf096' },
  ],
  interests: [
    { label: '美食探索', value: 'food', icon: '\uf044', color: '#F97316' },
    { label: '博物馆', value: 'museum', icon: '\ueb09', color: '#3B82F6' },
    { label: '自然风光', value: 'nature', icon: '\uee7d', color: '#22C55E' },
    { label: '亲子乐园', value: 'family', icon: '\uedab', color: '#22C55E' },
    { label: '购物血拼', value: 'shopping', icon: '\uf116', color: '#8B5CF6' },
    { label: '红色基地', value: 'red', icon: '\ued3b', color: '#EF4444' },
    { label: '夜生活', value: 'nightlife', icon: '\uef35', color: '#8B5CF6' },
    { label: '拍照打卡', value: 'photo', icon: '\ueb30', color: '#F59E0B' },
  ],
  budgets: [
    { label: '经济', value: 'economy', range: '¥500-1k' },
    { label: '舒适', value: 'comfort', range: '¥1k-1.5k' },
    { label: '品质', value: 'quality', range: '¥1.5k-2k' },
  ],
  accommodations: [
    { label: '经济型', value: 'budget' },
    { label: '舒适型', value: 'comfort' },
    { label: '高档型', value: 'premium' },
  ],
};

// ===== 旅行小贴士（按城市分类，生成页面轮播展示） =====
const mockTravelTips = [
  { city: '成都', tip: '成都6月平均气温22-30°C，建议携带防晒和雨具。大熊猫基地建议上午9点前到达。' },
  { city: '成都', tip: '锦里和宽窄巷子适合晚上逛，灯火阑珊更有氛围。火锅推荐本地人常去的社区店。' },
  { city: '西安', tip: '西安夏季气温25-35°C，注意防暑。兵马俑建议上午去，避开旅行团高峰。' },
  { city: '西安', tip: '陕博需提前3天在公众号预约，门票极为抢手。回民街美食众多，建议空着肚子去。' },
  { city: '西安', tip: '城墙骑行推荐下午4点后，避开正午暴晒。永宁门（南门）登城最方便。' },
  { city: '三亚', tip: '三亚全年温暖，11月至次年4月为最佳旅游季。防晒霜和泳衣是必备品。' },
  { city: '三亚', tip: '海鲜市场建议去第一市场，自己挑选后找加工店，比直接点菜实惠。' },
  { city: '北京', tip: '故宫需提前7天预约，周一闭馆。天安门广场安检严格，请勿携带大包。' },
  { city: '北京', tip: '北京地铁覆盖大部分景点，下载"亿通行"APP刷码乘车。王府井小吃偏贵，护国寺更地道。' },
  { city: '杭州', tip: '西湖免费开放，周长约15公里，骑行一圈约2小时。断桥残雪是经典打卡位。' },
  { city: '杭州', tip: '灵隐寺需购票进入飞来峰景区后才能到达。龙井村可体验采茶，春茶季最佳。' },
  { city: '重庆', tip: '重庆夏季炎热，洪崖洞夜景必看但人巨多。轻轨2号线李子坝站穿楼值得打卡。' },
  { city: '重庆', tip: '重庆火锅推荐巷子里的老店，解放碑附近的游客店性价比一般。' },
  { city: '上海', tip: '外滩夜景免费，从南京路步行街走到外滩约15分钟。迪士尼需提前购票和预约。' },
  { city: '上海', tip: '上海地铁发达，建议购买一日票（18元）不限次乘坐。田子坊和武康路适合拍照。' },
  { city: '广州', tip: '广州夏季多雨，随身带伞。早茶推荐陶陶居、点都德，上午11点前下单有折扣。' },
  { city: '广州', tip: '广州塔门票不菲，不想花钱可在花城广场免费拍远景。沙面岛适合漫步拍照。' },
  { city: '深圳', tip: '深圳年轻活力，华侨城、欢乐谷适合亲子游。深圳湾公园骑行看日落非常惬意。' },
  { city: '南京', tip: '南京春秋最美，中山陵免费但需预约。夫子庙小吃偏游客化，本地人推荐科巷菜场。' },
  { city: '厦门', tip: '鼓浪屿需提前在公众号买船票，岛上限流每天5万人。曾厝垵可住民宿体验慢生活。' },
  { city: '厦门', tip: '沙坡尾是文艺青年的天堂，各类文创小店和咖啡馆都很出片。' },
  { city: '长沙', tip: '长沙辣味天堂！茶颜悦色遍地都是。橘子洲头周六晚有烟花（季节限定）。' },
  { city: '桂林', tip: '桂林山水甲天下，漓江竹筏漂流是必玩项目。阳朔西街夜生活丰富，啤酒鱼是招牌菜。' },
  { city: '丽江', tip: '丽江海拔2400米，早晚温差大需带外套。玉龙雪山需提前购票，大索道最热门。' },
  { city: '哈尔滨', tip: '哈尔滨冬季必打卡冰雪大世界（12月底至次年2月），中央大街马迭尔冰棍是百年老店。' },
  { city: '昆明', tip: '昆明四季如春，全年都适合旅行。斗南花市是亚洲最大鲜花市场，超便宜。' },
];

/**
 * 按城市名获取对应的小贴士
 * 
 * filter(): 数组过滤方法，返回满足条件的元素组成的新数组
 * 如果该城市没有专属贴士，返回全部贴士（兜底）
 */
function getTravelTipsByCity(city) {
  if (!city) return mockTravelTips;
  var matched = mockTravelTips.filter(function(t) { return t.city === city; });
  return matched.length > 0 ? matched : mockTravelTips;
}

// ===== 历史行程模拟数据（"我的"页面使用，现在优先从 CloudBase 加载） =====
const now = new Date();
function daysAgo(n) { const d = new Date(now); d.setDate(d.getDate() - n); return d; }
function fmt(d) { return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`; }
function monthStr(d) { return `${d.getMonth() + 1}月`; }
function dayStr(d) { return String(d.getDate()); }

const mockHistoryTrips = [
  { id: 'h_001', title: '成都3日亲子游', destination: '成都',
    startDate: fmt(daysAgo(3)), endDate: fmt(daysAgo(1)), days: 3, people: 3,
    tags: '亲子乐园, 美食', status: 'completed', statusText: '已完成', budget: 3200,
    month: monthStr(daysAgo(3)), day: dayStr(daysAgo(3)) },
  { id: 'h_002', title: '西安红色文化之旅', destination: '西安',
    startDate: fmt(daysAgo(8)), endDate: fmt(daysAgo(5)), days: 4, people: 2,
    tags: '红色基地, 博物馆', status: 'completed', statusText: '已完成', budget: 4500,
    month: monthStr(daysAgo(8)), day: dayStr(daysAgo(8)) },
  { id: 'h_003', title: '三亚周末度假', destination: '三亚',
    startDate: fmt(daysAgo(12)), endDate: fmt(daysAgo(10)), days: 3, people: 2,
    tags: '海滩, 海鲜', status: 'completed', statusText: '已完成', budget: 5800,
    month: monthStr(daysAgo(12)), day: dayStr(daysAgo(12)) },
  { id: 'h_004', title: '北京文化之旅', destination: '北京',
    startDate: fmt(daysAgo(16)), endDate: fmt(daysAgo(14)), days: 3, people: 1,
    tags: '博物馆, 历史古迹', status: 'canceled', statusText: '已取消', budget: 2600,
    month: monthStr(daysAgo(16)), day: dayStr(daysAgo(16)) },
  { id: 'h_005', title: '杭州西湖周末游', destination: '杭州',
    startDate: fmt(daysAgo(20)), endDate: fmt(daysAgo(18)), days: 3, people: 2,
    tags: '自然风光, 拍照打卡', status: 'completed', statusText: '已完成', budget: 2100,
    month: monthStr(daysAgo(20)), day: dayStr(daysAgo(20)) },
  { id: 'h_006', title: '桂林山水甲天下', destination: '桂林',
    startDate: fmt(daysAgo(24)), endDate: fmt(daysAgo(21)), days: 4, people: 4,
    tags: '自然风光, 拍照打卡', status: 'completed', statusText: '已完成', budget: 6800,
    month: monthStr(daysAgo(24)), day: dayStr(daysAgo(24)) },
  { id: 'h_007', title: '丽江古城慢生活', destination: '丽江',
    startDate: fmt(daysAgo(28)), endDate: fmt(daysAgo(25)), days: 4, people: 2,
    tags: '文艺小资, 美食', status: 'completed', statusText: '已完成', budget: 5200,
    month: monthStr(daysAgo(28)), day: dayStr(daysAgo(28)) },
];

module.exports = {
  mockHotDestinations,    // 首页热门目的地
  mockRecentTrips,        // 最近行程（已弃用，改用 CloudBase）
  mockHistoryTrips,       // 历史行程（已弃用，改用 CloudBase）
  mockFormOptions,        // 表单选项（风格/兴趣/预算/住宿）
  mockTravelTips,         // 旅行小贴士
  getTravelTipsByCity,    // 按城市获取小贴士
};
