"""角色定义与权限矩阵：
  super_admin  超级管理员：全权限（账号/权限/全局配置）
  admin        运营管理员：商品/知识库/话术配置/数据看板
  team_leader  客服主管：会话池分配 + 质检 + 坐席绩效
  agent        在线客服：接待人工会话、回复、交还AI、转接
  analyst      数据分析师：看板只读
"""
from __future__ import annotations

from dataclasses import dataclass

ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"
ROLE_TEAM_LEADER = "team_leader"
ROLE_AGENT = "agent"
ROLE_ANALYST = "analyst"

ALL_ROLES = (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEADER, ROLE_AGENT, ROLE_ANALYST)

# 可查看：商品/知识库/配置/会话 等运营后台接口（含写接口的 READ 权限）
ROLE_CAN_VIEW = (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEADER, ROLE_AGENT)
# 看板/聊天记录等只读分析类接口：analyst + 所有运营角色
ROLE_CAN_ANALYZE = (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEADER, ROLE_AGENT, ROLE_ANALYST)
# 可写配置：商品/知识库/话术/敏感词
ROLE_CAN_CONFIGURE = (ROLE_SUPER_ADMIN, ROLE_ADMIN)
# 可接待人工会话
ROLE_CAN_AGENT = (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEADER, ROLE_AGENT)
# 可质检
ROLE_CAN_QA = (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEADER)
# 可管理账号/权限
ROLE_CAN_USER_ADMIN = (ROLE_SUPER_ADMIN,)


@dataclass(frozen=True)
class RoleDesc:
    key: str
    display: str
    can_view: bool
    can_configure: bool
    can_agent: bool
    can_qa: bool
    can_user_admin: bool


ROLE_DESC: list[RoleDesc] = [
    RoleDesc(ROLE_SUPER_ADMIN, "超级管理员", True, True, True, True, True),
    RoleDesc(ROLE_ADMIN, "运营管理员", True, True, True, True, False),
    RoleDesc(ROLE_TEAM_LEADER, "客服主管", True, False, True, True, False),
    RoleDesc(ROLE_AGENT, "在线客服", True, False, True, False, False),
    RoleDesc(ROLE_ANALYST, "数据分析师", False, False, False, False, False),
]


def has_any_role(role: str, allowed: tuple[str, ...]) -> bool:
    # super_admin 天然拥有所有权限
    return role == ROLE_SUPER_ADMIN or role in allowed


def role_display(role: str) -> str:
    for r in ROLE_DESC:
        if r.key == role:
            return r.display
    return role
