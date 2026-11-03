function FindProxyForURL(url, host) {
  host = host.toLowerCase();

  // 本地与局域网地址直连
  if (host === "localhost" || host === "127.0.0.1" || host === "::1" || host === "[::1]" ||
      shExpMatch(host, "*.local") ||
      shExpMatch(host, "127.*") ||
      shExpMatch(host, "10.*") ||
      shExpMatch(host, "192.168.*") ||
      shExpMatch(host, "169.254.*") ||
      shExpMatch(host, "172.16.*") || shExpMatch(host, "172.17.*") ||
      shExpMatch(host, "172.18.*") || shExpMatch(host, "172.19.*") ||
      shExpMatch(host, "172.20.*") || shExpMatch(host, "172.21.*") ||
      shExpMatch(host, "172.22.*") || shExpMatch(host, "172.23.*") ||
      shExpMatch(host, "172.24.*") || shExpMatch(host, "172.25.*") ||
      shExpMatch(host, "172.26.*") || shExpMatch(host, "172.27.*") ||
      shExpMatch(host, "172.28.*") || shExpMatch(host, "172.29.*") ||
      shExpMatch(host, "172.30.*") || shExpMatch(host, "172.31.*") ||
      isPlainHostName(host)) {
    return "DIRECT";
  }

  // Google 旗下大流量下载、软件自动更新、云盘相册与日常翻译子域豁免：
  // 优先放行走日常高速 VPN 通道，避免消耗静态住宅专线流量
  var highBandwidthBypass = [
    "dl.google.com",
    "drive.google.com",
    "docs.google.com",
    "photos.google.com",
    "takeout.google.com",
    "translate.google.com",
    "update.googleapis.com",
    "storage.googleapis.com",
    "commondatastorage.googleapis.com",
    "translate.googleapis.com"
  ];

  for (var b = 0; b < highBandwidthBypass.length; b++) {
    var bd = highBandwidthBypass[b];
    if (host === bd || dnsDomainIs(host, "." + bd)) {
      return "SOCKS5 127.0.0.1:8687; SOCKS 127.0.0.1:8687; DIRECT";
    }
  }

  // 全链路美东静态住宅保护名单（严格锁定本地 8121 住宅网关，绝不回退日常 VPN）
  var residentialDomains = [
    // 1. Claude / Anthropic 官方全系与客服组件
    "claude.ai",
    "claude.com",
    "anthropic.com",
    "claudeusercontent.com",
    "claudemcpclient.com",
    "claudemcpcontent.com",
    "anthropic.statuspage.io",
    "intercom.io",
    "intercomcdn.com",

    // 2. Google 纯净身份闭环（搜索、账号中心、OAuth 快捷登录、Gmail 邮箱、reCAPTCHA，不含 YouTube 视频）
    "google.com",
    "gmail.com",
    "googlemail.com",
    "accounts.youtube.com",
    "googleapis.com",
    "www.gstatic.com",
    "ssl.gstatic.com",
    "fonts.gstatic.com",
    "lh3.googleusercontent.com",
    "recaptcha.net",
    "withgoogle.com",

    // 3. Stripe 支付收银台与金融结算风控全系
    "stripe.com",
    "stripe.network",
    "stripecdn.com",
    "link.com",

    // 4. 人机验证盾全系（Cloudflare / hCaptcha / Arkose）
    "challenges.cloudflare.com",
    "csp-reporting.cloudflare.com",
    "cloudflareinsights.com",
    "cloudflareperf.com",
    "pat-issuer.cloudflare.com",
    "hcaptcha.com",
    "arkoselabs.com",
    "funcaptcha.com",

    // 5. 商业级反欺诈设备指纹与 KYC 身份核验全系
    "fpjs.io",
    "fpcdn.io",
    "fptls.com",
    "withpersona.com",
    "sift.com",
    "siftscience.com",

    // 6. Claude 前端真实用户监控、实验开关与地区合规组件
    "datadoghq.com",
    "browser-intake-datadoghq.com",
    "browser-intake-us3-datadoghq.com",
    "browser-intake-us5-datadoghq.com",
    "statsig.com",
    "statsigapi.net",
    "featuregates.org",
    "prodregistryv2.org",
    "beyondwickedmapping.org",
    "growthbook.io",
    "segment.io",
    "segment.com",
    "rudderstack.com",
    "rudderlabs.com",
    "ingest.us.sentry.io",
    "ingest.sentry.io",
    "onetrust.com",
    "cookielaw.org",

    // 7. 全网主流环境 / IP / 指纹泄露验真站
    "ippure.com",
    "ipin.io",
    "ipinfo.io",
    "ipinfo.cv",
    "ipapi.co",
    "ipip.net",
    "ipify.org",
    "icanhazip.com",
    "ip.sb",
    "net.coffee",
    "ipkk.com",
    "ipchaxun.net",
    "123169.xyz",
    "999831.xyz",
    "ip138.com",
    "ping0.cc",
    "scamalytics.com",
    "whoer.net",
    "browserleaks.com",
    "browserleaks.net",
    "browserleaks.org",
    "creepjs.com",

    // 8. Meta Muse AI 智能体与 Meta 账号认证全系
    "muse.ai",
    "meta.ai",
    "meta.com",
    "metaaivm.com",
    "metaaiusercontent.com",
    "ecto1usercontent.com",
    "meta-agents-apps.workers.dev",
    "facebook.com",
    "facebook.net",
    "fbcdn.net",
    "fbsbx.com",
    "instagram.com",
    "cdninstagram.com"
  ];

  for (var i = 0; i < residentialDomains.length; i++) {
    var d = residentialDomains[i];
    if (host === d || dnsDomainIs(host, "." + d)) {
      return "PROXY 127.0.0.1:8121";
    }
  }

  // 其余日常网站（含 YouTube 视频、飞书、国内网站等）走本地分流兜底与系统默认 VPN 路由
  return "SOCKS5 127.0.0.1:8687; SOCKS 127.0.0.1:8687; DIRECT";
}
