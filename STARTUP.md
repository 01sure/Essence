# 项目启动说明

## 1. 后端启动

```powershell
cd "D:\code\自主开发\ServSales AI\backend"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 2. 前端启动

```powershell
cd "D:\code\自主开发\ServSales AI\frontend\admin"
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

## 3. Docker 启动（推荐）

```powershell
cd "D:\code\自主开发\ServSales AI"
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
docker compose up -d --build
```

## 4. 访问地址

- 管理后台: http://localhost/admin
- 聊天组件: http://localhost/widget/demo.html
- 后端健康检查: http://localhost/api/health

## 5. 常见错误

如果出现 `npm ERR! code ENOENT`，通常是因为命令在错误目录执行，应该先进入 `frontend/admin` 目录，再执行 `npm install`。
如果出现 `No module named uvicorn`，应该在 `backend` 目录执行 `pip install -r requirements.txt`，并使用项目自带虚拟环境。
