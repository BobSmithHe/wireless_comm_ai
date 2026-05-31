import { createRouter, createWebHistory } from "vue-router";

const routes = [
  { path: "/login", name: "Login", component: () => import("../views/Login.vue") },
  { path: "/register", name: "Register", component: () => import("../views/Register.vue") },
  { path: "/", name: "Home", component: () => import("../views/Home.vue"), meta: { auth: true } },
  { path: "/chat", name: "Chat", component: () => import("../views/Chat.vue"), meta: { auth: true } },
  { path: "/knowledge", name: "Knowledge", component: () => import("../views/Knowledge.vue"), meta: { auth: true } },
  { path: "/code", name: "CodeEditor", component: () => import("../views/CodeEditor.vue"), meta: { auth: true } },
  { path: "/papers", name: "Papers", component: () => import("../views/Papers.vue"), meta: { auth: true } },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem("access_token");
  if (to.meta.auth && !token) {
    next("/login");
  } else if ((to.path === "/login" || to.path === "/register") && token) {
    next("/");
  } else {
    next();
  }
});

export default router;
