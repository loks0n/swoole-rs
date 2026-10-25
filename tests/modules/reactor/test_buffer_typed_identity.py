"""No compiler or engine execution: typed identity and unchanged assertion ledger."""
import hashlib
from pathlib import Path
import subprocess
import unittest
import buffer_typed_identity as identity

class TypedBufferIdentity(unittest.TestCase):
    def inputs(self):
        files={name:b'header' for name in (*identity.SOURCES,*identity.PATCHES)}
        files[identity.SOURCES[1]]='\n'.join('pub fn swr_v1_buffer_typed_'+op+'() {}' for op in identity.OPERATIONS).encode()
        files[identity.PATCHES[1]]='\n'.join('+ check_buffer_status(swr_v1_buffer_typed_'+op+'(args));' for op in identity.OPERATIONS).encode()
        files[identity.PATCHES[2]]=b'+ buffer->typed_front();\n+ buffer->typed_consume(args);\n+ buffer->typed_sendfile(args);'
        inputs={'buffer_typed_requested':True,'modules':['buffer','reactor'],'rust_sources_sha256':{n:hashlib.sha256(files[n]).hexdigest() for n in identity.SOURCES},'patches':[{'path':n,'sha256':hashlib.sha256(files[n]).hexdigest()} for n in identity.PATCHES]}
        return inputs,files
    def test_requests_are_literal_and_native_control_stays_off(self):
        inputs,_=self.inputs();self.assertTrue(identity.requested(inputs,True));self.assertFalse(identity.requested({},False))
        for bad in [{},dict(inputs,buffer_typed_requested=1),dict(inputs,buffer_typed_requested=False),dict(inputs,modules=['reactor'])]:
            with self.assertRaises(ValueError):identity.requested(bad,True)
        with self.assertRaises(ValueError):identity.requested(inputs,False)
    def test_configuration_is_literal_not_presence(self):
        self.assertTrue(identity.configured('#define SWOOLE_RS_BUFFER_TYPED 1',True))
        for text in ['', '#define SWOOLE_RS_BUFFER_TYPED 0']:
            self.assertFalse(identity.configured(text,False))
            with self.assertRaises(ValueError):identity.configured(text,True)
        for text in ['#define SWOOLE_RS_BUFFER_TYPED MAYBE','#define SWOOLE_RS_BUFFER_TYPED 1\n#define SWOOLE_RS_BUFFER_TYPED 1']:
            with self.assertRaises(ValueError):identity.configured(text,True)
    def test_source_closure_and_every_actual_operation_caller(self):
        inputs,files=self.inputs();self.assertEqual(len(identity.prepared(inputs,files)),5)
        for name in files:
            changed=dict(files);changed[name]+=b'changed'
            with self.assertRaises(ValueError):identity.prepared(inputs,changed)
        for op in identity.OPERATIONS:
            inputs,files=self.inputs();name=identity.PATCHES[1];files[name]=files[name].replace(('+ check_buffer_status(swr_v1_buffer_typed_'+op+'(args));').encode(),b'+ // excluded')
            inputs['patches'][1]['sha256']=hashlib.sha256(files[name]).hexdigest()
            with self.assertRaises(ValueError):identity.prepared(inputs,files)
    def test_repeated_overlay_and_commented_call_do_not_qualify(self):
        inputs,files=self.inputs();inputs['patches']*=2
        with self.assertRaises(ValueError):identity.prepared(inputs,files)
        inputs,files=self.inputs();name=identity.PATCHES[2];files[name]=files[name].replace(b'+ buffer->typed_front();',b'+ // buffer->typed_front();');inputs['patches'][2]['sha256']=hashlib.sha256(files[name]).hexdigest()
        with self.assertRaises(ValueError):identity.prepared(inputs,files)
    def test_real_constructor_front_and_rust_origins_are_required(self):
        result={'buffer_constructor_image':'/selected.so','typed_buffer_compiled':1,'typed_buffer_front_image':'/selected.so'}
        result.update({('typed_buffer_front_image_rust' if op=='front' else 'typed_buffer_'+op+'_image'):'/selected.so' for op in identity.OPERATIONS})
        imports=identity.CONSTRUCTOR+'\n'+identity.FRONT
        identity.consumer(result,imports,'/selected.so',True)
        for key in result:
            bad=dict(result);bad[key]='wrong'
            with self.assertRaises(ValueError):identity.consumer(bad,imports,'/selected.so',True)
        with self.assertRaises(ValueError):identity.consumer(result,identity.CONSTRUCTOR,'/selected.so',True)
        identity.consumer({'buffer_constructor_image':'/native.so','typed_buffer_compiled':0},identity.CONSTRUCTOR,'/native.so',False)
if __name__=='__main__':unittest.main()
