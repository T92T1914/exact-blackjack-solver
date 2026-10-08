import {ACTION_NAMES,display,modeledRows,metadataRows,compareRecords,recordSlot} from './record-inspection.mjs';

const element=(tag,text,className)=>{
  const node=document.createElement(tag);
  if (text!==undefined) node.textContent=text;
  if (className) node.className=className;
  return node;
};
function table(headers,rows,caption) {
  const wrap=element('div',undefined,'table-wrap record-table');
  wrap.tabIndex=0; wrap.setAttribute('role','region'); wrap.setAttribute('aria-label',caption);
  const table=element('table'),head=element('thead'),heading=element('tr'),body=element('tbody');
  table.append(element('caption',caption));
  headers.forEach(text=>{const cell=element('th',text);cell.scope='col';heading.append(cell);});
  head.append(heading);table.append(head);
  rows.forEach(row=>{
    const tr=element('tr');
    row.forEach((value,i)=>{const cell=element(i===0 ? 'th' : 'td',display(value));if(i===0)cell.scope='row';tr.append(cell);});
    body.append(tr);
  });
  table.append(body);wrap.append(table);return wrap;
}
function renderRecord(target,record,label) {
  target.replaceChildren();
  if (!record) { target.hidden=true;return; }
  target.hidden=false;
  target.append(element('h3',`${label}: modeled inputs`),
    table(['Field','Supplied value'],modeledRows(record),`${label} complete modeled state, rules and model`),
    element('h3',`${label}: record metadata`),
    table(['Field','Supplied label'],metadataRows(record),`${label} schema and unauthenticated package labels`),
    element('h3',`${label}: recorded answer`),
    table(['Field','Supplied value'],[
      ['decision.action',record.decision.action],['decision.action_name',record.decision.action_name],
      ['decision.margin',record.decision.margin],['decision.units',record.decision.units],
      ['decision.whole_game_estimate',record.decision.whole_game_estimate]
    ],`${label} recorded recommendation and raw margin`),
    table(['Recorded action','Raw expected net return'],
      Object.keys(ACTION_NAMES).filter(key=>Object.hasOwn(record.decision.evs,key)).map(key=>[`${key} (${ACTION_NAMES[key]})`,record.decision.evs[key]]),
      `${label} supplied action values in original wager units`));
}
function renderComparison(target,left,right) {
  target.replaceChildren();
  if (!left || !right) { target.hidden=true;return; }
  target.hidden=false;
  const compared=compareRecords(left,right);
  target.append(element('h3','1. Changed modeled inputs'),
    element('p',compared.inputs.length ?
      'Inspect these changes before the answers. When several inputs change, their combined difference does not identify a single cause.' :
      'All supplied modeled inputs agree, including dealt order, retained counts, rules and model declarations.'),
    ...(compared.inputs.length ? [table(['Changed field','Record A','Record B'],compared.inputs,'Modeled input changes, before answer differences')] : []),
    element('h3','2. Changed record labels'),
    element('p',compared.metadata.length ?
      'These supplied labels differ. Package labels are unauthenticated metadata and do not select or install an engine.' :
      'Supplied schema and package labels agree. Matching labels do not authenticate origin.'),
    ...(compared.metadata.length ? [table(['Changed label','Record A','Record B'],compared.metadata,'Record label changes')] : []),
    element('h3','3. Recorded answer comparison'),
    table(['Field','Record A','Record B','Equal supplied values','B minus A'],[
      ['Recommendation',compared.action.left,compared.action.right,compared.action.matches,'not numeric'],
      ['Raw margin',compared.margin.left,compared.margin.right,compared.margin.matches,compared.margin.delta]
    ],'Recorded recommendation and margin comparison'),
    table(['Recorded action','Record A raw EV','Record B raw EV','Equal supplied values','B minus A'],
      compared.evs.map(row=>[`${row.action} (${ACTION_NAMES[row.action]})`,row.left===null ? 'absent' : row.left,
        row.right===null ? 'absent' : row.right,row.matches,row.delta===null ? 'not available: action absent' : row.delta]),
      'Union of recorded actions, with absence distinguished from zero'),
    element('p','Numeric answers use exact finite binary-float equality with no display rounding or tolerance. Equality compares supplied values only. This page has not recomputed them or checked that the recorded action set is legal.','fine'));
}
export function initRecordInspector(root=document.getElementById('record-inspector')) {
  if (!root) return;
  const slots={A:null,B:null},controllers={};
  const comparison=root.querySelector('#record-comparison');
  for (const label of ['A','B']) {
    const input=root.querySelector(`#record-file-${label.toLowerCase()}`);
    const status=root.querySelector(`#record-status-${label.toLowerCase()}`);
    const filename=root.querySelector(`#record-name-${label.toLowerCase()}`);
    const result=root.querySelector(`#record-result-${label.toLowerCase()}`);
    controllers[label]=recordSlot(state=>{
      slots[label]=state.record;
      filename.textContent=state.name ? `Selected local file: ${state.name}` : 'No local file retained.';
      status.textContent=state.message;status.classList.toggle('error',state.status==='error');
      renderRecord(result,state.record,`Record ${label}`);
      renderComparison(comparison,slots.A,slots.B);
    });
    input.addEventListener('change',()=>{
      const file=input.files[0];
      // Reset the control so selecting the same file again triggers a new read.
      input.value='';void controllers[label].select(file);
    });
    root.querySelector(`#record-clear-${label.toLowerCase()}`).addEventListener('click',()=>{
      input.value='';controllers[label].clear();
    });
    controllers[label].clear();
  }
  root.querySelector('#record-clear-all').addEventListener('click',()=>{
    for (const label of ['A','B']) {
      root.querySelector(`#record-file-${label.toLowerCase()}`).value='';controllers[label].clear();
    }
  });
  root.hidden=false;
}
