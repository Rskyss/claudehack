// 在 Chrome 浏览器内部开启最高优先级的 WebRTC 防泄露保护，彻底杜绝暴露本地真实物理宽带 IP
function lockWebRTC() {
  if (chrome && chrome.privacy && chrome.privacy.network && chrome.privacy.network.webRTCIPHandlingPolicy) {
    chrome.privacy.network.webRTCIPHandlingPolicy.set({
      value: "disable_non_proxied_udp"
    });
  }
}

chrome.runtime.onInstalled.addListener(lockWebRTC);
chrome.runtime.onStartup.addListener(lockWebRTC);
lockWebRTC();
