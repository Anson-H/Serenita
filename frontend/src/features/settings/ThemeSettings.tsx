import { navigationLabels } from "../../components/navigationLabels";
import { GroupedList } from "../../components/GroupedList";
import { SelectPopover } from "../../components/SelectPopover";
import { CheckIcon } from "../../components/icons";
import { useAppearance, type ColorStyle, type ThemeMode } from "../appearance/useAppearance";

const colorStyles: { value: ColorStyle; label: string; description: string }[] = [
  { value: "apricot", label: "暖杏", description: "温暖的杏桃与米灰" },
  { value: "sage", label: "鼠尾草", description: "舒缓的草木绿与浅灰" },
  { value: "blue", label: "雾蓝", description: "清爽的雾蓝与石灰" },
  { value: "mauve", label: "藕紫", description: "柔和的藕紫与暖灰" },
  { value: "oat", label: "燕麦", description: "安静的燕麦与沙灰" }
];

export function ThemeSettings() {
  const { mode, style, theme, setAppearance } = useAppearance();
  return <div className="theme-settings">
    <GroupedList layout="fields" density="standard">
      <div className="field-row">
        <span>明暗主题</span>
        <SelectPopover ariaLabel="明暗主题" value={mode} menuWidth="content" menuAlign="end"
          interactionOwner="row" options={[
            { value: "system", label: "跟随系统" },
            { value: "light", label: "浅色" },
            { value: "dark", label: "深色" }
          ]} onChange={value => setAppearance({ mode: value as ThemeMode })} />
      </div>
    </GroupedList>
    <section aria-labelledby="theme-color-style-title">
      <div className="group-heading"><h3 id="theme-color-style-title">色彩风格</h3></div>
      <div className="theme-style-grid" role="group" aria-label="色彩风格">
        {colorStyles.map(option => <button key={option.value} type="button"
          className="theme-style-option" aria-pressed={style === option.value}
          aria-label={option.label} onClick={() => setAppearance({ style: option.value })}>
          <span className="theme-style-preview" data-theme-preview="" data-theme={theme}
            data-color-style={option.value} aria-hidden="true">
            <span className="theme-preview-rail"><span /><span /><span /></span>
            <span className="theme-preview-content">
              <span className="theme-preview-title">健康每一天</span>
              <span className="theme-preview-description">记录与陪伴</span>
              <span className="theme-preview-field">{navigationLabels.health}</span>
              <span className="theme-preview-action">查看医疗报告</span>
            </span>
          </span>
          <span className="theme-style-caption"><span>{option.label}</span>
            {style === option.value ? <CheckIcon /> : null}
          </span>
          <span className="theme-style-description">{option.description}</span>
        </button>)}
      </div>
    </section>
    <p className="content-description">主题选择自动保存在当前浏览器。</p>
  </div>;
}
