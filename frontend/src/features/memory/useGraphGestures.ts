import {useEffect, useRef, type PointerEvent as ReactPointerEvent, type RefObject} from 'react';

type Point = {x: number; y: number};
type View = Point & {width: number; height: number};
type Gesture = {
  points: Point[]; view: View; inverse: DOMMatrix; nodeId?: string; position?: Point;
  target: Element | null; moved: boolean;
};
const center = (points: Point[]): Point => points.length > 1
  ? {x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2} : points[0];
const distance = (points: Point[]) => Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y);
const world = (point: Point, inverse: DOMMatrix) => new DOMPoint(point.x, point.y).matrixTransform(inverse);

export function useGraphGestures({svg, view, fit, positions, onView, onNodeMove, onTap, onInteract}: {
  svg: RefObject<SVGSVGElement | null>; view: View; fit: View; positions: Record<string, Point>;
  onView: (view: View) => void; onNodeMove: (id: string, point: Point) => void;
  onTap: (target: Element) => void; onInteract: () => void;
}) {
  const pointers = useRef(new Map<number, Point>());
  const gesture = useRef<Gesture | null>(null);
  const current = useRef({view, fit, positions, onView, onNodeMove, onTap, onInteract});
  current.current = {view, fit, positions, onView, onNodeMove, onTap, onInteract};

  function zoom(factor: number, anchor?: Point) {
    const state = current.current, v = state.view;
    const point = anchor || {x: v.x + v.width / 2, y: v.y + v.height / 2};
    const width = Math.max(state.fit.width * .2, Math.min(state.fit.width * 3, v.width * factor));
    const ratio = width / v.width;
    state.onInteract();
    const next = {x: point.x - (point.x - v.x) * ratio, y: point.y - (point.y - v.y) * ratio, width, height: v.height * ratio};
    current.current.view = next;
    state.onView(next);
  }

  useEffect(() => {
    const element = svg.current;
    if (!element) return;
    function wheel(event: WheelEvent) {
      event.preventDefault();
      if (pointers.current.size) return;
      const matrix = element!.getScreenCTM();
      if (!matrix) return;
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? element!.clientHeight : 1);
      zoom(Math.exp(Math.max(-1, Math.min(1, delta * .002))), world({x: event.clientX, y: event.clientY}, matrix.inverse()));
    }
    element.addEventListener('wheel', wheel, {passive: false});
    return () => element.removeEventListener('wheel', wheel);
  }, [svg]);

  function begin(target: Element | null = null, moved = true) {
    const matrix = svg.current?.getScreenCTM();
    if (!matrix || !pointers.current.size) {gesture.current = null; return;}
    const points = [...pointers.current.values()].slice(0, 2);
    const nodeId = points.length === 1 ? target?.closest('[data-event-id]')?.getAttribute('data-event-id') || undefined : undefined;
    gesture.current = {points, view: current.current.view, inverse: matrix.inverse(), nodeId,
      position: nodeId ? current.current.positions[nodeId] : undefined, target, moved};
  }

  function down(event: ReactPointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    pointers.current.set(event.pointerId, {x: event.clientX, y: event.clientY});
    begin(pointers.current.size === 1 ? event.target as Element : null, pointers.current.size > 1);
    event.currentTarget.setPointerCapture(event.pointerId);
    current.current.onInteract();
  }

  function move(event: ReactPointerEvent<SVGSVGElement>) {
    if (!pointers.current.has(event.pointerId)) return;
    pointers.current.set(event.pointerId, {x: event.clientX, y: event.clientY});
    const state = gesture.current;
    if (!state) return;
    const points = [...pointers.current.values()].slice(0, 2);
    if (points.some((point, i) => Math.hypot(point.x - state.points[i].x, point.y - state.points[i].y) > 4)) state.moved = true;
    if (!state.moved) return;
    const start = world(center(state.points), state.inverse), now = world(center(points), state.inverse);
    if (state.nodeId && state.position && points.length === 1) {
      current.current.onNodeMove(state.nodeId, {x: state.position.x + now.x - start.x, y: state.position.y + now.y - start.y});
      return;
    }
    const v = state.view;
    const factor = points.length > 1 ? Math.max(1, distance(state.points)) / Math.max(1, distance(points)) : 1;
    const width = Math.max(current.current.fit.width * .2, Math.min(current.current.fit.width * 3, v.width * factor));
    const ratio = width / v.width;
    const next = {x: start.x - (now.x - v.x) * ratio, y: start.y - (now.y - v.y) * ratio, width, height: v.height * ratio};
    current.current.view = next;
    current.current.onView(next);
  }

  function end(event: ReactPointerEvent<SVGSVGElement>) {
    if (!pointers.current.has(event.pointerId)) return;
    const state = gesture.current;
    pointers.current.delete(event.pointerId);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    begin(); // A remaining finger continues panning from its current location.
    if (event.type === 'pointerup' && !pointers.current.size && state && !state.moved && state.target) current.current.onTap(state.target);
  }

  return {isInteracting: () => pointers.current.size > 0, handlers: {
    onPointerDown: down, onPointerMove: move, onPointerUp: end, onPointerCancel: end, onLostPointerCapture: end
  }};
}
