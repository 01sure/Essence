import { createRouter, createWebHashHistory } from "vue-router";
import { useAuthStore } from "../stores/auth";

const routes = [
  { path: "/login", component: () => import("../views/Login.vue") },
  {
    path: "/",
    component: () => import("../layouts/AdminLayout.vue"),
    redirect: "/dashboard",
    children: [
      {
        path: "dashboard",
        component: () => import("../views/Dashboard.vue"),
        meta: { title: "数据看板" },
      },
      {
        path: "workbench",
        component: () => import("../views/AgentWorkbench.vue"),
        meta: { title: "坐席工作台", requires: "can_agent" },
      },
      {
        path: "chat-window",
        component: () => import("../views/ChatWindow.vue"),
        meta: { title: "智能客服窗口", requires: "can_agent" },
      },
      {
        path: "sessions",
        component: () => import("../views/SessionList.vue"),
        meta: { title: "会话管理", requires: "can_agent" },
      },
      {
        path: "after-sale",
        component: () => import("../views/AfterSale.vue"),
        meta: { title: "售后工单", requires: "can_agent" },
      },
      {
        path: "quality",
        component: () => import("../views/QualityScore.vue"),
        meta: { title: "质检中心", requires: "can_qa" },
      },
      {
        path: "kb",
        component: () => import("../views/KbManage.vue"),
        meta: { title: "知识库", requires: "can_configure" },
      },
      {
        path: "products",
        component: () => import("../views/ProductManage.vue"),
        meta: { title: "商品管理", requires: "can_configure" },
      },
      {
        path: "prompts",
        component: () => import("../views/PromptConfig.vue"),
        meta: { title: "话术配置", requires: "can_configure" },
      },
      {
        path: "users",
        component: () => import("../views/UserAdmin.vue"),
        meta: { title: "用户管理", requires: "can_user_admin" },
      },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

const router = createRouter({ history: createWebHashHistory(), routes });

router.beforeEach((to) => {
  const token = localStorage.getItem("huami_token");
  if (to.path !== "/login" && !token) return "/login";
  if (to.path === "/login" && token) return "/";
  if (to.meta?.requires) {
    const auth = useAuthStore();
    const user = auth.user || JSON.parse(localStorage.getItem("huami_user") || "null");
    if (!user || !user[to.meta.requires]) {
      // 分析师登录后默认跳看板；其他角色跳工作台
      if (user?.role === "analyst") return "/dashboard";
      if (user?.can_agent) return "/workbench";
      return "/dashboard";
    }
  }
  return true;
});

export default router;
