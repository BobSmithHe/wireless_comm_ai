import { defineStore } from "pinia";
import { ref, computed } from "vue";
import api from "../api";

export const useAuthStore = defineStore("auth", () => {
  const user = ref(null);
  const token = ref(localStorage.getItem("access_token") || "");
  const isLoggedIn = computed(() => !!token.value);

  async function login(username, password) {
    const res = await api.post("/api/auth/login", { username, password });
    token.value = res.data.access_token;
    localStorage.setItem("access_token", res.data.access_token);
    localStorage.setItem("refresh_token", res.data.refresh_token);
    await fetchUser();
    return res;
  }

  async function register(username, email, password) {
    return await api.post("/api/auth/register", { username, email, password });
  }

  async function fetchUser() {
    try {
      const res = await api.get("/api/auth/me");
      user.value = res.data;
    } catch {
      logout();
    }
  }

  function logout() {
    token.value = "";
    user.value = null;
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  }

  return { user, token, isLoggedIn, login, register, fetchUser, logout };
});

export const useCodeStore = defineStore("code", () => {
  const pendingCode = ref("");
  const executionResult = ref(null);

  function setCode(code) {
    pendingCode.value = code;
  }

  function setResult(result) {
    executionResult.value = result;
  }

  function clearResult() {
    executionResult.value = null;
  }

  return { pendingCode, executionResult, setCode, setResult, clearResult };
});
