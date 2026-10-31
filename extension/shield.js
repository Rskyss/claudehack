// Claude 智能分网站美区环境护盾 v2.3.0
// 仅在 Claude 全系、Google 账号/Gmail/搜索、Stripe 支付收银台、人机验证盾、设备指纹探针与验真检测页生效，日常国内网站零触发
(function () {
  "use strict";

  const TARGET_TZ = "America/New_York";
  const TARGET_LOCALE = "en-US";

  // 记录已完成保护注入的窗口对象，确保同源动态空白 iframe 幂等零重复执行
  const patchedRealms = new WeakSet();

  const CJK_FONT_RE = /(PingFang|Hiragino\s*Sans\s*GB|STHeiti|Heiti\s*SC|Heiti\s*TC|STSong|Songti|STKaiti|Kaiti|STFangsong|FangSong|Microsoft\s*YaHei|YaHei|Microsoft\s*JhengHei|SimSun|NSimSun|SimHei|KaiTi|DengXian|YouYuan|LiSu|STCaiyun|STHupo|STLiti|STXinwei|STXingkai|STZhongsong|FZShuTi|FZYaoTi|HarmonyOS|MiSans|Alibaba|Source\s*Han|Noto\s*Sans\s*CJK|Noto\s*Sans\s*SC|Noto\s*Sans\s*TC|Noto\s*Serif\s*CJK|Noto\s*Serif\s*SC|WenQuanYi|Yuanti|Baoli|Libian|Wawati|Weibei|Xingkai|Yuppy|Lantinghei|Hanzipen|Klee|BiauKai|Apple\s*LiGothic|Apple\s*LiSung|PMingLiU|MingLiU|DFKai-SB)/i;
  const CJK_VOICE_LANG_RE = /^(zh|cmn|yue|wuu)\b/i;
  const CJK_VOICE_NAME_RE = /(Tingting|Ting-Ting|Sinji|Sin-ji|Meijia|Mei-Jia|Yu-shu|Li-mu|Tian-Tian|Putonghua|Cantonese|Chinese|普通话|粤语|國語)/i;

  function sanitizeFontString(fontVal) {
    if (typeof fontVal !== "string" || !CJK_FONT_RE.test(fontVal)) {
      return fontVal;
    }
    const sizeMatch = fontVal.match(/^(.*?\b\d+(?:\.\d+)?(?:px|pt|em|rem|%|vh|vw)\b(?:\s*\/\s*[\d.]+(?:px|pt|em|rem|%)?)?\s+)(.+)$/i);
    if (!sizeMatch) {
      return fontVal;
    }
    const prefix = sizeMatch[1];
    const families = sizeMatch[2]
      .split(",")
      .map(function (f) { return f.trim(); })
      .filter(function (f) {
        const clean = f.replace(/^['"]+|['"]+$/g, "");
        return !CJK_FONT_RE.test(clean);
      });
    if (families.length === 0) {
      families.push("sans-serif");
    }
    return prefix + families.join(", ");
  }

  // Worker 后台线程前导环境对齐脚本（防止反欺诈引擎在 Blob/Data Worker 线程内对比时区与语言穿帮）
  const WORKER_BOOTSTRAP_CODE = "(" + function () {
    "use strict";
    try {
      const TZ = "America/New_York";
      const LOC = "en-US";
      const LANGS = Object.freeze(["en-US", "en"]);
      const OrigDTF = self.Intl && self.Intl.DateTimeFormat;
      const OrigDate = self.Date;
      if (self.Navigator && self.Navigator.prototype) {
        Object.defineProperty(self.Navigator.prototype, "language", { get: function () { return LOC; }, configurable: true });
        Object.defineProperty(self.Navigator.prototype, "languages", { get: function () { return LANGS; }, configurable: true });
      } else if (self.WorkerNavigator && self.WorkerNavigator.prototype) {
        Object.defineProperty(self.WorkerNavigator.prototype, "language", { get: function () { return LOC; }, configurable: true });
        Object.defineProperty(self.WorkerNavigator.prototype, "languages", { get: function () { return LANGS; }, configurable: true });
      }
      if (OrigDTF) {
        const WrappedDTF = function DateTimeFormat(locales, options) {
          const loc = (locales === undefined) ? LOC : locales;
          let opts = options;
          if (opts === undefined) {
            opts = { timeZone: TZ };
          } else if (opts && typeof opts === "object" && opts.timeZone === undefined) {
            opts = Object.assign({}, opts, { timeZone: TZ });
          }
          return new.target ? new OrigDTF(loc, opts) : OrigDTF(loc, opts);
        };
        WrappedDTF.prototype = OrigDTF.prototype;
        Object.setPrototypeOf(WrappedDTF, OrigDTF);
        if (typeof OrigDTF.supportedLocalesOf === "function") {
          WrappedDTF.supportedLocalesOf = OrigDTF.supportedLocalesOf.bind(OrigDTF);
        }
        self.Intl.DateTimeFormat = WrappedDTF;
      }
      if (OrigDTF && OrigDate) {
        const offsetFmt = new OrigDTF("en-US", { timeZone: TZ, timeZoneName: "shortOffset" });
        const calcOffset = function (d) {
          const ms = OrigDate.prototype.getTime.call(d);
          if (Number.isNaN(ms)) return NaN;
          const parts = offsetFmt.formatToParts(d);
          for (let i = 0; i < parts.length; i++) {
            if (parts[i].type === "timeZoneName") {
              const m = parts[i].value.match(/GMT([+-])(\d+)(?::(\d+))?/);
              if (m) {
                const sign = m[1] === "-" ? 1 : -1;
                return sign * ((parseInt(m[2], 10) || 0) * 60 + (parseInt(m[3] || "0", 10) || 0));
              }
            }
          }
          return 240;
        };
        OrigDate.prototype.getTimezoneOffset = function getTimezoneOffset() { return calcOffset(this); };
      }
    } catch (_) {}
  }.toString() + ")();\n";

  function applyShieldToRealm(win) {
    if (!win || (typeof win !== "object" && typeof win !== "function")) return;
    try {
      if (patchedRealms.has(win)) return;
      patchedRealms.add(win);
    } catch (_) {
      return;
    }

    const RealmIntl = win.Intl;
    const OrigDateTimeFormat = RealmIntl && RealmIntl.DateTimeFormat;
    const OrigDate = win.Date;
    const RealmObject = win.Object || Object;
    const RealmFunction = win.Function;
    if (!OrigDateTimeFormat || !OrigDate || !RealmFunction) return;

    const US_LANGS = RealmObject.freeze(["en-US", "en"]);

    // 注册伪装函数至当前 Realm 的 native toString 白名单，防止函数签名检测
    const nativeToStringMap = new WeakMap();
    try {
      const origFnToString = RealmFunction.prototype.toString;
      const wrappedFnToString = function toString() {
        if (nativeToStringMap.has(this)) {
          return nativeToStringMap.get(this);
        }
        return origFnToString.call(this);
      };
      nativeToStringMap.set(wrappedFnToString, "function toString() { [native code] }");
      RealmObject.defineProperty(RealmFunction.prototype, "toString", {
        value: wrappedFnToString,
        configurable: true,
        writable: true
      });
    } catch (_) {}

    function markNative(fn, name) {
      try {
        nativeToStringMap.set(fn, "function " + (name || fn.name || "") + "() { [native code] }");
      } catch (_) {}
      return fn;
    }

    // 1. 锁定浏览器首选语言列表为美式英语
    try {
      if (win.Navigator && win.Navigator.prototype) {
        const getLang = markNative(function language() { return TARGET_LOCALE; }, "get language");
        const getLangs = markNative(function languages() { return US_LANGS; }, "get languages");
        RealmObject.defineProperty(win.Navigator.prototype, "language", {
          get: getLang,
          configurable: true
        });
        RealmObject.defineProperty(win.Navigator.prototype, "languages", {
          get: getLangs,
          configurable: true
        });
      }
    } catch (_) {}

    // 2. 锁定 Intl 系统时区为 America/New_York 及默认区域为 en-US
    try {
      const WrappedDTF = function DateTimeFormat(locales, options) {
        const loc = (locales === undefined) ? TARGET_LOCALE : locales;
        let opts = options;
        if (opts === undefined) {
          opts = { timeZone: TARGET_TZ };
        } else if (opts && typeof opts === "object" && opts.timeZone === undefined) {
          opts = RealmObject.assign({}, opts, { timeZone: TARGET_TZ });
        }
        if (new.target) {
          return new OrigDateTimeFormat(loc, opts);
        }
        return OrigDateTimeFormat(loc, opts);
      };
      WrappedDTF.prototype = OrigDateTimeFormat.prototype;
      RealmObject.setPrototypeOf(WrappedDTF, OrigDateTimeFormat);
      if (typeof OrigDateTimeFormat.supportedLocalesOf === "function") {
        WrappedDTF.supportedLocalesOf = OrigDateTimeFormat.supportedLocalesOf.bind(OrigDateTimeFormat);
      }
      markNative(WrappedDTF, "DateTimeFormat");
      RealmIntl.DateTimeFormat = WrappedDTF;

      ["NumberFormat", "Collator", "PluralRules", "RelativeTimeFormat", "ListFormat"].forEach(function (name) {
        const Orig = RealmIntl[name];
        if (typeof Orig !== "function") return;
        const Wrapped = function (locales, options) {
          const loc = (locales === undefined) ? TARGET_LOCALE : locales;
          if (new.target) {
            return new Orig(loc, options);
          }
          return Orig(loc, options);
        };
        Wrapped.prototype = Orig.prototype;
        RealmObject.setPrototypeOf(Wrapped, Orig);
        if (typeof Orig.supportedLocalesOf === "function") {
          Wrapped.supportedLocalesOf = Orig.supportedLocalesOf.bind(Orig);
        }
        markNative(Wrapped, name);
        RealmIntl[name] = Wrapped;
      });
    } catch (_) {}

    // 3. 动态计算并锁定 Date 时区偏移为美东时间 UTC-4 / UTC-5（自动兼容夏令时与冬令时）
    try {
      const offsetFmt = new OrigDateTimeFormat("en-US", {
        timeZone: TARGET_TZ,
        timeZoneName: "shortOffset"
      });
      const longTzFmt = new OrigDateTimeFormat("en-US", {
        timeZone: TARGET_TZ,
        timeZoneName: "long"
      });
      const partsFmt = new OrigDateTimeFormat("en-US", {
        timeZone: TARGET_TZ,
        weekday: "short",
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false
      });

      function getNYOffsetMinutes(dateObj) {
        const ms = OrigDate.prototype.getTime.call(dateObj);
        if (Number.isNaN(ms)) return NaN;
        const parts = offsetFmt.formatToParts(dateObj);
        for (let i = 0; i < parts.length; i++) {
          if (parts[i].type === "timeZoneName") {
            const m = parts[i].value.match(/GMT([+-])(\d+)(?::(\d+))?/);
            if (m) {
              const sign = m[1] === "-" ? 1 : -1;
              const hrs = parseInt(m[2], 10) || 0;
              const mins = parseInt(m[3] || "0", 10) || 0;
              return sign * (hrs * 60 + mins);
            }
          }
        }
        return 240;
      }

      function formatNYStrings(dateObj) {
        const off = getNYOffsetMinutes(dateObj);
        if (Number.isNaN(off)) return { dateStr: "Invalid Date", timeStr: "Invalid Date", fullStr: "Invalid Date" };
        const map = {};
        partsFmt.formatToParts(dateObj).forEach(function (p) { map[p.type] = p.value; });
        const hour = map.hour === "24" ? "00" : map.hour;
        const sign = off <= 0 ? "+" : "-";
        const abs = Math.abs(off);
        const hh = String(Math.floor(abs / 60)).padStart(2, "0");
        const mm = String(abs % 60).padStart(2, "0");
        let tzLong = "Eastern Daylight Time";
        longTzFmt.formatToParts(dateObj).forEach(function (p) {
          if (p.type === "timeZoneName") tzLong = p.value;
        });
        const datePart = map.weekday + " " + map.month + " " + map.day + " " + map.year;
        const timePart = hour + ":" + map.minute + ":" + map.second + " GMT" + sign + hh + mm + " (" + tzLong + ")";
        return {
          dateStr: datePart,
          timeStr: timePart,
          fullStr: datePart + " " + timePart
        };
      }

      OrigDate.prototype.getTimezoneOffset = markNative(function getTimezoneOffset() {
        return getNYOffsetMinutes(this);
      }, "getTimezoneOffset");

      OrigDate.prototype.toString = markNative(function toString() {
        return formatNYStrings(this).fullStr;
      }, "toString");

      OrigDate.prototype.toTimeString = markNative(function toTimeString() {
        return formatNYStrings(this).timeStr;
      }, "toTimeString");

      OrigDate.prototype.toDateString = markNative(function toDateString() {
        return formatNYStrings(this).dateStr;
      }, "toDateString");

      ["toLocaleString", "toLocaleDateString", "toLocaleTimeString"].forEach(function (fnName) {
        const origFn = OrigDate.prototype[fnName];
        if (typeof origFn !== "function") return;
        OrigDate.prototype[fnName] = markNative(function (locales, options) {
          const loc = (locales === undefined) ? TARGET_LOCALE : locales;
          let opts = options;
          if (opts === undefined) {
            opts = { timeZone: TARGET_TZ };
          } else if (opts && typeof opts === "object" && opts.timeZone === undefined) {
            opts = RealmObject.assign({}, opts, { timeZone: TARGET_TZ });
          }
          return origFn.call(this, loc, opts);
        }, fnName);
      });
    } catch (_) {}

    // 4. 拦截 Canvas 宽度法与 FontFaceSet 对中文字体的指纹探测（不影响网页正常显示高清中文）
    function patchCanvasFont(proto) {
      if (!proto) return;
      const desc = RealmObject.getOwnPropertyDescriptor(proto, "font");
      if (!desc || !desc.set || !desc.get) return;
      RealmObject.defineProperty(proto, "font", {
        get: markNative(function font() {
          return desc.get.call(this);
        }, "get font"),
        set: markNative(function font(val) {
          return desc.set.call(this, sanitizeFontString(val));
        }, "set font"),
        configurable: true,
        enumerable: true
      });
    }

    try {
      if (typeof win.CanvasRenderingContext2D !== "undefined") {
        patchCanvasFont(win.CanvasRenderingContext2D.prototype);
      }
      if (typeof win.OffscreenCanvasRenderingContext2D !== "undefined") {
        patchCanvasFont(win.OffscreenCanvasRenderingContext2D.prototype);
      }
    } catch (_) {}

    try {
      if (typeof win.FontFaceSet !== "undefined" && win.FontFaceSet.prototype && win.FontFaceSet.prototype.check) {
        const origCheck = win.FontFaceSet.prototype.check;
        win.FontFaceSet.prototype.check = markNative(function check(font) {
          if (typeof font === "string" && CJK_FONT_RE.test(font)) {
            return false;
          }
          return origCheck.apply(this, arguments);
        }, "check");
      }
    } catch (_) {}

    // 5. 隐藏本机中文 TTS 语音合成列表（防止反欺诈脚本通过 speechSynthesis 识别中文区系统）
    try {
      const synth = win.speechSynthesis;
      const synthProto = (win.SpeechSynthesis && win.SpeechSynthesis.prototype) || (synth && RealmObject.getPrototypeOf(synth));
      if (synthProto && typeof synthProto.getVoices === "function") {
        const origGetVoices = synthProto.getVoices;
        synthProto.getVoices = markNative(function getVoices() {
          const list = origGetVoices.apply(this, arguments);
          if (!Array.isArray(list) || list.length === 0) return list;
          const filtered = list.filter(function (v) {
            const lang = (v && v.lang) || "";
            const name = (v && v.name) || "";
            return !CJK_VOICE_LANG_RE.test(lang) && !CJK_VOICE_NAME_RE.test(name);
          });
          return filtered.length > 0 ? filtered : list;
        }, "getVoices");
      }
    } catch (_) {}

    // 6. 拦截 WebRTC STUN/TURN 外部打洞探测，双重杜绝物理宽带 IP 暴露
    function sanitizeRTCConfig(config) {
      if (!config || typeof config !== "object") {
        return { iceServers: [] };
      }
      const copy = RealmObject.assign({}, config);
      copy.iceServers = [];
      return copy;
    }

    function wrapPeerConnection(OrigPC, name) {
      if (!OrigPC) return OrigPC;
      const WrappedPC = function (config, constraints) {
        return new OrigPC(sanitizeRTCConfig(config), constraints);
      };
      WrappedPC.prototype = OrigPC.prototype;
      RealmObject.setPrototypeOf(WrappedPC, OrigPC);
      return markNative(WrappedPC, name);
    }

    try {
      if (typeof win.RTCPeerConnection !== "undefined") {
        win.RTCPeerConnection = wrapPeerConnection(win.RTCPeerConnection, "RTCPeerConnection");
      }
      if (typeof win.webkitRTCPeerConnection !== "undefined") {
        win.webkitRTCPeerConnection = wrapPeerConnection(win.webkitRTCPeerConnection, "webkitRTCPeerConnection");
      }
    } catch (_) {}

    // 7. 守护同源动态空白 iframe（封堵反欺诈探针同步创建 about:blank 子窗口偷读原生时区与语言）
    try {
      if (win.HTMLIFrameElement && win.HTMLIFrameElement.prototype) {
        const iframeProto = win.HTMLIFrameElement.prototype;
        const cwDesc = RealmObject.getOwnPropertyDescriptor(iframeProto, "contentWindow");
        if (cwDesc && typeof cwDesc.get === "function") {
          RealmObject.defineProperty(iframeProto, "contentWindow", {
            get: markNative(function contentWindow() {
              const subWin = cwDesc.get.call(this);
              try {
                if (subWin && subWin.Date) {
                  applyShieldToRealm(subWin);
                }
              } catch (_) {}
              return subWin;
            }, "get contentWindow"),
            configurable: true,
            enumerable: true
          });
        }
        const cdDesc = RealmObject.getOwnPropertyDescriptor(iframeProto, "contentDocument");
        if (cdDesc && typeof cdDesc.get === "function") {
          RealmObject.defineProperty(iframeProto, "contentDocument", {
            get: markNative(function contentDocument() {
              const subDoc = cdDesc.get.call(this);
              try {
                if (subDoc && subDoc.defaultView && subDoc.defaultView.Date) {
                  applyShieldToRealm(subDoc.defaultView);
                }
              } catch (_) {}
              return subDoc;
            }, "get contentDocument"),
            configurable: true,
            enumerable: true
          });
        }
      }
    } catch (_) {}

    // 8. 守护内联 Blob / Data Web Worker 后台线程，消除主线程与 Worker 线程时区语言不一致警报
    try {
      const OrigWorker = win.Worker;
      const OrigBlob = win.Blob;
      const OrigURL = win.URL;
      if (typeof OrigWorker === "function" && typeof OrigBlob === "function" && OrigURL && typeof OrigURL.createObjectURL === "function") {
        const WrappedWorker = function Worker(scriptURL, options) {
          if (!new.target) {
            throw new TypeError("Failed to construct 'Worker': Please use the 'new' operator.");
          }
          const isModule = options && typeof options === "object" && options.type === "module";
          const urlStr = (scriptURL && typeof scriptURL === "object" && "href" in scriptURL) ? String(scriptURL.href) : String(scriptURL);
          if (!isModule && typeof urlStr === "string" && (urlStr.indexOf("blob:") === 0 || urlStr.indexOf("data:") === 0)) {
            try {
              const bootBlob = new OrigBlob(
                [WORKER_BOOTSTRAP_CODE + "importScripts(" + JSON.stringify(urlStr) + ");\n"],
                { type: "application/javascript" }
              );
              const bootUrl = OrigURL.createObjectURL(bootBlob);
              const instance = options !== undefined ? new OrigWorker(bootUrl, options) : new OrigWorker(bootUrl);
              setTimeout(function () {
                try { OrigURL.revokeObjectURL(bootUrl); } catch (_) {}
              }, 15000);
              return instance;
            } catch (_) {
              // 若目标页存在严格 worker-src CSP 限制，自动平滑回退原生 Worker，确保页面功能零报错
            }
          }
          return options !== undefined ? new OrigWorker(scriptURL, options) : new OrigWorker(scriptURL);
        };
        WrappedWorker.prototype = OrigWorker.prototype;
        RealmObject.setPrototypeOf(WrappedWorker, OrigWorker);
        win.Worker = markNative(WrappedWorker, "Worker");
      }
    } catch (_) {}
  }

  applyShieldToRealm(window);
})();
