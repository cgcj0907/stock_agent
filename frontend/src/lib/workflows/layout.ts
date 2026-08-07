import { computeStepDepths, type WorkflowStep } from "./catalog";

export interface DagLayoutOptions {
  /** 列间距（px） */
  columnGap?: number;
  /** 行间距（px） */
  rowGap?: number;
  /** 节点宽高，用于估算画布尺寸 */
  nodeWidth?: number;
  nodeHeight?: number;
  /** 四周留白（px） */
  padding?: number;
}

export interface DagLayout {
  /** step id -> 画布坐标 */
  positions: Record<string, { x: number; y: number }>;
  /** 画布内容宽高（含留白与节点尺寸） */
  width: number;
  height: number;
}

const DEFAULTS: Required<DagLayoutOptions> = {
  columnGap: 220,
  rowGap: 96,
  nodeWidth: 176,
  nodeHeight: 62,
  padding: 32,
};

/**
 * 分层 DAG 自动排版（Sugiyama 简化版）：
 * 1. 按依赖深度分层（列），depth 即列号；
 * 2. 层内重心法排序降低交叉（前向/后向交替迭代）；
 * 3. 每列垂直居中，行间距均匀，整体紧凑且平衡。
 *
 * 纯函数、确定性输出，供运行视图与编排器共用。
 */
export function layoutWorkflow(
  steps: WorkflowStep[],
  options: DagLayoutOptions = {}
): DagLayout {
  const opts: Required<DagLayoutOptions> = { ...DEFAULTS, ...options };
  const { columnGap, rowGap, nodeWidth, nodeHeight, padding } = opts;

  const depth = computeStepDepths(steps);
  if (steps.length === 0) {
    return {
      positions: {},
      width: padding * 2 + nodeWidth,
      height: padding * 2 + nodeHeight,
    };
  }

  const maxDepth = Math.max(...Object.values(depth));

  // ---- 分层 ----
  const layers: string[][] = Array.from(
    { length: maxDepth + 1 },
    () => []
  );
  for (const s of steps) layers[depth[s.id]].push(s.id);

  // ---- 重心法排序：降低跨层连线交叉 ----
  const indexInLayer: Record<string, number> = {};
  const setIndex = (layer: string[]) =>
    layer.forEach((id, i) => (indexInLayer[id] = i));
  layers.forEach(setIndex);

  const parents: Record<string, string[]> = {};
  const children: Record<string, string[]> = {};
  for (const s of steps) {
    parents[s.id] = s.deps;
    for (const dep of s.deps) (children[dep] ??= []).push(s.id);
  }

  const sortByBary = (
    layer: string[],
    neighborOf: (id: string) => string[]
  ) => {
    const bary = new Map<string, number>();
    for (const id of layer) {
      const ns = neighborOf(id).filter((n) => depth[n] === depth[id] - 1);
      if (ns.length === 0) continue;
      bary.set(
        id,
        ns.reduce((sum, n) => sum + (indexInLayer[n] ?? 0), 0) / ns.length
      );
    }
    layer.sort((a, b) => {
      const ba = bary.get(a);
      const bb = bary.get(b);
      if (ba === undefined && bb === undefined)
        return (indexInLayer[a] ?? 0) - (indexInLayer[b] ?? 0);
      if (ba === undefined) return 1;
      if (bb === undefined) return -1;
      return ba - bb;
    });
  };

  for (let iter = 0; iter < 8; iter++) {
    // 前向：按上一层父节点重心排序
    for (let d = 1; d <= maxDepth; d++) {
      sortByBary(layers[d], (id) => parents[id] ?? []);
      setIndex(layers[d]);
    }
    // 后向：按下一层子节点重心排序
    for (let d = maxDepth - 1; d >= 0; d--) {
      const bary = new Map<string, number>();
      for (const id of layers[d]) {
        const ns = (children[id] ?? []).filter((c) => depth[c] === d + 1);
        if (ns.length === 0) continue;
        bary.set(
          id,
          ns.reduce((sum, c) => sum + (indexInLayer[c] ?? 0), 0) / ns.length
        );
      }
      layers[d].sort((a, b) => {
        const ba = bary.get(a);
        const bb = bary.get(b);
        if (ba === undefined && bb === undefined)
          return (indexInLayer[a] ?? 0) - (indexInLayer[b] ?? 0);
        if (ba === undefined) return 1;
        if (bb === undefined) return -1;
        return ba - bb;
      });
      setIndex(layers[d]);
    }
  }

  // ---- 坐标：每列垂直居中 ----
  const maxRows = Math.max(...layers.map((l) => l.length));
  const canvasH = (maxRows - 1) * rowGap;

  const positions: Record<string, { x: number; y: number }> = {};
  layers.forEach((layer, d) => {
    const layerH = (layer.length - 1) * rowGap;
    const y0 = padding + (canvasH - layerH) / 2;
    layer.forEach((id, i) => {
      positions[id] = { x: padding + d * columnGap, y: y0 + i * rowGap };
    });
  });

  return {
    positions,
    width: padding * 2 + maxDepth * columnGap + nodeWidth,
    height: padding * 2 + canvasH + nodeHeight,
  };
}
