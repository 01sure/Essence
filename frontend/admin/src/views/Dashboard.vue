<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="6" v-for="card in statCards" :key="card.label">
        <el-card shadow="hover">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="14">
        <el-card shadow="hover">
          <template #header>近 7 日会话趋势</template>
          <div ref="trendRef" style="height: 300px"></div>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="hover">
          <template #header>意图分布（近 7 日）</template>
          <div ref="pieRef" style="height: 300px"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row style="margin-top: 16px">
      <el-col :span="24">
        <el-card shadow="hover">
          <template #header>商品点击 Top5（近 7 日，转化信号）</template>
          <el-table :data="stats.top_clicked_products || []" size="small">
            <el-table-column type="index" label="#" width="60" />
            <el-table-column prop="product" label="商品" />
            <el-table-column prop="count" label="点击次数" width="120" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import * as echarts from "echarts";
import api from "../api";

const stats = ref({});
const trendRef = ref(null);
const pieRef = ref(null);
let trendChart = null;
let pieChart = null;

const INTENT_LABELS = {
  pre_sale: "售前咨询", order_service: "订单售后", complaint: "投诉",
  chitchat: "闲聊", human_request: "转人工", unknown: "未知",
};

const statCards = computed(() => {
  const s = stats.value;
  return [
    { label: "今日会话", value: s.today_sessions ?? "-", color: "#ff6b00" },
    { label: "今日消息数", value: s.today_messages ?? "-", color: "#409eff" },
    { label: "AI 解决率", value: s.ai_resolution_rate != null ? (s.ai_resolution_rate * 100).toFixed(1) + "%" : "-", color: "#67c23a" },
    { label: "转人工率", value: s.escalation_rate != null ? (s.escalation_rate * 100).toFixed(1) + "%" : "-", color: "#f56c6c" },
  ];
});

function renderCharts() {
  const s = stats.value;
  if (trendRef.value) {
    trendChart = trendChart || echarts.init(trendRef.value);
    trendChart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 40, right: 20, top: 20, bottom: 30 },
      xAxis: { type: "category", data: (s.session_trend || []).map((i) => i.date.slice(5)) },
      yAxis: { type: "value", minInterval: 1 },
      series: [{
        type: "line", smooth: true, data: (s.session_trend || []).map((i) => i.count),
        areaStyle: { opacity: 0.15 }, itemStyle: { color: "#ff6b00" },
      }],
    });
  }
  if (pieRef.value) {
    pieChart = pieChart || echarts.init(pieRef.value);
    pieChart.setOption({
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [{
        type: "pie", radius: ["38%", "62%"],
        data: (s.intent_distribution || []).map((i) => ({
          name: INTENT_LABELS[i.intent] || i.intent, value: i.count,
        })),
      }],
    });
  }
}

onMounted(async () => {
  const { data } = await api.get("/admin/dashboard");
  stats.value = data;
  renderCharts();
  window.addEventListener("resize", resizeCharts);
});
function resizeCharts() { trendChart?.resize(); pieChart?.resize(); }
onUnmounted(() => { window.removeEventListener("resize", resizeCharts); trendChart?.dispose(); pieChart?.dispose(); });
</script>

<style scoped>
.stat-label { color: #999; font-size: 13px; }
.stat-value { font-size: 30px; font-weight: 700; margin-top: 8px; }
</style>
