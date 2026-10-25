"""Exact complete bailout source and foreign-origin access closure."""
import re
from make_coroutine_bailout import CHOSEN
PATTERN=re.compile(r'#if defined\(SWOOLE_RS_COROUTINE\) && SWOOLE_RS_COROUTINE // SWR_BAILOUT_BEGIN\n(.*?)\n#else // SWR_BAILOUT_NATIVE\n(.*?)\n#endif // SWR_BAILOUT_END',re.S)
def restore_bailout(source):return PATTERN.sub(lambda m:m[2],source)
def verify_bailout(before,after):
 matches=list(PATTERN.finditer(after))
 if len(matches)!=1 or matches[0][1]!=CHOSEN or restore_bailout(after)!=before:
  raise ValueError('Whole bailout source differs outside exact accepted Native effects')
 old=matches[0][2]
 for text in ['static BailoutCallback fn = []()', 'on_bailout = fn;', 'swoole_error("bailout without callback function");', 'on_bailout = func;', 'exit(SW_CORO_BAILOUT_EXIT_CODE);']:
  if text not in old or text not in CHOSEN:raise ValueError('Original Native effect missing:'+text)
 if 'reinterpret_cast<const unsigned char *>(&co->origin)'not in CHOSEN or 'co->origin)'not in CHOSEN:
  raise ValueError('Exact forward member-address derivation missing')
 if 'while (co->'in CHOSEN or 'get_origin('in CHOSEN:raise ValueError('Native per-hop traversal remains')
 order=['case 0:', 'case 1:', 'function_present = !!func;', 'case 2:', 'case 3:', 'on_bailout = func;', 'origin_offset = ', 'case 4:', '->yield();','exit('];last=-1
 for text in order:last=CHOSEN.index(text,last+1)
 return dict(source_inverse=True,original_native_effects=True,full_walk_in_rust=True,
             forward_member_address_only=True,no_header_or_object_representation_change=True,
             actual_callback_bailout_executed=False)
