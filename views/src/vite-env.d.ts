/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 生产环境 API 基地址；开发环境默认走 Vite 代理 */
  readonly VITE_API_BASE?: string;
  /** 开发代理目标（默认 http://localhost:8000） */
  readonly VITE_API_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
