const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = {
  devServer: {
    port: 5173,
    setupMiddlewares: (middlewares, devServer) => {
      // SSE stream endpoint — no buffering
      devServer.app.use(
        "/api/chat/stream",
        createProxyMiddleware({
          target: "http://localhost:8765",
          changeOrigin: true,
          proxyRes: (proxyRes) => {
            delete proxyRes.headers["content-length"];
          },
        })
      );
      // All other API calls
      devServer.app.use(
        "/api",
        createProxyMiddleware({
          target: "http://localhost:8765",
          changeOrigin: true,
        })
      );
      return middlewares;
    },
  },
};
