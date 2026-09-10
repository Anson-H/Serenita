import { navigationLabels } from "../../components/navigationLabels";
import { ContentDialog } from "../../components/ContentDialog";
import { GroupedList } from "../../components/GroupedList";
import { CheckIcon } from "../../components/icons";
import { SelectPopover } from "../../components/SelectPopover";
import { useId, useState, type ReactNode } from "react";
import {
  attachFoodFile,
  removeFoodFile,
  bodyBase,
  saveRecord,
  deleteRecord,
  type BodyInput,
  type BodyRecord,
  type Catalog,
  type Food,
  type MetricData,
} from "../../api/bodyMetricApi";
import { DateTimePicker } from "../../components/DateTimePicker";
import { recordLabel, time } from "./bodyMetricPresentation";
import { apiUrl } from "../../api/request";
import { localDateTimeInputValue } from "../../utils/localTime";
export function BodyTimeField({
  label,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string | null;
  onChange: (v: string | null) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false),
    [draft, setDraft] = useState("");
  return (
    <div className="field-row">
      <span>{label}</span>
      {open ? (
        <DateTimePicker
          disabled={disabled}
          ariaLabel={label}
          mode="date-time"
          value={draft}
          onChange={setDraft}
          onCancel={() => setOpen(false)}
          onCommit={(v) => {
            onChange(
              v === (value ? localDateTimeInputValue(new Date(value)) : "")
                ? value
                : v
                  ? new Date(v).toISOString()
                  : null,
            );
            setOpen(false);
          }}
        />
      ) : (
        <button
          type="button"
          className="control"
          disabled={disabled}
          onClick={() => {
            setDraft(value ? localDateTimeInputValue(new Date(value)) : "");
            setOpen(true);
          }}
        >
          {value ? time(value) : "待补充"}
        </button>
      )}
    </div>
  );
}
export function BodyRecordEditor({
  memberId,
  initial,
  recordId,
  catalog,
  canEdit,
  onClose,
  onSaved,
}: {
  memberId: string;
  initial: BodyInput | BodyRecord;
  recordId?: string;
  catalog: Catalog;
  canEdit: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [addDialog, setAddDialog] = useState<"food" | "stage" | null>(null);
  const [value, setValue] = useState<BodyInput>(() => structuredClone(initial));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [saved, setSaved] = useState<BodyRecord | null>(
    "record_id" in initial ? initial : null,
  );
  const formId = useId();
  const data = value.data;
  const dataChange = (patch: Partial<MetricData>) =>
    setValue((v) => ({ ...v, data: { ...v.data, ...patch } }));
  const num = (label: string, key: keyof MetricData, required = false) => (
    <label className="field-row" key={key}>
      <span>{label}</span>
      <input
        type="number"
        step="any"
        min="0"
        required={required}
        disabled={!canEdit || busy}
        value={typeof data[key] === "number" ? String(data[key]) : ""}
        onChange={(e) =>
          dataChange({
            [key]: e.target.value === "" ? null : Number(e.target.value),
          })
        }
      />
    </label>
  );
  const txt = (label: string, key: keyof MetricData) => (
    <label className="field-row" key={key}>
      <span>{label}</span>
      <input
        disabled={!canEdit || busy}
        value={String(data[key] ?? "")}
        onChange={(e) => dataChange({ [key]: e.target.value })}
      />
    </label>
  );
  const foodChange = (i: number, patch: Partial<Food>) =>
    dataChange({
      foods: data.foods!.map((f, j) => (j === i ? { ...f, ...patch } : f)),
    });
  const group = (title: string, children: ReactNode) => (
    <section className="bm-edit-group">
      <h3>{title}</h3>
      <GroupedList density="standard" layout="fields">
        {children}
      </GroupedList>
    </section>
  );
  async function submit() {
    setBusy(true);
    setError("");
    try {
      let item = await saveRecord(
        memberId,
        value,
        saved?.record_id || recordId,
      );
      setSaved(item);
      for (const file of files) {
        item = await attachFoodFile(memberId, item.record_id, file);
        setSaved(item);
        setFiles((current) => current.filter((pending) => pending !== file));
      }
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <ContentDialog
      creation={!recordId}
      title={recordId ? recordLabel(initial, catalog) : navigationLabels.createRecord}
      onClose={onClose}
      busy={busy}
      bareBody
      actions={
        <>
          {canEdit && recordId ? (
            <button
              type="button"
              className="control control--danger"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await deleteRecord(memberId, recordId);
                  onSaved();
                } catch (e) {
                  setError(e instanceof Error ? e.message : "删除失败");
                } finally {
                  setBusy(false);
                }
              }}
            >
              删除记录
            </button>
          ) : null}
          {canEdit ? (
            <button
              className="control control--primary"
              disabled={busy}
              type="submit"
              form={formId}
            >
              <CheckIcon />{busy ? "正在保存…" : recordId ? "保存记录" : "完成"}
            </button>
          ) : null}
        </>
      }
    >
      <form
        className="bm-record-form"
        id={formId}
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="dialog-body scroll-content">
          <fieldset className="bm-fields-container" disabled={busy || !canEdit}>
            {group(
              "日期与时间",
              <>
                <BodyTimeField
                  label="发生时间"
                  value={value.starts_at}
                  disabled={!canEdit || busy}
                  onChange={(v) =>
                    v && setValue((s) => ({ ...s, starts_at: v }))
                  }
                />
                {value.kind === "sleep" ||
                value.kind === "workout" ||
                value.ends_at ? (
                  <BodyTimeField
                    label="结束时间"
                    value={value.ends_at}
                    disabled={!canEdit || busy}
                    onChange={(v) => setValue((s) => ({ ...s, ends_at: v }))}
                  />
                ) : null}
                <div className="field-row">
                  <span>时间粒度</span>
                  <SelectPopover
                    ariaLabel="时间粒度"
                    interactionOwner="row"
                    menuWidth="content"
                    menuAlign="end"
                    disabled={!canEdit || busy}
                    value={value.precision}
                    options={[
                      { value: "instant", label: "单次测量" },
                      { value: "interval", label: "时间区间" },
                      { value: "day", label: "日汇总" },
                    ]}
                    onChange={(precision) =>
                      setValue((s) => ({
                        ...s,
                        precision: precision as BodyInput["precision"],
                        ends_at:
                          precision === "instant"
                            ? s.ends_at
                            : s.ends_at ||
                              new Date(
                                new Date(s.starts_at).getTime() + 3600000,
                              ).toISOString(),
                      }))
                    }
                  />
                </div>
              </>,
            )}
            {value.kind === "measurement"
              ? group(
                  "测量内容",
                  <>
                    <div className="field-row">
                      <span>指标</span>
                      <SelectPopover
                        ariaLabel="指标"
                        interactionOwner="row"
                        menuWidth="content"
                        menuAlign="end"
                        disabled={!canEdit || busy}
                        value={value.metric || ""}
                        options={catalog.metrics.map((m) => ({
                          value: m.metric,
                          label: m.label,
                        }))}
                        onChange={(metric) => {
                          const m = catalog.metrics.find(
                            (m) => m.metric === metric,
                          )!;
                          setValue((v) => ({
                            ...v,
                            metric: m.metric,
                            data: {
                              value: 0,
                              unit: m.unit,
                              ...(m.metric === "blood_pressure"
                                ? { secondary_value: 0 }
                                : {}),
                            },
                          }));
                        }}
                      />
                    </div>
                    {num(
                      value.metric === "blood_pressure" ? "收缩压" : "数值",
                      "value",
                      true,
                    )}
                    {txt("单位", "unit")}
                    {value.metric === "blood_pressure" ? (
                      <>
                        {num("舒张压", "secondary_value", true)}
                        {num("伴随脉搏", "pulse")}
                      </>
                    ) : null}
                    {txt("测量方法 / HRV 方法", "method")}
                    {txt("测量背景", "context")}
                    {txt("数值依据", "basis")}
                  </>,
                )
              : null}
            {value.kind === "meal" ? (
              <>
                {group(
                  "本次饮食",
                  <>
                    <div className="field-row">
                      <span>餐次</span>
                      <SelectPopover
                        ariaLabel="餐次"
                        interactionOwner="row"
                        menuWidth="content"
                        menuAlign="end"
                        disabled={!canEdit || busy}
                        value={data.meal_type || ""}
                        options={[
                          { value: "", label: "待补充分餐" },
                          ...Object.entries(catalog.meal_types).map(
                            ([value, label]) => ({ value, label }),
                          ),
                        ]}
                        onChange={(meal_type) =>
                          dataChange({ meal_type: meal_type || null })
                        }
                      />
                    </div>
                    <div className="field-row">
                      <span>数值类型</span>
                      <SelectPopover
                        ariaLabel="数值类型"
                        interactionOwner="row"
                        menuWidth="content"
                        menuAlign="end"
                        disabled={!canEdit || busy}
                        value={data.estimated ? "estimate" : "provided"}
                        options={[
                          { value: "estimate", label: "估算" },
                          {
                            value: "provided",
                            label: "标签 / 来源 / 手工填写",
                          },
                        ]}
                        onChange={(value) =>
                          dataChange({ estimated: value === "estimate" })
                        }
                      />
                    </div>
                    {txt("营养依据", "basis")}
                  </>,
                )}
                {canEdit ? (
                  <button
                    className="control"
                    type="button"
                    onClick={() => setAddDialog("food")}
                  >
                    ＋ {navigationLabels.addFood}
                  </button>
                ) : null}
                {(data.foods || []).map((food, i) => (
                  <section className="bm-edit-group" key={food.food_id}>
                    <div className="bm-section-heading">
                      <h3>食物 {i + 1}</h3>
                      {canEdit ? (
                        <button
                          type="button"
                          className="control"
                          onClick={() =>
                            dataChange({
                              foods: data.foods!.filter((_, j) => j !== i),
                            })
                          }
                        >
                          移除食物
                        </button>
                      ) : null}
                    </div>
                    <GroupedList density="standard" layout="fields">
                      <label className="field-row">
                        <span>食物名称</span>
                        <input
                          required
                          disabled={!canEdit || busy}
                          value={food.name}
                          onChange={(e) =>
                            foodChange(i, { name: e.target.value })
                          }
                        />
                      </label>
                      <label className="field-row">
                        <span>摄入份量</span>
                        <input
                          type="number"
                          step="any"
                          min="0.01"
                          disabled={!canEdit || busy}
                          value={food.amount ?? ""}
                          onChange={(e) => {
                            const amount = e.target.value
                              ? Number(e.target.value)
                              : null;
                            const ratio =
                              amount && food.amount ? amount / food.amount : 1;
                            foodChange(i, {
                              amount,
                              ...Object.fromEntries(
                                [
                                  "energy",
                                  "carbohydrate",
                                  "protein",
                                  "fat",
                                ].map((k) => [
                                  k,
                                  food[k as keyof Food] == null
                                    ? null
                                    : Math.round(
                                        Number(food[k as keyof Food]) *
                                          ratio *
                                          100,
                                      ) / 100,
                                ]),
                              ),
                            });
                          }}
                        />
                      </label>
                      <label className="field-row">
                        <span>份量单位</span>
                        <input
                          disabled={!canEdit || busy}
                          value={food.amount_unit}
                          onChange={(e) =>
                            foodChange(i, { amount_unit: e.target.value })
                          }
                        />
                      </label>
                      {[
                        ["energy", "能量 (kcal)"],
                        ["carbohydrate", "碳水 (g)"],
                        ["protein", "蛋白质 (g)"],
                        ["fat", "脂肪 (g)"],
                      ].map(([key, label]) => (
                        <label className="field-row" key={key}>
                          <span>{label}</span>
                          <input
                            type="number"
                            min="0"
                            step="any"
                            disabled={!canEdit || busy}
                            value={food[key as keyof Food] ?? ""}
                            onChange={(e) =>
                              foodChange(i, {
                                [key]: e.target.value
                                  ? Number(e.target.value)
                                  : null,
                              })
                            }
                          />
                        </label>
                      ))}
                      <label className="field-row">
                        <span>食物营养依据</span>
                        <input
                          disabled={!canEdit || busy}
                          value={food.basis}
                          onChange={(e) =>
                            foodChange(i, { basis: e.target.value })
                          }
                        />
                      </label>
                    </GroupedList>
                  </section>
                ))}
                {!data.foods?.length ? (
                  group(
                    "整餐营养值",
                    <>
                      {num("能量 (kcal)", "energy")}
                      {num("碳水 (g)", "carbohydrate")}
                      {num("蛋白质 (g)", "protein")}
                      {num("脂肪 (g)", "fat")}
                    </>,
                  )
                ) : (
                  <p className="bm-muted">
                    本次总量按食物明细计算；编辑份量会按比例调整该食物的营养值，可继续手工修正。
                  </p>
                )}
                <section className="bm-edit-group">
                  <h3>饮食图片</h3>
                  <div className="bm-photos">
                    {saved?.files?.map((file) => (
                      <div key={file.file_id}>
                        <a
                          href={apiUrl(
                            `${bodyBase(memberId)}/records/${saved.record_id}/files/${file.file_id}`,
                          )}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <img
                            src={apiUrl(
                              `${bodyBase(memberId)}/records/${saved.record_id}/files/${file.file_id}`,
                            )}
                            alt={file.filename}
                          />
                        </a>
                        {canEdit ? (
                          <button
                            type="button"
                            className="control"
                            onClick={() => {
                              setBusy(true);
                              void removeFoodFile(
                                memberId,
                                saved.record_id,
                                file.file_id,
                              )
                                .then(setSaved)
                                .catch((e) => setError(e.message))
                                .finally(() => setBusy(false));
                            }}
                          >
                            移除图片
                          </button>
                        ) : null}
                      </div>
                    ))}
                  </div>
                  {canEdit ? (
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      multiple
                      onChange={(e) =>
                        setFiles(Array.from(e.target.files || []))
                      }
                    />
                  ) : null}
                  <p className="bm-muted">
                    {files.length
                      ? `待保存 ${files.length} 张图片`
                      : "图片与饮食记录关联保存"}
                  </p>
                </section>
              </>
            ) : null}
            {value.kind === "sleep" ? (
              <>
                {group(
                  "睡眠评分与时长",
                  <>
                    {num("评分", "score")}
                    {num("评分满分", "score_max")}
                    {txt("评分依据", "score_basis")}
                    {!data.stages?.length
                      ? num("睡眠时长 (min)", "duration_minutes")
                      : null}
                  </>,
                )}
                {data.score_stale ? (
                  <p className="bm-muted">
                    评分对应原始睡眠区间，编辑阶段后尚未重新评分。
                  </p>
                ) : null}
                <section className="bm-edit-group">
                  <h3>睡眠阶段</h3>
                  {canEdit ? (
                    <button
                      className="control"
                      type="button"
                      onClick={() => setAddDialog("stage")}
                    >
                      ＋ {navigationLabels.addSleepStage}
                    </button>
                  ) : null}
                  {(data.stages || []).map((stage, i) => (
                    <div className="bm-stage-editor" key={stage.stage_id}>
                      <div className="field-row">
                        <span>阶段 {i + 1}</span>
                        <SelectPopover
                          ariaLabel={`阶段 ${i + 1}`}
                          interactionOwner="row"
                          menuWidth="content"
                          menuAlign="end"
                          disabled={!canEdit || busy}
                          value={stage.stage}
                          options={Object.entries(catalog.stages).map(
                            ([value, label]) => ({ value, label }),
                          )}
                          onChange={(stage) =>
                            dataChange({
                              stages: data.stages!.map((s, j) =>
                                j === i ? { ...s, stage } : s,
                              ),
                            })
                          }
                        />
                      </div>
                      <BodyTimeField
                        label={`阶段 ${i + 1} 开始`}
                        value={stage.starts_at}
                        disabled={!canEdit || busy}
                        onChange={(v) =>
                          v &&
                          dataChange({
                            stages: data.stages!.map((s, j) =>
                              j === i ? { ...s, starts_at: v } : s,
                            ),
                          })
                        }
                      />
                      <BodyTimeField
                        label={`阶段 ${i + 1} 结束`}
                        value={stage.ends_at}
                        disabled={!canEdit || busy}
                        onChange={(v) =>
                          v &&
                          dataChange({
                            stages: data.stages!.map((s, j) =>
                              j === i ? { ...s, ends_at: v } : s,
                            ),
                          })
                        }
                      />
                      {canEdit ? (
                        <button
                          className="control"
                          type="button"
                          onClick={() =>
                            dataChange({
                              stages: data.stages!.filter((_, j) => j !== i),
                            })
                          }
                        >
                          删除阶段
                        </button>
                      ) : null}
                    </div>
                  ))}
                </section>
              </>
            ) : null}
            {value.kind === "workout"
              ? group(
                  "运动详情",
                  <>
                    {txt("运动类型", "activity")}
                    {num("运动时长 (min)", "duration_minutes", true)}
                    {num("距离 (km)", "distance_km")}
                    {num("运动能量 (kcal)", "energy")}
                  </>,
                )
              : null}
            {group(
              "来源与备注",
              <>
                <p className="bm-muted">
                  {value.source}
                  {value.device ? ` · ${value.device}` : ""}
                  {"edited" in initial && initial.edited ? " · 已手工修正" : ""}
                </p>
                <label className="field-row">
                  <span>备注</span>
                  <textarea
                    disabled={!canEdit || busy}
                    value={value.notes}
                    onChange={(e) =>
                      setValue((v) => ({ ...v, notes: e.target.value }))
                    }
                  />
                </label>
              </>,
            )}
          </fieldset>
          {error ? (
            <p role="alert" className="bm-error">
              {error}
            </p>
          ) : null}
        </div>
      </form>
      {addDialog === "food" ? (
        <FoodAddDialog
          onClose={() => setAddDialog(null)}
          onAdd={(food) => {
            dataChange({ foods: [...(data.foods || []), food] });
            setAddDialog(null);
          }}
        />
      ) : null}
      {addDialog === "stage" ? (
        <StageAddDialog
          catalog={catalog}
          startsAt={data.stages?.at(-1)?.ends_at || value.starts_at}
          endsAt={value.ends_at}
          onClose={() => setAddDialog(null)}
          onAdd={(stage) => {
            dataChange({ stages: [...(data.stages || []), stage] });
            setAddDialog(null);
          }}
        />
      ) : null}
    </ContentDialog>
  );
}

function FoodAddDialog({
  onClose,
  onAdd,
}: {
  onClose: () => void;
  onAdd: (food: Food) => void;
}) {
  const formId = useId();
  const [food, setFood] = useState<Food>({
    food_id: crypto.randomUUID(),
    name: "",
    amount: 100,
    amount_unit: "g",
    energy: null,
    carbohydrate: null,
    protein: null,
    fat: null,
    basis: "",
  });
  const text = (
    label: string,
    key: "name" | "amount_unit" | "basis",
    required = false,
  ) => (
    <label className="field-row">
      <span>{label}</span>
      <input
        aria-label={label}
        required={required}
        value={food[key]}
        onChange={(event) => setFood({ ...food, [key]: event.target.value })}
      />
    </label>
  );
  return (
    <ContentDialog
      creation
      onBack={onClose}
      title={navigationLabels.addFood}
      onClose={onClose}
      actions={
        <>
          <button
            className="control control--primary"
            type="submit"
            form={formId}
          >
            <CheckIcon />
            完成
          </button>
        </>
      }
    >
      <form
        id={formId}
        onSubmit={(event) => {
          event.preventDefault();
          if (food.name.trim() && food.amount_unit.trim())
            onAdd({
              ...food,
              name: food.name.trim(),
              amount_unit: food.amount_unit.trim(),
            });
        }}
      >
        <GroupedList density="standard" layout="fields">
          {text("食物名称", "name", true)}
          <label className="field-row">
            <span>摄入份量</span>
            <input
              aria-label="摄入份量"
              type="number"
              min="0.01"
              step="any"
              value={food.amount ?? ""}
              onChange={(event) =>
                setFood({
                  ...food,
                  amount: event.target.value
                    ? Number(event.target.value)
                    : null,
                })
              }
            />
          </label>
          {text("份量单位", "amount_unit", true)}
          {(
            [
              ["energy", "能量 (kcal)"],
              ["carbohydrate", "碳水 (g)"],
              ["protein", "蛋白质 (g)"],
              ["fat", "脂肪 (g)"],
            ] as const
          ).map(([key, label]) => (
            <label className="field-row" key={key}>
              <span>{label}</span>
              <input
                aria-label={label}
                type="number"
                min="0"
                step="any"
                value={food[key] ?? ""}
                onChange={(event) =>
                  setFood({
                    ...food,
                    [key]: event.target.value
                      ? Number(event.target.value)
                      : null,
                  })
                }
              />
            </label>
          ))}
          {text("营养依据", "basis")}
        </GroupedList>
      </form>
    </ContentDialog>
  );
}
function StageAddDialog({
  catalog,
  startsAt,
  endsAt,
  onClose,
  onAdd,
}: {
  catalog: Catalog;
  startsAt: string;
  endsAt: string | null;
  onClose: () => void;
  onAdd: (stage: NonNullable<MetricData["stages"]>[number]) => void;
}) {
  const [stage, setStage] = useState({
    stage_id: crypto.randomUUID(),
    stage: "light",
    starts_at: startsAt,
    ends_at: endsAt || startsAt,
  });
  const [error, setError] = useState("");
  function add() {
    if (new Date(stage.ends_at) <= new Date(stage.starts_at)) {
      setError("结束时间须晚于开始时间。");
      return;
    }
    onAdd(stage);
  }
  return (
    <ContentDialog
      creation
      onBack={onClose}
      title={navigationLabels.addSleepStage}
      onClose={onClose}
      actions={
        <>
          <button
            className="control control--primary"
            type="button"
            onClick={add}
          >
            <CheckIcon />
            完成
          </button>
        </>
      }
    >
      <GroupedList density="standard" layout="fields">
        <div className="field-row">
          <span>睡眠阶段</span>
          <SelectPopover
            interactionOwner="row"
            menuWidth="content"
            menuAlign="end"
            ariaLabel="睡眠阶段"
            value={stage.stage}
            options={Object.entries(catalog.stages).map(([value, label]) => ({
              value,
              label,
            }))}
            onChange={(value) => setStage({ ...stage, stage: value })}
          />
        </div>
        <BodyTimeField
          label="开始时间"
          value={stage.starts_at}
          onChange={(value) =>
            value && setStage({ ...stage, starts_at: value })
          }
        />
        <BodyTimeField
          label="结束时间"
          value={stage.ends_at}
          onChange={(value) => value && setStage({ ...stage, ends_at: value })}
        />
      </GroupedList>
      {error ? <p role="alert">{error}</p> : null}
    </ContentDialog>
  );
}
