import { defineStore } from "pinia";
import api from "../api";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    token: localStorage.getItem("huami_token") || "",
    user: JSON.parse(localStorage.getItem("huami_user") || "null"),
  }),
  actions: {
    async login(username, password) {
      const { data } = await api.post("/admin/auth/login", { username, password });
      this.token = data.token;
      this.user = data.user;
      localStorage.setItem("huami_token", data.token);
      localStorage.setItem("huami_user", JSON.stringify(data.user));
    },
    logout() {
      this.token = "";
      this.user = null;
      localStorage.removeItem("huami_token");
      localStorage.removeItem("huami_user");
    },
  },
});
