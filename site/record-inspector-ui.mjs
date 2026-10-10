import {display,modeledRows,metadataRows,compareRecords,recordSlot,recordedActionDifferences,
  recordActionNames,comparisonActionNames} from './record-inspection.mjs';

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
  const eligibility=recordedActionDifferences(record);
  const names=recordActionNames(record);
  const messages=[];
  if (eligibility.omitted.length) messages.push(`Permitted actions omitted from saved EVs: ${eligibility.omitted.join(', ')}.`);
  if (eligibility.unavailable.length) messages.push(`Saved EVs include unavailable actions: ${eligibility.unavailable.join(', ')}.`);
  if (eligibility.recommendation_unavailable) messages.push(`Recorded recommendation ${record.decision.action} is unavailable in this modeled state.`);
  const warning=element('p',messages.length ? messages.join(' ')+' Saved answers remain supplied values. No EVs were recomputed.' :
    'Saved EV keys match the permitted action set for this modeled state. Numerical answers have not been recomputed.','fine');
  warning.dataset.actionSetStatus=messages.length ? 'differs' : 'matches';warning.setAttribute('role','note');
  target.append(element('h3',`${label}: modeled inputs`),
    element('p',record.schema.version===1n ?
      'Version 1 has implicit current action defaults: can_double=true and can_split=true. These two effective values were not stored in the record. Surrender is outside this model: its effective permission is false and no surrender control was stored.' :
      record.schema.version===2n ?
      'Version 2 stores the declared current action controls as booleans. They restrict the present choices and do not change continuation rules. Surrender is outside this model: its effective permission is false and no surrender control was stored.' :
      record.schema.version===3n ?
      'Version 3 stores explicit current action controls and the bounded common-shoe model. Two sequential hands share depletion and one dealer settlement. Split aces take one card, with no resplits or natural premium. Surrender is outside this model: its effective permission is false and no surrender control was stored. This page has not recomputed the result.' :
      record.schema.version===4n ?
      'Version 4 declares bounded post-peek late surrender for one original initial two-card hand below 21. Supplied counts include the hidden hole and exclude visible cards. Current permission controls R, which loses half the original wager and draws no card. Hit continuations offer no surrender or double. Split, natural and later decisions are outside this family. The state cap is not a wall or memory guarantee. This page has not recomputed the result.' :
      'Version 5 declares bounded common-shoe resplitting for one original non-ace pair. An initial split has one shared extra resplit slot and at most three resulting hands. New children finish before an older pending hand receives its mandatory card. All completed wagers share depletion and one concealed-hole dealer settlement. Split 21 pays the ordinary wager. Split aces and surrender are excluded. Current double and split controls restrict the original choice. An unavailable offered joint draw refuses the whole calculation. Root hit, stand and double retain the ordinary last-player-draw convention. The state cap is not a wall or memory guarantee. Surrender permission is effectively false and no surrender control was stored. This page has not recomputed the result.','fine'),
    table(['Field','Modeled value'],modeledRows(record),`${label} complete modeled state, rules and model`),
    element('h3',`${label}: record metadata`),
    table(['Field','Supplied label'],metadataRows(record),`${label} schema and unauthenticated package labels`),
    element('h3',`${label}: permitted actions from modeled inputs`),
    element('p','Eligibility follows the supported saved-state model, including effective current action controls, retained counts and split rules. True intersects with existing eligibility. It does not establish which buttons an external table offers.','fine'),
    table(['Action','Permitted by modeled state','Supplied raw EV'],Object.keys(names).map(action=>[
      `${action} (${names[action]})`,eligibility.permitted.includes(action),
      Object.hasOwn(record.decision.evs,action) ? record.decision.evs[action] : 'absent (no saved value)'
    ]),`${label} derived permitted actions beside supplied EV presence`),warning,
    element('h3',`${label}: recorded answer`),
    table(['Field','Supplied value'],[
      ['decision.action',record.decision.action],['decision.action_name',record.decision.action_name],
      ['decision.margin',record.decision.margin],['decision.units',record.decision.units],
      ['decision.whole_game_estimate',record.decision.whole_game_estimate]
    ],`${label} recorded recommendation and raw margin`),
    table(['Recorded action','Raw expected net return'],
      Object.keys(names).filter(key=>Object.hasOwn(record.decision.evs,key)).map(key=>[`${key} (${names[key]})`,record.decision.evs[key]]),
      `${label} supplied action values in original wager units`));
}
function renderComparison(target,left,right) {
  target.replaceChildren();
  if (!left || !right) { target.hidden=true;return; }
  target.hidden=false;
  const compared=compareRecords(left,right);
  const names=comparisonActionNames(left,right),hasSurrender=left.schema.version===4n || right.schema.version===4n,
    hasResplit=left.schema.version===5n || right.schema.version===5n;
  target.append(element('h3','1. Changed modeled inputs'),
    element('p',compared.model_compatible ?
      (hasSurrender ? 'Both records declare the same post-peek late-surrender family. Current permission, rules and retained counts can still differ.' :
        hasResplit ? 'Both records declare the same bounded common-shoe resplit family. Current controls, rules, retained counts and work caps can still differ.' :
        'Both records declare the same mathematical split model. This is a supplied declaration, not independent numerical validation.') :
      (hasSurrender ? 'These records use different mathematical families. Initial late surrender and split models have different coverage. Their answer differences do not establish an engine regression. Inspect model identity and coverage before the EVs.' :
        hasResplit ? 'These records use different mathematical families. Bounded resplitting carries up to three hands and one shared extra slot. The older two-hand and independent-hand split models have different coverage. Their answer differences do not establish an engine regression. Inspect model identity and coverage before the EVs.' :
        'These records use different mathematical split models. Their answer differences compare different models and do not establish an engine regression. Inspect model identity and coverage before the EVs.'),'fine'),
    element('p',compared.inputs.length ?
      'Inspect these changes before the answers. When several inputs change, their combined difference does not identify a single cause.' :
      'All modeled inputs agree, including effective current action controls, dealt order, retained counts, rules and model declarations.'),
    ...(compared.inputs.length ? [table(['Changed field','Record A','Record B'],compared.inputs,'Modeled input changes, before answer differences')] : []),
    element('h3','2. Changed record labels'),
    element('p',compared.metadata.length ?
      'These supplied labels differ. Package labels are unauthenticated metadata and do not select or install an engine.' :
      'Supplied schema and package labels agree. Matching labels do not authenticate origin.'),
    ...(compared.metadata.length ? [table(['Changed label','Record A','Record B'],compared.metadata,'Record label changes')] : []),
    element('h3','3. Permitted actions from modeled inputs'),
    table(['Action','Record A permitted','Record B permitted'],Object.keys(names).map(action=>[
      `${action} (${names[action]})`,compared.permitted.left.includes(action),compared.permitted.right.includes(action)
    ]),'Derived action eligibility for each modeled input'),
    element('h3','4. Recorded answer comparison'),
    table(['Field','Record A','Record B','Equal supplied values','B minus A'],[
      ['Recommendation',compared.action.left,compared.action.right,compared.action.matches,'not numeric'],
      ['Raw margin',compared.margin.left,compared.margin.right,compared.margin.matches,compared.margin.delta]
    ],'Recorded recommendation and margin comparison'),
    table(['Recorded action','Record A raw EV','Record B raw EV','Equal supplied values','B minus A'],
      compared.evs.map(row=>[`${row.action} (${names[row.action]})`,row.left===null ? 'absent' : row.left,
        row.right===null ? 'absent' : row.right,row.matches,row.delta===null ? 'not available: action absent' : row.delta]),
      'Union of recorded actions, with absence distinguished from zero'),
    element('p','Numeric answers use exact finite binary-float equality with no display rounding or tolerance. Equality compares supplied values only. Eligibility was derived from the modeled inputs. This page has not recomputed the answers or validated their numerical correctness.','fine'));
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
