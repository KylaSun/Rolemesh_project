# 本地后端与可选匹配适配入口
main.py保留上游本地演示；没有正式身份系统，不可作为已认证生产服务公开运行。
安装请在交付根目录执行python -m pip install -r requirements.txt，匹配实现只有../matching一份。
vendor/RoleMesh_matching_v0_1/examples/input.json仅保留原seed程序需要的合成样例，不含第二套算法。
matching_adapter.py是本次新增的回调注入router，未自动挂载到main.app。集成方式见../docs/INTEGRATION_GUIDE.md。
openapi.json为上游原快照；新增router文档见../verification/adapter_openapi.json。
真实问卷导入和生产数据库不在本次执行范围。上游import_survey.py原样保留，其重复导入行为需要后端单独核验，不能以历史README描述代替测试。
