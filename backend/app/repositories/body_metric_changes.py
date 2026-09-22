"""Stable business field locations for body records and their attachments."""

import json


def _part(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def body_record_snapshot(row, files=()):
    """Read a physical body_records row plus its body_files rows, without I/O."""
    value = json.loads(row["payload"])
    fields = {f"/{_part(key)}": item for key, item in value.items() if key != "data"}
    data = value["data"]
    if value["kind"] == "measurement":
        prefix = f"/data/metrics/{_part(value['metric'])}"
        fields.update({f"{prefix}/{_part(key)}": item for key, item in data.items()})
    else:
        for key, item in data.items():
            if key in {"foods", "stages"}:
                identity = "food_id" if key == "foods" else "stage_id"
                for detail in item:
                    prefix = f"/data/{key}/{_part(detail[identity])}"
                    fields.update({f"{prefix}/{_part(name)}": nested for name, nested in detail.items()})
            else:
                fields[f"/data/{_part(key)}"] = item
    fields.update({f"/files/{_part(file['file_id'])}": file["file_id"] for file in files})
    return fields


def body_file_snapshot(row):
    """Preserve attachment identity and integrity metadata without copying bytes."""
    return {**{f"/{key}": row[key] for key in ("record_id", "filename", "mime_type", "sha256")},
            "/size_bytes": len(row["image_bytes"])}


def body_change_context(row):
    value = json.loads(row["payload"])
    return {"member_id": row["member_id"], "kind": value["kind"], "metric": value["metric"],
            "starts_at": value["starts_at"], "ends_at": value["ends_at"],
            "timezone": value["timezone"], "precision": value["precision"],
            "source": value["source"], "device": value["device"], "origin": value["origin"],
            "source_input": json.loads(row["source_payload"])}
