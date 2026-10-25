"""Whole qualified registry print source inverse and Native effect boundary."""
import re
from make_coroutine_print import CHOSEN,PREFIX
PATTERN=re.compile(re.escape(PREFIX)+r'(.*?)\n#else // SWR_PRINT_NATIVE\n(.*?)\n#endif // SWR_PRINT_END',re.S)
def restore_print(source):return PATTERN.sub(lambda m:m[2],source)
def verify_print(before,after):
 m=list(PATTERN.finditer(after))
 if len(m)!=1 or m[0][1]!=CHOSEN or restore_print(after)!=before:raise ValueError('Unrelated bytes changed outside whole qualified print operation')
 if 'for (auto &'in CHOSEN or 'get_state('in CHOSEN:raise ValueError('Native per-entry algorithm/status getter remains')
 if 'sw_printf("Coroutine\\t%ld\\t%s\\n", step.cid, step.label);'not in CHOSEN:raise ValueError('Original output format/argument order missing')
 if CHOSEN.count('reinterpret_cast<const Coroutine *>(step.token)')!=2:raise ValueError('Typed frozen-token projection must remain Native')
 return dict(whole_source_inverse=True,real_owner_loop_in_rust=True,genuine_Native_map_fallback_unchanged=True,
             Native_only_pointer_projection=True,no_snapshot_or_prefetch=True,actual_print_executed=False)
