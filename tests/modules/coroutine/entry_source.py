"""Whole entry source inverse; Native effect/conversion positions stay fixed."""
import re
from make_coroutine_entry import DRIVER
PATTERN=re.compile(r'#if defined\(SWOOLE_RS_COROUTINE\) && SWOOLE_RS_COROUTINE // SWR_ENTRY_BEGIN\n(.*?)\n#else // SWR_ENTRY_NATIVE\n(.*?)\n#endif // SWR_ENTRY_END',re.S)
def restore_entry(source):return PATTERN.sub(lambda m:m[2],source).replace(DRIVER,'',1)
def verify_entry(before,after):
 if len(list(PATTERN.finditer(after)))!=2 or after.count(DRIVER)!=1 or restore_entry(after)!=before:
  raise ValueError('Unrelated source changed outside whole entry control/effects')
 if DRIVER.count('Coroutine::create(fn, arg)')!=1 or 'template <typename Function>'not in DRIVER:
  raise ValueError('Native function conversion must remain only at actual create effect')
 return dict(whole_source_inverse=True,typed_Native_effect_driver=True,
             no_early_stdfunction_conversion=True,no_runtime_executed=True)
