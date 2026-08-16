import { useState } from 'react';

import { Button, Panel } from '@/components/ui';

import { CONTROL_CONSTRUCTS, LOGIC_KIND, NODE_KINDS } from './vocabulary';

/** Add-node controls: one button per plain kind, plus a construct picker for `logic`. */
export function NodePalette({
  onAddNode,
}: {
  onAddNode: (kind: string, controlConstruct: string | null) => void;
}) {
  const [construct, setConstruct] = useState<string>(CONTROL_CONSTRUCTS[0] ?? 'IF');
  const plainKinds = NODE_KINDS.filter((kind) => kind !== LOGIC_KIND);

  return (
    <Panel title="Node palette">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          {plainKinds.map((kind) => (
            <Button key={kind} onClick={() => onAddNode(kind, null)}>
              + {kind}
            </Button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 pt-3">
          <label htmlFor="logic-construct" className="text-sm font-medium text-slate-800">
            logic
          </label>
          <select
            id="logic-construct"
            value={construct}
            onChange={(event) => setConstruct(event.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900"
          >
            {CONTROL_CONSTRUCTS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <Button onClick={() => onAddNode(LOGIC_KIND, construct)}>+ logic node</Button>
        </div>
      </div>
    </Panel>
  );
}
