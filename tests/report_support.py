"""Shared medical report inputs for behavior tests."""




def report_payload(*, result="65 U/L", report_type="检验报告"):
    base = {
        "report_type": report_type,
        "report_name": "肝功能",
        "report_time": "2026-08-08T08:30:00+08:00",
        "source_kind": "screenshot",
        "institution_name": "测试医院",
        "lab_test_results": [],
        "examination_report": None,
        "pathology_report": None,
        "surgery_report": None,
        "other_report": None,
    }
    if report_type == "检验报告":
        base["lab_test_results"] = [
            {
                "item_id": "item-alt",
                "item_name_zh": "丙氨酸氨基转移酶",
                "aliases": ["谷丙转氨酶"],
                "category_name": "肝功能",
                "result_text": result,
                "reference_text": "9-50 U/L",
                "flag_text": "偏高",
            }
        ]
    else:
        base["report_name"] = "腹部超声"
        base["source_kind"] = "pdf"
        base["examination_report"] = {
            "exam_name": "腹部超声",
            "clinical_diagnosis": None,
            "exam_method": "超声",
            "exam_findings": "未见明显异常",
            "exam_diagnosis": "未见明显异常",
        }
    return base
