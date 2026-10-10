// Admission and supplied-value comparison only. No EV engine runs in this module.
export const MAX_RECORD_BYTES = 65536;
export const MAX_RECORD_DEPTH = 8;
export const MAX_INTEGER_DIGITS = 4300;
export const RANKS = Object.freeze(['A','2','3','4','5','6','7','8','9','T']);
export const ACTION_NAMES = Object.freeze({H:'HIT',S:'STAND',D:'DOUBLE',P:'SPLIT'});
export const SURRENDER_ACTION_NAMES = Object.freeze({S:'STAND',H:'HIT',D:'DOUBLE',R:'SURRENDER'});
export const RULE_FIELDS = Object.freeze(['decks','s17','das','peek','surrender',
  'resplit_aces','hit_split_aces','max_hands','blackjack_payout','double_any_two',
  'tens_are_pairs','insurance_payout']);

export class RecordError extends Error {
  constructor(message, status='invalid_input') { super(message); this.name='RecordError'; this.status=status; }
}
const invalid = message => { throw new RecordError(message); };
const unsupported = message => { throw new RecordError(message,'unsupported_record'); };
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
function fields(value, keys, path) {
  if (!object(value)) invalid(`${path} must be an object`);
  const missing=keys.filter(key=>!Object.hasOwn(value,key));
  const unknown=Object.keys(value).filter(key=>!keys.includes(key));
  if (missing.length || unknown.length) invalid(`${path}: missing fields [${missing.join(', ')}], unknown fields [${unknown.join(', ')}]`);
  return value;
}
function string(value,path) {
  if (typeof value !== 'string' || !value.length) invalid(`${path} must be a nonempty string`);
  return value;
}
function integer(value,path) {
  if (typeof value !== 'bigint') invalid(`${path} must be an integer token, not a float or boolean`);
  return value;
}
function finite(value,path) {
  if (!['number','bigint'].includes(typeof value) || !Number.isFinite(Number(value))) invalid(`${path} must be a finite number, not a boolean`);
  return Number(value);
}
function equal(left,right) {
  if (Array.isArray(left) && Array.isArray(right)) return left.length===right.length && left.every((value,i)=>equal(value,right[i]));
  return typeof left===typeof right && left===right;
}
function constant(value,expected,path,derived=false) {
  if (expected===null && ['number','bigint'].includes(typeof value)) {
    finite(value,path); unsupported(`${path} must be null`);
  }
  if (typeof value!==typeof expected || (expected===null && value!==null) ||
      (Array.isArray(expected) && !Array.isArray(value))) invalid(`${path} has the wrong type`);
  if (!equal(value,expected)) (derived ? invalid : unsupported)(`${path} disagrees with the supported declaration`);
}

function decode(input) {
  let bytes;
  if (typeof input==='string') {
    // TextEncoder replaces lone surrogates. Refuse before that replacement.
    for (let i=0;i<input.length;i++) {
      const code=input.charCodeAt(i);
      if (code>=0xd800 && code<=0xdbff) {
        const next=input.charCodeAt(++i);
        if (!(next>=0xdc00 && next<=0xdfff)) invalid('record must be valid UTF-8');
      } else if (code>=0xdc00 && code<=0xdfff) invalid('record must be valid UTF-8');
    }
    if (input.length>MAX_RECORD_BYTES) invalid(`record exceeds ${MAX_RECORD_BYTES} UTF-8 bytes`);
    bytes=new TextEncoder().encode(input);
  } else if (input instanceof Uint8Array) bytes=input;
  else invalid('record must be JSON text or UTF-8 bytes');
  if (bytes.length>MAX_RECORD_BYTES) invalid(`record exceeds ${MAX_RECORD_BYTES} UTF-8 bytes`);
  try { return new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes); }
  catch (_) { invalid('record must be valid UTF-8'); }
}

function parse(input) {
  const text=decode(input);
  let depth=0,inString=false,escaped=false;
  for (const char of text) {
    if (inString) {
      if (escaped) escaped=false;
      else if (char==='\\') escaped=true;
      else if (char==='"') inString=false;
    } else if (char==='"') inString=true;
    else if (char==='{' || char==='[') {
      if (++depth>MAX_RECORD_DEPTH) invalid(`record exceeds container depth ${MAX_RECORD_DEPTH}`);
    } else if (char==='}' || char===']') depth--;
  }
  let offset=0;
  const space=()=>{while (/^[\t\n\r ]$/.test(text[offset] ?? '')) offset++;};
  const syntax=()=>invalid(`invalid JSON near character ${offset+1}`);
  function quoted() {
    if (text[offset]!=='"') syntax();
    const start=offset++;
    let escaped=false;
    while (offset<text.length) {
      const char=text[offset++];
      if (escaped) escaped=false;
      else if (char==='\\') escaped=true;
      else if (char==='"') {
        try { return JSON.parse(text.slice(start,offset)); } catch (_) { syntax(); }
      }
    }
    syntax();
  }
  function value() {
    space(); const char=text[offset];
    if (char==='"') return quoted();
    if (char==='{' || char==='[') {
      offset++; space();
      const isObject=char==='{', result=isObject ? Object.create(null) : [];
      const end=isObject ? '}' : ']';
      if (text[offset]===end) { offset++; return result; }
      while (true) {
        if (isObject) {
          const key=quoted(); space();
          if (text[offset++]!==':') syntax();
          if (Object.hasOwn(result,key)) invalid(`duplicate JSON key: ${key}`);
          result[key]=value();
        } else result.push(value());
        space();
        if (text[offset]===end) { offset++; return result; }
        if (text[offset++]!==',') syntax();
        space();
      }
    }
    for (const [word,item] of [['true',true],['false',false],['null',null]]) {
      if (text.startsWith(word,offset)) { offset+=word.length; return item; }
    }
    const token=text.slice(offset).match(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/)?.[0];
    if (!token) syntax();
    offset+=token.length;
    if (/[.eE]/.test(token)) {
      const result=Number(token);
      if (!Number.isFinite(result)) invalid('JSON number must be finite');
      return result;
    }
    if (token.replace('-','').length>MAX_INTEGER_DIGITS) unsupported(`integer token exceeds the browser limit of ${MAX_INTEGER_DIGITS} decimal digits; use installed replay`);
    return BigInt(token);
  }
  const result=value(); space(); if (offset!==text.length) syntax();
  return result;
}

export function modelFor(up,maxStates=null) {
  const model={dealer_information:'hidden_hole_post_peek',
    hole_rank_excluded_by_peek:up==='A' ? 'T' : up==='T' ? 'A' : null,
    ten_value_ranks:'collapsed_to_T',insurance_priced:false,
    hit_stand_double:'finite_enumeration_binary_floating_point',
    split:'independent_hands_greedy_shared_resplit_budget',split_error_bound:null};
  return maxStates===null ? model : {...model,
    split:'common_shoe_sequential_two_hand_no_resplit_binary_float_v1',split_hands:2n,
    split_deal_order:'finish_first_before_dealing_second',
    split_aces:'one_card_no_double_no_natural_premium',
    split_exhaustion:'refuse_any_unavailable_continuation',enumeration_state_limit:maxStates};
}

export function surrenderModelFor(up,maxStates) {
  return {name:'post_peek_late_surrender',version:1n,
    dealer_information:'hidden_hole_post_peek',
    hole_rank_excluded_by_peek:up==='A' ? 'T' : up==='T' ? 'A' : null,
    ten_value_ranks:'collapsed_to_T',insurance_priced:false,
    hit_stand_double:'finite_enumeration_binary_floating_point',
    split:'excluded_single_original_hand',decision_phase:'initial_original_two_card_below_21',
    surrender:'terminal_half_original_wager_post_negative_peek',surrender_after_hit:false,
    surrender_after_double:false,surrender_draws:0n,
    player_last_draw:'stand_then_require_dealer_settlement',enumeration_state_limit:maxStates};
}

export function resplitModelFor(up,maxStates) {
  return {name:'common_shoe_bounded_resplit',version:1n,
    dealer_information:'hidden_hole_post_peek',
    hole_rank_excluded_by_peek:up==='A' ? 'T' : up==='T' ? 'A' : null,
    ten_value_ranks:'collapsed_to_T',insurance_priced:false,
    hit_stand_double:'finite_enumeration_binary_floating_point',
    player_last_draw:'stand_then_require_dealer_settlement',
    split:'common_shoe_sequential_up_to_three_one_extra_resplit_binary_float_v1',
    split_max_hands:3n,split_max_extra_resplits:1n,
    split_deal_order:'finish_active_child_before_dealing_next_pending',
    split_child_order:'new_sibling_before_older_pending',
    split_eligibility:'matching_two_card_active_hand_before_hit_or_double',
    split_aces:'excluded_non_ace_initial_pair',
    split_twenty_one:'ordinary_wager_no_natural_premium',
    split_objective:'combined_settlement_all_completed_wagers',
    split_exhaustion:'refuse_any_unavailable_continuation',
    split_cooperative_seconds:10,enumeration_state_limit:maxStates};
}

export function aceResplitModelFor(up,maxStates) {
  return {...resplitModelFor(up,maxStates),name:'common_shoe_bounded_ace_resplit',
    split:'common_shoe_sequential_up_to_three_one_extra_ace_resplit_binary_float_v1',
    split_eligibility:'matching_A_A_after_mandatory_card_with_shared_slot',
    split_aces:'one_card_optional_resplit_no_hit_no_double_no_natural_premium'};
}

export function recordActionNames(record) {
  return record.schema.version===4n ? SURRENDER_ACTION_NAMES : ACTION_NAMES;
}
export function comparisonActionNames(left,right) {
  return left.schema.version===4n || right.schema.version===4n ?
    {...ACTION_NAMES,R:SURRENDER_ACTION_NAMES.R} : ACTION_NAMES;
}

export function inspectRecord(input) {
  const saved=parse(input);
  if (!object(saved)) invalid('record must be an object');
  const schema=fields(saved.schema,['name','version'],'schema');
  string(schema.name,'schema.name'); integer(schema.version,'schema.version');
  if (schema.name!=='blackjack-decision' || ![1n,2n,3n,4n,5n,6n].includes(schema.version)) unsupported('supported schemas are blackjack-decision versions 1, 2, 3, 4, 5 and 6');
  const surrender=schema.version===4n,resplit=schema.version===5n,aceResplit=schema.version===6n;
  fields(saved,['schema','package','state','rules','decision','model'],'record');
  const pkg=fields(saved.package,['name','version'],'package');
  constant(pkg.name,'exact-blackjack-solver','package.name'); string(pkg.version,'package.version');
  const stateKeys=['cards','dealer_up','total','soft','is_split_hand','hand_count','shoe'];
  if (schema.version!==1n) stateKeys.push('action_controls');
  const state=fields(saved.state,stateKeys,'state');
  if (schema.version!==1n) {
    const keys=surrender ? ['can_double','can_split','can_surrender'] : ['can_double','can_split'];
    const controls=fields(state.action_controls,keys,'state.action_controls');
    for (const key of keys) if (typeof controls[key]!=='boolean') invalid(`state.action_controls.${key} must be a boolean`);
  }
  if (!Array.isArray(state.cards) || state.cards.some(rank=>typeof rank!=='string' || !RANKS.includes(rank))) invalid('state.cards must be a list of normalized ranks in dealt order');
  if (typeof state.dealer_up!=='string' || !RANKS.includes(state.dealer_up)) invalid('state.dealer_up must be a normalized rank');
  integer(state.total,'state.total'); integer(state.hand_count,'state.hand_count');
  for (const key of ['soft','is_split_hand']) if (typeof state[key]!=='boolean') invalid(`state.${key} must be a boolean`);
  const shoe=fields(state.shoe,['rank_order','counts','source','includes_hidden_hole','visible_cards_already_removed'],'state.shoe');
  constant(shoe.rank_order,RANKS,'state.shoe.rank_order',true);
  if (!Array.isArray(shoe.counts)) invalid('state.shoe.counts must be a list');
  const validCounts=()=>shoe.counts.length===10 && shoe.counts.every(count=>typeof count==='bigint' && count>=0n);
  if (!surrender && !validCounts()) invalid('state.shoe.counts must contain ten nonnegative integer tokens');
  constant(shoe.includes_hidden_hole,true,'state.shoe.includes_hidden_hole');
  constant(shoe.visible_cards_already_removed,true,'state.shoe.visible_cards_already_removed');
  string(shoe.source,'state.shoe.source');
  if (!['fresh_minus_visible','supplied_unseen'].includes(shoe.source)) unsupported('unsupported state.shoe.source');
  const rules=fields(saved.rules,RULE_FIELDS,'rules');
  for (const key of ['decks','max_hands']) if (integer(rules[key],`rules.${key}`)<1n) invalid(`rules.${key} must be a positive integer`);
  for (const key of ['s17','das','peek','surrender','resplit_aces','hit_split_aces','double_any_two','tens_are_pairs']) if (typeof rules[key]!=='boolean') invalid(`rules.${key} must be a boolean`);
  for (const key of ['blackjack_payout','insurance_payout']) {
    rules[key]=finite(rules[key],`rules.${key}`);
    if (rules[key]<0) invalid(`rules.${key} must be nonnegative`);
  }
  if (!rules.peek) unsupported('records model the post-peek game; rules.peek must be true');
  if (surrender ? !rules.surrender : rules.surrender) unsupported(surrender ?
    'late-surrender records require rules.surrender=true' : 'these record models do not price surrender');
  if (!rules.double_any_two) unsupported('records require doubling on any two-card hand');
  if (!rules.tens_are_pairs) unsupported('records collapse ten-value ranks and require tens_are_pairs');
  if (surrender && (rules.max_hands!==1n || rules.resplit_aces || rules.hit_split_aces))
    unsupported('late-surrender model requires max_hands=1, no resplits and no hittable split aces');
  if (resplit && (rules.max_hands!==3n || rules.resplit_aces || rules.hit_split_aces))
    unsupported('bounded-resplit model requires max_hands=3 and no split-ace extensions');
  if (aceResplit && (rules.max_hands!==3n || !rules.resplit_aces || rules.hit_split_aces))
    unsupported('bounded ace resplit model requires max_hands=3, optional ace resplitting and one-card split aces');
  if (state.hand_count<1n || state.hand_count>rules.max_hands) invalid('state.hand_count must be from 1 to rules.max_hands');
  if (state.is_split_hand ? state.hand_count<2n : state.hand_count!==1n) invalid('split state and state.hand_count disagree');
  if (state.cards.length<2) invalid('a hand needs at least two cards before it has a decision');
  let total=0,aces=0;
  for (const rank of state.cards) { total+=rank==='A' ? 11 : rank==='T' ? 10 : Number(rank); if (rank==='A') aces++; }
  while (total>21 && aces>0) { total-=10; aces--; }
  if (total>21) invalid('state.cards describes a busted hand with no decision left');
  if (state.is_split_hand && state.cards[0]==='A' && state.cards.length>2 && !rules.hit_split_aces) invalid('a split ace receives only one card when hit_split_aces is false');
  if (surrender && !validCounts()) invalid('state.shoe.counts must contain ten nonnegative integer tokens');
  const count=shoe.counts.reduce((sum,value)=>sum+value,0n);
  if (!count) invalid('an unseen shoe must include the reserved dealer hole card');
  const excluded=state.dealer_up==='A' ? 'T' : state.dealer_up==='T' ? 'A' : null;
  if (excluded!==null && count===shoe.counts[RANKS.indexOf(excluded)]) invalid('after the peek there is no possible hole card for this upcard');
  constant(state.total,BigInt(total),'state.total',true); constant(state.soft,aces>0,'state.soft',true);
  if (shoe.source==='fresh_minus_visible') {
    const expected=RANKS.map(rank=>rules.decks*(rank==='T' ? 16n : 4n));
    for (const rank of [...state.cards,state.dealer_up]) if (--expected[RANKS.indexOf(rank)]<0n) invalid('declared fresh shoe has too few visible cards');
    if (!equal(shoe.counts,expected)) invalid('fresh_minus_visible counts disagree with the declared state');
  }
  let maxStates=null;
  if (schema.version===3n) {
    if (!object(saved.model)) invalid('model must be an object');
    maxStates=integer(saved.model.enumeration_state_limit,'model.enumeration_state_limit');
    if (maxStates<1n || maxStates>100000n) unsupported('common model enumeration state limit must be from 1 through 100000');
    if (state.cards.length!==2 || state.cards[0]!==state.cards[1]) unsupported('common-shoe model requires an initial two-card pair');
    if (state.is_split_hand || state.hand_count!==1n) unsupported('common-shoe model requires an unsplit initial hand');
    if (rules.max_hands!==2n || rules.resplit_aces || rules.hit_split_aces) unsupported('common-shoe model requires max_hands=2, no resplits and one-card split aces');
    if (count<3n || count>20n) unsupported('common-shoe model requires 3 to 20 unseen cards including the hole');
    if (shoe.source!=='supplied_unseen') unsupported('common-shoe records require supplied_unseen counts');
  }
  if (surrender) {
    if (!object(saved.model)) invalid('model must be an object');
    maxStates=integer(saved.model.enumeration_state_limit,'model.enumeration_state_limit');
    if (maxStates<1n || maxStates>100000n) unsupported('late-surrender enumeration state limit must be from 1 through 100000');
    if (state.cards.length!==2 || total>=21 || state.is_split_hand || state.hand_count!==1n)
      unsupported('late-surrender model requires an original initial two-card hand below 21');
    if (state.action_controls.can_split)
      unsupported('late-surrender model excludes splitting and requires max_hands=1');
    if (count<3n || count>20n) unsupported('late-surrender model requires 3 to 20 unseen cards including the hole');
    if (shoe.source!=='supplied_unseen') unsupported('late-surrender records require supplied_unseen counts');
  }
  if (resplit) {
    if (!object(saved.model)) invalid('model must be an object');
    maxStates=integer(saved.model.enumeration_state_limit,'model.enumeration_state_limit');
    if (maxStates<1n || maxStates>100000n) unsupported('bounded-resplit enumeration state limit must be from 1 through 100000');
    if (state.cards.length!==2 || state.cards[0]!==state.cards[1] || state.cards[0]==='A')
      unsupported('bounded-resplit model requires an initial non-ace two-card pair');
    if (state.is_split_hand || state.hand_count!==1n)
      unsupported('bounded-resplit model requires one original unsplit hand');
    if (count<3n || count>20n) unsupported('bounded-resplit model requires 3 to 20 unseen cards including the hole');
    if (shoe.source!=='supplied_unseen') unsupported('bounded-resplit records require supplied_unseen counts');
  }
  if (aceResplit) {
    if (!object(saved.model)) invalid('model must be an object');
    maxStates=integer(saved.model.enumeration_state_limit,'model.enumeration_state_limit');
    if (maxStates<1n || maxStates>100000n) unsupported('bounded ace resplit enumeration state limit must be from 1 through 100000');
    if (state.cards.length!==2 || state.cards.some(rank=>rank!=='A'))
      unsupported('bounded ace resplit model requires an original A,A pair');
    if (state.is_split_hand || state.hand_count!==1n)
      unsupported('bounded ace resplit model requires one original unsplit hand');
    if (count<3n || count>20n) unsupported('bounded ace resplit model requires 3 to 20 unseen cards including the hole');
    if (shoe.source!=='supplied_unseen') unsupported('bounded ace resplit records require supplied_unseen counts');
  }
  const declarations=surrender ? surrenderModelFor(state.dealer_up,maxStates) :
    resplit ? resplitModelFor(state.dealer_up,maxStates) :
    aceResplit ? aceResplitModelFor(state.dealer_up,maxStates) : modelFor(state.dealer_up,maxStates);
  const model=fields(saved.model,Object.keys(declarations),'model');
  if (resplit || aceResplit) model.split_cooperative_seconds=finite(model.split_cooperative_seconds,'model.split_cooperative_seconds');
  for (const [key,expected] of Object.entries(declarations)) constant(model[key],expected,`model.${key}`,key==='hole_rank_excluded_by_peek');
  const decision=fields(saved.decision,['action','action_name','evs','margin','units','whole_game_estimate'],'decision');
  constant(decision.units,'original_wager','decision.units'); constant(decision.whole_game_estimate,null,'decision.whole_game_estimate');
  const names=recordActionNames(saved);
  if (typeof decision.action!=='string' || !Object.hasOwn(names,decision.action)) invalid('decision.action must be a supported action code for this record model');
  constant(decision.action_name,names[decision.action],'decision.action_name',true);
  if (!object(decision.evs) || !Object.keys(decision.evs).length || !Object.hasOwn(decision.evs,decision.action) || Object.keys(decision.evs).some(key=>!Object.hasOwn(names,key))) invalid('decision.evs must have supported action codes for this record model and include action');
  for (const key of Object.keys(decision.evs)) decision.evs[key]=finite(decision.evs[key],`decision.evs.${key}`);
  decision.margin=finite(decision.margin,'decision.margin');
  if (decision.margin<0) invalid('decision.margin must be nonnegative');
  return saved;
}

export function display(value) {
  if (value===undefined) return 'absent (not declared by this model)';
  if (value===null) return 'null';
  if (Array.isArray(value)) return '['+value.map(display).join(', ')+']';
  return String(value);
}
export function modeledRows(record) {
  const {state,rules,model}=record;
  const controls=actionControls(record);
  return [
    ...['cards','dealer_up','total','soft','is_split_hand','hand_count'].map(key=>[`state.${key}`,state[key]]),
    ...['can_double','can_split'].map(key=>[`state.action_controls.${key}`,controls[key]]),
    ['effective_action_controls.can_surrender',controls.can_surrender],
    ['state.action_controls.can_surrender',record.state.action_controls?.can_surrender],
    ['state.shoe.rank_order',state.shoe.rank_order],
    ...RANKS.map((rank,i)=>[`state.shoe.counts.${rank}`,state.shoe.counts[i]]),
    ...['source','includes_hidden_hole','visible_cards_already_removed'].map(key=>[`state.shoe.${key}`,state.shoe[key]]),
    ...RULE_FIELDS.map(key=>[`rules.${key}`,rules[key]]),
    ...Object.keys(model).map(key=>[`model.${key}`,model[key]])
  ];
}
export function metadataRows(record) {
  return [['schema.name',record.schema.name],['schema.version',record.schema.version],
    ['package.name',record.package.name],['package.version',record.package.version]];
}
// Effective defaults do not add fields to the admitted version 1 object.
export function actionControls(record) {
  return record.schema.version===1n ? {can_double:true,can_split:true,can_surrender:false} :
    {...record.state.action_controls,can_surrender:record.schema.version===4n ?
      record.state.action_controls.can_surrender : false};
}
// This derives eligibility only and never evaluates an action's return.
export function permittedActions(record) {
  const {state,rules}=record,controls=actionControls(record),allowed=new Set(['S']);
  if (record.schema.version===4n) return ['S','H',...(controls.can_double ? ['D'] : []),
    ...(controls.can_surrender ? ['R'] : [])];
  if (state.total===21n) return ['S'];
  const twoCards=state.cards.length===2,pair=twoCards && state.cards[0]===state.cards[1];
  const unseen=state.shoe.counts.reduce((sum,count)=>sum+count,0n);
  const frozenAce=state.is_split_hand && twoCards && state.cards[0]==='A' && !rules.hit_split_aces;
  if (!frozenAce && unseen>=2n) {
    allowed.add('H');
    if (controls.can_double && twoCards && (!state.is_split_hand || rules.das)) allowed.add('D');
  }
  const blockedAceResplit=state.is_split_hand && pair && state.cards[0]==='A' && !rules.resplit_aces;
  if (controls.can_split && pair && unseen>=3n && state.hand_count<rules.max_hands && !blockedAceResplit) allowed.add('P');
  return Object.keys(ACTION_NAMES).filter(action=>allowed.has(action));
}
export function recordedActionDifferences(record) {
  const permitted=permittedActions(record),recorded=Object.keys(record.decision.evs);
  return {permitted,omitted:permitted.filter(action=>!recorded.includes(action)),
    unavailable:recorded.filter(action=>!permitted.includes(action)),
    recommendation_unavailable:!permitted.includes(record.decision.action)};
}
export function compareRecords(left,right) {
  const changed=(rows,otherRows)=>{
    const one=new Map(rows),other=new Map(otherRows);
    return [...new Set([...one.keys(),...other.keys()])]
      .filter(key=>!equal(one.get(key),other.get(key)))
      .map(key=>[key,one.get(key),other.get(key)]);
  };
  const delta=(a,b)=> { const value=b-a; return Number.isFinite(value) ? value : 'outside finite delta range'; };
  return {
    inputs:changed(modeledRows(left),modeledRows(right)),metadata:changed(metadataRows(left),metadataRows(right)),
    model_compatible:(left.schema.version===4n || right.schema.version===4n) ?
      left.schema.version===4n && right.schema.version===4n : left.model.split===right.model.split,
    permitted:{left:permittedActions(left),right:permittedActions(right)},
    action:{left:left.decision.action,right:right.decision.action,matches:left.decision.action===right.decision.action},
    margin:{left:left.decision.margin,right:right.decision.margin,matches:left.decision.margin===right.decision.margin,delta:delta(left.decision.margin,right.decision.margin)},
    evs:Object.keys(comparisonActionNames(left,right)).filter(key=>Object.hasOwn(left.decision.evs,key) || Object.hasOwn(right.decision.evs,key)).map(action=>{
      const a=left.decision.evs[action],b=right.decision.evs[action];
      return {action,left:a ?? null,right:b ?? null,matches:a!==undefined && b!==undefined && a===b,
        delta:a===undefined || b===undefined ? null : delta(a,b)};
    })
  };
}

// Sequence ownership is separate from physical read completion. A stale read is ignored.
export function recordSlot(changed,read=async file=>new Uint8Array(await file.arrayBuffer())) {
  let sequence=0,record=null,name='';
  const notify=(status,message)=>changed({status,message,record,name});
  const clear=()=>{sequence++;record=null;name='';notify('empty','No record selected.');};
  return {clear,async select(file) {
    const request=++sequence; record=null; name=file?.name ?? '';
    if (!file) { name='';notify('empty','No record selected.');return; }
    notify('reading','Reading and validating the selected local file.');
    try {
      if (file.size>MAX_RECORD_BYTES) invalid(`record exceeds ${MAX_RECORD_BYTES} UTF-8 bytes`);
      const bytes=await read(file);
      if (request!==sequence) return;
      const admitted=inspectRecord(bytes);
      if (request!==sequence) return;
      record=admitted; notify('accepted','Supported representation admitted. The saved answer has not been recomputed.');
    } catch (error) {
      if (request!==sequence) return;
      record=null;
      const label=error instanceof RecordError ? error.status : 'io_error';
      notify('error',`${label}: ${error instanceof RecordError ? error.message : 'The local file could not be read.'}`);
    }
  }};
}
