/**
 * 华米商城 AI 智能客服 - 可嵌入聊天组件（无构建依赖）
 *
 * 使用方式：
 *   <script>window.HUAMI_CHAT_CONFIG = { server: "https://你的域名" };</script>
 *   <script src="https://你的域名/widget/huami-chat.js" defer></script>
 */
(function () {
  "use strict";

  var CFG = Object.assign(
    { server: "", title: "华米智能客服", subtitle: "AI 客服 · 7×24h 在线", theme: "#ff6b00" },
    window.HUAMI_CHAT_CONFIG || {}
  );
  var API = CFG.server.replace(/\/$/, "") + "/api";
  var SESSION_TTL = 24 * 3600 * 1000;

  var state = {
    sessionId: null,
    pollTimer: null,
    lastSeq: 0,
    escalated: false,
    streaming: false,
    greeting: "",
  };

  // ---------- 工具 ----------
  function $(sel, root) { return (root || document).querySelector(sel); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }
  function lsGet(key) {
    try { return JSON.parse(localStorage.getItem(key)); } catch (e) { return null; }
  }
  function lsSet(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* ignore */ }
  }
  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    // 追加引号转义，防止属性上下文（如 src="..."）被注入
    return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  // 简单换行渲染（防 XSS：先转义再替换换行）
  function renderText(s) { return esc(s).replace(/\n/g, "<br>"); }
  function fmtPrice(p) {
    var n = Number(p);
    return isNaN(n) ? "--" : "¥" + (n % 1 === 0 ? n : n.toFixed(2));
  }

  // ---------- 会话 ----------
  function visitorId() {
    var v = lsGet("huami_visitor_id");
    if (!v) {
      v = "v-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
      lsSet("huami_visitor_id", v);
    }
    return v;
  }

  function ensureSession(done) {
    var cached = lsGet("huami_session");
    if (cached && cached.id && Date.now() - cached.ts < SESSION_TTL) {
      state.sessionId = cached.id;
      // 校验会话仍有效，并同步已有消息的最大 seq（避免轮询重复拉取）
      fetch(API + "/chat/sessions/" + cached.id + "/messages?after_seq=0")
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data) { createSession(done); return; }
          state.lastSeq = 0;
          (data.messages || []).forEach(function (m) {
            state.lastSeq = Math.max(state.lastSeq, m.seq);
          });
          done();
        })
        .catch(function () { done(); });
      return;
    }
    createSession(done);
  }

  function createSession(done) {
    fetch(API + "/chat/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        visitor_id: visitorId(),
        page_url: location.href.slice(0, 480),
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        state.sessionId = data.session_id;
        state.greeting = data.greeting || "";
        lsSet("huami_session", { id: data.session_id, ts: Date.now() });
        done();
      })
      .catch(function () { done(); });
  }

  // ---------- DOM ----------
  function buildUI() {
    if ($("#huami-chat-root")) return;
    var root = el("div");
    root.id = "huami-chat-root";
    root.innerHTML =
      '<button class="hc-fab" aria-label="打开客服"><svg viewBox="0 0 24 24" width="26" height="26" fill="none"><path d="M12 3C7 3 3 6.6 3 11c0 2.2 1 4.2 2.6 5.6L5 21l4-1.6c1 .3 2 .5 3 .5 5 0 9-3.6 9-8S17 3 12 3z" fill="currentColor"/></svg></button>' +
      '<div class="hc-panel" style="display:none">' +
      '  <div class="hc-header">' +
      '    <div class="hc-avatar">华</div>' +
      '    <div class="hc-title-wrap"><div class="hc-title">' + esc(CFG.title) + '</div>' +
      '    <div class="hc-sub"><span class="hc-dot"></span>' + esc(CFG.subtitle) + '</div></div>' +
      '    <button class="hc-icon-btn hc-rate-btn" title="评价本次服务">☆</button>' +
      '    <button class="hc-icon-btn hc-close-btn" title="收起">—</button>' +
      '  </div>' +
      '  <div class="hc-rating" style="display:none"></div>' +
      '  <div class="hc-messages"></div>' +
      '  <div class="hc-quick"></div>' +
      '  <div class="hc-input-wrap">' +
      '    <input class="hc-input" type="text" maxlength="500" placeholder="请输入您的问题…"/>' +
      '    <button class="hc-send">发送</button>' +
      '  </div>' +
      '  <div class="hc-footer">AI 智能回复，仅供参考 · <a class="hc-human-link" href="javascript:;">转人工</a></div>' +
      '</div>';
    document.body.appendChild(root);

    $(".hc-fab").addEventListener("click", togglePanel);
    $(".hc-close-btn").addEventListener("click", togglePanel);
    $(".hc-send").addEventListener("click", sendCurrent);
    $(".hc-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); sendCurrent(); }
    });
    $(".hc-human-link").addEventListener("click", function () { sendText("转人工客服"); });
    $(".hc-rate-btn").addEventListener("click", toggleRating);
    addQuickReplies(["推荐一款运动手表", "帮我查订单", "退换货政策"]);
  }

  function togglePanel() {
    var panel = $(".hc-panel");
    var fab = $(".hc-fab");
    var showing = panel.style.display === "none";
    panel.style.display = showing ? "flex" : "none";
    fab.style.display = showing ? "none" : "flex";
    if (showing) {
      if (!state.sessionId) {
        ensureSession(function () {
          if (state.greeting) addBubble("assistant", state.greeting);
        });
      }
      var input = $(".hc-input");
      if (input && window.innerWidth > 480) input.focus();
      startPolling();
    }
  }

  function addQuickReplies(items) {
    var wrap = $(".hc-quick");
    wrap.innerHTML = "";
    items.forEach(function (text) {
      var chip = el("button", "hc-chip", text);
      chip.addEventListener("click", function () { sendText(text); });
      wrap.appendChild(chip);
    });
  }

  // ---------- 消息渲染 ----------
  function messagesEl() { return $(".hc-messages"); }

  function addBubble(role, content) {
    var wrap = el("div", "hc-row hc-" + role);
    var bubble = el("div", "hc-bubble");
    bubble.innerHTML = renderText(content);
    wrap.appendChild(bubble);
    messagesEl().appendChild(wrap);
    scrollBottom();
    return bubble;
  }

  function addInfo(text) {
    var row = el("div", "hc-row hc-info");
    row.appendChild(el("div", "hc-info-pill", text));
    messagesEl().appendChild(row);
    scrollBottom();
  }

  function addCards(cards) {
    if (!cards || !cards.length) return;
    var wrap = el("div", "hc-row hc-assistant");
    var grid = el("div", "hc-cards");
    cards.forEach(function (c) {
      var card = el("div", "hc-card");
      card.innerHTML =
        (c.image_url ? '<img class="hc-card-img" src="' + esc(c.image_url) + '" alt=""/>' : "") +
        '<div class="hc-card-body">' +
        '  <div class="hc-card-name">' + esc(c.name) + "</div>" +
        '  <div class="hc-card-tags">' + (c.tags || []).slice(0, 3).map(function (t) { return '<span>' + esc(t) + "</span>"; }).join("") + "</div>" +
        '  <div class="hc-card-price">' + fmtPrice(c.price) +
        (c.original_price ? '<del>' + fmtPrice(c.original_price) + "</del>" : "") + "</div>" +
        '  <div class="hc-card-meta">月销 ' + (c.sales || 0) + " · 评分 " + (c.rating || "-") + "</div>" +
        "</div>" +
        '<button class="hc-card-buy">去看看</button>';
      card.querySelector(".hc-card-buy").addEventListener("click", function () {
        trackEvent("product_click", { product_id: c.product_id, name: c.name });
        if (c.url) window.open(c.url, "_blank");
      });
      grid.appendChild(card);
    });
    wrap.appendChild(grid);
    messagesEl().appendChild(wrap);
    scrollBottom();
  }

  function showTyping(text) {
    hideTyping();
    var row = el("div", "hc-row hc-assistant hc-typing-row");
    row.innerHTML =
      '<div class="hc-bubble hc-typing"><span class="hc-typing-dot"></span><span class="hc-typing-dot"></span><span class="hc-typing-dot"></span>' +
      '<span class="hc-typing-text">' + esc(text || "正在思考…") + "</span></div>";
    messagesEl().appendChild(row);
    scrollBottom();
  }
  function setTypingText(text) {
    var t = $(".hc-typing-text");
    if (t) t.textContent = text;
  }
  function hideTyping() {
    var row = $(".hc-typing-row");
    if (row) row.remove();
  }
  function scrollBottom() {
    var m = messagesEl();
    m.scrollTop = m.scrollHeight;
  }

  // ---------- 发送与 SSE ----------
  function sendCurrent() {
    var input = $(".hc-input");
    var text = (input.value || "").trim();
    if (!text || state.streaming) return;
    input.value = "";
    sendText(text);
  }

  function sendText(text) {
    if (state.streaming) return;
    if (!state.sessionId) {
      ensureSession(function () { sendText(text); });
      return;
    }
    addBubble("user", text);
    state.streaming = true;
    showTyping("正在思考…");
    var bubble = null;
    var acc = ""; // 累积流式文本

    fetch(API + "/chat/sessions/" + state.sessionId + "/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text }),
    })
      .then(function (resp) {
        if (!resp.ok || !resp.body) {
          return resp.json().catch(function () { return {}; }).then(function (d) {
            throw new Error(d.detail || "服务暂时不可用");
          });
        }
        var reader = resp.body.getReader();
        var decoder = new TextDecoder("utf-8");
        var buf = "";

        function pump() {
          return reader.read().then(function (r) {
            if (r.done) { finishStream(); return; }
            buf += decoder.decode(r.value, { stream: true });
            var blocks = buf.split("\n\n");
            buf = blocks.pop();
            blocks.forEach(handleBlock);
            return pump();
          });
        }
        return pump();

        function handleBlock(block) {
          if (block.indexOf("data:") !== 0) return;
          var payload;
          try { payload = JSON.parse(block.slice(5).trim()); } catch (e) { return; }
          switch (payload.type) {
            case "status":
              setTypingText({ thinking: "正在思考…", retrieving: "正在查询商品与知识库…", generating: "正在组织回复…", transferring: "正在为您转接人工…" }[payload.stage] || "处理中…");
              break;
            case "delta":
              if (!bubble) { hideTyping(); bubble = addBubble("assistant", ""); }
              acc += payload.content;
              bubble.innerHTML = renderText(acc);
              scrollBottom();
              break;
            case "cards":
              addCards(payload.cards);
              break;
            case "escalated":
              state.escalated = true;
              addInfo("已转接人工，人工客服正在接入");
              break;
            case "notice":
              addInfo(payload.message);
              break;
            case "error":
              addBubble("assistant", payload.message || "服务异常，请稍后重试");
              break;
            case "done":
              finishStream();
              break;
          }
        }
        function finishStream() {
          hideTyping();
          state.streaming = false;
        }
      })
      .catch(function (err) {
        hideTyping();
        state.streaming = false;
        addBubble("assistant", (err && err.message) || "网络异常，请稍后重试");
      });
  }

  // ---------- 转人工后轮询人工回复 ----------
  function startPolling() {
    if (state.pollTimer) return;
    state.pollTimer = setInterval(function () {
      if (!state.sessionId || !state.escalated || state.streaming || document.hidden) return;
      fetch(API + "/chat/sessions/" + state.sessionId + "/messages?after_seq=" + state.lastSeq)
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data) return;
          data.messages.forEach(function (m) {
            state.lastSeq = Math.max(state.lastSeq, m.seq);
            if (m.role === "admin" && !m._shown) {
              addBubble("admin", m.content);
              addInfo("人工客服已接入，正在为您服务");
              state.escalated = true;
            }
          });
        })
        .catch(function () { /* ignore */ });
    }, 3000);
  }

  // ---------- 埋点与评价 ----------
  function trackEvent(type, payload) {
    if (!state.sessionId) return;
    fetch(API + "/chat/sessions/" + state.sessionId + "/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_type: type, payload: payload || {} }),
    }).catch(function () { /* ignore */ });
  }

  function toggleRating() {
    var box = $(".hc-rating");
    if (box.style.display === "block") { box.style.display = "none"; return; }
    box.style.display = "block";
    box.innerHTML = "";
    box.appendChild(el("span", "hc-rating-tip", "为本次服务打分："));
    for (var i = 1; i <= 5; i++) {
      (function (score) {
        var star = el("button", "hc-star", "★");
        star.addEventListener("click", function () {
          fetch(API + "/chat/sessions/" + state.sessionId + "/rating", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rating: score }),
          }).catch(function () { /* ignore */ });
          box.innerHTML = "";
          box.appendChild(el("span", "hc-rating-tip", score >= 4 ? "感谢您的好评！" : "感谢反馈，我们会继续改进！"));
          setTimeout(function () { box.style.display = "none"; }, 2000);
        });
        box.appendChild(star);
      })(i);
    }
  }

  // ---------- 启动 ----------
  function boot() {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", buildUI);
    } else {
      buildUI();
    }
  }
  boot();
})();
