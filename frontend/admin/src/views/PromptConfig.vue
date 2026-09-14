<template>
  <el-card shadow="never">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="品牌人设" name="persona">
        <p class="tip">定义 AI 客服的身份、语气与品牌背景。会注入到每轮对话的系统提示词中。</p>
        <el-input v-model="editors.persona" type="textarea" :rows="6" />
        <div class="actions"><el-button type="primary" @click="save('persona')">保存</el-button></div>
      </el-tab-pane>

      <el-tab-pane label="销售话术规范" name="sales_playbook">
        <p class="tip">售前咨询时强制遵循的销售策略与合规红线（FABE、推荐数量、引导下单等）。</p>
        <el-input v-model="editors.sales_playbook" type="textarea" :rows="10" />
        <div class="actions"><el-button type="primary" @click="save('sales_playbook')">保存</el-button></div>
      </el-tab-pane>

      <el-tab-pane label="意图话术规则" name="intent_rules">
        <p class="tip">不同意图下的差异化话术要求（JSON 格式，键：pre_sale / order_service / complaint / chitchat / human_request）。</p>
        <el-input v-model="intentRulesText" type="textarea" :rows="14" />
        <div class="actions"><el-button type="primary" @click="saveIntentRules">保存</el-button></div>
      </el-tab-pane>

      <el-tab-pane label="提示语与敏感词" name="misc">
        <el-form label-width="140px" style="max-width: 720px">
          <el-form-item label="开场白">
            <el-input v-model="editors.opening_greeting" type="textarea" :rows="4" />
          </el-form-item>
          <el-form-item label="转人工提示语">
            <el-input v-model="editors.human_handoff_message" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="AI 失败兜底语">
            <el-input v-model="editors.fallback_message" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="敏感词拦截回复">
            <el-input v-model="editors.sensitive_reply" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="敏感词列表">
            <el-input v-model="sensitiveWordsText" type="textarea" :rows="3" placeholder="逗号分隔。命中后自动拦截并转人工" />
          </el-form-item>
        </el-form>
        <div class="actions">
          <el-button type="primary" @click="saveMisc">保存全部</el-button>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import api from "../api";

const activeTab = ref("persona");
const editors = reactive({
  persona: "",
  sales_playbook: "",
  opening_greeting: "",
  human_handoff_message: "",
  fallback_message: "",
  sensitive_reply: "",
});
const intentRulesText = ref("{}");
const sensitiveWordsText = ref("");
// 每键保存读取时的 updated_at 用于乐观锁
const updateTokens = reactive({});

onMounted(async () => {
  const { data } = await api.get("/admin/settings");
  data.items.forEach(({ key, value, updated_at }) => {
    updateTokens[key] = updated_at || null;
    if (key === "intent_rules") intentRulesText.value = JSON.stringify(value ?? {}, null, 2);
    else if (key === "sensitive_words") sensitiveWordsText.value = (value ?? []).join("，");
    else if (key in editors) editors[key] = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  });
});

async function save(key) {
  const { data } = await api.put(`/admin/settings/${key}`, {
    value: editors[key],
    if_match_updated_at: updateTokens[key] || null,
  });
  if (data?.updated_at) updateTokens[key] = data.updated_at;
  ElMessage.success("已保存，30 秒内生效（缓存刷新）");
}

async function saveIntentRules() {
  try {
    const value = JSON.parse(intentRulesText.value);
    const { data } = await api.put("/admin/settings/intent_rules", {
      value,
      if_match_updated_at: updateTokens.intent_rules || null,
    });
    if (data?.updated_at) updateTokens.intent_rules = data.updated_at;
    ElMessage.success("已保存");
  } catch (e) {
    if (e instanceof SyntaxError) ElMessage.error("JSON 格式错误，请检查");
  }
}

async function saveMisc() {
  const keys = ["opening_greeting", "human_handoff_message", "fallback_message", "sensitive_reply"];
  for (const k of keys) {
    const { data } = await api.put(`/admin/settings/${k}`, {
      value: editors[k],
      if_match_updated_at: updateTokens[k] || null,
    });
    if (data?.updated_at) updateTokens[k] = data.updated_at;
  }
  const words = sensitiveWordsText.value.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
  const { data } = await api.put("/admin/settings/sensitive_words", {
    value: words,
    if_match_updated_at: updateTokens.sensitive_words || null,
  });
  if (data?.updated_at) updateTokens.sensitive_words = data.updated_at;
  ElMessage.success("已保存");
}
</script>

<style scoped>
.tip { color: #999; font-size: 13px; margin-bottom: 10px; }
.actions { margin-top: 14px; }
</style>
