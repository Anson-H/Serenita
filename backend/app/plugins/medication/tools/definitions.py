"""Assemble the medication plugin's model-visible tools."""

from backend.app.plugins.medication.constants import LABELS, NAMES
from backend.app.plugins.medication.tools.medication_tools import MedicationTool
from backend.app.plugins.medication.tools.parameters import (
    medication_plan_parameters,
    create_parameters,
    medication_information_parameters,
    medication_sources_parameters,
    identity_parameters,
    update_parameters,
)
from backend.app.schemas.medication import MODELS


def create_tools(*, runtime_context):
    if not runtime_context.member_id:
        return []
    result = []

    def add(name, description, schema, operation, kind=None):
        result.append(
            MedicationTool(
                runtime_context, name, description, schema, operation, kind
            )
        )

    for kind, model in MODELS.items():
        name, label = NAMES[kind], LABELS[kind]
        if kind == "medication":
            add(
                "read_medication_information",
                "读取当前成员中匹配的药品信息，返回已保存的药品资料。",
                medication_information_parameters(),
                "information",
                kind,
            )
            add(
                "read_medication_inventory",
                "读取当前成员的药品库存，返回库存批次、数量和有效期。",
                identity_parameters(kind),
                "inventory",
                kind,
            )
        elif kind == "plan":
            add(
                "read_" + name,
                f"读取当前成员的{label}，返回已保存内容。",
                medication_plan_parameters(),
                "catalog",
                kind,
            )
        elif kind == "batch":
            add(
                "read_" + name,
                f"读取当前成员的{label}，返回已保存内容。",
                identity_parameters(kind),
                "read",
                kind,
            )
        if kind == "medication":
            add(
                "add_medication_sources",
                "向药品目录中的一项药品补充原件，返回保存结果。",
                medication_sources_parameters(),
                "sources",
                kind,
            )
            add(
                "create_medication",
                "向药品目录添加一项药品，返回创建结果。",
                create_parameters(kind, model),
                "create",
                kind,
            )
            continue
        add(
            "create_" + name,
            f"为当前成员创建{label}，返回创建结果。",
            create_parameters(kind, model),
            "create",
            kind,
        )
        add(
            "update_" + name,
            f"更新当前成员的{label}，返回更新后的内容。",
            update_parameters(kind, model),
            "update",
            kind,
        )
        add(
            "delete_" + name,
            f"删除当前成员的{label}，返回删除结果。",
            identity_parameters(kind),
            "delete",
            kind,
        )
    return result
