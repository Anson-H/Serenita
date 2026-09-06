import assert from "node:assert/strict";
import test, { describe } from "node:test";
import { loadModule } from "./helpers/load-module.mjs";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";

describe("list-select-all", () => {
  const load = (path, dependencies = {}) => loadModule(path, {}, dependencies);

  const selection = load("utils/listSelection.ts");
  const { areAllSelected, toggleAllSelection } = selection;
  const { SelectAllButton } = load("components/SelectAllButton.tsx", {
    "../utils/listSelection": selection,
    "./icons": { ListChecksIcon: () => null }
  });

  test("select all fills a partial selection without mutating or losing hidden selections", () => {
    const current = new Set(["hidden", "a"]);
    assert.equal(areAllSelected(["a", "b"], current), false);
    const next = toggleAllSelection(["a", "b"], current);
    assert.deepEqual([...next], ["hidden", "a", "b"]);
    assert.deepEqual([...current], ["hidden", "a"]);
    assert.equal(areAllSelected(["a", "b"], next), true);
  });

  test("cancel all only clears the current filtered results", () => {
    const current = new Set(["hidden", "a", "b"]);
    assert.deepEqual([...toggleAllSelection(["a", "b"], current)], ["hidden"]);
    assert.deepEqual([...toggleAllSelection(["a", "b"], new Set(["a", "b"]))], []);
  });

  test("empty results are not all selected, and duplicate ids remain unique", () => {
    assert.equal(areAllSelected([], new Set(["hidden"])), false);
    assert.deepEqual([...toggleAllSelection([], new Set(["hidden"]))], ["hidden"]);
    assert.deepEqual([...toggleAllSelection(["a", "a", "b"], new Set())], ["a", "b"]);
  });

  test("shared icon button exposes select-all and cancel-all states with accessible labels", () => {
    let current = new Set(["a"]);
    const props = {
      ids: ["a", "b"], scopeLabel: "当前列表中的聊天",
      onChange: (update) => { current = update(current); }
    };
    let button = SelectAllButton({ ...props, selectedIds: current });
    assert.equal(button.type, "button");
    assert.equal(button.props["aria-label"], "全选当前列表中的聊天");
    assert.equal(button.props["aria-pressed"], false);
    assert.equal(button.props.title, button.props["aria-label"]);
    button.props.onClick();
    assert.deepEqual([...current], ["a", "b"]);
    button = SelectAllButton({ ...props, selectedIds: current });
    assert.equal(button.props["aria-label"], "取消全选当前列表中的聊天");
    assert.equal(button.props["aria-pressed"], true);
    button.props.onClick();
    assert.equal(current.size, 0);
  });

  test("button toggles against the latest selection", () => {
    let pending;
    const button = SelectAllButton({
      ids: ["a", "b"], selectedIds: new Set(["a"]), scopeLabel: "当前列表",
      onChange: (update) => { pending = update; }
    });
    button.props.onClick();
    assert.deepEqual([...pending(new Set(["hidden", "a", "b"]))], ["hidden"]);
  });

  test("busy and empty buttons cannot alter selection", () => {
    for (const state of [{ disabled: true, ids: ["a"] }, { ids: [] }]) {
      const button = SelectAllButton({
        ...state, selectedIds: new Set(), scopeLabel: "当前列表",
        onChange: () => assert.fail("disabled selection changed")
      });
      assert.equal(button.props.disabled, true);
      button.props.onClick();
    }
  });
});

describe("overlay-scroll-boundary", () => {
  class Element {
    constructor(parent = null) { this.parent = parent; }
    contains(node) {
      for (let current = node; current; current = current.parent) {
        if (current === this) return true;
      }
      return false;
    }
  }
  const { scrollAffectsAnchor } = loadModule("utils/overlayEvents.ts", { Element });

  test("only ancestor scrolling dismisses an anchored menu or cancels its long press", () => {
    const doc = { defaultView: {} };
    const page = new Element();
    const sidebar = new Element(page);
    const list = new Element(sidebar);
    const anchor = new Element(list);
    anchor.ownerDocument = doc;
    const conversation = new Element(page);
    const queue = new Element(conversation);
    const reportDetail = new Element(page);
    const menu = new Element(page);
    for (const target of [conversation, queue, reportDetail, menu, new Element(menu), anchor, new Element(anchor), null]) {
      assert.equal(scrollAffectsAnchor({ target }, anchor), false);
    }
    for (const target of [list, sidebar, page, doc, doc.defaultView]) {
      assert.equal(scrollAffectsAnchor({ target }, anchor), true);
    }
    assert.equal(scrollAffectsAnchor({ target: list }, null), false);
  });
});

describe("shared-design-components", () => {
  const load = (path, dependencies = {}) => loadModule(path, { document: { body: {} } }, dependencies);

  const { GroupedList } = load("components/GroupedList.tsx");
  const { Switch } = load("components/Switch.tsx");
  const { calculatePopoverPosition, samePopoverPosition } = load("utils/popoverPosition.ts");

  for (const tag of ["div", "ul", "ol", "dl"]) {
    test("GroupedList preserves " + tag + " semantics, children and attributes", () => {
      const ref = React.createRef();
      const element = GroupedList({ as: tag, density: "standard", layout: "fields", className: "example", ref, "aria-label": "报告", children: "内容" });
      assert.equal(element.type, tag);
      assert.equal(element.props.ref, ref);
      assert.match(renderToStaticMarkup(element), new RegExp("^<" + tag + ".*aria-label=\"报告\".*>内容</" + tag + ">$"));
    });
  }

  test("Switch exposes a named binary control and emits only the next state", () => {
    const values = [];
    const button = Switch({ checked: false, label: "启用", onChange: value => values.push(value) });
    assert.equal(button.props.role, "switch");
    assert.equal(button.props["aria-label"], "启用");
    assert.equal(button.props["aria-checked"], false);
    button.props.onClick();
    assert.deepEqual(values, [true]);
    const disabled = Switch({ checked: true, label: "禁用", disabled: true, onChange: () => {} });
    assert.equal(disabled.props.disabled, true);
    assert.match(renderToStaticMarkup(disabled), /aria-checked="true"/);
  });

  function nodes(element) {
    if (Array.isArray(element)) return element.flatMap(nodes);
    if (!React.isValidElement(element)) return [];
    return [element, ...nodes(element.props.children)];
  }

  function pickerComponent(name, props) {
    const calls = [];
    const picker = {
      open: true, position: { left: 15, top: 50, width: 200, maxHeight: 300, placement: "below" },
      listboxId: "choices", pickerRef: {}, triggerRef: {}, optionsRef: {},
      triggerProps: {}, onBlur() {}, moveOptionFocus() {}, close: mode => calls.push(mode)
    };
    const component = load("components/" + name + ".tsx", {
      "./useSelectPopover": { useSelectPopover: () => picker },
      "./GroupedList": { GroupedList },
      "./icons": { ChevronDownIcon: () => null, CheckIcon: () => null },
      "react-dom": { createPortal: node => node }
    })[name];
    return { elements: nodes(component({ menuWidth: "content", menuAlign: "end", interactionOwner: "self", ...props })), calls };
  }

  const options = ["A", "B", "C"].map(value => ({ value, label: value }));
  test("single selection closes and keeps one aria-selected option", () => {
    const values = [];
    const { elements, calls } = pickerComponent("SelectPopover", { ariaLabel: "类型", options, value: "A", onChange: v => values.push(v) });
    const rows = elements.filter(e => e.props.role === "option");
    assert.equal(rows.filter(e => e.props["aria-selected"]).length, 1);
    rows[1].props.onClick({ detail: 0 });
    assert.deepEqual(values, ["B"]);
    assert.deepEqual(calls, ["keyboard"]);
  });

  test("multi selection adds, removes the last item, and leaves its menu open", () => {
    for (const values of [[], ["B"]]) {
      const results = [];
      const { elements, calls } = pickerComponent("MultiSelectPopover", {
        ariaLabel: "类型", options, values, onChange: v => results.push(v),
        allSelectedLabel: "全部", emptySelectedLabel: "未选择", selectedCountLabel: n => String(n)
      });
      const row = elements.find(e => e.props.role === "option" && e.props.children?.[1]?.props.children === "B")
        ?? elements.filter(e => e.props.role === "option")[1];
      row.props.onClick({ detail: 0 });
      assert.deepEqual(results, [values.length ? [] : ["B"]]);
      assert.deepEqual(calls, []);
      assert.equal(elements.find(e => e.props.role === "listbox").props["aria-multiselectable"], "true");
    }
  });

  test("all selected options retain accessible selection and checkbox state, not current state", () => {
    const { elements } = pickerComponent("MultiSelectPopover", {
      ariaLabel: "类型", options, values: options.map(option => option.value), onChange() {},
      allSelectedLabel: "全部", emptySelectedLabel: "未选择", selectedCountLabel: String
    });
    const rows = elements.filter(element => element.props.role === "option");
    assert.equal(rows.length, options.length);
    for (const row of rows) {
      assert.equal(row.props["aria-selected"], true);
      assert.equal(row.props["aria-current"], undefined);
      assert.equal(row.props["data-active"], undefined);
      assert.doesNotMatch(row.props.className, /\bactive\b|\bselected\b/);
      assert.equal(nodes(row).find(element => element.props.className === "selection-check-control").props["data-selected"], "true");
    }
  });

  const position = (anchor, viewport = { left: 0, top: 0, width: 390, height: 844 }, contentWidth = 160) =>
    calculatePopoverPosition({ anchor, viewport, edgeInset: 15, gap: 5, contentWidth, maxHeight: 320, menuWidth: "content", menuAlign: "start" });

  test("menus expand above near the bottom and below near the top", () => {
    assert.equal(position({ left: 10, top: 790, bottom: 830, width: 220 }).placement, "above");
    assert.equal(position({ left: 10, top: 20, bottom: 60, width: 220 }).placement, "below");
  });

  for (const width of [300, 390, 650, 651, 834, 1440]) {
    test("menu geometry stays within the " + width + "px viewport including scrolled anchors", () => {
      const viewport = { left: 4, top: 6, width, height: 700 };
      for (const [top, contentWidth] of [-100, 40, 620, 850].flatMap(top => [80, 1200].map(contentWidth => [top, contentWidth]))) {
        const p = position({ left: width - 20, top, bottom: top + 40, width: 1200 }, viewport, contentWidth);
        assert.equal(p.width, Math.min(contentWidth, width - 30));
        assert.equal(p.maxWidth, width - 30);
        assert.ok(p.left >= viewport.left + 15);
        assert.ok(p.left + p.width <= viewport.left + width - 15);
        const menuTop = p.placement === "above" ? p.top - p.maxHeight : p.top;
        const menuBottom = p.placement === "above" ? p.top : p.top + p.maxHeight;
        assert.ok(menuTop >= viewport.top + 15);
        assert.ok(menuBottom <= viewport.top + viewport.height - 15);
      }
    });
  }

  test("unchanged geometry does not request another positioning render", () => {
    const p = position({ left: 15, top: 20, bottom: 60, width: 200 });
    assert.equal(samePopoverPosition(null, p), false);
    assert.equal(samePopoverPosition(p, { ...p }), true);
    assert.equal(samePopoverPosition(p, { ...p, width: p.width + 1 }), false);
    assert.equal(samePopoverPosition(p, { ...p, maxWidth: p.maxWidth + 1 }), false);
  });

  for (const menuWidth of ["trigger", "content"]) {
    for (const menuAlign of ["start", "end"]) {
      test(`${menuWidth} width with ${menuAlign} alignment follows the trigger`, () => {
        const input = {
          anchor: { left: 400, top: 100, bottom: 140, width: 240 },
          viewport: { left: 0, top: 0, width: 1000, height: 800 },
          edgeInset: 15, gap: 5, contentWidth: 360, maxHeight: 320, menuWidth, menuAlign
        };
        const p = calculatePopoverPosition(input);
        assert.equal(p.width, menuWidth === "trigger" ? 240 : 360);
        assert.equal(p.left, menuAlign === "start" ? 400 : 640 - p.width);
        for (const left of [0, 950]) {
          const edge = calculatePopoverPosition({ ...input, anchor: { ...input.anchor, left } });
          assert.ok(edge.left >= 15);
          assert.ok(edge.left + edge.width <= 985);
        }
        const narrow = calculatePopoverPosition({ ...input, viewport: { ...input.viewport, width: 200 } });
        assert.equal(narrow.width, 170);
        const resized = calculatePopoverPosition({ ...input, anchor: { ...input.anchor, width: 300 } });
        assert.equal(resized.width, menuWidth === "trigger" ? 300 : 360);
      });
    }
  }
});
