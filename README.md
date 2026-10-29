# RoleMesh 业务后端本地开发版

当前是本机开发版，没有正式登录、真实用户授权管理、发布编辑界面或公网部署。当前本地 SQLite 已导入 23 份经同意的正式问卷画像；没有导入真实姓名、微信号、IP 等直接身份信息。由于服务没有正式鉴权，请勿公开数据库文件或把服务暴露到公网。算法契约版本 0.1.0；部分问卷标签尚待团队统一编码。

## 环境和启动

当前实测 Python 3.14，FastAPI + Uvicorn + Python 自带 SQLite。数据库文件固定在项目根目录，不提交 Git。依赖包含相对路径的本地算法模块，安装时请在项目根目录运行。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python database.py
python seed_demo.py
python seed_projects.py
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

已有 .venv 可直接激活，无需重复创建。初始化和种子脚本可重复执行，已有记录不会被重置。数据库故障或契约错误不会被伪装为空推荐。

## 现有接口

所有业务接口均为 demo，无正式鉴权，只操作固定虚构用户或 is_demo=1 项目。

| 方法 | 地址 | 用途 |
| --- | --- | --- |
| GET | /health | 健康检查 |
| GET | /demo/profile | 读取固定虚构画像 |
| PATCH | /demo/profile/hours | 修改周时间，范围 0—168，递增画像版本 |
| GET | /demo/projects?limit=20&offset=0 | 虚构项目列表，limit 1—100，offset ≥0 |
| GET | /demo/projects/{project_id} | 项目详情与岗位要求 |
| GET | /demo/matches | 数据库画像对数据库虚构岗位，实时计算 |
| GET | /docs | Swagger 测试页 |
| GET | /openapi.json | 机器可读接口说明 |

响应使用 data 包装；部分演示接口附 meta 标明数据来源。缺少记录为 404，非法请求为 422，匹配存储或契约异常为 500。无候选岗位时返回 200 和空列表。

## 数据结构与迁移

users → talent_profiles：每个用户一个主画像。users → projects → project_roles：项目关联负责人，岗位关联项目。

画像 JSON 保存结构化匹配字段；项目保存领域，岗位保存角色、要求和版本。openings_remaining 由 required_count 减 filled_count 计算，不把招募总数直接当剩余名额。项目阶段 stage 与岗位招募状态 recruitment_status 分开。

初始用户画像建表在 database.py；新增项目岗位建表在 migrations/001_projects_roles.sql；问卷专属扩展字段建表在 migrations/002_survey_import_details.sql。schema_migrations 记录已执行版本。正式问卷使用 import_survey.py 导入：匹配 DTO 写入 talent_profiles，问卷专属答案单独写入 survey_profile_details；真实姓名、微信号、答题时间、IP、UA、Referrer 不导入。seed_projects.py 只从队友包的虚构样例首次导入，运行时匹配不再读取该样例文件。

本地导入的 23 份画像不会被现有 `/demo/*` 接口返回；这些接口仍只访问虚构演示数据。为避免重复导入，导入脚本使用稳定的问卷记录号生成用户和画像 ID，重复执行会跳过已有记录。导入前可加 `--dry-run` 只做检查：

```bash
python import_survey.py "/path/to/28217843_202610161909197743.csv" --dry-run
python import_survey.py "/path/to/28217843_202610161909197743.csv"
```

后续写接口修改岗位条件或项目领域时，必须递增受影响岗位版本；目前发布编辑接口尚未实现。演示不自动分配成员，filled_count 尚无成员流程维护接口。

## 算法接入

vendor/RoleMesh_matching_v0_1 保留队友交付源码；project_store.py 把数据库记录转成算法 DTO。main.py 调用 rolemesh_matching.integration.run_request，不改算法评分。GTE 未安装、未启用。

演示画像从 SQLite 读取，岗位也来自 SQLite。响应包含 meta.roles_source=sqlite；每次计算返回输入版本，不缓存。

## 验证

```bash
python -m unittest discover -s backend_tests -v
cd vendor/RoleMesh_matching_v0_1
python -m unittest discover -s tests -v
```

后端 HTTP 测试使用临时数据库，不修改项目现有 rolemesh.db。算法包已有 40 项测试；新增后端测试 12 项。

问卷画像已通过当前算法契约校验，但技能、角色和领域的代码词典覆盖不完整；对应字段在画像中标记为 `unknown`，不会伪装成已确认的匹配标签。需要与算法和前端同学统一标签代码后，才能完整用于正式匹配。

## 待实现

正式登录与权限、完整画像写接口、项目和岗位发布编辑、前端真实请求接入、持续问卷更新及授权撤回流程、申请邀请成团、会员预留与支付、生产部署。

.local-copy-recovery 为误复制文件的本地恢复备份，不提交 Git。真实微信答卷、密钥和数据库文件不要加入代码仓库或交接压缩包。
