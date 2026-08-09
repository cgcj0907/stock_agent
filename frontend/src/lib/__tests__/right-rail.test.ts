import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function readSource(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("dashboard layout provides shared right rail state but no global viewport", async () => {
  const source = await readSource("../../app/(dashboard)/layout.tsx");

  assert.match(source, /import \{ RightRailProvider \} from "@\/components\/ui\/right-rail";/);
  assert.match(source, /<SidebarProvider>\s*<RightRailProvider>/);
  assert.doesNotMatch(source, /RightRailViewport/);
  assert.doesNotMatch(source, /RightRailPortal/);
});

test("workflow and conversation views render the page-level right rail only when there is content", async () => {
  const workflowSource = await readSource("../../components/workflow/workflow-run-view.tsx");
  const conversationSource = await readSource("../../components/conversations/conversation-detail-view.tsx");

  assert.match(workflowSource, /import \{ RightRailShell \} from "@\/components\/ui\/right-rail";/);
  assert.match(workflowSource, /\{hasRun && \(\s*<RightRailShell/);
  assert.match(workflowSource, /<RightRailShell[\s\S]*<WorkflowRail/);

  assert.match(conversationSource, /import \{ RightRailShell \} from "@\/components\/ui\/right-rail";/);
  assert.match(conversationSource, /\{showRail && workflow && \(\s*<RightRailShell/);
  assert.match(conversationSource, /<RightRailShell[\s\S]*<WorkflowRail/);
});

test("right rail shell keeps a left divider and collapse toggle", async () => {
  const source = await readSource("../../components/ui/right-rail.tsx");

  assert.match(source, /const RIGHT_RAIL_STORAGE_KEY = "right_rail_state";/);
  assert.match(source, /lg:border-l/);
  assert.match(source, /aria-label=\{open \? "收起右侧栏" : "展开右侧栏"\}/);
  assert.doesNotMatch(source, /createPortal/);
  assert.doesNotMatch(source, /RightRailViewport/);
});

test("right rail provider is hydration-safe (server snapshot, no localStorage in initial render)", async () => {
  const source = await readSource("../../components/ui/right-rail.tsx");

  // 服务端快照恒为 true，水合后再经 getSnapshot 同步 localStorage 偏好
  assert.match(source, /useSyncExternalStore\(subscribe, readStoredOpen, \(\) => true\)/);
  // 不允许在 useState 初始值里读 window/localStorage（会导致 SSR/客户端首帧不一致）
  assert.doesNotMatch(source, /React\.useState\(\(\) => \{\s*if \(typeof window === "undefined"\)/);
  // 读取偏好必须包裹 try/catch（隐私模式等）
  assert.match(source, /function readStoredOpen\(\)[\s\S]*?try \{[\s\S]*?localStorage\.getItem/);
});
