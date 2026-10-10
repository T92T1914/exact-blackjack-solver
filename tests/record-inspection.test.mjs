import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {inspectRecord,compareRecords,recordSlot,display,modeledRows,modelFor,permittedActions,recordedActionDifferences,MAX_RECORD_BYTES,
  MAX_RECORD_DEPTH,MAX_INTEGER_DIGITS,RANKS,RULE_FIELDS,ACTION_NAMES,SURRENDER_ACTION_NAMES,
  surrenderModelFor,resplitModelFor,recordActionNames,actionControls} from '../site/record-inspection.mjs';

const fixture=await readFile(new URL('./fixtures/saved-decision-v1-7a38141.json',import.meta.url),'utf8');
const baseline=JSON.parse(fixture);
const bytes=text=>new TextEncoder().encode(text);
const change=update=>{const saved=structuredClone(baseline);update(saved);return JSON.stringify(saved);};
const cases=[];
const add=(name,text,status='accepted',pythonStatus=status)=>cases.push({name,bytes:typeof text==='string' ? bytes(text) : text,status,pythonStatus});
add('accepted original fixture',fixture);
add('whitespace and reordered fields',JSON.stringify(Object.fromEntries(Object.entries(baseline).reverse()),null,1)+'\r\n\t ');
add('UTF-8 package label',change(r=>{r.package.version='local édition <img src=x>'; }));
add('unpaired surrogate escaped in package label',change(r=>{r.package.version='\ud800'; }));
add('altered finite recommendation and margin',change(r=>{r.decision.action='S';r.decision.action_name='STAND';r.decision.margin=99;}));
add('supported altered action set including split',change(r=>{r.decision.evs={P:-7,H:8};r.decision.action='P';r.decision.action_name='SPLIT';}));
add('integer numeric answer',change(r=>{r.decision.evs.H=7;r.decision.margin=0;r.rules.blackjack_payout=2;}));
add('signed zero and subnormal answer',change(r=>{r.decision.margin=0;r.decision.evs.H=5e-324;}).replace('"margin":0','"margin":-0.0'));
add('floating underflow',change(r=>{r.decision.evs.H=0;}).replace('"H":0','"H":1e-1000'));
add('supplied count above fresh maxima',change(r=>{r.state.shoe.counts[0]=999;}));
add('unsafe exact integer count',change(r=>{r.state.shoe.counts[0]=0;}).replace('"counts":[0,','"counts":[9007199254740993,'));
add('400-digit count',change(r=>{r.state.shoe.counts[0]=0;}).replace('"counts":[0,','"counts":['+'1'+'0'.repeat(400)+','));
add('4,300-digit count',change(r=>{r.state.shoe.counts[0]=0;}).replace('"counts":[0,','"counts":['+'1'+'0'.repeat(4299)+','));
add('browser integer-token limit',change(r=>{r.state.shoe.counts[0]=0;}).replace('"counts":[0,','"counts":['+'1'+'0'.repeat(4300)+','),'unsupported_record','invalid_input');
add('fresh origin consistent',change(r=>{r.state.shoe.source='fresh_minus_visible';r.state.shoe.counts=[24,24,24,23,24,24,24,24,24,94];}));
add('split dealt ace order',change(r=>{r.state.cards=['A','4'];r.state.total=15;r.state.soft=true;r.state.is_split_hand=true;r.state.hand_count=2;}));
add('split non-ace first order',change(r=>{r.state.cards=['4','A'];r.state.total=15;r.state.soft=true;r.state.is_split_hand=true;r.state.hand_count=2;}));
add('changed supported rule',change(r=>{r.rules.s17=false;}));
add('schema future',change(r=>{r.schema.version=6;}),'unsupported_record');
add('schema name future',change(r=>{r.schema.name='different';}),'unsupported_record');
add('float schema version',fixture.replace('"version": 1','"version": 1.0'),'invalid_input');
add('exponent schema version',fixture.replace('"version": 1','"version": 1e0'),'invalid_input');
add('Boolean schema version',change(r=>{r.schema.version=true;}),'invalid_input');
add('duplicate escaped root key','{"schema":{},"\\u0073chema":{}}','invalid_input');
add('duplicate nested escaped key',fixture.replace('"decks": 6','"decks":6,"\\u0064ecks":6'),'invalid_input');
add('duplicate action key',fixture.replace('"H": -0.5916666666666668','"H":0,"\\u0048":1'),'invalid_input');
for (const path of ['package','state','rules','decision','model']) add(`unknown ${path} field`,change(r=>{r[path].unknown=0;}),'invalid_input');
add('unknown root field',change(r=>{r.unknown=0;}),'invalid_input');
add('missing required field',change(r=>{delete r.state.shoe;}),'invalid_input');
add('wrong total',change(r=>{r.state.total=15;}),'invalid_input');
add('wrong softness',change(r=>{r.state.soft=true;}),'invalid_input');
add('Boolean hand count',change(r=>{r.state.hand_count=true;}),'invalid_input');
add('floating count token',fixture.replace('"counts": [\n        0','"counts": [\n        0.0'),'invalid_input');
add('Boolean count',change(r=>{r.state.shoe.counts[0]=false;}),'invalid_input');
add('negative count',change(r=>{r.state.shoe.counts[0]=-1;}),'invalid_input');
add('missing count',change(r=>{r.state.shoe.counts.pop();}),'invalid_input');
add('rank-order mismatch',change(r=>{r.state.shoe.rank_order.reverse();}),'invalid_input');
add('non-normalized dealt rank',change(r=>{r.state.cards[0]='J';}),'invalid_input');
add('fresh-origin mismatch',change(r=>{r.state.shoe.source='fresh_minus_visible';}),'invalid_input');
add('no possible post-peek hole',change(r=>{r.state.shoe.counts=[1,0,0,0,0,0,0,0,0,0];}),'invalid_input');
add('no unseen hole',change(r=>{r.state.shoe.counts=Array(10).fill(0);}),'invalid_input');
add('split count mismatch',change(r=>{r.state.is_split_hand=true;}),'invalid_input');
add('non-split count mismatch',change(r=>{r.state.hand_count=2;}),'invalid_input');
add('split ace extra card',change(r=>{r.state.cards=['A','2','3'];r.state.total=16;r.state.soft=true;r.state.is_split_hand=true;r.state.hand_count=2;}),'invalid_input');
add('split non-ace extra card',change(r=>{r.state.cards=['2','A','3'];r.state.total=16;r.state.soft=true;r.state.is_split_hand=true;r.state.hand_count=2;}));
add('busted hand',change(r=>{r.state.cards=['T','T','4'];r.state.total=24;}),'invalid_input');
add('empty hand',change(r=>{r.state.cards=[];r.state.total=0;}),'invalid_input');
add('single card',change(r=>{r.state.cards=['T'];r.state.total=10;}),'invalid_input');
add('empty package version',change(r=>{r.package.version='';}),'invalid_input');
for (const [key,value] of [['peek',false],['surrender',true],['double_any_two',false],['tens_are_pairs',false]]) add(`unsupported rule ${key}`,change(r=>{r.rules[key]=value;}),'unsupported_record');
add('float rule deck token',fixture.replace('"decks": 6','"decks": 6.0'),'invalid_input');
add('Boolean payout',change(r=>{r.rules.blackjack_payout=true;}),'invalid_input');
add('negative payout',change(r=>{r.rules.blackjack_payout=-1;}),'invalid_input');
add('wrong derived hole exclusion',change(r=>{r.model.hole_rank_excluded_by_peek='T';}),'invalid_input');
add('unsupported model',change(r=>{r.model.split='different';}),'unsupported_record');
add('model null declaration with finite numeric value',change(r=>{r.model.split_error_bound=1;}),'unsupported_record');
add('model null declaration with Boolean',change(r=>{r.model.split_error_bound=false;}),'invalid_input');
add('unsupported units',change(r=>{r.decision.units='other';}),'unsupported_record');
add('negative margin',change(r=>{r.decision.margin=-1;}),'invalid_input');
add('Boolean EV',change(r=>{r.decision.evs.H=true;}),'invalid_input');
add('overflow float',fixture.replace('-0.5916666666666668','1e309'),'invalid_input');
add('huge integer EV',fixture.replace('-0.5916666666666668','1'+'0'.repeat(400)),'invalid_input');
add('JSON NaN',fixture.replace('-0.5916666666666668','NaN'),'invalid_input');
add('JSON Infinity',fixture.replace('-0.5916666666666668','Infinity'),'invalid_input');
add('unsupported action key',change(r=>{r.decision.evs.X=0;}),'invalid_input');
add('recommendation absent from recorded action set',change(r=>{delete r.decision.evs.H;}),'invalid_input');
add('derived action name wrong',change(r=>{r.decision.action_name='STAND';}),'invalid_input');
add('malformed trailing comma',fixture.replace('"name": "blackjack-decision",','"name": "blackjack-decision",,'),'invalid_input');
add('trailing text',fixture+'x','invalid_input');
add('UTF-8 BOM','\ufeff'+fixture,'invalid_input');
add('invalid UTF-8',new Uint8Array([0xff,0xfe]),'invalid_input');
add('depth eight accepted parsing, invalid representation','['.repeat(8)+'0'+']'.repeat(8),'invalid_input');
add('depth nine refused before allocation','['.repeat(9)+'0'+']'.repeat(9),'invalid_input');
add('byte limit exactly',fixture+' '.repeat(MAX_RECORD_BYTES-bytes(fixture).length));
add('byte limit exceeded',fixture+' '.repeat(MAX_RECORD_BYTES-bytes(fixture).length+1),'invalid_input');
add('UTF-8 byte limit distinct from character count',change(r=>{r.package.version='é'.repeat(33000);}),'invalid_input');

const controlled=(r,double=true,pair=true)=>{
  r.schema.version=2;r.state.action_controls={can_double:double,can_split:pair};
};
for (const [double,pair] of [[true,true],[false,true],[true,false],[false,false]]) {
  add(`version 2 controls ${double}/${pair}`,change(r=>controlled(r,double,pair)));
}
add('version 2 reordered controls',change(r=>{
  controlled(r);r.state.action_controls={can_split:true,can_double:true};
}));
add('version 1 excludes controls',change(r=>{r.state.action_controls={can_double:true,can_split:true};}),'invalid_input');
add('version 2 missing controls',change(r=>{r.schema.version=2;}),'invalid_input');
add('version 2 missing control key',change(r=>{controlled(r);delete r.state.action_controls.can_split;}),'invalid_input');
add('version 2 unknown control key',change(r=>{controlled(r);r.state.action_controls.extra=true;}),'invalid_input');
const commonText=update=>{
  const saved=structuredClone(baseline);
  saved.schema.version=3;saved.state.action_controls={can_double:true,can_split:true};
  Object.assign(saved.state,{cards:['T','T'],dealer_up:'7',total:20,soft:false});
  saved.state.shoe.counts=[1,...Array(8).fill(0),5];
  saved.rules.max_hands=2;
  saved.model=modelFor('7',100000n);
  saved.decision={action:'P',action_name:'SPLIT',evs:{S:1,H:-2/3,D:-4/3,P:2},
    margin:1,units:'original_wager',whole_game_estimate:null};
  if (update) update(saved);
  return JSON.stringify(saved,(_,value)=>typeof value==='bigint' ? Number(value) : value);
};
add('common version 3 complete record',commonText());
add('common version 3 missing controls',commonText(r=>{delete r.state.action_controls;}),'invalid_input');
add('common version 3 approximate identity',commonText(r=>{r.model.split=modelFor('7').split;}),'unsupported_record');
add('common version 3 unknown field',commonText(r=>{r.model.unknown=true;}),'invalid_input');
add('common version 3 nonpair',commonText(r=>{r.state.cards=['T','9'];r.state.total=19;}),'unsupported_record');
add('common version 3 resplits',commonText(r=>{r.rules.resplit_aces=true;}),'unsupported_record');
add('common version 3 hittable aces',commonText(r=>{r.rules.hit_split_aces=true;}),'unsupported_record');
add('common version 3 hand cap',commonText(r=>{r.rules.max_hands=4;}),'unsupported_record');
add('common version 3 too many cards',commonText(r=>{r.state.shoe.counts=[1,...Array(8).fill(0),20];}),'unsupported_record');
add('common version 3 Boolean state cap',commonText(r=>{r.model.enumeration_state_limit=true;}),'invalid_input');
add('common version 3 large state cap',commonText(r=>{r.model.enumeration_state_limit=100001;}),'unsupported_record');
add('common version 3 fractional state cap',commonText().replace('"enumeration_state_limit":100000','"enumeration_state_limit":100000.0'),'invalid_input');
const surrenderText=update=>{
  const saved=structuredClone(baseline);
  saved.schema.version=4;
  Object.assign(saved.state,{cards:['T','6'],dealer_up:'T',total:16,soft:false,
    action_controls:{can_double:true,can_split:false,can_surrender:true}});
  saved.state.shoe.counts=[...Array(9).fill(0),3];
  Object.assign(saved.rules,{max_hands:1,surrender:true,resplit_aces:false,hit_split_aces:false});
  saved.model=surrenderModelFor('T',100000n);
  saved.decision={action:'R',action_name:'SURRENDER',evs:{S:-1,H:-1,D:-2,R:-0.5},
    margin:0.5,units:'original_wager',whole_game_estimate:null};
  if (update) update(saved);
  return JSON.stringify(saved,(_,value)=>typeof value==='bigint' ? Number(value) : value);
};
add('late version 4 complete record',surrenderText());
add('late version 4 altered finite R',surrenderText(r=>{r.decision.evs.R=99;r.decision.margin=100;}));
add('late version 4 omitted permitted H',surrenderText(r=>{delete r.decision.evs.H;}));
add('late version 4 stored unavailable R',surrenderText(r=>{r.state.action_controls.can_surrender=false;}));
add('late version 4 disabled absent R',surrenderText(r=>{
  r.state.action_controls.can_surrender=false;delete r.decision.evs.R;
  r.decision.action='S';r.decision.action_name='STAND';r.decision.margin=0;
}));
add('late version 4 missing surrender control',surrenderText(r=>{delete r.state.action_controls.can_surrender;}),'invalid_input');
add('late version 4 nonboolean surrender control',surrenderText(r=>{r.state.action_controls.can_surrender=1;}),'invalid_input');
add('late version 4 split action vocabulary',surrenderText(r=>{r.decision.evs.P=0;}),'invalid_input');
add('late version 4 no table surrender',surrenderText(r=>{r.rules.surrender=false;}),'unsupported_record');
add('late version 4 no peek',surrenderText(r=>{r.rules.peek=false;}),'unsupported_record');
add('late version 4 natural',surrenderText(r=>{r.state.cards=['A','T'];r.state.total=21;r.state.soft=true;}),'unsupported_record');
add('late version 4 already hit',surrenderText(r=>{r.state.cards=['T','2','2'];r.state.total=14;}),'unsupported_record');
add('late version 4 split choice',surrenderText(r=>{r.state.action_controls.can_split=true;}),'unsupported_record');
add('late version 4 split hand allowance',surrenderText(r=>{r.rules.max_hands=2;}),'unsupported_record');
add('late version 4 unsupported rules precede inconsistent hand state',surrenderText(r=>{
  r.rules.max_hands=2;r.state.hand_count=2;
}),'unsupported_record');
add('late version 4 unsupported rules precede invalid count values',surrenderText(r=>{
  r.rules.max_hands=2;r.state.shoe.counts[0]=false;
}),'unsupported_record');
add('late version 4 resplit rule',surrenderText(r=>{r.rules.resplit_aces=true;}),'unsupported_record');
add('late version 4 hittable split ace rule',surrenderText(r=>{r.rules.hit_split_aces=true;}),'unsupported_record');
add('late version 4 fewer than three unseen',surrenderText(r=>{r.state.shoe.counts[9]=2;}),'unsupported_record');
add('late version 4 more than twenty unseen',surrenderText(r=>{r.state.shoe.counts[9]=21;}),'unsupported_record');
add('late version 4 fresh origin',surrenderText(r=>{
  r.rules.decks=1;r.state.shoe.source='fresh_minus_visible';
  r.state.shoe.counts=[4,4,4,4,4,3,4,4,4,14];
}),'unsupported_record');
add('late version 4 missing model field',surrenderText(r=>{delete r.model.surrender_after_hit;}),'invalid_input');
add('late version 4 unknown model field',surrenderText(r=>{r.model.extra=false;}),'invalid_input');
add('late version 4 wrong model name',surrenderText(r=>{r.model.name='common_shoe_two_hand';}),'unsupported_record');
add('late version 4 wrong model version',surrenderText(r=>{r.model.version=2;}),'unsupported_record');
add('late version 4 wrong continuation',surrenderText(r=>{r.model.surrender_after_hit=true;}),'unsupported_record');
add('late version 4 fractional model version',surrenderText().replace('"name":"post_peek_late_surrender","version":1',
  '"name":"post_peek_late_surrender","version":1.0'),'invalid_input');
add('late version 4 fractional draw count',surrenderText().replace('"surrender_draws":0','"surrender_draws":0.0'),'invalid_input');
add('late version 4 Boolean state cap',surrenderText(r=>{r.model.enumeration_state_limit=true;}),'invalid_input');
add('late version 4 oversized state cap',surrenderText(r=>{r.model.enumeration_state_limit=100001;}),'unsupported_record');
const resplitText=update=>{
  const saved=structuredClone(baseline);
  saved.schema.version=5;
  Object.assign(saved.state,{cards:['8','8'],dealer_up:'6',total:16,soft:false,
    action_controls:{can_double:true,can_split:true}});
  saved.state.shoe.counts=[0,0,0,0,0,0,0,8,0,0];
  Object.assign(saved.rules,{max_hands:3,surrender:false,resplit_aces:false,hit_split_aces:false});
  saved.model=resplitModelFor('6',100000n);
  saved.decision={action:'P',action_name:'SPLIT',evs:{S:1,H:-1,D:-2,P:3},
    margin:2,units:'original_wager',whole_game_estimate:null};
  if (update) update(saved);
  return JSON.stringify(saved,(_,value)=>typeof value==='bigint' ? Number(value) : value);
};
add('resplit version 5 complete record',resplitText());
for (const [double,pair] of [[true,true],[false,true],[true,false],[false,false]]) {
  add(`resplit version 5 controls ${double}/${pair}`,resplitText(r=>{
    r.state.action_controls={can_double:double,can_split:pair};
    if (!double) delete r.decision.evs.D;
    if (!pair) {delete r.decision.evs.P;r.decision.action='S';r.decision.action_name='STAND';}
  }));
}
add('resplit version 5 altered finite answer',resplitText(r=>{r.decision.evs.P=0;r.decision.margin=99;}));
add('resplit version 5 stored unavailable P',resplitText(r=>{r.state.action_controls.can_split=false;}));
add('resplit version 5 omitted permitted P',resplitText(r=>{
  delete r.decision.evs.P;r.decision.action='S';r.decision.action_name='STAND';
}));
add('resplit version 5 missing controls',resplitText(r=>{delete r.state.action_controls;}),'invalid_input');
add('resplit version 5 surrender control forbidden',resplitText(r=>{r.state.action_controls.can_surrender=false;}),'invalid_input');
add('resplit version 5 R action forbidden',resplitText(r=>{r.decision.evs.R=-0.5;}),'invalid_input');
for (const key of ['can_double','can_split']) {
  add(`resplit version 5 nonboolean ${key}`,resplitText(r=>{r.state.action_controls[key]=1;}),'invalid_input');
}
for (const [key,value] of [['max_hands',2],['resplit_aces',true],['hit_split_aces',true],['surrender',true]]) {
  add(`resplit version 5 unsupported rule ${key}`,resplitText(r=>{r.rules[key]=value;}),'unsupported_record');
}
add('resplit version 5 nonpair',resplitText(r=>{r.state.cards=['8','9'];r.state.total=17;}),'unsupported_record');
add('resplit version 5 original aces excluded',resplitText(r=>{r.state.cards=['A','A'];r.state.total=12;r.state.soft=true;}),'unsupported_record');
add('resplit version 5 split continuation excluded',resplitText(r=>{r.state.is_split_hand=true;r.state.hand_count=2;}),'unsupported_record');
add('resplit version 5 fewer than three unseen',resplitText(r=>{r.state.shoe.counts[7]=2;}),'unsupported_record');
add('resplit version 5 more than twenty unseen',resplitText(r=>{r.state.shoe.counts[7]=21;}),'unsupported_record');
add('resplit version 5 fresh origin',resplitText(r=>{
  r.rules.decks=1;r.state.shoe.source='fresh_minus_visible';r.state.shoe.counts=[4,4,4,4,4,3,4,2,4,16];
}),'unsupported_record');
add('resplit version 5 missing declaration',resplitText(r=>{delete r.model.split_child_order;}),'invalid_input');
add('resplit version 5 unknown declaration',resplitText(r=>{r.model.extra=true;}),'invalid_input');
for (const key of ['name','dealer_information','player_last_draw','split','split_deal_order','split_child_order',
  'split_eligibility','split_aces','split_twenty_one','split_objective','split_exhaustion']) {
  add(`resplit version 5 changed declaration ${key}`,resplitText(r=>{r.model[key]='different';}),'unsupported_record');
}
for (const [key,value] of [['version',2],['split_max_hands',4],['split_max_extra_resplits',2],
  ['split_cooperative_seconds',9],['enumeration_state_limit',100001]]) {
  add(`resplit version 5 unsupported ${key}`,resplitText(r=>{r.model[key]=value;}),'unsupported_record');
}
add('resplit version 5 numeric cooperative ten',resplitText().replace('"split_cooperative_seconds":10',
  '"split_cooperative_seconds":10.0'));
add('resplit version 5 Boolean cooperative seconds',resplitText(r=>{r.model.split_cooperative_seconds=true;}),'invalid_input');
add('resplit version 5 Boolean state cap',resplitText(r=>{r.model.enumeration_state_limit=true;}),'invalid_input');
add('resplit version 5 fractional model version',resplitText().replace('"name":"common_shoe_bounded_resplit","version":1',
  '"name":"common_shoe_bounded_resplit","version":1.0'),'invalid_input');
add('resplit version 5 fractional hand cap',resplitText().replace('"split_max_hands":3','"split_max_hands":3.0'),'invalid_input');
add('resplit version 5 wrong derived hole exclusion',resplitText(r=>{r.model.hole_rank_excluded_by_peek='T';}),'invalid_input');
for (const version of [1,2,3]) {
  const create=version===3 ? commonText : change;
  add(`legacy version ${version} forbids R`,create(r=>{
    if (version===2) controlled(r);
    r.decision.evs.R=-0.5;r.decision.action='R';r.decision.action_name='SURRENDER';
  }),'invalid_input');
  if (version!==1) add(`legacy version ${version} forbids surrender control`,create(r=>{
    if (version===2) controlled(r);
    r.state.action_controls.can_surrender=false;
  }),'invalid_input');
}
for (const value of [null,[],true,0,'false']) {
  add(`version 2 invalid control object ${JSON.stringify(value)}`,change(r=>{controlled(r);r.state.action_controls=value;}),'invalid_input');
}
for (const key of ['can_double','can_split']) for (const value of [null,0,1,'false',[]]) {
  add(`version 2 invalid ${key} ${JSON.stringify(value)}`,change(r=>{controlled(r);r.state.action_controls[key]=value;}),'invalid_input');
}
add('duplicate escaped control key',change(r=>controlled(r)).replace('"can_double":true','"can_double":true,"\\u0063an_double":false'),'invalid_input');

const eligibility=(name,update,expected,rewrite=text=>text)=>{
  add(`eligibility: ${name}`,rewrite(change(update)));
  cases.at(-1).expectedPermitted=expected;
};
const unseen=(r,count)=>{r.state.shoe.counts=[0,count,0,0,0,0,0,0,0,0];};
const pair=r=>{r.state.cards=['8','8'];r.state.total=16;};
const split=r=>{r.state.is_split_hand=true;r.state.hand_count=2;};
eligibility('one unseen reserves the hole',r=>unseen(r,1),['S']);
eligibility('two unseen permits one draw',r=>unseen(r,2),['H','S','D']);
eligibility('three unseen nonpair',r=>unseen(r,3),['H','S','D']);
eligibility('pair needs three unseen to split',r=>{pair(r);unseen(r,2);},['H','S','D']);
eligibility('pair with three unseen',r=>{pair(r);unseen(r,3);},['H','S','D','P']);
for (const [double,maySplit] of [[true,true],[false,true],[true,false],[false,false]]) {
  eligibility(`controlled pair ${double}/${maySplit}`,r=>{
    pair(r);unseen(r,3);controlled(r,double,maySplit);
  },['H','S',...(double ? ['D'] : []),...(maySplit ? ['P'] : [])]);
}
eligibility('natural 21 settles',r=>{r.state.cards=['A','T'];r.state.total=21;r.state.soft=true;},['S']);
eligibility('three-card 21 settles',r=>{r.state.cards=['7','7','7'];r.state.total=21;},['S']);
eligibility('split 21 settles',r=>{split(r);r.state.cards=['A','T'];r.state.total=21;r.state.soft=true;},['S']);
eligibility('three cards cannot double',r=>{r.state.cards=['T','2','2'];},['H','S']);
eligibility('split double after split allowed',r=>split(r),['H','S','D']);
eligibility('split double after split refused',r=>{split(r);r.rules.das=false;},['H','S']);
eligibility('shared hand cap reached',r=>{split(r);pair(r);r.state.hand_count=4;},['H','S','D']);
eligibility('one shared hand remains',r=>{split(r);pair(r);r.state.hand_count=3;},['H','S','D','P']);
eligibility('split ace first card frozen',r=>{split(r);r.state.cards=['A','4'];r.state.total=15;r.state.soft=true;},['S']);
eligibility('split four drew ace unfrozen',r=>{split(r);r.state.cards=['4','A'];r.state.total=15;r.state.soft=true;},['H','S','D']);
eligibility('split ace may hit',r=>{split(r);r.state.cards=['A','4'];r.state.total=15;r.state.soft=true;r.rules.hit_split_aces=true;},['H','S','D']);
const aces=r=>{split(r);r.state.cards=['A','A'];r.state.total=12;r.state.soft=true;};
eligibility('frozen ace pair cannot resplit',r=>aces(r),['S']);
eligibility('frozen ace pair may resplit',r=>{aces(r);r.rules.resplit_aces=true;},['S','P']);
eligibility('frozen ace pair needs two initial draws',r=>{aces(r);r.rules.resplit_aces=true;unseen(r,2);},['S']);
eligibility('unfrozen ace pair may hit double and resplit',r=>{aces(r);r.rules.resplit_aces=true;r.rules.hit_split_aces=true;},['H','S','D','P']);
eligibility('unfrozen ace pair cannot resplit',r=>{aces(r);r.rules.hit_split_aces=true;},['H','S','D']);
eligibility('unfrozen split ace three cards',r=>{split(r);r.state.cards=['A','2','3'];r.state.total=16;r.state.soft=true;r.rules.hit_split_aces=true;},['H','S']);
eligibility('huge retained counts remain integer eligibility',r=>{pair(r);unseen(r,0);},['H','S','D','P'],
  text=>text.replace('"counts":[0,0,','"counts":[0,'+'1'+'0'.repeat(400)+','));
eligibility('exact hand allowance above Number range',r=>{split(r);pair(r);r.state.hand_count=3;},['H','S','D','P'],
  text=>text.replace('"hand_count":3','"hand_count":9007199254740992').replace('"max_hands":4','"max_hands":9007199254740993'));
eligibility('exact hand cap above Number range',r=>{split(r);pair(r);r.state.hand_count=3;},['H','S','D'],
  text=>text.replace('"hand_count":3','"hand_count":9007199254740993').replace('"max_hands":4','"max_hands":9007199254740993'));

for (const item of cases) test(`admission: ${item.name}`,()=>{
  if (item.status==='accepted') {
    const admitted=inspectRecord(item.bytes);
    if (item.expectedPermitted) assert.deepEqual(permittedActions(admitted),item.expectedPermitted);
  }
  else assert.throws(()=>inspectRecord(item.bytes),error=>error.status===item.status);
});
test('shared corpus agrees with existing Python admission and schema declarations',()=>{
  const python=process.env.SOLVER_ADMISSION_PYTHON ?? 'python';
  const result=spawnSync(python,['tests/record_inspection_admission.py'],{
    cwd:fileURLToPath(new URL('../',import.meta.url)),
    input:JSON.stringify(cases.map(item=>({bytes:Array.from(item.bytes)}))),encoding:'utf8',maxBuffer:4*1024*1024,timeout:30000,
    env:{...process.env,PYTHONPATH:fileURLToPath(new URL('../',import.meta.url))}
  });
  assert.equal(result.status,0,result.stderr || String(result.error));
  const oracle=JSON.parse(result.stdout);
  assert.deepEqual(oracle.outcomes,cases.map(item=>item.pythonStatus));
  assert.equal(oracle.eligibility_scope,'best_action action keys with four EV routines stubbed to zero; schema 4 terminal R from admitted current permission');
  assert.deepEqual(oracle.permitted,cases.map(item=>item.status==='accepted' ? permittedActions(inspectRecord(item.bytes)) : null),
    'Eligibility parity only, not EV or mathematical validation');
  const plain=value=>JSON.parse(JSON.stringify(value,(_,item)=>typeof item==='bigint' ? Number(item) : item));
  assert.deepEqual(oracle.contract,{max_bytes:MAX_RECORD_BYTES,max_depth:MAX_RECORD_DEPTH,schema_version:1,controlled_schema_version:2,common_schema_version:3,
    surrender_schema_version:4,resplit_schema_version:5,rule_fields:RULE_FIELDS,ranks:RANKS,actions:ACTION_NAMES,surrender_actions:SURRENDER_ACTION_NAMES,
    models:Object.fromEntries(RANKS.map(rank=>[rank,modelFor(rank)])),
    surrender_models:Object.fromEntries(RANKS.map(rank=>[rank,plain(surrenderModelFor(rank,100000n))])),
    resplit_models:Object.fromEntries(RANKS.map(rank=>[rank,plain(resplitModelFor(rank,100000n))]))});
});
test('exact large integer counts survive inspection and input-first comparison',()=>{
  const left=inspectRecord(cases.find(item=>item.name==='unsafe exact integer count').bytes);
  const right=inspectRecord(cases.find(item=>item.name==='400-digit count').bytes);
  assert.equal(left.state.shoe.counts[0],9007199254740993n);
  assert.equal(right.state.shoe.counts[0],10n**400n);
  assert.equal(display(right.state.shoe.counts[0]),'1'+'0'.repeat(400));
  const result=compareRecords(left,right);
  assert.deepEqual(result.inputs,[['state.shoe.counts.A',9007199254740993n,10n**400n]]);
  assert.equal(modeledRows(left).length,43);
});
test('comparison distinguishes absent actions, one-ULP answers and input order',()=>{
  const left=inspectRecord(fixture);
  const right=inspectRecord(change(r=>{r.state.cards.reverse();r.decision.evs.H=-0.5916666666666667;delete r.decision.evs.D;}));
  const result=compareRecords(left,right);
  assert.deepEqual(result.inputs[0],['state.cards',['T','4'],['4','T']]);
  assert.equal(result.evs.find(row=>row.action==='H').matches,false);
  assert.notEqual(result.evs.find(row=>row.action==='H').delta,0);
  assert.equal(result.evs.find(row=>row.action==='D').right,null);
  assert.equal(result.evs.find(row=>row.action==='D').delta,null);
});
test('metadata-only change does not become a modeled input change',()=>{
  const result=compareRecords(inspectRecord(fixture),inspectRecord(change(r=>{r.package.version='future';})));
  assert.deepEqual(result.inputs,[]);assert.deepEqual(result.metadata,[['package.version','0.1.0','future']]);
  assert.ok(result.evs.every(row=>row.matches));
});
test('old and common model fields compare as a union in both directions',()=>{
  const legacy=inspectRecord(fixture),common=inspectRecord(commonText());
  for (const [left,right] of [[legacy,common],[common,legacy]]) {
    const result=compareRecords(left,right);
    assert.equal(result.model_compatible,false);
    const limit=result.inputs.find(([key])=>key==='model.enumeration_state_limit');
    assert.ok(limit);
    assert.deepEqual(limit.slice(1),left===common ? [100000n,undefined] : [undefined,100000n]);
    assert.ok(result.inputs.some(([key])=>key==='model.split'));
    assert.equal(modeledRows(common).filter(([key])=>key.startsWith('model.')).length,12);
  }
  assert.equal(compareRecords(common,inspectRecord(commonText())).model_compatible,true);
});
test('signed zeros compare by numerical equality and overflowing deltas are explicit',()=>{
  const left=inspectRecord(change(r=>{r.decision.margin=0;r.decision.evs.H=-1e308;}));
  const right=inspectRecord(change(r=>{r.decision.margin=0;r.decision.evs.H=1e308;}).replace('"margin":0','"margin":-0.0'));
  const result=compareRecords(left,right);
  assert.equal(result.margin.matches,true);
  assert.equal(result.evs.find(row=>row.action==='H').delta,'outside finite delta range');
});
test('direct string encoding refuses lone surrogates instead of replacing them',()=>{
  assert.throws(()=>inspectRecord(fixture+'\ud800'),/valid UTF-8/);
});
test('a replaced, cleared or failed file cannot restore stale recorded state',async()=>{
  const events=[],pending=[];
  const slot=recordSlot(state=>events.push(state),file=>new Promise((resolve,reject)=>pending.push({file,resolve,reject})));
  const first=slot.select({name:'first.json',size:100});
  const second=slot.select({name:'second.json',size:100});
  pending[1].resolve(bytes(fixture));await second;
  assert.equal(events.at(-1).name,'second.json');assert.ok(events.at(-1).record);
  pending[0].resolve(bytes(fixture));await first;
  assert.equal(events.at(-1).name,'second.json');
  const late=slot.select({name:'late.json',size:100});slot.clear();
  pending[2].resolve(bytes(fixture));await late;
  assert.equal(events.at(-1).record,null);assert.equal(events.at(-1).name,'');
  const replacement=slot.select({name:'invalid.json',size:100});
  assert.equal(events.at(-1).record,null);
  pending[3].resolve(bytes('{}'));await replacement;
  assert.equal(events.at(-1).status,'error');assert.equal(events.at(-1).record,null);
  const unreadable=slot.select({name:'unreadable.json',size:100});
  pending[4].reject(new Error('private OS detail'));await unreadable;
  assert.equal(events.at(-1).message,'io_error: The local file could not be read.');
  const before=pending.length;
  await slot.select({name:'oversized.json',size:MAX_RECORD_BYTES+1});
  assert.equal(pending.length,before);assert.equal(events.at(-1).status,'error');
});
test('declared browser integer digit limit is explicit',()=>assert.equal(MAX_INTEGER_DIGITS,4300));
test('parsing guards report the actual duplicate, depth and size boundaries',()=>{
  for (const name of ['duplicate escaped root key','duplicate nested escaped key','duplicate action key']) {
    assert.throws(()=>inspectRecord(cases.find(item=>item.name===name).bytes),/duplicate JSON key/);
  }
  assert.throws(()=>inspectRecord(cases.find(item=>item.name==='depth nine refused before allocation').bytes),/container depth 8/);
  assert.throws(()=>inspectRecord(cases.find(item=>item.name==='byte limit exceeded').bytes),/65536 UTF-8 bytes/);
  assert.throws(()=>inspectRecord(cases.find(item=>item.name==='browser integer-token limit').bytes),/browser limit of 4300/);
});
test('unavailable and omitted supplied actions stay inspectable with explicit differences',()=>{
  const admitted=inspectRecord(change(r=>{r.decision.evs={S:0,P:99};r.decision.action='P';r.decision.action_name='SPLIT';r.decision.margin=88;}));
  assert.deepEqual(recordedActionDifferences(admitted),{permitted:['H','S','D'],omitted:['H','D'],unavailable:['P'],recommendation_unavailable:true});
  assert.equal(admitted.decision.action,'P');assert.equal(admitted.decision.evs.P,99);assert.equal(admitted.decision.margin,88);
  const ordinary=inspectRecord(fixture);
  assert.deepEqual(recordedActionDifferences(ordinary),{permitted:['H','S','D'],omitted:[],unavailable:[],recommendation_unavailable:false});
});
test('comparison derives each input eligibility without replacing recorded action keys',()=>{
  const left=inspectRecord(fixture),right=inspectRecord(change(r=>{unseen(r,1);}));
  const compared=compareRecords(left,right);
  assert.deepEqual(compared.permitted,{left:['H','S','D'],right:['S']});
  assert.deepEqual(compared.evs.map(row=>row.action),['H','S','D']);
  assert.equal(right.decision.action,'H');
});
test('version 1 and declared true/true version 2 compare effective defaults in both directions',()=>{
  const legacy=inspectRecord(fixture),declared=inspectRecord(change(r=>controlled(r)));
  assert.equal(Object.hasOwn(legacy.state,'action_controls'),false);
  for (const [left,right] of [[legacy,declared],[declared,legacy]]) {
    const result=compareRecords(left,right);
    assert.deepEqual(result.inputs,[]);
    assert.deepEqual(result.metadata,[['schema.version',left.schema.version,right.schema.version]]);
    assert.deepEqual(result.permitted,{left:['H','S','D'],right:['H','S','D']});
  }
});
test('control differences are scalar modeled rows before answer differences',()=>{
  const left=inspectRecord(change(r=>controlled(r,false,true)));
  const right=inspectRecord(change(r=>controlled(r,true,false)));
  assert.deepEqual(compareRecords(left,right).inputs,[
    ['state.action_controls.can_double',false,true],['state.action_controls.can_split',true,false]
  ]);
  const rows=modeledRows(left);
  assert.deepEqual(rows.slice(6,8),[['state.action_controls.can_double',false],['state.action_controls.can_split',true]]);
});
test('disabled absent actions are not omissions, but stored disabled answers remain visible',()=>{
  const admitted=inspectRecord(change(r=>{controlled(r,false,false);delete r.decision.evs.D;}));
  assert.deepEqual(recordedActionDifferences(admitted),{
    permitted:['H','S'],omitted:[],unavailable:[],recommendation_unavailable:false
  });
  const altered=inspectRecord(change(r=>{
    controlled(r,false,false);r.decision.action='D';r.decision.action_name='DOUBLE';
  }));
  assert.deepEqual(recordedActionDifferences(altered),{
    permitted:['H','S'],omitted:[],unavailable:['D'],recommendation_unavailable:true
  });
  assert.equal(altered.decision.action,'D');assert.equal(altered.decision.evs.D,baseline.decision.evs.D);
});

test('late vocabulary and controls preserve stored absence and old model admission',()=>{
  const late=inspectRecord(surrenderText()),legacy=inspectRecord(fixture);
  assert.equal(Object.hasOwn(ACTION_NAMES,'R'),false);
  assert.deepEqual(recordActionNames(late),SURRENDER_ACTION_NAMES);
  assert.deepEqual(permittedActions(late),['S','H','D','R']);
  assert.equal(Object.hasOwn(legacy.state,'action_controls'),false);
  assert.equal(actionControls(legacy).can_surrender,false);
  const rows=new Map(modeledRows(legacy));
  assert.equal(rows.get('effective_action_controls.can_surrender'),false);
  assert.equal(rows.get('state.action_controls.can_surrender'),undefined);
  assert.deepEqual(recordedActionDifferences(inspectRecord(surrenderText(r=>{
    r.state.action_controls.can_surrender=false;
  }))),{permitted:['S','H','D'],omitted:[],unavailable:['R'],recommendation_unavailable:true});
});

test('late and prior mathematical families are incompatible in both comparison directions',()=>{
  const late=inspectRecord(surrenderText());
  for (const previous of [inspectRecord(fixture),inspectRecord(commonText())]) {
    for (const [left,right] of [[previous,late],[late,previous]]) {
      const compared=compareRecords(left,right);
      assert.equal(compared.model_compatible,false);
      assert.ok(compared.inputs.some(([key])=>key==='model.decision_phase'));
      assert.ok(compared.inputs.some(([key])=>key==='model.surrender'));
      const effective=compared.inputs.find(([key])=>key==='effective_action_controls.can_surrender');
      const stored=compared.inputs.find(([key])=>key==='state.action_controls.can_surrender');
      assert.deepEqual(effective.slice(1),left===late ? [true,false] : [false,true]);
      assert.deepEqual(stored.slice(1),left===late ? [true,undefined] : [undefined,true]);
      const r=compared.evs.find(row=>row.action==='R');
      assert.equal(left===late ? r.right : r.left,null);
      assert.equal(r.delta,null);
    }
  }
});

test('same late family separates permission, absence and operational cap changes',()=>{
  const offered=inspectRecord(surrenderText());
  const disabled=inspectRecord(surrenderText(r=>{
    r.state.action_controls.can_surrender=false;delete r.decision.evs.R;
    r.decision.action='S';r.decision.action_name='STAND';r.decision.margin=0;
    r.model.enumeration_state_limit=99;
  }));
  const compared=compareRecords(offered,disabled);
  assert.equal(compared.model_compatible,true);
  assert.deepEqual(compared.inputs,[
    ['effective_action_controls.can_surrender',true,false],
    ['state.action_controls.can_surrender',true,false],
    ['model.enumeration_state_limit',100000n,99n]
  ]);
  assert.deepEqual(recordedActionDifferences(disabled),{
    permitted:['S','H','D'],omitted:[],unavailable:[],recommendation_unavailable:false
  });
  assert.equal(compared.evs.find(row=>row.action==='R').right,null);
});

test('late supplied near-equal answers remain passive comparison data',()=>{
  const tied=surrenderText(r=>{
    r.state.cards=['T','8'];r.state.total=18;r.state.shoe.counts=[...Array(7).fill(0),2,0,2];
    r.decision={...r.decision,action:'S',action_name:'STAND',evs:{S:-0.5,H:-1,D:-2,R:-0.5},margin:0};
  });
  const changed=JSON.parse(tied);changed.decision.evs.R=-0.49999999999999994;
  changed.decision.action='R';changed.decision.action_name='SURRENDER';changed.decision.margin=2**-54;
  const compared=compareRecords(inspectRecord(tied),inspectRecord(JSON.stringify(changed)));
  assert.equal(compared.model_compatible,true);assert.deepEqual(compared.inputs,[]);
  assert.equal(compared.action.matches,false);
  assert.equal(compared.evs.find(row=>row.action==='R').matches,false);
  assert.equal(compared.evs.find(row=>row.action==='R').delta,2**-54);
});

test('resplit and previous families expose complete identities in either comparison order',()=>{
  const resplit=inspectRecord(resplitText());
  assert.deepEqual(recordActionNames(resplit),ACTION_NAMES);
  assert.deepEqual(permittedActions(resplit),['H','S','D','P']);
  assert.equal(actionControls(resplit).can_surrender,false);
  assert.equal(new Map(modeledRows(resplit)).get('state.action_controls.can_surrender'),undefined);
  for (const previous of [inspectRecord(fixture),inspectRecord(commonText()),inspectRecord(surrenderText())]) {
    for (const [left,right] of [[previous,resplit],[resplit,previous]]) {
      const compared=compareRecords(left,right);
      assert.equal(compared.model_compatible,false);
      for (const field of ['split','split_max_hands','split_max_extra_resplits','split_child_order',
        'split_deal_order','split_eligibility','split_twenty_one','split_objective','split_exhaustion']) {
        const modeled=new Map(modeledRows(resplit));
        assert.equal(modeled.has(`model.${field}`),true,field);
        assert.equal(modeled.get(`model.${field}`),resplit.model[field],field);
        // Different families may share an identical strict exhaustion clause.
        // Changed-input rows contain actual differences, not all declarations.
        assert.equal(compared.inputs.some(([key])=>key===`model.${field}`),
          left.model[field]!==right.model[field],field);
      }
      if (previous.schema.version===4n) {
        const r=compared.evs.find(row=>row.action==='R');
        assert.equal(left===resplit ? r.left : r.right,null);
        assert.equal(r.delta,null);
        const p=compared.evs.find(row=>row.action==='P');
        assert.equal(left===resplit ? p.right : p.left,null);
        assert.equal(p.delta,null);
      }
    }
  }
});

test('resplit current permissions and cap differences stay separate from saved answers',()=>{
  const offered=inspectRecord(resplitText());
  const disabled=inspectRecord(resplitText(r=>{
    r.state.action_controls.can_split=false;delete r.decision.evs.P;
    r.decision.action='S';r.decision.action_name='STAND';r.model.enumeration_state_limit=99;
  }));
  for (const [left,right] of [[offered,disabled],[disabled,offered]]) {
    const compared=compareRecords(left,right);
    assert.equal(compared.model_compatible,true);
    assert.ok(compared.inputs.some(([key])=>key==='state.action_controls.can_split'));
    assert.ok(compared.inputs.some(([key])=>key==='model.enumeration_state_limit'));
    assert.equal(compared.evs.find(row=>row.action==='P').delta,null);
  }
  assert.deepEqual(recordedActionDifferences(disabled),{
    permitted:['H','S','D'],omitted:[],unavailable:[],recommendation_unavailable:false
  });
  const stored=inspectRecord(resplitText(r=>{r.state.action_controls.can_split=false;}));
  assert.deepEqual(recordedActionDifferences(stored),{
    permitted:['H','S','D'],omitted:[],unavailable:['P'],recommendation_unavailable:true
  });
  const tied=inspectRecord(resplitText(r=>{
    r.decision.evs.P=1;r.decision.action='S';r.decision.action_name='STAND';r.decision.margin=0;
  }));
  const changed=inspectRecord(resplitText(r=>{
    r.decision.evs.P=1.0000000000000002;r.decision.margin=2**-52;
  }));
  const compared=compareRecords(tied,changed);
  assert.deepEqual(compared.inputs,[]);
  assert.equal(compared.action.matches,false);
  assert.equal(compared.evs.find(row=>row.action==='P').delta,2**-52);
});
