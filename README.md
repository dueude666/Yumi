# Yumi

Yumi 是一款面向大学学习场景的离线 AI 工具，基于 PyTorch 生态构建，支持本地部署与数据不出域。

当前版本聚焦 5 个能力：
- 课程资料库（本地文本导入与分片）
- 一键总结笔记（摘要 + 关键词）
- 本地问答（只检索本地资料并返回来源）
- 课堂内容整理（先支持文本，后续可接入 ASR/OCR）
- 期末周时间表分析（自动生成学习事件）

## 1. 环境要求
- Python 3.10+
- 标准 PyTorch 环境

## 2. 安装依赖
```bash
pip install -r requirements.txt
```

## 3. 启动方式
1. 初始化数据库
```bash
python scripts/init_db.py
```

2. 启动 API
```bash
python scripts/run_api.py
```

3. 启动 UI（另开终端）
```bash
python scripts/run_ui.py
```

默认地址：
- API: `http://127.0.0.1:8000`
- UI: `http://127.0.0.1:8501`

## 4. 期末周排程逻辑
单门课程优先级：

`priority = 0.35*紧急度 + 0.30*(1-掌握度) + 0.20*难度 + 0.15*学分权重`

- 深度学习块：默认 90 分钟
- 回顾复盘块：默认 30 分钟
- 机动缓冲：默认保留 20%
- 固定复盘点：`D-7 / D-3 / D-1`

## 5. 核心 API
- `POST /courses` 创建课程
- `POST /courses/{course_id}/materials` 导入资料文本并分片
- `POST /notes/summarize` 生成笔记摘要
- `POST /qa/ask` 本地问答
- `POST /planner/exams` 新增考试
- `PUT /planner/availability` 更新每周可学习时段
- `POST /planner/final-week-plan` 生成期末周学习事件
- `GET /planner/events?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` 查询事件

## 6. 数据库表
`courses`, `notes`, `document_chunks`, `exams`, `availability_slots`, `study_events`

## 7. 后续可扩展
- PDF/OCR 导入
- 离线语音转写（ASR）
- 向量检索（FAISS embedding）
- 课程知识图谱

