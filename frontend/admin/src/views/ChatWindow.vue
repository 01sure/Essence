<template>
  <div class="chat-window-page">
    <div class="chat-window-header">
      <div>
        <h2>智能客服与销售会话窗口</h2>
        <p>这里展示与商城页面一致的客服聊天组件，便于后台直接预览与调试。</p>
      </div>
    </div>
    <div class="chat-window-frame-wrap">
      <iframe
        title="智能客服聊天组件"
        class="chat-window-frame"
        src="/widget/demo.html"
        sandbox="allow-scripts allow-same-origin allow-forms"
      />
    </div>
  </div>
</template>

<style scoped>
.chat-window-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chat-window-header {
  background: #fff;
  border-radius: 12px;
  padding: 18px 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.chat-window-header h2 {
  margin: 0 0 6px;
  font-size: 20px;
  color: #1f2430;
}

.chat-window-header p {
  margin: 0;
  color: #667085;
  font-size: 14px;
}

.chat-window-frame-wrap {
  flex: 1;
  min-height: 680px;
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.chat-window-frame {
  width: 100%;
  height: 100%;
  min-height: 680px;
  border: none;
  background: #f7f9fc;
}
</style>
