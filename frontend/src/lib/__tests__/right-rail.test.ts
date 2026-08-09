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
