import { defineConfig } from '@playwright/test';
const baseURL=process.env.PLAYWRIGHT_BASE_URL||'http://127.0.0.1:5173';
const useExternalServer=Boolean(process.env.PLAYWRIGHT_BASE_URL);
export default defineConfig({
  testDir:'./tests', fullyParallel:false, workers:1, timeout:45000,
  use:{baseURL,viewport:{width:1600,height:1000},headless:true,launchOptions:{args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']},trace:'retain-on-failure'},
  webServer:useExternalServer?undefined:[{command:'python ../backend/app.py',url:'http://127.0.0.1:8000/health',reuseExistingServer:true},{command:'npm run dev',url:'http://127.0.0.1:5173',reuseExistingServer:true}],
});
