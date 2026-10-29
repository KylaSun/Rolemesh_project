本轮更新：先看“统一契约与联调.html”。工程契约版本0.1.0，团队确认状态：待祺与婕核对。

RoleMesh V0.1 匹配模块交付包

先打开：先看这里.html；再看：对接说明.html。

交付内容
- rolemesh_matching：可由Kyla直接导入的Python函数，不另建网络API。
- demo.py + examples：完整的输入、实际运行输出、AHP权重。
- frontend/bridge.mjs：把后端输出转换成现有前端展示形状的适配器，不会自行算分。
- contracts：完整输入JSON Schema、字段字典、示例词表。
- tests：硬条件、缺失信息、AHP、语义接入和排序验证。

运行要求
Python 3.10或以上。规则计算本身使用标准库；统一契约入口需要jsonschema。解压后在此文件夹打开终端：
  python -m pip install -r requirements.txt
  python demo.py
  python -m unittest discover -s tests -v
如有Node.js，还可运行：
  node frontend/test_bridge.mjs

Kyla接入
  from rolemesh_matching.integration import run_request, ContractError
  result = run_request(request)
request必须包含contract_version、profile和roles。输入输出都会按同一份JSON Schema校验。
后端负责身份权限、数据库读取、字段转换、候选过滤、缓存失效和API；本模块不处理登录、数据库连接、前端请求。

启用真实GTE（可选，不是skill安装）
  python -m venv .venv
Windows激活：.venv\Scripts\activate
  python -m pip install -r requirements-gte.txt
  python download_model.py --destination models/gte
记录下载脚本打印的revision，之后：
  python demo_gte.py --model-path models/gte --revision 下载时打印的提交号
大模型权重不随本包提供；这一步需要网络和模型存储空间。官方模型包含自定义Python代码，本包按官方方式加载，实际部署应固定并审阅模型提交。依赖范围不是经过真实GTE验证的锁文件。

语义处理边界
原文放raw_fields，结构化字段保持DOCX定义。GTE只辅助软性技能/领域评分，不补技能等级，不把想学认定为掌握，不代替硬条件。否定词拦截只是保守启发式，不能保证理解所有否定、语境和意愿。语义阈值0.4/0.8为未校准初值。
没有模型且需要语义评分时，不会伪造GTE得分；返回provisional和缺失项，match为null。

评分规则
四项：加分技能、角色意向、领域兴趣、期望时间。AHP矩阵和主观判断见说明。
未设置或无偏好项剔除后归一化。配置了但信息缺失的项不生成正式总分，只返回provisional_match与coverage；这样避免缺项导致正式高分。
项目分取同项目正式岗位中的最高分。只推荐、不自动分配。

当前状态
请看docs/validation.json。规则测试、示例运行与前端适配器测试均应有明确实测记录。真实GTE推理、原页面浏览器联调和数据库接入另列，不能把替身测试当真实模型评估。

不需要额外安装Codex skill。本包本身就是Codex生成的代码与说明。skill是帮助生成/审阅材料的工具，不是匹配模块运行依赖。
